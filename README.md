# ACP Bridge

ACP Bridge connects a local MCP client or CLI to remote Windows development
boxes through a relay. The MVP executes non-interactive CLI agents such as
Codex CLI and Claude Code on the worker host.

```text
Local Codex -> acp-bridge local client -> relay VM -> Windows worker -> CLI agent
```

The relay only routes JSON messages over WebSocket. It authenticates clients
with bearer tokens and does not execute commands.

## Entry Points

- `acp-bridge`: human-facing CLI.
- `acp-bridge-mcp`: MCP server for local Codex.
- `acp-bridge-relay`: relay service for Docker or direct use.
- `acp-bridge-worker`: worker process for the remote devbox.

## Quick Start

Create a config file from the examples in `examples/`, then run:

```bash
uv run acp-bridge-relay --config examples/relay.yaml
uv run acp-bridge-worker --config examples/worker.yaml
uv run acp-bridge run win-dev --agent codex --cwd C:\repo --prompt "run tests"
```

