from pathlib import Path

from inventory import activity_parser

FIXTURES = Path(__file__).parent / "fixtures"


def test_active_jobs_parsed():
    jobs = activity_parser.parse_active_jobs(FIXTURES / "sample_active_jobs.txt")
    assert len(jobs) == 3

    cics = next(j for j in jobs if j.name == "CICSPROD")
    assert cics.job_id == "STC03801"
    assert cics.job_type == "STC"
    assert cics.asid == "0043"
    assert cics.owner == "CICSUSR"
    assert cics.status == "AC"
    assert cics.job_class == "STC"
    assert cics.svc_class == "SYSSTC"
    assert cics.system == "BES2"
    assert cics.membname == "CICS"

    payroll = next(j for j in jobs if j.name == "PAYROLL")
    assert payroll.job_id == "JOB01234"
    assert payroll.job_type == "JOB"
    assert payroll.asid == "0091"
    assert payroll.job_class == "A"
    # Deliberately absent from the fixture, to prove tolerant partial matching.
    assert payroll.onode is None
    assert payroll.xnode is None
    assert payroll.membname is None


def test_processes_parsed():
    procs = activity_parser.parse_processes(FIXTURES / "sample_processes.txt")
    assert len(procs) == 3
    commands = [p.command for p in procs]
    assert "python3" in commands
    assert "/usr/sbin/sshd" in commands
