#!/usr/bin/env python3
"""extrracf.py -- Run the RACF database unload utility (IRRDBU00) against an
operator-supplied RACF database COPY, and capture its flat output as a USS
text file for off-host parsing by inventory/inventory/racf_parser.py.

*** IMPLEMENTATION ONLY -- NOT YET VALIDATED FOR PRODUCTION USE ***
This script has a real authorization prerequisite this pipeline's other
scripts don't: READ access to a copy of the RACF database. That is a
DIFFERENT, and typically much harder to get, authorization than anything
else in zos-extract/ -- console D commands, PARMLIB member reads, and
IDCAMS LISTCAT are all comparatively easy asks. Having BPX.SUPERUSER (OMVS
superuser authority) does NOT grant RACF database read access -- they are
unrelated authorizations governed by completely different RACF profiles.
Expect to need your security team's direct involvement before this script
is usable at all. See "Getting a RACF database copy you can read" in
zos-extract/README.md.

  python3 extrracf.py --racf-database YOURHLQ.RACF.COPY \\
      --workhlq YOURID.RACFDMP --outfile racf.txt

- --racf-database is a DSN for a READ-accessible COPY of the RACF
  database. This script deliberately does NOT create that copy -- making
  one (e.g. via IRRUT200, or pointing at last night's backup) is a
  separate, sensitive operation outside this tool's scope. Never point
  this at the live primary/backup RACF database that's actually in use --
  always a copy.
- --workhlq is a high-level-qualifier prefix for one small temporary work
  dataset holding IRRDBU00's unloaded output, deleted automatically once
  the command finishes.

Unlike smplist.py (run once per SMP/E zone) or extrcat.py (run once per
HLQ/pattern), this runs exactly once: IRRDBU00 has no selective-unload
option -- one run always dumps the ENTIRE RACF database (every user,
group, dataset profile, and general-resource profile across every class)
as one flat file of mixed record types, distinguished by a 4-character
record-type code at the start of each line. Any "only show me class X"
curation happens off-host, in racf_parser.py -- it cannot reduce what
IRRDBU00 itself does on z/OS.

PARM='NOLOCKINPUT' is hardcoded (not a flag): appropriate specifically
because --racf-database always points at a copy, never the live primary,
so there's no concurrent-update risk to protect against by taking a lock.
SYSPRINT is DUMMY'd -- it's IRRDBU00's informational message output, not
the substantive unload (that's OUTDD), same "DUMMY the non-essential DD"
precedent as smplist.py's SMPLOG/SMPLOGA. If this script fails and you
need to see IRRDBU00's messages for troubleshooting, temporarily change
the SYSPRINT DDStatement below to a FileDefinition/DatasetDefinition
instead of "DUMMY".

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's module
docstring and this script's DD-statement construction against your ZOAU
version's API.
"""

import argparse
import os

from zos_common import die

from zoautil_py import datasets, mvscmd
from zoautil_py.types import DatasetDefinition, DDStatement


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--racf-database", required=True, dest="racf_database",
                    help="DSN of a READ-accessible COPY of the RACF database "
                         "(never the live primary/backup) -- get this from your "
                         "security team")
    p.add_argument("--workhlq", required=True,
                   help="HLQ for the temporary unload output dataset, e.g. YOURID.RACFDMP")
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/racf.txt")
    args = p.parse_args()

    output_dsn = None

    try:
        output_dsn = datasets.tmp_name(args.workhlq)
        datasets.create(output_dsn, type="SEQ")

        dd_list = [
            DDStatement("INDD1", DatasetDefinition(args.racf_database)),
            DDStatement("OUTDD", DatasetDefinition(output_dsn)),
            DDStatement("SYSPRINT", "DUMMY"),
        ]

        try:
            response = mvscmd.execute_authorized(pgm="IRRDBU00", parm="NOLOCKINPUT", dds=dd_list)
        except Exception as exc:
            die("IRRDBU00 invocation failed: {}".format(exc))

        result = response.to_dict()
        rc = result["rc"]

        # IRRDBU00 returns RC=0 for a clean unload; anything higher is a
        # real error (commonly: not authorized to read --racf-database).
        if rc > 0:
            die("IRRDBU00 failed (rc={}): {}".format(rc, result.get("stderr_response", "")))

        unload_text = datasets.read(output_dsn)
        with open(args.outfile, "w", encoding="utf-8") as out:
            out.write(unload_text)

    finally:
        if output_dsn is not None:
            try:
                datasets.delete(output_dsn)
            except Exception as exc:
                print("WARNING: could not delete temp dataset {}: {}".format(output_dsn, exc))

    print("extrracf: wrote RACF database unload to {}".format(args.outfile))


if __name__ == "__main__":
    main()
