"""Local Ollama structured generation with bounded input and immutable call checkpoints."""

from hashlib import sha256
from importlib.resources import files
import json
import time

import httpx

from .config import Settings, SetupError
from .schemas import LLMCall, LLMModel


FEEDBACK_PREFIX = "The previous answer failed validation: "
FEEDBACK_SUFFIX = ". Return corrected JSON."
FEEDBACK_ERROR_BYTES = 400
FEEDBACK_BYTES = len((FEEDBACK_PREFIX + FEEDBACK_SUFFIX).encode()) + FEEDBACK_ERROR_BYTES


def repair_feedback(error):
    detail = str(error).encode("utf-8")[:FEEDBACK_ERROR_BYTES].decode("utf-8", errors="ignore")
    return FEEDBACK_PREFIX + detail + FEEDBACK_SUFFIX


def compact(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def digest(value) -> str:
    return sha256(compact(value).encode("utf-8")).hexdigest()


def generation_schema(contract, payload):
    schema = contract.model_json_schema()
    sources = [*payload.get("segments", []), *payload.get("context", []), *payload.get("sources", [])]
    ids = list(dict.fromkeys(item["id"] for item in sources if isinstance(item, dict) and "id" in item))
    if ids:
        schema.setdefault("$defs", {})["SourceID"] = {"type": "string", "enum": ids}
        for definition in [schema, *schema.get("$defs", {}).values()]:
            properties = definition.get("properties", {})
            if "evidence_ids" in properties:
                properties["evidence_ids"]["items"] = {"$ref": "#/$defs/SourceID"}
            for field in ("fact_ids", "summary_ids"):
                if field in properties:
                    properties[field]["items"] = {"$ref": "#/$defs/SourceID"}
            if "segment_id" in properties:
                properties["segment_id"]["enum"] = ids
    if "uncertainty_ids" in schema.get("properties", {}):
        ids = [item["id"] for item in payload.get("uncertainties", [])]
        schema["properties"]["uncertainty_ids"]["items"] = {"type": "string", "enum": ids} if ids else {"type": "string"}
        if not ids:
            schema["properties"]["uncertainty_ids"]["maxItems"] = 0
    return schema


def prompt(name: str) -> str:
    return files("metawispr").joinpath("prompts", f"{name}.txt").read_text(encoding="utf-8")


class Ollama:
    def __init__(self, settings: Settings):
        self.settings = settings

    def request(self, method, path, body=None, timeout=None):
        try:
            # Never send local meeting data through an ambient HTTP proxy.
            with httpx.Client(base_url=self.settings.ollama_url, trust_env=False,
                              timeout=timeout or self.settings.llm_timeout_seconds) as client:
                response = client.request(method, path, json=body)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                error = exc.response.json().get("error")
                if isinstance(error, str):
                    detail = ": " + error[:300]
            except (ValueError, AttributeError):
                pass
            raise SetupError(f"Local Ollama returned HTTP {exc.response.status_code}{detail}. "
                             "Check the runtime and available memory, then retry.") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SetupError(f"Local Ollama request failed ({type(exc).__name__}). "
                             "Check that Ollama is running and the configured models are installed, then retry.") from exc

    def models(self) -> tuple[LLMModel, LLMModel]:
        installed = self.request("GET", "/api/tags", timeout=3).get("models", [])
        version = self.request("GET", "/api/version", timeout=3).get("version", "unknown")
        result = []
        for tag in (self.settings.refiner_model, self.settings.documenter_model):
            entry = next((item for item in installed if tag in {item.get("name"), item.get("model")}), None)
            if entry is None:
                raise SetupError(f"Ollama model {tag} is missing. Run: ollama pull {tag}")
            details = entry.get("details", {})
            try:
                result.append(LLMModel(tag=tag, digest=entry["digest"], runtime_version=version,
                                       parameter_size=details.get("parameter_size", "unknown"),
                                       quantization=details.get("quantization_level", "unknown")))
            except (KeyError, ValueError) as exc:
                raise SetupError("Ollama returned incomplete model metadata.") from exc
        return tuple(result)

    def fits(self, name, contract, payload, feedback="") -> bool:
        system = prompt(name) + "\nJSON schema: " + compact(generation_schema(contract, payload))
        # A conservative byte bound for the selected byte-level tokenizers. Reserve
        # output and chat framing; reject capacity overflow instead of truncating text.
        # Grouping and both attempts share the same reservation, including UTF-8
        # validation feedback. A valid first request must also fit its repair.
        size = len((system + compact(payload)).encode("utf-8")) + max(FEEDBACK_BYTES, len(feedback.encode("utf-8")))
        return size + self.settings.llm_output_tokens + 512 <= self.settings.llm_context

    def generate(self, model, name, contract, payload, store, meeting_id, stage, validate):
        system = prompt(name)
        schema = generation_schema(contract, payload)
        options = {"temperature": 0, "seed": 0, "num_ctx": self.settings.llm_context,
                   "num_predict": self.settings.llm_output_tokens, "presence_penalty": 0,
                   "repeat_penalty": 1}
        identity = {"model": model.model_dump(), "prompt": system, "schema": schema,
                    "input": payload, "options": options, "think": False,
                    "policy": 5 if stage == "documenting" else 4}
        key = digest(identity)
        filename = f"{stage}/calls/{key}.json"
        saved = store.read_json(meeting_id, filename)
        if saved:
            try:
                output = contract.model_validate(saved["output"])
                call = LLMCall.model_validate(saved["call"])
                if call.key != key or call.model != model:
                    raise ValueError("checkpoint identity mismatch")
                validate(output)
                return output, call
            except (KeyError, ValueError) as exc:
                raise SetupError("A saved LLM call is invalid; inspect its checkpoint before retrying.") from exc
        feedback = ""
        started = time.perf_counter()
        for attempt in range(1, 3):
            if not self.fits(name, contract, payload, feedback):
                raise SetupError("Transcript or consolidation exceeds the configured LLM context. "
                                 "Increase METAWISPR_LLM_CONTEXT within available memory or submit a shorter meeting.")
            messages = [{"role": "system", "content": system + "\nJSON schema: " + compact(schema)},
                        {"role": "user", "content": compact(payload)}]
            if feedback:
                messages.append({"role": "user", "content": feedback})
            result = self.request("POST", "/api/chat", {"model": model.tag, "messages": messages,
                                  "format": schema, "stream": False, "think": False,
                                  "options": options, "keep_alive": "5m"})
            try:
                if result.get("done") is not True or result.get("done_reason") != "stop":
                    raise ValueError("generation did not finish normally; output may be truncated")
                output = contract.model_validate_json(result.get("message", {}).get("content", ""))
                validate(output)
            except ValueError as exc:
                store.write_json(meeting_id, f"{stage}/failed/{key}-{attempt}.json",
                                 {"error": str(exc)[:400], "response": result})
                # Small feedback avoids echoing the transcript or enormous validation errors.
                feedback = repair_feedback(exc)
                if attempt == 2:
                    raise SetupError(f"{stage.capitalize()} model returned invalid output twice. "
                                     "Completed calls are saved; retry after checking the model/context settings.") from exc
                continue
            call = LLMCall(key=key, model=model, prompt_sha256=sha256(system.encode()).hexdigest(),
                           input_sha256=digest(payload), schema_sha256=digest(schema),
                           context=self.settings.llm_context, output_tokens=self.settings.llm_output_tokens,
                           elapsed_seconds=time.perf_counter() - started,
                           prompt_tokens=result.get("prompt_eval_count", 0),
                           generated_tokens=result.get("eval_count", 0), attempts=attempt,
                           presence_penalty=options["presence_penalty"], repeat_penalty=options["repeat_penalty"])
            store.write_json(meeting_id, filename, {"output": output.model_dump(), "call": call.model_dump()})
            return output, call

    def unload(self, model):
        # An explicit barrier between model stages, rather than hoping eviction occurs.
        self.request("POST", "/api/generate", {"model": model.tag, "prompt": "", "stream": False,
                                               "keep_alive": 0})


def llm_readiness(settings):
    try:
        models = Ollama(settings).models()
        return {"llm_ready": True, "llm_models": [model.model_dump() for model in models], "llm_error": None}
    except SetupError as exc:
        return {"llm_ready": False, "llm_models": [], "llm_error": str(exc)}
