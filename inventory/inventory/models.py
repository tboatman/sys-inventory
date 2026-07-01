"""Data model shared by the JCL parser, SMP/E parser, and resolver.

A lineage chain runs:

    ProcMember -> JclStep -> (PGM name) -> Dataset -> Zone -> Fmid

Nested PROC steps are inlined into the owning ProcMember's step list by the
resolver, so by the time a chain is built, every JclStep is either a PGM
invocation or an unresolved PROC reference (one that wasn't found in any
ingested concatenation).
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JclStep:
    """One EXEC statement within a ProcMember."""

    step_name: str
    pgm: str | None = None          # set for EXEC PGM=
    proc: str | None = None         # set for EXEC PROCNAME or EXEC PROC=PROCNAME
    steplib: str | None = None      # DSN from STEPLIB DD, if present
    joblib: str | None = None       # DSN from JOBLIB DD, if present
    source_member: str = ""         # ProcMember.name this step came from
                                     # (differs from the top-level member once
                                     # nested PROC steps are inlined)


@dataclass
class ProcMember:
    """One PROCLIB or PARMLIB member, as dumped by EXTRPROC/EXTRPARM."""

    name: str
    library: str             # concatenation entry name/prefix it came from
    raw_text: list[str] = field(default_factory=list)
    steps: list[JclStep] = field(default_factory=list)


@dataclass
class Dataset:
    """A load library dataset, as referenced by STEPLIB/JOBLIB or LNKLST."""

    dsn: str
    zone: str | None = None  # SMP/E target zone that owns it, via DDDEF match


@dataclass
class Zone:
    """One SMP/E target (or global) zone, parsed from LIST ZONES/DDDEF."""

    name: str
    dddefs: dict[str, str] = field(default_factory=dict)   # ddname -> DSN
    # module name -> owning FMID, derived from LIST FILE / LIST SYSMOD
    module_fmid: dict[str, str] = field(default_factory=dict)
    # FMID -> status (e.g. APPLIED, ACCEPTED), derived from LIST SYSMOD
    fmid_status: dict[str, str] = field(default_factory=dict)


@dataclass
class Fmid:
    """An SMP/E function (FMID), as it appears in a zone's SYSMOD list."""

    fmid: str
    zone: str
    status: str = ""   # e.g. APPLIED, ACCEPTED


@dataclass
class LineageStep:
    """One resolved hop in a ProcMember's execution path, for reporting."""

    member: str
    step_name: str
    pgm: str
    dataset: str | None
    zone: str | None
    fmid: str | None
    resolution: str   # human-readable note on how the dataset was found,
                       # or why resolution failed at this hop
    apf_authorized: bool | None = None   # True/False if apf.txt was ingested
                                          # and `dataset` was/wasn't in it;
                                          # None if apf.txt wasn't ingested or
                                          # `dataset` is None


@dataclass
class Subsystem:
    """One SUBSYS() definition from an IEFSSNxx PARMLIB member."""

    name: str
    initrtn: str | None = None
    initparm: str | None = None
    source_member: str = ""   # IEFSSNxx member name it came from, e.g. "IEFSSN00"


@dataclass
class StartedTask:
    """One 'S taskname[.identifier]' auto-start command from a COMMNDxx
    PARMLIB member."""

    task_name: str
    identifier: str | None = None
    source_member: str = ""   # COMMNDxx member name it came from, e.g. "COMMND00"


@dataclass
class SystemInfo:
    """Single-record system/LPAR identity, as dumped by
    zos-extract/python/extrsys.py ('D SYMBOLS' + 'D IPLINFO'). Exists so a
    future multi-system merge can tag each ingested inventory with the
    system it came from."""

    sysname: str | None = None          # LPAR name (&SYSNAME.)
    sysclone: str | None = None         # SYSCLONE symbol
    sysplex: str | None = None          # sysplex name (&SYSPLEX.)
    ipl_volume: str | None = None       # SYSRES IPL volume
    ipl_parm_member: str | None = None  # IEASYSxx/IPL parm member suffix
