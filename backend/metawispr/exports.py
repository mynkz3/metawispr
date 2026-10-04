"""Render every download from the same validated artifacts; never run a model here."""

from html import escape
from io import BytesIO
import json
import re
from zipfile import ZIP_DEFLATED, ZipFile

from .documentation import validate_record


FORMATS = {"raw.txt", "raw.json", "refined.txt", "refined.json", "edits.json",
           "meeting.json", "meeting.md", "provenance.json", "bundle.zip"}


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def markdown_text(value):
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", escape(value, quote=False)).replace("\n", " ")


def markdown(meeting, refined, document):
    record = document.record
    times = {segment.id: f"{segment.start:.2f}–{segment.end:.2f}s" for segment in refined.segments}
    lines = [f"# {markdown_text(meeting.title)}", "", "Source times identify audio windows, not exact word boundaries.", ""]

    def add_fact(fact, task=False):
        lines.append("- " + markdown_text(fact.text))
        if task:
            lines.append(f"  - Owner: {markdown_text(fact.owner) if fact.owner is not None else 'Unspecified'}; "
                         f"deadline: {markdown_text(fact.deadline) if fact.deadline is not None else 'Unspecified'}")
        for evidence in fact.evidence:
            lines.append(f"  - Evidence ({markdown_text(evidence.segment_id)}, {times[evidence.segment_id]}): "
                         f"“{markdown_text(evidence.quote)}”")

    for title, items in (("Summary", record.summary), ("Decisions", record.decisions), ("Tasks", record.tasks)):
        lines.extend([f"## {title}", ""])
        if not items:
            lines.extend(["None stated.", ""])
        for fact in items:
            add_fact(fact, title == "Tasks")
        lines.append("")
    lines.extend(["## Topic minutes", ""])
    if not record.topics:
        lines.extend(["None stated.", ""])
    for topic in record.topics:
        lines.extend([f"### {markdown_text(topic.title)}", ""])
        for fact in topic.points:
            add_fact(fact)
        lines.append("")
    if document.revision_audit:
        lines.extend(["## Revision history", ""])
        for fact in document.revision_audit:
            add_fact(fact)
        lines.append("")
    lines.extend(["## Review notes", ""])
    for note in [*record.uncertainties, *document.warnings]:
        lines.append("- " + markdown_text(note))
    return "\n".join(lines) + "\n"


def export_files(meeting, raw=None, refined=None, document=None, include_bundle=True):
    result = {}
    if raw:
        result["raw.json"] = json_bytes(raw.model_dump(mode="json"))
        result["raw.txt"] = ("\n".join(item.text for item in raw.segments) + "\n").encode("utf-8")
    if refined:
        result["refined.json"] = json_bytes(refined.model_dump(mode="json"))
        result["refined.txt"] = ("\n".join(item.text for item in refined.segments) + "\n").encode("utf-8")
        result["edits.json"] = json_bytes({"accepted": [item.model_dump() for item in refined.accepted],
                                           "rejected": [item.model_dump() for item in refined.rejected]})
    if document:
        validate_record(document.record, refined.segments, document.revision_audit)
        result["meeting.json"] = json_bytes({"meeting_id": meeting.id, "title": meeting.title,
                                             **document.model_dump(mode="json")})
        result["meeting.md"] = markdown(meeting, refined, document).encode("utf-8")
        result["provenance.json"] = json_bytes({"asr": raw.model_dump(mode="json")["model"],
                                                "refinement": [item.model_dump() for item in refined.calls],
                                                "documentation": [item.model_dump() for item in document.calls],
                                                "input_sha256": raw.input_sha256})
        if include_bundle:
            buffer = BytesIO()
            with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
                for name, content in result.items():
                    archive.writestr(name, content)
            result["bundle.zip"] = buffer.getvalue()
    return result
