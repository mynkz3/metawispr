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


def main(argv=None):
    parser = ArgumentParser(prog="python -m metawispr")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="Report runtime/model readiness without downloading anything")
    download = commands.add_parser("download-model", help="Install the documented Parakeet v2 INT8 package")
    download.add_argument("--archive", type=Path, help="Install an already downloaded .tar.bz2 archive offline")
    download.add_argument("--sha256", help="Optional expected archive checksum from a trusted source")
    transcribe = commands.add_parser("transcribe", help="Save a recording and run genuine ASR")
    transcribe.add_argument("recording", type=Path)
    transcribe.add_argument("--title", default="")
    retry = commands.add_parser("retry", help="Resume a retryable failed meeting from saved checkpoints")
    retry.add_argument("meeting_id")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "doctor":
            report = readiness(settings)
            print(json.dumps(report, indent=2))
            return 0 if report["transcription_ready"] and report["conversion_ready"] else 2
        if args.command == "download-model":
            print(json.dumps(download_model(settings.model_dir, args.archive, args.sha256), indent=2))
            return 0
        runner = Runner(settings)
        if args.command == "retry":
            meeting = runner.store.get(args.meeting_id)
            if meeting.stage != "failed" or not meeting.retryable:
                raise InputError("This meeting is not eligible for retry.")
        else:
            path = args.recording.resolve()
            if not path.is_file() or not 0 < path.stat().st_size <= settings.max_upload_bytes:
                raise InputError("Provide a readable nonempty recording within the upload size limit.")
            meeting = runner.store.begin(path.name, args.title)
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
        return 0 if result.stage == "transcribed" else 1
    except (InputError, SetupError, OSError, ValueError) as exc:
        print(f"Metawispr: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
