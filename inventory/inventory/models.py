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

    NOT YET VALIDATED against a real JES2 init deck -- see
    jes2parm_parser.py's module docstring."""

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

    NOT YET VALIDATED against a real 'D TCPIP,,NETSTAT,HOME' reply --
    see tcpip_parser.py's module docstring."""

    link_name: str
    ip_address: str


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

    NOT YET VALIDATED against a real PROFILE.TCPIP sample -- see
    tcpip_parser.py's module docstring."""

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

    THE MOST SPECULATIVE DOMAIN IN THE PIPELINE -- NOT YET VALIDATED
    against a real DB2 subsystem; see db2_catalog_parser.py's module
    docstring for the full caveat."""

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
