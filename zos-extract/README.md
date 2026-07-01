# zos-extract

z/OS-side half of the inventory pipeline. Everything here runs **from an
OMVS shell** using IBM Open Enterprise Python for z/OS, and produces plain
text output that gets fed to the `inventory` Python package.

No binary or VSAM transfer is needed — everything is written straight to
USS files as text. PROCLIB/PARMLIB dumps use a `##MEMBER name` sentinel
line to delimit members (see `python/extrproc.py` header) so the off-host
parser never confuses a member boundary with an actual `//` JCL statement.

MVS data set access goes through base TSO/E commands (`LISTDS`, `OPUT`)
run via `tsocmd`, not JCL. The one exception is `smplist.py`
(see below), which needs a small REXX exec: TSO dynamic allocation is
scoped to one address space, and each `tsocmd` call spawns a fresh one, so
a multi-step ALLOC-then-run-a-program sequence only works if something
stays in one continuous TSO/E environment for the whole sequence — which
is exactly what REXX is for.

## What to run

1. **PROCLIB/PARMLIB dumps** — `python/extrproc.py`. Run once per library
   in the concatenation you care about (the first inventory slice only
   needs one PROCLIB and one PARMLIB):

   ```
   python3 extrproc.py --indsn SYS1.PROCLIB --outfile /u/me/inventory/00_proclib.txt
   python3 extrproc.py --indsn SYS1.PARMLIB --outfile /u/me/inventory/00_parmlib.txt
   ```

   PARMLIB members are plain text too, so the same script handles both —
   there's no separate PARMLIB wrapper. Members you aren't authorized to
   read are skipped with a warning rather than aborting the whole dump.

2. **LNKLST dataset list** — `python/extrlnk.py`. Used as the fallback
   search order when a JCL step has `PGM=` but no `STEPLIB`/`JOBLIB`:

   ```
   python3 extrlnk.py --outfile /u/me/inventory/lnklst.txt
   ```

   This shells out to the `opercmd` USS utility to issue `D PROG,LNKLST`.
   If your installation doesn't allow that command from your userid,
   capture it via SDSF/console manually and save it as one dataset name
   per line in the same `--outfile`.

3. **SMP/E CSI report** — `python/smplist.py` + `rexx/SMPDRV.rexx`. Drives
   `LIST DDDEF`, `LIST MOD`, and `LIST SYSMOD` against one
   target zone. One-time setup: upload `rexx/SMPDRV.rexx` into a PDS in
   your TSO exec library concatenation via your normal text-mode transfer
   process (same as you'd use for any other REXX member), then run once
   per zone you want included:

   ```
   python3 smplist.py --execlib YOUR.EXEC.LIB --csi YOUR.GLOBAL.CSI \
       --zone TZONE1 --workhlq YOURID.SMPLIST \
       --outfile /u/me/inventory/tzone1.smplist.txt
   ```

   `smplist.py` is a thin wrapper that just builds the parm string and
   invokes `SMPDRV` via `tsocmd EX ...`; `SMPDRV.rexx` does the actual
   ALLOC/`CALL *(GIMSMP)`/FREE work in one address space. SMP/E itself
   only needs READ access to the CSI for LIST commands (no
   APPLY/ACCEPT/RECEIVE), so this is safe to run broadly. `--workhlq` is
   used for temporary SYSUT1-4 sort work data sets, deleted again once the
   run finishes. If GIMSMP isn't in your LNKLST, pass `--steplib`.

See each script's `--help` / module docstring for full parameter details.

## Getting the output off-host

Once the files above exist under a USS directory (e.g. `/u/me/inventory/`),
copy that directory off-host directly, e.g.:

```
scp -r myuserid@mainframe:/u/me/inventory/ ./input/
```

Then run `inventory ingest input/` from the `inventory/` package — see
`inventory/README.md`.

## Naming convention for multiple concatenation entries

When you scale beyond one PROCLIB/PARMLIB library, name each `extrproc.py`
output file `NN_libname.txt` where `NN` is the library's position in the
concatenation (lower = searched first, matching real JCL PROCLIB/PARMLIB
search order). The resolver uses this prefix to break ties when the same
member name exists in more than one library.
