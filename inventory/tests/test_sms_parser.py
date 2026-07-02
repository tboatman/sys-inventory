from pathlib import Path

from inventory import sms_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_sms():
    return sms_parser.parse_sms(FIXTURES / "sample_sms.txt")


def test_storage_groups_parsed_with_volumes():
    groups, _, _ = load_sms()
    by_name = {g.name: (g.status, g.volumes) for g in groups}
    assert by_name == {
        "SG1": ("ENABLE", ["VOL001", "VOL002"]),
        "SG2": ("DISABLE", ["VOL010"]),
    }


def test_banner_and_header_lines_not_treated_as_storage_groups():
    groups, _, _ = load_sms()
    assert len(groups) == 2


def test_storage_classes_parsed_generically():
    _, storclas, _ = load_sms()
    by_name = {c.name: c.params for c in storclas}
    assert by_name == {
        "STANDARD": {"AVAILABILITY": "STANDARD", "ACCESSIBILITY": "CONTINUOUS", "PERFORMANCE": "3"},
        "FAST": {"AVAILABILITY": "STANDARD", "PERFORMANCE": "1"},
    }


def test_management_classes_parsed_generically():
    _, _, mgmtclas = load_sms()
    by_name = {c.name: c.params for c in mgmtclas}
    assert by_name == {
        "MCDEFLT": {"EXPIRE": "NOLIMIT", "MIGRATE": "030"},
    }


def test_message_id_lines_not_treated_as_class_names():
    _, storclas, mgmtclas = load_sms()
    names = {c.name for c in storclas} | {c.name for c in mgmtclas}
    assert "IGD002I" not in names
    assert "END" not in names
