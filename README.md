# Tillage Image-Pair Comparison Study

A crowdsourced labeling app for the **Conservation Agriculture Morocco** project.
You email a link to volunteers; each one sees **two field images (A & B) + two
questions**, presses **Next**, and repeats. Answers are saved after every Next.
Designed for **thousands of image pairs**, with:

- **Name-only login** (no accounts)
- **50-pair sessions**, with "give me another set" when finished
- **No per-pair labeler cap right now** (one answer per person per pair; a cap can be re-enabled in `app.py` / `schema.sql`)
- **Partial saving** — every answer is persisted immediately
- **One-page instructions** before labeling

It runs in two modes from **one codebase**:

| | Backend | Where it runs | Use for |
|---|---|---|---|
| **Local** | `app.py` + SQLite | your PC | building & **testing the whole flow today** |
| **Production** | Supabase (Postgres) | the cloud, free tier | the **public link you email out** |

The browser code is backend-agnostic ([static/api.js](static/api.js)); switching is a one-line config change.

---

## A. Try it now (local, no accounts, no internet)

1. Double-click **`run_app.bat`** (or run the two commands below).
   ```powershell
   cd "C:\Users\fdebundel\Documents\Dropbox\CA_Morocco\5_Code\App"
   python generate_pairs.py     # makes 200 synthetic starter pairs (first time)
   python app.py                # opens http://localhost:8000
   ```
2. Enter a name → read the intro → label pairs → ask for another set.
3. See progress: open `http://localhost:8000/api/stats`.
4. Analyze what you collected:
   ```powershell
   python export_responses.py       # -> responses_export.csv
   Rscript r\analyze_responses.R     # coverage, inter-rater kappa, accuracy vs truth
   ```

Everything here is **Python standard library only** — nothing to install.

> The starter images are **synthetic** placeholders (brown = tilled, green +
> straw = no-till, plus deliberately ambiguous ones). The metadata stores the
> "truth" so `analyze_responses.R` can report how accurate the crowd was.

---

## B. The two questions and instructions live in one file

Edit [static/config.js](static/config.js) — no build step, just save and refresh:

- `introHtml` — the one-page explanation shown before labeling
- `questions` — the two questions and their answer options
- `batchSize` — pairs per session (default 50)

The default questions ask the tillage status of image A and of image B. Replace
the wording/options with exactly what you want respondents to answer.

---

## C. Go live (free)

The app + images must be reachable by your external volunteers, so **the live
site is public either way.** Pick a host based on whether you want the *repo*
public:

- **Public repo → GitHub Pages** (simplest). Repo and images are public.
- **Private repo → Cloudflare Pages / Netlify** (free). Keeps your **source code
  and history private**; the deployed site is still public. Use this if the repo
  must stay private — free GitHub Pages and jsDelivr both require a *public* repo,
  so a private repo deploys via Cloudflare/Netlify instead.

Steps (same for both unless noted):

1. **Images** into `images/{province}/{year}/pair_NNNN_a|b.png`. Replace the
   synthetic ones with your real chips and regenerate `pairs_metadata.csv`.

2. **Push** the App folder to your repo (public or private per above).

3. **Set up Supabase** (free, EU region): run [supabase/schema.sql](supabase/schema.sql)
   in the SQL editor.

4. **Build the pairs list (R):** in [r/build_pairs.R](r/build_pairs.R) set
   `host_mode` — `"same_origin"` (images served by your host; works for Cloudflare,
   Netlify, and Pages) or `"jsdelivr"` (public repo, better bandwidth at scale).
   Run it, then load the output into Supabase (import `pairs_for_supabase.csv`, or
   run `pairs_seed.sql`).

5. **Point the app at Supabase:** in [static/config.js](static/config.js) set
   ```js
   backend: "supabase",
   supabaseUrl: "https://<your-project>.supabase.co",
   supabaseAnonKey: "<your anon public key>",
   ```

6. **Deploy:** public → enable GitHub Pages (Settings → Pages → branch `main`,
   `/root`). private → connect the repo in Cloudflare Pages/Netlify (framework
   preset *None*, no build command, output dir = repo root). Email the resulting URL.

To analyze production data, run `supabase/export_query.sql` in the Supabase SQL
Editor and *Download CSV* → save as `responses_export.csv` → `Rscript r/analyze_responses.R`.

Do **not** use the Table Editor's *Export → CSV* button: it dumps `responses`
verbatim (answers still one JSON blob, no `field_id`), which is *not* the shape
the local export produces and which `analyze_responses.R` rejects.
`export_responses.py` is local-SQLite-only — the anon key cannot read `responses`
(RLS), which is exactly what keeps respondents' answers private.

### Why responses can't live on GitHub
GitHub/jsDelivr host the **app and images** perfectly. They **cannot** hold
responses: partial-save means thousands of tiny writes (not what git is for),
concurrent writers would collide, and respondent names are personal data (a
public repo would expose them). A database also lets you re-impose a per-pair
labeler cap later with an atomic check. Supabase's Postgres handles all of this.

---

## Data model

`pairs(pair_id, province, year, image_a, image_b)` — one row per image pair.
`responses(pair_id, respondent, answers, created_at)` with `UNIQUE(pair_id,
respondent)`. **Label count = rows per pair.** Each Next click = one row
(your partial save). There is no per-pair labeler cap right now; `submit_response()`
(Supabase) and `app.py` (local) behave identically and a cap can be re-enabled in both.

## Files

```
App/
├─ run_app.bat            ← local test launcher (Windows)
├─ generate_pairs.py      ← synthetic A/B pairs -> images/ + pairs_metadata.csv
├─ app.py                 ← LOCAL backend (stdlib + SQLite), serves UI/images
├─ export_responses.py    ← dump local SQLite -> responses_export.csv
├─ index.html             ← the page GitHub Pages serves (landing → loop → done)
├─ .nojekyll              ← tells GitHub Pages not to run Jekyll
├─ static/
│  ├─ config.js           ← YOUR questions, intro text, backend switch
│  ├─ api.js              ← local ↔ supabase adapter (one interface)
│  ├─ app.js              ← questionnaire flow + partial save + resume
│  └─ style.css
├─ supabase/schema.sql    ← tables + claim_batch + submit_response + RLS
├─ r/
│  ├─ build_pairs.R       ← images/ -> jsDelivr URLs -> pairs seed (CSV + SQL)
│  └─ analyze_responses.R ← coverage, inter-rater kappa, accuracy vs truth
├─ images/                ← the chips (synthetic now; your real data later)
├─ pairs_metadata.csv     ← one row per pair (+ synthetic truth)
└─ data/study.db          ← local responses (created on first answer)
```

## Requirements
- **Local mode:** Python 3.8+ (tested 3.14), standard library only.
- **Analysis:** R (base only). **Production:** a free GitHub + Supabase account.
