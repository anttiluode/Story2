"""Tests for Story2 manuscript and offline audiobook preparation.

Run: python -m unittest discover -s tests -v
No voice download or audio dependencies required.
"""

import json
import tempfile
import unittest
import wave
from pathlib import Path

from tools.render_audio import (
    MANIFEST,
    ROOT,
    SpeechChunk,
    chunk_paragraphs,
    get_chapters,
    manuscript_paragraphs,
    merge_wavs,
)


class ManuscriptTests(unittest.TestCase):
    def test_published_manifest_points_to_existing_files(self):
        chapters = get_chapters()
        self.assertEqual([c["id"] for c in chapters], ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17"])
        self.assertTrue(all((ROOT / chapter["path"]).is_file() for chapter in chapters))
        self.assertTrue(all(chapter["audio"].endswith(".mp3") for chapter in chapters))

    def test_planned_parts_are_not_published(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["parts"]), 4)
        self.assertEqual(len(manifest["plannedParts"]), 2)

    def test_chapter_paths_remain_in_their_declared_part(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        for part in manifest["parts"]:
            for chapter in part["chapters"]:
                self.assertTrue(
                    chapter["path"].startswith("book/" + part["id"] + "/"),
                    (part["id"], chapter["path"]),
                )
                raw = (ROOT / chapter["path"]).read_text(encoding="utf-8")
                self.assertTrue(raw.startswith("# Chapter "), chapter["path"])
                self.assertIn(chapter["title"], raw.splitlines()[0])

    def test_markdown_removes_markup_but_not_narrative(self):
        source = "# Chapter One — A Name\n\n*Merrow, late summer.*\n\nThe **first** day was *warm*.\n\n***\n\nShe said, \"Yes.\""
        self.assertEqual(
            manuscript_paragraphs(source),
            ["Chapter One — A Name", "Merrow, late summer.",
             "The first day was warm.", 'She said, "Yes."'],
        )

    def test_chunking_preserves_every_word_and_limits_length(self):
        source = [
            "The first sentence is short. The second sentence is also quite short. " * 20,
            "A family met at the long table."
        ]
        segments = chunk_paragraphs(source, max_chars=150)
        self.assertTrue(segments)
        self.assertTrue(all(len(segment.text) <= 150 for segment in segments))
        self.assertEqual(" ".join(s.text for s in segments), " ".join(s.strip() for s in source))
        self.assertEqual(sum(chunk.end_paragraph for chunk in segments), 2)

    def test_all_published_prose_can_be_prepared_for_speech(self):
        for chapter in get_chapters():
            with self.subTest(chapter=chapter["id"]):
                raw = (ROOT / chapter["path"]).read_text(encoding="utf-8")
                paragraphs = manuscript_paragraphs(raw)
                chunks = chunk_paragraphs(paragraphs)
                self.assertGreater(len(paragraphs), 40)
                self.assertTrue(chunks)
                self.assertTrue(all(len(chunk.text) <= 650 for chunk in chunks))
                self.assertEqual(
                    " ".join(chunk.text for chunk in chunks),
                    " ".join(paragraphs),
                )

    def test_too_small_synthesis_budget_is_rejected(self):
        with self.assertRaises(ValueError):
            chunk_paragraphs(["A paragraph"], max_chars=99)


class WaveTests(unittest.TestCase):
    def test_merge_produces_valid_pcm_and_inserts_silence(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            paths = [root / "one.wav", root / "two.wav"]
            for path in paths:
                with wave.open(str(path), "wb") as output:
                    output.setnchannels(1)
                    output.setsampwidth(2)
                    output.setframerate(8000)
                    output.writeframes(b"\x00\x00" * 800)
            combined = root / "merged.wav"
            merge_wavs(
                paths,
                [SpeechChunk("Hello.", True), SpeechChunk("Goodbye.", True)],
                combined,
            )
            with wave.open(str(combined), "rb") as result:
                self.assertEqual(result.getnchannels(), 1)
                self.assertEqual(result.getsampwidth(), 2)
                self.assertEqual(result.getframerate(), 8000)
                self.assertGreater(result.getnframes(), 1600)


if __name__ == "__main__":
    unittest.main()
