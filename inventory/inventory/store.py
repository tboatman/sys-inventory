"""SQLite persistence for resolved lineage chains and the other inventory
dimensions (subsystems, started tasks, system identity)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import (
    ActiveJob,
    CatalogDataset,
    LineageStep,
    Product,
    StartedTask,
    Subsystem,
    SystemInfo,
    UssProcess,
    VsamCluster,
)

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

CREATE TABLE IF NOT EXISTS products (
    id             TEXT NOT NULL,
    name           TEXT,
    version        TEXT,
    release        TEXT,
    mod            TEXT,
    featurename    TEXT,
    state          TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_id ON products(id);

CREATE TABLE IF NOT EXISTS active_jobs (
    job_id    TEXT NOT NULL,
    name      TEXT NOT NULL,
    job_type  TEXT,
    asid      TEXT
);
CREATE INDEX IF NOT EXISTS idx_active_jobs_name ON active_jobs(name);

CREATE TABLE IF NOT EXISTS uss_processes (
    command TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_datasets (
    dsn      TEXT NOT NULL,
    volser   TEXT,
    dsorg    TEXT,
    recfm    TEXT,
    lrecl    INTEGER,
    blksize  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_catalog_datasets_dsn ON catalog_datasets(dsn);

CREATE TABLE IF NOT EXISTS vsam_clusters (
    name             TEXT NOT NULL,
    cluster_type     TEXT,
    volser           TEXT,
    key_length       INTEGER,
    key_offset       INTEGER,
    data_component   TEXT,
    index_component  TEXT
);
CREATE INDEX IF NOT EXISTS idx_vsam_clusters_name ON vsam_clusters(name);
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


def save_products(conn: sqlite3.Connection, products: list[Product]) -> None:
    conn.execute("DELETE FROM products")
    rows = [
        (p.id, p.name, p.version, p.release, p.mod, p.featurename, p.state, p.source_member)
        for p in products
    ]
    conn.executemany(
        "INSERT INTO products (id, name, version, release, mod, featurename, state, source_member) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_products(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM products ORDER BY id")
    return cur.fetchall()


def save_active_jobs(conn: sqlite3.Connection, active_jobs: list[ActiveJob]) -> None:
    conn.execute("DELETE FROM active_jobs")
    rows = [(j.job_id, j.name, j.job_type, j.asid) for j in active_jobs]
    conn.executemany(
        "INSERT INTO active_jobs (job_id, name, job_type, asid) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_active_jobs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM active_jobs ORDER BY name")
    return cur.fetchall()


def save_processes(conn: sqlite3.Connection, processes: list[UssProcess]) -> None:
    conn.execute("DELETE FROM uss_processes")
    rows = [(p.command,) for p in processes]
    conn.executemany("INSERT INTO uss_processes (command) VALUES (?)", rows)
    conn.commit()


def all_processes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM uss_processes ORDER BY command")
    return cur.fetchall()


def save_catalog_datasets(conn: sqlite3.Connection, catalog_datasets: list[CatalogDataset]) -> None:
    conn.execute("DELETE FROM catalog_datasets")
    rows = [(d.dsn, d.volser, d.dsorg, d.recfm, d.lrecl, d.blksize) for d in catalog_datasets]
    conn.executemany(
        "INSERT INTO catalog_datasets (dsn, volser, dsorg, recfm, lrecl, blksize) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_catalog_datasets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM catalog_datasets ORDER BY dsn")
    return cur.fetchall()


def save_vsam_clusters(conn: sqlite3.Connection, vsam_clusters: list[VsamCluster]) -> None:
    conn.execute("DELETE FROM vsam_clusters")
    rows = [
        (c.name, c.cluster_type, c.volser, c.key_length, c.key_offset,
         c.data_component, c.index_component)
        for c in vsam_clusters
    ]
    conn.executemany(
        "INSERT INTO vsam_clusters (name, cluster_type, volser, key_length, key_offset, "
        "data_component, index_component) VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_vsam_clusters(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM vsam_clusters ORDER BY name")
    return cur.fetchall()
