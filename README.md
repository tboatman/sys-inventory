# sys-inventory

**In plain English:** this tool answers "if I run PROCLIB member `MYPROC`,
what actual program code executes, which load library does it come from,
and which installed software product owns that code?" — across an entire
PROCLIB/PARMLIB, automatically, instead of you tracing STEPLIB/JOBLIB/PROC
chains and SMP/E LIST output by hand. It also separately catalogs what
subsystems and started tasks are defined, whether each load library it
finds is APF-authorized, which LPAR/sysplex the data came from, which
priced/optional products are actually licensed and enabled (as opposed to
merely installed), what's cataloged (non-VSAM attributes and VSAM
cluster/component detail) under whatever HLQs/patterns you point it at,
and — unlike everything else here, which is configuration/definition
data — a live snapshot of what's actually running right now (active
jobs/tasks and USS processes).

If you're new to any of the z/OS terms used below (PROCLIB, PARMLIB,
SMP/E, APF, LPAR, ...), see the [Glossary](zos-extract/README.md#glossary)
in `zos-extract/README.md` — it's written for exactly that.

## Why this exists / who it's for

Tracing "what does this started task actually run, and is it patched"
by hand means: open the PROCLIB member, follow any nested `EXEC
PROCNAME` steps, find the `STEPLIB` (or fall back to the LNKLST search
order if there isn't one), then cross-reference that load library against
SMP/E's zone/FMID catalog to find out what product and patch level owns
it. That's slow and error-prone to do for more than a handful of members.
This tool automates the whole chain and gives you a queryable database of
the result — useful for change-impact analysis ("what uses this load
library"), audits ("which of our load libraries are APF-authorized"), and
plain documentation ("what does this environment actually consist of").

## How it works, in two steps

This is a two-part pipeline because step 1 has to run *on* the mainframe
(it needs to read mainframe datasets and issue mainframe console
commands), while step 2 is ordinary Python that can run anywhere —
your laptop, a CI runner, wherever.

1. **`zos-extract/`** runs on z/OS, in an OMVS (UNIX) shell, using ZOAU (Z
   Open Automation Utilities). It reads PROCLIB/PARMLIB members, subsystem
   and started-task definitions, product enablement, the LNKLST and
   APF-authorized library lists, basic system identity, SMP/E's catalog, an
   HLQ/pattern-scoped dataset catalog, and a live snapshot of what's
   currently running — and writes what it finds out as plain text files. See
   [`zos-extract/README.md`](zos-extract/README.md) for exactly what to
   run and in what order; it's written assuming no prior familiarity with
   any of this.
2. You copy those text files off the mainframe (plain `scp`/`sftp`/FTP —
   no binary or VSAM transfer needed, it's all text).
3. **`inventory/`** runs anywhere with Python 3.9+. It parses those text
   files, resolves the full PROCLIB → program → load library → SMP/E
   zone/FMID chain for every member, and loads the result into a small
   SQLite database you can query from the command line. See
   [`inventory/README.md`](inventory/README.md) for install and usage.

```
  z/OS system                          your computer (anywhere)
 ┌─────────────────┐   flat text   ┌──────────────────────┐
 │  zos-extract/    │ ───────────► │  inventory/           │
 │  Python + ZOAU   │  (scp/sftp)   │  Python parser +      │
 │  - PROCLIB dump  │               │  SQLite store + CLI   │
 │  - PARMLIB dump  │               │                        │
 │  - IEFSSNxx/     │               │  jcl_parser     → ProcMember/JclStep
 │    COMMNDxx dump │               │  ssn_parser     → Subsystem/StartedTask
 │  - IFAPRDxx dump │               │  ifaprd_parser  → Product
 │  - LNKLST dump   │               │  sysinfo_parser → SystemInfo
 │  - APF dump      │               │  activity_parser→ ActiveJob/UssProcess
 │  - D SYMBOLS/    │               │  smpe_parser    → Zone (DDDEF, FMID)
 │    D IPLINFO dump│               │  resolver       → joins PROCLIB/LNKLST/
 │  - SMP/E LIST    │               │                   APF/SMP/E into full
 │    (DDDEF/FILE/  │               │                   lineage chains
 │     SYSMOD/ZONES)│               │                        │
 │  - active jobs/  │               │  catalog_parser → CatalogDataset/
 │    processes     │               │                   VsamCluster
 │  - dataset       │               │                        │
 │    catalog       │               │                        │
 └─────────────────┘               └──────────────────────┘
```

The core resolution chain, for every PROCLIB/PARMLIB member:

```
ProcMember → JclStep (PGM=) → Dataset (STEPLIB/JOBLIB/LNKLST) → SMP/E Zone → FMID
                                  │
                                  └→ APF-authorized? (from the live D PROG,APF list)
```

## Try it right now (no mainframe access needed)

The repo ships small synthetic sample files so you can see the whole
pipeline work end-to-end without touching a real z/OS system first. This
is the fastest way to understand what the tool actually produces before
you go run the real extraction steps.

```
cd inventory
pip install -e .
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
  cp tests/fixtures/sample_catalog.txt     /tmp/demo/demo_catalog.txt
inventory --db /tmp/demo/demo.db ingest /tmp/demo
inventory --db /tmp/demo/demo.db lineage MYPROC
inventory --db /tmp/demo/demo.db subsystems
inventory --db /tmp/demo/demo.db started-tasks
inventory --db /tmp/demo/demo.db sysinfo
inventory --db /tmp/demo/demo.db products
inventory --db /tmp/demo/demo.db active
inventory --db /tmp/demo/demo.db processes
inventory --db /tmp/demo/demo.db catalog
inventory --db /tmp/demo/demo.db vsam
```

`inventory lineage MYPROC` should print something like:

```
MYPROC
  step STEP1: PGM=IEFBR14 dataset=MY.SITE.LINKLIB zone=TZONE2 FMID=? [APF]  [module IEFBR14 not found in zone TZONE2's FILE list]
  step NSTEP1: PGM=IGYCRCTL dataset=SYS1.LINKLIB zone=TZONE1 FMID=HLA2280 [non-APF]  [resolved via STEPLIB (APPLIED)]
```

— one line per resolved execution step, with the load library, owning
SMP/E zone/FMID, and APF status. `inventory report` dumps the same
information as CSV for every member at once, for spreadsheet/scripting
use.

## Running it against a real system

1. Read [`zos-extract/README.md`](zos-extract/README.md) and run those
   scripts on your z/OS system (needs an OMVS shell, ZOAU, and read
   access to the datasets you're inventorying — all covered there).
2. Copy the resulting directory of text files to your own machine.
3. Follow [`inventory/README.md`](inventory/README.md): `pip install -e .`
   then `inventory ingest path/to/that/directory/`.
4. Query it with `inventory lineage`/`report`/`subsystems`/
   `started-tasks`/`sysinfo`/`products`/`active`/`processes`/`catalog`/
   `vsam` as shown above.

## Status

Core slice: one PROCLIB/PARMLIB concatenation entry + one SMP/E target
zone, plus subsystems/started tasks, APF authorization, system identity,
product enablement, a live active-jobs/processes snapshot, and an
HLQ/pattern-scoped dataset catalog (non-VSAM + VSAM), proven end-to-end
against the test fixtures in `inventory/tests/fixtures/`. The design
scales to multiple concatenation entries and multiple zones (Global +
every target zone) without code changes — see "Scaling" in
`inventory/README.md`.

## Sub-project docs

- [`zos-extract/README.md`](zos-extract/README.md) — beginner-friendly
  walkthrough of what to run on z/OS, a glossary of z/OS terms, exact
  parameters, output format, download instructions, and troubleshooting.
- [`inventory/README.md`](inventory/README.md) — install, CLI usage
  (with example output for every command), resolution algorithm, test
  suite, and troubleshooting.
