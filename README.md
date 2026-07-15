# session-elapsed

A [Hermes](https://github.com/nousresearch/hermes-agent) plugin that injects elapsed session time and turn count into every user message via the `pre_llm_call` hook.

## Why

When running unattended, the agent can't tell if it's been working on a problem for 10 minutes or 3 hours. The API message format (`{"role": "user", "content": "..."}`) carries no timestamps. This plugin gives the agent a lightweight time signal so it can self-regulate:

```
[⏱ session: 2h 17m elapsed, turn #47]
```

~20 tokens per turn. The agent can use this to decide whether to keep going, escalate, or stop.

## How it works

1. **Session start time**: Captured from the first `pre_llm_call` invocation and stored in memory keyed by `session_id`.
2. **Per-turn injection**: Each `pre_llm_call` computes `elapsed = now - session_start` and injects a compact line appended to the user message (not system prompt — preserves KV cache).
3. **Compression-safe**: After context compression, the injection naturally resets — the model sees fresh elapsed time relative to the compressed history.

## Install

```bash
# From source
cd ~/.hermes/plugins
git clone https://github.com/RyderFreeman4Logos/session-elapsed.git

# Or symlink from your project clone
ln -s ~/project/github/RyderFreeman4Logos/session-elapsed ~/.hermes/plugins/session-elapsed

# Enable
hermes plugins enable session-elapsed
```

## Configuration

Optional — works with sensible defaults. Add to `~/.hermes/config.yaml`:

```yaml
plugins:
  session-elapsed:
    enabled: true              # default: true
    warn_minutes: 60           # add urgency marker after this many minutes (default: 60)
    critical_minutes: 180      # add strong warning after this many minutes (default: 180)
```

## License

Apache-2.0
