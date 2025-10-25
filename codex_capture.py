#!/usr/bin/env python3
"""
Codex Capture TUI/CLI

A small text UI to make it easy to:
- Launch mitmweb with the capture addon (correct -s path, --set option)
- Launch the Flask web app to view the latest exchange
- Show helpful commands to route Codex traffic through the proxy

Usage:
  python3 codex_capture.py wizard      # guided setup
  python3 codex_capture.py start       # start mitmweb + webapp with defaults
  python3 codex_capture.py stop        # stop both
  python3 codex_capture.py status      # show status
  python3 codex_capture.py print-cmds  # print Codex env examples
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from typing import Optional, Tuple


BASE = Path(__file__).resolve().parent
ADDON = BASE / "mitm_addons" / "capture_codex.py"
CAPTURES = BASE / "captures"
RUN_DIR = BASE / ".run"
RUN_DIR.mkdir(exist_ok=True)


def _python_bin() -> str:
    venv_python = BASE / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable or "python3"


def _write_pid(name: str, pid: int) -> None:
    (RUN_DIR / f"{name}.pid").write_text(str(pid), encoding="utf-8")


def _read_pid(name: str) -> Optional[int]:
    p = RUN_DIR / f"{name}.pid"
    if not p.exists():
        return None
    try:
        return int(p.read_text().strip())
    except Exception:
        return None


def _kill_pid(pid: int) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def _spawn(cmd: list[str], log_path: Path, env: Optional[dict] = None) -> int:
    log_f = open(log_path, "ab", buffering=0)
    proc = subprocess.Popen(
        cmd,
        stdout=log_f,
        stderr=subprocess.STDOUT,
        env=env or os.environ.copy(),
        cwd=str(BASE),
    )
    return proc.pid


def start_mitmweb(listen_host: str = "127.0.0.1", port: int = 18110,
                  mode: str = "forward", upstream: str = "http://127.0.0.1:11434",
                  capture_dir: Optional[Path] = None) -> Tuple[int, list[str]]:
    capture_dir = capture_dir or CAPTURES
    capture_dir.mkdir(exist_ok=True)

    cmd = [
        "mitmweb",
        "--listen-host", listen_host,
        "-p", str(port),
        "-s", str(ADDON),
        "--set", f"codex_capture_dir={capture_dir}",
    ]
    if mode == "reverse":
        cmd.extend(["--mode", f"reverse:{upstream}"])

    pid = _spawn(cmd, RUN_DIR / "mitmweb.log")
    _write_pid("mitmweb", pid)
    return pid, cmd


def start_webapp(port: int = 5001) -> Tuple[int, list[str]]:
    env = os.environ.copy()
    env["PORT"] = str(port)
    py = _python_bin()
    cmd = [py, str(BASE / "webapp" / "app.py")]
    pid = _spawn(cmd, RUN_DIR / "webapp.log", env=env)
    _write_pid("webapp", pid)
    return pid, cmd


def stop(name: str) -> bool:
    pid = _read_pid(name)
    if not pid:
        return False
    _kill_pid(pid)
    # best-effort cleanup
    try:
        (RUN_DIR / f"{name}.pid").unlink()
    except Exception:
        pass
    return True


def status() -> str:
    lines = []
    for name in ("mitmweb", "webapp"):
        pid = _read_pid(name)
        if pid:
            lines.append(f"{name}: running (pid {pid})")
        else:
            lines.append(f"{name}: stopped")
    latest = CAPTURES / "latest.json"
    if latest.exists():
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest.stat().st_mtime))
        lines.append(f"latest capture: {latest} (updated {ts})")
    else:
        lines.append("latest capture: (none yet)")
    return "\n".join(lines)


def print_cmds(listen_host: str = "127.0.0.1", port: int = 18110) -> str:
    proxy = f"http://{listen_host}:{port}"
    lines = [
        "Route Codex OSS traffic via mitmweb:",
        f"HTTP_PROXY={proxy} HTTPS_PROXY={proxy} NO_PROXY= \\",
        "  codex exec --oss --model <your-ollama-model> \"say hello\"",
        "",
        "Interactive session:",
        f"HTTP_PROXY={proxy} HTTPS_PROXY={proxy} NO_PROXY= codex --oss --model <your-ollama-model>",
        "",
        "Sanity check curl through proxy:",
        f"HTTP_PROXY={proxy} curl -s http://127.0.0.1:11434/api/tags",
    ]
    return "\n".join(lines)


def wizard() -> int:
    print("Codex Capture Setup Wizard")
    print("Press Enter to accept defaults.")

    def ask(prompt: str, default: str) -> str:
        v = input(f"{prompt} [{default}]: ").strip()
        return v or default

    listen_host = ask("Listen host", "127.0.0.1")
    port_str = ask("Proxy port", "18110")
    mode = ask("Proxy mode (forward/reverse)", "forward")
    upstream = ask("Upstream (reverse only)", "http://127.0.0.1:11434")
    webapp_port_str = ask("Web app port", "5001")

    try:
        port = int(port_str)
        webapp_port = int(webapp_port_str)
    except ValueError:
        print("Invalid port.")
        return 2

    print("\nStarting mitmweb…")
    try:
        pid, cmd = start_mitmweb(listen_host, port, mode, upstream, CAPTURES)
        print("mitmweb started:")
        print("  ", " ".join(cmd))
        print(f"  log: {RUN_DIR / 'mitmweb.log'}")
    except FileNotFoundError:
        print("ERROR: 'mitmweb' not found on PATH. Install mitmproxy and try again.")
        return 1

    print("\nStarting web app…")
    try:
        pid2, cmd2 = start_webapp(webapp_port)
        print("webapp started:")
        print("  ", " ".join(cmd2))
        url = f"http://127.0.0.1:{webapp_port}/"
        print(f"  open: {url}")
        print(f"  log: {RUN_DIR / 'webapp.log'}")
        try:
            # Best-effort open in default browser for quick access.
            webbrowser.open_new_tab(url)
        except Exception:
            print("  (could not open browser automatically)")
    except FileNotFoundError:
        print("ERROR: Python not found. Ensure Python 3.9+ is installed.")
        return 1

    print("\nNext, route Codex traffic through the proxy:")
    print(print_cmds(listen_host, port))
    print("\nPress Ctrl+C to exit this wizard (processes keep running).")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nUse 'python3 codex_capture.py stop' to stop processes.")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Codex Capture TUI/CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("wizard", help="Run guided setup and start services")
    sub.add_parser("status", help="Show process status and latest capture info")
    sub.add_parser("stop", help="Stop mitmweb and webapp")
    p_start = sub.add_parser("start", help="Start mitmweb and webapp with defaults")
    p_start.add_argument("--mode", choices=["forward", "reverse"], default="forward")
    p_start.add_argument("--listen-host", default="127.0.0.1")
    p_start.add_argument("--port", type=int, default=18110)
    p_start.add_argument("--upstream", default="http://127.0.0.1:11434")
    p_start.add_argument("--webapp-port", type=int, default=5001)
    sub.add_parser("print-cmds", help="Print Codex env examples")

    args = ap.parse_args(argv)

    if args.cmd == "wizard":
        return wizard()
    if args.cmd == "status":
        print(status())
        return 0
    if args.cmd == "stop":
        a = stop("mitmweb")
        b = stop("webapp")
        print(f"mitmweb: {'stopped' if a else 'not running'}")
        print(f"webapp: {'stopped' if b else 'not running'}")
        return 0
    if args.cmd == "start":
        try:
            pid, cmd = start_mitmweb(args.listen_host, args.port, args.mode, args.upstream, CAPTURES)
            print("mitmweb started:", " ".join(cmd))
        except FileNotFoundError:
            print("ERROR: 'mitmweb' not found on PATH.")
            return 1
        try:
            pid2, cmd2 = start_webapp(args.webapp_port)
            print("webapp started:", " ".join(cmd2))
            print(f"open: http://127.0.0.1:{args.webapp_port}/")
        except FileNotFoundError:
            print("ERROR: Python not found.")
            return 1
        print("\n", print_cmds(args.listen_host, args.port))
        return 0
    if args.cmd == "print-cmds":
        print(print_cmds())
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
