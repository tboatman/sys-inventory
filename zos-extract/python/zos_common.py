"""Shared helpers for the zos-extract Python scripts.

These scripts run under OMVS (z/OS UNIX shell) using IBM Open Enterprise
Python for z/OS. No FTP/Zowe transfer step is needed since the script
already runs on z/OS -- write straight to a USS path and copy that
off-host with scp/sftp.

MVS data set access goes entirely through TSO commands via `tsocmd`
(LISTDS to enumerate members, OPUT to copy a member's text into a USS
file with EBCDIC->ASCII conversion), rather than the special z/OS UNIX
"//'DSN'" MVS-dataset pathname syntax. That syntax depends on an optional,
site-configured physical file system that isn't present on every z/OS
system; LISTDS/OPUT are base TSO/E and always available.
"""

import subprocess
import sys


def list_pds_members(dsn):
    """List member names of a PDS/PDSE via `tsocmd LISTDS ... MEMBERS`."""
    try:
        result = subprocess.run(
            ["tsocmd", "LISTDS '{}' MEMBERS".format(dsn)],
            capture_output=True, text=True, timeout=60,
        )
    except FileNotFoundError:
        die("'tsocmd' is not available on this system")
    except subprocess.TimeoutExpired:
        die("tsocmd timed out running LISTDS against {}".format(dsn))

    if result.returncode != 0:
        die("LISTDS failed for {} (rc={}):\n{}"
            .format(dsn, result.returncode, result.stdout + result.stderr))

    members = []
    parsing = False
    for line in result.stdout.splitlines():
        if "--MEMBERS--" in line:
            parsing = True
            continue
        if not parsing:
            continue
        word = line.split()[0] if line.split() else ""
        if word:
            members.append(word)
    return sorted(members)


def read_member_lines(dsn, member, workdir=None):
    """Read one PDS member as text lines via TSO OPUT (EBCDIC->ASCII TEXT
    convert into a scratch USS file). Returns (lines, None) on success, or
    (None, detail) if OPUT couldn't read it (e.g. a RACF-protected member),
    where detail is OPUT's own message text for troubleshooting."""
    import os
    import tempfile

    fd, tmp_path = tempfile.mkstemp(dir=workdir, prefix="extrproc_", suffix=".mem")
    os.close(fd)
    os.remove(tmp_path)  # OPUT creates the file fresh

    cmd = "OPUT '{}({})' '{}' TEXT".format(dsn, member, tmp_path)
    try:
        result = subprocess.run(["tsocmd", cmd], capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "tsocmd timed out"

    if result.returncode != 0 or not os.path.exists(tmp_path):
        detail = (result.stdout + result.stderr).strip() or "rc={}".format(result.returncode)
        return None, detail

    try:
        with open(tmp_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read().splitlines(), None
    finally:
        os.remove(tmp_path)


def die(message, rc=8):
    sys.stderr.write("ERROR: {}\n".format(message))
    sys.exit(rc)
