#!/usr/bin/env python3
"""Render Story2's published Markdown chapters to local Piper audio.

Requires Python 3.10+ and piper-tts for actual synthesis.
MP3 output additionally requires FFmpeg.
Dry runs and unit tests require only the standard library.

This script does not connect to any hosted text-to-speech service.
"""

from __future__ import annotations

import argparse
from functools import lru_cache
import json
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "book" / "manifest.json"


@dataclass(frozen=True)
class SpeechChunk:
    text: str
    end_paragraph: bool


def get_chapters(manifest_path: Path = MANIFEST) -> list[dict]:
    """Load and validate all *published* chapters, not outlined chapters."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chapters: list[dict] = []
    seen: set[str] = set()
    for part in manifest.get("parts", []):
        for chapter in part.get("chapters", []):
            ident = str(chapter.get("id", ""))
            if not re.fullmatch(r"\d{2}", ident) or ident in seen:
                raise ValueError(f"Invalid or duplicate chapter id: {ident!r}")
            seen.add(ident)
            relative = Path(chapter["path"])
            if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".md":
                raise ValueError(f"Unsafe chapter path: {relative}")
            output = Path(chapter["audio"])
            if output.is_absolute() or ".." in output.parts or output.parts[0] != "audio":
                raise ValueError(f"Unsafe audio path: {output}")
            if not (ROOT / relative).is_file():
                raise FileNotFoundError(f"Published chapter is missing: {relative}")
            chapters.append(chapter)
    return chapters


def manuscript_paragraphs(markdown: str) -> list[str]:
    """Convert this project's simple narrative Markdown to spoken paragraphs.

    Preserve the actual prose, including dialogue and chapter titles, while
    removing only Markdown formatting. Never summarize or generate new text.
    """
    text = markdown.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block or block.startswith("<!--"):
            continue
        if re.fullmatch(r"(\*\s*){3,}|(-\s*){3,}", block):
            continue
        if block.startswith("#"):
            block = re.sub(r"^#{1,6}\s+", "", block)
        if block.startswith("> "):
            block = re.sub(r"^>\s?", "", block, flags=re.MULTILINE)
        block = re.sub(r"\*\*(.*?)\*\*", r"\1", block, flags=re.DOTALL)
        block = re.sub(r"\*(.*?)\*", r"\1", block, flags=re.DOTALL)
        block = re.sub(r"(?<!\w)_(.*?)_(?!\w)", r"\1", block)
        block = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", block)
        block = re.sub(r"\s*\n\s*", " ", block)
        block = re.sub(r"\s+", " ", block).strip()
        if block:
            paragraphs.append(block)
    return paragraphs


def _break_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """Fallback when a sentence itself exceeds the synthesis chunk budget."""
    words = sentence.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            raise ValueError(f"Single word exceeds --max-chars: {word[:60]!r}")
        proposed = f"{current} {word}".strip()
        if len(proposed) > max_chars and current:
            pieces.append(current)
            current = word
        else:
            current = proposed
    if current:
        pieces.append(current)
    return pieces


def chunk_paragraphs(paragraphs: list[str], max_chars: int = 650) -> list[SpeechChunk]:
    """Chunk without omitting a single word; retain paragraph breaks for pauses."""
    if max_chars < 100:
        raise ValueError("--max-chars must be 100 or larger")
    result: list[SpeechChunk] = []
    for paragraph in paragraphs:
        sentences = re.split(r"(?<=[.!?])\s+", paragraph.strip())
        pieces: list[str] = []
        current = ""
        for sentence in sentences:
            if not sentence:
                continue
            for fragment in _break_long_sentence(sentence, max_chars):
                candidate = f"{current} {fragment}".strip()
                if len(candidate) > max_chars and current:
                    pieces.append(current)
                    current = fragment
                else:
                    current = candidate
        if current:
            pieces.append(current)
        for index, piece in enumerate(pieces):
            result.append(SpeechChunk(piece, index == len(pieces) - 1))
    return result


@lru_cache(maxsize=3)
def load_piper_voice(model: str, use_cuda: bool):
    """Load a Piper model once and reuse it for every passage and chapter."""
    try:
        from piper import PiperVoice
    except ImportError as error:
        raise RuntimeError(
            "Piper is not installed. Run 'python -m pip install -r requirements-audio.txt'."
        ) from error

    filename = Path(model)
    if not filename.is_file():
        named = model if model.endswith(".onnx") else model + ".onnx"
        for candidate in (ROOT / named, Path.cwd() / named):
            if candidate.is_file():
                filename = candidate
                break
    if not filename.is_file():
        raise FileNotFoundError(
            f"Voice model {model!r} not found. Download it with "
            "'python -m piper.download_voices en_US-lessac-medium' from "
            "the Story2 repository directory, or pass --voice path/to/voice.onnx."
        )
    try:
        return PiperVoice.load(str(filename), use_cuda=use_cuda)
    except Exception as error:
        raise RuntimeError(f"Could not load Piper voice {filename}: {error}") from error


def piper_wav(text: str, output_path: Path, model: str, use_cuda: bool) -> None:
    """Write local speech synthesis straight to a WAV using Piper's Python API."""
    voice = load_piper_voice(model, use_cuda)
    try:
        with wave.open(str(output_path), "wb") as output:
            voice.synthesize_wav(text, output)
    except Exception as error:
        raise RuntimeError(f"Piper synthesis failed for {output_path}: {error}") from error
    if not output_path.exists() or output_path.stat().st_size < 44:
        raise RuntimeError(f"Piper did not create a valid WAV: {output_path}")


def merge_wavs(paths: list[Path], chunks: list[SpeechChunk], destination: Path) -> None:
    """Losslessly concatenate compatible PCM WAV chunks with real pauses."""
    if not paths or len(paths) != len(chunks):
        raise ValueError("Audio paths and speech chunks must have the same nonzero size")
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
        signature = (first.getnchannels(), first.getsampwidth(), first.getframerate(), first.getcomptype())
    if signature[3] != "NONE":
        raise RuntimeError("Piper generated a compressed WAV; expected PCM.")
    with wave.open(str(destination), "wb") as writer:
        writer.setnchannels(signature[0])
        writer.setsampwidth(signature[1])
        writer.setframerate(signature[2])
        writer.setcomptype("NONE", "not compressed")
        for path, chunk in zip(paths, chunks):
            with wave.open(str(path), "rb") as reader:
                current = (reader.getnchannels(), reader.getsampwidth(), reader.getframerate(), reader.getcomptype())
                if current != signature:
                    raise RuntimeError(f"Incompatible WAV format for {path.name}: {current}")
                while True:
                    frames = reader.readframes(65536)
                    if not frames:
                        break
                    writer.writeframesraw(frames)
            seconds = 0.47 if chunk.end_paragraph else 0.10
            samples = round(signature[2] * seconds)
            writer.writeframesraw(b"\x00" * samples * signature[0] * signature[1])


def to_mp3(wav_path: Path, destination: Path, ffmpeg: str) -> None:
    """Convert PCM WAV to browser-friendly MP3; FFmpeg must be installed locally."""
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
             "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "128k", str(destination)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            "FFmpeg not found. Install FFmpeg for --format mp3, or use --format wav."
        ) from error
    if result.returncode != 0 or not destination.exists():
        detail = result.stderr.decode("utf-8", errors="replace")[-1600:]
        raise RuntimeError(f"FFmpeg conversion failed: {detail}")


def render_chapter(
    chapter: dict,
    *,
    voice: str,
    output_format: str,
    max_chars: int,
    use_cuda: bool,
    ffmpeg_executable: str,
    overwrite: bool,
    dry_run: bool,
) -> None:
    source = ROOT / chapter["path"]
    paragraphs = manuscript_paragraphs(source.read_text(encoding="utf-8"))
    chunks = chunk_paragraphs(paragraphs, max_chars)
    if not chunks:
        raise ValueError(f"Chapter {chapter['id']} contains no spoken text")
    # The manifest uses MP3 as the canonical browser URL.
    destination = ROOT / Path(chapter["audio"]).with_suffix("." + output_format)
    print(
        f"Chapter {chapter['id']} — {chapter['title']}: "
        f"{len(paragraphs)} paragraphs, {len(chunks)} chunks, "
        f"{sum(len(part.text) for part in chunks)} spoken characters -> "
        f"{destination.relative_to(ROOT)}",
        flush=True,
    )
    if dry_run:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not overwrite:
        print("  Existing file: skipping (use --overwrite to replace).", flush=True)
        return
    with tempfile.TemporaryDirectory(prefix="story2-audio-") as scratch:
        work = Path(scratch)
        pieces: list[Path] = []
        for index, chunk in enumerate(chunks):
            wave_path = work / f"chunk-{index:04d}.wav"
            piper_wav(chunk.text, wave_path, voice, use_cuda)
            pieces.append(wave_path)
            if index == 0 or (index + 1) % 10 == 0 or index == len(chunks) - 1:
                print(f"  Synthesized {index + 1}/{len(chunks)} chunks", flush=True)
        merged = work / "merged.wav"
        merge_wavs(pieces, chunks, merged)
        if output_format == "wav":
            shutil.copyfile(merged, destination)
        else:
            encoded = work / "merged.mp3"
            to_mp3(merged, encoded, ffmpeg_executable)
            shutil.copyfile(encoded, destination)
    print(f"  Audio written: {destination}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    selected = parser.add_mutually_exclusive_group()
    selected.add_argument("--all", action="store_true", help="Render all published chapters (default)")
    selected.add_argument("--chapter", action="append", metavar="ID", help="Render one chapter, e.g. 01 (can be repeated)")
    parser.add_argument("--voice", default="en_US-lessac-medium",
                        help="Piper voice name or a path to a local .onnx model")
    parser.add_argument("--format", choices=("mp3", "wav"), default="mp3")
    parser.add_argument("--max-chars", type=int, default=650)
    parser.add_argument("--cuda", action="store_true", help="Use onnxruntime-gpu when installed")
    parser.add_argument("--ffmpeg-executable", default="ffmpeg")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show exact chapter/chunk plan; no TTS install needed")
    args = parser.parse_args(argv)

    try:
        chapters = get_chapters()
        if args.chapter is not None:
            missing = set(args.chapter) - {chapter["id"] for chapter in chapters}
            if missing:
                parser.error("Unknown published chapter(s): " + ", ".join(sorted(missing)))
            requested = set(args.chapter)
            chapters = [chapter for chapter in chapters if chapter["id"] in requested]
        if args.max_chars < 100:
            parser.error("--max-chars must be at least 100")
        for chapter in chapters:
            render_chapter(
                chapter,
                voice=args.voice,
                output_format=args.format,
                max_chars=args.max_chars,
                use_cuda=args.cuda,
                ffmpeg_executable=args.ffmpeg_executable,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
            )
    except (RuntimeError, FileNotFoundError, ValueError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
