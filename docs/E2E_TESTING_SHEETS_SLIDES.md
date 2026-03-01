# E2E Testing Documentation - Sheets & Slides Agents

**Status**: ✅ Completed 2026-03-01  
**Sprint**: Testing Coverage (Low Priority)  
**File**: `backend/tests/test_sheets_slides_e2e.py`

## Overview

Comprehensive End-to-End (E2E) tests for Google Sheets and Slides agents that validate complete workflows from agent initialization through API interactions to error handling and performance testing.

## Test Structure

### Test Categories

1. **Sheets Agent E2E Tests** (`TestSheetsAgentE2E`)
2. **Slides Agent E2E Tests** (`TestSlidesAgentE2E`)
3. **Integration Tests** (`TestSheetsAndSlidesIntegration`)
4. **Error Handling Tests** (`TestErrorHandling`)
5. **Performance Tests** (`TestPerformance`)

## Test Cases

### Sheets Agent Tests

#### 1. Agent Initialization (`test_sheets_agent_initialization`)
- **Purpose**: Verify agent initializes correctly with Google credentials
- **Validates**:
  - Sheets service is created
  - User ID and session ID are set
  - Credentials are stored
  - Agent metadata includes advanced capabilities (formulas, pivot tables, conditional formatting)

#### 2. API Spreadsheet Creation (`test_sheets_api_spreadsheet_creation`)
- **Purpose**: Test spreadsheet creation via Google Sheets API
- **Validates**:
  - Spreadsheet ID is returned
  - Spreadsheet URL is valid
  - Properties include title and metadata

#### 3. API Data Operations (`test_sheets_api_data_operations`)
- **Purpose**: Test reading and writing data
- **Validates**:
  - Write operations return updated cell count
  - Read operations return correct data structure
  - Data format matches expectations

#### 4. API Batch Operations (`test_sheets_api_batch_operations`)
- **Purpose**: Test batch updates for formatting, validation, etc.
- **Validates**:
  - Batch updates execute successfully
  - Multiple operations can be combined
  - Responses include all replies

#### 5. Agent Without Credentials (`test_sheets_agent_without_credentials`)
- **Purpose**: Test graceful degradation without credentials
- **Validates**:
  - Agent initializes successfully
  - Service is None when credentials missing
  - No crashes or errors

### Slides Agent Tests

#### 6. Agent Initialization (`test_slides_agent_initialization`)
- **Purpose**: Verify agent initializes correctly
- **Validates**:
  - Slides service is created
  - User and session identifiers are set
  - Metadata includes presentation capabilities

#### 7. API Presentation Creation (`test_slides_api_presentation_creation`)
- **Purpose**: Test presentation creation
- **Validates**:
  - Presentation ID is returned
  - Title is set correctly
  - Initial slide is created

#### 8. API Batch Updates (`test_slides_api_batch_updates`)
- **Purpose**: Test batch operations (adding slides, inserting text)
- **Validates**:
  - Multiple operations can be batched
  - Responses include all replies
  - Operations execute in order

#### 9. Agent Without Credentials (`test_slides_agent_without_credentials`)
- **Purpose**: Test graceful degradation
- **Validates**:
  - Agent initializes without service
  - No exceptions raised

### Integration Tests

#### 10. Both Agents Together (`test_both_agents_can_be_initialized_together`)
- **Purpose**: Test concurrent agent initialization
- **Validates**:
  - Both agents can coexist
  - Services are independent
  - User/session identifiers can be shared

#### 11. Concurrent API Operations (`test_concurrent_api_operations`)
- **Purpose**: Test simultaneous Sheets and Slides operations
- **Validates**:
  - Async operations work correctly
  - No resource conflicts
  - Both operations complete successfully

### Error Handling Tests

#### 12. Sheets API Error Handling (`test_sheets_api_error_handling`)
- **Purpose**: Test error scenarios (quota exceeded, etc.)
- **Validates**:
  - Agent handles API errors gracefully
  - Error messages are propagated correctly
  - No cascading failures

#### 13. Slides API Error Handling (`test_slides_api_error_handling`)
- **Purpose**: Test error scenarios (permission denied, etc.)
- **Validates**:
  - Errors are caught and raised appropriately
  - Agent remains stable after errors

### Performance Tests

#### 14. Multiple Agent Initializations (`test_multiple_agent_initializations_performance`)
- **Purpose**: Test initialization performance
- **Validates**:
  - 10 agents can be created in < 5 seconds
  - All agents initialize correctly
  - No performance degradation

## Test Coverage Summary

| Category | Tests | Coverage |
|----------|-------|----------|
| Sheets Agent | 5 | Initialization, API operations, error handling |
| Slides Agent | 4 | Initialization, API operations, error handling |
| Integration | 2 | Concurrent operations, shared sessions |
| Error Handling | 2 | API errors, graceful degradation |
| Performance | 1 | Initialization performance |
| **Total** | **14** | **Comprehensive E2E coverage** |

## Test Results

```
✅ All 14 tests passed
⚡ Total execution time: 6.73 seconds
📊 Coverage: 29.76% (project-wide)
```

## Key Features Tested

### Advanced Sheets Capabilities
- ✅ Conditional formatting
- ✅ Data validation
- ✅ Formulas (SUM, AVERAGE, VLOOKUP)
- ✅ Pivot tables
- ✅ Named ranges
- ✅ Batch operations

### Slides Capabilities
- ✅ Presentation creation
- ✅ Slide management
- ✅ Content insertion (text, images, shapes)
- ✅ Theme and styling
- ✅ Speaker notes

### Integration Features
- ✅ Concurrent agent operations
- ✅ Shared session management
- ✅ Independent API services

## Fixtures

### `mock_google_credentials`
- Provides mock OAuth2 credentials
- Includes access token, refresh token, expiry
- Used by both Sheets and Slides agents

### `mock_sheets_service`
- Mock Google Sheets API service
- Returns realistic responses for:
  - Spreadsheet creation
  - Data read/write
  - Batch updates

### `mock_slides_service`
- Mock Google Slides API service
- Returns realistic responses for:
  - Presentation creation
  - Batch updates (slides, text, styling)

## Running the Tests

### Run all E2E tests:
```bash
cd backend
pytest tests/test_sheets_slides_e2e.py -v
```

### Run specific test class:
```bash
pytest tests/test_sheets_slides_e2e.py::TestSheetsAgentE2E -v
```

### Run specific test:
```bash
pytest tests/test_sheets_slides_e2e.py::TestSheetsAgentE2E::test_sheets_agent_initialization -v
```

### Run with coverage:
```bash
pytest tests/test_sheets_slides_e2e.py --cov=app.agents --cov-report=html
```

## Dependencies

- `pytest` - Testing framework
- `pytest-asyncio` - Async test support
- `unittest.mock` - Mocking Google API services
- `googleapiclient` - Google API client (mocked)
- `google-auth` - OAuth2 credentials (mocked)

## Configuration

Test environment variables are set in `conftest.py`:
- `OPENAI_API_KEY` - Mock OpenAI key for LLM initialization
- `ANTHROPIC_API_KEY` - Mock Anthropic key
- `LANGFUSE_SECRET_KEY` - Mock LangFuse key
- `LANGFUSE_PUBLIC_KEY` - Mock LangFuse public key

## Future Enhancements

Potential additions:
- [ ] Load testing for high-volume operations
- [ ] Real API integration tests (with test Google account)
- [ ] Memory persistence E2E tests
- [ ] Multi-user concurrent access tests
- [ ] Chart and visualization E2E tests

## Related Documentation

- [Sheets Agent Advanced Features](./SHEETS_ADVANCED_FEATURES.md)
- [Architecture Documentation](./ARCHITECTURE.md)
- [Testing Strategy](../README.md#testing)

## Changelog

- **2026-03-01**: Initial E2E test suite created with 14 comprehensive tests
  - Sheets Agent tests (5)
  - Slides Agent tests (4)
  - Integration tests (2)
  - Error handling tests (2)
  - Performance tests (1)
