"""Conservative terminology edits and evidence-checked chronological documentation."""

from difflib import SequenceMatcher
from datetime import datetime, timezone
import re

from .config import InputError, SetupError
from .llm import digest, prompt
from .schemas import (ConsolidatedNotes, DocumentationBatch, DocumentedMeeting, Edit, EditBatch,
                      Evidence, Fact, MeetingRecord, RefinedTranscript, RejectedEdit, ResolutionBatch,
                      SelectedNotes, SourceActions, SourceBatch, SourceNotes, SourceRecord, SourceResolutions, Task, Topic)


REFINEMENT_POLICY_VERSION = 9
POLICY_VERSION = 16
PROTECTED = re.compile(
    r"(?<!\w)[+-]?\d+(?:[.,:/-]\d+)*(?:%|\b)|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion|no|not|never|none|without|"
    r"cannot|can|can't|won't|don't|doesn't|isn't|wasn't|shouldn't|wouldn't|couldn't|mustn't|"
    r"will|must|shall|should|would|could|might|may|agree|agreed|promise|promised|commit|committed|"
    r"cancel|cancelled|withdraw|withdrawn)\b", re.IGNORECASE)
DATES = re.compile(r"\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|"
                   r"january|february|march|april|may|june|july|august|september|october|november|december)\b", re.I)
ANONYMOUS = re.compile(r"(?:I|me|we|us|you|he|she|they|him|her|them|my|our|your|their|it)", re.I)


def glossary_terms(text):
    canonical, aliases = set(), {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if "=>" in line:
            alias, term = (part.strip() for part in line.split("=>", 1))
            if not alias or not term:
                raise InputError("Glossary aliases must use: alias => canonical term (one entry per line).")
            if alias.casefold() in aliases and aliases[alias.casefold()] != term:
                raise InputError("A glossary alias cannot refer to two different canonical terms.")
            aliases[alias.casefold()] = term
        else:
            term = line
        canonical.add(term)
    return canonical, aliases


def apply_edits(segments, edits, glossary):
    source = {item.id: item for item in segments}
    canonical, aliases = glossary_terms(glossary)
    accepted, rejected = [], []
    for edit in edits:
        segment = source.get(edit.segment_id)
        reason = None
        if segment is None:
            reason = "Unknown segment"
        elif edit.end <= edit.start or edit.end > len(segment.text) or segment.text[edit.start:edit.end] != edit.original:
            reason = "Original span/offsets do not match"
        elif edit.replacement not in canonical and not any(
                re.search(r"(?<!\w)" + re.escape(edit.replacement) + r"(?!\w)",
                          part)
                for item in segments for part in ([item.text[:edit.start], item.text[edit.end:]]
                                                  if item.id == edit.segment_id else [item.text])):
            reason = "Replacement has no canonical glossary entry or independent meeting occurrence"
        elif edit.original == edit.replacement:
            reason = "No change"
        elif ((edit.start and segment.text[edit.start - 1].isalnum() and edit.original[0].isalnum()) or
              (edit.end < len(segment.text) and segment.text[edit.end].isalnum() and edit.original[-1].isalnum())):
            reason = "Edit cuts through a word"
        elif any(other.segment_id == edit.segment_id and edit.start < other.end and edit.end > other.start
                 for other in accepted):
            reason = "Overlaps an accepted edit"
        elif [m.group().casefold() for m in PROTECTED.finditer(edit.original)] != [
                m.group().casefold() for m in PROTECTED.finditer(edit.replacement)] or (
                re.findall(r"\d+", edit.original) != re.findall(r"\d+", edit.replacement)) or (
                DATES.findall(edit.original.casefold()) != DATES.findall(edit.replacement.casefold())):
            reason = "Changes a number, date, negation or commitment marker"
        else:
            letters = lambda value: re.sub(r"\W+", "", value.casefold())
            original, replacement = letters(edit.original), letters(edit.replacement)
            if aliases.get(edit.original.casefold()) != edit.replacement:
                if len(replacement) > len(original) * 1.25:
                    reason = "Adds unsupported speech or completes a role"
                elif original in {replacement + 's', replacement + 'es'} or replacement in {original + 's', original + 'es'}:
                    reason = "Changes grammatical number, not terminology spelling"
                elif SequenceMatcher(None, original, replacement).ratio() < 0.65:
                    reason = "Not a plausible terminology spelling or explicit alias"
        if reason:
            rejected.append(RejectedEdit(edit=edit, rejection=reason))
        else:
            accepted.append(edit)
    refined = []
    for segment in segments:
        text = segment.text
        for edit in sorted((item for item in accepted if item.segment_id == segment.id), key=lambda e: e.start, reverse=True):
            text = text[:edit.start] + edit.replacement + text[edit.end:]
        refined.append(segment.model_copy(update={"text": text}))
    return refined, accepted, rejected


def facts(record):
    return [*record.summary, *(point for topic in record.topics for point in topic.points),
            *record.decisions, *record.tasks]


def validate_record(record, segments, revisions=(), allowed=None):
    source = {item.id: item.text for item in segments}
    for fact in [*facts(record), *revisions]:
        if not fact.text.strip():
            raise ValueError("Fact text must not be blank")
        quotes = " ".join(item.quote for item in fact.evidence)
        for claimed in ("revenue", "profit"):
            if (re.search(r"\b" + claimed + r"s?\b", fact.text, re.I) and
                    not re.search(r"\b" + claimed + r"s?\b", quotes, re.I) and
                    not re.search(r"\b(?:unspecified|unknown|unclear|uncertain)\b|not stated|\bno (?:explicit )?mention\b|\bdid not (?:specify|state|mention)\b", fact.text, re.I)):
                raise ValueError(f"Unsupported financial label {claimed!r}: it is not stated in the cited source. "
                                 "Cite its explicit label or describe the stated financial target without guessing profit/revenue.")
        for evidence in fact.evidence:
            if not evidence.quote.strip() or evidence.segment_id not in source or evidence.quote not in source[evidence.segment_id]:
                raise ValueError(f"Evidence does not match segment {evidence.segment_id}")
            if ((evidence.start_char is None) != (evidence.end_char is None) or
                    (evidence.start_char is not None and
                     (evidence.end_char <= evidence.start_char or evidence.end_char > len(source[evidence.segment_id]) or
                      source[evidence.segment_id][evidence.start_char:evidence.end_char] != evidence.quote))):
                raise ValueError("Evidence character range does not match its source")
            if allowed is not None and (evidence.segment_id, evidence.quote) not in allowed:
                raise ValueError("Consolidation introduced evidence outside its input batches")
    for task in record.tasks:
        if task.owner is not None and ANONYMOUS.fullmatch(task.owner.strip()):
            raise ValueError("Owner must be an identified literal name/role, or null; pronouns do not identify a person.")
        for name in ("owner", "deadline"):
            value = getattr(task, name)
            if value is not None and (not value.strip() or not any(
                    re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", ev.quote) for ev in task.evidence)):
                raise ValueError(f"Task {name} {value!r} must be null or literal text in its supporting sources. "
                                 "Select the source ID containing the value; otherwise copy literal text or use null.")
    if any(not topic.title.strip() for topic in record.topics):
        raise ValueError("Topic titles must not be blank")


def groups(items, make_payload, fits):
    result, current = [], []
    for item in items:
        if not fits(make_payload([item])):
            raise SetupError("One transcript segment exceeds the configured LLM context; increase METAWISPR_LLM_CONTEXT.")
        if current and not fits(make_payload([*current, item])):
            result.append(current)
            current = []
        current.append(item)
    if current:
        result.append(current)
    return result


def evidence_key(item):
    value = item if isinstance(item, dict) else item.model_dump()
    return value["segment_id"], value["quote"], value.get("start_char"), value.get("end_char")


def source_units(segments):
    units, sources = [], {}
    for segment in segments:
        # These are immutable text spans, not speaker turns or word/audio alignment.
        spans = [(match.start(), match.end(), match.group()) for match in
                 re.finditer(r"\S.*?(?:[.!?](?=\s|$)|$)", segment.text, re.S)]
        for index, (start, end, text) in enumerate(spans):
            identifier = f"{segment.id}:u{index:03d}"
            units.append(segment.model_copy(update={"id": identifier, "text": text}))
            sources[identifier] = Evidence(segment_id=segment.id, quote=text,
                                           start_char=start, end_char=end)
    return units, sources


def document_input(title, items):
    return {"title": title, "segments": [{"id": item.id, "text": item.text,
                                          "parent_id": item.id.rsplit(":u", 1)[0]} for item in items]}


def document_groups(meeting, segments, llm):
    units, sources = source_units(segments)
    positions = {item.id: index for index, item in enumerate(units)}
    def payload(items):
        value = document_input(meeting.title, items)
        value["glossary"] = meeting.glossary
        start = positions[items[0].id]
        value["context"] = document_input(meeting.title, units[max(0, start - 6):start])["segments"]
        return value
    batches = groups(units, payload, lambda value: llm.fits("document", SourceActions, value)
                     and (len(value["segments"]) == 1 or
                          sum(len(item["text"].encode("utf-8")) for item in value["segments"]) <= 3500))
    return sources, batches, payload


def attach_evidence(output, contract, sources):
    """Resolve selected IDs in Python; model responses cannot supply quote text."""
    def expand(value):
        if isinstance(value, list):
            return [expand(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: expand(item) for key, item in value.items() if key != "evidence_ids"}
        if "evidence_ids" in value:
            ids = value["evidence_ids"]
            unknown = [identifier for identifier in ids if identifier not in sources]
            if len(set(ids)) != len(ids) or unknown:
                raise ValueError(f"Evidence IDs must be unique supplied IDs; unknown: {unknown[:3]!r}. Copy exact IDs.")
            result["evidence"] = [sources[identifier].model_dump() for identifier in ids]
            # Restore only capitalization from the selected literal source. This
            # cannot supply an absent name, role or deadline.
            for field in ("owner", "deadline"):
                if isinstance(result.get(field), str):
                    for identifier in ids:
                        match = re.search(r"(?<!\w)" + re.escape(result[field]) + r"(?!\w)",
                                          sources[identifier].quote, re.I)
                        if match:
                            result[field] = match.group()
                            break
            if isinstance(result.get("owner"), str) and ANONYMOUS.fullmatch(result["owner"].strip()):
                result["owner"] = None
        return result
    return contract.model_validate(expand(output.model_dump()))


def source_payload(value, sources, include_text=True):
    """Send each immutable source once across candidate facts and revision signals."""
    identifiers = {evidence_key(item): identifier for identifier, item in sources.items()}
    used = set()
    def select(value):
        if isinstance(value, list):
            return [select(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: select(item) for key, item in value.items() if key != "evidence"}
        if "evidence" in value:
            ids = [identifiers[evidence_key(item)] for item in value["evidence"]]
            used.update(ids)
            result["evidence_ids"] = ids
        return result
    result = select(value)
    result["sources"] = [{"id": identifier, **({"text": item.quote} if include_text else {})}
                         for identifier, item in sources.items() if identifier in used]
    return result


def refinement_policy(settings, glossary):
    return digest({"version": REFINEMENT_POLICY_VERSION, "prompt": prompt("refine"), "glossary": glossary,
                   "model": settings.refiner_model})


def selection_input(title, batches, decisions, tasks):
    """Consolidation selects whole facts; text and citations never separate."""
    catalogue, uncertainties = {}, {}
    def add(fact):
        fact = Fact(text=fact.text, evidence=fact.evidence)
        identifier = next((key for key, value in catalogue.items() if value == fact), None)
        if identifier is None:
            identifier = f"f{len(catalogue):04d}"
            catalogue[identifier] = fact
        return identifier
    chronological = []
    for batch in batches:
        record = batch.record
        chronological.append({"summary_ids": [add(fact) for fact in record.summary],
                              "topics": [{"title": topic.title, "fact_ids": [add(fact) for fact in topic.points]} for topic in record.topics]})
        for text in record.uncertainties:
            if text not in uncertainties.values():
                uncertainties[f"u{len(uncertainties):04d}"] = text
    payload = {"title": title, "chronological_batches": chronological,
               "resolved_current": {"decisions": [add(fact) for fact in decisions], "tasks": [add(fact) for fact in tasks]},
               "sources": [{"id": key, "text": fact.text} for key, fact in catalogue.items()],
               "uncertainties": [{"id": key, "text": text} for key, text in uncertainties.items()]}
    return payload, catalogue, uncertainties


def expand_selection(selected, catalogue, uncertainties):
    def select(ids):
        if len(ids) != len(set(ids)) or any(key not in catalogue for key in ids):
            raise ValueError("Select distinct supplied fact IDs only")
        return [catalogue[key].model_copy(deep=True) for key in ids]
    if len(selected.uncertainty_ids) != len(set(selected.uncertainty_ids)) or any(key not in uncertainties for key in selected.uncertainty_ids):
        raise ValueError("Select distinct supplied uncertainty IDs only")
    return ConsolidatedNotes(summary=select(selected.summary_ids),
                             topics=[Topic(title=topic.title, points=select(topic.fact_ids)) for topic in selected.topics],
                             uncertainties=[uncertainties[key] for key in selected.uncertainty_ids])


def documentation_policy(settings):
    return digest({"version": POLICY_VERSION, "prompts": [prompt("document"), prompt("review"), prompt("notes"), prompt("reconcile"), prompt("consolidate")],
                   "model": settings.documenter_model})


def candidate_items(batches):
    return [{"candidate_id": f"{kind}-{index}-{offset}", "kind": kind, "batch": index, "fact": fact}
            for index, batch in enumerate(batches) for kind in ("decisions", "tasks")
            for offset, fact in enumerate(getattr(batch.record, kind))]


def reconciliation_inputs(candidates, revisions, sources, llm):
    """Bound every resolution call while giving each one the full revision context."""
    def payload(items):
        return source_payload(
            {"candidates": [{**item, "fact": item["fact"].model_dump()} for item in items],
             "revisions": [item.model_dump() for item in revisions]}, sources)
    return [payload(batch) for batch in groups(
        candidates, payload, lambda value: llm.fits("reconcile", SourceResolutions, value))]


def resolve_candidates(output, candidates, segments, allowed):
    by_id = {item["candidate_id"]: item for item in candidates}
    if len(output.resolutions) != len(by_id) or {item.candidate_id for item in output.resolutions} != set(by_id):
        raise ValueError("Resolve every candidate_id exactly once")
    source = {item.id: item for item in segments}
    decisions, tasks, revisions = [], [], []
    for resolution in output.resolutions:
        candidate = by_id[resolution.candidate_id]
        original = candidate["fact"]
        validate_record(MeetingRecord(summary=[], topics=[], decisions=[], tasks=[], uncertainties=[]), segments,
                        [Fact(text=resolution.reason, evidence=resolution.evidence)], allowed)
        if resolution.disposition == "discard":
            if resolution.replacement is not None or not any(old == new for old in original.evidence for new in resolution.evidence):
                raise ValueError("Discard needs original evidence and no replacement")
            # An extraction error is not a withdrawal made in the meeting.
            # Its explanation remains in the saved resolution call, not minutes.
            continue
        if resolution.disposition == "keep":
            if resolution.replacement is not None or not any(old == new for old in original.evidence for new in resolution.evidence):
                raise ValueError("Keep must preserve original evidence and have no replacement")
            current = original
        else:
            replacement = resolution.replacement
            current = None
            if resolution.disposition == "replace":
                if replacement is None:
                    raise ValueError("Replace requires a complete replacement")
                if replacement.kind == "task":
                    current = Task(text=replacement.text, owner=replacement.owner, deadline=replacement.deadline,
                                   evidence=replacement.evidence)
                else:
                    if replacement.owner is not None or replacement.deadline is not None:
                        raise ValueError("A decision cannot have task assignment fields")
                    current = Fact(text=replacement.text, evidence=replacement.evidence)
            reclassified = (resolution.disposition == "replace" and replacement is not None and
                            (replacement.kind == "task") != isinstance(original, Task))
            directive = candidate["kind"] == "decisions" and any(
                re.match(r"\s*(withdraw|cancel|reassign|replace|correct)\b", item.quote, re.I) for item in original.evidence)
            def position(item):
                segment = source[item.segment_id]
                return segment.start, item.start_char if item.start_char is not None else segment.text.index(item.quote)
            if not directive and not reclassified and current != original and not any(position(new) > max(position(old) for old in original.evidence)
                                         for new in resolution.evidence):
                raise ValueError(f"{resolution.candidate_id}: retirement/replacement needs later supporting evidence; use keep for unchanged items")
            if reclassified and not any(old == new for old in original.evidence for new in replacement.evidence):
                raise ValueError("Recategorization needs the original supporting quote")
            audit_evidence = list(original.evidence)
            audit_evidence.extend(item for item in resolution.evidence if item not in audit_evidence)
            if current != original and not reclassified:
                revisions.append(Fact(text=resolution.reason, evidence=audit_evidence))
            if resolution.disposition == "retire":
                if resolution.replacement is not None:
                    raise ValueError("Retire cannot include a replacement")
                continue
            test = MeetingRecord(summary=[], topics=[], decisions=[], tasks=[], uncertainties=[])
            (test.tasks if isinstance(current, Task) else test.decisions).append(current)
            validate_record(test, segments, allowed=allowed)
        target = tasks if isinstance(current, Task) else decisions
        if current not in target:
            target.append(current)
    return decisions, tasks, revisions


class Documentation:
    def __init__(self, settings, store, llm):
        self.settings, self.store, self.llm = settings, store, llm

    def refine(self, meeting, raw, model, progress):
        payload = lambda items: {"title": meeting.title, "glossary": meeting.glossary,
                                 "segments": [item.model_dump() for item in items]}
        batches = groups(raw.segments, payload, lambda value: self.llm.fits("refine", EditBatch, value))
        edits, calls, outside = [], [], []
        try:
            for batch in batches:
                output, call = self.llm.generate(model, "refine", EditBatch, payload(batch), self.store,
                                                 meeting.id, "refining", lambda output: None)
                # An edit cannot reach outside the group that proposed it.
                source = {item.id: item.text for item in batch}
                for proposal in output.edits:
                    text = source.get(proposal.segment_id)
                    if text is None:
                        outside.append(RejectedEdit(edit=proposal, rejection="Segment is outside this input group"))
                    elif text.count(proposal.original) != 1:
                        outside.append(RejectedEdit(edit=proposal, rejection="Original anchor is absent or ambiguous"))
                    else:
                        start = text.index(proposal.original)
                        edits.append(Edit(**proposal.model_dump(), start=start, end=start + len(proposal.original)))
                calls.append(call)
                progress(len(calls))
        finally:
            self.llm.unload(model)
        segments, accepted, rejected = apply_edits(raw.segments, edits, meeting.glossary)
        rejected.extend(outside)
        return RefinedTranscript(source_sha256=digest(raw.model_dump()),
                                 policy_sha256=refinement_policy(self.settings, meeting.glossary),
                                 created_at=datetime.now(timezone.utc).isoformat(),
                                 segments=segments, accepted=accepted, rejected=rejected, calls=calls,
                                 warnings=["Automatic edit guards cannot establish meaning. Review accepted and rejected edits."])

    def document(self, meeting, refined, model, progress):
        sources, batches, payload = document_groups(meeting, refined.segments, self.llm)
        identifiers = {evidence_key(item): identifier for identifier, item in sources.items()}
        outputs, calls, context_repeats = [], [], 0
        try:
            index = 0
            while index < len(batches):
                batch = batches[index]
                value = payload(batch)
                batch_sources = {item["id"]: sources[item["id"]] for item in [*value["segments"], *value["context"]]}
                active = {item.id for item in batch}
                def action_batch(actions):
                    return SourceBatch(record=SourceRecord(summary=[], topics=[], uncertainties=[],
                                                          decisions=actions.decisions, tasks=actions.tasks),
                                       revisions=actions.revisions)
                def active_actions(actions):
                    # Context has already been processed in chronological order.
                    # Keep the original answer in its call checkpoint, while
                    # canonicalizing only items supported by new source units.
                    for item in [*actions.decisions, *actions.tasks, *actions.revisions]:
                        if not set(item.evidence_ids) <= batch_sources.keys() or len(item.evidence_ids) != len(set(item.evidence_ids)):
                            raise ValueError("Evidence IDs must be distinct supplied source IDs")
                    return actions.model_copy(update={kind: [item for item in getattr(actions, kind)
                        if active.intersection(item.evidence_ids)] for kind in ("decisions", "tasks", "revisions")})
                def validate_batch(result, draft=False):
                    result = active_actions(result)
                    expanded = attach_evidence(action_batch(result), DocumentationBatch, batch_sources)
                    if draft:
                        for task in expanded.record.tasks:
                            task.owner = task.deadline = None
                    else:
                        for task in expanded.record.tasks:
                            for field in ("owner", "deadline"):
                                literal = getattr(task, field)
                                if literal and not any(re.search(r"(?<!\w)" + re.escape(literal) + r"(?!\w)", ev.quote) for ev in task.evidence):
                                    matches = [key for key, ev in batch_sources.items() if
                                               re.search(r"(?<!\w)" + re.escape(literal) + r"(?!\w)", ev.quote, re.I)]
                                    raise ValueError(f"Task {field} {literal!r} needs literal text and its source ID. "
                                                     f"Matching available IDs: {matches[:4]}. Cite applicable sources or use null.")
                    validate_record(expanded.record, refined.segments, expanded.revisions)
                selected, call = self.llm.generate(model, "document", SourceActions, value, self.store,
                                                  meeting.id, "documenting", lambda result: validate_batch(result, draft=True))
                calls.append(call)
                progress(len(calls))
                review_input = {**value, "draft": selected.model_dump()}
                if not self.llm.fits("review", SourceActions, review_input):
                    if len(batch) == 1:
                        raise SetupError("One source unit plus its extraction draft exceeds the review context. Increase METAWISPR_LLM_CONTEXT or submit a shorter recording.")
                    middle = len(batch) // 2
                    batches[index:index + 1] = [batch[:middle], batch[middle:]]
                    continue
                # The first answer is a proposal. A focused second pass checks
                # every assignment against the same source before canonicalizing.
                reviewed, call = self.llm.generate(model, "review", SourceActions,
                                                   review_input, self.store,
                                                   meeting.id, "documenting", validate_batch)
                filtered = active_actions(reviewed)
                context_repeats += sum(len(getattr(reviewed, kind)) - len(getattr(filtered, kind)) for kind in ("decisions", "tasks", "revisions"))
                output = attach_evidence(action_batch(filtered), DocumentationBatch, batch_sources)
                calls.append(call)
                progress(len(calls))
                # Budget notes against the actual extracted actions. If they consume
                # more room, split notes inputs; never drop source or action evidence.
                def notes_payload(items):
                    ids = {item.id for item in items}
                    current = {kind: [fact.model_dump() for fact in getattr(output.record, kind)
                                      if any(identifiers[evidence_key(ev)] in ids for ev in fact.evidence)]
                               for kind in ("decisions", "tasks")}
                    revisions = [fact.model_dump() for fact in output.revisions
                                 if any(identifiers[evidence_key(ev)] in ids for ev in fact.evidence)]
                    value = source_payload({"title": meeting.title, "resolved_current": current,
                                            "revisions": revisions}, batch_sources)
                    ids.update(item["id"] for item in value.pop("sources"))
                    value["segments"] = [{"id": identifier, "text": item.quote} for identifier, item in batch_sources.items() if identifier in ids]
                    value["context"] = payload(items)["context"]
                    return value
                note_groups = groups(batch, notes_payload, lambda value: self.llm.fits("notes", SourceNotes, value))
                for note_group in note_groups:
                    value = notes_payload(note_group)
                    note_sources = {item["id"]: batch_sources[item["id"]] for item in [*value["segments"], *value["context"]]}
                    def validate_local_notes(result):
                        notes = attach_evidence(result, ConsolidatedNotes, note_sources)
                        validate_record(MeetingRecord(**notes.model_dump(), decisions=[], tasks=[]), refined.segments)
                    selected_notes, call = self.llm.generate(model, "notes", SourceNotes, value, self.store,
                                                            meeting.id, "documenting", validate_local_notes)
                    notes = attach_evidence(selected_notes, ConsolidatedNotes, note_sources)
                    output.record.summary.extend(notes.summary)
                    output.record.topics.extend(notes.topics)
                    output.record.uncertainties.extend(notes.uncertainties)
                    calls.append(call)
                    progress(len(calls))
                outputs.append(output)
                index += 1
            # Pair adjacent chronological groups. Revisions remain available until
            # the last pass so a cancellation in a later group can reach its target.
            while len(outputs) > 1:
                merged = []
                for index in range(0, len(outputs), 2):
                    pair = outputs[index:index + 2]
                    if len(pair) == 1:
                        merged.append(pair[0])
                        continue
                    allowed = {(ev.segment_id, ev.quote) for batch in pair
                               for fact in [*facts(batch.record), *batch.revisions] for ev in fact.evidence}
                    candidates = candidate_items(pair)
                    if candidates:
                        decisions, tasks, revisions = [], [], []
                        for resolution_input in reconciliation_inputs(
                                candidates, [item for batch in pair for item in batch.revisions], sources, self.llm):
                            chunk = [item for item in candidates if item["candidate_id"] in
                                     {value["candidate_id"] for value in resolution_input["candidates"]}]
                            allowed_sources = {item["id"]: sources[item["id"]] for item in resolution_input["sources"]}
                            def resolved(result):
                                return resolve_candidates(attach_evidence(result, ResolutionBatch, allowed_sources),
                                                          chunk, refined.segments, allowed)
                            selected, call = self.llm.generate(model, "reconcile", SourceResolutions, resolution_input,
                                                               self.store, meeting.id, "documenting", resolved)
                            for target, values in zip((decisions, tasks, revisions), resolved(selected)):
                                target.extend(value for value in values if value not in target)
                            calls.append(call)
                            progress(len(calls))
                    else:
                        decisions, tasks, revisions = [], [], []
                    def consolidate_notes(batches):
                        value, catalogue, ambiguities = selection_input(meeting.title, batches, decisions, tasks)
                        def validate_notes(selected):
                            notes = expand_selection(selected, catalogue, ambiguities)
                            validate_record(MeetingRecord(**notes.model_dump(), decisions=[], tasks=[]),
                                            refined.segments, allowed=allowed)
                        selected, call = self.llm.generate(model, "consolidate", SelectedNotes, value,
                                                          self.store, meeting.id, "documenting", validate_notes)
                        calls.append(call)
                        progress(len(calls))
                        return expand_selection(selected, catalogue, ambiguities)
                    value, _, _ = selection_input(meeting.title, pair, decisions, tasks)
                    if not self.llm.fits("consolidate", SelectedNotes, value):
                        # Explicit selection of existing facts compresses notes.
                        # Original text/evidence remain coupled; actions stay in Python.
                        for batch in pair:
                            notes = consolidate_notes([batch])
                            batch.record.summary, batch.record.topics = notes.summary, notes.topics
                            batch.record.uncertainties = notes.uncertainties
                    notes = consolidate_notes(pair)
                    record = MeetingRecord(**notes.model_dump(), decisions=decisions, tasks=tasks)
                    carried = [item for batch in pair for item in batch.revisions]
                    carried.extend(item for item in revisions if item not in carried)
                    output = DocumentationBatch(record=record, revisions=carried)
                    merged.append(output)
                outputs = merged
        finally:
            self.llm.unload(model)
        record = outputs[0].record
        validate_record(record, refined.segments)
        return DocumentedMeeting(source_sha256=digest(refined.model_dump()),
                                 policy_sha256=documentation_policy(self.settings), record=record, calls=calls,
                                 revision_audit=outputs[0].revisions,
                                 created_at=datetime.now(timezone.utc).isoformat(),
                                 warnings=["Exact evidence matching verifies provenance, not interpretation. Review decisions, tasks and revisions.",
                                           f"Excluded {context_repeats} preceding-context-only items. Original proposals remain in saved call checkpoints."])
