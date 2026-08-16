"""Tests for the message protocol core (MessageStore).

These exercise the store directly, without an MCP transport. They are the
small validation test called for in PLAN.md before the message protocol is
committed to the experimental schedule: they confirm that every call is
logged, that delivery is correct, and that per-agent cursors do not drop or
duplicate messages.

Run with: pytest tests/test_message_protocol.py
"""

import json

import pytest

from agent_comms.message_protocol.store import (
    MessageProtocolError, MessageStore, estimate_tokens,
)


def make_store(tmp_path, roster=None):
    return MessageStore(
        tmp_path / "run1" / "messages.jsonl", run_id="run1", roster=roster)


# --- recording ---------------------------------------------------------------

def test_send_appends_message_event(tmp_path):
    store = make_store(tmp_path)
    event = store.send("agent-1", "agent-2", "hello")
    assert event["event"] == "message"
    assert event["from"] == "agent-1"
    assert event["to"] == "agent-2"
    assert event["content"] == "hello"
    assert event["run"] == "run1"
    assert event["seq"] == 0


def test_seq_is_monotonic(tmp_path):
    store = make_store(tmp_path)
    first = store.send("agent-1", "agent-2", "one")
    second = store.send("agent-2", "agent-1", "two")
    assert first["seq"] == 0
    assert second["seq"] == 1


def test_bytes_and_token_estimate_recorded(tmp_path):
    store = make_store(tmp_path)
    event = store.send("agent-1", "agent-2", "hello")
    assert event["bytes"] == 5
    assert event["tokens_estimate"] == estimate_tokens("hello")


def test_log_is_valid_jsonl(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "hello")
    store.poll("agent-2")
    with open(store.log_path, encoding="utf-8") as fh:
        lines = [line for line in fh if line.strip()]
    assert len(lines) == 2
    for line in lines:
        json.loads(line)  # must not raise


# --- validation --------------------------------------------------------------

def test_send_rejects_empty_recipient(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(MessageProtocolError):
        store.send("agent-1", "", "hello")


def test_send_rejects_empty_sender(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(MessageProtocolError):
        store.send("", "agent-2", "hello")


def test_send_rejects_non_string_content(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(MessageProtocolError):
        store.send("agent-1", "agent-2", 123)


def test_send_rejects_self_message(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(MessageProtocolError):
        store.send("agent-1", "agent-1", "hello")


# --- delivery and cursors ----------------------------------------------------

def test_poll_delivers_messages_for_agent(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "for two")
    delivered = store.poll("agent-2")
    assert len(delivered) == 1
    assert delivered[0]["content"] == "for two"


def test_poll_excludes_messages_for_other_agents(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "for two")
    assert store.poll("agent-3") == []


def test_poll_is_idempotent(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "for two")
    store.poll("agent-2")
    assert store.poll("agent-2") == []


def test_poll_returns_only_new_messages(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "first")
    store.poll("agent-2")
    store.send("agent-1", "agent-2", "second")
    delivered = store.poll("agent-2")
    assert [e["content"] for e in delivered] == ["second"]


def test_message_order_preserved(tmp_path):
    store = make_store(tmp_path)
    for i in range(5):
        store.send("agent-1", "agent-2", f"msg {i}")
    delivered = store.poll("agent-2")
    assert [e["content"] for e in delivered] == [f"msg {i}" for i in range(5)]


def test_poll_records_poll_event(tmp_path):
    store = make_store(tmp_path)
    store.send("agent-1", "agent-2", "hello")
    store.poll("agent-2")
    poll_events = [e for e in store.events() if e["event"] == "poll"]
    assert len(poll_events) == 1
    assert poll_events[0]["agent"] == "agent-2"
    assert poll_events[0]["delivered"] == 1


# --- roster ------------------------------------------------------------------

def test_roster_flags_unknown_recipient(tmp_path):
    store = make_store(tmp_path, roster=["agent-1", "agent-2"])
    event = store.send("agent-1", "agent-9", "hello")
    assert event.get("unknown_recipient") is True


def test_roster_accepts_known_recipient(tmp_path):
    store = make_store(tmp_path, roster=["agent-1", "agent-2"])
    event = store.send("agent-1", "agent-2", "hello")
    assert "unknown_recipient" not in event


# --- multiple processes on one log ------------------------------------------

def test_separate_stores_share_one_log(tmp_path):
    # Two MessageStore objects on the same log file stand in for two agent
    # processes in one run.
    log = tmp_path / "run1" / "messages.jsonl"
    store_a = MessageStore(log, run_id="run1")
    store_b = MessageStore(log, run_id="run1")
    store_a.send("agent-1", "agent-2", "from a")
    store_b.send("agent-2", "agent-1", "from b")
    delivered = store_b.poll("agent-2")
    assert [e["content"] for e in delivered] == ["from a"]
