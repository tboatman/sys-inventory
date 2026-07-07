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


def test_lmod_fmid_parsed_when_real_load_module_name_differs_from_element():
    zones = load_zones()
    # SAMPMOD's real load-module name (LMOD=) is SAMPMD1, distinct from the
    # element name -- module_fmid stays keyed by element name, lmod_fmid is
    # the new lookup keyed by the real load-module name JCL PGM= actually
    # names (see doc/TODO.md "8e").
    assert zones["TZONE2"].lmod_fmid == {"SAMPMD1": "USER001"}
    # TZONE1's entries have no LMOD= line at all -- lmod_fmid stays empty,
    # not populated with a guessed element-name fallback.
    assert zones["TZONE1"].lmod_fmid == {}


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


def test_mod_section_title_says_module_not_mod():
    # Regression test for a real LIST MOD report (MVST target zone,
    # MVS.GLOBAL.CSI): the SMPCNTL command is "LIST MOD .", but GIMSMP
    # prints the section title as "<zone>    MODULE   ENTRIES" -- not
    # "MOD ENTRIES". _SECTION_HDR originally only recognized the literal
    # "MOD" alternative, so this title line never matched at all, leaving
    # current_zone/section unset (module_fmid/lmod_fmid entirely empty)
    # unless a preceding LIST DDDEF section in the same file happened to
    # have already set current_zone.
    zones = smpe_parser.parse_smplist(FIXTURES / "sample_smpe_mod_real.txt")
    assert zones["MVST"].module_fmid == {
        "ACBFUTO2": "HDZ3310",
        "ACBFUTO3": "HDZ3310",
        "ACBFUTO4": "HDZ3310",
    }
    assert zones["MVST"].lmod_fmid == {
        "ACBFUTO2": "HDZ3310",
        "ACBFUTO3": "HDZ3310",
        "ACBFUTO4": "HDZ3310",
    }


def test_mod_entry_survives_page_break_between_lastupd_and_fmid():
    # Regression test for a real ~15M-line LIST DDDEF/MOD/SYSMOD report
    # (MVST target zone, MVS.GLOBAL.CSI): SMP/E reprints the
    # "<zone>  <TYPE> ENTRIES" section title at the top of EVERY page, not
    # just once per section. A LIST MOD element's LASTUPD/FMID/LMOD lines
    # can straddle a page break, and the parser used to treat every
    # _SECTION_HDR match as a fresh section start, wiping pending_modname/
    # pending_fmid and silently dropping that element's FMID/LMOD tie.
    zones = smpe_parser.parse_smplist(FIXTURES / "sample_smpe_mod_page_break.txt")
    assert zones["MVST"].module_fmid == {"ADMAET0A": "JGD3219"}
    assert zones["MVST"].lmod_fmid == {"ADMAET0A": "JGD3219"}


def test_sysmod_entry_parsed_from_real_report_with_page_break():
    # Confirms LIST SYSMOD against a real entry (HBB77E0, MVST target zone,
    # MVS.GLOBAL.CSI): TYPE=FUNCTION/STATUS=REC APP resolve correctly, the
    # LASTUPD line's embedded "TYPE=UPD" doesn't false-positive as a new
    # SYSMOD header, and a page break landing mid-entry (inside the
    # DELETE VER(001) list) doesn't disturb the already-captured status --
    # see also test_mod_entry_survives_page_break_between_lastupd_and_fmid
    # for the analogous LIST MOD fix this same page-break behavior needed.
    zones = smpe_parser.parse_smplist(FIXTURES / "sample_smpe_sysmod_real.txt")
    assert zones["MVST"].fmid_status == {"HBB77E0": "REC/APP"}


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


def test_parse_globalzone_handles_unprefixed_zoneindex_line():
    # Regression test for a real LIST GLOBALZONE report (MVS.GLOBAL.CSI):
    # ZONEINDEX wasn't the first attribute printed (UPGLEVEL was), so its
    # line carried no leading entry-name token at all -- just indented
    # "ZONEINDEX       = ..." with nothing before it. The original regex
    # required that token and silently matched zero entries against this
    # real shape.
    entries = smpe_parser.parse_globalzone(FIXTURES / "sample_smpe_globalzone_real.txt")
    assert len(entries) == 4

    by_name = {e.zone_name: e for e in entries}
    assert by_name["MVST"].zone_type == "TARGET"
    assert by_name["MVST"].csi == "MVS.MVST.CSI"
    assert by_name["MVSD"].zone_type == "DLIB"
    assert by_name["MVSD"].csi == "MVS.MVSD.CSI"
    # A zone whose entries live in a completely different product's CSI
    # than the GLOBAL zone that cross-references it -- a real, documented
    # SMP/E pattern, not a fixture artifact.
    assert by_name["CSQ920T"].csi == "CSQ920.CSQ920T.CSI"
    assert all(e.source_csi == "MVS.GLOBAL.CSI" for e in entries)
