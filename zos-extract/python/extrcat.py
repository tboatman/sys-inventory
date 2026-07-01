#!/usr/bin/env python3
"""extrcat.py -- Catalog datasets under one or more operator-supplied HLQ/
name patterns: non-VSAM physical attributes (DSORG/RECFM/LRECL/BLKSIZE/
VOLSER) plus VSAM cluster/component detail (KSDS/ESDS/RRDS/LINEAR type,
DATA/INDEX component names), to one flat USS text file for off-host parsing
by inventory/inventory/catalog_parser.py.

This is deliberately scoped, not a full-catalog dump -- a real ICF catalog
can hold hundreds of thousands of entries. --pattern is required (at least
one) and there is no "match everything" default; pass the HLQ(s) actually
relevant to the inventory you're building, e.g.:

  python3 extrcat.py --pattern 'SYS1.*' --pattern 'PROD.**' \\
      --workhlq YOURID.CATALOG --outfile /u/me/inventory/prod_catalog.txt

Two extraction paths are used, not one, because ZOAU's own dataset-listing
API doesn't cover VSAM:

  - Non-VSAM attributes come straight from ZOAU's datasets.list_datasets(),
    which is confirmed (via ibm_zos_core's data_set.py, which wraps this
    same call) to return .name/.volume/.organization/.record_format/
    .record_length/.block_size -- but VSAM entries are NOT returned by this
    call at all (ibm_zos_core falls back to raw IDCAMS LISTCAT for VSAM
    detail for the same reason -- see its data_set_type()/_get_listcat_data
    functions). So this script uses list_datasets() directly for the
    non-VSAM block, with no MVS program invocation needed for that part.
  - VSAM cluster/component detail comes from running IDCAMS's LISTCAT
    command directly, via ZOAU's mvscmd.execute_authorized() -- the same
    "hold DD allocations for one program call" approach smplist.py already
    uses for GIMSMP. ibm_zos_core does the same thing for the same reason
    (its _get_listcat_data() runs `mvscmdauth --pgm=idcams`).

IDCAMS's LISTCAT LEVEL() parameter takes a qualifier prefix, not a wildcard
pattern -- unlike datasets.list_datasets(), which accepts TSO-style
wildcards (e.g. 'SYS1.*'). So each --pattern's trailing wildcard suffix
(.*, .**, *) is stripped before building the LISTCAT LEVEL() control
statement, so both extraction paths end up scoped to the same HLQ level
from one --pattern argument.

Output format: reuses the bare "##BLOCKNAME" sentinel convention from
extrsys.py/sysinfo_parser.py:

  ##NONVSAM
  <one line per non-VSAM dataset: "dsn volser dsorg recfm lrecl blksize">
  ##LISTCAT
  <raw IDCAMS LISTCAT ALL output, unchanged, for every --pattern's level>

Run this from an OMVS shell. IDCAMS LISTCAT only needs READ access to the
catalog(s) in the standard search order -- no special authorization beyond
that, though this script still calls mvscmd.execute_authorized() (like
smplist.py does for GIMSMP) since that's this project's established, proven
way to hold one program's DD allocations together for a single call.

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's module
docstring and this script's DD-statement construction against your ZOAU
version's API. Broad --pattern values (e.g. a shared top-level HLQ) can
still return a lot of output even though this is HLQ-scoped, not a full
catalog dump -- prefer patterns scoped to the HLQs actually relevant to the
inventory being built.
"""

import argparse
import os
import re

from zos_common import die

from zoautil_py import datasets, mvscmd
from zoautil_py.types import DatasetDefinition, DDStatement, FileDefinition


def _nonvsam_lines(patterns):
    lines = []
    for pattern in patterns:
        try:
            entries = datasets.list_datasets(pattern)
        except Exception as exc:
            die("datasets.list_datasets failed for pattern '{}': {}".format(pattern, exc))
        for entry in entries or []:
            volser = entry.volume or "?"
            dsorg = entry.organization or "?"
            recfm = entry.record_format or "?"
            lrecl = entry.record_length if entry.record_length is not None else "?"
            blksize = entry.block_size if entry.block_size is not None else "?"
            lines.append("{} {} {} {} {} {}".format(
                entry.name, volser, dsorg, recfm, lrecl, blksize))
    return lines


def _level_from_pattern(pattern):
    """Strip a trailing TSO/ZOAU-style wildcard suffix (.*, .**, *) so a
    --pattern like 'SYS1.*' becomes the qualifier-level prefix 'SYS1' that
    IDCAMS LISTCAT's LEVEL() parameter expects. A pattern with no wildcard
    suffix (e.g. 'SYS1.PARMLIB') is passed through unchanged -- LISTCAT
    LEVEL() lists that qualifier and everything below it."""
    return re.sub(r"\.?\*+$", "", pattern)


def _control_statements(patterns):
    levels = sorted(set(_level_from_pattern(p) for p in patterns))
    return "".join(" LISTCAT LEVEL({}) ALL .\n".format(level) for level in levels)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--pattern", required=True, action="append",
                    help="HLQ/dataset-name pattern to catalog, e.g. 'SYS1.*' "
                         "or 'PROD.**' -- repeatable, at least one required")
    p.add_argument("--workhlq", required=True,
                   help="HLQ for the temporary LISTCAT output dataset, e.g. YOURID.CATALOG")
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/prod_catalog.txt")
    args = p.parse_args()

    cntl_path = args.outfile + ".idcams.tmp"
    output_dsn = None

    try:
        with open(cntl_path, mode="w", encoding="cp1047") as f:
            f.write(_control_statements(args.pattern))

        output_dsn = datasets.tmp_name(args.workhlq)
        datasets.create(output_dsn, type="SEQ")

        dd_list = [
            DDStatement("SYSIN", FileDefinition(cntl_path)),
            DDStatement("SYSPRINT", DatasetDefinition(output_dsn)),
        ]

        try:
            response = mvscmd.execute_authorized(pgm="IDCAMS", dds=dd_list)
        except Exception as exc:
            die("IDCAMS invocation failed: {}".format(exc))

        result = response.to_dict()
        rc = result["rc"]

        # LISTCAT returns RC=0 (found) or RC=4 (informational, e.g. some
        # entries not found/protected); anything higher is a real error.
        if rc > 4:
            die("IDCAMS LISTCAT failed (rc={}): {}".format(rc, result.get("stderr_response", "")))

        listcat_text = datasets.read(output_dsn)
        nonvsam_lines = _nonvsam_lines(args.pattern)

        with open(args.outfile, "w", encoding="utf-8") as out:
            out.write("##NONVSAM\n")
            for line in nonvsam_lines:
                out.write(line + "\n")
            out.write("##LISTCAT\n")
            out.write(listcat_text)
            if not listcat_text.endswith("\n"):
                out.write("\n")

    finally:
        if os.path.exists(cntl_path):
            os.remove(cntl_path)
        if output_dsn is not None:
            try:
                datasets.delete(output_dsn)
            except Exception as exc:
                print("WARNING: could not delete temp dataset {}: {}".format(output_dsn, exc))

    print("extrcat: wrote {} non-VSAM entries and a LISTCAT report for {} pattern(s) to {}"
          .format(len(nonvsam_lines), len(args.pattern), args.outfile))


if __name__ == "__main__":
    main()
