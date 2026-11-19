# C-RUN: runtime-checking rules and messages

The `crun_*` tools talk to `CRunBackend` (`crun.thrift`), hosted by the debug
session (CSpyServer2) when a C-RUN-capable session is configured, or by
iaride directly. They require an active debug session, same as
`breakpoints_*`/`memory_*` (`require_session`).

## Setting up rules

`CRunBackend` only offers: add a rule (always created with the `LOG`
action), replace/dump the whole rule set from/to a file, and get/set the one
default (catch-all) rule's action — there is no list/update/delete RPC.
`crun_list_rules`/`crun_update_rule`/`crun_delete_rule` reconstruct those on
top of `crun_save_filters`/`crun_load_filters` (iar-cspy's `client.crun` does
the file round trip): write the rule set to a file, read it back, mutate one
entry in Python, write it back, load it. **This assumes the MCP server and
the debug backend share a filesystem** — true for the managed/local setup,
not for a backend on a different machine.

```
crun_list_rules()                                   → [{"index": 0, "message_pattern": "*", "is_default": true, "action": "STOP_AND_LOG", ...}]
crun_add_rule("AssertFailure")                       → index 0, action "LOG" (the backend's fixed default)
crun_add_rule("Division by zero", action="IGNORE")   → index 0, action "IGNORE" (one extra round trip to set it)
crun_update_rule(0, action="STOP_AND_LOG")           → edit by current index (shifts as rules are added/removed)
crun_delete_rule(0)
crun_get_default_action() / crun_set_default_action("LOG")
```

The default/catch-all rule (always the last index) always matches
everything: only its `action` can be changed (`crun_update_rule(index,
action=...)` or `crun_set_default_action`) — trying to rescope or delete it
fails with `error.code=CRUN_DEFAULT_RULE_RESTRICTED`. A bad index fails with
`CRUN_INVALID_RULE_INDEX`. No C-RUN-capable session configured fails with
`CRUN_NOT_INITIALIZED` (detected from the backend's message text — crun.thrift
declares no typed exception for it).

## Reading messages

`crun_get_messages()` returns the live runtime-check messages. `CRunBackend`
has no call to read them, so iar-cspy (`client.crun_messages`) hosts the
push-only `CRunDisplay` service, registers it as `crun.display` on first use,
and stores what the backend pushes, per namespace (the partner that sent
them; `""` for an IDE). Only messages pushed *after* registration are seen, so
call it before running the target. `crun_clear_messages([namespace])` forgets
them.

```
crun_get_messages()                 → {"receiving": true, "namespaces": ["core0"], "count": 2,
                                       "messages": [{"namespace": "core0", "name": "Division by zero",
                                                     "text": ..., "call_stack": [...], "sub_messages": [...]}]}
crun_get_messages(namespace="core0", max_messages=50)
```

If something else already registered `crun.display` — an IDE's own C-RUN
Messages window — nothing reaches this server and `data.receiving` is false.
A backend's `updateAll` push (no data) empties its namespace until the
following pushes refill it, so the list can briefly be shorter than the
backend's. This is a stopgap until the interface can return the current list.

## Reading messages and rules from the IDE's list windows

Against an IDE-hosted session both are also readable with the existing
`listwindow_*` tools (confirmed live against a running iaride), which works
even when the IDE owns `crun.display`:

```
listwindow_get_rows("WIN_C_RUN_MESSAGES")       → message text, source file, PC, core, with nested
                                                   call-stack rows
listwindow_get_rows("WIN_C_RUN_MESSAGE_RULES")  → the rules, read-only: Check / Source File / Action
                                                   columns, a second way to list them next to
                                                   crun_list_rules()
```

These are window ids, not registry service names: iaride serves them through
its shared `listwindow.snapshot` service. That needs cspy-py's
`listwindow.snapshot` routing (`feat/listwindow-snapshot`) in place first;
without it `listwindow_list_services` does not surface them and
`listwindow_get_rows` fails with a raw "No such service" error. Not verified
against a plain CSpyServer2 (headless) session.
