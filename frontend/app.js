// Gym Form Coach - the whole front end in one file, no framework and no build step.
// Flow: home -> (photo -> identify) -> guide -> record -> progress -> result

const $ = (id) => document.getElementById(id);
const SCREENS = ["home", "identify", "guide", "record", "progress", "result"];
const state = { catalog: null, machine: null, exerciseId: null, stack: ["home"], photoUrl: null, videoUrl: null };

// Tiny helper to build DOM nodes. Text always goes in as text, never as HTML.
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c.nodeType ? c : String(c));
  return el;
}
// Replace an element's content, skipping the `false` / `null` left behind by `condition && node`.
function fill(el, ...children) {
  el.replaceChildren(...children.flat().filter((c) => c != null && c !== false));
}
const svg = (tag, attrs = {}, ...children) => {
  const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  el.append(...children);
  return el;
};

function show(name, { push = true, title } = {}) {
  for (const s of SCREENS) $("screen-" + s).hidden = s !== name;
  if (push && state.stack[state.stack.length - 1] !== name) state.stack.push(name);
  $("back").hidden = name === "home" || name === "progress";
  $("title").textContent = title || "Gym Form Coach";
  window.scrollTo(0, 0);
}
function goBack() {
  state.stack.pop();
  let prev = state.stack[state.stack.length - 1] || "home";
  while (prev === "progress") { state.stack.pop(); prev = state.stack[state.stack.length - 1] || "home"; }
  if (prev === "home") { state.stack = ["home"]; renderHistory(); history.replaceState(null, "", location.pathname); }
  show(prev, { push: false, title: prev === "home" ? null : state.machine?.name });
}
function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 5000);
}
async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let detail = "The server returned an error.";
    try { detail = (await res.json()).detail || detail; } catch {}
    throw new Error(detail);
  }
  return res.json();
}

// ---- home ---------------------------------------------------------------------------
function renderHome() {
  const grid = $("machine-grid");
  grid.replaceChildren(...state.catalog.machines.map((m) =>
    h("button", { class: "tile", onclick: () => openMachine(m.id) },
      h("span", { class: "emoji", "aria-hidden": "true" }, m.icon), h("span", { class: "name" }, m.name))));
  renderHistory();
}
function loadHistory() {
  try { return JSON.parse(localStorage.getItem("history") || "[]"); } catch { return []; }
}
function saveHistory(entry) {
  try { localStorage.setItem("history", JSON.stringify([entry, ...loadHistory()].slice(0, 8))); } catch {}
}
function renderHistory() {
  const items = loadHistory();
  $("history-block").hidden = items.length === 0;
  $("history").replaceChildren(...items.map((i) =>
    h("li", {}, h("span", {}, `${i.name} · ${i.date}`), h("b", {}, `${i.score}/100`))));
}

// ---- step 1: photo -> machine ---------------------------------------------------------
async function onPhoto(event) {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
  state.photoUrl = URL.createObjectURL(file);
  $("photo-preview").src = state.photoUrl;
  const body = $("identify-body");
  fill(body, h("div", { class: "center" }, h("div", { class: "spinner" }), h("p", {}, "Looking at your photo…")));
  show("identify", { title: "Which machine is this?" });
  try {
    const form = new FormData();
    form.append("photo", file);
    const r = await api("/api/identify", { method: "POST", body: form });
    renderCandidates(r);
  } catch (e) {
    fill(body, h("div", { class: "card note" }, h("p", {}, e.message)), pickFromListButton());
  }
}
const pickFromListButton = () => h("button", { class: "btn ghost", onclick: () => { state.stack = ["home"]; show("home", { push: false }); } }, "Choose from the full list");

function renderCandidates(r) {
  const body = $("identify-body");
  const [first, ...rest] = r.candidates;
  const row = (c, primary) => h("button", { class: "btn candidate" + (primary ? " primary" : ""), onclick: () => openMachine(c.machine_id) },
    h("span", {}, c.name), h("small", {}, `${Math.round(c.confidence * 100)}% match`));
  if (r.recognized) {
    fill(body, 
      h("p", { class: "lead" }, "This looks like:"), row(first, true),
      h("p", { class: "muted" }, "Not right? It could also be:"), ...rest.map((c) => row(c, false)), pickFromListButton());
  } else {
    fill(body, 
      h("div", { class: "card note" }, h("h3", {}, "We are not sure about this photo"),
        h("p", {}, "Stand 2-3 metres back so the whole machine is in the picture, then try again. Or pick the machine below.")),
      ...r.candidates.map((c) => row(c, false)), pickFromListButton());
  }
}

// ---- step 2: guide -------------------------------------------------------------------
function openMachine(machineId, exerciseId) {
  const m = state.catalog.machines.find((x) => x.id === machineId);
  state.machine = m;
  state.exerciseId = exerciseId || m.exercises[0];
  renderGuide();
  show("guide", { title: m.name });
}
const listCard = (title, items, ordered) => h("div", { class: "card" }, h("h3", {}, title),
  h(ordered ? "ol" : "ul", {}, items.map((i) => h("li", {}, i))));

function renderGuide() {
  const m = state.machine, ex = state.catalog.exercises[state.exerciseId];
  const tabs = m.exercises.length > 1 && h("div", { class: "tabs" }, m.exercises.map((id) =>
    h("button", { class: "btn", "aria-pressed": String(id === state.exerciseId), onclick: () => { state.exerciseId = id; renderGuide(); } },
      state.catalog.exercises[id].name)));
  fill($("guide-body"),
    h("p", { class: "muted" }, m.what), tabs,
    h("h2", { style: "margin-top:8px" }, ex.name),
    h("div", { class: "tags" }, ex.muscles.map((x) => h("span", { class: "tag" }, x)), h("span", { class: "tag" }, ex.level)),
    h("div", { class: "card" }, h("h3", {}, "Your first workout"), h("p", { style: "margin:0" }, ex.plan)),
    listCard("1. Set up", ex.setup, true),
    listCard("2. Do the exercise", ex.steps, true),
    listCard("Common mistakes", ex.mistakes, false),
    h("div", { class: "card safe" }, h("h3", {}, "Safety"), h("p", { style: "margin:0" }, ex.safety)),
    ex.form_check
      ? h("button", { class: "btn primary big", onclick: openRecord }, "🎥 Check my form")
      : h("div", { class: "card note" }, h("p", { style: "margin:0" }, "Form check is not ready for this machine yet. The guide above still applies.")),
  );
}

// ---- step 3: record or upload ----------------------------------------------------------
function openRecord() {
  const ex = state.catalog.exercises[state.exerciseId];
  const chosen = h("div", {});
  const onVideo = (event) => {
    const file = event.target.files[0];
    event.target.value = "";
    if (!file) return;
    if (state.videoUrl) URL.revokeObjectURL(state.videoUrl);
    state.videoUrl = URL.createObjectURL(file);
    chosen.replaceChildren(
      h("video", { class: "preview", src: state.videoUrl, controls: true, playsinline: true, muted: true }),
      h("button", { class: "btn primary big", onclick: () => analyse(file) }, "Check this video"));
    chosen.scrollIntoView({ behavior: "smooth" });
  };
  const picker = (label, capture, cls) => h("label", { class: "btn " + cls }, label,
    h("input", { type: "file", accept: "video/*", capture, hidden: true, onchange: onVideo }));
  fill($("record-body"),
    h("h2", { style: "margin-top:4px" }, `Film your ${ex.name}`),
    ex.beta && h("div", { class: "card note" }, h("p", { style: "margin:0" }, "Beta: equipment can hide your arms on this exercise, so the score is less exact.")),
    h("div", { class: "card" }, h("h3", {}, "How to film"),
      h("ul", {}, [ex.camera.tip, "Lean the phone on something so it does not move. Hold it upright, not tilted.",
        "Record 3 to 8 reps (10-30 seconds). One person in the picture.", "Use a light weight. We are checking the movement, not your strength."]
        .map((x) => h("li", {}, x)))),
    picker("🎥 Record a video", "environment", "primary big"), picker("Upload a video from this device", false, "ghost"), chosen);
  show("record", { title: state.machine.name });
}

async function analyse(file) {
  show("progress", { title: "Checking your form" });
  const setProgress = (stage, p) => { $("progress-stage").textContent = stage; $("progress-fill").style.width = Math.round(p * 100) + "%"; };
  setProgress("Uploading your video", 0.03);
  try {
    const form = new FormData();
    form.append("exercise_id", state.exerciseId);
    form.append("video", file, file.name || "video.mp4");
    const { job_id } = await api("/api/analyze", { method: "POST", body: form });
    for (;;) {
      await new Promise((r) => setTimeout(r, 1000));
      const job = await api("/api/jobs/" + job_id);
      if (job.status === "error") throw new Error(job.error);
      if (job.status === "done") { history.replaceState(null, "", "#job=" + job_id); renderResult(job.result); return; }
      setProgress(job.stage, Math.max(0.05, job.progress));
    }
  } catch (e) {
    toast(e.message);
    state.stack = state.stack.filter((s) => s !== "progress");
    show("record", { push: false, title: state.machine?.name });
  }
}

// ---- step 4: result ---------------------------------------------------------------------
const colour = (score) => (score >= 80 ? "var(--good)" : score >= 55 ? "var(--warn)" : "var(--bad)");

function ring(score) {
  const r = 46, c = 2 * Math.PI * r;
  return svg("svg", { class: "ring", viewBox: "0 0 108 108", role: "img", "aria-label": `Score ${score} out of 100` },
    svg("circle", { cx: 54, cy: 54, r, fill: "none", stroke: "var(--line)", "stroke-width": 10 }),
    svg("circle", { cx: 54, cy: 54, r, fill: "none", stroke: colour(score), "stroke-width": 10, "stroke-linecap": "round",
      "stroke-dasharray": `${(c * score) / 100} ${c}`, transform: "rotate(-90 54 54)" }),
    Object.assign(svg("text", { x: 54, y: 64, "text-anchor": "middle" }), { textContent: score }));
}

function chart(series, reps) {
  const W = 320, H = 130, pad = { l: 30, r: 6, t: 8, b: 20 };
  const pts = series.t.map((t, i) => [t, series.value[i]]).filter((p) => p[1] != null);
  if (pts.length < 2) return null;
  const tMax = series.t[series.t.length - 1] || 1;
  const lo = Math.floor(Math.min(...pts.map((p) => p[1])) / 10) * 10, hi = Math.ceil(Math.max(...pts.map((p) => p[1])) / 10) * 10;
  const x = (t) => pad.l + (t / tMax) * (W - pad.l - pad.r), y = (v) => pad.t + (1 - (v - lo) / (hi - lo || 1)) * (H - pad.t - pad.b);
  const el = svg("svg", { class: "chart", viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": `${series.label} over time` });
  for (const r of reps) el.append(svg("rect", { class: "band", x: x(r.t_start), y: pad.t, width: Math.max(1, x(r.t_end) - x(r.t_start) - 1), height: H - pad.t - pad.b }));
  el.append(svg("line", { class: "axis", x1: pad.l, y1: H - pad.b, x2: W - pad.r, y2: H - pad.b }));
  el.append(svg("polyline", { class: "line", points: pts.map((p) => `${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ") }));
  const label = (tx, ty, text, anchor = "start") => Object.assign(svg("text", { x: tx, y: ty, "text-anchor": anchor }), { textContent: text });
  el.append(label(pad.l - 4, y(hi) + 8, hi + "°", "end"), label(pad.l - 4, y(lo), lo + "°", "end"),
    label(pad.l, H - 5, "0 s"), label(W - pad.r, H - 5, tMax.toFixed(0) + " s", "end"));
  return el;
}

function renderResult(r, { save = true } = {}) {
  const body = $("result-body");
  const again = h("button", { class: "btn primary", onclick: () => { state.stack = state.stack.filter((s) => s !== "result" && s !== "progress"); openRecord(); } }, "Film another set");
  const guide = h("button", { class: "btn ghost", onclick: () => { state.stack = ["home"]; openMachine(state.machine.id, state.exerciseId); } }, "Back to the guide");

  if (!r.ok) {
    fill(body, 
      h("div", { class: "card note" }, h("h3", {}, r.reason), h("ul", {}, r.tips.map((t) => h("li", {}, t)))),
      ...(r.warnings || []).map((w) => h("div", { class: "card note" }, w)), again, guide);
    show("result", { title: r.exercise_name });
    return;
  }

  if (save) saveHistory({ name: r.exercise_name, score: r.score, date: new Date().toLocaleDateString() });
  const count = r.type === "reps" ? `${r.rep_count} rep${r.rep_count === 1 ? "" : "s"} counted` : `${r.hold_seconds} second hold`;
  const meter = (label, score) => h("div", { class: "meter" },
    h("div", { class: "row" }, h("span", {}, label), h("b", {}, score)),
    h("div", { class: "track" }, h("div", { class: "fill", style: `width:${score}%;background:${colour(score)}` })));

  fill(body, 
    h("div", { class: "card" },
      h("div", { class: "score-head" }, ring(r.score),
        h("div", {}, h("div", { class: "verdict" }, r.verdict), h("div", { class: "muted" }, count),
          h("div", { class: "muted" }, `Confidence in this score: ${r.confidence}`)))),
    ...r.warnings.map((w) => h("div", { class: "card note" }, w)),

    r.video && h("h2", {}, "Watch your set"),
    r.video && h("div", { class: "card" },
      h("video", { class: "review", src: r.video, poster: r.video_poster, controls: true, playsinline: true, muted: true, preload: "metadata" }),
      h("p", { class: "muted", style: "margin:8px 0 10px" },
        "Left: your video with the measured joint in orange. Right: the angle through the set, with each counted rep shaded."),
      h("a", { class: "btn ghost", style: "margin:0", href: r.video, download: `form-check-${r.exercise_id}.mp4` }, "⬇ Save this video")),

    h("h2", {}, r.issues.length ? "What to fix" : "Nothing to fix"),
    !r.issues.length && h("div", { class: "card" }, "We found no clear problem in this video. Keep the same form when you add weight."),
    ...r.issues.map((i) => h("div", { class: "card issue " + i.severity },
      h("h3", {}, i.title, h("span", { class: "pill " + i.severity }, i.severity)),
      h("p", { class: "muted", style: "margin:0" }, i.detail,
        i.reps_affected.length ? ` Seen in ${r.unit} ${i.reps_affected.join(", ")}.` : ""),
      i.snapshot && h("img", { src: i.snapshot, alt: `Video frame at ${i.t} seconds showing: ${i.title}`, loading: "lazy" }),
      h("div", { class: "fix" }, h("b", {}, "Fix: "), i.fix))),

    r.positives.length > 0 && h("h2", {}, "What you did well"),
    r.positives.length > 0 && h("div", { class: "card" }, h("ul", { class: "ok-list" }, r.positives.map((p) => h("li", {}, p)))),

    h("h2", {}, "Score by area"),
    h("div", { class: "card" }, Object.values(r.subscores).map((s) => meter(s.label, s.score))),

    h("h2", {}, r.type === "reps" ? "Score for each rep" : "Score through the hold (2-second steps)"),
    h("div", { class: "card" }, h("div", { class: "reps" }, r.reps.map((rep) =>
      h("div", { class: "rep", title: `${rep.t_start}s - ${rep.t_end}s` }, h("b", {}, rep.score),
        h("i", { style: `height:${Math.max(4, rep.score * 0.6)}%;background:${colour(rep.score)}` }), rep.n)))),

    h("h2", {}, `${r.series.label} during the video`),
    h("div", { class: "card" }, chart(r.series, r.type === "reps" ? r.reps : []),
      h("p", { class: "muted", style: "margin:6px 0 0" }, r.type === "reps" ? "Each shaded block is one counted rep." : "A straight body is close to 180°.")),

    h("p", { class: "fine" }, `Analysed ${r.frames_analyzed} frames (${r.duration_s} s). View: ${r.view}, ${r.side} side. Angles from: ${r.angles_from}.` +
      (r.classifier_used ? ` Posture model: ${r.classifier_used}.` : "")),
    again, guide);
  show("result", { title: r.exercise_name });
}

// ---- start --------------------------------------------------------------------------------
async function pollHealth() {
  try {
    const hl = await api("/api/health");
    const s = hl.machine_recognizer;
    $("status").textContent = s === "ready" ? "" : s === "error" ? "⚠ scanner offline" : "⏳ scanner loading…";
    if (s !== "ready" && s !== "error") setTimeout(pollHealth, 3000);
  } catch { setTimeout(pollHealth, 5000); }
}
// Links like  /#machine=leg_press  or  /#job=abc123  open that screen directly (also after a reload).
async function openFromLink() {
  const [key, value] = location.hash.slice(1).split("=");
  if (key === "machine" && state.catalog.machines.some((m) => m.id === value)) openMachine(value);
  if (key === "job" && value) {
    try {
      const job = await api("/api/jobs/" + encodeURIComponent(value));
      if (job.status !== "done") return;
      const ex = job.result.exercise_id;
      state.machine = state.catalog.machines.find((m) => m.exercises.includes(ex));
      state.exerciseId = ex;
      renderResult(job.result, { save: false });
    } catch { history.replaceState(null, "", location.pathname); }
  }
}
async function start() {
  $("back").addEventListener("click", goBack);
  $("photo-input").addEventListener("change", onPhoto);
  $("photo-input-gallery").addEventListener("change", onPhoto);
  try {
    state.catalog = await api("/api/catalog");
    renderHome();
    pollHealth();
    await openFromLink();
  } catch (e) {
    toast("Could not reach the server. Is it running?");
  }
}
start();
