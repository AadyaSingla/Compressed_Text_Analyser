"""SQLite store for BPE experiments.

Rows are unique on (input_string, k): re-running the same text with the
same merge count reuses the stored row instead of inserting a duplicate.
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "experiments.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    input_string TEXT NOT NULL,
    k INTEGER NOT NULL,
    merges_applied INTEGER NOT NULL,
    original_chars INTEGER NOT NULL,
    token_count INTEGER NOT NULL,
    vocab_size INTEGER NOT NULL,
    utility INTEGER NOT NULL,
    longest_token TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (input_string, k)
);
CREATE INDEX IF NOT EXISTS idx_experiments_hash ON experiments (input_hash, k);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def input_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_experiment(conn, text, k):
    return conn.execute(
        "SELECT * FROM experiments WHERE input_string = ? AND k = ?", (text, k)
    ).fetchone()


def save_experiment(conn, label, text, stats):
    """Insert an experiment row, or return the existing one for (text, k)."""
    existing = get_experiment(conn, text, stats["k"])
    if existing:
        return existing, False
    conn.execute(
        """INSERT INTO experiments
           (label, input_hash, input_string, k, merges_applied, original_chars,
            token_count, vocab_size, utility, longest_token)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            label,
            input_hash(text),
            text,
            stats["k"],
            stats["merges_applied"],
            stats["original_chars"],
            stats["token_count"],
            stats["vocab_size"],
            stats["utility"],
            stats["longest_token"],
        ),
    )
    conn.commit()
    return get_experiment(conn, text, stats["k"]), True


def list_inputs(conn):
    """One summary row per distinct input, newest first."""
    return conn.execute(
        """SELECT input_hash, label, original_chars,
                  COUNT(*) AS runs, MAX(k) AS max_k, MAX(created_at) AS last_run
           FROM experiments
           GROUP BY input_hash
           ORDER BY last_run DESC"""
    ).fetchall()


def rows_for_input(conn, ihash):
    return conn.execute(
        "SELECT * FROM experiments WHERE input_hash = ? ORDER BY k", (ihash,)
    ).fetchall()


def delete_input(conn, ihash):
    conn.execute("DELETE FROM experiments WHERE input_hash = ?", (ihash,))
    conn.commit()