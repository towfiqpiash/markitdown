# MarkItDown-UI

> [!IMPORTANT]
> MarkItDown-UI is meant for **local use**. By default the server binds to
> `127.0.0.1` and is not exposed to other machines on the network or the
> Internet. MarkItDown performs I/O with the privileges of the current process —
> do not bind the server to a public interface or point it at untrusted input
> without understanding the [security implications](../../README.md#security-considerations).

A minimal, self-contained web UI for the [`markitdown`](../markitdown) library.
Drag in a file (or paste a URL) and get Markdown back — with a live preview,
copy button, and `.md` download.

It is built on FastAPI and a single static HTML page (no frontend build step),
and depends on `markitdown[all]`, so **every** built-in converter is available:
PDF, Word, PowerPoint, Excel, images, audio, HTML, CSV/JSON/XML, EPUB, ZIP,
Outlook `.msg`, Jupyter notebooks, and URL sources like YouTube, Wikipedia,
and RSS.

## Installation

From the repository root (editable install, recommended while developing):

```bash
pip install -e packages/markitdown-ui
```

Or, once published:

```bash
pip install markitdown-ui
```

## Usage

Start the server:

```bash
markitdown-ui
```

Then open <http://127.0.0.1:8000> in your browser.

Options:

```bash
markitdown-ui --host 127.0.0.1 --port 8000 --reload
```

| Flag       | Default     | Description                                  |
| ---------- | ----------- | -------------------------------------------- |
| `--host`   | `127.0.0.1` | Interface to bind to (local only by default) |
| `--port`   | `8000`      | Port to listen on                            |
| `--reload` | off         | Auto-reload for development                  |

You can also run it directly with uvicorn:

```bash
uvicorn markitdown_ui.app:app
```

## Optional integrations

These are picked up automatically from the environment when set, mirroring the
core library's capabilities:

- **Azure Document Intelligence** — set `DOCUMENT_INTELLIGENCE_ENDPOINT` to route
  supported documents through Azure Document Intelligence.

## How it works

- `POST /api/convert` — accepts a multipart file upload and converts it from an
  in-memory stream via `MarkItDown.convert_stream()` (no temp files on disk).
- `POST /api/convert-url` — converts an `http(s)` URL via `MarkItDown.convert_uri()`.

The preview tab uses a tiny built-in renderer for convenience; the **Markdown**
tab and the download always contain the exact converter output.

## License

MIT
