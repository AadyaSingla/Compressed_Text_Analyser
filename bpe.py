"""Byte Pair Encoding (BPE) core for the compressed-text analyser.

Trains BPE from characters upward: repeatedly merges the most frequent
adjacent token pair, k times (or until no pair occurs at least twice).
"""

import re
from collections import Counter


def normalize_whitespace(text):
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
        return normalize_whitespace(text)
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


def analyse(text, k):
    """Train BPE with k merges and return a stats dict for the experiment.

    Takes `text` exactly as given — cleaning, if wanted, is a separate
    step the caller applies beforehand (see `normalize()`), not something
    this function does implicitly."""
    tokens, merges = train_bpe(text, k)
    original_len = len(text)
    token_count = len(tokens)
    vocab_size = len(set(tokens))
    return {
        "k": k,
        "merges_applied": len(merges),
        "original_chars": original_len,
        "token_count": token_count,
        "vocab_size": vocab_size,
        "utility": original_len - token_count,
        "longest_token": max((t for t in set(tokens)), key=len, default=""),
        "merges": merges,
    }