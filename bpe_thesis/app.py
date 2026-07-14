"""Flask app for the compressed-text analyser (BPE thesis experiments)."""

import csv
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import bpe
import db

app = Flask(__name__)
app.secret_key = "bpe-thesis-dev-key"

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

SAMPLES = {
    "english": DATA_DIR / "sample_english.txt",
    "code": DATA_DIR / "sample_code.py",
}

MAX_INPUT_CHARS = 200_000
MAX_K = 2000


def _resolve_input():
    """Get (label, text) from the form: pasted text, upload, or sample."""
    sample = request.form.get("sample", "")
    upload = request.files.get("file")
    pasted = request.form.get("text", "").strip()

    if sample in SAMPLES:
        return sample, SAMPLES[sample].read_text(encoding="utf-8")
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / upload.filename).write_text(text, encoding="utf-8")
        return upload.filename, text
    if pasted:
        label = pasted[:30].replace("\n", " ")
        return label, pasted
    return None, None


def _parse_ks():
    """Parse the k specification: a single k, or a range with a step."""
    k_max = int(request.form.get("k_max", 100))
    step = int(request.form.get("k_step", 0))
    k_max = max(0, min(k_max, MAX_K))
    if step > 0:
        return list(range(0, k_max + 1, step)) or [k_max]
    return [k_max]


@app.route("/")
def index():
    conn = db.connect()
    inputs = db.list_inputs(conn)
    conn.close()
    return render_template("index.html", inputs=inputs, samples=sorted(SAMPLES))


@app.route("/run", methods=["POST"])
def run():
    label, text = _resolve_input()
    if not text:
        flash("Provide some text: paste it, upload a file, or pick a sample.")
        return redirect(url_for("index"))
    if len(text) > MAX_INPUT_CHARS:
        flash(f"Input too large ({len(text)} chars, limit {MAX_INPUT_CHARS}).")
        return redirect(url_for("index"))

    try:
        ks = _parse_ks()
    except ValueError:
        flash("k and step must be whole numbers.")
        return redirect(url_for("index"))

    conn = db.connect()
    new_rows = 0
    for k in ks:
        if db.get_experiment(conn, text, k):
            continue
        stats = bpe.analyse(text, k)
        _, created = db.save_experiment(conn, label, text, stats)
        new_rows += created
    conn.close()
    flash(f"Ran k = {ks[0]}..{ks[-1]}: {new_rows} new experiment(s), "
          f"{len(ks) - new_rows} already stored.")
    return redirect(url_for("results", ihash=db.input_hash(text)))


@app.route("/results/<ihash>")
def results(ihash):
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)
    preview = rows[0]["input_string"][:400]
    return render_template("results.html", rows=rows, ihash=ihash,
                           label=rows[0]["label"], preview=preview)


def _draw_plots(ax1, ax2, rows):
    ks = [r["k"] for r in rows]
    utilities = [r["utility"] for r in rows]
    vocab = [r["vocab_size"] for r in rows]

    ax1.plot(ks, utilities, marker="o", color="#4058B0")
    ax1.set_xlabel("k (BPE merges)")
    ax1.set_ylabel("Compression utility (|s| - |s_k|), characters saved")
    ax1.set_title("Compression utility vs k")
    ax1.grid(True, alpha=0.3)

    ax2.plot(ks, vocab, marker="o", color="#B05840")
    ax2.set_xlabel("k (BPE merges)")
    ax2.set_ylabel("Vocabulary size")
    ax2.set_title("Vocabulary size vs k")
    ax2.grid(True, alpha=0.3)


def _send_fig(fig, download_name=None):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    if download_name:
        return send_file(buf, mimetype="image/png", as_attachment=True,
                         download_name=download_name)
    return send_file(buf, mimetype="image/png")


@app.route("/plot/<ihash>.png")
def plot(ihash):
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    _draw_plots(ax1, ax2, rows)
    fig.suptitle(rows[0]["label"])
    fig.tight_layout()
    return _send_fig(fig)


@app.route("/report/<ihash>.png")
def report(ihash):
    """Graphs plus the results table rendered into a single PNG."""
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)

    table_height = 0.32 * (len(rows) + 1)
    fig = plt.figure(figsize=(10, 4.5 + table_height), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=[4, table_height])
    _draw_plots(fig.add_subplot(gs[0, 0]), fig.add_subplot(gs[0, 1]), rows)

    ax = fig.add_subplot(gs[1, :])
    ax.axis("off")
    columns = ["k", "Merges applied", "Chars", "Tokens", "Vocab", "Utility",
               "Longest token"]
    def _clip(token):
        token = token.replace("\n", "\\n")
        return token if len(token) <= 18 else token[:17] + "…"

    cells = [
        [r["k"], r["merges_applied"], r["original_chars"], r["token_count"],
         r["vocab_size"], str(r["utility"]),
         _clip(r["longest_token"])]
        for r in rows
    ]
    table = ax.table(cellText=cells, colLabels=columns, cellLoc="center",
                     bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor("#e3e6ee")
        if row == 0:
            cell.set_text_props(weight="bold")
            cell.set_facecolor("#eef2ff")

    fig.suptitle(rows[0]["label"])
    return _send_fig(fig, download_name=f"bpe_report_{ihash}.png")


@app.route("/download/<ihash>.csv")
def download_csv(ihash):
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)

    columns = ["label", "k", "merges_applied", "original_chars", "token_count",
               "vocab_size", "utility", "longest_token", "created_at"]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(columns)
    for r in rows:
        writer.writerow([r[c] for c in columns])
    buf = io.BytesIO(out.getvalue().encode("utf-8"))
    return send_file(buf, mimetype="text/csv", as_attachment=True,
                     download_name=f"bpe_results_{ihash}.csv")


@app.route("/delete/<ihash>", methods=["POST"])
def delete(ihash):
    conn = db.connect()
    db.delete_input(conn, ihash)
    conn.close()
    flash("Deleted all experiments for that input.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)