# Ports Visualizer (Python)

Simple Python tool to:
- see which ports are occupied
- see which ports are free in a range
- inspect which process is using a port
- kill the process using a port

## Setup

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
```

## Usage

Interactive mode (default):

```bash
python ports_visualizer.py
```

Scan a range:

```bash
python ports_visualizer.py --start 1 --end 2000 scan
```

Check who is using one port:

```bash
python ports_visualizer.py who 8000
```

Kill process using one port:

```bash
python ports_visualizer.py kill 8000
```

Force kill (if terminate times out) and skip prompt:

```bash
python ports_visualizer.py kill 8000 --force --yes
```

## Notes

- On Windows, killing system-owned ports may require running terminal as Administrator.
- This tool uses `psutil` network/process APIs.
