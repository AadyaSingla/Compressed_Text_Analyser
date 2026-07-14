"""Byte Pair Encoding (BPE) core for the compressed-text analyser.

Trains BPE from characters upward: repeatedly merges the most frequent
adjacent token pair, k times (or until no pair occurs at least twice).
"""

import re
from collections import Counter


def normalize_whitespace(text):
    """Collapse horizontal whitespace runs and blank lines before analysis."""
    # Intentionally discards indentation depth/style so stats reflect content redundancy, not formatting artifacts.
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n[ \t]*\n+', '\n', text)
    return text


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
    """Train BPE with k merges and return a stats dict for the experiment."""
    text = normalize_whitespace(text)
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