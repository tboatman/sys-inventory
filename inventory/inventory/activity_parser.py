"""Parse the active_jobs.txt / processes.txt dumps produced by
ansible/roles/zos_extract/tasks/activity.yml (jls directly) and
extrprocs.py -- the "what's actually running right now" live snapshot,
as opposed to the rest of this pipeline's PROCLIB/PARMLIB-sourced
configuration/definition data (e.g. Subsystem/StartedTask, which say
what's *defined*, not what's running).

active_jobs.txt is JSON Lines (one jls job object per line, using jls's
own field names) -- not real-world console/report output, but not this
project's own invented format either, so it's still worth being
tolerant of a field jls didn't return for a given job (defaults to
None) the same way sysinfo_parser.py/smpe_parser.py are tolerant of
missing fields. processes.txt (extrprocs.py) is still a simple
self-controlled one-command-per-line format.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import ActiveJob, UssProcess


def parse_active_jobs(path: Path) -> list[ActiveJob]:
    """Parse one activity.yml dump: one JSON job object per line, as
    returned by jls -o owner,name,id,status,ccode,jobclass,serviceclass,
    priority,asid,creationdate,creationtime,queueposition,jobtype,
    executiontime,executionseconds,system,subsystem,onode,xnode,membname,
    already filtered to status == "AC"."""
    jobs: list[ActiveJob] = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        job = json.loads(line)
        jobs.append(
            ActiveJob(
                job_id=job.get("id", ""),
                name=job.get("name", ""),
                job_type=job.get("jobtype"),
                asid=job.get("asid"),
                owner=job.get("owner"),
                status=job.get("status"),
                completion_code=job.get("ccode"),
                job_class=job.get("jobclass"),
                svc_class=job.get("serviceclass"),
                priority=job.get("priority"),
                creation_date=job.get("creationdate"),
                creation_time=job.get("creationtime"),
                queue_position=job.get("queueposition"),
                execution_time=job.get("executiontime"),
                execution_seconds=job.get("executionseconds"),
                system=job.get("system"),
                subsystem=job.get("subsystem"),
                onode=job.get("onode"),
                xnode=job.get("xnode"),
                membname=job.get("membname"),
            )
        )
    return jobs


def parse_processes(path: Path) -> list[UssProcess]:
    """Parse one extrprocs.py dump: one process command per line."""
    return [
        UssProcess(command=line.strip())
        for line in path.read_text(errors="replace").splitlines()
        if line.strip()
    ]
