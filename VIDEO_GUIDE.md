# Story2 Film Lab — turn the audiobook into a faceless film

The Film Lab is a local narration-to-video pipeline. It reads the complete
Story2 manuscript and the **actual narration MP3/WAV**, plans visual beats,
renders still images with slow cinematic camera movement, and writes a video
with the original narration intact. No hosted account or server is required.

## Why faces aren't necessary

Long-form image generation struggles with recognizable, consistent faces.
The story benefits from a deliberately faceless film language:

- **Characters:** rear views, silhouettes, hands, coats hanging on hooks,
  a figure through a window, never a front-facing identity-dependent closeup.
- **Recurring places:** Rowan Way at dusk, railway tracks, kitchens, the
  Merrow library, Eastmere's blue gate, the gulf, northern government offices.
- **Recurring objects:** six supper tables, one damaged white table, the
  fishing rod, Ivo's model bridge, a signed document, Irena's medal.
- **Continuity:** slate-blue shadows, amber windows, paper texture, rain,
  restrained 35 mm color. Reuse a reference image for important places.

The automatic prompts use these rules. Local image models can still produce
inconsistent or visible faces, so inspect frames before publishing.

## Run the desktop GUI on Windows

Install FFmpeg and FFprobe on your PATH. From the Story2 folder:

    py -3.13 -m pip install -r requirements-video.txt
    py -3.13 tools\film_lab_gui.py

Or double-click launch_film_lab.bat after installing Pillow.

1. Select a chapter, including 25 for the epilogue.
2. Select the narration MP3/WAV (the original file is never modified).
3. Choose Graphic (no AI) first, or point the optional image-model setting
   at a Diffusers model you have already downloaded locally.
4. Click Make storyboard. The tool creates storyboards/01.json.
5. Optionally open that JSON to refine individual visuals and timings.
6. Preview video (by default 40 seconds).
7. Render full chapter. The output appears under video/.

Narration must exist on your PC for rendering. If you used Story2's Piper
pipeline, it normally lives under audio/. If you recorded the audiobook
elsewhere, select its actual file. No narration was uploaded to this repo.

## Command line

Storyboard WITHOUT a model, audio, or FFmpeg:

    py -3.13 tools\film_lab.py --chapter 01 --plan-only

If there is no audio, cut timing is estimated from word counts.

Preview the first 40 seconds of a chapter with actual recorded narration:

    py -3.13 tools\film_lab.py --chapter 01 --audio "D:\Narration\chapter01.mp3" --mode graphic --preview-seconds 40

Render the entire chapter using built-in illustrated graphics:

    py -3.13 tools\film_lab.py --chapter 01 --audio "D:\Narration\chapter01.mp3" --mode graphic

Create a rougher, faster storyboard (replaces the current JSON plan):

    py -3.13 tools\film_lab.py --chapter 01 --shots 14 --regenerate-plan --plan-only

For the epilogue use --chapter 25.

The --regenerate-plan flag overwrites hand-edited JSON; do not use it once
you are happy with the prompts or manual timing edits.

## Optional image model: local Diffusers

The default graphic mode uses **only Pillow**, and runs on CPU. To use a
local model, also install compatible local PyTorch, Diffusers, Transformers,
Accelerate, and safetensors in the SAME Python environment:

    py -3.13 -m pip install diffusers transformers accelerate safetensors

Use an existing local Diffusers model folder, with CUDA when supported
by your PyTorch version:

    py -3.13 tools\film_lab.py --chapter 01 --audio "D:\Narration\chapter01.mp3" --mode diffusers --model "D:\models\my-diffusers-model" --device cuda --preview-seconds 40

RTX 3060 12 GB is a reasonable starting point at the default 896 × 504
resolution with a relatively small image model. Larger models, especially
SDXL-sized ones, may require memory optimizations and longer render times.
The code refuses a missing local model path and uses local-files-only loading.
Single-file .safetensors checkpoints may need cached configuration; a full
Diffusers model directory is the most predictable option.

Image-model mode still generates **stills**, not moving faces or lip sync.
Review every shot before distributing the film.

## Use images generated elsewhere

Create the plan, then open storyboards/01.json and edit shot image fields to
refer to JPG/PNG files you generated with any tool.

You can even point ten shots to the same location image to establish continuity.
To stitch those images with your original narration:

    py -3.13 tools\film_lab.py --chapter 01 --audio "D:\Narration\chapter01.mp3" --mode existing

Each editable shot in the JSON includes:
- start and end positions (seconds, initially approximate)
- a short excerpt of the source manuscript for visual context
- a motif (table, archive, rail, hospital, flag, and so on)
- a cinematic prompt and negative prompt
- a fixed seed for repeatable generation
- the image filename (relative to repository root or an absolute path)

**Timings are proportional to spoken word counts.** They are NOT exact
speech-aligned times; the recording itself is only used to establish the
total duration. Edit the start/end seconds in the JSON to fix important
scene boundaries. If the audio length later differs from the plan, the
script automatically rescales the timings.

## How it renders

Every planned image is cached and reused unless you specify
--overwrite-frames. FFmpeg renders one moving still per shot, applies
subtle slow zoom, joins the clips, and muxes your narration as AAC with
an H.264 video stream. This keeps long audiobook chapters manageable.

The default target is one shot about every 32 seconds of narration.
An image model may have to generate dozens of images for a 20-minute
chapter. For your first experiment, choose --shots 12 or 14 and render a
40-second preview before attempting the entire chapter.

The video/ folder and generated storyboards/frames are ignored by Git.
Editable storyboard JSON can be committed when you are happy with it.
Do not add a many-gigabyte video to your GitHub Pages repository by accident.

## What it does not do yet

It does not synthesize audio, invent acting performances, track faces, lip
sync characters, or give sentence-perfect automatic time alignment. It is
an **illustrated motion-storyboard video maker** backed by the real book
and real narration. A subsequent local forced-alignment pass could produce
more exact changes of image on spoken paragraphs.

Test with:

    py -3.13 -m unittest discover -s tests -v

A small automatic end-to-end smoke test builds a video from two seconds of
synthetic test audio when Pillow and FFmpeg are available.
