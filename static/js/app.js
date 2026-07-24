/* =========================================================================
   app.js — Paper Trail. Editorial UI controller.
   Screens: Today, Queue (editorial index + load more), Progress, Settings.
   Keeps all features (search, filters, notes, review, fetch, request, reader).
   ========================================================================= */

const api = {
  async get(p) { const r = await fetch(p); if (!r.ok) throw new Error(`GET ${p} ${r.status}`); return r.json(); },
  async post(p, b) {
    const r = await fetch(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: b ? JSON.stringify(b) : null });
    if (!r.ok) { let d = await r.text(); try { d = JSON.parse(d).detail || d; } catch (e) {} throw new Error(d || `POST ${p} ${r.status}`); }
    return r.json();
  },
};
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);
function esc(s) { return String(s ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"); }
let toastTimer = null;
function toast(m) { const e = $("#toast"); e.textContent = m; e.classList.remove("hidden"); clearTimeout(toastTimer); toastTimer = setTimeout(() => e.classList.add("hidden"), 2600); }
const pad = (n) => String(n).padStart(2, "0");
const dots = (d) => "●".repeat(Math.max(0, Math.min(5, d))) + "○".repeat(5 - Math.max(0, Math.min(5, d)));

/* ---- Lucide icons (inlined, no runtime dependency) ---------------------- */
const ICONS = {
  check: '<polyline points="20 6 9 17 4 12"/>',
  "arrow-right": '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  sliders: '<line x1="4" y1="21" x2="4" y2="14"/><line x1="4" y1="10" x2="4" y2="3"/><line x1="12" y1="21" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="3"/><line x1="20" y1="21" x2="20" y2="16"/><line x1="20" y1="12" x2="20" y2="3"/><line x1="1" y1="14" x2="7" y2="14"/><line x1="9" y1="8" x2="15" y2="8"/><line x1="17" y1="16" x2="23" y2="16"/>',
  x: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
  "chevron-right": '<polyline points="9 18 15 12 9 6"/>',
};
function icon(name, size = 14) {
  return `<svg class="ic" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name] || ""}</svg>`;
}
function hydrateIcons(root = document) {
  root.querySelectorAll("[data-ic]").forEach((el) => { el.innerHTML = icon(el.getAttribute("data-ic")); el.removeAttribute("data-ic"); });
}

/* ---- Theme -------------------------------------------------------------- */
function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", theme === "dark" ? "#131211" : "#FDFCFA");
  localStorage.setItem("pt-theme", theme);
  $$("#theme-seg .seg-btn").forEach((b) => b.classList.toggle("active", b.dataset.themeVal === theme));
}

/* ---- Navigation --------------------------------------------------------- */
const VIEWS = ["today", "queue", "progress", "settings"];
function showView(name) {
  VIEWS.forEach((v) => $(`#view-${v}`).classList.toggle("hidden", v !== name));
  $$(".nav-btn").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name === "today") loadToday();
  if (name === "queue") loadQueue(true);
  if (name === "progress") loadProgress();
  if (name === "settings") loadSettings();
}
$$(".nav-btn").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));

/* =========================================================================
   TODAY
   ========================================================================= */
let todayPaper = null;
let todayBusy = false;

/* Render the Today screen from a payload (shared by initial load + action buttons). */
function renderToday(d) {
  todayPaper = d.paper;
  const body = $("#today-body"), empty = $("#today-empty");
  if (!d.paper) {
    body.classList.add("hidden");
    empty.classList.remove("hidden");
    empty.textContent = "You're all caught up — no papers left. Fetch new papers from the Queue.";
    return;
  }
  body.classList.remove("hidden"); empty.classList.add("hidden");

  $("#today-daymeta").textContent = `${(d.weekday || "").toUpperCase()} · DAY ${d.day_number}`;
  const streak = $("#today-streak");
  if (d.streak > 0) { streak.textContent = `${d.streak} day streak`; streak.classList.remove("hidden"); }
  else streak.classList.add("hidden");

  const p = d.paper;
  const posBit = d.total ? ` · ${pad(d.position)} OF ${pad(d.total)}` : "";
  $("#today-label").textContent = `TODAY'S PAPER${posBit}`;
  $("#today-title").textContent = p.title;
  $("#today-idea").textContent = p.core_idea || "";
  $("#today-diff").textContent = dots(p.difficulty || 3);
  $("#today-time").textContent = `${p.est_reading_minutes || "?"} MIN`;
  $("#today-math").textContent = p.skip_the_math ? "SKIPPABLE" : "REQUIRED";

  const bo = (p.builds_on_papers || []);
  const un = (p.unlocks || []);
  $("#today-buildson").innerHTML = icon("check") +
    ` <span>BUILDS ON — ${bo.length ? esc(bo.join(", ")) : "foundational, no prerequisites"}</span>`;
  $("#today-buildson").classList.toggle("empty", bo.length === 0);
  $("#today-unlocks").innerHTML = icon("arrow-right") +
    ` <span>UNLOCKS — ${un.length ? esc(un.join(", ")) : "nothing yet"}</span>`;
  $("#today-unlocks").classList.toggle("empty", un.length === 0);

  $("#today-queued").textContent = `${d.queued_this_week} more queued this week`;
}

async function loadToday() {
  try { renderToday(await api.get("/api/today")); }
  catch (err) { toast("Couldn't load today."); console.error(err); }
}

/* Disable the Today buttons + show a "working" label while a request is in flight. */
function setTodayBusy(on, clickedSel, label) {
  todayBusy = on;
  ["#today-start", "#today-toohard", "#today-alreadyread"].forEach((s) => ($(s).disabled = on));
  if (clickedSel) {
    const b = $(clickedSel);
    if (on) { b.dataset.orig = b.textContent; b.textContent = label; }
    else if (b.dataset.orig) { b.textContent = b.dataset.orig; delete b.dataset.orig; }
  }
}

$("#today-start").addEventListener("click", () => { if (todayPaper && !todayBusy) window.Tutor.open(todayPaper); });
$("#today-seeall").addEventListener("click", () => showView("queue"));

$("#today-toohard").addEventListener("click", async () => {
  if (!todayPaper || todayBusy) return;
  setTodayBusy(true, "#today-toohard", "Finding an easier one…");
  try {
    // The endpoint already returns the next paper — render it directly (one round trip).
    const d = await api.post(`/api/papers/${todayPaper.id}/too-hard`);
    renderToday(d);
    toast("Skipped — here's an easier paper");
  } catch (err) { toast("Couldn't skip that one. Try again."); console.error(err); }
  finally { setTodayBusy(false, "#today-toohard"); }
});

$("#today-alreadyread").addEventListener("click", async () => {
  if (!todayPaper || todayBusy) return;
  setTodayBusy(true, "#today-alreadyread", "Updating…");
  try {
    await api.post(`/api/papers/${todayPaper.id}/read`);
    await loadToday();
    loadProgress();
    toast("Marked as read");
  } catch (err) { toast("Couldn't update. Try again."); console.error(err); }
  finally { setTodayBusy(false, "#today-alreadyread"); }
});

/* =========================================================================
   QUEUE (editorial index)
   ========================================================================= */
const PAGE_SIZE = 10;
let qPage = 1;

function feedParams(page) {
  const p = new URLSearchParams();
  const q = $("#search").value.trim();
  const m = { year: $("#f-year").value, topic: $("#f-topic").value, max_difficulty: $("#f-diff").value, recency: $("#f-recency").value };
  if (q) p.set("q", q);
  for (const [k, v] of Object.entries(m)) if (v !== "") p.set(k, v);
  if ($("#f-status").value !== "unread") p.set("status", $("#f-status").value);
  if ($("#f-sort").value !== "recommended") p.set("sort", $("#f-sort").value);
  p.set("page", page); p.set("page_size", PAGE_SIZE);
  return p;
}
function filtersActive() {
  return $("#search").value.trim() !== "" || $("#f-year").value !== "" ||
    $("#f-topic").value !== "" || $("#f-diff").value !== "" || $("#f-recency").value !== "" ||
    $("#f-status").value !== "unread" || $("#f-sort").value !== "recommended";
}

async function populateFilters() {
  try {
    const { topics, years } = await api.get("/api/filters");
    const tp = $("#f-topic"), y = $("#f-year");
    tp.length = 1; y.length = 1;
    (years || []).forEach((x) => y.add(new Option(x, x)));
    topics.forEach((x) => tp.add(new Option(x, x)));
  } catch (err) { console.error(err); }
}

/* One editorial row. startExpanded shows the idea + actions inline. */
function renderRow(paper, rankLabel, startExpanded) {
  const row = document.createElement("div");
  row.className = "row";
  const d = paper.difficulty || 3;
  const meta = `${dots(d)}<span class="dot-sep">${paper.est_reading_minutes || "?"} MIN</span>${paper.topic ? `<span class="dot-sep">${esc(String(paper.topic).toUpperCase())}</span>` : ""}`;
  row.innerHTML = `
    <div class="row-rank">${rankLabel}</div>
    <div class="row-body">
      <h3 class="row-title"><a href="${esc(paper.abs_url || paper.pdf_url || "#")}" target="_blank" rel="noopener">${esc(paper.title)}</a></h3>
      <div class="row-meta">${meta}</div>
      <div class="row-expand" style="display:none"></div>
    </div>`;
  row.querySelector(".row-title a").addEventListener("click", (e) => e.stopPropagation());

  const wrap = row.querySelector(".row-expand");
  let filled = false;
  function fill() {
    filled = true;
    const hasNotes = (paper.notes || "").trim().length > 0;
    wrap.innerHTML = `
      <p class="row-idea">${esc(paper.core_idea || "")}</p>
      <div class="row-actions">
        <button class="btn btn-outline read-btn">Read</button>
        <button class="btn btn-filled study-btn">Study</button>
      </div>
      <div class="row-sub">
        <button class="check-toggle ${paper.status === "read" ? "done" : ""}"><span class="check-box"></span>${paper.status === "read" ? "Read" : "Mark read"}</button>
        <button class="notes-btn ${hasNotes ? "has-notes" : ""}">Notes</button>
        <a class="pdf-link" href="${esc(paper.pdf_url || paper.abs_url || "#")}" target="_blank" rel="noopener">PDF</a>
      </div>`;
    wrap.querySelector(".study-btn").addEventListener("click", (e) => { e.stopPropagation(); window.Tutor.open(paper); });
    wrap.querySelector(".read-btn").addEventListener("click", (e) => { e.stopPropagation(); openReader(paper); });
    wrap.querySelector(".notes-btn").addEventListener("click", (e) => { e.stopPropagation(); openNotes(paper); });
    wrap.querySelector(".pdf-link").addEventListener("click", (e) => e.stopPropagation());
    wrap.querySelector(".check-toggle").addEventListener("click", (e) => { e.stopPropagation(); toggleRead(paper); });
  }
  let open = false;
  function setOpen(v) { open = v; if (v && !filled) fill(); wrap.style.display = v ? "block" : "none"; }
  if (startExpanded && !paper.locked) setOpen(true);

  row.addEventListener("click", () => setOpen(!open));
  return row;
}

async function toggleRead(paper) {
  const nowDone = paper.status !== "read";
  try {
    await api.post(`/api/papers/${paper.id}/${nowDone ? "read" : "unread"}`);
    toast(nowDone ? "Marked as read" : "Moved back to your queue");
    loadQueue(true); loadProgress();
  } catch (err) { toast("Couldn't update that paper."); console.error(err); }
}

let qReqId = 0;
async function loadQueue(reset) {
  const mine = ++qReqId;
  if (reset) qPage = 1;
  try {
    const calls = [api.get("/api/feed?" + feedParams(qPage).toString())];
    if (reset) { calls.push(api.get("/api/reviews/due").catch(() => ({ due: [] }))); calls.push(api.get("/api/progress").catch(() => null)); }
    const [data, reviews, prog] = await Promise.all(calls);
    if (mine !== qReqId) return;

    if (reset) {
      // Header numbers.
      if (prog) {
        $("#queue-subline").textContent = `${prog.papers_total} PAPERS · ${prog.papers_read} READ`;
        const pct = prog.percent != null ? prog.percent : 0;
        $("#queue-pbar").style.width = pct + "%"; $("#queue-pct").textContent = pct + "%";
      }
      // Due-for-review callout (page-independent). No separate "new" section —
      // every paper lives in the one list below.
      renderList("#review-section", "#review-list", "#review-count", reviews ? reviews.due : []);
      $("#queue-list").innerHTML = "";
      $("#result-count").textContent = filtersActive() ? `${data.count} matches` : "";
      $("#clear-filters").classList.toggle("hidden", !filtersActive());
    }

    const list = $("#queue-list");
    if (reset && (!data.queue || !data.queue.length)) {
      list.innerHTML = `<p class="mono muted" style="padding:16px 0">${filtersActive() ? "No papers match your filters." : "No papers yet — fetch or add one above."}</p>`;
    } else {
      data.queue.forEach((p, i) => {
        const rank = (qPage - 1) * PAGE_SIZE + i + 1;
        list.appendChild(renderRow(p, pad(rank), false));  // uniform name list; tap to expand
      });
    }
    // Load more.
    const more = $("#load-more");
    if (data.page < data.pages) { more.classList.remove("hidden"); } else { more.classList.add("hidden"); }
  } catch (err) { toast("Couldn't load the queue."); console.error(err); }
}

function renderList(sectionSel, listSel, countSel, papers) {
  const sec = $(sectionSel), list = $(listSel);
  list.innerHTML = "";
  if (papers && papers.length) {
    papers.forEach((p, i) => list.appendChild(renderRow(p, pad(i + 1), false)));
    if (countSel) $(countSel).textContent = ` — ${papers.length}`;
    sec.classList.remove("hidden");
  } else sec.classList.add("hidden");
}

$("#load-more").addEventListener("click", () => { qPage++; loadQueue(false); });

/* Collapsible panel + filter wiring */
function togglePanel(focusSearch) {
  const panel = $("#queue-panel");
  const willShow = panel.classList.contains("hidden");
  panel.classList.toggle("hidden");
  if (willShow && focusSearch) $("#search").focus();
}
$("#queue-search-toggle").addEventListener("click", () => togglePanel(true));
$("#queue-filter-toggle").addEventListener("click", () => togglePanel(false));

let searchTimer = null;
$("#search").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => loadQueue(true), 250); });
["#f-sort", "#f-status", "#f-recency", "#f-year", "#f-topic", "#f-diff"].forEach((s) =>
  $(s).addEventListener("change", () => loadQueue(true)));
$("#clear-filters").addEventListener("click", () => {
  ["#search", "#f-year", "#f-topic", "#f-diff", "#f-recency"].forEach((s) => ($(s).value = ""));
  $("#f-status").value = "unread"; $("#f-sort").value = "recommended"; loadQueue(true);
});

/* ---- Request a paper ---------------------------------------------------- */
$("#request-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = $("#request-input").value.trim(); if (!query) return;
  const btn = $("#request-btn"); btn.disabled = true; btn.textContent = "Adding…";
  try {
    const res = await api.post("/api/papers/request", { query });
    toast(res.added ? "Paper added" : (res.detail || "Already in your list"));
    $("#request-input").value = ""; await populateFilters(); loadQueue(true); loadToday();
  } catch (err) { toast(String(err.message || err).slice(0, 80)); }
  finally { btn.disabled = false; btn.textContent = "Add"; }
});

/* ---- Fetch new papers --------------------------------------------------- */
$("#fetch-btn").addEventListener("click", async () => {
  const btn = $("#fetch-btn");
  try {
    const res = await api.post("/api/ingest/run", {});
    if (!res.started) { toast(res.detail || "Already running"); return; }
    btn.disabled = true; btn.textContent = "Fetching…"; toast("Fetching new papers…");
    const timer = setInterval(async () => {
      try {
        const s = await api.get("/api/ingest/status");
        if (!s.running) { clearInterval(timer); btn.disabled = false; btn.textContent = "Fetch new papers"; toast(s.message || "Done"); await populateFilters(); loadQueue(true); loadToday(); }
      } catch (e) { clearInterval(timer); btn.disabled = false; btn.textContent = "Fetch new papers"; }
    }, 2000);
  } catch (err) { toast("Couldn't start fetch."); console.error(err); }
});

/* =========================================================================
   PROGRESS
   ========================================================================= */
async function loadProgress() {
  try {
    const [p, hist] = await Promise.all([api.get("/api/progress"), api.get("/api/history")]);
    $("#stat-read").textContent = p.papers_read;
    $("#stat-streak").textContent = p.streak;
    $("#stat-avg").textContent = hist.average_score != null ? hist.average_score : "–";
    $("#stat-pct").textContent = (p.percent != null ? p.percent : 0) + "%";

    const pct = p.percent != null ? p.percent : 0;
    $("#overall-fill").style.width = pct + "%";
    $("#overall-count").textContent = `${p.papers_read}/${p.papers_total}`;
    renderHistory(hist.sessions);
  } catch (err) { console.error(err); }
}
function renderHistory(sessions) {
  const wrap = $("#history-list"); wrap.innerHTML = "";
  if (!sessions || !sessions.length) { wrap.innerHTML = `<p class="mono muted" style="padding:14px 0">No study sessions yet.</p>`; return; }
  sessions.slice(0, 30).forEach((s) => {
    const item = document.createElement("div"); item.className = "history-item";
    const date = s.created_at ? new Date(s.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }).toUpperCase() : "";
    const recap = (s.recap || []).map((b) => `<div>${esc(b)}</div>`).join("");
    item.innerHTML = `
      <div class="history-head"><span class="history-title">${esc(s.title)}</span><span class="history-score">${s.score != null ? dots(s.score) : "—"}</span></div>
      <div class="history-sub">${date}</div>
      ${recap ? `<div class="history-recap collapsed">${recap}</div>` : ""}`;
    const r = item.querySelector(".history-recap");
    if (r) item.querySelector(".history-head").addEventListener("click", () => r.classList.toggle("collapsed"));
    wrap.appendChild(item);
  });
}

/* =========================================================================
   READER + NOTES
   ========================================================================= */
function openReader(paper) {
  const ext = paper.pdf_url || paper.abs_url; if (!ext) { toast("No link for this paper."); return; }
  $("#reader-title").textContent = paper.title; $("#reader-newtab").href = ext;
  $("#reader-frame").src = `/api/papers/${paper.id}/pdf`;
  $("#reader-overlay").classList.remove("hidden"); document.body.style.overflow = "hidden";
}
$("#reader-close").addEventListener("click", () => { $("#reader-overlay").classList.add("hidden"); $("#reader-frame").src = "about:blank"; document.body.style.overflow = ""; });

let notesPaper = null;
function openNotes(paper) {
  notesPaper = paper; $("#notes-paper-title").textContent = paper.title; $("#notes-text").value = paper.notes || "";
  $("#notes-modal").classList.remove("hidden"); $("#notes-text").focus();
}
$("#notes-close").addEventListener("click", () => { $("#notes-modal").classList.add("hidden"); notesPaper = null; });
$("#notes-modal").addEventListener("click", (e) => { if (e.target.id === "notes-modal") { $("#notes-modal").classList.add("hidden"); notesPaper = null; } });
$("#notes-save").addEventListener("click", async () => {
  if (!notesPaper) return;
  try { await api.post(`/api/papers/${notesPaper.id}/notes`, { notes: $("#notes-text").value }); notesPaper.notes = $("#notes-text").value; toast("Notes saved"); $("#notes-modal").classList.add("hidden"); loadQueue(true); }
  catch (err) { toast("Couldn't save notes."); console.error(err); }
});

/* =========================================================================
   SETTINGS
   ========================================================================= */
function fillHours(sel, selected) { sel.innerHTML = ""; for (let h = 0; h < 24; h++) { const o = document.createElement("option"); o.value = h; o.textContent = `${pad(h)}:00`; if (h === selected) o.selected = true; sel.appendChild(o); } }
async function loadSettings() {
  try {
    const s = await api.get("/api/settings");
    $("#notif-toggle").checked = !!s.notifications_enabled;
    $("#notif-details").classList.toggle("hidden", !s.notifications_enabled);
    $("#notif-frequency").value = String(s.notif_frequency || 3);
    fillHours($("#quiet-start"), s.quiet_start ?? 22); fillHours($("#quiet-end"), s.quiet_end ?? 8);
    window.Push?.describePlatform(s.push_available);
  } catch (err) { console.error(err); }
}
async function saveSetting(patch) { try { await api.post("/api/settings", patch); } catch (err) { toast("Couldn't save that."); console.error(err); } }
$$("#theme-seg .seg-btn").forEach((b) => b.addEventListener("click", () => { applyTheme(b.dataset.themeVal); saveSetting({ theme: b.dataset.themeVal }); }));
$("#notif-frequency").addEventListener("change", (e) => saveSetting({ notif_frequency: Number(e.target.value) }));
$("#quiet-start").addEventListener("change", (e) => saveSetting({ quiet_start: Number(e.target.value) }));
$("#quiet-end").addEventListener("change", (e) => saveSetting({ quiet_end: Number(e.target.value) }));

/* ---- Startup ------------------------------------------------------------ */
(function init() {
  hydrateIcons();
  applyTheme(localStorage.getItem("pt-theme") || "light");
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/service-worker.js").catch((e) => console.warn("SW:", e));
  populateFilters();
  showView("today");
})();

/* Shared with tutor.js / push.js. loadFeed refreshes Today + Queue. */
window.PT = { api, toast, esc, loadProgress, saveSetting, loadFeed: () => { loadToday(); loadQueue(true); } };
