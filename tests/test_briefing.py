from __future__ import annotations

import pytest
from psr_core.briefing import BriefValidationError, validate_brief


def _brief(*, kind: str, citation_ids: list[str]) -> dict:
    return {
        "schema_version": "1.0",
        "title": "공공복리 조사보고서",
        "subtitle": "검증용 브리프",
        "executive_summary": [
            {
                "kind": kind,
                "text": "검증할 주장",
                "citation_ids": citation_ids,
            }
        ],
        "key_findings": [],
        "implications": [],
        "recommendations": [],
        "open_questions": [],
    }


@pytest.mark.parametrize("kind", ["FACT", "INFERENCE"])
def test_fact_and_inference_require_citations(kind: str) -> None:
    with pytest.raises(BriefValidationError, match="requires citation_ids"):
        validate_brief(_brief(kind=kind, citation_ids=[]), citation_ids=["cit-known"])


def test_unknown_citation_is_rejected() -> None:
    with pytest.raises(BriefValidationError, match="unknown citation IDs: cit-unknown"):
        validate_brief(
            _brief(kind="FACT", citation_ids=["cit-unknown"]),
            citation_ids=["cit-known"],
        )


def test_uncited_recommendation_is_allowed_and_normalized() -> None:
    payload = _brief(kind="RECOMMENDATION", citation_ids=[])
    payload["title"] = "  공공복리   조사보고서  "

    normalized = validate_brief(payload, citation_ids=[])

    assert normalized["title"] == "공공복리 조사보고서"
    assert normalized["executive_summary"][0]["kind"] == "RECOMMENDATION"
    assert normalized["executive_summary"][0]["citation_ids"] == []


def test_key_finding_ids_must_be_unique() -> None:
    payload = _brief(kind="FACT", citation_ids=["cit-known"])
    finding = {
        "id": "same-id",
        "title": "확인사항",
        "kind": "FACT",
        "text": "원문이 직접 지지하는 내용",
        "citation_ids": ["cit-known"],
    }
    payload["key_findings"] = [finding, finding.copy()]

    with pytest.raises(BriefValidationError, match="duplicate key_findings id"):
        validate_brief(payload, citation_ids=["cit-known"])
