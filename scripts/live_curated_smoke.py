"""Run the reviewed no-key source catalog against live official endpoints."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from psr_mcp.bootstrap import PublicContainer, build_container
from psr_mcp.config import Settings
from psr_mcp.public.service import PublicResearchError

_QUESTION = (
    "공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용, 업체 종속, "
    "개인정보와 사람의 감독 조건을 포함해줘"
)


async def _run() -> int:
    with tempfile.TemporaryDirectory(prefix="psr-curated-smoke-") as directory:
        root = Path(directory) / "ephemeral"
        settings = Settings.from_env(
            {
                "PSR_SERVICE_MODE": "public_ephemeral",
                "PSR_EPHEMERAL_ROOT": str(root),
                "PSR_SEARCH_PROVIDER": "curated",
            }
        )
        container = build_container(settings)
        if not isinstance(container, PublicContainer):
            raise RuntimeError("curated smoke requires the public container")
        await container.open()
        try:
            output = await container.quick_service.quick(
                question=_QUESTION,
                as_of_date=None,
                jurisdiction="KR",
                profile="government-v0",
            )
        except PublicResearchError as error:
            print(
                json.dumps(
                    {
                        "status": "ERROR",
                        "code": error.code,
                        "retryable": error.retryable,
                        "ephemeral_empty": _empty(root),
                    },
                    ensure_ascii=False,
                )
            )
            return 2
        finally:
            await container.close()

        print(
            json.dumps(
                {
                    "status": output.status,
                    "source_discovery": output.scope.source_discovery,
                    "tracks": output.scope.source_tracks,
                    "citation_count": len(output.citations),
                    "citation_tracks": sorted({citation.track_id for citation in output.citations}),
                    "source_hosts": sorted(
                        {urlsplit(str(citation.url)).hostname for citation in output.citations}
                    ),
                    "failure_codes": sorted({failure.code for failure in output.failures}),
                    "gap_count": len(output.gaps),
                    "server_saved": output.retention.server_saved,
                    "purge_state": output.retention.purge_state,
                    "ephemeral_empty": _empty(root),
                },
                ensure_ascii=False,
            )
        )
        return 0


def _empty(root: Path) -> bool:
    return root.is_dir() and not any(root.iterdir())


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
