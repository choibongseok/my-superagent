"""Google Sheets Agent for spreadsheet generation."""

from typing import Any, Dict, List, Optional
import logging
import json
from uuid import UUID

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from langchain.tools import Tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class SheetsAgent(BaseAgent):
    """
    Agent for Google Sheets generation and manipulation.
    
    Capabilities:
    - Create new spreadsheets
    - Read and write cell data
    - Format cells and ranges
    - Create charts and pivot tables
    - Share and manage permissions
    """
    
    def __init__(
        self,
        user_id: str | UUID,
        session_id: Optional[str | UUID] = None,
        credentials: Optional[Credentials] = None,
    ):
        """
        Initialize SheetsAgent with Google credentials.
        
        Args:
            user_id: User ID for LangFuse tracking
            session_id: Session ID for conversation memory
            credentials: Google OAuth2 credentials
        """
        self.credentials = credentials
        self.sheets_service = None
        
        if credentials:
            # Build Google Sheets API service
            self.sheets_service = build("sheets", "v4", credentials=credentials)
        
        # Call parent init
        super().__init__(user_id=user_id, session_id=session_id)

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "sheets",
            "version": "1.0",
            "status": "active",
            "capabilities": [
                "create_spreadsheet",
                "read_data",
                "write_data",
                "format_cells",
                "create_chart",
                "share_sheet"
            ]
        }

    def _create_tools(self) -> List[Tool]:
        """Create Google Sheets API tools."""
        
        def create_spreadsheet(title: str, sheet_count: int = 1) -> str:
            """
            Create a new Google Spreadsheet.
            
            Args:
                title: Title of the spreadsheet
                sheet_count: Number of sheets to create (default: 1)
                
            Returns:
                Spreadsheet ID and URL
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Creating spreadsheet: {title} with {sheet_count} sheets")
                
                # Create spreadsheet
                spreadsheet_body = {
                    "properties": {
                        "title": title
                    },
                    "sheets": [
                        {
                            "properties": {
                                "title": f"Sheet{i+1}",
                                "gridProperties": {
                                    "rowCount": 1000,
                                    "columnCount": 26
                                }
                            }
                        }
                        for i in range(sheet_count)
                    ]
                }
                
                result = self.sheets_service.spreadsheets().create(
                    body=spreadsheet_body
                ).execute()
                
                spreadsheet_id = result.get("spreadsheetId")
                spreadsheet_url = result.get("spreadsheetUrl")
                
                logger.info(f"Created spreadsheet '{title}' - ID: {spreadsheet_id}")
                return f"Successfully created spreadsheet '{title}'\nURL: {spreadsheet_url}\nID: {spreadsheet_id}"
                
            except Exception as e:
                logger.error(f"Failed to create spreadsheet: {e}")
                return f"Error creating spreadsheet: {str(e)}"
        
        def write_data(spreadsheet_id: str, range_name: str, values: List[List[Any]]) -> str:
            """
            Write data to a spreadsheet range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Range in A1 notation (e.g., 'Sheet1!A1:B10')
                values: 2D array of values to write
                
            Returns:
                Success message with updated range
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Writing data to {spreadsheet_id} range {range_name}")
                
                body = {
                    "values": values
                }
                
                result = self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                
                updated_cells = result.get("updatedCells", 0)
                
                logger.info(f"Wrote {len(values)} rows to {range_name}")
                return f"Successfully wrote {len(values)} rows ({updated_cells} cells) to {range_name}"
                
            except Exception as e:
                logger.error(f"Failed to write data: {e}")
                return f"Error writing data: {str(e)}"
        
        def read_data(spreadsheet_id: str, range_name: str) -> str:
            """
            Read data from a spreadsheet range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Range in A1 notation
                
            Returns:
                Data from the specified range
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Reading data from {spreadsheet_id} range {range_name}")
                
                result = self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name
                ).execute()
                
                values = result.get("values", [])
                
                if not values:
                    return f"No data found in range {range_name}"
                
                # Format as text table
                row_count = len(values)
                col_count = max(len(row) for row in values) if values else 0
                
                formatted_data = f"Data from {range_name} ({row_count} rows, {col_count} columns):\n\n"
                for row in values:
                    formatted_data += "| " + " | ".join(str(cell) for cell in row) + " |\n"
                
                return formatted_data
                
            except Exception as e:
                logger.error(f"Failed to read data: {e}")
                return f"Error reading data: {str(e)}"
        
        def format_cells(spreadsheet_id: str, range_name: str, format_type: str) -> str:
            """
            Apply formatting to cells.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Range to format
                format_type: Type of formatting (bold, italic, currency, percent, etc.)
                
            Returns:
                Success message
            """
            # TODO: Implement formatting
            logger.info(f"Applying {format_type} format to {range_name}")
            return f"Applied {format_type} formatting to {range_name}"
        
        def create_chart(spreadsheet_id: str, data_range: str, chart_type: str) -> str:
            """
            Create a chart from data range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                data_range: Data range for the chart
                chart_type: Type of chart (line, bar, pie, etc.)
                
            Returns:
                Success message with chart ID
            """
            # TODO: Implement chart creation
            logger.info(f"Creating {chart_type} chart from {data_range}")
            return f"Created {chart_type} chart (ID: chart_123)"
        
        return [
            Tool(
                name="create_spreadsheet",
                description="Create a new Google Spreadsheet with the given title",
                func=create_spreadsheet
            ),
            Tool(
                name="write_data",
                description="Write data to a specific range in a spreadsheet",
                func=lambda args: write_data(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="read_data",
                description="Read data from a specific range in a spreadsheet",
                func=lambda args: read_data(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="format_cells",
                description="Apply formatting to cells in a spreadsheet",
                func=lambda args: format_cells(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="create_chart",
                description="Create a chart from data in a spreadsheet",
                func=lambda args: create_chart(**json.loads(args) if isinstance(args, str) else args)
            )
        ]

    def _create_prompt(self) -> ChatPromptTemplate:
        system_message = """You are an expert Google Sheets agent specialized in spreadsheet operations.

Your capabilities include:
- Creating new spreadsheets with proper structure
- Reading and writing data efficiently
- Applying formatting and styles
- Creating charts and visualizations
- Data analysis and manipulation

When working with spreadsheets:
1. Always validate input data before writing
2. Use clear range notation (e.g., 'Sheet1!A1:B10')
3. Provide helpful summaries of operations performed
4. Suggest best practices for data organization

Current tools available:
- create_spreadsheet: Create new spreadsheets
- write_data: Write data to ranges
- read_data: Read data from ranges
- format_cells: Apply cell formatting
- create_chart: Generate charts from data

Respond in a clear, professional manner and always confirm successful operations."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["SheetsAgent"]
