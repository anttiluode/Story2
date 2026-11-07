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

## New: RTX 3060 / DreamShaper 8 / entire book

The default AI model is **DreamShaper 8**, a Stable Diffusion 1.5 fine-tune
with a CreativeML OpenRAIL-M license. The default FP16 image pipeline
is designed for a 12 GB RTX 3060: **896 × 504**, 22 inference steps,
one image at a time. Models are fetched only when you explicitly run
setup; subsequent movie generation is offline. Real speed and VRAM use
depend on the installed CUDA build, the model version, and other GPU
applications. Close other GPU-heavy tools for a long job.

**Windows installer (run once):** double-click install_film_lab.bat
or execute:

    powershell -ExecutionPolicy Bypass -File .\setup_film_lab_windows.ps1

It creates a separate .film-venv with CUDA PyTorch, Pillow,
Diffusers/Transformers and an FP16 DreamShaper 8 model in
models/dreamshaper-8/. This downloads several gigabytes. The isolated
environment avoids breaking another Torch installation. If the NVIDIA
driver or CUDA wheel is incompatible, use the PyTorch Windows selector
at https://pytorch.org/get-started/locally/ and the installer
-CudaIndex option. Check that torch.cuda.is_available() prints True.

Then double-click launch_film_lab.bat. Choose a folder containing your
**25 actual narrated files**, press Check all narration, then choose
RENDER ENTIRE NOVEL + JOIN FILM. The GUI requires all narration before
starting a full run, avoiding a falsely labeled incomplete final video.

Equivalent command line:

    .\.film-venv\Scripts\python.exe tools\film_batch.py --audio-dir audio --join --strict-audio

**Scan narration without rendering**:

    .\.film-venv\Scripts\python.exe tools\film_batch.py --audio-dir "D:\My Narrated Novel" --dry-run

The scanner searches that folder recursively for manifest filenames such
as 01-the-long-table.mp3, or chapter-numbered names such as 01.mp3,
02.wav, chapter-03.mp3 and so on. Ambiguous duplicate matches are an
error, not a silent selection. If your narration is stored elsewhere,
pass the whole directory containing those files.

**Prepare all 25 storyboards before rendering**:

    .\.film-venv\Scripts\python.exe tools\film_batch.py --plan-only

**Preview only the first chapter with the AI model**:

    .\.film-venv\Scripts\python.exe tools\film_batch.py --chapters 01 --audio-dir audio --preview-seconds 40

**Lower the still count for faster first pass**:

    .\.film-venv\Scripts\python.exe tools\film_batch.py --audio-dir audio --shots 12 --join --strict-audio

Choose shots BEFORE building the storyboard or use --regenerate-plans
to replace old auto-generated plans. The default is about one
new image every 60 seconds. A full 7+ hour audiobook could require
hundreds of images. A 3060 can perform this without cloud GPU rental,
but it is not a quick one-minute job.

**Recovery and files**: render each chapter first as an MP4 under video/.
Finished images are cached under storyboards/frames-ai/ and finished
video clips under video/.clips/. If the program or PC stops unexpectedly,
run the exact same command again. Completed chapters and shots are reused.
The final joined MP4 appears at:

    video\The-Distance-Between-Houses-Full-Film.mp4

You can create it after chapter rendering by rerunning with --join.
The join refuses missing chapters. Large full-length video output can
require several gigabytes of additional storage.

The model is loaded once per batch, not 25 separate times. A text-to-image
model creates painted stills, not a character-consistent talking-person
video. The face-free prompts are intentional and can be edited in JSON.

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
