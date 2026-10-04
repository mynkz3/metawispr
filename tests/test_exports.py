from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import json
import unittest

from metawispr.audio import file_sha256
from metawispr.config import Settings
from metawispr.exports import export_files, markdown_text
from metawispr.pipeline import Runner
from metawispr.schemas import Evidence, Fact, Task
from support import FixtureASR, FixtureLLM, wav_bytes


class ExportTests(unittest.TestCase):
    def test_nonempty_decisions_tasks_and_nulls_agree_and_markup_is_escaped(self):
        with TemporaryDirectory() as folder:
            settings = Settings(data_dir=Path(folder))
            runner = Runner(settings)
            runner.asr, runner.llm = FixtureASR(), FixtureLLM(settings)
            meeting = runner.store.begin("fixture.wav", "<script> & *test*")
            source = runner.store.directory(meeting.id) / meeting.source_name
            source.write_bytes(wav_bytes())
            meeting.input_sha256 = file_sha256(source)
            runner.store.put(meeting)
            runner.run(meeting.id)
            raw, refined, document = runner.store.raw(meeting.id), runner.store.refined(meeting.id), runner.store.document(meeting.id)
            evidence = [Evidence(segment_id="s00001", quote="do not change 15 to 50")]
            document.record.decisions = [Fact(text="Preserve 15, not 50", evidence=evidence)]
            document.record.tasks = [Task(text="Review <script> [links]", owner=None, deadline=None, evidence=evidence)]
            files = export_files(meeting, raw, refined, document)
            output = json.loads(files["meeting.json"])
            text = files["meeting.md"].decode()
            for item in [*output["record"]["decisions"], *output["record"]["tasks"]]:
                self.assertIn(markdown_text(item["text"]), text)
            self.assertIn("Owner: Unspecified; deadline: Unspecified", text)
            self.assertNotIn("<script>", text)
            self.assertIn("&lt;script&gt;", text)
            self.assertIn("0.00–0.25s", text)
            with ZipFile(BytesIO(files["bundle.zip"])) as archive:
                for name, content in files.items():
                    if name != "bundle.zip":
                        self.assertEqual(archive.read(name), content)


if __name__ == "__main__":
    unittest.main()
