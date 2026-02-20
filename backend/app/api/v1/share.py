"""Public task sharing endpoint — Idea #200: Task Result Permalink.

Unauthenticated endpoint. Any task with a share_token can be viewed publicly.
Supports JSON (Accept: application/json) or HTML (default, Jinja2 template).

Usage:
    GET  /r/{share_token}            → HTML viewer with "Try AgentHQ" CTA
    GET  /r/{share_token}?fmt=json   → raw JSON result for integrations
    POST /r/{share_token}/try        → #220 Magic Link: anonymous 1-click re-run
    GET  /r/compare?a={t1}&b={t2}    → side-by-side diff of two task outputs (#209)
    GET  /r/compare?a={t1}&b={t2}&fmt=json → JSON diff for integrations

IMPORTANT — route ordering: /r/compare MUST be registered before /r/{share_token}
so that FastAPI does not swallow "compare" as a path parameter token.

Migration note: Task model needs a share_token UUID column.
Run: alembic revision --autogenerate -m "add share_token to tasks"
Then: alembic upgrade head
"""

import difflib
import html as html_module
import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache
from app.core.config import settings
from app.core.database import get_db
from app.models.qa_result import QAResult
from app.models.task import Task, TaskStatus

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------

VIEWER_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — AgentHQ</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           max-width: 800px; margin: 0 auto; padding: 2rem; color: #1a1a1a; }}
    .badge {{ display: inline-block; padding: .25rem .75rem; border-radius: 9999px;
              background: #e8f5e9; color: #2e7d32; font-size: .8rem; font-weight: 600; }}
    .qa-badge {{ display: inline-block; padding: .3rem .9rem; border-radius: 9999px;
                 font-size: .85rem; font-weight: 700; margin-left: .5rem; vertical-align: middle; }}
    .qa-A {{ background: #dcfce7; color: #166534; }}
    .qa-B {{ background: #dbeafe; color: #1e40af; }}
    .qa-C {{ background: #fef9c3; color: #854d0e; }}
    .qa-D {{ background: #fed7aa; color: #9a3412; }}
    .qa-F {{ background: #fecaca; color: #991b1b; }}
    .qa-tip {{ background: #fffbeb; border: 1px solid #fde68a; border-radius: .5rem;
               padding: .75rem 1rem; margin: 1rem 0; font-size: .85rem; color: #92400e; }}
    .prompt-box {{ background: #f5f5f5; border-left: 4px solid #6366f1;
                   padding: 1rem; border-radius: 0 .5rem .5rem 0; margin: 1.5rem 0; }}
    .result-box {{ background: #fafafa; border: 1px solid #e0e0e0;
                   border-radius: .5rem; padding: 1.5rem; white-space: pre-wrap;
                   font-size: .95rem; line-height: 1.6; }}
    .cta {{ margin-top: 3rem; padding: 2rem; background: #6366f1;
            border-radius: 1rem; text-align: center; color: white; }}
    .cta h3 {{ margin: 0 0 .5rem; font-size: 1.4rem; }}
    .cta a {{ display: inline-block; margin-top: 1rem; padding: .75rem 2rem;
              background: white; color: #6366f1; border-radius: .5rem;
              text-decoration: none; font-weight: 700; }}
    .footer {{ margin-top: 2rem; font-size: .8rem; color: #9e9e9e; text-align: center; }}
    h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: .25rem; }}
  </style>
</head>
<body>
  <div class="badge">✨ AgentHQ 생성 문서</div>{qa_badge}
  <h1>{title}</h1>
  <div class="prompt-box">
    <strong>🤖 AI 요청:</strong><br>{prompt}
  </div>
  <div class="result-box">{result_text}</div>

  <div class="cta">
    <h3>이런 문서, AI로 5초 만에 만들어보세요</h3>
    <p style="margin:.5rem 0;opacity:.9">Google Docs · Sheets · Slides 자동화</p>
    <a href="https://agenthq.io?ref=share&token={token}">AgentHQ 무료로 시작하기 →</a>
  </div>

  <div class="footer">
    AgentHQ로 자동 생성된 콘텐츠입니다 · <a href="https://agenthq.io">agenthq.io</a>
  </div>
</body>
</html>"""

DIFF_HTML = """<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>결과 비교 — AgentHQ</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
           margin: 0; padding: 1.5rem; background: #f8f9fa; color: #1a1a1a; }}
    h1 {{ font-size: 1.6rem; font-weight: 700; margin: 0 0 1rem; }}
    .subtitle {{ color: #666; font-size: .9rem; margin-bottom: 2rem; }}
    .compare-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }}
    @media (max-width: 768px) {{ .compare-grid {{ grid-template-columns: 1fr; }} }}
    .panel {{ background: white; border-radius: .75rem; border: 1px solid #e0e0e0;
              overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
    .panel-header {{ padding: .75rem 1.25rem; background: #f5f5f5;
                     border-bottom: 1px solid #e0e0e0; }}
    .panel-header .label {{ font-weight: 700; font-size: .8rem; text-transform: uppercase;
                             letter-spacing: .05em; color: #555; }}
    .panel-header .title {{ font-size: 1rem; font-weight: 600; margin-top: .2rem; }}
    .panel-header .prompt-snippet {{ font-size: .82rem; color: #888; margin-top: .15rem;
                                      white-space: nowrap; overflow: hidden;
                                      text-overflow: ellipsis; }}
    .panel-body {{ padding: 1.25rem; font-size: .88rem; line-height: 1.65;
                   white-space: pre-wrap; word-break: break-word; max-height: 60vh;
                   overflow-y: auto; }}
    .diff-section {{ margin-top: 2rem; background: white; border-radius: .75rem;
                     border: 1px solid #e0e0e0; overflow: hidden;
                     box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
    .diff-section-header {{ padding: .75rem 1.25rem; background: #ede9fe;
                             border-bottom: 1px solid #ddd6fe; font-weight: 700;
                             font-size: .9rem; color: #5b21b6; }}
    .diff-table {{ width: 100%; border-collapse: collapse; font-size: .83rem;
                   font-family: 'Menlo', 'Consolas', monospace; }}
    .diff-table td {{ padding: .2rem .75rem; vertical-align: top;
                      border-bottom: 1px solid #f0f0f0; }}
    .diff-table .ln {{ color: #bbb; user-select: none; text-align: right;
                        padding-right: .5rem; min-width: 2.5rem; border-right: 1px solid #eee; }}
    .diff-add  {{ background: #dcfce7; }}
    .diff-add .ln {{ background: #bbf7d0; color: #166534; }}
    .diff-del  {{ background: #fee2e2; }}
    .diff-del .ln {{ background: #fecaca; color: #991b1b; }}
    .diff-ctx  {{ background: white; }}
    .diff-empty {{ color: #aaa; font-style: italic; padding: 1.5rem; text-align: center; }}
    .badge {{ display: inline-block; padding: .2rem .65rem; border-radius: 9999px;
              font-size: .75rem; font-weight: 700; margin-right: .4rem; }}
    .badge-a {{ background: #dbeafe; color: #1d4ed8; }}
    .badge-b {{ background: #fce7f3; color: #9d174d; }}
    .stats {{ display: flex; gap: 1.5rem; padding: .75rem 1.25rem;
              background: #fafafa; border-top: 1px solid #eee;
              font-size: .82rem; color: #555; }}
    .stat-add {{ color: #16a34a; font-weight: 700; }}
    .stat-del {{ color: #dc2626; font-weight: 700; }}
    .cta {{ margin-top: 2.5rem; padding: 1.75rem; background: #6366f1;
            border-radius: 1rem; text-align: center; color: white; }}
    .cta h3 {{ margin: 0 0 .4rem; font-size: 1.3rem; }}
    .cta a {{ display: inline-block; margin-top: .9rem; padding: .65rem 1.75rem;
              background: white; color: #6366f1; border-radius: .5rem;
              text-decoration: none; font-weight: 700; }}
    .footer {{ margin-top: 1.5rem; font-size: .78rem; color: #9e9e9e; text-align: center; }}
  </style>
</head>
<body>
  <h1>📊 결과 비교</h1>
  <p class="subtitle">두 AgentHQ 작업 결과를 나란히 비교합니다.</p>

  <div class="compare-grid">
    <div class="panel">
      <div class="panel-header">
        <div class="label"><span class="badge badge-a">A</span> 버전 A</div>
        <div class="title">{title_a}</div>
        <div class="prompt-snippet">🤖 {prompt_a}</div>
      </div>
      <div class="panel-body">{text_a}</div>
    </div>
    <div class="panel">
      <div class="panel-header">
        <div class="label"><span class="badge badge-b">B</span> 버전 B</div>
        <div class="title">{title_b}</div>
        <div class="prompt-snippet">🤖 {prompt_b}</div>
      </div>
      <div class="panel-body">{text_b}</div>
    </div>
  </div>

  <div class="diff-section">
    <div class="diff-section-header">🔍 라인 단위 차이 (A → B)</div>
    {diff_table}
    <div class="stats">
      <span>전체 라인: {total_lines}</span>
      <span class="stat-add">+{added} 추가</span>
      <span class="stat-del">-{removed} 삭제</span>
      <span>변경 없음: {unchanged}</span>
    </div>
  </div>

  <div class="cta">
    <h3>AgentHQ로 더 많은 결과를 만들어보세요</h3>
    <p style="margin:.4rem 0;opacity:.9">Google Docs · Sheets · Slides 자동화</p>
    <a href="https://agenthq.io?ref=compare">AgentHQ 무료로 시작하기 →</a>
  </div>

  <div class="footer">
    AgentHQ로 자동 생성된 콘텐츠입니다 · <a href="https://agenthq.io">agenthq.io</a>
  </div>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Diff helper functions (#209)
# ---------------------------------------------------------------------------

def _task_display_text(task: Task) -> str:
    """Extract the primary display text from a completed task's result."""
    result_data = task.result or {}
    text = (
        result_data.get("content")
        or result_data.get("summary")
        or result_data.get("text")
        or str(result_data)
    )
    return str(text)[:4000]


def _task_title(task: Task) -> str:
    """Extract a human-readable title from a task's result."""
    result_data = task.result or {}
    task_type_labels = {
        "docs": "문서",
        "sheets": "스프레드시트",
        "slides": "슬라이드",
        "research": "리서치",
    }
    type_str = str(task.task_type.value if hasattr(task.task_type, "value") else task.task_type)
    default = f"AgentHQ {task_type_labels.get(type_str, '문서')}"
    return str(result_data.get("title") or default)


def _build_diff_table(text_a: str, text_b: str) -> tuple[str, int, int, int, int]:
    """Build an HTML diff table and return (html, total, added, removed, unchanged)."""
    lines_a = text_a.splitlines(keepends=True)
    lines_b = text_b.splitlines(keepends=True)

    sm = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    rows: list[str] = []
    added = removed = unchanged = 0
    ln_a = ln_b = 1

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for line in lines_a[i1:i2]:
                safe = html_module.escape(line.rstrip("\n"))
                rows.append(
                    f'<tr class="diff-ctx">'
                    f'<td class="ln">{ln_a}</td><td class="ln">{ln_b}</td>'
                    f"<td>&nbsp;&nbsp;{safe}</td></tr>"
                )
                ln_a += 1
                ln_b += 1
                unchanged += 1
        elif tag == "replace":
            for line in lines_a[i1:i2]:
                safe = html_module.escape(line.rstrip("\n"))
                rows.append(
                    f'<tr class="diff-del">'
                    f'<td class="ln">{ln_a}</td><td class="ln">-</td>'
                    f"<td>- {safe}</td></tr>"
                )
                ln_a += 1
                removed += 1
            for line in lines_b[j1:j2]:
                safe = html_module.escape(line.rstrip("\n"))
                rows.append(
                    f'<tr class="diff-add">'
                    f'<td class="ln">-</td><td class="ln">{ln_b}</td>'
                    f"<td>+ {safe}</td></tr>"
                )
                ln_b += 1
                added += 1
        elif tag == "delete":
            for line in lines_a[i1:i2]:
                safe = html_module.escape(line.rstrip("\n"))
                rows.append(
                    f'<tr class="diff-del">'
                    f'<td class="ln">{ln_a}</td><td class="ln">-</td>'
                    f"<td>- {safe}</td></tr>"
                )
                ln_a += 1
                removed += 1
        elif tag == "insert":
            for line in lines_b[j1:j2]:
                safe = html_module.escape(line.rstrip("\n"))
                rows.append(
                    f'<tr class="diff-add">'
                    f'<td class="ln">-</td><td class="ln">{ln_b}</td>'
                    f"<td>+ {safe}</td></tr>"
                )
                ln_b += 1
                added += 1

    if added == 0 and removed == 0:
        # Texts are identical — skip rendering the context table
        table_html = '<p class="diff-empty">차이가 없습니다 — 두 결과가 동일합니다.</p>'
    elif not rows:
        table_html = '<p class="diff-empty">차이가 없습니다 — 두 결과가 동일합니다.</p>'
    else:
        table_html = (
            '<table class="diff-table"><tbody>'
            + "".join(rows)
            + "</tbody></table>"
        )

    total = unchanged + added + removed
    return table_html, total, added, removed, unchanged


async def _get_qa_for_task(task_id, db: AsyncSession) -> QAResult | None:
    """Fetch the latest QA result for a task (if any)."""
    stmt = (
        select(QAResult)
        .where(QAResult.task_id == task_id)
        .order_by(QAResult.created_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


def _qa_badge_html(qa: QAResult | None) -> str:
    """Render a quality score badge + optional tip for the share viewer."""
    if qa is None:
        return ""
    grade = qa.get_grade()
    score = round(qa.overall_score, 1)
    badge = f' <span class="qa-badge qa-{grade}">품질 {grade} ({score}점)</span>'
    if qa.needs_improvement():
        suggestions = (qa.auto_fix_suggestions or {}).get("suggestions", [])
        tip_text = "💡 개선 팁: "
        if suggestions:
            tip_text += suggestions[0].get("suggestion", "품질을 높이려면 구조와 출처를 보강하세요.")
        else:
            tip_text += "구조, 문법, 출처를 보강하면 점수가 올라갑니다."
        badge += f'\n  <div class="qa-tip">{html_module.escape(tip_text)}</div>'
    return badge


def _qa_json(qa: QAResult | None) -> dict | None:
    """Serialize QA result for JSON share responses."""
    if qa is None:
        return None
    return {
        "overall_score": round(qa.overall_score, 1),
        "grade": qa.get_grade(),
        "scores": {
            "grammar": qa.grammar_score,
            "structure": qa.structure_score,
            "readability": qa.readability_score,
            "completeness": qa.completeness_score,
            "fact_check": qa.fact_check_score,
        },
        "confidence": qa.confidence_level,
    }


async def _resolve_token(token_str: str, db: AsyncSession) -> Task:
    """Resolve a share token (UUID string) to a completed Task.

    Raises 404 if the token is invalid or not found.
    Raises 410 Gone if the share link has expired (#206).
    """
    try:
        token_uuid = UUID(token_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token not found: {token_str!r}",
        )

    # Prefer share_token lookup; fall back to id for backward-compat (dev/test)
    result = await db.execute(
        select(Task).where(Task.share_token == token_uuid)
    )
    task: Task | None = result.scalar_one_or_none()

    if task is None:
        # Backward-compat: allow lookup by task.id (no share_token migration yet)
        result2 = await db.execute(select(Task).where(Task.id == token_uuid))
        task = result2.scalar_one_or_none()

    if task is None or task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {token_str!r} not found or not completed",
        )

    # #206 — enforce share link expiry
    if task.expires_at is not None:
        now_utc = datetime.now(tz=timezone.utc)
        # expires_at may be naive (SQLite) or tz-aware; normalise to UTC
        exp = task.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now_utc > exp:
            raise HTTPException(
                status_code=410,
                detail="This share link has expired.",
            )

    return task


# ---------------------------------------------------------------------------
# #220 Magic Link Guest Access — anonymous 1-click re-run
# ---------------------------------------------------------------------------

_GUEST_TRY_KEY_PREFIX = "magic_link_try"


def _extract_client_ip(request: Request) -> str:
    """Extract best-effort client IP from proxy headers or connection."""
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip
    x_real = request.headers.get("X-Real-IP")
    if x_real and x_real.strip():
        return x_real.strip()
    return request.client.host if request.client else "unknown"


async def _check_guest_rate_limit(client_ip: str) -> bool:
    """Check if anonymous guest has remaining tries today. Returns True if allowed."""
    key = f"{_GUEST_TRY_KEY_PREFIX}:{client_ip}"
    current = await cache.get(key)
    count = int(current) if current is not None else 0
    if count >= settings.ANONYMOUS_MAX_TRIES_PER_IP:
        return False
    await cache.set(key, count + 1, ttl=86400)  # 24h TTL
    return True


@router.post(
    "/r/{share_token}/try",
    include_in_schema=True,
    tags=["share"],
    summary="Magic Link — anonymous 1-click re-run (#220)",
    response_model=None,
)
async def try_shared_task(
    share_token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Re-run a shared task anonymously.

    No authentication required. The original task's prompt and type are reused.
    Rate-limited by IP (default 3 tries/day per IP, configurable via
    ``ANONYMOUS_MAX_TRIES_PER_IP``).

    Returns the new task result (or a reference to poll).
    """
    # 1. Resolve original task
    task = await _resolve_token(share_token, db)

    # 2. IP-based rate limiting
    client_ip = _extract_client_ip(request)
    allowed = await _check_guest_rate_limit(client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily limit reached ({settings.ANONYMOUS_MAX_TRIES_PER_IP} "
                f"free tries per day). Sign up for unlimited access!"
            ),
        )

    # 3. Queue a new task using the same prompt/type (fire-and-forget via Celery)
    from app.models.task import TaskType
    from uuid import uuid4

    guest_task_id = uuid4()
    task_type_str = str(task.task_type.value if hasattr(task.task_type, "value") else task.task_type)

    # Create a lightweight DB record so the task can be tracked
    guest_task = Task(
        id=guest_task_id,
        user_id=task.user_id,  # attribute to original user for billing context
        prompt=task.prompt,
        task_type=task.task_type,
        status=TaskStatus.PENDING,
        task_metadata={"source": "magic_link", "original_task_id": str(task.id), "guest_ip": client_ip},
    )
    db.add(guest_task)
    await db.commit()
    await db.refresh(guest_task)

    # 4. Dispatch to Celery
    try:
        from app.agents.celery_app import (
            process_docs_task,
            process_research_task,
            process_sheets_task,
            process_slides_task,
        )

        task_id_str = str(guest_task_id)
        user_id_str = str(task.user_id)

        if task_type_str == "research":
            celery_result = process_research_task.apply_async(
                args=[task_id_str, task.prompt, user_id_str]
            )
        elif task_type_str == "docs":
            celery_result = process_docs_task.apply_async(
                args=[task_id_str, task.prompt, user_id_str, "Guest Document"]
            )
        elif task_type_str == "sheets":
            celery_result = process_sheets_task.apply_async(
                args=[task_id_str, task.prompt, user_id_str, "Guest Spreadsheet"]
            )
        elif task_type_str == "slides":
            celery_result = process_slides_task.apply_async(
                args=[task_id_str, task.prompt, user_id_str, "Guest Presentation"]
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported task type for guest try: {task_type_str}",
            )

        guest_task.celery_task_id = celery_result.id
        guest_task.status = TaskStatus.IN_PROGRESS
        await db.commit()

    except HTTPException:
        raise
    except Exception as e:
        guest_task.status = TaskStatus.FAILED
        guest_task.error_message = f"Failed to queue guest task: {str(e)}"
        await db.commit()
        logger.error(f"Magic link task queue failed: {e}")

    # 5. Store a short-lived result pointer in cache for easy lookup
    result_cache_key = f"magic_link_result:{guest_task_id}"
    await cache.set(
        result_cache_key,
        {"task_id": str(guest_task_id), "status": str(guest_task.status.value)},
        ttl=settings.ANONYMOUS_RESULT_TTL_SECONDS,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "task_id": str(guest_task_id),
            "status": str(guest_task.status.value),
            "message": "Task queued! Poll GET /r/{share_token} to see results, or check back soon.",
            "original_prompt": task.prompt[:200],
            "task_type": task_type_str,
            "tries_remaining": max(0, settings.ANONYMOUS_MAX_TRIES_PER_IP - (int(await cache.get(f"{_GUEST_TRY_KEY_PREFIX}:{client_ip}") or 0))),
            "signup_url": f"https://agenthq.io?ref=magic_link&token={share_token}",
        },
    )


# ---------------------------------------------------------------------------
# #209 Task Output Diff Viewer
# IMPORTANT: This route MUST be defined before /r/{share_token} so that
# FastAPI does not match "compare" as a path parameter.
# ---------------------------------------------------------------------------

@router.get("/r/compare", include_in_schema=True, response_model=None, tags=["share"])
async def compare_tasks(
    a: str = Query(..., description="Share token (UUID) of the first task"),
    b: str = Query(..., description="Share token (UUID) of the second task"),
    fmt: str = Query("html", description="Response format: 'html' or 'json'"),
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse | JSONResponse:
    """Side-by-side diff of two shared task outputs.

    Both tokens must correspond to **completed** tasks.  No authentication required.

    - ``GET /r/compare?a={token1}&b={token2}`` → HTML side-by-side + line diff
    - ``GET /r/compare?a={token1}&b={token2}&fmt=json`` → machine-readable diff
    """
    task_a = await _resolve_token(a, db)
    task_b = await _resolve_token(b, db)

    text_a = _task_display_text(task_a)
    text_b = _task_display_text(task_b)
    title_a = _task_title(task_a)
    title_b = _task_title(task_b)

    if fmt == "json" or (request and "application/json" in request.headers.get("accept", "")):
        diff_lines = list(
            difflib.unified_diff(
                text_a.splitlines(),
                text_b.splitlines(),
                fromfile=f"A/{title_a}",
                tofile=f"B/{title_b}",
                lineterm="",
            )
        )
        return JSONResponse({
            "task_a": {
                "id": str(task_a.id),
                "title": title_a,
                "prompt": task_a.prompt,
                "type": str(task_a.task_type),
                "text": text_a,
                "document_url": task_a.document_url,
            },
            "task_b": {
                "id": str(task_b.id),
                "title": title_b,
                "prompt": task_b.prompt,
                "type": str(task_b.task_type),
                "text": text_b,
                "document_url": task_b.document_url,
            },
            "diff": {
                "unified": diff_lines,
                "identical": text_a == text_b,
            },
        })

    diff_table, total_lines, added, removed, unchanged = _build_diff_table(text_a, text_b)

    html = DIFF_HTML.format(
        title_a=html_module.escape(title_a),
        title_b=html_module.escape(title_b),
        prompt_a=html_module.escape(task_a.prompt[:120] + ("…" if len(task_a.prompt) > 120 else "")),
        prompt_b=html_module.escape(task_b.prompt[:120] + ("…" if len(task_b.prompt) > 120 else "")),
        text_a=html_module.escape(text_a),
        text_b=html_module.escape(text_b),
        diff_table=diff_table,
        total_lines=total_lines,
        added=added,
        removed=removed,
        unchanged=unchanged,
    )
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Public share viewer — /r/{share_token}
# NOTE: This wildcard route is registered AFTER /r/compare intentionally.
# ---------------------------------------------------------------------------

@router.get("/r/{share_token}", include_in_schema=False, response_model=None)
async def view_shared_task(
    share_token: str,
    request: Request,
    fmt: str = "html",
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse | JSONResponse:
    """Public viewer for a shared task result.

    No authentication required. Returns HTML by default; ?fmt=json for raw data.
    """
    # Validate UUID format
    try:
        token_uuid = UUID(share_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Prefer share_token lookup; fall back to id for backward-compat
    result = await db.execute(
        select(Task).where(Task.share_token == token_uuid)
    )
    task: Task | None = result.scalar_one_or_none()

    if task is None:
        result2 = await db.execute(select(Task).where(Task.id == token_uuid))
        task = result2.scalar_one_or_none()

    if task is None or task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # #206 — enforce share link expiry → 410 Gone
    if task.expires_at is not None:
        now_utc = datetime.now(tz=timezone.utc)
        exp = task.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if now_utc > exp:
            raise HTTPException(
                status_code=410,
                detail="This share link has expired.",
            )

    # Build display content
    task_type_labels = {"docs": "문서", "sheets": "스프레드시트", "slides": "슬라이드", "research": "리서치"}
    type_label = task_type_labels.get(
        str(task.task_type.value if hasattr(task.task_type, "value") else task.task_type), "문서"
    )

    result_data = task.result or {}
    result_text = result_data.get("content") or result_data.get("summary") or str(result_data)[:2000]
    title = result_data.get("title") or f"AgentHQ {type_label}"

    # #228 Quality Score Badge
    qa = await _get_qa_for_task(task.id, db)

    if fmt == "json" or "application/json" in request.headers.get("accept", ""):
        payload = {
            "id": str(task.id),
            "type": str(task.task_type),
            "prompt": task.prompt,
            "title": title,
            "result": result_data,
            "document_url": task.document_url,
        }
        qa_data = _qa_json(qa)
        if qa_data is not None:
            payload["quality"] = qa_data
        return JSONResponse(payload)

    html = VIEWER_HTML.format(
        title=title,
        prompt=task.prompt[:300] + ("…" if len(task.prompt) > 300 else ""),
        result_text=result_text[:3000],
        token=share_token,
        qa_badge=_qa_badge_html(qa),
    )
    return HTMLResponse(content=html)
