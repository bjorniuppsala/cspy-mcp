"""C-RUN runtime-checking rule tools (the ``CRunBackend`` service, crun.thrift).

Session-scoped, like breakpoints/memory: C-RUN's filter lives in the debug
session (CSpyServer2), so every tool here requires one (``require_session``).
See ``iar_cspy.crun`` for what is and is not natively supported by the
backend - in short, only "add a rule" (always with the ``Log`` action) and
"get/set the default rule's action" are real RPCs; list/update/delete are
reconstructed on top of a save/load file round trip, which assumes the MCP
server and the debug backend share a filesystem.

Failures are enveloped (not left to raise), mirroring project.py/options.py:
these are mutating, multi-step operations with real, structured failure
modes worth reporting distinctly to an AI caller (not initialized, bad rule
index, can't rescope/delete the default rule - see CRUN_* in
``iar_cspy.errors.ERROR_CODES``), not the bare-``Any`` style breakpoints.py
uses for pure passthroughs.

Live runtime-check messages come from ``crun_get_messages`` (iar-cspy's
``client.crun_messages``, which hosts ``CRunDisplay``); against an IDE that
already hosts that service, ``listwindow_get_rows("WIN_C_RUN_MESSAGES")`` reads
them instead. See docs/crun.md.
"""

from __future__ import annotations

from typing import Any

from iar_cspy import CSpyError, CrunRule

from .._app import envelope, get_client, mcp, require_session


def _rule_data(rule: CrunRule) -> dict[str, Any]:
    return rule.to_dict()


def _crun_error(tool: str, data: dict[str, Any], exc: CSpyError) -> dict[str, Any]:
    return envelope(ok=False, tool=tool, data=data, error=get_client().classify_error(exc))


@mcp.tool()
def crun_get_default_action() -> dict[str, Any]:
    """Get the default (always-last, catch-all) C-RUN rule's action.

    Returns one of "STOP_AND_LOG", "LOG", "IGNORE".
    """
    require_session("crun_get_default_action")
    try:
        action = get_client().crun_rules.default_action()
    except CSpyError as exc:
        return _crun_error("crun_get_default_action", {}, exc)
    return envelope(ok=True, tool="crun_get_default_action", data={"action": action.name})


@mcp.tool()
def crun_set_default_action(action: str) -> dict[str, Any]:
    """Set the default (always-last, catch-all) C-RUN rule's action.

    Args:
        action: "STOP_AND_LOG", "LOG", or "IGNORE".
    """
    require_session("crun_set_default_action")
    data = {"action": action}
    try:
        get_client().crun_rules.set_default_action(action)
    except CSpyError as exc:
        return _crun_error("crun_set_default_action", data, exc)
    return envelope(ok=True, tool="crun_set_default_action", data=data)


@mcp.tool()
def crun_list_rules() -> dict[str, Any]:
    """List every C-RUN rule, index 0 first; the last one is always the default/catch-all.

    Reconstructed from a save/load file round trip (CRunBackend has no
    listing RPC): `ok=False` with error.code=CRUN_NOT_INITIALIZED when no
    C-RUN-capable session is configured.
    """
    require_session("crun_list_rules")
    try:
        rules = get_client().crun_rules.rules()
    except CSpyError as exc:
        return _crun_error("crun_list_rules", {}, exc)
    data = {"rules": [_rule_data(r) for r in rules], "count": len(rules)}
    return envelope(ok=True, tool="crun_list_rules", data=data)


@mcp.tool()
def crun_add_rule(
    message_pattern: str,
    file: str | None = None,
    start_line: int | None = None,
    start_col: int | None = None,
    end_line: int | None = None,
    end_col: int | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """Add a C-RUN rule matching ``message_pattern``; it always lands at index 0.

    With no location it matches anywhere; with `file` alone, anywhere in
    that file; with a line/col too (`file` required), that source range
    (`end_line`/`end_col` default to `start_line`/`start_col` for a
    single-point rule). The backend always creates the rule with the "LOG"
    action; pass `action` ("STOP_AND_LOG"/"LOG"/"IGNORE") for a different one
    (one extra round trip).
    """
    require_session("crun_add_rule")
    data = {
        "message_pattern": message_pattern,
        "file": file,
        "start_line": start_line,
        "start_col": start_col,
        "end_line": end_line,
        "end_col": end_col,
        "action": action,
    }
    try:
        rule = get_client().crun_rules.add_rule(
            message_pattern,
            file=file,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            action=action,
        )
    except CSpyError as exc:
        return _crun_error("crun_add_rule", data, exc)
    return envelope(ok=True, tool="crun_add_rule", data=_rule_data(rule))


@mcp.tool()
def crun_update_rule(
    index: int,
    message_pattern: str | None = None,
    file: str | None = None,
    start_line: int | None = None,
    start_col: int | None = None,
    end_line: int | None = None,
    end_col: int | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    """Edit one rule by its current index (see crun_list_rules); only given fields change.

    The default/catch-all rule (the last index) always matches everything:
    only its `action` can be changed here (use crun_set_default_action, or
    this tool with only `action` set) - trying to change its pattern or
    location fails with error.code=CRUN_DEFAULT_RULE_RESTRICTED. A bad
    `index` fails with error.code=CRUN_INVALID_RULE_INDEX.
    """
    require_session("crun_update_rule")
    data = {
        "index": index,
        "message_pattern": message_pattern,
        "file": file,
        "start_line": start_line,
        "start_col": start_col,
        "end_line": end_line,
        "end_col": end_col,
        "action": action,
    }
    try:
        rule = get_client().crun_rules.update_rule(
            int(index),
            message_pattern=message_pattern,
            file=file,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            action=action,
        )
    except CSpyError as exc:
        return _crun_error("crun_update_rule", data, exc)
    return envelope(ok=True, tool="crun_update_rule", data=_rule_data(rule))


@mcp.tool()
def crun_delete_rule(index: int) -> dict[str, Any]:
    """Delete one rule by its current index (see crun_list_rules).

    The default/catch-all rule (the last index) cannot be deleted
    (error.code=CRUN_DEFAULT_RULE_RESTRICTED) - set its action instead. A bad
    `index` fails with error.code=CRUN_INVALID_RULE_INDEX.
    """
    require_session("crun_delete_rule")
    data = {"index": index}
    try:
        get_client().crun_rules.delete_rule(int(index))
    except CSpyError as exc:
        return _crun_error("crun_delete_rule", data, exc)
    return envelope(ok=True, tool="crun_delete_rule", data=data)


@mcp.tool()
def crun_load_filters(filename: str) -> dict[str, Any]:
    """Replace the whole C-RUN rule set from an XML file.

    `filename` is resolved on the backend's own filesystem (CSpyServer2 or
    iaride), not this server's - only meaningful when they share one.
    """
    require_session("crun_load_filters")
    data = {"filename": filename}
    try:
        get_client().crun_rules.load_filters(filename)
    except CSpyError as exc:
        return _crun_error("crun_load_filters", data, exc)
    return envelope(ok=True, tool="crun_load_filters", data=data)


@mcp.tool()
def crun_save_filters(filename: str) -> dict[str, Any]:
    """Write the whole C-RUN rule set to an XML file.

    `filename` is resolved on the backend's own filesystem (CSpyServer2 or
    iaride), not this server's - only meaningful when they share one.
    """
    require_session("crun_save_filters")
    data = {"filename": filename}
    try:
        get_client().crun_rules.save_filters(filename)
    except CSpyError as exc:
        return _crun_error("crun_save_filters", data, exc)
    return envelope(ok=True, tool="crun_save_filters", data=data)


@mcp.tool()
def crun_get_messages(namespace: str | None = None, max_messages: int = 200) -> dict[str, Any]:
    """Read the live C-RUN runtime-check messages the backend has pushed (CRunDisplay).

    Registers this server as the backend's `crun.display` on first use. Only
    messages pushed after that are seen: call it before running the target. If
    something else already registered `crun.display` (an IDE's own C-RUN
    Messages window), nothing reaches this server and `data.receiving` is false;
    read that window with listwindow_get_rows("WIN_C_RUN_MESSAGES") instead.

    Messages are kept per `namespace` (the backend partner that sent them; ""
    for an IDE, which hosts every core itself). Pass one to see only its
    messages. Each message has `name`, `text`, `core`, `cycle`, `repeat_count`,
    `call_stack`, `break_action` and nested `sub_messages`. `data.truncated` is
    true when more than `max_messages` matched.

    A backend's `updateAll` push empties a namespace until the following pushes
    refill it, so the list can briefly be shorter than the backend's.
    """
    messages = get_client().crun_messages
    try:
        registration = messages.ensure_registered()
    except CSpyError as exc:
        return _crun_error("crun_get_messages", {}, exc)
    stored = messages.all_messages() if namespace is None else {namespace: messages.messages(namespace)}
    limit = max(1, int(max_messages))
    flat = [(ns, m) for ns, items in sorted(stored.items()) for m in items]
    data = {
        "receiving": messages.receiving,
        "registration": registration,
        "namespaces": messages.namespaces(),
        "count": len(flat),
        "truncated": len(flat) > limit,
        "messages": [{"namespace": ns, **m.to_dict()} for ns, m in flat[:limit]],
    }
    return envelope(ok=True, tool="crun_get_messages", data=data)


@mcp.tool()
def crun_clear_messages(namespace: str | None = None) -> dict[str, Any]:
    """Forget the stored C-RUN messages of `namespace`, or of every namespace."""
    get_client().crun_messages.clear(namespace)
    return envelope(ok=True, tool="crun_clear_messages", data={"namespace": namespace})
