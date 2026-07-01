#!/usr/bin/env python3
"""extrprocs.py -- Dump the command names of currently-running USS (z/OS
UNIX System Services) processes to a flat USS text file: the process side
of the "what's running right now" live snapshot (extrjobs.py is the
MVS/JES side).

Output format: one process command per line, e.g.
  /usr/sbin/sshd
  /bin/tcsh
  python3

Run this from an OMVS shell:

  python3 extrprocs.py --outfile /u/me/inventory/processes.txt

Implementation: shells out to the z/OS UNIX `ps -ef` command directly --
there's no ZOAU or SDSF angle here, since this is plain USS process
listing, not an MVS/JES concern. `-ef` is IBM's own documented way to
list every process known by USS (confirmed against IBM's published USS
Command Reference / Redbooks cheat sheet), not just the caller's own
session. `ps -ef`'s output is a fixed set of columns (UID PID PPID C
STIME TTY TIME) followed by the command as a free-form last field, which
this parses by splitting on whitespace a fixed number of times so a
command containing its own spaces (arguments) doesn't get truncated.

If your userid isn't authorized to see other users' processes, `ps -ef`
still runs but only shows your own -- ask your admin about BPX.SUPERUSER
or equivalent if you need the full system-wide view.
"""

import argparse
import subprocess

from zos_common import die

_PS_COLUMNS_BEFORE_CMD = 7  # UID PID PPID C STIME TTY TIME, then CMD


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/processes.txt")
    args = p.parse_args()

    try:
        result = subprocess.run(["ps", "-ef"], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        die("'ps' is not available on this system")
    except subprocess.TimeoutExpired:
        die("ps timed out")

    if result.returncode != 0:
        die("ps failed (rc={}): {}".format(result.returncode, result.stderr))

    lines = result.stdout.splitlines()
    if lines:
        lines = lines[1:]  # drop the "UID PID PPID C STIME TTY TIME CMD" header

    names = []
    for line in lines:
        fields = line.split(maxsplit=_PS_COLUMNS_BEFORE_CMD)
        if len(fields) <= _PS_COLUMNS_BEFORE_CMD:
            continue  # short/malformed line, skip rather than guess
        names.append(fields[_PS_COLUMNS_BEFORE_CMD])

    if not names:
        die("no processes parsed from ps -ef output:\n" + result.stdout)

    with open(args.outfile, "w", encoding="utf-8") as out:
        for name in names:
            out.write(name + "\n")

    print("extrprocs: wrote {} process names to {}".format(len(names), args.outfile))


if __name__ == "__main__":
    main()
