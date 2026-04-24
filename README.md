# Windows Port Visualizer

Python ports visualizer for Windows with both GUI and CLI modes.

It can:
- scan all ports from `1` to `65535`
- show which ports are occupied
- show which ports are free in a selected CLI range
- show which process owns a port
- show local bind address so IPv4, IPv6, and multi-NIC bindings make sense
- dedupe exact duplicate socket rows
- kill the process using a selected port or selected GUI rows

## Requirements

- Python 3.10+
- Windows recommended
- `psutil` for process and socket inspection

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Quick Start

Launch the GUI:

```bash
python ports_visualizer.py
```

Or explicitly:

```bash
python ports_visualizer.py gui
```

## GUI Features

- live table of occupied ports
- columns for port, protocol, local address, PID, process, and command line
- filter box for port, PID, process name, or command text
- auto-refresh every 5 seconds
- inspect selected rows in a detail window
- kill selected rows with confirmation

## CLI Usage

Scan a range:

```bash
python ports_visualizer.py --start 1 --end 2000 scan
```

Text interactive mode:

```bash
python ports_visualizer.py interactive
```

Check who is using one port:

```bash
python ports_visualizer.py who 5433
```

Kill process using one port:

```bash
python ports_visualizer.py kill 5433
```

Force kill and skip prompt:

```bash
python ports_visualizer.py kill 5433 --force --yes
```

## Notes

- same port can appear more than once when it is bound on different local addresses such as `0.0.0.0`, `::`, or multiple network adapters
- exact duplicate socket rows are removed
- on Windows, killing system-owned ports may require running the terminal as Administrator
- the repo includes `.vscode/mcp.json` with `agent-kb` and `flowmap` server config
