# session-elapsed

A [Hermes](https://github.com/nousresearch/hermes-agent) plugin that injects elapsed session time and turn count into every user message via the `pre_llm_call` hook.

## Why

When running unattended, the agent can't tell if it's been working on a problem for 10 minutes or 3 hours. The API message format (`{"role": "user", "content": "..."}`) carries no timestamps. The system prompt has a session-start date, but no elapsed time — and after context compression, even that context is summarized away.

This plugin gives the agent a lightweight, factual time signal so it can self-regulate:

```
[⏱ session: 2h 17m elapsed, turn #47]
```

~20 tokens per turn. Zero external dependencies.

## Design philosophy

**The signal is neutral — facts, not commands.**

The plugin never tells the agent to stop, hurry, or skip quality gates. It provides elapsed time and turn count, then lets the agent (guided by its system prompt) decide what to do. This is deliberate:

- Some tasks legitimately take hours (multi-round code review, complex debugging, large refactors).
- "Making progress" is not the right test — a review loop that burns 151M tokens without converging makes "progress" every round.
- Time pressure can cause harmful behavior: skipping tests, bypassing hooks, lowering standards.

The right question at high elapsed time is not *should I stop?* but *is my approach the right one?*

### Threshold behavior

| Elapsed | Example output | Intent |
|---|---|---|
| < 60 min | `[⏱ session: 23m elapsed, turn #8]` | Pure facts |
| ≥ 60 min | `[⏱ session: 1h 12m elapsed, turn #31 — 1h 12m, 31 turns. Do NOT skip tests, bypass hooks, or lower quality standards.]` | Facts + quality-gate reminder |
| ≥ 180 min | `[⏱ session: 3h 05m elapsed, turn #72 — 3h 05m, 72 turns since context start. Do NOT skip tests, bypass hooks, or lower quality standards. Ask yourself: is the current approach the right one, or am I treating a symptom while the root cause remains unaddressed?]` | Facts + approach-reflection prompt |

Thresholds are configurable (see below).

## How it works

1. **Session start time**: Captured from the first `pre_llm_call` invocation, stored in memory keyed by `session_id`. Uses `time.monotonic()` so NTP adjustments don't skew elapsed time.
2. **Per-turn injection**: Each `pre_llm_call` computes `elapsed = now - session_start` and returns `{"context": "..."}`. Hermes appends this to the current turn's user message — **not the system prompt**, preserving KV cache prefix.
3. **Compression-safe**: The injection is ephemeral — it doesn't persist to conversation history. After context compression, elapsed time naturally resets relative to the compressed history. The model sees fresh time signals in the new context window.
4. **Multi-session**: Each `session_id` gets independent tracking. Stale sessions (>24h inactive) are automatically evicted to prevent unbounded memory growth.
5. **Config hot-reload**: Reads `config.yaml` with a 5-minute TTL cache, so threshold changes take effect without restarting.

## Recommended SOUL.md / system prompt addition

The plugin injects raw data. For the model to act on it, add a line to your `SOUL.md` or custom system prompt:

```markdown
When you see [⏱ session: Xh Ym elapsed, turn #N] at the end of a user message,
treat it as a neutral self-check signal. Some tasks legitimately take hours.
Long elapsed time is never a reason to skip tests, bypass hooks, or lower
quality standards. When the elapsed time feels disproportionate to the task's
inherent complexity, the right response is to question your approach — not to
rush, cut corners, or stop. Ask: am I treating symptoms while the root cause
persists? Would a fundamentally different strategy converge faster?
```

## Install

```bash
# Option 1: Clone directly into plugins dir
cd ~/.hermes/plugins
git clone https://github.com/RyderFreeman4Logos/session-elapsed.git

# Option 2: Symlink from your project checkout (recommended for development)
ln -s ~/project/github/RyderFreeman4Logos/session-elapsed ~/.hermes/plugins/session-elapsed

# Enable
hermes plugins enable session-elapsed
```

Takes effect on the next session.

## Configuration

Optional — works with sensible defaults. Add to `~/.hermes/config.yaml`:

```yaml
plugins:
  session-elapsed:
    enabled: true              # default: true
    warn_minutes: 60           # add quality-gate reminder after this many minutes
    critical_minutes: 180      # add approach-reflection prompt after this many minutes
```

To disable temporarily without uninstalling:

```yaml
plugins:
  session-elapsed:
    enabled: false
```

Changes take effect within 5 minutes (config TTL cache).

## Files

```
session-elapsed/
├── __init__.py      # Plugin logic: pre_llm_call hook
├── plugin.yaml      # Plugin manifest
├── test_plugin.py   # Unit tests (run: python3 test_plugin.py)
├── pyproject.toml
├── LICENSE
└── README.md
```

## Testing

```bash
cd session-elapsed
python3 test_plugin.py
# All tests passed!
```

## Limitations

- **Existing sessions don't hot-reload**: Python caches the plugin module in `sys.modules`. Only new sessions (started after `hermes plugins enable`) load the current code.
- **Elapsed time resets after compression**: This is by design. The signal tracks time within the current context window, not wall-clock session duration. For total session duration, the system prompt's `Conversation started: <date>` is the anchor.
- **No persistence across restarts**: If the gateway restarts, all session timers reset. The first turn after restart shows `0s elapsed, turn #1`.

## License

Apache-2.0
