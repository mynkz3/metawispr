"""One paired GTCRN/original-audio WER probe; no Qwen or production changes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import time
import wave
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import numpy as np
import sherpa_onnx

from phase5 import tokens, word_errors
from metawispr.audio import Parakeet, file_sha256
from metawispr.config import Settings


def write_wav(path, samples, rate):
    with wave.open(str(path), 'wb') as target:
        target.setparams((1, 2, rate, len(samples), 'NONE', 'not compressed'))
        target.writeframes((np.clip(samples, -1, 1) * 32767).round().astype('<i2').tobytes())


def main():
    root = Path('.cache/gtcrn-probe')
    root.mkdir(parents=True, exist_ok=True)
    output = root / 'result.json'
    if output.exists():
        raise SystemExit('Result already exists; refusing an accidental rerun.')
    settings = Settings.from_env()
    assert settings.asr_precision == 'int8' and settings.asr_provider == 'cuda'
    source = Path('.cache/ami/es2002a/prepared.wav')
    model = Path('models/gtcrn/gtcrn_simple.onnx')
    start, end = 450, 630
    with wave.open(str(source), 'rb') as audio:
        rate = audio.getframerate()
        assert (audio.getnchannels(), audio.getsampwidth(), rate) == (1, 2, 16000)
        audio.setpos(start * rate)
        samples = np.frombuffer(audio.readframes((end - start) * rate), dtype='<i2').astype(np.float32) / 32768
    assert len(samples) == (end - start) * rate
    # Preserve the original PCM bytes exactly in the control arm.
    with wave.open(str(root / 'original.wav'), 'wb') as target:
        target.setparams((1, 2, rate, len(samples), 'NONE', 'not compressed'))
        target.writeframes((samples * 32768).astype('<i2').tobytes())
    config = sherpa_onnx.OfflineSpeechDenoiserConfig(model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
        gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=str(model)),
        num_threads=1, provider='cpu', debug=False))
    assert config.validate()
    began = time.perf_counter()
    denoiser = sherpa_onnx.OfflineSpeechDenoiser(config)
    enhanced = denoiser(np.ascontiguousarray(samples), rate)
    enhancement_seconds = time.perf_counter() - began
    assert enhanced.sample_rate == rate and len(enhanced.samples) == len(samples), 'Enhancement changed audio alignment'
    write_wav(root / 'enhanced.wav', enhanced.samples, rate)
    words = []
    archive = Path('.cache/ami/ami_public_manual_1.6.2.zip')
    with ZipFile(archive) as zipped:
        for name in zipped.namelist():
            if Path(name).name.startswith('ES2002a.') and name.endswith('.words.xml'):
                for word in ET.fromstring(zipped.read(name)):
                    if word.tag == 'w' and word.get('punc') != 'true' and tokens(word.text or ''):
                        left, right = float(word.get('starttime')), float(word.get('endtime'))
                        if start <= (left + right) / 2 < end:
                            words.append((left, Path(name).name, right, word.text))
    words.sort(key=lambda item: (item[0], item[1], item[2]))
    reference = [t for *_, text in words for t in tokens(text)]
    assert reference
    report = {'meeting': 'ES2002a', 'scope': 'Single preselected excerpt, not full-meeting WER.',
              'interval_seconds': [start, end], 'duration_seconds': end-start,
              'model_bytes': model.stat().st_size, 'model_sha256': file_sha256(model),
              'model_url': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speech-enhancement-models/gtcrn_simple.onnx',
              'source_sha256': file_sha256(source), 'annotations_sha256': file_sha256(archive),
              'enhancement_seconds': enhancement_seconds, 'denoiser_provider': 'cpu',
              'normalization': 'Existing Phase 5 lowercase/punctuation/apostrophe tokenization; no number expansion.',
              'alignment': 'Reference word midpoint within excerpt; overlapping speakers sorted by start and speaker file.',
              'chunk_seconds': settings.chunk_seconds, 'reference_words': len(reference), 'arms': {}}
    asr = Parakeet(settings)
    for arm in ('original', 'enhanced'):
        path = root / (arm + '.wav')
        raw = asr.transcribe(path, file_sha256(path), datetime.now(timezone.utc).isoformat())
        text = ' '.join(s.text for s in raw.segments)
        report['arms'][arm] = {**word_errors(reference, tokens(text)), 'transcript': text,
                               'decode_seconds': raw.decode_seconds, 'load_seconds': raw.load_seconds,
                               'audio_sha256': raw.audio_sha256, 'asr_model': raw.model.model_dump()}
        (root / (arm + '-raw.json')).write_text(raw.model_dump_json(indent=2), encoding='utf-8')
        print(arm, report['arms'][arm]['wer'], flush=True)
    assert report['arms']['original']['asr_model'] == report['arms']['enhanced']['asr_model']
    report['wer_change_percentage_points'] = 100 * (report['arms']['enhanced']['wer'] - report['arms']['original']['wer'])
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'enhancement_seconds': enhancement_seconds, 'wer_change_percentage_points': report['wer_change_percentage_points']}))


if __name__ == '__main__':
    main()
