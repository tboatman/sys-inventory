#!/usr/bin/env python3
"""extrsys.py -- Capture single-record system identity metadata (LPAR
name/SYSCLONE, sysplex name, SYSRES IPL volume, IPL parm member) via
'D SYMBOLS' and 'D IPLINFO', to one flat USS text file for off-host
parsing by inventory/inventory/sysinfo_parser.py.

This identity record exists so that once the pipeline scales to merging
inventories from multiple systems into one DB (see "Scaling" in
inventory/README.md), each ingest run can be tied to the system it came
from.

Output format: reuses the project's "##" sentinel convention (see
extrproc.py), generalized from "member name" to "block name" -- one
sentinel line per console command's raw reply, e.g.:

  ##SYMBOLS
  <raw 'D SYMBOLS' console reply text, unchanged>
  ##IPLINFO
  <raw 'D IPLINFO' console reply text, unchanged>

Run this from an OMVS shell:

  python3 extrsys.py --outfile /u/me/inventory/sysinfo.txt

Implementation: issues 'D SYMBOLS' and 'D IPLINFO' via ZOAU's
operator-command API (zos_common.run_opercmd) and writes both raw replies,
sentinel-delimited, for off-host parsing. Same authority caveat as
extrlnk.py/extrapf.py: if console-command access is unavailable or
unauthorized, capture both commands from SDSF/console manually and paste
them into --outfile under the '##SYMBOLS' / '##IPLINFO' sentinel lines
above.

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's wrapper
functions against your ZOAU version's API.
"""

import argparse

from zos_common import die, run_opercmd


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/sysinfo.txt")
    args = p.parse_args()

    symbols_out, symbols_rc = run_opercmd("D SYMBOLS")
    if symbols_rc != 0:
        die("opercmd failed for 'D SYMBOLS' (rc={})".format(symbols_rc))

    iplinfo_out, iplinfo_rc = run_opercmd("D IPLINFO")
    if iplinfo_rc != 0:
        die("opercmd failed for 'D IPLINFO' (rc={})".format(iplinfo_rc))

    with open(args.outfile, "w", encoding="utf-8") as out:
        out.write("##SYMBOLS\n")
        out.write(symbols_out)
        if not symbols_out.endswith("\n"):
            out.write("\n")
        out.write("##IPLINFO\n")
        out.write(iplinfo_out)
        if not iplinfo_out.endswith("\n"):
            out.write("\n")

    print("extrsys: wrote D SYMBOLS + D IPLINFO output to {}".format(args.outfile))


if __name__ == "__main__":
    main()
