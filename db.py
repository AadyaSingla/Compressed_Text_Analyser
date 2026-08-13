"""SQLite store for BPE experiments.

Rows are unique on (input_string, k, category): re-running the same text
with the same merge count and category reuses the stored row instead of
inserting a duplicate.
"""

import hashlib
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "experiments.db"

# CREATE TABLE IF NOT EXISTS never alters an existing table, so any change to
# the columns below needs experiments.db deleted and recreated — it won't be
# migrated in place. The naming pass of 2026-08-11 renamed most columns in
# both tables (original_chars -> size_chars, token_count -> tokens,
# learned_vocab -> vocabulary, the knee_*/at_knee columns -> the k_star
# family, pct_captured_at_knee -> utility_ratio) and dropped
# file_summary.learned_vocab_at_knee, so any database written before then has
# the old column names and will fail on insert. Rebuild it from the stored
# input_strings rather than trying to migrate.
SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('code', 'english')),
    cleaned INTEGER NOT NULL CHECK (cleaned IN (0, 1)),
    input_hash TEXT NOT NULL,
    input_string TEXT NOT NULL,
    k INTEGER NOT NULL,
    merges_applied INTEGER NOT NULL,
    size_chars INTEGER NOT NULL,
    tokens INTEGER NOT NULL,
    distinct_tokens INTEGER NOT NULL,
    vocabulary INTEGER NOT NULL,
    utility INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (input_string, k, category)
);
CREATE INDEX IF NOT EXISTS idx_experiments_hash ON experiments (input_hash, k);
CREATE TABLE IF NOT EXISTS file_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    input_hash TEXT NOT NULL,
    label TEXT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('code', 'english')),
    size_chars INTEGER NOT NULL,
    k_star INTEGER NOT NULL,
    utility_at_k_star INTEGER NOT NULL,
    tokens_at_k_star INTEGER NOT NULL,
    max_utility INTEGER NOT NULL,
    utility_ratio REAL NOT NULL,
    saturation_k INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (input_hash, category)
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def input_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_experiment(conn, text, k, category):
    return conn.execute(
        "SELECT * FROM experiments WHERE input_string = ? AND k = ? AND category = ?",
        (text, k, category),
    ).fetchone()


def save_experiment(conn, label, category, cleaned, text, stats):
    """Insert an experiment row, or return the existing one for
    (text, k, category). `cleaned` is stored as provenance (was this text
    produced by the Clean step) but isn't part of the uniqueness key —
    cleaning a text changes the text itself, so a cleaned and a raw
    version of the same source already get different `input_string`s and
    never collide."""
    existing = get_experiment(conn, text, stats["k"], category)
    if existing:
        return existing, False
    conn.execute(
        """INSERT INTO experiments
           (label, category, cleaned, input_hash, input_string, k, merges_applied,
            size_chars, tokens, distinct_tokens, vocabulary, utility)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            label,
            category,
            int(cleaned),
            input_hash(text),
            text,
            stats["k"],
            stats["merges_applied"],
            stats["size_chars"],
            stats["tokens"],
            stats["distinct_tokens"],
            stats["vocabulary"],
            stats["utility"],
        ),
    )
    conn.commit()
    return get_experiment(conn, text, stats["k"], category), True


def list_inputs(conn):
    """One summary row per distinct (input, category), newest first."""
    return conn.execute(
        """SELECT input_hash, category, cleaned, label, size_chars,
                  COUNT(*) AS runs, MAX(k) AS max_k, MAX(created_at) AS last_run
           FROM experiments
           GROUP BY input_hash, category
           ORDER BY last_run DESC"""
    ).fetchall()


def rows_for_input(conn, ihash):
    return conn.execute(
        "SELECT * FROM experiments WHERE input_hash = ? ORDER BY category, k",
        (ihash,),
    ).fetchall()


def delete_input(conn, ihash):
    """Delete everything stored for one input: its experiment rows and its
    file_summary row(s), so a deleted input also leaves the /analysis page."""
    conn.execute("DELETE FROM experiments WHERE input_hash = ?", (ihash,))
    conn.execute("DELETE FROM file_summary WHERE input_hash = ?", (ihash,))
    conn.commit()


def save_summary(conn, ihash, summary):
    """Insert or replace the file_summary row for (ihash, category), so
    re-running a file's analysis refreshes its cross-file summary."""
    conn.execute(
        """INSERT OR REPLACE INTO file_summary
           (input_hash, label, category, size_chars, k_star, utility_at_k_star,
            tokens_at_k_star, max_utility, utility_ratio, saturation_k)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ihash,
            summary["label"],
            summary["category"],
            summary["size_chars"],
            summary["k_star"],
            summary["utility_at_k_star"],
            summary["tokens_at_k_star"],
            summary["max_utility"],
            summary["utility_ratio"],
            summary["saturation_k"],
        ),
    )
    conn.commit()


def get_summary(conn, ihash, category):
    """The one file_summary row for (ihash, category), or None if the input
    has experiment rows but was never summarized. Per category rather than
    per hash because the table is unique on the pair, and one text analysed
    as both code and english has a row under each."""
    return conn.execute(
        "SELECT * FROM file_summary WHERE input_hash = ? AND category = ?",
        (ihash, category),
    ).fetchone()


def get_all_summaries(conn):
    """All file_summary rows, ordered by category then size_chars, for the
    cross-file analysis page."""
    return conn.execute(
        "SELECT * FROM file_summary ORDER BY category, size_chars"
    ).fetchall()