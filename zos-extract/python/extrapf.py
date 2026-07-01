#!/usr/bin/env python3
"""extrapf.py -- Dump the live APF-authorized library list to a flat USS
text file. Used off-host (inventory/inventory/cli.py's _read_apf) to flag
whether a resolved load-library dataset is APF-authorized.

Captures live APF state via 'D PROG,APF' (rather than parsing the static
PROGxx PARMLIB member) to match the same precedent as extrlnk.py's LNKLST
capture: live state reflects the actual running system, including dynamic
SETPROG APF changes that PROGxx text alone wouldn't show.

Output format: one DSN per line, same shape as lnklst.txt, e.g.
  SYS1.LINKLIB
  SYS1.LPALIB
  MY.SITE.AUTHLIB

Run this from an OMVS shell:

  python3 extrapf.py --outfile /u/me/inventory/apf.txt

Implementation: issues 'D PROG,APF' via ZOAU's operator-command API
(zos_common.run_opercmd) and parses its reply the same way extrlnk.py
parses 'D PROG,LNKLST' (shared helper: zos_common.parse_numbered_dsn_list).
Same authority caveat as extrlnk.py: if console-command access is
unavailable/unauthorized, capture 'D PROG,APF' from SDSF/console manually
and save it as one DSN per line in --outfile.

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's wrapper
functions against your ZOAU version's API.
"""

import argparse

from zos_common import die, parse_numbered_dsn_list, run_opercmd

# CSV410I 'D PROG,APF' reply (FORMAT=DYNAMIC) looks like:
#   FORMAT=DYNAMIC
#   ENTRY  VOLUME  DSNAME
#      1   C3RES1  SYS1.LINKLIB
#      2   C3RES1  SYS1.LPALIB
# i.e. one 3-column row per entry, ENTRY numeric, DSNAME the last column.
# A site running FORMAT=STATIC gets a differently-framed reply; if this
# script reports "no APF entries parsed" on such a site, adjust
# expected_fields below to match your actual console reply.


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/apf.txt")
    args = p.parse_args()

    stdout_text, rc = run_opercmd("D PROG,APF")
    if rc != 0:
        die("opercmd failed with rc={}".format(rc))

    dsns = parse_numbered_dsn_list(stdout_text, expected_fields=3)

    if not dsns:
        die("no APF entries parsed from console reply:\n" + stdout_text)

    with open(args.outfile, "w", encoding="utf-8") as out:
        for dsn in dsns:
            out.write(dsn + "\n")

    print("extrapf: wrote {} APF-authorized data set names to {}".format(len(dsns), args.outfile))


if __name__ == "__main__":
    main()
