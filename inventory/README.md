# inventory

Off-host half of the pipeline: parses the text dumped by `zos-extract/`
(or, for domains with no standalone `zos-extract/python` script yet --
USS mounted filesystems, JES2's own initialization parameters, VTAM
major-node status/start options, TCP/IP home addresses/PROFILE.TCPIP, and
SMS storage groups/storage classes/management classes -- the `ansible/`
role directly; see
[`../ansible/README.md`](../ansible/README.md)) and resolves each
PROCLIB/PARMLIB member's full execution path back to the SMP/E FMID that
owns each program it runs, flags whether each resolved load library is
APF-authorized, and separately inventories defined subsystems,
auto-started tasks, the LPAR/sysplex identity of the system the dump came
from, product enablement status (IFAPRDxx), a live snapshot of
currently-running jobs/tasks and USS processes, an HLQ/pattern-scoped
dataset catalog (non-VSAM attributes + VSAM cluster/component detail),
mounted USS filesystems, JES2's own initialization statements, VTAM/APPN
status, TCP/IP configuration, SMS storage groups/classes, and a RACF
security snapshot (users, groups, dataset and general-resource access —
**implementation only, not
yet production-validated**, see below). Everything lands in one small
SQLite database you query from the command line.

This half runs on any ordinary computer — Mac, Linux, Windows (WSL),
CI runner — nothing here needs to touch a mainframe. If you just want to
see what it does before running the real z/OS extraction steps, skip to
["Try it without any z/OS data"](#try-it-without-any-zos-data) below.

## Install

```
cd inventory
pip install -e .
```

Requires Python 3.9+. No third-party runtime dependencies — only `pytest`
is needed for the test suite.

**If `pip install` fails with an error mentioning
"externally-managed-environment"** (common on recent macOS/Homebrew Python
or Debian/Ubuntu system Python): your system is deliberately blocking
`pip install` outside of a virtual environment. Use one:

```
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -e .
```

Every command below (`inventory ...`, `pytest`) then needs to run with
that same virtual environment activated (or use its full path, e.g.
`.venv/bin/inventory ...`, if you'd rather not activate it).

## Try it without any z/OS data

The repo ships small synthetic fixture files that exercise the whole
pipeline. This is the fastest way to see what `inventory` actually
produces:

```
mkdir -p /tmp/demo && \
  cp tests/fixtures/sample_proclib.txt   /tmp/demo/00_proclib.txt && \
  cp tests/fixtures/sample_smpe_list.txt /tmp/demo/tzone1.smplist.txt && \
  cp tests/fixtures/sample_lnklst.txt    /tmp/demo/lnklst.txt && \
  cp tests/fixtures/sample_apf.txt       /tmp/demo/apf.txt && \
  cp tests/fixtures/sample_ssn.txt       /tmp/demo/00_ssn.txt && \
  cp tests/fixtures/sample_commnd.txt    /tmp/demo/00_commnd.txt && \
  cp tests/fixtures/sample_sysinfo.txt   /tmp/demo/sysinfo.txt && \
  cp tests/fixtures/sample_ifaprd.txt    /tmp/demo/00_ifaprd.txt && \
  cp tests/fixtures/sample_active_jobs.txt /tmp/demo/active_jobs.txt && \
  cp tests/fixtures/sample_processes.txt   /tmp/demo/processes.txt && \
  cp tests/fixtures/sample_catalog.txt     /tmp/demo/demo_catalog.txt && \
  cp tests/fixtures/sample_racf.txt        /tmp/demo/racf.txt && \
  cp tests/fixtures/sample_uss_mounts.txt  /tmp/demo/uss_mounts.txt && \
  cp tests/fixtures/sample_jes2parm.txt    /tmp/demo/jes2parm.txt && \
  cp tests/fixtures/sample_vtam.txt        /tmp/demo/vtam.txt && \
  cp tests/fixtures/sample_tcpip.txt       /tmp/demo/tcpip.txt && \
  cp tests/fixtures/sample_sms.txt         /tmp/demo/sms.txt
inventory --db /tmp/demo/demo.db ingest /tmp/demo
```

(The fixture files aren't named the way `zos-extract/` would actually name
them — see the [naming convention cheat
sheet](../zos-extract/README.md#naming-convention-cheat-sheet) — this is
just renaming them into that shape for a quick demo.)

## Usage against real data

1. Run `zos-extract/` on the target z/OS system and download its output
   (PROCLIB/PARMLIB dumps, IEFSSNxx/COMMNDxx dumps, IFAPRDxx dumps,
   LNKLST list, APF list, system identity dump, SMP/E LIST reports, active
   jobs/processes snapshot, dataset catalog dumps, and — implementation
   only, see its README section — a RACF security snapshot) into one local
   directory — see
   [`../zos-extract/README.md`](../zos-extract/README.md) for the exact
   file naming and how to produce each file. Five more files —
   `uss_mounts.txt` (mounted USS filesystems), `jes2parm.txt`/
   `NN_jes2parm.txt` (JES2's own initialization statements), `vtam.txt`
   (VTAM major-node status and start options, incl. APPN
   enablement/role), `tcpip.txt` (TCP/IP home addresses and, if
   configured, `PROFILE.TCPIP` text), and `sms.txt` (SMS storage groups,
   storage classes, and management classes) — have no standalone
   `zos-extract/python` script yet and are only produced by the
   `ansible/` role's `uss_mounts`/`jes2parm`/`vtam`/`tcpip`/`sms` tags; see
   [`../ansible/README.md`](../ansible/README.md)'s Layout section. All
   five are implementation-only, same caveat as RACF below — not yet
   validated against a real system's actual command output.

2. Ingest and resolve:

   ```
   inventory ingest path/to/downloaded/input/
   ```

   This parses everything in that directory, builds the lineage chain for
   every member, and writes the result to `inventory.db` in the current
   directory (SQLite; override the path with `--db somewhere/else.db` —
   note `--db` goes *before* the subcommand, e.g.
   `inventory --db mydb.db ingest input/`). Expected output:

   ```
   inventory: ingested 5 members, 2 zones, 6 resolved steps, 2 subsystems, 2 started tasks, 2 products, 3 active jobs, 3 processes, 2 cataloged datasets, 2 VSAM clusters, 2 RACF users, 1 RACF groups, 3 USS mounts, 4 JES2 init statements, 3 VTAM major nodes, 4 VTAM start options, 2 TCPIP home addresses, 4 TCPIP profile statements, 2 SMS storage groups, 2 SMS storage classes, 1 SMS management classes -> /tmp/demo/demo.db
   ```

   You can re-run `ingest` any time (e.g. after extracting more zones or
   libraries) — it replaces the previous contents of the database rather
   than duplicating rows.

3. Query it. Every command below accepts `--db` before the subcommand if
   you're not using the default `inventory.db` in the current directory.

### `inventory lineage MEMBERNAME`

Full resolved execution path for one PROCLIB/PARMLIB member:

```
$ inventory lineage MYPROC
MYPROC
  step STEP1: PGM=IEFBR14 dataset=MY.SITE.LINKLIB zone=TZONE2 FMID=? [APF]  [module IEFBR14 not found in zone TZONE2's FILE list]
  step NSTEP1: PGM=IGYCRCTL dataset=SYS1.LINKLIB zone=TZONE1 FMID=HLA2280 [non-APF]  [resolved via STEPLIB (APPLIED)]
```

Nested `EXEC PROCNAME` steps are already flattened into this list — you
don't need to separately look up the nested PROC. `[APF]`/`[non-APF]`
shows APF authorization status (only shown as `[APF=?]` if you didn't
ingest an `apf.txt`). The bracketed text at the end of each line explains
*how* that hop was resolved, or why it couldn't be.

### `inventory report [--output file.csv]`

The same information as `lineage`, but for every member at once, as CSV
(to stdout by default, or a file with `--output`):

```
$ inventory report
member,step_name,pgm,dataset,zone,fmid,resolution,apf_authorized
JOBPROC,JSTEP1,SAMPMOD,MY.SITE.LINKLIB,TZONE2,USER001,resolved via JOBLIB (APPLIED),1
LNKPROC,LSTEP1,IEBGENER,SYS1.LINKLIB,TZONE1,HBB7790,resolved via LNKLST (APPLIED),0
...
```

`apf_authorized` is `1`/`0`/empty in the CSV (True/False/unknown).

### `inventory subsystems`

Everything found in your `IEFSSNxx` dump(s):

```
$ inventory subsystems
DB2P: INITRTN=DSN3INI INITPARM='' [IEFSSN00]
JES2: INITRTN=HASJES20 INITPARM='SUB=YES' [IEFSSN00]
```

### `inventory started-tasks`

Everything found in your `COMMNDxx` dump(s) that's an `S`/`START` command:

```
$ inventory started-tasks
S CICSPROD.CICSA  [COMMND00]
S VTAM  [COMMND00]
```

### `inventory sysinfo`

The single system-identity record, if you ingested a `sysinfo.txt`:

```
$ inventory sysinfo
SYSNAME:  SYS1
SYSCLONE: S1
SYSPLEX:  PLEX1
IPL VOLUME: RES0S1
IPL PARM MEMBER: 00
RELEASE: z/OS 02.05.00
ARCHLVL: 2
```

If you didn't ingest a `sysinfo.txt`, this prints `no system info
ingested` and exits with a non-zero status — that's expected, not a bug.

### `inventory products`

Everything found in your `IFAPRDxx` dump(s) — what's licensed/enabled, as
opposed to `lineage`/`report`'s FMID column, which says what's installed:

```
$ inventory products
5650-ZOS: SOME OPTIONAL FEATURE  VRM=2.5.0 FEATURENAME=OPTFEAT STATE=DISABLED  [IFAPRD00]
5655-EPS: EMBEDDED RUNTIME ENABLEMENT FOR ZOS  VRM=*.*.* FEATURENAME=* STATE=ENABLED  [IFAPRD00]
```

`VRM` is VERSION.RELEASE.MOD as coded in the PRODUCT statement — `*` means
"any" (a wildcard match), not literally the character `*` on your system.

### `inventory active`

Currently-active jobs/started tasks, if you ingested an `active_jobs.txt`
— unlike everything else in this tool, this is a live, point-in-time
snapshot, not configuration:

```
$ inventory active
STC03801 CICSPROD  TYPE=STC ASID=0043 OWNER=CICSUSR JOBCLASS=STC SVCCLASS=SYSSTC SYSTEM=BES2
STC00002 JES2  TYPE=STC ASID=0002 OWNER=STCUSR JOBCLASS=STC SVCCLASS=SYSSTC SYSTEM=BES2
JOB01234 PAYROLL  TYPE=JOB ASID=0091 OWNER=PAYUSR JOBCLASS=A SVCCLASS=BATCH SYSTEM=BES2
```

`active_jobs.txt` itself is JSON Lines (one job object per line, straight
from ZOAU's `jls`) rather than a fixed-width format -- `ActiveJob` carries
quite a few more fields than this summary prints (completion code,
priority, creation/execution timestamps, subsystem, node info, member
name); query the `active_jobs` table directly if you need those.

`ASID` (address space ID) distinguishes concurrently-running copies of the
same-named task. To check whether something defined in `started-tasks`
above is actually running, match its task name against this list's names.

### `inventory processes`

Currently-running USS process command names, if you ingested a
`processes.txt`:

```
$ inventory processes
/bin/tcsh
/usr/sbin/sshd
python3
```

### `inventory catalog`

Non-VSAM datasets matching whatever `--pattern`(s) you gave `extrcat.py`,
if you ingested a `*catalog*.txt` file:

```
$ inventory catalog
MY.SITE.LOADLIB  VOLSER=VOL001 DSORG=PO RECFM=FB LRECL=80 BLKSIZE=27920
MY.SITE.SEQFILE  VOLSER=VOL002 DSORG=PS RECFM=FB LRECL=133 BLKSIZE=1330
```

### `inventory vsam`

VSAM clusters (and their DATA/INDEX components) matching those same
patterns:

```
$ inventory vsam
MY.VSAM.KSDS1  TYPE=KSDS VOLSER=VOL001 KEYLEN=20 RKP=0 DATA=MY.VSAM.KSDS1.DATA INDEX=MY.VSAM.KSDS1.INDEX
MY.VSAM.ESDS1  TYPE=ESDS VOLSER=? KEYLEN=? RKP=? DATA=MY.VSAM.ESDS1.DATA INDEX=?
```

Both are HLQ/pattern-scoped, not a full catalog — see
[`../zos-extract/README.md`](../zos-extract/README.md#9-dataset-catalog-hlqpattern-scoped)
for how to run `extrcat.py`. `?` means that field didn't match anything in
the captured `LISTCAT` report (see "How resolution works" below).

### RACF security snapshot (implementation only, not yet production-validated)

Seven commands, if you ingested a `racf.txt` — see
[`../zos-extract/README.md`](../zos-extract/README.md#10-racf-security-snapshot-implementation-only--verify-authority-before-running)
for the (real) authorization hurdle before you can actually generate one.
**These are built and tested against a synthetic fixture, but not yet
checked against a real IRRDBU00 unload — see "How resolution works" below
for the specific field that's least certain.**

```
$ inventory racf-users
JDOE001  NAME=JOHN DOE OWNER=SYSPROG DFLTGRP=SYSPROG SPECIAL=YES OPERATIONS=NO AUDITOR=YES REVOKED=NO RESTRICTED=?
MARYADM  NAME=MARY ADMIN OWNER=SYSPROG DFLTGRP=APPGRP SPECIAL=NO OPERATIONS=NO AUDITOR=NO REVOKED=YES RESTRICTED=YES

$ inventory racf-groups
SYSPROG  SUPGROUP=SYS1 OWNER=IBMUSER UACC=NONE

$ inventory racf-connections
JDOE001 in SYSPROG  UACC=CONTROL GRP-SPECIAL=YES GRP-OPERATIONS=NO GRP-AUDITOR=NO REVOKED=NO
MARYADM in APPGRP  UACC=READ GRP-SPECIAL=NO GRP-OPERATIONS=NO GRP-AUDITOR=NO REVOKED=YES

$ inventory racf-dataset-profiles
PROD.PAYROLL.**  VOLUME=? GENERIC=YES OWNER=SYSPROG UACC=NONE AUDIT=NONE

$ inventory racf-dataset-access
PROD.PAYROLL.**  ADMGRP=ALTER
PROD.PAYROLL.**  PAYGRP=READ

$ inventory racf-resource-profiles
FACILITY/BPX.SUPERUSER  OWNER=IBMUSER UACC=NONE AUDIT=FAIL
STARTED/CICSPROD.STC  OWNER=SYSPROG UACC=NONE AUDIT=NONE

$ inventory racf-resource-access
FACILITY/BPX.SUPERUSER  OMVSADM=READ
STARTED/CICSPROD.STC  CICSRACF=READ
```

`racf-resource-profiles`/`racf-resource-access` only ever show classes in
`racf_parser.CURATED_CLASSES` (currently `SURROGAT`, `JESJOBS`,
`FACILITY`, `OPERCMDS`, `STARTED`, `SERVAUTH`, `APPL`, `DSNR`) — IRRDBU00
itself has no selective-unload option, so every other class is dropped
off-host during parsing, not at extraction time.

### `inventory uss-mounts` (not yet production-validated)

Every mounted USS filesystem, if you ingested a `uss_mounts.txt` — see
`ansible/roles/zos_extract/tasks/uss_mounts.yml` for how it's produced.
**Built and tested against a hand-constructed fixture, not a real `D
OMVS,F` reply — see `uss_mounts_parser.py`'s module docstring for the
same kind of caveat `racf_parser.py` carries.**

```
$ inventory uss-mounts
/  NAME=OMVS.ROOT.ZFS TYPE=ZFS DEVICE=1 STATUS=ACTIVE MODE=RDWR
/etc  NAME=OMVS.ETC.ZFS TYPE=ZFS DEVICE=2 STATUS=ACTIVE MODE=RDWR
/legacy  NAME=OMVS.LEGACY.HFS TYPE=HFS DEVICE=3 STATUS=ACTIVE MODE=READ
```

### `inventory jes2parm` (not yet production-validated)

Every JES2 initialization statement, if you ingested a `jes2parm.txt` —
JES2's own PARMLIB-equivalent init deck, distinct from both SYS1.PARMLIB's
IEFSSNxx/COMMNDxx and the JES2 *PROCLIB* concatenation `subsystems`/
`report` already cover. Captured generically (statement name + optional
subscript + a raw keyword=value map), not modeled per statement type — see
`Jes2InitStatement` in `models.py`. **Also not yet validated against a
real JES2 init deck — see `jes2parm_parser.py`'s module docstring.**

```
$ inventory jes2parm
JOBCLASS(1)  JOBPRTY=16,COMMAND=NO  [JES2PARM]
JOBDEF  JOBNUM=(999,999,1),RESTART=YES  [JES2PARM]
MASDEF  OWNMASN=1,NAME=NJE1  [JES2PARM]
OUTCLASS(A)  QUEUE=YES,BURST=YES  [JES2PARM]
```

### `inventory vtam-majnodes` / `inventory vtam-options` (not yet production-validated)

VTAM major-node status (`D NET,MAJNODES`) and start options (`D
NET,VTAMOPTS`), if you ingested a `vtam.txt`. `vtam-options` is where
APPN coverage lives this round: rather than a dedicated `nodetype`/
`cpname` field, every `KEYWORD = VALUE` pair VTAM's start-option display
exposes is captured generically (`VtamStartOption` in `models.py`) — look
for the `NODETYPE`/`CPNAME` rows to see whether APPN is enabled and as
what role (NN/EN/LEN vs. subarea-only). `D NET,TOPO` (the APPN topology
database itself) isn't captured yet — see `vtam_parser.py`'s module
docstring for why. **Neither command's reply has been checked against a
real system — see `vtam_parser.py`'s module docstring.**

```
$ inventory vtam-majnodes
APPLMAJ  STATUS=INACT
NCPMAJ  STATUS=ACTIV
VTAMLST  STATUS=ACT/S

$ inventory vtam-options
CPNAME=NN01
NETID=USIBMSC
NODETYPE=NN
SSCPID=1
```

### `inventory tcpip-home` / `inventory tcpip-profile` (not yet production-validated)

TCP/IP home addresses (`D TCPIP,,NETSTAT,HOME`, always captured) and
`PROFILE.TCPIP` configuration statements (only if
`zos_extract_tcpip_profile_dsn` was configured), if you ingested a
`tcpip.txt`. `tcpip-profile` rows are captured generically (statement
name + raw operand text, `TcpipProfileStatement` in `models.py`) since
`PROFILE.TCPIP` syntax is positional (`DEVICE`/`LINK`/`HOME`/`PORT` ...),
not uniform `KEYWORD=VALUE` — see `tcpip_parser.py`'s module docstring.
**Neither piece has been checked against a real system or a real
`PROFILE.TCPIP` sample.**

```
$ inventory tcpip-home
ETH0LINK  10.1.1.2
LOOPBACK  127.0.0.1

$ inventory tcpip-profile
DEVICE OSA2080 MPCIPA  [TCPIP.TCPPARMS(PROFILE1)]
HOME 10.1.1.2 ETH0LINK  [TCPIP.TCPPARMS(PROFILE1)]
HOSTNAME MVSTCPIP  [TCPIP.TCPPARMS(PROFILE1)]
LINK ETH0LINK IPAQENET OSA2080  [TCPIP.TCPPARMS(PROFILE1)]
```

### `inventory sms-storgrps` / `inventory sms-storclas` / `inventory sms-mgmtclas` (not yet production-validated)

SMS storage groups and their volumes (`D SMS,STORGRP(*),LISTVOL`),
storage classes (`D SMS,SC(*)`), and management classes (`D SMS,MC(*)`),
if you ingested an `sms.txt`. ACS routine *source* is out of scope here
(that needs ISMF, not a `D`-command). Storage/management class attributes
are captured generically (class name + a raw keyword->value map,
`SmsStorageClass`/`SmsManagementClass` in `models.py`) rather than
modeled per attribute, the same approach `VtamStartOption`/
`Jes2InitStatement` use. **None of the three commands has been checked
against a real system — see `sms_parser.py`'s module docstring.**

```
$ inventory sms-storgrps
SG1  STATUS=ENABLE  VOLUMES=VOL001,VOL002
SG2  STATUS=DISABLE  VOLUMES=VOL010

$ inventory sms-storclas
FAST  AVAILABILITY=STANDARD,PERFORMANCE=1
STANDARD  AVAILABILITY=STANDARD,ACCESSIBILITY=CONTINUOUS,PERFORMANCE=3

$ inventory sms-mgmtclas
MCDEFLT  EXPIRE=NOLIMIT,MIGRATE=030
```

## How resolution works

See `inventory/resolver.py`. For each PROCLIB/PARMLIB member:

1. Nested `EXEC PROCNAME` steps are inlined recursively (so a 3-level-deep
   PROC chain shows up as one flat list of PGM= hops).
2. Each `PGM=` is matched to a load library dataset via STEPLIB > JOBLIB >
   LNKLST search order.
3. The dataset is matched to an SMP/E target zone via that zone's DDDEF
   entries (`LIST DDDEF` output).
4. The module is looked up in that zone's `LIST FILE` output to get the
   owning FMID, with status (APPLIED/ACCEPTED) from `LIST SYSMOD`.
5. If `apf.txt` was ingested, the resolved dataset is flagged
   `apf_authorized` True/False; if `apf.txt` wasn't ingested, the flag is
   `None` (unknown) rather than defaulting to either True or False.

Any hop that can't be resolved (no STEPLIB and no LNKLST match, a dataset
not claimed by any ingested zone, etc.) is still recorded with a
human-readable reason in the `resolution` column — the inventory deliberately
surfaces gaps instead of silently dropping them.

Subsystems (`ssn_parser.parse_subsystems`), started tasks
(`ssn_parser.parse_started_tasks`), and products
(`ifaprd_parser.parse_products`) are parsed independently of the
STEPLIB/JOBLIB/LNKLST/SMP/E lineage above — they're not part of a
ProcMember's execution path, just separate inventory dimensions read from
PARMLIB text dumps. System identity (`sysinfo_parser.parse_sysinfo`) is a
single record per ingest, not a list. Active jobs and USS processes
(`activity_parser.parse_active_jobs`/`parse_processes`) are also
independent of the lineage chain and, unlike every other dimension, are a
live snapshot rather than configuration — see "Scaling" below on what
that means for re-ingesting. Cataloged datasets and VSAM clusters
(`catalog_parser.parse_catalog`) are likewise independent of the lineage
chain — they're not currently cross-referenced against `lineage`/`apf`/
`lnklst` (e.g. flagging which cataloged dataset is also a load library in
some member's execution path), though that's a natural follow-up once
this dimension has real-world data to check it against. The RACF snapshot
(`racf_parser.parse_racf`) is independent of everything else the same way,
and is also not yet cross-referenced (e.g. matching `STARTED`-class
resource profiles against `started_tasks`) for the same reason. USS mounts
(`uss_mounts_parser.parse_uss_mounts`), JES2 init statements
(`jes2parm_parser.parse_dump`), VTAM major nodes/start options
(`vtam_parser.parse_vtam`), TCP/IP home addresses/profile statements
(`tcpip_parser.parse_tcpip`), and SMS storage groups/classes
(`sms_parser.parse_sms`) are likewise independent, freshly-added
dimensions with no cross-referencing yet.

## Tests

```
pip install -e . pytest
pytest
```

`tests/fixtures/` contains small synthetic dumps exercising: direct
STEPLIB resolution, JOBLIB resolution, LNKLST fallback resolution, nested
PROC inlining, an intentionally-unresolvable module (to verify the "module
not found" reporting path), an intentionally-unresolvable nested PROC
reference, APF-authorized/non-authorized resolution, subsystem/started-task
parsing (including continuation-spanning INITPARM and a non-start COMMNDxx
line that should be skipped), system-identity parsing (including a field
deliberately missing from the fixture, to prove tolerant partial matching),
and product parsing (an enabled product with wildcard VERSION/RELEASE/
MOD/FEATURENAME, and a disabled product with a named feature). Also
active-job and USS-process parsing (`sample_active_jobs.txt`/
`sample_processes.txt`), and dataset catalog parsing
(`sample_catalog.txt`, covering non-VSAM attributes, a fully-populated
VSAM KSDS cluster, and a VSAM ESDS cluster with several fields
deliberately absent to prove tolerant partial matching). Also RACF
snapshot parsing (`sample_racf.txt`, covering users incl. a revoked/
RESTRICTED one, a group, group connections, a dataset profile + access
list, and general-resource profiles/access across two curated classes
plus one non-curated class proven to be filtered out) — **built against a
hand-constructed fixture, not a real IRRDBU00 unload; see "How resolution
works" for the specific field this is least confident about.** Also USS
mount parsing (`sample_uss_mounts.txt`, covering a read-write zFS root and
`/etc` mount plus a read-only HFS mount, and proving header/summary lines
aren't mistaken for mount records) and JES2 init-statement parsing
(`sample_jes2parm.txt`, covering a comment line that must be skipped, a
statement whose continuation spans two lines, a parenthesized statement
subscript, and a parameter value with inner commas that must not be split
as separate parameters) — **both built against hand-constructed fixtures,
not a real system reply; see `uss_mounts_parser.py`/`jes2parm_parser.py`'s
module docstrings.** Also VTAM parsing (`sample_vtam.txt`, covering major
nodes across ACTIV/ACT\/S/INACT statuses plus banner/header lines proven
not to be mistaken for data rows, and start options incl. the
`NODETYPE`/`CPNAME` pair that answers the APPN-enablement question) and
TCP/IP parsing (`sample_tcpip.txt`, covering paired `LINKNAME:`/`ADDRESS:`
home-address lines, a `PROFILE.TCPIP` excerpt with a comment line that
must be skipped, and confirming the `##PROFILE` block/`source_dsn` is
simply absent when a dump has no profile fetch) — **both also built
against hand-constructed fixtures, not a real system reply; see
`vtam_parser.py`/`tcpip_parser.py`'s module docstrings.** Also SMS parsing
(`sample_sms.txt`, covering storage groups with multi-volume continuation
lines, storage/management classes with generically-captured
`KEYWORD(VALUE)` attributes, and message-ID banner lines like `IGD002I`/
`END` proven not to be mistaken for a class name) — **also built against
a hand-constructed fixture, not a real system reply; see
`sms_parser.py`'s module docstring.**

## Scaling past the first slice

- Ingest accepts any number of `*proclib*.txt` / `*parmlib*.txt` /
  `*smplist*.txt` / `*ssn*.txt` / `*commnd*.txt` / `*ifaprd*.txt` /
  `*catalog*.txt` / `*uss_mounts*.txt` / `*jes2parm*.txt` / `*vtam*.txt` /
  `*tcpip*.txt` / `*sms*.txt` files in the input directory — just keep adding files as
  you extract more PROCLIB/PARMLIB concatenation entries, more SMP/E
  zones, more HLQ/pattern groups, or more JES2 PARMLIB concatenation
  entries; `ingest` merges them all into one inventory. `lnklst.txt` and
  `apf.txt` are each a single flat list.
- `system_info` (from `sysinfo.txt`), `active_jobs` (from
  `active_jobs.txt`), `uss_processes` (from `processes.txt`), and the
  seven `racf_*` tables (from `racf.txt`) are the exceptions: each is
  deliberately *not* additive like the tables above. `system_info`
  represents the identity of the one system being ingested; `active_jobs`/
  `uss_processes` represent one point-in-time snapshot of what was
  running; the `racf_*` tables represent IRRDBU00's full current database
  state, not an incremental slice. Re-ingesting any of them replaces
  rather than merges — for the live-snapshot pair, that's the whole point:
  re-run `extrjobs.py`/`extrprocs.py` and `ingest` again to get an updated
  picture, not an ever-growing history. `system_info` is also what a
  future multi-system merge (one inventory DB per system, or a `system`
  column added throughout) would key each ingest run on.
- The `smpe_parser` module's docstring explains how to tune its regexes if
  your shop's SMP/E LIST report formatting differs from the fixture; the
  `sysinfo_parser` module's docstring has the same guidance for `D
  SYMBOLS`/`D IPLINFO` output, which varies more by release/site than
  SMP/E's LIST format does. `catalog_parser`'s `##LISTCAT`-block regexes
  carry the same caveat — IDCAMS `LISTCAT ALL` report layout is documented
  but wasn't calibrated against a real system's actual output while
  writing this; the `##NONVSAM` block (from ZOAU's `datasets` API
  directly, not a parsed report) doesn't need this caveat.
- `racf_parser` carries the strongest version of this caveat in the
  project: IBM's own IRRDBU00 documentation is inaccessible to automated
  fetch, so its fixed-byte-offset field layout was derived from a real,
  working third-party parser (`github.com/s1th/racf`) rather than IBM's
  own docs or a real unload sample. One field in particular,
  `GeneralResourceProfile.universal_access` (the `0500` record's `UACC`
  field), is flagged in the module docstring as inferred rather than
  confirmed, after finding what looks like a bug in that third-party
  reference (it reads `UACC` from the same offset as `READ_CNT`). Verify
  this dimension's output against a real IRRDBU00 unload before relying on
  it — see `zos-extract/README.md`'s RACF step for why that's a bigger
  ask than everything else in this pipeline.

## Upgrading from an older `inventory.db`

Schema changes (like the `apf_authorized` column and the new tables) apply
via `CREATE TABLE IF NOT EXISTS`, which won't alter an already-existing
on-disk database. There's no migration framework at this project's current
stage — if `ingest` errors on an old `.db` file (e.g. mentioning a column
count mismatch), delete it and re-run `ingest` to rebuild it with the
current schema. Since `ingest` always fully rebuilds its tables from your
input directory, this loses no information beyond needing to re-run
`ingest` once.

## Troubleshooting

- **"command not found: inventory"** after `pip install -e .` — if you
  used a virtual environment (see Install above), make sure it's
  activated in the shell you're running `inventory` from, or use its full
  path (e.g. `.venv/bin/inventory`).
- **"no lineage found for member X"** from `inventory lineage` — either
  that member name doesn't exist in what you ingested (check spelling and
  that you actually ingested a file containing it), or you haven't run
  `ingest` yet / pointed `--db` at the wrong database file.
- **Every `zone`/`fmid` comes back empty in `lineage`/`report`** — your
  SMP/E LIST report likely isn't matching `smpe_parser.py`'s regexes.
  Compare your actual `*smplist*.txt` file's formatting against the
  patterns described in that module's docstring, and against
  `tests/fixtures/sample_smpe_list.txt`, which shows a minimal example of
  the expected shape.
- **Every `apf_authorized` comes back empty/unknown** — this is expected
  if you didn't ingest an `apf.txt` (see "How resolution works" above);
  if you did ingest one and it's still empty, double check the file is
  actually named `apf.txt` (exact name, not just containing `apf`).
- **`ingest` fails with a SQLite error mentioning a column count** — see
  "Upgrading from an older inventory.db" above.
- **`inventory active`/`processes` come back empty** — this is expected if
  you didn't ingest `active_jobs.txt`/`processes.txt` (they're optional,
  same as `apf.txt`/`sysinfo.txt`); double check the filenames are exact
  if you did generate them.
- **`inventory catalog`/`vsam` come back empty** — this is expected if you
  didn't ingest any `*catalog*.txt` file (it's optional, and always
  HLQ/pattern-scoped rather than a full dump — see
  [`../zos-extract/README.md`](../zos-extract/README.md#9-dataset-catalog-hlqpattern-scoped)).
- **`inventory vsam` shows a cluster but every field is `?`** — the
  `##LISTCAT` block's regexes didn't match your site's actual IDCAMS
  `LISTCAT ALL` report formatting; compare your `*catalog*.txt` file by eye
  against the patterns documented in `catalog_parser.py`'s module
  docstring and `tests/fixtures/sample_catalog.txt`.
- **Any `inventory racf-*` command comes back empty** — this is expected if
  you didn't ingest `racf.txt` (it's optional, and — unlike everything
  else — implementation-only for now; see
  [`../zos-extract/README.md`](../zos-extract/README.md#10-racf-security-snapshot-implementation-only--verify-authority-before-running)
  for the real authorization hurdle before you can generate one).
- **RACF fields look obviously wrong (garbled text, misaligned values)** —
  `racf_parser.py`'s byte offsets were derived from a third-party
  reference implementation, not IBM's own docs or a real unload sample
  (see "How resolution works" above). This is the single most likely place
  in the whole project for a real-system mismatch; compare your `racf.txt`
  against the offsets documented in that module's docstring.
