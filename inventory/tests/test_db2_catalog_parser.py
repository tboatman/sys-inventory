from pathlib import Path

from inventory import db2_catalog_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_db2_catalog():
    return db2_catalog_parser.parse_db2_catalog(FIXTURES / "sample_db2_catalog.txt")


def test_packages_parsed():
    # Regression test for the real DSNTEP2 report shape (confirmed
    # against this site's DBDG subsystem): DSNTEP2 transposes wide result
    # sets into one boxed column-section per column (NAME, then CREATOR,
    # then BINDTIME), not "NAME CREATOR BINDTIME" side by side on one
    # line as originally guessed. Row 3's NAME value lands on a second
    # physical page (a mid-section "PAGE 1.1" break) -- confirmed this
    # still reconstructs correctly since the row-number key doesn't care
    # which physical page a value printed on.
    packages, _ = load_db2_catalog()
    by_name = {p.name: (p.creator, p.bind_timestamp, p.ssid) for p in packages}
    assert by_name == {
        "PKG1": ("COLLID1", "2024-01-15-10.30.00.000000", "DBDG"),
        "PKG2": ("COLLID2", "2024-02-20-11.15.30.000000", "DBDG"),
        "PKG3": ("COLLID3", "2024-03-01-08.00.00.000000", "DBDG"),
    }


def test_plans_parsed():
    _, plans = load_db2_catalog()
    by_name = {p.name: (p.creator, p.bind_timestamp, p.ssid) for p in plans}
    assert by_name == {
        "PLAN01": ("SYSADM", "2023-11-01-09.00.00.000000", "DBDG"),
    }


def test_separator_header_and_message_lines_not_treated_as_rows():
    packages, plans = load_db2_catalog()
    assert len(packages) == 3
    assert len(plans) == 1
