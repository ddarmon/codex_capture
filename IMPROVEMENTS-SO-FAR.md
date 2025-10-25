# Improvements So Far

A running log of enhancements made to the Codex↔Ollama capture app
(mitmproxy addon + Flask UI + TUI helper). Entries are grouped by area
and roughly in the order delivered.

## Continue From

```bash
codex resume 019a1b45-a585-7953-ad85-06c46f1616f3
```

## Capture Addon (mitmproxy)

-   Added `mitm_addons/capture_codex.py` to persist
    the latest exchange and append to history:
    -   Writes to `captures/latest.json`,
        `captures/latest.request.json`, `captures/latest.response.txt`,
        and `captures/history.jsonl`.
    -   Stable output directory resolution:
        -   New option `--set codex_capture_dir=…` and env
            `CODEX_CAPTURE_DIR`.
        -   Defaults to `<addon_dir>/../captures` to avoid CWD
            surprises.
    -   Optional URL filter: `--set codex_capture_filter="<substring>"`.
    -   Correctly detects streaming (`text/event-stream`) and parses SSE
        lines into events.
    -   Reconstructs assistant content for previews from SSE deltas or
        non‑streaming JSON.
    -   Reconstructs assistant reasoning (when present in SSE deltas or
        JSON) and exposes it as a preview.
    -   Mojibake fixer for previews (UTF‑8/Latin‑1 round‑trip) to repair
        quotes/dashes.

## TUI / CLI Helper

-   Added `codex_capture.py` for one‑command setup:
    -   `wizard` guided flow to start mitmweb with the addon and the web
        app.
    -   `start`/`stop`/`status`/`print-cmds` commands.
    -   Ensures correct `-s` path, passes `--set codex_capture_dir=…`,
        and writes logs to `.run/`.

## Web App (Flask)

-   Added `webapp/app.py` with endpoints:
    -   `/` shows latest capture; `/capture/<idx>` opens a specific
        history entry.
    -   `/raw/latest.json`, `/raw/request`, `/raw/response` for direct
        downloads.
    -   `/api/last-updated` returns `mtime` for change‑detection based
        auto‑refresh.
-   Templates & static assets in
    `webapp/templates/index.html` and
    `webapp/static/style.css`.

## UI/UX -- Summary & Toolbar

-   Reworked summary into a proper two‑column key:value grid; consistent
    spacing and typography.
-   Added badges: method, HTTP status (color‑coded), stream/batch,
    model.
-   Improved toolbar spacing; long endpoint truncation with tooltip.

## Encoding & Preview Quality

-   Implemented mojibake repair for previews (quotes/dashes render
    cleanly).

## Auto‑Refresh

-   Initial simple hard‑reload refresh interval control
    (Off/5s/10s/30s + Pause/Resume).
-   Upgraded to change‑detection: poll `/api/last-updated` and reload
    only when `latest.json` changes.

## API‑Native View

-   JSON viewers for request/response:
    -   Toggle Tree/Raw, collapsible details/summary tree, monospace
        styling.
    -   Copy button for pretty JSON.
    -   Expand all / Collapse all controls.
-   SSE (streaming) responses:
    -   Raw SSE view with Copy.
    -   Timeline visualization with per‑chunk content vs reasoning
        columns.
    -   Controls: show/hide columns, wrap toggle, scroll‑to‑last,
        aggregated Copy content/reasoning, basic stats (chunk count,
        char counts).

## Conversation View

-   Render request `messages` as chat bubbles with role pills
    (user/assistant/system/tool).
-   System messages hidden by default; "Show system" toggle (persisted
    in localStorage).
-   Tooling:
    -   Inline chips for assistant `tool_calls` (function name + args
        preview, tooltip with full args).
    -   Collapsible raw JSON for `tool_calls`.
-   Assistant output & reasoning surfaced:
    -   Aggregates reasoning and content from SSE/JSON.
    -   Adds an "assistant reasoning" bubble followed by an "assistant"
        content bubble.
    -   Prefers reconstructed preview text to ensure consistency with
        the Summary.

## Previews Ordering

-   In Summary, "Assistant reasoning (reconstructed preview)" now
    appears above "Assistant output (reconstructed preview)". Both have
    Copy buttons.

## Documentation

-   `README.md` updated with:
    -   Working proxy approach (forward proxy with
        `HTTP_PROXY/HTTPS_PROXY` and `NO_PROXY=`).
    -   TUI/CLI usage and manual commands.
    -   Web app overview and paths.

## Notes & Rationale

-   Consistency: the conversation view prefers the same reconstructed
    text used in the preview, so both sections match.
-   Safety: raw response is preserved exactly; previews are
    annotated/cleaned for readability without altering source artifacts.
-   Portability: mitm addon no longer depends on the shell CWD; explicit
    `codex_capture_dir` makes behavior predictable.

## Potential Next Steps

-   Export/share: "Download bundle" (request/response/timeline/summary)
    as a ZIP.
-   Per‑chunk timestamps (if available in SSE) and simple diffing
    between neighbor chunks.
-   Quick filters: show only reasoning, only content, or only tool‑calls
    in the conversation.
-   Optional dark mode using CSS variables.
