"""Byte Pair Encoding (BPE) core for the compressed-text analyser.

Trains BPE from characters upward: repeatedly merges the most frequent
adjacent token pair, k times (or until no pair occurs at least twice).
"""

import re
from collections import Counter


def normalize_english(text):
    """Prose cleaning for category "english": newlines become spaces (word
    breaks, not structure), punctuation/symbols are stripped entirely,
    whitespace runs collapse to one space, and case is flattened. Word
    boundaries are the only whitespace that survives."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = text.replace('\n', ' ')
    text = re.sub(r'[^a-zA-Z0-9 \t]', '', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = text.strip()
    return text.lower()


def normalize_code(text):
    """Cleaning for category "code": preserve everything structurally
    significant to Python — leading indentation (beyond tabs->4-spaces),
    blank lines, punctuation/operators, case, comments, docstrings.
    Only: standardize line endings, expand indentation tabs to 4 spaces
    (so tab- and space-indented code don't look different to BPE), collapse
    space runs after the indentation (spacing between symbols carries no
    meaning), and strip trailing whitespace. String-literal contents are
    not special-cased — distinguishing them reliably isn't worth the
    complexity here, so BPE just compresses whatever spacing survives."""
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    cleaned_lines = []
    for line in text.split('\n'):
        line = line.rstrip(' \t')
        rest = line.lstrip(' \t')
        indent = line[: len(line) - len(rest)].replace('\t', '    ')
        rest = re.sub(r' {2,}', ' ', rest)
        cleaned_lines.append(indent + rest)
    return '\n'.join(cleaned_lines)


def normalize(text, category):
    """Dispatch to the category-appropriate cleaning rules."""
    if category == "english":
        return normalize_english(text)
    if category == "code":
        return normalize_code(text)
    raise ValueError(f"unknown category: {category!r}")


def _merge_pair(tokens, pair):
    """Return a new token list with every occurrence of `pair` merged."""
    merged = pair[0] + pair[1]
    out = []
    i = 0
    while i < len(tokens):
        if i < len(tokens) - 1 and tokens[i] == pair[0] and tokens[i + 1] == pair[1]:
            out.append(merged)
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return out


def train_bpe(text, k):
    """Run up to k BPE merges on `text` starting from single characters.

    Returns (tokens, merges) where merges is the ordered list of pairs
    that were merged. Stops early if no pair occurs at least twice.
    """
    tokens = list(text)
    merges = []
    for _ in range(k):
        if len(tokens) < 2:
            break
        pairs = Counter(zip(tokens, tokens[1:]))
        best, count = pairs.most_common(1)[0]
        if count < 2:
            break
        merges.append(best)
        tokens = _merge_pair(tokens, best)
    return tokens, merges


def analyse_series(text):
    """Run BPE once from single characters, recording stats after every merge.

    Stops at the same natural point as train_bpe (no pair occurs at least
    twice), so it replaces calling analyse() once per k: a single pass
    yields the whole utility curve find_elbow_k() needs. Returns a list of
    dicts, one per k from 0 (the starting state) to the stop, each with:
    k, token_count, utility, distinct_tokens, learned_vocab, longest_token.
    Pure — no I/O.
    """
    tokens = list(text)
    base_alphabet = len(set(text))

    def _record(k, tokens):
        return {
            "k": k,
            "token_count": len(tokens),
            "utility": len(text) - len(tokens),
            "distinct_tokens": len(set(tokens)),
            "learned_vocab": base_alphabet + k,
            "longest_token": max((t for t in set(tokens)), key=len, default=""),
        }

    series = [_record(0, tokens)]
    k = 0
    while len(tokens) >= 2:
        pairs = Counter(zip(tokens, tokens[1:]))
        best, count = pairs.most_common(1)[0]
        if count < 2:
            break
        tokens = _merge_pair(tokens, best)
        k += 1
        series.append(_record(k, tokens))
    return series


def find_elbow_k(utilities):
    """Return the k that best trades off compression against merge count.

    `utilities` is indexed by k (utility after k merges), k=0..saturation.
    Uses the knee / distance-to-chord method (Satopaa et al., 2011,
    "Finding a 'Kneedle' in a Haystack"): normalize both axes to [0, 1] and
    return the k whose point sits farthest above the straight chord from
    (0, 0) to (1, 1). Pure, so it's directly unit-testable.
    """
    k_max = len(utilities) - 1
    if k_max == 0:
        return 0
    u_max = utilities[k_max]
    if u_max == 0:
        return 0
    best_k, best_dist = 0, float("-inf")
    for k, u in enumerate(utilities):
        x = k / k_max
        y = u / u_max
        dist = y - x
        if dist > best_dist:
            best_k, best_dist = k, dist
    return best_k


def summarize(text, category, label):
    """Summarize one file's BPE behaviour as a single flat dict: size
    stats plus the elbow point (the k of diminishing returns).

    `text` must already be normalized by the caller, same convention as
    analyse(). Combines analyse_series() and find_elbow_k() into the row
    shape stored by db.save_summary().
    """
    series = analyse_series(text)
    utilities = [r["utility"] for r in series]
    elbow_k = find_elbow_k(utilities)
    elbow = series[elbow_k]
    saturation = series[-1]

    base_alphabet = len(set(text))
    max_utility = saturation["utility"]

    return {
        "label": label,
        "category": category,
        "size_chars": len(text),
        "elbow_k": elbow_k,
        "utility_at_elbow": elbow["utility"],
        "tokens_at_elbow": elbow["token_count"],
        "learned_vocab_at_elbow": base_alphabet + elbow_k,
        "max_utility": max_utility,
        "pct_captured_at_elbow": (elbow["utility"] / max_utility) if max_utility else 0.0,
        "longest_token_at_elbow": elbow["longest_token"],
        "saturation_k": saturation["k"],
    }


def analyse(text, k):
    """Train BPE with k merges and return a stats dict for the experiment.

    Takes `text` exactly as given — cleaning, if wanted, is a separate
    step the caller applies beforehand (see `normalize()`), not something
    this function does implicitly."""
    tokens, merges = train_bpe(text, k)
    original_len = len(text)
    token_count = len(tokens)
    distinct_tokens = len(set(tokens))
    learned_vocab = len(set(text)) + len(merges)
    return {
        "k": k,
        "merges_applied": len(merges),
        "original_chars": original_len,
        "token_count": token_count,
        "distinct_tokens": distinct_tokens,
        "learned_vocab": learned_vocab,
        "utility": original_len - token_count,
        "longest_token": max((t for t in set(tokens)), key=len, default=""),
        "merges": merges,
    }