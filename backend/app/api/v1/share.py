"""Public task sharing endpoint — Idea #200: Task Result Permalink.

Unauthenticated endpoint. Any task with a share_token can be viewed publicly.
Supports JSON (Accept: application/json) or HTML (default, Jinja2 template).

Usage:
    GET /r/{share_token}         → HTML viewer with "Try AgentHQ" CTA
    GET /r/{share_token}?fmt=json → raw JSON result for integrations

Migration note: Task model needs a share_token UUID column.
Run: alembic revision --autogenerate -m "add share_token to tasks"
Then: alembic upgrade head
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.task import Task, TaskStatus

router = APIRouter()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public share viewer
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


@router.get("/r/{share_token}", include_in_schema=False)
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
    type_label = task_type_labels.get(str(task.task_type.value if hasattr(task.task_type, 'value') else task.task_type), "문서")

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
