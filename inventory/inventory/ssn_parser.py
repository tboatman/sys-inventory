"""Parse IEFSSNxx (subsystem definitions) and COMMNDxx (auto-start
commands) PARMLIB member dumps, produced by the *same*
zos-extract/python/extrproc.py used for PROCLIB, into Subsystem/StartedTask
objects.

Reuses jcl_parser.split_members()/join_continuations() for the sentinel
splitting and comma-continuation joining -- IEFSSNxx and COMMNDxx are
PARMLIB free-form text with the same "##MEMBER name" dump format and the
same comma-continuation convention as JCL, so there's no reason to
reimplement either. Like jcl_parser, non-matching lines are silently
skipped rather than reported as errors.
"""
from __future__ import annotations

import re
from pathlib import Path

from .jcl_parser import join_continuations, split_members
from .models import StartedTask, Subsystem

_SUBSYS = re.compile(
    r"SUBSYS\s+SUBNAME\s*\(\s*(?P<name>[A-Za-z0-9$#@]+)\s*\)"
    r"(?:.*?INITRTN\s*\(\s*(?P<initrtn>[A-Za-z0-9$#@]+)\s*\))?"
    r"(?:.*?INITPARM\s*\(\s*'(?P<initparm>[^']*)'\s*\))?",
    re.IGNORECASE | re.DOTALL,
)
_COM_START = re.compile(
    r"COM\s*=\s*'S\s+(?P<taskname>[A-Za-z0-9$#@]+)"
    r"(?:\.(?P<identifier>[A-Za-z0-9$#@]+))?",
    re.IGNORECASE,
)


def parse_subsystems(path: Path) -> list[Subsystem]:
    """Parse one IEFSSNxx dump (as produced by extrproc.py) into Subsystem rows."""
    text = path.read_text(errors="replace")
    subsystems: list[Subsystem] = []
    for member_name, raw_lines in split_members(text).items():
        for line in join_continuations(raw_lines):
            m = _SUBSYS.search(line)
            if not m:
                continue
            subsystems.append(
                Subsystem(
                    name=m.group("name"),
                    initrtn=m.group("initrtn"),
                    initparm=m.group("initparm"),
                    source_member=member_name,
                )
            )
    return subsystems


def parse_started_tasks(path: Path) -> list[StartedTask]:
    """Parse one COMMNDxx dump (as produced by extrproc.py) into StartedTask rows."""
    text = path.read_text(errors="replace")
    tasks: list[StartedTask] = []
    for member_name, raw_lines in split_members(text).items():
        for line in join_continuations(raw_lines):
            m = _COM_START.search(line)
            if not m:
                continue
            tasks.append(
                StartedTask(
                    task_name=m.group("taskname"),
                    identifier=m.group("identifier"),
                    source_member=member_name,
                )
            )
    return tasks
