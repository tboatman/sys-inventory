from pathlib import Path

from inventory import ssn_parser

FIXTURES = Path(__file__).parent / "fixtures"


def load_subsystems():
    return ssn_parser.parse_subsystems(FIXTURES / "sample_ssn.txt")


def load_started_tasks():
    return ssn_parser.parse_started_tasks(FIXTURES / "sample_commnd.txt")


def test_subsystems_parsed():
    subsystems = load_subsystems()
    jes2 = next(s for s in subsystems if s.name == "JES2")
    assert jes2.initrtn == "HASJES20"
    assert jes2.initparm == "SUB=YES"
    assert jes2.source_member == "IEFSSN00"


def test_subsystem_without_initparm_parsed():
    subsystems = load_subsystems()
    db2p = next(s for s in subsystems if s.name == "DB2P")
    assert db2p.initrtn == "DSN3INI"
    assert db2p.initparm is None


def test_started_tasks_parsed():
    tasks = load_started_tasks()
    cics = next(t for t in tasks if t.task_name == "CICSPROD")
    assert cics.identifier == "CICSA"
    assert cics.source_member == "COMMND00"


def test_started_task_without_identifier_parsed():
    tasks = load_started_tasks()
    vtam = next(t for t in tasks if t.task_name == "VTAM")
    assert vtam.identifier is None


def test_non_start_commnd_line_skipped():
    tasks = load_started_tasks()
    names = [t.task_name for t in tasks]
    assert "SETPROG" not in names
    assert len(tasks) == 2
