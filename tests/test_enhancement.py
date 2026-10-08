from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import numpy as np

from metawispr.audio import enhance_prepared_audio, file_sha256, inspect_pcm
from metawispr.config import InputError, Settings, SetupError
from support import wav_bytes


class EnhancementTests(unittest.TestCase):
    def test_preserves_duration_normalized_source_and_reuses_hash_checked_output(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            prepared, model = root / 'prepared.wav', root / 'gtcrn.onnx'
            original = wav_bytes()
            prepared.write_bytes(original)
            model.write_bytes(b'fixture weights; not an ONNX model')
            settings = replace(Settings(), use_gtcrn=True, gtcrn_model=model)
            denoiser = lambda samples, rate: SimpleNamespace(samples=np.zeros_like(samples), sample_rate=rate)
            with patch('sherpa_onnx.OfflineSpeechDenoiser', return_value=denoiser):
                metadata = enhance_prepared_audio(prepared, settings)
            self.assertEqual((root / 'normalized.wav').read_bytes(), original)
            self.assertEqual(inspect_pcm(prepared, 10), 0.25)
            self.assertEqual(metadata.enhanced_sha256, file_sha256(prepared))
            with patch('sherpa_onnx.OfflineSpeechDenoiser', side_effect=AssertionError('must not denoise twice')):
                self.assertEqual(enhance_prepared_audio(prepared, settings), metadata)
            prepared.write_bytes(original)
            with self.assertRaises(InputError):
                enhance_prepared_audio(prepared, settings)

    def test_missing_weights_fail_clearly_without_overwriting_audio(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            prepared = root / 'prepared.wav'
            original = wav_bytes()
            prepared.write_bytes(original)
            with self.assertRaisesRegex(SetupError, 'GTCRN weights missing'):
                enhance_prepared_audio(prepared, replace(Settings(), use_gtcrn=True, gtcrn_model=root/'missing'))
            self.assertEqual(prepared.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
