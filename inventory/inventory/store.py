"""SQLite persistence for resolved lineage chains and the other inventory
dimensions (subsystems, started tasks, system identity)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .models import (
    ActiveJob,
    AutorStatement,
    BpxprmStatement,
    CatalogDataset,
    CicsCsdDefinition,
    CicsDfhrplEntry,
    CicsSitOverride,
    ClockStatement,
    ConsolStatement,
    CoupleStatement,
    DatasetAccess,
    DatasetProfile,
    Db2Package,
    Db2Plan,
    DevsupStatement,
    Fmid,
    GeneralResourceAccess,
    GeneralResourceProfile,
    GrsrnlStatement,
    IeasysStatement,
    IgdsmsStatement,
    IosStatement,
    Jes2InitStatement,
    LineageStep,
    OptStatement,
    ParmlibDataset,
    Product,
    RacfGroup,
    RacfGroupConnection,
    RacfSnapshot,
    RacfUser,
    SchedStatement,
    SmfStatement,
    SmsStorageGroup,
    StartedTask,
    Subsystem,
    SystemInfo,
    TcpipHomeAddress,
    TcpipProfileStatement,
    UssMount,
    UssProcess,
    VsamCluster,
    VtamMajorNode,
    VtamStartOption,
    VtamTopologySummary,
    WlmPolicy,
    WlmZosmfEntry,
    Zone,
    ZoneIndexEntry,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS lineage (
    member         TEXT NOT NULL,
    step_name      TEXT NOT NULL,
    pgm            TEXT NOT NULL,
    dataset        TEXT,
    zone           TEXT,
    fmid           TEXT,
    csi            TEXT,
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

CREATE TABLE IF NOT EXISTS parmlib_datasets (
    entry   TEXT NOT NULL,
    flags   TEXT,
    volume  TEXT,
    dsn     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ieasys_statements (
    keyword        TEXT NOT NULL,
    value          TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ieasys_statements_keyword ON ieasys_statements(keyword);

CREATE TABLE IF NOT EXISTS bpxprm_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bpxprm_statements_stmt ON bpxprm_statements(stmt);

CREATE TABLE IF NOT EXISTS devsup_statements (
    keyword        TEXT NOT NULL,
    value          TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_devsup_statements_keyword ON devsup_statements(keyword);

CREATE TABLE IF NOT EXISTS opt_statements (
    keyword        TEXT NOT NULL,
    value          TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_opt_statements_keyword ON opt_statements(keyword);

CREATE TABLE IF NOT EXISTS clock_statements (
    keyword        TEXT NOT NULL,
    value          TEXT,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clock_statements_keyword ON clock_statements(keyword);

CREATE TABLE IF NOT EXISTS autor_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_autor_statements_stmt ON autor_statements(stmt);

CREATE TABLE IF NOT EXISTS sched_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sched_statements_stmt ON sched_statements(stmt);

CREATE TABLE IF NOT EXISTS couple_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_couple_statements_stmt ON couple_statements(stmt);

CREATE TABLE IF NOT EXISTS grsrnl_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grsrnl_statements_stmt ON grsrnl_statements(stmt);

CREATE TABLE IF NOT EXISTS smf_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_smf_statements_stmt ON smf_statements(stmt);

CREATE TABLE IF NOT EXISTS ios_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ios_statements_stmt ON ios_statements(stmt);

CREATE TABLE IF NOT EXISTS consol_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_consol_statements_stmt ON consol_statements(stmt);

-- Deliberately named igdsms_statements, not sms_* -- this project
-- already has an unrelated sms_storage_groups table for the *live*
-- `D SMS,STORGRP` console command (see SmsStorageGroup); this is the
-- active IGDSMSxx PARMLIB member instead (doc/TODO.md "9.2").
CREATE TABLE IF NOT EXISTS igdsms_statements (
    stmt           TEXT NOT NULL,
    operands       TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_igdsms_statements_stmt ON igdsms_statements(stmt);

CREATE TABLE IF NOT EXISTS active_jobs (
    job_id             TEXT NOT NULL,
    name               TEXT NOT NULL,
    job_type           TEXT,
    asid               TEXT,
    owner              TEXT,
    status             TEXT,
    completion_code    TEXT,
    job_class          TEXT,
    svc_class          TEXT,
    priority           TEXT,
    creation_date      TEXT,
    creation_time      TEXT,
    queue_position     TEXT,
    execution_time     TEXT,
    execution_seconds  TEXT,
    system             TEXT,
    subsystem          TEXT,
    onode              TEXT,
    xnode              TEXT,
    membname           TEXT
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

CREATE TABLE IF NOT EXISTS racf_users (
    userid         TEXT NOT NULL,
    name           TEXT,
    owner          TEXT,
    default_group  TEXT,
    special        INTEGER,
    operations     INTEGER,
    auditor        INTEGER,
    revoked        INTEGER,
    restricted     INTEGER
);
CREATE INDEX IF NOT EXISTS idx_racf_users_userid ON racf_users(userid);

CREATE TABLE IF NOT EXISTS racf_groups (
    name              TEXT NOT NULL,
    superior_group    TEXT,
    owner             TEXT,
    universal_access  TEXT,
    description       TEXT
);
CREATE INDEX IF NOT EXISTS idx_racf_groups_name ON racf_groups(name);

CREATE TABLE IF NOT EXISTS racf_group_connections (
    userid                   TEXT NOT NULL,
    grp                      TEXT NOT NULL,
    group_special            INTEGER,
    group_operations         INTEGER,
    group_auditor            INTEGER,
    group_universal_access   TEXT,
    revoked_in_group         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_racf_group_connections_userid ON racf_group_connections(userid);

CREATE TABLE IF NOT EXISTS racf_dataset_profiles (
    profile           TEXT NOT NULL,
    volume            TEXT,
    generic           INTEGER,
    owner             TEXT,
    universal_access  TEXT,
    audit_level       TEXT
);
CREATE INDEX IF NOT EXISTS idx_racf_dataset_profiles_profile ON racf_dataset_profiles(profile);

CREATE TABLE IF NOT EXISTS racf_dataset_access (
    profile  TEXT NOT NULL,
    auth_id  TEXT NOT NULL,
    access   TEXT
);
CREATE INDEX IF NOT EXISTS idx_racf_dataset_access_profile ON racf_dataset_access(profile);

CREATE TABLE IF NOT EXISTS racf_general_resource_profiles (
    profile           TEXT NOT NULL,
    class_name        TEXT NOT NULL,
    owner             TEXT,
    universal_access  TEXT,
    audit_level       TEXT
);
CREATE INDEX IF NOT EXISTS idx_racf_gr_profiles_class_profile ON racf_general_resource_profiles(class_name, profile);

CREATE TABLE IF NOT EXISTS racf_general_resource_access (
    profile     TEXT NOT NULL,
    class_name  TEXT NOT NULL,
    auth_id     TEXT NOT NULL,
    access      TEXT
);
CREATE INDEX IF NOT EXISTS idx_racf_gr_access_class_profile ON racf_general_resource_access(class_name, profile);

CREATE TABLE IF NOT EXISTS uss_mounts (
    path          TEXT NOT NULL,
    name          TEXT,
    fs_type       TEXT,
    device        TEXT,
    status        TEXT,
    mode          TEXT,
    mounted_date  TEXT
);
CREATE INDEX IF NOT EXISTS idx_uss_mounts_path ON uss_mounts(path);

CREATE TABLE IF NOT EXISTS jes2_init_statements (
    stmt           TEXT NOT NULL,
    subscript      TEXT,
    params_json    TEXT NOT NULL,
    source_member  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jes2_init_statements_stmt ON jes2_init_statements(stmt);

CREATE TABLE IF NOT EXISTS vtam_major_nodes (
    name    TEXT NOT NULL,
    status  TEXT
);
CREATE INDEX IF NOT EXISTS idx_vtam_major_nodes_name ON vtam_major_nodes(name);

CREATE TABLE IF NOT EXISTS vtam_start_options (
    keyword  TEXT NOT NULL,
    value    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_vtam_start_options_keyword ON vtam_start_options(keyword);

CREATE TABLE IF NOT EXISTS vtam_topology_summary (
    last_checkpoint             TEXT,
    adj                         INTEGER,
    nn                          INTEGER,
    en                          INTEGER,
    served_en                   INTEGER,
    cdservr                     INTEGER,
    icn                         INTEGER,
    bn                          INTEGER,
    initdb_checkpoint_dataset   TEXT,
    last_garbage_collection     TEXT
);

CREATE TABLE IF NOT EXISTS tcpip_home_addresses (
    link_name   TEXT NOT NULL,
    ip_address  TEXT NOT NULL,
    is_primary  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tcpip_home_addresses_link ON tcpip_home_addresses(link_name);

CREATE TABLE IF NOT EXISTS tcpip_profile_statements (
    stmt        TEXT NOT NULL,
    operands    TEXT NOT NULL,
    source_dsn  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tcpip_profile_statements_stmt ON tcpip_profile_statements(stmt);

CREATE TABLE IF NOT EXISTS sms_storage_groups (
    name          TEXT NOT NULL,
    status        TEXT,
    group_type    TEXT,
    volumes_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sms_storage_groups_name ON sms_storage_groups(name);

CREATE TABLE IF NOT EXISTS wlm_policy (
    policy_name  TEXT,
    mode         TEXT
);

CREATE TABLE IF NOT EXISTS db2_packages (
    name            TEXT NOT NULL,
    creator         TEXT,
    bind_timestamp  TEXT,
    ssid            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_db2_packages_name ON db2_packages(name);

CREATE TABLE IF NOT EXISTS db2_plans (
    name            TEXT NOT NULL,
    creator         TEXT,
    bind_timestamp  TEXT,
    ssid            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_db2_plans_name ON db2_plans(name);

CREATE TABLE IF NOT EXISTS wlm_zosmf_entries (
    name      TEXT NOT NULL,
    raw_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wlm_zosmf_entries_name ON wlm_zosmf_entries(name);

CREATE TABLE IF NOT EXISTS cics_dfhrpl_entries (
    dsn             TEXT NOT NULL,
    proc            TEXT NOT NULL,
    zone            TEXT,
    apf_authorized  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_cics_dfhrpl_entries_dsn ON cics_dfhrpl_entries(dsn);

CREATE TABLE IF NOT EXISTS cics_sit_overrides (
    keyword  TEXT NOT NULL,
    value    TEXT NOT NULL,
    proc     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cics_sit_overrides_proc ON cics_sit_overrides(proc);

CREATE TABLE IF NOT EXISTS cics_csd_definitions (
    def_type  TEXT NOT NULL,
    name      TEXT NOT NULL,
    grp       TEXT NOT NULL,
    csd_dsn   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cics_csd_definitions_name ON cics_csd_definitions(name);

CREATE TABLE IF NOT EXISTS zone_index (
    zone_name   TEXT NOT NULL,
    zone_type   TEXT NOT NULL,
    csi         TEXT NOT NULL,
    source_csi  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_zone_index_zone_name ON zone_index(zone_name);

CREATE TABLE IF NOT EXISTS zones (
    name         TEXT NOT NULL,
    csi          TEXT,
    dddefs_json  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_zones_name ON zones(name);

CREATE TABLE IF NOT EXISTS fmids (
    fmid    TEXT NOT NULL,
    zone    TEXT NOT NULL,
    status  TEXT
);
CREATE INDEX IF NOT EXISTS idx_fmids_fmid ON fmids(fmid);
CREATE INDEX IF NOT EXISTS idx_fmids_zone ON fmids(zone);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    return conn


def save_lineage(conn: sqlite3.Connection, lineage_by_member: dict[str, list[LineageStep]]) -> None:
    conn.execute("DELETE FROM lineage")
    rows = [
        (step.member, step.step_name, step.pgm, step.dataset, step.zone, step.fmid,
         step.csi, step.resolution, step.apf_authorized)
        for steps in lineage_by_member.values()
        for step in steps
    ]
    conn.executemany(
        "INSERT INTO lineage (member, step_name, pgm, dataset, zone, fmid, csi, resolution, apf_authorized) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


def save_parmlib_datasets(conn: sqlite3.Connection, datasets: list[ParmlibDataset]) -> None:
    conn.execute("DELETE FROM parmlib_datasets")
    rows = [(d.entry, d.flags, d.volume, d.dsn) for d in datasets]
    conn.executemany(
        "INSERT INTO parmlib_datasets (entry, flags, volume, dsn) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_parmlib_datasets(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM parmlib_datasets ORDER BY CAST(entry AS INTEGER)")
    return cur.fetchall()


def save_ieasys_statements(conn: sqlite3.Connection, statements: list[IeasysStatement]) -> None:
    conn.execute("DELETE FROM ieasys_statements")
    rows = [(s.keyword, s.value, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO ieasys_statements (keyword, value, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_ieasys_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM ieasys_statements ORDER BY keyword")
    return cur.fetchall()


def save_bpxprm_statements(conn: sqlite3.Connection, statements: list[BpxprmStatement]) -> None:
    conn.execute("DELETE FROM bpxprm_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO bpxprm_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_bpxprm_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM bpxprm_statements ORDER BY stmt")
    return cur.fetchall()


def save_devsup_statements(conn: sqlite3.Connection, statements: list[DevsupStatement]) -> None:
    conn.execute("DELETE FROM devsup_statements")
    rows = [(s.keyword, s.value, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO devsup_statements (keyword, value, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_devsup_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM devsup_statements ORDER BY keyword")
    return cur.fetchall()


def save_opt_statements(conn: sqlite3.Connection, statements: list[OptStatement]) -> None:
    conn.execute("DELETE FROM opt_statements")
    rows = [(s.keyword, s.value, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO opt_statements (keyword, value, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_opt_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM opt_statements ORDER BY keyword")
    return cur.fetchall()


def save_clock_statements(conn: sqlite3.Connection, statements: list[ClockStatement]) -> None:
    conn.execute("DELETE FROM clock_statements")
    rows = [(s.keyword, s.value, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO clock_statements (keyword, value, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_clock_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM clock_statements ORDER BY keyword")
    return cur.fetchall()


def save_autor_statements(conn: sqlite3.Connection, statements: list[AutorStatement]) -> None:
    conn.execute("DELETE FROM autor_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO autor_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_autor_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM autor_statements ORDER BY stmt")
    return cur.fetchall()


def save_sched_statements(conn: sqlite3.Connection, statements: list[SchedStatement]) -> None:
    conn.execute("DELETE FROM sched_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO sched_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_sched_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM sched_statements ORDER BY stmt")
    return cur.fetchall()


def save_couple_statements(conn: sqlite3.Connection, statements: list[CoupleStatement]) -> None:
    conn.execute("DELETE FROM couple_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO couple_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_couple_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM couple_statements ORDER BY stmt")
    return cur.fetchall()


def save_grsrnl_statements(conn: sqlite3.Connection, statements: list[GrsrnlStatement]) -> None:
    conn.execute("DELETE FROM grsrnl_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO grsrnl_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_grsrnl_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM grsrnl_statements ORDER BY stmt")
    return cur.fetchall()


def save_smf_statements(conn: sqlite3.Connection, statements: list[SmfStatement]) -> None:
    conn.execute("DELETE FROM smf_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO smf_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_smf_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM smf_statements ORDER BY stmt")
    return cur.fetchall()


def save_ios_statements(conn: sqlite3.Connection, statements: list[IosStatement]) -> None:
    conn.execute("DELETE FROM ios_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO ios_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_ios_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM ios_statements ORDER BY stmt")
    return cur.fetchall()


def save_consol_statements(conn: sqlite3.Connection, statements: list[ConsolStatement]) -> None:
    conn.execute("DELETE FROM consol_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO consol_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_consol_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM consol_statements ORDER BY stmt")
    return cur.fetchall()


def save_igdsms_statements(conn: sqlite3.Connection, statements: list[IgdsmsStatement]) -> None:
    conn.execute("DELETE FROM igdsms_statements")
    rows = [(s.stmt, s.operands, s.source_member) for s in statements]
    conn.executemany(
        "INSERT INTO igdsms_statements (stmt, operands, source_member) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_igdsms_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM igdsms_statements ORDER BY stmt")
    return cur.fetchall()


def save_active_jobs(conn: sqlite3.Connection, active_jobs: list[ActiveJob]) -> None:
    conn.execute("DELETE FROM active_jobs")
    rows = [
        (
            j.job_id, j.name, j.job_type, j.asid, j.owner, j.status,
            j.completion_code, j.job_class, j.svc_class, j.priority,
            j.creation_date, j.creation_time, j.queue_position,
            j.execution_time, j.execution_seconds, j.system, j.subsystem,
            j.onode, j.xnode, j.membname,
        )
        for j in active_jobs
    ]
    conn.executemany(
        """
        INSERT INTO active_jobs (
            job_id, name, job_type, asid, owner, status,
            completion_code, job_class, svc_class, priority,
            creation_date, creation_time, queue_position,
            execution_time, execution_seconds, system, subsystem,
            onode, xnode, membname
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
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


def save_racf_snapshot(conn: sqlite3.Connection, snapshot: RacfSnapshot) -> None:
    """Save every RacfSnapshot table together as one atomic, non-additive
    replace -- IRRDBU00 always represents the RACF database's full current
    state, not an incremental slice, so re-ingesting a new racf.txt
    replaces the previous snapshot rather than merging into it."""
    conn.execute("DELETE FROM racf_users")
    conn.executemany(
        "INSERT INTO racf_users (userid, name, owner, default_group, special, operations, "
        "auditor, revoked, restricted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(u.userid, u.name, u.owner, u.default_group, u.special, u.operations,
          u.auditor, u.revoked, u.restricted) for u in snapshot.users],
    )

    conn.execute("DELETE FROM racf_groups")
    conn.executemany(
        "INSERT INTO racf_groups (name, superior_group, owner, universal_access, description) "
        "VALUES (?, ?, ?, ?, ?)",
        [(g.name, g.superior_group, g.owner, g.universal_access, g.description)
         for g in snapshot.groups],
    )

    conn.execute("DELETE FROM racf_group_connections")
    conn.executemany(
        "INSERT INTO racf_group_connections (userid, grp, group_special, group_operations, "
        "group_auditor, group_universal_access, revoked_in_group) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(c.userid, c.group, c.group_special, c.group_operations, c.group_auditor,
          c.group_universal_access, c.revoked_in_group) for c in snapshot.group_connections],
    )

    conn.execute("DELETE FROM racf_dataset_profiles")
    conn.executemany(
        "INSERT INTO racf_dataset_profiles (profile, volume, generic, owner, universal_access, "
        "audit_level) VALUES (?, ?, ?, ?, ?, ?)",
        [(p.profile, p.volume, p.generic, p.owner, p.universal_access, p.audit_level)
         for p in snapshot.dataset_profiles],
    )

    conn.execute("DELETE FROM racf_dataset_access")
    conn.executemany(
        "INSERT INTO racf_dataset_access (profile, auth_id, access) VALUES (?, ?, ?)",
        [(a.profile, a.auth_id, a.access) for a in snapshot.dataset_access],
    )

    conn.execute("DELETE FROM racf_general_resource_profiles")
    conn.executemany(
        "INSERT INTO racf_general_resource_profiles (profile, class_name, owner, "
        "universal_access, audit_level) VALUES (?, ?, ?, ?, ?)",
        [(p.profile, p.class_name, p.owner, p.universal_access, p.audit_level)
         for p in snapshot.general_resource_profiles],
    )

    conn.execute("DELETE FROM racf_general_resource_access")
    conn.executemany(
        "INSERT INTO racf_general_resource_access (profile, class_name, auth_id, access) "
        "VALUES (?, ?, ?, ?)",
        [(a.profile, a.class_name, a.auth_id, a.access) for a in snapshot.general_resource_access],
    )

    conn.commit()


def all_racf_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_users ORDER BY userid")
    return cur.fetchall()


def all_racf_groups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_groups ORDER BY name")
    return cur.fetchall()


def all_racf_group_connections(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_group_connections ORDER BY userid, grp")
    return cur.fetchall()


def all_racf_dataset_profiles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_dataset_profiles ORDER BY profile")
    return cur.fetchall()


def all_racf_dataset_access(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_dataset_access ORDER BY profile, auth_id")
    return cur.fetchall()


def all_racf_general_resource_profiles(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_general_resource_profiles ORDER BY class_name, profile")
    return cur.fetchall()


def all_racf_general_resource_access(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM racf_general_resource_access ORDER BY class_name, profile, auth_id")
    return cur.fetchall()


def save_uss_mounts(conn: sqlite3.Connection, mounts: list[UssMount]) -> None:
    conn.execute("DELETE FROM uss_mounts")
    rows = [(m.path, m.name, m.fs_type, m.device, m.status, m.mode, m.mounted_date) for m in mounts]
    conn.executemany(
        "INSERT INTO uss_mounts (path, name, fs_type, device, status, mode, mounted_date) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_uss_mounts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM uss_mounts ORDER BY path")
    return cur.fetchall()


def save_jes2_init_statements(conn: sqlite3.Connection, statements: list[Jes2InitStatement]) -> None:
    conn.execute("DELETE FROM jes2_init_statements")
    rows = [
        (s.stmt, s.subscript, json.dumps(s.params), s.source_member)
        for s in statements
    ]
    conn.executemany(
        "INSERT INTO jes2_init_statements (stmt, subscript, params_json, source_member) "
        "VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_jes2_init_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM jes2_init_statements ORDER BY stmt, subscript")
    return cur.fetchall()


def save_vtam_major_nodes(conn: sqlite3.Connection, nodes: list[VtamMajorNode]) -> None:
    conn.execute("DELETE FROM vtam_major_nodes")
    rows = [(n.name, n.status) for n in nodes]
    conn.executemany("INSERT INTO vtam_major_nodes (name, status) VALUES (?, ?)", rows)
    conn.commit()


def all_vtam_major_nodes(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM vtam_major_nodes ORDER BY name")
    return cur.fetchall()


def save_vtam_start_options(conn: sqlite3.Connection, options: list[VtamStartOption]) -> None:
    conn.execute("DELETE FROM vtam_start_options")
    rows = [(o.keyword, o.value) for o in options]
    conn.executemany("INSERT INTO vtam_start_options (keyword, value) VALUES (?, ?)", rows)
    conn.commit()


def all_vtam_start_options(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM vtam_start_options ORDER BY keyword")
    return cur.fetchall()


def save_vtam_topology_summary(conn: sqlite3.Connection, summary: VtamTopologySummary | None) -> None:
    conn.execute("DELETE FROM vtam_topology_summary")
    if summary is not None:
        conn.execute(
            "INSERT INTO vtam_topology_summary (last_checkpoint, adj, nn, en, served_en, "
            "cdservr, icn, bn, initdb_checkpoint_dataset, last_garbage_collection) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (summary.last_checkpoint, summary.adj, summary.nn, summary.en, summary.served_en,
             summary.cdservr, summary.icn, summary.bn, summary.initdb_checkpoint_dataset,
             summary.last_garbage_collection),
        )
    conn.commit()


def get_vtam_topology_summary(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM vtam_topology_summary LIMIT 1")
    return cur.fetchone()


def save_tcpip_home_addresses(conn: sqlite3.Connection, addresses: list[TcpipHomeAddress]) -> None:
    conn.execute("DELETE FROM tcpip_home_addresses")
    rows = [(a.link_name, a.ip_address, int(a.is_primary)) for a in addresses]
    conn.executemany(
        "INSERT INTO tcpip_home_addresses (link_name, ip_address, is_primary) VALUES (?, ?, ?)", rows
    )
    conn.commit()


def all_tcpip_home_addresses(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM tcpip_home_addresses ORDER BY link_name")
    return cur.fetchall()


def save_tcpip_profile_statements(conn: sqlite3.Connection, statements: list[TcpipProfileStatement]) -> None:
    conn.execute("DELETE FROM tcpip_profile_statements")
    rows = [(s.stmt, s.operands, s.source_dsn) for s in statements]
    conn.executemany(
        "INSERT INTO tcpip_profile_statements (stmt, operands, source_dsn) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_tcpip_profile_statements(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM tcpip_profile_statements ORDER BY stmt")
    return cur.fetchall()


def save_sms_storage_groups(conn: sqlite3.Connection, groups: list[SmsStorageGroup]) -> None:
    conn.execute("DELETE FROM sms_storage_groups")
    rows = [(g.name, g.status, g.group_type, json.dumps(g.volumes)) for g in groups]
    conn.executemany(
        "INSERT INTO sms_storage_groups (name, status, group_type, volumes_json) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_sms_storage_groups(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM sms_storage_groups ORDER BY name")
    return cur.fetchall()


def save_wlm_policy(conn: sqlite3.Connection, policy: WlmPolicy | None) -> None:
    conn.execute("DELETE FROM wlm_policy")
    if policy is not None:
        conn.execute(
            "INSERT INTO wlm_policy (policy_name, mode) VALUES (?, ?)",
            (policy.policy_name, policy.mode),
        )
    conn.commit()


def get_wlm_policy(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM wlm_policy LIMIT 1")
    return cur.fetchone()


def save_db2_packages(conn: sqlite3.Connection, packages: list[Db2Package]) -> None:
    conn.execute("DELETE FROM db2_packages")
    rows = [(p.name, p.creator, p.bind_timestamp, p.ssid) for p in packages]
    conn.executemany(
        "INSERT INTO db2_packages (name, creator, bind_timestamp, ssid) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_db2_packages(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM db2_packages ORDER BY name")
    return cur.fetchall()


def save_db2_plans(conn: sqlite3.Connection, plans: list[Db2Plan]) -> None:
    conn.execute("DELETE FROM db2_plans")
    rows = [(p.name, p.creator, p.bind_timestamp, p.ssid) for p in plans]
    conn.executemany(
        "INSERT INTO db2_plans (name, creator, bind_timestamp, ssid) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_db2_plans(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM db2_plans ORDER BY name")
    return cur.fetchall()


def save_wlm_zosmf_entries(conn: sqlite3.Connection, entries: list[WlmZosmfEntry]) -> None:
    conn.execute("DELETE FROM wlm_zosmf_entries")
    rows = [(e.name, json.dumps(e.raw)) for e in entries]
    conn.executemany(
        "INSERT INTO wlm_zosmf_entries (name, raw_json) VALUES (?, ?)",
        rows,
    )
    conn.commit()


def all_wlm_zosmf_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM wlm_zosmf_entries ORDER BY name")
    return cur.fetchall()


def save_cics_dfhrpl_entries(conn: sqlite3.Connection, entries: list[CicsDfhrplEntry]) -> None:
    conn.execute("DELETE FROM cics_dfhrpl_entries")
    rows = [(e.dsn, e.proc, e.zone, e.apf_authorized) for e in entries]
    conn.executemany(
        "INSERT INTO cics_dfhrpl_entries (dsn, proc, zone, apf_authorized) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_cics_dfhrpl_entries(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM cics_dfhrpl_entries ORDER BY proc, dsn")
    return cur.fetchall()


def save_cics_sit_overrides(conn: sqlite3.Connection, overrides: list[CicsSitOverride]) -> None:
    conn.execute("DELETE FROM cics_sit_overrides")
    rows = [(o.keyword, o.value, o.proc) for o in overrides]
    conn.executemany(
        "INSERT INTO cics_sit_overrides (keyword, value, proc) VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()


def all_cics_sit_overrides(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM cics_sit_overrides ORDER BY proc, keyword")
    return cur.fetchall()


def save_cics_csd_definitions(conn: sqlite3.Connection, definitions: list[CicsCsdDefinition]) -> None:
    conn.execute("DELETE FROM cics_csd_definitions")
    rows = [(d.def_type, d.name, d.group, d.csd_dsn) for d in definitions]
    conn.executemany(
        "INSERT INTO cics_csd_definitions (def_type, name, grp, csd_dsn) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_cics_csd_definitions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM cics_csd_definitions ORDER BY grp, name")
    return cur.fetchall()


def save_zone_index(conn: sqlite3.Connection, entries: list[ZoneIndexEntry]) -> None:
    conn.execute("DELETE FROM zone_index")
    rows = [(e.zone_name, e.zone_type, e.csi, e.source_csi) for e in entries]
    conn.executemany(
        "INSERT INTO zone_index (zone_name, zone_type, csi, source_csi) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()


def all_zone_index(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM zone_index ORDER BY source_csi, zone_name")
    return cur.fetchall()


def save_zones(conn: sqlite3.Connection, zones: list[Zone]) -> None:
    conn.execute("DELETE FROM zones")
    rows = [(z.name, z.csi or None, json.dumps(z.dddefs)) for z in zones]
    conn.executemany("INSERT INTO zones (name, csi, dddefs_json) VALUES (?, ?, ?)", rows)
    conn.commit()


def all_zones(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM zones ORDER BY name")
    return cur.fetchall()


def save_fmids(conn: sqlite3.Connection, fmids: list[Fmid]) -> None:
    conn.execute("DELETE FROM fmids")
    rows = [(f.fmid, f.zone, f.status or None) for f in fmids]
    conn.executemany("INSERT INTO fmids (fmid, zone, status) VALUES (?, ?, ?)", rows)
    conn.commit()


def all_fmids(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT * FROM fmids ORDER BY fmid, zone")
    return cur.fetchall()
