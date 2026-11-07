#!/usr/bin/env python3
"""Small desktop GUI for the offline Story2 Film Lab. Windows: python tools/film_lab_gui.py"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parents[1]
CHAPTERS = [c for p in json.loads((ROOT / "book/manifest.json").read_text(encoding="utf-8"))["parts"]
            for c in p["chapters"]]


class FilmGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Story2 — Film Lab")
        self.geometry("860x730")
        self.minsize(680, 570)
        self.configure(bg="#121a25")
        self.chapter = tk.StringVar(value="01")
        self.audio = tk.StringVar(value="")
        self.mode = tk.StringVar(value="graphic")
        self.model = tk.StringVar(value="")
        self.width = tk.StringVar(value="896")
        self.height = tk.StringVar(value="504")
        self.shots = tk.StringVar(value="0")
        self.preview = tk.StringVar(value="40")
        self.status = tk.StringVar(value="Choose a chapter. Plan first to see the visual beats.")
        self.working = False
        self._build()
        self.chapter.trace_add("write", lambda *_: self._select_chapter())
        self._select_chapter()

    def _build(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#121a25")
        style.configure("TLabel", background="#121a25", foreground="#e0e6ec", font=("Segoe UI", 10))
        style.configure("TButton", padding=7, font=("Segoe UI", 10))
        style.configure("TRadiobutton", background="#121a25", foreground="#e0e6ec")
        style.configure("TCombobox", padding=6)
        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="THE DISTANCE BETWEEN HOUSES  /  FILM LAB",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(body, text="Narration + editable storyboards + faceless cinematic shots → MP4",
                  foreground="#9cb1c2").pack(anchor="w", pady=(2, 14))
        row = ttk.Frame(body)
        row.pack(fill="x", pady=5)
        ttk.Label(row, text="Chapter", width=18).pack(side="left")
        chapter_choices = [f"{c['id']} — {c['title']}" for c in CHAPTERS]
        self.pick = ttk.Combobox(row, values=chapter_choices, state="readonly", width=65)
        self.pick.pack(side="left", fill="x", expand=True)
        self.pick.current(0)
        self.pick.bind("<<ComboboxSelected>>", lambda *_: self.chapter.set(self.pick.get()[:2]))
        self._field(body, "Narration MP3/WAV", self.audio, True, "audio")
        options = ttk.Frame(body)
        options.pack(fill="x", pady=(12, 8))
        ttk.Label(options, text="Visual mode", width=18).pack(side="left")
        for value, label in [("graphic", "Graphic (no AI)"),
                             ("diffusers", "Local image model"),
                             ("existing", "Use my images")]:
            ttk.Radiobutton(options, text=label, value=value, variable=self.mode).pack(side="left", padx=(0, 18))
        self._field(body, "Local model folder", self.model, True, "model")
        fmt = ttk.Frame(body)
        fmt.pack(fill="x", pady=8)
        ttk.Label(fmt, text="Width × height", width=18).pack(side="left")
        ttk.Entry(fmt, textvariable=self.width, width=7).pack(side="left")
        ttk.Label(fmt, text=" × ").pack(side="left")
        ttk.Entry(fmt, textvariable=self.height, width=7).pack(side="left")
        ttk.Label(fmt, text="   Shots (0 = automatic)").pack(side="left", padx=(16, 8))
        ttk.Entry(fmt, textvariable=self.shots, width=7).pack(side="left")
        act = ttk.Frame(body)
        act.pack(fill="x", pady=(15, 8))
        self.buttons = []
        for label, task in [("1. Make storyboard", "plan"),
                            ("2. Preview video", "preview"),
                            ("3. Render full chapter", "render"),
                            ("Edit storyboard JSON", "edit")]:
            button = ttk.Button(act, text=label, command=lambda t=task: self._start(t))
            button.pack(side="left", padx=(0, 8))
            self.buttons.append(button)
        prev = ttk.Frame(body)
        prev.pack(fill="x", pady=5)
        ttk.Label(prev, text="Preview duration (sec)", width=22).pack(side="left")
        ttk.Entry(prev, textvariable=self.preview, width=8).pack(side="left")
        self.bar = ttk.Progressbar(body, mode="indeterminate")
        self.bar.pack(fill="x", pady=(12, 5))
        ttk.Label(body, textvariable=self.status, wraplength=780).pack(anchor="w", pady=(0, 8))
        self.log = tk.Text(body, bg="#0c121b", fg="#c9d7df", insertbackground="white",
                           font=("Consolas", 9), wrap="word", height=13, relief="flat",
                           padx=12, pady=12, state="disabled")
        self.log.pack(fill="both", expand=True)
        ttk.Label(body, text="No cloud account needed. Built-in graphics avoid faces; "
                  "image-model mode needs locally installed Diffusers + weights.",
                  foreground="#91a3ad", wraplength=780).pack(anchor="w", pady=(10, 0))

    def _field(self, parent, label, variable, browse, kind):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=6)
        ttk.Label(row, text=label, width=18).pack(side="left")
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        if browse:
            ttk.Button(row, text="Browse", command=lambda: self._browse(variable, kind)).pack(side="left", padx=(8, 0))

    def _browse(self, variable, kind):
        if kind == "audio":
            name = filedialog.askopenfilename(title="Choose chapter narration",
                   filetypes=[("Audio", "*.mp3 *.wav *.m4a"), ("All files", "*.*")])
        else:
            name = filedialog.askdirectory(title="Choose local Diffusers model folder")
        if name:
            variable.set(name)

    def _select_chapter(self):
        entry = next((c for c in CHAPTERS if c["id"] == self.chapter.get()), None)
        if not entry:
            return
        default = ROOT / entry["audio"]
        wav = default.with_suffix(".wav")
        self.audio.set(str(default if default.exists() or not wav.exists() else wav))
        self.status.set(f"Chapter {entry['id']}: {entry['title']}. "
                        "The storyboard works before audio exists; rendering requires narration.")

    def _append(self, line):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _toggle(self, busy):
        self.working = busy
        for b in self.buttons:
            b.configure(state="disabled" if busy else "normal")
        if busy:
            self.bar.start(12)
        else:
            self.bar.stop()

    def _start(self, task):
        if self.working:
            return
        ident = self.chapter.get()
        plan = ROOT / "storyboards" / f"{ident}.json"
        if task == "edit":
            if not plan.is_file():
                messagebox.showinfo("Story2 Film Lab", "Create the storyboard first.")
                return
            try:
                if os.name == "nt":
                    os.startfile(str(plan))
                else:
                    subprocess.Popen(["xdg-open", str(plan)])
            except OSError as error:
                messagebox.showerror("Could not open file", str(error))
            return
        try:
            width, height, shots = int(self.width.get()), int(self.height.get()), int(self.shots.get())
            seconds = float(self.preview.get())
            if seconds <= 0:
                raise ValueError("Preview seconds must be positive")
        except ValueError as error:
            messagebox.showerror("Invalid settings", str(error))
            return
        cmd = [sys.executable, str(ROOT / "tools" / "film_lab.py"),
               "--chapter", ident, "--mode", self.mode.get(),
               "--width", str(width), "--height", str(height),
               "--shots", str(shots)]
        if self.audio.get().strip():
            cmd.extend(["--audio", self.audio.get().strip()])
        if self.mode.get() == "diffusers":
            if not self.model.get().strip():
                messagebox.showerror("Local model needed", "Choose a local model directory.")
                return
            cmd.extend(["--model", self.model.get().strip()])
        if task == "plan":
            cmd.append("--plan-only")
        if task == "preview":
            cmd.extend(["--preview-seconds", str(seconds),
                        "--output", str(ROOT / "video" / f"{ident}-preview.mp4")])
        self._toggle(True)
        self.status.set("Running " + task + "…")
        self._append("$ " + " ".join(f'"{x}"' if " " in x else x for x in cmd))
        threading.Thread(target=self._run, args=(cmd, task), daemon=True).start()

    def _run(self, cmd, task):
        try:
            proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    encoding="utf-8", errors="replace", bufsize=1)
            for line in proc.stdout:
                self.after(0, self._append, line.rstrip())
            code = proc.wait()
            self.after(0, self._done, task, code)
        except Exception as exc:
            self.after(0, self._append, "ERROR: " + str(exc))
            self.after(0, self._done, task, 1)

    def _done(self, task, code):
        self._toggle(False)
        if code:
            self.status.set("Failed. See log for details.")
        elif task == "plan":
            self.status.set("Storyboard ready. Edit its image prompts, or render a preview.")
        else:
            self.status.set("Finished! MP4 is in the video/ folder.")
            if os.name == "nt":
                try:
                    os.startfile(str(ROOT / "video"))
                except OSError:
                    pass


if __name__ == "__main__":
    FilmGUI().mainloop()
