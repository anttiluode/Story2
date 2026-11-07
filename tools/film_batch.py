#!/usr/bin/env python3
"""Render EVERY narrated Story2 chapter with one reusable local image model.

Plans all 25 chapters; discovers narration; creates/caches frames; resumes from
finished chapter MP4 files; optionally concatenates the full-length novel.
The image model is loaded ONCE per Python process by film_lab.load_local_pipeline.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

try:
    from tools.film_lab import (
        ROOT, ffprobe_duration, fit_timing, plan_chapter, render_video,
        run_checked,
    )
    from tools.render_audio import get_chapters
    from tools.model_setup import DEFAULT_DIR, is_installed
except ModuleNotFoundError:
    from film_lab import ROOT, ffprobe_duration, fit_timing, plan_chapter, render_video, run_checked
    from render_audio import get_chapters
    from model_setup import DEFAULT_DIR, is_installed


AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


@dataclass
class RenderJob:
    chapter: dict
    audio: Path | None
    destination: Path


def scan_audio(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise NotADirectoryError(f"Audio location is not a directory: {directory}")
    return sorted(path.resolve() for path in directory.rglob("*")
                  if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS)


def match_audio(chapter: dict, files: list[Path]) -> Path | None:
    """Prefer exact Story2 slugs, then chapter numbers; detect ambiguity."""
    ident = chapter["id"]
    stem = Path(chapter["audio"]).stem.casefold()
    priorities = []
    for path in files:
        name = path.stem.casefold()
        if name == stem:
            score = 0
        elif name.startswith(stem + "-") or name.startswith(stem + "_"):
            score = 1
        elif name == ident or name == f"chapter-{ident}" or name == f"chapter{ident}":
            score = 2
        elif re.match(r"^" + re.escape(ident) + r"(?=[\s._-])", name):
            score = 3
        elif re.match(r"^chapter[\s._-]*0?" + re.escape(str(int(ident))) + r"(?=[\s._-]|$)", name):
            score = 4
        else:
            continue
        # Prefer MP3 to WAV within the same matching group.
        ext_priority = 0 if path.suffix.lower() == ".mp3" else 1
        priorities.append((score, ext_priority, path))
    if not priorities:
        return None
    priorities.sort(key=lambda x: (x[0], x[1], str(x[2])))
    best = priorities[0][:2]
    equal = [p for s, e, p in priorities if (s, e) == best]
    if len(equal) > 1:
        raise ValueError(
            f"Ambiguous chapter {ident} narration. Rename one file to "
            f"{Path(chapter['audio']).name}: " + ", ".join(str(p) for p in equal[:6])
        )
    return equal[0]


def prepare_jobs(chapters: list[dict], audio_directory: Path, video_directory: Path) -> list[RenderJob]:
    files = scan_audio(audio_directory)
    jobs = []
    for chapter in chapters:
        stem = Path(chapter["audio"]).stem
        jobs.append(RenderJob(chapter, match_audio(chapter, files),
                              video_directory / f"{stem}.mp4"))
    return jobs


def is_complete_video(dest: Path, expected_seconds: float, ffprobe: str = "ffprobe") -> bool:
    if not dest.is_file() or dest.stat().st_size < 4096:
        return False
    try:
        actual = ffprobe_duration(dest, ffprobe)
    except (ValueError, RuntimeError, OSError):
        return False
    return abs(actual - expected_seconds) < 1.2


def load_or_build_plan(chapter: dict, duration: float, shots: int,
                       seconds_per_shot: float, overwrite: bool) -> dict:
    import hashlib
    plan_path = ROOT / "storyboards" / f"{chapter['id']}.json"
    source = (ROOT / chapter["path"]).read_text(encoding="utf-8")
    fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if plan_path.is_file() and not overwrite:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if plan.get("format") != "story2-film-lab-v1" or plan.get("chapter") != chapter["id"]:
            raise ValueError(f"Invalid Story2 storyboard: {plan_path}")
        if plan.get("source_sha256") != fingerprint:
            raise ValueError(
                f"Chapter {chapter['id']} prose changed since storyboard creation. "
                "Review it and use --regenerate-plans to rebuild."
            )
        if plan.get("estimated_timing") or abs(float(plan.get("audio_seconds", 0)) - duration) > .03:
            plan = fit_timing(plan, duration)
    else:
        plan = plan_chapter(chapter, source, duration,
                            shots=shots, seconds_per_shot=seconds_per_shot)
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n",
                         encoding="utf-8")
    return plan


def join_chapters(jobs: list[RenderJob], destination: Path, ffmpeg: str,
                  ffprobe: str, overwrite: bool) -> bool:
    """Concatenate completed MP4s without reencoding, but NEVER label a partial novel as full."""
    import tempfile
    missing = [job for job in jobs if not job.audio or not
               is_complete_video(job.destination, ffprobe_duration(job.audio, ffprobe), ffprobe)]
    if missing:
        print("Skipping full-book MP4: not all 25 chapters are ready.", flush=True)
        print("Missing: " + ", ".join(job.chapter["id"] for job in missing), flush=True)
        return False
    if destination.is_file() and not overwrite:
        print("Full-book MP4 already exists (use --overwrite to replace):", destination)
        return True
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="story2-join-") as scratch:
        listing = Path(scratch) / "book.txt"
        # Use forward slashes even on Windows; escape single quote in FFmpeg path.
        content = "".join(
            "file '" + str(job.destination.resolve()).replace("\\", "/").replace("'", "'\\''") + "'\n"
            for job in jobs
        )
        listing.write_text(content, encoding="utf-8")
        output = Path(scratch) / "complete.mp4"
        run_checked([ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                     "-f", "concat", "-safe", "0", "-i", str(listing),
                     "-c", "copy", "-movflags", "+faststart", str(output)])
        output.replace(destination) if output.parent == destination.parent else __import__("shutil").move(str(output), str(destination))
    print("FULL BOOK FILM:", destination, flush=True)
    return True


def render_all(args: argparse.Namespace) -> int:
    chapters = get_chapters()
    if args.chapters:
        requested = set(args.chapters)
        unknown = requested - {c["id"] for c in chapters}
        if unknown:
            raise ValueError("Unknown chapter ID(s): " + ", ".join(sorted(unknown)))
        chapters = [c for c in chapters if c["id"] in requested]
    jobs = prepare_jobs(chapters, args.audio_dir.expanduser().resolve(),
                        args.output_dir.expanduser().resolve())
    model_path = args.model.expanduser().resolve()
    print("Story2 / Whole Book Film Lab", flush=True)
    print(f"Chapters requested: {len(jobs)} | Visual mode: {args.mode}", flush=True)
    print("Audio folder:", args.audio_dir, flush=True)
    print("Film folder:", args.output_dir, flush=True)
    print("Model:", model_path, flush=True)
    if args.mode == "diffusers" and not (args.dry_run or args.plan_only):
        if not is_installed(model_path):
            raise FileNotFoundError(
                f"No local image model at {model_path}. "
                "Install it with: python tools/model_setup.py --download"
            )
    discovered = sum(bool(job.audio) for job in jobs)
    print(f"Found narration for {discovered}/{len(jobs)} chapters", flush=True)
    missing = [job.chapter["id"] for job in jobs if not job.audio]
    if missing:
        print("Missing narration: " + ", ".join(missing), flush=True)
    if args.strict_audio and missing and not args.plan_only:
        raise RuntimeError("Not all narration files were found; refusing an incomplete job.")
    if args.dry_run:
        for job in jobs:
            print(f"{job.chapter['id']} {job.chapter['title']}  "
                  f"{job.audio if job.audio else '[MISSING AUDIO]'}")
        return 0
    succeeded = []
    skipped = []
    failed = []
    started = time.monotonic()
    for i, job in enumerate(jobs, start=1):
        chapter = job.chapter
        print(f"\n{'='*60}\n[{i}/{len(jobs)}] {chapter['id']} — {chapter['title']}", flush=True)
        try:
            if not job.audio and not args.plan_only:
                print("Skipping: no matching narration audio.", flush=True)
                skipped.append(chapter["id"])
                continue
            duration = ffprobe_duration(job.audio, args.ffprobe) if job.audio else None
            if duration is None:
                # Planning without recorded narration is allowed.
                raw = (ROOT / chapter["path"]).read_text(encoding="utf-8")
                plan = plan_chapter(chapter, raw, None, args.shots, args.seconds_per_shot)
                plan_path = ROOT / "storyboards" / f"{chapter['id']}.json"
                plan_path.parent.mkdir(parents=True, exist_ok=True)
                if args.regenerate_plans or not plan_path.exists():
                    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+"\n",
                                         encoding="utf-8")
                else:
                    plan = json.loads(plan_path.read_text(encoding="utf-8"))
            else:
                plan = load_or_build_plan(
                    chapter, duration, args.shots, args.seconds_per_shot,
                    args.regenerate_plans,
                )
            print(f"Storyboard: {len(plan['shots'])} images, "
                  f"{float(plan['audio_seconds'])/60:.1f} min", flush=True)
            if args.plan_only:
                succeeded.append(chapter["id"])
                continue
            if is_complete_video(job.destination, duration, args.ffprobe) and not args.overwrite:
                print("Already rendered: skipping complete MP4.", flush=True)
                succeeded.append(chapter["id"])
                continue
            render_video(
                plan, audio=job.audio, output=job.destination,
                mode=args.mode, model=str(model_path), device=args.device,
                width=args.width, height=args.height, fps=args.fps,
                steps=args.steps, guidance=args.guidance, ffmpeg=args.ffmpeg,
                preview_seconds=args.preview_seconds,
                overwrite_frames=args.overwrite_frames,
            )
            succeeded.append(chapter["id"])
        except Exception as error:
            failed.append((chapter["id"], str(error)))
            print(f"ERROR in chapter {chapter['id']}: {error}", file=sys.stderr, flush=True)
            if not args.continue_on_error:
                break
    total = time.monotonic() - started
    print(f"\nDone after {total/60:.1f} min. "
          f"Completed/skipped existing: {len(succeeded)}; "
          f"no audio: {len(skipped)}; errors: {len(failed)}.", flush=True)
    for ident, error in failed:
        print(f"  ERROR {ident}: {error}", flush=True)
    if args.join and not args.plan_only and not args.preview_seconds and not failed and len(jobs) == 25:
        join_chapters(jobs, args.output_dir / "The-Distance-Between-Houses-Full-Film.mp4",
                      args.ffmpeg, args.ffprobe, args.overwrite)
    elif args.join and len(jobs) != 25:
        print("Full-film join requires all 25 book entries (without --chapters).", flush=True)
    if not args.plan_only and discovered == 0:
        print("No narration found: no films could be rendered.", file=sys.stderr)
        return 1
    return 1 if failed or (args.strict_audio and missing) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
             formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--audio-dir", type=Path, default=ROOT/"audio",
                        help="Directory containing 01-the-long-table.mp3 etc.; searched recursively")
    parser.add_argument("--output-dir", type=Path, default=ROOT/"video")
    parser.add_argument("--model", type=Path, default=DEFAULT_DIR,
                        help="Local DreamShaper Diffusers directory")
    parser.add_argument("--mode", choices=("diffusers","graphic","existing"), default="diffusers")
    parser.add_argument("--device", choices=("cuda","cpu"), default="cuda")
    parser.add_argument("--width", type=int, default=896)
    parser.add_argument("--height", type=int, default=504)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--steps", type=int, default=22)
    parser.add_argument("--guidance", type=float, default=6.5)
    parser.add_argument("--shots", type=int, default=0,
                        help="Number of shots per chapter; 0 uses duration/seconds-per-shot")
    parser.add_argument("--seconds-per-shot", type=float, default=60)
    parser.add_argument("--preview-seconds", type=float, default=0)
    parser.add_argument("--chapters", nargs="+", metavar="ID", help="Subset, e.g. 01 02 03")
    parser.add_argument("--plan-only", action="store_true",
                        help="Build storyboard JSON for ALL chapters without rendering video")
    parser.add_argument("--dry-run", action="store_true", help="List all narration files; generate nothing")
    parser.add_argument("--join", action="store_true", help="Concatenate the 25 chapter MP4s into one full film")
    parser.add_argument("--strict-audio", action="store_true",
                        help="Fail if any selected chapter lacks a narration file")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--overwrite", action="store_true", help="Rebuild completed videos")
    parser.add_argument("--regenerate-plans", action="store_true", help="Overwrite edited storyboard JSON")
    parser.add_argument("--overwrite-frames", action="store_true", help="Regenerate existing stills")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--ffprobe", default="ffprobe")
    args = parser.parse_args(argv)
    try:
        return render_all(args)
    except (RuntimeError, ValueError, FileNotFoundError, OSError) as error:
        print("Film batch error:", error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
