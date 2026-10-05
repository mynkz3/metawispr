from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import tarfile
import unittest

from metawispr.audio import file_sha256
from metawispr.config import MODEL_FILES, MODEL_PACKAGE, InputError, SetupError
from metawispr.models import install_archive


class ModelArchiveTests(unittest.TestCase):
    """Artificial archive members exercise extraction safety, not ONNX validity."""

    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.archive = self.root / "fixture.tar.bz2"
        self.destination = self.root / "models" / MODEL_PACKAGE

    def write_archive(self, extra=None):
        with tarfile.open(self.archive, "w:bz2") as archive:
            for name in MODEL_FILES:
                data = b"test fixture, not actual ONNX weights"
                member = tarfile.TarInfo(f"{MODEL_PACKAGE}/{name}")
                member.size = len(data)
                archive.addfile(member, BytesIO(data))
            if extra:
                archive.addfile(extra, BytesIO(b"x") if extra.isfile() else None)

    def test_regular_files_install_with_recorded_hashes(self):
        self.write_archive()
        result = install_archive(self.archive, self.destination, file_sha256(self.archive))
        self.assertTrue(result["checksum_supplied"])
        self.assertEqual(result["file_sha256"]["encoder.int8.onnx"], file_sha256(self.destination / "encoder.int8.onnx"))
        self.assertEqual(json.loads((self.destination / "metawispr-manifest.json").read_text()), result)

    def test_paths_outside_destination_are_rejected(self):
        for path in ("../../outside.txt", "tokens.txt:payload", r"folder\outside.txt"):
            with self.subTest(path=path):
                member = tarfile.TarInfo(f"{MODEL_PACKAGE}/{path}")
                member.size = 1
                self.write_archive(member)
                with self.assertRaisesRegex(InputError, "unsafe"):
                    install_archive(self.archive, self.destination)
                self.assertFalse(self.destination.exists())
                self.assertFalse((self.root / "outside.txt").exists())

    def test_symlinks_and_duplicate_files_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.REGTYPE):
            member = tarfile.TarInfo(f"{MODEL_PACKAGE}/encoder.int8.onnx")
            member.type = kind
            member.linkname = "../../outside"
            member.size = 1 if kind == tarfile.REGTYPE else 0
            self.write_archive(member)
            with self.assertRaises(InputError):
                install_archive(self.archive, self.destination)
            self.assertFalse(self.destination.exists())

    def test_checksum_mismatch_and_existing_directory_are_rejected(self):
        self.write_archive()
        with self.assertRaisesRegex(InputError, "SHA-256"):
            install_archive(self.archive, self.destination, "0" * 64)
        self.destination.mkdir()
        marker = self.destination / "keep.txt"
        marker.write_text("existing data")
        with self.assertRaisesRegex(SetupError, "already exists"):
            install_archive(self.archive, self.destination)
        self.assertEqual(marker.read_text(), "existing data")

    def test_fp16_variant_records_distinct_package_and_rejects_int8_archive(self):
        package = "sherpa-onnx-nemo-parakeet-tdt-0.6b-v2-fp16"
        destination = self.root / "models" / package
        self.write_archive()
        with self.assertRaisesRegex(InputError, "Unexpected or unsafe path"):
            install_archive(self.archive, destination, precision="fp16")
        with tarfile.open(self.archive, "w:bz2") as archive:
            for name in ("encoder.fp16.onnx", "decoder.fp16.onnx", "joiner.fp16.onnx", "tokens.txt"):
                data = b"fp16 fixture"
                member = tarfile.TarInfo(f"{package}/{name}")
                member.size = len(data)
                archive.addfile(member, BytesIO(data))
        result = install_archive(self.archive, destination, file_sha256(self.archive), precision="fp16")
        self.assertEqual(result["package"], package)
        self.assertEqual(result["archive_sha256"], file_sha256(self.archive))
        self.assertEqual(result["file_sha256"]["encoder.fp16.onnx"], file_sha256(destination / "encoder.fp16.onnx"))


if __name__ == "__main__":
    unittest.main()
