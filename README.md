# Compressed Text Analyser

This repository contains the source code for the Bachelor thesis *An Analysis of Byte-Pair Encoding*.
The thesis was submitted at the Institute of Theoretical Computer Science, Technische Universität Dresden.

A small Flask web app for running **Byte Pair Encoding (BPE)** experiments on
text. You give it a file and a number **k** (how many merges to perform), and
it reports how far the text compressed: how many tokens are left, how many are
distinct, and how large the vocabulary grew. Every run is stored in a local
SQLite database, so results accumulate and can be plotted against k. It also
finds each input's **k\***, the knee of the utility curve, and compares that
across every input analysed so far.

Built as part of a thesis on compressed text analysis.

---

## Contents

1. [How BPE works](#how-bpe-works)
2. [Worked example](#worked-example)
3. [The rules](#the-rules)
4. [What the app measures](#what-the-app-measures)
5. [k\* and saturation](#k-and-saturation)
6. [Project structure](#project-structure)
7. [File reference](#file-reference)
8. [Running the app](#running-the-app)
9. [Tests](#tests)
10. [Using it](#using-it)
11. [The palette](#the-palette)
12. [Saving figures](#saving-figures)
13. [Storage and deduplication](#storage-and-deduplication)

---

## How BPE works

BPE starts by treating the text as a list of single characters, then repeats
one step k times:

1. Look at every pair of neighbouring tokens (`t`+`h`, `h`+`e`, `e`+` `).
2. Count how often each pair appears.
3. Glue the **most frequent pair** into one new token everywhere it occurs.

Each merge makes the text shorter but the vocabulary larger. Frequent patterns
like `the `, `ing` or `def ` collapse into single tokens quickly. This is the
same idea used by LLM tokenizers, in its simplest character-level form, with no
byte-level encoding and no pretrained merge table.

## Worked example

`"banana bandana"` with k = 3. Start from 14 characters:

```
b a n a n a ␣ b a n d a n a
```

**Round 1.** Pair counts: `(a,n)` 4, `(n,a)` 3, `(b,a)` 2. `(a,n)` wins:

```
b an an a ␣ b an d an a      →  10 tokens
```

**Round 2.** `(b,an)` 2 and `(an,a)` 2 are tied. `Counter.most_common` returns
whichever it encountered first while scanning, here `(b,an)`:

```
ban an a ␣ ban d an a        →  8 tokens
```

**Round 3.** `(an,a)` 2 wins:

```
ban ana ␣ ban d ana          →  6 tokens
```

14 symbols → 6 tokens. Utility = 14 − 6 = **8**. The distinct set is
`{ban, ana, ␣, d}` = **4 distinct tokens**.

Round 1 shows the overlap rule at work: `(a,n)` and `(n,a)` overlap inside
`banana`, and merging scans strictly left to right (rule 6), so `(a,n)` counts
a clean 4.

## The rules

1. **Start from single characters.** The initial tokens are the raw characters
   — spaces, newlines, punctuation, everything. Nothing is lower-cased or
   split into words first, which is why learned tokens often end with a space.
2. **Only adjacent pairs merge.** Two tokens directly next to each other in the
   *current* list. BPE never merges at a distance.
3. **Greedy: merge the single most frequent pair.** One merge per round, no
   look-ahead.
4. **Ties go to "first counted wins."** `Counter.most_common` returns the pair
   it encountered first. This makes runs deterministic: same text and same k
   give an identical result every time, which is what makes the database's
   reuse-the-stored-row rule safe.
5. **A merge applies everywhere at once**, not to one occurrence.
6. **Overlaps resolve left to right.** In `aaa`, a left-to-right scan merges
   positions 0–1 and continues after them, giving `['aa', 'a']`. A token is
   never used in two merges at once.
7. **Stop after k merges.** k is an upper bound, capped at 2000 in the app.
8. **Stop early if the best pair occurs fewer than 2 times.** Merging a
   once-only pair saves exactly one symbol while costing a whole new
   vocabulary entry — a trade not worth making. This is why *merges applied*
   can be lower than k.
9. **Stop if fewer than 2 tokens remain.**
10. **Merges are never undone.** Later merges only combine existing tokens
    into bigger ones.
11. **Tokens are characters, not bytes.** Tokens are Python strings, so an
    emoji or accented letter is one unit.

## What the app measures

Each run is one input text plus one value of k. `bpe.analyse(text, k)` trains
BPE on the text exactly as given and compares the token list after merging
with the text before. Cleaning is decided upstream of this call; `analyse()`
sees only a string.

| Term | How it's computed |
|---|---|
| **k** | The number you typed. Everything else is measured as a function of it. |
| **Merges applied** | `len(merges)` — rounds that actually ran. Below k means the text hit its ceiling (rule 8). |
| **Size (characters)** | `len(text)`. Also the token count at k = 0. |
| **Tokens** | `len(tokens)` remaining after all merges. |
| **Distinct tokens** | `len(set(tokens))` — how many *different* tokens appear at the end. This can go **down** as k rises: merging away the last `q` leaves that character unused. |
| **Vocabulary** | `len(set(text)) + len(merges)` — starting alphabet plus one symbol per merge. A symbol stays counted whether or not the token still appears. |
| **Utility** | U(s,k) = \|s\| − \|s_k\|, the number of symbols saved after k merges. It is a difference of two sequence lengths, not a file size in bytes, and the vocabulary is not counted in bits. Always a non-negative whole number, and lossless — the original text is exactly recoverable from the tokens. |

**Sweeping over k.** With a **sweep step**, the app runs k = 0, step, 2·step, …
up to your k and stores every point. k = 0 is included so results start from
the utility-0 baseline. Utility vs k rises steeply then flattens. Vocabulary vs
k climbs exactly one symbol per merge, then goes flat at the early stop.
Distinct tokens tracks vocabulary at first, then peels away and can fall; the
gap between the two lines is vocabulary you pay for but no longer use, which
is why the results plot draws both.

## k\* and saturation

The utility curve is steep then flat, so the interesting question is how few
merges get you most of the way. The k at that bend — the **knee** — is
**k\***.

**How it's found.** `bpe.analyse_series(text)` runs BPE once and records the
utility after every merge, from k = 0 to saturation. `bpe.find_k_star()`
applies the distance-to-chord method (Satopaa et al., 2011, *Finding a
"Kneedle" in a Haystack*):

1. Scale k to [0, 1] by the largest k, and utility to [0, 1] by the maximum
   utility, so texts of very different sizes are judged on the same footing.
2. Draw the chord from (0, 0) to (1, 1) — the curve you'd get if every merge
   paid off equally.
3. k\* is the k whose point sits **farthest above** that chord.

A single-point curve, or one that compresses nothing, returns k = 0.

**Saturation, k_sat**, is the smallest k at which no pair of adjacent tokens
occurs more than once. Merges are still possible past it — every remaining
pair occurs once, and merging one still saves a symbol — but each buys that
single symbol with a full vocabulary entry, so this is where the run stops.

The per-input plot marks and labels k\* and k_sat on the utility panel, with
the chord drawn as a thin dashed grey line. Marks outside the swept range are
left off rather than allowed to stretch the axes.

**Stored per input** by `bpe.summarize()` in the `file_summary` table and shown
on `/analysis`:

| Field | Meaning |
|---|---|
| `size_chars` | Input size in characters. The x-axis of both cross-file plots. |
| `k_star` (**k\***) | The knee: how many merges before returns visibly diminish. |
| `utility_at_k_star` / `tokens_at_k_star` | Symbols saved and tokens left at k\*. The vocabulary there is not stored — it is the base alphabet plus `k_star`. |
| `max_utility` | Utility at saturation, which is where the run stops — not the largest utility reachable in principle. For english_20k it is 13,222 symbols saved; merging on past saturation, one once-only pair at a time, would eventually reach 17,295. |
| `utility_ratio` | `utility_at_k_star ÷ max_utility` — the share of the run's own compression you get at k\* instead of k_sat. The denominator is utility at saturation, not the theoretical maximum, so this is a fraction of what the run actually reaches. Shown as a decimal to two places (`0.74`), never a percentage. |
| `saturation_k` | k_sat, as defined above. |

**The two cross-file plots** both put **Size (characters)** on the x-axis, with
points coloured by category: **k\* vs Size** and **Utility ratio vs Size**.
Size is on the x-axis so the length confound can be read off directly — if the
code and prose points lie on one line, category adds nothing beyond length.

---

## Project structure

```
main.py                    Entry point — starts the Flask dev server
bpe.py                     BPE algorithm, analyse(), k* detection
app.py                     Flask routes, figures, Save PDF
api.py                     JSON API blueprint (/api/...) with Swagger docs
db.py                      SQLite storage (schema, save/load, dedup)
config.py                  Shared constants (paths, samples, caps)
test_bpe.py                Tests for the k* + summary logic
test_db.py                 Tests for the no-duplicate-rows guarantees
templates/                 base, index, results, analysis, figures
data/
  english.txt              Full English corpus (gitignored)
  python.txt               Full Python corpus (gitignored)
  english_10k.txt …_40k    Size-graded English samples (10k–40k, step 5k)
  python_10k.txt …_40k     Size-graded Python samples (same sizes)
  uploads/                 Copies of uploaded files
figures/                   Vector PDFs written by Save PDF
experiments.db             SQLite database (created on first run)
```

The layering is one-way: `app.py` imports `bpe` and `db`; `bpe.py` and `db.py`
import neither each other nor Flask. So `bpe.analyse("banana bandana", 3)`
can be checked in a shell with no server or database running. The stats dict
from `analyse()` maps 1:1 onto the database columns, so `db.save_experiment()`
consumes it directly.

## File reference

| File | What it does |
|---|---|
| `main.py` | Starts the dev server. **Port 5001, not 5000**: on macOS the AirPlay Receiver holds 5000. |
| `bpe.py` | `train_bpe()` and `_merge_pair()` (the algorithm, including the left-to-right scan that enforces rule 6), `analyse()` (the single place `utility = size_chars - tokens` is defined), `analyse_series()` (the whole curve in one pass, so a k\* search is O(k) not O(k²)), `find_k_star()`, `summarize()`, and the three `normalize*` functions. |
| `db.py` | `connect()` (also runs `CREATE TABLE IF NOT EXISTS`, the whole migration strategy), `input_hash()`, `get_experiment()` / `save_experiment()` (check-then-insert, returning `(row, created)`), `list_inputs()`, `rows_for_input()`, `delete_input()`, and `save_summary()` / `get_summary()` / `get_all_summaries()`. |
| `app.py` | All HTTP: `_resolve_input()` and `_parse_ks()` read the form, `run()` is the controller, `results()` / `analysis()` / `figures()` render pages, and the plot routes stream PNGs from `io.BytesIO` or write PDFs. `MAX_INPUT_CHARS = 200_000` and `MAX_K = 2000` are the safety envelope. |
| `api.py` | JSON API blueprint with Swagger docs at `/apidocs/`. `POST /api/experiments` takes a `clean` parameter and does the same summarize-and-save as `run()`. |
| `config.py` | Paths, `SAMPLE_SIZES`, and the input/k caps. |
| `templates/` | Five Jinja templates extending `base.html`, which holds the flash-message loop, all CSS and the header links to `/analysis` and `/figures`. They contain loops and output only; every number was computed in `bpe.py` and stored by `db.py`. |

**Cleaning.** `normalize_english()` reduces the text to `[a-z0-9]` words
separated by single spaces: line endings become spaces, other non-alphanumerics
are stripped, whitespace runs collapse, the text is trimmed and lowercased.
`normalize_code()` keeps indentation, blank lines, punctuation, case, comments
and docstrings; it standardizes line endings, expands indent tabs to 4 spaces,
collapses space runs after the indentation and strips trailing whitespace. **It
does not protect string literals**: runs of spaces are collapsed inside strings
and docstrings too. `normalize(text, category)` dispatches between the two and
raises on any other category.

`analyse()` does not clean. `normalize()` is called explicitly before any text
reaches it — by `run()`, or by an API caller. The web app always calls it, so
every run through the UI is a run on cleaned text.

**Storage schema.** `experiments` holds one row per (input, k, category) with
every stat as a column, `UNIQUE (input_string, k, category)`, indexed on
`(input_hash, k)`. `category` is a required `CHECK`-constrained enum (`'code'`
or `'english'`) picked by the user, never inferred. `cleaned` is a 0/1
provenance flag, not part of the unique key — cleaning changes the text, so
cleaned and raw versions already differ. `label` is free-text and cosmetic.
`file_summary` is a separate table, one row per (input hash, category), because
a summary is a property of an input, not of a run.

**Figures.** `plot()` draws two charts: Utility vs k, and Vocabulary (solid)
with Distinct tokens (dashed, second colour) vs k. Rows are grouped by
category, so a hash with both draws one line each. `matplotlib.use("Agg")` is
set before `pyplot` is imported. The figure title is the only place
"Cleaned"/"Raw" appears in the UI. `_mark_summary_points()` adds a black dot at
k\*, a black square at k_sat, the dashed grey chord and a dotted vertical line
at k\* on the vocabulary panel — never in the category colour, and never for a
k beyond the largest stored one. The two cross-file plots differ only in the y
column, so their arguments live in one `ANALYSIS_PLOTS` dict shared by the PNG
routes and the Save PDF route; each key is the summary column, the URL segment
and the filename segment.

### `data/`

The bundled samples are **size-graded slices**: consecutive, non-overlapping
cuts from one English corpus (`english.txt`, Shakespeare) and one source-code
corpus (`python.txt`), at 10k, 15k, 20k, 25k, 30k, 35k and 40k characters —
14 samples. The sizes come from `SAMPLE_SIZES` in `config.py`.

The **slices are committed; the two full corpora are not** (they're
gitignored). `config.py` only opens the slices, so a fresh clone has
everything the app runs on.

Two things make this a usable experiment. First, prose vs. source code is the
comparison the thesis cares about; we expected code to be more repetitive, and
§6.5 of the thesis reports what the measurements actually showed — code
compresses slightly more per character. Second, within a category every slice
comes from the *same source at the same register*, so comparing `english_10k`
against `english_25k` varies input size and little else. Non-overlapping
matters for the same reason: overlapping slices would share text, and the
larger sample would inherit the smaller one's merges. One caveat: *All's Well
That Ends Well* is 144,166 characters and the seven slices need 175,000, so
`english_40k` runs past the end of that play into *Antony and Cleopatra*.

`uploads/` holds copies of uploaded files. `figures/` is tracked in git,
unlike `data/uploads/` and `experiments.db`.

---

## Running the app

```bash
.venv/bin/python main.py
```

Then open <http://127.0.0.1:5001>. **Port 5001, not 5000**: on macOS the
AirPlay Receiver listens on 5000.

Three dependencies, pinned in `requirements.txt` and already installed in
`.venv`: **Flask**, **flasgger** (API docs at `/apidocs/`) and **matplotlib**
(plots). `experiments.db` is created automatically on first run, including the
`file_summary` table.

## Tests

```bash
.venv/bin/python test_bpe.py
.venv/bin/python test_db.py
```

Plain `assert`s and a `__main__` block — no pytest.

**`test_bpe.py`** covers the k\* maths: `find_k_star` on a concave curve whose
knee is known by construction (asserted as a range, since the method finds the
bend *region*), its degenerate cases and an internal-consistency check on
`summarize()` (`0 <= k_star <= saturation_k`, `utility_ratio` in [0, 1],
`max_utility >= utility_at_k_star >= 0`). The BPE core is pinned by the
[worked example](#worked-example) above.

**`test_db.py`** covers the no-duplicates guarantees: three runs of one file
leave one summary row and one experiment row per k; the surviving summary is
the newest, compared field by field against a fresh `summarize()`; one text
under two categories stays two rows; deleting an input empties both tables.
Every test points `db.DB_PATH` at a temporary file first.

## Using it

1. Provide a file: **upload** it, or pick a built-in **sample** (English prose
   or Python code, 10k–40k characters). If both are given, the sample wins.
2. Choose a **category** — Source code or English language. Required, never
   inferred: it decides which cleaning rules apply.
3. Choose **k** (up to 2000) and optionally a **sweep step** (0 = a single run
   at k).
4. Click **Run BPE**. It cleans the text with the category's rules and
   analyses the result, then shows the results page: a graph and a table of
   every stored run for that text.
5. Click **Analysis** for every input analysed so far in one table, with k\*,
   utility ratio and both scatter plots. Every run adds to this page
   automatically.
6. Click **Save PDF** next to any graph, and **Saved figures** to get back to
   what you've saved.

Limits: input up to 200,000 characters, k up to 2000.

To compare the two categories' cleaning, run the same file twice with the
category switched. Cleaning changes the text, so each lands on its own results
page; compare them side by side, or as two points on `/analysis`.

Comparing cleaned against **raw** is not possible through the UI, which always
cleans. `POST /api/experiments` with `"clean": false` still does it.

## The palette

Four colours, defined once in `app.py` as `CATEGORY_COLOURS` and
`DISTINCT_TOKEN_COLOURS`, used by every figure:

| Category | Utility, Vocabulary, cross-file points | Distinct tokens |
|---|---|---|
| `code` | blue `#4058B0` | aqua `#1baf7a` |
| `english` | rust `#B05840` | yellow `#eda100` |

A category keeps its colour everywhere, and Distinct tokens gets a second hue
in the same temperature family because it shares a panel and an axis with
Vocabulary; it stays dashed as well, so the two survive a greyscale print.

## Saving figures

Every graph — the per-input pair on a results page, and both cross-file plots
on `/analysis` — has a **Save PDF** button beside its heading. Clicking it
writes that graph into `figures/` as a vector PDF and flashes a confirmation.
The PDF and the on-screen PNG come from the same figure-building function.

**Filenames are stable, so saving twice replaces rather than accumulates.** A
cross-file plot saves as `analysis_k_star.pdf` or
`analysis_utility_ratio.pdf`; a per-input plot as
`results_<label>_<hash8>.pdf`. The hash fragment is there because labels
aren't unique, and `_safe_stem()` reduces the label to `[A-Za-z0-9_-]` first.

The **Saved figures** page (`/figures`) lists everything saved, newest first,
with save time and size. Each name links to the PDF; each row has a delete
button.

## Storage and deduplication

- Each experiment row is **unique on (input text, k, category)**. Re-running
  the same text with the same k and category reuses the stored row; the flash
  message reports how many rows were new vs. already stored. Category is part
  of the key because the same text produces different stats under each
  category's cleaning rules.
- Inputs are grouped by a short **SHA-256 hash** of the text, so the same file
  submitted twice — even under a different filename or category — lands on the
  same results page, which can show rows from both categories side by side. A
  cleaned and a raw run hash differently and get separate pages.
- Deleting an input removes **all** its runs, across both categories, **and**
  its summary row, so it leaves the results page and `/analysis` together.
- `file_summary` is written on every run with `INSERT OR REPLACE`, so
  re-running updates a summary in place. Nothing here is deduplicated
  *against* — it is derived data, always recomputed.
- **Re-running a file changes nothing on the analysis page.** One input
  contributes exactly one summary row and one experiment row per k, however
  many times it is run. `test_db.py` pins this. The intended exception is
  category: the same text as both `code` and `english` is two summaries by
  design, and two points — that's the comparison, not a duplicate.
- Inputs analysed **before** the `file_summary` table existed have no summary
  and don't appear on `/analysis` until they're run once more; the re-run
  writes exactly the row they would have had.
