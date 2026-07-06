from pathlib import Path

from inventory import jcl_parser, smpe_parser
from inventory.models import JclStep, ProcMember, Zone
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
    assert direct_steplib_hop.csi == "EDUC.TEST.GLOBAL.CSI"

    nested_hop = chain[1]
    assert nested_hop.pgm == "IGYCRCTL"
    assert nested_hop.dataset == "SYS1.LINKLIB"
    assert nested_hop.zone == "TZONE1"
    assert nested_hop.fmid == "HLA2280"
    assert "APPLIED" in nested_hop.resolution
    assert nested_hop.apf_authorized is False
    assert nested_hop.csi == "EDUC.TEST.GLOBAL.CSI"


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


def test_duplicate_member_name_resolves_to_lowest_numbered_library():
    """Per doc/zos-extract.md's NN-prefix convention, when the same member
    name is ingested from more than one PROCLIB/PARMLIB library, the one
    from the lowest-numbered (searched-first) library must win -- not
    whichever instance happens to be last in the input list."""
    first = ProcMember(
        name="MYPROC",
        library="00_proclib",
        steps=[JclStep(step_name="STEP1", pgm="FIRSTPGM")],
    )
    second = ProcMember(
        name="MYPROC",
        library="01_proclib",
        steps=[JclStep(step_name="STEP1", pgm="SECONDPGM")],
    )

    # Order in the input list must not matter -- feed it backwards (as a
    # naive last-write-wins dict comprehension would receive it if cli.py's
    # glob ever returned libraries out of order) and confirm the
    # lower-numbered library still wins.
    lineage = resolve_all([second, first], zones={}, lnklst=[])

    assert list(lineage.keys()) == ["MYPROC"]
    assert lineage["MYPROC"][0].pgm == "FIRSTPGM"


def test_pgm_resolves_via_lmod_fmid_when_it_differs_from_element_name():
    """Per doc/TODO.md's '8e', a JCL PGM= names the real load-module name,
    which can differ from the SMP/E element name module_fmid is keyed by
    -- lmod_fmid must be checked first."""
    zone = Zone(
        name="TZONE1",
        dddefs={"STEPLIB": "MY.LOADLIB"},
        module_fmid={"SAMPMOD": "USER001"},   # keyed by element name
        lmod_fmid={"SAMPMD1": "USER001"},      # keyed by real load-module name
    )
    member = ProcMember(
        name="LMODPROC",
        library="00_proclib",
        steps=[JclStep(step_name="STEP1", pgm="SAMPMD1", steplib="MY.LOADLIB")],
    )

    lineage = resolve_all([member], zones={"TZONE1": zone}, lnklst=[])

    assert lineage["LMODPROC"][0].fmid == "USER001"


def test_pgm_falls_back_to_module_fmid_when_no_lmod_entry():
    """Zones ingested before LMOD= was captured (or an element with no
    LMOD= line at all) still resolve via the element-name-keyed
    module_fmid, unchanged."""
    zone = Zone(
        name="TZONE1",
        dddefs={"STEPLIB": "MY.LOADLIB"},
        module_fmid={"SAMPMOD": "USER001"},
    )
    member = ProcMember(
        name="LMODPROC",
        library="00_proclib",
        steps=[JclStep(step_name="STEP1", pgm="SAMPMOD", steplib="MY.LOADLIB")],
    )

    lineage = resolve_all([member], zones={"TZONE1": zone}, lnklst=[])

    assert lineage["LMODPROC"][0].fmid == "USER001"
