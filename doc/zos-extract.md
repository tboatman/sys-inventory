# zos-extract

This is the half of the pipeline that runs **on the mainframe**. It reads
things like your PROCLIB, PARMLIB, and SMP/E catalog and writes what it
finds out as plain text files. Those text files then get copied to a
regular computer, where the `inventory/` package (see
[`inventory.md`](inventory.md)) turns them into a
searchable database. This README assumes no prior familiarity with any of
that — if a term looks unfamiliar, check the [Glossary](#glossary) below
before searching elsewhere.

## Before you start

You need all of the following. If you're not sure whether you have them,
ask your systems programmer / z/OS admin — these aren't things you can
install yourself.

- **An OMVS/z/OS UNIX shell logon.** This is a Unix-like command line that
  runs on the mainframe, separate from the traditional 3270/green-screen
  TSO interface. If you can run `ssh youruserid@yourmainframe` and land at
  a `$` prompt (not `READY` or `===>`), you're in OMVS. If your site uses
  ISPF, option 6 ("TSO command") with `OMVS` typed in, or option `=` with
  a shortcut, usually gets you there too.
- **IBM Open Enterprise Python for z/OS**, installed and on your `PATH`.
  Check with:
  ```
  python3 --version
  ```
  If that says "command not found," ask your admin where Python is
  installed (often somewhere like `/usr/lpp/IBM/cyp/v3r*` — you may need
  to add it to your `PATH` or `.profile`).
- **ZOAU (Z Open Automation Utilities)**, with its Python API
  (`zoautil_py`) importable from that same Python. Check with:
  ```
  python3 -c "from zoautil_py import datasets; print('ZOAU OK')"
  ```
  If this errors out, ZOAU either isn't installed or isn't on your
  `PYTHONPATH` — again, this is something your admin sets up, usually via
  a line in `/etc/profile` or your own `.profile` that does something like
  `export PYTHONPATH=/usr/lpp/IBM/zoautil/lib/some_version:$PYTHONPATH`.
  See [ZOAU version differences](#zoau-version-differences-if-imports-fail)
  below if the import fails with something *other* than "module not
  found."
- **READ access** to whatever PROCLIB/PARMLIB/CSI datasets you're
  inventorying, and (for `extrlnk.py`/`extrapf.py`/`extrsys.py`)
  authority to issue a handful of read-only MVS console `D` (DISPLAY)
  commands. None of the commands in this pipeline modify anything on the
  mainframe — everything here is read-only, display/list-style access.
  If a command fails with something like "not authorized," that's a
  RACF/security permission your admin needs to grant, not a bug.
  **Exception:** step 10 (`extrracf.py`) needs a materially different, much
  harder-to-get authorization — READ access to a copy of the RACF database
  itself. See that step for details; it's implementation-only for now and
  not something to chase down unless you're specifically working on that
  piece.

No binary or VSAM transfer is ever needed — every script here writes
straight to a USS (z/OS UNIX System Services) text file, which you copy
off-host the normal way (`scp`/`sftp`/FTP in text mode).

## Glossary

If you're new to z/OS, skim this before the "What to run" section — the
script names and flags below assume you know what these mean.

| Term | Meaning |
|---|---|
| **OMVS / USS** | z/OS UNIX System Services — the Unix-like shell/filesystem layer on top of z/OS. Everything in this directory runs there. |
| **PROCLIB** | A library of JCL procedures (reusable job step templates) — mainly cataloged started-task and batch job procedures. |
| **PARMLIB** | A library of system configuration members (e.g. `IEASYS00`, `IEFSSN00`) read at IPL (boot) or via operator commands. |
| **PDS / PDSE** | Partitioned Data Set (Extended) — a mainframe "library" containing named "members" (think: a folder of text files, sort of). |
| **DSN** | Data Set Name — the mainframe equivalent of a file path, e.g. `SYS1.PROCLIB`. |
| **STEPLIB / JOBLIB** | A JCL statement that says "load programs for this step/job from this specific library" (overrides the default search order). |
| **LNKLST** | The system-wide default list of libraries searched for a program when no STEPLIB/JOBLIB is given. |
| **APF** | Authorized Program Facility — libraries flagged APF-authorized can run programs that need elevated system privileges. This pipeline flags whether each resolved load library is on that list. |
| **SMP/E** | System Modification Program/Extended — the tool that tracks which software (and patch level) is installed where on the system. |
| **CSI** | Consolidated Software Inventory — the SMP/E database/catalog itself. |
| **Zone (SMP/E)** | A subdivision within a CSI (e.g. one per product or one Global + one per target library set). |
| **FMID** | Function Modification ID — SMP/E's identifier for one installed software product/feature. |
| **Subsystem** | A major system facility registered at IPL via PARMLIB member `IEFSSNxx` (e.g. JES2, DB2, CICS region managers). |
| **Started task** | A long-running address space started via an operator `START`/`S` command, often automatically at IPL via `COMMNDxx`. |
| **IFAPRDxx** | A PARMLIB member listing `PRODUCT` statements that say which priced/optional features are licensed and enabled — different from SMP/E, which says what's installed and patched but not whether it's turned on. |
| **ASID** | Address Space ID — a small hex number identifying one specific running instance of a job/started task. Only assigned while something is actually executing; useful for telling two concurrently-running copies of the same task apart. |
| **LPAR** | Logical Partition — one "virtual mainframe" carved out of the physical hardware; a physical box can run several LPARs at once. |
| **Sysplex** | A cluster of LPARs (possibly across physical boxes) configured to work together as one logical system. |
| **IPL** | Initial Program Load — z/OS's term for "boot"/"reboot." |
| **ZOAU** | Z Open Automation Utilities — IBM's toolkit (CLI commands + a Python API called `zoautil_py`) for scripting z/OS tasks like dataset access and issuing console commands, without hand-rolling JCL. |
| **ICF catalog** | Integrated Catalog Facility catalog — the system-wide directory mapping dataset names to the volumes/details where they actually live. |
| **VSAM** | Virtual Storage Access Method — a mainframe dataset access method for structured, indexed, or keyed data (as opposed to plain sequential/partitioned datasets). |
| **VSAM cluster** | One logical VSAM dataset, made up of a DATA component (the actual records) and, for keyed clusters, an INDEX component. |
| **KSDS / ESDS / RRDS** | The three main VSAM cluster types: Key-Sequenced (indexed by a key), Entry-Sequenced (append-only, accessed by position), and Relative-Record (accessed by record number). |
| **IDCAMS** | The standard MVS utility program for VSAM/catalog management commands like `LISTCAT` (list catalog entries) — this pipeline only ever issues the read-only `LISTCAT` command, never anything that modifies a dataset or catalog. |
| **RACF** | Resource Access Control Facility — IBM's mainframe security product: who's a valid user, what groups they're in, and who's allowed to access which datasets/resources. |
| **IRRDBU00** | The RACF database unload utility — dumps the entire RACF database as a flat text report, one record type per kind of data (users, groups, dataset profiles, ...). Read-only; never modifies RACF. |
| **SPECIAL / OPERATIONS / AUDITOR** | The three RACF "superuser-style" user attributes: SPECIAL (full security-administration authority), OPERATIONS (can access nearly any dataset/resource regardless of its own permissions), AUDITOR (can view/change audit settings). Can be scoped system-wide or to just one group. |
| **UACC** | Universal Access — the default access level a RACF profile grants to anyone not otherwise explicitly permitted (e.g. `NONE`, `READ`, `UPDATE`). |

## What to run

Run these from your OMVS shell, in an empty directory you're allowed to
write to (e.g. `/u/yourid/inventory/`). Each command below is meant to be
copy-pasted, with `SYS1.PROCLIB` etc. replaced by your site's actual
dataset names.

```
mkdir -p /u/yourid/inventory
cd /u/yourid/inventory
```

### 1. PROCLIB/PARMLIB dumps

Script: `python/extrproc.py`. Run once per library you care about — the
minimum useful set is one PROCLIB and one PARMLIB:

```
python3 /path/to/zos-extract/python/extrproc.py --indsn SYS1.PROCLIB --outfile 00_proclib.txt
python3 /path/to/zos-extract/python/extrproc.py --indsn SYS1.PARMLIB --outfile 00_parmlib.txt
```

(Replace `/path/to/zos-extract/python/` with wherever you copied this
`zos-extract/python/` directory on the mainframe — e.g. if you `scp`'d
the whole `zos-extract` folder to `/u/yourid/zos-extract`, that's
`/u/yourid/zos-extract/python/extrproc.py`.)

Expected output: a line like
`extrproc: dumped 214 of 214 members from SYS1.PROCLIB to 00_proclib.txt`,
and a new file `00_proclib.txt` full of your PROCLIB's JCL text. Members
you're not authorized to read are skipped with a warning, not an error —
that's normal and doesn't stop the dump.

PARMLIB members are plain text too, so the same script handles both —
there's no separate PARMLIB-specific tool.

### 2. Subsystem & started-task dumps

Also `python/extrproc.py`, run twice more against PARMLIB with a member
filter, so the off-host parser can tell these apart from the JCL-style
dumps above:

```
python3 /path/to/zos-extract/python/extrproc.py --indsn SYS1.PARMLIB --members 'IEFSSN*' --outfile 00_ssn.txt
python3 /path/to/zos-extract/python/extrproc.py --indsn SYS1.PARMLIB --members 'COMMND*' --outfile 00_commnd.txt
```

**Filename rule:** the output filename must contain `ssn` or `commnd` —
that substring is what tells the off-host `inventory ingest` command which
parser to use. Don't let a filename contain `proclib`/`parmlib` *and*
`ssn`/`commnd` together (e.g. don't name it
`00_ssn_parmlib.txt`) — it would get picked up by both, which is harmless
but pointless.

If your site names its subsystem/command PARMLIB members differently, the
`--members` value is a wildcard filter you can adjust (`*`/`?` supported,
same as `ls`).

### 3. Product enablement dump

Also `python/extrproc.py`, run once more against PARMLIB with a member
filter, for whatever's licensed/enabled via `IFAPRDxx`:

```
python3 /path/to/zos-extract/python/extrproc.py --indsn SYS1.PARMLIB --members 'IFAPRD*' --outfile 00_ifaprd.txt
```

**Filename rule:** same idea as step 2 — the output filename must contain
`ifaprd`. Not every shop uses IFAPRDxx (some products are always-enabled
or licensed a different way); if yours doesn't have any `IFAPRD*` members,
just skip this step — `inventory ingest` treats a missing input as "no
data," not an error.

### 4. LNKLST dataset list

Script: `python/extrlnk.py`. This is the fallback search order used when
a JCL step has `PGM=` but no `STEPLIB`/`JOBLIB`:

```
python3 /path/to/zos-extract/python/extrlnk.py --outfile lnklst.txt
```

This issues the read-only console command `D PROG,LNKLST`. Expected
output: `extrlnk: wrote 47 LNKLST data set names to lnklst.txt` (the
number will differ). If your userid isn't allowed to issue MVS console
commands (common at security-conscious shops), this will fail — ask your
admin for that authority, or run `D PROG,LNKLST` from SDSF/console
yourself and paste the dataset names, one per line, into `lnklst.txt` by
hand.

### 5. APF-authorized library list

Script: `python/extrapf.py`. Flags whether each resolved load library is
APF-authorized:

```
python3 /path/to/zos-extract/python/extrapf.py --outfile apf.txt
```

Same idea as step 4, but issues `D PROG,APF` instead — this reflects the
*live* APF list (including any `SETPROG APF` changes made since IPL), not
just what's coded in PARMLIB. Same manual-capture fallback if
console-command access isn't available to you.

### 6. LPAR/sysplex identity

Script: `python/extrsys.py`. A small "which system did this inventory come
from" fingerprint:

```
python3 /path/to/zos-extract/python/extrsys.py --outfile sysinfo.txt
```

Issues `D SYMBOLS` and `D IPLINFO` and writes both replies to one file.
Console output formatting for these two commands varies more by z/OS
release/site customization than SMP/E's report format does — if the
off-host `inventory sysinfo` command comes back with `?` for every field,
open `sysinfo.txt` and compare it by eye against the patterns documented
in `inventory/inventory/sysinfo_parser.py`'s module docstring.

### 7. SMP/E CSI report

Script: `python/smplist.py`. Run once per SMP/E zone you want in the
inventory:

```
python3 /path/to/zos-extract/python/smplist.py --csi YOUR.GLOBAL.CSI \
    --zone TZONE1 --workhlq YOURID.SMPLIST --outfile tzone1.smplist.txt
```

- `--csi` is your SMP/E Global CSI dataset name — ask whoever manages
  software installs at your shop if you don't know it.
- `--zone` is the SMP/E zone to report on (e.g. a target zone name like
  `TZONE1`, or `GLOBAL`). Run this once per zone you want included; run
  it again with a different `--zone` and `--outfile` for each additional
  zone. Covering more than one CSI (a real site can have several -- its
  own product CSIs alongside the base z/OS one) just means running this
  again with a different `--csi`/`--outfile` -- `inventory ingest` merges
  any number of `*.smplist.txt` files, each stamped with its own CSI via
  the `##CSI` line this script writes (see `inventory/README.md`'s "How
  resolution works").
- `--workhlq` is a high-level-qualifier prefix used to name a couple of
  small temporary work datasets, deleted automatically once the command
  finishes (e.g. `YOURID.SMPLIST` — anything under your own userid's
  naming convention is fine).
- `--steplib` is optional — only needed if the SMP/E program `GIMSMP`
  isn't already reachable via LNKLST at your site; if you don't know,
  try without it first.

SMP/E itself only needs READ access to the CSI for LIST commands (no
APPLY/ACCEPT/RECEIVE happens here), so this is safe to run broadly.

`smplist.py` (and the `ansible/` role's equivalent `_smplist_zone.yml`
task) automatically prepends a `##CSI YOUR.GLOBAL.CSI` line ahead of the
GIMSMP report text — `inventory/smpe_parser.py` reads it to stamp every
zone parsed from that file with its owning CSI (`inventory
lineage`/`report`/`trace`'s `CSI=`/`csi` column), which matters once you
run this against more than one CSI (a real site can have several — see
`ansible/roles/zos_extract/tasks/discover_smpe_csis.yml`). If you're
running an older copy of either script, the file just won't have that
line and `csi` comes back empty — nothing else changes.

**Zone discovery has no standalone script yet** — same "ansible-only for
now" situation USS mounts/JES2/VTAM/TCPIP/SMS/WLM/DB2/CICS are already in
(see this file's own intro). If you don't already know a CSI's zones,
`ansible/roles/zos_extract/tasks/discover_smpe_zones.yml` (tag
`smpe_zone_discovery`) runs GIMSMP's `LIST GLOBALZONE` for you instead,
writing one `*.smpzones.txt` per CSI that `inventory ingest`/`inventory
zone-index` also picks up — see `ansible/README.md`'s own section on it.

### 8. Live activity snapshot (currently-running jobs and processes)

Everything above is either configuration (what's *defined*) or fairly
stable point-in-time state. This step is different: it's a live,
second-to-second snapshot of what's actually *running right now*, from
two angles — `python/extrjobs.py` for MVS/JES jobs and started tasks, and
`python/extrprocs.py` for USS (Unix) processes:

```
python3 /path/to/zos-extract/python/extrjobs.py --outfile active_jobs.txt
python3 /path/to/zos-extract/python/extrprocs.py --outfile processes.txt
```

`extrjobs.py` uses ZOAU's job-listing API to find every job/started task
currently in `ACTIVE` status, writing `job_id name job_type asid` per
line — the ASID (address space ID) lets you tell two concurrently-running
copies of the same started task apart. `extrprocs.py` just runs the
standard z/OS UNIX `ps -ef` command directly (no ZOAU/SDSF involved — this
is plain USS process listing) and writes one command name per line.

Since this is a snapshot, not configuration, re-running these two scripts
and re-running `inventory ingest` replaces the previous snapshot rather
than accumulating history — run them again whenever you want an updated
picture of what's running.

See each script's `--help` output (or open the `.py` file — the top
comment has the same information) for full parameter details.

### 9. Dataset catalog (HLQ/pattern-scoped)

Script: `python/extrcat.py`. Catalogs non-VSAM dataset attributes
(DSORG/RECFM/LRECL/BLKSIZE/VOLSER) and VSAM cluster/component detail
(KSDS/ESDS/RRDS/LINEAR type, DATA/INDEX component names) — but only for
datasets matching one or more HLQ/name patterns you supply. This is
deliberately **not** a full-catalog dump: a real ICF catalog can hold
hundreds of thousands of entries, so scope `--pattern` to the HLQs actually
relevant to the inventory you're building (e.g. your applications' HLQs,
not a shared top-level qualifier used by many unrelated things):

```
python3 /path/to/zos-extract/python/extrcat.py --pattern 'SYS1.*' --pattern 'PROD.**' \
    --workhlq YOURID.CATALOG --outfile prod_catalog.txt
```

- `--pattern` is repeatable and required (at least one) — TSO-style
  wildcards are supported (e.g. `HLQ.*` for one level, `HLQ.**` for
  everything under `HLQ`), the same as `datasets.list_datasets()` accepts.
- `--workhlq` is a high-level-qualifier prefix for one small temporary work
  dataset used to capture the IDCAMS `LISTCAT` report, deleted
  automatically once the command finishes.

Non-VSAM attributes come straight from ZOAU's dataset-listing API (no
console command or MVS program call needed for that part). VSAM detail
comes from running IDCAMS's `LISTCAT ... ALL` command — this only needs
READ access to the catalog(s) in the standard search order, the same
read-only kind of authority as everything else in this pipeline.

Run this once per HLQ/pattern group you care about, same idea as step 7's
"once per zone" — each run's `--outfile` becomes one more input file for
`inventory ingest`.

### 10. RACF security snapshot (implementation only — verify authority before running)

Script: `python/extrracf.py`. Captures who's a RACF user/group, who has
elevated authority (SPECIAL/OPERATIONS/AUDITOR), and access lists for
dataset profiles and a curated set of general-resource classes. **This
step is built and tested, but not yet validated against a real system —
treat it as implementation-only until you've verified it against your own
site's RACF database unload.**

```
python3 /path/to/zos-extract/python/extrracf.py --racf-database YOURHLQ.RACF.COPY \
    --workhlq YOURID.RACFDMP --outfile racf.txt
```

Unlike everything above, this runs `IRRDBU00` (the RACF database unload
utility) against a **copy** of the RACF database, and it always unloads
the entire database in one pass — there's no per-zone/per-pattern loop
like steps 7 or 9, so you only run this once.

#### Getting a RACF database copy you can read

This is a genuinely different, and typically much harder, authorization
ask than everything else in this pipeline. Console `D` commands, PARMLIB
member reads, and `LISTCAT` are all comparatively easy to get approved.
Reading the RACF database itself — even a copy — is not, because it's the
security team's own crown jewels.

- **You almost certainly don't already have this.** If you can issue
  console commands or read PARMLIB, that doesn't imply RACF database read
  access; they're governed by completely separate RACF profiles.
- **`BPX.SUPERUSER` does not grant this.** Having OMVS superuser authority
  (the `BPX.SUPERUSER` FACILITY-class profile) feels like "root," but it's
  an unrelated authorization — it does not give you READ access to the
  RACF database dataset. This is a common misconception worth heading off
  before you spend time chasing the wrong permission.
- **What to actually ask your security team for:** either an existing,
  more-broadly-readable backup copy of the RACF database (many shops
  already make one nightly via `IRRUT200` for exactly this kind of
  reporting use case), or a one-time copy made for you. Ask them, don't
  try to make the copy yourself — this tool deliberately doesn't automate
  that step, since it involves the live RACF database.
- Once you have a DSN you can read, `--racf-database` is the only new
  thing you need to point at it — everything else about running this
  script is the same as every other step above.

## Getting the output off-host

Once the files above exist under a USS directory (e.g.
`/u/yourid/inventory/`), copy that whole directory to your own machine:

```
scp -r yourid@yourmainframe:/u/yourid/inventory/ ./input/
```

(or use `sftp`, or your site's Zowe/FTP tooling — as long as it's a
text-mode transfer, since these are all plain text files, not binary.)

Then, on your own machine, follow
[`inventory.md`](inventory.md) — specifically
`inventory ingest input/`.

## Naming convention cheat sheet

`inventory ingest` looks for files by substring match. This is the full
list of what it looks for in the directory you point it at:

| What | Filename must contain | Produced by |
|---|---|---|
| PROCLIB/PARMLIB dumps | `proclib` or `parmlib` (except anything matching `parmlib_snapshot`, see below) | `extrproc.py` (step 1) |
| Subsystem dumps | `ssn` | `extrproc.py` with `--members 'IEFSSN*'` (step 2) |
| Started-task dumps | `commnd` | `extrproc.py` with `--members 'COMMND*'` (step 2) |
| Product enablement dumps | `ifaprd` | `extrproc.py` with `--members 'IFAPRD*'` (step 3) |
| LNKLST list | exactly `lnklst.txt` | `extrlnk.py` (step 4) |
| APF list | exactly `apf.txt` | `extrapf.py` (step 5) |
| System identity | `sysinfo` | `extrsys.py` (step 6) |
| SMP/E LIST report | `smplist` | `smplist.py` (step 7), one file per CSI/zone pair |
| SMP/E zone index (LIST GLOBALZONE) | `smpzones` | ansible-only, `discover_smpe_zones.yml`, one file per CSI |
| PARMLIB concatenation snapshot (D PARMLIB) | `parmlib_snapshot` (default filename `parmlib_snapshot.txt`, override via `zos_extract_parmlib_snapshot_outfile`) | ansible-only, `parmlib_snapshot.yml` -- deliberately excluded from the `parmlib` rule above so it isn't mistaken for a PARMLIB member dump |
| Active IEASYSxx member snapshot (the actual system parameters) | `ieasys_snapshot` (default filename `ieasys_snapshot.txt`, override via `zos_extract_ieasys_snapshot_outfile`) | ansible-only, `ieasys_snapshot.yml` |
| Active BPXPRMxx member snapshot (z/OS UNIX/OMVS config, named by IEASYSxx's own OMVS=) | `bpxprm_snapshot` (default filename `bpxprm_snapshot.txt`, override via `zos_extract_bpxprm_snapshot_outfile`) | ansible-only, `bpxprm_snapshot.yml` -- not yet production-validated |
| Active DEVSUPxx member snapshot (device support definitions, named by IEASYSxx's own DEVSUP=) | `devsup_snapshot` (default filename `devsup_snapshot.txt`, override via `zos_extract_devsup_snapshot_outfile`) | ansible-only, `devsup_snapshot.yml` -- not yet production-validated |
| Active IEAOPTxx member snapshot (system tuning/options parameters, named by IEASYSxx's own OPT=) | `opt_snapshot` (default filename `opt_snapshot.txt`, override via `zos_extract_opt_snapshot_outfile`) | ansible-only, `opt_snapshot.yml` -- not yet production-validated |
| Active CLOCKxx member snapshot (TOD clock/timezone parameters, named by IEASYSxx's own CLOCK=) | `clock_snapshot` (default filename `clock_snapshot.txt`, override via `zos_extract_clock_snapshot_outfile`) | ansible-only, `clock_snapshot.yml` -- not yet production-validated |
| Active AUTORxx member snapshot (WTOR auto-reply policy, named by IEASYSxx's own AUTOR=) | `autor_snapshot` (default filename `autor_snapshot.txt`, override via `zos_extract_autor_snapshot_outfile`) | ansible-only, `autor_snapshot.yml` -- not yet production-validated |
| Active SCHEDxx member snapshot (PPT/Program Properties Table entries, named by IEASYSxx's own SCH=) | `sched_snapshot` (default filename `sched_snapshot.txt`, override via `zos_extract_sched_snapshot_outfile`) | ansible-only, `sched_snapshot.yml` -- not yet production-validated |
| Active jobs/tasks snapshot | exactly `active_jobs.txt` | `extrjobs.py` (step 8) |
| USS process snapshot | exactly `processes.txt` | `extrprocs.py` (step 8) |
| Dataset catalog | `catalog` | `extrcat.py` (step 9), one file per HLQ/pattern group |
| RACF security snapshot | exactly `racf.txt` | `extrracf.py` (step 10, implementation only) |

When you scale beyond one PROCLIB/PARMLIB library, name each additional
`extrproc.py` output file `NN_libname.txt`, where `NN` is that library's
position in the concatenation (lower number = searched first, matching
real JCL PROCLIB/PARMLIB search order) — e.g. `00_proclib.txt` for the
first PROCLIB in the concatenation, `01_proclib.txt` for the second. The
off-host resolver uses this prefix to break ties when the same member name
exists in more than one library.

## Troubleshooting

- **"command not found: python3"** — Python isn't on your `PATH`. Ask your
  admin where IBM Open Enterprise Python is installed.
- **"ModuleNotFoundError: No module named 'zoautil_py'"** — ZOAU isn't on
  your `PYTHONPATH`. Ask your admin, or check whether a `zoau-env`-style
  setup script needs to be sourced first (often something like
  `. /usr/lpp/IBM/zoautil/bin/zoau-env.sh` at shop-specific paths).
- **"ERROR: could not list members of SYS1.PROCLIB: ..."** — usually a
  READ authority problem. Ask for READ access to that dataset.
- **"opercmd failed" / a console command script exits with an error** —
  either you don't have authority to issue MVS console commands (ask your
  admin), or (if it worked before) something about your site's console
  command routing changed. Fall back to the "capture manually" instructions
  in that script's `--help` output.
- **A script errors immediately on `from zoautil_py import ...`, but ZOAU
  is definitely installed** — see the next section; you may be on an older
  ZOAU release with a different API shape.

### ZOAU version differences (if imports fail)

This project's scripts (`zos_common.py`, `smplist.py`) use ZOAU's current
API style: lowercase modules with plain functions, e.g.
`from zoautil_py import datasets, opercmd` and calls like
`datasets.list_members(dsn)`. That's confirmed against IBM's own published
samples and current tooling as of this writing. Some older ZOAU releases
(roughly the "IBM Master the Mainframe 2020" era) shipped a different,
capitalized API instead — `from zoautil_py import Datasets`,
`Datasets.read(...)`. If every ZOAU-using script here fails at the same
`from zoautil_py import ...` line, that mismatch is the most likely cause.
Every ZOAU call in this project is deliberately isolated to
`python/zos_common.py` (plus the DD-statement construction local to
`python/smplist.py`, `python/extrcat.py`, and `python/extrracf.py`, which
each call `mvscmd.execute_authorized()` directly to run one MVS program),
so that adapting to your installed version's exact API only means editing
those files — nothing else in the pipeline needs to change.


#### Basic Env requirements
PATH=/shrd/zoautil//bin:/shrd/cyp/pyz/bin/:/bin
_BPXK_AUTOCVT=ON
ZOAU_ROOT=/shrd/zoautil/
_CEE_RUNOPTS=FILETAG(AUTOCVT,AUTOTAG) POSIX(ON)
CLASSPATH=/shrd/zoautil//lib/*:
STEPLIB=none
LANG=C
LIBPATH=/shrd/zoautil/lib:/shrd/cyp/pyz/lib:/lib:/usr/lib:.
TERM=xterm
PYTHONPATH=/shrd/zoautil//lib/: