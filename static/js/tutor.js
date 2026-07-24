/* =========================================================================
   tutor.js — Tutor Mode: the guided, chat-like study flow.

   Flow for one paper:
     1. Show title + abstract.
     2. Ask the learner to summarize the core idea (free text).
     3. Grade it (score + right + missed + correction).
     4. Ask 2-3 progressively deeper Socratic follow-ups.
     5. Show a 3-bullet recap; mark the paper read; save the session.

   The browser holds the conversation transcript and sends it to the server on
   each turn (the server is stateless). Exposed as window.Tutor.
   ========================================================================= */

(function () {
  const { api, esc, toast, loadFeed, loadProgress } = window.PT;

  const overlay = document.getElementById("tutor-overlay");
  const thread = document.getElementById("tutor-thread");
  const form = document.getElementById("tutor-form");
  const input = document.getElementById("tutor-input");
  const sendBtn = document.getElementById("tutor-send");
  const titleEl = document.getElementById("tutor-paper-title");

  // Session state (reset every time we open a paper).
  let paper = null;
  let transcript = [];
  let phase = "idle"; // idle | summary | followup | done
  let score = null;
  let busy = false;

  /* Convert our light markdown (**bold**) into safe HTML. */
  function md(text) {
    return esc(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  /* Add a hairline-separated turn. role = "tutor" | "user". */
  function addBubble(text, role, extraClass = "") {
    const label = role === "user" ? "You" : "Tutor";
    const t = document.createElement("div");
    t.className = `turn turn-${role} ${extraClass}`.trim();
    t.innerHTML = `<div class="turn-who">${label}</div><div class="turn-text">${md(text)}</div>`;
    thread.appendChild(t);
    scrollDown();
    return t;
  }

  /* Add the abstract block (display only, not part of transcript). */
  function addAbstractBubble(p) {
    const abstract = p.abstract || "(No abstract available for this paper.)";
    const t = document.createElement("div");
    t.className = "turn abstract";
    t.innerHTML = `<div class="turn-who">Abstract</div><div class="turn-text">${esc(abstract)}</div>`;
    thread.appendChild(t);
    scrollDown();
  }

  /* Typing indicator (three dots) while we wait on the model. */
  function showTyping() {
    const t = document.createElement("div");
    t.className = "typing";
    t.id = "typing-indicator";
    t.innerHTML = "<span></span><span></span><span></span>";
    thread.appendChild(t);
    scrollDown();
  }
  function hideTyping() {
    document.getElementById("typing-indicator")?.remove();
  }

  function scrollDown() {
    // Wait a tick so the new node is measured before scrolling.
    requestAnimationFrame(() => {
      thread.scrollTop = thread.scrollHeight;
    });
  }

  function setBusy(state) {
    busy = state;
    sendBtn.disabled = state;
    input.disabled = state;
  }

  /* ---- Public: open Tutor Mode for a paper ------------------------------ */
  async function open(p) {
    paper = p;
    transcript = [];
    score = null;
    phase = "summary";
    thread.innerHTML = "";
    titleEl.textContent = p.title;
    overlay.classList.remove("hidden");
    document.body.style.overflow = "hidden";

    // Remove any leftover "back to feed" button.
    removeDoneActions();
    input.value = "";
    input.placeholder = "Summarize the core idea in your own words…";
    setBusy(true);

    try {
      // Tell the server we've started (marks paper "studying") and get the prompt.
      const res = await api.post("/api/tutor/start", { paper_id: p.id });
      addAbstractBubble(p);
      addBubble(res.message, "tutor");
      transcript.push({ role: "tutor", text: res.message });
    } catch (err) {
      addBubble("Hmm, I couldn't start the session. Is the server running?", "tutor");
      console.error(err);
    } finally {
      setBusy(false);
      input.focus();
    }
  }

  /* ---- Close ------------------------------------------------------------ */
  function close() {
    overlay.classList.add("hidden");
    document.body.style.overflow = "";
    phase = "idle";
  }

  /* ---- Handle a submitted answer ---------------------------------------- */
  async function handleSubmit(text) {
    if (busy || !text.trim()) return;
    const answer = text.trim();

    addBubble(answer, "user");
    transcript.push({ role: "user", text: answer });
    input.value = "";
    autoGrow();
    setBusy(true);

    try {
      if (phase === "summary") {
        // Grade the summary.
        showTyping();
        const grade = await api.post("/api/tutor/grade", {
          paper_id: paper.id,
          summary: answer,
        });
        hideTyping();
        score = grade.score;
        addBubble(grade.message, "tutor");
        transcript.push({ role: "tutor", text: grade.message });
        phase = "followup";
        input.placeholder = "Your answer…";
        // Immediately ask the first Socratic follow-up.
        await nextTurn();
      } else if (phase === "followup") {
        await nextTurn();
      }
    } catch (err) {
      hideTyping();
      addBubble("Something went wrong reaching the tutor. Try again in a moment.", "tutor");
      console.error(err);
    } finally {
      if (phase !== "done") {
        setBusy(false);
        input.focus();
      }
    }
  }

  /* Ask the server for the next follow-up, or finish if we've done enough. */
  async function nextTurn() {
    showTyping();
    const res = await api.post("/api/tutor/turn", {
      paper_id: paper.id,
      transcript,
    });
    hideTyping();

    if (res.done) {
      await finish();
    } else {
      addBubble(res.question, "tutor");
      transcript.push({ role: "tutor", text: res.question });
    }
  }

  /* Wrap up: recap, save, mark read. */
  async function finish() {
    showTyping();
    const res = await api.post("/api/tutor/finish", {
      paper_id: paper.id,
      transcript,
      score,
    });
    hideTyping();
    addBubble(res.message, "tutor");
    phase = "done";
    setBusy(true); // no more input needed

    showDoneActions();
    // Refresh the feed + progress in the background so they're up to date.
    loadFeed();
    loadProgress();
  }

  /* A "Back to feed" button shown when the session is complete. */
  function showDoneActions() {
    removeDoneActions();
    const wrap = document.createElement("div");
    wrap.className = "tutor-done-actions";
    wrap.id = "tutor-done-actions";
    const btn = document.createElement("button");
    btn.className = "btn btn-accent full";
    btn.textContent = "✓ Done — back to feed";
    btn.addEventListener("click", () => {
      close();
      toast("Paper marked as read");
    });
    wrap.appendChild(btn);
    // Insert above the input bar.
    form.parentNode.insertBefore(wrap, form);
    form.classList.add("hidden");
  }
  function removeDoneActions() {
    document.getElementById("tutor-done-actions")?.remove();
    form.classList.remove("hidden");
  }

  /* ---- Input behaviour: auto-grow + Enter to send ----------------------- */
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  }
  input.addEventListener("input", autoGrow);
  input.addEventListener("keydown", (e) => {
    // Enter sends; Shift+Enter makes a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(input.value);
    }
  });

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSubmit(input.value);
  });

  document.getElementById("tutor-close").addEventListener("click", close);

  // Expose the API used by the feed cards.
  window.Tutor = { open, close };
})();
