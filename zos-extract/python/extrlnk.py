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

Implementation: shells out to the `opercmd` USS utility to issue the MVS
console command 'D PROG,LNKLST' and parses its reply. This needs the same
console-command authority the original REXX needed via the TSO CONSOLE
service (most installations restrict MVS commands from general users). If
`opercmd` is unavailable or unauthorized at your site, capture
'D PROG,LNKLST' from SDSF/console manually and save it as one DSN per line
in the same --outfile.
"""

import argparse
import subprocess
import sys

from zos_common import die

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

    try:
        result = subprocess.run(
            ["opercmd", "D PROG,LNKLST"],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        die("'opercmd' is not available on this system; capture "
            "'D PROG,LNKLST' from SDSF/console manually instead.")
    except subprocess.TimeoutExpired:
        die("opercmd timed out waiting for the console reply")

    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        die("opercmd failed with rc={}".format(result.returncode))

    dsns = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        entry, _apf, _volume, dsname = fields
        if not entry.isdigit():
            continue
        dsns.append(dsname)

    if not dsns:
        die("no LNKLST entries parsed from console reply:\n" + result.stdout)

    with open(args.outfile, "w", encoding="utf-8") as out:
        for dsn in dsns:
            out.write(dsn + "\n")

    print("extrlnk: wrote {} LNKLST data set names to {}".format(len(dsns), args.outfile))


if __name__ == "__main__":
    main()
