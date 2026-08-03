"""Shared configuration for the compressed-text analyser (HTML app + JSON API)."""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

SAMPLES = {
    "english": DATA_DIR / "sample_english.txt",
    "code": DATA_DIR / "sample_code.py",
}

MAX_INPUT_CHARS = 200_000
MAX_K = 2000