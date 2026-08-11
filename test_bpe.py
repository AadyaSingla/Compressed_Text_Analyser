"""Plain-assert tests for bpe.py's k* detection and summary logic.

Run directly: python test_bpe.py
"""

import bpe


def test_find_k_star_on_concave_curve():
    """A curve with sharp early gains that flattens out should have its
    k* near the visible bend, not at the very start or very end."""
    utilities = [0, 8, 14, 18, 19, 19.5, 19.8, 19.9, 19.95, 19.98, 20]
    k_star = bpe.find_k_star(utilities)
    assert 2 <= k_star <= 4, f"expected k* near k=3, got {k_star}"


def test_find_k_star_degenerate_cases():
    """A single point or an all-zero curve has no meaningful k*: k=0."""
    assert bpe.find_k_star([5]) == 0
    assert bpe.find_k_star([0, 0, 0]) == 0


def test_summarize_on_short_string():
    """summarize() should return internally consistent fields for a
    small, real piece of text."""
    text = "the cat sat on the mat the cat sat"
    summary = bpe.summarize(text, "english", "short-test")
    assert summary["size_chars"] == len(text)
    assert 0 <= summary["k_star"] <= summary["saturation_k"]
    assert 0.0 <= summary["utility_ratio"] <= 1.0
    assert summary["max_utility"] >= summary["utility_at_k_star"] >= 0


if __name__ == "__main__":
    test_find_k_star_on_concave_curve()
    test_find_k_star_degenerate_cases()
    test_summarize_on_short_string()
    print("All tests passed.")
