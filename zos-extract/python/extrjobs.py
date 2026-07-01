#!/usr/bin/env python3
"""extrjobs.py -- Dump the names of currently-active z/OS jobs and started
tasks to a flat USS text file: a live, point-in-time snapshot of what's
actually running right now. This is the MVS/JES side of the "what's
running" pair; extrprocs.py is the USS process side.

This is a different thing from extrproc.py's IEFSSNxx/COMMNDxx dumps
(steps 1-2 in zos-extract/README.md), which say what's *defined* to
exist/auto-start -- this says what's *actually executing this instant*.
The off-host inventory can cross-reference the two (e.g. "is this
defined-to-auto-start task from COMMNDxx actually running right now").

Output format: one active job/task per line, space-separated
"job_id name job_type asid", e.g.
  STC03801 CICSPROD STC 0043
  JOB01234 PAYROLL JOB 0091

Run this from an OMVS shell:

  python3 extrjobs.py --outfile /u/me/inventory/active_jobs.txt

Implementation: ZOAU's jobs.fetch_multiple() lists every job/task JES
currently knows about, in any state (queued, active, or sitting on the
output queue) -- this filters to status == "ACTIVE" to get just what's
actually executing right now (confirmed against ibm_zos_core's job.py,
which maps this same ZOAU call's entries' .status/.asid/.job_type fields
the same way this script does).

Requires ZOAU; if `zoautil_py` imports fail, check zos_common.py's module
docstring for the version-difference note.
"""

import argparse

from zos_common import die

from zoautil_py import jobs


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--outfile", required=True,
                   help="USS output text file path, e.g. /u/me/inventory/active_jobs.txt")
    args = p.parse_args()

    try:
        entries = jobs.fetch_multiple(include_extended=True)
    except Exception as exc:
        die("could not list active jobs: {}".format(exc))

    active = [e for e in (entries or []) if e.status == "ACTIVE"]

    if not active:
        die("no active jobs found -- unexpected, at minimum core system "
            "started tasks (JES2/JES3, master scheduler, ...) should be "
            "active; this likely means the ZOAU call above isn't behaving "
            "as documented on your system")

    with open(args.outfile, "w", encoding="utf-8") as out:
        for entry in active:
            job_type = (entry.job_type or "?").strip() or "?"
            asid = entry.asid or "?"
            out.write("{} {} {} {}\n".format(entry.job_id, entry.name, job_type, asid))

    print("extrjobs: wrote {} active jobs/tasks to {}".format(len(active), args.outfile))


if __name__ == "__main__":
    main()
