#!/usr/bin/env python3
"""Tests for session-elapsed plugin."""

import sys
import os
import time

# Import the plugin's __init__ module directly
sys.path.insert(0, os.path.dirname(__file__))
import __init__ as plugin

on_pre_llm_call = plugin.on_pre_llm_call
_format_elapsed = plugin._format_elapsed
_session_starts = plugin._session_starts
_session_elapsed = plugin

# --- _format_elapsed ----------------------------------------------------------


def test_format_seconds():
    assert _format_elapsed(5) == "5s"
    assert _format_elapsed(59) == "59s"


def test_format_minutes():
    assert _format_elapsed(60) == "1m"
    assert _format_elapsed(119) == "1m"
    assert _format_elapsed(120) == "2m"
    assert _format_elapsed(3599) == "59m"


def test_format_hours():
    assert _format_elapsed(3600) == "1h 0m"
    assert _format_elapsed(3660) == "1h 1m"
    assert _format_elapsed(7200) == "2h 0m"


def test_format_days():
    assert _format_elapsed(86400) == "1d 0h"
    assert _format_elapsed(90000) == "1d 1h"


# --- on_pre_llm_call ----------------------------------------------------------


def test_returns_context_dict():
    """Should return {"context": "..."} for the hook to pick up."""
    _session_starts.clear()
    result = on_pre_llm_call(session_id="test-1", is_first_turn=True)
    assert result is not None
    assert "context" in result
    assert "session:" in result["context"]
    assert "turn #1" in result["context"]


def test_disabled_returns_none():
    """When disabled, should return None."""
    _session_elapsed._config_cache = {"enabled": False, "warn_turns": 30, "critical_turns": 80}
    _session_elapsed._config_loaded_at = time.monotonic()
    result = on_pre_llm_call(session_id="test-disabled")
    assert result is None
    # Restore
    _session_elapsed._config_cache = None


def test_turn_counter_increments():
    """Turn count should increment across calls."""
    _session_starts.clear()
    r1 = on_pre_llm_call(session_id="test-inc", is_first_turn=True)
    assert "turn #1" in r1["context"]
    r2 = on_pre_llm_call(session_id="test-inc")
    assert "turn #2" in r2["context"]
    r3 = on_pre_llm_call(session_id="test-inc")
    assert "turn #3" in r3["context"]


def test_separate_sessions():
    """Different session_ids should have independent counters."""
    _session_starts.clear()
    on_pre_llm_call(session_id="sess-a")
    on_pre_llm_call(session_id="sess-a")
    r = on_pre_llm_call(session_id="sess-b")
    assert "turn #1" in r["context"]


def test_normal_no_urgency():
    """Under warn_turns, should have plain marker."""
    _session_starts.clear()
    r = on_pre_llm_call(session_id="test-normal")
    assert "⏱" in r["context"]
    assert "Do NOT" not in r["context"]


def test_warn_threshold():
    """At warn_turns (default 30), should include quality-gate reminder."""
    _session_starts.clear()
    # Simulate 30 turns
    for _ in range(29):
        on_pre_llm_call(session_id="test-warn")
    r = on_pre_llm_call(session_id="test-warn")
    assert "turn #30" in r["context"]
    assert "Do NOT skip tests" in r["context"]
    assert "root cause" not in r["context"]


def test_critical_threshold():
    """At critical_turns (default 80), should include approach-reflection prompt."""
    _session_starts.clear()
    for _ in range(79):
        on_pre_llm_call(session_id="test-crit")
    r = on_pre_llm_call(session_id="test-crit")
    assert "turn #80" in r["context"]
    assert "root cause" in r["context"]
    assert "Do NOT skip tests" in r["context"]


if __name__ == "__main__":
    test_format_seconds()
    test_format_minutes()
    test_format_hours()
    test_format_days()
    test_returns_context_dict()
    test_disabled_returns_none()
    test_turn_counter_increments()
    test_separate_sessions()
    test_normal_no_urgency()
    test_warn_threshold()
    test_critical_threshold()
    print("All tests passed!")
