"""Public task sharing endpoint — Idea #200: Task Result Permalink.

Unauthenticated endpoint. Any task with a share_token can be viewed publicly.
Supports JSON (Accept: application/json) or HTML (default, Jinja2 template).

Usage:
    GET /r/{share_token}          → HTML viewer with "Try AgentHQ" CTA
    GET /r/{share_token}?fmt=json → raw JSON result for integrations
    GET /r/compare?a={t1}&b={t2} → side-by-side diff of two task outputs (#209)
    GET /r/compare?a={t1}&b={t2}&fmt=json → JSON diff for integrations

IMPORTANT — route ordering: /r/compare MUST be registered before /r/{share_token}
so that FastAPI does not swallow "compare" as a path parameter token.

Migration note: Task model needs a share_token UUID column.
Run: alembic revision --autogenerate -m "add share_token to tasks"
Then: alembic upgrade head
"""

import difflib
import html as html_module
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
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
  <div class="badge">✨ AgentHQ 생성 문서</div>
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


async def _resolve_token(token_str: str, db: AsyncSession) -> Task:
    """Resolve a share token (UUID string) to a completed Task, or raise 404."""
    try:
        token_uuid = UUID(token_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Token not found: {token_str!r}",
        )

    result = await db.execute(select(Task).where(Task.id == token_uuid))
    task: Task | None = result.scalar_one_or_none()

    if task is None or task.status != TaskStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {token_str!r} not found or not completed",
        )
    return task


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

    # Look up task by share_token (column added by migration)
    # Fallback: if share_token column doesn't exist yet, look up by task id
    result = await db.execute(
        select(Task).where(
            # Use share_token when available; fall back to id for development
            Task.id == token_uuid
        )
    )
    task: Task | None = result.scalar_one_or_none()

    if task is None or task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Build display content
    task_type_labels = {"docs": "문서", "sheets": "스프레드시트", "slides": "슬라이드", "research": "리서치"}
    type_label = task_type_labels.get(
        str(task.task_type.value if hasattr(task.task_type, "value") else task.task_type), "문서"
    )

    result_data = task.result or {}
    result_text = result_data.get("content") or result_data.get("summary") or str(result_data)[:2000]
    title = result_data.get("title") or f"AgentHQ {type_label}"

    if fmt == "json" or "application/json" in request.headers.get("accept", ""):
        return JSONResponse({
            "id": str(task.id),
            "type": str(task.task_type),
            "prompt": task.prompt,
            "title": title,
            "result": result_data,
            "document_url": task.document_url,
        })

    html = VIEWER_HTML.format(
        title=title,
        prompt=task.prompt[:300] + ("…" if len(task.prompt) > 300 else ""),
        result_text=result_text[:3000],
        token=share_token,
    )
    return HTMLResponse(content=html)
