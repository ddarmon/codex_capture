from mitmproxy import http, ctx  # type: ignore
import json
import os
import time
from typing import Any, Dict, List, Optional


def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None


def _parse_sse(body_text: str) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for line in body_text.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            events.append({"type": "done", "raw": line})
            continue
        obj = _safe_json_loads(payload)
        events.append({"type": "data", "raw": line, "json": obj})
    return events


def _reconstruct_assistant_text_from_events(events: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    for e in events:
        if e.get("type") != "data":
            continue
        obj = e.get("json") or {}
        for choice in obj.get("choices", []) or []:
            delta = choice.get("delta") or {}
            if isinstance(delta.get("content"), str):
                out.append(delta["content"])  # OpenAI-/Ollama-style content
            elif isinstance(delta.get("text"), str):
                out.append(delta["text"])  # Some providers stream as text
            # Some OSS providers put early thoughts into a "reasoning" field; we keep raw elsewhere
    return "".join(out)


_MOJIBAKE_MARKERS = ("Ã", "Â", "â", "œ", "ž", "¢", "€", "™", "�")


def _maybe_unmojibake(s: str) -> str:
    """Attempt to repair common UTF‑8/Latin‑1 mojibake (e.g., â€™ → ’).
    Strategy: if suspicious bytes are present, try latin1->utf8 roundtrip and
    accept if it reduces marker frequency.
    """
    if not s:
        return s
    orig_bad = sum(s.count(m) for m in _MOJIBAKE_MARKERS)
    if orig_bad == 0:
        return s
    try:
        cand = s.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
    except Exception:
        return s
    cand_bad = sum(cand.count(m) for m in _MOJIBAKE_MARKERS)
    return cand if cand_bad < orig_bad else s


class CodexCapture:
    def __init__(self) -> None:
        # Resolved lazily so we can honor addon options/env and avoid CWD pitfalls
        self.output_dir: Optional[str] = None

    def load(self, loader) -> None:
        loader.add_option(
            "codex_capture_filter",
            str,
            "",
            "Optional substring to match request URL to decide what to capture.",
        )
        loader.add_option(
            "codex_capture_dir",
            str,
            "",
            "Directory to store captures (default: <addon_dir>/../captures)",
        )

    def _ensure_output_dir(self) -> str:
        if self.output_dir:
            return self.output_dir
        opt_dir = getattr(ctx.options, "codex_capture_dir", "") or ""
        env_dir = os.environ.get("CODEX_CAPTURE_DIR", "")
        if opt_dir:
            base = opt_dir
        elif env_dir:
            base = env_dir
        else:
            addon_dir = os.path.dirname(os.path.abspath(__file__))
            base = os.path.abspath(os.path.join(addon_dir, os.pardir, "captures"))
        os.makedirs(base, exist_ok=True)
        self.output_dir = base
        return base

    def response(self, flow: http.HTTPFlow) -> None:
        # Only consider POSTs with JSON-like bodies that look like LLM calls
        req = flow.request
        resp = flow.response
        if not req or not resp:
            return

        if req.method.upper() != "POST":
            return

        try:
            req_body = req.get_text(strict=False)
        except Exception:
            req_body = ""

        # Heuristic: must contain a model field to be relevant
        if '"model"' not in req_body:
            return

        # Optional URL filter
        flt = ctx.options.codex_capture_filter or ""
        if flt and (flt not in req.url):
            return

        # Parse request JSON if possible
        req_json = _safe_json_loads(req_body)

        # Extract response text
        try:
            resp_body = resp.get_text(strict=False)
        except Exception:
            resp_body = (resp.raw_content or b"").decode("utf-8", errors="replace")

        resp_ct = (resp.headers.get("content-type") or "").lower()
        is_sse = ("text/event-stream" in resp_ct) or resp_body.lstrip().startswith("data:")

        events: Optional[List[Dict[str, Any]]] = None
        assistant_text = ""
        if is_sse:
            events = _parse_sse(resp_body)
            assistant_text = _reconstruct_assistant_text_from_events(events)
        else:
            # Try to reconstruct from non-streaming JSON
            resp_obj = _safe_json_loads(resp_body)
            if isinstance(resp_obj, dict) and "choices" in resp_obj:
                for ch in resp_obj.get("choices", []) or []:
                    msg = ch.get("message") or {}
                    if isinstance(msg.get("content"), str):
                        assistant_text += msg["content"]
                    elif isinstance(ch.get("text"), str):
                        assistant_text += ch["text"]

        # Repair common mojibake in reconstructed text (preview only)
        assistant_text_fixed = _maybe_unmojibake(assistant_text)

        # Aggregate assistant reasoning, if present
        reasoning_text = ""
        if is_sse and events:
            for e in events:
                if e.get("type") != "data":
                    continue
                obj = e.get("json") or {}
                for choice in obj.get("choices", []) or []:
                    d = choice.get("delta") or {}
                    if isinstance(d.get("reasoning"), str):
                        reasoning_text += d["reasoning"]
        else:
            resp_obj = _safe_json_loads(resp_body)
            if isinstance(resp_obj, dict):
                for ch in (resp_obj.get("choices") or []):
                    if isinstance(ch.get("reasoning"), str):
                        reasoning_text += ch["reasoning"]
                    msg = ch.get("message") or {}
                    if isinstance(msg.get("reasoning"), str):
                        reasoning_text += msg["reasoning"]
                if not reasoning_text and isinstance(resp_obj.get("reasoning"), str):
                    reasoning_text = resp_obj.get("reasoning")
        reasoning_text_fixed = _maybe_unmojibake(reasoning_text)

        # Build a concise summary for the web app
        model = None
        messages_count = 0
        last_user = None
        sys_chars = 0
        tools_count = 0
        stream_flag = False
        if isinstance(req_json, dict):
            model = req_json.get("model")
            msgs = req_json.get("messages") or []
            if isinstance(msgs, list):
                messages_count = len(msgs)
                for m in reversed(msgs):
                    if isinstance(m, dict) and m.get("role") == "user":
                        last_user = m.get("content")
                        break
                sys_chars = sum(
                    len(m.get("content"))
                    for m in msgs
                    if isinstance(m, dict)
                    and m.get("role") == "system"
                    and isinstance(m.get("content"), str)
                )
            tools = req_json.get("tools") or []
            if isinstance(tools, list):
                tools_count = len(tools)
            stream_flag = bool(req_json.get("stream"))

        summary: Dict[str, Any] = {
            "endpoint": req.url,
            "method": req.method,
            "model": model,
            "messages_count": messages_count,
            "last_user_message_preview": (last_user[:300] + "…") if isinstance(last_user, str) and len(last_user) > 300 else last_user,
            "system_prompt_chars": sys_chars,
            "tools_count": tools_count,
            "status_code": resp.status_code,
            "is_stream": is_sse or stream_flag,
            "assistant_text_preview": (assistant_text_fixed[:800] + ("…" if len(assistant_text_fixed) > 800 else "")) if assistant_text_fixed else None,
            "assistant_reasoning_preview": (reasoning_text_fixed[:800] + ("…" if len(reasoning_text_fixed) > 800 else "")) if reasoning_text_fixed else None,
            "duration_ms": int(1000 * ((flow.response.timestamp_end or time.time()) - (flow.request.timestamp_start or time.time()))),
        }

        payload: Dict[str, Any] = {
            "timestamp": time.time(),
            "summary": summary,
            "request": {
                "url": req.url,
                "method": req.method,
                "headers": dict(req.headers),
                "body_text": req_body,
                "json": req_json,
            },
            "response": {
                "status_code": resp.status_code,
                "headers": dict(resp.headers),
                "body_text": resp_body,
                "events": events,
            },
        }

        try:
            outdir = self._ensure_output_dir()
            # Write latest artifacts
            with open(os.path.join(outdir, "latest.json"), "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            with open(os.path.join(outdir, "latest.request.json"), "w", encoding="utf-8") as f:
                if isinstance(req_json, dict):
                    json.dump(req_json, f, ensure_ascii=False, indent=2)
                else:
                    f.write(req_body)
            with open(os.path.join(outdir, "latest.response.txt"), "w", encoding="utf-8") as f:
                f.write(resp_body)
            # Append to history
            with open(os.path.join(outdir, "history.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
            ctx.log.info(f"Captured Codex/Ollama flow: {model} {resp.status_code}")
        except Exception as e:
            ctx.log.warn(f"codex-capture: failed writing files: {e}")


addons = [CodexCapture()]
