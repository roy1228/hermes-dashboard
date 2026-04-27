# Hermes Dashboard

Terminal TUI dashboard for [Hermes Agent](https://github.com/tek/nous-hermes-agent), replacing the remote WebUI.

## Features

- **Session management** — list, search, chat, delete, copy resume commands
- **Cron jobs** — list, enable/disable, trigger, view output
- **Environment variables** — view, add, edit, delete `~/.hermes/.env`
- **Log viewer** — agent, errors, gateway, WebUI logs
- **System status** — model, gateway state, session count, load/memory/disk

## Quick Start

Requires a working [Hermes Agent](https://github.com/tek/nous-hermes-agent) installation.

```bash
pip install textual pyyaml
curl -O https://raw.githubusercontent.com/<your-username>/hermes-dashboard/main/hermes_dashboard.py
python hermes_dashboard.py
```

## Usage

| Key | Action |
|-----|--------|
| `1`-`5` | Switch tabs (Status / Sessions / Cron / Env / Logs) |
| `Enter` | Chat with selected session |
| `n` | New conversation |
| `Ctrl+Y` | Copy last AI response to clipboard |
| `r` | Refresh current tab |
| `q` | Quit |

In the sessions tab:
- Left panel: session list with search and delete
- Right panel: chat feed with shimmer bar while AI responds
- `◀` marks the active session

## Requirements

- Python 3.11+
- `textual` >= 8.0
- `pyyaml` >= 6.0
- `hermes` CLI available in `$PATH`

## License

MIT
