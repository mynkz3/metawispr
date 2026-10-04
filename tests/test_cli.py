from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import json
import unittest

from metawispr.__main__ import main
from metawispr.config import Settings
from metawispr.pipeline import Runner
from support import FixtureASR, wav_bytes


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings = Settings(data_dir=self.root / "data", model_dir=self.root / "models")

    def invoke(self, arguments):
        output, error = StringIO(), StringIO()
        with patch("metawispr.__main__.Settings.from_env", return_value=self.settings), \
                redirect_stdout(output), redirect_stderr(error):
            result = main(arguments)
        return result, output.getvalue(), error.getvalue()

    def test_doctor_reports_missing_weights_without_downloading(self):
        result, output, error = self.invoke(["doctor"])
        report = json.loads(output)
        self.assertEqual(result, 2)
        self.assertFalse(report["transcription_ready"])
        self.assertEqual(len(report["missing_model_files"]), 4)
        self.assertEqual(error, "")
        self.assertFalse(self.settings.model_dir.exists())

    def test_missing_recording_is_a_readable_error(self):
        result, output, error = self.invoke(["transcribe", str(self.root / "absent.wav")])
        self.assertEqual(result, 1)
        self.assertIn("readable nonempty recording", error)
        self.assertEqual(output, "")
        self.assertEqual(list(self.settings.data_dir.glob("*/meeting.json")), [])

    def test_saved_setup_failure_can_be_retried_without_replacing_original(self):
        recording = self.root / "meeting.wav"
        recording.write_bytes(wav_bytes())
        result, output, error = self.invoke(["transcribe", str(recording), "--title", "CLI test"])
        failed = json.loads(output)
        self.assertEqual(result, 1)
        self.assertTrue(failed["meeting"]["retryable"])
        self.assertEqual(failed["meeting"]["failed_stage"], "transcribing")
        self.assertEqual(error, "")
        identifier = failed["meeting"]["id"]
        directory = Path(failed["artifacts"])
        self.assertEqual((directory / "original.wav").read_bytes(), recording.read_bytes())
        prepared_time = (directory / "prepared.wav").stat().st_mtime_ns
        runner = Runner(self.settings)
        runner.asr = FixtureASR()
        with patch("metawispr.__main__.Runner", return_value=runner):
            result, output, error = self.invoke(["retry", identifier])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output)["meeting"]["stage"], "transcribed")
        self.assertEqual((directory / "prepared.wav").stat().st_mtime_ns, prepared_time)
        self.assertEqual(runner.store.raw(identifier).model.runtime, "test-double")
        self.assertEqual(error, "")

    def test_invalid_offline_archive_returns_error_without_traceback(self):
        archive = self.root / "broken.tar.bz2"
        archive.write_bytes(b"not a model archive")
        result, output, error = self.invoke(["download-model", "--archive", str(archive)])
        self.assertEqual(result, 1)
        self.assertIn("not a readable tar.bz2", error)
        self.assertNotIn("Traceback", error)
        self.assertFalse(self.settings.model_dir.exists())


if __name__ == "__main__":
    unittest.main()
