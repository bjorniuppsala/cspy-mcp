# Open items

Planned improvements to the MCP server and the `iar_cspy` API under it, with a
focus on making them easier and safer for AI agents to use.
The `iar_cspy` API lives in https://github.com/iarsystems/cspy-py; items that
need API or backend work are tracked in its TODO.md as well.

## Status Legend
- [ ] Not started
- [~] In progress
- [x] Done

## Done: the first roadmap (items 1-12)

A happy-path configure-and-start tool, a status tool, the response envelope,
idempotent stop/ensure, first-class tools for common `debugger_call` uses,
wait tools, the error taxonomy, backend diagnostics on failures, capability
discovery, the playbooks, a self-contained live test harness, and the strict
cleanup tool.

## Feedback from AI black-box usability test (2026-08-10, J-Link + sim on live E31 Arty)

The whole session was driven without reading the MCP source. What worked well:
the happy-path configure-and-start tool, the error envelopes (specific enough to
recover from every failure), managed-mode auto-restart after backend crashes,
and libsupport stdout capture working without any plugin configuration.

New items, roughly in priority order:

13. [~] Document the launch_json schema on the tool surface
- `debugger_configure_and_start_session` / `debugger_configure_session` accept a
  `launch_json` string but nothing describes its shape. The agent had to learn it
  from a stray example file plus the backend error "Missing JSON member: name".
- It is a *single* configuration object (one entry of a C-SPY VS Code
  launch.json), NOT the `{"configurations":[...]}` wrapper. Either accept both
  forms or state this clearly.
- Include a minimal working example (sim and one hardware driver) in the tool
  docstring or a schema-discovery tool.
- The IAR tooling already ships a formal launch.json schema (used by the
  VS Code debug extension). Reference or embed it.
- Done: the configure tools' descriptions now show the shape and a minimal
  simulator example, and a whole launch.json (`configurations` wrapper) is
  accepted, using its first entry. Still open: a hardware example and a
  reference to the extension's formal schema.

14. [~] Breakpoint tools are effectively sim-only against emulator drivers
- `breakpoints_set_on_source`/`_set_code`/`_set_data`/`_set_log` set
  breakpoints from descriptors with the driver's category (iar-cspy's
  `add_*`), as the VS Code extension does. Open: verify on emulator drivers.
- Root cause is two known backend bugs in breakpoint category handling
  (default categories only cover STD_CODE*/STD_DATA*; explicit category ids
  outside the backend translation map are silently dropped, so even the
  correct `EMUL_CODE` fails). Backend fixes are tracked separately, but until
  they land:
- The breakpoint tool errors should mention the working alternatives:
  `debugger_call runToULE ["<ule>"]`, or eval `__setCodeBreak("main", 0, "1",
  "TRUE", "")`. Consider first-class `debugger_run_to_ule` and a macro-based
  breakpoint fallback tool.

15. [~] Clarify the access_type enum
- Docstring says 1 = execute/fetch, but created breakpoints report
  `accessType: 0` and the sim accepts both 0 and 1.
- Verified: `shared.AccessType` is 1-4 (1 = kDkFetchAccess), and a fetch
  breakpoint on the Cortex-M3 simulator reads back `accessType=0`. The docs
  now say to pass 1-4 and not to rely on the value read back
  (docs/backend-notes.md). Open: whether 0 is a backend bug, and what emulator
  drivers report.

16. [ ] Fix cycle counter signedness
- `debugger_get_cycle_counter` returned -821365371 on hardware (i32 truncation
  of the 64-bit CYCLECOUNTER). Return unsigned 64-bit.

17. [~] Surface the known stopSession backend crash better
- Every `stopSession` in `-standalone -sockets` mode hits a known backend
  assertion and aborts the process; managed mode recovers but the error
  payload embeds the same ~30-line stack trace twice (~30 KB).
  Deduplicate/truncate, and tag it as a known backend issue with
  "retry configure_and_start once" as the recovery hint.
- Managed mode no longer calls `stopSession`: `iar_cspy` ends the session
  with `Debugger.exit()`, as cspy.thrift prescribes and the VS Code
  extension does. Open: the standalone-mode path, and whether the assertion
  still occurs (not reproduced with EWARM 10.10).

18. [x] Implement stopOnSymbol in the MCP server (it is a frontend contract)
- With `stopOnSymbol: "main"` the session halts at `__iar_program_start`.
  Verified on both sim and J-Link: generic, not driver-specific.
- Root cause: CSpyServer2.startSession() never reads stopOnSymbol; it is the
  *frontend's* job to run to the symbol after start (both the IAR IDE and the
  VS Code DAP adapter do this). The MCP server is the frontend in this flow,
  so configure-and-start should call runToULE(stopOnSymbol) after start when
  the field is non-empty.
- Fixed: `debugger_configure_and_start_session` now calls
  `runToULE(stopOnSymbol, True)` after start when the field is present, and
  reports the outcome via `stopOnSymbol`/`ranToSymbol`/`stopOnSymbolError` in
  the response. Verified on a Cortex-M3 Simulator session.
- `runToULE` returns before the target has arrived, so `ranToSymbol` is now
  only reported once the target-stopped event has come in (see
  `Debugger.run_to` in iar_cspy).

19. [~] Add zone discovery
- `memory_read`/`memory_write_hex`/`disassemble_range` require a `zone_id` but
  there is no tool to list zones (agent guessed 0 = Memory, which worked).
  Promote `getAllZones` to a first-class tool or document common zone ids
  (incl. the CSR zone for RISC-V).
- Partly done: the Python API has `client.debugger.zones()`, and the
  `memory_read` description points at `debugger_call("getAllZones")`. No
  first-class MCP tool yet.

20. [x] Document core state values
- Wait tools say "for example halted=0" but there is no enum reference.
  A one-line table (0=halted, ...) in the docstrings would remove guesswork.
- Done: the core-state tools list 0 = stopped, 1 = running, 2 = sleeping,
  3 = unknown, 4 = no power; the API has `iar_cspy.CoreState`.

21. [ ] Host a headless `frontend` service
- Without an IDE, `getStack`, `getContextInfo`, source lookup and disassembly
  at the PC fail with "No such service, serviceName=frontend": the backend calls
  back into the IDE's UI service (`frontend.thrift`: message boxes, file
  dialogs). A stand-in hosted like the event handler would likely unblock them,
  but it has to answer the backend's prompts on the user's behalf, so decide
  on a policy first (e.g. default answer + log every prompt).

22. [x] C-RUN runtime-checking rules: list/add/edit/delete
- `crun_get_default_action`/`crun_set_default_action`/`crun_list_rules`/
  `crun_add_rule`/`crun_update_rule`/`crun_delete_rule`/`crun_load_filters`/
  `crun_save_filters`, over the new `client.crun` API in iar-cspy.
- `CRunBackend` (crun.thrift) only has add-rule (always `Log` action),
  load/saveFilters (bulk file replace/dump) and get/setDefaultAction - no
  list/update/delete RPC. `iar_cspy.crun` reconstructs those on a
  save->parse->mutate->write->load round trip against the on-disk filter XML
  format (reverse-engineered from `CrMessageFilter::Save`/`Load`, not
  guessed). This assumes the MCP server and the debug backend share a
  filesystem - true for the managed/local setup, not for a remote backend.
- Open: `CRunDisplay` (the push-only service presenting live runtime-check
  messages) is not built yet - it needs a hosted callback server like
  `debugger.eventhandler`, plus a local cache/`crun_get_messages`-style tool.
  Separate, larger piece of work.
- For now: against an IDE-hosted session, both the messages and the rules
  are already readable with the *existing* `listwindow_*` tools, no new code
  - confirmed live (2026-11-18) against a running iaride: `listwindow_get_rows`
  on window id `WIN_C_RUN_MESSAGES` ("C-RUN Messages") returns the live
  runtime-check hits (message, source file, PC, core, nested call-stack
  rows); `WIN_C_RUN_MESSAGE_RULES` ("C-RUN Message Rules") returns the rules
  read-only (Check/Source File/Action columns), a second way to list them
  alongside `crun_list_rules`. See `docs/crun.md`. This needs cspy-py's
  `feat/listwindow-snapshot` fix first (tracked in cspy-py's TODO.md) - until
  it lands, `listwindow_list_services`/`listwindow_get_rows` do not reach
  these ids against an iaride host (only against CSpyServer2, which registers
  one `ListWindowBackend` per window the old way).
