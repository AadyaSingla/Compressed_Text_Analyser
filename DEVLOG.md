# Dev Log — Compressed Text Analyser

A running log of how the app was built and why each part is the way it is.
(The project isn't in its own git history yet, so this log reconstructs the
build steps from the code; new entries should be added at the top as the
project evolves.)

---

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
  compression ratio (chars/tokens, guarded against division by zero for empty
  input), and the longest learned token.

## Step 0 — Project setup

- Flask app in a `bpe_thesis/` package with a thin `main.py` entry point that
  adds the package dir to `sys.path` and starts the dev server on **port 5001**
  (5000 is taken by AirPlay on macOS).
- Two bundled samples (`data/sample_english.txt`, `data/sample_code.py`) so
  the app is usable immediately and prose-vs-code compression can be compared.