// Gym Form Coach - the whole front end in one file, no framework and no build step.
// Flow: home -> (photo -> identify) -> guide -> record -> progress -> result

const $ = (id) => document.getElementById(id);
const SCREENS = ["home", "identify", "guide", "record", "progress", "result", "feedback"];
const MAX_VIDEO_MB = 100;   // same limit as the server
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
  $("feedback-btn").hidden = name === "feedback" || name === "progress";
  $("title").textContent = title || "Gym Form Coach";
  window.scrollTo(0, 0);
}
function goBack() {
  state.stack.pop();
  let prev = state.stack[state.stack.length - 1] || "home";
  while (prev === "progress") { state.stack.pop(); prev = state.stack[state.stack.length - 1] || "home"; }
  if (prev === "home") { state.stack = ["home"]; renderHistory(); history.replaceState(null, "", location.pathname); }
  show(prev, { push: false, title: prev === "home" ? null : prev === "identify" ? "Which machine is this?" : state.machine?.name });
}
function toast(message) {
  const t = $("toast");
  t.textContent = message;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (t.hidden = true), 5000);
}
// The page can come from two places. From the server itself: API stays "". From GitHub Pages (a copy of
// this folder plus server.json and catalog.json): STATIC is true and API is the server's current address.
let API = "", STATIC = false;
const OFFLINE = "The checker is offline right now. The guides still work. Please try again later.";
const media = (url) => (url ? API + url : url);
async function api(path, options) {
  if (STATIC && !API) throw new Error(OFFLINE);
  let res;
  try { res = await fetch(API + path, options); } catch { throw new Error(STATIC ? OFFLINE : "Could not reach the server."); }
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
    if (file.size > MAX_VIDEO_MB * 1024 * 1024) {
      toast(`This video is ${Math.round(file.size / 1024 / 1024)} MB. The limit is ${MAX_VIDEO_MB} MB. Record 10-30 seconds and try again.`);
      return;
    }
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
    h("div", { class: "card note" }, h("h3", {}, "Read this before you film"),
      h("p", { style: "margin:0" }, "The check only works when the video is filmed the right way. Most failed checks are a camera problem, not a form problem.")),
    h("div", { class: "card" }, h("h3", {}, "Watch: how to film (24 seconds)"),
      h("video", { class: "howto", src: "demo/how-to-film.mp4", poster: "demo/how-to-film.jpg", controls: true, playsinline: true, muted: true, loop: true, preload: "metadata" }),
      h("p", { class: "muted", style: "margin:8px 0 0" }, "The example shows a squat. Film every exercise the same way: from the side, with the whole body in the picture.")),
    h("div", { class: "card" }, h("h3", {}, "Do this"),
      h("ul", { class: "ok-list" }, [ex.camera.tip, "Lean the phone on a bottle or a bag so it does not move. Hold it upright, not tilted.",
        "Record 3 to 8 reps (10-30 seconds), from start to finish, without cuts.", "Only one person in the picture, in good light.",
        "Use a light weight and normal speed. We are checking the movement, not your strength."]
        .map((x) => h("li", {}, x)))),
    h("div", { class: "card" }, h("h3", {}, "This will not work"),
      h("ul", { class: "no-list" }, [ex.camera.view === "side" ? "Filming from the front or from behind." : "Filming from the side.",
        "Standing too close, so part of the body is cut off.", "Holding the phone in a hand, or a friend walking around you.",
        "A dark room, or other people moving behind you.", `A video longer than about 30 seconds (the limit is ${MAX_VIDEO_MB} MB).`]
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
    // Some phone file pickers give a name with no ending; the server needs one to accept the video.
    const ending = { "video/quicktime": "mov", "video/webm": "webm", "video/3gpp": "3gp", "video/x-matroska": "mkv" }[file.type] || "mp4";
    form.append("video", file, /\.(mp4|mov|m4v|webm|avi|mkv|3gp)$/i.test(file.name || "") ? file.name : "video." + ending);
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
      ...(r.warnings || []).map((w) => h("div", { class: "card note" }, w)), again, guide,
      h("h2", {}, "Tell us what happened"), feedbackForm({ exerciseId: r.exercise_id }));
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
      h("video", { class: "review", src: media(r.video), poster: media(r.video_poster), controls: true, playsinline: true, muted: true, preload: "metadata" }),
      h("p", { class: "muted", style: "margin:8px 0 10px" },
        "Left: your video with the measured joint in orange. Right: the angle through the set, with each counted rep shaded."),
      h("a", { class: "btn ghost", style: "margin:0", href: media(r.video), download: `form-check-${r.exercise_id}.mp4` }, "⬇ Save this video")),

    h("h2", {}, r.issues.length ? "What to fix" : "Nothing to fix"),
    !r.issues.length && h("div", { class: "card" }, "We found no clear problem in this video. Keep the same form when you add weight."),
    ...r.issues.map((i) => h("div", { class: "card issue " + i.severity },
      h("h3", {}, i.title, h("span", { class: "pill " + i.severity }, i.severity)),
      h("p", { class: "muted", style: "margin:0" }, i.detail,
        i.reps_affected.length ? ` Seen in ${r.unit} ${i.reps_affected.join(", ")}.` : ""),
      i.snapshot && h("img", { src: media(i.snapshot), alt: `Video frame at ${i.t} seconds showing: ${i.title}`, loading: "lazy" }),
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
    again, guide,
    h("h2", {}, "Was this check right?"),
    feedbackForm({ jobId: jobIdFromLink(), exerciseId: r.exercise_id, askAccuracy: true }));
  show("result", { title: r.exercise_name });
}

// ---- feedback from testers ----------------------------------------------------------------
const jobIdFromLink = () => (location.hash.startsWith("#job=") ? location.hash.slice(5) : "");

// A card with stars, an optional "was the result right?" question and a comment box.
function feedbackForm({ jobId = "", exerciseId = "", askAccuracy = false } = {}) {
  const answer = { rating: 0, accurate: null };
  const card = h("div", { class: "card" });
  const comment = h("textarea", { rows: 4, maxlength: 2000, "aria-label": "Your comments",
    placeholder: "What worked? What was confusing or wrong? What would you add?" });
  const contact = h("input", { type: "text", maxlength: 120, "aria-label": "Name or contact (optional)", placeholder: "Your name or email (optional)" });
  const send = h("button", { class: "btn primary", disabled: true, style: "margin:10px 0 0" }, "Send feedback");
  const stars = [1, 2, 3, 4, 5].map((n) => h("button", { class: "star", type: "button", "aria-label": `${n} out of 5`, "aria-pressed": "false",
    onclick: () => { answer.rating = n; stars.forEach((s, k) => s.setAttribute("aria-pressed", String(k < n))); send.disabled = false; } }, "★"));
  const choices = [["yes", "Yes"], ["partly", "Partly"], ["no", "No"]].map(([value, label]) => h("button", { class: "btn", type: "button", "aria-pressed": "false",
    onclick: () => { answer.accurate = value; choices.forEach((c) => c.setAttribute("aria-pressed", String(c.textContent === label))); } }, label));
  send.addEventListener("click", async () => {
    send.disabled = true;
    try {
      await api("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...answer, comment: comment.value, contact: contact.value, job_id: jobId, exercise_id: exerciseId }) });
      fill(card, h("h3", {}, "Thank you!"), h("p", { class: "muted", style: "margin:0" }, "Your feedback was saved. It helps us decide what to fix next."));
    } catch (e) {
      toast(e.message);
      send.disabled = false;
    }
  });
  fill(card,
    h("h3", {}, "How useful was this app for you? Tap a star."), h("div", { class: "stars" }, stars),
    askAccuracy && h("h3", { style: "margin-top:14px" }, "Did the rep count and the score match what you did?"),
    askAccuracy && h("div", { class: "tabs" }, choices),
    comment, contact, send);
  return card;
}
function openFeedback() {
  fill($("feedback-body"),
    h("p", { class: "lead" }, "This is a test version. Tell us honestly what you think. Every answer is read."),
    feedbackForm({ jobId: jobIdFromLink(), exerciseId: state.exerciseId || "" }));
  show("feedback", { title: "Feedback" });
}

// ---- start --------------------------------------------------------------------------------
async function pollHealth() {
  try {
    const hl = await api("/api/health");
    const s = hl.machine_recognizer;
    $("status").textContent = s === "ready" ? "" : s === "error" ? "⚠ scanner offline" : "⏳ scanner loading…";
    $("offline-note").hidden = true;
    if (s !== "ready" && s !== "error") setTimeout(pollHealth, 3000);
    else if (STATIC) setTimeout(pollHealth, 30000);   // the server is someone's computer: it can go away
  } catch {
    if (STATIC) { $("status").textContent = "⚠ checker offline"; $("offline-note").hidden = false; }
    setTimeout(pollHealth, STATIC ? 15000 : 5000);
  }
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
  $("feedback-btn").addEventListener("click", openFeedback);
  $("photo-input").addEventListener("change", onPhoto);
  $("photo-input-gallery").addEventListener("change", onPhoto);
  try {
    // server.json exists only in the GitHub Pages copy. The time in the link stops an old copy being used.
    const res = await fetch("server.json?t=" + Date.now());
    if (res.ok) { API = String((await res.json()).server || "").replace(/\/+$/, ""); STATIC = true; }
  } catch {}
  try {
    state.catalog = STATIC ? await (await fetch("catalog.json")).json() : await api("/api/catalog");
    // Offer the Android app to Android browsers, but not inside the app itself ("wv" = WebView).
    $("apk-block").hidden = !(STATIC && /Android/i.test(navigator.userAgent) && !/; wv\)/.test(navigator.userAgent));
    renderHome();
    pollHealth();
    await openFromLink();
  } catch (e) {
    toast("Could not reach the server. Is it running?");
  }
}
start();
