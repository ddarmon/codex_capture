# Intercept Codex CLI ↔︎ Ollama traffic with mitmproxy

This document explains how to capture Codex CLI traffic to a local
Ollama server using mitmproxy/mitmweb. It starts with the working
approach, then notes what didn't work and why.

## Prerequisites

You need the Codex CLI, an Ollama server with at least one model pulled,
mitmproxy/mitmweb, and Python 3.9+ with venv/pip support. All commands
below assume a bash-compatible shell on macOS or Linux.

### Codex CLI

Install the Codex CLI using the instructions provided with your Codex
account (outside the scope of this repo). Confirm it is available:

``` bash
codex --help
```

### Ollama

-   macOS (Homebrew):

    ``` bash
    brew install ollama
    ```

-   macOS or Linux (official script):

    ``` bash
    curl -fsSL https://ollama.com/install.sh | sh
    ```

After installation, pull at least one model you plan to use (e.g.,
`qwen3-coder:latest`, `gpt-oss:20b`):

``` bash
ollama pull <model-name>
```

Ensure Ollama runs locally on port 11434 (default) and consider using
the environment variables shown later when starting the server.

### mitmproxy / mitmweb

Install mitmproxy (which ships with mitmweb) using one of:

-   macOS (Homebrew):

    ``` bash
    brew install mitmproxy
    ```

-   macOS or Linux (pipx):

    ``` bash
    python3 -m pip install --user pipx
    python3 -m pipx install mitmproxy
    ```

Verify the install:

``` bash
mitmweb --version
```

### Python environment

Python 3.9 or newer is required to run the helper CLI and the Flask web
app.

-   macOS (Homebrew):

    ``` bash
    brew install python@3.11
    ```

-   Debian/Ubuntu (APT):

    ``` bash
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip
    ```

Inside this repository create a virtual environment (optional but
recommended) and install Flask for the web UI:

``` bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install flask
```

### Quick checklist

Before proceeding, ensure all dependencies respond:

``` bash
codex --help            # Codex CLI available
ollama --version        # Ollama installed
ollama list             # Shows pulled models
mitmweb --version       # mitmproxy/mitmweb available
python3 --version       # Python 3.9+
```

Ports used by this setup:

-   Ollama default HTTP API: `127.0.0.1:11434`
-   mitmweb forward proxy: `127.0.0.1:18110`
-   mitmweb UI: `127.0.0.1:8081`
-   Flask web UI: `127.0.0.1:5001`

Free or reconfigure these ports if other services occupy them.

## What Works (recommended)

Use mitmweb as a forward proxy and force Codex's OSS provider HTTP
through it.

### Start the `ollama` server

``` bash
OLLAMA_CONTEXT_LENGTH=65536 OLLAMA_FLASH_ATTENTION=1 ollama serve
```

### Start mitmweb (forward proxy)

``` bash
mitmweb --listen-host 127.0.0.1 -p 18110
```

### Route Codex's OSS traffic through the proxy and clear `NO_PROXY` so localhost traffic is not bypassed

-   One‑shot command example:

``` bash
HTTP_PROXY=http://127.0.0.1:18110 \
HTTPS_PROXY=http://127.0.0.1:18110 \
NO_PROXY= \
  codex exec --oss --model <your-ollama-model> "say hello"
```

-   Interactive session example:

``` bash
HTTP_PROXY=http://127.0.0.1:18110 \
HTTPS_PROXY=http://127.0.0.1:18110 \
NO_PROXY= \
  codex --oss --model <your-ollama-model>
```

-   Example with the model the session used:

``` bash
HTTP_PROXY=http://127.0.0.1:18110 \
HTTPS_PROXY=http://127.0.0.1:18110 \
NO_PROXY= \
  codex exec --oss --model gpt-oss:20b "say hello"
```

### Verify traffic shows in mitmweb UI (default: http://127.0.0.1:8081/)

You should see requests to `http://127.0.0.1:11434/...` routed via the
proxy.

### Optional: sanity check with curl through the same proxy

``` bash
HTTP_PROXY=http://127.0.0.1:18110 curl -s http://127.0.0.1:11434/api/tags
```

### Notes

-   Clearing `NO_PROXY` is crucial; many tools bypass proxies for
    `127.0.0.1` by default.
-   Use an installed Ollama model tag (e.g., `llama3.1:8b-instruct`,
    `qwen2.5:14b-instruct`, or your own). Substitute for
    `<your-ollama-model>`.
-   This approach requires no TLS interception because local Ollama
    typically runs over HTTP.

## What Didn't Work (and why)

-   Using `OPENAI_BASE_URL` with `--oss`:
    -   The `--oss` provider talks to Ollama's native API and ignores
        OpenAI env vars, so requests did not route via the `/v1` base
        URL.
-   Using the OpenAI provider with Ollama's OpenAI‑compatible port
    (`-c model_provider=openai` plus
    `OPENAI_BASE_URL=http://127.0.0.1:18110/v1`):
    -   Codex's OpenAI integration often calls the new OpenAI Responses
        API endpoint (`/v1/responses`). Ollama does not implement
        `/v1/responses`, causing `404 page not found` in mitmproxy.
-   Reverse proxying to Ollama and trying to point the OSS provider at
    it (e.g., `mitmproxy --mode reverse:http://127.0.0.1:11434 ...`
    together with `OLLAMA_HOST=...` or attempting an `oss.base_url`
    override):
    -   In this Codex build, `OLLAMA_HOST` had no effect and the
        attempted override didn't take. No traffic appeared in the
        proxy.
-   `OPENAI_*` env vars while using `--oss`:
    -   Not applicable; the OSS provider doesn't read these.

## Troubleshooting

-   No flows in mitmweb:
    -   Ensure `NO_PROXY` is empty, so `127.0.0.1` is not bypassed.
    -   Confirm mitmweb is listening (`127.0.0.1:18110`) and Ollama is
        reachable at `127.0.0.1:11434`.
    -   Smoke test the proxy path:
        `HTTP_PROXY=http://127.0.0.1:18110 curl -s http://127.0.0.1:11434/api/tags`.
    -   Verify the model exists: `ollama list`.
    -   Use `--oss` so Codex talks to Ollama's native API (not the
        OpenAI provider).
-   Want to intercept all Codex HTTP(S) for debugging:
    -   Keep mitmweb as a forward proxy and set `HTTP_PROXY/HTTPS_PROXY`
        with `NO_PROXY=`. This covers calls to localhost services too.

------------------------------------------------------------------------

## Simple Web App to View Latest Request/Response

This repo also includes a tiny web app and a mitmproxy addon to display
the latest captured Codex ↔ Ollama request/response pair in both
human‑readable and API‑native forms.

Files:

-   `mitm_addons/capture_codex.py` --- mitmproxy addon that writes the
    latest exchange to `captures/`.
-   `webapp/app.py` --- Flask web server to render the latest exchange.
-   `webapp/templates/index.html`, `webapp/static/style.css` --- UI.

### Option A: Use the built-in TUI/CLI (recommended)

``` bash
python3 codex_capture.py wizard
```

This guides you through starting mitmweb and the web app and prints the
correct Codex proxy commands.

Use the helper to manage processes:

-   Start guided setup:
    `python3 codex_capture.py wizard`
-   Start with defaults:
    `python3 codex_capture.py start`
-   Stop both: `python3 codex_capture.py stop`
-   Status: `python3 codex_capture.py status`
-   Print Codex proxy commands:
    `python3 codex_capture.py print-cmds`

The helper ensures the addon `-s` path is correct and passes
`--set codex_capture_dir=…` so files land in
`captures` for the web UI.

### Option B: Manual start

``` bash
mitmweb --listen-host 127.0.0.1 -p 18110 \
  -s mitm_addons/capture_codex.py \
  --set codex_capture_dir="$(pwd)/captures"
```

#### Route Codex traffic through the proxy (clear `NO_PROXY`):

``` bash
HTTP_PROXY=http://127.0.0.1:18110 \
HTTPS_PROXY=http://127.0.0.1:18110 \
NO_PROXY= \
  codex exec --oss --model <your-ollama-model> "say hello"
```

#### Install and run the web app (Python 3.9+):

``` bash
python3 -m venv .venv
. .venv/bin/activate
pip install flask
python3 webapp/app.py
```

#### Open the UI: http://127.0.0.1:5001/

### Notes

-   The addon writes:
    -   `captures/latest.json` (combined summary + raw)
    -   `captures/latest.request.json` (request body or JSON)
    -   `captures/latest.response.txt` (raw response --- SSE stream for
        streaming requests)
    -   `captures/history.jsonl` (append‑only history)
-   You can limit captured flows to matching URLs with
    `-o codex_capture_filter=11434` (or any substring).
-   The addon now writes to the directory given by the
    `codex_capture_dir` option (or env `CODEX_CAPTURE_DIR`). If not set,
    it defaults to `<addon_dir>/../captures`.
