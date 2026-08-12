# SPDX-FileCopyrightText: 2024-present Adam Fourney <adamfo@microsoft.com>
#
# SPDX-License-Identifier: MIT
"""Command-line entry point: ``markitdown-ui``.

Starts the local web UI. By default it binds to 127.0.0.1 so the server is not
exposed to other machines on the network.
"""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="markitdown-ui",
        description="Launch the MarkItDown local web UI.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind to (default: 127.0.0.1, local only).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on (default: 8000).",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development.",
    )
    args = parser.parse_args()

    print(f"MarkItDown UI running at http://{args.host}:{args.port}")
    uvicorn.run(
        "markitdown_ui.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
