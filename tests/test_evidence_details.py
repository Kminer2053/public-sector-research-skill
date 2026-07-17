from __future__ import annotations

from psr_core.evidence import _content_quality, _excerpt
from psr_core.models import Passage


def test_excerpt_preserves_case_and_centers_matching_term() -> None:
    text = "Prefix " * 80 + "Human Oversight Requirement" + " Suffix" * 80

    excerpt = _excerpt(text, ["human oversight"], 120)

    assert len(excerpt) == 120
    assert "Human Oversight" in excerpt
    assert excerpt.startswith("…")
    assert excerpt.endswith("…")


def test_excerpt_without_match_uses_leading_text() -> None:
    text = "Official Guidance " * 80

    excerpt = _excerpt(text, ["missing-term"], 80)

    assert excerpt.startswith("Official Guidance")
    assert excerpt.endswith("…")
    assert len(excerpt) == 80


def test_content_quality_rejects_page_furniture() -> None:
    assert _content_quality(Passage(id="p1", text="로그인", locator="html:block:1")) == 0
    assert (
        _content_quality(
            Passage(
                id="p2",
                text="공공기관은 개인정보 보호지침과 보유기간을 검토한다.",
                locator="html:block:2",
            )
        )
        > 0
    )
