# zos-extract

This is the half of the pipeline that runs **on the mainframe**. It reads
things like your PROCLIB, PARMLIB, and SMP/E catalog and writes what it
finds out as plain text files. Those text files then get copied to a
regular computer, where the `inventory/` package (see
[`../inventory/README.md`](../inventory/README.md)) turns them into a
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
| **LPAR** | Logical Partition — one "virtual mainframe" carved out of the physical hardware; a physical box can run several LPARs at once. |
| **Sysplex** | A cluster of LPARs (possibly across physical boxes) configured to work together as one logical system. |
| **IPL** | Initial Program Load — z/OS's term for "boot"/"reboot." |
| **ZOAU** | Z Open Automation Utilities — IBM's toolkit (CLI commands + a Python API called `zoautil_py`) for scripting z/OS tasks like dataset access and issuing console commands, without hand-rolling JCL. |

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

### 3. LNKLST dataset list

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

### 4. APF-authorized library list

Script: `python/extrapf.py`. Flags whether each resolved load library is
APF-authorized:

```
python3 /path/to/zos-extract/python/extrapf.py --outfile apf.txt
```

Same idea as step 3, but issues `D PROG,APF` instead — this reflects the
*live* APF list (including any `SETPROG APF` changes made since IPL), not
just what's coded in PARMLIB. Same manual-capture fallback if
console-command access isn't available to you.

### 5. LPAR/sysplex identity

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

### 6. SMP/E CSI report

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
  zone.
- `--workhlq` is a high-level-qualifier prefix used to name a couple of
  small temporary work datasets, deleted automatically once the command
  finishes (e.g. `YOURID.SMPLIST` — anything under your own userid's
  naming convention is fine).
- `--steplib` is optional — only needed if the SMP/E program `GIMSMP`
  isn't already reachable via LNKLST at your site; if you don't know,
  try without it first.

SMP/E itself only needs READ access to the CSI for LIST commands (no
APPLY/ACCEPT/RECEIVE happens here), so this is safe to run broadly.

See each script's `--help` output (or open the `.py` file — the top
comment has the same information) for full parameter details.

## Getting the output off-host

Once the files above exist under a USS directory (e.g.
`/u/yourid/inventory/`), copy that whole directory to your own machine:

```
scp -r yourid@yourmainframe:/u/yourid/inventory/ ./input/
```

(or use `sftp`, or your site's Zowe/FTP tooling — as long as it's a
text-mode transfer, since these are all plain text files, not binary.)

Then, on your own machine, follow
[`../inventory/README.md`](../inventory/README.md) — specifically
`inventory ingest input/`.

## Naming convention cheat sheet

`inventory ingest` looks for files by substring match. This is the full
list of what it looks for in the directory you point it at:

| What | Filename must contain | Produced by |
|---|---|---|
| PROCLIB/PARMLIB dumps | `proclib` or `parmlib` | `extrproc.py` (step 1) |
| Subsystem dumps | `ssn` | `extrproc.py` with `--members 'IEFSSN*'` (step 2) |
| Started-task dumps | `commnd` | `extrproc.py` with `--members 'COMMND*'` (step 2) |
| LNKLST list | exactly `lnklst.txt` | `extrlnk.py` (step 3) |
| APF list | exactly `apf.txt` | `extrapf.py` (step 4) |
| System identity | `sysinfo` | `extrsys.py` (step 5) |
| SMP/E LIST report | `smplist` | `smplist.py` (step 6), one file per zone |

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
`python/smplist.py`), specifically so that adapting to your installed
version's exact API only means editing those two files — nothing else in
the pipeline needs to change.
