#!/usr/bin/env python3
"""Ports visualizer: scan, inspect, and kill processes by port. GUI and CLI."""

from __future__ import annotations

import argparse
import os
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import psutil  # third-party: network + process info


# ── constants ────────────────────────────────────────────────────────────────

PORT_MIN = 1
PORT_MAX = 65535
GUI_REFRESH_MS = 5000      # auto-refresh interval in milliseconds
KILL_TIMEOUT_S = 3         # seconds to wait after terminate() before giving up


# ── data model ───────────────────────────────────────────────────────────────

@dataclass
class PortBinding:
    protocol: str
    port: int
    local_ip: str
    pid: int | None
    process_name: str
    process_cmd: str


# ── core data layer ──────────────────────────────────────────────────────────

def safe_process_info(pid: int | None) -> Tuple[str, str]:
    if pid is None:
        return "unknown", ""
    try:
        proc = psutil.Process(pid)
        name = proc.name()
        cmd = " ".join(proc.cmdline())
        return name or "unknown", cmd
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return "unknown", ""


def get_active_bindings() -> List[PortBinding]:
    seen: Set[Tuple] = set()
    bindings: List[PortBinding] = []

    for conn in psutil.net_connections(kind="inet"):
        if not conn.laddr:
            continue

        protocol = "TCP" if conn.type == socket.SOCK_STREAM else "UDP"
        is_tcp_listener = conn.type == socket.SOCK_STREAM and conn.status == psutil.CONN_LISTEN
        is_udp_bound = conn.type == socket.SOCK_DGRAM

        if not is_tcp_listener and not is_udp_bound:
            continue

        # dedupe: same proto + port + local ip + pid is the same socket
        key = (protocol, conn.laddr.port, conn.laddr.ip, conn.pid)
        if key in seen:
            continue
        seen.add(key)

        process_name, process_cmd = safe_process_info(conn.pid)
        bindings.append(PortBinding(
            protocol=protocol,
            port=conn.laddr.port,
            local_ip=conn.laddr.ip,
            pid=conn.pid,
            process_name=process_name,
            process_cmd=process_cmd,
        ))

    bindings.sort(key=lambda b: (b.port, b.protocol, b.local_ip))
    return bindings


def build_port_index(bindings: Sequence[PortBinding]) -> Dict[int, List[PortBinding]]:
    index: Dict[int, List[PortBinding]] = {}
    for b in bindings:
        index.setdefault(b.port, []).append(b)
    return index


def compress_ports(ports: Iterable[int]) -> List[str]:
    sorted_ports = sorted(set(ports))
    if not sorted_ports:
        return []

    ranges: List[str] = []
    start = sorted_ports[0]
    prev = sorted_ports[0]

    for port in sorted_ports[1:]:
        if port == prev + 1:
            prev = port
            continue
        ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
        start = prev = port

    ranges.append(f"{start}-{prev}" if start != prev else f"{start}")
    return ranges


def kill_pids(pids: List[int], force: bool) -> List[str]:
    """Kill list of pids. Returns result messages."""
    messages: List[str] = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=KILL_TIMEOUT_S)
            messages.append(f"Terminated PID {pid}.")
        except psutil.TimeoutExpired:
            if force:
                try:
                    proc.kill()
                    proc.wait(timeout=KILL_TIMEOUT_S)
                    messages.append(f"Force-killed PID {pid}.")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as err:
                    messages.append(f"Failed to force-kill PID {pid}: {err}")
            else:
                messages.append(f"PID {pid} did not stop. Re-run with --force.")
        except (psutil.NoSuchProcess, psutil.AccessDenied) as err:
            messages.append(f"Failed to kill PID {pid}: {err}")
    return messages


# ── CLI render helpers ───────────────────────────────────────────────────────

def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def render_scan(start_port: int, end_port: int) -> None:
    if start_port < PORT_MIN or end_port > PORT_MAX or start_port > end_port:
        raise ValueError(f"Port range must be {PORT_MIN}-{PORT_MAX}, start <= end.")

    bindings = get_active_bindings()
    index = build_port_index(bindings)

    scanned = list(range(start_port, end_port + 1))
    used = [p for p in scanned if p in index]
    free = [p for p in scanned if p not in index]

    print(f"Range: {start_port}-{end_port}")
    print(f"Occupied: {len(used)} | Free: {len(free)} | Total: {len(scanned)}")
    print()

    if used:
        print("Occupied ports:")
        print(f"{'PORT':<7}{'PROTO':<8}{'LOCAL ADDR':<18}{'PID':<9}PROCESS")
        for port in used:
            for b in index[port]:
                pid_text = str(b.pid) if b.pid is not None else "N/A"
                print(f"{b.port:<7}{b.protocol:<8}{b.local_ip:<18}{pid_text:<9}{b.process_name}")
        print()
    else:
        print("No occupied ports in selected range.")
        print()

    free_ranges = compress_ports(free)
    if free_ranges:
        print("Free ports (compressed):")
        print(", ".join(free_ranges))


def inspect_port(port: int) -> List[PortBinding]:
    bindings = [b for b in get_active_bindings() if b.port == port]

    if not bindings:
        print(f"Port {port} is free.")
        return []

    print(f"Port {port} is occupied by:")
    print(f"{'PROTO':<8}{'LOCAL ADDR':<18}{'PID':<9}{'PROCESS':<22}CMD")
    for b in bindings:
        pid_text = str(b.pid) if b.pid is not None else "N/A"
        cmd = b.process_cmd or "(no access)"
        print(f"{b.protocol:<8}{b.local_ip:<18}{pid_text:<9}{b.process_name:<22}{cmd}")

    return bindings


def kill_by_port(port: int, force: bool, yes: bool) -> None:
    bindings = inspect_port(port)
    if not bindings:
        return

    pids = sorted({b.pid for b in bindings if b.pid is not None})
    if not pids:
        print("Could not resolve PID. Nothing to kill.")
        return

    if not yes:
        answer = input(f"Kill PID(s) {', '.join(str(p) for p in pids)}? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("Kill cancelled.")
            return

    for msg in kill_pids(pids, force):
        print(msg)


def run_interactive(start_port: int, end_port: int) -> None:
    while True:
        clear_screen()
        print("Ports Visualizer")
        print("================")
        render_scan(start_port, end_port)
        print()
        print("1) Refresh  2) Check port  3) Kill by port  4) Change range  5) Exit")
        choice = input("Select [1-5]: ").strip()

        if choice == "1":
            continue
        if choice == "2":
            try:
                inspect_port(int(input("Port: ").strip()))
            except ValueError:
                print("Invalid port.")
            input("\nPress Enter to continue...")
        elif choice == "3":
            try:
                port = int(input("Port: ").strip())
                force = input("Force kill? [y/N]: ").strip().lower() in {"y", "yes"}
                kill_by_port(port=port, force=force, yes=False)
            except ValueError:
                print("Invalid port.")
            input("\nPress Enter to continue...")
        elif choice == "4":
            try:
                ns = int(input("Start port: ").strip())
                ne = int(input("End port: ").strip())
                if ns < PORT_MIN or ne > PORT_MAX or ns > ne:
                    print("Invalid range.")
                else:
                    start_port, end_port = ns, ne
            except ValueError:
                print("Invalid range.")
            input("\nPress Enter to continue...")
        elif choice == "5":
            print("Bye.")
            return
        else:
            print("Unknown action.")
            input("\nPress Enter to continue...")


# ── GUI ──────────────────────────────────────────────────────────────────────

class PortsApp(tk.Tk):
    COLUMNS = ("port", "proto", "local_addr", "pid", "process", "cmd")
    COL_HEADERS = ("Port", "Proto", "Local Address", "PID", "Process", "Command")
    COL_WIDTHS = (65, 60, 140, 75, 160, 360)

    TAG_OCCUPIED = "occupied"

    def __init__(self) -> None:
        super().__init__()
        self.title("Ports Visualizer")
        self.geometry("960x640")
        self.minsize(800, 480)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", self._on_filter_change)
        self._all_rows: List[Tuple] = []
        self._after_id: str | None = None
        self._build_ui()
        self._refresh()

    # ── build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_toolbar()
        self._build_stats_bar()
        self._build_tree()
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, pady=6, padx=8)
        bar.pack(side=tk.TOP, fill=tk.X)

        tk.Label(bar, text="Filter:").pack(side=tk.LEFT)
        tk.Entry(bar, textvariable=self._filter_var, width=28).pack(side=tk.LEFT, padx=(4, 12))

        tk.Button(bar, text="Refresh", command=self._refresh, width=10).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Inspect Selected", command=self._inspect_selected, width=16).pack(side=tk.LEFT, padx=4)
        tk.Button(bar, text="Kill Selected", command=self._kill_selected,
                  bg="#c0392b", fg="white", width=14).pack(side=tk.LEFT, padx=4)

        self._auto_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text="Auto-refresh (5s)", variable=self._auto_var,
                       command=self._toggle_auto).pack(side=tk.LEFT, padx=12)

    def _build_stats_bar(self) -> None:
        self._stats_var = tk.StringVar(value="Scanning…")
        tk.Label(self, textvariable=self._stats_var, anchor=tk.W, padx=8,
                 relief=tk.GROOVE, bg="#ecf0f1",
                 font=("TkDefaultFont", 9, "bold")).pack(side=tk.TOP, fill=tk.X)

    def _build_tree(self) -> None:
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(frame, columns=self.COLUMNS,
                                  show="headings", selectmode="extended")

        for col, header, width in zip(self.COLUMNS, self.COL_HEADERS, self.COL_WIDTHS):
            self._tree.heading(col, text=header,
                               command=lambda c=col: self._sort_by(c))
            self._tree.column(col, width=width, anchor=tk.W,
                              stretch=(col == "cmd"))

        self._tree.tag_configure(self.TAG_OCCUPIED, background="#fde8e8")

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)

        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self._tree.bind("<Double-1>", lambda _e: self._inspect_selected())

    def _build_status_bar(self) -> None:
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var, anchor=tk.W, padx=8,
                 relief=tk.SUNKEN).pack(side=tk.BOTTOM, fill=tk.X)

    # ── data refresh ─────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        self._set_status("Scanning all ports…")
        threading.Thread(target=self._fetch_and_update, daemon=True).start()

    def _fetch_and_update(self) -> None:
        bindings = get_active_bindings()
        self.after(0, lambda: self._update_tree(bindings))

    def _update_tree(self, bindings: List[PortBinding]) -> None:
        index = build_port_index(bindings)
        total_occupied = len(index)
        total_free = PORT_MAX - PORT_MIN + 1 - total_occupied

        rows: List[Tuple] = []
        for b in bindings:
            rows.append((
                b.port,
                b.protocol,
                b.local_ip,
                str(b.pid) if b.pid is not None else "N/A",
                b.process_name,
                b.process_cmd or "",
            ))

        self._all_rows = rows
        self._stats_var.set(
            f"  Occupied: {total_occupied}   Free: {total_free}   "
            f"Total ports: {PORT_MAX}   "
            f"Last refresh: {datetime.now().strftime('%H:%M:%S')}"
        )
        self._apply_filter()
        self._set_status("Ready")
        self._schedule_auto_refresh()

    def _apply_filter(self) -> None:
        query = self._filter_var.get().strip().lower()
        for item in self._tree.get_children():
            self._tree.delete(item)

        for row in self._all_rows:
            if query and not any(query in str(v).lower() for v in row):
                continue
            self._tree.insert("", tk.END, values=row, tags=(self.TAG_OCCUPIED,))

    def _on_filter_change(self, *_args: object) -> None:
        self._apply_filter()

    # ── auto refresh ─────────────────────────────────────────────────────────

    def _schedule_auto_refresh(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None
        if self._auto_var.get():
            self._after_id = self.after(GUI_REFRESH_MS, self._refresh)

    def _toggle_auto(self) -> None:
        if self._auto_var.get():
            self._schedule_auto_refresh()
        elif self._after_id:
            self.after_cancel(self._after_id)
            self._after_id = None

    # ── sort ─────────────────────────────────────────────────────────────────

    def _sort_by(self, col: str) -> None:
        rows = [(self._tree.set(child, col), child) for child in self._tree.get_children("")]

        def sort_key(item: Tuple) -> object:
            val = item[0]
            if col in ("port", "pid"):
                try:
                    return int(val)
                except ValueError:
                    return -1
            return val.lower()

        rows.sort(key=sort_key)
        for idx, (_val, child) in enumerate(rows):
            self._tree.move(child, "", idx)

    # ── actions ──────────────────────────────────────────────────────────────

    def _selected_rows(self) -> List[Tuple]:
        return [self._tree.item(sel)["values"] for sel in self._tree.selection()]

    def _inspect_selected(self) -> None:
        selected = self._selected_rows()
        if not selected:
            messagebox.showinfo("Inspect", "Select a row first.")
            return

        lines: List[str] = []
        for row in selected:
            port, proto, local_addr, pid, process, cmd = row
            lines.append(
                f"Port {port}  {proto}  {local_addr}\n"
                f"PID: {pid}   Process: {process}\n"
                f"CMD: {cmd or '(unavailable)'}\n"
            )

        win = tk.Toplevel(self)
        win.title("Port Details")
        win.geometry("640x300")
        txt = tk.Text(win, wrap=tk.WORD, padx=8, pady=8)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.insert(tk.END, "\n─────────────────────────────────────\n".join(lines))
        txt.config(state=tk.DISABLED)
        tk.Button(win, text="Close", command=win.destroy).pack(pady=6)

    def _kill_selected(self) -> None:
        selected = self._selected_rows()
        if not selected:
            messagebox.showinfo("Kill", "Select a row first.")
            return

        pids: List[int] = []
        labels: List[str] = []
        for row in selected:
            port, proto, local_addr, pid_str, process, _cmd = row
            try:
                pids.append(int(pid_str))
                labels.append(f"Port {port} / {process} (PID {pid_str})")
            except (ValueError, TypeError):
                pass

        if not pids:
            messagebox.showwarning("Kill", "Selected rows have no resolvable PID.")
            return

        if not messagebox.askyesno(
            "Confirm Kill",
            "Kill these processes?\n\n" + "\n".join(labels),
            icon=messagebox.WARNING,
        ):
            return

        results = kill_pids(pids, force=False)
        messagebox.showinfo("Kill Result", "\n".join(results))
        self._refresh()

    # ── status ───────────────────────────────────────────────────────────────

    def _set_status(self, text: str) -> None:
        self._status_var.set(text)


def run_gui() -> None:
    app = PortsApp()
    app.mainloop()


# ── CLI ──────────────────────────────────────────────────────────────────────

def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ports_visualizer",
        description="Visualize occupied/free ports, inspect owners, and kill owning process.",
    )
    parser.add_argument("--start", type=int, default=PORT_MIN,
                        help="Start port (CLI scan/interactive).")
    parser.add_argument("--end", type=int, default=PORT_MAX,
                        help="End port (CLI scan/interactive).")

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("gui", help="Open tkinter GUI (default when no command given).")
    sub.add_parser("scan", help="Print scan report for range.")
    sub.add_parser("interactive", help="Interactive text mode.")

    who = sub.add_parser("who", help="Show process using one port.")
    who.add_argument("port", type=int)

    kill = sub.add_parser("kill", help="Kill process(es) using one port.")
    kill.add_argument("port", type=int)
    kill.add_argument("--force", action="store_true", help="kill() if terminate() times out.")
    kill.add_argument("--yes", action="store_true", help="Skip confirmation.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "scan":
            render_scan(args.start, args.end)
            return 0
        if args.command == "who":
            inspect_port(args.port)
            return 0
        if args.command == "kill":
            kill_by_port(port=args.port, force=args.force, yes=args.yes)
            return 0
        if args.command == "interactive":
            run_interactive(args.start, args.end)
            return 0
        # default: gui
        run_gui()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.")
        return 130
    except ValueError as err:
        print(f"Error: {err}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
