from pathlib import Path

from inventory import smpe_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_zones():
    return smpe_parser.parse_smplist(FIXTURES / "sample_smpe_list.txt")


def test_zones_discovered():
    zones = load_zones()
    assert set(zones) == {"TZONE1", "TZONE2"}


def test_dddefs_parsed_per_zone():
    zones = load_zones()
    assert zones["TZONE1"].dddefs == {"LINKLIB": "SYS1.LINKLIB"}
    assert zones["TZONE2"].dddefs == {"SITELIB": "MY.SITE.LINKLIB"}


def test_module_fmid_parsed_per_zone():
    zones = load_zones()
    assert zones["TZONE1"].module_fmid == {"IGYCRCTL": "HLA2280", "IEBGENER": "HBB7790"}
    assert zones["TZONE2"].module_fmid == {"SAMPMOD": "USER001"}


def test_fmid_status_parsed():
    zones = load_zones()
    assert zones["TZONE1"].fmid_status == {"HLA2280": "APPLIED", "HBB7790": "APPLIED"}
    assert zones["TZONE2"].fmid_status == {"USER001": "APPLIED"}


def test_merge_zones_combines_entries():
    zones_a = {"TZONE1": load_zones()["TZONE1"]}
    zones_b = load_zones()
    merged = smpe_parser.merge_zones(zones_a, zones_b)
    assert set(merged) == {"TZONE1", "TZONE2"}


def test_csi_stamped_on_every_zone():
    zones = load_zones()
    assert zones["TZONE1"].csi == "EDUC.TEST.GLOBAL.CSI"
    assert zones["TZONE2"].csi == "EDUC.TEST.GLOBAL.CSI"


def test_missing_csi_header_defaults_to_empty(tmp_path):
    # A file with no ##CSI sentinel (e.g. captured before it existed)
    # still parses fine, just with an unset csi -- backward compatible.
    original = (FIXTURES / "sample_smpe_list.txt").read_text()
    no_header = original.split("\n", 1)[1]
    p = tmp_path / "no_csi.smplist.txt"
    p.write_text(no_header)
    zones = smpe_parser.parse_smplist(p)
    assert zones["TZONE1"].csi == ""


def test_merge_zones_preserves_csi():
    merged = smpe_parser.merge_zones(load_zones())
    assert merged["TZONE1"].csi == "EDUC.TEST.GLOBAL.CSI"
