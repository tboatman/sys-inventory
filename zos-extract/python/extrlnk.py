#!/usr/bin/env python3
"""extrlnk.py -- Dump the active LNKLST data set concatenation, in search
order, to a flat USS text file. Used by the off-host resolver as the
fallback search order for PGM= references that have no explicit
STEPLIB/JOBLIB DD.

Replaces zos-extract/rexx/EXTRLNK.rexx.

Output format: one DSN per line, in LNKLST search order, e.g.
  SYS1.LINKLIB
  SYS1.CSSLIB
  MY.SITE.LINKLIB

Run this from an OMVS shell:

  python3 extrlnk.py --outfile /u/me/inventory/lnklst.txt

Implementation: issues the MVS console command 'D PROG,LNKLST' via ZOAU's
operator-command API (zos_common.run_opercmd) and parses its reply. This
needs the same console-command authority the original REXX needed via the
TSO CONSOLE service (most installations restrict MVS commands from general
users). If console-command access is unavailable or unauthorized at your
site, capture 'D PROG,LNKLST' from SDSF/console manually and save it as one
DSN per line in the same --outfile.

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's wrapper
functions against your ZOAU version's API.
"""

import argparse

from zos_common import die, parse_numbered_dsn_list, run_opercmd

# CSV470I 'D PROG,LNKLST' reply looks like:
#   LNKLST SET LNKLST00   LNKAUTH=LNKLST
#   ENTRY  APF  VOLUME  DSNAME
#      1    A   C3RES1  SYS1.LINKLIB
#      2    A   C3RES1  SYS1.MIGLIB
# i.e. one 4-column row per entry, ENTRY being numeric and DSNAME the last
# (and only reliably `.`-containing) column.


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/lnklst.txt")
    args = p.parse_args()

    stdout_text, rc = run_opercmd("D PROG,LNKLST")
    if rc != 0:
        die("opercmd failed with rc={}".format(rc))

    dsns = parse_numbered_dsn_list(stdout_text, expected_fields=4)

    if not dsns:
        die("no LNKLST entries parsed from console reply:\n" + stdout_text)

    with open(args.outfile, "w", encoding="utf-8") as out:
        for dsn in dsns:
            out.write(dsn + "\n")

    print("extrlnk: wrote {} LNKLST data set names to {}".format(len(dsns), args.outfile))


if __name__ == "__main__":
    main()
