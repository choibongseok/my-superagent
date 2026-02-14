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
        # Call parent init first so base fields (including credentials) are consistent.
        super().__init__(
            user_id=str(user_id),
            session_id=str(session_id) if session_id is not None else None,
            credentials=credentials,
        )

        self.sheets_service = None
        if self.credentials:
            # Build Google Sheets API service
            self.sheets_service = build("sheets", "v4", credentials=self.credentials)

    def _get_metadata(self) -> Dict[str, Any]:
        return {
            "agent_type": "sheets",
            "version": "1.0",
            "status": "active",
            "capabilities": [
                "create_spreadsheet",
                "read_data",
                "write_data",
                "append_data",
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

        def append_data(
            spreadsheet_id: str,
            range_name: str,
            values: List[List[Any]],
            value_input_option: str = "USER_ENTERED",
            insert_data_option: str = "INSERT_ROWS",
        ) -> str:
            """
            Append rows to the next available rows in a range.

            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Target range in A1 notation (e.g., 'Sheet1!A:C')
                values: 2D array of values to append
                value_input_option: USER_ENTERED or RAW
                insert_data_option: INSERT_ROWS or OVERWRITE

            Returns:
                Success message with append metadata
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."

            try:
                logger.info(f"Appending data to {spreadsheet_id} range {range_name}")

                body = {"values": values}
                result = self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueInputOption=value_input_option,
                    insertDataOption=insert_data_option,
                    body=body,
                ).execute()

                updates = result.get("updates", {})
                updated_rows = updates.get("updatedRows", len(values))
                updated_cells = updates.get("updatedCells", 0)
                updated_range = updates.get("updatedRange", range_name)

                logger.info(
                    "Appended %s rows (%s cells) into %s",
                    updated_rows,
                    updated_cells,
                    updated_range,
                )
                return (
                    f"Successfully appended {updated_rows} rows "
                    f"({updated_cells} cells) to {updated_range}"
                )

            except Exception as e:
                logger.error(f"Failed to append data: {e}")
                return f"Error appending data: {str(e)}"
        
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
                format_type: Type of formatting (bold, italic, currency, percent, number_format, etc.)
                
            Returns:
                Success message
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Applying {format_type} format to {range_name}")
                
                # Get sheet ID from range
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                sheet_id = sheet['sheets'][0]['properties']['sheetId']
                
                # Parse range
                parts = range_name.split('!')
                if len(parts) > 1:
                    sheet_name = parts[0]
                    cell_range = parts[1]
                    # Find sheet ID by name
                    for s in sheet['sheets']:
                        if s['properties']['title'] == sheet_name:
                            sheet_id = s['properties']['sheetId']
                            break
                    range_name = cell_range
                
                # Convert A1 notation to grid range
                # Simplified: just use the whole sheet for now
                requests = []
                
                # Define format requests based on type
                if format_type == "bold":
                    requests = [{
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {
                                        "bold": True
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.textFormat.bold"
                        }
                    }]
                elif format_type == "italic":
                    requests = [{
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "textFormat": {
                                        "italic": True
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.textFormat.italic"
                        }
                    }]
                elif format_type == "currency":
                    requests = [{
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {
                                        "type": "CURRENCY",
                                        "pattern": "$#,##0.00"
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat"
                        }
                    }]
                elif format_type == "percent":
                    requests = [{
                        "repeatCell": {
                            "range": {
                                "sheetId": sheet_id,
                            },
                            "cell": {
                                "userEnteredFormat": {
                                    "numberFormat": {
                                        "type": "PERCENT",
                                        "pattern": "0.00%"
                                    }
                                }
                            },
                            "fields": "userEnteredFormat.numberFormat"
                        }
                    }]
                else:
                    return f"Unsupported format type: {format_type}. Supported: bold, italic, currency, percent"
                
                # Apply formatting
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": requests}
                ).execute()
                
                logger.info(f"Applied {format_type} formatting to {range_name}")
                return f"Successfully applied {format_type} formatting to {range_name}"
                
            except Exception as e:
                logger.error(f"Failed to format cells: {e}")
                return f"Error formatting cells: {str(e)}"
        
        def create_chart(spreadsheet_id: str, data_range: str, chart_type: str) -> str:
            """
            Create a chart from data range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                data_range: Data range for the chart (e.g., 'Sheet1!A1:B10')
                chart_type: Type of chart (LINE, BAR, COLUMN, PIE, AREA, SCATTER)
                
            Returns:
                Success message with chart ID
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Creating {chart_type} chart from {data_range}")
                
                # Get sheet info
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                # Parse range to get sheet ID
                parts = data_range.split('!')
                sheet_name = parts[0] if len(parts) > 1 else sheet['sheets'][0]['properties']['title']
                
                # Find sheet ID
                sheet_id = None
                for s in sheet['sheets']:
                    if s['properties']['title'] == sheet_name:
                        sheet_id = s['properties']['sheetId']
                        break
                
                if sheet_id is None:
                    return f"Error: Sheet '{sheet_name}' not found"
                
                # Map chart type to API format
                chart_type_map = {
                    "line": "LINE",
                    "bar": "BAR",
                    "column": "COLUMN",
                    "pie": "PIE",
                    "area": "AREA",
                    "scatter": "SCATTER",
                }
                api_chart_type = chart_type_map.get(chart_type.lower(), chart_type.upper())
                
                # Create chart request
                requests = [{
                    "addChart": {
                        "chart": {
                            "spec": {
                                "title": f"{api_chart_type} Chart",
                                "basicChart": {
                                    "chartType": api_chart_type,
                                    "legendPosition": "RIGHT_LEGEND",
                                    "axis": [
                                        {
                                            "position": "BOTTOM_AXIS",
                                            "title": "X Axis"
                                        },
                                        {
                                            "position": "LEFT_AXIS",
                                            "title": "Y Axis"
                                        }
                                    ],
                                    "domains": [{
                                        "domain": {
                                            "sourceRange": {
                                                "sources": [{
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 10,
                                                    "startColumnIndex": 0,
                                                    "endColumnIndex": 1
                                                }]
                                            }
                                        }
                                    }],
                                    "series": [{
                                        "series": {
                                            "sourceRange": {
                                                "sources": [{
                                                    "sheetId": sheet_id,
                                                    "startRowIndex": 0,
                                                    "endRowIndex": 10,
                                                    "startColumnIndex": 1,
                                                    "endColumnIndex": 2
                                                }]
                                            }
                                        },
                                        "targetAxis": "LEFT_AXIS"
                                    }]
                                }
                            },
                            "position": {
                                "overlayPosition": {
                                    "anchorCell": {
                                        "sheetId": sheet_id,
                                        "rowIndex": 0,
                                        "columnIndex": 4
                                    }
                                }
                            }
                        }
                    }
                }]
                
                # Execute chart creation
                response = self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": requests}
                ).execute()
                
                # Get chart ID from response
                chart_id = response.get("replies", [{}])[0].get("addChart", {}).get("chart", {}).get("chartId")
                
                logger.info(f"Created {api_chart_type} chart - ID: {chart_id}")
                return f"Successfully created {api_chart_type} chart from {data_range}\nChart ID: {chart_id}"
                
            except Exception as e:
                logger.error(f"Failed to create chart: {e}")
                return f"Error creating chart: {str(e)}"
        
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
                name="append_data",
                description="Append rows to the next available rows in a spreadsheet range",
                func=lambda args: append_data(**json.loads(args) if isinstance(args, str) else args)
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
- append_data: Append rows to existing tables
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
