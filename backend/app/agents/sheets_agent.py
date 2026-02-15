"""Google Sheets Agent for spreadsheet generation."""

from typing import Any, Dict, List, Optional
import logging
import json
import re
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

    @staticmethod
    def _column_to_index(column_label: str) -> int:
        """Convert spreadsheet column labels (A, Z, AA...) into zero-based indexes."""
        if not column_label:
            raise ValueError("Column label cannot be empty")

        result = 0
        for char in column_label.upper():
            if not ("A" <= char <= "Z"):
                raise ValueError(f"Invalid column label: {column_label}")
            result = result * 26 + (ord(char) - ord("A") + 1)

        return result - 1

    @classmethod
    def _parse_a1_component(cls, component: str) -> tuple[Optional[int], Optional[int]]:
        """Parse a single A1 component (e.g., A1, A, 10) into column/row indexes."""
        cleaned = component.strip().replace("$", "")
        if not cleaned:
            return None, None

        match = re.fullmatch(r"([A-Za-z]*)(\d*)", cleaned)
        if not match:
            raise ValueError(f"Invalid A1 component: {component}")

        col_label, row_label = match.groups()
        if not col_label and not row_label:
            raise ValueError(f"Invalid A1 component: {component}")

        col_index = cls._column_to_index(col_label) if col_label else None
        row_index = int(row_label) - 1 if row_label else None

        if row_index is not None and row_index < 0:
            raise ValueError(f"Row must be >= 1 in A1 component: {component}")

        return col_index, row_index

    @classmethod
    def _parse_a1_range_bounds(cls, cell_range: str) -> Dict[str, int]:
        """Parse A1 notation into Google Sheets GridRange bounds."""
        normalized = cell_range.strip()
        if not normalized:
            return {}

        if ":" in normalized:
            start_component, end_component = normalized.split(":", 1)
            start_col, start_row = cls._parse_a1_component(start_component)
            end_col, end_row = cls._parse_a1_component(end_component)
        else:
            start_col, start_row = cls._parse_a1_component(normalized)
            end_col = start_col + 1 if start_col is not None else None
            end_row = start_row + 1 if start_row is not None else None

        bounds: Dict[str, int] = {}
        if start_row is not None:
            bounds["startRowIndex"] = start_row
        if end_row is not None:
            bounds["endRowIndex"] = end_row + 1 if ":" in normalized else end_row

        if start_col is not None:
            bounds["startColumnIndex"] = start_col
        if end_col is not None:
            bounds["endColumnIndex"] = end_col + 1 if ":" in normalized else end_col

        # Normalize to explicit exclusive end indexes when range notation provides both ends.
        if ":" in normalized:
            if "endRowIndex" in bounds and "startRowIndex" in bounds:
                bounds["endRowIndex"] = max(
                    bounds["endRowIndex"], bounds["startRowIndex"] + 1
                )
            if "endColumnIndex" in bounds and "startColumnIndex" in bounds:
                bounds["endColumnIndex"] = max(
                    bounds["endColumnIndex"], bounds["startColumnIndex"] + 1
                )

        return bounds

    @staticmethod
    def _split_sheet_and_range(range_name: str) -> tuple[Optional[str], str]:
        """Split `<sheet>!<range>` into (sheet_name, cell_range)."""
        raw_value = range_name.strip()
        if "!" not in raw_value:
            return None, raw_value

        sheet_name, cell_range = raw_value.split("!", 1)
        return sheet_name.strip().strip("'"), cell_range.strip()

    @classmethod
    def _resolve_grid_range(
        cls,
        spreadsheet_data: Dict[str, Any],
        range_name: str,
    ) -> tuple[Dict[str, int], str]:
        """Resolve A1 range into a GridRange payload with a concrete sheetId."""
        sheet_name, cell_range = cls._split_sheet_and_range(range_name)

        sheets = spreadsheet_data.get("sheets", [])
        if not sheets:
            raise ValueError("Spreadsheet has no sheets")

        selected_sheet = None
        if sheet_name:
            for sheet in sheets:
                properties = sheet.get("properties", {})
                if properties.get("title") == sheet_name:
                    selected_sheet = properties
                    break
            if selected_sheet is None:
                raise ValueError(f"Sheet '{sheet_name}' not found")
        else:
            selected_sheet = sheets[0].get("properties", {})

        sheet_id = selected_sheet.get("sheetId")
        if sheet_id is None:
            raise ValueError("Unable to resolve sheet ID")

        grid_range: Dict[str, int] = {"sheetId": sheet_id}
        grid_range.update(cls._parse_a1_range_bounds(cell_range))

        return grid_range, selected_sheet.get("title", "Sheet1")

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
                "share_sheet",
            ],
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
                    "properties": {"title": title},
                    "sheets": [
                        {
                            "properties": {
                                "title": f"Sheet{i+1}",
                                "gridProperties": {"rowCount": 1000, "columnCount": 26},
                            }
                        }
                        for i in range(sheet_count)
                    ],
                }

                result = (
                    self.sheets_service.spreadsheets()
                    .create(body=spreadsheet_body)
                    .execute()
                )

                spreadsheet_id = result.get("spreadsheetId")
                spreadsheet_url = result.get("spreadsheetUrl")

                logger.info(f"Created spreadsheet '{title}' - ID: {spreadsheet_id}")
                return f"Successfully created spreadsheet '{title}'\nURL: {spreadsheet_url}\nID: {spreadsheet_id}"

            except Exception as e:
                logger.error(f"Failed to create spreadsheet: {e}")
                return f"Error creating spreadsheet: {str(e)}"

        def write_data(
            spreadsheet_id: str, range_name: str, values: List[List[Any]]
        ) -> str:
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

                body = {"values": values}

                result = (
                    self.sheets_service.spreadsheets()
                    .values()
                    .update(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption="USER_ENTERED",
                        body=body,
                    )
                    .execute()
                )

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
                result = (
                    self.sheets_service.spreadsheets()
                    .values()
                    .append(
                        spreadsheetId=spreadsheet_id,
                        range=range_name,
                        valueInputOption=value_input_option,
                        insertDataOption=insert_data_option,
                        body=body,
                    )
                    .execute()
                )

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

                result = (
                    self.sheets_service.spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=range_name)
                    .execute()
                )

                values = result.get("values", [])

                if not values:
                    return f"No data found in range {range_name}"

                # Format as text table
                row_count = len(values)
                col_count = max(len(row) for row in values) if values else 0

                formatted_data = f"Data from {range_name} ({row_count} rows, {col_count} columns):\n\n"
                for row in values:
                    formatted_data += (
                        "| " + " | ".join(str(cell) for cell in row) + " |\n"
                    )

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
                format_type: Type of formatting (bold, italic, currency, percent)

            Returns:
                Success message
            """
            if not self.sheets_service:
                return "Error: Google Sheets API not initialized. Missing credentials."

            try:
                normalized_format = format_type.strip().lower()
                logger.info("Applying %s format to %s", normalized_format, range_name)

                spreadsheet_data = (
                    self.sheets_service.spreadsheets()
                    .get(spreadsheetId=spreadsheet_id)
                    .execute()
                )
                grid_range, _ = self._resolve_grid_range(spreadsheet_data, range_name)

                request_by_format = {
                    "bold": {
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "bold": True,
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.bold",
                    },
                    "italic": {
                        "cell": {
                            "userEnteredFormat": {
                                "textFormat": {
                                    "italic": True,
                                }
                            }
                        },
                        "fields": "userEnteredFormat.textFormat.italic",
                    },
                    "currency": {
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "CURRENCY",
                                    "pattern": "$#,##0.00",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    },
                    "percent": {
                        "cell": {
                            "userEnteredFormat": {
                                "numberFormat": {
                                    "type": "PERCENT",
                                    "pattern": "0.00%",
                                }
                            }
                        },
                        "fields": "userEnteredFormat.numberFormat",
                    },
                }

                if normalized_format not in request_by_format:
                    supported = ", ".join(request_by_format)
                    return (
                        f"Unsupported format type: {format_type}. "
                        f"Supported: {supported}"
                    )

                format_request = request_by_format[normalized_format]
                requests = [
                    {
                        "repeatCell": {
                            "range": grid_range,
                            "cell": format_request["cell"],
                            "fields": format_request["fields"],
                        }
                    }
                ]

                self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": requests},
                ).execute()

                logger.info(
                    "Applied %s formatting to %s", normalized_format, range_name
                )
                return (
                    f"Successfully applied {normalized_format} formatting "
                    f"to {range_name}"
                )

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
                logger.info("Creating %s chart from %s", chart_type, data_range)

                spreadsheet_data = (
                    self.sheets_service.spreadsheets()
                    .get(spreadsheetId=spreadsheet_id)
                    .execute()
                )
                grid_range, _ = self._resolve_grid_range(spreadsheet_data, data_range)

                start_row = grid_range.get("startRowIndex", 0)
                end_row = grid_range.get("endRowIndex", start_row + 10)
                start_col = grid_range.get("startColumnIndex", 0)
                end_col = grid_range.get("endColumnIndex", start_col + 2)

                if end_row <= start_row:
                    return (
                        "Error creating chart: data_range must include at least one row"
                    )

                if end_col - start_col < 2:
                    return (
                        "Error creating chart: data_range must include at least "
                        "two columns (domain + series)"
                    )

                # Map chart type to API format
                chart_type_map = {
                    "line": "LINE",
                    "bar": "BAR",
                    "column": "COLUMN",
                    "pie": "PIE",
                    "area": "AREA",
                    "scatter": "SCATTER",
                }
                api_chart_type = chart_type_map.get(
                    chart_type.lower(), chart_type.upper()
                )

                domain_source = {
                    "sheetId": grid_range["sheetId"],
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": start_col + 1,
                }
                series = [
                    {
                        "series": {
                            "sourceRange": {
                                "sources": [
                                    {
                                        "sheetId": grid_range["sheetId"],
                                        "startRowIndex": start_row,
                                        "endRowIndex": end_row,
                                        "startColumnIndex": column_index,
                                        "endColumnIndex": column_index + 1,
                                    }
                                ]
                            }
                        },
                        "targetAxis": "LEFT_AXIS",
                    }
                    for column_index in range(start_col + 1, end_col)
                ]

                requests = [
                    {
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
                                                "title": "X Axis",
                                            },
                                            {
                                                "position": "LEFT_AXIS",
                                                "title": "Y Axis",
                                            },
                                        ],
                                        "domains": [
                                            {
                                                "domain": {
                                                    "sourceRange": {
                                                        "sources": [domain_source]
                                                    }
                                                }
                                            }
                                        ],
                                        "series": series,
                                    },
                                },
                                "position": {
                                    "overlayPosition": {
                                        "anchorCell": {
                                            "sheetId": grid_range["sheetId"],
                                            "rowIndex": start_row,
                                            "columnIndex": end_col + 1,
                                        }
                                    }
                                },
                            }
                        }
                    }
                ]

                response = (
                    self.sheets_service.spreadsheets()
                    .batchUpdate(
                        spreadsheetId=spreadsheet_id,
                        body={"requests": requests},
                    )
                    .execute()
                )

                chart_id = (
                    response.get("replies", [{}])[0]
                    .get("addChart", {})
                    .get("chart", {})
                    .get("chartId")
                )

                logger.info("Created %s chart - ID: %s", api_chart_type, chart_id)
                return (
                    f"Successfully created {api_chart_type} chart from {data_range}\n"
                    f"Chart ID: {chart_id}"
                )

            except Exception as e:
                logger.error(f"Failed to create chart: {e}")
                return f"Error creating chart: {str(e)}"

        return [
            Tool(
                name="create_spreadsheet",
                description="Create a new Google Spreadsheet with the given title",
                func=create_spreadsheet,
            ),
            Tool(
                name="write_data",
                description="Write data to a specific range in a spreadsheet",
                func=lambda args: write_data(
                    **json.loads(args) if isinstance(args, str) else args
                ),
            ),
            Tool(
                name="append_data",
                description="Append rows to the next available rows in a spreadsheet range",
                func=lambda args: append_data(
                    **json.loads(args) if isinstance(args, str) else args
                ),
            ),
            Tool(
                name="read_data",
                description="Read data from a specific range in a spreadsheet",
                func=lambda args: read_data(
                    **json.loads(args) if isinstance(args, str) else args
                ),
            ),
            Tool(
                name="format_cells",
                description="Apply formatting to cells in a spreadsheet",
                func=lambda args: format_cells(
                    **json.loads(args) if isinstance(args, str) else args
                ),
            ),
            Tool(
                name="create_chart",
                description="Create a chart from data in a spreadsheet",
                func=lambda args: create_chart(
                    **json.loads(args) if isinstance(args, str) else args
                ),
            ),
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

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_message),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        return prompt


__all__ = ["SheetsAgent"]
