# Compressed Text Analyser

A small Flask web app for running **Byte Pair Encoding (BPE)** experiments on
any text. Give it some text and a number **k** (how many merges to perform),
and it reports how well BPE compresses that text: how many tokens are left,
how big the learned vocabulary grew, and what the longest learned token looks
like. Every run is saved to a local SQLite database so results can be
compared and plotted against k. It also finds each input's **elbow** — the
k where extra merges stop paying for themselves — and plots that across
every input analysed so far, so prose and code can be compared directly.

Built as part of a thesis on compressed text analysis.

---

## Table of contents

1. [How BPE works](#how-bpe-works)
2. [Worked example](#worked-example)
3. [The rules](#the-rules)
4. [What the app measures](#what-the-app-measures)
5. [The elbow: where merges stop paying off](#the-elbow-where-merges-stop-paying-off)
6. [Project structure](#project-structure)
7. [Architecture](#architecture)
8. [File-by-file reference](#file-by-file-reference)
9. [Running the app](#running-the-app)
10. [Tests](#tests)
11. [Using it](#using-it)
12. [Data storage and deduplication](#data-storage-and-deduplication)

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
`bpe.analyse(text, k)`, which trains BPE on `text` exactly as given and
then compares the token list *after* merging with the text *before*
merging. Whether `text` has been cleaned first is decided entirely
upstream of this call (see "Cleaning is a separate step," below) —
`analyse()` itself has no opinion on it. Everything reported comes from
that before/after comparison:

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

## The elbow: where merges stop paying off

The utility curve always has the same shape — steep, then flat — so the
interesting question isn't "how much can this text compress" but **"how few
merges get you most of the way there."** That bend in the curve is the
**elbow**, and the app computes it per input, then compares it across
inputs on the `/analysis` page.

**How it's found.** `bpe.analyse_series(text)` runs BPE once and records
the utility after *every* merge, from k = 0 to saturation (the point where
no pair repeats and further merges are impossible). `bpe.find_elbow_k()`
then takes that list of utilities and applies the knee / distance-to-chord
method (Satopaa et al., 2011, *Finding a "Kneedle" in a Haystack*):

1. Scale k to [0, 1] by dividing by the largest k, and utility to [0, 1] by
   dividing by the maximum utility — this makes the curve fit in a unit
   square, so a 200-character text and a 200,000-character one are judged
   on the same footing.
2. Draw the straight chord from (0, 0) to (1, 1) — that's what the curve
   would look like if every merge paid off equally, i.e. no bend at all.
3. The elbow is the k whose point sits **farthest above** that chord — the
   point of maximum "you're ahead of a linear pace here."

A single-point curve, or one that compresses nothing at all, has no
meaningful bend, so both return k = 0.

**Why the chord and not curvature.** The utility curve is a discrete
sequence of integers, so numerical second derivatives on it are noisy and
would need smoothing parameters chosen by hand. The chord distance is one
subtraction per point, has nothing to tune, and is deterministic — the same
text always gives the same elbow.

**What's reported per input** (`bpe.summarize()`, stored in the
`file_summary` table, shown on `/analysis`):

| Field | Meaning |
|---|---|
| **`size_chars` / `size_words`** | Input size, the first thing any cross-file comparison has to control for. |
| **`base_alphabet`** | Number of distinct characters — the vocabulary BPE starts from, before any merge. |
| **`unique_words` / `type_token_ratio`** | Distinct words, and distinct ÷ total. A rough lexical-repetition measure that's independent of BPE, useful as a sanity check against what BPE finds. |
| **`elbow_k`** | The knee: how many merges before returns visibly diminish. |
| **`utility_at_elbow` / `tokens_at_elbow` / `vocab_at_elbow`** | The state of the text at that k — characters saved, tokens left, vocabulary size (`base_alphabet + elbow_k`). |
| **`max_utility`** | Utility at saturation — the most this text can ever be compressed by BPE. |
| **`pct_captured_at_elbow`** | `utility_at_elbow ÷ max_utility`. **The headline number**: the share of all available compression you get for `elbow_k` merges instead of `saturation_k`. |
| **`longest_token_at_elbow`** | The longest token learned by the elbow — a qualitative peek at *what* the useful merges actually captured. |
| **`saturation_k`** | Where merging stops being possible at all (rule 8). |

**The two cross-file plots**, both with input size on the x-axis and points
coloured by category (the same blue/red as the per-input plot):

- **Elbow k vs input size** — does the point of diminishing returns depend
  mostly on how long a text is, or on what kind of text it is? Size is on
  the x-axis specifically so that confound can be read off directly: if the
  code and prose points lie on the same line, the category isn't adding
  anything beyond length.
- **Utility captured at elbow vs input size** — how good a deal the elbow
  is, per input. A high value means a small vocabulary buys nearly all of
  the available compression.

---

## Project structure

```
main.py                    Entry point — starts the Flask dev server
bpe.py                     The BPE algorithm, analyse(), and elbow detection
app.py                     Flask routes: form handling, running experiments
api.py                     JSON API blueprint (/api/...) with Swagger docs
db.py                      SQLite storage (schema, save/load, dedup logic)
config.py                  Shared constants (paths, samples, input/k caps)
test_bpe.py                Plain-assert tests for the elbow + summary logic
test_db.py                 Tests for the no-duplicate-rows guarantees
templates/
  base.html                Shared layout + all CSS
  index.html               Home page: input form + list of stored inputs
  results.html             Results page: stats table + input preview
  analysis.html            Cross-file page: summary table + comparison plots
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
  in a thesis. `test_bpe.py` does exactly this for the elbow logic: it
  imports `bpe` and nothing else, no server, no database, no fixtures.
- **Each file has one reason to change.** A new metric touches `bpe.py` (and
  a column in `db.py`); a new page touches `app.py` and a template; a schema
  change touches only `db.py`.

The stats dict returned by `bpe.analyse()` is the contract between layers:
its keys map 1:1 onto the database columns, so `db.save_experiment()` can
consume it directly with no field-mapping code. `bpe.summarize()` and the
`file_summary` table follow the same convention — one flat dict, one row,
no translation layer in between.

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

- **`normalize_whitespace(text)` / `normalize_code(text)` / `normalize(text,
  category)`** — cleaning rules that run before training, chosen by
  `category` rather than applied uniformly, because code and prose have
  different notions of "noise."

  `normalize_whitespace` (`category="english"`) reduces the text to
  `[a-z0-9]` words separated by exactly one space: line endings become
  spaces (not removed — a line break is usually just wrapping, not
  meaningful structure, so words on either side of it must stay
  separated); every character that isn't a letter, digit, space, or tab
  is stripped (punctuation, quotes, brackets, dashes, …); whitespace runs
  collapse to one space; the whole text is trimmed and lowercased.

  `normalize_code` (`category="code"`) preserves everything structurally
  or semantically significant to source: leading indentation (beyond
  expanding tabs to 4 spaces, so tab- and space-indented code look
  identical to BPE), blank lines (never merged or removed — a change
  from an earlier version of this function, which used to collapse 3+
  blank lines; that turned out to destroy information a user comparing
  code compression might actually want), punctuation/operators, case,
  comments, and docstrings. It only standardizes line endings, expands
  indentation tabs, collapses space runs *after* the indentation
  (`x   =   1` → `x = 1` — inter-symbol spacing carries no meaning), and
  strips trailing whitespace. It does not special-case string-literal
  contents — reliably telling "inside a string" from "outside a string"
  needs real parsing, not a regex, so a string literal's internal spacing
  gets collapsed like anywhere else; BPE just compresses whatever
  survives instead of the rule trying to protect it.

  `normalize()` is a thin dispatcher between the two, raising on any
  other category value.

  **Cleaning is a separate step, not something `analyse()` does.** Earlier
  versions of this app had `analyse()` normalize internally behind a
  `clean` flag, which made "cleaned" part of an experiment's stored
  identity alongside `category` and let one raw input balloon into up to
  four rows (two categories × cleaned/raw). That's gone: `normalize()` is
  called explicitly, by the `/clean` route (see `app.py` below) or by an
  API caller, *before* any text ever reaches `analyse()`. Cleaning and
  analysing are two unrelated actions on two potentially-different pieces
  of text, not two modes of the same action.

- **`analyse(text, k)`** — the bridge between algorithm and application:
  trains BPE on `text` exactly as given, then derives every reported stat
  from the before/after comparison. It exists on its own (rather than
  letting `app.py` call `train_bpe` directly) so there is exactly one
  place in the codebase that defines what each number means — `utility`
  is `original_len - token_count`, computed here and nowhere else.
  `longest_token` uses `max(..., default="")` so an empty input yields an
  empty string instead of a crash. `original_len` is always `len(text)`
  for whatever was actually passed in — since cleaning happens (or
  doesn't) before this function is ever called, a cleaned and a raw
  version of the same source simply arrive as two different strings with
  two different lengths, rather than this function needing to know or
  care which one it's looking at.

- **`analyse_series(text)`** — the whole utility curve in one pass: runs
  BPE from single characters and records a stats row (`k`, `token_count`,
  `utility`, `active_types`, `learned_vocab`, `longest_token`) after every
  merge, stopping at the same natural point as `train_bpe`. It exists
  because the alternative — calling `analyse(text, k)` once per k — retrains
  from scratch every time, turning an O(k) walk into O(k²) work for a curve
  the single pass already passes through. It also yields *every* k, not
  just a sweep's step points, which is what makes locating an exact elbow
  possible. The first row is k = 0 (the untouched character list), so the
  series always starts from the utility-0 baseline.

- **`find_elbow_k(utilities)`** — the knee finder described in
  [The elbow](#the-elbow-where-merges-stop-paying-off) above: normalize
  both axes to [0, 1], return the k farthest above the (0,0)–(1,1) chord.
  It takes a plain list of numbers rather than the series dicts on purpose
  — that makes it a pure function of a curve, with no dependency on BPE or
  anything else in the app, so it can be tested on hand-written curves whose
  answer is known by construction (see `test_bpe.py`). `k_max == 0` or
  `u_max == 0` return 0: a one-point curve, or a text that compresses
  nothing, has no bend to find.

- **`summarize(text, category, label)`** — combines the two into the flat
  dict `db.save_summary()` stores, one row per input: size stats, the
  elbow point, the saturation k, and `pct_captured_at_elbow`. Same
  convention as `analyse()` — the caller normalizes the text first; this
  function has no opinion on cleaning. Every field is listed in
  [The elbow](#the-elbow-where-merges-stop-paying-off).

### `db.py` — storage (the experiment ledger)

The purpose of this file is to make experiments **cumulative and
non-duplicated**: every run ever made is queryable, and re-running never
creates a second copy. SQLite was chosen because it's a single file with
zero setup.

- **The schema** — one table, `experiments`, one row per (input, k,
  category) run, with every stat as a column. `category` is a required,
  validated enum (`'code'` or `'english'`, enforced by a `CHECK`
  constraint) that the user picks explicitly at submission time — it's
  never inferred from the text. `cleaned` is a 0/1 flag (also
  `CHECK`-constrained) recording whether the stored text passed through
  the cleaning rules before this row was saved — pure provenance, kept so
  the results page can label a plot "Cleaned" or "Raw." Both `category`
  and `cleaned` are distinct from `label`, which stays a free-text,
  purely cosmetic handle with no effect on results — but only `category`
  is part of an experiment's *identity*. `cleaned` deliberately is **not**
  in the `UNIQUE` constraint: cleaning a text changes the text itself
  (that's the whole point of `/clean` — see `app.py` below), so a cleaned
  and a raw version of the same source already have different
  `input_string`s and can never collide even without `cleaned` in the
  key. `UNIQUE (input_string, k, category)` enforces no-duplicate-
  experiments at the database level, as a backstop behind the
  application-level check — the same text can still legitimately be
  analysed under both categories, so `category` stays in the uniqueness
  key. `CREATE INDEX ... ON (input_hash, k)` makes "all rows for this
  input, ordered by k" — the query every page needs — fast.

- **`connect()`** — opens the connection, sets `row_factory = sqlite3.Row`
  (so templates can say `r['utility']` instead of a tuple index), and runs
  `CREATE TABLE IF NOT EXISTS` on every connect. That single statement is
  the entire migration strategy: the app never has an "uninitialized
  database" state.

- **`input_hash(text)`** — first 16 hex characters of the SHA-256 of the
  text. This is the app's addressing scheme: results pages live at
  `/results/<ihash>`, so the same file submitted twice (even under a
  different filename or category) hashes to the same address and lands on the same
  results page — a hash's results page can therefore show rows from both
  categories side by side, though never a mix of cleaned and raw, since
  those are different text and so different hashes entirely.

- **`get_experiment(conn, text, k, category)`** — exact-match lookup used
  for dedup, matched on the full `input_string` plus `k` and `category`,
  not the hash, so a hash collision could never cause one text's results
  to silently overwrite another's.

- **`save_experiment(conn, label, category, cleaned, text, stats)`** —
  check-then-insert, returning a `(row, created)` pair. `app.py` sums the
  boolean across a sweep to report "N new, M already stored" in the flash
  message. `cleaned` is stored but, per above, plays no role in the
  check — it's just carried along for display.

- **`list_inputs(conn)`** — one `GROUP BY input_hash, category` query that
  powers the home page's "stored inputs" table (run count, max k, last-run
  time), newest-first. The same text run under both categories appears as
  two rows here, since the stats genuinely differ per category.

- **`rows_for_input(conn, ihash)`** — all runs for one input,
  `ORDER BY category, k`, which is what lets the results table read
  left-to-right in increasing k within each category's block, rather than
  interleaving the two categories when a hash has both.

- **`delete_input(conn, ihash)`** — deletes every run for an input hash at
  once, across both categories if the hash has rows in both. There's
  deliberately no per-row or per-category delete — the meaningful unit of
  work in this app is "an input and its whole sweep," not an individual row.
  It clears the input's `file_summary` row in the same call — the summary is
  derived from the experiments, so it must never outlive them and leave a
  deleted input listed on `/analysis`.

- **The `file_summary` table** — one row per (input hash, category), holding
  everything `bpe.summarize()` returns. It's a *separate table*, not extra
  columns on `experiments`, because a summary is a property of an input,
  not of an (input, k) run: storing it per row would repeat identical values
  once per sweep point and leave it ambiguous which copy is authoritative.

- **`save_summary(conn, ihash, summary)`** — `INSERT OR REPLACE` against
  `UNIQUE (input_hash, category)`, so re-running a file refreshes its
  summary in place instead of accumulating stale copies. Replacing is
  always safe here because the summary is derived data — a cache of what
  the current text implies, never something the user typed.

- **`get_all_summaries(conn)`** — every summary row, `ORDER BY category,
  size_chars`, which is the order the `/analysis` table and both scatter
  plots read most naturally: categories grouped, and within each, small
  inputs before large ones.

### `app.py` — the Flask layer

`app.py` owns everything HTTP: forms in, pages out. It contains no
algorithm and no SQL beyond calls into `db.py`. Two module-level constants,
`MAX_INPUT_CHARS = 200_000` and `MAX_K = 2000`, are the app's safety
envelope — the naive O(n)-per-merge algorithm stays comfortably fast inside
these caps.

- **`_resolve_input()`** — turns the form into a
  `(label, text, category, cleaned)` tuple. There are exactly **two ways to
  supply text: upload a file, or pick a bundled sample** — there's no paste
  box. (Pasting existed once and was removed: this is a tool for analysing
  *files*, and a textarea invited ad-hoc snippets that clutter the stored-
  inputs list without being reproducible later.) A third source exists but
  isn't user-typed input — the cleaned text carried back from a previous
  **Clean** click in a hidden field — and the priority is
  **sample > upload > carried cleaned text**, so picking a new source after
  cleaning analyses the new source rather than stale text. `cleaned` is
  derived from *which* source won rather than from a form flag, so a row
  can't be mislabelled as cleaned. The carrier's line endings are
  re-normalized on the way back in, since a hidden field round-trip can
  turn `\n` into `\r\n` and the analysed text must be byte-identical to the
  text just shown. Uploads are decoded as UTF-8 with
  `errors="replace"`, so a binary or oddly-encoded file degrades into
  replacement characters instead of a server error. A copy of every upload
  is kept in `data/uploads/` so the exact file behind an experiment can be
  revisited later. The label is the sample name or the uploaded filename,
  and a Clean click carries that same label through so a cleaned run stays
  recognisable — the label is only a human-friendly handle either way; the
  text's content hash is what actually identifies it. `category` comes from a
  required form field and is read the same way regardless of input source
  — even when a sample is picked, the user still has to explicitly select
  a category (the two bundled samples happen to match their own category,
  but nothing stops picking the code sample and analysing it as English,
  or vice versa, deliberately). Both `run()` and `clean()` reject the
  request with a flash message if `category` isn't `"code"` or `"english"`.

- **`_parse_ks()`** — converts the form's k and step into the list of k
  values to run. `step = 0` means a single run at `k`; `step > 0` means
  `range(0, k_max + 1, step)`, starting at k = 0 on purpose so results
  always include the utility-0 baseline. Out-of-range values are clamped
  (`max(0, min(k_max, MAX_K))`) rather than rejected.

- **`index()` / `_render_index(**prefill)`** — the home page: one query for
  the stored-inputs list, plus optional keyword args (`prefill_text`,
  `prefill_label`, `prefill_category`, `prefill_k_max`, `prefill_k_step`)
  that populate the form when it's being re-rendered right after a Clean
  action rather than loaded fresh. `index()` itself just calls
  `_render_index()` with no prefill.

- **`clean()`** — `POST /clean`, a sibling to `run()` that shares its
  input-resolution and validation but does something different with the
  result: it calls `bpe.normalize(text, category)` and re-renders the
  *index* page showing the cleaned text read-only (via `_render_index`),
  rather than saving anything or redirecting anywhere. Nothing is written
  to the database — cleaning is a preview/transform step the user can
  inspect before deciding to analyse. The cleaned text and its label ride
  along in hidden fields, which is how the next **Run BPE** click gets
  hold of exactly the text on screen; since the file input and sample
  dropdown come back empty on a re-render, that carrier is what
  `_resolve_input()` falls through to.

- **`run()`** — the POST handler for **Run BPE**, and the app's one
  real "controller" for actually producing results. It resolves the
  input, validates it (empty, too large, non-numeric k — each with a
  flash message and a redirect rather than a server error), then for each k in the sweep checks
  the database first and skips work already done. This check-before-
  compute loop is what makes sweeps incremental: a second sweep with a
  finer step only computes the new k values, and identical re-runs cost
  one `SELECT` each. Crucially, `run()` never calls `bpe.normalize()`
  itself — whatever text `_resolve_input()` hands it is exactly what gets
  analysed, cleaned or not. After the sweep it calls `bpe.summarize()` once
  and `db.save_summary()` once — unconditionally, even when every k was
  already stored, since the summary is cheap (one BPE pass) and an
  `INSERT OR REPLACE` keeps it correct rather than stale. It finishes by
  redirecting to `/results/<hash-of-text>` — the content hash, not a row id
  — so refreshing the results page never re-submits the form.
  `POST /api/experiments` in `api.py` does the same summarize-and-save at
  the same point, so the two entry paths keep `/analysis` equally up to date.

- **`results(ihash)`** — fetches the rows (404 if the hash is unknown — the
  honest answer for a stale bookmark after a delete) and renders the table,
  the plot, and a 400-character preview of the input.

- **`plot(ihash)`** — `GET /plot/<ihash>.png`, streamed from memory
  (`io.BytesIO`, nothing written to disk). Two side-by-side matplotlib
  charts — compression utility vs k, and vocabulary size vs k — built with
  `matplotlib.use("Agg")` set before `pyplot` is imported (the app runs
  headless; without this, Flask can crash on macOS). Rows are grouped by
  `category` first, so a hash with rows in both categories draws one line
  per category (with a legend), rather than one line zig-zagging between
  two different curves. The figure's title carries the *only* place
  "Cleaned"/"Raw" is mentioned anywhere in the UI — `rows[0]["cleaned"]`,
  since every row on one hash shares the same cleaned state (they're
  necessarily the same underlying text). Each figure is `plt.close()`d
  after saving to avoid leaking memory across requests.

- **`analysis()`** — `GET /analysis`, the cross-file page: one
  `get_all_summaries()` query, straight into the template. Unlike
  `results()` it isn't scoped to a hash — it's the only page in the app
  that looks at every input at once.

- **`_analysis_scatter(y_field, y_label, title)` + `analysis_elbow_plot()` /
  `analysis_captured_plot()`** — `GET /analysis/elbow.png` and
  `/analysis/captured.png`. The two plots differ only in which summary
  column goes on the y-axis, so they're two three-line routes over one
  helper. Points are grouped and coloured by category with the **same
  palette as `plot()`** (`code` = `#4058B0`, `english` = `#B05840`) so the
  mapping carries across pages, and the legend is drawn only when more than
  one category is present — same rule, same reason. Like `plot()`, the PNG
  is streamed from `io.BytesIO` and the figure is `plt.close()`d after
  saving.

- **`delete(ihash)`** — POST-only, because anything that destroys data must
  never be reachable by a GET (browsers and crawlers can prefetch links). A
  browser-side `confirm()` dialog in the template is the second guard.
  One call into `db.delete_input()` removes both the experiment rows and
  the summary, so the input disappears from the results and analysis pages
  together.

### `templates/` — the presentation layer

Four Jinja templates extending one base, with all CSS inline in a
`<style>` block in `base.html` — at this size, a separate stylesheet buys
nothing.

- **`base.html`** — the shared skeleton: page title, the flash-message loop
  (where every guardrail message from `run()` surfaces), and all styling.
  The `.num` class right-aligns numbers with `font-variant-numeric:
  tabular-nums`, since the UI is mostly tables of numbers meant to be
  compared down a column. The heading carries the app's only navigation:
  the title links home, and a **Cross-file analysis** link sits beside it,
  so `/analysis` is reachable from every page rather than only from the
  home page.
- **`index.html`** — one form containing both input methods (file upload,
  sample dropdown), a required category radio group (Source code / English
  language), the k and step fields, and three controls: **Clean** and
  **Run BPE**, two submit buttons posting to two genuinely different
  endpoints (`/clean` and `/run`) via HTML's `formaction` attribute rather
  than sharing one endpoint distinguished by a value, so they read as the
  separate actions they are; plus **Analysis**, which is a link to
  `/analysis` styled as a button (`a.button`) rather than a submit — it
  navigates, it doesn't act on the form, so it must not be able to submit
  it. After a Clean, the page also shows the cleaned text in a read-only
  `<pre>` (first 2,000 characters) with the full text and its label in
  hidden fields — read-only because the text is now machine-produced
  output to check, not something to keep editing, and hidden-field carriage
  is what avoids a redirect or session storage. Below the form, the
  stored-inputs table has a Category column and per-input delete buttons —
  no Cleaned column; that only shows up as a word on the results-page plot
  (see `plot()` in `app.py` above). Keeping upload/sample in a single form
  (rather than tabs) is what makes the fixed priority order in
  `_resolve_input()` the only conflict-resolution logic needed.
- **`results.html`** — the plot (`<img src="{{ url_for('plot', ihash=ihash) }}">`),
  the stats table (one row per k, plus a Category column since a single
  input hash can have rows spanning both categories), and the input
  preview. The preview's truncation indicator is computed in `app.py`'s
  `results()` route from the raw stored text's length
  (`len(input_string) > 400`) rather than from any one row's
  `original_chars`, since that number can still vary by category and
  isn't a reliable proxy for the raw text's length. The template otherwise
  contains loops and output only — every number it prints was computed in
  `bpe.py` and stored by `db.py`, so the view layer can't introduce a
  discrepancy.
- **`analysis.html`** — the cross-file page: one table row per stored
  summary (category, size, elbow k, vocab at elbow, % utility captured,
  longest token at elbow), then the two scatter plots. It shows a subset of
  the summary columns, not all of them — the rest are stored for querying
  the database directly, but a table wide enough to hold every field stops
  being readable. When no summaries exist yet it says so and points at the
  home page, rather than rendering an empty table above two empty plots.

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

Dependencies are pinned in `requirements.txt` (Flask, flasgger for the API
docs at `/apidocs/`, matplotlib for the plots) and are already installed in
`.venv`. The SQLite database (`experiments.db`) is created automatically on
first run, including the `file_summary` table — an `experiments.db` from
before that table existed does *not* need deleting, it just won't have
summaries for inputs analysed earlier until they're run again.

## Tests

```bash
.venv/bin/python test_bpe.py
.venv/bin/python test_db.py
```

Plain `assert`s and a `__main__` block — no pytest, no test runner to
install. Both files cover the places where a wrong answer would still look
perfectly plausible on screen.

**`test_bpe.py` — the elbow maths.** `find_elbow_k` on a concave curve
whose bend is known by construction (asserted as a range, since the method
claims to find the bend *region*, not one exact index), its degenerate
cases, and an internal-consistency check on `summarize()`
(`vocab_at_elbow == base_alphabet + elbow_k`, `0 <= elbow_k <=
saturation_k`, the captured percentage within [0, 1]). The BPE core itself
isn't retested here — the [worked example](#worked-example) above pins it
by hand.

**`test_db.py` — the no-duplicates guarantees**, since a double-counted
input would silently skew every cross-file comparison: three runs of one
file leave exactly one summary row and one experiment row per k; the
surviving summary is the newest one (compared field by field against a
fresh `summarize()`, so a stale row can't pass); one text under two
categories deliberately stays two rows; and deleting an input empties both
tables. Every test points `db.DB_PATH` at a temporary file first, so the
suite can never touch a real `experiments.db`.

## Using it

1. Provide a file one of two ways: **upload** it, or pick a built-in
   **sample** (English prose or Python code). Those are the only two input
   methods — there's no paste box. If both are given, the sample wins.
2. Choose a **category** — Source code or English language. This is
   required and never inferred: it decides which cleaning rules the Clean
   button would apply (indentation is preserved for code, collapsed for
   English prose).
3. Choose **k** (max merges, up to 2000) and optionally a **sweep step**
   (0 means a single run at k).
4. Optionally click **Clean** first — it applies the category's cleaning
   rules and shows you the result to check, without running anything yet.
   Then click **Run BPE**: it analyses the cleaned text if you've just
   cleaned, and the file or sample you picked otherwise. You land on the
   results page with a graph and a table of every stored run for that
   exact text.
5. Click **Analysis** (button on the home page, or the header link on every
   page) to see every input analysed so far in one table, with its elbow k
   and how much of the available compression that elbow captures, plus both
   against input size as scatter plots. Every run adds to this page
   automatically — there's nothing extra to click.

Limits: input up to 200,000 characters, k up to 2000.

To compare cleaned vs. raw, or one category's cleaning against the
other's, just run both: pick the file and click **Run BPE** straight away
for the raw baseline, then pick it again and click **Clean** followed by
**Run BPE** for the cleaned version (or switch category first). Since
cleaning changes the text, each combination lands on its own results page
with its own graph — there's no single page that merges them, by design;
compare the two pages side by side, or use `/analysis` to see them as
separate points.

## Data storage and deduplication

- Each experiment row is **unique on (input text, k, category)**.
  Re-running the same text with the same k and category reuses the stored
  row instead of inserting a duplicate — the flash message reports how
  many rows were new vs. already stored. Category is part of this key
  (not just `label`, which carries no such guarantee) because the same
  text produces different stats under each category's cleaning rules, so
  the same text can deliberately be run under both to compare the effect.
  `cleaned` is recorded per row but isn't part of this key — see below.
- Inputs are grouped by a short **SHA-256 hash** of the text, so the same
  file submitted twice — even under a different filename or category —
  lands on the same results page, which can then show rows from both categories
  side by side. A cleaned and a raw run are never on the same page: since
  cleaning changes the text, they hash differently and get separate
  results pages, each with its own graph.
- Deleting an input removes **all** of its stored runs, across both
  categories if the hash has rows in both, **and** its summary row — so it
  leaves the results page and the `/analysis` page at the same time.
- Alongside `experiments`, a second table **`file_summary`** holds one row
  per (input hash, category) — the elbow stats described
  [above](#the-elbow-where-merges-stop-paying-off). It's written on every
  run and keyed `UNIQUE (input_hash, category)` with `INSERT OR REPLACE`,
  so re-running a file updates its summary in place rather than adding a
  second one. Unlike `experiments`, nothing here is deduplicated *against*
  — the summary is derived data, always recomputed, always overwritten.
- **Re-running the same file changes nothing on the analysis page.** Run an
  input once or ten times and it contributes exactly one summary row and
  one experiment row per k, so no input is ever double-counted or
  double-plotted. `test_db.py` pins this. The one intended exception is
  category: the same text analysed as both `code` and `english` is two
  summaries by design, and shows as two points — that's the comparison, not
  a duplicate.
- Inputs analysed **before** the `file_summary` table existed have no
  summary and don't appear on `/analysis` until they're run once more; the
  re-run writes exactly the row they would have had.