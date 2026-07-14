



# Compressed Text Analyser

A small web app for running **Byte Pair Encoding (BPE)** experiments on any text.
You give it some text and a number **k** (how many merges to perform), and it
tells you how well BPE "compresses" that text: how many tokens are left, how big
the vocabulary grew, and what the longest learned token looks like. Every run is
saved to a local database so you can compare results and plot them against k.

Built as part of a thesis on compressed text analysis.

---

## What is BPE, in plain words?

Byte Pair Encoding starts by treating the text as a list of single characters.
Then it repeats one simple step, k times:

1. Look at every pair of neighbouring tokens (e.g. `t`+`h`, `h`+`e`, `e`+` `).
2. Count how often each pair appears.
3. Take the **most frequent pair** and glue it together into one new token
   (so `t` + `h` becomes `th` everywhere it appears side by side).

Each merge makes the text shorter (fewer tokens) but the vocabulary larger
(one new token per merge). Frequent patterns like `the `, `ing`, or `def ` get
merged into single tokens quickly — that's the "compression".

This is the same core idea used by tokenizers in large language models
(GPT, Llama, etc.), just in its simplest character-level form.

## How the BPE code runs, step by step

All of the algorithm lives in `bpe_thesis/bpe.py`, in two small functions:
`train_bpe(text, k)` does the merging, and `_merge_pair(tokens, pair)` applies
one merge. Here is exactly what happens when you run an experiment:

**1. Split the text into characters.**
`tokens = list(text)` turns `"the theme"` into
`['t','h','e',' ','t','h','e','m','e']`. At this point there are exactly as
many tokens as characters — this is the k = 0 state, compression ratio 1.0.

**2. Count every neighbouring pair.**
`Counter(zip(tokens, tokens[1:]))` slides a two-token window over the list and
counts each pair. For the example above: `(t,h)` appears 2×, `(h,e)` 2×,
`(e,' ')` 1×, `(' ',t)` 1×, `(e,m)` 1×, `(m,e)` 1×.

**3. Pick the winner.**
`pairs.most_common(1)[0]` gives the single most frequent pair and its count.

**4. Merge the winner everywhere.**
`_merge_pair` walks the token list once, left to right. Whenever it sees the
winning pair side by side, it writes the two tokens as one glued-together token
and jumps past both; otherwise it copies the token as-is. Merging `(t,h)` turns
the example into `['th','e',' ','th','e','m','e']` — 9 tokens became 7.

**5. Repeat from step 2**, on the *new* token list, until a stopping rule fires.
Merges can build on earlier merges: after `th` exists, the pair `(th,e)` can win
a later round and become the single token `the`. This is how BPE grows from
characters to syllables to whole words.

**6. Record the order of merges.**
Every winning pair is appended to a `merges` list, so the exact sequence of
decisions is known (`merges_applied` in the results is the length of this list).

### The rules, all in one place

These are every rule the implementation follows — they decide what gets merged,
when it stops, and how ties and edge cases are handled:

1. **Start from single characters.** The initial tokens are the characters of
   the text, including spaces, newlines, and punctuation. Nothing is
   lower-cased, stripped, or split into words first — whitespace is a token
   like any other, which is why learned tokens often end with a space
   (e.g. `the `).
2. **Only adjacent pairs can merge.** A pair means two tokens directly next to
   each other in the current list. BPE never merges tokens at a distance.
3. **Greedy choice: always merge the single most frequent pair.** One merge
   per round, no look-ahead. BPE never asks "would a different merge pay off
   more two steps from now?" — it just takes the current best. That greedy
   simplicity is the whole algorithm.
4. **Tie-breaking is "first counted wins."** If two pairs have the same count,
   `Counter.most_common` returns the one it encountered first, i.e. the pair
   whose first occurrence is earliest in the text. Ties are rare in real text
   but this makes runs fully deterministic: same text + same k ⇒ identical
   result, every time. (That determinism is also what makes the database's
   "reuse the stored row" rule safe.)
5. **A merge applies everywhere at once.** When a pair wins, *every*
   occurrence of it in the text is merged in that round, not just one.
6. **Overlaps resolve left to right.** In `aaa`, the pair `(a,a)` occurs
   twice but the occurrences overlap. The left-to-right scan merges positions
   0–1 and then continues *after* them, so the result is `['aa','a']` — a
   token is never used in two merges at once.
7. **Stop after k merges.** k is an upper bound you choose (capped at 2000 in
   the app).
8. **Stop early if the best pair occurs fewer than 2 times.** Merging a pair
   that appears once would just rename two tokens as one — the vocabulary grows
   but nothing repeats, so nothing is really compressed. This rule is why
   *merges applied* can be smaller than k, and it gives every text a natural
   ceiling: once no pair repeats, more k changes nothing.
9. **Stop if fewer than 2 tokens remain.** A text that has collapsed into a
   single token (or was empty) has no pairs left to merge.
10. **Merges are never undone.** Once glued, a token stays glued; later merges
    can only combine existing tokens into bigger ones.
11. **Characters, not bytes.** Tokens are Python strings, so an emoji or
    accented letter is one unit. (GPT-style tokenizers work on raw bytes
    instead; the character version is simpler and better suited to analysing
    text structure.)

### A worked example

Take `"banana bandana"` with k = 3:

| Round | Pair counts (top) | Winner | Tokens after merge |
| --- | --- | --- | --- |
| start | — | — | `b,a,n,a,n,a,␣,b,a,n,d,a,n,a` (14 tokens) |
| 1 | `(a,n)`×4, `(n,a)`×3, `(b,a)`×2 | `(a,n)` | `b,an,an,a,␣,b,an,d,an,a` (10) |
| 2 | `(an,a)`×2, `(b,an)`×2 | `(an,a)` | `b,an,ana,␣,b,an,d,ana` (8) |
| 3 | `(b,an)`×2 | `(b,an)` | `ban,ana,␣,ban,d,ana` (6) |

Note round 1: `(a,n)` and `(n,a)` overlap in `banana`, and the left-to-right
rule (rule 6) resolves it — `(a,n)` is counted 4 times but after merging, the
`n,a` pairs are gone. After 3 merges: 14 characters → 6 tokens, ratio 0.43,
vocab {`ban`,`ana`,`an`,`d`,`␣`} = 5, longest token `ana`.

## What the app measures, and why

For each run (one input text + one value of k) the app calls
`bpe.analyse(text, k)`, which trains BPE and then compares the token list
*after* merging with the raw text *before* merging. Everything it reports comes
from that before/after comparison:

| Term | How it's computed | Why it matters |
|---|---|---|
| **k** | The number you typed in the form. | The independent variable of the experiment — everything else is measured *as a function of k*. |
| **Merges applied** | `len(merges)` — the number of rounds that actually ran. | Shows whether the text hit its natural ceiling (rule 8) before reaching k. If this is below k, raising k further changes nothing for this text. |
| **Chars** | `len(text)` — characters in the original input. | The baseline. It's also the token count at k = 0, which anchors the compression ratio at exactly 1.0. |
| **Tokens** | `len(tokens)` — tokens remaining after all merges. | The direct measure of compression: every successful merge round removes one token per occurrence of the winning pair. |
| **Vocab** | `len(set(tokens))` — number of *distinct* tokens in the final list. | The cost side of the trade-off. Compressing isn't free: each merge can add a new symbol you'd need in your "dictionary" to decode the text. Real tokenizers care about exactly this number (vocabulary size). |
| **Ratio** | `tokens / chars` (0 for empty input). | The headline number: how much of the original length remains. 1.0 = untouched; 0.25 = the text shrank to a quarter of its length (each token stands for 4 characters on average) — lower means better compression. It is a *lossless* measure — the original text is always exactly recoverable from the tokens. |
| **Longest token** | The longest string in the final vocabulary. | A qualitative window into what BPE learned. In prose it's usually a frequent word with its space (`the `); in code it can be a whole keyword or repeated snippet (`def `, `return `). If it looks surprising, it tells you something about the text's repetitiveness. |

### Why sweep over k instead of running once?

A single run tells you one point; the shape of the curve is where the insight
is. With a **sweep step**, the app runs k = 0, step, 2·step, … up to your k
(k = 0 included on purpose, so the plot starts from the ratio-1.0 baseline),
and the results page plots two curves:

- **Compression ratio vs k** falls steeply at first — the earliest merges grab
  the most frequent pairs, which remove the most tokens — and then flattens as
  only rare pairs are left. Classic diminishing returns.
- **Vocabulary size vs k** climbs roughly one token per merge until the early
  stop kicks in, then goes flat.

Read together, the two plots show the fundamental BPE trade-off: **you buy a
shorter text by paying with a bigger vocabulary.** Where the ratio curve
flattens is, in effect, the "reasonable k" for that text — and comparing the
curves of different inputs (prose vs code, short vs long) shows how the
*structure* of a text determines how compressible it is, which is the question
this analyser exists to explore.

## Running the app

```bash
.venv/bin/python main.py
```

Then open <http://127.0.0.1:5001>.

Dependencies: Flask and matplotlib (already installed in `.venv`).
The SQLite database (`bpe_thesis/experiments.db`) is created automatically.

## Using it

1. Provide text one of three ways: **paste** it, **upload** a file, or pick a
   built-in **sample** (English prose or Python code). If more than one is
   given, priority is: sample → upload → pasted text.
2. Choose **k** (max merges, up to 2000) and optionally a **sweep step**
   (0 means one single run at k).
3. Click **Run analysis**. You land on the results page with the plot and a
   table of all stored runs for that input.

Limits: input up to 200,000 characters, k up to 2000.

## Project layout

```
main.py                      Entry point — starts the Flask server on port 5001
bpe_thesis/
  bpe.py                     The BPE algorithm + the analyse() stats function
  app.py                     Flask routes: form handling, running experiments, plotting
  db.py                      SQLite storage (schema, save/load, dedup logic)
  templates/
    base.html                Shared layout + all CSS
    index.html               Home page: input form + list of stored inputs
    results.html             Results page: plot + stats table + input preview
  data/
    sample_english.txt       Built-in English sample
    sample_code.py           Built-in Python-code sample
    uploads/                 Copies of uploaded files
  experiments.db             SQLite database (created on first run)
```

## How results are stored (and why there are no duplicates)

- Each experiment row is **unique on (input text, k)**. Re-running the same
  text with the same k reuses the stored row instead of inserting a duplicate —
  the flash message tells you how many rows were new vs already stored.
- Inputs are grouped by a short **SHA-256 hash** of the text, so the same text
  pasted twice (even with different labels) lands on the same results page.
- Deleting an input removes **all** of its runs.

## Reading the plots

- **Compression ratio vs k**: drops quickly at first (the most frequent pairs
  give the biggest wins), then flattens — classic diminishing returns.
- **Vocabulary size vs k**: grows as merges add new tokens. Comparing the two
  curves shows the core BPE trade-off: *shorter text vs bigger vocabulary*.
- Different kinds of text behave differently — repetitive code usually
  compresses better than prose. Try both samples and compare.
