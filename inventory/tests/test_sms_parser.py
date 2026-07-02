from pathlib import Path

from inventory import sms_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_sms():
    return sms_parser.parse_sms(FIXTURES / "sample_sms.txt")


def test_storage_groups_parsed_with_type_and_status():
    groups = load_sms()
    by_name = {g.name: (g.group_type, g.status) for g in groups}
    assert by_name == {
        "SG1": ("POOL", "+ +"),
        "TAPEGRP": ("TAPE", "+ +"),
        "SG2": ("POOL", "+ -"),
    }


def test_repeated_storgrp_header_does_not_break_consecutive_groups():
    # Confirmed against a real reply: the "STORGRP TYPE SYSTEM= 1 2"
    # header can appear once before several consecutive group rows
    # (TAPEGRP and SG2 here), not once per group as originally guessed.
    groups = load_sms()
    assert len(groups) == 3


def test_volumes_come_from_a_separate_flat_table_not_indented_lines():
    groups = load_sms()
    by_name = {g.name: g.volumes for g in groups}
    assert by_name["SG1"] == ["VOL001", "VOL002"]
    assert by_name["SG2"] == ["VOL010"]


def test_tape_group_has_no_volumes_listvol_ignored():
    # "LISTVOL IS IGNORED FOR OBJECT, OBJECT BACKUP, AND TAPE STORAGE
    # GROUPS" -- confirmed real behavior, TAPEGRP never appears in the
    # volume table.
    groups = load_sms()
    tapegrp = next(g for g in groups if g.name == "TAPEGRP")
    assert tapegrp.volumes == []


def test_legend_and_footer_lines_not_treated_as_volume_rows():
    groups = load_sms()
    all_volumes = [v for g in groups for v in g.volumes]
    assert "SYSTEM" not in all_volumes
    assert len(all_volumes) == 3
