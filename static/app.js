/* =====================================================================
 *  Questionnaire flow (vanilla JS, no build step).
 *  Screens: landing -> intro -> loading -> question(loop) -> batchdone -> complete
 * ===================================================================== */
const cfg = window.STUDY_CONFIG;
// Bump this version whenever the image set / paths change, so old saved
// sessions (with now-dead image URLs) are ignored instead of resumed.
const LS_KEY = "tillage_study_session_v3";
let _selfHealed = false;   // guard so a bad image triggers at most one reclaim

const state = {
  name: "",
  batch: [],        // [{pair_id, image_a, image_b, province, year}]
  idx: 0,
  answers: {},      // answers for the CURRENT pair: {q_a:"till", q_b:"no_till"}
  remaining: null,
};

const $ = (s) => document.querySelector(s);
const screens = ["landing", "intro", "examples", "loading", "question", "batchdone", "complete"];
function show(name) {
  screens.forEach((s) => $("#screen-" + s).classList.toggle("hidden", s !== name));
}

/* ---------- persistence (resume after refresh / partial progress) ---------- */
function persist() {
  localStorage.setItem(LS_KEY, JSON.stringify({
    name: state.name, batch: state.batch, idx: state.idx, remaining: state.remaining,
  }));
}
function clearPersist() { localStorage.removeItem(LS_KEY); }

/* ---------- init ---------- */
function init() {
  $("#app-title").textContent = cfg.title;
  $("#app-org").textContent = cfg.org;
  $("#intro-body").innerHTML = cfg.introHtml;
  $("#defs-body").innerHTML = cfg.quickRefHtml || cfg.introHtml;

  $("#btn-start").addEventListener("click", onStart);
  $("#btn-begin").addEventListener("click", () => show("examples"));
  $("#btn-examples-start").addEventListener("click", beginBatch);
  $("#btn-next").addEventListener("click", onNext);
  $("#btn-more").addEventListener("click", beginBatch);
  $("#btn-stop").addEventListener("click", () => finish("stopped"));
  $("#btn-defs").addEventListener("click", () => $("#defs-modal").classList.remove("hidden"));
  $("#defs-close").addEventListener("click", () => $("#defs-modal").classList.add("hidden"));
  $("#name-input").addEventListener("keydown", (e) => { if (e.key === "Enter") onStart(); });

  // fullscreen montage viewer (essential on a phone, handy on a laptop)
  $("#img-a").addEventListener("click", openZoom);
  $("#btn-zoom").addEventListener("click", (e) => { e.stopPropagation(); openZoom(); });
  $("#zoom-close").addEventListener("click", closeZoom);
  $("#zoom-modal").addEventListener("click", (e) => { if (e.target.id === "zoom-scroll") closeZoom(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeZoom(); });

  renderExamples();   // build the worked-examples sheet
  loadProgress();     // populate the landing-page progress panel

  // Always start from the homepage. We only remember the name for convenience;
  // we never resume into a mid-batch question screen.
  const saved = safeParse(localStorage.getItem(LS_KEY));
  if (saved && saved.name) $("#name-input").value = saved.name;
  show("landing");
}

/* ---------- worked-examples sheet ---------- */
function renderExamples() {
  const ex = cfg.examples;
  if (!ex) return;
  $("#examples-intro").innerHTML = ex.intro || "";

  // red development-only banner (drop `devNote` from config to hide it)
  const dev = $("#examples-devnote");
  dev.textContent = ex.devNote || "";
  dev.classList.toggle("hidden", !ex.devNote);

  // what the labeler should actually look for
  const note = $("#examples-note");
  note.innerHTML = ex.note || "";
  note.classList.toggle("hidden", !ex.note);

  const grid = $("#examples-grid");
  grid.innerHTML = "";
  (ex.items || []).forEach((it) => {
    const card = document.createElement("div");
    card.className = "example";
    const fig = document.createElement("figure");
    fig.className = "example-img";
    const img = document.createElement("img");
    img.src = it.src; img.alt = it.label + " field example"; img.loading = "lazy";
    img.addEventListener("click", () => openZoom(it.src));   // same viewer as the task screen
    const badge = document.createElement("span");
    const isNo = /no/i.test(it.label);
    badge.className = "example-badge " + (isNo ? "notill" : "till");
    badge.textContent = it.label;
    fig.appendChild(img); fig.appendChild(badge);
    const ul = document.createElement("ul");
    ul.className = "example-points";
    (it.points || []).forEach((pt) => {
      const li = document.createElement("li"); li.textContent = pt; ul.appendChild(li);
    });
    card.appendChild(fig); card.appendChild(ul);
    grid.appendChild(card);
  });
}

function safeParse(s) { try { return JSON.parse(s); } catch (_) { return null; } }

/* ---------- technical context sent with each answer ----------
 * Disclosed to participants on the landing page. The client IP is NOT here —
 * a browser cannot read its own public IP; the server records it on arrival.
 * Precise GPS is deliberately not collected: navigator.geolocation always
 * raises a permission prompt, so it can't be silent. Coarse location can be
 * derived from the IP offline during analysis. */
function clientMeta() {
  const n = navigator;
  const d = new Date();
  try {
    return {
      user_agent: n.userAgent || null,
      platform: (n.userAgentData && n.userAgentData.platform) || n.platform || null,
      language: n.language || null,
      languages: (n.languages || []).slice(0, 3),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || null,
      tz_offset_min: d.getTimezoneOffset(),
      client_time: d.toISOString(),          // hours+dates, client clock
      screen: `${screen.width}x${screen.height}`,
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      pixel_ratio: window.devicePixelRatio || null,
      cpu_cores: n.hardwareConcurrency || null,
      memory_gb: n.deviceMemory || null,
      touch: (n.maxTouchPoints || 0) > 0,
    };
  } catch (_) {
    return { client_time: new Date().toISOString() };
  }
}

/* ---------- landing-page progress panel ---------- */
async function loadProgress() {
  const g = cfg.goal || {};
  const seasons = (g.seasonEnd - g.seasonStart + 1) || 1;
  const goalFields = (g.provinces || 0) * seasons * (g.fieldsPerSeasonPerProvince || 0);
  const goalCells = (g.provinces || 0) * seasons;
  const fmt = (n) => Number(n || 0).toLocaleString();
  try {
    const p = await Api.progress();
    // one field per screen (imagesPerScreen:1), or two in legacy pair mode
    const classified = (p.pairs_done || 0) * (cfg.imagesPerScreen || 2);
    const remaining = Math.max(0, goalFields - classified);
    const pct = goalFields ? Math.round((classified / goalFields) * 100) : 0;
    $("#pp-contributors").textContent = fmt(p.contributors);
    $("#pp-classified").textContent = fmt(classified);
    $("#pp-remaining").textContent = fmt(remaining);
    $("#pp-cells").textContent = `${fmt(p.cells_done)}/${fmt(goalCells)}`;
    $("#pp-bar-fill").style.width = pct + "%";
    const parts = [`${fmt(classified)} of ${fmt(goalFields)} fields classified`, `${pct}%`];
    if (seasons > 1 || g.provinces > 1) {   // only spell out the grid when there is one
      parts.push(`goal: ${g.fieldsPerSeasonPerProvince} fields × ${seasons} season(s) × ${g.provinces} province(s)`);
    }
    $("#pp-goal").textContent = parts.join(" · ");
  } catch (e) {
    $("#pp-goal").textContent = "Live progress will appear once the study database is connected.";
  }
}

/* ---------- landing -> intro ---------- */
function onStart() {
  const name = $("#name-input").value.trim();
  if (name.length < 2) { toast("Please enter your name first."); $("#name-input").focus(); return; }
  state.name = name;
  setWho();
  show("intro");
}
function setWho() {
  $("#who-label").textContent = "Labeler: " + state.name;
  $("#who-label").classList.remove("hidden");
  $("#btn-defs").classList.remove("hidden");
}

/* ---------- claim a batch ---------- */
async function beginBatch() {
  show("loading");
  $("#loading-text").textContent = "Finding fields for you to check…";
  try {
    const res = await Api.claim(state.name);
    state.batch = res.pairs || [];
    state.remaining = res.remaining ?? null;
    state.idx = 0;
    persist();
    if (state.batch.length === 0) { finish("none_left"); return; }
    renderPair();
    show("question");
  } catch (e) {
    show("intro");
    toast("Could not load a batch: " + e.message);
  }
}

/* If an image fails to load (e.g. a stale saved session points at a URL that
   no longer exists), discard the session and pull a fresh batch — once. */
function onImageError() {
  if (_selfHealed) return;
  _selfHealed = true;
  clearPersist();
  toast("Your saved session was out of date — loading fresh images…");
  beginBatch();
}

/* ---------- fullscreen montage viewer ----------
 * The montage is 1305x695. Fit to a phone's width it becomes a ~180px strip and
 * each of the 8 panels is unreadable, so tapping opens it at a legible size that
 * can be scrolled and pinch-zoomed. */
function openZoom(src) {
  if (typeof src !== "string") {                 // called from a click handler
    const p = state.batch[state.idx];
    if (!p) return;
    src = p.image_a;
  }
  $("#zoom-img").src = src;
  $("#zoom-modal").classList.remove("hidden");
  // Always open at panel A. Without this the container keeps the pan position from
  // the previous field, so field 2 opens already scrolled to wherever you left
  // field 1 — and the labeler may never notice A/E are off-screen to the left.
  $("#zoom-scroll").scrollLeft = 0;
  $("#zoom-scroll").scrollTop = 0;
  document.body.style.overflow = "hidden";
}
function closeZoom() {
  $("#zoom-modal").classList.add("hidden");
  document.body.style.overflow = "";
}

/* ---------- render current pair ---------- */
function renderPair() {
  const p = state.batch[state.idx];
  if (!p) { onBatchEnd(); return; }
  state.answers = {};

  // One montage per screen (imagesPerScreen: 1) or the legacy A/B pair (2).
  const single = (cfg.imagesPerScreen || 2) === 1;
  const ia = $("#img-a"), ib = $("#img-b");
  $("#pair-grid").classList.toggle("single", single);
  $("#card-b").classList.toggle("hidden", single);
  $("#tag-a").classList.toggle("hidden", single);   // no A/B labels when there's one image
  $("#btn-zoom").classList.toggle("hidden", !single);   // zoom only applies to the montage
  ia.onerror = onImageError;                        // self-heal if a URL is dead/stale
  ia.src = p.image_a;
  if (!single) {
    ib.onerror = onImageError;
    ib.src = p.image_b;
  }

  const total = state.batch.length;
  $("#qcount").textContent = `${state.idx + 1} / ${total}`;
  $("#qbar").style.width = `${(state.idx / total) * 100}%`;
  $("#save-status").textContent = "";
  $("#save-status").className = "save-status";

  // build the questions from config
  const wrap = $("#questions");
  wrap.innerHTML = "";
  cfg.questions.forEach((q) => {
    const fs = document.createElement("fieldset");
    fs.className = "q";
    fs.dataset.qid = q.id;
    const legend = document.createElement("legend");
    legend.innerHTML = q.text;
    fs.appendChild(legend);
    const opts = document.createElement("div");
    // `layout: "grid4"` lays the buttons out 4-across so they mirror the montage panels.
    opts.className = "opts" + (q.layout ? " opts-" + q.layout : "");
    q.options.forEach((o) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "opt" + (o.sub ? " opt-stack" : "");
      if (o.sub) {
        const big = document.createElement("b");
        big.className = "opt-key";
        big.textContent = o.label;
        const small = document.createElement("span");
        small.className = "opt-sub";
        small.textContent = o.sub;
        b.appendChild(big); b.appendChild(small);
      } else {
        b.textContent = o.label;
      }
      b.addEventListener("click", () => {
        state.answers[q.id] = o.value;
        opts.querySelectorAll(".opt").forEach((x) => x.classList.remove("sel"));
        b.classList.add("sel");
        applyConditionals();
        refreshNext();
      });
      opts.appendChild(b);
    });
    fs.appendChild(opts);
    wrap.appendChild(fs);
  });
  applyConditionals();
  refreshNext();
}

/* A question with `showIf` only appears once its trigger answer is given. */
function isVisible(q) {
  if (!q.showIf) return true;
  return state.answers[q.showIf.question] === q.showIf.equals;
}

function applyConditionals() {
  cfg.questions.forEach((q) => {
    if (!q.showIf) return;
    const fs = $(`fieldset.q[data-qid="${q.id}"]`);
    if (!fs) return;
    const vis = isVisible(q);
    fs.classList.toggle("hidden", !vis);
    if (!vis && state.answers[q.id] !== undefined) {
      delete state.answers[q.id];      // don't keep an answer to a hidden question
      fs.querySelectorAll(".opt").forEach((x) => x.classList.remove("sel"));
    }
  });
}

function allAnswered() {
  return cfg.questions.filter(isVisible).every((q) => state.answers[q.id] !== undefined);
}
function refreshNext() {
  $("#btn-next").disabled = cfg.requireAllAnswers && !allAnswered();
}

/* ---------- submit + advance (partial save happens here) ---------- */
async function onNext() {
  if (cfg.requireAllAnswers && !allAnswered()) return;
  const p = state.batch[state.idx];
  const btn = $("#btn-next");
  btn.disabled = true;
  setSave("Saving…", "");

  try {
    const res = await Api.submit(state.name, p.pair_id, { ...state.answers }, clientMeta());
    if (res.ok === false) {
      if (res.reason === "pair_full") {
        // someone else completed it meanwhile — skip quietly
        setSave("That field was just completed by others — skipping.", "");
      } else {
        setSave("Save problem: " + (res.reason || "unknown"), "err");
        btn.disabled = false; return;
      }
    } else {
      setSave("Saved ✓", "ok");
    }
  } catch (e) {
    setSave("Network error — tap Next to retry.", "err");
    btn.disabled = false; return;
  }

  state.idx += 1;
  persist();
  if (state.idx >= state.batch.length) onBatchEnd();
  else renderPair();
}

function setSave(msg, cls) {
  const el = $("#save-status");
  el.textContent = msg;
  el.className = "save-status" + (cls ? " " + cls : "");
}

/* ---------- end of a batch ---------- */
function onBatchEnd() {
  $("#qbar").style.width = "100%";
  clearPersist();
  const rem = state.remaining;
  let txt = `You labeled ${state.batch.length} pairs. Thank you!`;
  if (rem !== null && rem !== undefined) {
    const left = Math.max(0, rem - state.batch.length);
    txt += left > 0
      ? ` There are still about ${left} pairs that need a look.`
      : " That may have been the last of them.";
    if (left === 0) { finish("done_all"); return; }
  }
  $("#batchdone-text").textContent = txt;
  show("batchdone");
}

/* ---------- finish ---------- */
function finish(why) {
  clearPersist();
  const t = $("#complete-title"), b = $("#complete-text");
  if (why === "none_left" || why === "done_all") {
    t.textContent = "The study is complete";
    b.textContent = "Every field has now been reviewed. Thank you for contributing — "
      + "your responses make a real difference to the analysis.";
  } else {
    t.textContent = "Thank you";
    b.textContent = "Your responses are saved. You can close this tab, or return any time "
      + "with the same link to continue.";
  }
  show("complete");
}

/* ---------- toast ---------- */
let toastTimer;
function toast(msg) {
  const el = $("#toast");
  el.textContent = msg; el.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.add("hidden"), 2200);
}

init();
