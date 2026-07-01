#!/usr/bin/env python3
"""smplist.py -- Drive standard SMP/E LIST commands against one CSI/zone and
capture the printed report as a USS text file for off-host parsing by
inventory/smpe_parser.py.

Replaces zos-extract/jcl/SMPLIST.jcl. Run once per target zone you want in
the inventory.

This is a thin wrapper around zos-extract/rexx/SMPDRV.rexx, which does the
actual work (ALLOC the SMP/E DDs, CALL GIMSMP, FREE/DELETE work data
sets). It has to be a REXX exec rather than pure Python: TSO dynamic
allocation is scoped to one address space, so the ALLOCs and the GIMSMP
CALL that uses them must run in one continuous TSO/E environment -- and
each `tsocmd` call from a shell spawns a fresh one. REXX (like the
original EXTRPROC.rexx) is what stays in a single environment start to
finish; trying to generate and inject that logic from Python at runtime
just adds an ASCII<->EBCDIC transcoding step with no benefit.

One-time setup: upload zos-extract/rexx/SMPDRV.rexx into a PDS in your
TSO exec library concatenation via your normal text-mode transfer process
(same as any other REXX member), then pass that library as --execlib.

Run this from an OMVS shell:

  python3 smplist.py --execlib YOUR.EXEC.LIB --csi YOUR.GLOBAL.CSI \\
      --zone TZONE1 --workhlq YOURID.SMPLIST \\
      --outfile /u/me/inventory/tzone1.smplist.txt

SMP/E itself only needs READ access to the CSI for LIST commands (no
APPLY/ACCEPT/RECEIVE), so this is safe to run broadly. If GIMSMP isn't in
your LNKLST, pass --steplib with the SMP/E load library that contains it.

Requires `tsocmd` (standard z/OS UNIX utility) and READ authority to
--csi.
"""

import argparse
import subprocess
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--execlib", required=True,
                   help="PDS containing SMPDRV (uploaded from zos-extract/rexx/SMPDRV.rexx)")
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

    parms = "CSI({}) ZONE({}) OUTFILE({}) WORKHLQ({})".format(
        args.csi, args.zone, args.outfile, args.workhlq)
    if args.steplib:
        parms += " STEPLIB({})".format(args.steplib)

    cmd = "EX '{}(SMPDRV)' '{}'".format(args.execlib, parms)
    try:
        result = subprocess.run(["tsocmd", cmd], capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        sys.stderr.write("ERROR: 'tsocmd' is not available on this system\n")
        sys.exit(8)
    except subprocess.TimeoutExpired:
        sys.stderr.write("ERROR: SMPDRV timed out\n")
        sys.exit(8)

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    # SMP/E LIST commands return RC=0 (clean) or RC=4 (informational, e.g.
    # an empty LIST FILE section); anything higher is a real error.
    if result.returncode > 4:
        sys.stderr.write("ERROR: SMPDRV/GIMSMP failed (rc={}); see {} for SMP/E messages\n"
                          .format(result.returncode, args.outfile))
        sys.exit(8)

    print("smplist: wrote LIST DDDEF/MOD/SYSMOD report for {} to {}"
          .format(args.zone, args.outfile))


if __name__ == "__main__":
    main()
