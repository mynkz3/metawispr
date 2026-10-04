"""Conservative terminology edits and evidence-checked chronological documentation."""

from difflib import SequenceMatcher
from datetime import datetime, timezone
import re

from .config import InputError, SetupError
from .llm import digest, prompt
from .schemas import (ConsolidatedNotes, DocumentationBatch, DocumentedMeeting, Edit, EditBatch,
                      Fact, MeetingRecord, RefinedTranscript, RejectedEdit, ResolutionBatch, Task)


POLICY_VERSION = 2
PROTECTED = re.compile(
    r"(?<!\w)[+-]?\d+(?:[.,:/-]\d+)*(?:%|\b)|\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|"
    r"sixty|seventy|eighty|ninety|hundred|thousand|million|billion|no|not|never|none|without|"
    r"cannot|can|can't|won't|don't|doesn't|isn't|wasn't|shouldn't|wouldn't|couldn't|mustn't|"
    r"will|must|shall|should|would|could|might|may|agree|agreed|promise|promised|commit|committed|"
    r"cancel|cancelled|withdraw|withdrawn)\b", re.IGNORECASE)


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
        elif edit.replacement not in canonical:
            reason = "Replacement is absent from the canonical glossary"
        elif edit.original == edit.replacement:
            reason = "No change"
        elif ((edit.start and segment.text[edit.start - 1].isalnum() and edit.original[0].isalnum()) or
              (edit.end < len(segment.text) and segment.text[edit.end].isalnum() and edit.original[-1].isalnum())):
            reason = "Edit cuts through a word"
        elif any(other.segment_id == edit.segment_id and edit.start < other.end and edit.end > other.start
                 for other in accepted):
            reason = "Overlaps an accepted edit"
        elif [m.group().casefold() for m in PROTECTED.finditer(edit.original)] != [
                m.group().casefold() for m in PROTECTED.finditer(edit.replacement)]:
            reason = "Changes a number, negation or commitment marker"
        else:
            letters = lambda value: re.sub(r"\W+", "", value.casefold())
            if aliases.get(edit.original.casefold()) != edit.replacement and SequenceMatcher(
                    None, letters(edit.original), letters(edit.replacement)).ratio() < 0.65:
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
        for evidence in fact.evidence:
            if not evidence.quote.strip() or evidence.segment_id not in source or evidence.quote not in source[evidence.segment_id]:
                raise ValueError(f"Evidence does not match segment {evidence.segment_id}")
            if allowed is not None and (evidence.segment_id, evidence.quote) not in allowed:
                raise ValueError("Consolidation introduced evidence outside its input batches")
    for task in record.tasks:
        for name in ("owner", "deadline"):
            value = getattr(task, name)
            if value is not None and (not value.strip() or not any(
                    re.search(r"(?<!\w)" + re.escape(value) + r"(?!\w)", ev.quote) for ev in task.evidence)):
                raise ValueError(f"Task {name} must be null or literal text in its supporting quotes")
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


def refinement_policy(settings, glossary):
    return digest({"version": POLICY_VERSION, "prompt": prompt("refine"), "glossary": glossary,
                   "model": settings.refiner_model})


def documentation_policy(settings):
    return digest({"version": POLICY_VERSION, "prompts": [prompt("document"), prompt("reconcile"), prompt("consolidate")],
                   "model": settings.documenter_model})


def consolidation_payload(title, batches):
    # Quotes often repeat across summary, minutes, decisions and tasks. Send each
    # exact quote once, with indices in candidate facts; outputs still use full quotes.
    evidence, identifiers, compact_batches = [], {}, []
    def candidate(fact):
        ids = []
        for item in fact.evidence:
            key = (item.segment_id, item.quote)
            if key not in identifiers:
                identifiers[key] = len(evidence)
                evidence.append(item.model_dump())
            ids.append(identifiers[key])
        value = {"text": fact.text, "evidence_ids": ids}
        if hasattr(fact, "owner"):
            value.update(owner=fact.owner, deadline=fact.deadline)
        return value
    for batch in batches:
        record = batch.record
        compact_batches.append({"record": {
            "summary": [candidate(item) for item in record.summary],
            "topics": [{"title": topic.title, "points": [candidate(item) for item in topic.points]} for topic in record.topics],
            "decisions": [candidate(item) for item in record.decisions],
            "tasks": [candidate(item) for item in record.tasks], "uncertainties": record.uncertainties},
            "revisions": [candidate(item) for item in batch.revisions]})
    return {"title": title, "evidence": evidence, "chronological_batches": compact_batches}


def candidate_items(batches):
    return [{"candidate_id": f"{kind}-{index}-{offset}", "kind": kind, "batch": index, "fact": fact}
            for index, batch in enumerate(batches) for kind in ("decisions", "tasks")
            for offset, fact in enumerate(getattr(batch.record, kind))]


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
                return segment.start, segment.text.index(item.quote)
            if not directive and not reclassified and current != original and not any(position(new) > max(position(old) for old in original.evidence)
                                         for new in resolution.evidence):
                raise ValueError(f"{resolution.candidate_id}: retirement/replacement needs later supporting evidence; use keep for unchanged items")
            if reclassified and not any(old == new for old in original.evidence for new in replacement.evidence):
                raise ValueError("Recategorization needs the original supporting quote")
            audit_evidence = list(original.evidence)
            audit_evidence.extend(item for item in resolution.evidence if item not in audit_evidence)
            if current != original:
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
        payload = lambda items: {"title": meeting.title, "segments": [item.model_dump() for item in items]}
        batches = groups(refined.segments, payload, lambda value: self.llm.fits("document", DocumentationBatch, value))
        outputs, calls = [], []
        try:
            for batch in batches:
                output, call = self.llm.generate(model, "document", DocumentationBatch, payload(batch), self.store,
                                                 meeting.id, "documenting",
                                                 lambda output: validate_record(output.record, batch, output.revisions))
                outputs.append(output)
                calls.append(call)
                progress(len(calls))
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
                    value = consolidation_payload(meeting.title, pair)
                    candidates = candidate_items(pair)
                    if candidates:
                        resolution_input = {"candidates": [{**item, "fact": item["fact"].model_dump()} for item in candidates],
                                            "revisions": [item.model_dump() for batch in pair for item in batch.revisions]}
                        resolution, call = self.llm.generate(model, "reconcile", ResolutionBatch, resolution_input,
                                                            self.store, meeting.id, "documenting",
                                                            lambda result: resolve_candidates(result, candidates, refined.segments, allowed))
                        decisions, tasks, revisions = resolve_candidates(resolution, candidates, refined.segments, allowed)
                        calls.append(call)
                        progress(len(calls))
                    else:
                        decisions, tasks, revisions = [], [], []
                    value["resolved_current"] = {"decisions": [item.model_dump() for item in decisions],
                                                 "tasks": [item.model_dump() for item in tasks]}
                    # Notes cannot overwrite the separately resolved canonical arrays.
                    def validate_notes(notes):
                        record = MeetingRecord(**notes.model_dump(), decisions=decisions, tasks=tasks)
                        validate_record(record, refined.segments, allowed=allowed)
                    notes, call = self.llm.generate(model, "consolidate", ConsolidatedNotes, value, self.store,
                                                    meeting.id, "documenting", validate_notes)
                    record = MeetingRecord(**notes.model_dump(), decisions=decisions, tasks=tasks)
                    carried = [item for batch in pair for item in batch.revisions]
                    carried.extend(item for item in revisions if item not in carried)
                    output = DocumentationBatch(record=record, revisions=carried)
                    merged.append(output)
                    calls.append(call)
                    progress(len(calls))
                outputs = merged
        finally:
            self.llm.unload(model)
        record = outputs[0].record
        validate_record(record, refined.segments)
        return DocumentedMeeting(source_sha256=digest(refined.model_dump()),
                                 policy_sha256=documentation_policy(self.settings), record=record, calls=calls,
                                 revision_audit=outputs[0].revisions,
                                 created_at=datetime.now(timezone.utc).isoformat(),
                                 warnings=["Exact evidence matching verifies provenance, not interpretation. Review decisions, tasks and revisions."])
