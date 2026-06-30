/* =====================================================================
 *  Questionnaire flow (vanilla JS, no build step).
 *  Screens: landing -> intro -> loading -> question(loop) -> batchdone -> complete
 * ===================================================================== */
const cfg = window.STUDY_CONFIG;
const LS_KEY = "tillage_study_session_v1";

const state = {
  name: "",
  batch: [],        // [{pair_id, image_a, image_b, province, year}]
  idx: 0,
  answers: {},      // answers for the CURRENT pair: {q_a:"till", q_b:"no_till"}
  remaining: null,
};

const $ = (s) => document.querySelector(s);
const screens = ["landing", "intro", "loading", "question", "batchdone", "complete"];
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
  $("#btn-begin").addEventListener("click", beginBatch);
  $("#btn-next").addEventListener("click", onNext);
  $("#btn-more").addEventListener("click", beginBatch);
  $("#btn-stop").addEventListener("click", () => finish("stopped"));
  $("#btn-defs").addEventListener("click", () => $("#defs-modal").classList.remove("hidden"));
  $("#defs-close").addEventListener("click", () => $("#defs-modal").classList.add("hidden"));
  $("#name-input").addEventListener("keydown", (e) => { if (e.key === "Enter") onStart(); });

  // resume an in-progress batch if one exists
  const saved = safeParse(localStorage.getItem(LS_KEY));
  if (saved && saved.name && Array.isArray(saved.batch) && saved.idx < saved.batch.length) {
    state.name = saved.name; state.batch = saved.batch;
    state.idx = saved.idx; state.remaining = saved.remaining;
    $("#name-input").value = saved.name;
    setWho();
    renderPair();
    show("question");
    toast("Welcome back — resuming where you left off.");
    return;
  }
  if (saved && saved.name) $("#name-input").value = saved.name;
  show("landing");
}

function safeParse(s) { try { return JSON.parse(s); } catch (_) { return null; } }

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

/* ---------- render current pair ---------- */
function renderPair() {
  const p = state.batch[state.idx];
  if (!p) { onBatchEnd(); return; }
  state.answers = {};

  $("#img-a").src = p.image_a;
  $("#img-b").src = p.image_b;

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
    const legend = document.createElement("legend");
    legend.innerHTML = q.text;
    fs.appendChild(legend);
    const opts = document.createElement("div");
    opts.className = "opts";
    q.options.forEach((o) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "opt";
      b.textContent = o.label;
      b.addEventListener("click", () => {
        state.answers[q.id] = o.value;
        opts.querySelectorAll(".opt").forEach((x) => x.classList.remove("sel"));
        b.classList.add("sel");
        refreshNext();
      });
      opts.appendChild(b);
    });
    fs.appendChild(opts);
    wrap.appendChild(fs);
  });
  refreshNext();
}

function allAnswered() {
  return cfg.questions.every((q) => state.answers[q.id] !== undefined);
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
    const res = await Api.submit(state.name, p.pair_id, { ...state.answers });
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
    t.innerHTML = "All done — the study is complete! 🎉";
    b.textContent = "Every field has now been checked by enough people. "
      + "Thank you so much for contributing.";
  } else {
    t.innerHTML = "Thank you! 🙏";
    b.textContent = "Your answers are saved. You can close this tab, or come back any time "
      + "with the same link to do more.";
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
