# Dev Log — Compressed Text Analyser

A running log of how the app was built and why each part is the way it is.
(The project isn't in its own git history yet, so this log reconstructs the
build steps from the code; new entries should be added at the top as the
project evolves.)

---

## 2026-08-13 — The per-input plot shows what it worked out

- **k\* and saturation are now marked on the per-input plot.** The app was
  computing the two most interesting points on the curve, storing them in
  `file_summary`, and then drawing a figure that read none of them —
  `_build_results_figure()` only ever saw the `experiments` rows. It now
  looks the summary up as well and hands it to a new
  `_mark_summary_points()`: a starred point at k\*, a square at saturation,
  both labelled, and the chord from (0, 0) to (`saturation_k`,
  `max_utility`) as a thin dashed grey line. The chord earns its place
  because it is the definition — k\* is the point furthest above it — so
  drawing it turns the marker from an assertion into something the reader
  can check by eye. The vocabulary panel gets a light dotted vertical line
  at k\*, unlabelled, so the vocabulary cost there can be read off without
  repeating the label that already sits on the utility panel.

- **The saturation marker and chord are conditional, and that is the whole
  subtlety.** They are drawn only when `saturation_k` is at most the largest
  k among the stored rows. Most files were swept to k = 300 but saturate
  somewhere past 1,000: marking a point out there stretches the x-axis by a
  factor of five and squashes the actual measured curve into the left edge,
  which loses more than the marker gains. Out of range, k\* is marked alone
  and the axes stay exactly where the data put them. (k\* itself is always
  marked; on a couple of files swept to 300 it sits a few merges past the
  end, which nudges the axis slightly and is worth knowing.)

- **`db.get_summary(conn, ihash, category)`** is new — the single-row
  counterpart to `get_all_summaries()`. Keyed on the pair the table is
  unique on, since a hash can have a summary under each category and the
  figure marks each in that category's own colour. A category with no
  summary row draws its curve unmarked rather than raising, so an input
  analysed before summaries existed still plots.

- **No schema change, no new dependencies**, and both the PNG route and the
  Save PDF route go through the same builder, so the saved vector PDF
  carries the markers too.

- **Merges is back as a table column.** The naming pass below dropped it as
  repetition, which was wrong: unlike category and size, `merges_applied`
  varies down the rows, and it is the only way to tell a flat tail that
  means "more merges bought nothing" from one that means "no further merges
  happened at all." It sits directly after k, requested next to actual.

---

## 2026-08-11 — One name per metric

- **Every quantity now has exactly one name, used the same in the code, the
  tables and the graphs.** The vocabulary was drifting per surface — the
  same number was "learned vocab" in a table header, `learned_vocab` in a
  column, and "learned vocab (memory)" in a plot legend. The agreed names
  are: **k** (merges), **k\*** (the recommended merge count),
  **Saturation k**, **Size (characters)**, **Utility**, **Vocabulary**,
  **Distinct tokens**, **Tokens** (encoded length) and **Utility ratio**
  (the share of the maximum utility that k\* reaches).

- **The bend in the curve is k\*, not the "knee".** `find_knee_k()` is now
  `find_k_star()`; the summary fields are `k_star`, `utility_at_k_star`,
  `tokens_at_k_star` and `utility_ratio`. The words *knee* and *elbow*
  are gone from every field name, table header, axis label, title and image
  alt text. The only surviving occurrence anywhere is the *Kneedle* paper
  citation in `find_k_star`'s docstring, which is a title and stays as
  published.

- **The cross-file plot routes were renamed too, breaking the old links.**
  `/analysis/knee.png` → `/analysis/k_star.png` and `/analysis/captured.png`
  → `/analysis/utility_ratio.png`, with `analysis_knee_plot()` /
  `analysis_captured_plot()` and the `ANALYSIS_PLOTS` keys following. Each
  key is now exactly the summary column it charts, so the name in the URL,
  the name in the database and the name on the axis are one name — the
  alternative was a URL saying *knee* for an axis labelled *k\**, which is
  the drift this pass exists to remove. The saved filenames move with the
  keys: `analysis_k_star.pdf` and `analysis_utility_ratio.pdf`. Anything
  linking to the old URLs (a bookmark, a figure path in a draft) needs
  updating; nothing in the app itself does, since every link is built with
  `url_for`.

- **Columns renamed to match**: `experiments.original_chars` → `size_chars`,
  `token_count` → `tokens`, `learned_vocab` → `vocabulary`, and the
  `file_summary` knee columns → the `k_star` family. Dropped
  `learned_vocab_at_knee`: it is exactly `len(set(text)) + k_star`, so it
  was a stored restatement of two other columns.

- **Tables show less.** The per-k table is down to k, Tokens, Utility,
  Vocabulary, Distinct tokens — category, merges applied and the character
  count are identical on every row of a single input, so as columns they
  were pure repetition. The cross-file table is Input, Type, Size, k\*,
  Utility ratio, Saturation k: Saturation k gained a column (it bounds k\*
  and was already stored), vocabulary-at-k\* lost one along with its field.

- **Utility ratio is shown as a decimal** (`0.74`), not `74.0%` — it is
  a ratio of two utilities and reads as one on a plot axis, so the table
  and the axis now agree digit for digit.

- **Migration**: renames, so no in-place migration — `experiments.db` was
  rebuilt from the `input_string`s it already stored (backup at
  `experiments.db.pre-k-star-rename.bak`). All 198 experiment rows and 14
  summary rows came back with values identical to the backup's, field for
  field; nothing about how anything is computed changed. The three saved
  PDFs in `figures/` were re-saved through the app's own Save PDF routes so
  they carry the new labels, and the two cross-file ones under their new
  filenames — `analysis_knee.pdf` and `analysis_captured.pdf` were deleted
  rather than left behind as stale copies under dead names.

---

## 2026-08-09 — Longest-token metric removed

- **`longest_token` / `longest_token_at_knee` are gone** from `analyse()`,
  `analyse_series()`, `summarize()`, both database tables, and the
  `/results` and `/analysis` tables. It was the one purely qualitative
  number in an otherwise quantitative set: nothing plots it, the knee
  doesn't depend on it, and a single longest string says little about a
  vocabulary — ties are broken arbitrarily by `max()`, so which token
  appeared was partly an artifact of set iteration order. The quantitative
  vocabulary story is already told by `distinct_tokens` and
  `learned_vocab`.

- **Migration**: dropping columns is expressible as `ALTER TABLE ... DROP
  COLUMN`, so the existing `experiments.db` was migrated in place (backup
  at `experiments.db.pre-longest-token-drop.bak`) rather than deleted — all
  190 experiment rows and 14 summary rows are unchanged. A database that
  has not had the drops applied still has both columns declared `NOT NULL`
  with no default, so it will fail on `save_experiment`'s and
  `save_summary`'s INSERTs.

---

## 2026-08-09 — "Elbow" renamed to "knee" throughout

- **One name for one concept.** The code called the bend in the utility
  curve the *elbow* while the method it uses is published as the *knee* /
  Kneedle method, and the docs used both words interchangeably. Everything
  is now *knee*: `find_knee_k()`, the `knee_k` / `*_at_knee` summary fields
  and `file_summary` columns, the `/analysis/knee.png` route and
  `analysis_knee_plot()`, the `"knee"` key in `ANALYSIS_PLOTS` (and so the
  `/save/analysis/knee` URL and the `analysis_knee.pdf` filename), the
  `/analysis` table headers, and the prose in this log and the README.

- **Migration**: renaming columns is a `file_summary` shape change, but this
  one is expressible as `ALTER TABLE ... RENAME COLUMN`, so the existing
  `experiments.db` was migrated in place with the six renames rather than
  deleted — the stored rows are unchanged, only the labels on them moved.
  A database that has not had those renames applied still has the `elbow_*`
  names and will fail on `save_summary`'s INSERT.

---

## 2026-08-08 — Word-count fields dropped from the summary

- **`size_words`, `unique_words`, and `type_token_ratio` are gone** from
  `summarize()`, the `file_summary` table, and the `/analysis` table. They
  were added as a BPE-independent sanity check on lexical repetition, but
  nothing in the app ever read them: no plot uses them, the knee doesn't
  depend on them, and no analysis was ever written against them. A stored
  column that nothing consumes still has to be kept correct on every write,
  so it's a liability rather than an option held open.

- **`size_chars` stays** and remains the x-axis of both cross-file plots.
  Characters are the right size measure here anyway — BPE operates on
  characters, and `text.split()` means something quite different for prose
  than for source code, so a word count was never comparable across the two
  categories the app exists to compare.

- **Migration**: another `file_summary` shape change, so `experiments.db`
  was deleted and recreated again. `db.py` now carries a comment at the
  `SCHEMA` definition stating the rule once — `CREATE TABLE IF NOT EXISTS`
  never alters an existing table, so any column change here means deleting
  the database — with this drop recorded as the instance. A database from
  before this change still has the three columns and will fail on
  `save_summary`'s INSERT, since they're `NOT NULL` with no default.

## 2026-08-08 — Vocabulary split into two numbers; clearer names

- **`vocab_size` was one column doing two jobs.** It stored
  `len(set(tokens))` — the distinct tokens *present after* merging — but the
  UI labelled it "Vocab" and the README described it as the dictionary you'd
  need to decode the text. Those aren't the same quantity, and they diverge:
  once merging consumes the last occurrence of a character, that character
  stops appearing while its symbol is still in the vocabulary. The old
  column also isn't monotonic in k, which made "vocabulary grows as you
  merge" — the trade-off the whole app exists to show — look false on the plot.

- **Split into `distinct_tokens` and `learned_vocab`.**
  `distinct_tokens = len(set(tokens))` is what the text is built from at
  this k and may fall; `learned_vocab = len(set(text)) + len(merges)` is the
  starting alphabet plus one symbol per merge, rises exactly one per merge,
  and is the number tokenizers mean by "vocabulary size." Both are stored
  per experiment row, and the results plot draws them together — learned
  vocab solid, distinct tokens dashed, same colour per category — because
  the *gap* between them is the point: it's vocabulary paid for but no
  longer used. That chart now always gets a legend (it has two lines even
  for one category), while the utility chart keeps the old
  only-when-multiple-categories rule.

- **`vocab_at_knee` → `learned_vocab_at_knee`** in `file_summary` and on
  `/analysis`, for the same reason: it was always `base_alphabet + knee_k`,
  i.e. the learned vocabulary, never the distinct-token count.

- **`base_alphabet` dropped as a stored column.** It's `len(set(text))` —
  derivable from the input in one call, never independently interesting, and
  a stored copy is one more thing that can go stale. It survives as a local
  in `bpe.py` where it's used. `test_bpe.py`'s consistency assertion now
  computes it directly instead of reading it back from the summary, which
  makes the test check the invariant rather than a column against itself.

- **Renames for accuracy**: `normalize_whitespace` → **`normalize_english`**
  (it does far more than whitespace — strips punctuation, lowercases — and
  the name now matches its sibling `normalize_code` and the `category`
  values the dispatcher switches on), and the series field `active_types` →
  **`distinct_tokens`**, matching the experiment column and dropping the
  "types" jargon.

- **Migration: `experiments.db` was deleted, not migrated.** `CREATE TABLE
  IF NOT EXISTS` won't add or drop columns on an existing table, and this
  changes both tables. The data was 195 rows over 9 bundled samples, all
  reproducible by re-running (BPE is deterministic), so recreating beat
  writing a migration for local, disposable experiment data — same drill as
  every schema change before this. Anyone with an older database needs the
  same `rm experiments.db`.

## 2026-08-08 — Save PDF on every graph, a saved-figures page, and samples up to 40k

- **Why**: the graphs were only ever pixels in a browser tab. Getting one
  into the thesis meant screenshotting it, which produces a fixed-resolution
  raster that goes soft the moment it's scaled or printed. Every plot route
  now has a **Save PDF** sibling that writes the same figure as a vector PDF
  into `figures/`, so a figure can be dropped into a document at any size and
  stay sharp.

- **Split "build the figure" from "send the figure."** `plot()` and the two
  `/analysis/*.png` routes used to build a figure and stream it as PNG in one
  function. They're now `_build_results_figure()` / `_build_analysis_figure()`
  plus one of two sinks: `_serve_png(fig)` (stream from `io.BytesIO`) or
  `_save_pdf(fig, stem)` (write to `FIGURE_DIR`). The point of the split is
  that the PNG and the PDF can't drift — there's one definition of each graph
  and two ways to emit it, not two near-identical plotting bodies to keep in
  sync. Both sinks `plt.close()`, so the existing no-leaked-figures rule holds
  by construction: every route ends in exactly one of them.

- **The two cross-file plots' arguments moved into an `ANALYSIS_PLOTS` dict**
  keyed `"knee"` / `"captured"`. There were two routes over one helper before;
  adding Save PDF would have made it four routes repeating the same three
  literal arguments. Now the URL segment *is* the key (`POST
  /save/analysis/<name>`), and a third cross-file plot would be one dict entry
  plus one PNG route.

- **Stable filenames, so re-saving replaces.** `analysis_knee.pdf`,
  `analysis_captured.pdf`, and `results_<label>_<hash8>.pdf`. The alternative
  — timestamped names — accumulates six near-identical PDFs of the same graph
  after a few re-runs and leaves you picking the newest by eye; overwriting
  means a figure referenced from a document keeps its path and just gets
  fresher. The hash fragment is in the per-input name because labels are *not*
  unique (two uploads can share a filename), and `_safe_stem()` reduces the
  label to `[A-Za-z0-9_-]` first since it comes from a sample name or an
  uploaded filename.

- **`/figures` browse page + `_figure_path()`'s double check.** The page lists
  saved PDFs newest-first with size and save time, each linking to the file,
  each with a delete button. `name` comes from the URL on both the serve and
  delete routes, so it goes through one gatekeeper that checks it twice: a
  `[A-Za-z0-9_.-]+\.pdf` full-match (no separators, no `..` segments), then a
  resolved-parent comparison against `FIGURE_DIR`. Two checks because neither
  covers the other — the pattern can't see a symlink pointing out of the
  folder, and the resolve alone would still admit odd names. Anything failing
  either 404s before the filesystem is touched.

- **`figures/` is tracked in git** (with a `.gitkeep`), unlike `data/uploads/`
  and `experiments.db` which are gitignored. The distinction is
  regenerable-input vs. kept-output: an upload can be re-uploaded, a saved
  figure is the artefact being produced.

- **Samples extended to 30k, 35k, and 40k** — `SAMPLE_SIZES` grew by three
  entries and six new slices were cut, same non-overlapping-consecutive rule
  as the existing ones, so a category still varies only in size. Four points
  per category was thin for reading a trend off the knee-vs-size plot;
  seven gives the line something to be.

- **`_sample_names()` replaces `sorted(SAMPLES)` for the dropdown.** Plain
  string sorting happens to read correctly while every size is two digits, but
  it sorts `english_5k` after `english_35k` — a latent bug that the 30k–40k
  additions didn't trigger and a future 5k would. It now sorts on (category,
  the integer parsed out of the suffix).

- **No schema or migration impact**: no database columns changed, and saved
  figures live on the filesystem rather than in SQLite — a figure is a
  rendering of data already stored, so there's nothing to keep consistent
  beyond re-clicking Save after a re-run.

## 2026-08-05 — Files only: paste removed, buttons renamed, Analysis button added

- **Paste is gone; upload and sample are the only two inputs.** Requested
  directly, and it fits what the tool is for: the thesis compares *files*
  (prose vs code, short vs long), and a textarea invited one-off snippets
  that land in the stored-inputs list without being reproducible later —
  an uploaded file is kept in `data/uploads/`, a pasted paragraph exists
  only as a database row. `_resolve_input()` no longer reads `text` at all,
  the textarea is out of `index.html`, and the "provide some text" flash
  became "Choose an input: upload a file or pick a sample."

- **The Clean → Run handoff had to be rebuilt**, because it was riding on
  the textarea: `/clean` used to drop cleaned text into the box, and since
  a re-render clears the file input and sample dropdown, the box was what
  the following Run picked up. With no box, the cleaned text now travels in
  a **hidden field** (`cleaned_text`, plus `cleaned_label` so a cleaned run
  keeps the sample name or filename instead of a 30-character text
  fragment) and is displayed **read-only** in a `<pre>` — read-only
  because it's machine-produced output to check, not something to keep
  editing. `_resolve_input()`'s priority is unchanged in spirit —
  **sample > upload > carried cleaned text** — so picking a new file after
  cleaning analyses the new file, not stale text.

- **`was_cleaned` (hidden form flag) deleted; `cleaned` is now derived.**
  `_resolve_input()` returns a 4th value saying whether the text came from
  the cleaned carrier, and `run()` stores that. The old flag could lie: it
  persisted across a re-render, so cleaning a file and *then* picking a
  different sample would have stored the new, uncleaned text tagged
  `cleaned=1` — and the results plot titles itself "Cleaned" off that
  column. Deriving provenance from which source actually won makes the
  wrong state unrepresentable rather than merely unlikely.

- **Line endings are re-normalized on the way back out of the hidden
  field.** A hidden-input round-trip can return `\n` as `\r\n`, which would
  make the analysed text differ from the text just displayed — different
  hash, different results page, cleaning silently undone for `code` (whose
  rules guarantee `\n`). Both cleaning rules already promise `\n` only, so
  redoing that one conversion is a no-op on untouched text and a repair
  otherwise. Verified by feeding a CRLF-mangled carrier through `/run` and
  checking the stored hash matches the clean version's.

- **Button renames and the new Analysis button**: "Run analysis" → **"Run
  BPE"** (it names the operation, and stops colliding with the *other*
  meaning of "analysis" now that a page owns that word); **Analysis** added
  to the home page next to Clean and Run BPE. It's an `<a class="button">`,
  not a `<button>` — it navigates rather than acting on the form, and a
  submit button inside the form would post the form to `/analysis`. New
  `a.button` rule in `base.html` shares the existing button styling. The
  header link stays too, since it serves the results and analysis pages
  where there's no form at all.

- **The JSON API keeps its `text` field.** It looks like the same thing but
  isn't: for an HTTP client, a JSON body *is* the upload mechanism — there
  is no file picker to use instead. Removing it would leave
  `POST /api/experiments` able to analyse nothing but the two bundled
  samples.

## 2026-08-05 — Knee detection, a per-file summary table, and a cross-file analysis page

- **Why**: everything the app did up to here answered a *within-one-input*
  question — "how does this text compress as k grows" — and answered it as
  a curve the reader had to eyeball. Two things were missing. First, the
  interesting point on that curve (where extra merges stop paying for
  themselves) was never computed, only visible. Second, there was no way to
  put inputs next to each other: comparing prose against code, or short
  against long, meant opening two results pages and squinting. This change
  adds a single scalar per input — the **knee k** — and a page that plots
  it across every input analysed so far, which is what turns a pile of
  individual runs into an actual cross-file finding.

- **`bpe.analyse_series(text)`** — runs BPE *once* from single characters
  and records a stats row after every merge, up to the same natural stop
  as `train_bpe` (no pair occurs at least twice). This exists because the
  obvious way to get the utility curve — calling `analyse(text, k)` for
  every k — retrains from scratch each time, i.e. O(k²) work for a curve
  the single pass already walks through. It also gives the curve at *every*
  k rather than only at the sweep's step points, which matters: the knee
  is a specific k, and a sweep with step 50 could only ever locate it to
  the nearest 50. Returns k = 0 (the untouched character list) as the first
  row, so the series always has a utility-0 baseline like the sweep does.

- **`bpe.find_knee_k(utilities)`** — the knee / distance-to-chord method
  (Satopaa et al., 2011, *Finding a "Kneedle" in a Haystack*): normalize
  both axes to [0, 1] and take the k whose point sits farthest **above**
  the straight chord from (0, 0) to (1, 1). Chosen over curvature/second-
  derivative approaches because the utility curve is a discrete, integer-
  valued sequence — numerical second derivatives on it are noisy and need
  smoothing parameters, whereas the chord distance is one subtraction per
  point and has no tuning knobs at all. It takes a plain list of numbers
  rather than the series dicts, deliberately: that keeps it a pure function
  of a curve with no dependency on the rest of the app, which is what makes
  it directly unit-testable on hand-written curves (see the tests below).
  Degenerate inputs return 0 — a one-point curve, or an all-zero one, has
  no meaningful knee.

- **`bpe.summarize(text, category, label)`** — glues the two together into
  the flat dict `db.save_summary()` stores: size stats (chars, words,
  base alphabet, unique words, type/token ratio), the knee point (k,
  utility, tokens, vocab, longest token there), the saturation k, and
  **`pct_captured_at_knee`** — the knee's utility as a fraction of the
  maximum achievable utility. That last one is the number worth reading:
  it says "you get X% of all the compression this text will ever give you,
  for `knee_k` merges instead of `saturation_k`." Same convention as
  `analyse()`: the caller normalizes the text first, `summarize()` has no
  opinion on cleaning.

- **New `file_summary` table, not extra columns on `experiments`.** A
  summary is a property of an *input*, not of an (input, k) run — putting
  it on `experiments` would repeat the same values once per sweep point and
  leave "which row's copy is authoritative" ambiguous. `UNIQUE (input_hash,
  category)` plus `INSERT OR REPLACE` in `save_summary()` means re-running
  a file refreshes its summary in place rather than accumulating stale
  copies; the summary is a derived cache of the current text, so replacing
  it is always correct.

- **`/analysis`** renders one row per stored summary, plus two scatter
  plots served by `/analysis/knee.png` (knee k vs input size) and
  `/analysis/captured.png` (% of max utility captured at the knee vs input
  size). Both come from one helper, `_analysis_scatter(y_field, y_label,
  title)`, since they differ only in which column goes on the y-axis. Points
  are coloured by category using **the same two colours as the per-input
  plot** (`code` = blue `#4058B0`, `english` = red `#B05840`), so a reader
  moving between the two pages doesn't have to relearn the mapping, and the
  legend is drawn only when more than one category is present — same rule
  `plot()` already used. Input size is the x-axis on both because it's the
  confound worth ruling out first: if knee k just tracks length, that's not
  a finding about prose vs code.

- **First tests in the project (`test_bpe.py`)** — plain asserts and a
  `__main__` block, run with `.venv/bin/python test_bpe.py`, no pytest
  dependency added. They cover exactly the parts where a silent wrong
  answer would be invisible in the UI: `find_knee_k` on a hand-built
  concave curve whose bend is known by construction (asserted as a range,
  `2 <= k <= 4`, not an exact k — pinning the precise index would make the
  test a change-detector for a method that only claims to find the bend
  *region*), its degenerate cases, and an internal-consistency check on
  `summarize()` for a short real string (`vocab_at_knee` = alphabet +
  knee k, `0 <= knee_k <= saturation_k`, the percentage in [0, 1]). The
  BPE core itself stays untested here — it's already pinned by the worked
  example in the README.

- **`delete_input()` now clears both tables.** It deleted only from
  `experiments` at first, which left an orphaned `file_summary` row listing
  a deleted input on `/analysis` forever — the summary is derived data, so
  outliving its source is never right. One more `DELETE` in the same
  function and the same transaction.

- **Redundancy on re-runs, pinned by tests rather than assumed
  (`test_db.py`)**: the analysis page is only worth reading if re-running a
  file adds nothing to it — a second summary row for the same input would
  double-plot a point and quietly bias every cross-file comparison. The
  guarantee is structural (`UNIQUE (input_hash, category)` +
  `INSERT OR REPLACE`, mirroring `save_experiment`'s check-then-insert),
  but structural guarantees are exactly the kind that get broken later by
  an innocent-looking schema edit, so there are now tests: three runs of
  one file leave one summary row and one experiment row per k; the
  surviving summary is the *newest* one (compared field-by-field against a
  fresh `summarize()`, so a stale row can't pass); one text under both
  categories deliberately stays two rows; and delete empties both tables.
  Each test points `db.DB_PATH` at a temp file first — the suite must never
  be able to touch a real `experiments.db`.

- **Migration**: `file_summary` is a brand-new table, so
  `CREATE TABLE IF NOT EXISTS` creates it on the next `connect()` with no
  need to delete `experiments.db` this time — the first schema change in
  this project that doesn't require it. The one consequence: inputs
  analysed *before* this change have no summary row, so they stay off
  `/analysis` until they're run once more. Deliberately not backfilled
  automatically — re-running an input is one click and writes exactly the
  same row, which is a better trade than start-up code that rewrites
  historical data every time the app connects.

## 2026-08-04 — Decoupled Clean from Analyse; graphs restored

- **Why, for the button redesign**: the previous "Run analysis (raw)" /
  "Clean" pair (same form, same `/run` endpoint, distinguished by a
  `clean` value) made `cleaned` part of an experiment's identity alongside
  `category`, which meant one raw hash could fan out into up to 4 stored
  rows (2 categories × 2 cleaned states) all sharing the same results
  page. That was reported back as unwanted complexity — cleaned and raw
  are "completely separate metrics," not two options of the same run, and
  nothing needed 4 hashes for one input. Fixed by making cleaning and
  analysis genuinely separate actions instead of two branches of one:
  - **`POST /clean`** (new route, `bpe.py`'s existing `normalize()`) takes
    whatever text/category the form currently holds, cleans it, and
    re-renders the *same* index page with the cleaned text sitting in the
    textarea for review — it does not touch the database or run BPE.
  - **`POST /run`** ("Run analysis") just runs BPE on whatever text is in
    the box at that moment, full stop — no clean/raw branching inside it
    at all. If the box holds cleaned text (because Clean was clicked
    first), that's what gets analysed; if it holds the original text,
    that's what gets analysed. `bpe.analyse(text, k)` lost its `category`
    and `clean` parameters entirely — it went back to being a pure
    "train BPE on this exact text" function, with cleaning fully external
    to it now.
  - Because cleaning now changes the actual text before it's ever saved,
    a cleaned version and a raw version of the same source naturally get
    **different `input_hash`es** — they were never the same experiment to
    begin with, so there's no longer any reason for them to share one.
    `cleaned` is still stored per row (so the UI can label it), but it's
    dropped from the `UNIQUE` constraint — `(input_string, k, category)`,
    same shape as before cleaned existed at all. One hash, one result set.
  - The two buttons share one `<form>` via HTML's `formaction` attribute
    (`Clean` points at `/clean`, `Run analysis` uses the form's default
    `/run` action) — no JS needed, and both buttons still submit
    text/file/sample/category/k together.
  - **No mention of "cleaned"/"raw" in the tables anymore** — the
    stored-inputs and results tables dropped the Cleaned column entirely.
    The only place it shows up now is a single word ("Cleaned" or "Raw")
    in the plot's title, since a plotted hash's rows always share one
    cleaned state (they're the same underlying text) even though they can
    still span two categories.

- **Why, for the graphs**: turns out this app used to have them —
  `/plot/<ihash>.png` (matplotlib, two side-by-side charts: compression
  utility vs k, vocabulary size vs k) existed as of commit `014aa65` and
  was intentionally dropped in `5783008` ("flatten `bpe_thesis/` to
  project root... dropped the matplotlib-based plot/report/CSV routes")
  when the JSON API was added — not a bug, just never brought back until
  now. Restored the inline `/plot/<ihash>.png` route and the `<img>` on
  `results.html`; skipped the old full-report-PNG and CSV-export routes
  since only the inline graphs were asked for this time. One addition
  the old version didn't need: since `category` (unlike `cleaned`) can
  still span two rows on one hash, `/plot` now draws one line per
  category present, with a legend only when there's more than one —
  `matplotlib` is back in `requirements.txt` (it was already sitting
  installed in the venv from before the drop, just undeclared).

- **No migration needed for the schema shrink** (`cleaned` dropped from
  `UNIQUE`): SQLite's `CREATE TABLE IF NOT EXISTS` still won't retroactively
  loosen a constraint on an existing table any more than it would tighten
  one, so `experiments.db` still needs deleting for the new schema to take
  effect — same drill as every schema change so far in this project.

## 2026-08-04 — Precise cleaning rules for code vs. english

- **Why**: the earlier `normalize_code`/`normalize_whitespace` were
  reasonable first passes but under-specified — in particular the old
  `normalize_code` collapsed runs of 3+ blank lines, which turned out to
  be an overreach (blank-line count between functions/blocks is something
  a user studying code compression might actually want intact). This
  entry replaces both functions with an exact, explicitly-specified rule
  set per category, given directly by the project owner rather than
  inferred, so the rationale below is "why this exact rule," not "why
  cleaning at all" (see the two entries below for that).

- **`normalize_code(text)` — rewritten, simpler and stricter about what it
  preserves:**
  1. `\r\n`/`\r` → `\n` (one newline convention).
  2. **Blank lines are never touched** — no merging, no removal. This is
     the one behavior actually removed from the old version; blank-line
     structure is left entirely to the person/BPE run to deal with.
  3. Tabs *in the leading indentation only* become 4 spaces, so
     tab-indented and space-indented code stop looking different to BPE.
  4. Leading spaces are otherwise left exactly as they are — Python's
     nesting is encoded in them, so touching them would corrupt meaning.
  5. After the indentation, runs of multiple spaces collapse to one
     (`x   =   1` → `x = 1`) — inter-symbol spacing carries no meaning.
  6. Trailing spaces/tabs on every line are stripped.
  7. Punctuation, operators, case, comments, and docstrings are left
     completely alone — none of them are noise in code.
  - **Deliberately skipped**: distinguishing string-literal contents from
    real code so their internal whitespace could be left alone. Reliably
    telling "inside a string" from "outside a string" needs a real
    tokenizer/parser, not a regex (nested quotes, triple-quoted strings,
    escaped quotes, f-strings all break a naive approach) — not worth the
    complexity for this tool. A string literal with padded spacing will
    have that spacing collapsed like anywhere else; BPE just compresses
    whatever spacing survives instead of the rule trying to protect it.
  - Implementation: rather than one big regex, each line is split into
    its leading-whitespace run and the rest, so the tab→4-spaces and
    space-collapsing rules can be applied to exactly the right half of
    the line without a lookbehind trying to do both at once.

- **`normalize_whitespace(text)` (english) — rewritten around "only
  letters, numbers, and single spaces survive":**
  1. `\r\n`/`\r` → `\n`, **then every `\n` becomes a space** — in prose,
     line breaks are usually just where the text wrapped, not meaningful
     structure, so they're treated as word separators like any other
     whitespace, not removed outright (removing them instead of spacing
     them would glue words together across line breaks).
  2. Every character that isn't a letter, digit, space, or tab is
     stripped — commas, periods, quotes, brackets, dashes, colons, etc.
     Tabs are deliberately kept alive through this step (not stripped
     outright) so step 3 can still treat them as word separators; if they
     were dropped here instead, a tab-separated pair of words would fuse
     into one token.
  3. Runs of spaces/tabs collapse to a single space.
  4. Leading/trailing space is trimmed from the whole text.
  5. Everything is lowercased.
  - Net effect: the character stream is reduced to `[a-z0-9]` tokens
    separated by exactly one space, so BPE sees spaces purely as word
    boundaries with no punctuation or capitalization noise competing for
    merges.

- **No migration needed**: these are pure function-body changes with no
  schema impact — existing `category`/`cleaned` rows are unaffected,
  only what a *new* `clean=1` run produces changes. No need to touch
  `experiments.db`.

## 2026-08-04 — "Clean" button: raw vs. cleaned as a separate, comparable axis

- **Why**: the category feature (previous entry) always cleaned before BPE,
  so there was no way to see what the cleaning rules actually changed, or
  to isolate that effect from the category choice itself. The goal is
  direct comparison: cleaned vs. raw for the same text, and — since the
  two categories' cleaning rules differ — how the two cleaning *processes*
  (`normalize_code` vs. `normalize_whitespace`) differ from each other.
  Getting there meant `cleaned` had to become part of an experiment's
  identity (like `category` already is), not just a flag: otherwise a
  cleaned run and a raw run of the same (text, k, category) would collide
  under the old uniqueness constraint, and the second submission would be
  silently deduped against the first instead of stored for comparison.
- **Breaking change, done deliberately and visibly**: `bpe.analyse()`
  used to always clean; going forward it takes a required `clean` bool
  with no default, forcing every call site to choose explicitly. The
  already-shipped "Run analysis" button is relabeled **"Run analysis
  (raw)"** and now skips cleaning entirely — a new **"Clean"** button
  (`clean=1`) is the explicit opt-in for the old behavior. This is a real
  behavior change to an existing button, not purely additive, so the
  label, the flash message ("...raw..."/"...cleaned..."), and this log
  entry all call it out rather than changing it silently. The JSON API
  gets a softer landing: `clean` defaults to `true` there, since API
  callers who don't know about the new field should see no change.
- **Schema**: `experiments.cleaned INTEGER NOT NULL CHECK (cleaned IN
  (0,1))`; uniqueness is now `UNIQUE (input_string, k, category,
  cleaned)`. `list_inputs` groups by `(input_hash, category, cleaned)` —
  one hash can now show up to 4 summary rows (code×clean, code×raw,
  english×clean, english×raw) — and `rows_for_input` orders by
  `category, cleaned, k` so a results page renders as contiguous blocks
  per combination instead of interleaving them.
- **Known, accepted quirk**: when `clean=0`, category has zero effect on
  the actual BPE run (raw text is identical either way), so `code`+raw
  and `english`+raw rows for the same text are numerically identical,
  just tagged with different categories. This is a direct consequence of
  category being a user-declared identity field rather than an inferred
  one, not a bug — a naive "raw vs raw across categories" comparison is a
  no-op by construction; the meaningful raw/clean comparison is within
  one category.
- **Incidental fix**: `results.html`'s "…" truncation indicator used to
  check `rows[0]['original_chars'] > 400`, but `original_chars` reflects
  whichever text BPE actually saw (raw or normalized length, now varying
  per row), not `len(input_string)`. `app.py`'s `results()` route now
  computes the truncation flag directly from the raw stored text's length
  instead.
- **No migration script**: `experiments.db` deleted and recreated again,
  same reasoning as the category change — local, gitignored, disposable.

## 2026-08-04 — Required category (code / english) with per-category cleaning

- **Why**: every input was cleaned with one uniform rule regardless of
  content, but code and prose have different notions of "noise." In prose,
  extra spaces and blank lines are meaningless and safe to collapse; in
  code, indentation is often structurally significant (Python blocks) and
  collapsing it would corrupt what BPE sees. Splitting the cleaning rules
  by content type needed a category to dispatch on — and since detecting
  "is this code or English" reliably is itself an unsolved problem, the
  category is a required, explicit choice the user makes at submission
  time (paste, upload, or sample), never inferred from the text.
- **Investigation note**: while adding this, `bpe.py` on disk turned out to
  have *no* whitespace-cleaning step at all, despite a prior commit history
  entry ("Normalize whitespace before BPE analysis") describing one —
  `git log -- bpe.py` shows it was apparently dropped during the later
  "flatten `bpe_thesis/` to project root" commit. This change reintroduces
  that cleaning step, now split by category, so the regression is fixed as
  a side effect.
- **`category` is part of an experiment's identity, not just a metadata
  tag** (unlike the pre-existing `label` column, which stays purely
  cosmetic/free-text and has no effect on results or uniqueness). Why: the
  same raw text produces genuinely different stats depending on which
  cleaning rules ran, so it can be legitimate to analyse the same text
  under both categories on purpose (e.g. to see how much the category
  choice itself changes compression). Making category part of the
  uniqueness key — `UNIQUE (input_string, k, category)`, was
  `(input_string, k)` — lets both tracks be stored side by side under the
  same `input_hash` (hashing stays content-only) instead of the second
  submission silently reusing the first's row. `list_inputs` now
  `GROUP BY input_hash, category` and `rows_for_input` sorts
  `ORDER BY category, k` so the two tracks render as separate blocks
  rather than interleaved.
- **`normalize_code(text)`** (new, `bpe.py`): preserves all leading/internal
  spaces and tabs — only normalizes line endings, strips trailing per-line
  whitespace, and collapses runs of 3+ blank lines to one (blank lines stay
  meaningful block separators in code, so unlike the prose path they
  aren't removed entirely). `normalize_whitespace` (collapse
  horizontal-whitespace runs to one space, collapse blank-line runs to
  nothing) is now used only for `category="english"`.
- **No migration script**: `experiments.db` is local, gitignored,
  disposable experiment data, so the pre-category database was simply
  deleted (`rm experiments.db`) and recreated empty by
  `CREATE TABLE IF NOT EXISTS` on next run — consistent with this
  project's existing no-migration-tooling-at-this-size approach (see the
  utility-column entry below). Anyone else running this app needs to do
  the same `rm experiments.db`, since the old table lacks the new
  `category` column and constraint.
- **Note for later readers**: `original_chars` (and everything derived
  from it) reflects the *normalized* text length, not the raw input
  length — this was already true before this change, but is now more
  visible, since `code` normalization preserves far more characters than
  `english` normalization for the same raw input.

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