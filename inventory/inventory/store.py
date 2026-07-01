"""SQLite persistence for resolved lineage chains."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import LineageStep

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage (
    member     TEXT NOT NULL,
    step_name  TEXT NOT NULL,
    pgm        TEXT NOT NULL,
    dataset    TEXT,
    zone       TEXT,
    fmid       TEXT,
    resolution TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_lineage_member ON lineage(member);
CREATE INDEX IF NOT EXISTS idx_lineage_fmid ON lineage(fmid);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_lineage(conn: sqlite3.Connection, lineage_by_member: dict[str, list[LineageStep]]) -> None:
    conn.execute("DELETE FROM lineage")
    rows = [
        (step.member, step.step_name, step.pgm, step.dataset, step.zone, step.fmid, step.resolution)
        for steps in lineage_by_member.values()
        for step in steps
    ]
    conn.executemany(
        "INSERT INTO lineage (member, step_name, pgm, dataset, zone, fmid, resolution) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def lineage_for_member(conn: sqlite3.Connection, member: str) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM lineage WHERE member = ? ORDER BY rowid", (member,)
    )
    return cur.fetchall()


def all_lineage(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM lineage ORDER BY member, rowid")
    return cur.fetchall()
