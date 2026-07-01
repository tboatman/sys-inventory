#!/usr/bin/env python3
"""extrproc.py -- Dump every member of a PDS/PDSE (PROCLIB, PARMLIB, or any
single library in a concatenation) to a flat USS text file for off-host
parsing by the `inventory` package.

Replaces zos-extract/rexx/EXTRPROC.rexx and EXTRPARM.rexx (PARMLIB members
are plain text too, so one script covers both).

Output format (one record stream, easy for a line-oriented parser):
  ##MEMBER MEMBERNAME   <- sentinel header, never valid JCL/parmlib text
  <raw member text, one line per record, unchanged>
  ##MEMBER MEMBERNAME   <- header line for next member
  ...
The "##MEMBER " prefix is reserved: it cannot appear as a literal JCL or
parmlib statement (those always start with "//" or are PARMLIB-specific
keywords), so the off-host parser can split on it unambiguously.

Run this from an OMVS shell (or batch via BPXBATCH sh):

  python3 extrproc.py --indsn SYS1.PROCLIB --outfile /u/me/inventory/00_proclib.txt
  python3 extrproc.py --indsn SYS1.PARMLIB --outfile /u/me/inventory/00_parmlib.txt

Requires READ access to --indsn. Members are read via TSO OPUT (TEXT mode,
which converts EBCDIC to ASCII), so members you aren't authorized to read
are skipped with a warning rather than aborting the whole dump -- some
sites restrict specific members (e.g. started-task procs) at a finer grain
than the library itself.

Run once per library in the PROCLIB/PARMLIB concatenation; name --outfile
NN_libname.txt (NN = position in the concatenation, low = searched first)
so the off-host resolver can preserve search order and break member-name
ties -- see zos-extract/README.md.
"""

import argparse
import fnmatch
import os

from zos_common import die, list_pds_members, read_member_lines


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--indsn", required=True,
                   help="source PDS/PDSE to dump, e.g. SYS1.PROCLIB")
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/00_proclib.txt")
    p.add_argument("--members", default="*",
                   help="member name filter, '*'/'?' wildcards supported (default: all)")
    args = p.parse_args()
    workdir = os.path.dirname(os.path.abspath(args.outfile)) or None

    all_members = list_pds_members(args.indsn)
    if not all_members:
        die("no members found in {}".format(args.indsn))

    pattern = args.members.upper()
    selected = [m for m in all_members if fnmatch.fnmatchcase(m.upper(), pattern)]
    if not selected:
        die("no members of {} matched filter {}".format(args.indsn, args.members))

    total = 0
    with open(args.outfile, "w", encoding="utf-8") as out:
        for member in selected:
            lines, detail = read_member_lines(args.indsn, member, workdir=workdir)
            if lines is None:
                # OPUT can't read some members (e.g. RACF-protected ones);
                # skip and keep going rather than aborting the whole dump.
                print("extrproc: could not read member {}, skipped ({})"
                      .format(member, detail))
                continue
            out.write("##MEMBER {}\n".format(member))
            for line in lines:
                out.write(line + "\n")
            total += 1

    print("extrproc: dumped {} of {} members from {} to {}"
          .format(total, len(selected), args.indsn, args.outfile))


if __name__ == "__main__":
    main()
