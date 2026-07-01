"""Shared helpers for the zos-extract Python scripts.

These scripts run under OMVS (z/OS UNIX shell) using IBM Open Enterprise
Python for z/OS. No FTP/Zowe transfer step is needed since the script
already runs on z/OS -- write straight to a USS path and copy that
off-host with scp/sftp.

All MVS data set and operator-command access goes through ZOAU (Z Open
Automation Utilities)'s `zoautil_py` Python API rather than shelling out to
`tsocmd`/`opercmd`. ZOAU is already an implicit dependency of this project
(`opercmd`, used elsewhere in zos-extract, is itself a ZOAU CLI utility, not
a bare z/OS component), so this just makes that dependency explicit and
uses more of what ZOAU offers: `datasets` for member listing/reading
(faster and simpler than `tsocmd LISTDS`/`OPUT` + a scratch USS tempfile),
and its operator-command API instead of shelling to the `opercmd` binary.

Requires ZOAU installed with `zoautil_py` on PYTHONPATH. This module uses
the current (ZOAU ~1.2+) lowercase-module API --
`from zoautil_py import datasets, opercmd`, calling module-level functions
like `datasets.list_members(dsn)`/`datasets.read(dsn)` and
`opercmd.execute(command, timeout=...)` -- confirmed against IBM's own
published samples (github.com/IBM/zoau-samples) and the `ibm_zos_core`
Ansible collection's source (which wraps these same calls), both fetched
and cross-checked while writing this. Older ZOAU releases (~1.0.x, the
"Master the Mainframe" era) exposed a different, PascalCase API
(`from zoautil_py import Datasets`, `Datasets.read(...)`) -- if these
imports fail on your system, that's almost certainly why; every ZOAU call
in this project is isolated to this one file (plus the DD-statement
construction local to `smplist.py`) so adjusting for your installed
version only means editing here.
"""

import sys

from zoautil_py import datasets, opercmd


def list_pds_members(dsn):
    """List member names of a PDS/PDSE via ZOAU's datasets.list_members()."""
    try:
        members = datasets.list_members(dsn)
    except Exception as exc:
        die("could not list members of {}: {}".format(dsn, exc))
    return sorted(members)


def read_member_lines(dsn, member, workdir=None):
    """Read one PDS member as text lines via ZOAU's datasets.read(). Returns
    (lines, None) on success, or (None, detail) if the member couldn't be
    read (e.g. a RACF-protected member), where detail is the underlying
    error text for troubleshooting.

    `workdir` is accepted for backward compatibility with callers that
    used to pass it for a scratch-file location; ZOAU's datasets.read()
    doesn't need a USS tempfile, so it's unused now.
    """
    try:
        content = datasets.read("{}({})".format(dsn, member))
    except Exception as exc:
        return None, str(exc)
    if content is None:
        return None, "no content returned for {}({})".format(dsn, member)
    return content.splitlines(), None


def run_opercmd(command, timeout=30):
    """Issue an MVS console command via ZOAU's opercmd.execute(). Returns
    (stdout_text, rc). `timeout` is in seconds, like every other timeout in
    this project.

    IMPORTANT: as of ZOAU 1.3.0, opercmd.execute()'s own `timeout` argument
    is in *centiseconds*, not seconds -- confirmed against ibm_zos_core's
    zos_operator.py module, which explicitly converts before calling it
    ("as of ZOAU v1.3.0, timeout is measured in centiseconds"). This
    wrapper does that conversion so every caller in this project can keep
    thinking in seconds. If your ZOAU version predates that change and
    takes plain seconds, drop the `* 100` below.
    """
    try:
        response = opercmd.execute(command, timeout=timeout * 100)
    except Exception as exc:
        die("opercmd failed for '{}': {}".format(command, exc))
    return response.stdout_response, response.rc


def parse_numbered_dsn_list(stdout_text, expected_fields):
    """Parse a console reply shaped as a numbered list of data set names,
    e.g. 'D PROG,LNKLST' (4 columns: ENTRY APF VOLUME DSNAME) or
    'D PROG,APF' (3 columns: ENTRY VOLUME DSNAME). Common shape across both:
    the first column is a numeric entry number and the last column is the
    DSN; any non-matching row (banners, headers) is skipped.

    Returns a list of DSNs in reply order."""
    dsns = []
    for line in stdout_text.splitlines():
        fields = line.split()
        if len(fields) != expected_fields:
            continue
        entry = fields[0]
        if not entry.isdigit():
            continue
        dsns.append(fields[-1])
    return dsns


def die(message, rc=8):
    sys.stderr.write("ERROR: {}\n".format(message))
    sys.exit(rc)
