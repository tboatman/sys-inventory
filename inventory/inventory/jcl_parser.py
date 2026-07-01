"""Parse PROCLIB/PARMLIB dumps produced by zos-extract/python/extrproc.py
into ProcMember/JclStep objects, and inline nested PROC
calls into a single flat execution path per top-level member.

Dump format: a stream of lines where each member is introduced by a
sentinel header line ``##MEMBER name`` followed by that member's raw text,
unchanged, up to the next sentinel (or end of file).
"""
from __future__ import annotations

import re
from pathlib import Path

from .models import JclStep, ProcMember

_MEMBER_HEADER = re.compile(r"^##MEMBER\s+(\S+)\s*$")
_EXEC_PGM = re.compile(r"EXEC\s+(?:.*?,)?PGM=([A-Za-z0-9$#@]+)", re.IGNORECASE)
_EXEC_PROC = re.compile(
    r"EXEC\s+(?:PROC=)?([A-Za-z0-9$#@]+)(?=[\s,]|$)", re.IGNORECASE
)
_DD_DSN = re.compile(r"\bDSN=([A-Za-z0-9$#@.()]+)", re.IGNORECASE)
_STEP_NAME = re.compile(r"^//(\S+)\s+EXEC\b", re.IGNORECASE)
_DD_NAME = re.compile(r"^//(\S+)\s+DD\b", re.IGNORECASE)


def split_members(text: str) -> dict[str, list[str]]:
    """Split a raw dump file into {member_name: [raw lines]}."""
    members: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _MEMBER_HEADER.match(line)
        if m:
            current = m.group(1)
            members[current] = []
            continue
        if current is not None:
            members[current].append(line)
    return members


def _join_continuations(lines: list[str]) -> list[str]:
    """Join JCL continuation records (a statement ending in ',') into one
    logical line so the regexes above don't have to deal with line breaks
    inside an operand list."""
    joined: list[str] = []
    buf = ""
    continuing = False
    for line in lines:
        stripped = line.rstrip()
        if stripped.startswith("//*"):
            joined.append(stripped)  # comments never continue
            continue
        if continuing:
            content = stripped[2:].lstrip() if stripped.startswith("//") else stripped.lstrip()
            buf += " " + content
        else:
            buf = stripped
        if buf.endswith(","):
            continuing = True
            continue
        continuing = False
        joined.append(buf)
        buf = ""
    if buf:
        joined.append(buf)
    return joined


def parse_member(name: str, library: str, raw_lines: list[str]) -> ProcMember:
    member = ProcMember(name=name, library=library, raw_text=list(raw_lines))
    logical_lines = _join_continuations(raw_lines)

    steps: list[JclStep] = []
    current_step: JclStep | None = None

    for line in logical_lines:
        if not line.startswith("//") or line.startswith("//*"):
            continue

        exec_match = _STEP_NAME.match(line)
        if exec_match:
            step_name = exec_match.group(1)
            current_step = JclStep(step_name=step_name, source_member=name)
            pgm_match = _EXEC_PGM.search(line)
            if pgm_match:
                current_step.pgm = pgm_match.group(1)
            else:
                proc_match = _EXEC_PROC.search(line)
                if proc_match:
                    current_step.proc = proc_match.group(1)
            steps.append(current_step)
            continue

        dd_match = _DD_NAME.match(line)
        if dd_match and current_step is not None:
            ddname = dd_match.group(1).upper()
            if ddname in ("STEPLIB", "JOBLIB"):
                dsn_match = _DD_DSN.search(line)
                if dsn_match:
                    dsn = dsn_match.group(1)
                    if ddname == "STEPLIB":
                        current_step.steplib = dsn
                    else:
                        current_step.joblib = dsn

    member.steps = steps
    return member


def parse_dump(path: Path, library: str | None = None) -> list[ProcMember]:
    """Parse one EXTRPROC/EXTRPARM dump file into a list of ProcMember."""
    library = library or path.stem
    text = path.read_text(errors="replace")
    members = []
    for name, raw_lines in split_members(text).items():
        members.append(parse_member(name, library, raw_lines))
    return members


def inline_nested_procs(
    member: ProcMember, all_members: dict[str, ProcMember], _seen: frozenset[str] = frozenset()
) -> list[JclStep]:
    """Return the flattened execution path for `member`: every EXEC PROC=
    step that resolves to a known member is replaced by that member's own
    (recursively flattened) steps. Unresolved PROC references and direct
    PGM= steps pass through unchanged.

    `_seen` guards against circular PROC references (A calls B calls A).
    """
    if member.name in _seen:
        return []  # cycle guard: stop recursing, leave the caller's step as-is

    flattened: list[JclStep] = []
    for step in member.steps:
        if step.pgm:
            flattened.append(step)
        elif step.proc and step.proc in all_members:
            nested = all_members[step.proc]
            flattened.extend(
                inline_nested_procs(nested, all_members, _seen | {member.name})
            )
        else:
            # unresolved PROC reference (not in any ingested concatenation)
            flattened.append(step)
    return flattened
