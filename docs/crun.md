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

## Reading rules and messages (for now: via the list window tools)

`CRunBackend` has no RPC to read the live runtime-check messages at all —
`CRunDisplay` (push-only: `itemAdded`/`itemUpdated`/...) is not wired up on
the MCP side yet (see `TODO.md`). **Until then, both the messages and the
rules can already be read with the existing `listwindow_*` tools**, against
an IDE-hosted session (confirmed live against a running iaride):

```
listwindow_get_rows("WIN_C_RUN_MESSAGES")       → the live runtime-check hits: message text, source
                                                   file, PC, core, with nested call-stack rows
listwindow_get_rows("WIN_C_RUN_MESSAGE_RULES")  → the rules, read-only: Check / Source File / Action
                                                   columns — a second way to list them, next to
                                                   crun_list_rules()
```

`WIN_C_RUN_MESSAGES`/`WIN_C_RUN_MESSAGE_RULES` are window ids, not registry
service names — on an iaride host they are served through its shared
`listwindow.snapshot` service, not one registry entry per window. This needs
cspy-py's `listwindow.snapshot` routing fix (`feat/listwindow-snapshot`;
tracked in cspy-py's `TODO.md`) to be in place first: without it,
`listwindow_list_services` will not surface these ids and
`listwindow_get_overview`/`listwindow_get_rows` on them fails with a raw
"No such service" error. Against a plain CSpyServer2 (headless) session, this
has not been verified yet — CRunLib registers the same window models there
too, but whether that means one `ListWindowBackend` registry entry per
window (the direct path) or nothing reachable at all is unconfirmed.
