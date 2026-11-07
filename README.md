# The Distance Between Houses

**Story2 — a complete original political thriller, twenty-four chapters and an epilogue, with a local audiobook production pipeline.**

> They did not conquer the country by crossing its borders. They persuaded its people that their neighbors were the enemy.

The story takes place in the fictional Republic of **Liora** in the south, and the expansionist **Northern Directorate of Veyr**. A neighborhood lives its life while a distant state department studies how a society can lose the trust required to remain a country.

The ending is uncompromising: **Liora ceases to exist as a sovereign state. Whistleblowers are wrongfully institutionalized. The psychologists directing the northern project receive medals.** This is fiction, not an accusation about a named contemporary nation or a claim that all real polarization is engineered.

## What is actually written?

**The complete six-part novel is published: Chapters 01–24 plus the epilogue (*The Official Record*).** Part VI, *The Last Country*, follows the legal dissolution of Liora's sovereignty, awards the northern psychologists their medals, and returns to Rowan Way. The epilogue preserves the uncorrected record of Sela's wrongful confinement. [DESIGN.md](DESIGN.md) contains the cast, writing rules, completed chapter structure, and continuity notes. The prose is complete; locally generated audio files are not yet included.

| Chapter | Title |
| --- | --- |
| 01 | The Long Table |
| 02 | The Department of Civic Weather |
| 03 | A Very Ordinary Notification |
| 04 | The First Silence |
| 05 | The Shape of a Missing Person |
| **Part II** | **The Names We Give Our Enemies** |
| 06 | A Useful Kind of Certainty |
| 07 | The Second Table |
| 08 | A Man Worth Listening To |
| 09 | The Ledger |
| **Part III** | **The Feed Between Us** |
| 10 | The Separate Bedrooms |
| 11 | Children of the Borderless War |
| 12 | Official Results |
| 13 | The Last Shared Sunday |
| **Part IV** | **The Country That Hated Itself** |
| 14 | The Election Nobody Could Lose |
| 15 | A Republic of Small Rooms |
| 16 | The File That Crossed the Sea |
| 17 | Every Fact Has Two Histories |
| **Part V** | **The Diagnosis** |
| 18 | The Public Disorder Act |
| 19 | A Doctor's Signature |
| 20 | The House With No Street Number |
| 21 | The Calm Report |
| **Part VI** | **The Last Country** |
| 22 | The Map With Fewer Names |
| 23 | The Medals |
| 24 | The Empty Table |
| **Epilogue (audio ID 25)** | **The Official Record** |

The canonical chapter files live in `book/part-01/` through `book/part-06/`; the published table of contents lives in `book/manifest.json`. The epilogue is the last entry of Part VI with audio/reader ID `25` so the existing offline audio pipeline can render it.

## Publish the reading website (GitHub Pages)

The root of this repository contains a complete, responsive reading site: `index.html`, `style.css`, and `app.js`. No Node.js, build step, CDN, database, sign-in, or cloud API is needed.

1. Open **Settings → Pages** for this repository.
2. Under **Build and deployment**, select **Deploy from a branch**.
3. Select **main** and **/(root)**, then save.
4. Visit `https://anttiluode.github.io/Story2/` after GitHub Pages finishes deployment.

The site includes chapter navigation, direct chapter links, text size controls, dark/light reading mode, reading-position indicator, mobile layout, and optional HTML audio players that appear only when the corresponding audio exists.

To test locally, run `python -m http.server 8000` in the repository directory, then visit `http://localhost:8000/`. Opening `index.html` directly as `file://` may prevent the browser from loading chapter files.

## Create audiobook narration on your Windows PC

The Python tool renders chapters locally using **Piper TTS**, loading the voice model once per run rather than reloading it for each text chunk. It does **not** require LM Studio, a hosted model, or an account. The initial installation and voice download need an internet connection; inference after setup is local. Review a voice model's license before publishing recordings made with it.

PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
.\.venv\Scripts\python.exe -m piper.download_voices en_US-lessac-medium
.\.venv\Scripts\python.exe tools\render_audio.py --dry-run
.\.venv\Scripts\python.exe tools\render_audio.py --chapter 01 --format wav
```

For the **smaller, website-friendly MP3 files**, install FFmpeg, make sure `ffmpeg` is on your PATH, then run:

```powershell
.\.venv\Scripts\python.exe tools\render_audio.py --all --format mp3
```

The tool writes a separate chapter file under `audio/`, for example `audio/01-the-long-table.mp3`. Commit or upload those MP3 files if you want public listening on GitHub Pages. They are **not included yet** in the repository; the site will accurately say narration has not been published until a file appears.

Options:
- `--chapter 01` (repeat to select multiple chapters), `--chapter 25` for the epilogue, or `--all` to narrate the complete book.
- `--voice en_US-lessac-medium` or `--voice path\to\custom-voice.onnx`.
- `--format wav` requires only Piper; `--format mp3` also needs FFmpeg.
- `--dry-run` previews the chapters and text chunks without Piper or FFmpeg.
- `--overwrite` replaces an existing audio output; otherwise it is skipped.
- `--max-chars 650` changes chunk size if your voice needs shorter input.
- `--cuda` enables GPU synthesis when the compatible `onnxruntime-gpu` package and drivers are installed; CPU works by default.
- `--ffmpeg-executable` allows a custom FFmpeg binary location.

This is a **single-narrator audiobook pipeline**. Dramatic multi-voice production and music/sound design are future enhancements. No generated audio has been auditioned yet.

## NEW — make illustrated film videos from narration

**Story2 Film Lab** can turn any narrated chapter into a cinematic MP4.
It uses the original chapter's text to create an editable storyboard, renders
atmospheric faceless scenes, animates them with slow camera moves, then
stitches them to your actual recorded MP3/WAV with FFmpeg.

Faces are deliberately optional: the story can be told through Rowan Way,
the six tables, backlit figures, windows, the school drawbridge, railway
tracks, the clinic, the blue gate, official papers, and the northern medals.
This avoids having AI-generated characters change faces between shots.

It has three modes: **built-in illustrated graphics (no AI required)**,
**local image generation via Diffusers**, and **your own supplied images**.
No cloud API, hosted model, or local web server is required for graphic mode.
It does not pretend that unreleased narration files are present.

Windows quick start:

    py -3.13 -m pip install -r requirements-video.txt
    py -3.13 tools\film_lab_gui.py

Alternatively double-click launch_film_lab.bat after the Pillow installation.

Storyboard without audio:

    py -3.13 tools\film_lab.py --chapter 01 --plan-only

Preview using an actual recorded narration:

    py -3.13 tools\film_lab.py --chapter 01 --audio "D:\Narration\chapter01.mp3" --mode graphic --preview-seconds 40

The result is saved to video/. Shot prompts and timing can be edited in
storyboards/01.json. Video shot timing is estimated from prose length;
the image transitions are not automatically sentence-aligned yet.

**Full instructions: [VIDEO_GUIDE.md](VIDEO_GUIDE.md).**

## Validate

```powershell
py -3.13 -m unittest discover -s tests -v
py -3.13 tools\render_audio.py --dry-run
```

No external dependencies are necessary to run the tests or the dry run.

## Files

```text
index.html / style.css / app.js     Static reading site
DESIGN.md                           Plot, cast, themes, all six parts
book/manifest.json                  Published chapter index
book/part-01/*.md                   Written Part I manuscript
book/part-02/*.md                   Written Part II manuscript
book/part-03/*.md                   Written Part III manuscript
book/part-04/*.md                   Written Part IV manuscript
book/part-05/*.md                   Written Part V manuscript
book/part-06/*.md                   Written Part VI and epilogue
tools/render_audio.py               Offline text-to-speech pipeline
requirements-audio.txt              Piper dependency
tools/film_lab.py                  Audio + images -> cinematic MP4
tools/film_lab_gui.py              Desktop Tkinter GUI
launch_film_lab.bat                Windows Film Lab launcher
requirements-video.txt            Pillow for built-in graphic mode
VIDEO_GUIDE.md                    Film Lab usage, image models and faces
storyboards/README.md             Editable visual plans
tests/test_film_lab.py             Storyboard / frame / FFmpeg tests
tests/test_audio_pipeline.py        Parser / manifest / chunking tests
audio/README.md                     Where generated narrations go
```

**Writing and setting:** Original fictional work. The root MIT license covers the code; see `STORY_LICENSE.md` for the prose terms.
