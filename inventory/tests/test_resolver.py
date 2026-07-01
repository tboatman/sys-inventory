from pathlib import Path

from inventory import jcl_parser, smpe_parser
from inventory.resolver import resolve_all

FIXTURES = Path(__file__).parent / "fixtures"


def load_all():
    members = jcl_parser.parse_dump(FIXTURES / "sample_proclib.txt", library="proclib")
    zones = smpe_parser.parse_smplist(FIXTURES / "sample_smpe_list.txt")
    lnklst = [
        line.strip()
        for line in (FIXTURES / "sample_lnklst.txt").read_text().splitlines()
        if line.strip()
    ]
    apf = {
        line.strip()
        for line in (FIXTURES / "sample_apf.txt").read_text().splitlines()
        if line.strip()
    }
    return resolve_all(members, zones, lnklst, apf)


def test_full_chain_member_to_fmid_via_steplib_and_nested_proc():
    lineage = load_all()
    chain = lineage["MYPROC"]
    assert len(chain) == 2

    direct_steplib_hop = chain[0]
    assert direct_steplib_hop.pgm == "IEFBR14"
    assert direct_steplib_hop.dataset == "MY.SITE.LINKLIB"
    assert direct_steplib_hop.zone == "TZONE2"
    assert direct_steplib_hop.fmid is None  # IEFBR14 isn't in TZONE2's FILE list
    assert direct_steplib_hop.apf_authorized is True

    nested_hop = chain[1]
    assert nested_hop.pgm == "IGYCRCTL"
    assert nested_hop.dataset == "SYS1.LINKLIB"
    assert nested_hop.zone == "TZONE1"
    assert nested_hop.fmid == "HLA2280"
    assert "APPLIED" in nested_hop.resolution
    assert nested_hop.apf_authorized is False


def test_lnklst_fallback_resolution():
    lineage = load_all()
    chain = lineage["LNKPROC"]
    assert len(chain) == 1
    hop = chain[0]
    assert hop.pgm == "IEBGENER"
    assert hop.dataset == "SYS1.LINKLIB"
    assert hop.zone == "TZONE1"
    assert hop.fmid == "HBB7790"


def test_joblib_resolution():
    lineage = load_all()
    chain = lineage["JOBPROC"]
    hop = chain[0]
    assert hop.pgm == "SAMPMOD"
    assert hop.dataset == "MY.SITE.LINKLIB"
    assert hop.zone == "TZONE2"
    assert hop.fmid == "USER001"


def test_unresolved_proc_reference_reported():
    lineage = load_all()
    chain = lineage["MISSPROC"]
    assert len(chain) == 1
    hop = chain[0]
    assert hop.pgm == ""
    assert "unresolved PROC reference: NOTFOUND" in hop.resolution


def test_apf_authorized_none_when_apf_not_ingested():
    members = jcl_parser.parse_dump(FIXTURES / "sample_proclib.txt", library="proclib")
    zones = smpe_parser.parse_smplist(FIXTURES / "sample_smpe_list.txt")
    lnklst = [
        line.strip()
        for line in (FIXTURES / "sample_lnklst.txt").read_text().splitlines()
        if line.strip()
    ]
    lineage = resolve_all(members, zones, lnklst)
    for chain in lineage.values():
        for hop in chain:
            assert hop.apf_authorized is None
