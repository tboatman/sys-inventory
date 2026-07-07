# Fleshing out sys-inventory: six new collection domains

## Context

The inventory pipeline today covers PROCLIB/PARMLIB+lineage, SSN/COMMND,
IFAPRD, LNKLST, APF, sysinfo, SMP/E, live activity (jobs/processes),
catalog, and RACF (implementation-only). The user asked what else would
flesh this out; this plan sketches six candidate domains end-to-end
(Ansible extraction side + Python parse/model/store/CLI side) so any of
them can be picked up and implemented on its own later, following the
exact two patterns already established in this repo:

- **Ansible side** (`ansible/roles/zos_extract/tasks/`): either (a) a
  console `D`-command parsed with `zos_operator` + regex (like
  `lnklst.yml`/`sysinfo.yml`), or (b) a PARMLIB/PROCLIB member dump via
  `zos_find`+`zos_fetch` (reusing `_member_dump.yml`, like
  `ssn_commnd.yml`/`ifaprd.yml`), wired into `main.yml` with its own tag
  and defaults in `defaults/main.yml`.
- **Python side** (`inventory/inventory/`): a new dataclass (or a few)
  in `models.py`, a new `<domain>_parser.py` module, a glob/exact-filename
  hook added to `cmd_ingest()` in `cli.py`, a table + `save_*`/`all_*`
  pair in `store.py`, one or more query subcommands in `cli.py`, and a
  `tests/test_<domain>_parser.py` with a synthetic fixture.

Every domain below follows that shape. **RACF is the best precedent for
how to handle uncertainty**: it's fully implemented and tested against a
synthetic fixture, but explicitly flagged in its own docstring and the
READMEs as "not yet validated against a real system" wherever the exact
wire format wasn't independently confirmed. Three of the six domains below
(networking, WLM, SMS) don't have a confirmed real console-reply sample
to build a regex against, so they get the same treatment: implemented,
tested against a hand-built fixture, explicitly flagged as needing
validation against a real reply before being trusted.

## Scope for this round

All six original candidate domains are now implemented (Ansible task
files, Python model/parser/store/CLI wiring, tests, READMEs all in place
and verified -- see git history): 1 (USS mounted filesystems), 2 (JES2
initialization parameters), 3 (deepened DB2 packages/plans via
DSNTEP2), 4 (networking: VTAM/APPN/TCPIP), 5 (SMS storage
groups/classes), 6 (WLM active policy name/mode, first cut).

**This latest round goes beyond the original six**, implementing the
"materially bigger follow-up" WLM's own section explicitly called out:
full service-class/goal/resource-group definitions via z/OSMF's REST API
(`wlm_zosmf.yml`, tag `wlm_zosmf`, gated `never`; standalone entry point
`playbooks/wlm_zosmf.yml`). Two real judgment calls were resolved with
the user before implementing (not guessed):
- **Auth**: prompt for z/OSMF username/password at runtime (same
  `vars_prompt` idiom `playbooks/interactive.yml` already uses for SSH),
  never stored in `hosts.yml`.
- **TLS**: `zos_extract_zosmf_validate_certs` defaults to `false` (skip
  cert validation) -- common for internal z/OSMF instances with a
  self-signed/internal-CA cert; documented as a real security tradeoff in
  both the task file and README, with the CA-bundle alternative noted for
  anyone who wants it.

This is **the single most speculative piece in the entire pipeline** --
more so even than DB2's DSNTEP2 domain (previously the most speculative):
every other domain here at least parses a well-documented, stable console
command or MVS program; this one guesses at both a z/OSMF REST API
endpoint path and its response JSON schema, with no other REST/JSON
precedent anywhere else in this codebase. `WlmZosmfEntry`/
`wlm_zosmf_parser.py` capture the response maximally generically (a
best-guess `name` field plus the entire raw JSON blob preserved
verbatim) specifically because of that uncertainty. The user's local
z/OS system was down for this round (and the round before it, DB2) --
built and unit-tested against hand-constructed JSON fixtures only, with
the caveat emphasized more heavily here than anywhere else in the
project.

With all six original candidates plus this WLM/z/OSMF follow-up now
either fully implemented or scoped to a documented first cut, most
remaining work is the "Verification" section below (real-system
validation against an actual z/OS system, and for the WLM/z/OSMF round
specifically, against a real z/OSMF instance to nail down the actual REST
endpoint/schema).

**Domain 7 (deepened CICS resource view: DFHRPL lineage + `DFHCSDUP` CSD
definitions) is now implemented too**, in a follow-up round after this
plan was first written. The two things that had blocked it -- real
`DFHCSDUP` control-statement syntax and concurrent CSD-access safety --
were resolved via web research against IBM's own CICS TS documentation
and a real IBM APAR record (PM04030, whose own title references the exact
`PARM='CSD(READONLY)'` read-only access parameter this pipeline now
uses), not guessed: `LIST ALL` / `LIST LIST(name) OBJECTS` are confirmed
real DFHCSDUP LIST operands, and `CSD(READONLY)` is the documented way to
read a live region's CSD without quiescing it (quiescing is only a
documented requirement for *update* access to a recoverable CSD opened in
RLS mode). What's still genuinely unconfirmed -- and now the single most
speculative parsing surface in the whole pipeline -- is DFHCSDUP's own
LIST report *print format* (no real sample was found even after that
research); see `ansible/roles/zos_extract/tasks/cics_deepening.yml`'s and
`inventory/inventory/cics_csdup_parser.py`'s own header
comments/docstrings for the full caveat. **APPN topology via `D NET,TOPO`
is now implemented too**, in a further follow-up round: it had been
skipped deliberately when VTAM/TCPIP was first implemented (see below)
for the same "format uncertainty, no real sample available" reason CICS
was, but a real reply was provided this round, resolving that uncertainty
outright rather than leaving it as a documented guess. Its real shape
turned out to be a topology *database summary* (counts of known
adjacent/NN/EN nodes plus checkpoint/garbage-collection metadata, message
IDs `IST1306I`/`IST1307I`/`IST1781I`/`IST1785I`), not a list of individual
known nodes by name as originally assumed -- see
`inventory/inventory/vtam_parser.py`'s module docstring and
`VtamTopologySummary` in `models.py`. `D NET,MAJNODES`/`D NET,VTAMOPTS`
remain unconfirmed, same as before.

IBM's own docs site and a few secondary sources were checked this round
for real `D NET,MAJNODES`/`D NET,TOPO`/`D NET,VTAMOPTS`/`D TCPIP,,NETSTAT`
sample output to calibrate against (same as was attempted for RACF's
byte offsets) -- IBM's docs pages 403'd on direct fetch and no secondary
source had real sample output either. So, same as sysinfo_parser.py's own
documented situation ("D SYMBOLS'/'D IPLINFO' reply formatting ... there
was no real system available to calibrate these regexes against"), this
is built from well-documented, stable command syntax knowledge, flagged
for validation against a real reply, not confirmed against one this round.

User decisions from this round's clarifying questions:
- **TCPIP**: capture both live `D TCPIP,,NETSTAT,HOME` (unconditional) AND
  fetch the actual `PROFILE.TCPIP`-style dataset (opt-in, new
  `zos_extract_tcpip_profile_dsn` variable) for fuller DEVICE/LINK/HOME/
  PORT statement detail.
- **APPN**: skip `D NET,TOPO` (topology database) for now, given the
  format uncertainty above -- APPN enablement is instead confirmed via
  `D NET,VTAMOPTS`'s `NODETYPE`/`CPNAME` fields (is this node running
  APPN, and as what role: NN/EN/LEN vs subarea-only).

## Suggested priority order (cheap+confirmable first)

1. **USS mounted filesystems** — cheap, one console command, same shape as
   existing `lnklst.yml`/`apf.yml`.
2. **JES2 initialization parameters** — reuses the existing member-dump
   machinery almost as-is (JES2 has its own PARMLIB concatenation,
   discoverable the same way PROCLIB/PARMLIB already are).
3. **Deepened DB2 subsystem view** (packages/plans via a batch SQL query)
   — CICS deepening is *not* included: this site has no CMCI/CICSplex SM
   (confirmed in `ansible/README.md`), so real CICS resource definitions
   genuinely aren't reachable without a new product being enabled first.
4. **Networking (VTAM + APPN + TCPIP)** — bigger, own syntax to parse,
   needs a real-sample validation pass; scoped down to skip APPN topology
   (`D NET,TOPO`) specifically, per the user's own call this round.
5. **SMS storage groups/storage classes** — same caveat as #4; ACS routine
   *source* is explicitly out of scope (needs ISMF, not a D-command).
6. **WLM policy** — start with just the active policy name/mode (cheap);
   full service-class/goal definitions need the z/OSMF REST API (the
   already-pinned-but-unused `ibm.ibm_zosmf` collection), which is a
   materially bigger follow-up, not part of this pass.

---

## 1. USS mounted filesystems

**Goal:** one more "what's configured" table, parallel to LNKLST/APF —
every mounted filesystem (zFS/HFS), its mount point, device, mode
(RDWR/READ), and status.

**Ansible (`ansible/roles/zos_extract/tasks/uss_mounts.yml`, tag `uss_mounts`):**
- `zos_operator: {cmd: "D OMVS,F"}` → `zos_extract_omvs_reply`
- Parse `stdout_lines`: z/OS's `D OMVS,F` reply (`BPXO040I`) is one header
  line per filesystem (`TYPENAME DEVICE STATUS MODE ...`) followed by
  indented `NAME=`/`PATH=` continuation lines — same "multi-line record"
  shape as `D A,L`, but 3 lines/record instead of 1. Regex per-record
  block, not per-line (see `discover_active_address_spaces.yml`'s comment
  on why per-line regex_findall is needed for packed console replies).
- Write `uss_mounts.txt`, one line per filesystem:
  `type device status mode name path`
- **No real reply captured yet for this site** — flag in the task file's
  header comment (same convention as every other console-parsing task
  here) that the regex needs confirming against an actual `D OMVS,F`
  before trusting it blindly; ship it anyway (matches the RACF precedent).
- `main.yml`: add `import_tasks: uss_mounts.yml` tagged `[uss_mounts]`,
  unconditional (like lnklst/apf, not opt-in — this is cheap and always
  useful).
- `defaults/main.yml`: `zos_extract_uss_mounts_outfile: "uss_mounts.txt"`

**Python:**
- `models.py`: `UssMount` — `fs_type`, `device`, `status`, `mode`, `name`
  (zFS dataset or device), `path`.
- New `uss_mounts_parser.py`: `parse_uss_mounts(path) -> list[UssMount]`,
  same regex-block strategy as the ansible side (kept in sync, or ideally
  the parser is the one place the block regex lives and the ansible side
  just captures raw text — worth deciding at implementation time whether
  parsing happens off-host only, same as everything else here).
- `store.py`: `uss_mounts` table (indexed on `path`); `save_uss_mounts`/`all_uss_mounts`.
- `cli.py`: glob `*uss_mounts*.txt` in `cmd_ingest`; new `inventory uss-mounts` command.
- `tests/test_uss_mounts_parser.py` with a hand-built `D OMVS,F`-shaped fixture.
- Update `zos-extract/README.md` (new step, e.g. "11. USS mounted
  filesystems") and its naming-convention table; update
  `ansible/README.md`'s Layout section.

---

## 2. JES2 initialization parameters

**Goal:** JES2's own init deck (its PARMLIB-equivalent — separate from
the JES2 *PROCLIB* concatenation `discover_proclib.yml` already covers)
isn't captured anywhere. This is genuinely different from SYS1.PARMLIB:
JES2 reads its own init parms from a member selected at JES2 start via
`$T PARMLIB`/the JES2 proc's own parm, and JES2 can report its current
parmlib concatenation via `$D PARMLIB` (the JES2 command — distinct from
plain MVS `D PARMLIB`, same relationship `$D PROCLIB` has to `D PARMLIB`).

**Ansible (`ansible/roles/zos_extract/tasks/discover_jes2_parmlib.yml` +
`jes2parm.yml`, tag `jes2parm`):**
- `discover_jes2_parmlib.yml`: issue `$D PARMLIB`, parse the same
  `$HASPnnn`-prefixed wrapped-message shape `discover_proclib.yml` already
  handles for `$D PROCLIB` (reuse that file's strip/rejoin/regex_findall
  idiom directly — same message family). Produces
  `zos_extract_jes2_parmlibs` (dsn+prefix list) and the active member
  suffix/name.
- `jes2parm.yml`: reuse `_member_dump.yml` exactly as `ssn_commnd.yml`
  does, dumping just the active JES2 init member (or all of them if the
  active one can't be determined, same "fall back to broad" pattern as
  ssn_commnd/ifaprd) to `jes2parm.txt`.
- **Needs a real `$D PARMLIB` reply to confirm the message ID/shape**
  before trusting the reuse of discover_proclib.yml's parsing — flag this
  same as #1.
- `defaults/main.yml`: `zos_extract_jes2parm_outfile` pattern, matching
  existing `*_outfile` naming.

**Python:**
- JES2 init statements are `STMT param1=val1,param2=val2(subscript),...`
  with comma continuation — structurally close to IEASYSxx's
  `KEYWORD=value` lines (`discover_active_members.yml`'s parsing idiom)
  but with parenthesized statement subscripts (e.g. `JOBCLASS(STC)`).
  Rather than modeling every JES2 statement type (huge surface area),
  follow the **generic capture** precedent set by `ActiveJob`
  (capture every field jls exposes, not just the ones some code currently
  uses) and `discover_active_members.yml` (one generic
  KEYWORD=value pass, not three hand-tuned regexes): a single
  `Jes2InitStatement(stmt_name, subscript, params: dict[str,str],
  source_member)` model captures every statement generically, without
  needing per-statement-type schemas.
- `models.py`: `Jes2InitStatement` as above.
- New `jes2parm_parser.py`: reuse `jcl_parser.split_members()` for the
  `##MEMBER` sentinel, write a JES2-specific continuation-joiner (comma
  continuation, but no `//` prefix — can't reuse `join_continuations` as
  written), then a generic `STMT(subscript)? key=val,...` regex per
  logical line.
- `store.py`/`cli.py`/tests: same pattern as domain 1.

---

## 3. Deepened DB2 subsystem view (packages/plans)

**Goal:** `db2.yml` currently only reports "is a DB2 address space up
right now" (PROCSTEP/job-name heuristic via `D A,L`). Real DB2 catalog
content — installed plans/packages/DBRMs — is genuinely reachable via a
read-only batch SQL query, unlike CICS (blocked on missing CMCI/CICSplex
SM at this site, per `ansible/README.md`'s own note — **not** attempted
in this pass).

**Ansible (`ansible/roles/zos_extract/tasks/db2_catalog.yml`, tag `db2`,
`when: zos_extract_db2_ssid | length > 0`):**
- New required config: `zos_extract_db2_ssid` (subsystem ID, e.g. `DB2A`)
  and `zos_extract_db2_plan`/`zos_extract_db2_steplib` (whatever's needed
  to run a batch SQL job against that subsystem — DSNTEP2 or DSNTIAUL
  under `zos_mvs_raw`, the same module `catalog.yml`'s IDCAMS call and
  `racf.yml`'s IRRDBU00 call already use for "run one read-only MVS
  program").
- `zos_mvs_raw` invocation: `program_name: IKJEFT01` (TSO batch, the
  standard way to run DSNTEP2), with a `SYSTSIN`/`SYSIN` DD containing
  `DSN SYSTEM({{ ssid }})` + `RUN PROGRAM(DSNTEP2) PLAN({{ plan }})` and a
  `SYSIN` query like `SELECT NAME,CREATOR,BOUNDTS FROM SYSIBM.SYSPACKAGE`
  / `SELECT NAME,CREATOR,BOUNDTS FROM SYSIBM.SYSPLAN`, capturing
  `SYSPRINT` as text — mechanically identical to `racf.yml`'s
  `dd_output`/`return_content: {type: text}` pattern.
- Write `db2_catalog.txt` (raw DSNTEP2 report text, parsed off-host,
  matching the "capture raw, parse off-host" convention used everywhere
  else in this pipeline).
- **This one is the most speculative of all six** — DSNTEP2's exact
  authorization/PLAN requirements vary by site DB2 setup; needs real
  validation against an actual DB2 subsystem more than any other domain
  here.

**Python:**
- `models.py`: `Db2Package` (name, creator, bound_timestamp, ssid),
  `Db2Plan` (name, creator, bound_timestamp, ssid).
- New `db2_catalog_parser.py`: DSNTEP2's report format is fixed-width
  column headers over each `SELECT` — closest existing precedent is
  `racf_parser.py`'s fixed-offset slicing, or simpler, whitespace-split
  per data row (DSNTEP2 output is more regular than IRRDBU00's).
- `store.py`/`cli.py`/tests: same pattern.

---

## 4. Networking: VTAM + APPN + TCPIP

**Goal:** VTAM major-node status and APPN enablement/role (`vtam.yml`,
tag `vtam`), plus live TCP/IP interface addresses and (opt-in) the actual
`PROFILE.TCPIP`-style configuration text (`tcpip.yml`, tag `tcpip`).
Parallels PROCLIB/PARMLIB's "what's configured" role for the network
stack, same as USS mounts did for the filesystem side.

### VTAM (`ansible/roles/zos_extract/tasks/vtam.yml`, tag `vtam`, unconditional)

Two `zos_operator` calls, bundled into one `vtam.txt` via the
`##BLOCKNAME` sentinel convention `sysinfo.yml`/`catalog.yml` already use
(`blocks.split_named_blocks()`, not `jcl_parser.split_members()`'s
`##MEMBER name` vocabulary) -- exact same template shape as
`sysinfo.yml`'s `##SYMBOLS`/`##IPLINFO` bundling:

```yaml
- name: Issue D NET,MAJNODES
  ibm.ibm_zos_core.zos_operator: {cmd: "D NET,MAJNODES"}
  register: zos_extract_vtam_majnodes_reply

- name: Issue D NET,VTAMOPTS
  ibm.ibm_zos_core.zos_operator: {cmd: "D NET,VTAMOPTS"}
  register: zos_extract_vtam_options_reply

- name: Write vtam.txt
  ansible.builtin.copy:
    dest: "{{ zos_extract_local_output_dir }}/{{ zos_extract_vtam_outfile }}"
    content: |-
      ##MAJNODES
      {{ zos_extract_vtam_majnodes_reply.stdout_lines | join('\n') }}
      ##VTAMOPTS
      {{ zos_extract_vtam_options_reply.stdout_lines | join('\n') }}
  delegate_to: localhost
```

`defaults/main.yml`: `zos_extract_vtam_outfile: "vtam.txt"`.

**Python** (`inventory/inventory/vtam_parser.py`):
- `models.py`: `VtamMajorNode(name, status, source_member="")` (a plain
  name+status row, tolerant regex over the `##MAJNODES` block -- same
  "match a status token like ACTIV/ACT\\/S/INACT/PEND\\w* generically
  rather than fixed columns" tolerance `uss_mounts_parser.py` uses for `D
  OMVS,F`'s header lines, since the exact `D NET,MAJNODES` column layout
  isn't confirmed here).
- `VtamStartOption(keyword, value)` for `##VTAMOPTS` -- **generic
  KEYWORD=VALUE capture**, not a narrow `nodetype`/`cpname`-only
  dataclass, matching `Jes2InitStatement`'s precedent: `D NET,VTAMOPTS`'s
  reply is a set of `KEYWORD = VALUE` pairs (same shape
  `discover_active_members.yml`'s IEASYSxx keyword pass already handles
  in Jinja, done here in Python instead), and the exact full keyword set
  isn't confirmed, so capture every one generically rather than guessing
  which subset to hand-model. Answering "is APPN enabled, and as what
  role" is then just `inventory vtam-options` and looking for the
  `NODETYPE`/`CPNAME` rows -- no special-casing needed in the model.
- `parse_vtam(path) -> tuple[list[VtamMajorNode], list[VtamStartOption]]`,
  same return shape as `catalog_parser.parse_catalog()`.
- `store.py`: two tables (`vtam_major_nodes`, `vtam_start_options` --
  latter needs a `source` or just an unindexed flat table, no natural key
  beyond keyword); `cli.py`: `inventory vtam-majnodes` / `inventory
  vtam-options` commands.
- **Not yet validated against a real reply** -- flag in
  `vtam_parser.py`'s docstring and both READMEs, same treatment as
  domains 1/2. `D NET,TOPO` (APPN topology database) is explicitly
  **not** attempted this round per the user's own call, given the same
  format-uncertainty -- `D NET,VTAMOPTS`'s `NODETYPE` is the extent of
  APPN coverage here; topology capture is a candidate follow-up once a
  real reply can be checked. **Update, later round: that real reply
  arrived and `D NET,TOPO` is now implemented and confirmed -- see the
  top-of-file summary and `vtam_parser.py`'s current module docstring.**

### TCPIP (`ansible/roles/zos_extract/tasks/tcpip.yml`, tag `tcpip`)

Same bundling idiom, but the `##PROFILE` block is conditional on
`zos_extract_tcpip_profile_dsn` being set (the `##NETSTAT_HOME` block
always runs):

```yaml
- name: Issue D TCPIP,,NETSTAT,HOME
  ibm.ibm_zos_core.zos_operator: {cmd: "D TCPIP,,NETSTAT,HOME"}
  register: zos_extract_tcpip_netstat_reply

- name: Create a scratch directory for the TCPIP profile fetch
  ansible.builtin.tempfile: {state: directory, prefix: zos_extract_}
  register: zos_extract_tcpip_profile_scratch
  delegate_to: localhost
  when: zos_extract_tcpip_profile_dsn | length > 0

- name: Fetch the TCPIP profile dataset
  ibm.ibm_zos_core.zos_fetch:
    src: "{{ zos_extract_tcpip_profile_dsn }}"
    dest: "{{ zos_extract_tcpip_profile_scratch.path }}/"
    flat: true
  when: zos_extract_tcpip_profile_dsn | length > 0

- name: Write tcpip.txt
  ansible.builtin.copy:
    dest: "{{ zos_extract_local_output_dir }}/{{ zos_extract_tcpip_outfile }}"
    content: |-
      ##NETSTAT_HOME
      {{ zos_extract_tcpip_netstat_reply.stdout_lines | join('\n') }}
      {% if zos_extract_tcpip_profile_dsn | length > 0 %}
      ##PROFILE
      {{ lookup('ansible.builtin.file', zos_extract_tcpip_profile_scratch.path ~ '/' ~ (zos_extract_tcpip_profile_dsn | regex_replace('^.*\(([^)]+)\)$', '\1') if '(' in zos_extract_tcpip_profile_dsn else zos_extract_tcpip_profile_dsn) }}
      {% endif %}
  delegate_to: localhost

- name: Remove scratch directory for the TCPIP profile fetch
  ansible.builtin.file: {path: "{{ zos_extract_tcpip_profile_scratch.path }}", state: absent}
  delegate_to: localhost
  when: zos_extract_tcpip_profile_scratch.path is defined
```

(The `lookup` filename needs the member name, not the full `DSN(MEMBER)`
spec, if the user points `zos_extract_tcpip_profile_dsn` at a PDS member
rather than a sequential dataset -- worth a small helper var instead of
that inline conditional expression at actual implementation time, but the
logic is: zos_fetch already flattens to just the member/dataset name
under the scratch dir, same as `_fetch_active_ieasys_member.yml` does for
IEASYSxx.)

`defaults/main.yml`: `zos_extract_tcpip_outfile: "tcpip.txt"`,
`zos_extract_tcpip_profile_dsn: ""`.

**Python** (`inventory/inventory/tcpip_parser.py`):
- `models.py`: `TcpipHomeAddress(link_name, ip_address, is_primary)`.
  `TcpipProfileStatement(stmt, operands, source_dsn)` -- **generic
  capture** again (first token = statement name, rest of line = raw
  operand text), since `PROFILE.TCPIP` statement syntax is positional
  and varied (`DEVICE name type ...`, `HOME ip link`, `PORT ...`
  reservations) rather than uniform `KEYWORD=VALUE` like VTAMOPTS/JES2 --
  modeling every statement type isn't worth it given the same
  uncertainty as everything else in this section. Skip comment lines
  (`;` is `PROFILE.TCPIP`'s comment marker, confirmed to also work
  mid-line, not just as a full-line comment).
- `parse_tcpip(path) -> tuple[list[TcpipHomeAddress],
  list[TcpipProfileStatement]]`, same shape as `parse_catalog()`/
  `parse_vtam()`.
- `store.py`: two tables; `cli.py`: `inventory tcpip-home` / `inventory
  tcpip-profile` commands.
- **`D TCPIP,,NETSTAT,HOME` CONFIRMED against a real reply on
  2026-07-02** -- the real shape mixes legacy `LINKNAME:` rows with
  OSA-Express QDIO `INTFNAME:` rows under the same HOME ADDRESS LIST,
  and each entry carries its own `FLAGS:` line (sometimes `PRIMARY`,
  which `is_primary` now captures); `tcpip_parser.py` was fixed to
  handle both row kinds (the original guess only matched `LINKNAME:`
  and silently dropped every `INTFNAME:` entry).
- **`PROFILE.TCPIP` statement parsing also CONFIRMED against a real
  member on 2026-07-02**, and needed an actual redesign rather than
  regex tuning: the original "every non-comment, non-blank line is its
  own statement" guess was wrong -- real statements like
  `INTERFACE`/`PORT`/`AUTOLOG`/`BEGINROUTES`/`SMFCONFIG` span multiple
  physical lines (indented sub-parameter continuations, or whole
  indented tables bracketed by a start keyword and, where one exists,
  an `END*` keyword). Indentation alone can't tell a new statement from
  a continuation either -- the real member has `SMFCONFIG` statements
  themselves indented by 2 spaces for no structural reason. Fixed by
  recognizing a fixed, evidence-based vocabulary of top-level statement
  keywords (`_PROFILE_STATEMENT_KEYWORDS`) instead: a line starting
  with a known keyword (regardless of indentation) begins a new
  statement, any other non-comment line is folded into the *current*
  statement's operands. See `tcpip_parser.py`'s module docstring for
  the full detail and the known limitation (an unrecognized keyword
  gets merged into the preceding statement).

---

## 5. SMS storage groups / storage classes

**Goal:** SMS constructs (storage groups, storage classes, management
classes) aren't reachable via `catalog.yml`'s `IDCAMS LISTCAT` (that's
regular dataset catalog entries, not the SMS control dataset). **ACS
routine source is explicitly out of scope** — reading those needs ISMF,
not a read-only D-command, and is a different, much bigger effort.

**Ansible (`ansible/roles/zos_extract/tasks/sms.yml`, tag `sms`):**
- `D SMS,STORGRP(*),LISTVOL` for storage groups + their volumes,
  `D SMS,SC(*)` for storage classes, `D SMS,MC(*)` for management
  classes — three `zos_operator` calls, same console-parse pattern as
  everywhere else (numbered/columnar `D` replies).
- Unconditional (like LNKLST/APF — no opt-in variable needed, these
  commands are always safe/available at any SMS-managed site) or opt-in
  behind a `zos_extract_sms_enabled` flag if SMS isn't universal across
  every site this role might run against — **worth confirming with the
  user before implementing** which gating style fits their actual sites.
- Write `sms_storgrp.txt`/`sms_storclas.txt`/`sms_mgmtclas.txt`.
- **No confirmed real reply for any of the three commands** — same
  validation flag as domains 1/2/4.

**Python:**
- `models.py`: `SmsStorageGroup`, `SmsStorageClass`, `SmsManagementClass`
  (name + the handful of attributes each `D SMS,...` reply exposes).
- New `sms_parser.py`, same numbered-row regex strategy as `lnklst`/`ssn_parser`.
- `store.py`/`cli.py`/tests: three new tables, same pattern.

---

## 6. WLM policy (first cut only — full service classes need z/OSMF)

**Goal:** minimal first cut — active WLM policy name and mode
(goal/compat), the same "single small record" shape as `sysinfo.yml`.
Full service-class/goal/resource-group definitions are **not** part of
this pass: they require the z/OSMF WLM REST API, which means actually
using the `ibm.ibm_zosmf` collection already pinned in `requirements.yml`
("Not used by any task yet -- pinned for future...discovery") for the
first time — a materially bigger effort (new connection/auth model, new
collection actually wired into a play) that deserves its own separate
plan later, not bundled into this sketch.

**Ansible (`ansible/roles/zos_extract/tasks/wlm.yml`, tag `wlm`):**
- `D WLM,POLICY` via `zos_operator`, regex-extract policy name + mode
  (same `_first_match()`-anchor-on-keyword strategy `sysinfo_parser.py`
  already uses for `D IPLINFO`/`D SYMBOLS`).
- Write `wlm.txt`.
- Unconditional, cheap, no new config variable needed.

**Python:**
- `models.py`: `WlmPolicy` (policy_name, mode) — single-record, same
  shape as `SystemInfo`.
- New `wlm_parser.py`: `parse_wlm(path) -> WlmPolicy | None`, modeled
  directly on `sysinfo_parser.parse_sysinfo()`.
- `store.py`: singleton-replace pattern (like `system_info`, not a
  delete-all-rows list table).
- `cli.py`: `inventory wlm` command, same shape as `inventory sysinfo`.
- `tests/test_wlm_parser.py`.

---

## 7. Deepened CICS resource view (DFHRPL lineage + DFHCSDUP definitions) -- IMPLEMENTED (follow-up round)

**Goal:** `cics.yml` (already implemented) only reports "is a CICS address
space up right now" via a `D A,L` job-name/PROCSTEP heuristic -- same
limitation `db2.yml` had before its own deepening (domain 3 above). Two
things are genuinely reachable **without CMCI/CICSplex SM**:

1. **DFHRPL** (CICS's own load-library concatenation, functionally
   identical to STEPLIB/JOBLIB but for CICS's dynamic program loading) --
   feeding its datasets through the *already-implemented* SMP/E zone/FMID/
   APF resolution this project already applies to STEPLIB/JOBLIB/LNKLST
   gives "what installed, patched software does this CICS region actually
   depend on," the same value proposition as the core PROCLIB/PARMLIB
   pipeline. Enumerating DFHRPL's member list also gives a *candidate*
   list of load modules the region could execute -- a supply-side ceiling,
   not an authoritative resource inventory (a member being present doesn't
   mean a `PROGRAM` resource definition actually points at it).
2. **DFHCSDUP LIST** -- CICS's own offline batch utility for reading
   resource definitions straight out of the CSD (the VSAM KSDS backing a
   region's `PROGRAM`/`TRANSACTION`/`FILE`/... definitions). This is the
   actual analog to what CMCI would otherwise provide live: real
   *defined* resources, not just "is the address space up." Structurally
   identical to how this project already runs GIMSMP/IDCAMS/IRRDBU00/
   DSNTEP2 via `zos_mvs_raw` -- authorize, run, capture `SYSPRINT` text,
   parse off-host.

Also cheap to grab alongside DFHRPL/CSD discovery: the CICS startup
step's **SYSIN** (SIT -- System Initialization Table -- override
parameters: `APPLID=`, `GRPLIST=`, `SEC=YES/NO`, `START=`, etc.) -- a
"what's configured" region-identity/posture snapshot, the same idea as
IEASYSxx keyword capture elsewhere in this pipeline. Lower value than the
two items above, but free once the PROC is already being fetched for
DFHRPL/DFHCSD.

**Scope decision confirmed with the user:** there is no reliable
*live-discoverable* link from a running CICS address space's job name
back to which specific PROCLIB member started it (`D A,L`'s PROCSTEP is
the step name within the PROC, not the PROC's own member name) -- unlike
PROCLIB/PARMLIB/JES2-parmlib, which all have a real console command or
IEASYSxx-keyword path to their active member/concatenation. Matches this
project's own established precedent (`zos_extract_db2_ssid`,
`zos_extract_smpe_csi`, `zos_extract_racf_database_dsn`): where
auto-discovery isn't reliable, require **explicit config** instead of
guessing, rather than attempting a fragile job-name-to-PROC-name
cross-reference. New var: `zos_extract_cics_proc` (the CICS startup
PROCLIB member name(s) -- a list, since a site can run several CICS
regions from different PROCs).

**Ansible (`ansible/roles/zos_extract/tasks/cics_deepening.yml` or similar,
tag `cics`, `when: zos_extract_cics_proc | length > 0`):**
- Fetch the named PROC member(s) from the already-configured
  `zos_extract_proclibs` concatenation -- same `zos_find` (across every
  configured PROCLIB) + `subelements`/`selectattr` ("which configured
  PROCLIB actually contains this member") + `zos_fetch` idiom
  `discover_mstrjcl_proclibs.yml`/`_fetch_active_ieasys_member.yml`
  already use for MSTJCLxx/IEASYSxx.
- Parse the fetched PROC text (off-host, new `cics_proc_parser.py`) for:
  - `DFHRPL` DD + unnamed continuation DDs -> concatenation of DSNs (same
    "DD group" regex `discover_mstrjcl_proclibs.yml` already uses for
    `IEFPDSI`, reusable near-verbatim).
  - `SYSIN` DD `*` inline cards (or `SYSIN DD DSN=...` pointing at a PDS
    member) -> SIT override text, captured generically as
    `KEYWORD=VALUE` pairs (same idiom `VtamStartOption`/
    `Jes2InitStatement` already use).
  - `DFHCSD` DD `DSN=` -> the CSD dataset name.
- Once the CSD dsn is known, run `DFHCSDUP LIST` via `zos_mvs_raw`
  (mirrors `db2_catalog.yml`/`racf.yml`/`catalog.yml`'s `zos_mvs_raw`
  precedent exactly): `STEPLIB`/`DFHRPL` = the just-discovered DFHRPL
  concatenation (reuse the conditional-DD-list-building idiom
  `_smplist_zone.yml`/`db2_catalog.yml` already use), `SYSIN` = a control
  statement (**exact real syntax not confirmed** -- something like
  `LIST ALL GROUP(...)`, needs checking against real DFHCSDUP docs),
  `DFHCSD` DD = the discovered CSD dsn, `SYSPRINT` = `dd_output` text.
- **Real operational risk, not just a formatting uncertainty:** a live
  CICS region normally holds its CSD open -- whether a batch `DFHCSDUP
  LIST` job can read it concurrently (`DISP=SHR`) or needs a backup copy
  first isn't confirmed here. Flag this with the same weight RACF's own
  "needs a READ-accessible COPY, not the live primary" caveat carries,
  not folded in as an afterthought.
- Bundle DFHRPL list + SIT text + DFHCSDUP `SYSPRINT` report into one file
  via `##DFHRPL`/`##SIT`/`##CSD` sentinels, same `##BLOCKNAME` convention
  `sms.txt`/`vtam.txt` already use.

**Python:**
- `models.py`: a `CicsDfhrplEntry` (dsn, zone, apf_authorized,
  source_member) for the store layer (conceptually reuses `Dataset`'s own
  zone-matching, but needs its own denormalized row shape the way
  `lineage` already does); `CicsSitOverride` (keyword, value,
  source_member) -- generic capture, same shape as `VtamStartOption`/
  `Jes2InitStatement`; `CicsCsdDefinition` (def_type, name, group,
  params: dict, source_member) -- generic capture again, since
  DFHCSDUP's real `LIST` report column layout isn't confirmed (this
  sub-piece is at least as speculative as the DB2/WLM-z/OSMF domains).
- `resolver.py`: expose the currently-private `_dataset_to_zone` as a
  small reusable public helper (e.g. `dataset_zone()`) so DFHRPL entries
  can be zone/APF-resolved the same way LNKLST/STEPLIB already are,
  without duplicating that logic in a new module.
- New `cics_proc_parser.py` (DFHRPL/SIT/CSD-dsn extraction from the PROC
  text) and `cics_csdup_parser.py` (the DFHCSDUP `LIST` report) --
  **the DFHCSDUP report parser is the most speculative piece of this
  whole domain**, same tier as `db2_catalog_parser.py`/
  `wlm_zosmf_parser.py`.
- `store.py`/`cli.py`: three new tables + `save_*`/`all_*` pairs + query
  subcommands (`cics-dfhrpl`, `cics-sit`, `cics-csd`), same pattern as
  every other domain.
- Tests + hand-built fixtures for both new parsers.

**Resolved via research, implemented:** `DFHCSDUP`'s control-statement
syntax (`LIST ALL` / `LIST LIST(name) OBJECTS`) and its real read-only
access parameter (`PARM='CSD(READONLY)'`, confirmed via IBM APAR
PM04030's own title) were both confirmed against real IBM documentation
rather than guessed, resolving the two blockers noted above -- see
`ansible/roles/zos_extract/tasks/cics_deepening.yml`'s header comment for
the full reasoning, including why `CSD(READONLY)` is the documented-safe
way to read a live region's CSD without quiescing it.

**Still genuinely open (needs a real system, not just documentation
research):** DFHCSDUP's own LIST report *print format* -- no real sample
was found even after the syntax/access-mode research above, so
`cics_csdup_parser.py` is deliberately the most tolerant parser in the
pipeline as a result (see its module docstring). Also still open: whether
this site's actual CICS regions' CSD-access mode lets a concurrent
`CSD(READONLY)` batch DFHCSDUP job succeed cleanly in practice, and
whether DFHCSDUP's real return code for a clean `LIST` is always 0 (left
at `zos_mvs_raw`'s default, unlike GIMSMP's `max_rc: 4` in
`smplist.yml`) -- both need a real system to confirm, the same way
DSNTEP2's authorization/PLAN requirements needed a real DB2 subsystem.

---

## 8. SMP/E traceability: CSI-aware zones + started-task lineage

**Context:** gap analysis (2026-07-02) of the SMP/E side of the pipeline,
prompted by the user needing full traceability from started task -> PROCLIB
member -> program -> SMP/E holding CSI. Found that the started-task ->
lineage join doesn't exist anywhere in code, and the CSI itself isn't
modeled at all despite this site having (at least) four real CSIs --
`ansible/output/bes2/smpe_csi_candidates.txt` shows separate CPWR, IOA,
OPSDATAI, and ACOM100 GLOBAL CSIs, each presumably with its own
target/dlib zones. Seven items below, in the priority order the user
picked; implementation proceeds 8a+8b, then 8c+8d, then 8e, then 8f, then
8g.

### 8a. `Zone.csi` field (do first)

- `models.py`: add `csi: str = ""` to `Zone`.
- `smpe_parser.py`: recognize an optional `##CSI <name>` sentinel as the
  first line of a `*smplist*.txt` file (same `##BLOCKNAME`-prefix
  convention `sysinfo.yml`/`vtam.yml`/`cics_deepening.yml` already use
  elsewhere) and stamp every `Zone` parsed from that file with it; a file
  with no header defaults to `csi=""` (backward compatible with the
  existing fixture and any already-captured real files that predate this).
- `merge_zones()`: copy `csi` across when combining zone maps
  (`target.csi = zone.csi or target.csi`).
- Extraction side, both paths that produce `*.smplist.txt` need to emit
  the header: `zos-extract/python/smplist.py` (prepend `##CSI {csi}\n`
  before writing `report_text`) and
  `ansible/roles/zos_extract/tasks/_smplist_zone.yml` (prepend the same
  line in its `content:` template, using `zos_extract_smpe_csi`).
- Known limitation accepted for now: `merge_zones()` still keys purely on
  zone *name*, so two same-named zones from two different CSIs would
  collide -- 8c is what actually fixes that; 8a just makes the CSI
  visible/queryable for the common single-CSI-per-run case this pipeline
  handles today.

### 8b. `inventory trace NAME`: started task -> proclib -> program -> zone -> FMID -> CSI (do first, alongside 8a)

- `LineageStep` gets a `csi: str | None = None` field; `resolver.py`'s
  `resolve_member()` sets it from `zones[zone_name].csi` alongside the
  existing `fmid`/status lookup.
- `store.py`: add a `csi TEXT` column to the `lineage` table, update
  `save_lineage()`'s INSERT accordingly.
- `cli.py`: new `cmd_trace(name)` -- looks up `started_tasks` rows
  matching `name` (case-insensitive), `active_jobs` rows matching `name`
  (is it running right now, and as what ASID), and
  `lineage_for_member(name)` (reusing the existing member->steps query,
  since `StartedTask.task_name` is actually the PROC member name per real
  MVS `START procname[.identifier]` syntax) -- printed as one combined
  narrative, with each lineage step now also showing `CSI=`.
- Also surface `csi` in the existing `lineage`/`report` output -- it's the
  same data, just was never plumbed through to those commands before.
- Known gap flagged, not fixed this round: `S task,PROC=realproc` override
  syntax isn't parsed by `ssn_parser.py`'s `_COM_START` regex -- a task
  started that way won't join correctly by name alone. Note this in
  `ssn_parser.py`'s docstring as a follow-up.

### 8c. Multi-CSI ingest -- IMPLEMENTED

- Extraction: `zos_extract_smpe_csi`/`zos_extract_smpe_zones` (scalars)
  were hard-renamed to `zos_extract_smpe_csis` (a list of `{csi, zones}`
  entries, no back-compat shim -- same precedent as the earlier
  `zos_extract_jes2_parmlibs` -> `zos_extract_jes2_init_members` rename).
  `smplist.yml` flattens it via `zos_extract_smpe_csis | subelements
  ('zones')` (same idiom `_fetch_active_ieasys_member.yml`/
  `_cics_proc_dump.yml` already use) into one (csi, zone) pair per
  include of `_smplist_zone.yml`, so each CSI's zones land tagged
  correctly via 8a's `##CSI` header. Output filenames now also carry the
  CSI (`<csi-slug>.<zone>.smplist.txt`) so two CSIs' same-named zones
  don't clobber each other's output file either.
- `merge_zones()`: rather than a `(csi, name)` composite key everywhere
  (which would've broken `resolver._dataset_to_zone()`'s `return
  zone.name` -> `zones[zone_name]` lookup chain, since that return value
  has to double as a valid dict key), zones are normally still merged by
  bare name; a genuine collision (same name, different non-empty `csi`)
  is detected and the *incoming* zone is kept under a disambiguated
  `"NAME@CSI"` key/`.name`, so `zone.name` and its own dict key always
  stay in sync. Covered by
  `test_merge_zones_disambiguates_cross_csi_name_collision`.
- Deliberately **not** resolved this round: a dataset genuinely shared
  across two loaded CSIs' DDDEF entries (e.g. a common `SYS1.LINKLIB`)
  still resolves to whichever zone `_dataset_to_zone()` happens to find
  first -- flagged in `merge_zones()`'s docstring, not silently assumed
  fixed.

### 8d. Authoritative zone discovery via `LIST GLOBALZONE` -- IMPLEMENTED

- Real command confirmed via research (not guessed from scratch, same
  standard this project already held CICS/WLM/JES2/SMS command syntax
  to): `LIST ZONES` isn't a real GIMSMP command at all -- the actual way
  to enumerate every zone tied to a CSI is `SET BDY(GLOBAL). LIST
  GLOBALZONE .`, whose report includes a `ZONEINDEX` attribute (zone
  name / zone type / owning CSI dataset, one per line). CONFIRMED against
  a real LIST GLOBALZONE report from this site (`MVS.GLOBAL.CSI`,
  `smpe_zone_discovery` tag run against zdt3) -- found and fixed a real
  bug in the process: `_ZONEINDEX_FIRST` required the ZONEINDEX line to
  carry its entry's name-token prefix (as in the third-party reference
  this was first built against), but that prefix is only present when
  ZONEINDEX happens to be the *first* attribute printed for that entry.
  Real output had UPGLEVEL first instead, so ZONEINDEX appeared bare with
  no name token and silently parsed to zero entries. Fixed by making that
  leading token optional; regression test
  `test_parse_globalzone_handles_unprefixed_zoneindex_line` covers it.
  Also surfaced a real, legitimate SMP/E pattern worth noting: this
  GLOBAL zone's ZONEINDEX cross-references a target/dlib zone pair
  (`CSQ920T`/`CSQ920D`) that live in a completely different product's CSI
  (`CSQ920.CSQ920*.CSI`) than the GLOBAL zone itself -- `Zone.csi` vs.
  `ZoneIndexEntry.source_csi` already distinguished exactly this case.
- New `discover_smpe_zones.yml` (tag `smpe_zone_discovery`) +
  `_smplist_globalzone.yml` worker, one GIMSMP call per configured CSI,
  writing `<csi-slug>.smpzones.txt` (with the same `##CSI` sentinel).
- Deliberately **not** wired to auto-drive `smplist.yml`'s own per-zone
  loop in the same run -- doing so would mean parsing GIMSMP's report
  text in Jinja/Ansible, breaking this whole pipeline's "capture raw
  text, parse off-host in Python" convention every other domain follows.
  Populating `zos_extract_smpe_csis`' `zones:` list from what this
  reveals is still a manual step, same human-in-the-loop precedent
  `discover_smpe_csis.yml` already set for CSI names themselves -- just
  backed by an authoritative SMP/E fact now instead of nothing.
- New `ZoneIndexEntry` model, `smpe_parser.parse_globalzone()`, a
  `zone_index` table, and `inventory zone-index`.
- **Not yet built**: any "zone-gaps" comparison against what
  `*smplist*.txt` actually captured -- doing that against `lineage` alone
  would falsely flag a zone with no PROCLIB step pointing into it as
  "missing." That comparison belongs with 8f's standalone `zones` table
  below, not bolted onto `zone_index` early.

### 8e. Capture `LMOD=` for module resolution -- IMPLEMENTED

- `smpe_parser.py`'s `LIST MOD` section previously keyed `module_fmid`
  only by the *element* name (from the `LASTUPD` line) and ignored the
  `LMOD=` line entirely. `Zone` now has a separate `lmod_fmid: dict[str,
  str]`, keyed by the real load-module name from `LIST MOD`'s own `LMOD=`
  line (which can differ from the element name), and
  `resolver._fmid_for_module()` checks `lmod_fmid` first, falling back to
  `module_fmid` (by element name) for zones ingested before this existed
  or an element with no `LMOD=` line at all.

### 8f. Standalone `zones`/`fmids` tables + CLI -- IMPLEMENTED

- `store.py`: new `zones` table (name, csi, dddefs as JSON) and `fmids`
  table (fmid, zone, status), populated directly from the parsed `Zone`
  objects at ingest time -- not derived from lineage, so this is
  queryable independent of whether any PROCLIB step happens to reference
  the FMID.
- `cli.py`: `inventory zones` / `inventory fmids` commands -- a full
  SMP/E software inventory, not just what lineage resolution touches.
- The previously-dead `Fmid` dataclass in `models.py` is now wired up as
  this table's row shape (built by flattening every zone's `fmid_status`
  at ingest time).
- `inventory zone-gaps`: the cross-reference 8d's `zone_index` table
  deliberately didn't get -- compares `zone_index` entries against the
  `zones` table (by name) to flag a zone SMP/E itself says exists but
  that was never actually captured via `*smplist*.txt` -- the real "find
  the gaps" capability this whole round started from, made permanent
  instead of a one-time by-hand analysis.

### 8g. Confirm `smpe_parser.py` against a real `*.smplist.txt` -- CONFIRMED

- Every other console/text parser in this pipeline has been confirmed
  against real output this round except this one -- get a real
  `LIST DDDEF`/`MOD`/`SYSMOD` report from this site and diff it against
  the regex assumptions here, the same process already used for
  VTAM/TCPIP/JES2/WLM/SMS above. `LIST ZONES`/`LIST GLOBALZONE` (8d) is
  already confirmed separately, above.
- Discovered a real infrastructure blocker before a single real
  `*.smplist.txt` was even in hand: this site's base z/OS target zone
  (`MVST` in `MVS.GLOBAL.CSI`, found via `MVS.*.CSI` CSI discovery once
  `EDUC.**.CSI` came back empty on zdt3) produces a `LIST DDDEF`/`MOD`/
  `SYSMOD` report near **15 million lines**. Two fixes landed for this
  before a real capture could even be attempted:
  - `SMPWRK6`'s original fixed 5MB-primary/no-secondary allocation
    B37-04'd (out of space) against a zone this size -- both now
    configurable (`zos_extract_smpe_smpwrk6_primary`/`_secondary`,
    default 50MB/50MB).
  - `SMPLIST` itself was captured via `zos_mvs_raw`'s
    `dd_output`/`return_content`, which buffers the *entire* report
    inline in the ansible module's own JSON result -- that architecture
    can't scale to millions of lines at all, independent of space sizing.
    `_smplist_zone.yml` now allocates `SMPLIST` as a real persistent data
    set (`zos_extract_smpe_smplist_primary`/`_secondary`, default
    2000MB/2000MB) and retrieves it via `zos_fetch` (a real SFTP-style
    transfer, not JSON-embedded content), finalizing the `##CSI`-prefixed
    output file with a local `cat` rather than loading it into Ansible's
    own memory/Jinja engine.
  - A third bug surfaced once the pipeline actually ran end-to-end: the
    final "Prepend the `##CSI` sentinel..." task's `ansible.builtin.shell`
    used a `>-` (folded) block scalar with its `cat ...` continuation line
    indented two spaces deeper than the lines above/below it. YAML's
    folding rule preserves (rather than folds to a space) the newlines
    around any more-indented line, so the *executed* command actually had
    a bare newline between `cat ...report.txt; }` and `> dest.txt` --
    which parses in `sh` as two separate statements: the `{ ...; }` group
    (whose stdout landed in the ansible module's own captured `stdout`,
    not the file) followed by a command-less `> dest.txt` redirect that
    just truncated the destination to zero bytes. Fixed by re-indenting
    all three continuation lines to the same level so the block scalar
    folds into one real single-line command; confirmed via
    `yaml.safe_load` that the rendered command is now one line with the
    redirect attached to the `{ ...; }` group.
  - Confirmed fixed: rerunning the `smplist` tag against `MVST` after the
    indentation fix produces a real, non-empty `mvs_global_csi.mvst.smplist.txt`.
  - `LIST DDDEF` CONFIRMED against a real slice of that report (`MVST`
    target zone, MVS.GLOBAL.CSI): the `"<zone>  <TYPE> ENTRIES"` section
    title and the two-line `NAME  DATASET = dsn` / `disposition` entry
    shape both matched as expected.
  - That same real report exposed a genuine parser bug, unrelated to the
    DDDEF shape itself: the section title reprints at the top of **every
    page** (confirmed from the raw stdout -- `"MVST    DDDEF ENTRIES"` /
    `"  NAME"` repeat on page 2, page 3, ...), not just once per section.
    `LIST MOD` entries are multi-line blocks (LASTUPD name, then later
    FMID=, then LMOD=, sometimes several lines apart), and the parser
    treated every repeated section-title match as a fresh section start,
    unconditionally wiping `pending_modname`/`pending_fmid`. Against a
    report this size, a page break landing between an element's LASTUPD
    and FMID lines would silently drop that element's FMID/LMOD tie with
    no error. Fixed in `parse_smplist()` to only reset that pending state
    on an actual section change, not a same-section page-break repeat.
    Regression test: `test_mod_entry_survives_page_break_between_lastupd_and_fmid`
    (`sample_smpe_mod_page_break.txt`, modeled on the real page-break
    shape) -- confirmed it fails without the fix (empty `module_fmid`)
    and passes with it.
  - `LIST SYSMOD` CONFIRMED against a real entry (`HBB77E0`, same `MVST`
    zone): `TYPE=`/`STATUS=` resolve correctly (`STATUS = REC  APP` ->
    `REC/APP`), its `LASTUPD` line's embedded `TYPE=UPD` doesn't
    false-positive as a new SYSMOD header, and a page break landing
    mid-entry doesn't disturb an already-captured status. Regression
    test: `test_sysmod_entry_parsed_from_real_report_with_page_break`
    (`sample_smpe_sysmod_real.txt`, a trimmed real slice including a page
    break inside the entry). Noted (not fixed, out of current scope):
    real SYSMOD entries carry several long dependency-list attributes
    this parser doesn't extract at all (`DLMOD=`/`CLIST=`/`DATA=`/`MAC=`/
    `MOD=`/`HELP=`/`HFS=`/...), and those values can be split mid-token
    across a page boundary (e.g. a real `IWMARID`/`M` split producing
    `IWMARIDM`) -- irrelevant to the fields already extracted, but would
    need reassembly logic if any of those attributes are ever added to
    `Zone`.
  - `LIST MOD` CONFIRMED against a real report (three `ACBFUTOx` elements,
    same `MVST` zone) -- and that real report exposed one more genuine
    bug: the SMPCNTL command is `LIST MOD .`, but GIMSMP's own section
    title prints as `"<zone>    MODULE   ENTRIES"`, not `"MOD ENTRIES"`.
    `_SECTION_HDR` only recognized the literal `"MOD"` alternative, so
    this title line never matched at all -- in this pipeline's own
    single-zone-per-file shape (LIST DDDEF always run first in the same
    SMPCNTL), `current_zone` had already been set by the preceding DDDEF
    section title, so element data still landed in the right zone by
    accident, but nothing about MOD sections would work standalone, and
    (since the title never matched at all) the every-page-reprint
    page-break fix above could never even engage for MOD sections in
    practice. Fixed by adding `"MODULE"` to `_SECTION_HDR`'s alternation
    and `_SECTION_BY_TYPE`. Also corrected the earlier page-break
    regression fixture (`sample_smpe_mod_page_break.txt`), which had used
    the wrong `"MOD ENTRIES"` title text and so wasn't actually testing
    the real shape. Regression test: `test_mod_section_title_says_module_not_mod`
    (`sample_smpe_mod_real.txt`) -- confirmed it fails without the fix
    (`module_fmid`/`lmod_fmid` both completely empty, not just missing
    LMOD, since `current_zone` never got set at all in a standalone
    single-section fixture) and passes with it.
  - Every `LIST DDDEF`/`MOD`/`SYSMOD` section is now confirmed against
    real output from this site -- this section is done.

---

## Cross-cutting work (applies to whichever domain(s) get picked up)

- **README updates**, every time: `zos-extract/README.md`'s numbered
  "What to run" list + naming-convention table, `ansible/README.md`'s
  Layout section and any opt-in-domain explanation section, and
  `inventory/README.md`'s naming-convention table.
- **Validation flag convention**: any domain whose console-command output
  shape isn't confirmed against a real reply from this site gets the same
  treatment RACF got — implemented and tested against a synthetic
  fixture, with an explicit "not yet validated against a real system,
  confirm before relying on it" note in the module docstring and README.
- **Testing**: one `tests/test_<domain>_parser.py` per new parser module,
  fixtures under `tests/fixtures/`, following the existing per-parser test
  file structure (see `test_racf_parser.py`/`test_ssn_parser.py` as
  templates).

## Verification (once any domain above is actually implemented)

1. `cd inventory && python -m pytest` — new parser tests plus the full
   existing suite (must stay green).
2. `cd ansible && ansible-playbook --syntax-check playbooks/site.yml -i inventory` —
   confirm the new task file(s) parse cleanly (see the
   `pds_patterns`/`zos_operator.content` breakage found earlier this
   session — this check alone won't catch API-shape drift against a real
   target, so real execution against a test LPAR remains the actual
   confirmation step).
3. Run the new tagged step against a real system
   (`ansible-playbook playbooks/interactive.yml --tags <domain>`) and
   diff the actual console/dump output against the regex assumptions
   above before trusting the parser — this is the step that resolves
   every "not yet validated" flag in this plan.
4. `inventory ingest input/` then the new `inventory <domain>` command,
   confirming rows show up as expected.

**Progress on step 3, this round**: the user ran real `opercmd`/console
`D`-commands against their actual z/OS system and pasted the output back,
across several rounds. Confirmed against real replies so far: `D
NET,TOPO`, `D NET,MAJNODES`, `D NET,VTAMOPTS` (all of VTAM), `D OMVS,F`
(USS mounts), `D SYMBOLS`/`D IPLINFO` (sysinfo), `D WLM` (WLM policy),
`$DINITINFO` (JES2's own init-member discovery), and `D
SMS,STORGRP(ALL),LISTVOL`/`D SMS,SG(ALL),LISTVOL` (SMS storage groups) --
each parser was checked against the real text and, where it didn't
already match, corrected and re-flagged as confirmed rather than "not yet
validated" in both the module docstrings and both READMEs.

Several of these turned out to be more than formatting fixes -- some
originally-guessed *commands themselves* didn't exist:
- `sysinfo_parser.py`'s regexes needed real rewrites (no `SYSNAME  =
  &SYSNAME. = value` label prefix in a real reply, `VOLUME(x)` not
  `VOLUME: x`, no `IPL PARM nn` text at all).
- **`wlm.yml`'s originally-guessed command, `D WLM,POLICY`, doesn't exist
  as a command at all** -- a real system rejected the `POLICY` keyword
  outright; the real command is bare `D WLM`, and the real reply never
  contains a `MODE=` token either (`mode` is now inferred as `GOAL` from
  a policy name being present, since WLM compatibility mode is
  desupported on modern z/OS).
- **`discover_jes2_parmlib.yml`'s originally-guessed command, `$D
  PARMLIB`/`$DPARMLIB`, also doesn't exist** -- confirmed invalid against
  a real system. The real command is `$DINITINFO`, and its real reply
  changed the *design*, not just the command name: it reports the exact
  `dsn(member)` pairs JES2 read at startup directly, not a concatenation
  needing a separate "find the active member" step -- `jes2parm.yml` was
  rewritten to fetch exactly those pairs instead of dumping every member
  of their owning dataset(s) (which, in the real reply, is a shared
  site-wide PARMLIB that would have been noisy/wrong to dump wholesale).
  `zos_extract_jes2_parmlibs` was renamed to `zos_extract_jes2_init_members`
  to reflect the new shape.
- **`sms.yml`'s originally-guessed `D SMS,SC(*)`/`D SMS,MC(*)` commands
  don't exist at all** -- confirmed invalid against a real system, and
  IBM's own `D SMS` syntax reference confirms there's no console
  D-command for storage/management classes whatsoever (needs ISMF or a
  batch report, same category as CICS/DB2/RACF). Removed entirely rather
  than kept as dead code. `D SMS,STORGRP(*),LISTVOL` also had a real
  syntax bug (`*` isn't valid, only a name/`ALERT`/`ALL`) -- fixed to `D
  SMS,STORGRP(ALL),LISTVOL`, then confirmed against a real reply (via the
  `SG` alias) whose actual shape (a storage-group summary table plus a
  *separate* flat volume-to-group table) was completely different from
  the original "header + indented VOLSER lines" guess. `sms_parser.py`
  was rewritten from scratch; `SmsStorageGroup` gained a `group_type`
  field and its `status` field now holds raw per-system symbols instead
  of a decoded word.

USS mounts and VTAM's three commands, by contrast, turned out to already
be tolerant enough to handle their real reply shapes without any code
changes, just re-flagging.

`D TCPIP,,NETSTAT,HOME` is now confirmed too (see section 4 above) --
the real reply mixed legacy `LINKNAME:` rows with OSA-Express QDIO
`INTFNAME:` rows the original guess never accounted for, silently
dropping every `INTFNAME:` entry until fixed. `PROFILE.TCPIP` statement
parsing is confirmed as well, against a real member -- unlike
`NETSTAT,HOME` this one needed an actual redesign, not just regex
tuning: real statements can span many physical lines (continuation
sub-parameters, or whole indented tables like `PORT`'s ~80-row
reservation list), which the original one-line-per-statement guess
didn't account for at all.

The content of a real JES2 init-deck member is now confirmed too, against
two real members (`JES2PARM` and the `JES2NJE` member it pulls in via an
`INCLUDE` statement) -- and it needed a real parser fix, not just
re-flagging. The real members are a site copy of IBM's own
HASPPARM-derived template, comments and all (a common, legitimate way
shops build their real init deck): `/* ... */` comments trailing on the
same line as real content, and comments spanning multiple physical lines
(decorative section-divider boxes), weren't stripped by the original
"skip a line that's *entirely* a comment" check -- a trailing same-line
comment got glued onto real parameter text (corrupting the params dict
with a garbage key), and a multi-line comment's non-`/*`-prefixed
continuation line got fed to the statement parser as if it were real
content. Fixed by stripping every `/* ... */` span from the whole
member's raw text up front (regex, DOTALL so a multi-line span is
stripped as a whole) before any line-based processing. Also found: a
statement can legitimately have a subscript and zero live parameters if
its only real parameters are documented-but-commented-out in this
particular member (`FSS(PRINTOFF)`, `LOADMOD(JESEXIT5)`) -- the original
regex required at least one parameter and silently dropped these; the
trailing params group is now optional.

Still outstanding from the original "not yet validated" list: DSNTEP2
(DB2), IRRDBU00 (RACF), IDCAMS `LISTCAT` (catalog), and DFHCSDUP's LIST
report format (CICS) -- these four aren't console
`D`-commands runnable via a quick `opercmd` paste (they all need a
batch JCL run instead).

**Attempting DSNTEP2 validation surfaced a real, unrelated bug first**:
`db2.yml`'s "Write db2.txt" task (tag `db2`, runs before `db2_catalog.yml`
in the same play/tag) crashed the whole run with `"src (or content) is
required"` against a real site (`DBDG` subsystem on `zdt3`) where zero
address spaces matched its `PROCSTEP == 'DB2PROC'` OR job-name-pattern
heuristic -- this site's real DB2 job names are prefixed with the
subsystem ID itself (`DBDGMSTR`/`DBDGDBM1`/`DBDGIRLM`/`DBDGDIST`), not a
literal `"DB2"`, and none of their real PROCSTEPs are `"DB2PROC"` either
(`IEFPROC`, or none). Root cause: `ansible.builtin.copy` treats an empty
(or Jinja-`None`) `content:` string as "not provided" rather than writing
an empty file, and the task's `{% for %}...{% endfor %}` template
rendered to nothing when no address space matched. `db2.yml`'s own
docstring had also overclaimed `PROCSTEP == "DB2PROC"` was "true for
every DB2 address space... in a real reply from this site" -- disproven
by this real reply; corrected. Fixed both the crash (split into a
`set_fact` building the matched text, then `(text | default('', true)) ~
'\n'` guarantees non-empty content) and found/fixed the identical latent
bug in `cics.yml` (same for-loop-in-content pattern; hadn't crashed yet
only because this site's real CICS regions do have `PROCSTEP="CICS"`).
Confirmed the fix against the exact real zero-match data from this run.
DSNTEP2 itself is still unconfirmed -- this just unblocks getting there.

**Two more real DSNTEP2 failures, in sequence, once `db2.yml` stopped
blocking the run:**
1. `rc=12`, empty `SYSPRINT`, nothing to diagnose why -- `SYSTSPRT` (where
   the `DSN`/`RUN` TSO command processor prints its own diagnostics:
   connection failures, plan-not-found, RACF authorization errors) was
   wired as `dd_dummy` in `db2_catalog.yml`, discarding exactly the
   output needed. Fixed by capturing it as text too, same as `SYSPRINT`.
2. With that fixed, the real diagnostic came back: `IKJ56500I COMMAND DSN
   NOT FOUND` -- the `DSN` TSO command processor's load module wasn't
   reachable from the batch job with only `zos_extract_db2_steplib` (one
   DSN) on STEPLIB. Root cause: DB2's own load modules are conventionally
   split across **two** libraries (`SDSNLOAD` plus `SDSNLOD2`, an IBM
   DB2-for-z/OS installation convention that predates and is unrelated to
   this site specifically -- confirmed real for this site's DB2 install,
   `DSND10.SDSNLOAD`/`DSND10.SDSNLOD2`), but `zos_extract_db2_steplib`
   was designed single-DSN, matching `zos_extract_smpe_steplib`'s own
   precedent -- which turned out not to generalize here. Added
   `zos_extract_db2_steplib2` (optional, second DSN) and switched
   `db2_catalog.yml`'s STEPLIB DD from a single `dd_data_set` to
   `zos_mvs_raw`'s `dd_concat` (confirmed via `ibm_zos_core`'s own module
   docs that a real STEPLIB concatenation needs `dd_concat` -- two
   separate `dd_data_set` entries sharing one `dd_name` is not how this
   module represents a concatenation, unlike some other DD types).
   Verified the rendered DD list is correct for zero/one/two STEPLIB DSNs
   via a standalone test playbook before committing. DSNTEP2 itself is
   still unconfirmed -- next real run should reveal whether `DSN`/`RUN`
   now succeed, or surface report-format specifics for
   `db2_catalog_parser.py` to check.
3. With STEPLIB fixed, `DSN`/`RUN` themselves parsed correctly this
   time (`rc=8`, not a TSO/JCL-level failure), but DB2 itself reported
   `DSNE139E NOT ABLE TO LOCATE DSNTEP2 IN THE STANDARD SEARCH ORDER` --
   this site never installed/bound `DSNTEP2` under that name.
   `zos_extract_db2_program` had been hardcoded to the literal
   `"DSNTEP2"` in the `RUN PROGRAM(...)` command all along, with no way
   to override it independently of `zos_extract_db2_plan` -- fixed by
   adding it as a real variable (defaulting to `"DSNTEP2"`, preserving
   prior behavior). Considered switching to `DSNTIAD` (IBM's other
   sample dynamic-SQL batch program) as an alternative first, but
   researched it against IBM's own documentation before implementing
   anything and found it **cannot run `SELECT` statements at all**
   (`UPDATE`/`INSERT`/`DELETE`/`CREATE`/`GRANT`/`LABEL ON` only) -- since
   every query this domain runs is a `SELECT`, DSNTIAD would have just
   traded one failure for a different, predictable one. Dropped that
   path; documented the finding in both the task file and
   `defaults/main.yml` so it isn't tried again.
4. The user supplied this site's real, separately-bound program/plan
   name (`DSNTEP13`) to test with, then immediately after asked to go
   back to real `DSNTEP2` with one more real STEPLIB DSN
   (`DSND10.DBDG.RUNLIB.LOAD`, this site's own RUNLIB, where its real
   bound `DSNTEP2` copy actually lives) -- a **third** STEPLIB DSN,
   proving the just-added two-fixed-slot design (`zos_extract_db2_steplib`/
   `zos_extract_db2_steplib2`) was already too narrow. Rather than add a
   third slot (and risk needing a fourth later), converted
   `zos_extract_db2_steplib` to a real list and rebuilt the `dd_concat`
   `dds` entries via a task-level `loop:`-based `set_fact` (confirmed
   ansible-core's native Jinja templating here doesn't support list
   comprehensions at all -- tested one directly, got "expected token
   ',', got 'for'" -- so a `loop:` task, not a Jinja `map`/comprehension
   chain, is the supported way to build a list of dicts from a list of
   scalars). Verified the rendered DD list for zero/one/three STEPLIB
   DSNs via standalone test playbooks. DSNTEP2 itself is still
   unconfirmed against a real run with all of the above in place --
   that's the next step.
5. With `DSN`/`RUN` and STEPLIB both correct (real program/plan
   `DSNTEP2`/`DSNTEP13`), the run got past TSO/DB2-connection entirely
   and DSNTEP2 itself started -- then abended `USER ABEND CODE 4038
   REASON CODE 00000001`, with `SYSPRINT` still 0 bytes. Researched this
   against IBM's own documentation (not guessed) and found the exact
   documented cause: DSNTEP2 requires its `SYSPRINT` DD to have
   `LRECL=133`, or it abends exactly `U4038` reason code 1 (a PL/I
   `IBM0201S ONCODE=81` file-attribute-mismatch exception). Checked
   `zos_mvs_raw`'s own `dd_output` schema (`ibm_zos_core`'s module
   source) and confirmed it has no `record_format`/`record_length`
   suboptions whatsoever -- structurally impossible to set `LRECL=133`
   through `dd_output`, so `SYSPRINT` had to become a real `dd_data_set`
   instead (`record_format=fba`/`record_length=133`, new configurable
   `zos_extract_db2_sysprint_primary`/`_secondary`, default 10/10
   tracks), one per query since two `zos_mvs_raw` invocations can't both
   `disposition=new` the same data set name, fetched back via
   `zos_fetch` into a scratch dir (new `zos_extract_db2_workhlq`, same
   idiom as `zos_extract_smpe_workhlq`) and read with `lookup('file',
   ...)` once cleaned up -- simpler than `_smplist_zone.yml`'s
   scratch-dir/local-`cat` streaming approach since a DB2 catalog listing
   isn't expected to be anywhere near SMPLIST's confirmed ~15M-line
   scale. Verified the rendered DD list via a standalone test playbook
   before committing -- though that verification used the dataset name
   `TOMMY.DB2CAT.SYSPACKAGE`, which the very next real run proved invalid
   (see item 6): the standalone test confirmed the Jinja *rendered*
   correctly, not that the resulting dataset name was itself valid.
6. That dataset name was rejected outright: `ValueError('Invalid argument
   "TOMMY.DB2CAT.SYSPACKAGE" for type "data_set".')`. Root cause: MVS
   dataset name qualifiers are capped at 8 characters, and `SYSPACKAGE`
   is 10 -- `SYSPLAN` (7 characters) happened to fit, so only the
   `SYSPACKAGE` query's `SYSPRINT` dataset hit this. Fixed by using
   `SYSPKG` (6 characters) as that query's real dataset qualifier instead
   -- the `##SYSPACKAGE` sentinel/parser-facing name and the real
   `SELECT ... FROM SYSIBM.SYSPACKAGE` SQL are both unaffected, only the
   temporary MVS dataset's own name changed. A reminder that "verified
   the Jinja renders correctly" and "verified the resulting value is
   itself a valid MVS name" are two different checks -- the standalone
   test playbooks used earlier in this round confirmed the former, not
   the latter.
7. With all five real fixes above in place, DSNTEP2 finally ran
   end-to-end and produced real `db2_catalog.txt` content -- but the
   real report *shape* was nothing like the original guess. The parser
   assumed one row per line (`NAME CREATOR BINDTIME` whitespace-split);
   the real DSNTEP2 report instead **transposes** the result set into one
   boxed column-section per column (`| NAME |`, then `| CREATOR |`, then
   `| BINDTIME |`, each spanning as many physical print pages as it
   needs -- SYSIBM.SYSPACKAGE's NAME column apparently prints wide enough
   that DSNTEP2 doesn't fit all three columns side by side at all), with
   only a shared row-number prefix (`479_|`) tying a value in one section
   back to the same logical row in another. Rewrote
   `db2_catalog_parser.py` from scratch around this real shape: each
   column section accumulates into its own `{row_number: value}` dict
   (immune to the same "section title reprints on every page" class of
   bug `_smplist_zone.yml`'s `LIST MOD` had, since there's no separate
   pending-state to reset here -- a page break splitting one column's
   section across pages just keeps writing into the same dict), then
   rows are reconstructed by `NAME`'s own row numbers once the whole
   block is read. Verified against both a hand-built fixture (including
   a mid-section page break, modeled on a real `"PAGE 28.1"` sub-page
   continuation) and a literal excerpt of the real report text pasted
   by the user. `Db2Package`/`Db2Plan` and their "most speculative
   domain" flags are updated to CONFIRMED throughout (`models.py`,
   `db2_catalog_parser.py`, `db2_catalog.yml`, `doc/ansible.md`,
   `doc/inventory.md`) -- DB2 catalog deepening is no longer the most
   speculative domain in the pipeline; CICS `DFHCSDUP` and WLM z/OSMF
   deepening remain the genuinely unconfirmed ones now.

**A real attempt at WLM z/OSMF deepening followed, against a real z/OSMF
instance (this site's `zdt3`, port `10443`):**
- `wlm_zosmf.yml` (the standalone playbook) previously only targeted
  hosts already in `inventory/hosts.yml`'s `zos` group -- but every real
  system this session has gone through `interactive.yml`'s one-off
  registration instead (no real `hosts.yml` here, only `.example`), so
  it couldn't reach `zdt3` at all. Fixed by merging `interactive.yml`'s
  own connection-detail `vars_prompt`/`add_host` tasks in alongside the
  z/OSMF credential prompts it already had.
- First real error: `Connection refused` -- `zos_extract_zosmf_port`
  defaults to `443`, this site's real z/OSMF port is `10443`. Not a code
  bug, just a real per-site value the user supplied via `-e`.
- Second real error: a clean `404` on the guessed
  `zos_extract_wlm_zosmf_path` (`/zosmf/wlm/policies`). Tried to confirm
  the real path against IBM's own z/OSMF REST API documentation first
  (not guess again blindly) -- IBM's doc pages consistently returned
  `403 Forbidden` to direct fetches, and web search results never
  surfaced the literal endpoint path either. Had the user check
  `/zosmf/info` (a real, stable, unauthenticated z/OSMF endpoint) first,
  which confirmed the `WorkloadManagement` plugin is genuinely `ACTIVE`
  on this system -- so a real REST API does exist, the path was just
  wrong. The user then found the real base path themselves via the
  z/OSMF web UI's own browser DevTools Network tab (the Workload
  Management task's actual REST call): `/zosmf/zwlm/rest`, not
  `/zosmf/wlm/...`. Updated `zos_extract_wlm_zosmf_path`'s default
  accordingly.
- **Dropped for this round, not because of a technical blocker**:
  connectivity, port, auth, and now the real base path are all solved,
  but the user found `/zosmf/zwlm` looks mostly action/write-oriented
  (starting/stopping resources, activating policies) rather than
  exposing a general `GET` for reading the active policy's full
  service-class/goal/resource-group definitions -- the actual thing this
  domain wants. Simply having the right base path may not be enough;
  the underlying data may not be reachable via a simple REST `GET` the
  way the original plan assumed. Documented in `wlm_zosmf.yml`'s own
  header comment and `zos_extract_wlm_zosmf_path`'s default-value
  comment for whoever picks this back up -- next step would be checking
  for a narrower real `GET` endpoint under `/zosmf/zwlm`, or accepting
  this data may need a non-REST transport entirely (e.g. WLM's own ISPF
  administrative application).

---

## 9. Broader active-PARMLIB-member capture (26 more IEASYSxx-named members)

**Context:** `ieasys_snapshot.txt`/`bpxprm_snapshot.txt` (this round)
established the pattern -- IEASYSxx's own keywords (`SSN=`, `CMD=`,
`PROD=`, `MSTRJCL=`, `OMVS=`, ...) each name an *active* PARMLIB member of
a specific type, and this pipeline can fetch+save+parse that member's
real content generically instead of treating IEASYSxx as just a
suffix-selector lookup table. The user asked for the same treatment
across 26 more (IEASYSxx keyword, member type) pairs:

```
AUTOR/AUTORxx     CATALOG/IGGCATxx  CLOCK/CLOCKxx     CMD/COMMNDxx
CON/CONSOLxx      COUPLE/COUPLxx    DEVSUP/DEVSUPxx   DIAG/DIAGxx
FIX/IEAFIXxx      GRSCNF/GRSCNFxx   GRSRNL/GRSRNLxx   IOS/IECIOSxx
IZU/IZUPRMxx      LPA/LPALSTxx      MLPA/IEALPAxx     MSTRJCL/MSTJCLxx
OPT/IEAOPTxx      PROG/PROGxx       PAK/IEAPAKxx      SMS/IGDSMSxx
SCH/SCHEDxx       SMF/SMFxx         SSN/IEFSSNxx      SVC/IEASVCxx
UNI/CUNIMGxx      VAL/VATLSTxx
```

**Before writing 23 more parsers, two things need to happen first** (this
section is that plan, not an implementation):

### 9.0. Three of these need *no new work at all*

- **SSN/IEFSSNxx** -- already fully ingested: `ssn_parser.parse_subsystems()`,
  `Subsystem` table, `inventory subsystems`.
- **CMD/COMMNDxx** -- already fully ingested: `ssn_parser.parse_started_tasks()`,
  `StartedTask` table, `inventory started-tasks`.
- **MSTRJCL/MSTJCLxx** -- this member's content *is* real JCL (the master
  scheduler's own startup JCL), not KEYWORD=value/statement config like
  the other 25. It's already captured generically once PARMLIB's full
  member dump runs (`proclib.yml`, tag `proclib`, `.*` member regex) and
  parsed by the existing `jcl_parser`/lineage pipeline -- no new parser
  needed, just confirm `inventory lineage MSTJCLxx` (or whatever suffix)
  shows real steps once that tag has been run. `discover_mstrjcl_proclibs.yml`
  already separately extracts this member's own PROCLIB-concatenation
  additions.

That leaves 23.

### 9.1. Architectural change needed before scaling past 2 more of these -- IMPLEMENTED

**Python side:** `parmlib_engines.py` now holds `flat_keyword_engine()`
(IEASYSxx's shape) and `statement_engine()` (BPXPRMxx's shape), plus the
shared `split_params()`/`strip_comments()` primitives underneath both
(also now the single source `jes2parm_parser.py` imports, instead of its
own copy-pasted `_split_params` -- `ieasys_parser.py` had drifted into an
actual duplicate of that same function despite its own docstring
claiming to "reuse" it). `ieasys_parser.py`/`bpxprm_parser.py` were
refactored to call these engines with zero behavior change (full test
suite, including a new `tests/test_parmlib_engines.py` exercising the
engines directly, stays green).

**Ansible side:** the former `_fetch_active_ieasys_member.yml`/
`_fetch_active_bpxprm_member.yml` (two hand-written, near-identical
files) are replaced by one generic `_fetch_active_parmlib_member.yml`,
parameterized by member prefix (`IEASYS`/`BPXPRM`/...) and driven by
Ansible's documented "templated variable name" `set_fact` idiom
(`set_fact: "{{ var_name }}": value`) so it can append into whichever
accumulator fact name its caller passes in, instead of each domain
hand-writing its own copy of the same fetch-and-accumulate logic.
`discover_active_members.yml`'s two loops now call this generic worker
via `vars:` instead of the two retired per-domain files.

**NOT YET RUN against a real system in this generalized form.** Both
predecessor files were individually confirmed working against this
site's real IEASYSxx/BPXPRMxx members; this rewrite preserves their
logic task-for-task and passed `ansible-playbook --syntax-check` plus an
isolated Jinja2 check of the `vars[name]` accumulator-read pattern used,
but that only confirms it parses and that the indirection technique
itself works in principle -- not that it behaves correctly end-to-end
against a real PARMLIB concatenation. **Confirm the next real-system run
produces byte-identical `ieasys_snapshot.txt`/`bpxprm_snapshot.txt`
output to before this change** before trusting this worker for a new
Category B/C domain.

`bpxprm_parser.py`'s own statement-parsing output (independent of the
ansible worker above) is now further CONFIRMED against a real BPXPRMxx
member with two real edge cases the original hand-picked sample never
exercised: a fully commented-out `MOUNT` block (every physical line its
own `/* ... */` comment) correctly disappears entirely rather than
becoming a bogus statement, and multiple `MOUNT` statements in the same
member are all kept, in order, rather than the last one silently
overwriting the others.

`ieasys_snapshot`/`bpxprm_snapshot` each got their own hand-written
ansible task file pair (`_fetch_active_*_member.yml` + `*_snapshot.yml`)
and their own hand-written Python parser. That was the right call for
*two* domains (each genuinely needed its own review), but copy-pasting
this 23 more times would be a real maintenance burden and error-prone
(the `ieasys_snapshot` tag-propagation bug just fixed is exactly the kind
of mistake that gets repeated at scale). Two refactors should land first:

**Ansible: one parameterized fetch worker instead of N near-duplicates.**
Replace `_fetch_active_ieasys_member.yml`/`_fetch_active_bpxprm_member.yml`
with a single `_fetch_active_parmlib_member.yml` parameterized by
`zos_extract_active_member_prefix` (e.g. `"SCHED"`), a suffix (from the
loop), and an accumulator fact name (via Ansible's dict-literal
`set_fact: "{{ {accumulator_name: ...} }}"` / `vars[accumulator_name]`
indirection). Driven by one data table (list of `{ieasys_keyword,
member_prefix, outfile, tag}` entries) in `defaults/main.yml`, with a
single generic task in `discover_active_members.yml` that loops the table
twice: once to extract every `zos_extract_active_<keyword>_suffixes` list
generically (replacing the current copy-pasted `SSN@@@`/`CMD@@@`/
`PROD@@@`/`OMVS@@@`/`MSTRJCL@@@` blocks with one loop), once to fetch+
accumulate+write each member type. `main.yml`'s tag wiring becomes a loop
too (one `include_tasks` per table row) instead of one hand-written
import block per domain -- and critically, *every* row automatically gets
its tag added to `discover_parmlib.yml`/`discover_active_parmlib_
suffixes.yml`/`discover_active_members.yml`'s tag lists from the same
table, so the "forgot to add the tag to the prerequisite" bug class
becomes structurally impossible instead of a thing to remember 23 times.

**Python: two shared parsing engines, not 23 copy-pasted ones.** Group the
23 by real shape (see 9.2 below) and extract each shape's logic into one
reusable function each domain's thin parser module calls:
- `_flat_keyword_engine(text) -> dict[str, str|None]` -- generalizes
  `ieasys_parser.py`'s comma-split logic (IEASYSxx's own shape).
- `_statement_engine(text, keywords: set[str]) -> list[(stmt, operands)]`
  -- generalizes `bpxprm_parser.py`'s (itself modeled on
  `tcpip_parser.py`'s PROFILE.TCPIP logic) fold-into-current-statement
  approach, parameterized by each member type's own keyword vocabulary.
- Category D (below) reuses `jes2parm_parser.py`'s existing
  `_split_params`/`_join_continuations` as-is; it's already generic.
- Category E (below) needs small dedicated parsers -- genuinely
  different shapes, not worth forcing into either engine above.

Each of the 23 still gets its own `dataclass` (in `models.py`), its own
`store.py` table, and its own `inventory <name>` command -- only the
*parsing mechanics* are shared, not the domains' identities. This mirrors
how `Jes2InitStatement`/`VtamStartOption`/`CicsSitOverride` already share
one *idea* ("generic KEYWORD capture") without sharing one *class*.

### 9.2. The 23, categorized by real syntax shape

**B -- flat `KEYWORD=value`, comma-continued (reuse the IEASYSxx engine):**
- `DEVSUP`/`DEVSUPxx` -- IMPLEMENTED and CONFIRMED against a real
  DEVSUPxx member: `DevsupStatement`/`devsup_parser.py` (a thin wrapper
  around `parmlib_engines.flat_keyword_engine()`), `devsup_statements`
  table, `inventory devsup` command, `devsup_snapshot.yml` (built on the
  generalized `_fetch_active_parmlib_member.yml` worker from "9.1" --
  the first domain to actually exercise it). One wrinkle the real member
  exercised that IEASYSxx's own confirmed sample never did: a keyword
  can take a parenthesized value with no `=` at all (e.g.
  `DISABLE(SSR)`) -- `parmlib_engines.split_params()` now handles this
  explicitly instead of swallowing the whole `KEYWORD(value)` token as
  one bare keyword name.
- `OPT`/`IEAOPTxx` -- IMPLEMENTED and CONFIRMED against a real IEAOPTxx
  member (`ERV=500`): `OptStatement`/`opt_parser.py`, `opt_statements`
  table, `inventory opt` command, `opt_snapshot.yml`.
- `CLOCK`/`CLOCKxx` was originally grouped in here too, on the assumption
  it shared IEASYSxx's comma-separated shape -- **CONFIRMED WRONG**
  against a real CLOCKxx member; moved to Category G below, its own
  space-separated shape, and `clock_parser.py` fixed accordingly.
  Category B (DEVSUP/OPT) is now fully confirmed against real members;
  IEASYSxx/BPXPRMxx's own output still just needs the byte-identical
  regression check "9.1" already calls for on the ansible-worker
  generalization itself.

**G -- space-separated `KEYWORD value`, no `=`/commas/continuation char,
small known vocabulary (own small parser, not either engine above):**
- `CLOCK`/`CLOCKxx` -- IMPLEMENTED and CONFIRMED against a real CLOCKxx
  member (e.g. `OPERATOR NOPROMPT`, `TIMEZONE W.05.00.00`, `ETRMODE  NO`,
  `ETRZONE  NO`, `ETRDELTA 1`, `STPMODE  NO`): `ClockStatement`/
  `clock_parser.py` (its own small line-splitter, not
  `parmlib_engines.flat_keyword_engine()`), `clock_statements` table,
  `inventory clock` command, `clock_snapshot.yml` (the ansible-side fetch
  via `_fetch_active_parmlib_member.yml` is unaffected -- only the
  Python-side parsing differs from the original Category B assumption).

**C -- statement-oriented `STMT KEYWORD(value)...`, multi-line, no
continuation char (reuse the BPXPRMxx engine, one keyword vocabulary per
domain):**
- `AUTOR`/`AUTORxx` -- IMPLEMENTED and CONFIRMED against a real AUTORxx
  member: `AutorStatement`/`autor_parser.py`, `autor_statements` table,
  `inventory autor` command, `autor_snapshot.yml`. WTOR auto-reply
  policy -- `NOTIFYMSGS(...)` and `MSGID(msgid) DELAY(nnS) REPLY(text)`/
  `NOAUTORREPLY` statements defining automatic operator replies to
  specific WTORs; the top-level statement vocabulary is confirmed via
  IBM's z/OS MVS Initialization and Tuning Reference -- **not** Automatic
  Restart Management policy, an earlier draft of this plan mislabeled it.
  The real member exercised a multi-line `/* ... */` comment block
  preceding a live statement (stripped cleanly) and a `MSGID` statement
  with its full operand list on one physical line rather than spread
  across continuation lines -- both handled correctly by
  `parmlib_engines.statement_engine()` already.
- `SCH`/`SCHEDxx` -- IMPLEMENTED and CONFIRMED against a real SCHEDxx
  member: `SchedStatement`/`sched_parser.py` (PPT entries, one keyword
  vocabulary `{"PPT"}`), `sched_statements` table, `inventory sched`
  command, `sched_snapshot.yml`. The `PPT PGMNAME(name) flag flag KEY(n)
  ...` statement shape is confirmed against real-world PPT examples, and
  the real member exercised a run of entries where every physical line
  (statement line and every continuation line alike) carries its own
  trailing `/* ... */` comment -- stripped cleanly by
  `parmlib_engines.statement_engine()` without bleeding into the next
  PPT entry.
- `COUPLE`/`COUPLExx` -- IMPLEMENTED and CONFIRMED against a real
  COUPLExx member: `CoupleStatement`/`couple_parser.py` (statement
  vocabulary `{"COUPLE", "DATA"}`), `couple_statements` table,
  `inventory couple` command, `couple_snapshot.yml`. **Real member name
  is `COUPLExx` (e.g. `COUPLE00`), not `COUPLxx`** as this table
  originally had it above -- corrected after checking a real IBM source;
  unlike `MSTRJCL=` (which drops its `R`), `COUPLE=` keeps its full name
  in the member suffix. The real member exercised one `COUPLE` statement
  followed by four distinct `DATA TYPE(...)` statements (`CFRM`, `LOGR`,
  `BPXMCDS`, `WLM`), all correctly kept in order rather than collapsed
  by `parmlib_engines.statement_engine()`.
- `GRSRNL`/`GRSRNLxx` -- IMPLEMENTED and CONFIRMED against a real
  (partial) GRSRNLxx member: `GrsrnlStatement`/`grsrnl_parser.py`
  (RNLDEF statements, one keyword vocabulary `{"RNLDEF"}`),
  `grsrnl_statements` table, `inventory grsrnl` command,
  `grsrnl_snapshot.yml`. The real member exercised a shape not in the
  original documented sample: `QNAME(...)`/`RNAME(...)` each on their
  own continuation line rather than sharing the `RNLDEF` line, with
  blank lines separating entries -- both handled correctly by
  `parmlib_engines.statement_engine()` already.
- `SMF`/`SMFPRMxx` -- IMPLEMENTED and CONFIRMED against a real SMFPRMxx
  member: `SmfStatement`/`smf_parser.py`, `smf_statements` table,
  `inventory smf` command, `smf_snapshot.yml`. Statement vocabulary is
  now `ACTIVE`, `DSNAME`, `PROMPT`, `NOPROMPT`, `SYS`, `SUBSYS`, plus
  `REC`, `MAXDORM`, `STATUS`, `JWT`, `SID`, `LISTDSN`, `INTVAL`,
  `SYNCVAL`, `AUTHSETSMF` -- the last nine were missing from the
  original **partial** vocabulary and got silently folded into
  `NOPROMPT`'s operands until the real member exercised them; broaden
  `_SMF_STATEMENT_KEYWORDS` further if a future real member exercises
  one not yet in this set (SMFPRMxx's full documented keyword surface
  may still be larger). **Real member name is `SMFPRMxx` (e.g.
  `SMFPRM00`), not `SMFxx`** as this table originally had it -- another
  naming error like `COUPLE=`'s, corrected after checking a real IBM
  source.
- `IOS`/`IECIOSxx` -- IMPLEMENTED: `IosStatement`/`ios_parser.py`
  (statement vocabulary `MIH`, `HOTIO`, `TERMINAL`, `FICON`, `STORAGE`,
  `CAPTUCB`, `EKM`, `RECOVERY`, `CTRACE`, `MIDAW`, `HYPERPAV`,
  `HYPERWRITE`, `ZHPF`), `ios_statements` table, `inventory ios`
  command, `ios_snapshot.yml`. Checked against this site's real system:
  IEASYSxx's own `IOS=` keyword is genuinely not set here (no active
  IECIOSxx member at all -- not a bug, this site just doesn't configure
  one), so `ios_snapshot.yml` correctly produces empty output. That
  confirms the "no member found" path, but the actual statement-parsing
  regexes (`MIH`/`HOTIO`/etc.) still have no real IECIOSxx content to
  check against at this site -- still NOT YET VALIDATED for the
  statement content itself; would need a different site/system that
  does configure `IOS=` to confirm that part. Skipped for this round
  per the user's own call.
- `CON`/`CONSOLxx` -- IMPLEMENTED and CONFIRMED against a real CONSOLxx
  member: `ConsolStatement`/`consol_parser.py`, `consol_statements`
  table, `inventory consol` command, `consol_snapshot.yml`. Statement
  vocabulary is `INIT`, `DEFAULT`, `CONSOLE`, `HARDCOPY` -- the real
  member exercised multiple `CONSOLE` statements (one per device),
  a `CONSOLE` statement whose first keyword(s) shared the `CONSOLE`
  line itself rather than starting on a continuation line, and an
  `INIT` statement whose `CMDDELIM(")` value is itself a literal quote
  character inside the parens -- all handled correctly by
  `parmlib_engines.statement_engine()` with no code change needed.
  CONSOLxx's full documented statement surface may still be larger
  (e.g. `ALTGRP`, `CNGRP`, `MSCOPE`, `SPECIAL`); broaden
  `_CONSOL_STATEMENT_KEYWORDS` if a future real member exercises one
  not yet in this set.
- `SMS`/`IGDSMSxx` -- IMPLEMENTED and CONFIRMED against a real IGDSMSxx
  member: `IgdsmsStatement`/`igdsms_parser.py`, `igdsms_statements`
  table, `inventory igdsms` command, `igdsms_snapshot.yml`. One-keyword
  vocabulary (`{"SMS"}`), the real member's single `SMS ACDS(...)
  COMMDS(...) INTERVAL(...) ...` statement spanning 13 continuation
  lines, all folded correctly with no code change needed.
  **Naming collision avoided, not just watched**: this project already
  has an unrelated `sms` tag/`SmsStorageGroup` table for the *live* `D
  SMS,STORGRP` console command -- confirmed this would have been a real
  bug, not just a cosmetic one: the live domain's ingest glob was
  `*sms*.txt`, which would have also matched `igdsms_snapshot.txt`
  (contains `sms` as a substring) and fed it to `sms_parser.parse_sms()`
  by mistake. Fixed by excluding `*igdsms*` matches from that glob, the
  same precedent `*wlm*`/`*wlm_zosmf*` already established. Every other
  new name (`IgdsmsStatement`, `igdsms_parser.py`, `igdsms_statements`,
  `inventory igdsms`, tag `igdsms_snapshot`) uses `igdsms`, not `sms`,
  throughout.
- `DIAG`/`DIAGxx` -- IMPLEMENTED and CONFIRMED against a real DIAG00
  member: `DiagStatement`/`diag_parser.py` (one-keyword vocabulary
  `{"VSM"}`, e.g. `VSM TRACK CSA(ON) SQA(ON)`, `VSM TRACE
  GETFREE(OFF)`), `diag_statements` table, `inventory diag` command,
  `diag_snapshot.yml`. Tenth Category C domain from doc/TODO.md "9.2",
  and the first one whose confirming real member carried traditional
  PARMLIB sequence numbers in columns 73-80 of every physical line --
  since that trailing field sits on the *same* line as real statement
  content (not a separate comment line), `strip_comments()` alone
  wouldn't remove it; `diag_parser.py`'s own `_strip_sequence_numbers()`
  strips it before handing lines to `parmlib_engines.statement_engine()`.
- `CATALOG`/`IGGCATxx`, `GRSCNF`/`GRSCNFxx`, and `PROG`/`PROGxx`
  (**the richest and riskiest of these** -- LNKLST/APF/EXIT/LPA/SCHED are
  all distinct sub-statement types inside one PROGxx member; treat as its
  own careful pass, not a drive-by addition alongside the simpler ones)
  still to do. **`IGGCATxx`'s own exact statement vocabulary couldn't be
  confidently confirmed this round** (IBM's docs pages and known mirrors
  all 403'd on direct fetch, same recurring friction this project has
  hit before) -- needs a real member sample or a working docs fetch
  before implementing, not a guess.

**D -- `STMT param,KEYWORD=value,...` (reuse jes2parm_parser.py's engine
as-is):**
- `SVC`/`IEASVCxx` (`SVCPARM nnn,KEYWORD=value,...` -- note the leading
  `nnn` is a bare positional parameter, not a parenthesized subscript like
  JES2's own `JOBCLASS(1)`; `jes2parm_parser.py`'s `_STMT` regex needs a
  small extension to accept that shape, not a fresh rewrite)

**E -- positional/list formats, not KEYWORD=value at all (need their own
small dedicated parsers, closer to how `lnklst.txt`/`apf.txt` are
handled than any of the above):**
- `LPA`/`LPALSTxx` -- a dataset name list, same shape LNKLST already is
- `FIX`/`IEAFIXxx`, `MLPA`/`IEALPAxx` -- `modname,ddname` pairs, same
  shape as each other
- `VAL`/`VATLSTxx` -- volume attribute list (`PRIVATE`/`PUBLIC`/`STORAGE`
  + volser lists)

**F -- needs research before committing to *any* design, not just a
"not yet validated" flag like everything above:**
- `PAK`/`IEAPAKxx` -- RESOLVED, dropped from scope: user confirmed this
  isn't a real, current z/OS PARMLIB member -- effectively an IEFBR14 (a
  no-op), not something to design a parser for. No further work needed
  here; this leaves 1 domain in Category F, not 3.
- `UNI`/`CUNIMGxx` -- RESOLVED, dropped from scope: user confirmed
  Unicode conversion image tables aren't a concern for this site --
  not worth the doc research pass to pin down its statement syntax.
  This leaves Category F empty (both PAK/IEAPAKxx and UNI/CUNIMGxx
  dropped, IZU/IZUPRMxx implemented and confirmed below).
- `IZU`/`IZUPRMxx` (z/OSMF configuration) -- IMPLEMENTED and CONFIRMED
  against a real IZUPRM00 member, and turned out to be a much better fit
  for Category C's `parmlib_engines.statement_engine()` than the
  "likely more elaborate/nested" worry this entry originally carried:
  `IzuprmStatement`/`izuprm_parser.py`, `izuprm_statements` table,
  `inventory izuprm` command, `izuprm_snapshot.yml`. Statement vocabulary
  (HOSTNAME, HTTP_SSL_PORT, INCIDENT_LOG, JAVA_HOME, KEYRING_NAME,
  LOGGING, RESTAPI_FILE, COMMON_TSO, SAF_PREFIX, CLOUD_SAF_PREFIX,
  CLOUD_SEC_ADMIN, SEC_GROUPS, SESSION_EXPIRE, TEMP_DIR, CSRF_SWITCH,
  SERVER_PROC, ANGEL_PROC, AUTOSTART, AUTOSTART_GROUP, USER_DIR,
  UNAUTH_USER, WLM_CLASSES, PLUGINS) is confirmed against a real member
  but is one shop's actual content, not IBM's full documented surface --
  broaden it if a future member exercises more. The real member
  exercised two shapes no earlier Category C domain had: a single-quoted
  value spanning two physical lines (`LOGGING('...=\nfiner')`, per the
  member's own documented rule that a quoted value may continue on the
  next physical line, closing quote and all) and a repeated top-level
  statement keyword (`CSRF_SWITCH` appeared twice, `ON` then `OFF` --
  both kept in order, not collapsed, same precedent COUPLExx's repeated
  `DATA` statements already set) -- both handled correctly by
  `statement_engine()` with no code change needed. This leaves Category
  F empty -- see UNI/CUNIMGxx above.

### 9.3. Suggested sequencing

1. The two refactors in 9.1 (parameterized ansible worker + shared Python
   engines) -- do this before adding a third hand-written domain, not
   after the fifth.
2. Category B (2 domains, DEVSUP/OPT) plus Category G (1 domain, CLOCK,
   its own small parser but no new engine) -- cheapest, most mechanical
   once 9.1 lands.
3. Category E (4 domains) -- simple positional formats, no engine
   dependency, can happen in parallel with B/G.
4. Category C minus PROG/IGDSMS (8 domains) -- mechanical once the
   statement engine exists.
5. Category D (1 domain, SVC) -- needs the small `jes2parm_parser.py`
   extension first.
6. `PROG` on its own, given its complexity (`IGDSMS` implemented and
   confirmed).
7. Category F -- now empty (`PAK`/`IEAPAKxx` and `UNI`/`CUNIMGxx` both
   dropped as out of scope, `IZU`/`IZUPRMxx` implemented and
   confirmed).

Each domain still needs: model + parser + `store.py` table + `cli.py`
command + fixture + tests + doc updates (`zos-extract.md`/`ansible.md`/
`inventory.md`), same as `ieasys`/`bpxprm` this round -- 9.1's refactor
only removes the *ansible* and *parsing-engine* duplication, not this
per-domain wiring, which is inherently one-per-domain.

---

## 10. CICS resource discovery via CMCI -- IN PROGRESS (design decided, implementation partial)

**Context:** `cics_deepening.yml`'s DFHCSDUP-based CSD reading
(`CicsCsdDefinition`/`cics_csdup_parser.py`) is this pipeline's most
speculative parser alongside DB2/WLM-z/OSMF, and only works at all for
sites with no CMCI/CICSplex SM. The user clarified not every system they
inventory lacks CMCI -- some do have it -- so CMCI is a genuinely better
alternative *for those specific systems*, not a replacement for
DFHCSDUP (which stays as the only option for CMCI-less regions).

**Real judgment calls resolved with the user before implementing:**
- **Topology**: standalone regions (SMSS), not full CICSplex SM -- `context`
  in every CMCI call is a CICS region's own APPLID, not a CICSplex name.
- **Resource types**: both CSD-sourced *definitions*
  (`cicsdefinitionprogram`/`cicsdefinitiontransaction`/`cicsdefinitionfile`,
  matching `cics_deepening.yml`'s existing scope) AND the
  currently-installed/active equivalents (`CICSProgram`/`CICSTransaction`/
  `CICSLocalFile`, a live snapshot like `cics.yml`/`db2.yml`) -- six
  resource-type queries total, per configured CMCI target.

**Mechanism**: `ibm.ibm_zos_cics`'s `cmci_get` module -- already installed
*and* already pinned in `ansible/requirements.yml` with a comment
anticipating exactly this ("pinned for future CMCI-based CICS resource
discovery ... if this site ever enables CICSplex SM"). Confirmed (reading
the module's own source/docs) that `cmci_get` already parses CMCI's XML
wire format into clean per-record Python dicts (`records`) -- unlike
every other REST-based domain here (`wlm_zosmf.yml`'s hand-rolled
`ansible.builtin.uri` call), there's no report/response-format guessing
needed at all for the mechanics, only for which attribute key holds each
resource type's own "name" (see below). `context`/`resources.filter`/
`get_parameters` shapes are all confirmed against `cmci_get`'s own
module documentation examples (real, not guessed).

**File format decided**: `cics_cmci.txt` as JSON Lines -- one line per
(context, resource_type) query result, e.g. `{"context": "CICSA",
"resource_type": "cicsdefinitionprogram", "records": [...]}`. This is
this pipeline's *own* file format (not an external API response saved
verbatim), so there's no schema uncertainty on the file-parsing side
either -- a first for any REST-based domain in this codebase.

**Done so far:**
- `models.py`: `CmciResource` (`resource_type`, `context`, `name`,
  `attributes` -- maximally generic like `WlmZosmfEntry`, full raw
  per-record dict preserved, since CMCI's real attribute set varies by
  resource type/CICS version and isn't worth guessing at typed fields
  for).
- `cmci_parser.py`: `parse_cmci()`, a straightforward JSON-Lines reader
  (no report-format guessing, per above) plus `_resource_name()`, which
  tries several candidate primary-identifier keys across all six
  resource types (`name`/`program`/`tranid`/`transid`/`file`/`dsname`) --
  `name` is confirmed via `cmci_get`'s own docs for the CSD-definition
  types; the installed-resource types' candidate keys are partly
  confirmed (`program`, from `cmci_get`'s own `CICSProgram` RETURN
  sample) and partly inferred, not independently confirmed. Falls back
  to `"?"` if nothing matches, same precedent as
  `wlm_zosmf_parser.py`'s `_entry_name()`.
- Both verified importable and the full existing test suite still
  passes (312 tests) -- but **no dedicated fixture/tests for
  `cmci_parser.py` itself yet**.

**Still to do (stopped here, not yet implemented):**
- `ansible/roles/zos_extract/tasks/cics_cmci.yml`: loop over configured
  CMCI targets × the six resource types (Jinja's `product` filter, not
  yet confirmed available/working in this ansible-core's native
  templating -- verify before relying on it, same caution list
  comprehensions needed earlier this session), call `cmci_get` with
  `fail_on_nodata: false` (cmci_get's own default, `true`, would crash
  the whole task on a legitimately-empty resource type -- same class of
  bug already found and fixed twice this round for `db2.yml`/`cics.yml`),
  build the JSON-Lines accumulator via a task-level `loop:`-based
  `set_fact` (same idiom `db2_catalog.yml`'s STEPLIB-list fix uses, not
  a Jinja comprehension), and write the file guarding against the
  empty-content `ansible.builtin.copy` crash (`~ '\n'` suffix, same fix
  already applied to `db2.yml`/`cics.yml`).
- Still need to confirm whether `cmci_get` should run
  `delegate_to: localhost` (like `wlm_zosmf.yml`'s REST call) rather than
  executing on the target z/OS system's own Python interpreter -- its
  module_utils imports `urllib`/`http.client` (stdlib only, not
  `requests`), which should work either way, but delegating to localhost
  avoids any dependency on the z/OS Unix System Services Python
  environment having networking configured for outbound HTTPS, and
  matches this pipeline's existing precedent of running REST calls from
  the control node. Not yet confirmed either way.
- `ansible/roles/zos_extract/defaults/main.yml`: `zos_extract_cics_cmci_targets`
  (list of `{host, port, context}`, default `[]`, opt-in),
  `zos_extract_cmci_username`/`_password` (default `""`, runtime-prompted,
  same idiom as `zos_extract_zosmf_username`/`_password`),
  `zos_extract_cics_cmci_scheme` (default `"https"`),
  `zos_extract_cics_cmci_insecure` (default `true`, same self-signed-cert
  tradeoff as `zos_extract_zosmf_validate_certs`), `zos_extract_cics_cmci_outfile`
  (default `"cics_cmci.txt"`).
- `ansible/roles/zos_extract/tasks/main.yml`: wire in, tag `cics_cmci`,
  gated `never` (needs runtime-prompted credentials, same convention as
  `racf.yml`/`wlm_zosmf.yml`) and
  `zos_extract_cics_cmci_targets | length > 0`.
- `playbooks/cics_cmci.yml`: new standalone entry point, merging
  connection-detail prompts (same `vars_prompt`/`add_host` idiom
  `interactive.yml` uses) with `zos_extract_cmci_username`/`_password`
  prompts -- mirror `playbooks/wlm_zosmf.yml`'s now-fixed merged
  structure exactly (that playbook originally only worked for hosts
  already in `inventory/hosts.yml`; don't repeat that mistake here).
- `store.py`: `cmci_resources` table, `save_cmci_resources`/
  `all_cmci_resources`.
- `cli.py`: glob `*cics_cmci*.txt` in `cmd_ingest` (no collision with the
  existing `*cics_deepening*.txt` glob or the unglobbed `cics.txt`),
  new `inventory cmci` command.
- `tests/test_cmci_parser.py` + a hand-built JSON-Lines fixture
  (including a legitimately-empty resource type, to exercise the
  `fail_on_nodata: false` behavior downstream, and a malformed/truncated
  trailing line to exercise the "skip invalid lines" tolerance).
- Docs: `README.md`, `doc/ansible.md`, `doc/inventory.md` (new sections),
  same as every other domain.
- Real-system validation once implemented: whether CMCI genuinely
  returns every CSD group's definitions with no `csdgroup` filter (no
  `get_parameters` passed for the CSD-definition queries currently
  planned) or requires one -- flagged for confirmation, not guessed.
