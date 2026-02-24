"""
FactoryHub Integration API

이 모듈은 FactoryHub Go 백엔드와 AgentHQ 간의 통합을 처리합니다.
- FactoryHub에서 이벤트 수신 (task 실행 요청)
- Task 완료 시 FactoryHub로 웹훅 발송
- 통합 상태 및 헬스 체크
"""

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from datetime import datetime, UTC
import httpx
import logging

from app.db.session import get_db
from app.models.user import User
from app.models.task import Task
from app.core.security import get_current_user
from app.tasks.celery_app import celery_app
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================

class FactoryHubEvent(BaseModel):
    """FactoryHub에서 수신하는 이벤트"""
    event_type: str = Field(..., description="이벤트 타입 (task.create, task.cancel 등)")
    task_id: Optional[str] = Field(None, description="FactoryHub Task ID")
    user_id: str = Field(..., description="User ID")
    agent_type: str = Field(..., description="에이전트 타입 (docs, sheets, slides, orchestrator)")
    prompt: str = Field(..., description="사용자 요청")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="추가 메타데이터")
    callback_url: Optional[str] = Field(None, description="완료 시 호출할 웹훅 URL")


class FactoryHubCallback(BaseModel):
    """FactoryHub로 전송하는 콜백 데이터"""
    task_id: str
    factory_task_id: Optional[str]
    status: str  # done, failed
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class IntegrationStatus(BaseModel):
    """통합 상태"""
    service: str = "AgentHQ"
    version: str = "1.0.0"
    status: str = "healthy"
    last_event_received: Optional[datetime] = None
    total_events_processed: int = 0
    active_tasks: int = 0


# ============================================================================
# Security: FactoryHub Token Validation
# ============================================================================

async def validate_factoryhub_token(
    x_factoryhub_token: Optional[str] = Header(None)
) -> bool:
    """
    FactoryHub 인증 토큰 검증
    
    실제 프로덕션에서는:
    - 공유 시크릿 또는 JWT 검증
    - mTLS (mutual TLS) 인증
    - IP 화이트리스트
    """
    # TODO: 환경변수에서 실제 토큰 읽기
    # FACTORYHUB_SECRET_TOKEN = os.getenv("FACTORYHUB_SECRET_TOKEN", "your-secret-token")
    
    if not x_factoryhub_token:
        raise HTTPException(
            status_code=401,
            detail="Missing X-FactoryHub-Token header"
        )
    
    # 간단한 검증 (실제로는 더 복잡한 로직 필요)
    VALID_TOKEN = "factoryhub-dev-token-12345"  # 개발용
    
    if x_factoryhub_token != VALID_TOKEN:
        logger.warning(f"Invalid FactoryHub token: {x_factoryhub_token[:10]}...")
        raise HTTPException(
            status_code=403,
            detail="Invalid FactoryHub token"
        )
    
    return True


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/callback", status_code=202)
async def receive_factoryhub_event(
    event: FactoryHubEvent,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _: bool = Depends(validate_factoryhub_token)
):
    """
    FactoryHub에서 이벤트 수신
    
    - FactoryHub Go 백엔드가 사용자 요청을 AgentHQ로 라우팅할 때 호출
    - Task 생성 후 비동기로 Celery에 전달
    - 완료 시 callback_url로 결과 전송
    """
    logger.info(f"Received FactoryHub event: {event.event_type} (factory_task_id={event.task_id})")
    
    if event.event_type == "task.create":
        # User 조회 (FactoryHub user_id → AgentHQ user_id 매핑)
        user = db.query(User).filter(User.id == event.user_id).first()
        if not user:
            logger.error(f"User not found: {event.user_id}")
            raise HTTPException(status_code=404, detail="User not found")
        
        # Task 생성
        task = Task(
            user_id=user.id,
            agent_type=event.agent_type,
            prompt=event.prompt,
            status="pending",
            metadata={
                "source": "factoryhub",
                "factory_task_id": event.task_id,
                "callback_url": event.callback_url,
                **event.metadata
            }
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        logger.info(f"Created task {task.id} from FactoryHub event")
        
        # Celery task 실행
        celery_app.send_task(
            "app.tasks.run_agent_task",
            args=[str(task.id)],
            queue="agent_tasks"
        )
        
        # 백그라운드로 콜백 등록 (task 완료 시 호출됨)
        if event.callback_url:
            background_tasks.add_task(
                _schedule_callback,
                task_id=str(task.id),
                callback_url=event.callback_url,
                factory_task_id=event.task_id
            )
        
        return {
            "status": "accepted",
            "task_id": str(task.id),
            "factory_task_id": event.task_id,
            "message": "Task queued for processing"
        }
    
    elif event.event_type == "task.cancel":
        # Task 취소 요청 (미구현)
        logger.warning(f"Task cancellation not yet implemented: {event.task_id}")
        return {
            "status": "not_implemented",
            "message": "Task cancellation will be implemented in Phase 5"
        }
    
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown event type: {event.event_type}"
        )


@router.get("/status", response_model=IntegrationStatus)
async def get_integration_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    FactoryHub 통합 상태 조회
    
    - 마지막 이벤트 수신 시간
    - 처리된 총 이벤트 수
    - 현재 실행 중인 task 수
    """
    # FactoryHub에서 온 task 통계
    factory_tasks = db.query(Task).filter(
        Task.metadata["source"].astext == "factoryhub"
    ).all()
    
    active_tasks = [t for t in factory_tasks if t.status in ["pending", "running"]]
    
    last_event = None
    if factory_tasks:
        last_event = max(t.created_at for t in factory_tasks)
    
    return IntegrationStatus(
        last_event_received=last_event,
        total_events_processed=len(factory_tasks),
        active_tasks=len(active_tasks)
    )


# ============================================================================
# Helper Functions
# ============================================================================

async def _schedule_callback(task_id: str, callback_url: str, factory_task_id: Optional[str]):
    """
    Task 완료 시 FactoryHub로 콜백 전송 (백그라운드)
    
    실제로는 Celery Beat 또는 polling으로 구현해야 하지만,
    여기서는 간단히 비동기 HTTP 호출로 구현
    """
    import asyncio
    
    # Task 완료 대기 (최대 5분)
    max_wait = 300  # seconds
    check_interval = 5  # seconds
    elapsed = 0
    
    from app.db.session import SessionLocal
    
    while elapsed < max_wait:
        await asyncio.sleep(check_interval)
        elapsed += check_interval
        
        # DB에서 task 상태 체크
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                logger.error(f"Task {task_id} not found for callback")
                return
            
            if task.status in ["done", "failed"]:
                # Task 완료 → 콜백 전송
                callback_data = FactoryHubCallback(
                    task_id=task_id,
                    factory_task_id=factory_task_id,
                    status=task.status,
                    result=task.result if task.status == "done" else None,
                    error=task.error if task.status == "failed" else None,
                    metadata=task.metadata or {}
                )
                
                await _send_callback(callback_url, callback_data)
                return
        finally:
            db.close()
    
    logger.warning(f"Task {task_id} timeout waiting for completion (callback not sent)")


async def _send_callback(callback_url: str, data: FactoryHubCallback):
    """FactoryHub로 HTTP POST 콜백 전송"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                callback_url,
                json=data.model_dump(),
                timeout=10.0,
                headers={
                    "Content-Type": "application/json",
                    "X-AgentHQ-Callback": "true"
                }
            )
            response.raise_for_status()
            logger.info(f"FactoryHub callback sent successfully: {callback_url}")
    except Exception as e:
        logger.error(f"Failed to send FactoryHub callback to {callback_url}: {e}")


# ============================================================================
# Webhook endpoint for FactoryHub to call when task completes (alternative)
# ============================================================================

@router.post("/webhook/task-complete")
async def task_complete_webhook(
    task_id: str,
    db: Session = Depends(get_db),
    _: bool = Depends(validate_factoryhub_token)
):
    """
    AgentHQ Task 완료 시 호출되는 웹훅 (FactoryHub가 polling 대신 사용 가능)
    
    실제로는 Task 완료 시 자동으로 FactoryHub로 콜백을 보내지만,
    FactoryHub가 직접 이 엔드포인트를 polling할 수도 있음
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.metadata and task.metadata.get("source") != "factoryhub":
        raise HTTPException(status_code=403, detail="Not a FactoryHub task")
    
    return {
        "task_id": str(task.id),
        "factory_task_id": task.metadata.get("factory_task_id"),
        "status": task.status,
        "result": task.result if task.status == "done" else None,
        "error": task.error if task.status == "failed" else None,
        "created_at": task.created_at,
        "updated_at": task.updated_at
    }
