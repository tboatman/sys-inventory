"""Tests for store.py: schema creation and the save/all persistence
mechanics every domain shares (delete-then-insert "replace" semantics,
JSON-encoded fields, and singleton tables) -- not per-domain field
correctness, which is each parser's own test file's job."""
from __future__ import annotations

import json

import pytest

from inventory import store
from inventory.models import (
    ActiveJob,
    BpxprmStatement,
    CatalogDataset,
    CicsCsdDefinition,
    CicsDfhrplEntry,
    CicsSitOverride,
    DatasetAccess,
    DatasetProfile,
    Db2Package,
    Db2Plan,
    Fmid,
    GeneralResourceAccess,
    GeneralResourceProfile,
    IeasysStatement,
    Jes2InitStatement,
    LineageStep,
    ParmlibDataset,
    Product,
    RacfGroup,
    RacfGroupConnection,
    RacfSnapshot,
    RacfUser,
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

EXPECTED_TABLES = {
    "lineage", "subsystems", "started_tasks", "system_info", "products",
    "parmlib_datasets", "ieasys_statements", "bpxprm_statements",
    "active_jobs", "uss_processes", "catalog_datasets", "vsam_clusters",
    "racf_users", "racf_groups", "racf_group_connections",
    "racf_dataset_profiles", "racf_dataset_access",
    "racf_general_resource_profiles", "racf_general_resource_access",
    "uss_mounts", "jes2_init_statements", "vtam_major_nodes",
    "vtam_start_options", "vtam_topology_summary", "tcpip_home_addresses",
    "tcpip_profile_statements", "sms_storage_groups", "wlm_policy",
    "db2_packages", "db2_plans", "wlm_zosmf_entries",
    "cics_dfhrpl_entries", "cics_sit_overrides", "cics_csd_definitions",
    "zone_index", "zones", "fmids",
}


@pytest.fixture
def conn(tmp_path):
    c = store.connect(tmp_path / "test.db")
    yield c
    c.close()


def test_connect_creates_every_table(conn):
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables


def test_connect_is_idempotent_and_preserves_committed_data(tmp_path):
    # A second `inventory ingest` run (or any second connect() against the
    # same file) must not fail re-issuing 'CREATE TABLE IF NOT EXISTS', and
    # must see what the first connection already committed.
    db_path = tmp_path / "test.db"
    conn1 = store.connect(db_path)
    store.save_subsystems(conn1, [Subsystem(name="JES2", source_member="IEFSSN00")])
    conn1.close()

    conn2 = store.connect(db_path)
    rows = store.all_subsystems(conn2)
    conn2.close()
    assert [r["name"] for r in rows] == ["JES2"]


def test_save_lineage_replaces_not_appends(conn):
    step_a = LineageStep(member="A", step_name="S1", pgm="PGM1", dataset="D1",
                          zone="Z1", fmid="F1", resolution="APPLIED",
                          apf_authorized=True, csi="CSI1")
    store.save_lineage(conn, {"A": [step_a]})
    assert len(store.all_lineage(conn)) == 1

    step_b = LineageStep(member="B", step_name="S1", pgm="PGM2", dataset="D2",
                          zone="Z2", fmid="F2", resolution="LNKLST",
                          apf_authorized=False, csi=None)
    store.save_lineage(conn, {"B": [step_b]})
    rows = store.all_lineage(conn)
    assert len(rows) == 1
    assert rows[0]["member"] == "B"
    assert rows[0]["csi"] is None


def test_lineage_for_member_filters_by_member(conn):
    store.save_lineage(conn, {
        "A": [LineageStep(member="A", step_name="S1", pgm="P1", dataset=None,
                           zone=None, fmid=None, resolution="LNKLST")],
        "B": [LineageStep(member="B", step_name="S1", pgm="P2", dataset=None,
                           zone=None, fmid=None, resolution="LNKLST")],
    })
    rows = store.lineage_for_member(conn, "A")
    assert len(rows) == 1
    assert rows[0]["pgm"] == "P1"


def test_system_info_singleton_replaces_and_clears(conn):
    assert store.get_system_info(conn) is None

    store.save_system_info(conn, SystemInfo(sysname="SYS1", sysclone="A1"))
    assert store.get_system_info(conn)["sysname"] == "SYS1"

    store.save_system_info(conn, SystemInfo(sysname="SYS2"))
    row = store.get_system_info(conn)
    assert row["sysname"] == "SYS2"  # replaced, not appended

    store.save_system_info(conn, None)
    assert store.get_system_info(conn) is None


def test_wlm_policy_singleton(conn):
    assert store.get_wlm_policy(conn) is None
    store.save_wlm_policy(conn, WlmPolicy(policy_name="WLMPOL", mode="GOAL"))
    row = store.get_wlm_policy(conn)
    assert row["policy_name"] == "WLMPOL"
    assert row["mode"] == "GOAL"

    store.save_wlm_policy(conn, None)
    assert store.get_wlm_policy(conn) is None


def test_vtam_topology_summary_singleton(conn):
    assert store.get_vtam_topology_summary(conn) is None
    store.save_vtam_topology_summary(conn, VtamTopologySummary(
        last_checkpoint="NONE", adj=1, nn=2, en=3, served_en=4, cdservr=5,
        icn=6, bn=7, initdb_checkpoint_dataset="NONE", last_garbage_collection="07/01/26",
    ))
    row = store.get_vtam_topology_summary(conn)
    assert row["adj"] == 1
    assert row["last_garbage_collection"] == "07/01/26"

    store.save_vtam_topology_summary(conn, None)
    assert store.get_vtam_topology_summary(conn) is None


def test_jes2_init_statements_params_json_round_trips(conn):
    store.save_jes2_init_statements(conn, [
        Jes2InitStatement(stmt="JOBCLASS", subscript="STC",
                           params={"MAXCARDS": "9999"}, source_member="JES2PARM"),
    ])
    row = store.all_jes2_init_statements(conn)[0]
    assert json.loads(row["params_json"]) == {"MAXCARDS": "9999"}


def test_sms_storage_groups_volumes_json_round_trips(conn):
    store.save_sms_storage_groups(conn, [
        SmsStorageGroup(name="SG1", status="+ +", group_type="POOL", volumes=["VOL001", "VOL002"]),
    ])
    row = store.all_sms_storage_groups(conn)[0]
    assert json.loads(row["volumes_json"]) == ["VOL001", "VOL002"]


def test_wlm_zosmf_entries_raw_json_round_trips(conn):
    store.save_wlm_zosmf_entries(conn, [
        WlmZosmfEntry(name="SVC1", raw={"nested": {"a": 1}}),
    ])
    row = store.all_wlm_zosmf_entries(conn)[0]
    assert json.loads(row["raw_json"]) == {"nested": {"a": 1}}


def test_racf_snapshot_saves_and_clears_all_seven_tables_atomically(conn):
    snapshot = RacfSnapshot(
        users=[RacfUser(userid="USER1")],
        groups=[RacfGroup(name="GRP1")],
        group_connections=[RacfGroupConnection(userid="USER1", group="GRP1")],
        dataset_profiles=[DatasetProfile(profile="SYS1.**")],
        dataset_access=[DatasetAccess(profile="SYS1.**", auth_id="USER1")],
        general_resource_profiles=[GeneralResourceProfile(profile="FACILITY.X", class_name="FACILITY")],
        general_resource_access=[GeneralResourceAccess(profile="FACILITY.X", class_name="FACILITY", auth_id="USER1")],
    )
    store.save_racf_snapshot(conn, snapshot)
    assert len(store.all_racf_users(conn)) == 1
    assert len(store.all_racf_groups(conn)) == 1
    assert len(store.all_racf_group_connections(conn)) == 1
    assert len(store.all_racf_dataset_profiles(conn)) == 1
    assert len(store.all_racf_dataset_access(conn)) == 1
    assert len(store.all_racf_general_resource_profiles(conn)) == 1
    assert len(store.all_racf_general_resource_access(conn)) == 1

    # IRRDBU00 always represents the RACF database's full current state, so
    # re-ingesting must replace every table, not merge into it (see
    # save_racf_snapshot's own docstring).
    store.save_racf_snapshot(conn, RacfSnapshot())
    assert store.all_racf_users(conn) == []
    assert store.all_racf_groups(conn) == []
    assert store.all_racf_group_connections(conn) == []
    assert store.all_racf_dataset_profiles(conn) == []
    assert store.all_racf_dataset_access(conn) == []
    assert store.all_racf_general_resource_profiles(conn) == []
    assert store.all_racf_general_resource_access(conn) == []


# Every remaining table follows the same "delete then insert" replace
# mechanics store.py implements uniformly -- covered generically here
# rather than once per domain, since the interesting behavior (does a
# second, smaller save() actually replace the first) is identical across
# all of them. Field-level parsing correctness belongs to each parser's
# own test file, not here.
ROUND_TRIP_CASES = [
    pytest.param(
        store.save_subsystems, store.all_subsystems,
        lambda n: [Subsystem(name=f"SUB{i}", source_member="IEFSSN00") for i in range(n)],
        id="subsystems",
    ),
    pytest.param(
        store.save_started_tasks, store.all_started_tasks,
        lambda n: [StartedTask(task_name=f"TASK{i}", source_member="COMMND00") for i in range(n)],
        id="started_tasks",
    ),
    pytest.param(
        store.save_products, store.all_products,
        lambda n: [Product(id=f"PROD{i}", source_member="IFAPRD00") for i in range(n)],
        id="products",
    ),
    pytest.param(
        store.save_parmlib_datasets, store.all_parmlib_datasets,
        lambda n: [ParmlibDataset(entry=str(i + 1), dsn=f"DSN{i}") for i in range(n)],
        id="parmlib_datasets",
    ),
    pytest.param(
        store.save_ieasys_statements, store.all_ieasys_statements,
        lambda n: [IeasysStatement(keyword=f"KW{i}", value="V", source_member="IEASYS00") for i in range(n)],
        id="ieasys_statements",
    ),
    pytest.param(
        store.save_bpxprm_statements, store.all_bpxprm_statements,
        lambda n: [BpxprmStatement(stmt=f"STMT{i}", operands="OP", source_member="BPXPRM00") for i in range(n)],
        id="bpxprm_statements",
    ),
    pytest.param(
        store.save_active_jobs, store.all_active_jobs,
        lambda n: [ActiveJob(job_id=f"JOB{i}", name=f"NAME{i}") for i in range(n)],
        id="active_jobs",
    ),
    pytest.param(
        store.save_processes, store.all_processes,
        lambda n: [UssProcess(command=f"cmd{i}") for i in range(n)],
        id="uss_processes",
    ),
    pytest.param(
        store.save_catalog_datasets, store.all_catalog_datasets,
        lambda n: [CatalogDataset(dsn=f"DSN{i}") for i in range(n)],
        id="catalog_datasets",
    ),
    pytest.param(
        store.save_vsam_clusters, store.all_vsam_clusters,
        lambda n: [VsamCluster(name=f"CLUSTER{i}") for i in range(n)],
        id="vsam_clusters",
    ),
    pytest.param(
        store.save_uss_mounts, store.all_uss_mounts,
        lambda n: [UssMount(path=f"/mnt{i}") for i in range(n)],
        id="uss_mounts",
    ),
    pytest.param(
        store.save_jes2_init_statements, store.all_jes2_init_statements,
        lambda n: [Jes2InitStatement(stmt=f"STMT{i}", source_member="JES2PARM") for i in range(n)],
        id="jes2_init_statements",
    ),
    pytest.param(
        store.save_vtam_major_nodes, store.all_vtam_major_nodes,
        lambda n: [VtamMajorNode(name=f"NODE{i}") for i in range(n)],
        id="vtam_major_nodes",
    ),
    pytest.param(
        store.save_vtam_start_options, store.all_vtam_start_options,
        lambda n: [VtamStartOption(keyword=f"KW{i}", value="V") for i in range(n)],
        id="vtam_start_options",
    ),
    pytest.param(
        store.save_tcpip_home_addresses, store.all_tcpip_home_addresses,
        lambda n: [TcpipHomeAddress(link_name=f"LINK{i}", ip_address="1.2.3.4") for i in range(n)],
        id="tcpip_home_addresses",
    ),
    pytest.param(
        store.save_tcpip_profile_statements, store.all_tcpip_profile_statements,
        lambda n: [TcpipProfileStatement(stmt=f"STMT{i}", operands="OP") for i in range(n)],
        id="tcpip_profile_statements",
    ),
    pytest.param(
        store.save_sms_storage_groups, store.all_sms_storage_groups,
        lambda n: [SmsStorageGroup(name=f"SG{i}") for i in range(n)],
        id="sms_storage_groups",
    ),
    pytest.param(
        store.save_db2_packages, store.all_db2_packages,
        lambda n: [Db2Package(name=f"PKG{i}", ssid="DB2A") for i in range(n)],
        id="db2_packages",
    ),
    pytest.param(
        store.save_db2_plans, store.all_db2_plans,
        lambda n: [Db2Plan(name=f"PLAN{i}", ssid="DB2A") for i in range(n)],
        id="db2_plans",
    ),
    pytest.param(
        store.save_wlm_zosmf_entries, store.all_wlm_zosmf_entries,
        lambda n: [WlmZosmfEntry(name=f"E{i}") for i in range(n)],
        id="wlm_zosmf_entries",
    ),
    pytest.param(
        store.save_cics_dfhrpl_entries, store.all_cics_dfhrpl_entries,
        lambda n: [CicsDfhrplEntry(dsn=f"DSN{i}", proc="CICSPROC") for i in range(n)],
        id="cics_dfhrpl_entries",
    ),
    pytest.param(
        store.save_cics_sit_overrides, store.all_cics_sit_overrides,
        lambda n: [CicsSitOverride(keyword=f"KW{i}", value="V", proc="CICSPROC") for i in range(n)],
        id="cics_sit_overrides",
    ),
    pytest.param(
        store.save_cics_csd_definitions, store.all_cics_csd_definitions,
        lambda n: [CicsCsdDefinition(def_type="PROGRAM", name=f"PGM{i}") for i in range(n)],
        id="cics_csd_definitions",
    ),
    pytest.param(
        store.save_zone_index, store.all_zone_index,
        lambda n: [ZoneIndexEntry(zone_name=f"ZONE{i}", zone_type="TARGET", csi="CSI1") for i in range(n)],
        id="zone_index",
    ),
    pytest.param(
        store.save_zones, store.all_zones,
        lambda n: [Zone(name=f"ZONE{i}", csi="CSI1") for i in range(n)],
        id="zones",
    ),
    pytest.param(
        store.save_fmids, store.all_fmids,
        lambda n: [Fmid(fmid=f"FMID{i}", zone="ZONE1") for i in range(n)],
        id="fmids",
    ),
]


@pytest.mark.parametrize("save_fn, all_fn, make_items", ROUND_TRIP_CASES)
def test_save_replaces_not_appends(conn, save_fn, all_fn, make_items):
    assert all_fn(conn) == []

    save_fn(conn, make_items(3))
    assert len(all_fn(conn)) == 3

    save_fn(conn, make_items(1))
    assert len(all_fn(conn)) == 1  # replaced, not appended to the 3 above

    save_fn(conn, [])
    assert all_fn(conn) == []
