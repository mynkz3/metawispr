"""Run `python -m metawispr --help` for local setup and transcription commands."""

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
import json
import sys

from .audio import readiness
from .config import InputError, Settings, SetupError
from .models import download_model
from .pipeline import Runner
from .llm import llm_readiness
from .exports import export_files


def main(argv=None):
    parser = ArgumentParser(prog="python -m metawispr")
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report runtime/model readiness without downloading anything")
    doctor.add_argument("--asr-only", action="store_true", help="Check only transcription dependencies")
    download = commands.add_parser("download-model", help="Install the selected Parakeet v2 export (INT8 or FP16)")
    download.add_argument("--archive", type=Path, help="Install an already downloaded .tar.bz2 archive offline")
    download.add_argument("--sha256", help="Optional expected archive checksum from a trusted source")
    transcribe = commands.add_parser("transcribe", help="Save a recording and run genuine ASR")
    transcribe.add_argument("recording", type=Path)
    transcribe.add_argument("--title", default="")
    process = commands.add_parser("process", help="Run ASR, terminology refinement and meeting documentation")
    process.add_argument("recording", type=Path)
    process.add_argument("--title", default="")
    process.add_argument("--glossary", default="", help="One term per line, optionally alias => canonical")
    document = commands.add_parser("document", help="Document an existing ASR-only meeting")
    document.add_argument("meeting_id")
    export = commands.add_parser("export", help="Write available validated exports to a directory")
    export.add_argument("meeting_id")
    export.add_argument("--output", type=Path, required=True)
    retry = commands.add_parser("retry", help="Resume a retryable failed meeting from saved checkpoints")
    retry.add_argument("meeting_id")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "doctor":
            report = {**readiness(settings), **llm_readiness(settings)}
            print(json.dumps(report, indent=2))
            return 0 if report["transcription_ready"] and report["conversion_ready"] and (args.asr_only or report["llm_ready"]) else 2
        if args.command == "download-model":
            print(json.dumps(download_model(settings.model_dir, args.archive, args.sha256,
                                            settings.asr_precision), indent=2))
            return 0
        runner = Runner(settings)
        if args.command == "export":
            meeting = runner.store.get(args.meeting_id)
            artifacts = export_files(meeting, runner.store.raw(meeting.id), runner.store.refined(meeting.id),
                                     runner.store.document(meeting.id))
            if not artifacts:
                raise InputError("No validated artifacts are available yet.")
            args.output.mkdir(parents=True, exist_ok=True)
            for name, content in artifacts.items():
                (args.output / name).write_bytes(content)
            print(json.dumps({"output": str(args.output.resolve()), "files": list(artifacts)}, indent=2))
            return 0
        if args.command == "retry":
            meeting = runner.store.get(args.meeting_id)
            if meeting.stage != "failed" or not meeting.retryable:
                raise InputError("This meeting is not eligible for retry.")
        elif args.command == "document":
            meeting = runner.store.get(args.meeting_id)
            if meeting.stage != "transcribed":
                raise InputError("Document requires an existing transcribed meeting. Use retry for a failed full pipeline.")
            meeting.target = "complete"
            runner.store.put(meeting)
        else:
            path = args.recording.resolve()
            if not path.is_file() or not 0 < path.stat().st_size <= settings.max_upload_bytes:
                raise InputError("Provide a readable nonempty recording within the upload size limit.")
            meeting = runner.store.begin(path.name, args.title, getattr(args, "glossary", ""))
            meeting.target = "transcribed" if args.command == "transcribe" else "complete"
            directory = runner.store.directory(meeting.id)
            temporary = directory / "upload.partial"
            digest, size = sha256(), 0
            try:
                with path.open("rb") as source, temporary.open("wb") as target:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        size += len(block)
                        if size > settings.max_upload_bytes:
                            raise InputError("Recording exceeds the upload size limit.")
                        target.write(block)
                        digest.update(block)
                if not size:
                    raise InputError("The recording became empty while it was being copied.")
                temporary.replace(directory / meeting.source_name)
            finally:
                temporary.unlink(missing_ok=True)
            meeting.size_bytes, meeting.input_sha256 = size, digest.hexdigest()
            runner.store.put(meeting)
        runner.run(meeting.id)
        result = runner.store.get(meeting.id)
        print(json.dumps({"meeting": result.model_dump(mode="json"),
                          "artifacts": str(runner.store.directory(meeting.id))}, indent=2))
        return 0 if result.stage == result.target else 1
    except (InputError, SetupError, OSError, ValueError) as exc:
        print(f"Metawispr: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
