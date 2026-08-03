"""JSON API for the BPE compressed-text analyser.

Mirrors the HTML routes in app.py but speaks JSON instead of rendering
templates. Documented for Swagger UI (see /apidocs, wired up in app.py).
"""

from flask import Blueprint, jsonify, request

import bpe
import db
from config import MAX_INPUT_CHARS, MAX_K, SAMPLES

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _parse_ks(payload):
    k_max = int(payload.get("k_max", payload.get("k", 100)))
    step = int(payload.get("k_step", 0))
    k_max = max(0, min(k_max, MAX_K))
    if step > 0:
        return list(range(0, k_max + 1, step)) or [k_max]
    return [k_max]


@api_bp.route("/inputs", methods=["GET"])
def list_inputs():
    """
    List all distinct inputs with stored experiments.
    ---
    tags:
      - inputs
    responses:
      200:
        description: One summary row per distinct input, newest first.
        schema:
          type: array
          items:
            type: object
            properties:
              input_hash: {type: string}
              label: {type: string}
              original_chars: {type: integer}
              runs: {type: integer}
              max_k: {type: integer}
              last_run: {type: string}
    """
    conn = db.connect()
    rows = db.list_inputs(conn)
    conn.close()
    return jsonify([dict(r) for r in rows])


@api_bp.route("/results/<ihash>", methods=["GET"])
def get_results(ihash):
    """
    Get all stored experiments for a given input hash.
    ---
    tags:
      - results
    parameters:
      - name: ihash
        in: path
        type: string
        required: true
        description: Hash identifying the input text (returned by POST /api/experiments).
    responses:
      200:
        description: Experiment rows for the input, ordered by k.
        schema:
          type: array
          items:
            type: object
      404:
        description: No experiments found for this input hash.
    """
    conn = db.connect()
    rows = db.rows_for_input(conn, ihash)
    conn.close()
    if not rows:
        return jsonify({"error": "not found"}), 404
    return jsonify([dict(r) for r in rows])


@api_bp.route("/experiments", methods=["POST"])
def run_experiments():
    """
    Run BPE analysis over a text for one or more values of k.
    ---
    tags:
      - experiments
    consumes:
      - application/json
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            text:
              type: string
              description: Raw text to analyse. Omit if `sample` is set.
            sample:
              type: string
              enum: [english, code]
              description: Use a bundled sample instead of `text`.
            label:
              type: string
              description: Optional label; defaults to the first 30 chars of the text.
            k_max:
              type: integer
              default: 100
              description: Maximum number of BPE merges to run.
            k_step:
              type: integer
              default: 0
              description: If > 0, run every k from 0 to k_max in steps of this size.
    responses:
      200:
        description: The resulting experiment rows (existing or newly created) plus the input hash.
        schema:
          type: object
          properties:
            input_hash: {type: string}
            new_rows: {type: integer}
            experiments:
              type: array
              items:
                type: object
      400:
        description: Missing/invalid text or k parameters.
    """
    payload = request.get_json(silent=True) or {}

    sample = payload.get("sample", "")
    text = payload.get("text", "")
    label = payload.get("label")

    if sample in SAMPLES:
        text = SAMPLES[sample].read_text(encoding="utf-8")
        label = label or sample
    if not text:
        return jsonify({"error": "provide `text` or a valid `sample`"}), 400
    if len(text) > MAX_INPUT_CHARS:
        return jsonify(
            {"error": f"input too large ({len(text)} chars, limit {MAX_INPUT_CHARS})"}
        ), 400
    label = label or text[:30].replace("\n", " ")

    try:
        ks = _parse_ks(payload)
    except (TypeError, ValueError):
        return jsonify({"error": "k_max and k_step must be whole numbers"}), 400

    conn = db.connect()
    new_rows = 0
    for k in ks:
        if db.get_experiment(conn, text, k):
            continue
        stats = bpe.analyse(text, k)
        _, created = db.save_experiment(conn, label, text, stats)
        new_rows += created
    ihash = db.input_hash(text)
    rows = db.rows_for_input(conn, ihash)
    conn.close()

    return jsonify(
        {
            "input_hash": ihash,
            "new_rows": new_rows,
            "experiments": [dict(r) for r in rows],
        }
    )


@api_bp.route("/inputs/<ihash>", methods=["DELETE"])
def delete_input(ihash):
    """
    Delete all stored experiments for a given input hash.
    ---
    tags:
      - inputs
    parameters:
      - name: ihash
        in: path
        type: string
        required: true
    responses:
      204:
        description: Deleted.
    """
    conn = db.connect()
    db.delete_input(conn, ihash)
    conn.close()
    return "", 204