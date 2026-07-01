"""SQLite persistence for resolved lineage chains and the other inventory
dimensions (subsystems, started tasks, system identity)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import LineageStep, StartedTask, Subsystem, SystemInfo

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage (
    member         TEXT NOT NULL,
    step_name      TEXT NOT NULL,
    pgm            TEXT NOT NULL,
    dataset        TEXT,
    zone           TEXT,
    fmid           TEXT,
    resolution     TEXT NOT NULL,
    apf_authorized INTEGER
);
CREATE INDEX IF NOT EXISTS idx_lineage_member ON lineage(member);
CREATE INDEX IF NOT EXISTS idx_lineage_fmid ON lineage(fmid);

CREATE TABLE IF NOT EXISTS subsystems (
    name           TEXT NOT NULL,
    initrtn        TEXT,
    initparm       TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_subsystems_name ON subsystems(name);

CREATE TABLE IF NOT EXISTS started_tasks (
    task_name      TEXT NOT NULL,
    identifier     TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_started_tasks_name ON started_tasks(task_name);

CREATE TABLE IF NOT EXISTS system_info (
    sysname          TEXT,
    sysclone         TEXT,
    sysplex          TEXT,
    ipl_volume       TEXT,
    ipl_parm_member  TEXT,
    release          TEXT,
    archlvl          TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_lineage(conn: sqlite3.Connection, lineage_by_member: dict[str, list[LineageStep]]) -> None:
    conn.execute("DELETE FROM lineage")
    rows = [
        (step.member, step.step_name, step.pgm, step.dataset, step.zone, step.fmid,
         step.resolution, step.apf_authorized)
        for steps in lineage_by_member.values()
        for step in steps
    ]
    conn.executemany(
        "INSERT INTO lineage (member, step_name, pgm, dataset, zone, fmid, resolution, apf_authorized) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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


def save_subsystems(conn: sqlite3.Connection, subsystems: list[Subsystem]) -> None:
    conn.execute("DELETE FROM subsystems")
    rows = [(s.name, s.initrtn, s.initparm, s.source_member) for s in subsystems]
    conn.executemany(
        "INSERT INTO subsystems (name, initrtn, initparm, source_member) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_subsystems(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM subsystems ORDER BY name")
    return cur.fetchall()


def save_started_tasks(conn: sqlite3.Connection, tasks: list[StartedTask]) -> None:
    conn.execute("DELETE FROM started_tasks")
    rows = [(t.task_name, t.identifier, t.source_member) for t in tasks]
    conn.executemany(
        "INSERT INTO started_tasks (task_name, identifier, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_started_tasks(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM started_tasks ORDER BY task_name")
    return cur.fetchall()


def save_system_info(conn: sqlite3.Connection, info: SystemInfo | None) -> None:
    conn.execute("DELETE FROM system_info")
    if info is not None:
        conn.execute(
            "INSERT INTO system_info (sysname, sysclone, sysplex, ipl_volume, ipl_parm_member, "
            "release, archlvl) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (info.sysname, info.sysclone, info.sysplex, info.ipl_volume, info.ipl_parm_member,
             info.release, info.archlvl),
        )
    conn.commit()


def get_system_info(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM system_info LIMIT 1")
    return cur.fetchone()
