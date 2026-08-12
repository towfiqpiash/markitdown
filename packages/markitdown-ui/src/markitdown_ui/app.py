# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
#
# SPDX-License-Identifier: MIT
"""A minimal FastAPI web UI for converting files and URLs to Markdown.

The server exposes two JSON endpoints used by the single-page frontend:

* ``POST /api/convert``      -- convert an uploaded file
* ``POST /api/convert-url``  -- convert a http(s) URL (YouTube, Wikipedia, RSS, ...)

Everything is served from ``localhost`` and runs entirely on the local machine,
so all of MarkItDown's converters (including optional extras installed via
``markitdown[all]``) are available.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from markitdown import MarkItDown, StreamInfo
from markitdown._exceptions import (
    FileConversionException,
    UnsupportedFormatException,
)

STATIC_DIR = Path(__file__).parent / "static"


def _build_markitdown() -> MarkItDown:
    """Create a MarkItDown instance with the built-in converters only.

    Azure Document Intelligence is picked up from an environment variable when
    present so the UI can use it without hard-coding any secrets.
    """
    kwargs: dict = {}

    # Azure Document Intelligence -- used automatically when an endpoint is set.
    docintel_endpoint = os.getenv("DOCUMENT_INTELLIGENCE_ENDPOINT")
    if docintel_endpoint:
        kwargs["docintel_endpoint"] = docintel_endpoint

    return MarkItDown(**kwargs)


def create_app() -> FastAPI:
    app = FastAPI(title="MarkItDown UI", version="0.0.1")

    # Serve bundled assets (self-hosted Fraunces font, etc.) so the UI works
    # fully offline with no external network requests.
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        index_path = STATIC_DIR / "index.html"
        return HTMLResponse(index_path.read_text(encoding="utf-8"))

    @app.post("/api/convert")
    async def convert_file(
        file: UploadFile = File(...),
    ) -> JSONResponse:
        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

        md = _build_markitdown()

        # Give MarkItDown the filename/extension so type detection has good hints,
        # then convert straight from memory (no temp files touch disk).
        extension = os.path.splitext(file.filename or "")[1] or None
        stream_info = StreamInfo(
            filename=file.filename,
            extension=extension,
            mimetype=file.content_type,
        )

        try:
            result = md.convert_stream(io.BytesIO(raw), stream_info=stream_info)
        except UnsupportedFormatException as exc:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported file format: {exc}",
            )
        except FileConversionException as exc:
            raise HTTPException(status_code=422, detail=f"Conversion failed: {exc}")

        return JSONResponse(
            {
                "title": result.title,
                "markdown": result.markdown,
                "filename": file.filename,
            }
        )

    @app.post("/api/convert-url")
    async def convert_url(
        url: str = Form(...),
    ) -> JSONResponse:
        url = url.strip()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail="Please provide an http:// or https:// URL.",
            )

        md = _build_markitdown()

        try:
            result = md.convert_uri(url)
        except UnsupportedFormatException as exc:
            raise HTTPException(
                status_code=415,
                detail=f"Unsupported content: {exc}",
            )
        except FileConversionException as exc:
            raise HTTPException(status_code=422, detail=f"Conversion failed: {exc}")
        except Exception as exc:  # network errors, bad hosts, etc.
            raise HTTPException(status_code=400, detail=f"Could not fetch URL: {exc}")

        return JSONResponse(
            {
                "title": result.title,
                "markdown": result.markdown,
                "filename": url,
            }
        )

    return app


# Module-level instance so `uvicorn markitdown_ui.app:app` works out of the box.
app = create_app()
