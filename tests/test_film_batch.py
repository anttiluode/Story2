"""Film Lab full-book orchestration checks; no image model or cloud needed."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import film_batch, film_lab
from tools.film_batch import is_complete_video, match_audio, prepare_jobs


class AudioDiscoveryTests(unittest.TestCase):
    def test_manifest_slug_preferred_over_numeric_filename(self):
        chapter = {"id": "01", "audio": "audio/01-the-long-table.mp3"}
        files = [Path("/tmp/01.mp3"), Path("/tmp/01-the-long-table.mp3")]
        self.assertEqual(match_audio(chapter, files), Path("/tmp/01-the-long-table.mp3"))

    def test_chapter_one_does_not_match_chapter_ten(self):
        chapter = {"id": "01", "audio": "audio/01-the-long-table.mp3"}
        self.assertIsNone(match_audio(chapter, [Path("/tmp/10-the-separate-bedrooms.mp3")]))

    def test_ambiguous_narration_is_not_silently_chosen(self):
        chapter = {"id": "01", "audio": "audio/01-the-long-table.mp3"}
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            match_audio(chapter, [Path("/a/01.mp3"), Path("/b/01.mp3")])

    def test_nested_audio_folders_and_audio_extensions(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "Part One").mkdir()
            (root / "Part One" / "01-the-long-table.wav").write_bytes(b"wav")
            chapters = [
                {"id": "01", "audio": "audio/01-the-long-table.mp3"},
                {"id": "02", "audio": "audio/02-the-department-of-civic-weather.mp3"},
            ]
            jobs = prepare_jobs(chapters, root, root / "video")
            self.assertEqual(jobs[0].audio.name, "01-the-long-table.wav")
            self.assertIsNone(jobs[1].audio)

    def test_tiny_or_missing_outputs_do_not_count_as_completed(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clip.mp4"
            self.assertFalse(is_complete_video(path, 1.5))
            path.write_bytes(b"not a video")
            self.assertFalse(is_complete_video(path, 1.5))


class BatchRenderTests(unittest.TestCase):
    def test_batch_uses_one_process_and_renders_every_found_chapter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "audio"
            audio.mkdir()
            source1 = root / "book" / "part-01" / "01-example.md"
            source2 = root / "book" / "part-01" / "02-example.md"
            source1.parent.mkdir(parents=True)
            source1.write_text("# Chapter One — Example\n\nThe table was long.\n\n"
                               "***\n\nThe street was empty.\n", encoding="utf-8")
            source2.write_text("# Chapter Two — Example\n\nThe corridor was silent.\n\n"
                               "***\n\nThe door was locked.\n", encoding="utf-8")
            chapters = [
                {"id": "01", "title": "Example", "path": "book/part-01/01-example.md",
                 "audio": "audio/01-example.mp3"},
                {"id": "02", "title": "Example", "path": "book/part-01/02-example.md",
                 "audio": "audio/02-example.mp3"},
            ]
            for chapter in chapters:
                (audio / Path(chapter["audio"]).name).write_bytes(b"fake recording")
            calls = []

            def fake_render(plan, **kwargs):
                calls.append(plan["chapter"])
                target = kwargs["output"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"fake rendered film")

            args = [
                "--audio-dir", str(audio), "--output-dir", str(root / "video"),
                "--mode", "graphic", "--shots", "4",
                "--chapters", "01", "02",
            ]
            with patch.object(film_batch, "ROOT", root), \
                 patch.object(film_batch, "get_chapters", return_value=chapters), \
                 patch.object(film_batch, "ffprobe_duration", return_value=8.0), \
                 patch.object(film_batch, "render_video", side_effect=fake_render), \
                 contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(film_batch.main(args), 0)
            self.assertEqual(calls, ["01", "02"])
            self.assertTrue((root / "storyboards" / "01.json").is_file())
            self.assertTrue((root / "storyboards" / "02.json").is_file())
            first = json.loads((root / "storyboards" / "01.json").read_text(encoding="utf-8"))
            self.assertEqual(first["audio_seconds"], 8.0)

    def test_strict_audio_fails_before_loading_gpu(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chapters = [{"id": "01", "title": "Example",
                         "audio": "audio/01-example.mp3", "path": "book/a.md"}]
            with patch.object(film_batch, "get_chapters", return_value=chapters), \
                 contextlib.redirect_stdout(io.StringIO()), \
                 contextlib.redirect_stderr(io.StringIO()):
                result = film_batch.main(["--audio-dir", str(root),
                                          "--mode", "graphic", "--strict-audio"])
            self.assertEqual(result, 1)

    def test_model_loader_is_cached_for_many_chapters(self):
        self.assertTrue(hasattr(film_lab.load_local_pipeline, "cache_info"))


if __name__ == "__main__":
    unittest.main()
