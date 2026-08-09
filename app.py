"""Flask app for the compressed-text analyser (BPE thesis experiments)."""

import io
import re
from collections import defaultdict
from datetime import datetime

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
from config import FIGURE_DIR, MAX_INPUT_CHARS, MAX_K, SAMPLES, UPLOAD_DIR

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
    """Get (label, text, category, cleaned) from the form.

    Text comes from a bundled sample or an uploaded file — those are the
    only two ways in. The third case isn't a user-typed input at all: it's
    the cleaned text handed back by a previous Clean click, carried in a
    hidden field so Run BPE can analyse it. Sample and upload win over it,
    so choosing a new source after cleaning analyses the new source rather
    than stale cleaned text.

    `cleaned` is derived from which source won, not from a form flag, so a
    row can never be labelled cleaned when it isn't. Category is a separate
    required field, never inferred, so the same text can deliberately be
    run under either category.
    """
    sample = request.form.get("sample", "")
    upload = request.files.get("file")
    carried = request.form.get("cleaned_text", "")
    category = request.form.get("category", "")

    if sample in SAMPLES:
        return sample, SAMPLES[sample].read_text(encoding="utf-8"), category, False
    if upload and upload.filename:
        text = upload.read().decode("utf-8", errors="replace")
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        (UPLOAD_DIR / upload.filename).write_text(text, encoding="utf-8")
        return upload.filename, text, category, False
    if carried.strip():
        # Round-tripping through a hidden field can turn newlines into CRLF
        # on the way back. Both cleaning rules guarantee \n only, so undoing
        # that is a no-op on untouched text and a repair otherwise — without
        # it, the text analysed would differ from the text just displayed.
        carried = carried.replace("\r\n", "\n").replace("\r", "\n")
        label = request.form.get("cleaned_label", "") or carried[:30].replace("\n", " ")
        return label, carried, category, True
    return None, None, category, False


def _parse_ks():
    """Parse the k specification: a single k, or a range with a step."""
    k_max = int(request.form.get("k_max", 100))
    step = int(request.form.get("k_step", 0))
    k_max = max(0, min(k_max, MAX_K))
    if step > 0:
        return list(range(0, k_max + 1, step)) or [k_max]
    return [k_max]


def _sample_names():
    """Sample names grouped by category, ascending by size. Sorting the names
    as plain strings happens to read correctly while every size is two digits,
    but would put a `english_5k` after `english_35k` — so sort on the number."""
    return sorted(SAMPLES, key=lambda name: (name.rsplit("_", 1)[0],
                                             int(name.rsplit("_", 1)[1].rstrip("k"))))


def _render_index(**prefill):
    conn = db.connect()
    inputs = db.list_inputs(conn)
    conn.close()
    return render_template("index.html", inputs=inputs, samples=_sample_names(),
                           **prefill)


@app.route("/")
def index():
    return _render_index()


@app.route("/clean", methods=["POST"])
def clean():
    """Clean the selected file's text and hand it back for review, without
    running BPE. A separate step from Run BPE — cleaning is something the
    user opts into explicitly, not a flag bundled into the analysis run.
    The result is shown read-only and carried in a hidden field, so the
    next Run BPE click analyses exactly the text on screen."""
    label, text, category, _ = _resolve_input()
    if not text:
        flash("Choose an input: upload a file or pick a sample.")
        return redirect(url_for("index"))
    if category not in VALID_CATEGORIES:
        flash("Choose a category: source code or English language.")
        return redirect(url_for("index"))
    if len(text) > MAX_INPUT_CHARS:
        flash(f"Input too large ({len(text)} chars, limit {MAX_INPUT_CHARS}).")
        return redirect(url_for("index"))

    cleaned_text = bpe.normalize(text, category)
    flash("Text cleaned below — click Run BPE when you're ready.")
    return _render_index(
        prefill_text=cleaned_text,
        prefill_label=label,
        prefill_category=category,
        prefill_k_max=request.form.get("k_max", "200"),
        prefill_k_step=request.form.get("k_step", "25"),
    )


@app.route("/run", methods=["POST"])
def run():
    label, text, category, cleaned = _resolve_input()
    if not text:
        flash("Choose an input: upload a file or pick a sample.")
        return redirect(url_for("index"))
    if category not in VALID_CATEGORIES:
        flash("Choose a category: source code or English language.")
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


def _serve_png(fig):
    """Send a figure to the browser as a PNG, closing it afterwards."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


def _save_pdf(fig, stem):
    """Write a figure to FIGURE_DIR as a vector PDF and close it. Stable
    filename per graph, so re-saving replaces the previous version rather
    than piling up near-identical files."""
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    path = FIGURE_DIR / f"{stem}.pdf"
    fig.savefig(path, format="pdf")
    plt.close(fig)
    return path


def _safe_stem(label):
    """Filename-safe version of a label. Labels come from sample names and
    uploaded filenames, so they can carry separators and spaces."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", label).strip("_")
    return cleaned or "figure"


def _build_results_figure(ihash):
    """Compression utility, and learned vocabulary vs distinct tokens, vs k. One line per category
    if a hash has rows from more than one (still possible — category,
    unlike cleaned, stays part of an experiment's identity)."""
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
        ax2.plot(ks, [r["learned_vocab"] for r in crows], marker="o",
                 label=f"{category} — learned vocab (memory)", color=color)
        ax2.plot(ks, [r["distinct_tokens"] for r in crows], marker="o", linestyle="--",
                 label=f"{category} — distinct tokens", color=color)

    ax1.set_xlabel("k (BPE merges)")
    ax1.set_ylabel("Compression utility (|s| - |s_k|), characters saved")
    ax1.set_title("Compression utility vs k")
    ax1.grid(True, alpha=0.3)

    ax2.set_xlabel("k (BPE merges)")
    ax2.set_ylabel("Vocabulary (tokens)")
    ax2.set_title("Learned vocabulary & distinct tokens vs k")
    ax2.grid(True, alpha=0.3)

    ax2.legend(fontsize=8)
    if len(by_category) > 1:
        ax1.legend()

    status_word = "Cleaned" if rows[0]["cleaned"] else "Raw"
    fig.suptitle(f"{rows[0]['label']} — {status_word}")
    fig.tight_layout()
    return fig


@app.route("/plot/<ihash>.png")
def plot(ihash):
    return _serve_png(_build_results_figure(ihash))


@app.route("/save/results/<ihash>", methods=["POST"])
def save_results_plot(ihash):
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        abort(404)
    stem = f"results_{_safe_stem(rows[0]['label'])}_{ihash[:8]}"
    path = _save_pdf(_build_results_figure(ihash), stem)
    flash(f"Saved {path.name} — see Saved figures.")
    return redirect(url_for("results", ihash=ihash))


@app.route("/analysis")
def analysis():
    """Cross-file summary: one row per analysed input, with knee-point
    stats, plus links to the two comparison plots."""
    conn = db.connect()
    summaries = db.get_all_summaries(conn)
    conn.close()
    return render_template("analysis.html", summaries=summaries)


def _build_analysis_figure(y_field, y_label, title):
    """Category-coloured plot of `y_field` vs size_chars — one marked line per
    category, so the trend across the size-graded samples is visible and not
    just the individual points. Shared by the /analysis/knee.png and
    /analysis/captured.png routes and their Save PDF counterparts."""
    conn = db.connect()
    summaries = db.get_all_summaries(conn)
    conn.close()

    by_category = defaultdict(list)
    for s in summaries:
        by_category[s["category"]].append(s)
    colors = {"code": "#4058B0", "english": "#B05840"}

    fig, ax = plt.subplots(figsize=(6, 4.5))
    for category, srows in by_category.items():
        # Sort here rather than relying on the query's ORDER BY: a line drawn
        # through points in any other order zigzags back on itself.
        srows = sorted(srows, key=lambda r: r["size_chars"])
        xs = [s["size_chars"] for s in srows]
        ys = [s[y_field] for s in srows]
        ax.plot(xs, ys, marker="o", markersize=7, linewidth=2,
                label=category, color=colors.get(category))

    ax.set_xlabel("Input size (characters)")
    ax.set_ylabel(y_label)
    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    if len(by_category) > 1:
        ax.legend()
    fig.tight_layout()
    return fig


# The two cross-file plots differ only in which summary field they chart, so
# their arguments live here and both the PNG and the Save PDF routes read them.
ANALYSIS_PLOTS = {
    "knee": ("knee_k", "Knee k (BPE merges)", "Knee k vs input size"),
    "captured": ("pct_captured_at_knee", "% of max utility captured at knee",
                 "Utility captured at knee vs input size"),
}


@app.route("/analysis/knee.png")
def analysis_knee_plot():
    return _serve_png(_build_analysis_figure(*ANALYSIS_PLOTS["knee"]))


@app.route("/analysis/captured.png")
def analysis_captured_plot():
    return _serve_png(_build_analysis_figure(*ANALYSIS_PLOTS["captured"]))


@app.route("/save/analysis/<name>", methods=["POST"])
def save_analysis_plot(name):
    if name not in ANALYSIS_PLOTS:
        abort(404)
    path = _save_pdf(_build_analysis_figure(*ANALYSIS_PLOTS[name]), f"analysis_{name}")
    flash(f"Saved {path.name} — see Saved figures.")
    return redirect(url_for("analysis"))


def _figure_path(name):
    """Resolve a saved-figure filename to a path inside FIGURE_DIR.

    `name` arrives from the URL, so it is checked twice: the pattern rules out
    separators and traversal segments up front, and the resolved-parent check
    catches anything that slips through (a symlink pointing out of the folder,
    say). Anything else 404s rather than reaching the filesystem.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.-]+\.pdf", name):
        abort(404)
    path = FIGURE_DIR / name
    if path.resolve().parent != FIGURE_DIR.resolve() or not path.is_file():
        abort(404)
    return path


@app.route("/figures")
def figures():
    """Every PDF saved so far, newest first."""
    saved = []
    if FIGURE_DIR.is_dir():
        for path in FIGURE_DIR.glob("*.pdf"):
            stat = path.stat()
            saved.append({
                "name": path.name,
                "mtime": stat.st_mtime,
                "saved_at": datetime.fromtimestamp(stat.st_mtime).strftime("%d %b %Y, %H:%M"),
                "size_kb": stat.st_size / 1024,
            })
        saved.sort(key=lambda f: f["mtime"], reverse=True)
    return render_template("figures.html", figures=saved)


@app.route("/figures/<name>")
def figure_file(name):
    return send_file(_figure_path(name), mimetype="application/pdf")


@app.route("/figures/<name>/delete", methods=["POST"])
def delete_figure(name):
    _figure_path(name).unlink()
    flash(f"Deleted {name}.")
    return redirect(url_for("figures"))


@app.route("/delete/<ihash>", methods=["POST"])
def delete(ihash):
    conn = db.connect()
    db.delete_input(conn, ihash)
    conn.close()
    flash("Deleted all experiments for that input.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)