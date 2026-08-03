"""Entry point: run the BPE compressed-text analyser web app."""

from app import app

if __name__ == "__main__":
    app.run(debug=True, port=5001)
