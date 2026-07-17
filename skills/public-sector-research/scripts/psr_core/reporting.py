# ruff: noqa: E501
"""Human-reviewable Markdown, HTML, and JSON result rendering."""

from __future__ import annotations

import html
from typing import Any, Dict, List, Mapping, Sequence
from urllib.parse import quote, urlsplit

from psr_core.briefing import build_default_brief
from psr_core.models import Citation, Failure, ResearchPlan


def build_result_payload(
    *,
    plan: ResearchPlan,
    status: str,
    citations: List[Citation],
    gaps: List[str],
    failures: List[Failure],
    reused_sources: int,
    collected_sources: int,
    deduplicated_count: int,
) -> Dict[str, Any]:
    official_primary = sum(
        citation.source_tier == "OFFICIAL_PRIMARY" for citation in citations
    )
    summary = (
        f"검토 가능한 원문 구간 {len(citations)}건을 확보했습니다. "
        f"공식 1차자료 인용은 {official_primary}건이며, "
        f"새로 수집한 출처 {collected_sources}건과 "
        f"재사용한 출처 {reused_sources}건을 반영했습니다. "
        "자동 결과는 법률·감사·조달의 최종 판단이 아니라 사람이 검토할 근거 패키지입니다."
    )
    return {
        "schema_version": "1.0",
        "run_id": plan.id,
        "status": status,
        "summary": summary,
        "scope": {
            "question": plan.question,
            "as_of_date": plan.as_of_date,
            "jurisdiction": plan.jurisdiction,
            "profile": plan.profile,
            "tracks": [track.id for track in plan.tracks],
            "completion_criteria": plan.completion_criteria,
            "stop_conditions": {
                "max_sources": plan.stop_conditions.max_sources,
                "max_bytes": plan.stop_conditions.max_bytes,
                "timeout_seconds": plan.stop_conditions.timeout_seconds,
                "require_official_primary": plan.stop_conditions.require_official_primary,
            },
        },
        "metrics": {
            "citation_count": len(citations),
            "official_primary_count": official_primary,
            "reused_source_count": reused_sources,
            "collected_source_count": collected_sources,
            "deduplicated_passage_count": deduplicated_count,
        },
        "citations": [citation.to_dict() for citation in citations],
        "gaps": gaps,
        "failures": [failure.to_dict() for failure in failures],
        "review": {
            "required": True,
            "facts_are_extractive": True,
            "inference_generated": False,
            "recommendation_generated": False,
            "notice": "원문의 적용범위·현행성·상충 여부를 업무담당자가 확인해야 합니다.",
        },
    }


def render_markdown(
    *,
    plan: ResearchPlan,
    payload: Dict[str, Any],
    citations: List[Citation],
    gaps: List[str],
    failures: List[Failure],
    brief: Dict[str, Any] | None = None,
) -> str:
    brief = brief or build_default_brief(plan=plan, citations=citations, gaps=gaps)
    track_titles = {track.id: track.title for track in plan.tracks}
    lines = [
        f"# {_md(brief['title'])}",
        "",
        _md(brief.get("subtitle", "")),
        "",
        f"> **조사상태 {_md(payload['status'])}** · 기준일 {_md(plan.as_of_date)} · "
        f"공식 1차자료 {payload['metrics']['official_primary_count']}건 · "
        f"확인한 원문 구간 {len(citations)}건",
        "",
        "## 한눈에 보기",
        "",
    ]
    lines.extend(_markdown_items(brief.get("executive_summary", [])))
    if not brief.get("executive_summary"):
        lines.append("- 요약할 수 있는 검증된 원문 구간이 없습니다.")
    lines.extend(["", "## 핵심 확인사항", ""])
    for index, item in enumerate(brief.get("key_findings", []), 1):
        lines.extend(
            [
                f"### {index}. {_md(item.get('title', '확인사항'))}",
                "",
                _kind_label(item["kind"]),
                "",
                f"{_md(item['text'])} {_markdown_citations(item['citation_ids'])}",
                "",
            ]
        )
    if not brief.get("key_findings"):
        lines.extend(["검증된 핵심 확인사항이 없습니다.", ""])
    for title, key in (("업무 시사점", "implications"), ("검토 권고", "recommendations")):
        items = brief.get(key, [])
        if items:
            lines.extend([f"## {title}", ""])
            lines.extend(_markdown_items(items))
            lines.append("")
    lines.extend(["## 조사 범위", ""])
    for track in plan.tracks:
        lines.append(f"- **{_md(track.title)}**: {_md(track.research_question)}")
    lines.extend(["", "## 원문 근거", ""])
    if not citations:
        lines.append("인용 가능한 원문 구간을 확보하지 못했습니다.")
    for citation in citations:
        score = citation.score
        source_link = _markdown_source_link(citation.source_locator)
        snapshot = (
            f" · 로컬 보존본 `{citation.local_snapshot_path}`"
            if citation.local_snapshot_path
            else ""
        )
        lines.extend(
            [
                f"<a id=\"evidence-{citation.id}\"></a>",
                f"### [{citation.id}] "
                f"{_md(track_titles.get(citation.track_id, citation.track_id))}",
                "",
                f"- 문서: {_md(citation.publisher)}, 「{_md(citation.title)}」",
                f"- 원문: {source_link}{snapshot}",
                f"- 원문 위치: `{citation.locator}`",
                f"- 수집시점: {citation.retrieved_at}",
                f"- 출처등급: `{citation.source_tier}`",
                f"- 문서 SHA-256: `{citation.document_sha256}`",
                (
                    "- 근거 점수: "
                    f"**{score.overall:.2f}** "
                    f"(권위 {score.authority.value:.2f}, "
                    f"1차성 {score.primary_source.value:.2f}, "
                    f"직접성 {score.direct_relevance.value:.2f}, "
                    f"최신성 {score.freshness.value:.2f})"
                ),
                "",
                f"> {_md(citation.excerpt)}",
                "",
            ]
        )
    lines.extend(["## 확인이 더 필요한 사항", ""])
    open_questions = list(dict.fromkeys([*brief.get("open_questions", []), *gaps]))
    if not open_questions:
        lines.append("- 자동 검사에서 추가 조사 공백을 발견하지 못했습니다.")
    else:
        lines.extend(f"- {_md(gap)}" for gap in open_questions)
    lines.extend(["", "## 수집 중 발생한 문제", ""])
    if not failures:
        lines.append("- 기록된 수집·파싱 실패가 없습니다.")
    else:
        for failure in failures:
            retry = "재시도 가능" if failure.retryable else "재시도 비권장"
            lines.append(
                f"- `{_md(failure.code)}` · {_md(failure.track_id)} · "
                f"{_md(failure.source_locator)}: {_md(failure.message)} ({retry})"
            )
    lines.extend(
        [
            "",
            "## 담당자 검토 체크",
            "",
            "- [ ] 각 출처가 기준일 현재 공식 원문인지 확인",
            "- [ ] 인용 구간이 질문의 적용대상과 관할에 직접 적용되는지 확인",
            "- [ ] 의무·권고·사례·해석을 구분",
            "- [ ] 상충하거나 더 최신인 공식자료가 없는지 확인",
            "- [ ] `INFERENCE`와 `RECOMMENDATION`을 기관 판단과 구분",
            "",
            "---",
            "",
            "이 문서는 로컬 근거 저장소에서 생성됐으며 자동 법률·감사·조달 판단이 아닙니다.",
            "",
        ]
    )
    return "\n".join(value for value in lines if value is not None)


def render_html(
    *,
    plan: ResearchPlan,
    payload: Dict[str, Any],
    citations: List[Citation],
    gaps: List[str],
    failures: List[Failure],
    brief: Dict[str, Any] | None = None,
    local_snapshot_prefix: str = "../../",
) -> str:
    """Render one dependency-free, offline-readable HTML policy brief."""

    brief = brief or build_default_brief(plan=plan, citations=citations, gaps=gaps)
    citation_map = {citation.id: citation for citation in citations}
    track_titles = {track.id: track.title for track in plan.tracks}
    references = _claim_references(brief)
    status_class = "status-ok" if payload["status"] == "SUCCEEDED" else "status-partial"
    summary_html = _html_items(
        brief.get("executive_summary", []),
        section="summary",
        citation_map=citation_map,
    ) or '<p class="empty">검증된 핵심 요약을 만들 수 있는 원문 구간이 없습니다.</p>'
    findings_html = _html_findings(brief.get("key_findings", []), citation_map)
    implications_html = _html_section_items(
        "implications",
        "업무 시사점",
        "확인된 사실이 실제 업무에 의미하는 바입니다.",
        brief.get("implications", []),
        citation_map,
    )
    recommendations_html = _html_section_items(
        "recommendations",
        "검토 권고",
        "근거와 기관 여건을 함께 살펴 담당자가 결정할 사항입니다.",
        brief.get("recommendations", []),
        citation_map,
    )
    scope_html = "".join(
        f'<li><strong>{_h(track.title)}</strong><span>{_h(track.research_question)}</span></li>'
        for track in plan.tracks
    )
    evidence_html = "".join(
        _evidence_card(
            citation,
            track_titles=track_titles,
            references=references,
            local_snapshot_prefix=local_snapshot_prefix,
        )
        for citation in citations
    ) or '<p class="empty">인용 가능한 원문 구간을 확보하지 못했습니다.</p>'
    open_questions = list(dict.fromkeys([*brief.get("open_questions", []), *gaps]))
    gaps_html = "".join(f"<li>{_h(value)}</li>" for value in open_questions)
    if not gaps_html:
        gaps_html = "<li>자동 검사에서 추가 조사 공백을 발견하지 못했습니다.</li>"
    failures_html = "".join(_failure_item(value) for value in failures)
    if not failures_html:
        failures_html = "<li>기록된 수집·파싱 실패가 없습니다.</li>"
    filters = "".join(
        f'<button type="button" class="filter" data-filter="{kind}" aria-pressed="true">'
        f"{label}</button>"
        for kind, label in (
            ("FACT", "확인된 사실"),
            ("INFERENCE", "해석"),
            ("RECOMMENDATION", "권고"),
        )
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>{_h(brief['title'])}</title>
<style>
:root{{--ink:#17212b;--muted:#617080;--paper:#f5f7f6;--card:#fff;--navy:#12324a;--teal:#087f75;--line:#dce3e3;--amber:#a15c00;--soft:#e8f3f1;--shadow:0 18px 55px rgba(18,50,74,.10);font-family:Pretendard,"Noto Sans KR","Apple SD Gothic Neo",system-ui,sans-serif;color:var(--ink);background:var(--paper);font-synthesis:none}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;line-height:1.68}}a{{color:var(--teal);text-underline-offset:.2em}}button{{font:inherit}}.skip{{position:fixed;left:1rem;top:-5rem;z-index:99;background:#fff;padding:.65rem 1rem;border-radius:.5rem}}.skip:focus{{top:1rem}}.progress{{position:fixed;inset:0 auto auto 0;height:4px;width:0;background:linear-gradient(90deg,var(--teal),#5ebbb1);z-index:90}}.hero{{background:linear-gradient(135deg,#102d43,#174c5b 65%,#0e766f);color:#fff;padding:4.5rem max(1.25rem,calc((100vw - 1180px)/2)) 4rem}}.eyebrow{{font-size:.78rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#a9e3db}}h1{{max-width:920px;margin:.7rem 0 1rem;font-size:clamp(2rem,4.7vw,4.5rem);line-height:1.12;letter-spacing:-.045em}}.subtitle{{max-width:780px;margin:0;color:#d6e8ea;font-size:1.08rem}}.meta{{display:flex;flex-wrap:wrap;gap:.55rem;margin:2rem 0 0}}.badge{{display:inline-flex;align-items:center;gap:.4rem;border:1px solid rgba(255,255,255,.24);background:rgba(255,255,255,.09);padding:.4rem .7rem;border-radius:999px;font-size:.85rem}}.status-partial{{background:#fff3dc;color:#6f4000;border-color:#ffd28b}}.status-ok{{background:#dff7ed;color:#075a49;border-color:#9ce0cc}}.layout{{display:grid;grid-template-columns:220px minmax(0,1fr);gap:3rem;max-width:1180px;margin:auto;padding:3rem 1.25rem 6rem}}.toc{{position:sticky;top:1.5rem;align-self:start}}.toc strong{{display:block;margin-bottom:.75rem;font-size:.8rem;letter-spacing:.08em;color:var(--muted)}}.toc a{{display:block;color:#40505d;text-decoration:none;padding:.35rem 0;border-left:2px solid var(--line);padding-left:.8rem;font-size:.9rem}}.toc a:hover,.toc a:focus{{color:var(--teal);border-color:var(--teal)}}main{{min-width:0}}section{{scroll-margin-top:1.5rem;margin-bottom:4.5rem}}.section-head{{display:flex;align-items:end;justify-content:space-between;gap:1rem;margin-bottom:1.35rem}}h2{{font-size:clamp(1.55rem,2.5vw,2.25rem);line-height:1.25;letter-spacing:-.035em;margin:0}}.section-lead{{margin:.3rem 0 0;color:var(--muted)}}.summary-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:1rem}}.summary-card,.finding,.evidence,.panel{{background:var(--card);border:1px solid var(--line);border-radius:1.15rem;box-shadow:0 8px 30px rgba(18,50,74,.05)}}.summary-card{{position:relative;padding:1.35rem;min-height:190px}}.summary-card::before{{content:attr(data-number);display:block;color:var(--teal);font-size:.78rem;font-weight:900;letter-spacing:.12em;margin-bottom:1rem}}.summary-card p{{margin:0;font-size:1.02rem}}.kind{{display:inline-block;font-size:.72rem;font-weight:800;letter-spacing:.06em;border-radius:999px;padding:.25rem .55rem;margin-bottom:.7rem;background:var(--soft);color:#07645d}}[data-kind="INFERENCE"] .kind{{background:#f0eaff;color:#5942a6}}[data-kind="RECOMMENDATION"] .kind{{background:#fff0d8;color:#845000}}.finding-list{{display:grid;gap:1rem}}.finding{{display:grid;grid-template-columns:70px minmax(0,1fr);gap:1.25rem;padding:1.4rem}}.finding-index{{font-size:2.2rem;line-height:1;color:#9fb6b5;font-weight:300}}.finding h3{{margin:0 0 .5rem;font-size:1.25rem}}.finding p{{margin:0}}.citations{{display:flex;flex-wrap:wrap;gap:.4rem;margin-top:1rem}}.citation-chip{{border:1px solid #b9d8d4;background:#f4fbfa;color:#09675f;border-radius:999px;padding:.32rem .65rem;cursor:pointer;font-size:.78rem;font-weight:700}}.citation-chip:hover,.citation-chip:focus{{background:#dff4f0;outline:2px solid transparent}}.filters{{display:flex;flex-wrap:wrap;gap:.45rem}}.filter{{border:1px solid var(--line);background:#fff;color:#455563;border-radius:999px;padding:.38rem .7rem;cursor:pointer;font-size:.8rem}}.filter[aria-pressed="false"]{{opacity:.45;text-decoration:line-through}}.scope-list{{list-style:none;padding:0;margin:0;display:grid;grid-template-columns:repeat(2,1fr);gap:.8rem}}.scope-list li{{background:#edf2f1;border-radius:.8rem;padding:1rem}}.scope-list strong,.scope-list span{{display:block}}.scope-list span{{font-size:.88rem;color:var(--muted);margin-top:.25rem}}.evidence-list{{display:grid;gap:1rem}}.evidence{{padding:1.35rem;scroll-margin-top:1.5rem}}.evidence:target{{outline:3px solid #87cfc6}}.evidence-head{{display:flex;justify-content:space-between;gap:1rem;align-items:start}}.evidence h3{{margin:.2rem 0;font-size:1.08rem}}.evidence-id{{font:700 .72rem ui-monospace,SFMono-Regular,monospace;color:var(--teal)}}blockquote{{margin:1rem 0 0;padding:1rem 1.1rem;border-left:4px solid var(--teal);background:#f7faf9;border-radius:0 .65rem .65rem 0}}.evidence-meta{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.65rem;margin-top:1rem;font-size:.82rem;color:#51616e}}.evidence-meta span{{display:block;overflow-wrap:anywhere}}.scorebar{{width:90px;height:7px;border-radius:99px;background:#dce8e6;overflow:hidden;margin-top:.35rem}}.scorebar i{{display:block;height:100%;background:var(--teal)}}.actions{{display:flex;flex-wrap:wrap;gap:.5rem;margin-top:1rem}}.action{{display:inline-block;text-decoration:none;border:1px solid #bed4d2;border-radius:.55rem;padding:.45rem .65rem;font-size:.8rem;font-weight:700}}details{{margin-top:1rem}}summary{{cursor:pointer;color:var(--teal);font-weight:700}}.backlinks{{font-size:.82rem;color:var(--muted);margin-top:.8rem}}.review-grid{{display:grid;grid-template-columns:1fr 1fr;gap:1rem}}.panel{{padding:1.35rem}}.panel h3{{margin-top:0}}.panel ul{{padding-left:1.2rem}}.empty{{padding:1rem;border:1px dashed #aebdbd;border-radius:.75rem;color:var(--muted)}}.drawer{{position:fixed;inset:0 0 0 auto;width:min(540px,100%);z-index:100;background:#fff;box-shadow:-20px 0 70px rgba(0,0,0,.2);padding:1.25rem;overflow:auto;transform:translateX(105%);transition:transform .22s ease}}.drawer.open{{transform:none}}.drawer-close{{position:sticky;top:0;float:right;border:0;border-radius:99px;background:#173f4d;color:#fff;width:2.4rem;height:2.4rem;cursor:pointer}}.drawer .evidence{{box-shadow:none;border:0;padding:2.5rem .2rem 1rem}}.scrim{{position:fixed;inset:0;background:rgba(7,25,34,.46);z-index:95;display:none}}.scrim.open{{display:block}}.footer{{max-width:1180px;margin:auto;border-top:1px solid var(--line);padding:2rem 1.25rem 4rem;color:var(--muted);font-size:.82rem}}[hidden]{{display:none!important}}:focus-visible{{outline:3px solid #efb84e;outline-offset:2px}}
@media(max-width:840px){{.layout{{display:block}}.toc{{position:relative;top:auto;margin-bottom:3rem}}.toc a{{display:inline-block;border-left:0;border-bottom:1px solid var(--line);padding:.4rem .65rem}}.summary-grid{{grid-template-columns:1fr}}.summary-card{{min-height:0}}.scope-list,.review-grid{{grid-template-columns:1fr}}}}
@media(max-width:520px){{.hero{{padding-top:3rem}}.finding{{grid-template-columns:1fr}}.finding-index{{font-size:1rem;font-weight:800}}.evidence-meta{{grid-template-columns:1fr}}.section-head{{display:block}}.filters{{margin-top:1rem}}}}
@media print{{.progress,.toc,.filters,.drawer,.scrim,.citation-chip,.actions{{display:none!important}}.hero{{background:#fff;color:#111;padding:1cm 0;border-bottom:2px solid #111}}.subtitle,.eyebrow{{color:#333}}.layout{{display:block;max-width:none;padding:1cm 0}}section{{break-inside:auto;margin-bottom:1cm}}.summary-card,.finding,.evidence,.panel{{box-shadow:none;break-inside:avoid}}body{{background:#fff;font-size:10pt}}a{{color:#111;text-decoration:none}}}}
</style>
</head>
<body>
<a class="skip" href="#main">본문 바로가기</a><div class="progress" id="progress"></div>
<header class="hero">
  <div class="eyebrow">Public Sector Research Brief · {_h(plan.id)}</div>
  <h1>{_h(brief['title'])}</h1>
  <p class="subtitle">{_h(brief.get('subtitle', ''))}</p>
  <div class="meta">
    <span class="badge {status_class}">{_h(payload['status'])}</span>
    <span class="badge">기준일 {_h(plan.as_of_date)}</span>
    <span class="badge">공식 1차자료 {payload['metrics']['official_primary_count']}건</span>
    <span class="badge">확인한 원문 구간 {len(citations)}건</span>
    <span class="badge">추가 확인 {len(open_questions)}건</span>
  </div>
</header>
<div class="layout">
<nav class="toc" aria-label="보고서 목차"><strong>INDEX</strong>
  <a href="#overview">한눈에 보기</a><a href="#findings">핵심 확인사항</a>
  {('<a href="#implications">업무 시사점</a>' if implications_html else '')}
  {('<a href="#recommendations">검토 권고</a>' if recommendations_html else '')}
  <a href="#scope">조사 범위</a><a href="#evidence">원문 근거</a><a href="#review">확인 필요사항</a>
</nav>
<main id="main">
<section id="overview"><div class="section-head"><div><h2>한눈에 보기</h2><p class="section-lead">원문이 직접 뒷받침하는 핵심 내용입니다.</p></div><div class="filters">{filters}</div></div><div class="summary-grid">{summary_html}</div></section>
<section id="findings"><div class="section-head"><div><h2>핵심 확인사항</h2><p class="section-lead">항목마다 연결된 근거를 눌러 원문 구간을 바로 확인할 수 있습니다.</p></div></div><div class="finding-list">{findings_html}</div></section>
{implications_html}{recommendations_html}
<section id="scope"><div class="section-head"><div><h2>조사 범위</h2><p class="section-lead">질문을 다음 쟁점으로 나눠 살펴봤습니다.</p></div></div><ul class="scope-list">{scope_html}</ul></section>
<section id="evidence"><div class="section-head"><div><h2>원문 근거</h2><p class="section-lead">수집시점·원문 위치·점수 구성을 함께 보존합니다.</p></div></div><div class="evidence-list">{evidence_html}</div></section>
<section id="review"><div class="section-head"><div><h2>담당자 확인사항</h2><p class="section-lead">자동 조사에서 확인하지 못했거나 사람이 최종 판단할 부분입니다.</p></div></div><div class="review-grid"><div class="panel"><h3>추가 확인</h3><ul>{gaps_html}</ul></div><div class="panel"><h3>수집 중 발생한 문제</h3><ul>{failures_html}</ul></div></div></section>
</main></div>
<footer class="footer">이 보고서는 로컬 근거 저장소에서 생성됐습니다. 자동 법률·감사·조달 판단이 아니며, 담당자는 적용범위·현행성·상충자료를 최종 확인해야 합니다.</footer>
<div class="scrim" id="scrim"></div><aside class="drawer" id="drawer" aria-hidden="true" aria-label="원문 근거 상세"><button class="drawer-close" id="drawer-close" aria-label="닫기">&times;</button><div id="drawer-content"></div></aside>
<noscript><p class="footer">JavaScript가 꺼져 있어도 보고서 전체와 원문 링크를 읽을 수 있습니다. 근거 팝업 대신 아래 원문 근거 목록을 이용하세요.</p></noscript>
<script>
(()=>{{const progress=document.getElementById('progress');const update=()=>{{const max=document.documentElement.scrollHeight-innerHeight;progress.style.width=(max?scrollY/max*100:0)+'%'}};addEventListener('scroll',update,{{passive:true}});update();
const drawer=document.getElementById('drawer'),scrim=document.getElementById('scrim'),content=document.getElementById('drawer-content');let last=null;const close=()=>{{drawer.classList.remove('open');scrim.classList.remove('open');drawer.setAttribute('aria-hidden','true');if(last)last.focus()}};document.getElementById('drawer-close').onclick=close;scrim.onclick=close;addEventListener('keydown',e=>{{if(e.key==='Escape')close()}});
document.querySelectorAll('.citation-chip').forEach(btn=>btn.addEventListener('click',()=>{{const card=document.getElementById('evidence-'+btn.dataset.citationId);if(!card)return;last=btn;content.replaceChildren(card.cloneNode(true));drawer.classList.add('open');scrim.classList.add('open');drawer.setAttribute('aria-hidden','false');document.getElementById('drawer-close').focus()}}));
const active=new Set(['FACT','INFERENCE','RECOMMENDATION']);document.querySelectorAll('.filter').forEach(btn=>btn.addEventListener('click',()=>{{const kind=btn.dataset.filter;if(active.has(kind))active.delete(kind);else active.add(kind);btn.setAttribute('aria-pressed',String(active.has(kind)));document.querySelectorAll('[data-kind]').forEach(el=>el.hidden=!active.has(el.dataset.kind))}}));}})();
</script>
</body></html>"""


def _markdown_items(items: Sequence[Mapping[str, Any]]) -> List[str]:
    return [
        f"- **{_kind_label(item['kind'])}** {_md(item['text'])} "
        f"{_markdown_citations(item['citation_ids'])}".rstrip()
        for item in items
    ]


def _markdown_citations(citation_ids: Sequence[str]) -> str:
    return " ".join(f"[{value}](#evidence-{value})" for value in citation_ids)


def _markdown_source_link(locator: str) -> str:
    if _safe_url(locator):
        href = quote(locator, safe=":/?&=#%+@;,-._~")
        return f"[{_md(locator)}]({href})"
    return f"`{_md(locator)}`"


def _kind_label(kind: str) -> str:
    return {
        "FACT": "확인된 사실",
        "INFERENCE": "해석",
        "RECOMMENDATION": "검토 권고",
    }[kind]


def _html_items(
    items: Sequence[Mapping[str, Any]],
    *,
    section: str,
    citation_map: Mapping[str, Citation],
) -> str:
    return "".join(
        f'<article class="summary-card" data-kind="{item["kind"]}" data-number="0{index}">'
        f'<span class="kind">{_kind_label(item["kind"])}</span><p>{_h(item["text"])}</p>'
        f'{_citation_buttons(item["citation_ids"], citation_map)}</article>'
        for index, item in enumerate(items, 1)
    )


def _html_findings(
    items: Sequence[Mapping[str, Any]],
    citation_map: Mapping[str, Citation],
) -> str:
    if not items:
        return '<p class="empty">검증된 핵심 확인사항이 없습니다.</p>'
    return "".join(
        f'<article class="finding" id="claim-{_h(item["id"])}" data-kind="{item["kind"]}">'
        f'<div class="finding-index">{index:02d}</div><div><span class="kind">'
        f'{_kind_label(item["kind"])}</span><h3>{_h(item.get("title", "확인사항"))}</h3>'
        f'<p>{_h(item["text"])}</p>{_citation_buttons(item["citation_ids"], citation_map)}</div>'
        f"</article>"
        for index, item in enumerate(items, 1)
    )


def _html_section_items(
    section_id: str,
    title: str,
    lead: str,
    items: Sequence[Mapping[str, Any]],
    citation_map: Mapping[str, Citation],
) -> str:
    if not items:
        return ""
    content = _html_items(items, section=section_id, citation_map=citation_map)
    return (
        f'<section id="{section_id}"><div class="section-head"><div><h2>{title}</h2>'
        f'<p class="section-lead">{lead}</p></div></div><div class="summary-grid">'
        f"{content}</div></section>"
    )


def _citation_buttons(
    citation_ids: Sequence[str],
    citation_map: Mapping[str, Citation],
) -> str:
    buttons = []
    for citation_id in citation_ids:
        citation = citation_map.get(citation_id)
        label = citation.publisher if citation else citation_id
        buttons.append(
            f'<button type="button" class="citation-chip" data-citation-id="{_h(citation_id)}" '
            f'aria-label="{_h(label)} 근거 보기">근거 · {_h(label)}</button>'
        )
    return f'<div class="citations">{"".join(buttons)}</div>' if buttons else ""


def _evidence_card(
    citation: Citation,
    *,
    track_titles: Mapping[str, str],
    references: Mapping[str, Sequence[tuple[str, str]]],
    local_snapshot_prefix: str,
) -> str:
    score = citation.score
    original = ""
    if _safe_url(citation.source_locator):
        original = (
            f'<a class="action" href="{_h(citation.source_locator)}" target="_blank" '
            'rel="noopener noreferrer">공식 원문 열기 ↗</a>'
        )
    snapshot = ""
    if citation.local_snapshot_path:
        href = quote(local_snapshot_prefix + citation.local_snapshot_path, safe="/._-")
        snapshot = f'<a class="action" href="{href}">수집 당시 원문 보기</a>'
    breakdown = "".join(
        f"<li><strong>{label} {component.value:.2f}</strong> — {_h(component.explanation)}</li>"
        for label, component in (
            ("권위", score.authority),
            ("1차성", score.primary_source),
            ("직접성", score.direct_relevance),
            ("원문 확보", score.original_snapshot),
            ("위치 구체성", score.specificity),
            ("최신성", score.freshness),
            ("독립성", score.independence),
        )
    )
    backlinks = references.get(citation.id, [])
    backlinks_html = ""
    if backlinks:
        links = " · ".join(f'<a href="#{_h(anchor)}">{_h(label)}</a>' for anchor, label in backlinks)
        backlinks_html = f'<p class="backlinks">이 근거를 사용한 항목: {links}</p>'
    return f"""<article class="evidence" id="evidence-{_h(citation.id)}">
<div class="evidence-head"><div><div class="evidence-id">{_h(citation.id)}</div><h3>{_h(citation.title)}</h3><div>{_h(citation.publisher)} · {_h(track_titles.get(citation.track_id, citation.track_id))}</div></div><div><strong>{score.overall:.2f}</strong><div class="scorebar" aria-label="근거 점수 {score.overall:.2f}"><i style="width:{score.overall * 100:.0f}%"></i></div></div></div>
<blockquote>{_h(citation.excerpt)}</blockquote>
<div class="evidence-meta"><span><strong>원문 위치</strong><br>{_h(citation.locator)}</span><span><strong>수집시점</strong><br>{_h(citation.retrieved_at)}</span><span><strong>출처등급</strong><br>{_h(citation.source_tier)}</span><span><strong>SHA-256</strong><br>{_h(citation.document_sha256)}</span></div>
<div class="actions">{original}{snapshot}</div>{backlinks_html}
<details><summary>점수 구성과 설명</summary><ul>{breakdown}</ul></details></article>"""


def _claim_references(brief: Mapping[str, Any]) -> Dict[str, List[tuple[str, str]]]:
    result: Dict[str, List[tuple[str, str]]] = {}
    sections = (
        ("summary", "요약", brief.get("executive_summary", [])),
        ("finding", "핵심 확인사항", brief.get("key_findings", [])),
        ("implication", "업무 시사점", brief.get("implications", [])),
        ("recommendation", "검토 권고", brief.get("recommendations", [])),
    )
    for prefix, label, items in sections:
        for index, item in enumerate(items, 1):
            anchor = (
                f"claim-{item['id']}"
                if prefix == "finding" and item.get("id")
                else ("overview" if prefix == "summary" else f"{prefix}s")
            )
            for citation_id in item.get("citation_ids", []):
                result.setdefault(citation_id, []).append((anchor, f"{label} {index}"))
    return result


def _failure_item(failure: Failure) -> str:
    retry = "재시도 가능" if failure.retryable else "재시도 비권장"
    return (
        f"<li><strong>{_h(failure.code)}</strong> · {_h(failure.track_id)} · "
        f"{_h(failure.message)} ({retry})</li>"
    )


def _safe_url(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _h(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _md(value: Any) -> str:
    return html.escape(str(value), quote=False)
