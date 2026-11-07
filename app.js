"use strict";

const state = { manifest: null, chapters: [], current: null, audioRequest: 0 };
const $ = (id) => document.getElementById(id);

function readSetting(key, fallback) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function saveSetting(key, value) {
  try { localStorage.setItem(key, value); } catch { /* Storage may be disabled */ }
}

function setTheme(theme) {
  document.body.dataset.theme = theme === "light" ? "light" : "dark";
  $("theme-toggle").textContent = theme === "light" ? "☾" : "☼";
  $("theme-toggle").setAttribute("aria-label", theme === "light" ? "Switch to dark theme" : "Switch to light theme");
  saveSetting("story2-theme", document.body.dataset.theme);
}
function setSize(size) {
  const value = Math.max(0, Math.min(3, Number(size) || 0));
  document.body.dataset.size = String(value);
  saveSetting("story2-size", String(value));
}
function addInline(parent, content) {
  const tokens = content.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  for (const token of tokens) {
    if (!token) continue;
    if (token.startsWith("**") && token.endsWith("**")) {
      const bold = document.createElement("strong");
      bold.textContent = token.slice(2, -2);
      parent.append(bold);
    } else if (token.startsWith("*") && token.endsWith("*")) {
      const em = document.createElement("em");
      em.textContent = token.slice(1, -1);
      parent.append(em);
    } else parent.append(document.createTextNode(token));
  }
}
function makeParagraph(text, className) {
  const p = document.createElement("p");
  if (className) p.className = className;
  addInline(p, text.replace(/\s*\n\s*/g, " ").trim());
  return p;
}
function renderMarkdown(markdown, container) {
  container.replaceChildren();
  const blocks = markdown.replace(/\r/g, "").trim().split(/\n\s*\n/g);
  for (const original of blocks) {
    const block = original.trim();
    if (!block || block.startsWith("# ")) continue;
    if (/^\*\s*\*\s*\*$/.test(block)) {
      const breakEl = document.createElement("div");
      breakEl.className = "scene-break";
      breakEl.textContent = "✦";
      breakEl.setAttribute("aria-hidden", "true");
      container.append(breakEl);
      continue;
    }
    if (block.startsWith("## ")) {
      const heading = document.createElement("h2");
      heading.textContent = block.slice(3);
      container.append(heading);
    } else if (/^\*[^*]+\*$/.test(block)) {
      container.append(makeParagraph(block.slice(1, -1), "story-location"));
    } else container.append(makeParagraph(block));
  }
}

function renderChapterCards() {
  const target = $("chapter-cards");
  target.replaceChildren();
  for (const chapter of state.chapters) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chapter-card";
    button.dataset.chapter = chapter.id;
    const n = document.createElement("span");
    n.className = "chapter-num";
    n.textContent = "CHAPTER " + chapter.id;
    const title = document.createElement("h3");
    title.textContent = chapter.title;
    const desc = document.createElement("p");
    desc.textContent = chapter.description || "";
    const foot = document.createElement("div");
    foot.className = "card-bottom";
    const time = document.createElement("span");
    time.textContent = Math.max(1, Math.round(chapter.words / 190)) + " MIN READ";
    const arrow = document.createElement("span");
    arrow.textContent = "READ →";
    foot.append(time, arrow);
    button.append(n, title, desc, foot);
    target.append(button);
  }
}
function renderTOC() {
  const target = $("reader-toc");
  target.replaceChildren();
  for (const ch of state.chapters) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "toc-entry" + (ch.id === state.current ? " active" : "");
    button.dataset.chapter = ch.id;
    const number = document.createElement("span");
    number.textContent = "CHAPTER " + ch.id;
    button.append(number, document.createTextNode(ch.title));
    target.append(button);
  }
}

function showHome() {
  state.current = null;
  $("home-view").hidden = false;
  $("reader-view").hidden = true;
  $("scroll-progress").style.width = "0%";
  document.title = "The Distance Between Houses — Story2";
  const anchor = location.hash === "#chapters" ? $("chapters") : location.hash === "#about" ? $("about") : null;
  if (anchor) requestAnimationFrame(() => anchor.scrollIntoView({ block: "start" }));
  else window.scrollTo({ top: 0, behavior: "instant" });
}

async function checkAudio(chapter) {
  const request = ++state.audioRequest;
  const player = $("chapter-audio");
  const status = $("audio-status");
  player.pause();
  player.hidden = true;
  player.removeAttribute("src");
  player.load();
  status.textContent = "Checking for a published narration…";
  const source = chapter.audio || ("audio/" + chapter.id + ".mp3");
  for (const path of [source, source.replace(/\.mp3$/i, ".wav")]) {
    try {
      const response = await fetch(path, { method: "HEAD" });
      if (request !== state.audioRequest) return;
      if (response.ok) {
        player.src = path;
        player.hidden = false;
        status.textContent = "Narrated edition · " + chapter.title;
        return;
      }
    } catch { /* Audio not published yet */ }
  }
  if (request === state.audioRequest) {
    status.textContent = "Narration hasn't been published yet. The repository includes a Python tool to generate local chapter audio with Piper; the written chapter is complete.";
  }
}

async function showChapter(id) {
  const chapter = state.chapters.find((item) => item.id === id);
  if (!chapter) { showHome(); return; }
  state.current = chapter.id;
  $("home-view").hidden = true;
  $("reader-view").hidden = false;
  $("chapter-kicker").textContent = "PART " + chapter.partNumber + " · CHAPTER " + chapter.id;
  $("chapter-title").textContent = chapter.title;
  $("chapter-byline").textContent = "The Distance Between Houses · " + chapter.words.toLocaleString() + " words";
  $("chapter-body").textContent = "Loading chapter…";
  $("previous-chapter").disabled = state.chapters.indexOf(chapter) === 0;
  $("next-chapter").disabled = state.chapters.indexOf(chapter) === state.chapters.length - 1;
  $("next-chapter").textContent = $("next-chapter").disabled ? "More chapters forthcoming" : "Next chapter →";
  $("next-chapter").disabled = state.chapters.indexOf(chapter) === state.chapters.length - 1;
  $("footer-progress").textContent = "READING CHAPTER " + chapter.id;
  document.title = chapter.title + " — The Distance Between Houses";
  saveSetting("story2-last-chapter", chapter.id);
  renderTOC();
  window.scrollTo({ top: 0, behavior: "instant" });
  try {
    const result = await fetch(chapter.path);
    if (!result.ok) throw new Error("HTTP " + result.status);
    const markdown = await result.text();
    if (state.current !== chapter.id) return;
    renderMarkdown(markdown, $("chapter-body"));
    updateProgress();
  } catch (error) {
    if (state.current === chapter.id) $("chapter-body").textContent = "Could not load this chapter: " + error.message + ". Please refresh the page.";
  }
  checkAudio(chapter);
}
function updateProgress() {
  if (!state.current) return;
  const full = document.documentElement.scrollHeight - window.innerHeight;
  const fraction = full <= 0 ? 1 : Math.min(1, Math.max(0, window.scrollY / full));
  $("scroll-progress").style.width = Math.round(fraction * 100) + "%";
}
function navigate() {
  const hash = decodeURIComponent(location.hash.slice(1));
  const match = /^chapter-(\d{2})$/.exec(hash);
  if (match) showChapter(match[1]);
  else showHome();
}
function goAdjacent(step) {
  const at = state.chapters.findIndex((ch) => ch.id === state.current);
  const target = state.chapters[at + step];
  if (target) location.hash = "chapter-" + target.id;
}
async function main() {
  setTheme(readSetting("story2-theme", "dark"));
  setSize(readSetting("story2-size", "1"));
  $("theme-toggle").addEventListener("click", () => setTheme(document.body.dataset.theme === "light" ? "dark" : "light"));
  $("font-smaller").addEventListener("click", () => setSize(Number(document.body.dataset.size) - 1));
  $("font-larger").addEventListener("click", () => setSize(Number(document.body.dataset.size) + 1));
  $("previous-chapter").addEventListener("click", () => goAdjacent(-1));
  $("next-chapter").addEventListener("click", () => goAdjacent(1));
  $("start-reading").addEventListener("click", () => { location.hash = "chapter-01"; });
  document.addEventListener("click", (event) => {
    const control = event.target.closest("[data-chapter]");
    if (control) location.hash = "chapter-" + control.dataset.chapter;
  });
  window.addEventListener("hashchange", navigate);
  window.addEventListener("scroll", updateProgress, { passive: true });
  try {
    const response = await fetch("book/manifest.json");
    if (!response.ok) throw new Error("HTTP " + response.status);
    state.manifest = await response.json();
    state.chapters = state.manifest.parts.flatMap((part, i) => part.chapters.map((chapter) => ({...chapter, partNumber: ["I", "II", "III", "IV", "V", "VI"][i] || String(i + 1)})));
    renderChapterCards();
    navigate();
  } catch (error) {
    $("chapter-cards").textContent = "The chapter index could not be loaded. Open this site through a web server rather than a local file: " + error.message;
  }
}
main();
