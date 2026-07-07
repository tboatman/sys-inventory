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
who has access to what per RACF (users, groups, dataset and
general-resource access — **implementation only, not yet
production-validated**), and — unlike everything else here, which is
configuration/definition data — a live snapshot of what's actually
running right now (active jobs/tasks and USS processes).

Beyond that core chain, it also covers: the active PARMLIB concatenation
and IEASYSxx/BPXPRMxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx/DIAGxx member content actually in effect (not just where
PARMLIB search order looks); SMP/E zones/FMIDs across multiple CSIs, plus
SMP/E's own authoritative per-CSI zone census; mounted USS filesystems;
JES2's own initialization statements; the network stack (VTAM major
nodes/start options/APPN topology, TCP/IP home addresses and `PROFILE.TCPIP`
config); SMS storage groups; the active WLM policy (and, opt-in, full
service-class/goal definitions via z/OSMF); installed DB2 packages/plans
(opt-in); and a deepened CICS view — DFHRPL load-library lineage, SIT
overrides, and CSD resource definitions via DFHCSDUP (opt-in). Most of
these have been confirmed against real command/API output from an actual
z/OS system; a handful (DB2 catalog access, WLM z/OSMF, RACF, DFHCSDUP's
own report format) remain implementation-only until checked against a
real one — see [`doc/inventory.md`](doc/inventory.md) for the full,
per-command breakdown and current confirmation status of each, and
[`doc/TODO.md`](doc/TODO.md) for what's still planned.

If you're new to any of the z/OS terms used below (PROCLIB, PARMLIB,
SMP/E, APF, LPAR, ...), see the [Glossary](doc/zos-extract.md#glossary)
in `doc/zos-extract.md` — it's written for exactly that.

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
   Open Automation Utilities), for the original ten domains (PROCLIB/PARMLIB
   members, subsystem and started-task definitions, product enablement, the
   LNKLST and APF-authorized library lists, basic system identity, SMP/E's
   catalog, an HLQ/pattern-scoped dataset catalog, a live snapshot of what's
   currently running, and a RACF security snapshot). See
   [`doc/zos-extract.md`](doc/zos-extract.md) for exactly what to
   run and in what order; it's written assuming no prior familiarity with
   any of this. **`ansible/`** covers everything since — the active
   PARMLIB/IEASYSxx/BPXPRMxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx/DIAGxx snapshots, multi-CSI SMP/E zone discovery, USS
   mounts, JES2 init, VTAM/TCP-IP, SMS, WLM, DB2 catalog, and CICS deepening
   — as well as re-running the original ten across many LPARs at once; see
   [`doc/ansible.md`](doc/ansible.md). Either path writes what it finds as
   plain text files.
2. You copy those text files off the mainframe (plain `scp`/`sftp`/FTP —
   no binary or VSAM transfer needed, it's all text).
3. **`inventory/`** runs anywhere with Python 3.9+. It parses those text
   files, resolves the full PROCLIB → program → load library → SMP/E
   zone/FMID chain for every member, and loads the result into a small
   SQLite database you can query from the command line. See
   [`doc/inventory.md`](doc/inventory.md) for install and usage.

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
 │  - dataset       │               │  racf_parser    → RacfSnapshot
 │    catalog       │               │                   (impl. only)
 │  - RACF unload   │               │                        │
 │    (impl. only)  │               │                        │
 └─────────────────┘               └──────────────────────┘
```

That diagram shows the original core chain only. `ansible/` adds a
matching set of parsers for every domain listed above (`uss_mounts_parser`,
`jes2parm_parser`, `vtam_parser`, `tcpip_parser`, `sms_parser`, `wlm_parser`,
`wlm_zosmf_parser`, `db2_catalog_parser`, `cics_proc_parser`/
`cics_csdup_parser`, `parmlib_parser`/`ieasys_parser`/`bpxprm_parser`), each
feeding its own table(s) in the same SQLite database — see
[`doc/inventory.md`](doc/inventory.md) for the complete list.

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
  cp tests/fixtures/sample_cics_deepening.txt /tmp/demo/cics_deepening.txt && \
  cp tests/fixtures/sample_parmlib_snapshot.txt /tmp/demo/parmlib_snapshot.txt && \
  cp tests/fixtures/sample_ieasys_snapshot.txt  /tmp/demo/ieasys_snapshot.txt && \
  cp tests/fixtures/sample_bpxprm_snapshot.txt  /tmp/demo/bpxprm_snapshot.txt && \
  cp tests/fixtures/sample_devsup_snapshot.txt  /tmp/demo/devsup_snapshot.txt && \
  cp tests/fixtures/sample_opt_snapshot.txt     /tmp/demo/opt_snapshot.txt && \
  cp tests/fixtures/sample_clock_snapshot.txt   /tmp/demo/clock_snapshot.txt && \
  cp tests/fixtures/sample_autor_snapshot.txt   /tmp/demo/autor_snapshot.txt && \
  cp tests/fixtures/sample_sched_snapshot.txt   /tmp/demo/sched_snapshot.txt && \
  cp tests/fixtures/sample_couple_snapshot.txt  /tmp/demo/couple_snapshot.txt && \
  cp tests/fixtures/sample_grsrnl_snapshot.txt  /tmp/demo/grsrnl_snapshot.txt && \
  cp tests/fixtures/sample_smf_snapshot.txt     /tmp/demo/smf_snapshot.txt && \
  cp tests/fixtures/sample_ios_snapshot.txt     /tmp/demo/ios_snapshot.txt
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
inventory --db /tmp/demo/demo.db racf-users
inventory --db /tmp/demo/demo.db racf-groups
inventory --db /tmp/demo/demo.db uss-mounts
inventory --db /tmp/demo/demo.db jes2parm
inventory --db /tmp/demo/demo.db vtam-majnodes
inventory --db /tmp/demo/demo.db tcpip-home
inventory --db /tmp/demo/demo.db sms-storgrps
inventory --db /tmp/demo/demo.db wlm
inventory --db /tmp/demo/demo.db db2-packages
inventory --db /tmp/demo/demo.db cics-dfhrpl
inventory --db /tmp/demo/demo.db parmlib
inventory --db /tmp/demo/demo.db ieasys
```

See [`doc/inventory.md`](doc/inventory.md) for the rest of the commands
(`vtam-options`, `vtam-topology`, `tcpip-profile`, `wlm-zosmf`, `db2-plans`,
`cics-sit`, `cics-csd`, `bpxprm`, `devsup`, `opt`, `clock`, `autor`, `sched`,
`couple`, `grsrnl`, `smf`, `ios`,
`zone-index`, `zones`, `fmids`,
`zone-gaps`, `racf-connections`,
`racf-dataset-profiles`, `racf-dataset-access`, `racf-resource-profiles`,
`racf-resource-access`) and each one's current confirmation status.

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

1. Read [`doc/zos-extract.md`](doc/zos-extract.md) (the original ten
   domains, runnable by hand with no Ansible) and/or
   [`doc/ansible.md`](doc/ansible.md) (those ten plus everything since,
   runnable across one or more LPARs). Either way needs an OMVS shell,
   ZOAU, and read access to the datasets/commands you're inventorying —
   covered in both.
2. Copy the resulting directory of text files to your own machine.
3. Follow [`doc/inventory.md`](doc/inventory.md): `pip install -e .`
   then `inventory ingest path/to/that/directory/`.
4. Query it — see the full command list in
   [`doc/inventory.md`](doc/inventory.md), or the representative subset
   shown above under "Try it right now."

## Status

Core slice: one PROCLIB/PARMLIB concatenation entry + one SMP/E target
zone, plus subsystems/started tasks, APF authorization, system identity,
product enablement, a live active-jobs/processes snapshot, and an
HLQ/pattern-scoped dataset catalog (non-VSAM + VSAM), proven end-to-end
against the test fixtures in `inventory/tests/fixtures/`. The design
scales to multiple concatenation entries and multiple zones (Global +
every target zone), and multiple SMP/E CSIs, without code changes — see
"Scaling" in `doc/inventory.md`.

Since that core slice, the pipeline has grown a lot more: the active
PARMLIB/IEASYSxx/BPXPRMxx/DEVSUPxx/IEAOPTxx/CLOCKxx/AUTORxx/SCHEDxx/COUPLExx/GRSRNLxx/SMFPRMxx/IECIOSxx/CONSOLxx/IGDSMSxx/IZUPRMxx/DIAGxx snapshots, SMP/E's own authoritative per-CSI
zone census, USS mounts, JES2 init statements, VTAM (major nodes, start
options, APPN topology), TCP/IP (home addresses, `PROFILE.TCPIP`), SMS
storage groups, the active WLM policy, installed DB2 packages/plans, and
a deepened CICS view (DFHRPL lineage, SIT overrides, CSD definitions via
DFHCSDUP). Most of these have been confirmed against real command/API
output from an actual z/OS system (see `doc/TODO.md` for exactly which,
and what changed once a real reply was checked). A handful remain
**implementation-only, not yet production-validated**: RACF (users,
groups, dataset and curated general-resource access — needs a real, and
likely hard-to-get, RACF database read authorization this environment
can't provide, and its parser's field layout was derived from a
third-party reference rather than IBM's own documentation or a real
unload sample), DB2 catalog access via DSNTEP2, WLM's z/OSMF REST API
deepening (the single most speculative dimension in the pipeline), and
DFHCSDUP's own `LIST` report print format. Treat each of those as
implementation-only until checked against a real system — see
`doc/inventory.md`'s per-command sections for specifics on each.

## Sub-project docs

- [`doc/zos-extract.md`](doc/zos-extract.md) — beginner-friendly
  walkthrough of what to run on z/OS, a glossary of z/OS terms, exact
  parameters, output format, download instructions, and troubleshooting.
  Covers the original ten domains only (no Ansible required).
- [`doc/inventory.md`](doc/inventory.md) — install, CLI usage
  (with example output for every command, across every domain), resolution
  algorithm, test suite, and troubleshooting.
- [`doc/ansible.md`](doc/ansible.md) — run extraction across one or more
  LPARs with Ansible instead of by hand: the original ten domains plus
  every domain added since, with results fetched straight into a directory
  ready for `inventory ingest`.
- [`doc/TODO.md`](doc/TODO.md) — the roadmap: what's implemented and
  confirmed, what's implemented but not yet production-validated, and
  what's still just planned (including the 23-more-PARMLIB-member-types
  plan).
