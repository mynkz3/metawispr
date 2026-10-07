"""One ES2002a documentation run using the manual transcript, without ASR/refinement."""
from dataclasses import replace
from pathlib import Path
import json
import time
import argparse

from ami import read, save, source_input
from run import MeasuredOllama
from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.documentation import Documentation, documentation_policy
from metawispr.exports import markdown
from metawispr.llm import digest, prompt
from metawispr.pipeline import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resume', action='store_true', help='Resume the failed test once using saved calls.')
    args = parser.parse_args()
    root = Path('.cache/ami/es2002a')
    previous = Path('.cache/manual-es2002a/result.json')
    output = previous.with_name('result-resumed.json') if args.resume else previous
    if output.exists():
        raise SystemExit('Result already exists; refusing an accidental rerun.')
    manual, manifest = read(root / 'manual.json'), read(root / 'manifest.json')
    assert manual['meeting'] == 'ES2002a'
    assert digest(manual) == manifest['manual_input_sha256']
    settings = replace(Settings.from_env(), data_dir=output.parent / 'data')
    store, llm = Store(settings), MeasuredOllama(settings, cpu=False)
    prior = read(previous) if args.resume else None
    if prior:
        assert prior['stage'] == 'failed' and prior['manual_sha256'] == file_sha256(root / 'manual.json')
    meeting = store.get(prior['meeting_id']) if prior else store.begin('manual-transcript.wav', 'ES2002a')
    report = {'scope': 'Manual-transcript documentation test; no ASR or refinement. Not a controlled audit ablation.',
              'manual_sha256': file_sha256(root / 'manual.json'), 'meeting_id': meeting.id,
              'model': llm.models()[1].model_dump(), 'context': settings.llm_context,
              'output_tokens': settings.llm_output_tokens, 'policy': documentation_policy(settings),
              'prompts': {name: digest(prompt(name)) for name in
                          ('document', 'review', 'notes', 'reconcile', 'consolidate', 'audit')}}
    started = time.perf_counter()
    if prior:
        assert prior['model'] == report['model'] and prior['prompts'] == report['prompts']
        assert prior['context'] == report['context'] and prior['output_tokens'] == report['output_tokens']
        report.update(resumed_from=str(previous), prior_wall_seconds=prior['wall_seconds'])
    try:
        document = Documentation(settings, store, llm).document(
            meeting, source_input(manual), llm.models()[1],
            lambda count: print(f'Completed documentation calls: {count}', flush=True))
        report.update(stage='complete', document=document.model_dump())
        (output.parent / 'meeting.md').write_text(markdown(meeting, source_input(manual), document), encoding='utf-8')
    except Exception as exc:
        report.update(stage='failed', error=str(exc))
    finally:
        report.update(wall_seconds=time.perf_counter() - started, measurements=llm.measurements)
        directory = store.directory(meeting.id) / 'documenting'
        report['saved_calls'] = [read(path) for path in sorted((directory / 'calls').glob('*.json'))]
        report['failures'] = [read(path) for path in sorted((directory / 'failed').glob('*.json'))]
        save(output, report)
    print(json.dumps({key: report[key] for key in ('stage', 'wall_seconds')}), flush=True)
    return 0 if report['stage'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
