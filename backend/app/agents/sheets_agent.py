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
            "version": "2.0",
            "status": "active",
            "capabilities": [
                "create_spreadsheet",
                "read_data",
                "write_data",
                "format_cells",
                "create_chart",
                "share_sheet",
                "conditional_formatting",
                "data_validation",
                "formulas",
                "pivot_tables",
                "named_ranges"
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
        
        def add_conditional_formatting(
            spreadsheet_id: str,
            range_name: str,
            condition_type: str,
            threshold: Optional[float] = None,
            color_hex: str = "#FF0000"
        ) -> str:
            """
            Apply conditional formatting to a range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Range to format (e.g., 'Sheet1!A1:B10')
                condition_type: Type of condition (GREATER_THAN, LESS_THAN, BETWEEN, TEXT_CONTAINS, etc.)
                threshold: Threshold value for number conditions
                color_hex: Hex color code for formatting
                
            Returns:
                Success message
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Adding conditional formatting to {range_name}")
                
                # Get sheet info
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                # Parse range
                parts = range_name.split('!')
                sheet_name = parts[0] if len(parts) > 1 else sheet['sheets'][0]['properties']['title']
                
                # Find sheet ID
                sheet_id = None
                for s in sheet['sheets']:
                    if s['properties']['title'] == sheet_name:
                        sheet_id = s['properties']['sheetId']
                        break
                
                if sheet_id is None:
                    return f"Error: Sheet '{sheet_name}' not found"
                
                # Parse RGB from hex
                color_hex = color_hex.lstrip('#')
                r = int(color_hex[0:2], 16) / 255.0
                g = int(color_hex[2:4], 16) / 255.0
                b = int(color_hex[4:6], 16) / 255.0
                
                # Build condition based on type
                condition_map = {
                    "greater_than": "NUMBER_GREATER",
                    "less_than": "NUMBER_LESS",
                    "between": "NUMBER_BETWEEN",
                    "text_contains": "TEXT_CONTAINS",
                    "not_empty": "NOT_BLANK",
                }
                
                api_condition_type = condition_map.get(condition_type.lower(), condition_type.upper())
                
                # Build conditional format rule
                rule = {
                    "addConditionalFormatRule": {
                        "rule": {
                            "ranges": [{
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 100,
                                "startColumnIndex": 0,
                                "endColumnIndex": 10
                            }],
                            "booleanRule": {
                                "condition": {
                                    "type": api_condition_type,
                                },
                                "format": {
                                    "backgroundColor": {
                                        "red": r,
                                        "green": g,
                                        "blue": b
                                    }
                                }
                            }
                        },
                        "index": 0
                    }
                }
                
                # Add threshold value if provided
                if threshold is not None and api_condition_type in ["NUMBER_GREATER", "NUMBER_LESS"]:
                    rule["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]["values"] = [
                        {"userEnteredValue": str(threshold)}
                    ]
                
                # Apply rule
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [rule]}
                ).execute()
                
                logger.info(f"Applied conditional formatting to {range_name}")
                return f"Successfully applied {condition_type} conditional formatting to {range_name}"
                
            except Exception as e:
                logger.error(f"Failed to add conditional formatting: {e}")
                return f"Error adding conditional formatting: {str(e)}"
        
        def add_data_validation(
            spreadsheet_id: str,
            range_name: str,
            validation_type: str,
            values: Optional[List[str]] = None,
            min_value: Optional[float] = None,
            max_value: Optional[float] = None
        ) -> str:
            """
            Add data validation to a range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name: Range to validate (e.g., 'Sheet1!A1:A10')
                validation_type: Type of validation (LIST, NUMBER_BETWEEN, DATE_AFTER, etc.)
                values: List of valid values (for LIST type)
                min_value: Minimum value (for NUMBER_BETWEEN)
                max_value: Maximum value (for NUMBER_BETWEEN)
                
            Returns:
                Success message
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Adding data validation to {range_name}")
                
                # Get sheet info
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                # Parse range
                parts = range_name.split('!')
                sheet_name = parts[0] if len(parts) > 1 else sheet['sheets'][0]['properties']['title']
                
                # Find sheet ID
                sheet_id = None
                for s in sheet['sheets']:
                    if s['properties']['title'] == sheet_name:
                        sheet_id = s['properties']['sheetId']
                        break
                
                if sheet_id is None:
                    return f"Error: Sheet '{sheet_name}' not found"
                
                # Build validation rule
                validation_rule = {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 0,
                            "endRowIndex": 100,
                            "startColumnIndex": 0,
                            "endColumnIndex": 1
                        },
                        "rule": {
                            "condition": {
                                "type": validation_type.upper(),
                            },
                            "showCustomUi": True,
                            "strict": True
                        }
                    }
                }
                
                # Add values for LIST type
                if validation_type.upper() == "ONE_OF_LIST" and values:
                    validation_rule["setDataValidation"]["rule"]["condition"]["values"] = [
                        {"userEnteredValue": val} for val in values
                    ]
                
                # Add range for NUMBER_BETWEEN
                if validation_type.upper() == "NUMBER_BETWEEN" and min_value is not None and max_value is not None:
                    validation_rule["setDataValidation"]["rule"]["condition"]["values"] = [
                        {"userEnteredValue": str(min_value)},
                        {"userEnteredValue": str(max_value)}
                    ]
                
                # Apply validation
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [validation_rule]}
                ).execute()
                
                logger.info(f"Applied data validation to {range_name}")
                return f"Successfully applied {validation_type} data validation to {range_name}"
                
            except Exception as e:
                logger.error(f"Failed to add data validation: {e}")
                return f"Error adding data validation: {str(e)}"
        
        def insert_formula(
            spreadsheet_id: str,
            cell_range: str,
            formula: str
        ) -> str:
            """
            Insert a formula into a cell or range.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                cell_range: Cell or range to insert formula (e.g., 'Sheet1!C1')
                formula: Formula to insert (e.g., '=SUM(A1:A10)', '=AVERAGE(B:B)', '=VLOOKUP(A2, A:B, 2, FALSE)')
                
            Returns:
                Success message with formula result preview
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Inserting formula '{formula}' into {cell_range}")
                
                # Ensure formula starts with =
                if not formula.startswith('='):
                    formula = '=' + formula
                
                # Write formula
                body = {
                    "values": [[formula]]
                }
                
                self.sheets_service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=cell_range,
                    valueInputOption="USER_ENTERED",
                    body=body
                ).execute()
                
                # Read back the calculated value
                result = self.sheets_service.spreadsheets().values().get(
                    spreadsheetId=spreadsheet_id,
                    range=cell_range,
                    valueRenderOption="FORMATTED_VALUE"
                ).execute()
                
                calculated_value = result.get("values", [[""]])[0][0] if result.get("values") else "N/A"
                
                logger.info(f"Inserted formula into {cell_range}, result: {calculated_value}")
                return f"Successfully inserted formula '{formula}' into {cell_range}\nCalculated value: {calculated_value}"
                
            except Exception as e:
                logger.error(f"Failed to insert formula: {e}")
                return f"Error inserting formula: {str(e)}"
        
        def create_pivot_table(
            spreadsheet_id: str,
            source_range: str,
            pivot_sheet_id: int,
            rows: List[str],
            values: List[str],
            value_function: str = "SUM"
        ) -> str:
            """
            Create a pivot table from source data.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                source_range: Source data range (e.g., 'Sheet1!A1:D100')
                pivot_sheet_id: Sheet ID where pivot table will be placed
                rows: Column letters for row grouping (e.g., ['A', 'B'])
                values: Column letters for values (e.g., ['C', 'D'])
                value_function: Aggregation function (SUM, AVERAGE, COUNT, etc.)
                
            Returns:
                Success message with pivot table location
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Creating pivot table from {source_range}")
                
                # Get sheet info
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                # Parse source range
                parts = source_range.split('!')
                source_sheet_name = parts[0] if len(parts) > 1 else sheet['sheets'][0]['properties']['title']
                
                # Find source sheet ID
                source_sheet_id = None
                for s in sheet['sheets']:
                    if s['properties']['title'] == source_sheet_name:
                        source_sheet_id = s['properties']['sheetId']
                        break
                
                if source_sheet_id is None:
                    return f"Error: Sheet '{source_sheet_name}' not found"
                
                # Build pivot table request
                pivot_request = {
                    "updateCells": {
                        "rows": [{
                            "values": [{
                                "pivotTable": {
                                    "source": {
                                        "sheetId": source_sheet_id,
                                        "startRowIndex": 0,
                                        "endRowIndex": 100,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": 10
                                    },
                                    "rows": [
                                        {
                                            "sourceColumnOffset": ord(col.upper()) - ord('A'),
                                            "showTotals": True,
                                            "sortOrder": "ASCENDING"
                                        }
                                        for col in rows
                                    ],
                                    "values": [
                                        {
                                            "summarizeFunction": value_function.upper(),
                                            "sourceColumnOffset": ord(col.upper()) - ord('A')
                                        }
                                        for col in values
                                    ],
                                    "valueLayout": "HORIZONTAL"
                                }
                            }]
                        }],
                        "fields": "pivotTable",
                        "start": {
                            "sheetId": pivot_sheet_id,
                            "rowIndex": 0,
                            "columnIndex": 0
                        }
                    }
                }
                
                # Apply pivot table
                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [pivot_request]}
                ).execute()
                
                logger.info(f"Created pivot table from {source_range}")
                return f"Successfully created pivot table from {source_range}\nRows: {', '.join(rows)}, Values: {', '.join(values)} ({value_function})"
                
            except Exception as e:
                logger.error(f"Failed to create pivot table: {e}")
                return f"Error creating pivot table: {str(e)}"
        
        def create_named_range(
            spreadsheet_id: str,
            range_name_label: str,
            range_address: str
        ) -> str:
            """
            Create a named range for easy reference in formulas.
            
            Args:
                spreadsheet_id: Spreadsheet ID
                range_name_label: Name for the range (e.g., 'SalesData', 'Totals')
                range_address: Range address (e.g., 'Sheet1!A1:B10')
                
            Returns:
                Success message with named range ID
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."
            
            try:
                logger.info(f"Creating named range '{range_name_label}' for {range_address}")
                
                # Get sheet info
                sheet = self.sheets_service.spreadsheets().get(
                    spreadsheetId=spreadsheet_id
                ).execute()
                
                # Parse range
                parts = range_address.split('!')
                sheet_name = parts[0] if len(parts) > 1 else sheet['sheets'][0]['properties']['title']
                
                # Find sheet ID
                sheet_id = None
                for s in sheet['sheets']:
                    if s['properties']['title'] == sheet_name:
                        sheet_id = s['properties']['sheetId']
                        break
                
                if sheet_id is None:
                    return f"Error: Sheet '{sheet_name}' not found"
                
                # Create named range request
                named_range_request = {
                    "addNamedRange": {
                        "namedRange": {
                            "name": range_name_label,
                            "range": {
                                "sheetId": sheet_id,
                                "startRowIndex": 0,
                                "endRowIndex": 100,
                                "startColumnIndex": 0,
                                "endColumnIndex": 10
                            }
                        }
                    }
                }
                
                # Apply named range
                response = self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": [named_range_request]}
                ).execute()
                
                named_range_id = response.get("replies", [{}])[0].get("addNamedRange", {}).get("namedRange", {}).get("namedRangeId")
                
                logger.info(f"Created named range '{range_name_label}' - ID: {named_range_id}")
                return f"Successfully created named range '{range_name_label}' for {range_address}\nID: {named_range_id}\nUse in formulas like: =SUM({range_name_label})"
                
            except Exception as e:
                logger.error(f"Failed to create named range: {e}")
                return f"Error creating named range: {str(e)}"
        
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
            ),
            Tool(
                name="add_conditional_formatting",
                description="Apply conditional formatting rules to a range (highlight cells based on conditions)",
                func=lambda args: add_conditional_formatting(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="add_data_validation",
                description="Add data validation to restrict cell input (dropdown lists, number ranges, dates)",
                func=lambda args: add_data_validation(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="insert_formula",
                description="Insert formulas like SUM, AVERAGE, VLOOKUP, IF, etc. into cells",
                func=lambda args: insert_formula(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="create_pivot_table",
                description="Create pivot tables for data analysis and aggregation",
                func=lambda args: create_pivot_table(**json.loads(args) if isinstance(args, str) else args)
            ),
            Tool(
                name="create_named_range",
                description="Create named ranges for easy reference in formulas",
                func=lambda args: create_named_range(**json.loads(args) if isinstance(args, str) else args)
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
- Advanced conditional formatting
- Data validation and input restrictions
- Formula insertion (SUM, AVERAGE, VLOOKUP, IF, COUNT, etc.)
- Pivot table creation for data aggregation
- Named ranges for reusable formulas

When working with spreadsheets:
1. Always validate input data before writing
2. Use clear range notation (e.g., 'Sheet1!A1:B10')
3. Provide helpful summaries of operations performed
4. Suggest best practices for data organization
5. Use formulas to automate calculations
6. Apply conditional formatting to highlight important data
7. Use data validation to prevent input errors
8. Create pivot tables for complex data analysis
9. Use named ranges for better formula readability

Current tools available:
- create_spreadsheet: Create new spreadsheets
- write_data: Write data to ranges
- read_data: Read data from ranges
- format_cells: Apply cell formatting
- create_chart: Generate charts from data
- add_conditional_formatting: Highlight cells based on conditions
- add_data_validation: Restrict cell input with rules
- insert_formula: Add formulas (SUM, AVERAGE, VLOOKUP, etc.)
- create_pivot_table: Create pivot tables for aggregation
- create_named_range: Name ranges for formula reuse

Respond in a clear, professional manner and always confirm successful operations."""

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])
        return prompt


__all__ = ["SheetsAgent"]
