#!/usr/bin/env python3
"""smplist.py -- Drive standard SMP/E LIST commands against one CSI/zone and
capture the printed report as a USS text file for off-host parsing by
inventory/smpe_parser.py.

Run once per target zone you want in the inventory:

  python3 smplist.py --csi YOUR.GLOBAL.CSI --zone TZONE1 \\
      --workhlq YOURID.SMPLIST --outfile /u/me/inventory/tzone1.smplist.txt

SMP/E itself only needs READ access to the CSI for LIST commands (no
APPLY/ACCEPT/RECEIVE), so this is safe to run broadly. If GIMSMP isn't in
your LNKLST, pass --steplib with the SMP/E load library that contains it.

Implementation: allocates the SMP/E DDs and calls GIMSMP directly via
ZOAU's mvscmd.execute_authorized(), which -- like the SMPDRV.rexx exec
this replaces -- holds every DD allocation for the one GIMSMP call in a
single step. Earlier versions of this pipeline needed a REXX exec
(SMPDRV.rexx, since removed) for this because `tsocmd`-driven TSO dynamic
allocation is scoped to one address space, and each `tsocmd` invocation
from a shell spawns a fresh one -- an ALLOC-then-CALL-then-FREE sequence
only survives if something stays in one continuous TSO/E environment
start to finish. ZOAU's mvscmd provides that same guarantee natively from
Python, so no REXX/upload step is needed anymore: there's no --execlib
argument, and nothing to upload to a PDS before running this.

The DD list and call shape here (SMPCSI/SMPLOG(DUMMY)/SMPLOGA(DUMMY)/
SMPWRK6/SMPCNTL/SMPLIST, `mvscmd.execute_authorized(pgm="GIMSMP", ...)`,
control statements written to a cp1047-encoded USS file rather than an MVS
dataset) is adapted from IBM's own published ZOAU sample for this exact
task, github.com/IBM/zoau-samples' samples/smpe_list.py, fetched and
cross-checked while writing this -- it's a more reliable reference than
guessing at GIMSMP's DD requirements from scratch. Two things are added on
top of that sample to fit this project's "everything lands as a USS text
file" convention (see zos-extract/README.md): after GIMSMP finishes, the
SMPLIST output -- which IBM's sample leaves in a temporary MVS dataset --
is read back and written to --outfile, and that temp dataset is deleted;
and an optional --steplib DD is added for shops where GIMSMP isn't in
LNKLST (IBM's sample assumes it is).

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's module
docstring and this script's DD-statement construction against your ZOAU
version's API.

On datasets.create()'s space/volume parameters below: this call
deliberately omits `primary_space`/`secondary_space`/`volumes` and relies
on ZOAU's own defaults, rather than hardcoding a size or volume serial
that would only be right for one shop. This is confirmed safe, not just
hoped: IBM's `ibm_zos_core` Ansible collection wraps this same
`datasets.create()` call and documents "reasonable default arguments will
be set by ZOAU when necessary," and documents `volumes` as optional for
SMS-managed shops (the common case) -- only needed for non-SMS sites, or
SMS storage classes with GUARANTEED_SPACE=YES. If dataset creation fails
on your system, it's most likely one of those two cases; add
`primary_space="5M", secondary_space="5M"` (a number plus a unit suffix
-- M/K/CYL/TRK -- in one string, confirmed against IBM's own sample data)
and/or `volumes="YOURVOL"` to the two datasets.create() calls below.
"""

import argparse
import os

from zos_common import die

from zoautil_py import datasets, mvscmd
from zoautil_py.types import DatasetDefinition, DDStatement, FileDefinition


def _control_statements(zone):
    return "SET     BDY({}).\nLIST DDDEF .\nLIST MOD .\nLIST SYSMOD .\n".format(zone)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csi", required=True, help="GLOBAL CSI data set name, e.g. YOUR.GLOBAL.CSI")
    p.add_argument("--zone", required=True, help="target zone name to report on, e.g. TZONE1")
    p.add_argument("--workhlq", required=True,
                   help="HLQ for temporary SMP/E work data sets, e.g. YOURID.SMPLIST")
    p.add_argument("--outfile", required=True,
                   help="USS output text file path for the SMPLIST report, "
                        "e.g. /u/me/inventory/tzone1.smplist.txt")
    p.add_argument("--steplib", default=None,
                   help="SMP/E load library containing GIMSMP, if it's not in LNKLST")
    args = p.parse_args()

    cntl_path = args.outfile + ".smpcntl.tmp"
    output_dsn = None
    work_dsn = None

    try:
        with open(cntl_path, mode="w", encoding="cp1047") as f:
            f.write(_control_statements(args.zone))

        output_dsn = datasets.tmp_name(args.workhlq)
        datasets.create(output_dsn, type="SEQ")

        work_dsn = datasets.tmp_name(args.workhlq)
        datasets.create(work_dsn, type="PDS", record_format="FB", record_length=80,
                         directory_blocks=10)

        dd_list = [
            DDStatement("SMPCSI", DatasetDefinition(args.csi)),
            DDStatement("SMPLOG", "DUMMY"),
            DDStatement("SMPLOGA", "DUMMY"),
            DDStatement("SMPWRK6", DatasetDefinition(work_dsn)),
            DDStatement("SMPCNTL", FileDefinition(cntl_path)),
            DDStatement("SMPLIST", DatasetDefinition(output_dsn)),
        ]
        if args.steplib:
            dd_list.append(DDStatement("STEPLIB", DatasetDefinition(args.steplib)))

        try:
            response = mvscmd.execute_authorized(pgm="GIMSMP", dds=dd_list)
        except Exception as exc:
            die("GIMSMP invocation failed: {}".format(exc))

        result = response.to_dict()
        rc = result["rc"]

        # SMP/E LIST commands return RC=0 (clean) or RC=4 (informational,
        # e.g. an empty LIST FILE section); anything higher is a real error.
        if rc > 4:
            die("GIMSMP failed (rc={}): {}".format(rc, result.get("stderr_response", "")))

        report_text = datasets.read(output_dsn)
        with open(args.outfile, "w", encoding="utf-8") as out:
            # ##CSI sentinel line, read by inventory/smpe_parser.py to stamp
            # every Zone parsed from this file with its owning CSI -- see
            # that module's docstring and doc/TODO.md ("8a. Zone.csi field").
            out.write("##CSI {}\n".format(args.csi))
            out.write(report_text)

    finally:
        if os.path.exists(cntl_path):
            os.remove(cntl_path)
        for dsn in (output_dsn, work_dsn):
            if dsn is not None:
                try:
                    datasets.delete(dsn)
                except Exception as exc:
                    print("WARNING: could not delete temp dataset {}: {}".format(dsn, exc))

    print("smplist: wrote LIST DDDEF/MOD/SYSMOD report for {} to {}"
          .format(args.zone, args.outfile))


if __name__ == "__main__":
    main()
