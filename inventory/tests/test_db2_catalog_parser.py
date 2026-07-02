from pathlib import Path

from inventory import db2_catalog_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_db2_catalog():
    return db2_catalog_parser.parse_db2_catalog(FIXTURES / "sample_db2_catalog.txt")


def test_packages_parsed():
    packages, _ = load_db2_catalog()
    by_name = {p.name: (p.creator, p.bind_timestamp, p.ssid) for p in packages}
    assert by_name == {
        "PKG1": ("COLLID1", "2024-01-15-10.30.00.000000", "DB2A"),
        "PKG2": ("COLLID2", "2024-02-20-11.15.30.000000", "DB2A"),
    }


def test_plans_parsed():
    _, plans = load_db2_catalog()
    by_name = {p.name: (p.creator, p.bind_timestamp, p.ssid) for p in plans}
    assert by_name == {
        "PLAN01": ("SYSADM", "2023-11-01-09.00.00.000000", "DB2A"),
    }


def test_separator_header_and_message_lines_not_treated_as_rows():
    packages, plans = load_db2_catalog()
    assert len(packages) == 2
    assert len(plans) == 1
