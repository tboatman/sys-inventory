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
    csi: str = ""   # owning CSI dataset name, from an optional ##CSI sentinel
                     # line in the *smplist*.txt file (see smpe_parser.py);
                     # "" if the file predates that sentinel or omits it.
    dddefs: dict[str, str] = field(default_factory=dict)   # ddname -> DSN
    # element name -> owning FMID, derived from LIST MOD's LASTUPD/FMID lines
    module_fmid: dict[str, str] = field(default_factory=dict)
    # real load-module name -> owning FMID, derived from LIST MOD's own
    # LMOD= line. A SYSMOD can package an element under a load-module name
    # that differs from the element name in module_fmid above, and it's the
    # load-module name a JCL PGM= actually names -- see doc/TODO.md ("8e")
    # and resolver._fmid_for_module(), which checks this first and falls
    # back to module_fmid for compatibility with data captured before this
    # existed.
    lmod_fmid: dict[str, str] = field(default_factory=dict)
    # FMID -> status (e.g. APPLIED, ACCEPTED), derived from LIST SYSMOD
    fmid_status: dict[str, str] = field(default_factory=dict)


@dataclass
class Fmid:
    """An SMP/E function (FMID), as it appears in a zone's SYSMOD list."""

    fmid: str
    zone: str
    status: str = ""   # e.g. APPLIED, ACCEPTED


@dataclass
class ZoneIndexEntry:
    """One row of a CSI's global zone ZONEINDEX, as reported by GIMSMP
    LIST GLOBALZONE -- SMP/E's own authoritative list of every zone tied
    to that CSI (unlike discover_smpe_csis.yml's naming-heuristic CSI
    search, this is a real SMP/E-reported fact, not a guess). See
    smpe_parser.parse_globalzone() and doc/TODO.md ("8d")."""

    zone_name: str
    zone_type: str   # e.g. TARGET, DLIB, GLOBAL
    csi: str         # the CSI dataset this zone actually lives in, per
                      # ZONEINDEX -- can differ from source_csi below if a
                      # site splits target/dlib zones across separate
                      # physical CSI data sets cross-referenced from one
                      # GLOBAL zone (a real, documented SMP/E pattern)
    source_csi: str = ""   # which CSI's LIST GLOBALZONE this entry came
                            # from (i.e. the *.smpzones.txt file's ##CSI)


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
    csi: str | None = None   # owning CSI dataset name (Zone.csi), if `zone`
                              # resolved and that zone's file carried a
                              # ##CSI sentinel; None otherwise


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
class Jes2InitStatement:
    """One JES2 initialization statement, from JES2's own PARMLIB member
    (its init deck -- distinct from SYS1.PARMLIB's IEFSSNxx/COMMNDxx/
    IEASYSxx, and from the JES2 *PROCLIB* concatenation discover_proclib.yml
    already covers; see discover_jes2_parmlib.yml/jes2parm.yml).

    Captured generically (statement name + optional subscript + a raw
    keyword=value map) rather than modeled per statement type -- JES2's
    init-statement surface is large and stable, so this follows the same
    "capture everything generically" approach ActiveJob and
    discover_active_members.yml's KEYWORD=value pass both use, rather than
    hand-modeling a dataclass per JES2 statement.

    CONFIRMED against a real JES2 init deck on 2026-07-02. params can be
    empty for a statement whose only real parameters are documented but
    commented out in this particular member -- see jes2parm_parser.py's
    module docstring for the full detail."""

    stmt: str                                   # e.g. "MASDEF", "JOBCLASS"
    subscript: str | None = None                # e.g. "1" from "JOBCLASS(1)"
    params: dict[str, str] = field(default_factory=dict)
    source_member: str = ""   # JES2 parmlib member name it came from


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
    release: str | None = None          # z/OS release, e.g. "z/OS 02.05.00"
    archlvl: str | None = None          # architecture level, from D IPLINFO


@dataclass
class Product:
    """One PRODUCT enablement statement from an IFAPRDxx PARMLIB member --
    complements the SMP/E FMID data (which says what's installed/patched)
    with what's actually licensed/enabled for use."""

    id: str                       # product ID, e.g. "5650-ZOS"
    name: str | None = None
    version: str | None = None
    release: str | None = None
    mod: str | None = None
    featurename: str | None = None
    state: str | None = None      # ENABLED / DISABLED
    source_member: str = ""       # IFAPRDxx member name it came from, e.g. "IFAPRD00"


@dataclass
class ParmlibDataset:
    """One dataset in the live PARMLIB concatenation, as reported by 'D
    PARMLIB' (see ansible/roles/zos_extract/tasks/parmlib_snapshot.yml)
    and parsed by parmlib_parser.py -- explicit, always-captured
    counterpart to discover_parmlib.yml's own implicit 'D PARMLIB' call
    (issued only when zos_extract_parmlibs isn't already configured, and
    reduced in-place to a bare DSN list, never saved or ingested as its
    own dimension). `entry` is PARMLIB search order (lowest = searched
    first, "1"-based as MVS reports it -- distinct from this project's
    own "00"/"01"/... NN-prefix convention for zos_extract_parmlibs).

    Same confirmed 4-column ENTRY/FLAGS/VOLUME/DATA-SET reply shape
    LNKLST/APF use (see discover_parmlib.yml's own header comment) --
    not a fresh guess."""

    entry: str
    flags: str | None = None
    volume: str | None = None
    dsn: str = ""


@dataclass
class IeasysStatement:
    """One KEYWORD=value statement from an active IEASYSxx PARMLIB
    member -- the actual system parameters ("the parms") active at IPL,
    as opposed to ParmlibDataset above (which is just the PARMLIB
    dataset search order, all 'D PARMLIB' can report). Dumped by
    ansible/roles/zos_extract/tasks/ieasys_snapshot.yml (which reuses
    discover_active_members.yml's own active-member fetch, previously
    used only to pull out SSN=/CMD=/PROD=/MSTRJCL= internally and then
    discarded) and parsed by ieasys_parser.py.

    Generic capture, same rationale as Jes2InitStatement/VtamStartOption/
    CicsSitOverride: IEASYSxx's real keyword surface is large (100+
    documented keywords) and this project doesn't attempt to hand-model
    each one."""

    keyword: str
    value: str | None = None
    source_member: str = ""


@dataclass
class BpxprmStatement:
    """One statement from an active BPXPRMxx PARMLIB member -- z/OS UNIX
    System Services (OMVS) configuration, named by IEASYSxx's own OMVS=
    keyword (IeasysStatement above) the same way SSN=/CMD=/PROD=/MSTRJCL=
    name IEFSSNxx/COMMNDxx/IFAPRDxx/MSTJCLxx. Dumped by
    ansible/roles/zos_extract/tasks/bpxprm_snapshot.yml and parsed by
    bpxprm_parser.py.

    Unlike IeasysStatement's flat KEYWORD=value shape, a real BPXPRMxx
    member is statement-oriented -- STMT KEYWORD(value) KEYWORD2(value2)
    ..., continuing onto further physical lines with no continuation
    character until the next recognized top-level statement keyword
    starts (e.g. ROOT/MOUNT/FILESYSTYPE spanning several lines) -- the
    same shape this project already solved for PROFILE.TCPIP
    (TcpipProfileStatement/tcpip_parser.py), so this reuses that same
    "known keyword vocabulary, fold everything else into operands"
    approach rather than IeasysStatement's comma-split one.

    CONFIRMED against a real BPXPRMxx member, including a fully
    commented-out MOUNT block and multiple MOUNT statements in the same
    member (both kept, in order)."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class DevsupStatement:
    """One KEYWORD=value statement from an active DEVSUPxx PARMLIB
    member -- device support definitions, named by IEASYSxx's own
    DEVSUP= keyword (IeasysStatement above) the same way SSN=/CMD=/
    PROD=/OMVS=/MSTRJCL= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
    MSTJCLxx. Dumped by ansible/roles/zos_extract/tasks/
    devsup_snapshot.yml and parsed by devsup_parser.py. First of the
    Category B active-PARMLIB-member domains from doc/TODO.md "9.2" --
    same flat, comma-continued KEYWORD=value shape as IEASYSxx, so this
    reuses parmlib_engines.flat_keyword_engine() directly rather than
    hand-writing a third copy of that logic.

    CONFIRMED against a real DEVSUPxx member, including a bare
    KEYWORD(value) form with no '=' at all (e.g. DISABLE(SSR)) that
    parmlib_engines.split_params() now handles explicitly."""

    keyword: str
    value: str | None = None
    source_member: str = ""


@dataclass
class OptStatement:
    """One KEYWORD=value statement from an active IEAOPTxx PARMLIB
    member -- system tuning/options parameters, named by IEASYSxx's own
    OPT= keyword the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP= name
    IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx. Dumped by
    ansible/roles/zos_extract/tasks/opt_snapshot.yml and parsed by
    opt_parser.py. Second of the Category B active-PARMLIB-member
    domains from doc/TODO.md "9.2" -- same flat, comma-continued
    KEYWORD=value shape as IEASYSxx/DEVSUPxx, so this reuses
    parmlib_engines.flat_keyword_engine() directly.

    CONFIRMED against a real IEAOPTxx member (ERV=500)."""

    keyword: str
    value: str | None = None
    source_member: str = ""


@dataclass
class ClockStatement:
    """One bare "KEYWORD value" statement from an active CLOCKxx PARMLIB
    member -- TOD clock/timezone parameters, named by IEASYSxx's own
    CLOCK= keyword the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/
    OPT= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/
    IEAOPTxx. Dumped by ansible/roles/zos_extract/tasks/
    clock_snapshot.yml and parsed by clock_parser.py. Category G (not B)
    from doc/TODO.md "9.2" -- CONFIRMED against a real CLOCKxx member to
    be space-separated, one keyword per line, with no `=`, comma, or
    continuation character, unlike IEASYSxx/DEVSUPxx/IEAOPTxx -- so this
    has its own small parser instead of reusing
    parmlib_engines.flat_keyword_engine()."""

    keyword: str
    value: str | None = None
    source_member: str = ""


@dataclass
class AutorStatement:
    """One statement from an active AUTORxx PARMLIB member -- WTOR
    auto-reply policy (NOT Automatic Restart Management, despite the
    name's resemblance -- confirmed via IBM's z/OS MVS Initialization
    and Tuning Reference), named by IEASYSxx's own AUTOR= keyword the
    same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK= name
    IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/
    CLOCKxx. Dumped by ansible/roles/zos_extract/tasks/
    autor_snapshot.yml and parsed by autor_parser.py. First of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- unlike Category B's flat KEYWORD=value shape,
    a real AUTORxx member is statement-oriented (NOTIFYMSGS(...) and
    MSGID(msgid) DELAY(nnS) REPLY(text)/NOAUTORREPLY statements), the
    same shape BPXPRMxx has, so this reuses
    parmlib_engines.statement_engine() directly.

    CONFIRMED against a real AUTORxx member, including a multi-line
    '/* ... */' comment block preceding a live statement and a MSGID
    statement with its full operand list on one physical line."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class SchedStatement:
    """One PPT (Program Properties Table) statement from an active
    SCHEDxx PARMLIB member, named by IEASYSxx's own SCH= keyword the
    same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=
    name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/
    CLOCKxx/AUTORxx. Dumped by ansible/roles/zos_extract/tasks/
    sched_snapshot.yml and parsed by sched_parser.py. Second of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- a real SCHEDxx member is a repeated single
    statement shape, 'PPT PGMNAME(name) flag flag KEY(n) ...', so this
    reuses parmlib_engines.statement_engine() with a one-keyword
    vocabulary ({"PPT"}), capturing every flag/sub-parameter after
    PGMNAME generically as raw operand text rather than hand-modeling
    each PPT flag individually (the same generic-capture rationale
    CicsSitOverride/Jes2InitStatement use).

    CONFIRMED against a real SCHEDxx member, including a run of PPT
    entries where every physical line carries its own trailing
    '/* ... */' comment, stripped cleanly."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class CoupleStatement:
    """One statement from an active COUPLExx PARMLIB member -- XCF/
    sysplex couple dataset definitions (COUPLE and DATA TYPE(...)
    statements), named by IEASYSxx's own COUPLE= keyword the same way
    SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH= name
    IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/
    CLOCKxx/AUTORxx/SCHEDxx -- note the real member name keeps the
    trailing E (COUPLExx, e.g. COUPLE00), unlike MSTRJCL= (which drops
    its R to name MSTJCLxx). Dumped by ansible/roles/zos_extract/tasks/
    couple_snapshot.yml and parsed by couple_parser.py. Third of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- reuses parmlib_engines.statement_engine() with
    COUPLExx's own top-level keyword vocabulary (COUPLE, DATA),
    capturing every sub-parameter (SYSPLEX(...)/PCOUPLE(...)/
    ACOUPLE(...)/TYPE(...)/...) generically as raw operand text rather
    than hand-modeling each one individually.

    CONFIRMED against a real COUPLExx member, including one COUPLE
    statement followed by four distinct DATA TYPE(...) statements
    (CFRM, LOGR, BPXMCDS, WLM), all kept in order."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class GrsrnlStatement:
    """One RNLDEF statement from an active GRSRNLxx PARMLIB member --
    global resource serialization resource name lists, named by
    IEASYSxx's own GRSRNL= keyword the same way SSN=/CMD=/PROD=/OMVS=/
    MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE= name IEFSSNxx/
    COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
    AUTORxx/SCHEDxx/COUPLExx. Dumped by ansible/roles/zos_extract/tasks/
    grsrnl_snapshot.yml and parsed by grsrnl_parser.py. Fourth of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- a real GRSRNLxx member is a repeated single
    statement shape, 'RNLDEF RNL(EXCL|INCL|CON) TYPE(GENERIC|SPECIFIC|
    PATTERN) QNAME(...) RNAME(...)', so this reuses
    parmlib_engines.statement_engine() with a one-keyword vocabulary
    ({"RNLDEF"}), capturing every sub-parameter generically as raw
    operand text rather than hand-modeling RNL/TYPE/QNAME/RNAME
    individually -- the same generic-capture rationale
    SchedStatement/CoupleStatement use.

    CONFIRMED against a real (partial) GRSRNLxx member, including
    QNAME(...)/RNAME(...) each on their own continuation line rather
    than sharing the RNLDEF line."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class SmfStatement:
    """One statement from an active SMFPRMxx PARMLIB member -- System
    Management Facilities (SMF) recording configuration (ACTIVE/DSNAME/
    PROMPT/NOPROMPT/SYS/SUBSYS statements), named by IEASYSxx's own SMF=
    keyword the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/
    CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL= name IEFSSNxx/COMMNDxx/IFAPRDxx/
    BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/
    COUPLExx/GRSRNLxx -- note the real member name is SMFPRMxx, not
    "SMFxx" as doc/TODO.md's own table originally had it (corrected
    after checking a real IBM source, same class of naming error
    COUPLE= had). Dumped by ansible/roles/zos_extract/tasks/
    smf_snapshot.yml and parsed by smf_parser.py. Fifth of the Category
    C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- reuses parmlib_engines.statement_engine() with
    a statement vocabulary CONFIRMED against a real SMFPRMxx member
    (ACTIVE, DSNAME, PROMPT, NOPROMPT, SYS, SUBSYS, REC, MAXDORM,
    STATUS, JWT, SID, LISTDSN, INTVAL, SYNCVAL, AUTHSETSMF) -- the last
    nine were added after the real member exercised them (previously
    folded into the preceding statement's operands). SMFPRMxx's full
    documented keyword surface may still be larger than this list; an
    unrecognized top-level statement keyword still gets folded into the
    preceding statement's operands instead of starting its own, the same
    documented limitation every other statement_engine() consumer here
    carries."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class IosStatement:
    """One statement from an active IECIOSxx PARMLIB member -- I/O
    related parameters (MIH/HOTIO/TERMINAL/FICON/STORAGE/CAPTUCB/EKM/
    RECOVERY statements, plus CTRACE/MIDAW/HYPERPAV/HYPERWRITE/ZHPF
    specifications), named by IEASYSxx's own IOS= keyword the same way
    SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/
    COUPLE=/GRSRNL=/SMF= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
    MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/
    GRSRNLxx/SMFPRMxx. Dumped by ansible/roles/zos_extract/tasks/
    ios_snapshot.yml and parsed by ios_parser.py. Sixth of the Category
    C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- reuses parmlib_engines.statement_engine() with
    IECIOSxx's own top-level keyword vocabulary (MIH, HOTIO, TERMINAL,
    FICON, STORAGE, CAPTUCB, EKM, RECOVERY, CTRACE, MIDAW, HYPERPAV,
    HYPERWRITE, ZHPF), capturing every sub-parameter generically as raw
    operand text.

    NOT YET VALIDATED against a real IECIOSxx member -- the statement
    vocabulary is confirmed against IBM's z/OS MVS Initialization and
    Tuning Reference, but the parser itself hasn't been checked against
    a real member, same caveat smf_parser.py carries."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class ConsolStatement:
    """One statement from an active CONSOLxx PARMLIB member -- MCS/EMCS
    console definitions (INIT/DEFAULT/CONSOLE/HARDCOPY statements),
    named by IEASYSxx's own CON= keyword the same way SSN=/CMD=/PROD=/
    OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/
    IOS= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/
    IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/
    IECIOSxx. Dumped by ansible/roles/zos_extract/tasks/
    consol_snapshot.yml and parsed by consol_parser.py. Seventh of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- reuses parmlib_engines.statement_engine() with
    a statement vocabulary CONFIRMED against a real CONSOLxx member
    (INIT, DEFAULT, CONSOLE, HARDCOPY), capturing every sub-parameter
    (CMDDELIM(...)/DEVNUM(...)/AUTH(...)/NAME(...)/ROUTCODE(...)/...)
    generically as raw operand text rather than hand-modeling each one
    individually. CONSOLxx's full documented statement surface may still
    be larger (e.g. ALTGRP, CNGRP, MSCOPE, SPECIAL) -- an unrecognized
    top-level statement keyword gets folded into the preceding
    statement's operands instead of starting its own, the same
    documented limitation every other statement_engine() consumer here
    carries."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class IgdsmsStatement:
    """One SMS statement from an active IGDSMSxx PARMLIB member -- SMS
    (Storage Management Subsystem) base configuration (ACDS(...)/
    COMMDS(...)/INTERVAL(...)/SIZE(...)/... sub-parameters), named by
    IEASYSxx's own SMS= keyword the same way SSN=/CMD=/PROD=/OMVS=/
    MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/
    CON= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/
    IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/
    IECIOSxx/CONSOLxx. Dumped by ansible/roles/zos_extract/tasks/
    igdsms_snapshot.yml and parsed by igdsms_parser.py. Eighth of the
    Category C (statement-oriented) active-PARMLIB-member domains from
    doc/TODO.md "9.2" -- reuses parmlib_engines.statement_engine() with
    a one-keyword vocabulary ({"SMS"}), CONFIRMED against a real
    IGDSMSxx member, capturing every sub-parameter generically as raw
    operand text rather than hand-modeling each one individually.

    NAMING, deliberately distinct from SmsStorageGroup: this project
    already has an unrelated `SmsStorageGroup`/`sms_storage_groups`
    table for the *live* `D SMS,STORGRP` console command (see
    sms_parser.py) -- a completely different dimension (live
    storage-group status vs. this member's static base configuration).
    `IgdsmsStatement`/`igdsms_parser.py`/`igdsms_statements`/`inventory
    igdsms` all use the `igdsms` name instead of `sms` throughout,
    exactly to keep the two apart (doc/TODO.md "9.2")."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class IzuprmStatement:
    """One statement from an active IZUPRMxx PARMLIB member -- z/OSMF
    (z/OS Management Facility) configuration (HOSTNAME/JAVA_HOME/
    KEYRING_NAME/SEC_GROUPS/WLM_CLASSES/PLUGINS/... statements), named by
    IEASYSxx's own IZU= keyword the same way SSN=/CMD=/PROD=/OMVS=/
    MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/
    CON=/SMS= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
    DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/
    SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx. Dumped by
    ansible/roles/zos_extract/tasks/izuprm_snapshot.yml and parsed by
    izuprm_parser.py. Ninth of the Category C (statement-oriented)
    active-PARMLIB-member domains from doc/TODO.md "9.2" -- reuses
    parmlib_engines.statement_engine() with a statement vocabulary
    CONFIRMED against a real IZUPRM00 member (HOSTNAME, HTTP_SSL_PORT,
    INCIDENT_LOG, JAVA_HOME, KEYRING_NAME, LOGGING, RESTAPI_FILE,
    COMMON_TSO, SAF_PREFIX, CLOUD_SAF_PREFIX, CLOUD_SEC_ADMIN,
    SEC_GROUPS, SESSION_EXPIRE, TEMP_DIR, CSRF_SWITCH, SERVER_PROC,
    ANGEL_PROC, AUTOSTART, AUTOSTART_GROUP, USER_DIR, UNAUTH_USER,
    WLM_CLASSES, PLUGINS), capturing every sub-parameter generically as
    raw operand text rather than hand-modeling each one individually.
    IZUPRMxx's full documented statement surface is likely larger (this
    is one shop's real member, not IBM's full reference) -- an
    unrecognized top-level statement keyword still gets folded into the
    preceding statement's operands instead of starting its own, the
    same documented limitation every other statement_engine() consumer
    here carries."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class DiagStatement:
    """One statement from an active DIAGxx PARMLIB member -- diagnostic
    function defaults (common storage tracking, GETMAIN/FREEMAIN/storage
    trace), named by IEASYSxx's own DIAG= keyword the same way SSN=/
    CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/
    GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU= name IEFSSNxx/COMMNDxx/IFAPRDxx/
    BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/
    COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx.
    Dumped by ansible/roles/zos_extract/tasks/diag_snapshot.yml and
    parsed by diag_parser.py. Tenth of the Category C
    (statement-oriented) active-PARMLIB-member domains from doc/TODO.md
    "9.2" -- reuses parmlib_engines.statement_engine() with a
    one-keyword vocabulary ({"VSM"}), CONFIRMED against a real DIAG00
    member (`VSM TRACK CSA(ON) SQA(ON)`, `VSM TRACE GETFREE(OFF)`),
    capturing every sub-parameter generically as raw operand text.

    DIAGxx's real member content carries traditional MVS PARMLIB
    sequence numbers in columns 73-80 of every physical line (data
    columns 1-71/72, ignored by the system) -- diag_parser.py strips
    these before handing lines to statement_engine(), the first Category
    C domain here to need that preprocessing step (no earlier confirmed
    member happened to carry sequence numbers)."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class IggcatStatement:
    """One statement from an active IGGCATxx PARMLIB member -- catalog
    system parameters (GDGEXTENDED/VVDSSPACE/NOTIFYEXTENT/TASKMAX/...),
    named by IEASYSxx's own CATALOG= keyword the same way SSN=/CMD=/
    PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/
    SMF=/IOS=/CON=/SMS=/IZU=/DIAG= name IEFSSNxx/COMMNDxx/IFAPRDxx/
    BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/
    COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx/
    DIAGxx. Dumped by ansible/roles/zos_extract/tasks/iggcat_snapshot.yml
    and parsed by iggcat_parser.py.

    CONFIRMED against a real IGGCAT00 member -- and its real shape is
    neither of the two existing engines: unlike IEASYSxx/DEVSUPxx (Category
    B, comma-separated `KEYWORD=value`/`KEYWORD(value)` on one continued
    logical line) or AUTORxx/SCHEDxx/etc. (Category C, `STMT
    KEYWORD(value)...` blocks needing a per-domain statement vocabulary),
    a real IGGCATxx member is simply one independent `KEYWORD(value)` (or
    bare `KEYWORD`) entry per physical line, with no `=`, no commas
    joining entries, and no statement/sub-parameter grouping at all --
    closest to CLOCKxx's own "one bare pair per line" shape (Category G),
    but parenthesized rather than space-separated. iggcat_parser.py's own
    small tokenizer handles both bare keywords and `KEYWORD(value)` pairs
    generically rather than hand-listing IGGCATxx's full documented
    keyword set."""

    keyword: str
    value: str | None = None
    source_member: str = ""


@dataclass
class GrscnfStatement:
    """One statement from an active GRSCNFxx PARMLIB member -- Global
    Resource Serialization configuration parameters (GRSDEF's own
    GRSQ/RESMIL/TOLINT/ACCELSYS/RESTART/REJOIN/CTRACE sub-parameters),
    named by IEASYSxx's own GRSCNF= keyword the same way SSN=/CMD=/
    PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/
    GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU=/DIAG=/CATALOG= name IEFSSNxx/
    COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/
    AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/
    IGDSMSxx/IZUPRMxx/DIAGxx/IGGCATxx. Dumped by
    ansible/roles/zos_extract/tasks/grscnf_snapshot.yml and parsed by
    grscnf_parser.py.

    CONFIRMED against a real GRSCNFxx member -- like GRSRNLxx's own
    RNLDEF statement, a real member is a single repeated statement shape
    ('GRSDEF' followed by its sub-parameters on continuation lines with
    no continuation character), so this reuses
    parmlib_engines.statement_engine() with a one-keyword vocabulary
    ({"GRSDEF"}), capturing every sub-parameter generically as raw
    operand text rather than hand-modeling GRSQ/RESMIL/TOLINT/... each.
    The real confirming member exercised every non-GRSQ sub-parameter as
    a full-line `/* ... */` comment (documenting the site's own
    defaulted/removed settings) -- stripped cleanly by
    parmlib_engines.strip_comments() with no code change needed, leaving
    just `GRSDEF GRSQ(LOCAL)`."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class ProgStatement:
    """One statement from an active PROGxx PARMLIB member -- dynamic
    APF/LNKLST/LPA/EXIT/SCHED definitions, named by IEASYSxx's own PROG=
    keyword the same way SSN=/CMD=/PROD=/OMVS=/MSTRJCL=/DEVSUP=/OPT=/
    CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/CON=/SMS=/IZU=/DIAG=/
    CATALOG=/GRSCNF= name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/MSTJCLxx/
    DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/
    SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx/DIAGxx/IGGCATxx/
    GRSCNFxx. Dumped by ansible/roles/zos_extract/tasks/prog_snapshot.yml
    and parsed by prog_parser.py.

    CONFIRMED against a real PROGxx member -- this was flagged in
    doc/TODO.md as "the richest and riskiest" of the remaining
    active-PARMLIB domains (LNKLST/APF/EXIT/LPA/SCHED all being distinct
    sub-statement families inside one member), but the real member's own
    top-level statement vocabulary (`APF`, `LNKLST`, and -- per IBM's
    documented PROGxx syntax, though not exercised by this particular
    confirming member -- `EXIT`/`LPA`/`SCHED`) is a single first-word
    keyword per statement (`APF ADD`/`APF FORMAT(DYNAMIC)`/`LNKLST
    DEFINE`/`LNKLST ADD`/`LNKLST ACTIVATE`), with the action verb
    (`ADD`/`FORMAT`/`DEFINE`/`ACTIVATE`) and every sub-parameter folded
    into the same generic operand text `parmlib_engines.statement_engine()`
    already produces for every other Category C domain -- no per-family
    modeling or new engine turned out to be needed after all. Each `APF
    ADD`/`LNKLST ADD` entry (whether written on one physical line or
    continued onto further lines with no continuation character, and
    regardless of a trailing `/* ... */` comment on the same line as its
    own statement text) becomes its own row, since every entry restarts
    with the literal `APF`/`LNKLST` keyword. `EXIT`/`LPA`/`SCHED` are
    included in the recognized vocabulary on the strength of IBM's own
    PROGxx documentation, not because this confirming member exercised
    them -- if a real member ever uses one, it'll be captured the same
    generic way; until then they're unconfirmed, same "broaden if a
    future member exercises it" precedent every other generic-vocabulary
    Category C domain here follows."""

    stmt: str
    operands: str
    source_member: str = ""


@dataclass
class IeasvcStatement:
    """One SVCPARM definition from an active IEASVCxx PARMLIB member --
    user SVC (Supervisor Call) routine additions/replacements, named by
    IEASYSxx's own SVC= keyword the same way SSN=/CMD=/PROD=/OMVS=/
    MSTRJCL=/DEVSUP=/OPT=/CLOCK=/AUTOR=/SCH=/COUPLE=/GRSRNL=/SMF=/IOS=/
    CON=/SMS=/IZU=/DIAG=/CATALOG=/GRSCNF=/PROG= name IEFSSNxx/COMMNDxx/
    IFAPRDxx/BPXPRMxx/MSTJCLxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/
    SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/
    IZUPRMxx/DIAGxx/IGGCATxx/GRSCNFxx/PROGxx. Dumped by
    ansible/roles/zos_extract/tasks/ieasvc_snapshot.yml and parsed by
    ieasvc_parser.py. The Category D active-PARMLIB-member domain from
    doc/TODO.md "9.2" -- unlike JES2's own init deck (Jes2InitStatement),
    a SVCPARM statement's positional value right after the statement
    name is a bare SVC number (e.g. `SVCPARM 254,REPLACE,TYPE(1),
    APF(NO)`), not a parenthesized subscript like JES2's own
    `JOBCLASS(1)` -- captured as its own svc_number field instead of
    forced into a subscript-shaped slot, reusing
    jes2parm_parser.py's continuation-joiner and
    parmlib_engines.split_params() for the rest, per doc/TODO.md's own
    "reuse jes2parm_parser.py's engine as-is" plan for this domain.

    CONFIRMED syntax via a real IEASVCxx member's own documented example
    (`SVCPARM 254,REPLACE,TYPE(1),APF(NO)`, itself commented out in the
    member -- confirming the real syntax even though this particular
    line isn't a live definition) -- not yet validated against a live,
    uncommented SVCPARM statement from a real system."""

    stmt: str                                   # e.g. "SVCPARM"
    svc_number: str                              # e.g. "254"
    params: dict[str, str] = field(default_factory=dict)
    source_member: str = ""


@dataclass
class ActiveJob:
    """One currently-executing job/started task, as dumped by
    ansible/roles/zos_extract/tasks/activity.yml calling ZOAU's jls
    binary directly (one JSON object per line, filtered to status ==
    "AC") -- see that file for why this goes straight to jls rather
    than ibm.ibm_zos_core's zos_job_query. This is a live, point-in-time
    snapshot -- unlike Subsystem/StartedTask (what's *defined*), this is
    what's actually running right now.

    Field names mostly match jls's own -o field names (snake_cased);
    onode/xnode/membname are kept exactly as jls names them since their
    precise semantics (e.g. which of onode/xnode is the submitting vs.
    executing node) aren't independently confirmed."""

    job_id: str
    name: str
    job_type: str | None = None        # JOB / STC / TSU
    asid: str | None = None            # address space ID; only set while running
    owner: str | None = None
    status: str | None = None          # AC while running (CC/ABEND/JCLERR/... once finished)
    completion_code: str | None = None
    job_class: str | None = None
    svc_class: str | None = None
    priority: str | None = None
    creation_date: str | None = None
    creation_time: str | None = None
    queue_position: str | None = None
    execution_time: str | None = None
    execution_seconds: str | None = None
    system: str | None = None
    subsystem: str | None = None
    onode: str | None = None
    xnode: str | None = None
    membname: str | None = None


@dataclass
class UssProcess:
    """One currently-running USS process, as dumped by
    zos-extract/python/extrprocs.py via the z/OS UNIX `ps -ef` command."""

    command: str


@dataclass
class UssMount:
    """One mounted USS filesystem, as dumped by 'D OMVS,F' (see
    ansible/roles/zos_extract/tasks/uss_mounts.yml) and parsed by
    uss_mounts_parser.py.

    CONFIRMED against a real 'D OMVS,F' reply -- see
    uss_mounts_parser.py's module docstring for the real shape."""

    path: str
    name: str | None = None      # zFS/HFS dataset name (or device) backing the mount
    fs_type: str | None = None   # e.g. ZFS, HFS, TFS, NFS
    device: str | None = None
    status: str | None = None    # e.g. ACTIVE
    mode: str | None = None      # RDWR / READ / RDONLY
    mounted_date: str | None = None


@dataclass
class VtamMajorNode:
    """One VTAM major node, as dumped by 'D NET,MAJNODES' (see
    ansible/roles/zos_extract/tasks/vtam.yml) and parsed by
    vtam_parser.py.

    CONFIRMED against a real 'D NET,MAJNODES' reply -- see
    vtam_parser.py's module docstring for the confirmed shape."""

    name: str
    status: str | None = None   # e.g. ACTIV, ACT/S, INACT, PEND...


@dataclass
class VtamStartOption:
    """One VTAM start option KEYWORD=VALUE pair, as dumped by
    'D NET,VTAMOPTS' (see ansible/roles/zos_extract/tasks/vtam.yml) and
    parsed by vtam_parser.py.

    Captured generically (every keyword found, not a hand-modeled
    subset) the same way Jes2InitStatement captures JES2 init
    statements. APPN enablement/role is answered by querying this table
    for the NODETYPE/CPNAME keywords rather than a dedicated field.

    CONFIRMED against a real 'D NET,VTAMOPTS' reply -- see
    vtam_parser.py's module docstring for the confirmed shape and one
    minor, documented limitation (a couple of keywords have two-token
    values; only the first token is captured)."""

    keyword: str
    value: str


@dataclass
class VtamTopologySummary:
    """Single-record APPN topology database summary, from 'D NET,TOPO'
    (see ansible/roles/zos_extract/tasks/vtam.yml) and parsed by
    vtam_parser.py.

    CONFIRMED against a real 'D NET,TOPO' reply -- unlike
    VtamMajorNode/VtamStartOption above, this one isn't a "not yet
    validated" guess. The real reply is a topology *database summary*
    (counts of known adjacent/NN/EN nodes plus checkpoint/
    garbage-collection metadata), not a list of individual known nodes by
    name -- contrary to what was originally assumed (and used to justify
    skipping this command entirely in an earlier round)."""

    last_checkpoint: str | None = None            # e.g. "NONE"
    adj: int | None = None
    nn: int | None = None
    en: int | None = None
    served_en: int | None = None
    cdservr: int | None = None
    icn: int | None = None
    bn: int | None = None
    initdb_checkpoint_dataset: str | None = None   # e.g. "NONE"
    last_garbage_collection: str | None = None     # e.g. "07/01/26 21:44:28"


@dataclass
class TcpipHomeAddress:
    """One TCP/IP stack home address, as dumped by
    'D TCPIP,,NETSTAT,HOME' (see ansible/roles/zos_extract/tasks/tcpip.yml)
    and parsed by tcpip_parser.py.

    CONFIRMED against a real 'D TCPIP,,NETSTAT,HOME' reply on 2026-07-02.
    link_name covers both the legacy 'LINKNAME:' rows and the newer
    OSA-Express QDIO 'INTFNAME:' rows -- the real reply mixes both under
    the same HOME ADDRESS LIST -- see tcpip_parser.py's module docstring
    for the full real shape."""

    link_name: str
    ip_address: str
    is_primary: bool = False


@dataclass
class TcpipProfileStatement:
    """One PROFILE.TCPIP configuration statement, as fetched directly
    from the dataset named by zos_extract_tcpip_profile_dsn (see
    ansible/roles/zos_extract/tasks/tcpip.yml) and parsed by
    tcpip_parser.py.

    Captured generically (statement name + raw remaining operand text)
    rather than modeled per statement type, the same "capture
    everything generically" approach Jes2InitStatement/VtamStartOption
    use -- PROFILE.TCPIP statement syntax is positional and varied
    (DEVICE/LINK/HOME/PORT ...), not uniform KEYWORD=VALUE, so there's
    no single generic split like VTAMOPTS gets.

    CONFIRMED against a real PROFILE.TCPIP member on 2026-07-02, and the
    real shape needed more than the original one-line-per-statement
    guess: statements like INTERFACE/PORT/AUTOLOG/BEGINROUTES/SMFCONFIG
    span multiple physical lines (continuation lines and, for
    PORT/AUTOLOG, whole indented tables), all folded into that one
    statement's operands. See tcpip_parser.py's module docstring for the
    real shape and exactly how continuation lines are recognized."""

    stmt: str
    operands: str
    source_dsn: str = ""


@dataclass
class SmsStorageGroup:
    """One SMS storage group, as dumped by 'D SMS,STORGRP(ALL),LISTVOL'
    (see ansible/roles/zos_extract/tasks/sms.yml) and parsed by
    sms_parser.py.

    SMS storage classes and management classes were originally modeled
    here too (SmsStorageClass/SmsManagementClass), but 'D SMS,SC(*)'/
    'D SMS,MC(*)' were confirmed INVALID against a real system -- and
    IBM's own 'D SMS' command syntax reference confirms there's no
    console D-command for either at all (STORCLAS only appears as a
    filter on the unrelated PDSE HSPSTATS command). Removed rather than
    kept as dead code for commands that don't exist -- see sms.yml's own
    header comment.

    CONFIRMED against a real reply (via the 'SG' alias for 'STORGRP') --
    and the real shape was different enough from the original guess that
    `status`'s meaning changed and a new `group_type` field was added.
    See sms_parser.py's module docstring for the full detail, including
    why `status` is a raw per-system symbol sequence (e.g. "+ +") rather
    than a decoded ENABLE/DISABLE/NOTCNCT word."""

    name: str
    status: str | None = None   # raw per-system status symbols, e.g. "+ +" -- see the reply's own LEGEND
    group_type: str | None = None   # e.g. POOL, TAPE, OBJECT, OBJECT BACKUP, DUMMY
    volumes: list[str] = field(default_factory=list)


@dataclass
class Db2Package:
    """One installed DB2 package (SYSIBM.SYSPACKAGE row), as dumped by a
    DSNTEP2 batch SQL query (see
    ansible/roles/zos_extract/tasks/db2_catalog.yml) and parsed by
    db2_catalog_parser.py. Complements the live-activity address-space
    heuristic in db2.yml with real DB2 catalog content.

    CONFIRMED against a real DB2 subsystem (this site's DBDG) -- DSNTEP2's
    real report shape turned out to transpose wide result sets into one
    column-per-section rather than one row per line; see
    db2_catalog_parser.py's module docstring for the full detail."""

    name: str
    creator: str | None = None
    bind_timestamp: str | None = None
    ssid: str = ""


@dataclass
class Db2Plan:
    """One installed DB2 plan (SYSIBM.SYSPLAN row), same source/caveats
    as Db2Package."""

    name: str
    creator: str | None = None
    bind_timestamp: str | None = None
    ssid: str = ""


@dataclass
class WlmPolicy:
    """Single-record active WLM policy identity, as dumped by 'D WLM'
    (see ansible/roles/zos_extract/tasks/wlm.yml) and parsed by
    wlm_parser.py. First cut only -- full service-class/goal/
    resource-group definitions need the z/OSMF WLM REST API, not
    captured here.

    CONFIRMED against a real system -- and the fix here was bigger than a
    formatting tweak: the originally-guessed command, 'D WLM,POLICY',
    doesn't exist at all (a real system rejected the 'POLICY' keyword
    outright). The real command is bare 'D WLM'; see wlm_parser.py's
    module docstring for the confirmed IWM025I reply shape."""

    policy_name: str | None = None
    mode: str | None = None   # e.g. GOAL / COMPATIBILITY, if the reply exposes it


@dataclass
class WlmZosmfEntry:
    """One entry returned by z/OSMF's WLM REST API (see
    ansible/roles/zos_extract/tasks/wlm_zosmf.yml and playbooks/
    wlm_zosmf.yml) and parsed by wlm_zosmf_parser.py -- full
    service-class/goal/resource-group definitions, which 'D WLM,POLICY'
    (WlmPolicy above) can't expose. Not necessarily one row per "service
    class" specifically -- see the parser's own docstring for why this
    stays deliberately vague about what a "row" represents.

    Captured maximally generically (a best-guess `name` plus the entire
    raw JSON object for that entry) rather than modeling individual
    fields -- THE SINGLE MOST SPECULATIVE PIECE IN THE PIPELINE: neither
    the REST API path nor its response JSON schema is confirmed against
    real z/OSMF documentation or a real response, and there's no other
    REST/JSON precedent anywhere else in this codebase to lean on (every
    other domain parses console text). See wlm_zosmf_parser.py's module
    docstring for the full caveat."""

    name: str
    raw: dict = field(default_factory=dict)


@dataclass
class CatalogDataset:
    """One non-VSAM dataset under an operator-supplied HLQ/pattern, as
    dumped by zos-extract/python/extrcat.py via ZOAU's
    datasets.list_datasets()."""

    dsn: str
    volser: str | None = None
    dsorg: str | None = None    # e.g. PS, PO
    recfm: str | None = None
    lrecl: int | None = None
    blksize: int | None = None


@dataclass
class VsamCluster:
    """One VSAM cluster and its DATA/INDEX components, under an
    operator-supplied HLQ/pattern, as dumped by
    zos-extract/python/extrcat.py via IDCAMS LISTCAT ... ALL."""

    name: str
    cluster_type: str | None = None   # KSDS / ESDS / RRDS / LINEAR
    volser: str | None = None
    key_length: int | None = None
    key_offset: int | None = None
    data_component: str | None = None
    index_component: str | None = None


@dataclass
class RacfUser:
    """One RACF user (0200 USER BASIC DATA), as dumped by
    zos-extract/python/extrracf.py via IRRDBU00. IMPLEMENTATION ONLY --
    not yet validated against a real RACF database unload."""

    userid: str
    name: str | None = None
    owner: str | None = None
    default_group: str | None = None
    special: bool | None = None
    operations: bool | None = None
    auditor: bool | None = None
    revoked: bool | None = None
    restricted: bool | None = None   # RESTRICTED attribute, from ATTRIBS


@dataclass
class RacfGroup:
    """One RACF group (0100 GROUP BASIC DATA)."""

    name: str
    superior_group: str | None = None
    owner: str | None = None
    universal_access: str | None = None
    description: str | None = None   # INSTALL_DATA


@dataclass
class RacfGroupConnection:
    """One user-to-group connection (0205 USER CONNECT DATA) -- who's in
    what group, and what elevated authority (if any) they have scoped to
    that group specifically."""

    userid: str
    group: str
    group_special: bool | None = None
    group_operations: bool | None = None
    group_auditor: bool | None = None
    group_universal_access: str | None = None
    revoked_in_group: bool | None = None


@dataclass
class DatasetProfile:
    """One RACF DATASET-class profile (0400 DATASET BASIC DATA) -- a
    protection rule for a dataset name/pattern, not a physical dataset
    (see CatalogDataset for that)."""

    profile: str
    volume: str | None = None
    generic: bool | None = None
    owner: str | None = None
    universal_access: str | None = None
    audit_level: str | None = None


@dataclass
class DatasetAccess:
    """One access-list entry (0404 DATASET ACCESS) for a DatasetProfile."""

    profile: str
    auth_id: str   # user ID or group name
    access: str | None = None   # NONE / EXECUTE / READ / UPDATE / CONTROL / ALTER


@dataclass
class GeneralResourceProfile:
    """One general-resource-class profile (0500 GENERAL RESOURCE BASIC
    DATA), limited to racf_parser.CURATED_CLASSES -- IRRDBU00 itself has
    no selective-unload option, so this curation happens off-host."""

    profile: str
    class_name: str
    owner: str | None = None
    universal_access: str | None = None
    audit_level: str | None = None


@dataclass
class GeneralResourceAccess:
    """One access-list entry (0505 GENERAL RESOURCE ACCESS) for a
    GeneralResourceProfile."""

    profile: str
    class_name: str
    auth_id: str
    access: str | None = None


@dataclass
class CicsDfhrplEntry:
    """One DFHRPL (CICS's own load-library concatenation, functionally
    STEPLIB/JOBLIB for CICS's own dynamic program loading) dataset, as
    extracted from a CICS startup PROC's DFHRPL DD group (see
    ansible/roles/zos_extract/tasks/cics_deepening.yml) and parsed by
    cics_proc_parser.py. `zone`/`apf_authorized` are left unset by the
    parser and filled in at ingest time (cli.py) via
    resolver.dataset_zone()/apf.txt membership, the same STEPLIB/JOBLIB/
    LNKLST zone/APF resolution machinery lineage already uses -- giving
    "what installed, patched software does this CICS region actually
    depend on."

    NOT YET VALIDATED against a real CICS startup PROC -- the DFHRPL
    DD-group regex is reused near-verbatim from
    discover_mstrjcl_proclibs.yml's confirmed IEFPDSI handling, but that
    reuse itself hasn't been checked against a real CICS PROC."""

    dsn: str
    proc: str = ""
    zone: str | None = None
    apf_authorized: bool | None = None


@dataclass
class CicsSitOverride:
    """One CICS SIT (System Initialization Table) override KEYWORD=VALUE
    pair, from a CICS startup PROC's inline SYSIN cards (see
    cics_deepening.yml) and parsed by cics_proc_parser.py. Captured
    generically, same rationale as VtamStartOption/Jes2InitStatement --
    the full SIT override keyword set isn't confirmed here.

    NOT YET VALIDATED against a real CICS startup PROC's SYSIN cards."""

    keyword: str
    value: str
    proc: str = ""


@dataclass
class CicsCsdDefinition:
    """One CICS resource definition, from a DFHCSDUP LIST report against
    the CSD named by a CICS startup PROC's DFHCSD DD (see
    cics_deepening.yml, cics_csdup_parser.py). Captured maximally
    generically (def_type, name, group, csd_dsn -- no attribute dict, just
    the identifying fields a report row can be reasonably expected to
    carry) since DFHCSDUP's real LIST report *print format* isn't
    confirmed here, unlike its LIST command syntax (LIST ALL / LIST
    LIST(name) OBJECTS), which cics_deepening.yml's own header comment
    confirms against real IBM documentation.

    THE MOST SPECULATIVE PARSER IN THIS PIPELINE, alongside
    db2_catalog_parser.py and wlm_zosmf_parser.py -- see
    cics_csdup_parser.py's module docstring for the full caveat,
    including the real, documented operational risk around reading a
    live CICS region's CSD concurrently."""

    def_type: str
    name: str
    group: str = ""
    csd_dsn: str = ""


@dataclass
class CmciResource:
    """One CICS resource, fetched via CMCI (CICS Management Client
    Interface)'s REST API using ibm.ibm_zos_cics's cmci_get module (see
    ansible/roles/zos_extract/tasks/cics_cmci.yml) and parsed by
    cmci_parser.py -- an alternative to the DFHCSDUP-based
    CicsCsdDefinition above for whichever of this site's CICS regions
    actually have CMCI enabled (not all do; see zos_extract_cics_cmci_targets).

    Unlike DFHCSDUP's own LIST report (a raw print-format report this
    pipeline has to guess at the column layout of), cmci_get already
    parses CMCI's XML wire format into clean per-record dicts itself --
    there's no report-format uncertainty here the way there is for
    db2_catalog_parser.py/wlm_zosmf_parser.py/cics_csdup_parser.py.
    `resource_type` is one of the CMCI external resource names queried
    (cicsdefinitionprogram/cicsdefinitiontransaction/cicsdefinitionfile
    for CSD-sourced definitions, CICSProgram/CICSTransaction/
    CICSLocalFile for the currently-installed/active equivalents -- see
    cics_cmci.yml's own header comment for why both categories are
    queried). `context` is the CMCI context the query ran against -- in
    this project's SMSS (standalone-region) usage, that's the CICS
    region's own APPLID, not a CICSplex name.

    Captured with the full raw attribute dict preserved (`attributes`),
    same "don't lose data even if a specific field extraction guesses
    wrong" rationale as WlmZosmfEntry.raw -- `name` is a best-guess
    extraction of whichever attribute is that resource type's own primary
    identifier (see cmci_parser.py's module docstring for the exact
    candidate keys and which are confirmed against cmci_get's own
    documented examples vs. still a guess)."""

    resource_type: str
    context: str
    name: str
    attributes: dict = field(default_factory=dict)


@dataclass
class RacfSnapshot:
    """Everything parsed from one extrracf.py dump, bundled together
    rather than returned as a 7-tuple (error-prone to unpack)."""

    users: list[RacfUser] = field(default_factory=list)
    groups: list[RacfGroup] = field(default_factory=list)
    group_connections: list[RacfGroupConnection] = field(default_factory=list)
    dataset_profiles: list[DatasetProfile] = field(default_factory=list)
    dataset_access: list[DatasetAccess] = field(default_factory=list)
    general_resource_profiles: list[GeneralResourceProfile] = field(default_factory=list)
    general_resource_access: list[GeneralResourceAccess] = field(default_factory=list)
