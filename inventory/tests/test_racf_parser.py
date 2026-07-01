from pathlib import Path

from inventory import racf_parser

FIXTURES = Path(__file__).parent / "fixtures"


def _snapshot():
    return racf_parser.parse_racf(FIXTURES / "sample_racf.txt")


def test_users_parsed():
    snap = _snapshot()
    assert len(snap.users) == 2

    jdoe = next(u for u in snap.users if u.userid == "JDOE001")
    assert jdoe.name == "JOHN DOE"
    assert jdoe.owner == "SYSPROG"
    assert jdoe.default_group == "SYSPROG"
    assert jdoe.special is True
    assert jdoe.operations is False
    assert jdoe.auditor is True
    assert jdoe.revoked is False
    assert jdoe.restricted is None

    mary = next(u for u in snap.users if u.userid == "MARYADM")
    assert mary.revoked is True
    assert mary.restricted is True


def test_groups_parsed():
    snap = _snapshot()
    assert len(snap.groups) == 1
    group = snap.groups[0]
    assert group.name == "SYSPROG"
    assert group.superior_group == "SYS1"
    assert group.owner == "IBMUSER"
    assert group.universal_access == "NONE"
    assert group.description == "Systems programming group"


def test_group_connections_parsed():
    snap = _snapshot()
    assert len(snap.group_connections) == 2

    jdoe_conn = next(c for c in snap.group_connections if c.userid == "JDOE001")
    assert jdoe_conn.group == "SYSPROG"
    assert jdoe_conn.group_special is True
    assert jdoe_conn.group_universal_access == "CONTROL"
    assert jdoe_conn.revoked_in_group is False

    mary_conn = next(c for c in snap.group_connections if c.userid == "MARYADM")
    assert mary_conn.revoked_in_group is True


def test_dataset_profile_and_access_parsed():
    snap = _snapshot()
    assert len(snap.dataset_profiles) == 1
    profile = snap.dataset_profiles[0]
    assert profile.profile == "PROD.PAYROLL.**"
    assert profile.generic is True
    assert profile.owner == "SYSPROG"
    assert profile.universal_access == "NONE"

    assert len(snap.dataset_access) == 2
    paygrp = next(a for a in snap.dataset_access if a.auth_id == "PAYGRP")
    assert paygrp.access == "READ"
    admgrp = next(a for a in snap.dataset_access if a.auth_id == "ADMGRP")
    assert admgrp.access == "ALTER"


def test_general_resource_curated_classes_kept():
    snap = _snapshot()
    class_names = {p.class_name for p in snap.general_resource_profiles}
    assert class_names == {"STARTED", "FACILITY"}

    started = next(p for p in snap.general_resource_profiles if p.class_name == "STARTED")
    assert started.profile == "CICSPROD.STC"
    assert started.owner == "SYSPROG"

    access_class_names = {a.class_name for a in snap.general_resource_access}
    assert access_class_names == {"STARTED", "FACILITY"}


def test_non_curated_class_filtered_out():
    snap = _snapshot()
    profile_names = {p.profile for p in snap.general_resource_profiles}
    access_profile_names = {a.profile for a in snap.general_resource_access}
    assert "TERM001" not in profile_names
    assert "TERM001" not in access_profile_names
