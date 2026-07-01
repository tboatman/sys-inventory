from pathlib import Path

from inventory import jcl_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_members():
    return {m.name: m for m in jcl_parser.parse_dump(FIXTURES / "sample_proclib.txt", library="proclib")}


def test_split_members_finds_all_members():
    members = load_members()
    assert set(members) == {"MYPROC", "NESTPROC", "LNKPROC", "JOBPROC", "MISSPROC"}


def test_pgm_and_steplib_parsed():
    members = load_members()
    step = members["MYPROC"].steps[0]
    assert step.step_name == "STEP1"
    assert step.pgm == "IEFBR14"
    assert step.steplib == "MY.SITE.LINKLIB"


def test_nested_proc_reference_parsed():
    members = load_members()
    step = members["MYPROC"].steps[1]
    assert step.pgm is None
    assert step.proc == "NESTPROC"


def test_joblib_parsed():
    members = load_members()
    step = members["JOBPROC"].steps[0]
    assert step.pgm == "SAMPMOD"
    assert step.joblib == "MY.SITE.LINKLIB"


def test_inline_nested_procs_flattens_chain():
    members = load_members()
    flat = jcl_parser.inline_nested_procs(members["MYPROC"], members)
    pgms = [s.pgm for s in flat]
    assert pgms == ["IEFBR14", "IGYCRCTL"]


def test_inline_unresolved_proc_passes_through():
    members = load_members()
    flat = jcl_parser.inline_nested_procs(members["MISSPROC"], members)
    assert len(flat) == 1
    assert flat[0].proc == "NOTFOUND"
    assert flat[0].pgm is None
