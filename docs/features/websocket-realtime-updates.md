# WebSocket Real-Time Updates - Implementation Plan

## Overview
Enable real-time bidirectional communication between backend and clients for live task updates, notifications, and agent progress.

## User Stories

1. **As a user**, I want to see my Agent tasks progress in real-time without refreshing
2. **As a user**, I want to receive instant notifications when my task completes
3. **As a user**, I want to see live Agent "thinking" indicators and streaming responses
4. **As a developer**, I need a foundation for future team collaboration features

## Technical Design

### Architecture

```
┌─────────────┐       WebSocket        ┌─────────────┐
│   Client    │ <──────────────────> │  FastAPI    │
│ (Web/Desktop│                        │   Server    │
└─────────────┘                        └──────┬──────┘
                                              │
                                              │ Publish
                                              ▼
                                        ┌──────────┐
                                        │  Redis   │
                                        │  Pub/Sub │
                                        └────┬─────┘
                                             │ Subscribe
                                             ▼
                                       ┌────────────┐
                                       │   Celery   │
                                       │  Workers   │
                                       └────────────┘
```

### Components

#### 1. WebSocket Manager (`app/websocket/manager.py`)

```python
from typing import Dict, List
from fastapi import WebSocket
import json
import redis.asyncio as redis


class ConnectionManager:
    """Manage WebSocket connections and broadcast messages."""
    
    def __init__(self):
        # user_id -> List[WebSocket connections]
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.redis_client: redis.Redis = None
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and store a WebSocket connection."""
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove a WebSocket connection."""
        if user_id in self.active_connections:
            self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
    
    async def send_personal_message(self, message: dict, user_id: str):
        """Send message to specific user's all connections."""
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.append(connection)
            
            # Clean up dead connections
            for conn in disconnected:
                self.disconnect(conn, user_id)
    
    async def broadcast(self, message: dict):
        """Send message to all connected clients."""
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)
    
    async def init_redis(self, redis_url: str):
        """Initialize Redis pub/sub for multi-worker support."""
        self.redis_client = await redis.from_url(redis_url)
        
    async def subscribe_to_user_channel(self, user_id: str):
        """Subscribe to user-specific Redis channel."""
        pubsub = self.redis_client.pubsub()
        await pubsub.subscribe(f"user:{user_id}")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                await self.send_personal_message(data, user_id)


manager = ConnectionManager()
```

#### 2. WebSocket Endpoint (`app/api/v1/websocket.py`)

```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from app.core.auth import get_current_user_ws
from app.websocket.manager import manager
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = None
):
    """WebSocket endpoint for real-time updates."""
    
    # Authenticate user (extract from query param or first message)
    try:
        if not token:
            await websocket.accept()
            # Wait for auth message
            auth_msg = await websocket.receive_json()
            token = auth_msg.get("token")
        
        user = await get_current_user_ws(token)
        user_id = str(user.id)
        
    except Exception as e:
        logger.error(f"WebSocket auth failed: {e}")
        await websocket.close(code=1008, reason="Authentication failed")
        return
    
    # Connect
    await manager.connect(websocket, user_id)
    logger.info(f"WebSocket connected: user={user_id}")
    
    # Send welcome message
    await manager.send_personal_message({
        "type": "connection_established",
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat()
    }, user_id)
    
    try:
        # Keep connection alive and handle incoming messages
        while True:
            data = await websocket.receive_json()
            
            # Handle different message types
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            
            elif data.get("type") == "subscribe_task":
                task_id = data.get("task_id")
                # Subscribe to task updates
                await manager.send_personal_message({
                    "type": "subscribed",
                    "task_id": task_id
                }, user_id)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
        logger.info(f"WebSocket disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket, user_id)
```

#### 3. Celery Task Integration

Update Celery tasks to publish progress updates:

```python
# app/agents/celery_app.py

from app.core.cache import cache
import json


async def publish_task_update(user_id: str, task_id: str, data: dict):
    """Publish task update to Redis for WebSocket broadcast."""
    message = {
        "type": "task_update",
        "task_id": task_id,
        "data": data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Publish to user-specific channel
    await cache.redis.publish(
        f"user:{user_id}",
        json.dumps(message)
    )


@celery.task(bind=True)
def research_task(self, prompt: str, user_id: str, task_id: str):
    """Research task with real-time updates."""
    
    # Update: Starting
    asyncio.run(publish_task_update(
        user_id, task_id,
        {"status": "running", "stage": "initializing"}
    ))
    
    agent = ResearchAgent()
    
    # Update: Searching
    asyncio.run(publish_task_update(
        user_id, task_id,
        {"status": "running", "stage": "searching", "progress": 0.3}
    ))
    
    result = asyncio.run(agent.research(prompt))
    
    # Update: Complete
    asyncio.run(publish_task_update(
        user_id, task_id,
        {
            "status": "completed",
            "result": result,
            "progress": 1.0
        }
    ))
    
    return result
```

#### 4. Frontend Integration (Desktop - React)

```typescript
// desktop/src/hooks/useWebSocket.ts

import { useEffect, useRef, useState } from 'react';

interface WebSocketMessage {
  type: string;
  task_id?: string;
  data?: any;
  timestamp: string;
}

export function useWebSocket(token: string) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  
  useEffect(() => {
    // Connect to WebSocket
    ws.current = new WebSocket(`ws://localhost:8000/api/v1/ws?token=${token}`);
    
    ws.current.onopen = () => {
      console.log('WebSocket connected');
      setConnected(true);
    };
    
    ws.current.onmessage = (event) => {
      const message = JSON.parse(event.data);
      setLastMessage(message);
    };
    
    ws.current.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
    
    ws.current.onclose = () => {
      console.log('WebSocket disconnected');
      setConnected(false);
      
      // Reconnect after 3 seconds
      setTimeout(() => {
        // Retry connection
      }, 3000);
    };
    
    // Cleanup
    return () => {
      ws.current?.close();
    };
  }, [token]);
  
  const sendMessage = (message: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(message));
    }
  };
  
  return { connected, lastMessage, sendMessage };
}
```

```typescript
// desktop/src/pages/TaskDetailPage.tsx

import { useWebSocket } from '../hooks/useWebSocket';

export function TaskDetailPage({ taskId }: { taskId: string }) {
  const { connected, lastMessage } = useWebSocket(token);
  const [taskStatus, setTaskStatus] = useState('pending');
  const [progress, setProgress] = useState(0);
  
  useEffect(() => {
    if (lastMessage?.type === 'task_update' && lastMessage.task_id === taskId) {
      setTaskStatus(lastMessage.data.status);
      setProgress(lastMessage.data.progress || 0);
    }
  }, [lastMessage, taskId]);
  
  return (
    <div>
      <h2>Task: {taskId}</h2>
      <p>Status: {taskStatus}</p>
      
      {taskStatus === 'running' && (
        <div className="progress-bar">
          <div style={{ width: `${progress * 100}%` }} />
        </div>
      )}
      
      {connected && <span className="status-indicator">🟢 Live</span>}
    </div>
  );
}
```

## Message Types

### Client → Server

```json
{
  "type": "ping"
}

{
  "type": "subscribe_task",
  "task_id": "task_123"
}
```

### Server → Client

```json
{
  "type": "connection_established",
  "user_id": "user_456",
  "timestamp": "2026-03-01T08:30:00Z"
}

{
  "type": "pong"
}

{
  "type": "task_update",
  "task_id": "task_123",
  "data": {
    "status": "running",
    "stage": "searching",
    "progress": 0.5
  },
  "timestamp": "2026-03-01T08:31:00Z"
}

{
  "type": "notification",
  "title": "Task Complete",
  "message": "Your research task has finished",
  "task_id": "task_123"
}
```

## Implementation Phases

### Phase 1: Core Infrastructure (Week 1)
- [ ] WebSocket manager with connection pooling
- [ ] Redis pub/sub integration
- [ ] Authentication for WebSocket connections
- [ ] Basic ping/pong keepalive

### Phase 2: Task Updates (Week 2)
- [ ] Integrate with Celery tasks
- [ ] Publish task status changes
- [ ] Progress updates from agents
- [ ] Error notifications

### Phase 3: Frontend Integration (Week 3)
- [ ] Desktop app WebSocket hook
- [ ] Real-time UI updates
- [ ] Reconnection logic
- [ ] Connection status indicator

### Phase 4: Advanced Features (Week 4)
- [ ] Typing indicators for agents
- [ ] Live streaming of agent responses
- [ ] Multi-device sync
- [ ] Presence indicators

## Testing Strategy

```python
# tests/test_websocket.py

import pytest
from fastapi.testclient import TestClient


def test_websocket_connection(client):
    """Test WebSocket connection establishment."""
    with client.websocket_connect("/api/v1/ws?token=valid_token") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection_established"


def test_websocket_auth_required(client):
    """Test WebSocket requires authentication."""
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws"):
            pass


def test_websocket_task_updates(client, db):
    """Test receiving task updates via WebSocket."""
    with client.websocket_connect("/api/v1/ws?token=valid_token") as websocket:
        # Subscribe to task
        websocket.send_json({
            "type": "subscribe_task",
            "task_id": "task_123"
        })
        
        # Trigger task
        # ... (create task via API)
        
        # Receive update
        update = websocket.receive_json()
        assert update["type"] == "task_update"
        assert update["task_id"] == "task_123"
```

## Performance Considerations

1. **Connection Limits**: Limit max connections per user (e.g., 5 devices)
2. **Message Rate Limiting**: Prevent spam with rate limits
3. **Cleanup**: Automatic cleanup of stale connections
4. **Scalability**: Redis pub/sub enables horizontal scaling

## Monitoring

Add Prometheus metrics:
- `websocket_connections_total`: Active WebSocket connections
- `websocket_messages_sent_total`: Messages sent
- `websocket_errors_total`: Connection errors
- `websocket_reconnects_total`: Reconnection attempts

## Documentation

- API documentation in `/docs`
- WebSocket protocol specification
- Frontend integration guide
- Troubleshooting guide

## Success Criteria

- [ ] WebSocket connections stable for > 1 hour
- [ ] Task updates received < 100ms after status change
- [ ] Automatic reconnection works on network disruption
- [ ] 95%+ uptime for WebSocket service
- [ ] Zero message loss in normal conditions

## Timeline

- **Week 1**: Core infrastructure + Redis pub/sub
- **Week 2**: Celery integration + task updates
- **Week 3**: Frontend hooks + UI
- **Week 4**: Testing + optimization

**Total**: 4 weeks

## Next Steps After Completion

This feature enables:
1. **Team Collaboration** (Phase 5 #2): Real-time multi-user editing
2. **Live Chat with Agents**: Streaming responses
3. **Notifications**: Instant alerts
4. **Presence System**: See who's online
