# Phase 4 Implementation Guide: Collaboration & Enterprise

> **목표**: 팀 협업 기능 및 엔터프라이즈 기능 구축
> **기간**: 3주
> **우선순위**: P1 (High Priority)

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Prerequisites](#prerequisites)
3. [Architecture](#architecture)
4. [Implementation](#implementation)
5. [Testing](#testing)
6. [Success Criteria](#success-criteria)

---

## Overview

Phase 4는 AgentHQ의 팀 협업 및 엔터프라이즈 기능을 구현합니다.

### Key Features
- ✅ **Multi-User Support**: 팀 단위 사용자 관리
- ✅ **Permission System**: 역할 기반 접근 제어 (RBAC)
- ✅ **Workspace Management**: 여러 워크스페이스 관리
- ✅ **Activity Logs**: 전체 활동 감사 추적
- ✅ **Real-time Sync**: WebSocket 기반 실시간 동기화
- ✅ **Billing & Usage**: 사용량 추적 및 과금

---

## Prerequisites

### Required Components
- Phase 0, 1, 2, 3 completed
- PostgreSQL 15+
- Redis 7+ (for WebSocket)
- Backend API running

---

## Architecture

### System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  Collaboration Architecture                  │
├─────────────────────────────────────────────────────────────┤
│                    Presentation Layer                        │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │ Team Admin │   Workspace  │   Members   │   Activity   │ │
│  │    UI      │     UI       │     UI      │   Logs UI    │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Application Layer                         │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │    Team    │   Workspace  │   Roles &   │   Activity   │ │
│  │  Service   │   Service    │ Permissions │   Tracker    │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                      Data Layer                              │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │   Teams    │  Workspaces  │    Roles    │   Activity   │ │
│  │   Table    │    Table     │    Table    │     Logs     │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
├─────────────────────────────────────────────────────────────┤
│                    Real-time Layer                           │
│  ┌────────────┬──────────────┬─────────────┬──────────────┐ │
│  │ WebSocket  │    Redis     │    Pub/Sub  │   Presence   │ │
│  │  Manager   │   Adapter    │   System    │   Tracking   │ │
│  └────────────┴──────────────┴─────────────┴──────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. Database Schema

```sql
-- Teams table
CREATE TABLE teams (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    owner_id UUID NOT NULL REFERENCES users(id),
    plan VARCHAR(50) DEFAULT 'free', -- free, pro, enterprise
    max_members INT DEFAULT 5,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Team members junction table
CREATE TABLE team_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL, -- admin, member, viewer
    joined_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(team_id, user_id)
);

-- Workspaces table
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Activity logs table
CREATE TABLE activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    action VARCHAR(100) NOT NULL, -- task_created, task_completed, member_added
    resource_type VARCHAR(50), -- task, user, workspace
    resource_id UUID,
    metadata JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Permissions table
CREATE TABLE permissions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role VARCHAR(50) NOT NULL,
    resource VARCHAR(50) NOT NULL, -- task, workspace, team
    action VARCHAR(50) NOT NULL, -- create, read, update, delete
    allowed BOOLEAN DEFAULT true,
    UNIQUE(role, resource, action)
);

-- Usage tracking table
CREATE TABLE usage_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    tasks_created INT DEFAULT 0,
    tasks_completed INT DEFAULT 0,
    llm_tokens_used BIGINT DEFAULT 0,
    api_calls INT DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    UNIQUE(team_id, date)
);

-- Indexes
CREATE INDEX idx_team_members_team ON team_members(team_id);
CREATE INDEX idx_team_members_user ON team_members(user_id);
CREATE INDEX idx_workspaces_team ON workspaces(team_id);
CREATE INDEX idx_activity_logs_team ON activity_logs(team_id);
CREATE INDEX idx_activity_logs_created ON activity_logs(created_at DESC);
CREATE INDEX idx_usage_stats_team_date ON usage_stats(team_id, date DESC);
```

### 2. Team Management Service

**File**: `backend/app/services/team_service.py`

```python
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.team import Team, TeamMember
from app.models.user import User
from app.core.exceptions import PermissionDeniedError, NotFoundError

class TeamService:
    """Service for team management"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_team(
        self,
        name: str,
        owner_id: UUID,
        plan: str = "free"
    ) -> Team:
        """Create a new team"""
        team = Team(
            name=name,
            owner_id=owner_id,
            plan=plan,
            max_members=5 if plan == "free" else 50
        )
        self.db.add(team)

        # Add owner as admin
        member = TeamMember(
            team_id=team.id,
            user_id=owner_id,
            role="admin"
        )
        self.db.add(member)

        await self.db.commit()
        await self.db.refresh(team)
        return team

    async def add_member(
        self,
        team_id: UUID,
        user_id: UUID,
        role: str = "member",
        added_by: UUID = None
    ) -> TeamMember:
        """Add member to team"""
        # Check permissions
        if added_by:
            await self._check_permission(added_by, team_id, "manage_members")

        # Check team member limit
        team = await self.get_team(team_id)
        current_members = await self.get_member_count(team_id)

        if current_members >= team.max_members:
            raise PermissionDeniedError("Team member limit reached")

        member = TeamMember(
            team_id=team_id,
            user_id=user_id,
            role=role
        )
        self.db.add(member)
        await self.db.commit()
        return member

    async def remove_member(
        self,
        team_id: UUID,
        user_id: UUID,
        removed_by: UUID
    ) -> bool:
        """Remove member from team"""
        await self._check_permission(removed_by, team_id, "manage_members")

        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise NotFoundError("Member not found")

        await self.db.delete(member)
        await self.db.commit()
        return True

    async def get_team_members(self, team_id: UUID) -> List[User]:
        """Get all members of a team"""
        result = await self.db.execute(
            select(User)
            .join(TeamMember)
            .where(TeamMember.team_id == team_id)
        )
        return result.scalars().all()

    async def _check_permission(
        self,
        user_id: UUID,
        team_id: UUID,
        permission: str
    ) -> bool:
        """Check if user has permission"""
        result = await self.db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            )
        )
        member = result.scalar_one_or_none()

        if not member:
            raise PermissionDeniedError("Not a team member")

        # Check role permissions
        if member.role == "admin":
            return True

        if permission == "manage_members" and member.role == "member":
            return False

        return True
```

### 3. Real-time Sync with WebSocket

**File**: `backend/app/websocket/manager.py`

```python
from fastapi import WebSocket
from typing import Dict, List, Set
from uuid import UUID
import json
import asyncio

class ConnectionManager:
    """Manage WebSocket connections"""

    def __init__(self):
        # team_id -> set of WebSocket connections
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, team_id: UUID):
        """Connect client to team channel"""
        await websocket.accept()

        if team_id not in self.active_connections:
            self.active_connections[team_id] = set()

        self.active_connections[team_id].add(websocket)

    def disconnect(self, websocket: WebSocket, team_id: UUID):
        """Disconnect client"""
        if team_id in self.active_connections:
            self.active_connections[team_id].discard(websocket)

            # Clean up empty team channels
            if not self.active_connections[team_id]:
                del self.active_connections[team_id]

    async def broadcast_to_team(
        self,
        team_id: UUID,
        message: dict,
        exclude: WebSocket = None
    ):
        """Broadcast message to all team members"""
        if team_id not in self.active_connections:
            return

        disconnected = set()

        for connection in self.active_connections[team_id]:
            if connection == exclude:
                continue

            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending message: {e}")
                disconnected.add(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, team_id)

    async def send_personal_message(
        self,
        message: str,
        websocket: WebSocket
    ):
        """Send message to specific client"""
        await websocket.send_text(message)

manager = ConnectionManager()
```

**WebSocket Endpoint**:

```python
@app.websocket("/ws/{team_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    team_id: UUID,
    token: str = Query(...)
):
    # Verify token and team membership
    user = await verify_websocket_token(token)
    is_member = await check_team_membership(user.id, team_id)

    if not is_member:
        await websocket.close(code=1008, reason="Not a team member")
        return

    # Connect
    await manager.connect(websocket, team_id)

    try:
        while True:
            # Receive and handle messages
            data = await websocket.receive_json()

            # Broadcast to team
            await manager.broadcast_to_team(
                team_id,
                {
                    "type": data.get("type"),
                    "user_id": str(user.id),
                    "data": data.get("data")
                },
                exclude=websocket
            )
    except WebSocketDisconnect:
        manager.disconnect(websocket, team_id)
```

### 4. Activity Logging

**File**: `backend/app/services/activity_service.py`

```python
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.activity_log import ActivityLog

class ActivityService:
    """Service for activity logging"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_activity(
        self,
        team_id: UUID,
        user_id: UUID,
        action: str,
        resource_type: str = None,
        resource_id: UUID = None,
        metadata: dict = None,
        ip_address: str = None,
        user_agent: str = None
    ) -> ActivityLog:
        """Log an activity"""
        log = ActivityLog(
            team_id=team_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata,
            ip_address=ip_address,
            user_agent=user_agent
        )

        self.db.add(log)
        await self.db.commit()
        return log

    async def get_team_activities(
        self,
        team_id: UUID,
        limit: int = 100,
        offset: int = 0
    ) -> List[ActivityLog]:
        """Get team activity logs"""
        result = await self.db.execute(
            select(ActivityLog)
            .where(ActivityLog.team_id == team_id)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def get_user_activities(
        self,
        team_id: UUID,
        user_id: UUID,
        limit: int = 100
    ) -> List[ActivityLog]:
        """Get user activity logs"""
        result = await self.db.execute(
            select(ActivityLog)
            .where(
                ActivityLog.team_id == team_id,
                ActivityLog.user_id == user_id
            )
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
        )
        return result.scalars().all()
```

### 5. Usage Tracking & Billing

**File**: `backend/app/services/usage_service.py`

```python
from datetime import date
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.usage_stats import UsageStats

class UsageService:
    """Service for usage tracking"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def track_usage(
        self,
        team_id: UUID,
        tasks_created: int = 0,
        tasks_completed: int = 0,
        llm_tokens_used: int = 0,
        api_calls: int = 0,
        storage_bytes: int = 0
    ):
        """Track usage statistics"""
        today = date.today()

        # Get or create usage record
        result = await self.db.execute(
            select(UsageStats).where(
                UsageStats.team_id == team_id,
                UsageStats.date == today
            )
        )
        usage = result.scalar_one_or_none()

        if not usage:
            usage = UsageStats(team_id=team_id, date=today)
            self.db.add(usage)

        # Update stats
        usage.tasks_created += tasks_created
        usage.tasks_completed += tasks_completed
        usage.llm_tokens_used += llm_tokens_used
        usage.api_calls += api_calls
        usage.storage_bytes += storage_bytes

        await self.db.commit()

    async def get_monthly_usage(
        self,
        team_id: UUID,
        year: int,
        month: int
    ) -> dict:
        """Get monthly usage summary"""
        start_date = date(year, month, 1)

        if month == 12:
            end_date = date(year + 1, 1, 1)
        else:
            end_date = date(year, month + 1, 1)

        result = await self.db.execute(
            select(UsageStats).where(
                UsageStats.team_id == team_id,
                UsageStats.date >= start_date,
                UsageStats.date < end_date
            )
        )
        usage_records = result.scalars().all()

        # Aggregate
        total = {
            'tasks_created': 0,
            'tasks_completed': 0,
            'llm_tokens_used': 0,
            'api_calls': 0,
            'storage_bytes': 0
        }

        for record in usage_records:
            total['tasks_created'] += record.tasks_created
            total['tasks_completed'] += record.tasks_completed
            total['llm_tokens_used'] += record.llm_tokens_used
            total['api_calls'] += record.api_calls
            total['storage_bytes'] += record.storage_bytes

        return total
```

---

## Testing

### Unit Tests

```python
@pytest.mark.asyncio
async def test_create_team():
    service = TeamService(db)
    team = await service.create_team(
        name="Test Team",
        owner_id=user_id
    )

    assert team.name == "Test Team"
    assert team.owner_id == user_id

@pytest.mark.asyncio
async def test_add_member():
    service = TeamService(db)
    member = await service.add_member(
        team_id=team_id,
        user_id=new_user_id,
        role="member",
        added_by=admin_id
    )

    assert member.role == "member"
```

### Integration Tests

```python
@pytest.mark.asyncio
async def test_real_time_sync():
    """Test WebSocket real-time sync"""
    async with websockets.connect(
        f"ws://localhost:8000/ws/{team_id}?token={token}"
    ) as websocket:
        # Send message
        await websocket.send(json.dumps({
            "type": "task_created",
            "data": {"task_id": "123"}
        }))

        # Receive broadcast
        response = await websocket.recv()
        data = json.loads(response)

        assert data["type"] == "task_created"
```

---

## Success Criteria

### Technical Metrics
- ✅ Team 생성/관리 성공
- ✅ 실시간 동기화 < 100ms
- ✅ Activity logs 정상 추적
- ✅ 권한 시스템 정상 작동
- ✅ Usage tracking 정확도 100%

### Performance
- ✅ WebSocket 연결 1000+ 동시 지원
- ✅ Activity log 검색 < 500ms
- ✅ Permission check < 10ms

---

## Next Steps

- **Phase 5**: Scale & Performance optimization
- **Phase 6**: Advanced Features (Plugin system, Templates)

---

## References

- [WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [PHASE_PLAN.md](PHASE_PLAN.md)
