# sys-inventory

Inventories a z/OS system's PROCLIB/PARMLIB members by tracing their full
execution path — including nested PROCs and STEPLIB/JOBLIB/LNKLST-resolved
load modules — back to the SMP/E target zone and FMID that owns each
program.

## Architecture

```
  z/OS system                          off-host
 ┌─────────────────┐   flat text   ┌──────────────────────┐
 │  zos-extract/    │ ───────────► │  inventory/           │
 │  REXX + JCL      │  (FTP/Zowe)   │  Python parser +      │
 │  - PROCLIB dump  │               │  SQLite store + CLI   │
 │  - PARMLIB dump  │               │                        │
 │  - LNKLST dump   │               │  jcl_parser  → ProcMember/JclStep
 │  - SMP/E LIST    │               │  smpe_parser → Zone (DDDEF, FMID)
 │    (DDDEF/FILE/  │               │  resolver    → joins them into
 │     SYSMOD/ZONES)│               │                full lineage chains
 └─────────────────┘               └──────────────────────┘
```

`zos-extract/` runs on the mainframe and only produces plain text (no
binary/VSAM transfer needed). `inventory/` runs anywhere with Python 3.9+
and turns that text into a queryable inventory:

```
ProcMember → JclStep (PGM=) → Dataset (STEPLIB/JOBLIB/LNKLST) → SMP/E Zone → FMID
```

## Quick start (using the bundled fixtures, no z/OS access required)

`ingest` expects an input directory with files matching `*proclib*.txt`,
`*parmlib*.txt`, `*smplist*.txt`, and `lnklst.txt` (the naming convention
documented in `zos-extract/README.md`). The test fixtures aren't named that
way, so for a quick manual demo, copy them into that shape first:

```
cd inventory
pip install -e .
mkdir -p /tmp/demo && \
  cp tests/fixtures/sample_proclib.txt   /tmp/demo/00_proclib.txt && \
  cp tests/fixtures/sample_smpe_list.txt /tmp/demo/tzone1.smplist.txt && \
  cp tests/fixtures/sample_lnklst.txt    /tmp/demo/lnklst.txt
inventory --db /tmp/demo/demo.db ingest /tmp/demo
inventory --db /tmp/demo/demo.db lineage MYPROC
```

For a real system: run `zos-extract/` first (see its README), download the
output, then point `inventory ingest` at the download directory.

## Status

First working slice: one PROCLIB/PARMLIB concatenation entry + one SMP/E
target zone, proven end-to-end against the test fixtures in
`inventory/tests/fixtures/`. The design scales to multiple concatenation
entries and multiple zones (Global + every target zone) without code
changes — see "Scaling" in `inventory/README.md`.

## Sub-project docs

- [`zos-extract/README.md`](zos-extract/README.md) — what to run on z/OS,
  parameters, output format, download instructions.
- [`inventory/README.md`](inventory/README.md) — install, CLI usage,
  resolution algorithm, test suite.
