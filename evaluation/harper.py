"""Two frozen short HarperValleyBank calls through the unchanged production Runner."""
from dataclasses import replace
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import json
import re
import shutil
import subprocess
import time
import wave

import numpy as np

from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.documentation import documentation_policy, refinement_policy
from metawispr.exports import export_files
from metawispr.pipeline import Runner
from phase5 import tokens, word_errors


ROOT = Path('.cache/harper')
IDS = ['01cefd6f5c044a6f', '01f7ec3700424bc0']
OUTPUT = Path('evaluation/results/harper-short-calls.json')


def mix_call(sid):
    """Same-time channels, averaged at native rate; never trim or time-shift."""
    channels, parameters = [], []
    for role in ('agent', 'caller'):
        with wave.open(str(ROOT/'data/audio'/role/(sid+'.wav')), 'rb') as source:
            parameters.append(source.getparams())
            channels.append(np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.int32))
    assert parameters[0] == parameters[1]
    spec = parameters[0]
    assert spec.nchannels == 1 and spec.sampwidth == 2 and spec.comptype == 'NONE'
    duration = spec.nframes/spec.framerate
    assert 60 <= duration <= 120
    path = ROOT/sid/'mixed.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as output:
        output.setparams(spec)
        output.writeframes(np.rint((channels[0]+channels[1])/2).astype('<i2').tobytes())
    return path, duration


def main():
    if OUTPUT.exists():
        raise SystemExit('Saved results exist; refusing an accidental rerun.')
    settings = Settings.from_env()
    assert settings.use_gtcrn and settings.asr_provider == 'cuda' and settings.asr_precision == 'int8'
    assert settings.refiner_model == settings.documenter_model == 'qwen3.5:4b'
    revision = json.loads((ROOT/'tree.json').read_text())['sha']
    report = {'dataset':'Gridspace-Stanford Harper Valley', 'repository_revision':revision,
              'attribution':'Gridspace and Stanford; CC BY 4.0; https://github.com/cricketclub/gridspace-stanford-harper-valley',
              'selection':'First two lexically sorted IDs with equal channel file sizes between 960100 and 1919000 bytes; verified complete duration 60-120 seconds before inference. No selection by model results.',
              'scope':'Two simulated human-spoken banking calls; fast development checks, not real meeting-minutes or held-out meeting acceptance.',
              'normalization':'Full-call lowercase WER; punctuation to separators, apostrophes retained, non-speech bracket/angle annotations removed from references; no number expansion.',
              'channel_handling':'Average synchronized channels at original rate; no trimming, cropping or shifts; normal production conversion to mono 16 kHz follows.',
              'reference_use':'Human transcripts are read only for scoring after generation, never injected into model input. Empty glossary; generic call title.',
              'git_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'started_at':datetime.now(timezone.utc).isoformat(),
              'documentation_policy':documentation_policy(settings),
              'refinement_policy':refinement_policy(settings,''), 'calls':[]}
    for sid in IDS:
        path, duration = mix_call(sid)
        runner = Runner(replace(settings,data_dir=ROOT/sid/'run-data'))
        meeting = runner.store.begin('short-call.wav','Short banking dialogue')
        directory = runner.store.directory(meeting.id)
        shutil.copyfile(path, directory/meeting.source_name)
        meeting.input_sha256 = file_sha256(path)
        meeting.size_bytes = path.stat().st_size
        runner.store.put(meeting)
        print(f'{sid}: starting complete {duration:.2f}s call',flush=True)
        started = time.perf_counter()
        runner.run(meeting.id)
        elapsed = time.perf_counter()-started
        state = runner.store.get(meeting.id)
        raw, refined, document = (runner.store.raw(meeting.id), runner.store.refined(meeting.id), runner.store.document(meeting.id))
        annotations = json.loads((ROOT/'data/transcript'/(sid+'.json')).read_text())
        ordered = sorted(annotations,key=lambda item:(item['start_ms'],item['channel_index'],item['index']))
        reference = ' '.join(re.sub(r'\[[^\]]*\]|<[^>]*>',' ',item['human_transcript']) for item in ordered)
        entry = {'id':sid, 'duration_seconds':duration,'wall_seconds':elapsed,
                 'source_hashes':{role:file_sha256(ROOT/'data/audio'/role/(sid+'.wav')) for role in ('agent','caller')},
                 'mixed_sha256':meeting.input_sha256,
                 'transcript_sha256':file_sha256(ROOT/'data/transcript'/(sid+'.json')),
                 'meeting':state.model_dump(),'reference_text':reference,
                 'raw':raw.model_dump() if raw else None,
                 'refined':refined.model_dump() if refined else None,
                 'document':document.model_dump() if document else None}
        if raw:
            entry['raw_wer'] = word_errors(tokens(reference),tokens(' '.join(s.text for s in raw.segments)))
        if refined:
            entry['refined_wer'] = word_errors(tokens(reference),tokens(' '.join(s.text for s in refined.segments)))
        if document:
            files = export_files(state,raw,refined,document)
            with ZipFile(BytesIO(files['bundle.zip'])) as bundle:
                assert all(bundle.read(name)==body for name,body in files.items() if name!='bundle.zip')
            assert json.loads(files['meeting.json'])['record']==document.record.model_dump()
            entry['exports_consistent'] = True
            (ROOT/sid/'meeting.md').write_bytes(files['meeting.md'])
        report['calls'].append(entry)
        OUTPUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({'id':sid,'stage':state.stage,'seconds':elapsed,'wer':entry.get('raw_wer',{}).get('wer'),'error':state.error}),flush=True)
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    OUTPUT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__ == '__main__':
    main()
