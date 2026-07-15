"""session-elapsed — inject elapsed time and turn count via pre_llm_call hook.

Zero-config: works on first install. Configure thresholds under
``plugins.session-elapsed`` in config.yaml.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# --- Module-level state (persisted across hook calls within a process) --------

# session_id → (start_monotonic, start_wall, turn_count)
_session_starts: dict[str, tuple[float, float, int]] = {}

# Config cache (loaded once, then refreshed if config changes)
_config_cache: dict[str, Any] | None = None
_config_loaded_at: float = 0.0
_CONFIG_TTL_SECONDS = 300.0  # re-read config every 5 min


def _load_config() -> dict[str, Any]:
    """Load plugin config from config.yaml with TTL caching."""
    global _config_cache, _config_loaded_at
    now = time.monotonic()
    if _config_cache is not None and (now - _config_loaded_at) < _CONFIG_TTL_SECONDS:
        return _config_cache
    try:
        from hermes_cli.config import load_config
        cfg = load_config() or {}
        plugin_cfg = (cfg.get("plugins") or {}).get("session-elapsed") or {}
    except Exception:
        plugin_cfg = {}
    _config_cache = {
        "enabled": plugin_cfg.get("enabled", True),
        "warn_minutes": plugin_cfg.get("warn_minutes", 60),
        "critical_minutes": plugin_cfg.get("critical_minutes", 180),
    }
    _config_loaded_at = now
    return _config_cache


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds into a compact human-readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    mins = minutes % 60
    if hours < 24:
        return f"{hours}h {mins}m"
    days = hours // 24
    hrs = hours % 24
    return f"{days}d {hrs}h"


def on_pre_llm_call(
    *,
    session_id: str = "",
    task_id: str = "",
    turn_id: str = "",
    user_message: Any = None,
    conversation_history: Any = None,
    is_first_turn: bool = False,
    model: str = "",
    **_: Any,
) -> dict[str, str] | None:
    """Inject elapsed time and turn count into the user message.

    Returns ``{"context": "..."}`` which Hermes appends to the current
    turn's user message (not system prompt — preserves KV cache prefix).
    """
    cfg = _load_config()
    if not cfg["enabled"]:
        return None

    now_mono = time.monotonic()
    now_wall = time.time()
    sid = session_id or "_default"

    # Track session start and turn count
    if sid not in _session_starts:
        _session_starts[sid] = (now_mono, now_wall, 0)

    start_mono, start_wall, turn_count = _session_starts[sid]
    turn_count += 1
    elapsed_s = now_mono - start_mono
    elapsed_str = _format_elapsed(elapsed_s)
    elapsed_min = elapsed_s / 60.0

    # Update state
    _session_starts[sid] = (start_mono, start_wall, turn_count)

    # Build the injection line
    parts: list[str] = [f"[⏱ session: {elapsed_str} elapsed, turn #{turn_count}"]

    # Add urgency markers based on thresholds
    # IMPORTANT: never suggest bypassing quality gates. Long sessions are
    # often legitimate (fixing review findings, iterating on tests). The
    # signal is for self-awareness — am I stuck in a loop doing the same
    # thing, or am I making steady progress?
    if elapsed_min >= cfg["critical_minutes"]:
        parts[0] = "[⏱ session"
        parts.append(
            f" — {elapsed_str}, {turn_count} turns since context start. "
            "If you are making progress, continue. If you are stuck in a loop "
            "repeating the same failed approach, pause and report the blocker "
            "to the user. Do NOT skip tests, bypass hooks, or lower quality "
            "standards regardless of elapsed time.]"
        )
    elif elapsed_min >= cfg["warn_minutes"]:
        parts[0] = "[⏱ session"
        parts.append(
            f" — {elapsed_str}, {turn_count} turns. "
            "If you are making steady progress, ignore this. "
            "If stuck on the same issue, consider escalating or "
            "reporting to the user.]"
        )
    else:
        parts.append("]")

    context = "".join(parts)

    # Evict stale sessions (older than 24h with no activity) to prevent
    # unbounded growth of _session_starts
    _evict_stale(now_mono)

    return {"context": context}


def _evict_stale(now_mono: float, max_age_seconds: float = 86400.0) -> None:
    """Remove session entries older than 24h."""
    stale = [
        sid
        for sid, (start_mono, _, _) in _session_starts.items()
        if (now_mono - start_mono) > max_age_seconds
    ]
    for sid in stale:
        del _session_starts[sid]
