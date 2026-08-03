# Compressed Text Analyser

A small Flask web app for running **Byte Pair Encoding (BPE)** experiments on
any text. Give it some text and a number **k** (how many merges to perform),
and it reports how well BPE compresses that text: how many tokens are left,
how big the learned vocabulary grew, and what the longest learned token looks
like. Every run is saved to a local SQLite database so results can be
compared and plotted against k.

Built as part of a thesis on compressed text analysis.




---

## Table of contents

1. [How BPE works](#how-bpe-works)
2. [Worked example](#worked-example)
3. [The rules](#the-rules)
4. [What the app measures](#what-the-app-measures)
5. [Project structure](#project-structure)
6. [Architecture](#architecture)
7. [File-by-file reference](#file-by-file-reference)
8. [Running the app](#running-the-app)
9. [Using it](#using-it)
10. [Data storage and deduplication](#data-storage-and-deduplication)

---

## How BPE works

Byte Pair Encoding starts by treating the text as a list of single
characters, then repeats one simple step, k times:

1. Look at every pair of neighbouring tokens (e.g. `t`+`h`, `h`+`e`, `e`+` `).
2. Count how often each pair appears.
3. Take the **most frequent pair** and glue it together into one new token,
   so `t` + `h` becomes `th` everywhere the two appear side by side.

Each merge makes the text shorter (fewer tokens) but the vocabulary larger
(one new token per merge). Frequent patterns like `the `, `ing`, or `def `
get merged into single tokens quickly — that's the "compression."

This is the same core idea used by tokenizers in large language models
(GPT, Llama, etc.), just in its simplest character-level form, with no
byte-level encoding or pretrained merge table.

## Worked example

Take the string `"banana bandana"` and run it with k = 3.

**Step 0 — start from characters.** `list("banana bandana")` gives 14 tokens:

```
b a n a n a ␣ b a n d a n a
```

**Round 1 — count every adjacent pair.**

| Pair | Count |
|---|---|
| `(a,n)` | 4 |
| `(n,a)` | 3 |
| `(b,a)` | 2 |

`(a,n)` wins. Merge every occurrence:

```
b an an a ␣ b an d an a      →  10 tokens
```

**Round 2 — recount on the new tokens.**

| Pair | Count |
|---|---|
| `(b,an)` | 2 |
| `(an,a)` | 2 |

`Counter.most_common` returns whichever of the tied pairs it *encountered
first* while scanning the token list — here that's `(b,an)`, whose first
occurrence (position 0) comes before `(an,a)`'s first occurrence (position
2). Merge it:

```
ban an a ␣ ban d an a        →  8 tokens
```

**Round 3 — recount again.**

| Pair | Count |
|---|---|
| `(an,a)` | 2 |

`(an,a)` wins. Merge it:

```
ban ana ␣ ban d ana          →  6 tokens
```

**After 3 merges:** 14 characters → 6 tokens.

- **Utility** (characters saved) = 14 − 6 = **8**
- **Vocabulary** — the final tokens are `ban, ana, ␣, ban, d, ana`, so the
  distinct set is `{ban, ana, ␣, d}` = **4 distinct tokens**
- **Longest token** = `ban` (the first token of length 3 found)

Note how round 1 has an interesting subtlety: `(a,n)` and `(n,a)` overlap
inside `banana`, and merging is resolved strictly left to right (see rule 6
below) — that's why `(a,n)` wins with a clean count of 4 even though the
substring `anana` looks like it could be read either way.

## The rules

These are every rule the implementation follows — they decide what gets
merged, when it stops, and how ties and edge cases are handled:

1. **Start from single characters.** The initial tokens are the raw
   characters of the text — spaces, newlines, punctuation, everything.
   Nothing is lower-cased or split into words first, which is why learned
   tokens often end with a space (e.g. `the `).
2. **Only adjacent pairs can merge.** A pair means two tokens directly next
   to each other in the *current* list. BPE never merges tokens at a
   distance.
3. **Greedy choice: always merge the single most frequent pair.** One merge
   per round, no look-ahead. BPE never asks "would a different merge pay off
   more two steps from now?" — it just takes the current best. That greedy
   simplicity is the whole algorithm.
4. **Tie-breaking is "first counted wins."** If two pairs have the same
   count, `Counter.most_common` returns the one it encountered first. Ties
   are rare in real text, but this makes runs fully deterministic: same text
   + same k ⇒ identical result, every time. That determinism is also what
   makes the database's "reuse the stored row" dedup rule safe.
5. **A merge applies everywhere at once.** When a pair wins, *every*
   occurrence of it in the text is merged in that round, not just one.
6. **Overlaps resolve left to right.** In `aaa`, the pair `(a,a)` occurs
   twice but the occurrences overlap. A left-to-right scan merges positions
   0–1 and then continues *after* them, so the result is `['aa', 'a']` — a
   token is never used in two merges at once.
7. **Stop after k merges.** k is an upper bound you choose (capped at 2000
   in the app).
8. **Stop early if the best pair occurs fewer than 2 times.** Merging a pair
   that appears once would just rename two tokens as one — the vocabulary
   grows but nothing repeats, so nothing is really compressed. This rule is
   why *merges applied* can be smaller than k, and it gives every text a
   natural ceiling: once no pair repeats, more k changes nothing.
9. **Stop if fewer than 2 tokens remain.** A text that has collapsed into a
   single token (or was empty to begin with) has no pairs left to merge.
10. **Merges are never undone.** Once glued, a token stays glued; later
    merges can only combine existing tokens into bigger ones.
11. **Characters, not bytes.** Tokens are Python strings, so an emoji or
    accented letter is one unit. GPT-style tokenizers work on raw bytes
    instead; the character version is simpler and better suited to
    analysing text structure.

## What the app measures

For each run (one input text + one value of k) the app calls
`bpe.analyse(text, k)`, which trains BPE and then compares the token list
*after* merging with the text *before* merging. Everything reported comes
from that before/after comparison:

| Term | How it's computed | Why it matters |
|---|---|---|
| **k** | The number you typed in the form. | The independent variable of the experiment — everything else is measured *as a function of k*. |
| **Merges applied** | `len(merges)` — the number of rounds that actually ran. | Shows whether the text hit its natural ceiling (rule 8) before reaching k. If this is below k, raising k further changes nothing for this text. |
| **Chars** | `len(text)` — characters in the input. | The baseline. It's also the token count at k = 0, which anchors the utility at exactly 0. |
| **Tokens** | `len(tokens)` — tokens remaining after all merges. | The direct measure of compression: every successful merge round removes one token per occurrence of the winning pair. |
| **Vocab** | `len(set(tokens))` — number of *distinct* tokens in the final list. | The cost side of the trade-off. Compressing isn't free: each merge can add a new symbol you'd need in your "dictionary" to decode the text. Real tokenizers care about exactly this number. |
| **Utility** | `chars − tokens`, i.e. U(s,k) = \|s\| − \|s_k\| — the number of characters saved after k merges. | The headline number. 0 = untouched; higher means better compression. Always a non-negative whole number, and a *lossless* measure — the original text is always exactly recoverable from the tokens. |
| **Longest token** | The longest string in the final vocabulary. | A qualitative window into what BPE learned. In prose it's usually a frequent word with its space (`the `); in code it can be a whole keyword or repeated snippet (`def `, `return `). |

### Why sweep over k instead of running once?

A single run tells you one point; the shape of the curve is where the
insight is. With a **sweep step**, the app runs k = 0, step, 2·step, … up to
your k (k = 0 included on purpose, so the results start from the
utility-0 baseline), and stores every point so they can be compared:

- **Utility vs k** rises steeply at first — the earliest merges grab the
  most frequent pairs, which save the most characters — then flattens as
  only rare pairs are left. Classic diminishing returns.
- **Vocabulary vs k** climbs roughly one token per merge until the early
  stop kicks in, then goes flat.

Read together, the two curves show the fundamental BPE trade-off: **you buy
a shorter text by paying with a bigger vocabulary.** Comparing the curves of
different inputs (prose vs code, short vs long) shows how the *structure* of
a text determines how compressible it is — which is the question this
analyser exists to explore.

---

## Project structure

```
main.py                    Entry point — starts the Flask dev server
bpe.py                     The BPE algorithm + the analyse() stats function
app.py                     Flask routes: form handling, running experiments
db.py                      SQLite storage (schema, save/load, dedup logic)
templates/
  base.html                Shared layout + all CSS
  index.html               Home page: input form + list of stored inputs
  results.html             Results page: stats table + input preview
data/
  sample_english.txt       Built-in English prose sample
  sample_code.py           Built-in Python-code sample
  uploads/                 Copies of uploaded files (created on first upload)
experiments.db             SQLite database (created automatically on first run)
```

## Architecture

The app is a small **three-layer design**, one file per layer, plus
templates:

```
main.py    →  starts the server           (knows nothing about BPE)
bpe.py     →  the algorithm                (knows nothing about Flask or SQLite)
db.py      →  the storage                  (knows nothing about Flask or BPE)
app.py     →  the web glue                 (imports both, owns all HTTP concerns)
templates/ →  the presentation             (HTML + loops, no logic)
```

The dependency arrows only point one way: `app.py` imports `bpe` and `db`,
but `bpe.py` and `db.py` import neither each other nor Flask. That
separation matters for two reasons:

- **The algorithm is testable in isolation.** You can open a Python shell,
  `import bpe`, and check `bpe.analyse("banana bandana", 3)` by hand without
  a server or database running — important when the numbers need to hold up
  in a thesis.
- **Each file has one reason to change.** A new metric touches `bpe.py` (and
  a column in `db.py`); a new page touches `app.py` and a template; a schema
  change touches only `db.py`.

The stats dict returned by `bpe.analyse()` is the contract between layers:
its keys map 1:1 onto the database columns, so `db.save_experiment()` can
consume it directly with no field-mapping code.

## File-by-file reference

### `main.py`

```python
from app import app
app.run(debug=True, port=5001)
```

Every module lives flat at the project root, so `app.py` can say `import
bpe` and `import db` as plain top-level modules — no package, no path
manipulation. **Port 5001, not 5000**: on macOS the AirPlay Receiver listens
on port 5000, so Flask's default port silently collides with it.
`debug=True` is appropriate here because this is a local, single-user
research tool — it gives auto-reload on edit and real tracebacks in the
browser.

### `bpe.py` — the algorithm

- **`_merge_pair(tokens, pair)`** — returns a new token list with every
  occurrence of `pair` glued into one token. It's a single left-to-right
  scan: when the pair is found at position `i`, append the merged token and
  jump `i += 2`; otherwise copy one token and `i += 1`. The `i += 2` jump is
  what encodes the *overlap rule* (rule 6): a token can never participate in
  two merges in the same round. It returns a new list rather than mutating
  in place, so each round is a pure function of the previous one — the
  leading underscore marks it as an internal helper.

- **`train_bpe(text, k)`** — the training loop itself:

  ```python
  tokens = list(text)
  for _ in range(k):
      if len(tokens) < 2:
          break
      pairs = Counter(zip(tokens, tokens[1:]))
      best, count = pairs.most_common(1)[0]
      if count < 2:
          break
      merges.append(best)
      tokens = _merge_pair(tokens, best)
  ```

  Each line embodies one rule from [The rules](#the-rules): `list(text)` is
  the k = 0 state; `Counter(zip(tokens, tokens[1:]))` counts every adjacent
  pair by sliding a two-token window over the list; `most_common(1)[0]` is
  the greedy choice and the tie-break in one call; `if count < 2: break` is
  the early stop that prevents the vocabulary from growing with merges that
  don't actually compress anything. Recounting pairs from scratch every
  round is O(n) per merge — real tokenizer implementations avoid this with
  incremental counters — but the naive version is simple to verify by hand
  and comfortably handles this app's 200k-char / k ≤ 2000 limits.

- **`analyse(text, k)`** — the bridge between algorithm and application:
  trains BPE, then derives every reported stat from the before/after
  comparison. It exists as its own function (rather than letting `app.py`
  call `train_bpe` directly) so there is exactly one place in the codebase
  that defines what each number means — `utility` is
  `original_len - token_count`, computed here and nowhere else.
  `longest_token` uses `max(..., default="")` so an empty input yields an
  empty string instead of a crash.

### `db.py` — storage (the experiment ledger)

The purpose of this file is to make experiments **cumulative and
non-duplicated**: every run ever made is queryable, and re-running never
creates a second copy. SQLite was chosen because it's a single file with
zero setup.

- **The schema** — one table, `experiments`, one row per (input, k) run,
  with every stat as a column. `UNIQUE (input_string, k)` enforces
  no-duplicate-experiments at the database level, as a backstop behind the
  application-level check. `CREATE INDEX ... ON (input_hash, k)` makes "all
  rows for this input, ordered by k" — the query every page needs — fast.

- **`connect()`** — opens the connection, sets `row_factory = sqlite3.Row`
  (so templates can say `r['utility']` instead of a tuple index), and runs
  `CREATE TABLE IF NOT EXISTS` on every connect. That single statement is
  the entire migration strategy: the app never has an "uninitialized
  database" state.

- **`input_hash(text)`** — first 16 hex characters of the SHA-256 of the
  text. This is the app's addressing scheme: results pages live at
  `/results/<ihash>`, so the same text pasted twice (even under different
  labels) hashes to the same address and lands on the same results page.

- **`get_experiment(conn, text, k)`** — exact-match lookup used for dedup,
  matched on the full `input_string`, not the hash, so a hash collision
  could never cause one text's results to silently overwrite another's.

- **`save_experiment(conn, label, text, stats)`** — check-then-insert,
  returning a `(row, created)` pair. `app.py` sums the boolean across a
  sweep to report "N new, M already stored" in the flash message.

- **`list_inputs(conn)`** — one `GROUP BY input_hash` query that powers the
  home page's "stored inputs" table (run count, max k, last-run time),
  newest-first.

- **`rows_for_input(conn, ihash)`** — all runs for one input, `ORDER BY k`,
  which is what lets the results table read left-to-right in increasing k.

- **`delete_input(conn, ihash)`** — deletes every run for an input hash at
  once. There's deliberately no per-row delete — the meaningful unit of
  work in this app is "an input and its whole sweep," not an individual row.

### `app.py` — the Flask layer

`app.py` owns everything HTTP: forms in, pages out. It contains no
algorithm and no SQL beyond calls into `db.py`. Two module-level constants,
`MAX_INPUT_CHARS = 200_000` and `MAX_K = 2000`, are the app's safety
envelope — the naive O(n)-per-merge algorithm stays comfortably fast inside
these caps.

- **`_resolve_input()`** — turns the three input mechanisms (paste, upload,
  sample) into one `(label, text)` pair, with priority **sample > upload >
  paste**. Uploads are decoded as UTF-8 with `errors="replace"`, so a
  binary or oddly-encoded file degrades into replacement characters instead
  of a server error. A copy of every upload is kept in `data/uploads/` so
  the exact file behind an experiment can be revisited later. The label for
  pasted text is just its first 30 characters — the label is only a
  human-friendly handle; the text's content hash is what actually identifies
  it.

- **`_parse_ks()`** — converts the form's k and step into the list of k
  values to run. `step = 0` means a single run at `k`; `step > 0` means
  `range(0, k_max + 1, step)`, starting at k = 0 on purpose so results
  always include the utility-0 baseline. Out-of-range values are clamped
  (`max(0, min(k_max, MAX_K))`) rather than rejected.

- **`index()`** — the home page: one query for the stored-inputs list,
  render.

- **`run()`** — the POST handler and the app's one real "controller." It
  resolves the input, validates it (empty, too large, non-numeric k — each
  with a flash message and a redirect rather than a server error), then for
  each k in the sweep checks the database first and skips work already
  done. This check-before-compute loop is what makes sweeps incremental: a
  second sweep with a finer step only computes the new k values, and
  identical re-runs cost one `SELECT` each. It finishes by redirecting to
  `/results/<hash-of-text>` — the content hash, not a row id — so refreshing
  the results page never re-submits the form.

- **`results(ihash)`** — fetches the rows (404 if the hash is unknown — the
  honest answer for a stale bookmark after a delete) and renders the table
  plus a 400-character preview of the input.

- **`delete(ihash)`** — POST-only, because anything that destroys data must
  never be reachable by a GET (browsers and crawlers can prefetch links). A
  browser-side `confirm()` dialog in the template is the second guard.

### `templates/` — the presentation layer

Three Jinja templates extending one base, with all CSS inline in a
`<style>` block in `base.html` — at this size, a separate stylesheet buys
nothing.

- **`base.html`** — the shared skeleton: page title, the flash-message loop
  (where every guardrail message from `run()` surfaces), and all styling.
  The `.num` class right-aligns numbers with `font-variant-numeric:
  tabular-nums`, since the UI is mostly tables of numbers meant to be
  compared down a column.
- **`index.html`** — one form containing all three input methods plus the k
  and step fields, and the stored-inputs table with per-input delete
  buttons. Keeping paste/upload/sample in a single form (rather than tabs)
  is what makes the fixed priority order in `_resolve_input()` the only
  conflict-resolution logic needed.
- **`results.html`** — the stats table (one row per k) and the input
  preview. The template contains loops and output only — every number it
  prints was computed in `bpe.py` and stored by `db.py`, so the view layer
  can't introduce a discrepancy.

### `data/`

`sample_english.txt` and `sample_code.py` exist so the app is useful within
seconds of first launch, with zero input preparation — and the choice isn't
arbitrary: prose vs. source code is the comparison the thesis cares about
(code tends to be more repetitive, so it compresses better, and the two
samples make that visible immediately). `uploads/` holds retained copies of
uploaded files; `experiments.db` is created here automatically on first run.

---

## Running the app

```bash
.venv/bin/python main.py
```

Then open <http://127.0.0.1:5001>.

Dependency: Flask (already installed in `.venv`). The SQLite database
(`experiments.db`) is created automatically on first run.

## Using it

1. Provide text one of three ways: **paste** it, **upload** a file, or pick
   a built-in **sample** (English prose or Python code). If more than one is
   given, priority is: sample → upload → pasted text.
2. Choose **k** (max merges, up to 2000) and optionally a **sweep step**
   (0 means a single run at k).
3. Click **Run analysis**. You land on the results page with a table of
   every stored run for that input.

Limits: input up to 200,000 characters, k up to 2000.

## Data storage and deduplication

- Each experiment row is **unique on (input text, k)**. Re-running the same
  text with the same k reuses the stored row instead of inserting a
  duplicate — the flash message reports how many rows were new vs. already
  stored.
- Inputs are grouped by a short **SHA-256 hash** of the text, so the same
  text pasted twice (even with different labels) lands on the same results
  page.
- Deleting an input removes **all** of its stored runs.