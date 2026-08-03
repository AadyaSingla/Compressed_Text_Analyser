# Dev Log — Compressed Text Analyser

A running log of how the app was built and why each part is the way it is.
(The project isn't in its own git history yet, so this log reconstructs the
build steps from the code; new entries should be added at the top as the
project evolves.)

---

## 2026-08-03 — Added a JSON API with Swagger docs

- **New `/api/...` blueprint (`api.py`), alongside the existing HTML pages.**
  The original routes in `app.py` render Jinja templates from form
  submissions; they aren't a fit for API documentation since they don't speak
  JSON. Rather than force Swagger onto HTML routes, the same underlying
  operations (run an analysis, list inputs, fetch results, delete an input)
  are now also exposed as JSON endpoints: `POST /api/experiments`,
  `GET /api/inputs`, `GET /api/results/<ihash>`, `DELETE /api/inputs/<ihash>`.
- **`flasgger` serves interactive docs at `/apidocs/`.** Each route's
  docstring carries a YAML OpenAPI spec that flasgger picks up automatically,
  so the docs stay next to the code they describe instead of a separate spec
  file that can drift.
- **Shared constants moved to `config.py`.** `DATA_DIR`, `SAMPLES`,
  `MAX_INPUT_CHARS`, and `MAX_K` were defined in `app.py`; both `app.py` and
  the new `api.py` need them, and `api.py` importing from `app.py` would be
  circular (`app.py` also imports the blueprint from `api.py` to register
  it). Pulling the constants into their own module breaks the cycle.
- **`requirements.txt` added.** The project had no dependency manifest before
  this; `flasgger` is now a real dependency, so `Flask` and `flasgger` are
  both pinned to the versions installed in `.venv`.

## 2026-07-20 — Flattened the `bpe_thesis/` folder to the project root

- **Removed the `bpe_thesis/` layer entirely.** `app.py`, `bpe.py`, `db.py`,
  `templates/`, `data/`, and `experiments.db` now live directly at the project
  root. The subfolder was never a real Python package (no `__init__.py`, and
  the modules imported each other flat as `import bpe` / `import db`), so it was
  organizational only — a container that the code inside didn't actually use.
- **`main.py` lost its `sys.path` hack.** With the modules at the root, the
  `sys.path.insert(0, .../bpe_thesis)` line is unnecessary, so `main.py` is now
  just `from app import app` plus the `app.run(...)` call. The run command is
  unchanged: `.venv/bin/python main.py` from the project root.
- **No code logic changed.** `app.py` and `db.py` locate `data/`,
  `templates/`, and `experiments.db` via `Path(__file__).parent`, which now
  resolves to the root — so uploads, samples, and the database keep working with
  no edits. Only file locations and the docs moved; the app behaves identically.

## 2026-07-14 — Compression ratio replaced by compression utility

- **The headline metric is now compression utility** `U(s,k) = |s| − |s_k|` —
  the absolute number of characters saved after k BPE merges (Kozma &
  Voderholzer's definition of compression utility, applied to BPE's own greedy
  merge sequence). It replaces `compression_ratio` everywhere: `bpe.analyse()`
  returns it under the `"utility"` key, the DB column is `utility INTEGER`
  (it's always a non-negative whole number of characters, never a ratio), and
  the plot, report PNG, CSV export, and results table all show it. The k = 0
  baseline is now utility = 0 (was ratio 1.0), and the curve *rises* with k.
- **Existing `experiments.db` migrated in place, no re-runs needed**: utility
  is exactly derivable from stored columns as `original_chars − token_count`,
  so the table was rebuilt under the new schema with utility recomputed for
  all rows (ids and timestamps preserved). Old `compression_ratio` values were
  dropped. A DB created before this change will not work with the new code
  without this migration — `save_experiment` inserts a `utility` column that
  the old table lacks (`CREATE TABLE IF NOT EXISTS` won't alter an existing
  table), so any un-migrated copy must be migrated the same way or its
  experiments re-run from scratch.

## 2026-07-14 — Whitespace normalization before BPE

- **New preprocessing step**: `bpe.normalize_whitespace()` runs as the first
  line of `analyse()`, before training, so it applies uniformly to every k
  value and every input source (pasted text, uploads, samples) with no changes
  to `app.py`, `db.py`, or the templates.
- Every run of spaces/tabs collapses to a single space
  (`re.sub(r'[ \t]+', ' ', text)`), and any sequence of blank lines collapses
  to a single newline (`re.sub(r'\n[ \t]*\n+', '\n', text)`). Leading/trailing
  whitespace of the whole text is *not* stripped and non-whitespace characters
  are untouched.
- **Deliberate trade-off**: the raw multi-space/tab indentation structure of
  source-code inputs is intentionally *not* preserved. Compression ratio and
  vocabulary size should measure textual/content redundancy, not formatting
  artifacts like indentation depth or tabs-vs-spaces style.

## 2026-07-13 — Ratio inverted to tokens/chars; downloadable report

- **Compression ratio is now `tokens / chars`** (was `chars / tokens`): 1.0 =
  uncompressed, lower = better compression, so the ratio curve now *falls*
  with k. Changed in `bpe.analyse()`, the plot axis label, README, and this
  log; stored rows in `experiments.db` were recomputed in place from their
  token/char counts (exact, no re-run needed).
- Results page gained a **Download results (PNG)** button (`/report/<ihash>.png`):
  both graphs plus the full stats table rendered into a single image, height
  scaled to the row count. A CSV export route (`/download/<ihash>.csv`) exists
  but is not linked in the UI.

## 2026-07-13 — Documentation pass

- Added this dev log and a README explaining BPE, every stat the app reports,
  and how each module works, in simple language.
- Known state: app runs with `.venv/bin/python main.py` on port 5001;
  experiments deduplicate on (input_string, k).

## Step 5 — Web UI (templates/)

- Three Jinja templates extending a shared `base.html` that holds all the CSS
  (no external stylesheet — keeps the app to a single folder, no static dir).
- `index.html`: one form with three input choices (paste / upload / sample),
  k and sweep-step fields, plus a table of previously analysed inputs with
  per-input delete buttons (guarded by a JS `confirm`).
- `results.html`: the plot image, a stats table (one row per k), and a 400-char
  preview of the input so you can tell inputs apart.
- Numbers are right-aligned with tabular numerals so columns line up.

## Step 4 — Plotting (`app.py: /plot/<ihash>.png`)

- Plots are generated server-side with matplotlib and streamed as PNG from
  memory (`io.BytesIO`) — nothing is written to disk.
- `matplotlib.use("Agg")` is set **before** importing pyplot because the app
  runs headless (no GUI backend); without this Flask can crash on macOS.
- Two side-by-side charts: compression ratio vs k, vocabulary size vs k.
  Together they show the BPE trade-off (shorter text ↔ bigger vocab).
- Each figure is `plt.close()`d after saving to avoid leaking memory across
  requests.

## Step 3 — Flask app (`app.py`)

- Routes: `/` (form + stored inputs), `/run` (POST, runs experiments),
  `/results/<ihash>` (stats table + plot), `/plot/<ihash>.png`,
  `/delete/<ihash>` (POST).
- **Input resolution priority**: sample > uploaded file > pasted text
  (`_resolve_input`). Uploads are decoded as UTF-8 with `errors="replace"`
  so binary-ish files don't crash the app, and a copy is kept in
  `data/uploads/`.
- **k sweep** (`_parse_ks`): step = 0 means a single run at k; step > 0 means
  k = 0, step, 2·step, …, k. Running k = 0 too gives the plot a proper
  baseline point (ratio exactly 1.0).
- **Guardrails**: input capped at 200,000 chars, k capped at 2000, invalid
  numbers and empty input redirect back with a flash message instead of a 500.
- Before running each k, the app checks the DB first and skips work already
  done — the flash message reports "N new, M already stored".
- Redirect target after a run is the input's hash, not a row id, so all runs
  for the same text share one results page.

## Step 2 — Storage (`db.py`)

- SQLite, single `experiments` table, schema created on every `connect()`
  via `CREATE TABLE IF NOT EXISTS` — no migration tooling needed at this size.
- **Key rule: rows are UNIQUE on (input_string, k).** `save_experiment`
  checks for an existing row first and returns `(row, False)` instead of
  inserting a duplicate. This was an explicit requirement: re-running an
  experiment must reuse the stored result.
- Inputs are addressed by `input_hash` — the first 16 hex chars of the
  SHA-256 of the text. The hash is used in URLs (`/results/<ihash>`) so the
  full text never appears in a URL; an index on (input_hash, k) keeps the
  results queries fast.
- The full input text *is* stored in each row (needed for the exact-match
  dedup and the preview), which is fine at the 200k-char input cap.

## Step 1 — BPE core (`bpe.py`)

- Deliberately the simplest correct implementation, so it's easy to explain
  in the thesis: start from single characters, and k times count all adjacent
  pairs with `Counter(zip(tokens, tokens[1:]))`, then merge the most frequent
  pair everywhere with a single left-to-right scan.
- **Early stop**: if the best pair occurs fewer than 2 times, further merges
  can't compress anything, so training stops — this is why "merges applied"
  can be less than k.
- Left-to-right merging handles overlaps the standard way: in `aaa` the pair
  `aa` merges once (positions 0–1), leaving `aa`,`a`.
- Tokens are plain Python strings (character-level BPE, not byte-level like
  GPT tokenizers) — simpler, and fine for text analysis purposes.
- `analyse()` wraps training and returns the stats dict that maps 1:1 onto a
  database row: k, merges applied, char count, token count, vocab size,
  compression ratio (tokens/chars, guarded against division by zero for empty
  input), and the longest learned token.

## Step 0 — Project setup

- Flask app in a `bpe_thesis/` package with a thin `main.py` entry point that
  adds the package dir to `sys.path` and starts the dev server on **port 5001**
  (5000 is taken by AirPlay on macOS).
- Two bundled samples (`data/sample_english.txt`, `data/sample_code.py`) so
  the app is usable immediately and prose-vs-code compression can be compared.