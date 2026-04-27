# Hermes Dashboard

A terminal-native TUI dashboard that replaces the [Hermes Agent](https://github.com/tek/nous-hermes-agent) remote WebUI — no browser, no WebSocket reconnects, no SSH port forwarding.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Textual](https://img.shields.io/badge/textual-8.x-cyan.svg)](https://textual.textualize.io/)

## Why

Hermes Agent ships with a WebUI (`hermes dashboard --web`), but using it over a remote server means:

- **Unstable connections** — WebSocket drops on flaky SSH tunnels, requiring page refresh
- **Port forwarding hassle** — `ssh -L 8080:localhost:8080` on every login
- **Context switching** — tabbing between terminal and browser breaks flow

Hermes Dashboard ditches the browser entirely. It runs **inside your terminal** via [Textual](https://textual.textualize.io/). Same data, same actions, zero latency.

## What it does

| Tab | Capability |
|-----|-----------|
| **会话 (Sessions)** | Browse/search/delete sessions, full chat with context preservation, copy resume commands |
| **状态 (Status)** | Live system resources — load, memory, disk, top processes, skill/plugin counts |
| **任务 (Cron)** | Manage 14 cron jobs — view, enable/disable, trigger manually, inspect output |
| **环境变量 (Env)** | Add/edit/delete variables in `~/.hermes/.env` — sensitive values auto-masked |
| **日志 (Logs)** | Tail agent, errors, gateway, WebUI logs with toggle-able auto-refresh |

Each tab is a single keystroke away (`1`–`5`).

## Install

**Prerequisites**: A working [Hermes Agent](https://github.com/tek/nous-hermes-agent) installation with `hermes` in your `$PATH`.

```bash
# 1. Install dependencies
pip install textual pyyaml

# 2. Download
curl -O https://raw.githubusercontent.com/roy1228/hermes-dashboard/master/hermes_dashboard.py

# 3. Run
python hermes_dashboard.py
```

Optionally install as a command:

```bash
chmod +x hermes_dashboard.py
sudo ln -s $(pwd)/hermes_dashboard.py /usr/local/bin/hermes_dashboard
hermes_dashboard
```

## Keybindings

| Key | Action |
|-----|--------|
| `1`–`5` | Switch tabs instantly |
| `Enter` | Chat with selected session |
| `n` | Start new conversation |
| `Ctrl+C` / `Ctrl+Y` | Copy last AI response to clipboard |
| `Ctrl+Shift+C` | Terminal-native: copy selected text with mouse |
| `r` | Refresh current tab |
| `q` | Quit |

**In the Sessions tab:**
- `◀` marks the currently active conversation
- Shimmer bar animates while the agent is thinking
- "复制恢复命令" button copies `hermes --resume <id>` to clipboard for opening in a full terminal

## How it works

```
┌─ hermes_dashboard ──────────────────────────────────┐
│  Textual TUI  ──shell out──▶  hermes CLI  ──▶  AI   │
│  (async, non-blocking)         (chat -q -Q)          │
│                                                      │
│  Session context persists via:                       │
│  hermes chat -r SID -q "msg" -Q                      │
└──────────────────────────────────────────────────────┘
```

All chat goes through `hermes chat -q -Q` (quiet mode) which produces clean `session_id: <id>\n<response>` output. No banner-parsing, no skin-dependency.

## Requirements

- Python 3.11+
- `textual` >= 8.0
- `pyyaml` >= 6.0
- `hermes` CLI in `$PATH` with a configured provider/model in `~/.hermes/config.yaml`

## License

MIT
