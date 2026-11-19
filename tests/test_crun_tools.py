"""crun_* tools."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from iar_cspy.crun import _RawEntry, _parse_filter_xml, _render_filter_xml
from iar_cspy.testing import crun_message
from iar_cspy.types import CRunBreakAction


class _FakeCrunBackend:
    """Mirrors CssCRunBackendHandler.cpp closely enough for tool-level tests
    (see cspy-py's tests/test_crun.py for the detailed behavior)."""

    def __init__(self) -> None:
        self.entries: list[_RawEntry] = [_RawEntry("*", "*", None, None, "*", None, None, CRunBreakAction.STOP_AND_LOG)]

    def wire(self, rpc: Any) -> None:
        rpc.on("crun", "saveFilters", self._save)
        rpc.on("crun", "loadFilters", self._load)
        rpc.on("crun", "addRuleOnMessage", lambda name: self._prepend(name, "*", None, None, "*", None, None))
        rpc.on(
            "crun",
            "addRuleOnMessageFile",
            lambda name, file: self._prepend(name, file, None, None, file, None, None),
        )
        rpc.on("crun", "getDefaultAction", lambda: int(self.entries[-1].action))
        rpc.on("crun", "setDefaultAction", self._set_default_action)

    def _prepend(self, name, start_file, start_line, start_col, end_file, end_line, end_col) -> None:
        self.entries.insert(0, _RawEntry(name, start_file, start_line, start_col, end_file, end_line, end_col, CRunBreakAction.LOG))

    def _set_default_action(self, action: int) -> None:
        self.entries[-1] = _RawEntry("*", "*", None, None, "*", None, None, CRunBreakAction(action))

    def _save(self, filename: str) -> None:
        Path(filename).write_text(_render_filter_xml(self.entries), encoding="utf-8")

    def _load(self, filename: str) -> None:
        self.entries = _parse_filter_xml(Path(filename).read_text(encoding="utf-8"))


def _backend(rpc: Any) -> _FakeCrunBackend:
    fake = _FakeCrunBackend()
    fake.wire(rpc)
    return fake


def test_crun_list_rules_starts_with_just_the_default(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_list_rules()
    assert out["ok"] is True
    assert out["data"]["count"] == 1
    assert out["data"]["rules"][0]["is_default"] is True
    assert out["data"]["rules"][0]["action"] == "STOP_AND_LOG"


def test_crun_add_rule_lands_at_index_zero_with_log_action(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_add_rule("AssertFailure")
    assert out["ok"] is True
    assert out["data"]["index"] == 0
    assert out["data"]["action"] == "LOG"
    assert out["data"]["is_default"] is False


def test_crun_add_rule_with_action_sets_it(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_add_rule("AssertFailure", action="IGNORE")
    assert out["ok"] is True
    assert out["data"]["action"] == "IGNORE"


def test_crun_update_and_delete_rule(server, fake):
    _, rpc = fake
    _backend(rpc)
    server.crun_add_rule("AssertFailure")

    out = server.crun_update_rule(0, message_pattern="Other", action="STOP_AND_LOG")
    assert out["ok"] is True
    assert out["data"]["message_pattern"] == "Other"
    assert out["data"]["action"] == "STOP_AND_LOG"

    out = server.crun_delete_rule(0)
    assert out["ok"] is True

    out = server.crun_list_rules()
    assert out["data"]["count"] == 1


def test_crun_delete_default_rule_is_a_structured_error(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_delete_rule(0)
    assert out["ok"] is False
    assert out["error"]["code"] == "CRUN_DEFAULT_RULE_RESTRICTED"
    assert out["error"]["retryable"] is False


def test_crun_update_rule_bad_index_is_a_structured_error(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_update_rule(5)
    assert out["ok"] is False
    assert out["error"]["code"] == "CRUN_INVALID_RULE_INDEX"


def test_crun_default_action_get_and_set(server, fake):
    _, rpc = fake
    _backend(rpc)

    out = server.crun_set_default_action("LOG")
    assert out["ok"] is True

    out = server.crun_get_default_action()
    assert out["ok"] is True
    assert out["data"]["action"] == "LOG"


def test_crun_not_initialized_is_a_structured_error(server, fake):
    _, rpc = fake

    def not_initialized(*args, **kwargs):
        raise Exception("C-RUN is not initialized")

    rpc.on("crun", "getDefaultAction", not_initialized)

    out = server.crun_get_default_action()
    assert out["ok"] is False
    assert out["error"]["code"] == "CRUN_NOT_INITIALIZED"


def test_crun_load_and_save_filters_pass_the_filename_through(server, fake, tmp_path):
    _, rpc = fake
    rpc.on("crun", "saveFilters", lambda filename: None)
    rpc.on("crun", "loadFilters", lambda filename: None)

    out_path = str(tmp_path / "rules.xml")
    out = server.crun_save_filters(out_path)
    assert out["ok"] is True
    assert rpc.args("crun", "saveFilters") == [(out_path,)]

    out = server.crun_load_filters(out_path)
    assert out["ok"] is True
    assert rpc.args("crun", "loadFilters") == [(out_path,)]


def _display(client):
    """Push as the backend would: through the CRunDisplay handler iar_cspy hosts."""
    return client.crun_messages.server.handler


def test_crun_get_messages_reports_what_the_backend_pushed(server, fake):
    client, _ = fake
    handler = _display(client)
    handler.itemAdded(crun_message(index=0, name="Division by zero", text="x / 0"), "core0")
    handler.itemAdded(crun_message(index=1, name="Access out of bounds"), "core0")
    handler.itemAdded(crun_message(index=0, name="Other"), "core1")

    out = server.crun_get_messages()
    assert out["ok"] is True
    assert out["data"]["namespaces"] == ["core0", "core1"]
    assert out["data"]["count"] == 3
    assert [m["name"] for m in out["data"]["messages"]] == ["Division by zero", "Access out of bounds", "Other"]
    assert out["data"]["messages"][0]["namespace"] == "core0"
    assert out["data"]["messages"][0]["break_action"] == "LOG"

    only = server.crun_get_messages(namespace="core1")
    assert [m["name"] for m in only["data"]["messages"]] == ["Other"]


def test_crun_get_messages_truncates(server, fake):
    client, _ = fake
    for i in range(5):
        _display(client).itemAdded(crun_message(index=i), "")

    out = server.crun_get_messages(max_messages=2)
    assert (out["data"]["count"], out["data"]["truncated"], len(out["data"]["messages"])) == (5, True, 2)


def test_crun_clear_messages(server, fake):
    client, _ = fake
    _display(client).itemAdded(crun_message(index=0), "core0")
    _display(client).itemAdded(crun_message(index=0), "core1")

    assert server.crun_clear_messages("core0")["ok"] is True
    assert server.crun_get_messages()["data"]["namespaces"] == ["core1"]
    server.crun_clear_messages()
    assert server.crun_get_messages()["data"]["count"] == 0
