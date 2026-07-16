"""Print a local human-review packet for the live curated research path."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from psr_mcp.bootstrap import PublicContainer, build_container
from psr_mcp.config import Settings
from psr_mcp.public.review import evaluate_structural_review, render_human_review_packet
from psr_mcp.public.service import PublicResearchError

_QUESTION = (
    "공공기관 AI 구매 원칙에 데이터 권리, 학습 재사용, 업체 종속, "
    "개인정보와 사람의 감독 조건을 포함해줘"
)


async def _run() -> int:
    with tempfile.TemporaryDirectory(prefix="psr-curated-review-") as directory:
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
            raise RuntimeError("curated review requires the public container")
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

        print(render_human_review_packet(question=_QUESTION, output=output))
        return 0 if evaluate_structural_review(output).passed and _empty(root) else 3


def _empty(root: Path) -> bool:
    return root.is_dir() and not any(root.iterdir())


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
