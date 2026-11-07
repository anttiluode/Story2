#!/usr/bin/env python3
"""Install a 3060-friendly Story2 image model for offline Film Lab generation.

The model weights are downloaded ONLY when explicitly invoked with --download.
Model: Lykon/dreamshaper-8, CreativeML OpenRAIL-M on Hugging Face.
An FP16 pipeline is saved locally; renders afterward use local_files_only=True.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ID = "Lykon/dreamshaper-8"
DEFAULT_DIR = ROOT / "models" / "dreamshaper-8"
MODEL_URL = "https://huggingface.co/Lykon/dreamshaper-8"


def is_installed(directory: Path) -> bool:
    return (directory / "model_index.json").is_file() and (directory / "unet" / "config.json").is_file()


def install_model(directory: Path = DEFAULT_DIR, download: bool = False, model_id: str = DEFAULT_ID) -> Path:
    directory = Path(directory).expanduser().resolve()
    if is_installed(directory):
        print("AI model already installed:", directory, flush=True)
        return directory
    if not download:
        raise FileNotFoundError(
            f"No local AI image model at {directory}.\n"
            "Run: python tools/model_setup.py --download\n"
            f"Model card and license: {MODEL_URL}"
        )
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError as error:
        raise RuntimeError(
            "Install a CUDA-capable PyTorch for your GPU, and then: "
            "python -m pip install -r requirements-video-ai.txt"
        ) from error
    print("Model:", model_id, flush=True)
    print("License: CreativeML OpenRAIL-M (review before distributing generated art)", flush=True)
    print("Downloading FP16 weights to the Hugging Face cache. Internet required this ONE time.", flush=True)
    print("Model weights are NOT committed to Git or embedded in the application.", flush=True)
    try:
        pipe = AutoPipelineForText2Image.from_pretrained(
            model_id, torch_dtype=torch.float16, variant="fp16",
            use_safetensors=True,
        )
        directory.mkdir(parents=True, exist_ok=True)
        pipe.save_pretrained(str(directory), safe_serialization=True)
        del pipe
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception as error:
        raise RuntimeError(
            f"Model download/save failed: {error}. "
            "Check network, disk space, package compatibility, and available RAM."
        ) from error
    if not is_installed(directory):
        raise RuntimeError(f"Download did not result in a valid Diffusers model at {directory}")
    print("Ready for OFFLINE generation:", directory, flush=True)
    return directory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true",
                        help="Download and save DreamShaper 8 once (requires internet)")
    parser.add_argument("--path", type=Path, default=DEFAULT_DIR)
    parser.add_argument("--model-id", default=DEFAULT_ID,
                        help="Advanced: select another Diffusers-compatible FP16 model")
    args = parser.parse_args(argv)
    try:
        install_model(args.path, download=args.download, model_id=args.model_id)
    except (RuntimeError, ValueError, FileNotFoundError, OSError) as error:
        print("Model setup error:", error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
