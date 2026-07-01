# inventory

Off-host half of the pipeline: parses the text dumped by `zos-extract/` and
resolves each PROCLIB/PARMLIB member's full execution path back to the
SMP/E FMID that owns each program it runs.

## Install

```
pip install -e .
```

Requires Python 3.9+. No third-party runtime dependencies — only `pytest`
is needed for the test suite.

## Usage

1. Run `zos-extract/` on the target z/OS system and download its output
   (PROCLIB/PARMLIB dumps, LNKLST list, SMP/E LIST reports) into one local
   directory — see `../zos-extract/README.md` for the exact file naming.

2. Ingest and resolve:

   ```
   inventory ingest path/to/downloaded/input/
   ```

   This parses everything in that directory, builds the lineage chain for
   every member, and writes the result to `inventory.db` (SQLite; override
   with `--db`).

3. Query:

   ```
   inventory lineage MYPROC      # full execution path for one member
   inventory report              # CSV dump of every resolved hop
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

Any hop that can't be resolved (no STEPLIB and no LNKLST match, a dataset
not claimed by any ingested zone, etc.) is still recorded with a
human-readable reason in the `resolution` column — the inventory deliberately
surfaces gaps instead of silently dropping them.

## Tests

```
pip install -e . pytest
pytest
```

`tests/fixtures/` contains a small synthetic PROCLIB dump and SMP/E LIST
report exercising: direct STEPLIB resolution, JOBLIB resolution, LNKLST
fallback resolution, nested PROC inlining, an intentionally-unresolvable
module (to verify the "module not found" reporting path), and an
intentionally-unresolvable nested PROC reference.

## Scaling past the first slice

- Ingest accepts any number of `*proclib*.txt` / `*parmlib*.txt` /
  `*smplist*.txt` files in the input directory — just keep adding files as
  you extract more PROCLIB/PARMLIB concatenation entries and more SMP/E
  zones; `ingest` merges them all into one inventory.
- The `smpe_parser` module's docstring explains how to tune its regexes if
  your shop's SMP/E LIST report formatting differs from the fixture.
