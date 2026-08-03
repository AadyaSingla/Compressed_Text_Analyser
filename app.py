"""Flask app for the compressed-text analyser (BPE thesis experiments)."""

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
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


@app.route("/delete/<ihash>", methods=["POST"])
def delete(ihash):
    conn = db.connect()
    db.delete_input(conn, ihash)
    conn.close()
    flash("Deleted all experiments for that input.")
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)