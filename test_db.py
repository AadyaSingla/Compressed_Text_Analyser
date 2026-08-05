"""Plain-assert tests for db.py's no-duplicates guarantees.

The analysis pages are only trustworthy if re-running the same file adds
nothing and deleting an input removes everything, so both are pinned here.
Each test runs against a throwaway database file, never experiments.db.

Run directly: python test_db.py
"""

import tempfile
from pathlib import Path

import bpe
import db

TEXT = "the cat sat on the mat the cat sat on the mat"
KS = [0, 5, 10]


def _fresh_db():
    """Point db at an empty temp file and return a connection to it."""
    tmp = Path(tempfile.mkdtemp()) / "test.db"
    db.DB_PATH = tmp
    return db.connect()


def _run_file(conn, text, category, label):
    """One full run of one file, mirroring what app.run() does: a k sweep
    plus one summary write. Returns how many experiment rows were new."""
    new_rows = 0
    for k in KS:
        if db.get_experiment(conn, text, k, category):
            continue
        stats = bpe.analyse(text, k)
        _, created = db.save_experiment(conn, label, category, 0, text, stats)
        new_rows += created
    db.save_summary(conn, db.input_hash(text), bpe.summarize(text, category, label))
    return new_rows


def _count(conn, table, ihash):
    return conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE input_hash = ?", (ihash,)
    ).fetchone()[0]


def test_rerunning_a_file_adds_nothing():
    """Three runs of the same file leave exactly one summary row and one
    experiment row per k — the second and third runs are no-ops."""
    conn = _fresh_db()
    ihash = db.input_hash(TEXT)

    assert _run_file(conn, TEXT, "english", "run-1") == len(KS)
    assert _run_file(conn, TEXT, "english", "run-2") == 0
    assert _run_file(conn, TEXT, "english", "run-3") == 0

    assert _count(conn, "experiments", ihash) == len(KS)
    assert _count(conn, "file_summary", ihash) == 1
    assert len(db.get_all_summaries(conn)) == 1
    conn.close()


def test_rerun_refreshes_the_summary_in_place():
    """The surviving summary row is the newest one, not the first — a
    re-run overwrites rather than being silently dropped."""
    conn = _fresh_db()
    _run_file(conn, TEXT, "english", "first-label")
    _run_file(conn, TEXT, "english", "second-label")

    summaries = db.get_all_summaries(conn)
    assert len(summaries) == 1
    assert summaries[0]["label"] == "second-label"

    expected = bpe.summarize(TEXT, "english", "second-label")
    for field, value in expected.items():
        assert summaries[0][field] == value, field
    conn.close()


def test_same_text_under_both_categories_stays_two_rows():
    """Category is part of an input's identity, so one text analysed as
    both code and english is two summaries — separate points on the
    analysis plots, not a duplicate."""
    conn = _fresh_db()
    _run_file(conn, TEXT, "english", "as-english")
    _run_file(conn, TEXT, "code", "as-code")

    summaries = db.get_all_summaries(conn)
    assert len(summaries) == 2
    assert {s["category"] for s in summaries} == {"code", "english"}
    conn.close()


def test_delete_input_clears_both_tables():
    """Deleting an input must remove its summary too, or it lingers on the
    analysis page after its experiments are gone."""
    conn = _fresh_db()
    ihash = db.input_hash(TEXT)
    _run_file(conn, TEXT, "english", "doomed")
    _run_file(conn, TEXT, "code", "doomed")

    db.delete_input(conn, ihash)

    assert _count(conn, "experiments", ihash) == 0
    assert _count(conn, "file_summary", ihash) == 0
    assert db.get_all_summaries(conn) == []
    conn.close()


if __name__ == "__main__":
    test_rerunning_a_file_adds_nothing()
    test_rerun_refreshes_the_summary_in_place()
    test_same_text_under_both_categories_stays_two_rows()
    test_delete_input_clears_both_tables()
    print("All tests passed.")
