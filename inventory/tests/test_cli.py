"""Tests for cli.py: `inventory ingest`'s glob-matching/dispatch logic (the
piece with real history of silent bugs -- e.g. `*wlm*.txt` originally also
matched `wlm_zosmf.txt`) and a broad smoke test that every query subcommand
at least runs without crashing. Per-parser field correctness belongs to
each parser's own test file, not here."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from inventory import store
from inventory.cli import build_parser, main

FIXTURES = Path(__file__).parent / "fixtures"

# Maps each fixture to the filename `zos-extract`/`ansible` would actually
# produce, matching the demo block in doc/inventory.md and the root README.
FIXTURE_TO_REAL_NAME = {
    "sample_proclib.txt": "00_proclib.txt",
    "sample_smpe_list.txt": "tzone1.smplist.txt",
    "sample_lnklst.txt": "lnklst.txt",
    "sample_apf.txt": "apf.txt",
    "sample_ssn.txt": "00_ssn.txt",
    "sample_commnd.txt": "00_commnd.txt",
    "sample_sysinfo.txt": "sysinfo.txt",
    "sample_ifaprd.txt": "00_ifaprd.txt",
    "sample_active_jobs.txt": "active_jobs.txt",
    "sample_processes.txt": "processes.txt",
    "sample_catalog.txt": "demo_catalog.txt",
    "sample_racf.txt": "racf.txt",
    "sample_uss_mounts.txt": "uss_mounts.txt",
    "sample_jes2parm.txt": "jes2parm.txt",
    "sample_vtam.txt": "vtam.txt",
    "sample_tcpip.txt": "tcpip.txt",
    "sample_sms.txt": "sms.txt",
    "sample_wlm.txt": "wlm.txt",
    "sample_db2_catalog.txt": "db2_catalog.txt",
    "sample_wlm_zosmf.txt": "wlm_zosmf.txt",
    "sample_cics_deepening.txt": "cics_deepening.txt",
    "sample_parmlib_snapshot.txt": "parmlib_snapshot.txt",
    "sample_ieasys_snapshot.txt": "ieasys_snapshot.txt",
    "sample_bpxprm_snapshot.txt": "bpxprm_snapshot.txt",
    "sample_devsup_snapshot.txt": "devsup_snapshot.txt",
}


@pytest.fixture
def full_input_dir(tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    for fixture_name, real_name in FIXTURE_TO_REAL_NAME.items():
        (input_dir / real_name).write_text((FIXTURES / fixture_name).read_text())
    return input_dir


def test_ingest_populates_every_domain(full_input_dir, tmp_path):
    db_path = tmp_path / "demo.db"
    rc = main(["--db", str(db_path), "ingest", str(full_input_dir)])
    assert rc == 0

    conn = store.connect(db_path)
    try:
        assert len(store.all_lineage(conn)) > 0
        assert len(store.all_subsystems(conn)) > 0
        assert len(store.all_started_tasks(conn)) > 0
        assert len(store.all_products(conn)) > 0
        assert store.get_system_info(conn) is not None
        assert len(store.all_parmlib_datasets(conn)) > 0
        assert len(store.all_ieasys_statements(conn)) > 0
        assert len(store.all_bpxprm_statements(conn)) > 0
        assert len(store.all_devsup_statements(conn)) > 0
        assert len(store.all_active_jobs(conn)) > 0
        assert len(store.all_processes(conn)) > 0
        assert len(store.all_catalog_datasets(conn)) > 0
        assert len(store.all_racf_users(conn)) > 0
        assert len(store.all_uss_mounts(conn)) > 0
        assert len(store.all_jes2_init_statements(conn)) > 0
        assert len(store.all_vtam_major_nodes(conn)) > 0
        assert len(store.all_vtam_start_options(conn)) > 0
        assert store.get_vtam_topology_summary(conn) is not None
        assert len(store.all_tcpip_home_addresses(conn)) > 0
        assert len(store.all_tcpip_profile_statements(conn)) > 0
        assert len(store.all_sms_storage_groups(conn)) > 0
        assert store.get_wlm_policy(conn) is not None
        assert len(store.all_db2_packages(conn)) > 0
        assert len(store.all_db2_plans(conn)) > 0
        assert len(store.all_wlm_zosmf_entries(conn)) > 0
        dfhrpl = store.all_cics_dfhrpl_entries(conn)
        assert len(dfhrpl) > 0
        # zone/apf are resolved at ingest time via resolver.dataset_zone(),
        # not left as the parser's own unset defaults -- see cli.py's
        # cics_dfhrpl_entries loop.
        assert any(row["apf_authorized"] is not None for row in dfhrpl)
        assert len(store.all_cics_sit_overrides(conn)) > 0
        assert len(store.all_cics_csd_definitions(conn)) > 0
        assert len(store.all_zones(conn)) > 0
        assert len(store.all_fmids(conn)) > 0
    finally:
        conn.close()


def test_ingest_rejects_non_directory(tmp_path, capsys):
    not_a_dir = tmp_path / "nope.txt"
    not_a_dir.write_text("")
    rc = main(["--db", str(tmp_path / "x.db"), "ingest", str(not_a_dir)])
    assert rc == 1
    assert "is not a directory" in capsys.readouterr().err


def test_ingest_wlm_glob_excludes_wlm_zosmf_file(tmp_path):
    """Regression test for the bug fixed during WLM-z/OSMF wiring: '*wlm*.txt'
    must not also match 'wlm_zosmf.txt'."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "wlm_zosmf.txt").write_text(
        json.dumps([{"serviceClassName": "SVC1", "goal": 1}])
    )

    db_path = tmp_path / "demo.db"
    rc = main(["--db", str(db_path), "ingest", str(input_dir)])
    assert rc == 0

    conn = store.connect(db_path)
    try:
        assert store.get_wlm_policy(conn) is None
        assert len(store.all_wlm_zosmf_entries(conn)) == 1
    finally:
        conn.close()


def test_ingest_parmlib_snapshot_glob_excludes_from_member_dumps(tmp_path):
    """Regression test for the parallel bug class in the PARMLIB member-dump
    glob: a 'D PARMLIB' console reply must be parsed as parmlib_datasets,
    not fed to jcl_parser as if it were a PROCLIB/PARMLIB member dump."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "parmlib_snapshot.txt").write_text(
        "  ENTRY  FLAGS  VOLUME  DATA SET\n"
        "    1      S    HCD000  SYS1.COMMON.PARMLIB\n"
        "    2      S    BES2W1  SYS3.BES2.PARMLIB\n"
    )

    db_path = tmp_path / "demo.db"
    rc = main(["--db", str(db_path), "ingest", str(input_dir)])
    assert rc == 0

    conn = store.connect(db_path)
    try:
        assert len(store.all_parmlib_datasets(conn)) == 2
        assert store.all_lineage(conn) == []
    finally:
        conn.close()


def test_ingest_picks_up_renamed_snapshot_files(tmp_path):
    """The three snapshot outfiles are now glob-matched (see
    zos_extract_*_snapshot_outfile), not exact-matched, so a
    site-customized filename must still be ingested."""
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "lpar1_ieasys_snapshot.txt").write_text(
        (FIXTURES / "sample_ieasys_snapshot.txt").read_text()
    )

    db_path = tmp_path / "demo.db"
    rc = main(["--db", str(db_path), "ingest", str(input_dir)])
    assert rc == 0

    conn = store.connect(db_path)
    try:
        assert len(store.all_ieasys_statements(conn)) > 0
    finally:
        conn.close()


# Every subcommand below takes no positional argument, so it can be run
# against a freshly-created, empty database purely to confirm the command
# doesn't crash (e.g. a column-name typo against the real schema) -- exact
# per-command output formatting isn't asserted here. 'ingest'/'lineage'/
# 'trace' take a required positional and are exercised in their own tests
# above/below instead.
NO_ARG_SUBCOMMANDS = [
    "subsystems", "started-tasks", "sysinfo", "products", "parmlib",
    "ieasys", "bpxprm", "devsup", "active", "processes", "catalog", "vsam",
    "racf-users", "racf-groups", "racf-connections", "racf-dataset-profiles",
    "racf-dataset-access", "racf-resource-profiles", "racf-resource-access",
    "uss-mounts", "jes2parm", "vtam-majnodes", "vtam-options",
    "vtam-topology", "tcpip-home", "tcpip-profile", "sms-storgrps", "wlm",
    "db2-packages", "db2-plans", "wlm-zosmf", "cics-dfhrpl", "cics-sit",
    "cics-csd", "zone-index", "zones", "fmids", "zone-gaps", "report",
]


def test_build_parser_registers_every_expected_subcommand():
    parser = build_parser()
    subparsers_action = next(
        a for a in parser._subparsers._group_actions if a.dest == "command"
    )
    assert set(subparsers_action.choices) == set(NO_ARG_SUBCOMMANDS) | {"ingest", "lineage", "trace"}


@pytest.mark.parametrize("name", NO_ARG_SUBCOMMANDS)
def test_no_arg_subcommand_runs_cleanly_against_empty_db(tmp_path, name):
    db_path = tmp_path / "empty.db"
    store.connect(db_path).close()  # create schema, no data ingested

    rc = main(["--db", str(db_path), name])
    assert rc in (0, 1)


def test_lineage_reports_not_found_against_empty_db(tmp_path, capsys):
    db_path = tmp_path / "empty.db"
    store.connect(db_path).close()

    rc = main(["--db", str(db_path), "lineage", "NOSUCH"])
    assert rc == 1
    assert "no lineage found" in capsys.readouterr().err


def test_trace_combines_started_active_and_lineage(full_input_dir, tmp_path, capsys):
    db_path = tmp_path / "demo.db"
    assert main(["--db", str(db_path), "ingest", str(full_input_dir)]) == 0
    capsys.readouterr()  # discard ingest's own summary line

    conn = store.connect(db_path)
    task_name = store.all_started_tasks(conn)[0]["task_name"]
    conn.close()

    rc = main(["--db", str(db_path), "trace", task_name])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"TRACE: {task_name}" in out
