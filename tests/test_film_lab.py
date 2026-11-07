"""Tests for the no-cloud Story2 Film Lab and its narrated-video timing."""

import importlib.util
import json
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from tools.film_lab import (
    ffprobe_duration, fit_timing, graphic_still, pick_motif, plan_chapter,
    render_video, source_scenes,
)
from tools.render_audio import ROOT, get_chapters


class FilmPlanTests(unittest.TestCase):
    def test_scene_separators_are_kept(self):
        scenes = source_scenes(
            "# Chapter One — Test\n\nFirst paragraph.\n\n***\n\n"
            "Second paragraph.\n\n***\n\nThird scene."
        )
        self.assertEqual(len(scenes), 3)
        self.assertIn("First paragraph.", scenes[0])

    def test_storyboards_from_actual_manuscript(self):
        chapters = {chapter["id"]: chapter for chapter in get_chapters()}
        for ident in ("01", "07", "17", "25"):
            with self.subTest(chapter=ident):
                chapter = chapters[ident]
                source = (ROOT / chapter["path"]).read_text(encoding="utf-8")
                plan = plan_chapter(chapter, source, duration=180.0, shots=12)
                self.assertEqual(plan["chapter"], ident)
                self.assertGreaterEqual(len(plan["shots"]), 3)
                self.assertAlmostEqual(plan["shots"][0]["start"], 0)
                self.assertAlmostEqual(plan["shots"][-1]["end"], 180.0)
                self.assertTrue(all(item["end"] > item["start"] for item in plan["shots"]))
                for before, after in zip(plan["shots"], plan["shots"][1:]):
                    self.assertAlmostEqual(before["end"], after["start"], places=3)
                self.assertTrue(all("no recognizable faces" in x["prompt"] for x in plan["shots"]))
                self.assertTrue(all(x["image"].endswith(".png") for x in plan["shots"]))
                self.assertEqual(len({x["seed"] for x in plan["shots"]}), len(plan["shots"]))

    def test_timing_can_be_rescaled_after_audio_is_recorded(self):
        chapter = {"id": "01", "title": "Test", "path": "book/test.md"}
        plan = plan_chapter(chapter, "# One\n\nThe first scene.\n\n***\n\nThe second.", None, shots=2)
        old = json.loads(json.dumps(plan))
        tuned = fit_timing(plan, 12.5)
        self.assertEqual(tuned["audio_seconds"], 12.5)
        self.assertEqual(tuned["shots"][-1]["end"], 12.5)
        self.assertTrue(tuned["shots"][0]["end"] > 0)
        self.assertEqual(old, plan)

    def test_visual_motifs_match_objects_not_people(self):
        self.assertEqual(pick_motif("A table with plates, bread, supper, and tea")[0], "table")
        self.assertEqual(pick_motif("A nurse in the hospital corridor")[0], "hospital")
        self.assertEqual(pick_motif("The award ceremony presented a medal")[0], "medal")


class NativeMediaToolRegressionTests(unittest.TestCase):
    def test_wav_ignores_broken_python_ffprobe_shim(self):
        """Windows Scripts/ffprobe.exe from panda3d-tools must not run."""
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            narration = Path(folder) / "01-the-long-table.wav"
            with wave.open(str(narration), "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(16000)
                output.writeframes(b"\0\0" * 32000)
            with patch("tools.film_lab.subprocess.run",
                       side_effect=AssertionError("Executed broken ffprobe shim")):
                self.assertAlmostEqual(ffprobe_duration(narration), 2.0)

    def test_ffmpeg_shim_is_rejected_and_bundled_native_binary_used(self):
        from unittest.mock import patch
        from tools.film_lab import resolve_ffmpeg
        import subprocess
        import imageio_ffmpeg

        def fake_run(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                return subprocess.CompletedProcess(
                    cmd, 1, "", "ModuleNotFoundError: No module named 'panda3d_tools'"
                )
            if cmd[0] == "/a-real-ffmpeg":
                return subprocess.CompletedProcess(cmd, 0, "ffmpeg version 7.0\n", "")
            raise AssertionError("Unexpected binary probe: " + repr(cmd))
        resolve_ffmpeg.cache_clear()
        try:
            with patch("tools.film_lab.subprocess.run", side_effect=fake_run), \
                 patch.object(imageio_ffmpeg, "get_ffmpeg_exe",
                              return_value="/a-real-ffmpeg"):
                self.assertEqual(resolve_ffmpeg(), "/a-real-ffmpeg")
        finally:
            resolve_ffmpeg.cache_clear()


@unittest.skipUnless(importlib.util.find_spec("PIL"), "Pillow not installed")
class FilmImageTests(unittest.TestCase):
    def test_graphic_frame_has_correct_dimensions(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            frame = Path(tmp) / "shot.png"
            graphic_still({"seed": 91, "index": 1, "motif": "table"},
                          frame, 320, 180, "The Long Table")
            with Image.open(frame) as im:
                self.assertEqual(im.size, (320, 180))
                self.assertEqual(im.mode, "RGB")


@unittest.skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe") and importlib.util.find_spec("PIL"),
    "Requires FFmpeg/ffprobe and Pillow",
)
class FilmEndToEndTests(unittest.TestCase):
    def test_two_second_narration_and_graphic_cut_produce_mp4(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "voice.wav"
            with wave.open(str(audio), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 32000)
            duration = ffprobe_duration(audio)
            chapter = {"id": "01", "title": "Test", "path": "book/test.md"}
            prose = ("# Chapter One — Test\n\nA long folding table.\n\n"
                     "The street was silent.\n\n***\n\n"
                     "The nurse stood beside the hospital doorway.")
            plan = plan_chapter(chapter, prose, duration=duration, shots=3)
            for shot in plan["shots"]:
                shot["image"] = str(root / ("shot-%03d.png" % shot["index"]))
            dest = root / "movie.mp4"
            render_video(plan, audio=audio, output=dest, mode="graphic",
                         model=None, device="cpu", width=320, height=180, fps=12,
                         steps=2, guidance=4, ffmpeg="ffmpeg",
                         preview_seconds=0, overwrite_frames=False)
            self.assertTrue(dest.exists())
            self.assertGreater(dest.stat().st_size, 1000)
            self.assertAlmostEqual(ffprobe_duration(dest), duration, delta=.25)


if __name__ == "__main__":
    unittest.main()
