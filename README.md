# D2 Build Maker

A personal, Destiny Item Manager-style web app that:

- Logs into your Bungie account and shows your characters, inventory, and vault.
- Generates optimal builds from a natural-language query (e.g. _"I want a Telesto build"_).
- Uses a free, rules-based engine driven by:
  - **DIM wishlist files** (community god rolls) for weapon roll scoring,
  - a curated **`archetypes.json`** exotic-synergy dataset, and
  - a **persistent reference knowledge base** you build up by ingesting YouTube videos (captions + comments), DIM loadout links, and web guides **once** so queries never hit the internet.

No paid LLM is used. The build engine reads everything from local caches.

## Architecture

- `backend/` - FastAPI (Python). Bungie OAuth, manifest cache, profile/inventory, reference ingestion + knowledge base, and the build engine. Data is stored in a local SQLite database (`backend/data/app.db`).
- `frontend/` - Vite + React + TypeScript + Tailwind. Inventory browser, Builds page, References manager.

## Prerequisites

- Python 3.10+
- Node.js 18+
- A Bungie API application (free).

## Quick start (Windows PowerShell)

After registering your Bungie app (below), you can set up and launch everything with:

```powershell
./run.ps1            # installs deps (first run) and starts backend + frontend
./run.ps1 -Setup     # only install dependencies, don't start servers
```

The first run creates `backend/.env` from the template - fill in your Bungie
credentials and re-run. The manual steps are below if you prefer them.

## 1. Register a Bungie application

1. Go to https://www.bungie.net/en/Application and create a new app.
2. Set **OAuth Client Type** to **Confidential**.
3. Set the **Redirect URL** to exactly:
   ```
   https://localhost:8000/api/auth/callback
   ```
   (Local HTTPS via `make_cert.py`. For Render hosting, use your
   `https://YOUR-SERVICE.onrender.com/api/auth/callback` URL instead — or add both.)
4. Note your **API Key**, **OAuth client_id**, and **OAuth client_secret**.

## 2. (Optional) YouTube Data API key

Only needed to ingest video **comments** (captions/transcripts work without it).
Create a key at https://console.cloud.google.com/ (enable "YouTube Data API v3").

## 3. Backend setup

```bash
cd backend
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows  (use: cp .env.example .env  on macOS/Linux)
```

Edit `backend/.env` and fill in `BUNGIE_API_KEY`, `BUNGIE_CLIENT_ID`, `BUNGIE_CLIENT_SECRET`
(and optionally `YOUTUBE_API_KEY`). Then run:

```bash
uvicorn app.main:app --reload --port 8000
```

## 4. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173.

## 5. First run

1. Click **Login with Bungie** and authorize.
2. Click **Sync Manifest** (downloads and caches Destiny item definitions; takes a bit the first time).
3. Open **Inventory** to confirm your gear loads.
4. (Recommended) Add a DIM wishlist for god-roll scoring: download
   [voltron.txt](https://raw.githubusercontent.com/48klocs/dim-wish-list-sources/master/voltron.txt)
   into `backend/data/wishlists/` and restart the backend.
5. On **References**, paste YouTube / DIM / guide URLs to build your knowledge base.
6. On **Builds**, type a query like `telesto build` and generate.

## How build generation works

1. Your query is matched to an exotic via the manifest name index (with fuzzy fallback).
2. The engine loads any curated archetype for that exotic and merges in facts from your
   ingested references (weapons, mods, aspects, fragments, subclass) weighted by how many
   sources mention them.
3. It scans your inventory to fill weapon slots (scored by wishlist god rolls + reference
   recommendations) and armor slots (by class and power), and flags anything you don't own.

## Host on Render (free)

One Docker service serves the API and the built React UI over HTTPS.

1. Push this repo to GitHub (already connected if you use `patrickcabel/d2buildbot`).
2. Open [Render Blueprints](https://dashboard.render.com/blueprints) → **New Blueprint Instance** → select this repo (`render.yaml`).
   Or: **New → Web Service** → connect the repo → Runtime **Docker** → instance type **Free**.
3. Set these environment variables (Blueprint prompts for `sync: false` ones):
   - `BUNGIE_API_KEY`
   - `BUNGIE_CLIENT_ID`
   - `BUNGIE_CLIENT_SECRET`
   - Leave `BUNGIE_REDIRECT_URI` / `FRONTEND_ORIGIN` blank (auto from `RENDER_EXTERNAL_URL`).
4. Deploy, then copy your public URL (e.g. `https://d2buildbot.onrender.com`).
5. In [Bungie Applications](https://www.bungie.net/en/Application), set **Redirect URL** to:
   ```
   https://YOUR-SERVICE.onrender.com/api/auth/callback
   ```
6. Open the Render URL → **Login with Bungie** → **Sync Manifest**.

**Free-tier caveats:** the service sleeps after ~15 minutes idle (cold start ~30–60s). Disk is ephemeral, so login + manifest may need a refresh after sleep. 512 MB RAM is tight for a full manifest sync — if sync fails, retry once the service is warm.

## Extending

- Add more exotics to `backend/data/archetypes.json` (keyed by in-game name).
- Add more wishlist `.txt` files to `backend/data/wishlists/`.
- The reference extractor currently matches item names via the manifest (no LLM). An
  LLM-summarization step could be added in `backend/app/references/ingest.py`.

## Notes / limitations

- Personal, single-user app: one Bungie login is stored locally (OAuth tokens are encrypted at rest).
- DIM loadout-link decoding is best-effort; if the share API is unavailable it falls back to page text.
- Aspect/fragment ownership isn't verified against your account; those are recommendations.
