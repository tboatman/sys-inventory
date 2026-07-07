# inventory

Off-host half of the pipeline: parses the text dumped by `zos-extract/`
(or, for domains with no standalone `zos-extract/python` script yet --
USS mounted filesystems, JES2's own initialization parameters, VTAM
major-node status/start options, TCP/IP home addresses/PROFILE.TCPIP, SMS
storage groups/storage classes/management classes, the active WLM policy
name/mode, deepened DB2 packages/plans, WLM service-class/goal
definitions via z/OSMF, and deepened CICS DFHRPL/SIT/CSD detail -- the
`ansible/` role directly; see
[`ansible.md`](ansible.md)) and resolves each
PROCLIB/PARMLIB member's full execution path back to the SMP/E FMID that
owns each program it runs, flags whether each resolved load library is
APF-authorized, and separately inventories defined subsystems,
auto-started tasks, the LPAR/sysplex identity of the system the dump came
from, product enablement status (IFAPRDxx), a live snapshot of
currently-running jobs/tasks and USS processes, an HLQ/pattern-scoped
dataset catalog (non-VSAM attributes + VSAM cluster/component detail),
mounted USS filesystems, JES2's own initialization statements, VTAM/APPN
status, TCP/IP configuration, SMS storage groups, the active WLM
policy name/mode, deepened DB2 packages/plans, WLM service-class/goal
definitions via z/OSMF, deepened CICS resource detail (DFHRPL
load-library lineage, SIT overrides, and CSD resource definitions via
DFHCSDUP), and a RACF security snapshot (users, groups,
dataset and general-resource access —
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
  cp tests/fixtures/sample_sms.txt         /tmp/demo/sms.txt && \
  cp tests/fixtures/sample_wlm.txt         /tmp/demo/wlm.txt && \
  cp tests/fixtures/sample_db2_catalog.txt /tmp/demo/db2_catalog.txt && \
  cp tests/fixtures/sample_wlm_zosmf.txt   /tmp/demo/wlm_zosmf.txt && \
  cp tests/fixtures/sample_cics_deepening.txt /tmp/demo/cics_deepening.txt
inventory --db /tmp/demo/demo.db ingest /tmp/demo
```

(The fixture files aren't named the way `zos-extract/` would actually name
them — see the [naming convention cheat
sheet](zos-extract.md#naming-convention-cheat-sheet) — this is
just renaming them into that shape for a quick demo.)

## Usage against real data

1. Run `zos-extract/` on the target z/OS system and download its output
   (PROCLIB/PARMLIB dumps, IEFSSNxx/COMMNDxx dumps, IFAPRDxx dumps,
   LNKLST list, APF list, system identity dump, SMP/E LIST reports, active
   jobs/processes snapshot, dataset catalog dumps, and — implementation
   only, see its README section — a RACF security snapshot) into one local
   directory — see
   [`zos-extract.md`](zos-extract.md) for the exact
   file naming and how to produce each file. Twenty-four more files —
   `uss_mounts.txt` (mounted USS filesystems), `jes2parm.txt`/
   `NN_jes2parm.txt` (JES2's own initialization statements), `vtam.txt`
   (VTAM major-node status and start options, incl. APPN
   enablement/role), `tcpip.txt` (TCP/IP home addresses and, if
   configured, `PROFILE.TCPIP` text), `sms.txt` (SMS storage groups),
   `wlm.txt` (the active WLM
   policy name/mode, first cut only), `db2_catalog.txt` (installed DB2
   packages/plans, opt-in), `wlm_zosmf.txt` (WLM service-class/goal
   definitions via z/OSMF's REST API, opt-in, raw JSON text despite the
   `.txt` name), `cics_deepening.txt` (deepened CICS DFHRPL/SIT/CSD
   detail, opt-in), `*.smpzones.txt` (SMP/E zone census via LIST
   GLOBALZONE, one per CSI), `parmlib_snapshot.txt` (the live PARMLIB
   concatenation via an explicit, always-run `D PARMLIB` capture,
   distinct from the implicit one `zos_extract_parmlibs` auto-discovery
   uses internally), `ieasys_snapshot.txt` (the active IEASYSxx
   member(s)' actual `KEYWORD=value` content — the real system parameters
   `D PARMLIB` itself can't show, since it only reports the PARMLIB
   dataset search order), `bpxprm_snapshot.txt` (the active BPXPRMxx
   member(s) — z/OS UNIX/OMVS configuration, named by IEASYSxx's own
   `OMVS=` keyword), `devsup_snapshot.txt` (the active DEVSUPxx
   member(s) — device support definitions, named by IEASYSxx's own
   `DEVSUP=` keyword; the first of the further active-PARMLIB-member
   domains from `doc/TODO.md` "9.2", built on the same generalized
   ansible fetch worker `ieasys_snapshot.txt`/`bpxprm_snapshot.txt` now
   share), `opt_snapshot.txt` (the active IEAOPTxx member(s) — system
   tuning/options parameters, named by IEASYSxx's own `OPT=` keyword),
   `clock_snapshot.txt` (the active CLOCKxx member(s) — TOD
   clock/timezone parameters, named by IEASYSxx's own `CLOCK=` keyword),
   `autor_snapshot.txt` (the active AUTORxx member(s) — WTOR auto-reply
   policy, named by IEASYSxx's own `AUTOR=` keyword; the first of the
   Category C, statement-oriented further active-PARMLIB-member
   domains), `sched_snapshot.txt` (the active SCHEDxx member(s) —
   PPT/Program Properties Table entries, named by IEASYSxx's own `SCH=`
   keyword), `couple_snapshot.txt` (the active COUPLExx member(s) —
   XCF/sysplex couple dataset definitions, named by IEASYSxx's own
   `COUPLE=` keyword), `grsrnl_snapshot.txt` (the active GRSRNLxx
   member(s) — global resource serialization resource name lists, named
   by IEASYSxx's own `GRSRNL=` keyword), `smf_snapshot.txt` (the active
   SMFPRMxx member(s) — SMF recording configuration, named by
   IEASYSxx's own `SMF=` keyword), `ios_snapshot.txt` (the active
   IECIOSxx member(s) — I/O related parameters, named by IEASYSxx's own
   `IOS=` keyword), `consol_snapshot.txt` (the active CONSOLxx
   member(s) — MCS/EMCS console definitions, named by IEASYSxx's own
   `CON=` keyword), `igdsms_snapshot.txt` (the active IGDSMSxx
   member(s) — SMS base configuration, named by IEASYSxx's own `SMS=`
   keyword — deliberately distinct naming from the live
   `sms`/`SmsStorageGroup` domain below, see `inventory igdsms`'s own
   section), `izuprm_snapshot.txt` (the active IZUPRMxx member(s) —
   z/OSMF configuration, named by IEASYSxx's own `IZU=` keyword), and
   `diag_snapshot.txt` (the active DIAGxx member(s) — diagnostic
   function defaults, named by IEASYSxx's own `DIAG=` keyword)
   — have no standalone `zos-extract/python` script
   yet and are only produced by the `ansible/` role's
   `uss_mounts`/`jes2parm`/`vtam`/`tcpip`/`sms`/`wlm`/`db2`/`wlm_zosmf`/`cics`/
   `smpe_zone_discovery`/`parmlib_snapshot`/`ieasys_snapshot`/`bpxprm_snapshot`/
   `devsup_snapshot`/`opt_snapshot`/`clock_snapshot`/`autor_snapshot`/
   `sched_snapshot`/`couple_snapshot`/`grsrnl_snapshot`/`smf_snapshot`/
   `ios_snapshot`/`consol_snapshot`/`igdsms_snapshot`/`izuprm_snapshot`/
   `diag_snapshot`
   tags; see [`ansible.md`](ansible.md)'s Layout
   section. `wlm_zosmf.txt` specifically comes from
   `playbooks/wlm_zosmf.yml`, a standalone entry point, not `site.yml`/
   `interactive.yml` — see that README's own section on it. The original
   nine (everything except `*.smpzones.txt`/`parmlib_snapshot.txt`/
   `ieasys_snapshot.txt`/`bpxprm_snapshot.txt`) are
   implementation-only, same caveat as RACF below — not yet validated
   against a real system's actual command/API output. `db2_catalog.txt`
   and especially `wlm_zosmf.txt` carry the strongest versions of that
   caveat, alongside `ios_snapshot.txt` (built from documented statement
   syntax only, no real sample yet -- `bpxprm_snapshot.txt`/
   `devsup_snapshot.txt`/`opt_snapshot.txt`/`clock_snapshot.txt`/
   `autor_snapshot.txt`/`sched_snapshot.txt`/`couple_snapshot.txt`/
   `grsrnl_snapshot.txt`/`smf_snapshot.txt`/`consol_snapshot.txt`/
   `igdsms_snapshot.txt`/`izuprm_snapshot.txt`/`diag_snapshot.txt` have
   since been confirmed against real members, see their own sections
   below); `cics_deepening.txt`'s own CSD-report portion is right behind
   `ios_snapshot.txt` — see their own sections below. `parmlib_snapshot.txt`
   reuses the already-confirmed LNKLST/APF 4-column reply shape, so it
   doesn't carry that caveat; `*.smpzones.txt` is CONFIRMED against a real
   `LIST GLOBALZONE` report from this site (found and fixed a real parser
   bug in the process — see `ansible.md`'s SMP/E CSI/zone section);
   `ieasys_snapshot.txt`'s underlying `KEYWORD=value`/comma-continuation
   shape is confirmed against a real IEASYSxx sample (the same content
   `discover_active_members.yml` already extracts internally, just
   narrowed to three keywords there) — see their own sections below.

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
   inventory: ingested 5 members, 2 zones, 6 resolved steps, 2 subsystems, 2 started tasks, 2 products, 0 PARMLIB concatenation datasets, 0 active IEASYSxx statements, 0 active BPXPRMxx statements, 3 active jobs, 3 processes, 2 cataloged datasets, 2 VSAM clusters, 2 RACF users, 1 RACF groups, 4 USS mounts, 8 JES2 init statements, 3 VTAM major nodes, 8 VTAM start options, 6 TCPIP home addresses, 20 TCPIP profile statements, 3 SMS storage groups, 2 DB2 packages, 1 DB2 plans, 2 WLM z/OSMF entries, 2 CICS DFHRPL entries, 3 CICS SIT overrides, 3 CICS CSD definitions, 0 SMP/E zone index entries -> /tmp/demo/demo.db
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
  step STEP1: PGM=IEFBR14 dataset=MY.SITE.LINKLIB zone=TZONE2 FMID=? CSI=EDUC.TEST.GLOBAL.CSI [APF]  [module IEFBR14 not found in zone TZONE2's FILE list]
  step NSTEP1: PGM=IGYCRCTL dataset=SYS1.LINKLIB zone=TZONE1 FMID=HLA2280 CSI=EDUC.TEST.GLOBAL.CSI [non-APF]  [resolved via STEPLIB (APPLIED)]
```

Nested `EXEC PROCNAME` steps are already flattened into this list — you
don't need to separately look up the nested PROC. `[APF]`/`[non-APF]`
shows APF authorization status (only shown as `[APF=?]` if you didn't
ingest an `apf.txt`). `CSI` is the SMP/E CSI dataset that owns the
resolved zone (shown as `?` if the ingested `*smplist*.txt` file predates
the `##CSI` sentinel line — see `inventory/smpe_parser.py`). The bracketed
text at the end of each line explains *how* that hop was resolved, or why
it couldn't be.

### `inventory trace NAME`

Full traceability for one name, tying together everything that's
otherwise spread across `started-tasks`/`active`/`lineage`: is `NAME`
defined as a `COMMNDxx` auto-start task, is it running right now, and (by
reusing the same PROCLIB-member lookup `lineage` uses — a started task's
name *is* the PROC member name per real MVS `START
procname[.identifier]` syntax) its full resolved execution path down to
the SMP/E zone/FMID/holding CSI for every step:

```
$ inventory trace CICSPROD
TRACE: CICSPROD
  defined as auto-start: S CICSPROD.CICSA  [COMMND00]
  not currently active (or no active_jobs.txt ingested)
  no PROCLIB/PARMLIB member named CICSPROD was ingested -- cannot resolve an execution path
```

This is the one command that answers "started task -> proclib -> program
-> SMP/E holding CSI" end to end without cross-referencing `started-tasks`/
`lineage` by hand. Known gap: `ssn_parser.py` doesn't yet parse the
`S task,PROC=realproc` override form of the `START` command, so a task
started that way won't join correctly by name alone — see `doc/TODO.md`
("8b").

### `inventory report [--output file.csv]`

The same information as `lineage`, but for every member at once, as CSV
(to stdout by default, or a file with `--output`):

```
$ inventory report
member,step_name,pgm,dataset,zone,fmid,csi,resolution,apf_authorized
JOBPROC,JSTEP1,SAMPMOD,MY.SITE.LINKLIB,TZONE2,USER001,EDUC.TEST.GLOBAL.CSI,resolved via JOBLIB (APPLIED),1
LNKPROC,LSTEP1,IEBGENER,SYS1.LINKLIB,TZONE1,HBB7790,EDUC.TEST.GLOBAL.CSI,resolved via LNKLST (APPLIED),0
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

### `inventory parmlib`

The live PARMLIB concatenation in search order (`D PARMLIB`), if you
ingested a `parmlib_snapshot.txt` — an explicit, always-captured
counterpart to `discover_parmlib.yml`'s own implicit `D PARMLIB` call
(only issued when `zos_extract_parmlibs` isn't already configured, and
never saved anywhere; see `ansible.md`'s Available tags section):

```
$ inventory parmlib
1  FLAGS=S VOLUME=HCD000 SYS1.COMMON.PARMLIB
2  FLAGS=S VOLUME=BES2W1 SYS3.BES2.PARMLIB
3  FLAGS=D VOLUME=BES2W1 SYS3.BES2.LOCAL.PARMLIB
```

`entry` is PARMLIB search order as MVS itself numbers it (1-based, lowest
searched first) — distinct from this project's own `zos_extract_parmlibs`
`"00"`/`"01"`/... prefix convention. Same confirmed 4-column reply shape
LNKLST/APF already use (see `parmlib_parser.py`'s module docstring), not
a fresh guess.

### `inventory ieasys`

The actual system parameters — every `KEYWORD=value` statement in the
active IEASYSxx member(s) — if you ingested an `ieasys_snapshot.txt`.
`inventory parmlib` above is *not* this: `D PARMLIB` can only report the
PARMLIB dataset search order, never any member's content, so a separate
explicit capture is needed for the real "parms" people usually mean by
that word:

```
$ inventory ieasys
CLPA=  [IEASYSBN]
CMD=(BN)  [IEASYSBN]
PROD=(BN)  [IEASYSBN]
REAL=(4096,ONLINE)  [IEASYSBN]
SQA=(16,32)  [IEASYSBN]
SSN=(BN)  [IEASYSBN]
```

`source_member` (the `[...]` suffix) matters once more than one IEASYSxx
member is concatenated (`zos_extract_ieasys_suffixes` can have more than
one entry) — each is captured separately rather than merged, since a
later member's same keyword is meant to *override* an earlier one's at
IPL time, not be indistinguishable from it. Captured generically (every
keyword found, not a hand-modeled subset) the same approach
`Jes2InitStatement`/`VtamStartOption`/`CicsSitOverride` already use —
IEASYSxx's real keyword surface is 100+ documented keywords, too many to
model individually. Reuses the exact `D PARMLIB`/discovery machinery
`discover_active_members.yml` already had internally (to pull out just
`SSN=`/`CMD=`/`PROD=`/`MSTRJCL=` for its own use, then discard) — this
just saves and generalizes what was already being fetched.

### `inventory bpxprm` (opt-in)

z/OS UNIX System Services (OMVS) configuration — every statement in the
active BPXPRMxx member(s) — if you ingested a `bpxprm_snapshot.txt`.
Named by IEASYSxx's own `OMVS=` keyword the same way `SSN=`/`CMD=`/
`PROD=`/`MSTRJCL=` name IEFSSNxx/COMMNDxx/IFAPRDxx/MSTJCLxx:

```
$ inventory bpxprm
MAXPROCSYS (3000)  [BPXPRM00]
MOUNT FILESYSTEM('OMVS.ETC.ZFS') MOUNTPOINT('/etc') TYPE(ZFS) MODE(RDWR)  [BPXPRM00]
ROOT FILESYSTEM('OMVS.ROOT.ZFS') TYPE(ZFS) MODE(RDWR)  [BPXPRM00]
TZ (EST5EDT)  [BPXPRM00]
MOUNT FILESYSTEM('ZFS.TOMMY') MOUNTPOINT('/u/tommy') TYPE(ZFS) NOAUTOMOVE  [BPXPRM01]
MOUNT FILESYSTEM('ZFS.GRB') MOUNTPOINT('/usr/lpp/grb') TYPE(ZFS)  [BPXPRM01]
```

Unlike `inventory ieasys`'s flat `KEYWORD=value` shape, a real BPXPRMxx
member is statement-oriented (`ROOT`/`MOUNT`/`FILESYSTYPE`/... spanning
several physical lines each, no continuation character — just a known
top-level statement vocabulary, same approach `tcpip-profile`'s
PROFILE.TCPIP parsing already uses) — see `bpxprm_parser.py`'s module
docstring for the full detail, including its known limitation (an
unrecognized statement keyword gets folded into the preceding
statement's operands instead of starting its own). CONFIRMED against a
real BPXPRMxx member, including a fully commented-out `MOUNT` block
(each physical line its own `/* ... */` comment) disappearing entirely
and multiple `MOUNT` statements in one member all being kept, in order
(the `BPXPRM01` rows above).

### `inventory devsup`

Device support definitions — every `KEYWORD=value` statement in the
active DEVSUPxx member(s) — if you ingested a `devsup_snapshot.txt`.
Named by IEASYSxx's own `DEVSUP=` keyword the same way `SSN=`/`CMD=`/
`PROD=`/`OMVS=`/`MSTRJCL=` name IEFSSNxx/COMMNDxx/IFAPRDxx/BPXPRMxx/
MSTJCLxx. Same flat, comma-continued shape as `inventory ieasys` (this
is the first of the further active-PARMLIB-member domains from
`doc/TODO.md` "9.2", and reuses `ieasys`'s own parsing engine directly).
CONFIRMED against a real DEVSUPxx member:

```
$ inventory devsup
COMPACT=YES  [DEVSUPBN]
VOLNSNS=YES  [DEVSUPBN]
NON_VSAM_XTIOT=YES  [DEVSUPBN]
MEDIA1=BE01  [DEVSUPBN]
...
PRIVATE=BE0F  [DEVSUPBN]
DISABLE=(SSR)  [DEVSUPBN]
```

The real member also exercised a shape `inventory ieasys`'s own
confirmed sample never did — a keyword taking a parenthesized value
with no `=` at all (`DISABLE(SSR)` above) — now handled explicitly by
`parmlib_engines.split_params()` rather than being swallowed whole as
one bare keyword name.

### `inventory opt`

System tuning/options parameters — every `KEYWORD=value` statement in
the active IEAOPTxx member(s) — if you ingested an `opt_snapshot.txt`.
Named by IEASYSxx's own `OPT=` keyword. Second of the further
active-PARMLIB-member domains from `doc/TODO.md` "9.2", same flat
shape and parsing engine as `inventory ieasys`/`inventory devsup`.
CONFIRMED against a real IEAOPTxx member (`ERV=500`):

```
$ inventory opt
CNTRYCD=1  [IEAOPTBN]
ERV=500  [IEAOPTBN]
MCCAFCTH=90  [IEAOPTBN]
MCCFXEPR=YES  [IEAOPTBN]
```

### `inventory clock`

TOD clock/timezone parameters — every bare `KEYWORD value` statement in
the active CLOCKxx member(s) — if you ingested a `clock_snapshot.txt`.
Named by IEASYSxx's own `CLOCK=` keyword. Category G (not B) from
`doc/TODO.md` "9.2" — CONFIRMED against a real CLOCKxx member to be
space-separated, one keyword per line, with no `=`, comma, or
continuation character, unlike `inventory ieasys`/`inventory devsup`/
`inventory opt`, so it has its own small parser (`clock_parser.py`):

```
$ inventory clock
OPERATOR=NOPROMPT  [CLOCKBN]
TIMEZONE=W.05.00.00  [CLOCKBN]
ETRMODE=NO  [CLOCKBN]
ETRZONE=NO  [CLOCKBN]
ETRDELTA=1  [CLOCKBN]
STPMODE=NO  [CLOCKBN]
```

(the `KEYWORD=value` display above is just this CLI's own consistent
output convention across all `inventory <name>` commands — it doesn't
reflect CLOCKxx's real on-disk syntax, which is space-separated.)

### `inventory autor`

WTOR auto-reply policy — every statement in the active AUTORxx
member(s) — if you ingested an `autor_snapshot.txt`. Named by IEASYSxx's
own `AUTOR=` keyword. First of the Category C (statement-oriented)
domains from `doc/TODO.md` "9.2" — unlike `inventory ieasys`/`inventory
devsup`/`inventory opt`/`inventory clock`'s flat shape, a real AUTORxx
member is statement-oriented (`NOTIFYMSGS(...)` and `MSGID(msgid)
DELAY(nnS) REPLY(text)`/`NOAUTORREPLY`), the same shape `inventory
bpxprm` has, so this reuses that parsing engine:

```
$ inventory autor
MSGID (ARC0380A) DELAY(60S) REPLY(CANCEL)  [AUTORBN]
MSGID (IEE094D) NOAUTORREPLY  [AUTORBN]
NOTIFYMSGS (CONSOLE)  [AUTORBN]
MSGID (IEFC166D) DELAY(2S) REPLY(Y)  [AUTOR01]
```

**Not** Automatic Restart Management policy, despite the superficial
name resemblance. The `NOTIFYMSGS`/`MSGID` statement vocabulary is
confirmed against IBM's z/OS MVS Initialization and Tuning Reference,
and `autor_parser.py` is now CONFIRMED against a real AUTORxx member
(the `AUTOR01` row above) — including a multi-line `/* ... */` comment
block preceding the live statement (stripped cleanly) and the full
operand list on one physical line rather than spread across
continuation lines.

### `inventory sched`

PPT (Program Properties Table) entries — every `PPT PGMNAME(name) ...`
statement in the active SCHEDxx member(s) — if you ingested a
`sched_snapshot.txt`. Named by IEASYSxx's own `SCH=` keyword. Second of
the Category C domains from `doc/TODO.md` "9.2" — a real SCHEDxx member
is a repeated single statement shape, so every flag/sub-parameter after
`PGMNAME` (`NOSWAP`/`PRIV`/`SYST`/`KEY(n)`/`AFF(...)`/...) is captured
generically as raw operand text rather than modeled individually:

```
$ inventory sched
PPT PGMNAME(IEDQTCAM) NOSWAP KEY(1) SYST  [SCHEDBN]
PPT PGMNAME(ZWESIS01) KEY(4) NOSWAP  [SCHEDBN]
PPT PGMNAME(XGMMAIN) CANCEL KEY(4) NOSYST PRIV NOSWAP DSI PASS AFF(NONE) NOPREF  [SCHEDBN]
PPT PGMNAME(OSZSIRIS) KEY(0) SYST  [SCHED01]
PPT PGMNAME(OSZMOSYS) KEY(0) NOCANCEL NOSWAP SYST  [SCHED01]
```

CONFIRMED against a real SCHEDxx member (the `SCHED01` rows above) —
including a run of PPT entries where every physical line, statement
line and every continuation line alike, carries its own trailing
`/* ... */` comment, stripped cleanly without bleeding into the next
entry.

### `inventory couple`

XCF/sysplex couple dataset definitions — every `COUPLE`/`DATA TYPE(...)`
statement in the active COUPLExx member(s) — if you ingested a
`couple_snapshot.txt`. Named by IEASYSxx's own `COUPLE=` keyword — note
the real member name keeps the trailing E (`COUPLExx`, e.g. `COUPLE00`),
unlike `MSTRJCL=` (which drops its `R` to name `MSTJCLxx`). Third of the
Category C domains from `doc/TODO.md` "9.2":

```
$ inventory couple
COUPLE SYSPLEX(PLEX1) PCOUPLE(SYS1.XCF.CDS01,VOL001) ACOUPLE(SYS1.XCF.CDS02,VOL002)  [COUPLE00]
DATA TYPE(LOGR) PCOUPLE(SYS1.LOGR.CDS01,VOL001) ACOUPLE(SYS1.LOGR.CDS02,VOL002)  [COUPLE00]
COUPLE SYSPLEX(&SYSPLEX) PCOUPLE(SYS1.ADCDPL.CDS01) ACOUPLE(SYS1.ADCDPL.CDS02)  [COUPLE01]
DATA TYPE(CFRM) PCOUPLE(SYS1.ADCDPL.CFRM.CDS01) ACOUPLE(SYS1.ADCDPL.CFRM.CDS02)  [COUPLE01]
DATA TYPE(LOGR) PCOUPLE(SYS1.ADCDPL.LOGR.CDS01) ACOUPLE(SYS1.ADCDPL.LOGR.CDS02)  [COUPLE01]
DATA TYPE(BPXMCDS) PCOUPLE(SYS1.ADCDPL.OMVS.CDS01) ACOUPLE(SYS1.ADCDPL.OMVS.CDS02)  [COUPLE01]
DATA TYPE(WLM) PCOUPLE(SYS1.ADCDPL.WLM.CDS01) ACOUPLE(SYS1.ADCDPL.WLM.CDS02)  [COUPLE01]
```

CONFIRMED against a real COUPLExx member (the `COUPLE01` rows above) --
one `COUPLE` statement followed by four distinct `DATA TYPE(...)`
statements, all kept in order rather than collapsed.

### `inventory grsrnl`

Global resource serialization resource name lists — every `RNLDEF`
statement in the active GRSRNLxx member(s) — if you ingested a
`grsrnl_snapshot.txt`. Named by IEASYSxx's own `GRSRNL=` keyword.
Fourth of the Category C domains from `doc/TODO.md` "9.2":

```
$ inventory grsrnl
RNLDEF RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSIGGV2) RNAME('ICFCAT.CAT1.SHARED')  [GRSRNL00]
RNLDEF RNL(INCL) TYPE(GENERIC) QNAME(SYSDSN)  [GRSRNL00]
RNLDEF RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSDSN) RNAME(PASSWORD)  [GRSRNL01]
RNLDEF RNL(EXCL) TYPE(SPECIFIC) QNAME(SYSDSN) RNAME(SYS1.BRODCAST)  [GRSRNL01]
```

CONFIRMED against a real (partial) GRSRNLxx member (the `GRSRNL01` rows
above) — including a shape not in the original documented sample:
`QNAME(...)`/`RNAME(...)` each on their own continuation line rather
than sharing the `RNLDEF` line, with blank lines separating entries.

### `inventory smf`

SMF (System Management Facilities) recording configuration — every
statement in the active SMFPRMxx member(s) — if you ingested a
`smf_snapshot.txt`. Named by IEASYSxx's own `SMF=` keyword — note the
real member name is `SMFPRMxx` (e.g. `SMFPRM00`), not `SMFxx`. Fifth of
the Category C domains from `doc/TODO.md` "9.2":

```
$ inventory smf
ACTIVE   [SMFPRM00]
DSNAME (SYS1.MAN1,SYS1.MAN2)  [SMFPRM00]
NOPROMPT   [SMFPRM00]
SUBSYS (STC,NOTYPE(17))  [SMFPRM00]
SYS (NOTYPE(14:19,62:69,99))  [SMFPRM00]
REC (PERM)  [SMFPRM01]
MAXDORM (3000)  [SMFPRM01]
STATUS (010000)  [SMFPRM01]
JWT (0400)  [SMFPRM01]
SID (&SYSNAME(1:4))  [SMFPRM01]
LISTDSN   [SMFPRM01]
INTVAL (05)  [SMFPRM01]
SYNCVAL (05)  [SMFPRM01]
AUTHSETSMF   [SMFPRM01]
```

CONFIRMED against a real SMFPRMxx member (the `SMFPRM01` rows above) --
its statement vocabulary grew from a **partial** `ACTIVE`/`DSNAME`/
`PROMPT`/`NOPROMPT`/`SYS`/`SUBSYS` to also include `REC`/`MAXDORM`/
`STATUS`/`JWT`/`SID`/`LISTDSN`/`INTVAL`/`SYNCVAL`/`AUTHSETSMF`, all of
which the real member exercised and which would otherwise have been
silently folded into the preceding statement's operands. SMFPRMxx's
full documented keyword surface may still be larger than this list; an
unrecognized statement keyword still folds into the preceding
statement's operands instead of starting its own.

### `inventory ios` (not yet production-validated)

I/O related parameters — every `MIH`/`HOTIO`/`TERMINAL`/`FICON`/
`STORAGE`/`CAPTUCB`/`EKM`/`RECOVERY`/`CTRACE`/`MIDAW`/`HYPERPAV`/
`HYPERWRITE`/`ZHPF` statement in the active IECIOSxx member(s) — if you
ingested an `ios_snapshot.txt`. Named by IEASYSxx's own `IOS=` keyword.
Sixth of the Category C domains from `doc/TODO.md` "9.2":

```
$ inventory ios
HOTIO DEV=(0100-01FF),TIME=1000  [IECIOS00]
MIH TIME=00:15:00,DEV=(0100-01FF)  [IECIOS00]
ZHPF YES  [IECIOS00]
```

**Built from IBM's z/OS MVS Initialization and Tuning Reference — not
yet checked against a real IECIOSxx member.**

### `inventory consol`

MCS/EMCS console definitions — every `INIT`/`DEFAULT`/`CONSOLE`/
`HARDCOPY` statement in the active CONSOLxx member(s) — if you ingested
a `consol_snapshot.txt`. Named by IEASYSxx's own `CON=` keyword.
Seventh of the Category C domains from `doc/TODO.md` "9.2":

```
$ inventory consol
CONSOLE DEVNUM(SMCS) AUTH(ALL) LOGON(REQUIRED) CON(N) DEL(R) MFORM(J,T) MONITOR(JOBNAMES-T) NAME(SMCS01) PFKTAB(PFKTAB1) RNUM(19) ROUTCODE(ALL) RTME(1) SEG(14)  [CONSOL00]
DEFAULT ROUTCODE(ALL)  [CONSOL00]
HARDCOPY DEVNUM(SYSLOG,OPERLOG) CMDLEVEL(CMDS) ROUTCODE(ALL)  [CONSOL00]
INIT CMDDELIM(") MLIM(1500) APPLID(SMCS&SYSCLONE.) MONITOR(DSNAME) MPF(00) PFK(00) RLIM(10) UEXIT(N) CNGRP(00) AMRF(N)  [CONSOL00]
```

CONFIRMED against a real CONSOLxx member: multiple `CONSOLE` statements
(one per device), a `CONSOLE` statement whose first keyword(s) shared
the `CONSOLE` line itself rather than starting on a continuation line,
and an `INIT` statement whose `CMDDELIM(")` value is itself a literal
quote character inside the parens — all handled correctly with no code
change needed. **Partial statement vocabulary**: only `INIT`, `DEFAULT`,
`CONSOLE`, and `HARDCOPY` were exercised by the confirming member —
CONSOLxx's full documented statement surface may still be larger (e.g.
`ALTGRP`, `CNGRP`, `MSCOPE`, `SPECIAL`).

### `inventory igdsms`

SMS (Storage Management Subsystem) base configuration — the single `SMS
ACDS(...) COMMDS(...) ...` statement in the active IGDSMSxx member(s) —
if you ingested an `igdsms_snapshot.txt`. Named by IEASYSxx's own `SMS=`
keyword. Eighth of the Category C domains from `doc/TODO.md` "9.2".

**Deliberately distinct from `inventory sms-storgrps`** (the *live* `D
SMS,STORGRP` console-command snapshot, a completely different
dimension): this command, its model (`IgdsmsStatement`), its store
table (`igdsms_statements`), and its ingest source
(`igdsms_snapshot.txt`) all use the `igdsms` name instead of `sms`
throughout, specifically because `igdsms_snapshot.txt` contains `sms`
as a substring and would otherwise have been silently picked up by
`inventory sms-storgrps`'s own ingest glob (`*sms*.txt`) — fixed by
excluding `*igdsms*` matches there, the same precedent `*wlm*`/
`*wlm_zosmf*` already established:

```
$ inventory igdsms
SMS ACDS(SYS1.ZDT3.ACDS) COMMDS(SYS1.ZDT3.COMMDS) INTERVAL(15) DINTERVAL(150) REVERIFY(NO) ACSDEFAULTS(NO) OAMPROC(OAM) TRACE(ON) SIZE(128K) TYPE(ALL) JOBNAME(*) ASID(*) SELECT(ALL)  [IGDSMSTB]
```

CONFIRMED against a real IGDSMSxx member -- one `SMS` statement
spanning 13 continuation lines, folded correctly with no code change
needed.

### `inventory izuprm`

z/OSMF (z/OS Management Facility) configuration statements
(`HOSTNAME`/`JAVA_HOME`/`KEYRING_NAME`/`SEC_GROUPS`/`WLM_CLASSES`/
`PLUGINS`/...) from the active IZUPRMxx member(s), if you ingested an
`izuprm_snapshot.txt`. Named by IEASYSxx's own `IZU=` keyword. Ninth of
the Category C domains from `doc/TODO.md` "9.2":

```
$ inventory izuprm
HOSTNAME ('s0w1.dal-ebis.ihost.com')  [IZUPRM00]
JAVA_HOME ('/usr/lpp/java/J11.0_64')  [IZUPRM00]
KEYRING_NAME ('IZUKeyring.IZUDFLT')  [IZUPRM00]
CSRF_SWITCH (ON)  [IZUPRM00]
CSRF_SWITCH (OFF)  [IZUPRM00]
WLM_CLASSES DEFAULT(IZUGHTTP) LONG_WORK(IZUGWORK)  [IZUPRM00]
```

CONFIRMED against a real IZUPRM00 member, which exercised two shapes no
earlier Category C domain had: a quoted value spanning two physical
lines (`LOGGING(...)`, per the member's own documented continuation
rule) and a repeated statement keyword (`CSRF_SWITCH` appears twice
above, both kept in order rather than collapsed to the last one) — both
handled correctly with no code change needed. IZUPRMxx's full documented
statement surface is likely larger than what's captured here (this
reflects one shop's real member, not IBM's complete reference).

### `inventory diag`

Diagnostic function defaults (common storage tracking, GETMAIN/
FREEMAIN/storage trace) from the active DIAGxx member(s), if you
ingested a `diag_snapshot.txt`. Named by IEASYSxx's own `DIAG=` keyword.
Tenth, and for now last, of the Category C domains from `doc/TODO.md`
"9.2":

```
$ inventory diag
VSM TRACK CSA(ON) SQA(ON)  [DIAG00]
VSM TRACE GETFREE(OFF)  [DIAG00]
```

CONFIRMED against a real DIAG00 member, which exercised a wrinkle no
earlier Category C domain's confirming member had: traditional MVS
PARMLIB sequence numbers in columns 73-80 of every physical line, sitting
on the *same* line as real statement content (unlike a `/* ... */`
comment, which `strip_comments()` already handles regardless of where it
falls). `diag_parser.py` strips that trailing field before handing lines
to `parmlib_engines.statement_engine()`.

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
[`zos-extract.md`](zos-extract.md#9-dataset-catalog-hlqpattern-scoped)
for how to run `extrcat.py`. `?` means that field didn't match anything in
the captured `LISTCAT` report (see "How resolution works" below).

### RACF security snapshot (implementation only, not yet production-validated)

Seven commands, if you ingested a `racf.txt` — see
[`zos-extract.md`](zos-extract.md#10-racf-security-snapshot-implementation-only--verify-authority-before-running)
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

### `inventory uss-mounts` (confirmed against a real reply)

Every mounted USS filesystem, if you ingested a `uss_mounts.txt` — see
`ansible/roles/zos_extract/tasks/uss_mounts.yml` for how it's produced.
**Confirmed against a real `D OMVS,F` reply** (a follow-up round provided
one) — see `uss_mounts_parser.py`'s module docstring for the real shape
and the one thing that differed from the original guess (`NAME=`/`PATH=`
land on separate continuation lines in practice).

```
$ inventory uss-mounts
/  NAME=OMVS.ROOT.ZFS TYPE=ZFS DEVICE=117 STATUS=ACTIVE MODE=RDWR
/etc  NAME=OMVS.ETC.ZFS TYPE=ZFS DEVICE=116 STATUS=ACTIVE MODE=RDWR
/legacy  NAME=OMVS.LEGACY.HFS TYPE=HFS DEVICE=115 STATUS=ACTIVE MODE=READ
```

### `inventory jes2parm` (confirmed against real init-deck members)

Every JES2 initialization statement, if you ingested a `jes2parm.txt` —
JES2's own PARMLIB-equivalent init deck, distinct from both SYS1.PARMLIB's
IEFSSNxx/COMMNDxx and the JES2 *PROCLIB* concatenation `subsystems`/
`report` already cover. Captured generically (statement name + optional
subscript + a raw keyword=value map), not modeled per statement type — see
`Jes2InitStatement` in `models.py`. **Confirmed against two real init-deck
members on 2026-07-02** (`JES2PARM` and the `JES2NJE` member it pulls in
via an `INCLUDE` statement) — the real members are a site copy of IBM's
own HASPPARM-derived template, comments and all, which needed a real
parser fix, not just re-flagging: `/* ... */` comments trailing on the
same line as real content, and comments spanning multiple physical lines
(decorative section-divider boxes), weren't stripped by the original
"skip a line that's *entirely* a comment" check — see
`jes2parm_parser.py`'s module docstring for the full detail.

```
$ inventory jes2parm
CKPTDEF  CKPT1=(DSNAME=SYS1.BES2.HASPCKPT, VOLSER=BES2W1, INUSE=YES),DUPLEX=ON  [JES2PARM]
CKPTSPACE  BERTNUM=6500,BERTWARN=80  [JES2PARM]
FSS(PRINTOFF)    [JES2PARM]
INCLUDE  DSNAME=SYS1.BES2.PARMLIB(JES2NJE),VOLSER=BES2W1  [JES2PARM]
INIT(1)  NAME=1,CLASS=QE,START=  [JES2PARM]
NETSRV(1)  SOCKET=LOCAL  [JES2NJE]
NODE(1)  NAME=SYSP,PATHMGR=NO,NETSRV=1  [JES2NJE]
SOCKET(SYSP)  IPADDR=SYSP.BMC.COM,PORT=175,NODE=1  [JES2NJE]
```

### `inventory vtam-majnodes` / `inventory vtam-options` (both confirmed against real replies)

VTAM major-node status (`D NET,MAJNODES`) and start options (`D
NET,VTAMOPTS`), if you ingested a `vtam.txt`. `vtam-options` is where
one path to APPN coverage lives: rather than a dedicated `nodetype`/
`cpname` field, every `KEYWORD = VALUE` pair VTAM's start-option display
exposes is captured generically (`VtamStartOption` in `models.py`) — look
for the `NODETYPE`/`CPNAME` rows to see whether APPN is enabled and as
what role (NN/EN/LEN vs. subarea-only). **Both are now confirmed against
real replies** (across two follow-up rounds) — the real per-row/per-line
shapes differed from the original guesses in a few places, documented in
full in `vtam_parser.py`'s module docstring, including one small,
confirmed limitation: a couple of VTAMOPTS keywords (`HPRPST`,
`IQDIOSTG`) have two-token values, of which only the first token is
captured — doesn't affect `NODETYPE`/`CPNAME` or the vast majority of
keywords.

```
$ inventory vtam-majnodes
APPLMAJ  STATUS=INACT
NCPMAJ  STATUS=ACTIV
VTAMLST  STATUS=ACT/S

$ inventory vtam-options
AIMON=(EQDIO,IQDIO,ISM,QDIO,ROCE)
ALSREQ=NO
API64R=YES
CPNAME=NN01
HPRPST=LOW
NETID=USIBMSC
NODETYPE=NN
SSCPID=1
```

### `inventory vtam-topology` (confirmed against a real reply)

The APPN topology database summary (`D NET,TOPO`), if you ingested a
`vtam.txt` — a single record (`VtamTopologySummary` in `models.py`, same
shape as `sysinfo`/`wlm`), not a list. **Unlike every other VTAM/TCPIP
dimension above, this one's parsing is confirmed against a real reply**,
provided in a follow-up round after VTAM was first implemented — see
`vtam_parser.py`'s module docstring for the exact message IDs
(`IST1306I`/`IST1307I`/`IST1781I`/`IST1785I`) it anchors on. Its real
shape turned out to be counts of known adjacent/NN/EN nodes plus
checkpoint/garbage-collection metadata, not a list of individual known
nodes by name — the original assumption that led to skipping this
command entirely in an earlier round.

```
$ inventory vtam-topology
LAST CHECKPOINT: NONE
ADJ=1 NN=2 EN=0 SERVED EN=0 CDSERVR=0 ICN=0 BN=0
INITDB CHECKPOINT DATASET: NONE
LAST GARBAGE COLLECTION: 01/01/26 00:00:00
```

If you didn't ingest a `vtam.txt`, or it didn't contain a `##TOPO` block,
this prints `no VTAM topology summary ingested` and exits with a
non-zero status — same as `inventory sysinfo`/`inventory wlm`.

### `inventory tcpip-home` / `inventory tcpip-profile` (both confirmed against real replies)

TCP/IP home addresses (`D TCPIP,,NETSTAT,HOME`, always captured) and
`PROFILE.TCPIP` configuration statements (only if
`zos_extract_tcpip_profile_dsn` was configured), if you ingested a
`tcpip.txt`. `tcpip-profile` rows are captured generically (statement
name + raw operand text, `TcpipProfileStatement` in `models.py`) since
`PROFILE.TCPIP` syntax is positional (`DEVICE`/`LINK`/`HOME`/`PORT` ...),
not uniform `KEYWORD=VALUE` — see `tcpip_parser.py`'s module docstring.
**`tcpip-home` is confirmed against a real reply (2026-07-02)** — the
real HOME ADDRESS LIST mixes legacy `LINKNAME:` rows with OSA-Express
QDIO `INTFNAME:` rows, and each entry carries a `FLAGS:` line marking
the stack's primary home address, shown as `(PRIMARY)` below.
**`tcpip-profile` is confirmed against a real member too, also
2026-07-02** — and needed a real redesign, not just regex tuning: real
statements like `INTERFACE`/`PORT`/`AUTOLOG`/`BEGINROUTES`/`SMFCONFIG`
span multiple physical lines (continuation sub-parameters, or whole
indented tables like `PORT`'s port-reservation list), all folded into
that one statement's `operands` — see `tcpip_parser.py`'s module
docstring for exactly how.

```
$ inventory tcpip-home
EZASAMEMVS  10.1.1.1
EZAXCFS1  10.1.1.1
HPRIP  10.1.1.1
LOOPBACK  127.0.0.1
LOOPBACK6  ::1
QDIOLE2  10.1.1.2  (PRIMARY)

$ inventory tcpip-profile
ARPAGE 20  [TCPIP.TCPPARMS(PROFILE1)]
AUTOLOG FTPD TN3270  [TCPIP.TCPPARMS(PROFILE1)]
BEGINROUTES ROUTE 10.1.1.0/24 = QDIOLE2 MTU 1500 ROUTE DEFAULT 10.1.1.254 QDIOLE2 MTU DEFAULTSIZE  [TCPIP.TCPPARMS(PROFILE1)]
ENDAUTOLOG   [TCPIP.TCPPARMS(PROFILE1)]
ENDROUTES   [TCPIP.TCPPARMS(PROFILE1)]
GLOBALCONFIG NOTCPIPSTATISTICS  [TCPIP.TCPPARMS(PROFILE1)]
INTERFACE QDIOLE2 DEFINE IPAQENET IPADDR 10.1.1.2/24 PORTNAME QDIOE2  [TCPIP.TCPPARMS(PROFILE1)]
INTERFACE HPRIP DEFINE VIRTUAL IPADDR 10.1.1.1  [TCPIP.TCPPARMS(PROFILE1)]
IPCONFIG DATAGRAMFWD  [TCPIP.TCPPARMS(PROFILE1)]
IPCONFIG DYNAMICXCF 10.1.1.1/24 2  [TCPIP.TCPPARMS(PROFILE1)]
PORT 7 UDP MISCSERV 7 TCP MISCSERV 21 TCP FTPD1 23 TCP TN3270  [TCPIP.TCPPARMS(PROFILE1)]
SACONFIG ENABLED COMMUNITY public AGENT 161  [TCPIP.TCPPARMS(PROFILE1)]
SACONFIG OSAENABLED OSASF 721  [TCPIP.TCPPARMS(PROFILE1)]
SMFCONFIG TYPE118 TCPINIT TCPTERM FTPCLIENT TN3270CLIENT TCPIPSTATISTICS  [TCPIP.TCPPARMS(PROFILE1)]
SMFCONFIG TYPE119 DVIPA FTPCLIENT IFSTATISTICS IPSECURITY PORTSTATISTICS PROFILE  [TCPIP.TCPPARMS(PROFILE1)]
SOMAXCONN 10  [TCPIP.TCPPARMS(PROFILE1)]
START QDIOLE2  [TCPIP.TCPPARMS(PROFILE1)]
TCPCONFIG TTLS  [TCPIP.TCPPARMS(PROFILE1)]
TCPCONFIG TCPSENDBFRSIZE 16K TCPRCVBUFRSIZE 16K SENDGARBAGE FALSE  [TCPIP.TCPPARMS(PROFILE1)]
UDPCONFIG RESTRICTLOWPORTS  [TCPIP.TCPPARMS(PROFILE1)]
```

### `inventory sms-storgrps` (confirmed against a real reply)

SMS storage groups, their type, per-system status, and volumes
(`D SMS,STORGRP(ALL),LISTVOL`), if you ingested an `sms.txt`.

**Storage classes and management classes (`sms-storclas`/`sms-mgmtclas`)
were removed entirely** — `D SMS,SC(*)`/`D SMS,MC(*)` were confirmed
INVALID against a real system, and there turns out to be no console
`D`-command for either at all (confirmed against IBM's own `D SMS`
syntax reference — this is a bigger version of the same "needs ISMF, not
a `D`-command" limitation already documented for ACS routine *source*,
now known to apply to the class definitions themselves too). See
`ansible.md`'s SMS section for the full detail.

**`sms-storgrps` is confirmed against a real reply**, and the real shape
was different enough from the original guess that the output changed:
`status` is now a raw per-system symbol sequence (e.g. `+ +`, not a
decoded `ENABLE`/`DISABLE` word), and a new `TYPE` field
(`POOL`/`TAPE`/etc) was added. Volumes come from a separate table in the
real reply, keyed back to each group by name — see `sms_parser.py`'s
module docstring for the full before/after.

```
$ inventory sms-storgrps
SG1  TYPE=POOL  STATUS=+ +  VOLUMES=VOL001,VOL002
TAPEGRP  TYPE=TAPE  STATUS=+ +  VOLUMES=?
SG2  TYPE=POOL  STATUS=+ -  VOLUMES=VOL010
```

### `inventory wlm` (first cut only, confirmed against a real reply)

The single active WLM policy record (`D WLM`), if you ingested a
`wlm.txt` — just the policy name and its mode. Full service-class/goal/
resource-group definitions aren't captured here; those need the z/OSMF
WLM REST API, a materially bigger follow-up. **Confirmed against a real
system, and the fix needed was bigger than a formatting tweak: the
originally-guessed command, `D WLM,POLICY`, doesn't exist at all — a real
system rejected the `POLICY` keyword outright. The real command is bare
`D WLM`; `mode` is inferred as `GOAL` whenever a policy name is found
(the real reply never contains a `MODE=` token — see `wlm_parser.py`'s
module docstring for why that's a documented inference, not a guess).**

```
$ inventory wlm
POLICY: PROD1
MODE: GOAL
```

If you didn't ingest a `wlm.txt`, this prints `no WLM policy ingested`
and exits with a non-zero status — same as `inventory sysinfo`.

### `inventory db2-packages` / `inventory db2-plans` (opt-in, the most speculative *console/MVS-program* dimension, not yet production-validated)

Installed DB2 packages (`SYSIBM.SYSPACKAGE`) and plans (`SYSIBM.SYSPLAN`),
if you ingested a `db2_catalog.txt` — deepens `db2.yml`'s "is a DB2
address space up right now" live heuristic with real catalog content, via
a read-only DSNTEP2 batch SQL query. **This is the most speculative
console/MVS-program-based dimension in the pipeline** (`wlm-zosmf` below
is more speculative still, being a different transport entirely): beyond
the reply not being checked against a real system, DSNTEP2's exact
authorization/PLAN/STEPLIB requirements themselves vary by site DB2
setup — see `db2_catalog_parser.py`'s module docstring for the full
caveat, including what to check first if a real run's report layout
doesn't match the simple whitespace-split row parsing used here.

```
$ inventory db2-packages
PKG1  CREATOR=COLLID1 BINDTIME=2024-01-15-10.30.00.000000  [DB2A]
PKG2  CREATOR=COLLID2 BINDTIME=2024-02-20-11.15.30.000000  [DB2A]

$ inventory db2-plans
PLAN01  CREATOR=SYSADM BINDTIME=2023-11-01-09.00.00.000000  [DB2A]
```

### `inventory wlm-zosmf` (opt-in, the single most speculative dimension in the entire pipeline)

Full WLM service-class/goal/resource-group definitions fetched via
z/OSMF's REST API, if you ingested a `wlm_zosmf.txt` — deepens `wlm.txt`'s
active-policy-name/mode first cut with the actual policy content WLM
enforces. Produced only by the standalone `playbooks/wlm_zosmf.yml` entry
point (`ansible-playbook playbooks/wlm_zosmf.yml --tags wlm_zosmf`), not
`site.yml`/`interactive.yml` — see
[`ansible.md`](ansible.md)'s own section on it for
why (separate REST/HTTPS credentials, prompted at runtime rather than
stored in `hosts.yml`).

Captured maximally generically (`WlmZosmfEntry` in `models.py`: a
best-guess `name` plus the entire raw JSON object for that entry,
preserved verbatim) since **neither the z/OSMF WLM REST API's endpoint
path nor its response JSON schema is confirmed** against IBM's own
current REST API reference or a real response — there's no other
REST/JSON precedent anywhere else in this codebase to lean on either
(every other domain parses console text). See
`wlm_zosmf_parser.py`'s module docstring for exactly how loosely the
response is interpreted, and what to check/rewrite first once you have a
real response to compare against.

```
$ inventory wlm-zosmf
WLMPOL01  {"policy_name": "WLMPOL01", "description": "Standard goal-mode policy", "service_classes": [{"name": "SYSSTC", "importance": 1}, {"name": "PRODBAT", "importance": 2}]}
WLMPOL02  {"policy_name": "WLMPOL02", "description": "Backup policy"}
```

### `inventory cics-dfhrpl` / `inventory cics-sit` / `inventory cics-csd` (opt-in, not yet production-validated)

Deepened CICS resource detail, if you ingested a `cics_deepening.txt` —
distinct from `cics.txt`'s "is a CICS address space up right now"
live-activity heuristic (not currently ingested into the database at
all). See
[`ansible.md`](ansible.md#deepened-cics-resource-view-opt-in-dfhrpl-lineage--dfhcsdup-csd-definitions)
for what produces this file and why it needs explicit
`zos_extract_cics_proc` configuration rather than auto-discovery.

`cics-dfhrpl` lists DFHRPL (CICS's own load-library concatenation)
entries, zone/APF-resolved via `resolver.dataset_zone()` the same way
STEPLIB/JOBLIB/LNKLST hops already are in `lineage`/`report` above:

```
$ inventory cics-dfhrpl
CICS.SDFHLOAD  ZONE=TZONE1 [APF]  [CICSPROC]
MY.SITE.LOADLIB  ZONE=? [APF=?]  [CICSPROC]
```

`cics-sit` lists SIT (System Initialization Table) override
`KEYWORD=VALUE` pairs, captured generically (`CicsSitOverride` in
`models.py`) the same approach `VtamStartOption`/`Jes2InitStatement` use:

```
$ inventory cics-sit
APPLID=CICSA  [CICSPROC]
GRPLIST=DFHLIST  [CICSPROC]
SEC=YES  [CICSPROC]
```

`cics-csd` lists CICS resource definitions read from the CSD via a
read-only `DFHCSDUP LIST` run (`CicsCsdDefinition` in `models.py`):

```
$ inventory cics-csd
PROGRAM PROG1  GROUP=GRP1  [CICS.PROD.DFHCSD]
TRANSACTION TRAN1  GROUP=GRP1  [CICS.PROD.DFHCSD]
FILE FILE001  GROUP=GRP2  [CICS.PROD.DFHCSD]
```

**`cics-csd` is the most speculative dimension in the pipeline alongside
`db2-packages`/`db2-plans` and `wlm-zosmf`, and uniquely speculative on
two separate axes at once**: unlike those two, the *command syntax* sent
to DFHCSDUP (`LIST ALL` / `LIST LIST(name) OBJECTS`, `PARM='CSD(READONLY)'`)
is confirmed against real IBM documentation this round — but DFHCSDUP's
own LIST report *print format* (the column layout `cics_csdup_parser.py`
has to make sense of) is not, and no real sample was found while writing
this. `cics_csdup_parser.py` deliberately does the loosest, most tolerant
parsing in the whole pipeline as a result — see its module docstring for
exactly what it recognizes and what it silently skips, and treat any
count from this dimension as a floor, not a real total, until it's
checked against a real DFHCSDUP LIST report.

### `inventory zone-index` (opt-in)

SMP/E's own authoritative zone census per CSI — every zone (target/dlib)
tied to it, per its global zone's `ZONEINDEX` attribute — if you ingested
any `*smpzones*.txt` files (from `LIST GLOBALZONE`; see
`ansible/roles/zos_extract/tasks/discover_smpe_zones.yml`, tag
`smpe_zone_discovery`). Unlike `discover_smpe_csis.yml`'s naming
heuristic for *finding* a CSI, this is a real fact SMP/E reports about a
CSI you've already confirmed — no guessing involved in what it returns,
only in how the report text is parsed (see below):

```
$ inventory zone-index
DZONE1  TYPE=DLIB CSI=EDUC.TEST.DLIB.CSI  (cross-referenced from EDUC.TEST.GLOBAL.CSI)
TZONE1  TYPE=TARGET CSI=EDUC.TEST.GLOBAL.CSI
```

The "(cross-referenced from ...)" note appears when a zone's own CSI
(where it actually lives) differs from the CSI whose global zone reported
it — a real, documented SMP/E pattern where a site splits target/dlib
zones across separate physical CSI data sets, cross-referenced from one
GLOBAL zone's `ZONEINDEX` (this project's own `smpe_csi_candidates.txt`
shows exactly this shape for a couple of products: separate `.GLOBAL.CSI`/
`.TARGET.CSI`/`.DLIB.CSI` datasets).

`smpe_parser.parse_globalzone()`'s report-shape parsing is CONFIRMED
against a real `LIST GLOBALZONE` report from this site
(`MVS.GLOBAL.CSI`) — that real report exposed and fixed a genuine parser
bug (the `ZONEINDEX` line's entry-name prefix isn't always present; see
the parser's own docstring and `doc/TODO.md` "8d" for the detail).

### `inventory zones` / `inventory fmids` / `inventory zone-gaps`

A full, standalone SMP/E software inventory, populated directly from
every ingested `*smplist*.txt` — independent of lineage, so it's
queryable even for zones/FMIDs no PROCLIB step happens to reference (see
`doc/TODO.md` "8f"):

```
$ inventory zones
TZONE1 CSI=EDUC.TEST.GLOBAL.CSI  1 DDDEFs
TZONE2 CSI=EDUC.TEST.GLOBAL.CSI  1 DDDEFs

$ inventory fmids
HBB7790  zone=TZONE1 (APPLIED)
HLA2280  zone=TZONE1 (APPLIED)
USER001  zone=TZONE2 (APPLIED)
```

`zone-gaps` is the cross-reference `zone-index` above didn't have: it
compares `zone-index`'s `LIST GLOBALZONE` census (if any `*smpzones*.txt`
was ingested) against the zones actually captured via `*smplist*.txt`, and
flags any zone SMP/E itself says exists but that was never captured —
the real "find the gaps" check, not a one-off by-hand comparison:

```
$ inventory zone-gaps
inventory: no zone gaps found (every LIST GLOBALZONE zone was also captured via *smplist*.txt)
```

`smpe_parser.parse_smplist()`'s `LIST DDDEF` parsing is CONFIRMED against
a real report from this site (`MVST` target zone, `MVS.GLOBAL.CSI`, near
15M lines) — that report also exposed and fixed a genuine bug: its
section-title line reprints at the top of every page, which used to wipe
a `LIST MOD` element's in-progress FMID/LMOD linkage if a page break fell
between its LASTUPD and FMID lines (see the parser's own docstring and
`doc/TODO.md` "8g" for the detail). `LIST SYSMOD` is also CONFIRMED
against a real entry (`HBB77E0`, same zone) — TYPE=/STATUS= resolve
correctly and a page break mid-entry doesn't disturb an already-captured
status. `LIST MOD` is also CONFIRMED against a real report — and exposed
one more genuine bug: its section title actually prints as `"MODULE"`,
not `"MOD"` (despite the SMPCNTL command being `LIST MOD .`), which the
parser's section-title regex didn't originally recognize at all (see the
parser's own docstring and `doc/TODO.md` "8g"). Every `LIST DDDEF`/`MOD`/
`SYSMOD` section is now confirmed against real output from this site.

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
   The zone's owning CSI (`Zone.csi`), if known, rides along on the
   resolved step too — see the `##CSI` sentinel note below.
5. If `apf.txt` was ingested, the resolved dataset is flagged
   `apf_authorized` True/False; if `apf.txt` wasn't ingested, the flag is
   `None` (unknown) rather than defaulting to either True or False.

`resolver.dataset_zone()` is a public wrapper around the same
dataset-to-zone DDDEF matching step 3 above uses, exposed specifically so
other domains can reuse it without duplicating that logic — `cics-dfhrpl`
entries (see below) are zone/APF-resolved this way at ingest time
(`cli.py`), not by `cics_proc_parser.py` itself.

Each ingested `*smplist*.txt` file can optionally start with a `##CSI
<dsn>` sentinel line naming the CSI it was generated from (both
`zos-extract/python/smplist.py` and the `ansible/` role's
`_smplist_zone.yml` write this automatically); every `Zone` parsed from
that file is stamped with it, and it rides along into `lineage`/`report`/
`trace` as the `csi` column/field. A file with no `##CSI` line (e.g. one
captured before this existed) still parses fine — `csi` is just empty for
those zones.

A single ingest can cover more than one CSI (a real site can have
several — its own product CSIs alongside the base z/OS one;
`zos_extract_smpe_csis` is a list on the Ansible side for exactly this).
`merge_zones()` normally combines same-named zones across files, but if
two *different* CSIs both define a same-named zone (e.g. two vendor
products each with a `TZONE1`), the later one is kept under a
disambiguated `"NAME@CSI"` key instead of silently overwriting the first
— you'll see that combined name show up as `zone` in `lineage`/`report`/
`trace` output for whichever hop resolved to it. This only keeps the two
zone *entries* distinct; it does not resolve a deeper ambiguity where one
physical dataset (e.g. a shared `SYS1.LINKLIB`) is claimed by DDDEF
entries in more than one loaded CSI — `resolver.dataset_zone()` still
returns the first match it finds in that case. See `doc/TODO.md` ("8c")
for the full detail.

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
(`tcpip_parser.parse_tcpip`), SMS storage groups
(`sms_parser.parse_sms`), the WLM policy record (`wlm_parser.parse_wlm`,
a single record like `system_info`), DB2 packages/plans
(`db2_catalog_parser.parse_db2_catalog`), and WLM z/OSMF entries
(`wlm_zosmf_parser.parse_wlm_zosmf`) are likewise independent,
freshly-added dimensions with no cross-referencing yet. CICS SIT
overrides and CSD definitions (`cics_proc_parser.parse_cics_proc`,
`cics_csdup_parser.parse_cics_csdup`) are independent the same way; CICS
DFHRPL entries are the one exception among this round's additions --
they *are* cross-referenced, via `resolver.dataset_zone()` at ingest time
(see "How resolution works" above), the same zone/APF resolution every
STEPLIB/JOBLIB/LNKLST lineage hop already gets.

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
`/etc` mount, a read-only HFS mount, NAME=/PATH= landing on separate
continuation lines (the real shape), a TFS mount with an extra `MOUNT
PARM=` continuation line, and proving header/summary lines aren't
mistaken for mount records) — **confirmed against a real `D OMVS,F`
reply, see `uss_mounts_parser.py`'s module docstring** — and JES2
init-statement parsing (`sample_jes2parm.txt`, covering a decorative
multi-line box comment and a trailing same-line comment right after a
continuation comma (both proven not to corrupt or get merged into real
statement content), a nested-parenthesized value built from several
inner KEYWORD=VALUE pairs across multiple comment-interrupted
continuation lines, a subscript-only statement with no live parameters
(`FSS(PRINTOFF)`, real params documented but commented out) proven not
to be dropped, a bare flag parameter with no `=` (`START`) captured
with an empty value, an `INCLUDE` statement captured generically like
any other, and a second real member (`JES2NJE`, the one `INCLUDE`
pulls in) parsed with its own `source_member`) — **confirmed against
two real init-deck members (2026-07-02); see `jes2parm_parser.py`'s
module docstring for the full detail.** Also VTAM parsing
(`sample_vtam.txt`, covering major nodes across ACT/S/ACTIV/INACT
statuses in the real `IST089I ... TYPE = ..., STATUS` row shape (not the
originally-guessed `IST486I NAME STATUS` shape) plus banner/summary lines
(incl. the real `IST1454I n RESOURCE(S) DISPLAYED` line) proven not to be
mistaken for data rows; start options incl. two-KEYWORD=VALUE-pairs-per-
line parsing, a parenthesized value, the `NODETYPE`/`CPNAME` pair that
answers the APPN-enablement question, and the confirmed two-token-value
truncation limitation (`HPRPST`); and an APPN topology summary block
covering the checkpoint/ADJ/NN/EN/SERVED EN/CDSERVR/ICN/BN counts plus
the INITDB checkpoint dataset/garbage-collection fields, and confirming a
dump with no `##TOPO` block returns `None` rather than a half-populated
record) — **the entire fixture is now confirmed against real replies
(across two follow-up rounds), same as USS mounts above; see
`vtam_parser.py`'s module docstring for exactly what changed from the
original guesses.** Also
TCP/IP parsing (`sample_tcpip.txt`, covering `LINKNAME:` rows and the
real OSA-Express QDIO `INTFNAME:` rows the original guess never
accounted for, a `FLAGS:`/`PRIMARY` line setting `is_primary`; a
`PROFILE.TCPIP` excerpt covering simple single-line statements, a
repeated statement keyword (`TCPCONFIG`) captured as separate records,
`INTERFACE` continuation lines folded into one statement, a
`BEGINROUTES`/`ENDROUTES` block, an `AUTOLOG`/`ENDAUTOLOG` block with a
commented-out entry proven excluded, a `PORT` reservation table folded
into one statement with a commented-out reservation proven excluded,
and an indented `SMFCONFIG` statement proven *not* mistaken for a
continuation line of the preceding statement; and confirming the
`##PROFILE` block/`source_dsn` is simply absent when a dump has no
profile fetch) — **the entire fixture is now confirmed against real
replies (2026-07-02), same as VTAM/USS mounts above; see
`tcpip_parser.py`'s module docstring for exactly what changed from the
original guesses.** Also SMS storage
group parsing (`sample_sms.txt`, now the real confirmed two-section reply
shape rather than the originally-guessed one, covering a `STORGRP TYPE
SYSTEM=` header shared across several consecutive group rows, `TYPE`
(`POOL`/`TAPE`) and raw per-system status symbols like `+ +`/`+ -`, a
separate flat `VOLUME`-to-`STORGRP` table proven to attribute volumes
back to the right group by name, a `TAPE`-type group proven to get zero
volumes via the real `LISTVOL IS IGNORED FOR OBJECT, OBJECT BACKUP, AND
TAPE STORAGE GROUPS` marker, and legend/footer lines proven not to be
mistaken for volume rows) — **confirmed against a real system; storage
classes/management classes were removed entirely (no console command for
either exists) rather than left as untestable dead code — see
`sms_parser.py`'s module docstring for the full before/after.** Also WLM
policy parsing
(`sample_wlm.txt`, now the real confirmed `IWM025I` reply shape rather
than the originally-guessed one, covering the policy name, `mode` being
inferred as `GOAL` from the policy name's presence rather than parsed
from a `MODE=` token that doesn't actually exist in a real reply, plus a
test that an unrecognized/empty dump returns `None` rather than a
half-populated record) — **confirmed against a real system; see
`wlm_parser.py`'s module docstring for the real reply and why the
originally-guessed command didn't even exist.** Also deepened DB2
catalog parsing (`sample_db2_catalog.txt`, covering DSNTEP2-shaped
packages/plans, the `;;SSID=` marker line, and dashed separator/column-
header/`DSNE6xxI` message lines proven not to be mistaken for data rows)
— **also built against a hand-constructed fixture, not a real DB2
subsystem reply, and the most speculative console/MVS-program-based
parser in the pipeline; see `db2_catalog_parser.py`'s module docstring.**
Also WLM z/OSMF entry parsing (`sample_wlm_zosmf.txt`, a JSON fixture
covering the `policies`-key response shape, plus separate tests -- built
directly against `tmp_path`-generated JSON rather than fixture files --
for a bare top-level list, a single bare object wrapped as one entry,
missing name keys falling back to `"?"`, and malformed/non-JSON content
returning an empty list rather than raising) — **built against hand-
constructed JSON, not a real z/OSMF response, and the single most
speculative parser in the entire pipeline: see
`wlm_zosmf_parser.py`'s module docstring for why even the response shape
itself is a guess.** Also deepened CICS resource parsing
(`sample_cics_deepening.txt`, covering `##DFHRPL`/`##SIT`/`##CSD`/
`##CSDUP_REPORT` blocks: DFHRPL entries with `zone`/`apf_authorized` left
unset by the parser, generically-captured SIT `KEYWORD=VALUE` overrides
incl. a comma-separated pair on one line, and a DFHCSDUP LIST report
excerpt proving a `GROUP:` marker line's value carries forward onto
subsequent resource rows until the next one, with a page-banner line
proven not to be mistaken for a data row) — **built against a
hand-constructed fixture, not a real CICS startup PROC or DFHCSDUP LIST
report; the `##CSDUP_REPORT` portion specifically is the most speculative
parser in the pipeline alongside `db2_catalog_parser.py`/
`wlm_zosmf_parser.py`, and uniquely so on two axes at once (report
*format*, not just "not checked against a real system" like everywhere
else) — see `cics_csdup_parser.py`'s module docstring.**

## Scaling past the first slice

- Ingest accepts any number of `*proclib*.txt` / `*parmlib*.txt` /
  `*smplist*.txt` / `*smpzones*.txt` / `*ssn*.txt` / `*commnd*.txt` /
  `*ifaprd*.txt` /
  `*catalog*.txt` / `*uss_mounts*.txt` / `*jes2parm*.txt` / `*vtam*.txt` /
  `*tcpip*.txt` / `*sms*.txt` / `*db2_catalog*.txt` / `*wlm_zosmf*.txt` /
  `*cics_deepening*.txt`
  files in the input directory — just keep adding files as you extract
  more PROCLIB/PARMLIB concatenation entries, more SMP/E CSIs/zones, more
  HLQ/pattern groups, or more JES2 PARMLIB concatenation entries;
  `ingest` merges them all into one inventory. Note `*wlm*.txt` (the
  single-record `wlm.txt` policy name/mode file) explicitly excludes any
  filename containing `zosmf` so it doesn't also match `wlm_zosmf.txt` —
  see `cmd_ingest()`'s own comment in `cli.py`. `lnklst.txt` and
  `apf.txt` are each a single flat list.
- `system_info` (from `sysinfo.txt`), `wlm_policy` (from `wlm.txt`),
  `active_jobs` (from `active_jobs.txt`), `uss_processes` (from
  `processes.txt`), `parmlib_datasets` (from `parmlib_snapshot.txt`),
  `ieasys_statements` (from `ieasys_snapshot.txt`), `bpxprm_statements`
  (from `bpxprm_snapshot.txt`), and
  the seven `racf_*` tables (from `racf.txt`) are
  the exceptions: each is deliberately *not* additive like the tables
  above. `system_info`/`wlm_policy` represent a single-record identity
  (system, or active policy) rather than a list; `active_jobs`/
  `uss_processes` represent one point-in-time snapshot of what was
  running; `parmlib_datasets`/`ieasys_statements`/`bpxprm_statements`
  represent the current
  PARMLIB concatenation/active system parameters/active OMVS config, same
  "one system's current state" reasoning; the
  `racf_*` tables represent IRRDBU00's full current database
  state, not an incremental slice. Re-ingesting any of them replaces
  rather than merges — for the live-snapshot pair, that's the whole point:
  re-run `extrjobs.py`/`extrprocs.py` and `ingest` again to get an updated
  picture, not an ever-growing history. `system_info` is also what a
  future multi-system merge (one inventory DB per system, or a `system`
  column added throughout) would key each ingest run on.
- The `smpe_parser` module's docstring explains how to tune its regexes if
  your shop's SMP/E LIST report formatting differs from the fixture.
  `sysinfo_parser`'s `D SYMBOLS`/`D IPLINFO` regexes are now **confirmed**
  against a real reply (a follow-up round provided one) -- the real shape
  differed from the original guess in a few places that mattered (no
  `SYSNAME  = &SYSNAME. = value` label prefix on symbol lines, `VOLUME(x)`
  not `VOLUME: x`, and no `IPL PARM nn` text at all -- `ipl_parm_member`
  is now sourced from `IEASYS LIST = (...)` instead, same field
  `discover_active_parmlib_suffixes.yml` already parses); see the module's
  own docstring for the full before/after. If your site's release/symbol
  set produces something different, that docstring is still the place to
  compare against and tune. `catalog_parser`'s `##LISTCAT`-block regexes
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
  it — see `zos-extract.md`'s RACF step for why that's a bigger
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
  [`zos-extract.md`](zos-extract.md#9-dataset-catalog-hlqpattern-scoped)).
- **`inventory vsam` shows a cluster but every field is `?`** — the
  `##LISTCAT` block's regexes didn't match your site's actual IDCAMS
  `LISTCAT ALL` report formatting; compare your `*catalog*.txt` file by eye
  against the patterns documented in `catalog_parser.py`'s module
  docstring and `tests/fixtures/sample_catalog.txt`.
- **Any `inventory racf-*` command comes back empty** — this is expected if
  you didn't ingest `racf.txt` (it's optional, and — unlike everything
  else — implementation-only for now; see
  [`zos-extract.md`](zos-extract.md#10-racf-security-snapshot-implementation-only--verify-authority-before-running)
  for the real authorization hurdle before you can generate one).
- **RACF fields look obviously wrong (garbled text, misaligned values)** —
  `racf_parser.py`'s byte offsets were derived from a third-party
  reference implementation, not IBM's own docs or a real unload sample
  (see "How resolution works" above). This is the single most likely place
  in the whole project for a real-system mismatch; compare your `racf.txt`
  against the offsets documented in that module's docstring.
