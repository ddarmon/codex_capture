from __future__ import annotations

import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, render_template, send_from_directory, abort, jsonify


BASE_DIR = Path(__file__).resolve().parent.parent
CAPTURES_DIR = BASE_DIR / "captures"

app = Flask(__name__, template_folder="templates", static_folder="static")


def read_latest() -> Dict[str, Any] | None:
    path = CAPTURES_DIR / "latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _read_history_lines() -> List[str]:
    p = CAPTURES_DIR / "history.jsonl"
    if not p.exists():
        return []
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []


def read_history_meta(max_items: int = 25) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """Return a list of recent history entries (meta only) and the last index.
    Each item: {idx, ts, ts_iso, model, status}
    """
    lines = _read_history_lines()
    n = len(lines)
    items: List[Dict[str, Any]] = []
    last_idx: Optional[int] = n - 1 if n > 0 else None
    # take last max_items items
    start = max(0, n - max_items)
    for i in range(start, n):
        try:
            obj = json.loads(lines[i])
        except Exception:
            continue
        ts = float(obj.get("timestamp", 0)) if isinstance(obj, dict) else 0.0
        ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else ""
        model = (obj.get("summary") or {}).get("model") if isinstance(obj, dict) else None
        status = (obj.get("summary") or {}).get("status_code") if isinstance(obj, dict) else None
        items.append({
            "idx": i,
            "ts": ts,
            "ts_iso": ts_iso,
            "model": model,
            "status": status,
        })
    return items, last_idx


def read_capture_by_idx(idx: int) -> Optional[Dict[str, Any]]:
    lines = _read_history_lines()
    if idx < 0 or idx >= len(lines):
        return None
    try:
        return json.loads(lines[idx])
    except Exception:
        return None


@app.route("/")
def index() -> str:
    data = read_latest()
    latest_path = CAPTURES_DIR / "latest.json"
    last_mtime = latest_path.stat().st_mtime if latest_path.exists() else 0
    last_mtime_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_mtime)) if last_mtime else "—"
    history, last_idx = read_history_meta()
    # current view is latest; use history's last index as current_idx if present
    current_idx = last_idx
    view_ts = float(data.get("timestamp", 0)) if isinstance(data, dict) else 0.0
    view_ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(view_ts)) if view_ts else "—"
    prev_idx = (current_idx - 1) if (current_idx is not None and current_idx > 0) else None
    next_idx = None  # already latest
    return render_template(
        "index.html",
        data=data,
        last_mtime=last_mtime,
        last_mtime_iso=last_mtime_iso,
        history=history,
        current_idx=current_idx,
        prev_idx=prev_idx,
        next_idx=next_idx,
        view_ts_iso=view_ts_iso,
        is_latest=True,
    )


@app.route("/capture/<int:idx>")
def capture_by_idx(idx: int):
    data = read_capture_by_idx(idx)
    if not data:
        abort(404)
    latest_path = CAPTURES_DIR / "latest.json"
    last_mtime = latest_path.stat().st_mtime if latest_path.exists() else 0
    last_mtime_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_mtime)) if last_mtime else "—"
    history, last_idx = read_history_meta()
    prev_idx = idx - 1 if idx > 0 else None
    next_idx = idx + 1 if (last_idx is not None and idx < last_idx) else None
    view_ts = float(data.get("timestamp", 0)) if isinstance(data, dict) else 0.0
    view_ts_iso = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(view_ts)) if view_ts else "—"
    return render_template(
        "index.html",
        data=data,
        last_mtime=last_mtime,
        last_mtime_iso=last_mtime_iso,
        history=history,
        current_idx=idx,
        prev_idx=prev_idx,
        next_idx=next_idx,
        view_ts_iso=view_ts_iso,
        is_latest=(last_idx is not None and idx == last_idx),
    )


@app.route("/raw/latest.json")
def raw_latest_json():
    path = CAPTURES_DIR / "latest.json"
    if not path.exists():
        abort(404)
    return send_from_directory(CAPTURES_DIR, path.name, mimetype="application/json")


@app.route("/raw/request")
def raw_request():
    path = CAPTURES_DIR / "latest.request.json"
    if not path.exists():
        abort(404)
    return send_from_directory(CAPTURES_DIR, path.name)


@app.route("/raw/response")
def raw_response():
    path = CAPTURES_DIR / "latest.response.txt"
    if not path.exists():
        abort(404)
    return send_from_directory(CAPTURES_DIR, path.name)


@app.route("/api/last-updated")
def api_last_updated():
    latest_path = CAPTURES_DIR / "latest.json"
    last_mtime = latest_path.stat().st_mtime if latest_path.exists() else 0
    return jsonify({"mtime": last_mtime})


if __name__ == "__main__":
    # Minimal dev server
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="127.0.0.1", port=port, debug=True)
