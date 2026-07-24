# ✈️ PaperPilot

A mobile-first web app (PWA) that turns reading AI/ML research papers into an
active-learning habit. It shows you a **ranked feed** of papers and — the heart
of the app — a **Tutor Mode** that makes you summarize each paper in your own
words, grades your understanding, corrects you kindly, and drills the idea
deeper with Socratic follow-up questions.

Built with **FastAPI** (Python) + a lightweight **vanilla-JS PWA**. It installs
to your phone's home screen, works fullscreen, and can send you gentle reading
nudges.

> **New to all this?** That's exactly who this README is written for. Follow the
> sections in order. Every command is spelled out; nothing is assumed.

---

## What you'll end up with

- A **Feed** of papers ranked "easiest + most relevant + unlocked first," each
  card showing a one-sentence core idea, a colour-coded difficulty pill, reading
  time, tier/topic, a **Read PDF** button, and a **Study this** button.
- A **Tutor Mode** chat: summarize → get scored 1–5 → see what you got right and
  missed → answer 2–3 deeper questions → get a 3-bullet recap; the paper is
  marked **read**.
- A **Progress** screen: papers read, day streak, current tier, tier bars.
- Optional **push notifications** and an automatic **weekly** fetch of brand-new
  papers.

---

## Table of contents

1. [Run it locally](#1-run-it-locally)
2. [Test it on your phone (same Wi-Fi)](#2-test-it-on-your-phone-same-wi-fi)
3. [Get a free LLM API key (Groq or Gemini)](#3-get-a-free-llm-api-key-groq-or-gemini)
4. [Create a free Postgres database (Neon)](#4-create-a-free-postgres-database-neon)
5. [Deploy to Render](#5-deploy-to-render)
6. [Install the app on your phone + notifications](#6-install-the-app-on-your-phone--notifications)
7. [iOS Shortcut: "when Instagram opens, open PaperPilot"](#7-ios-shortcut-when-instagram-opens-open-paperpilot)
8. [The weekly auto-fetch job](#8-the-weekly-auto-fetch-job)
9. [Optional: Google Sheets export](#9-optional-google-sheets-export)
10. [How it all fits together](#how-it-all-fits-together)
11. [Troubleshooting](#troubleshooting)

---

## 1. Run it locally

### 1.1 — You need Python 3.11+

Check what you have:

```bash
python3 --version
```

If that prints `Python 3.11.x` or higher, great. If not, install Python 3.11+
from [python.org/downloads](https://www.python.org/downloads/).

> **Note for this machine:** your system Python/Command Line Tools are broken,
> but you have a working Python 3.11.9 inside `myenv/`. The next step uses it to
> build PaperPilot's own isolated environment, so you don't need to fix anything
> system-wide. If `python3` doesn't work for you, replace it in the command
> below with `/Users/bharatagrawal/AppDev/myenv/bin/python3.11`.

### 1.2 — Create a virtual environment and install dependencies

A "virtual environment" (venv) is a private folder of Python packages just for
this project, so it never clashes with anything else.

From inside the `PaperPilot/` folder:

```bash
# Create the venv (using your working 3.11 interpreter)
/Users/bharatagrawal/AppDev/myenv/bin/python3.11 -m venv .venv
# (on a normal machine this is just:  python3 -m venv .venv )

# "Activate" it — your prompt will show (.venv)
source .venv/bin/activate      # macOS / Linux
# .venv\Scripts\activate       # Windows PowerShell

# Install everything PaperPilot needs
pip install -r requirements.txt
```

### 1.3 — Create your `.env` file (your secrets)

```bash
cp .env.example .env
```

Open `.env` in any text editor. To get the app fully working you need **one**
LLM key. The default is **Groq** — see
[section 3](#3-get-a-free-llm-api-key-groq-or-gemini) to grab a free one, then
paste it:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_your_real_key_here
```

Leave `DATABASE_URL=sqlite:///./paperpilot.db` as-is for now (a local file
database — zero setup).

### 1.4 — Generate the app icons

```bash
python scripts/make_icons.py
```

This writes placeholder icons into `static/icons/`. (Replace them with your own
art anytime; keep the filenames.)

### 1.5 — Load your reading list (INIT)

This reads `seed_papers.py`, confirms each paper on arXiv (fixing any stale IDs
and grabbing the real PDF link + abstract), then asks the LLM to score each one.

**First, a fast free smoke test** (no LLM calls, ~30 seconds) just to see the app
populate:

```bash
python -m cli.main --mode init --limit 3 --skip-enrich
```

**Then the real thing** (calls the LLM once per paper — a few minutes for all 30):

```bash
# delete the smoke-test database first so every paper gets real analysis
rm paperpilot.db
python -m cli.main --mode init
```

You'll see each paper get an arXiv match and an enrichment line.

### 1.6 — Start the server

```bash
uvicorn app.main_api:app --reload
```

Open **http://localhost:8000** in your browser. You should see your ranked feed.
Click **Study this ✨** on any card to try Tutor Mode. 🎉

> `--reload` auto-restarts the server when you edit code. Press `Ctrl+C` to stop.

---

## 2. Test it on your phone (same Wi-Fi)

You can use the app on your phone before deploying, as long as your phone and
laptop are on the **same Wi-Fi**.

1. Start the server bound to your whole network (note the `--host`):

   ```bash
   uvicorn app.main_api:app --host 0.0.0.0 --port 8000
   ```

2. Find your laptop's local IP address:
   - **macOS:** System Settings → Wi-Fi → Details → look for `IP Address`
     (looks like `192.168.1.23`). Or run `ipconfig getifaddr en0`.
   - **Windows:** run `ipconfig` and read the `IPv4 Address`.

3. On your phone's browser, go to `http://<that-ip>:8000`
   (e.g. `http://192.168.1.23:8000`).

> Notifications and "Add to Home Screen" work best over **https**, which you get
> automatically once you deploy (section 5). Local Wi-Fi is great for trying the
> feed and Tutor Mode.

---

## 3. Get a free LLM API key (Groq or Gemini)

PaperPilot talks to a language model for enrichment and Tutor Mode. Pick **one**.
You can switch later by changing just `LLM_PROVIDER` in `.env`.

### Option A — Groq (default, recommended: fast + generous free tier)

1. Go to **https://console.groq.com** and sign in (Google/GitHub works).
2. In the left menu click **API Keys** → **Create API Key**.
3. Copy the key (it starts with `gsk_...`). You won't see it again, so paste it
   somewhere safe.
4. Put it in `.env`:

   ```
   LLM_PROVIDER=groq
   GROQ_API_KEY=gsk_your_key
   GROQ_MODEL=llama-3.3-70b-versatile
   ```

### Option B — Google Gemini

1. Go to **https://aistudio.google.com/apikey** and sign in.
2. Click **Create API key**, copy it.
3. In `.env`:

   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=your_key
   GEMINI_MODEL=gemini-1.5-flash
   ```

### Option C — Ollama (fully local, no key, no cloud)

Only works on a machine where [Ollama](https://ollama.com) is running (not on
Render's free tier). Install Ollama, then:

```bash
ollama pull llama3.1
```

```
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.1
```

> **Swapping providers never requires code changes** — all LLM calls go through
> one `ask()` function in `app/llm.py`.

---

## 4. Create a free Postgres database (Neon)

Locally you use SQLite (a file). But on Render's free tier, the disk is **wiped
on every redeploy** — so your reading history/scores would vanish. The fix is a
free cloud Postgres from **Neon**. (Supabase works too; steps are similar.)

1. Go to **https://neon.tech** and sign up (free).
2. Click **Create Project**. Give it any name; pick a region near you.
3. After it's created, find the **Connection string** (a.k.a. connection URI).
   It looks like:

   ```
   postgresql://alex:AbCd1234@ep-cool-name-123456.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```

4. Copy that whole string. You'll paste it into Render as `DATABASE_URL`
   (section 5) and into GitHub secrets (section 8).

> PaperPilot automatically handles the `postgres://` vs `postgresql://` naming
> and makes sure SSL is on, so just paste the URL exactly as Neon gives it.

---

## 5. Deploy to Render

Render will host your app at a public `https://` URL, for free.

### 5.1 — Put the project on GitHub

1. Create a free account at **https://github.com** if you don't have one.
2. Create a **new repository** (the "+" top-right → New repository). Name it
   `paperpilot`. Leave it empty (no README — you already have one).
3. From inside the `PaperPilot/` folder, push your code:

   ```bash
   git init
   git add .
   git commit -m "PaperPilot initial version"
   git branch -M main
   git remote add origin https://github.com/<your-username>/paperpilot.git
   git push -u origin main
   ```

   > Your `.env` is **not** uploaded — it's protected by `.gitignore`. Good.

### 5.2 — Create the Render web service

1. Sign up at **https://render.com** (log in with GitHub — easiest).
2. Click **New +** → **Web Service**.
3. Choose **Build and deploy from a Git repository**, connect GitHub, and pick
   your `paperpilot` repo.
4. Render detects `render.yaml` and pre-fills most settings. Confirm:
   - **Runtime:** Python
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main_api:app --host 0.0.0.0 --port $PORT`
   - **Instance type:** Free

### 5.3 — Add your environment variables

In the service's **Environment** section, add these (click **Add Environment
Variable** for each). These are the ones marked `sync: false` in `render.yaml`:

| Key | Value |
|-----|-------|
| `GROQ_API_KEY` | your `gsk_...` key |
| `DATABASE_URL` | your Neon connection string from section 4 |
| `LLM_PROVIDER` | `groq` (already set, confirm) |

Leave the VAPID keys blank for now — add them later when you turn on
notifications (section 6).

### 5.4 — Deploy + seed the database

1. Click **Create Web Service**. Render builds and starts it. When it's live
   you'll get a URL like `https://paperpilot.onrender.com`.
2. Your Neon database starts empty, so seed it **once**. Open the service's
   **Shell** tab in Render and run:

   ```bash
   python -m cli.main --mode init
   ```

   (This uses the same `DATABASE_URL`, so it fills your Neon database.)
3. Refresh your Render URL — your feed is live on the internet. 🎉

> **Heads-up about the free tier:** the service "sleeps" after ~15 minutes of no
> traffic and takes ~30 seconds to wake on the next visit. That's normal for
> free hosting.

---

## 6. Install the app on your phone + notifications

### 6.1 — Add to Home Screen (makes it a real app)

**iPhone / iPad (Safari):**
1. Open your Render URL in **Safari**.
2. Tap the **Share** icon (square with an up-arrow).
3. Scroll down, tap **Add to Home Screen**, then **Add**.
4. Launch PaperPilot from the new icon — it opens fullscreen, no browser bars.

**Android (Chrome):**
1. Open your Render URL in **Chrome**.
2. Tap the **⋮** menu → **Install app** (or **Add to Home screen**).
3. Launch it from the icon.

### 6.2 — Turn on notifications

Open PaperPilot (from the home-screen icon), go to **Settings**, and flip
**Notifications** on. Set how many nudges per day and your quiet hours.

**Honest platform reality (this is a real limitation, not a bug):**
- **Android Chrome:** push works once the app is installed. ✅
- **iPhone/iPad:** web push works **only** for a PWA **added to the Home Screen**,
  on **iOS 16.4 or later**, and only when you open it from that icon. In a normal
  Safari tab, iOS will not deliver push. The app detects this and tells you.
- **Desktop Chrome/Edge/Firefox:** great for testing.

To actually **send** notifications you also need VAPID keys on the server:

```bash
python scripts/gen_vapid.py
```

Copy the two printed lines into your `.env` (locally) **and** add them as
environment variables on Render (`VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`), then
redeploy. Use the **Send a test notification** button in Settings to check it.

> **Free-tier caveat:** Render sleeps when idle, so the app's own hourly timer
> pauses. For reliable nudges in production, have an external scheduler ping your
> app hourly — see the tip at the end of [section 8](#8-the-weekly-auto-fetch-job).

---

## 7. iOS Shortcut: "when Instagram opens, open PaperPilot"

A gentle intervention: every time you open Instagram, your phone bounces you to
PaperPilot for a 2-minute paper break first.

1. Make sure PaperPilot is on your Home Screen (section 6.1).
2. Open the **Shortcuts** app → tap the **Automation** tab at the bottom.
3. Tap **+** (top-right) → **Create Personal Automation**.
4. Scroll to and choose **App**.
5. Tap **Choose**, select **Instagram**, tap **Done**. Make sure **Is Opened**
   is selected.
6. Tap **Next**.
7. Tap **Add Action**. Search for **Open App** and select it.
8. In the action, tap the word **App** and choose **PaperPilot**.
9. Tap **Next**.
10. Turn **Ask Before Running** **OFF** (so it's automatic), confirm **Don't Ask**.
11. Tap **Done**.

Now opening Instagram immediately launches PaperPilot. (To undo, delete the
automation from the Automation tab.)

> Tip: you can point the same automation at TikTok, X, or any app you'd like to
> intercept.

---

## 8. The weekly auto-fetch job

Every week, PaperPilot can fetch brand-new arXiv papers (last 7 days, filtered by
the categories/keywords in `config.yaml`), enrich them, and add them to your feed
under **🆕 New this week** — automatically, for free, using **GitHub Actions**.

The workflow file is already included at
[`.github/workflows/weekly.yml`](.github/workflows/weekly.yml). It runs every
Monday and can also be triggered by hand.

### Set it up

1. Push your repo to GitHub (you did this in section 5.1).
2. In your GitHub repo, go to **Settings → Secrets and variables → Actions →
   New repository secret** and add:
   - `DATABASE_URL` — your Neon connection string (same one Render uses, so new
     papers show up in your live app).
   - `GROQ_API_KEY` — your Groq key.
   - *(optional)* `LLM_PROVIDER` (defaults to `groq`), `GROQ_MODEL`.
3. That's it. It runs automatically on schedule. To run it now: **Actions** tab →
   **Weekly paper fetch** → **Run workflow**.

> **Bonus — reliable notification nudges in production.** Because Render's free
> service sleeps, you can reuse a scheduler to both wake it and drive nudges:
> sign up at a free cron service like **cron-job.org** and have it send a
> `POST` to `https://your-app.onrender.com/api/push/tick` once an hour. The app
> decides (based on your frequency + quiet hours) whether to actually send.

---

## 9. Optional: Google Sheets export

PaperPilot works fully **without** Google. If you ever want to mirror your paper
list into a Google Sheet, it's a stub you can switch on later — no credentials
needed to deploy today.

To enable it later:
1. `pip install gspread google-auth`
2. In Google Cloud, create a **Service Account** and download its JSON key.
3. Create a Google Sheet and **share** it with the service account's email.
4. In `.env` set `GOOGLE_SHEETS_ENABLED=true`,
   `GOOGLE_SHEETS_CREDENTIALS_FILE=/path/to/key.json`, and `GOOGLE_SHEETS_ID=...`
   (the long id in your sheet's URL).
5. Open `app/sources/sheets.py` and uncomment the reference implementation
   (it's written out for you).

---

## How it all fits together

```
PaperPilot/
├── app/
│   ├── main_api.py     FastAPI app: /api/* routes + serves the PWA
│   ├── llm.py          ONE ask() function → Groq / Gemini / Ollama
│   ├── enrich.py       one LLM call per paper → strict JSON (scores, core idea)
│   ├── ranker.py       computes the adaptive "read next" order
│   ├── tutor.py        grading + Socratic follow-ups + recap prompts
│   ├── models.py       database tables (papers, sessions, settings, subs)
│   ├── db.py           SQLAlchemy engine (SQLite local / Postgres prod)
│   ├── config.py       loads .env + config.yaml
│   ├── push.py         Web Push sending (VAPID)
│   ├── scheduler.py    hourly nudge logic (+ /api/push/tick for prod)
│   └── sources/
│       ├── arxiv.py    title-confirm search + weekly fetch
│       └── sheets.py   optional Google Sheets stub
├── cli/main.py         `--mode init` and `--mode weekly`
├── static/             the PWA (index.html, css, js, manifest, service worker)
├── scripts/            make_icons.py, gen_vapid.py
├── seed_papers.py      your curated reading list (the INIT source)
├── config.yaml         topics, arXiv categories, keywords, ranker weights
├── render.yaml         Render deploy config
├── Dockerfile          optional container build
└── .github/workflows/weekly.yml   the weekly job
```

**The ranking idea:** each unread paper scores higher when it's more relevant,
less difficult, in an earlier tier, and its prerequisites are already among the
papers you've marked **read**. Finishing a paper re-runs the ranking, so the
queue keeps adapting to you.

---

## Troubleshooting

**"No papers yet" in the feed.**
Run `python -m cli.main --mode init` (locally) or in Render's Shell (production).

**`GROQ_API_KEY is not set` / `Invalid API Key`.**
Your key is missing or wrong/expired in `.env` (local) or Render env vars (prod).
Generate a fresh one at https://console.groq.com/keys.

**arXiv confirmation says "no arXiv confirmation" for a paper.**
That's expected for classics not on arXiv (they fall back to the seed's link).
For arXiv papers, it means the title search didn't find a confident match — the
app still stores the paper using the seed values.

**Enrichment is slow.**
It's one LLM call per paper. Use `--limit N` and/or `--skip-enrich` for quick
tests; run the full `--mode init` once when you're ready.

**Notifications don't arrive.**
Check, in order: (1) VAPID keys are set on the server, (2) you installed the app
to your home screen (required on iOS 16.4+), (3) you granted permission,
(4) it's not quiet hours, (5) on Render, remember the free tier sleeps — use the
external-cron tip in section 8.

**Postgres connection errors on Render.**
Make sure `DATABASE_URL` is the full Neon string including `?sslmode=require`.

---

Happy reading — one paper at a time. ✈️
