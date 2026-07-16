from __future__ import annotations

from psr_core.evidence import _excerpt


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
