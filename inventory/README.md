# inventory

Off-host half of the pipeline: parses the text dumped by `zos-extract/` and
resolves each PROCLIB/PARMLIB member's full execution path back to the
SMP/E FMID that owns each program it runs, flags whether each resolved
load library is APF-authorized, and separately inventories defined
subsystems, auto-started tasks, and the LPAR/sysplex identity of the
system the dump came from. Everything lands in one small SQLite database
you query from the command line.

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
  cp tests/fixtures/sample_sysinfo.txt   /tmp/demo/sysinfo.txt
inventory --db /tmp/demo/demo.db ingest /tmp/demo
```

(The fixture files aren't named the way `zos-extract/` would actually name
them — see the [naming convention cheat
sheet](../zos-extract/README.md#naming-convention-cheat-sheet) — this is
just renaming them into that shape for a quick demo.)

## Usage against real data

1. Run `zos-extract/` on the target z/OS system and download its output
   (PROCLIB/PARMLIB dumps, IEFSSNxx/COMMNDxx dumps, LNKLST list, APF list,
   system identity dump, SMP/E LIST reports) into one local directory —
   see [`../zos-extract/README.md`](../zos-extract/README.md) for the
   exact file naming and how to produce each file.

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
   inventory: ingested 5 members, 2 zones, 6 resolved steps, 2 subsystems, 2 started tasks -> /tmp/demo/demo.db
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
```

If you didn't ingest a `sysinfo.txt`, this prints `no system info
ingested` and exits with a non-zero status — that's expected, not a bug.

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

Subsystems (`ssn_parser.parse_subsystems`) and started tasks
(`ssn_parser.parse_started_tasks`) are parsed independently of the
STEPLIB/JOBLIB/LNKLST/SMP/E lineage above — they're not part of a
ProcMember's execution path, just a separate inventory dimension read from
the same PARMLIB text dump format. System identity
(`sysinfo_parser.parse_sysinfo`) is a single record per ingest, not a list.

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
line that should be skipped), and system-identity parsing (including a
field deliberately missing from the fixture, to prove tolerant partial
matching).

## Scaling past the first slice

- Ingest accepts any number of `*proclib*.txt` / `*parmlib*.txt` /
  `*smplist*.txt` / `*ssn*.txt` / `*commnd*.txt` files in the input
  directory — just keep adding files as you extract more PROCLIB/PARMLIB
  concatenation entries and more SMP/E zones; `ingest` merges them all into
  one inventory. `lnklst.txt` and `apf.txt` are each a single flat list.
- `system_info` (from `sysinfo.txt`) is the one exception: it's
  deliberately *not* additive like the tables above. It represents the
  identity of the one system being ingested, so re-ingesting replaces
  rather than merges it — this is what a future multi-system merge (one
  inventory DB per system, or a `system` column added throughout) would
  key each ingest run on.
- The `smpe_parser` module's docstring explains how to tune its regexes if
  your shop's SMP/E LIST report formatting differs from the fixture; the
  `sysinfo_parser` module's docstring has the same guidance for `D
  SYMBOLS`/`D IPLINFO` output, which varies more by release/site than
  SMP/E's LIST format does.

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
