"""Isolated command-line worker for pypdf extraction."""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
from collections.abc import Sequence

from psr_mcp.parsers.pdf_core import PdfCoreError, extract_pdf


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-input-bytes", type=int, required=True)
    parser.add_argument("--max-pages", type=int, required=True)
    parser.add_argument("--max-text-chars", type=int, required=True)
    parser.add_argument("--memory-bytes", type=int, required=True)
    parser.add_argument("--cpu-seconds", type=float, required=True)
    args = parser.parse_args(argv)
    _apply_resource_limits(
        memory_bytes=args.memory_bytes,
        cpu_seconds=args.cpu_seconds,
    )
    body = sys.stdin.buffer.read(args.max_input_bytes + 1)
    if len(body) > args.max_input_bytes:
        return _write(
            {
                "status": "error",
                "code": "INPUT_TOO_LARGE",
            }
        )
    try:
        result = extract_pdf(
            body,
            max_pages=args.max_pages,
            max_total_text_chars=args.max_text_chars,
        )
    except PdfCoreError as error:
        return _write(
            {
                "status": "error",
                "code": error.code.value,
            }
        )
    return _write(
        {
            "status": "ok",
            "title": result.title,
            "page_count": result.page_count,
            "pages": [
                {
                    "page_number": page.page_number,
                    "text": page.text,
                }
                for page in result.pages
            ],
        }
    )


def _apply_resource_limits(
    *,
    memory_bytes: int,
    cpu_seconds: float,
) -> None:
    cpu_limit = max(1, math.ceil(cpu_seconds))
    _set_limit(resource.RLIMIT_CPU, cpu_limit)
    _set_limit(resource.RLIMIT_NOFILE, 64)
    if sys.platform.startswith("linux"):
        _set_limit(resource.RLIMIT_AS, memory_bytes)


def _set_limit(kind: int, value: int) -> None:
    soft, hard = resource.getrlimit(kind)
    effective = value if hard == resource.RLIM_INFINITY else min(value, hard)
    if soft == resource.RLIM_INFINITY or effective < soft:
        resource.setrlimit(kind, (effective, hard))


def _write(payload: dict[str, object]) -> int:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    if len(encoded) > 8_388_608:
        encoded = b'{"status":"error","code":"RESOURCE_LIMIT"}'
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
