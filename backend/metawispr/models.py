"""Install the documented model package, with bounded download and safe extraction."""

from pathlib import Path, PurePosixPath
from urllib.request import urlopen
import json
import shutil
import tarfile
import tempfile

from .audio import file_sha256
from .config import ASR_VARIANTS, MODEL_ID, MODEL_URL, InputError, SetupError


MAX_ARCHIVE_BYTES = 1024 * 1024 * 1024


def install_archive(archive: Path, destination: Path, expected_sha256: str | None = None,
                    precision: str = "int8"):
    package_name, files = ASR_VARIANTS[precision]
    archive_limit = MAX_ARCHIVE_BYTES * (2 if precision == "fp16" else 1)
    destination = destination.resolve()
    root = destination.parent
    root.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise SetupError("The model directory already exists. Verify it with doctor; installation never overwrites it.")
    if archive.stat().st_size > archive_limit:
        raise InputError("The model archive exceeds the selected precision's installation limit.")
    archive_hash = file_sha256(archive)
    if expected_sha256 and archive_hash != expected_sha256.lower():
        raise InputError("Model archive SHA-256 does not match the supplied checksum.")
    with tempfile.TemporaryDirectory(prefix="parakeet-install-", dir=root) as temporary:
        staging = Path(temporary).resolve()
        if not staging.is_relative_to(root) or not destination.is_relative_to(root):
            raise InputError("Model installation path escapes the selected directory.")
        extracted = set()
        expanded_size = 0
        with tarfile.open(archive, "r:bz2") as package:
            for index, member in enumerate(package):
                name = PurePosixPath(member.name)
                if index >= 1000 or name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != package_name:
                    raise InputError("Unexpected or unsafe path in the model archive.")
                if any("\\" in part or ":" in part for part in name.parts):
                    raise InputError("Unexpected or unsafe path in the model archive.")
                if member.isdir():
                    continue
                if not member.isfile() or member.size < 0:
                    raise InputError("Model archives may contain only regular files and directories.")
                relative = Path(*name.parts[1:])
                target = (staging / relative).resolve()
                identity = relative.as_posix().casefold()
                if not relative.parts or not target.is_relative_to(staging) or identity in extracted:
                    raise InputError("Duplicate or unsafe file in the model archive.")
                expanded_size += member.size
                if expanded_size > archive_limit:
                    raise InputError("Expanded model archive exceeds the selected precision's installation limit.")
                extracted.add(identity)
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.extractfile(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        missing = [name for name in files if not (staging / name).is_file() or not (staging / name).stat().st_size]
        if missing:
            raise InputError("Model archive is missing the required encoder, decoder, joiner, or token files.")
        source_url = MODEL_URL if precision == "int8" else MODEL_URL.replace("-int8.tar.bz2", "-fp16.tar.bz2")
        manifest = {"model_id": MODEL_ID, "package": package_name, "source_url": source_url,
                    "archive_sha256": archive_hash, "checksum_supplied": bool(expected_sha256),
                    "file_sha256": {name: file_sha256(staging / name) for name in files},
                    "attribution": f"NVIDIA Parakeet v2 (CC BY 4.0); {precision.upper()} export by sherpa-onnx maintainers",
                    "base_model_url": "https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2"}
        (staging / "metawispr-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        staging.rename(destination)
    return manifest


def download_model(destination: Path, archive: Path | None = None,
                   expected_sha256: str | None = None, precision: str = "int8"):
    if precision not in ASR_VARIANTS:
        raise ValueError("ASR precision must be int8 or fp16")
    archive_limit = MAX_ARCHIVE_BYTES * (2 if precision == "fp16" else 1)
    if archive is not None:
        try:
            return install_archive(archive.resolve(), destination, expected_sha256, precision)
        except tarfile.TarError as exc:
            raise InputError("The model archive is not a readable tar.bz2 file.") from exc
    root = destination.resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, suffix=".tar.bz2", delete=False) as target:
            temporary = Path(target.name)
            source_url = MODEL_URL if precision == "int8" else MODEL_URL.replace("-int8.tar.bz2", "-fp16.tar.bz2")
            with urlopen(source_url, timeout=30) as response:
                size = 0
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    size += len(block)
                    if size > archive_limit:
                        raise InputError("Downloaded model archive exceeds the selected precision's installation limit.")
                    target.write(block)
        try:
            return install_archive(temporary, destination, expected_sha256, precision)
        except tarfile.TarError as exc:
            raise InputError("The downloaded model archive is not a readable tar.bz2 file.") from exc
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
