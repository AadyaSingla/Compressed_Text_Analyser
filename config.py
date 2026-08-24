"""Shared configuration for the compressed-text analyser (HTML app + JSON API)."""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
FIGURE_DIR = Path(__file__).parent / "figures"

# Size-graded samples: consecutive, non-overlapping slices cut from one
# English corpus (Shakespeare) and one source-code corpus (Python), at exact
# character lengths. Same source and register within a category, so a
# cross-file comparison varies input size and nothing else.
SAMPLE_SIZES = (10_000, 15_000, 20_000, 25_000, 30_000, 35_000, 40_000)

SAMPLES = {
    f"{stem}_{size // 1000}k": DATA_DIR / f"{stem}_{size // 1000}k.txt"
    for stem in ("english", "python")
    for size in SAMPLE_SIZES
}

MAX_INPUT_CHARS = 200_000
MAX_K = 2000