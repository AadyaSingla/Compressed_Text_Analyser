"""Entry point: run the BPE compressed-text analyser web app."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "bpe_thesis"))

from app import app

if __name__ == "__main__":
    app.run(debug=True, port=5001)