"""Parse the active_jobs.txt / processes.txt dumps produced by
zos-extract/python/extrjobs.py and extrprocs.py -- the "what's actually
running right now" live snapshot, as opposed to the rest of this
pipeline's PROCLIB/PARMLIB-sourced configuration/definition data (e.g.
Subsystem/StartedTask, which say what's *defined*, not what's running).

Both dumps are simple, self-controlled formats -- this project's own
extract scripts write them in a format this parser dictates, not
real-world console/report output -- so unlike smpe_parser.py/
sysinfo_parser.py there's no "tune against your real system" caveat
needed here.
"""
from __future__ import annotations

from pathlib import Path

from .models import ActiveJob, UssProcess


def parse_active_jobs(path: Path) -> list[ActiveJob]:
    """Parse one extrjobs.py dump: one 'job_id name job_type asid' row per
    currently-active job/started task."""
    jobs: list[ActiveJob] = []
    for line in path.read_text(errors="replace").splitlines():
        fields = line.split()
        if not fields:
            continue
        job_id = fields[0]
        name = fields[1] if len(fields) > 1 else ""
        job_type = fields[2] if len(fields) > 2 else None
        asid = fields[3] if len(fields) > 3 else None
        jobs.append(ActiveJob(job_id=job_id, name=name, job_type=job_type, asid=asid))
    return jobs


def parse_processes(path: Path) -> list[UssProcess]:
    """Parse one extrprocs.py dump: one process command per line."""
    return [
        UssProcess(command=line.strip())
        for line in path.read_text(errors="replace").splitlines()
        if line.strip()
    ]
