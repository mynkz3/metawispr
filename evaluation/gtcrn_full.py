"""Full-recording GTCRN probe with the historical baseline's exact ASR windows."""
from datetime import datetime, timezone
from pathlib import Path
import json
import argparse
import time
import wave
from types import SimpleNamespace

import numpy as np
import sherpa_onnx

from gtcrn_probe import write_wav
from phase5 import aligned_wer
from metawispr.audio import Parakeet, file_sha256, asr_profile_matches
from metawispr.config import Settings
from metawispr.schemas import RawTranscript, Segment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume-asr', action='store_true', help='Reuse enhanced audio after an interrupted ASR probe.')
    args = parser.parse_args()
    root = Path('.cache/gtcrn-full-es2002a')
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'result.json').exists():
        raise SystemExit('Result exists; refusing an accidental rerun.')
    fixed = json.loads(Path('evaluation/baseline-es2002a.json').read_text())['baseline']
    baseline_path = Path(fixed['asr_source']['path'])
    assert file_sha256(baseline_path) == fixed['asr_source']['sha256']
    baseline = json.loads(baseline_path.read_text())
    old = RawTranscript.model_validate(baseline['raw'])
    settings = Settings.from_env()
    assert settings.asr_precision == 'int8' and settings.asr_provider == 'cuda'
    assert asr_profile_matches(old.model, settings)
    source = Path('.cache/ami/es2002a/prepared.wav')
    assert file_sha256(source) == old.audio_sha256
    with wave.open(str(source), 'rb') as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) == (1, 2, 16000)
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
    model = Path('models/gtcrn/gtcrn_simple.onnx')
    path = root / 'enhanced.wav'
    metadata = root / 'enhancement.json'
    if args.resume_asr:
        saved = json.loads(metadata.read_text())
        assert saved['source_sha256'] == old.audio_sha256 and saved['enhanced_sha256'] == file_sha256(path)
        assert saved['model_sha256'] == file_sha256(model)
        enhancement_seconds = saved['enhancement_seconds']
    else:
        enhance(source, model, path, samples, root)
        enhancement_seconds = json.loads(metadata.read_text())['enhancement_seconds']
    print(f'Full recording denoised in {enhancement_seconds:.2f} seconds', flush=True)
    asr = Parakeet(settings)
    asr.load()
    segments, decode_seconds = [], 0.0
    completed = []
    if (root / 'asr-windows.json').exists():
        completed = json.loads((root / 'asr-windows.json').read_text())
    with wave.open(str(path), 'rb') as audio:
        for index, item in enumerate(old.segments):
            if index < len(completed):
                window = completed[index]
                assert (window['id'], window['start'], window['end']) == (item.id, item.start, item.end)
            else:
                left, right = round(item.start * 16000), round(item.end * 16000)
                audio.setpos(left)
                block = np.frombuffer(audio.readframes(right-left), dtype='<i2').astype(np.float32) / 32768
                assert len(block) == right-left
                began = time.perf_counter()
                stream = asr.recognizer.create_stream()
                stream.accept_waveform(16000, block)
                asr.recognizer.decode_stream(stream)
                window = {'id':item.id, 'start':item.start, 'end':item.end, 'text':stream.result.text,
                          'decode_seconds':time.perf_counter() - began}
                completed.append(window)
                (root / 'asr-windows.json').write_text(json.dumps(completed), encoding='utf-8')
            decode_seconds += window['decode_seconds']
            if window['text'].strip():
                segments.append(Segment(**{k:window[k] for k in ('id','start','end','text')}))
            print(f'ASR {item.end:.1f}/{old.duration_seconds:.1f}s', flush=True)
    raw = RawTranscript(input_sha256=old.input_sha256, audio_sha256=file_sha256(path),
        duration_seconds=old.duration_seconds, segments=segments, model=asr.model_info,
        load_seconds=asr.load_seconds, decode_seconds=decode_seconds,
        created_at=datetime.now(timezone.utc).isoformat(), warnings=['Experimental enhanced audio; baseline nonempty windows reused.'])
    archive = Path('.cache/ami/ami_public_manual_1.6.2.zip')
    # Include empty decoded windows for scoring so lost boundary speech counts
    # as deletions rather than shrinking the evaluation interval.
    scoring = SimpleNamespace(duration_seconds=old.duration_seconds,
                              segments=[SimpleNamespace(**window) for window in completed])
    metrics = aligned_wer(scoring, 'ES2002a', archive)
    original = fixed['asr_word_errors']
    for key in ('reference_words', 'aligned_start_seconds', 'aligned_end_seconds', 'normalization', 'alignment'):
        assert metrics[key] == original[key], f'Evaluation changed: {key}'
    assert raw.model == old.model
    report = {'meeting':'ES2002a', 'scope':'Full recording denoised; WER on unchanged historical aligned interval.',
        'baseline_source_sha256':fixed['asr_source']['sha256'], 'source_audio_sha256':old.audio_sha256,
        'model_sha256':file_sha256(model), 'model_bytes':model.stat().st_size,
        'denoiser_provider':'cpu', 'denoiser_threads':1, 'enhancement_seconds':enhancement_seconds,
        'original_metrics':original, 'enhanced_metrics':metrics,
        'wer_change_percentage_points':100*(metrics['wer']-original['wer']),
        'raw':raw.model_dump(), 'qwen_run':False, 'production_enabled':False,
        'window_scope':'Only baseline nonempty ASR windows decoded; baseline omitted windows were not retested.',
        'empty_enhanced_windows':[w['id'] for w in completed if not w['text'].strip()]}
    (root / 'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (root / 'raw.json').write_text(raw.model_dump_json(indent=2),encoding='utf-8')
    print(json.dumps({'original_wer':original['wer'],'enhanced_wer':metrics['wer'],
                      'enhancement_seconds':enhancement_seconds,'decode_seconds':decode_seconds}),flush=True)


def enhance(source, model, path, samples, root):
    started = time.perf_counter()
    config = sherpa_onnx.OfflineSpeechDenoiserConfig(model=sherpa_onnx.OfflineSpeechDenoiserModelConfig(
        gtcrn=sherpa_onnx.OfflineSpeechDenoiserGtcrnModelConfig(model=str(model)),
        num_threads=1, provider='cpu', debug=False))
    assert config.validate()
    enhanced = sherpa_onnx.OfflineSpeechDenoiser(config)(np.ascontiguousarray(samples), 16000)
    enhancement_seconds = time.perf_counter() - started
    assert enhanced.sample_rate == 16000 and len(enhanced.samples) == len(samples)
    write_wav(path, enhanced.samples, 16000)
    (root / 'enhancement.json').write_text(json.dumps({'source_sha256':file_sha256(source),
        'enhanced_sha256':file_sha256(path), 'model_sha256':file_sha256(model),
        'enhancement_seconds':enhancement_seconds}),encoding='utf-8')


if __name__ == '__main__':
    main()
