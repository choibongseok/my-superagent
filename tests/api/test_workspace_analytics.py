"""Tests for workspace analytics endpoints."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.models.workspace_insight import WorkspaceInsight, WorkspaceCleanupLog
from backend.app.services.workspace_analyzer import WorkspaceAnalyzer


@pytest.fixture
def mock_drive_service():
    """Mock Google Drive service."""
    service = MagicMock()
    
    # Mock files().list() chain
    list_mock = MagicMock()
    list_mock.execute.return_value = {
        "files": [
            {
                "id": "file1",
                "name": "test.docx",
                "mimeType": "application/vnd.google-apps.document",
                "size": "1024",
                "createdTime": "2024-01-01T00:00:00Z",
                "modifiedTime": "2024-01-15T00:00:00Z",
                "viewedByMeTime": "2024-02-01T00:00:00Z",
                "parents": ["root"],
                "webViewLink": "https://docs.google.com/document/d/file1"
            },
            {
                "id": "file2",
                "name": "test.docx",
                "mimeType": "application/vnd.google-apps.document",
                "size": "1024",
                "createdTime": "2024-01-02T00:00:00Z",
                "modifiedTime": "2024-01-16T00:00:00Z",
                "viewedByMeTime": "2024-02-02T00:00:00Z",
                "parents": ["root"],
                "webViewLink": "https://docs.google.com/document/d/file2"
            },
            {
                "id": "file3",
                "name": "old.xlsx",
                "mimeType": "application/vnd.google-apps.spreadsheet",
                "size": "2048",
                "createdTime": "2023-01-01T00:00:00Z",
                "modifiedTime": "2023-01-01T00:00:00Z",
                "viewedByMeTime": "2023-01-01T00:00:00Z",
                "parents": ["root"],
                "webViewLink": "https://docs.google.com/spreadsheets/d/file3"
            }
        ],
        "nextPageToken": None
    }
    
    service.files.return_value.list.return_value = list_mock
    return service


class TestWorkspaceAnalyzer:
    """Test workspace analyzer service."""
    
    @pytest.mark.asyncio
    async def test_analyze_workspace(self, db_session, test_user, mock_drive_service):
        """Test basic workspace analysis."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            insight = await analyzer.analyze_workspace()
            
            assert insight.user_id == test_user.id
            assert insight.total_files == 3
            assert insight.total_size_bytes == 4096  # 1024 + 1024 + 2048
            assert insight.duplicate_files is not None
            assert insight.stale_files is not None
            assert insight.storage_breakdown is not None
            assert insight.organization_suggestions is not None
    
    @pytest.mark.asyncio
    async def test_detect_duplicates(self, db_session, test_user, mock_drive_service):
        """Test duplicate file detection."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            insight = await analyzer.analyze_workspace()
            
            # Should detect 1 duplicate group (2 files named "test.docx" with same size)
            duplicate_groups = insight.duplicate_files
            assert len(duplicate_groups) == 1
            assert len(duplicate_groups[0]["files"]) == 2
            assert duplicate_groups[0]["total_size"] == 2048  # 1024 * 2
    
    @pytest.mark.asyncio
    async def test_identify_stale_files(self, db_session, test_user, mock_drive_service):
        """Test stale file identification."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            insight = await analyzer.analyze_workspace()
            
            # file3 (old.xlsx) should be stale (accessed in 2023)
            stale_files = insight.stale_files
            assert len(stale_files) >= 1
            assert any(f["name"] == "old.xlsx" for f in stale_files)
    
    @pytest.mark.asyncio
    async def test_storage_breakdown(self, db_session, test_user, mock_drive_service):
        """Test storage breakdown by file type."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            insight = await analyzer.analyze_workspace()
            
            breakdown = insight.storage_breakdown
            assert "categories" in breakdown
            
            categories = {cat["type"]: cat for cat in breakdown["categories"]}
            assert "documents" in categories
            assert "spreadsheets" in categories
            assert categories["documents"]["count"] == 2
            assert categories["spreadsheets"]["count"] == 1
    
    @pytest.mark.asyncio
    async def test_organization_suggestions(self, db_session, test_user, mock_drive_service):
        """Test organization suggestion generation."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            insight = await analyzer.analyze_workspace()
            
            suggestions = insight.organization_suggestions
            assert len(suggestions) > 0
            
            # Should have suggestions for duplicates and stale files
            suggestion_types = [s["type"] for s in suggestions]
            assert "remove_duplicates" in suggestion_types
            assert "archive_old_files" in suggestion_types


class TestWorkspaceEndpoints:
    """Test workspace API endpoints."""
    
    @pytest.mark.asyncio
    async def test_analyze_workspace_endpoint(self, client, auth_headers, db_session, test_user, mock_drive_service):
        """Test POST /workspace/analyze endpoint."""
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            response = client.post("/api/v1/workspace/analyze", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["user_id"] == test_user.id
            assert data["total_files"] == 3
            assert "duplicate_files" in data
            assert "stale_files" in data
            assert "storage_breakdown" in data
            assert "organization_suggestions" in data
    
    @pytest.mark.asyncio
    async def test_get_insights_endpoint(self, client, auth_headers, db_session, test_user):
        """Test GET /workspace/insights endpoint."""
        # Create test insights
        insight1 = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=10,
            total_size_bytes=10240
        )
        insight2 = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow() - timedelta(days=1),
            total_files=12,
            total_size_bytes=12288
        )
        db_session.add_all([insight1, insight2])
        db_session.commit()
        
        response = client.get("/api/v1/workspace/insights", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["total_files"] == 10  # Most recent first
        assert data[1]["total_files"] == 12
    
    @pytest.mark.asyncio
    async def test_get_single_insight_endpoint(self, client, auth_headers, db_session, test_user):
        """Test GET /workspace/insights/{id} endpoint."""
        insight = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=5,
            total_size_bytes=5120
        )
        db_session.add(insight)
        db_session.commit()
        
        response = client.get(f"/api/v1/workspace/insights/{insight.id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == insight.id
        assert data["total_files"] == 5
    
    @pytest.mark.asyncio
    async def test_organize_workspace_endpoint(self, client, auth_headers, db_session, test_user, mock_drive_service):
        """Test POST /workspace/organize endpoint."""
        # Create test insight with stale files
        insight = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=3,
            total_size_bytes=4096,
            stale_files=[
                {"id": "file3", "name": "old.xlsx", "size": 2048, "last_accessed": "2023-01-01T00:00:00Z"}
            ]
        )
        db_session.add(insight)
        db_session.commit()
        
        # Mock Drive operations
        mock_drive_service.files.return_value.update.return_value.execute.return_value = {"id": "file3"}
        mock_drive_service.files.return_value.create.return_value.execute.return_value = {
            "id": "archive_folder",
            "name": "Archive"
        }
        mock_drive_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            response = client.post(
                "/api/v1/workspace/organize",
                headers=auth_headers,
                json={"insight_id": insight.id, "suggestion_type": "archive_old_files"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["operation_type"] == "archive_old_files"
            assert data["files_affected"] >= 0
    
    @pytest.mark.asyncio
    async def test_get_cleanup_logs_endpoint(self, client, auth_headers, db_session, test_user):
        """Test GET /workspace/cleanup-logs endpoint."""
        # Create test cleanup logs
        log1 = WorkspaceCleanupLog(
            user_id=test_user.id,
            operation_type="archive_old_files",
            performed_at=datetime.utcnow(),
            files_affected=5,
            bytes_freed=10240
        )
        log2 = WorkspaceCleanupLog(
            user_id=test_user.id,
            operation_type="remove_duplicates",
            performed_at=datetime.utcnow() - timedelta(hours=1),
            files_affected=3,
            bytes_freed=3072
        )
        db_session.add_all([log1, log2])
        db_session.commit()
        
        response = client.get("/api/v1/workspace/cleanup-logs", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["operation_type"] == "archive_old_files"  # Most recent first
        assert data[0]["files_affected"] == 5
    
    @pytest.mark.asyncio
    async def test_unauthorized_access(self, client):
        """Test that endpoints require authentication."""
        response = client.post("/api/v1/workspace/analyze")
        assert response.status_code == 401


class TestWorkspaceCleanupOperations:
    """Test workspace cleanup operations."""
    
    @pytest.mark.asyncio
    async def test_archive_old_files(self, db_session, test_user, mock_drive_service):
        """Test archiving old files."""
        insight = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=3,
            total_size_bytes=4096,
            stale_files=[
                {"id": "file3", "name": "old.xlsx", "size": 2048, "last_accessed": "2023-01-01T00:00:00Z", "parents": ["root"]}
            ]
        )
        db_session.add(insight)
        db_session.commit()
        
        # Mock Drive operations
        mock_drive_service.files.return_value.update.return_value.execute.return_value = {"id": "file3"}
        mock_drive_service.files.return_value.create.return_value.execute.return_value = {
            "id": "archive_folder",
            "name": "Archive"
        }
        mock_drive_service.files.return_value.list.return_value.execute.return_value = {"files": []}
        
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            cleanup_log = await analyzer.organize_files(insight.id, "archive_old_files")
            
            assert cleanup_log.operation_type == "archive_old_files"
            assert cleanup_log.files_affected >= 0
    
    @pytest.mark.asyncio
    async def test_organize_by_year(self, db_session, test_user, mock_drive_service):
        """Test organizing files by year."""
        insight = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=3,
            total_size_bytes=4096
        )
        db_session.add(insight)
        db_session.commit()
        
        # Mock Drive operations
        mock_drive_service.files.return_value.list.return_value.execute.return_value = {
            "files": [
                {
                    "id": "file1",
                    "name": "doc.pdf",
                    "mimeType": "application/pdf",
                    "createdTime": "2024-01-01T00:00:00Z",
                    "parents": ["root"]
                }
            ],
            "nextPageToken": None
        }
        mock_drive_service.files.return_value.create.return_value.execute.return_value = {
            "id": "year_folder",
            "name": "2024"
        }
        mock_drive_service.files.return_value.update.return_value.execute.return_value = {"id": "file1"}
        
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            cleanup_log = await analyzer.organize_files(insight.id, "organize_by_year")
            
            assert cleanup_log.operation_type == "organize_by_year"
            assert cleanup_log.files_affected >= 0
    
    @pytest.mark.asyncio
    async def test_remove_duplicates(self, db_session, test_user, mock_drive_service):
        """Test removing duplicate files."""
        insight = WorkspaceInsight(
            user_id=test_user.id,
            analyzed_at=datetime.utcnow(),
            total_files=3,
            total_size_bytes=4096,
            duplicate_files=[
                {
                    "files": [
                        {"id": "file1", "name": "test.docx", "size": 1024, "modified": "2024-02-01T00:00:00Z"},
                        {"id": "file2", "name": "test.docx", "size": 1024, "modified": "2024-01-01T00:00:00Z"}
                    ],
                    "total_size": 2048
                }
            ]
        )
        db_session.add(insight)
        db_session.commit()
        
        # Mock Drive delete
        mock_drive_service.files.return_value.delete.return_value.execute.return_value = {}
        
        with patch("backend.app.services.workspace_analyzer.get_google_service", return_value=mock_drive_service):
            analyzer = WorkspaceAnalyzer(db_session, test_user.id)
            cleanup_log = await analyzer.organize_files(insight.id, "remove_duplicates")
            
            assert cleanup_log.operation_type == "remove_duplicates"
            assert cleanup_log.files_affected >= 0
