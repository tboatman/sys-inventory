# ansible

Orchestrates step 1 of the pipeline described in the top-level
[`README.md`](../README.md) and [`zos-extract.md`](zos-extract.md)
via Ansible, instead of you SSHing into each LPAR by hand and running every
`zos-extract/python/*.py` script and `scp` one at a time. Each of that
pipeline's steps is reimplemented here as a direct
[`ibm.ibm_zos_core`](https://github.com/ansible-collections/ibm_zos_core)
module call (`zos_operator`, `zos_apf`, `zos_job_query`, `zos_find`/
`zos_fetch`, `zos_mvs_raw`, ...) instead of staging and shelling out to the
Python script for that step -- see the header comment in each
`roles/zos_extract/tasks/*.yml` file for exactly which module replaces
which script/ZOAU call, and why. Every step writes its result straight to a
local directory ready for `inventory ingest` (see
[`inventory.md`](inventory.md)) -- there's no separate
"copy the output off-host" step, since these modules return their results
to the control node directly.

## Why native modules instead of running the Python scripts

`zos_common.py`'s own docstring already notes that this project's ZOAU calls
were cross-checked against `ibm_zos_core`'s source, since it wraps the same
`zoautil_py` API this pipeline uses directly -- so `ibm_zos_core` already had
a purpose-built module for nearly everything `zos-extract/python/` does by
hand: `zos_apf` for the APF list, `zos_job_query` for active jobs,
`zos_mvs_raw` for the raw MVS program invocations (GIMSMP/IDCAMS/IRRDBU00),
`zos_find`/`zos_fetch`/`zos_stat` for dataset/member listing and attributes,
and `zos_operator` for the couple of console commands with no more specific
module (`D PROG,LNKLST`, `D SYMBOLS`, `D IPLINFO`). Using those directly
means Ansible manages the DD/dataset allocate-read-back-delete lifecycle
declaratively instead of the hand-rolled `datasets.tmp_name()`+`create()`+
`read()`+`delete()` dance the original scripts needed, and there's no
separate "stage the scripts, then fetch the output back" round trip.

Every task file reconstructs its output in the **exact same text format**
the original script produced (same `##MEMBER`/`##SYMBOLS`/`##NONVSAM`
sentinels, same "one DSN per line" shape, etc.), so
`inventory/inventory/*_parser.py` needs no changes to ingest it.

One step keeps the "nicer structured result" module documented but unused:
`sysinfo.yml` sticks with `zos_operator`'s raw `D SYMBOLS`/`D IPLINFO` text
rather than `zos_gather_facts`'s structured JSON, specifically to stay
byte-for-byte compatible with `sysinfo_parser.py`'s raw-text parsing -- see
that file's header comment.

## Prerequisites

Everything in `zos-extract.md`'s "Before you start" section still
applies (OMVS shell, IBM Open Enterprise Python, ZOAU, read authority) --
these modules still shell out to ZOAU/`zoautil_py` on the target under the
hood, they just do it through `ibm_zos_core` instead of
`zos-extract/python/`'s own wrapper code. On top of that:

- Ansible on your control node (wherever you run `ansible-playbook` from --
  your laptop, a CI runner, etc.), plus the collection this directory
  depends on:
  ```
  ansible-galaxy collection install -r requirements.yml
  ```
- SSH access from that control node to each LPAR's OMVS shell as the userid
  that has the READ/console-command authority `zos-extract.md`
  describes.

## Setup

```
cp inventory/hosts.yml.example inventory/hosts.yml
```

Edit `inventory/hosts.yml` (gitignored -- it'll hold your real dataset
names and hostnames): add one entry under `zos.hosts` per LPAR, and fill in
`zos_extract_proclibs`/`zos_extract_parmlibs`/`zos_extract_smpe_csis`/`zos_extract_catalog_patterns` for each.
`inventory/group_vars/zos.yml` has the shared ZOAU/Python environment variables from
`zos-extract.md`'s "Basic Env requirements" section -- adjust the
paths there if your site installs ZOAU/Python somewhere else. That
environment is applied at the play level (`playbooks/site.yml`) since
`ibm_zos_core`'s modules need it too, not just raw shell commands.

## Running it

```
cd ansible
ansible-playbook playbooks/site.yml
```

This runs every step (except RACF, see below) against every host in the
`zos` group and leaves the results in `output/<lpar-name>/` -- hand that
directory straight to `inventory ingest`:

```
cd ../inventory
inventory ingest ../ansible/output/lpar1/
```

Run a subset with `--tags` (each tag matches one numbered step in
`zos-extract.md`):

```
ansible-playbook playbooks/site.yml --tags lnklst,apf
ansible-playbook playbooks/site.yml --limit lpar1 --tags activity
```

Available tags: `proclib`, `ssn_commnd`, `ifaprd`, `parmlib_snapshot`,
`ieasys_snapshot`,
`lnklst`, `apf`,
`sysinfo`, `uss_mounts`, `jes2parm`, `vtam`, `tcpip`, `sms`, `wlm`,
`smplist`, `activity`, `catalog`, `cics`, `db2`, `racf`, `wlm_zosmf`.
`wlm_zosmf` (like `racf`) is gated `never` -- it only runs when
explicitly requested with `--tags wlm_zosmf`, normally via the dedicated
`playbooks/wlm_zosmf.yml` entry point (see below), not `site.yml`.
`smplist`/`catalog` only run on hosts where `zos_extract_smpe_csis`/
`zos_extract_catalog_patterns` are actually set, so it's safe to leave them
out of `hosts.yml` for LPARs you don't want those steps on.

`parmlib_snapshot` is a deliberately explicit, separate tag: unlike
`proclib`/`ssn_commnd`/`ifaprd` (which each trigger `discover_parmlib.yml`'s
own *implicit* `D PARMLIB` call as internal plumbing -- only issued when
`zos_extract_parmlibs` isn't already configured, and never saved anywhere),
this always issues `D PARMLIB` and writes the raw reply to
`parmlib_snapshot.txt`, ingested as its own dimension (`inventory
parmlib`) -- request it explicitly with `--tags parmlib_snapshot`, or via
an untagged full run.

**`D PARMLIB` only reports the PARMLIB dataset search order, not any
member's actual content** -- that's not what the command is for. The
real system parameters ("the parms") live in the active IEASYSxx
member(s), and `ieasys_snapshot` is the tag for those: `discover_active_
members.yml` already fetches that exact content internally (to pull out
just `SSN=`/`CMD=`/`PROD=`/`MSTRJCL=` for its own use, then discards it)
-- `ieasys_snapshot` reuses that same fetch (its tag is also added to
`discover_active_parmlib_suffixes.yml`/`discover_active_members.yml`, so
it pulls in that discovery chain standalone) and writes the full member
content to `ieasys_snapshot.txt`, ingested generically (every
`KEYWORD=value` statement, not just the three this pipeline already
cared about) via `inventory ieasys`.

### Running it against a system that isn't in `hosts.yml` yet

`playbooks/interactive.yml` prompts for connection details instead of
requiring them in `inventory/hosts.yml` -- useful for a one-off run against
a system you haven't added to inventory, or don't want to:

```
ansible-playbook playbooks/interactive.yml
```

It asks for the hostname/IP, username, password (leave blank to use
key-based auth via your normal `ssh` config/agent instead), and SSH port,
then runs the same role against just that system. Everything else --
which steps run, `zos_extract_proclibs`/`zos_extract_smpe_csis`/
`zos_extract_catalog_patterns`/... -- still comes from
`roles/zos_extract/defaults/main.yml` and `inventory/group_vars/zos.yml`,
same as `playbooks/site.yml`; override those with `-e` as needed, e.g.:

```
ansible-playbook playbooks/interactive.yml \
  -e '{"zos_extract_proclibs": [{"dsn": "SYS1.PROCLIB", "prefix": "00"}]}'
```

`--tags`/`--limit` work the same as with `playbooks/site.yml`. Answering
the password prompt needs `sshpass` installed on your control node, the
same as any Ansible password-based SSH connection -- if you don't have
it, leave the prompt blank and rely on key-based auth instead.

### PROCLIB/PARMLIB and active-member auto-discovery

You don't have to hand-populate `zos_extract_proclibs`/`zos_extract_parmlibs`,
and `ssn_commnd`/`ifaprd` don't have to dump every `IEFSSN*`/`COMMND*`/
`IFAPRD*` member -- this role can work it all out live instead:

1. **`discover_proclib.yml`** -- if `zos_extract_proclibs` isn't set, it
   queries the live PROCLIB concatenation via JES2's `$D PROCLIB` command,
   in search (DD) order. This is JES2-specific -- there's no system-wide
   MVS console command for PROCLIB the way `D PARMLIB` covers PARMLIB, and
   JES3 sites haven't been verified against this parser, so configure
   `zos_extract_proclibs` by hand if your site is JES3 or this doesn't
   find anything. An explicit list in `hosts.yml` always wins over this.
2. **`discover_parmlib.yml`** -- if `zos_extract_parmlibs` isn't set, it
   queries the live PARMLIB concatenation via `D PARMLIB` (a real
   system-wide MVS console command, same idea as the existing LNKLST
   discovery), in search order. An explicit list in `hosts.yml` always
   wins over this too.
3. **`discover_active_parmlib_suffixes.yml`** + **`discover_active_members.yml`**
   -- `D IPLINFO`'s `IEASYM LIST`/`IEASYS LIST` give the active
   `IEASYSxx`/`IEASYMxx` suffix(es); this role then reads the actual
   content of those `IEASYSxx` member(s) and pulls out their `SSN=`/
   `CMD=`/`PROD=`/`MSTRJCL=` keyword values -- the *real* mechanism z/OS
   uses to select the active `IEFSSNxx`/`COMMNDxx`/`IFAPRDxx`/`MSTJCLxx`
   member, as opposed to assuming they share the same suffix by
   convention. `ssn_commnd.yml`/`ifaprd.yml` use those suffixes (when
   found) to fetch just the active member(s) instead of every member
   matching the wildcard filter. If this comes up empty for any reason
   (unreadable `IEASYSxx`, unexpected `D IPLINFO` format, etc.), it falls
   back to the broad wildcard filter automatically -- no separate flag to
   flip.
4. **`discover_mstrjcl_proclibs.yml`** -- fills a real gap in step 1:
   `$D PROCLIB` only reports JES2's own PROCLIB concatenation (used to
   resolve batch job PROCs), not the separate one the master scheduler
   uses to resolve `START`/`S` command PROCs for started tasks, which
   comes from the `IEFPDSI` DD inside the `MSTJCLxx` member (selected by
   the `MSTRJCL=` suffix from step 3). A site can concatenate extra
   proclib datasets straight onto that DD without ever touching JES2's
   own PROCLIB definition -- confirmed as a real site's setup -- so this
   fetches the active `MSTJCLxx` member (from wherever it's found in
   `zos_extract_proclibs`), pulls every `DSN=` out of the `IEFPDSI` DD
   group (the DD itself plus any unnamed concatenated DD statements after
   it), and appends any not already known to `zos_extract_proclibs` before
   `proclib.yml` dumps everything. Skipped entirely if `MSTRJCL=` wasn't
   found in step 3.

Each of these is tagged with exactly the step(s) that need it, not `always`
-- `discover_proclib.yml` is tagged `proclib`; `discover_parmlib.yml` is
tagged `proclib, ssn_commnd, ifaprd` (all three consume the PARMLIB list);
`discover_active_parmlib_suffixes.yml`/`discover_active_members.yml` are
tagged `proclib, ssn_commnd, ifaprd` (`proclib` needs them too now, for the
`MSTRJCL=` suffix `discover_mstrjcl_proclibs.yml` consumes);
`discover_mstrjcl_proclibs.yml` is tagged `proclib` only. So e.g.
`--tags catalog` or `--tags smpe_csi_discovery` alone doesn't also issue
`$D PROCLIB`/`D PARMLIB`/`D IPLINFO`, fetch `IEASYSxx` members, or fetch
`MSTJCLxx` for no reason -- a tagless run still does all of it, same as
before, since Ansible runs every task when no `--tags`/`--skip-tags` is
given regardless of what tags it carries.

### Finding your SMP/E CSI(s) and their zones if you don't already know them

`zos_extract_smpe_csis` (used by `smplist.yml`) has to be set by hand -- unlike
PROCLIB/PARMLIB, there's no system command that enumerates registered CSIs
(SMP/E doesn't register a CSI anywhere central; it's just a VSAM KSDS a site
chooses to use as one). A real site can have several distinct CSIs (its own
product CSIs alongside the base z/OS one), so this is a list of `{csi,
zones}` entries even for a single-CSI site -- see
`inventory/hosts.yml.example`. If you don't know a CSI's name yet, run:

```
ansible-playbook playbooks/site.yml --tags smpe_csi_discovery --limit lpar1
```

This searches the catalog with `zos_find` (`resource_type: cluster`), the
same module `catalog.yml` uses for its non-VSAM search, and writes matches to
`smpe_csi_candidates.txt` -- a naming-heuristic list, not a verified one.
Confirm a candidate is really usable as an `SMPCSI` (e.g. by pointing
`smplist.yml` at it) before adding it to `zos_extract_smpe_csis`.

`zos_extract_smpe_csi_search_patterns` defaults to `["EDUC.**.CSI"]`
(`roles/zos_extract/defaults/main.yml`) since that's this site's actual
convention -- every CSI lives under the `EDUC` HLQ. Override it in
`hosts.yml` if yours differs. Keep the leading qualifier literal (e.g.
`SMPE.*.CSI`, not `*.CSI` or `**.CSI`): `zos_find`'s own docs say it "does
not support wildcards for high level qualifiers" -- confirmed the hard way,
a real run against a `**.CSI`-only pattern (no shared prefix) silently
returned nothing, no error. A genuinely suffix-only convention with no
shared prefix has no catalog-search primitive on z/OS at all -- the only way
to find those is an unrestricted `LISTCAT ALL` scan of the whole catalog
followed by a client-side filter, which is real overkill once (like here)
there's a literal prefix to anchor on instead.

Once you know a CSI's name but not its zones (rather than guessing at
`TZONE1`/`TARGET`-style conventions), run:

```
ansible-playbook playbooks/site.yml --tags smpe_zone_discovery --limit lpar1
```

This runs GIMSMP's `LIST GLOBALZONE` against every CSI already listed in
`zos_extract_smpe_csis` -- unlike CSI discovery above, this isn't a naming
heuristic: a CSI's own global zone genuinely knows every zone tied to it,
via its `ZONEINDEX` attribute. Writes one `*.smpzones.txt` per CSI, which
`inventory ingest` picks up and `inventory zone-index` shows (see
`inventory/README.md`) -- not yet confirmed against a real reply from this
site, only against a third-party reference implementation, so tune
`smpe_parser.parse_globalzone()`'s regexes if it comes back empty.

### zos_job_query is unusable here -- activity/CICS/DB2 all route around it

`activity.yml` (tag `activity`), `cics.yml` (tag `cics`), and `db2.yml`
(tag `db2`) all avoid `ibm.ibm_zos_core`'s `zos_job_query`, which was tried
first and crashed ZOAU's own `jls` utility on a real run:

```
CEE3209S The system detected a fixed-point divide exception
(System Completion Code=0C9) ... at entry point parseSMFRecord
```

Root cause, confirmed by reading `ibm_zos_core`'s own
`module_utils/job.py`: `zos_job_query` unconditionally calls
`jobs.fetch_multiple(..., include_extended=True)` no matter what `job_name`
is passed (its own code comment: "Observation shows the job_name parameter
is not being used, so we will drop that"). `include_extended` is what pulls
in the SMF-derived fields (`program_name`, `cpu_time`, `srb_time`), and
it's specifically SMF-record parsing that's crashing -- so narrowing the
query pattern was never going to help, and there's no module option to
turn `include_extended` off. `zos_job_query` is unusable here for any
job_name/pattern as a result.

**`activity.yml`** doesn't need those SMF-derived fields at all, so it
calls ZOAU's `jls` binary directly (`ansible.builtin.command`, same as this
file's own `ps -ef` call) requesting every *other* field jls exposes --
`owner,name,id,status,ccode,jobclass,serviceclass,priority,asid,creationdate,`
`creationtime,queueposition,jobtype,executiontime,executionseconds,system,`
`subsystem,onode,xnode,membname` -- confirmed against a real run to avoid
the crash entirely (`rc: 0`, hundreds of jobs) while capturing far more than
the original `extrjobs.py` dump did. `active_jobs.txt` is JSON Lines (one
job object per line, jls's own field names) rather than a fixed four-column
format as a result; `inventory/inventory/models.py`'s `ActiveJob` and
`activity_parser.py`'s `parse_active_jobs()` were updated to match.
`extrjobs.py`'s own plain `jobs.fetch_multiple()` call (no
`include_extended`) presumably never hit the crash for the same reason.

**`cics.yml`/`db2.yml`** need `PROCSTEP`, which isn't one of `jls`'s
available fields, so they consume `discover_active_address_spaces.yml`'s
shared `D A,L` (Display Active, Long form) console command instead (tagged
`cics, db2`, so it only runs once if both tags are selected together).
`D A,L` sidesteps ZOAU/`jls` entirely, going straight to MVS, at the cost
of a narrower field set than `jls` provides (job name, step name,
`PROCSTEP`, status -- no job ID or ASID, which these two don't need
anyway). An address space counts as CICS if its `PROCSTEP` is literally
`CICS` (true for every CICS region in a real reply from this site) **or**
its job name matches `zos_extract_cics_job_patterns` (`CTS*`, `ECB2*`,
`MTSEDUC*`); DB2 the same way via `PROCSTEP` `DB2PROC` **or**
`zos_extract_db2_job_patterns` (`DB2*`) -- OR'd together as a fallback in
case some address space doesn't use the expected `PROCSTEP`. Both are
opt-in (skipped unless their respective patterns are configured) and both
are a naming/content heuristic, not authoritative, same as the CSI
candidate list.

### RACF (step 10) is opt-in on purpose

Per `zos-extract.md`, `extrracf.py` needs a materially different and
harder-to-get authorization (READ access to a RACF database **copy**), and
its output is explicitly implementation-only / not yet production-validated.
This role won't run it unless you both set `zos_extract_racf_database_dsn` in
`hosts.yml` **and** pass `--tags racf` explicitly:

```
ansible-playbook playbooks/site.yml --tags racf --limit lpar1
```

### USS mounts and JES2 init parameters (all confirmed against real replies)

`uss_mounts.yml` (`D OMVS,F`) and `discover_jes2_parmlib.yml`/`jes2parm.yml`
(JES2's own `$DINITINFO` command -- distinct from `discover_parmlib.yml`'s
plain MVS `D PARMLIB` and from `discover_proclib.yml`'s `$D PROCLIB`) were
both implemented and unit-tested against hand-built fixtures the same way
RACF was. **Both are now confirmed against real replies.** Specifically:

- `uss_mounts.yml` writes `D OMVS,F`'s raw console reply verbatim (same
  "capture raw, parse off-host" approach as `sysinfo.yml`) rather than
  parsing it in Jinja -- the real regex work lives entirely in
  `inventory/inventory/uss_mounts_parser.py`, whose module docstring now
  has the confirmed real per-filesystem shape and the one thing that
  differed from the original guess (`NAME=`/`PATH=` land on separate
  continuation lines, not combined on one line -- didn't require a code
  change, since the parser already matched each independently).
- `discover_jes2_parmlib.yml`/`jes2parm.yml` needed a bigger fix than a
  formatting tweak. The originally-guessed command, `$D PARMLIB`
  (`$DPARMLIB`), **doesn't exist** -- confirmed against a real system
  ("not valid JES commands"). The real command is `$DINITINFO`
  ("display initialization information"), replying with message
  `$HASP825` and, critically, a **different design realization**: the
  real reply doesn't describe a concatenation needing a separate "find
  the active member" step the way PROCLIB/PARMLIB do -- it lists the
  *exact* `dsn(member)` pairs JES2 actually read at startup directly
  (via `DSN=`, not `DSNAME=` -- confirmed these two JES2 messages
  genuinely use different field names). `jes2parm.yml` was rewritten to
  fetch exactly those discovered pairs directly (one `zos_fetch` per
  pair) instead of reusing `_member_dump.yml`'s "list and dump every
  member of the whole dataset" approach `proclib.yml`/`ssn_commnd.yml`
  use -- that broader approach would have been actively wrong here: the
  real reply's owning dataset (`SYS1.BES2.PARMLIB` at the site that
  confirmed this) is a site-wide shared PARMLIB holding many unrelated
  members, not just JES2's own. `zos_extract_jes2_parmlibs` was renamed
  to `zos_extract_jes2_init_members` (a list of `{dsn, member}` pairs,
  not `{dsn, prefix}`) to reflect this.

The command/discovery mechanism above is confirmed, and so now is the
*content* of a real JES2 init-deck member -- two real members
(`SYS1.BES2.PARMLIB(JES2PARM)` and the `JES2NJE` member it pulls in via
an `INCLUDE` statement) were checked against `jes2parm_parser.py` on
2026-07-02, and needed a real fix, not just re-flagging: the real
member turned out to be a site copy of IBM's own HASPPARM-derived
template, comments and all -- a common, legitimate way shops build
their real init deck. That meant '/* ... */' comments trailing on the
same line as real content (most commonly right after a parameter's
continuation comma), and comments spanning multiple physical lines
(decorative section-divider boxes, and a couple of cases where a `/*`
opened on one line and didn't close until `*/` several lines later).
The original parser only skipped a line if its *entire* stripped text
started with `/*`, so a trailing same-line comment got glued onto real
parameter text (corrupting the params dict with a garbage key), and a
multi-line comment's non-`/*`-prefixed continuation line got fed to the
statement parser as if it were real content. Fixed by stripping every
`/* ... */` span from the whole member's raw text up front (DOTALL, so
a multi-line span is stripped as a whole) before any line-based
processing. Also found: a statement can legitimately have a subscript
and zero live parameters if its only real parameters happen to be
documented-but-commented-out in this particular member (`FSS(PRINTOFF)`
and `LOADMOD(JESEXIT5)` in the real member) -- the original regex
required at least one parameter and silently dropped these; now the
trailing params group is optional. See `jes2parm_parser.py`'s module
docstring for the full detail.

### VTAM/APPN/TCPIP (all confirmed against real replies)

`vtam.yml` (`D NET,MAJNODES` + `D NET,VTAMOPTS` + `D NET,TOPO`) and
`tcpip.yml` (`D TCPIP,,NETSTAT,HOME`, plus an opt-in `PROFILE.TCPIP`
dataset fetch) are implemented and unit-tested against hand-built
fixtures the same way USS mounts/JES2 init parameters were. **All three
VTAM commands are now confirmed against real replies** (across two
follow-up rounds -- `D NET,TOPO` first, then `D NET,MAJNODES`/`D
NET,VTAMOPTS`). **`D TCPIP,,NETSTAT,HOME` is now confirmed too
(2026-07-02)** -- the real shape mixes legacy `LINKNAME:` rows with
OSA-Express QDIO `INTFNAME:` rows the original guess never accounted
for, silently dropping every `INTFNAME:` entry until `tcpip_parser.py`
was fixed; each entry also carries a `FLAGS:` line (sometimes
`PRIMARY`), now captured as `is_primary`. **A real `PROFILE.TCPIP`
member is confirmed too, also on 2026-07-02** -- unlike `NETSTAT,HOME`
this one needed an actual redesign, not just regex tuning; see below.
Specifically:

- `vtam.yml` bundles all three D-commands' raw console replies into one
  `vtam.txt` via the same `##BLOCKNAME`-sentinel convention `sysinfo.yml`
  uses for `D SYMBOLS`/`D IPLINFO` -- the real parsing lives entirely in
  `inventory/inventory/vtam_parser.py`, whose docstring carries the full
  before/after detail for each command. `D NET,MAJNODES` rows are
  matched by a name token followed by a known status value
  (`ACTIV`/`ACT/S`/`INACT`/`PEND*`) rather than fixed columns -- the real
  per-row shape (`IST089I NAME  TYPE = ..., STATUS`) differs from the
  original guess, but this tolerant match handled it without a code
  change. `D NET,VTAMOPTS` is captured generically as `KEYWORD=VALUE`
  pairs (same idiom `discover_active_members.yml` uses for IEASYSxx,
  confirmed to appear two-per-line in the real reply), not a narrow
  `nodetype`/`cpname`-only model -- **APPN enablement/role is answered by
  filtering that generic table for the `NODETYPE`/`CPNAME` keywords**,
  not a dedicated field. One confirmed, minor, low-impact limitation: a
  couple of keywords (`HPRPST`, `IQDIOSTG`) have two-token values in the
  real reply, and only the first token is captured -- doesn't affect
  `NODETYPE`/`CPNAME`.
- `D NET,TOPO` (the APPN topology database) **is now captured and
  confirmed against a real reply**, unlike the two commands above -- a
  real system provided one in a follow-up round after this domain was
  first implemented. Its actual shape turned out to be a topology
  *database summary* (counts of known adjacent/NN/EN nodes plus
  checkpoint/garbage-collection metadata, anchored on message IDs
  `IST1306I`/`IST1307I`/`IST1781I`/`IST1785I`), not a list of individual
  known nodes by name -- contrary to what the original round assumed when
  it explicitly skipped this command for being "even less certain" than
  MAJNODES/VTAMOPTS. Modeled as a single record (`VtamTopologySummary` in
  `models.py`, same shape as `SystemInfo`/`WlmPolicy`), queryable via
  `inventory vtam-topology`.
- `tcpip.yml`'s `D TCPIP,,NETSTAT,HOME` capture always runs; the
  `PROFILE.TCPIP` fetch only runs if `zos_extract_tcpip_profile_dsn` is
  set (it can name either a sequential dataset or a PDS member, e.g.
  `TCPIP.TCPPARMS(PROFILE1)` -- `zos_fetch`'s own documented behavior
  flattens either shape to just the dataset/member name locally, which
  `zos_extract_tcpip_profile_local_filename` accounts for). Profile
  statements are captured generically (statement name + raw operand
  text) since `PROFILE.TCPIP` syntax is positional
  (`DEVICE`/`LINK`/`HOME`/`PORT` ...), not uniform `KEYWORD=VALUE` like
  `VTAMOPTS`. **Confirmed against a real member on 2026-07-02, and the
  real shape forced a real redesign**: statements like
  `INTERFACE`/`PORT`/`AUTOLOG`/`BEGINROUTES`/`SMFCONFIG` span multiple
  physical lines in the real file -- indented continuation lines
  carrying a statement's own sub-parameters, or whole indented tables
  (`PORT`'s ~80-row port-reservation list; `AUTOLOG`'s job-name list,
  terminated by `ENDAUTOLOG`; `BEGINROUTES`'s `ROUTE` rows, terminated
  by `ENDROUTES`) -- none of which the original one-line-per-statement
  guess accounted for. Indentation alone can't reliably distinguish a
  new statement from a continuation either (the real member indents
  `SMFCONFIG` statements themselves by 2 spaces, no structural reason
  found), so `tcpip_parser.py` was fixed to recognize a fixed,
  evidence-based vocabulary of top-level statement keywords instead --
  see its module docstring for the full detail and the resulting known
  limitation (an unrecognized keyword gets folded into the preceding
  statement rather than starting its own).

Both `##NETSTAT_HOME` and `##PROFILE` are now confirmed, same as
`vtam.txt`'s three commands -- no further real-system validation run is
needed for this dimension unless the real member relies on a top-level
statement keyword outside `_PROFILE_STATEMENT_KEYWORDS`.

### SMS (storage groups confirmed; storage/management classes removed -- no such console command exists)

`sms.yml` issues `D SMS,STORGRP(ALL),LISTVOL` and writes its raw reply
verbatim to `sms.txt` (no `##BLOCKNAME` bundling needed anymore -- see
below). Runs unconditionally (like `lnklst`/`apf`), not gated behind an
enablement flag.

**This domain originally also issued `D SMS,SC(*)`/`D SMS,MC(*)` to list
storage classes and management classes -- both confirmed INVALID against
a real system.** IBM's own full `D SMS` command syntax reference confirms
why: there's no console `D`-command that lists storage classes or
management classes at all (`STORCLAS` only appears as a filter on the
unrelated PDSE `HSPSTATS` cache-statistics command; `MGMTCLAS` doesn't
appear in `D SMS`'s syntax at all). That's a bigger limitation than the
already-documented "ACS routine *source* needs ISMF, not a `D`-command" --
it turns out the class *definitions themselves* need ISMF (or a batch
report against the SCDS/ACDS) too, not just their ACS routine logic.
Removed entirely (Ansible task, Python model/parser/store/CLI) rather
than kept as dead code for commands that don't exist -- a candidate
follow-up in the same category as CICS's `DFHCSDUP`/DB2's `DSNTEP2`/
RACF's `IRRDBU00` (a batch job, not a console command) if ever picked up.

**`D SMS,STORGRP(*),LISTVOL` also had a real syntax bug** (corrected to
`D SMS,STORGRP(ALL),LISTVOL` -- IBM's documented syntax only accepts a
specific group name, `ALERT`, or `ALL`, not `*`), and **is now confirmed
against a real reply** (via the `SG` alias for `STORGRP`, both documented
as equivalent). The real shape turned out to be completely different from
the original guess -- not "header line + indented VOLSER continuation
lines" per group, but two separate sections:
- A storage-group summary table (name, `TYPE` -- `POOL`/`TAPE`/etc --,
  and a raw per-system status *symbol* sequence like `+ +`, not a decoded
  `ENABLE`/`DISABLE`/`NOTCNCT` word as originally guessed -- see the
  reply's own `LEGEND` for what each symbol means). A `STORGRP TYPE
  SYSTEM=` header line can appear once before *several* consecutive group
  rows, not once per group.
- A completely separate, flat `VOLUME`-to-`STORGRP` mapping table, using
  each row's first token (VOLSER) and last token (owning group name) --
  ended by the real, stable `LISTVOL IS IGNORED FOR OBJECT, OBJECT
  BACKUP, AND TAPE STORAGE GROUPS` marker line, which also explains why
  `TAPE`-type groups never get volume rows.

`inventory/inventory/sms_parser.py` was rewritten from scratch against
the real text; see its module docstring for the full detail, and
`SmsStorageGroup` in `models.py` for the new `group_type` field this
added.

Run `ansible-playbook playbooks/site.yml --tags sms --limit lpar1`
against a real system if you want to double-check this against your own
site's reply -- it's confirmed against one real system already, but not
independently re-verified elsewhere.

### WLM (first cut only, confirmed against a real reply)

`wlm.yml` issues a single `D WLM` and writes its raw console reply
verbatim to `wlm.txt` (no `##BLOCKNAME` bundling needed, same "single
command, no bundling" shape `uss_mounts.yml` uses). This is a **minimal
first cut**: just the active policy name and its mode — modeled directly
on `sysinfo.yml`'s "single small record" shape. Full service-class/goal/
resource-group definitions need the z/OSMF WLM REST API (the
already-pinned-but-unused `ibm.ibm_zosmf` collection), a materially
bigger follow-up not attempted here. Runs unconditionally, no new config
variable needed.

**Confirmed against a real system — and the fix needed was bigger than a
formatting tweak.** The originally-guessed command, `D WLM,POLICY`,
**doesn't exist**: a real system rejected it outright ("WLM SYNTAX ERROR,
UNIDENTIFIABLE KEYWORD" for the `POLICY` keyword). The real command is
bare `D WLM` (no operand), confirmed against both IBM's own documentation
and a real reply from this site (message `IWM025I`). That real reply also
never contains a `MODE=` token anywhere — `wlm_parser.py` now anchors on
the stable `POLICY NAME:` token and infers `mode="GOAL"` from a policy
name being present at all (WLM compatibility mode is desupported on
modern z/OS releases), rather than parsing a mode keyword that doesn't
exist. See `wlm_parser.py`'s module docstring for the full detail and the
real sample reply.

### Deepened DB2 catalog view (opt-in, the most speculative *console/MVS-program* domain in the pipeline)

`db2_catalog.yml` (tag `db2`, same tag as `db2.yml` above, but gated
separately by `zos_extract_db2_ssid`) deepens `db2.yml`'s "is a DB2
address space up right now" heuristic with real catalog content --
installed packages and plans -- via a read-only DSNTEP2 batch SQL query
against `SYSIBM.SYSPACKAGE`/`SYSIBM.SYSPLAN`. Unlike CICS, this is
genuinely reachable without a new product (no CMCI/CICSplex SM
dependency).

- Opt-in: skipped entirely unless `zos_extract_db2_ssid` is set. Also
  needs a plan already bound at the target site for DSNTEP2
  (`zos_extract_db2_plan`, defaults to `DSNTEP2`, IBM's own sample plan
  name -- sites commonly rebind/rename it) and, if DSNTEP2 isn't already
  reachable via the default STEPLIB concatenation, the one DB2 load
  library it needs (`zos_extract_db2_steplib`, a single DSN, same
  single-dataset convention `_smplist_zone.yml` already uses for its own
  optional STEPLIB).
- `zos_mvs_raw` runs `IKJEFT01` (TSO batch, the standard way to invoke
  DSNTEP2) the same way `racf.yml` runs `IRRDBU00` and `catalog.yml` runs
  `IDCAMS`. Two separate invocations (one per catalog table) rather than
  one job with two `SELECT`s, so each result lands under its own
  unambiguous `##SYSPACKAGE`/`##SYSPLAN` sentinel -- both queries return
  the same `NAME`/`CREATOR`/`BINDTIME` column shape, so nothing in
  DSNTEP2's own report text could otherwise tell the two blocks apart. A
  `;;SSID=` marker line (not part of DSNTEP2's own report, same idiom
  `tcpip.yml`'s `;;SOURCE_DSN=` marker uses) tags each block with which
  subsystem it ran against.

**THIS IS THE MOST SPECULATIVE *CONSOLE/MVS-PROGRAM* DOMAIN IN THE
PIPELINE** (the WLM z/OSMF deepening below is more speculative still,
being a different transport entirely): beyond the usual "not yet
confirmed against a real reply" caveat every implementation-only domain
above carries, DSNTEP2's exact authorization/PLAN/STEPLIB requirements
themselves vary by site DB2 setup, on top of report-format uncertainty.
`inventory/inventory/db2_catalog_parser.py`'s docstring carries the full
caveat, including what to check first if a real run's report layout
doesn't match a simple whitespace-split row.

Run `ansible-playbook playbooks/site.yml --tags db2 --limit lpar1
-e '{"zos_extract_db2_ssid": "YOUR_SSID"}'` (add
`zos_extract_db2_plan`/`zos_extract_db2_steplib` if the defaults don't
fit your site) against a real DB2 subsystem and check the resulting
`db2_catalog.txt` against what `db2_catalog_parser.py` assumes before
relying on this dimension at all.

### WLM deepening via z/OSMF (opt-in, the single most speculative dimension in the entire pipeline)

`wlm_zosmf.yml` (tag `wlm_zosmf`, gated `never`) goes beyond `wlm.yml`'s
active-policy-name/mode first cut to the full service-class/goal/
resource-group definitions WLM actually enforces -- but only reachable
via z/OSMF's REST API, not any console command. This is a **materially
different mechanism** from every other domain in this pipeline: an
HTTPS/JSON REST call (`ansible.builtin.uri`, `delegate_to: localhost`)
with its own separate credentials, rather than a console command or MVS
program run over the existing SSH-based connection.

- **Not part of `site.yml`/`interactive.yml`**: run it via the dedicated
  `playbooks/wlm_zosmf.yml` entry point instead --
  `ansible-playbook playbooks/wlm_zosmf.yml --tags wlm_zosmf` (add
  `--limit lpar1` to scope to one host). That playbook prompts for your
  z/OSMF username/password at runtime (same `vars_prompt` pattern
  `playbooks/interactive.yml` already uses for SSH credentials) rather
  than storing them in `hosts.yml` -- credentials are registered onto
  each targeted host via `add_host` and never written to disk.
- `zos_extract_zosmf_host` defaults to that host's own `ansible_host`
  (z/OSMF commonly runs reachable at the same address as the LPAR
  itself); override it in `hosts.yml` if your site has one shared z/OSMF
  instance on its own hostname/port instead.
- `zos_extract_zosmf_validate_certs` defaults to `false` -- many internal
  z/OSMF instances present a self-signed/internal-CA certificate. Set it
  `true` (and make sure your control node actually trusts that CA chain)
  if yours is trusted normally; leaving it `false` means this connection
  has no protection against a MITM between your control node and z/OSMF.
- The response is saved verbatim to `wlm_zosmf.txt` (raw JSON text,
  despite the `.txt` extension -- kept consistent with every other
  dimension's ingest-glob convention, same as `active_jobs.txt` already
  being JSON Lines despite its own `.txt` name).

**THIS IS THE SINGLE MOST SPECULATIVE PIECE IN THE ENTIRE PIPELINE.**
Every other domain here at least reuses a well-documented, stable console
command or MVS program; this one instead guesses at both the z/OSMF WLM
REST API's endpoint path (`zos_extract_wlm_zosmf_path`, defaulted to
`/zosmf/wlm/policies`) and its response JSON schema, with **no other
REST/JSON precedent anywhere else in this codebase** to lean on. Check
IBM's current z/OSMF REST API reference ("Workload Management services")
for your z/OS release before trusting the default path, and see
`inventory/inventory/wlm_zosmf_parser.py`'s module docstring for exactly
how loosely the response JSON is interpreted (and how to fix it once you
know the real shape).

### Deepened CICS resource view (opt-in, DFHRPL lineage + DFHCSDUP CSD definitions)

`cics_deepening.yml` (tag `cics`, same tag as `cics.yml` above, but gated
separately by `zos_extract_cics_proc`) goes beyond `cics.yml`'s "is a CICS
address space up right now" heuristic to two things genuinely reachable
without CMCI/CICSplex SM: DFHRPL (CICS's own load-library concatenation,
functionally STEPLIB/JOBLIB for CICS's own dynamic program loading) and
real CICS resource definitions read from the CSD via a read-only
`DFHCSDUP LIST` run. CICS resource-definition deepening was explicitly
scoped but not implemented in an earlier round of this project, pending
real `DFHCSDUP` documentation to resolve two open questions -- both are
now confirmed against IBM's own CICS TS documentation:

- **`DFHCSDUP` LIST command syntax**: `LIST ALL` (enumerates every
  list/group name on the CSD) and `LIST LIST(name) OBJECTS` (full
  resource-definition attributes for every group in a named list) are
  real, documented operands. `_cics_csdup_dump.yml` always runs `LIST
  ALL`, plus one `LIST LIST(grplist) OBJECTS` per distinct `GRPLIST`
  value found among the querying CSD's own CICS region(s)' SIT overrides
  (see below) -- GRPLIST is exactly "the list of groups this region
  actually uses," a grounded choice rather than a guess at an arbitrary
  group/list name.
- **Concurrent access to a live region's CSD**: `PARM='CSD(READONLY)'`
  is DFHCSDUP's real, documented read-only access option (default is
  `CSD(READWRITE)`) -- confirmed via IBM APAR PM04030's own title, which
  references this exact parameter string. Quiescing a CSD before running
  DFHCSDUP is only a documented requirement for *update* access to a
  recoverable CSD opened in RLS mode; read-only access doesn't need it,
  which is why this pipeline only ever uses `CSD(READONLY)`.

Unlike DB2's deepening above, DFHCSDUP's own LIST report *print format*
(the column layout its SYSPRINT output actually uses) is still
unconfirmed -- no real sample was found while researching this, only a
secondhand forum mention of column positions for what may be a different
report variant. `inventory/inventory/cics_csdup_parser.py` is
deliberately the most tolerant parser in the pipeline as a result (a
generic "resource-type-like token + resource-name-like token" row match,
with the current `GROUP:` marker line's value carried forward) -- see its
module docstring for the full caveat, including why this is speculative
on two separate axes at once (report format, on top of the usual "not
checked against a real system").

- Opt-in: skipped entirely unless `zos_extract_cics_proc` (a list of CICS
  startup PROCLIB member names) is set. There's no reliable
  live-discoverable link from a running CICS job name back to its
  starting PROCLIB member (`D A,L`'s `PROCSTEP` is the step name within
  the PROC, not the PROC's own member name) -- unlike PROCLIB/PARMLIB/
  JES2 parmlib, which each have a real console command or IEASYSxx-keyword
  path to their active member -- so this needs explicit configuration,
  the same precedent `zos_extract_db2_ssid`/`zos_extract_smpe_csis`
  already set.
- For each configured PROC, `_cics_proc_dump.yml` locates and fetches it
  from `zos_extract_proclibs` (same `zos_find` + `subelements`/
  `selectattr` + `zos_fetch` idiom `discover_mstrjcl_proclibs.yml`/
  `_fetch_active_ieasys_member.yml` already use for MSTJCLxx/IEASYSxx),
  then pulls DFHRPL DSNs and the DFHCSD DD's DSN out of the fetched JCL
  text via the same "DD group" `regex_findall` idiom
  `discover_mstrjcl_proclibs.yml` uses for `IEFPDSI`, reused
  near-verbatim, plus the startup step's inline SYSIN cards (SIT
  overrides).
- If `zos_extract_cics_sdfhload` (the CICS SDFHLOAD library -- DFHCSDUP's
  own STEPLIB, since it isn't normally reachable via LNKLST) is set,
  `_cics_csdup_dump.yml` then runs DFHCSDUP once per distinct discovered
  CSD DSN via `zos_mvs_raw` -- mirrors `db2_catalog.yml`/`racf.yml`/
  `catalog.yml`'s `zos_mvs_raw` precedent exactly (`SYSUT1` is a real
  scratch work dataset DFHCSDUP itself needs, named via
  `zos_extract_cics_workhlq`, same idiom `zos_extract_smpe_workhlq` uses
  for GIMSMP's `SMPWRK6`). Leave `zos_extract_cics_sdfhload` blank to
  skip the DFHCSDUP job entirely while still getting DFHRPL/SIT/CSD-dsn
  discovery.
- All four pieces (DFHRPL entries, SIT overrides, CSD dsns, and the
  DFHCSDUP report text) bundle into one `cics_deepening.txt` via the same
  `##BLOCKNAME`-sentinel convention `vtam.txt`/`sms.txt` already use --
  `##DFHRPL`, `##SIT`, `##CSD`, `##CSDUP_REPORT` -- with `;;PROC=`/
  `;;CSD_DSN=` marker lines (same idiom `db2_catalog.yml`'s `;;SSID=`/
  `tcpip.yml`'s `;;SOURCE_DSN=` markers already use) identifying which
  region/CSD each entry came from.

Run `ansible-playbook playbooks/site.yml --tags cics --limit lpar1
-e '{"zos_extract_cics_proc": ["YOUR_CICS_PROC"], "zos_extract_cics_sdfhload": "YOUR.CICS.SDFHLOAD"}'`
against a real system and check the resulting `cics_deepening.txt`
against what `cics_proc_parser.py`/`cics_csdup_parser.py` assume before
relying on this dimension -- especially the `##CSDUP_REPORT` portion's
report-format parsing, and whether this site's own CICS regions'
CSD-access mode lets a concurrent `CSD(READONLY)` batch DFHCSDUP job
succeed cleanly in practice, not just per IBM's general documentation.

### A performance note on `catalog`

Unlike `zoautil_py`'s `datasets.list_datasets()` (which returns DSORG/RECFM/
LRECL/BLKSIZE/VOLSER for every matching data set in one call), `zos_find`
only returns data set names -- so `catalog.yml` queries each matched
non-VSAM data set individually with `zos_stat` to get those attributes. This
means roughly one extra module call per matched data set, on top of
`zos_find`'s own call. `zos-extract.md` already recommends scoping
`zos_extract_catalog_patterns` narrowly rather than to a broad shared HLQ --
that advice matters even more here.

## Layout

```
ansible/
ansible.cfg
requirements.yml           # ibm.ibm_zos_core collection pin, plus
                            # ibm.ibm_zos_cics/ibm.ibm_zos_ims for future
                            # expansion (both still unused today) --
                            # ibm.ibm_zosmf is pinned too, but not
                            # actually needed by wlm_zosmf.yml below
                            # (that uses plain ansible.builtin.uri, not
                            # any module from this collection); kept
                            # pinned for whichever future domain does
                            # need one of its actual modules
inventory/hosts.yml.example
inventory/group_vars/zos.yml  # shared ZOAU/Python env + local output path
                               # (must live beside the inventory file --
                               # that's how Ansible auto-loads group_vars)
playbooks/site.yml         # entry point; sets the ZOAU env at the play level
playbooks/interactive.yml  # same, but prompts for connection details for a
                            # one-off system instead of reading hosts.yml
playbooks/wlm_zosmf.yml    # standalone entry point for the opt-in WLM
                            # z/OSMF deepening (see below) -- prompts for
                            # z/OSMF credentials, never run as part of
                            # site.yml/interactive.yml
playbooks/roles            # symlink to ../roles -- ansible.cfg's roles_path
                            # setting only applies when a tool's cwd is this
                            # ansible/ directory (so it finds ansible.cfg at
                            # all); this symlink makes the role discoverable
                            # via Ansible's own default playbook-relative
                            # search too, so e.g. an IDE's ansible-lint
                            # integration running from the repo root still
                            # finds roles/zos_extract. Don't delete it.
roles/zos_extract/
  defaults/main.yml        # per-step defaults (member filters, HLQs, ...)
  tasks/
    main.yml               # dispatches to one file per step, by tag
    local_prep.yml          # ensures the local output directory exists
    discover_proclib.yml    # auto-discovers zos_extract_proclibs via
                             # JES2's '$D PROCLIB' if it isn't set explicitly
    discover_parmlib.yml    # auto-discovers zos_extract_parmlibs via
                             # 'D PARMLIB' if it isn't set explicitly
    discover_active_parmlib_suffixes.yml
                             # parses 'D IPLINFO's IEASYM/IEASYS LIST
                             # into the active IEASYSxx/IEASYMxx suffixes
    discover_active_members.yml
                             # reads the active IEASYSxx member(s) (see
                             # _fetch_active_ieasys_member.yml) and pulls
                             # their SSN=/CMD=/PROD=/MSTRJCL= keywords --
                             # the active IEFSSNxx/COMMNDxx/IFAPRDxx
                             # suffixes, used by ssn_commnd.yml/ifaprd.yml
                             # to fetch just those members instead of
                             # every one matching the broad wildcard
                             # filter, plus the active MSTJCLxx suffix,
                             # used by discover_mstrjcl_proclibs.yml, and
                             # (as zos_extract_ieasys_member_blocks) the
                             # full IEASYSxx content, for ieasys_snapshot.yml
    discover_mstrjcl_proclibs.yml
                             # fetches the active MSTJCLxx member and
                             # appends any proclib DSN concatenated onto
                             # its IEFPDSI DD to zos_extract_proclibs --
                             # accounts for proclib datasets invisible to
                             # '$D PROCLIB' (see above)
    proclib.yml, ssn_commnd.yml, ifaprd.yml
                             # zos_find + zos_fetch member dumps (see
                             # _member_dump.yml, the shared worker they
                             # each include per PROCLIB/PARMLIB entry)
    parmlib_snapshot.yml     # explicit, always-run 'D PARMLIB' capture,
                             # tag parmlib_snapshot -- separate from
                             # discover_parmlib.yml's own implicit,
                             # conditional call above; writes
                             # parmlib_snapshot.txt, ingested as its own
                             # dimension (inventory parmlib) -- just the
                             # PARMLIB dataset search order, not any
                             # member's actual content
    ieasys_snapshot.yml      # explicit capture of the active IEASYSxx
                             # member(s)' full content -- the real "actual
                             # parms" D PARMLIB above can't show; tag
                             # ieasys_snapshot (added to
                             # discover_active_parmlib_suffixes.yml/
                             # discover_active_members.yml too, so it
                             # pulls in that discovery chain standalone);
                             # writes ieasys_snapshot.txt, ingested via
                             # inventory ieasys
    lnklst.yml, apf.yml, sysinfo.yml
                             # zos_operator / zos_apf console-command and
                             # APF-list analogs
    uss_mounts.yml            # 'D OMVS,F' captured raw (see above) --
                               # confirmed against a real reply
    discover_jes2_parmlib.yml # issues JES2's '$DINITINFO' and extracts the
                               # exact dsn/member pairs it reports reading
                               # at startup -- confirmed against a real
                               # reply (see above)
    jes2parm.yml               # zos_fetch's exactly the pairs discover_
                                # jes2_parmlib.yml found -- JES2's own init
                                # deck, confirmed against real members
    vtam.yml                   # 'D NET,MAJNODES' + 'D NET,VTAMOPTS' +
                                # 'D NET,TOPO' bundled into one vtam.txt
                                # (see above) -- all three confirmed
                                # against real replies
    tcpip.yml                  # 'D TCPIP,,NETSTAT,HOME' (always) + opt-in
                                # PROFILE.TCPIP fetch, bundled into one
                                # tcpip.txt (see above) -- both confirmed
                                # against real replies
    sms.yml                    # 'D SMS,STORGRP(ALL),LISTVOL' captured raw
                                # into sms.txt (see above) -- confirmed
                                # against a real reply; storage/management
                                # class capture removed (no such console
                                # command exists)
    wlm.yml                    # 'D WLM' captured raw into wlm.txt (see
                                # above) -- first cut only, confirmed
                                # against a real reply
    activity.yml             # direct `jls -o id,name,status,jobtype,asid`
                              # (not zos_job_query, see above) + `ps -ef`
                              # for the live jobs/processes snapshot
    discover_active_address_spaces.yml
                               # shared 'D A,L' console query + parse for
                               # cics.yml/db2.yml (not zos_job_query, see
                               # above)
    cics.yml, db2.yml          # opt-in PROCSTEP/job-name filters over
                               # discover_active_address_spaces.yml's
                               # output -- not authoritative, see above
    db2_catalog.yml            # opt-in zos_mvs_raw (DSNTEP2 via IKJEFT01)
                                # deepened DB2 packages/plans view (see
                                # above) -- the most speculative domain in
                                # the pipeline, not yet validated
    cics_deepening.yml, _cics_proc_dump.yml, _cics_csdup_dump.yml
                                # opt-in DFHRPL lineage + DFHCSDUP CSD
                                # definitions (see above) -- the
                                # DFHCSDUP LIST report format is the most
                                # speculative parsing surface in the
                                # pipeline, even though the command
                                # syntax/read-only access mode sent to it
                                # are confirmed against real IBM docs
    smplist.yml               # zos_mvs_raw (GIMSMP) per CSI/zone pair (see
                               # _smplist_zone.yml, the shared per-pair
                               # worker) -- zos_extract_smpe_csis is a list,
                               # flattened via subelements('zones')
    discover_smpe_csis.yml     # opt-in zos_find (cluster) search for CSI
                                # candidates by naming pattern -- not
                                # authoritative, see above
    discover_smpe_zones.yml, _smplist_globalzone.yml
                                # opt-in GIMSMP LIST GLOBALZONE per CSI --
                                # authoritative zone census (ZONEINDEX),
                                # unlike CSI discovery above; writes
                                # *.smpzones.txt, parsed by
                                # inventory/smpe_parser.py's
                                # parse_globalzone()
    catalog.yml                # zos_find + zos_stat (non-VSAM) and
                                # zos_mvs_raw/IDCAMS (VSAM) combined
    racf.yml                   # zos_mvs_raw (IRRDBU00), implementation
                                # only -- see above
```
