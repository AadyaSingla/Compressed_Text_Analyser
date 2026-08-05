"""Flask app for the compressed-text analyser (BPE thesis experiments)."""

import io
from collections import defaultdict

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
from flasgger import Swagger

import bpe
import db
from api import api_bp
from config import MAX_INPUT_CHARS, MAX_K, SAMPLES, UPLOAD_DIR

app = Flask(__name__)
app.secret_key = "bpe-thesis-dev-key"
app.register_blueprint(api_bp)

app.config["SWAGGER"] = {
    "title": "Compressed Text Analyser API",
    "specs_route": "/apidocs/",
}
Swagger(app)


VALID_CATEGORIES = {"code", "english"}


def _resolve_input():
    """Get (label, text, category) from the form: pasted text, upload, or
    sample. Category is a separate required field, never inferred, so the
    same text can deliberately be run under either category."""
    sample = request.form.get("sample", "")
    upload = request.files.get("file")
    pasted = request.form.get("text", "").strip()
    category = request.form.get("category", "")

    if sample in SAMPLES:
        return sample, SAMPLES[sample].read_text(encoding="utf-8"), category
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / upload.filename).write_text(text, encoding="utf-8")
        return upload.filename, text, category
    if pasted:
        label = pasted[:30].replace("\n", " ")
        return label, pasted, category
    return None, None, category


def _parse_ks():
    """Parse the k specification: a single k, or a range with a step."""
    k_max = int(request.form.get("k_max", 100))
    step = int(request.form.get("k_step", 0))
    k_max = max(0, min(k_max, MAX_K))
    if step > 0:
        return list(range(0, k_max + 1, step)) or [k_max]
    return [k_max]


def _render_index(**prefill):
    conn = db.connect()
    inputs = db.list_inputs(conn)
    conn.close()
    return render_template("index.html", inputs=inputs, samples=sorted(SAMPLES),
                           **prefill)


@app.route("/")
def index():
    return _render_index()


@app.route("/clean", methods=["POST"])
def clean():
    """Clean the submitted text and hand it back in the textarea for
    review, without running BPE. A separate step from Analyse — cleaning
    is something the user opts into explicitly, not a flag bundled into
    the analysis run."""
    label, text, category = _resolve_input()
    if not text:
        flash("Provide some text: paste it, upload a file, or pick a sample.")
        return redirect(url_for("index"))
    if category not in VALID_CATEGORIES:
        flash("Choose a category: source code or English language.")
        return redirect(url_for("index"))
    if len(text) > MAX_INPUT_CHARS:
        flash(f"Input too large ({len(text)} chars, limit {MAX_INPUT_CHARS}).")
        return redirect(url_for("index"))

    cleaned_text = bpe.normalize(text, category)
    flash("Text cleaned below — click Run analysis when you're ready.")
    return _render_index(
        prefill_text=cleaned_text,
        prefill_category=category,
        prefill_cleaned=True,
        prefill_k_max=request.form.get("k_max", "200"),
        prefill_k_step=request.form.get("k_step", "25"),
    )


@app.route("/run", methods=["POST"])
def run():
    label, text, category = _resolve_input()
    if not text:
        flash("Provide some text: paste it, upload a file, or pick a sample.")
        return redirect(url_for("index"))
    if category not in VALID_CATEGORIES:
        flash("Choose a category: source code or English language.")
        return redirect(url_for("index"))
    if len(text) > MAX_INPUT_CHARS:
        flash(f"Input too large ({len(text)} chars, limit {MAX_INPUT_CHARS}).")
        return redirect(url_for("index"))

    cleaned = request.form.get("was_cleaned") == "1"

    try:
        ks = _parse_ks()
    except ValueError:
        flash("k and step must be whole numbers.")
        return redirect(url_for("index"))

    conn = db.connect()
    new_rows = 0
    for k in ks:
        if db.get_experiment(conn, text, k, category):
            continue
        stats = bpe.analyse(text, k)
        _, created = db.save_experiment(conn, label, category, cleaned, text, stats)
        new_rows += created
    summary = bpe.summarize(text, category, label)
    db.save_summary(conn, db.input_hash(text), summary)
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
    full_text = rows[0]["input_string"]
    preview = full_text[:400]
    return render_template("results.html", rows=rows, ihash=ihash,
                           label=rows[0]["label"], preview=preview,
                           truncated=len(full_text) > 400)


@app.route("/plot/<ihash>.png")
def plot(ihash):
    """Compression utility and vocabulary size vs k, as a PNG. One line
    per category if a hash has rows from more than one (still possible —
    category, unlike cleaned, stays part of an experiment's identity)."""
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)

    by_category = defaultdict(list)
    for r in rows:
        by_category[r["category"]].append(r)
    colors = {"code": "#4058B0", "english": "#B05840"}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    for category, crows in by_category.items():
        ks = [r["k"] for r in crows]
        color = colors.get(category)
        ax1.plot(ks, [r["utility"] for r in crows], marker="o", label=category, color=color)
        ax2.plot(ks, [r["vocab_size"] for r in crows], marker="o", label=category, color=color)

    ax1.set_xlabel("k (BPE merges)")
    ax1.set_ylabel("Compression utility (|s| - |s_k|), characters saved")
    ax1.set_title("Compression utility vs k")
    ax1.grid(True, alpha=0.3)

    ax2.set_xlabel("k (BPE merges)")
    ax2.set_ylabel("Vocabulary size")
    ax2.set_title("Vocabulary size vs k")
    ax2.grid(True, alpha=0.3)

    if len(by_category) > 1:
        ax1.legend()
        ax2.legend()

    status_word = "Cleaned" if rows[0]["cleaned"] else "Raw"
    fig.suptitle(f"{rows[0]['label']} — {status_word}")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/analysis")
def analysis():
    """Cross-file summary: one row per analysed input, with elbow-point
    stats, plus links to the two comparison plots."""
    conn = db.connect()
    summaries = db.get_all_summaries(conn)
    conn.close()
    return render_template("analysis.html", summaries=summaries)


def _analysis_scatter(y_field, y_label, title):
    """Category-coloured scatter PNG of `y_field` vs size_chars, shared by
    the /analysis/elbow.png and /analysis/captured.png routes."""
    conn = db.connect()
    summaries = db.get_all_summaries(conn)
    conn.close()

    by_category = defaultdict(list)
    for s in summaries:
        by_category[s["category"]].append(s)
    colors = {"code": "#4058B0", "english": "#B05840"}

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for category, srows in by_category.items():
        xs = [s["size_chars"] for s in srows]
        ys = [s[y_field] for s in srows]
        ax.scatter(xs, ys, label=category, color=colors.get(category))

    ax.set_xlabel("Input size (characters)")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    if len(by_category) > 1:
        ax.legend()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/analysis/elbow.png")
def analysis_elbow_plot():
    return _analysis_scatter("elbow_k", "Elbow k (BPE merges)", "Elbow k vs input size")


@app.route("/analysis/captured.png")
def analysis_captured_plot():
    return _analysis_scatter(
        "pct_captured_at_elbow",
        "% of max utility captured at elbow",
        "Utility captured at elbow vs input size",
    )


@app.route("/delete/<ihash>", methods=["POST"])
def delete(ihash):
    conn = db.connect()
    db.delete_input(conn, ihash)
    conn.close()
    flash("Deleted all experiments for that input.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)