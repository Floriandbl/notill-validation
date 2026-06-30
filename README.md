# Tillage Image-Pair Comparison Study

A crowdsourced labeling app for the **Conservation Agriculture Morocco** project.
You email a link to volunteers; each one sees **two field images (A & B) + two
questions**, presses **Next**, and repeats. Answers are saved after every Next.
Designed for **thousands of image pairs**, with:

- **Name-only login** (no accounts)
- **50-pair sessions**, with "give me another set" when finished
- **Max 2 labelers per pair**, enforced atomically (never 3, even under races)
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
   python generate_pairs.py     # makes ~10 synthetic starter pairs (first time)
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

## C. Go live (public link via GitHub Pages + Supabase)

Free within the free tiers. Six steps; R owns the data, the app is already built.

1. **Generate / collect images** into `images/{province}/{year}/pair_NNNN_a.png`
   (+`_b.png`). For real data, replace the synthetic `images/` with your exported
   parcel chips and regenerate `pairs_metadata.csv` to match (same columns).

2. **Push `images/` to a PUBLIC GitHub repo.** jsDelivr serves any file in it via
   CDN automatically. (Keep total repo size under ~1 GB.)

3. **Build the pairs list (R):** edit the GitHub user/repo/branch at the top of
   [r/build_pairs.R](r/build_pairs.R), then run it. It writes
   `pairs_for_supabase.csv` and `pairs_seed.sql` with jsDelivr URLs.

4. **Set up Supabase** (free project, EU region): open the SQL editor and run
   [supabase/schema.sql](supabase/schema.sql). Then load the pairs — import
   `pairs_for_supabase.csv` in the Table editor, or run `pairs_seed.sql`.

5. **Point the app at Supabase:** in [static/config.js](static/config.js) set
   ```js
   backend: "supabase",
   supabaseUrl: "https://<your-project>.supabase.co",
   supabaseAnonKey: "<your anon public key>",
   ```

6. **Deploy the frontend on GitHub Pages:** push `static/` (and `index.html`)
   and enable Pages. Email the resulting `https://<you>.github.io/...` link.

To analyze production data, export the Supabase `responses` table to CSV (same
columns as the local export) and run `r/analyze_responses.R` on it.

### Why responses can't live on GitHub
GitHub/jsDelivr host the **app and images** perfectly. They **cannot** hold
responses: the max-2 rule needs an atomic transaction (git would race to 3+
labelers), partial-save means thousands of tiny writes (not what git is for),
and respondent names are personal data (a public repo would expose them).
Supabase's Postgres handles all three. That's the whole reason for the split.

---

## Data model

`pairs(pair_id, province, year, image_a, image_b)` — one row per image pair.
`responses(pair_id, respondent, answers, created_at)` with `UNIQUE(pair_id,
respondent)`. **Label count = rows per pair.** Each Next click = one row
(your partial save). The atomic max-2 check lives in `submit_response()`
(Supabase) and `app.py` (local) — identical behaviour.

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
