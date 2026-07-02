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
