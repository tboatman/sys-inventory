from pathlib import Path

from inventory import smpe_parser
from inventory.models import Zone

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


def test_merge_zones_disambiguates_cross_csi_name_collision():
    # Two different CSIs (e.g. two vendor products) can each define a
    # same-named zone -- the second one must not silently clobber the
    # first, and must land under a key its own `.name` field can be
    # looked up by (see resolver._dataset_to_zone()'s "return zone.name").
    zone_a = {"TZONE1": Zone(name="TZONE1", csi="EDUC.A.CSI")}
    zone_b = {"TZONE1": Zone(name="TZONE1", csi="EDUC.B.CSI")}
    merged = smpe_parser.merge_zones(zone_a, zone_b)
    assert set(merged) == {"TZONE1", "TZONE1@EDUC.B.CSI"}
    assert merged["TZONE1"].csi == "EDUC.A.CSI"
    assert merged["TZONE1@EDUC.B.CSI"].csi == "EDUC.B.CSI"
    assert merged["TZONE1@EDUC.B.CSI"].name == "TZONE1@EDUC.B.CSI"


def test_merge_zones_no_collision_when_csi_unknown():
    # A zone with no csi (e.g. from a file predating the ##CSI sentinel)
    # merging with a later, csi-stamped same-named zone is still treated
    # as the same zone, not a collision.
    zone_a = {"TZONE1": Zone(name="TZONE1")}
    zone_b = {"TZONE1": Zone(name="TZONE1", csi="EDUC.B.CSI")}
    merged = smpe_parser.merge_zones(zone_a, zone_b)
    assert set(merged) == {"TZONE1"}
    assert merged["TZONE1"].csi == "EDUC.B.CSI"


def test_parse_globalzone_reads_zoneindex():
    entries = smpe_parser.parse_globalzone(FIXTURES / "sample_smpe_globalzone.txt")
    assert len(entries) == 2

    tzone1, dzone1 = entries
    assert tzone1.zone_name == "TZONE1"
    assert tzone1.zone_type == "TARGET"
    assert tzone1.csi == "EDUC.TEST.GLOBAL.CSI"
    assert tzone1.source_csi == "EDUC.TEST.GLOBAL.CSI"

    assert dzone1.zone_name == "DZONE1"
    assert dzone1.zone_type == "DLIB"
    # This zone's own CSI differs from the file's ##CSI (source_csi) --
    # a real, documented SMP/E pattern where target/dlib zones live in
    # separate physical CSI data sets cross-referenced from one GLOBAL
    # zone's ZONEINDEX.
    assert dzone1.csi == "EDUC.TEST.DLIB.CSI"
    assert dzone1.source_csi == "EDUC.TEST.GLOBAL.CSI"
