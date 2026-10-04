from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import unittest
import wave

import numpy as np

from metawispr.audio import Parakeet, audio_windows, file_sha256, inspect_pcm, prepare_audio
from metawispr.config import InputError, Settings, SetupError
from support import FixtureASR, wav_bytes


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings = Settings(data_dir=self.root / "data", model_dir=self.root / "missing-model")
        self.source, self.prepared = self.root / "original.wav", self.root / "prepared.wav"

    def test_normalized_wav_preserves_original_without_decoder(self):
        content = wav_bytes()
        self.source.write_bytes(content)
        with patch("metawispr.audio.ffmpeg_executable", side_effect=AssertionError("decoder should not run")):
            self.assertEqual(prepare_audio(self.source, self.prepared, self.settings), 0.25)
        self.assertEqual(self.source.read_bytes(), content)
        self.assertEqual(self.prepared.read_bytes(), content)

    def test_empty_recording_is_rejected(self):
        self.source.touch()
        with self.assertRaisesRegex(InputError, "empty"):
            prepare_audio(self.source, self.prepared, self.settings)

    def test_truncated_pcm_does_not_become_a_checkpoint(self):
        self.source.write_bytes(wav_bytes()[:-20])
        with self.assertRaisesRegex(InputError, "truncated"):
            prepare_audio(self.source, self.prepared, self.settings)
        self.assertFalse(self.prepared.exists())

    def test_duration_and_upload_limits_reject_audio(self):
        self.source.write_bytes(wav_bytes(seconds=1.1))
        with self.assertRaisesRegex(InputError, "duration"):
            inspect_pcm(self.source, 1)
        settings = Settings(data_dir=self.root, max_upload_bytes=1)
        with self.assertRaisesRegex(InputError, "size"):
            prepare_audio(self.source, self.prepared, settings)

    def test_wrong_sample_rate_requires_conversion(self):
        self.source.write_bytes(wav_bytes(rate=8000, channels=2))
        with patch("metawispr.audio.ffmpeg_executable", side_effect=SetupError("missing decoder")):
            with self.assertRaisesRegex(SetupError, "missing decoder"):
                prepare_audio(self.source, self.prepared, self.settings)
        self.assertFalse(self.prepared.exists())

    def test_conversion_is_bounded_and_does_not_use_a_shell(self):
        self.source.write_bytes(b"invalid compressed recording")
        with patch("metawispr.audio.ffmpeg_executable", return_value="ffmpeg"), patch(
            "metawispr.audio.subprocess.run", return_value=subprocess.CompletedProcess([], 1, stderr=b"invalid")
        ) as run:
            with self.assertRaisesRegex(InputError, "decoded"):
                prepare_audio(self.source, self.prepared, self.settings)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-protocol_whitelist") + 1], "file,pipe")
        self.assertIn("-format_whitelist", command)
        self.assertIn("-t", command)
        self.assertEqual(run.call_args.kwargs["timeout"], 180)
        self.assertNotIn("shell", run.call_args.kwargs)

    def test_conversion_timeout_removes_partial_working_copy(self):
        self.source.write_bytes(b"not WAV")
        def timeout(command, **_):
            Path(command[-1]).write_bytes(b"partial")
            raise subprocess.TimeoutExpired(command, 180)
        with patch("metawispr.audio.ffmpeg_executable", return_value="ffmpeg"), patch(
            "metawispr.audio.subprocess.run", side_effect=timeout
        ):
            with self.assertRaisesRegex(InputError, "timed out"):
                prepare_audio(self.source, self.prepared, self.settings)
        self.assertFalse((self.root / "prepared.partial.wav").exists())
        self.assertEqual(self.source.read_bytes(), b"not WAV")

    def test_windows_cover_every_original_frame_once(self):
        self.source.write_bytes(wav_bytes(seconds=11.25))
        with wave.open(str(self.source), "rb") as source:
            expected = np.frombuffer(source.readframes(source.getnframes()), dtype="<i2").astype(np.float32) / 32768
        windows = list(audio_windows(self.source, 5))
        np.testing.assert_array_equal(np.concatenate([item[2] for item in windows]), expected)
        self.assertEqual(windows[0][0], 0.0)
        self.assertEqual(windows[-1][1], 11.25)
        for left, right in zip(windows, windows[1:]):
            self.assertEqual(left[1], right[0])
        self.assertTrue(all(len(samples) <= 5 * 16000 for _, _, samples in windows))

    def test_silence_does_not_load_or_hallucinate_a_model(self):
        self.source.write_bytes(wav_bytes(silent=True))
        asr = Parakeet(self.settings)
        with patch.object(asr, "load", side_effect=AssertionError("silence must not load ASR")):
            with self.assertRaisesRegex(InputError, "No speech"):
                asr.transcribe(self.source, file_sha256(self.source), "test-time")

    def test_missing_weights_fail_instead_of_using_fake_output(self):
        self.source.write_bytes(wav_bytes())
        with self.assertRaisesRegex(SetupError, "files are missing"):
            Parakeet(self.settings).transcribe(self.source, file_sha256(self.source), "test-time")

    def test_recognizer_text_and_global_window_offsets_are_preserved(self):
        self.source.write_bytes(wav_bytes(seconds=2.5))
        settings = Settings(data_dir=self.root, model_dir=self.root, chunk_seconds=1)
        asr = Parakeet(settings)
        # An explicit native-interface double; this is not a Parakeet inference result.
        stream = lambda: SimpleNamespace(
            accept_waveform=lambda rate, samples: None,
            result=SimpleNamespace(text="  Native-interface test fixture.  "),
        )
        asr.recognizer = SimpleNamespace(create_stream=stream, decode_stream=lambda stream: None)
        asr.model_info = FixtureASR().transcribe(self.source, file_sha256(self.source), "test-time").model
        progress = []
        raw = asr.transcribe(self.source, file_sha256(self.source), "test-time", progress.append)
        self.assertEqual([(s.start, s.end) for s in raw.segments], [(0.0, 1.0), (1.0, 2.0), (2.0, 2.5)])
        self.assertEqual(progress, [1.0, 2.0, 2.5])
        self.assertTrue(all(s.text == "  Native-interface test fixture.  " for s in raw.segments))
        self.assertEqual(raw.timing, "audio_window")
        self.assertEqual(raw.model.runtime, "test-double")

    def test_raw_contract_rejects_infinite_or_overlapping_timestamps(self):
        self.source.write_bytes(wav_bytes())
        raw = FixtureASR().transcribe(self.source, file_sha256(self.source), "test-time")
        for end in [float("inf"), 5.0]:
            data = raw.model_dump()
            data["segments"][0]["end"] = end
            with self.assertRaises(ValueError):
                type(raw).model_validate(data)
        for identifier in ["s00001", "s00002"]:
            data = raw.model_dump()
            data["segments"].append({"id": identifier, "start": 0.1, "end": 0.2, "text": "overlap"})
            with self.assertRaises(ValueError):
                type(raw).model_validate(data)


if __name__ == "__main__":
    unittest.main()
