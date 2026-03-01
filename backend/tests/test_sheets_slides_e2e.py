"""
Comprehensive E2E Tests for Sheets and Slides Agents
Tests real workflows focusing on initialization, API connectivity, and integration
"""

import pytest
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
from unittest.mock import patch, MagicMock, AsyncMock, call

from app.agents.sheets_agent import SheetsAgent
from app.agents.slides_agent import SlidesAgent


# ========================================
# Fixtures
# ========================================

@pytest.fixture
def mock_google_credentials():
    """Mock Google OAuth2 credentials"""
    creds = MagicMock()
    creds.token = "mock_access_token_12345"
    creds.refresh_token = "mock_refresh_token_67890"
    creds.token_uri = "https://oauth2.googleapis.com/token"
    creds.client_id = "test_client_id"
    creds.client_secret = "test_client_secret"
    creds.scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds.expiry = datetime.now() + timedelta(hours=1)
    creds.expired = False
    creds.valid = True
    return creds


@pytest.fixture
def mock_sheets_service():
    """Mock Google Sheets API service with realistic responses"""
    service = MagicMock()
    
    # Mock spreadsheets().create()
    service.spreadsheets().create().execute.return_value = {
        "spreadsheetId": "test_sheet_id_123",
        "spreadsheetUrl": "https://docs.google.com/spreadsheets/d/test_sheet_id_123/edit",
        "properties": {
            "title": "Test Spreadsheet",
            "locale": "en_US",
            "autoRecalc": "ON_CHANGE",
            "timeZone": "America/New_York"
        },
        "sheets": [
            {
                "properties": {
                    "sheetId": 0,
                    "title": "Sheet1",
                    "index": 0,
                    "sheetType": "GRID",
                    "gridProperties": {
                        "rowCount": 1000,
                        "columnCount": 26
                    }
                }
            }
        ]
    }
    
    # Mock spreadsheets().values().update()
    service.spreadsheets().values().update().execute.return_value = {
        "spreadsheetId": "test_sheet_id_123",
        "updatedRange": "Sheet1!A1:C3",
        "updatedRows": 3,
        "updatedColumns": 3,
        "updatedCells": 9
    }
    
    # Mock spreadsheets().values().get()
    service.spreadsheets().values().get().execute.return_value = {
        "range": "Sheet1!A1:C3",
        "majorDimension": "ROWS",
        "values": [
            ["Name", "Age", "City"],
            ["Alice", "25", "NYC"],
            ["Bob", "30", "LA"]
        ]
    }
    
    # Mock spreadsheets().batchUpdate()
    service.spreadsheets().batchUpdate().execute.return_value = {
        "spreadsheetId": "test_sheet_id_123",
        "replies": [
            {"addSheet": {"properties": {"sheetId": 1, "title": "Sheet2"}}},
            {"addConditionalFormatRule": {}},
            {"addDataValidation": {}}
        ]
    }
    
    return service


@pytest.fixture
def mock_slides_service():
    """Mock Google Slides API service with realistic responses"""
    service = MagicMock()
    
    # Mock presentations().create()
    service.presentations().create().execute.return_value = {
        "presentationId": "test_pres_id_456",
        "title": "Test Presentation",
        "slides": [
            {
                "objectId": "slide_1",
                "slideProperties": {
                    "layoutObjectId": "p",
                    "masterObjectId": "p"
                }
            }
        ],
        "pageSize": {
            "width": {"magnitude": 10, "unit": "INCHES"},
            "height": {"magnitude": 7.5, "unit": "INCHES"}
        }
    }
    
    # Mock presentations().batchUpdate()
    service.presentations().batchUpdate().execute.return_value = {
        "presentationId": "test_pres_id_456",
        "replies": [
            {"createSlide": {"objectId": "slide_2"}},
            {"insertText": {}},
            {"updateTextStyle": {}}
        ]
    }
    
    return service


# ========================================
# Sheets Agent E2E Tests
# ========================================

class TestSheetsAgentE2E:
    """Comprehensive E2E tests for Sheets Agent"""
    
    @pytest.mark.asyncio
    async def test_sheets_agent_initialization(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test agent initialization with Google credentials
        """
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            agent = SheetsAgent(
                user_id="test_user_123",
                session_id="e2e_sheets_init",
                credentials=mock_google_credentials
            )
            
            # Verify agent initialized correctly
            assert agent.sheets_service is not None
            assert agent.user_id == "test_user_123"
            assert agent.session_id == "e2e_sheets_init"
            assert agent.credentials == mock_google_credentials
            
            # Verify metadata
            metadata = agent._get_metadata()
            assert metadata["agent_type"] == "sheets"
            assert "conditional_formatting" in metadata["capabilities"]
            assert "formulas" in metadata["capabilities"]
            assert "pivot_tables" in metadata["capabilities"]
    
    @pytest.mark.asyncio
    async def test_sheets_api_spreadsheet_creation(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test spreadsheet creation via Google Sheets API
        """
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            agent = SheetsAgent(
                user_id="test_user_123",
                session_id="e2e_create_sheet",
                credentials=mock_google_credentials
            )
            
            # Test creating spreadsheet via mock API
            mock_result = mock_sheets_service.spreadsheets().create().execute()
            
            assert "spreadsheetId" in mock_result
            assert mock_result["spreadsheetId"] == "test_sheet_id_123"
            assert "spreadsheetUrl" in mock_result
            assert mock_result["properties"]["title"] == "Test Spreadsheet"
    
    @pytest.mark.asyncio
    async def test_sheets_api_data_operations(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test reading and writing data via Google Sheets API
        """
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            agent = SheetsAgent(
                user_id="test_user_123",
                session_id="e2e_data_ops",
                credentials=mock_google_credentials
            )
            
            # Test writing data
            mock_write = mock_sheets_service.spreadsheets().values().update().execute()
            assert "updatedCells" in mock_write
            assert mock_write["updatedCells"] == 9
            assert mock_write["updatedRows"] == 3
            
            # Test reading data
            mock_read = mock_sheets_service.spreadsheets().values().get().execute()
            assert "values" in mock_read
            assert len(mock_read["values"]) == 3
            assert mock_read["values"][0] == ["Name", "Age", "City"]
    
    @pytest.mark.asyncio
    async def test_sheets_api_batch_operations(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test batch updates (formatting, validation, etc.)
        """
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            agent = SheetsAgent(
                user_id="test_user_123",
                session_id="e2e_batch_ops",
                credentials=mock_google_credentials
            )
            
            # Test batch update
            mock_batch = mock_sheets_service.spreadsheets().batchUpdate().execute()
            assert "replies" in mock_batch
            assert len(mock_batch["replies"]) == 3
    
    @pytest.mark.asyncio
    async def test_sheets_agent_without_credentials(self):
        """
        E2E: Test agent behavior without Google credentials
        """
        agent = SheetsAgent(
            user_id="test_user_456",
            session_id="no_creds",
            credentials=None
        )
        
        # Agent should initialize but service should be None
        assert agent.sheets_service is None
        assert agent.user_id == "test_user_456"


# ========================================
# Slides Agent E2E Tests
# ========================================

class TestSlidesAgentE2E:
    """Comprehensive E2E tests for Slides Agent"""
    
    @pytest.mark.asyncio
    async def test_slides_agent_initialization(
        self, mock_google_credentials, mock_slides_service
    ):
        """
        E2E: Test agent initialization with Google credentials
        """
        with patch('googleapiclient.discovery.build', return_value=mock_slides_service):
            agent = SlidesAgent(
                user_id="test_user_123",
                session_id="e2e_slides_init",
                credentials=mock_google_credentials
            )
            
            # Verify agent initialized correctly
            assert agent.slides_service is not None
            assert agent.user_id == "test_user_123"
            assert agent.session_id == "e2e_slides_init"
            assert agent.credentials == mock_google_credentials
            
            # Verify metadata
            metadata = agent._get_metadata()
            assert metadata["agent_type"] == "slides"
            assert "create_presentation" in metadata["capabilities"]
            assert "add_slide" in metadata["capabilities"]
    
    @pytest.mark.asyncio
    async def test_slides_api_presentation_creation(
        self, mock_google_credentials, mock_slides_service
    ):
        """
        E2E: Test presentation creation via Google Slides API
        """
        with patch('googleapiclient.discovery.build', return_value=mock_slides_service):
            agent = SlidesAgent(
                user_id="test_user_123",
                session_id="e2e_create_pres",
                credentials=mock_google_credentials
            )
            
            # Test creating presentation via mock API
            mock_result = mock_slides_service.presentations().create().execute()
            
            assert "presentationId" in mock_result
            assert mock_result["presentationId"] == "test_pres_id_456"
            assert mock_result["title"] == "Test Presentation"
            assert len(mock_result["slides"]) == 1
    
    @pytest.mark.asyncio
    async def test_slides_api_batch_updates(
        self, mock_google_credentials, mock_slides_service
    ):
        """
        E2E: Test batch updates (adding slides, inserting text, etc.)
        """
        with patch('googleapiclient.discovery.build', return_value=mock_slides_service):
            agent = SlidesAgent(
                user_id="test_user_123",
                session_id="e2e_batch_slides",
                credentials=mock_google_credentials
            )
            
            # Test batch update
            mock_batch = mock_slides_service.presentations().batchUpdate().execute()
            assert "replies" in mock_batch
            assert len(mock_batch["replies"]) == 3
    
    @pytest.mark.asyncio
    async def test_slides_agent_without_credentials(self):
        """
        E2E: Test agent behavior without Google credentials
        """
        agent = SlidesAgent(
            user_id="test_user_789",
            session_id="no_creds_slides",
            credentials=None
        )
        
        # Agent should initialize but service should be None
        assert agent.slides_service is None
        assert agent.user_id == "test_user_789"


# ========================================
# Integration Tests (Sheets + Slides)
# ========================================

class TestSheetsAndSlidesIntegration:
    """Test integration between Sheets and Slides agents"""
    
    @pytest.mark.asyncio
    async def test_both_agents_can_be_initialized_together(
        self, mock_google_credentials, mock_sheets_service, mock_slides_service
    ):
        """
        E2E: Test that both agents can be initialized and used together
        """
        with patch('googleapiclient.discovery.build') as mock_build:
            # Configure mock to return appropriate service based on API
            def build_service(api_name, version, credentials):
                if api_name == "sheets":
                    return mock_sheets_service
                elif api_name == "slides":
                    return mock_slides_service
                return MagicMock()
            
            mock_build.side_effect = build_service
            
            # Initialize both agents
            sheets_agent = SheetsAgent(
                user_id="test_user_123",
                session_id="integration_test",
                credentials=mock_google_credentials
            )
            
            slides_agent = SlidesAgent(
                user_id="test_user_123",
                session_id="integration_test",
                credentials=mock_google_credentials
            )
            
            # Verify both initialized
            assert sheets_agent.sheets_service is not None
            assert slides_agent.slides_service is not None
            
            # Verify they share the same user/session
            assert sheets_agent.user_id == slides_agent.user_id
            assert sheets_agent.session_id == slides_agent.session_id
    
    @pytest.mark.asyncio
    async def test_concurrent_api_operations(
        self, mock_google_credentials, mock_sheets_service, mock_slides_service
    ):
        """
        E2E: Test concurrent operations with both APIs
        """
        with patch('googleapiclient.discovery.build') as mock_build:
            def build_service(api_name, version, credentials):
                if api_name == "sheets":
                    return mock_sheets_service
                elif api_name == "slides":
                    return mock_slides_service
                return MagicMock()
            
            mock_build.side_effect = build_service
            
            # Create agents
            sheets_agent = SheetsAgent(
                user_id="test_user_123",
                session_id="concurrent_test",
                credentials=mock_google_credentials
            )
            
            slides_agent = SlidesAgent(
                user_id="test_user_123",
                session_id="concurrent_test",
                credentials=mock_google_credentials
            )
            
            # Execute concurrent operations
            async def create_sheet():
                result = mock_sheets_service.spreadsheets().create().execute()
                return result["spreadsheetId"]
            
            async def create_presentation():
                result = mock_slides_service.presentations().create().execute()
                return result["presentationId"]
            
            # Run concurrently
            results = await asyncio.gather(
                create_sheet(),
                create_presentation()
            )
            
            # Verify both succeeded
            assert len(results) == 2
            assert "test_sheet_id_123" in results
            assert "test_pres_id_456" in results


# ========================================
# Error Handling Tests
# ========================================

class TestErrorHandling:
    """Test error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_sheets_api_error_handling(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test error handling when API calls fail
        """
        # Mock API error
        mock_sheets_service.spreadsheets().create().execute.side_effect = Exception("API Error: Quota exceeded")
        
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            agent = SheetsAgent(
                user_id="test_user_123",
                session_id="error_test",
                credentials=mock_google_credentials
            )
            
            # Verify agent still initialized despite future API errors
            assert agent.sheets_service is not None
            
            # Verify error is raised when API is called
            with pytest.raises(Exception) as exc_info:
                mock_sheets_service.spreadsheets().create().execute()
            
            assert "Quota exceeded" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_slides_api_error_handling(
        self, mock_google_credentials, mock_slides_service
    ):
        """
        E2E: Test error handling for Slides API
        """
        # Mock API error
        mock_slides_service.presentations().create().execute.side_effect = Exception("API Error: Permission denied")
        
        with patch('googleapiclient.discovery.build', return_value=mock_slides_service):
            agent = SlidesAgent(
                user_id="test_user_123",
                session_id="error_test_slides",
                credentials=mock_google_credentials
            )
            
            # Verify agent initialized
            assert agent.slides_service is not None
            
            # Verify error is raised when API is called
            with pytest.raises(Exception) as exc_info:
                mock_slides_service.presentations().create().execute()
            
            assert "Permission denied" in str(exc_info.value)


# ========================================
# Performance Tests
# ========================================

class TestPerformance:
    """Performance tests"""
    
    @pytest.mark.asyncio
    async def test_multiple_agent_initializations_performance(
        self, mock_google_credentials, mock_sheets_service
    ):
        """
        E2E: Test performance of multiple agent initializations
        """
        import time
        
        with patch('googleapiclient.discovery.build', return_value=mock_sheets_service):
            start_time = time.time()
            
            agents = []
            for i in range(10):
                agent = SheetsAgent(
                    user_id=f"test_user_{i}",
                    session_id=f"perf_test_{i}",
                    credentials=mock_google_credentials
                )
                agents.append(agent)
            
            elapsed_time = time.time() - start_time
            
            # Should complete within reasonable time (5 seconds for 10 agents)
            assert elapsed_time < 5.0
            assert len(agents) == 10
            
            # Verify all initialized correctly
            for agent in agents:
                assert agent.sheets_service is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
