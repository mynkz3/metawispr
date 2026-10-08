"""Recovery must publish only independently validated claims, never broken actions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.exports import export_files
from metawispr.pipeline import Runner
from metawispr.llm import digest
from support import FixtureASR, FixtureLLM, wav_bytes


class PartialDocumentationTests(unittest.TestCase):
    def test_broken_refinement_preserves_asr_and_allows_valid_summary(self):
        def request(original, method, path, body=None, timeout=None):
            if 'edits' in body['format']['properties']:
                return {'done': True, 'done_reason': 'stop', 'message': {'content': '{}'}}
            return original(method, path, body, timeout)
        runner, meeting = self.run_meeting(request)
        self.assertEqual(runner.store.get(meeting.id).stage, 'complete')
        refined = runner.store.refined(meeting.id)
        self.assertEqual(refined.segments, runner.store.raw(meeting.id).segments)
        self.assertEqual(refined.accepted, [])
        self.assertIn('unavailable', refined.warnings[0])
        self.assertTrue(runner.store.document(meeting.id).record.summary)

    def test_legacy_raw_hash_without_enhancement_still_validates_and_tampering_fails(self):
        runner, meeting = self.run_meeting(lambda original, *args, **kwargs: original(*args, **kwargs))
        raw = runner.store.read_json(meeting.id, 'raw.json')
        raw.pop('enhancement')
        refined = runner.store.read_json(meeting.id, 'refined.json')
        refined['source_sha256'] = digest(raw)
        runner.store.write_json(meeting.id, 'raw.json', raw)
        runner.store.write_json(meeting.id, 'refined.json', refined)
        self.assertIsNotNone(runner.store.refined(meeting.id))
        raw['segments'][0]['text'] = 'Tampered content'
        runner.store.write_json(meeting.id, 'raw.json', raw)
        from metawispr.config import SetupError
        with self.assertRaises(SetupError):
            runner.store.refined(meeting.id)

    def run_meeting(self, request):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        settings = Settings(data_dir=Path(folder.name))
        runner = Runner(settings)
        llm = FixtureLLM(settings)
        original = llm.request
        llm.request = lambda *args, **kwargs: request(original, *args, **kwargs)
        runner.asr, runner.llm = FixtureASR(), llm
        meeting = runner.store.begin('fixture.wav', 'Synthetic recovery check')
        source = runner.store.directory(meeting.id) / meeting.source_name
        source.write_bytes(wav_bytes())
        meeting.input_sha256 = file_sha256(source)
        runner.store.put(meeting)
        runner.run(meeting.id)
        return runner, meeting

    def test_broken_actions_yield_valid_summary_and_explicit_unavailable_exports(self):
        def request(original, method, path, body=None, timeout=None):
            if 'tasks' in body['format']['properties']:
                return {'done': True, 'done_reason': 'stop', 'message': {'content': '{}'}}
            return original(method, path, body, timeout)
        runner, meeting = self.run_meeting(request)
        self.assertEqual(runner.store.get(meeting.id).stage, 'complete')
        document = runner.store.document(meeting.id)
        self.assertTrue(document.record.summary)
        self.assertEqual(document.record.tasks, [])
        self.assertEqual(document.unavailable_sections, ['tasks', 'decisions'])
        outputs = export_files(meeting, runner.store.raw(meeting.id), runner.store.refined(meeting.id), document)
        self.assertIn(b'Unavailable: generation or validation failed', outputs['meeting.md'])
        self.assertEqual(json.loads(outputs['meeting.json'])['unavailable_sections'], ['tasks', 'decisions'])

    def test_incomplete_audit_batch_recovers_each_claim_without_weakening_coverage(self):
        attempts = []
        def request(original, method, path, body=None, timeout=None):
            payload = json.loads(body['messages'][1]['content'])
            if 'verdicts' in body['format']['properties']:
                attempts.append(len(payload['candidates']))
                if len(attempts) <= 2:
                    return {'done': True, 'done_reason': 'stop', 'message': {'content': '{"verdicts":[]}'}}
            result = original(method, path, body, timeout)
            if 'summary' in body['format']['properties']:
                value = json.loads(result['message']['content'])
                value['summary'].append({**value['summary'][0], 'text': 'Second explicit fixture summary'})
                result['message']['content'] = json.dumps(value)
            return result
        runner, meeting = self.run_meeting(request)
        self.assertEqual(runner.store.get(meeting.id).stage, 'complete')
        self.assertTrue(runner.store.document(meeting.id).record.summary)
        self.assertEqual(attempts, [2, 2, 1, 1])

    def test_summary_failing_support_audit_is_not_published(self):
        def request(original, method, path, body=None, timeout=None):
            properties = body['format']['properties']
            if 'tasks' in properties:
                return {'done': True, 'done_reason': 'stop', 'message': {'content': '{}'}}
            result = original(method, path, body, timeout)
            if 'verdicts' in properties:
                value = json.loads(result['message']['content'])
                for verdict in value['verdicts']:
                    verdict['verdict'] = 'unsupported'
                result['message']['content'] = json.dumps(value)
            return result
        runner, meeting = self.run_meeting(request)
        self.assertEqual(runner.store.get(meeting.id).stage, 'failed')
        self.assertIsNone(runner.store.document(meeting.id))


if __name__ == '__main__':
    unittest.main()
