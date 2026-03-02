# 🎯 Feature Implementation Plan: Smart Workspace Manager

**Created**: 2026-03-02  
**Sprint**: 3 (Post Sprint-2)  
**Priority**: 🔥 HIGH  
**Duration**: 6 weeks  
**Status**: Planning

---

## 📋 Executive Summary

Implement multi-workspace functionality to enable users to manage multiple projects simultaneously with isolated contexts. This solves the context-switching problem and lays the foundation for team collaboration (Phase 5).

---

## 🎯 Problem Statement

**Current Pain Points:**
1. Single conversation thread → projects get mixed up
2. Context loss when switching between Marketing/Finance/Development tasks
3. Users must re-explain context after every task switch
4. No way to organize work by project
5. Team collaboration impossible (everyone shares one workspace)

**User Stories:**
- "As a product manager, I want separate workspaces for Q1 Planning, Q2 Planning, and Bug Triage"
- "As a developer, I want Backend workspace and Frontend workspace isolated"
- "As a marketer, I want Social Media, Email, and Blog workspaces"

---

## 🏗️ Technical Architecture

### Database Schema

```python
# app/models/workspace.py (ALREADY EXISTS - needs enhancement)
class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    
    # Workspace type (custom or from template)
    template_id: Mapped[Optional[UUID]] = mapped_column(
        ForeignKey("workspace_templates.id"), nullable=True
    )
    
    # Settings
    settings: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True, default=dict)
    
    # Icon/color for UI
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, default="📁")
    color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True, default="#3B82F6")
    
    # Soft delete
    is_archived: Mapped[bool] = mapped_column(default=False, index=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    
    # Relationships (already exist)
    owner: Mapped["User"] = relationship("User", back_populates="workspaces")
    chats: Mapped[List["Chat"]] = relationship("Chat", back_populates="workspace")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="workspace")
    members: Mapped[List["WorkspaceMember"]] = relationship(...)

# app/models/workspace_template.py (ALREADY EXISTS - needs enhancement)
class WorkspaceTemplate(Base, TimestampMixin):
    __tablename__ = "workspace_templates"
    
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(50), default="📁")
    category: Mapped[str] = mapped_column(String(50), default="general")  # marketing, finance, dev, etc.
    
    # Template configuration
    default_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    prompt_examples: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Visibility
    is_public: Mapped[bool] = mapped_column(default=True)
    is_featured: Mapped[bool] = mapped_column(default=False)
    
    # Usage stats
    usage_count: Mapped[int] = mapped_column(default=0)
```

### API Endpoints

#### Workspaces

```python
# app/api/v1/workspaces.py (ALREADY EXISTS - needs enhancement)

@router.get("/workspaces")
async def list_workspaces(
    include_archived: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[WorkspaceResponse]:
    """List user's workspaces"""
    query = db.query(Workspace).filter(Workspace.owner_id == current_user.id)
    if not include_archived:
        query = query.filter(Workspace.is_archived == False)
    return query.order_by(Workspace.created_at.desc()).all()

@router.post("/workspaces")
async def create_workspace(
    data: WorkspaceCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> WorkspaceResponse:
    """Create new workspace"""
    workspace = Workspace(
        name=data.name,
        description=data.description,
        owner_id=current_user.id,
        template_id=data.template_id,
        icon=data.icon or "📁",
        color=data.color or "#3B82F6"
    )
    
    # If created from template, copy settings
    if data.template_id:
        template = db.query(WorkspaceTemplate).get(data.template_id)
        workspace.settings = template.default_settings
        template.usage_count += 1
    
    db.add(workspace)
    db.commit()
    return workspace

@router.patch("/workspaces/{workspace_id}")
async def update_workspace(
    workspace_id: UUID,
    data: WorkspaceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> WorkspaceResponse:
    """Update workspace"""
    workspace = get_workspace_or_404(db, workspace_id, current_user.id)
    
    if data.name is not None:
        workspace.name = data.name
    if data.description is not None:
        workspace.description = data.description
    if data.icon is not None:
        workspace.icon = data.icon
    if data.color is not None:
        workspace.color = data.color
    
    db.commit()
    return workspace

@router.delete("/workspaces/{workspace_id}")
async def delete_workspace(
    workspace_id: UUID,
    hard_delete: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete/archive workspace"""
    workspace = get_workspace_or_404(db, workspace_id, current_user.id)
    
    if hard_delete:
        # Cascade delete all chats, messages, tasks
        db.delete(workspace)
    else:
        # Soft delete
        workspace.is_archived = True
        workspace.archived_at = datetime.utcnow()
    
    db.commit()
    return {"status": "success"}
```

#### Cross-Workspace Search

```python
@router.get("/search")
async def cross_workspace_search(
    q: str,
    workspace_ids: Optional[List[UUID]] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> SearchResults:
    """Search across all user's workspaces"""
    
    # Build base query
    query = db.query(Message).join(Chat).join(Workspace).filter(
        Workspace.owner_id == current_user.id,
        Workspace.is_archived == False
    )
    
    # Filter by specific workspaces if provided
    if workspace_ids:
        query = query.filter(Workspace.id.in_(workspace_ids))
    
    # Full-text search
    query = query.filter(
        or_(
            Message.content.ilike(f"%{q}%"),
            Chat.title.ilike(f"%{q}%")
        )
    )
    
    results = query.order_by(Message.created_at.desc()).limit(limit).all()
    
    return {
        "query": q,
        "total": len(results),
        "results": [
            {
                "message_id": msg.id,
                "content": msg.content[:200],
                "chat_id": msg.chat_id,
                "chat_title": msg.chat.title,
                "workspace_id": msg.chat.workspace_id,
                "workspace_name": msg.chat.workspace.name,
                "created_at": msg.created_at
            }
            for msg in results
        ]
    }
```

#### Templates

```python
@router.get("/templates")
async def list_templates(
    category: Optional[str] = None,
    featured_only: bool = False,
    db: Session = Depends(get_db)
) -> List[TemplateResponse]:
    """List workspace templates"""
    query = db.query(WorkspaceTemplate).filter(WorkspaceTemplate.is_public == True)
    
    if category:
        query = query.filter(WorkspaceTemplate.category == category)
    if featured_only:
        query = query.filter(WorkspaceTemplate.is_featured == True)
    
    return query.order_by(
        WorkspaceTemplate.is_featured.desc(),
        WorkspaceTemplate.usage_count.desc()
    ).all()
```

### Frontend Components

#### Desktop (React/Tauri)

```typescript
// desktop/src/components/WorkspaceSidebar.tsx
export const WorkspaceSidebar = () => {
  const { workspaces, currentWorkspace, switchWorkspace } = useWorkspaces();
  
  return (
    <div className="workspace-sidebar">
      <h3>Workspaces</h3>
      
      {workspaces.map((ws, idx) => (
        <WorkspaceItem
          key={ws.id}
          workspace={ws}
          isActive={ws.id === currentWorkspace?.id}
          onClick={() => switchWorkspace(ws.id)}
          shortcut={idx < 9 ? `⌘${idx + 1}` : undefined}
        />
      ))}
      
      <button onClick={() => setShowCreateModal(true)}>
        <PlusIcon /> New Workspace
      </button>
    </div>
  );
};

// desktop/src/hooks/useWorkspaces.ts
export const useWorkspaces = () => {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<Workspace | null>(null);
  
  const switchWorkspace = useCallback(async (workspaceId: string) => {
    // Save current state
    localStorage.setItem('lastWorkspaceId', workspaceId);
    
    // Load new workspace
    const workspace = workspaces.find(w => w.id === workspaceId);
    setCurrentWorkspace(workspace);
    
    // Fetch workspace chats
    const chats = await api.getWorkspaceChats(workspaceId);
    setChats(chats);
  }, [workspaces]);
  
  // Keyboard shortcuts (Cmd+1, Cmd+2, ...)
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if (e.metaKey && e.key >= '1' && e.key <= '9') {
        const idx = parseInt(e.key) - 1;
        if (workspaces[idx]) {
          switchWorkspace(workspaces[idx].id);
        }
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [workspaces]);
  
  return {
    workspaces,
    currentWorkspace,
    switchWorkspace,
    createWorkspace: async (data) => { ... },
    updateWorkspace: async (id, data) => { ... },
    deleteWorkspace: async (id) => { ... }
  };
};
```

#### Mobile (Flutter)

```dart
// mobile/lib/features/workspaces/presentation/screens/workspaces_screen.dart
class WorkspacesScreen extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final workspaces = ref.watch(workspacesProvider);
    
    return Scaffold(
      appBar: AppBar(title: Text('Workspaces')),
      body: ListView.builder(
        itemCount: workspaces.length,
        itemBuilder: (context, index) {
          final workspace = workspaces[index];
          return WorkspaceCard(
            workspace: workspace,
            onTap: () => ref.read(workspacesProvider.notifier).switchTo(workspace.id),
          );
        },
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showCreateWorkspaceDialog(context),
        child: Icon(Icons.add),
      ),
    );
  }
}
```

---

## 🚀 Implementation Phases

### Week 1-2: Backend Foundation
- [x] Workspace model already exists (enhance with icon, color, archived fields)
- [ ] Enhance workspace CRUD API endpoints
- [ ] Add cross-workspace search endpoint
- [ ] Add workspace templates system
- [ ] Unit tests for workspace operations

### Week 3-4: Frontend Implementation
- [ ] Desktop: Workspace sidebar UI
- [ ] Desktop: Workspace switcher + keyboard shortcuts
- [ ] Desktop: Create/edit workspace modal
- [ ] Desktop: Cross-workspace search UI
- [ ] Mobile: Workspaces screen
- [ ] Mobile: Workspace switcher drawer

### Week 5: Templates & Polish
- [ ] Seed default workspace templates (Marketing, Finance, Development, etc.)
- [ ] Template selection UI during workspace creation
- [ ] Workspace settings page
- [ ] Archive/restore functionality

### Week 6: Testing & Documentation
- [ ] Integration tests (workspace switching, search)
- [ ] E2E tests (create workspace → switch → search)
- [ ] Performance testing (1000+ messages, 50+ workspaces)
- [ ] User documentation
- [ ] API documentation

---

## ✅ Success Metrics

**Functional Requirements:**
- [ ] User can create unlimited workspaces
- [ ] Switching between workspaces preserves context
- [ ] Cross-workspace search returns accurate results
- [ ] Keyboard shortcuts work (Cmd+1-9)
- [ ] Templates accelerate workspace creation
- [ ] Archive doesn't lose data

**Performance Requirements:**
- [ ] Workspace switch < 500ms
- [ ] Search response < 1s (1000+ messages)
- [ ] UI rendering < 100ms (50+ workspaces)

**User Experience:**
- [ ] Onboarding prompts workspace creation
- [ ] Intuitive workspace icons/colors
- [ ] Search highlights matches
- [ ] No data loss on switch

---

## 🎯 Future Enhancements (Phase 5: Team Collaboration)

After this foundation is solid, enable:
- **Shared Workspaces**: Invite team members to workspaces
- **Real-time Collaboration**: Google Docs-style simultaneous editing
- **Workspace Permissions**: Owner/Admin/Editor/Viewer roles
- **Activity Feed**: "Alice updated the Q1 Planning workspace"
- **Workspace Templates Marketplace**: Community-created templates

---

## 📊 Business Impact

**User Acquisition:**
- Professional users need multi-project support → Higher retention
- Power users (10+ workspaces) → Premium tier conversion

**Monetization:**
- Free: 3 workspaces
- Pro: Unlimited workspaces + templates
- Team: Shared workspaces (Phase 5)

**Competitive Advantage:**
- Notion: Has workspaces but weak AI
- ChatGPT: No workspaces (single thread)
- **AgentHQ: Workspaces + AI** ⭐

---

## 🧪 Testing Strategy

```python
# tests/integration/test_workspaces.py
def test_workspace_context_isolation():
    """Ensure workspace contexts don't leak"""
    ws1 = create_workspace("Marketing")
    ws2 = create_workspace("Finance")
    
    # Create chats in each
    chat1 = create_chat(workspace=ws1, title="Social Media Campaign")
    chat2 = create_chat(workspace=ws2, title="Q4 Budget")
    
    # Messages should be isolated
    msg1 = send_message(chat1, "Create Instagram post")
    msg2 = send_message(chat2, "Analyze expenses")
    
    # Search in ws1 should only return ws1 messages
    results = search(workspace_id=ws1.id, query="Instagram")
    assert len(results) == 1
    assert results[0].workspace_id == ws1.id
    
def test_workspace_switching_preserves_state():
    """State should be preserved when switching"""
    ws1 = create_workspace("Project A")
    ws2 = create_workspace("Project B")
    
    # Set up state in ws1
    chat1 = create_chat(workspace=ws1)
    send_message(chat1, "Hello from Project A")
    
    # Switch to ws2
    switch_workspace(ws2.id)
    chat2 = create_chat(workspace=ws2)
    send_message(chat2, "Hello from Project B")
    
    # Switch back to ws1
    switch_workspace(ws1.id)
    
    # State should be preserved
    chats = get_workspace_chats(ws1.id)
    assert len(chats) == 1
    assert chats[0].messages[-1].content == "Hello from Project A"
```

---

## 📝 Implementation Notes

**Existing Infrastructure:**
- ✅ Workspace model exists
- ✅ Workspace members table exists
- ✅ Chat → Workspace relationship exists
- ✅ Task → Workspace relationship exists

**What's Needed:**
- Enhance workspace model (icon, color, archived)
- Build workspace switcher UI
- Implement cross-workspace search
- Add keyboard shortcuts
- Create templates system

**Migration Required:**
- Add `icon`, `color`, `is_archived`, `archived_at` columns to `workspaces` table
- Migrate existing chats to a default workspace for each user

---

**Next Steps:**
1. Review this plan with team
2. Create database migration
3. Start Week 1 backend implementation
4. Weekly progress reviews

---

**Created by**: Dev Codex Cron  
**Sprint**: 3 (Post Sprint-2)  
**Estimated Completion**: 2026-04-13 (6 weeks from 2026-03-02)
