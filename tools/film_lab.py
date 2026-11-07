#!/usr/bin/env python3
"""Story2 Film Lab: offline narration-to-video animatic maker.

Plan real chapter prose into editable visual beats, make faceless stills (graphic
illustration or optional local Diffusers), and stitch with narration via FFmpeg.
No hosted API, face recognition, tracking, or pretrained model is required for
the graphic mode. Python >=3.10; Pillow is required to draw graphic frames.
The cut points are estimates from word proportions, not forced alignment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    from tools.render_audio import ROOT, get_chapters, manuscript_paragraphs
except ModuleNotFoundError:
    from render_audio import ROOT, get_chapters, manuscript_paragraphs


STYLE = (
    "cinematic painterly frame from a restrained European political thriller, "
    "graphic novel realism, deep slate blue shadows, muted amber practical lights, "
    "weathered architecture, fine 35mm grain, strong compositions, mist and distance, "
    "no recognizable faces, back views or silhouettes only, no facial features, "
    "no writing, no typography, no logos, no contemporary politicians, 16:9 widescreen"
)
NEGATIVE = (
    "face close-up, frontal portrait, visible facial details, distinct identity, "
    "celebrity, photorealistic face, eyes, mouth, text, words, watermark, "
    "logo, political party branding, malformed hands, extra fingers, glossy 3d render"
)
MOTIFS = [
    ("archive", r"\b(file|documents?|ledger|record|archives?|paper|report|folder|evidence|photograph|newspaper|letter|citation)\b",
     "a folder of papers on a shadowed wooden desk, single shaft of cold window light, hands outside the frame"),
    ("table", r"\b(supper|dinner|plates?|table|chairs?|food|bread|tea|kitchen)\b",
     "a long folding supper table extending into an empty residential street at blue hour, chairs and warm windows, no faces"),
    ("rail", r"\b(train|rail|signal|depot|tracks?|station|junction|crossing)\b",
     "wet railway tracks and a lonely signal light receding into blue fog at twilight, industrial lines"),
    ("hospital", r"\b(clinic|hospital|patient|nurse|doctor|psychiatr|ward|medical)\b",
     "a quiet hospital corridor with a distant faceless figure seen from behind, fluorescent light, closed door"),
    ("detention", r"\b(detained|detention|confined|locked|secure|eastmere|gate|cell|custody)\b",
     "a long institutional corridor ending in a blue gate, a small coat hanging behind glass, no faces"),
    ("flag", r"\b(flag|parliament|sovereig|republic|compact|territory|government|election|council)\b",
     "a wind-torn generic flag seen from its back above an empty civic square, distant monumental stone building"),
    ("medal", r"\b(medals?|award|ceremony|honou?r|decoration|stage|applause)\b",
     "a solitary silver ceremonial medal resting in an open dark velvet box beneath an austere overhead light"),
    ("sea", r"\b(sea|gulf|north|directorate|veyr|tarven|war|border)\b",
     "a cold gulf under a heavy overcast sky, distant industrial coastline and dim lights across water"),
    ("school", r"\b(school|children|ivo|tessa|sami|bridge|bicycle|classroom)\b",
     "a small mechanical drawbridge on a deserted school workbench, dusk light and long shadows"),
    ("house", r"\b(house|rowan|street|neighbou?r|home|window|bedroom|garage|door|garden)\b",
     "a row of ordinary houses at dusk with scattered warm windows and empty pavement, stillness"),
]
FALLBACK = "an empty residential street at blue hour, one lit window, pale drizzle over asphalt"


def words(text: str) -> int:
    return max(1, len(text.split()))


def ffprobe_duration(audio: Path, ffprobe: str = "ffprobe") -> float:
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio)],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise RuntimeError("ffprobe failed: " + result.stderr[-1000:])
    try:
        seconds = float(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError("ffprobe could not read duration for " + str(audio)) from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError("Audio duration must be positive")
    return seconds


def source_scenes(markdown: str) -> list[list[str]]:
    """Scene breaks are the prose's *** separators; title is part of narration."""
    source = markdown.replace("\r\n", "\n")
    pieces = re.split(r"(?m)^\s*\*\*\*\s*$", source)
    result = [manuscript_paragraphs(piece) for piece in pieces]
    return [item for item in result if item]


def sentence_atoms(paragraphs: list[str]) -> list[str]:
    atoms = []
    for paragraph in paragraphs:
        # Very long single paragraphs can be divided for visual choices.
        parts = re.split(r"(?<=[.!?])\s+(?=[“\"A-Z0-9])", paragraph)
        atoms.extend(x for x in parts if x.strip())
    return atoms


def split_atoms(atoms: list[str], groups: int) -> list[list[str]]:
    groups = min(groups, len(atoms))
    output = []
    cursor = 0
    for i in range(groups):
        remaining = groups - i
        if remaining == 1:
            end = len(atoms)
        else:
            remaining_words = sum(words(a) for a in atoms[cursor:])
            target = remaining_words / remaining
            end = cursor
            count = 0
            while end < len(atoms) - (remaining - 1) and (count < target or end == cursor):
                count += words(atoms[end])
                end += 1
        output.append(atoms[cursor:end])
        cursor = end
    return output


def allocate(scenes: list[list[str]], target: int) -> list[int]:
    counts = [1] * len(scenes)
    capacities = [len(sentence_atoms(scene)) for scene in scenes]
    target = min(max(len(scenes), target), sum(capacities))
    weights = [sum(words(p) for p in scene) for scene in scenes]
    for _ in range(target - len(scenes)):
        choices = [i for i in range(len(scenes)) if counts[i] < capacities[i]]
        if not choices:
            break
        best = max(choices, key=lambda i: weights[i] / counts[i])
        counts[best] += 1
    return counts


def pick_motif(text: str) -> tuple[str, str]:
    # A recurring prop or place ties the visual language together across shots.
    scored = []
    for i, (name, pattern, visual) in enumerate(MOTIFS):
        hits = len(re.findall(pattern, text, flags=re.I))
        if hits:
            scored.append((hits, -i, name, visual))
    if scored:
        _, _, name, visual = max(scored)
        return name, visual
    return "house", FALLBACK


def plan_chapter(chapter: dict, markdown: str, duration: float | None,
                 shots: int = 0, seconds_per_shot: float = 32.0) -> dict:
    if seconds_per_shot <= 0:
        raise ValueError("seconds_per_shot must be > 0")
    scenes = source_scenes(markdown)
    if not scenes:
        raise ValueError("No narrative text found")
    spoken = manuscript_paragraphs(markdown)
    total_words = sum(words(x) for x in spoken)
    estimated = duration is None
    total_seconds = duration or total_words / 2.65
    target = shots if shots > 0 else max(len(scenes), round(total_seconds / seconds_per_shot))
    allocations = allocate(scenes, target)
    beats = []
    for scene_id, (scene, count) in enumerate(zip(scenes, allocations), start=1):
        for group in split_atoms(sentence_atoms(scene), count):
            text = " ".join(group).strip()
            motif, visual = pick_motif(text)
            beat_id = len(beats) + 1
            seed = int(hashlib.sha256(f"{chapter['id']}:{beat_id}".encode()).hexdigest()[:8], 16)
            beats.append({
                "index": beat_id, "scene": scene_id, "motif": motif,
                "excerpt": text[:340], "words": words(text), "seed": seed,
                "prompt": f"{visual}, {STYLE}",
                "negative_prompt": NEGATIVE,
                "image": f"storyboards/frames/{chapter['id']}/shot-{beat_id:03d}.png",
            })
    # Shots use word-proportional estimates. Real forced-aligned audio timestamps
    # can be entered by hand in this editable JSON before rendering.
    mass = sum(shot["words"] for shot in beats)
    cumulative = 0
    for shot in beats:
        shot["start"] = round(total_seconds * cumulative / mass, 3)
        cumulative += shot["words"]
        shot["end"] = round(total_seconds * cumulative / mass, 3)
    beats[-1]["end"] = round(total_seconds, 3)
    return {
        "format": "story2-film-lab-v1", "chapter": chapter["id"],
        "title": chapter["title"], "source": chapter["path"],
        "source_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "audio_seconds": round(total_seconds, 3), "estimated_timing": estimated,
        "timing_note": "Shot boundaries estimated from spoken word counts, not exact audio alignment.",
        "style": "faceless cinematic film", "shots": beats,
    }


def fit_timing(storyboard: dict, duration: float) -> dict:
    """Resize an existing plan to actual audio length, retaining edited cues."""
    old = float(storyboard["audio_seconds"])
    if old <= 0:
        raise ValueError("Invalid storyboard duration")
    factor = duration / old
    storyboard = json.loads(json.dumps(storyboard))
    for shot in storyboard["shots"]:
        shot["start"] = round(float(shot["start"]) * factor, 3)
        shot["end"] = round(float(shot["end"]) * factor, 3)
    storyboard["shots"][-1]["end"] = round(duration, 3)
    storyboard["audio_seconds"] = round(duration, 3)
    storyboard["estimated_timing"] = False
    return storyboard


def image_path(shot: dict, root: Path = ROOT) -> Path:
    candidate = Path(shot["image"])
    return candidate if candidate.is_absolute() else root / candidate


def graphic_still(shot: dict, dest: Path, width: int, height: int, chapter_title: str) -> None:
    """Illustrated atmospheric no-face fallback; deterministic from shot seed."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
    except ImportError as exc:
        raise RuntimeError("Pillow is needed: pip install -r requirements-video.txt") from exc
    rng = random.Random(int(shot["seed"]))
    motif = shot.get("motif", "house")
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image, "RGB")
    # Wide cinematic dusk gradient: always establish the visual language.
    for y in range(height):
        t = y / max(1, height - 1)
        dusk = (13 + int(30*t), 23 + int(25*t), 38 + int(23*t))
        draw.line((0, y, width, y), fill=dusk)
    for _ in range(18):
        x = rng.randrange(width)
        y = rng.randrange(max(1, height // 2))
        r = rng.randint(30, max(31, width // 5))
        draw.ellipse((x-r,y-r//3,x+r,y+r//3), fill=(27,39,54))
    floor_y = int(height * 0.68)
    draw.rectangle((0, floor_y, width, height), fill=(31,37,45))

    def building(x: int, y: int, w: int, h: int) -> None:
        draw.rectangle((x, y, x+w, y+h), fill=(20,28,36))
        draw.polygon([(x-5,y),(x+w//2,y-int(h*.13)),(x+w+5,y)], fill=(22,28,35))
        for wy in range(y+int(h*.14), y+h-15, max(18,h//4)):
            for wx in range(x+15, x+w-10, max(20,w//4)):
                if rng.random() < .4:
                    draw.rectangle((wx,wy,wx+int(w*.08),wy+int(h*.09)), fill=(167,124,73))
    if motif in {"house", "table", "school", "flag"}:
        for i in range(7):
            x = int((i - .4) * width / 6)
            w = int(width / 5.9)
            h = int(height * (0.24 + rng.random()*.12))
            building(x, floor_y-h, w, h)
        draw.polygon([(0,height),(int(width*.47),floor_y),(int(width*.55),floor_y),(width,height)], fill=(51,51,54))
        for _ in range(28):
            x,y=rng.randrange(width),rng.randrange(floor_y,height)
            draw.line((x,y,x+rng.randint(2,14),y), fill=(65,63,65))
    if motif == "table":
        y=int(height*.78)
        draw.polygon([(int(width*.24),y),(int(width*.78),y),(int(width*.94),height),(int(width*.08),height)],fill=(99,78,60))
        for j in range(6):
            x=int(width*(.2+j*.105))
            draw.line((x,y-15,x+int(width*.015),y+35), fill=(15,20,28),width=max(2,width//250))
    elif motif in {"archive", "medal"}:
        draw.polygon([(0,int(height*.68)),(width,int(height*.62)),(width,height),(0,height)],fill=(66,55,51))
        if motif == "archive":
            for j in range(3):
                x=int(width*(.28+j*.11)); y=int(height*(.37+j*.07))
                draw.polygon([(x,y),(x+int(width*.36),y-15),(x+int(width*.42),y+int(height*.3)),(x+int(width*.04),y+int(height*.32))], fill=(163-j*20,148-j*18,123-j*13))
                draw.line((x+20,y+42,x+int(width*.24),y+35),fill=(77,81,79),width=2)
        else:
            x=width//2;y=height//2
            draw.ellipse((x-90,y-90,x+90,y+90),fill=(129,123,102),outline=(201,167,101),width=6)
            for k in range(10):
                ang=k*math.pi/5
                x0=x+int(math.cos(ang)*50);y0=y+int(math.sin(ang)*50)
                x1=x+int(math.cos(ang)*72);y1=y+int(math.sin(ang)*72)
                draw.line((x0,y0,x1,y1),fill=(206,176,108),width=4)
    elif motif in {"hospital","detention"}:
        draw.polygon([(0,0),(int(width*.24),int(height*.26)),(int(width*.24),int(height*.78)),(0,height)],fill=(32,44,52))
        draw.polygon([(width,0),(int(width*.76),int(height*.26)),(int(width*.76),int(height*.78)),(width,height)],fill=(28,36,43))
        draw.rectangle((int(width*.4),int(height*.18),int(width*.6),int(height*.75)),fill=(63,76,82))
        draw.rectangle((int(width*.43),int(height*.23),int(width*.57),int(height*.71)),fill=(22,32,42))
        for i in range(2):
            xx=int(width*(.12 if i==0 else .88))
            draw.line((xx,0,xx,height),fill=(72,81,86),width=3)
        draw.polygon([(0,height),(int(width*.4),int(height*.75)),(int(width*.6),int(height*.75)),(width,height)],fill=(49,58,62))
    elif motif == "rail":
        vanish=(width//2,int(height*.51))
        for base in [int(width*.05),int(width*.36),int(width*.64),int(width*.95)]:
            draw.line((*vanish,base,height),fill=(139,117,86),width=5)
        for i in range(1,12):
            t=i/12; y=vanish[1]+int((height-vanish[1])*t*t)
            draw.line((int(width*(.5-.43*t)),y,int(width*(.5+.43*t)),y),fill=(81,76,73),width=3)
        draw.ellipse((int(width*.52),int(height*.3),int(width*.54),int(height*.34)),fill=(222,123,74))
    elif motif == "sea":
        for i in range(35):
            y=int(height*(.53+.47*i/35))
            x=rng.randrange(width)
            draw.line((x,y,min(width,x+rng.randint(20,200)),y),fill=(67,85,95),width=2)
    # Gentle, identifiable faceless foreground silhouette, never a portrait.
    if motif in {"house","school","flag","sea"}:
        x=int(width*(.68 if shot["index"] % 2 else .28)); y=int(height*.71)
        draw.ellipse((x-14,y-84,x+14,y-56),fill=(12,20,29))
        draw.polygon([(x-16,y-55),(x+17,y-55),(x+28,height),(x-28,height)],fill=(11,20,28))
    if motif == "flag":
        pole_x=int(width*.73)
        draw.line((pole_x,int(height*.1),pole_x,int(height*.64)),fill=(155,155,148),width=4)
        draw.polygon([(pole_x,int(height*.12)),(pole_x+130,int(height*.14)),(pole_x+105,int(height*.26)),(pole_x,int(height*.25))],fill=(108,105,115))
    # Analog grain, slightly blurred at a distance.
    grain=Image.effect_noise((width,height),8).convert("RGB")
    image=Image.blend(image,grain,.06)
    draw=ImageDraw.Draw(image)
    try:
        font=ImageFont.truetype("DejaVuSans.ttf",max(12,width//70))
        small=ImageFont.truetype("DejaVuSans.ttf",max(10,width//100))
    except OSError:
        font=ImageFont.load_default();small=font
    draw.rectangle((0,height-62,width,height),fill=(10,16,24))
    draw.text((30,height-49),"THE DISTANCE BETWEEN HOUSES",font=font,fill=(201,181,151))
    draw.text((31,height-27),f"{chapter_title.upper()[:54]}  /  {motif.upper()}",font=small,fill=(133,143,149))
    dest.parent.mkdir(parents=True,exist_ok=True)
    image.save(dest,optimize=True)


def diffusion_still(shot: dict, dest: Path, pipeline, torch, width: int,
                    height: int, steps: int, guidance: float, device: str) -> None:
    if width % 8 or height % 8:
        raise ValueError("Diffusers dimensions must be divisible by 8")
    generator=torch.Generator(device=device).manual_seed(int(shot["seed"]))
    result=pipeline(
        prompt=shot["prompt"], negative_prompt=shot["negative_prompt"],
        num_inference_steps=steps,guidance_scale=guidance,
        width=width,height=height,generator=generator,
    )
    dest.parent.mkdir(parents=True,exist_ok=True)
    result.images[0].convert("RGB").save(dest)


def load_local_pipeline(model: str, device: str):
    if not model or not Path(model).exists():
        raise FileNotFoundError("--model must name an existing LOCAL Diffusers model directory or .safetensors file")
    try:
        import torch
        from diffusers import AutoPipelineForText2Image
    except ImportError as exc:
        raise RuntimeError("Install local torch, diffusers, transformers and accelerate for --mode diffusers") from exc
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is not available. Use --device cpu (very slow) or --mode graphic")
    dtype=torch.float16 if device == "cuda" else torch.float32
    location=str(Path(model).resolve())
    if Path(model).is_file():
        pipe=AutoPipelineForText2Image.from_single_file(location,torch_dtype=dtype,local_files_only=True)
    else:
        pipe=AutoPipelineForText2Image.from_pretrained(location,torch_dtype=dtype,local_files_only=True)
    pipe=pipe.to(device)
    if hasattr(pipe,"enable_vae_slicing"):
        pipe.enable_vae_slicing()
    return pipe,torch


def run_checked(cmd: list[str]) -> None:
    result=subprocess.run(cmd,capture_output=True,text=True,check=False)
    if result.returncode:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(cmd[:8])}\n{result.stderr[-1800:]}")


def render_video(plan: dict, *, audio: Path, output: Path, mode: str,
                 model: str | None, device: str, width: int, height: int,
                 fps: int, steps: int, guidance: float, ffmpeg: str,
                 preview_seconds: float, overwrite_frames: bool) -> None:
    if width < 320 or height < 180 or width % 2 or height % 2:
        raise ValueError("Video size must be even and at least 320x180")
    if fps < 10 or fps > 60:
        raise ValueError("fps must be between 10 and 60")
    if not audio.is_file():
        raise FileNotFoundError("Narration audio missing: " + str(audio))
    total=float(plan["audio_seconds"])
    if preview_seconds:
        total=min(total,preview_seconds)
    timeline=[]
    for shot in plan["shots"]:
        start=float(shot["start"])
        end=min(float(shot["end"]),total)
        if start < total and end > start:
            timeline.append((shot,round(start*fps),round(end*fps)))
    if not timeline:
        raise ValueError("Storyboard does not contain shots in the render range")
    pipe=torch=None
    if mode == "diffusers":
        pipe,torch=load_local_pipeline(model or "",device)
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="story2-film-") as temp:
        work=Path(temp)
        clips=[]
        for i,(shot,start,end) in enumerate(timeline):
            frame=image_path(shot)
            if overwrite_frames or not frame.is_file():
                if mode=="existing":
                    raise FileNotFoundError(f"Missing storyboard image for shot {shot['index']}: {frame}")
                print(f"Image {i+1}/{len(timeline)}: {shot['motif']}",flush=True)
                if mode=="graphic":
                    graphic_still(shot,frame,width,height,plan["title"])
                else:
                    diffusion_still(shot,frame,pipe,torch,width,height,steps,guidance,device)
            count=max(1,end-start)
            clip=work/f"clip-{i:04d}.mp4"
            increment=min(.00035,.10/max(count,1))
            vf=(
                f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},"
                f"zoompan=z='min(zoom+{increment:.8f},1.10)':"
                f"x='(iw-iw/zoom)/2':y='(ih-ih/zoom)/2':"
                f"d=1:s={width}x{height}:fps={fps},format=yuv420p"
            )
            run_checked([ffmpeg,"-y","-hide_banner","-loglevel","error",
                         "-loop","1","-framerate",str(fps),"-i",str(frame),
                         "-vf",vf,"-frames:v",str(count),"-an",
                         "-c:v","libx264","-preset","veryfast","-crf","25",
                         "-pix_fmt","yuv420p",str(clip)])
            clips.append(clip)
            print(f"Shot {i+1}/{len(timeline)} — {count/fps:.1f}s",flush=True)
        listing=work/"clips.txt"
        listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in clips),encoding="utf-8")
        mute=work/"picture.mp4"
        run_checked([ffmpeg,"-y","-hide_banner","-loglevel","error",
                     "-f","concat","-safe","0","-i",str(listing),
                     "-c","copy",str(mute)])
        # Source audio is the clock. Encoding video in independent clips prevents
        # a single hours-long in-memory filter graph.
        run_checked([ffmpeg,"-y","-hide_banner","-loglevel","error",
                     "-i",str(mute),"-i",str(audio),
                     "-map","0:v:0","-map","1:a:0","-c:v","copy",
                     "-c:a","aac","-b:a","160k","-t",f"{total:.3f}",
                     "-movflags","+faststart",str(output)])
    print(f"Film written: {output} ({total:.1f}s)",flush=True)


def main(argv: list[str] | None = None) -> int:
    ap=argparse.ArgumentParser(description=__doc__,
          formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--chapter",required=True,help="Published chapter ID 01-25 (25 = epilogue)")
    ap.add_argument("--audio",type=Path,help="Narration MP3 or WAV; defaults to audio/<chapter>.mp3 or .wav")
    ap.add_argument("--plan",type=Path,help="Editable storyboard JSON; default storyboards/<chapter>.json")
    ap.add_argument("--plan-only",action="store_true",help="Write/inspect visual plan; no image model, FFmpeg or audio needed")
    ap.add_argument("--regenerate-plan",action="store_true",help="Replace hand-edited plan")
    ap.add_argument("--shots",type=int,default=0,help="Number of shots; 0 = auto based on prose length")
    ap.add_argument("--seconds-per-shot",type=float,default=32)
    ap.add_argument("--mode",choices=["graphic","diffusers","existing"],default="graphic")
    ap.add_argument("--model",help="Path to a LOCAL Diffusers model directory or safetensors checkpoint")
    ap.add_argument("--device",choices=["cuda","cpu"],default="cuda")
    ap.add_argument("--width",type=int,default=896)
    ap.add_argument("--height",type=int,default=504)
    ap.add_argument("--fps",type=int,default=24)
    ap.add_argument("--steps",type=int,default=22,help="Diffusers inference steps per missing image")
    ap.add_argument("--guidance",type=float,default=6.5)
    ap.add_argument("--preview-seconds",type=float,default=0,help="Render only beginning for quick tests")
    ap.add_argument("--overwrite-frames",action="store_true")
    ap.add_argument("--ffmpeg",default="ffmpeg")
    ap.add_argument("--ffprobe",default="ffprobe")
    ap.add_argument("--output",type=Path,help="MP4 destination")
    args=ap.parse_args(argv)
    try:
        chapters={ch["id"]:ch for ch in get_chapters()}
        if args.chapter not in chapters:
            ap.error("Unknown chapter: " + args.chapter)
        chapter=chapters[args.chapter]
        source=(ROOT/chapter["path"]).read_text(encoding="utf-8")
        default_audio=ROOT/chapter["audio"]
        audio=args.audio or (default_audio if default_audio.exists() else default_audio.with_suffix(".wav"))
        if args.audio is not None:
            audio=args.audio.expanduser().resolve()
        duration=ffprobe_duration(audio,args.ffprobe) if audio.is_file() else None
        plan_path=args.plan or ROOT/"storyboards"/f"{chapter['id']}.json"
        if not plan_path.is_absolute():
            plan_path=(ROOT/plan_path).resolve()
        if plan_path.is_file() and not args.regenerate_plan:
            plan=json.loads(plan_path.read_text(encoding="utf-8"))
            if plan.get("format")!="story2-film-lab-v1" or plan.get("chapter")!=args.chapter:
                raise ValueError("This storyboard is not for the selected chapter")
            if plan.get("source_sha256")!=hashlib.sha256(source.encode("utf-8")).hexdigest():
                print("Warning: manuscript changed since storyboard was prepared.",file=sys.stderr)
        else:
            plan=plan_chapter(chapter,source,duration,args.shots,args.seconds_per_shot)
            plan_path.parent.mkdir(parents=True,exist_ok=True)
            plan_path.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
            print("Storyboard written:",plan_path)
        if duration is not None and abs(float(plan["audio_seconds"])-duration)>.03:
            plan=fit_timing(plan,duration)
            print("Timed storyboard to narration duration:",f"{duration:.2f}s")
        print(f"Chapter {args.chapter}: {len(plan['shots'])} visual beats, "
              f"{plan['audio_seconds']:.1f}s, mode={args.mode}")
        if args.plan_only:
            for s in plan["shots"][:8]:
                print(f"  {s['index']:03d}  {s['start']:6.1f}–{s['end']:6.1f}s  {s['motif']}")
            if len(plan["shots"])>8:
                print("  ... edit the plan's prompts/images before rendering.")
            if not audio.is_file():
                print("Timing estimated; generate narration first for exact chapter duration.")
            return 0
        if not audio.is_file():
            raise FileNotFoundError(f"No audio found for chapter {args.chapter}: {audio}. "
                                    "Run tools/render_audio.py first, or use --audio.")
        output=args.output or ROOT/"video"/(Path(chapter["audio"]).stem+".mp4")
        if not output.is_absolute():
            output=(ROOT/output).resolve()
        render_video(plan,audio=audio,output=output,mode=args.mode,model=args.model,
            device=args.device,width=args.width,height=args.height,fps=args.fps,
            steps=args.steps,guidance=args.guidance,ffmpeg=args.ffmpeg,
            preview_seconds=args.preview_seconds,overwrite_frames=args.overwrite_frames)
    except (RuntimeError,ValueError,FileNotFoundError,OSError) as exc:
        print("Error:",exc,file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    sys.exit(main())
