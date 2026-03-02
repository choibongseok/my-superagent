"""
Pre-built Workflow Templates
5 ready-to-use workflow templates for common use cases
"""
from typing import Dict, Any, List


def get_prebuilt_templates() -> List[Dict[str, Any]]:
    """Get all pre-built workflow templates"""
    
    return [
        weekly_report_generator(),
        competitor_analysis(),
        meeting_prep(),
        content_audit(),
        budget_tracker(),
    ]


def weekly_report_generator() -> Dict[str, Any]:
    """Weekly Report Generator - Research → Sheets → Docs"""
    
    return {
        "name": "Weekly Report Generator",
        "description": "Automatically generate a weekly report with research, data summary, and formatted document",
        "version": "v1",
        "category": "reporting",
        "tags": ["research", "reporting", "automation"],
        "is_public": True,
        "variables": [
            {
                "name": "company_name",
                "type": "string",
                "description": "Name of the company or project",
                "required": True,
            },
            {
                "name": "date_range",
                "type": "string",
                "description": "Date range for the report (e.g., 'Feb 24 - Mar 2, 2026')",
                "required": True,
            },
            {
                "name": "topics",
                "type": "string",
                "description": "Comma-separated topics to research",
                "required": True,
            },
        ],
        "steps": [
            {
                "id": "step1_research",
                "agent_type": "research",
                "description": "Research key topics for the week",
                "inputs": {
                    "query": "{{company_name}} {{topics}} {{date_range}}",
                    "max_results": 10,
                },
                "depends_on": [],
            },
            {
                "id": "step2_spreadsheet",
                "agent_type": "sheets",
                "description": "Create spreadsheet with research summary",
                "inputs": {
                    "title": "{{company_name}} Weekly Report - {{date_range}}",
                    "data": "{{step1_research.data}}",
                },
                "depends_on": ["step1_research"],
            },
            {
                "id": "step3_document",
                "agent_type": "docs",
                "description": "Generate formatted weekly report document",
                "inputs": {
                    "title": "{{company_name}} Weekly Report - {{date_range}}",
                    "content": "{{step1_research.data}}",
                    "spreadsheet_url": "{{step2_spreadsheet.url}}",
                },
                "depends_on": ["step1_research", "step2_spreadsheet"],
            },
        ],
    }


def competitor_analysis() -> Dict[str, Any]:
    """Competitor Analysis - Research → Sheets with charts"""
    
    return {
        "name": "Competitor Analysis",
        "description": "Analyze competitors and generate comparison spreadsheet with charts",
        "version": "v1",
        "category": "analysis",
        "tags": ["research", "competition", "analysis"],
        "is_public": True,
        "variables": [
            {
                "name": "company_name",
                "type": "string",
                "description": "Your company name",
                "required": True,
            },
            {
                "name": "competitors",
                "type": "string",
                "description": "Comma-separated list of competitor names",
                "required": True,
            },
            {
                "name": "metrics",
                "type": "string",
                "description": "Metrics to compare (e.g., 'pricing, features, market share')",
                "required": False,
                "default": "pricing, features, market share",
            },
        ],
        "steps": [
            {
                "id": "step1_research_own",
                "agent_type": "research",
                "description": "Research your company",
                "inputs": {
                    "query": "{{company_name}} {{metrics}}",
                    "max_results": 10,
                },
                "depends_on": [],
            },
            {
                "id": "step2_research_competitors",
                "agent_type": "research",
                "description": "Research competitors",
                "inputs": {
                    "query": "{{competitors}} {{metrics}}",
                    "max_results": 20,
                },
                "depends_on": [],
            },
            {
                "id": "step3_comparison_sheet",
                "agent_type": "sheets",
                "description": "Create comparison spreadsheet with charts",
                "inputs": {
                    "title": "Competitor Analysis - {{company_name}}",
                    "own_data": "{{step1_research_own.data}}",
                    "competitor_data": "{{step2_research_competitors.data}}",
                    "create_charts": True,
                },
                "depends_on": ["step1_research_own", "step2_research_competitors"],
            },
        ],
    }


def meeting_prep() -> Dict[str, Any]:
    """Meeting Prep - Calendar → Research → Slides"""
    
    return {
        "name": "Meeting Prep",
        "description": "Prepare for upcoming meetings with research and presentation slides",
        "version": "v1",
        "category": "productivity",
        "tags": ["calendar", "research", "presentations"],
        "is_public": True,
        "variables": [
            {
                "name": "meeting_title",
                "type": "string",
                "description": "Title of the meeting",
                "required": True,
            },
            {
                "name": "topics",
                "type": "string",
                "description": "Key topics to cover",
                "required": True,
            },
            {
                "name": "attendees",
                "type": "string",
                "description": "Comma-separated list of attendees",
                "required": False,
                "default": "",
            },
        ],
        "steps": [
            {
                "id": "step1_research_topics",
                "agent_type": "research",
                "description": "Research meeting topics",
                "inputs": {
                    "query": "{{topics}}",
                    "max_results": 15,
                },
                "depends_on": [],
            },
            {
                "id": "step2_research_attendees",
                "agent_type": "research",
                "description": "Research attendees (if provided)",
                "inputs": {
                    "query": "{{attendees}}",
                    "max_results": 5,
                },
                "depends_on": [],
                "condition": "{{attendees}} != ''",
            },
            {
                "id": "step3_presentation",
                "agent_type": "slides",
                "description": "Create meeting presentation",
                "inputs": {
                    "title": "{{meeting_title}} - Meeting Prep",
                    "content": "{{step1_research_topics.data}}",
                    "attendee_info": "{{step2_research_attendees.data}}",
                },
                "depends_on": ["step1_research_topics"],
            },
        ],
    }


def content_audit() -> Dict[str, Any]:
    """Content Audit - Drive → Analysis → Sheets"""
    
    return {
        "name": "Content Audit",
        "description": "Audit Drive files and generate organization recommendations",
        "version": "v1",
        "category": "organization",
        "tags": ["drive", "organization", "cleanup"],
        "is_public": True,
        "variables": [
            {
                "name": "folder_id",
                "type": "string",
                "description": "Google Drive folder ID to audit",
                "required": True,
            },
            {
                "name": "date_threshold",
                "type": "string",
                "description": "Flag files older than this date (e.g., '2025-01-01')",
                "required": False,
                "default": "2025-01-01",
            },
        ],
        "steps": [
            {
                "id": "step1_scan_files",
                "agent_type": "research",
                "description": "Scan Drive folder for files",
                "inputs": {
                    "query": "Google Drive folder {{folder_id}} files",
                    "folder_id": "{{folder_id}}",
                },
                "depends_on": [],
            },
            {
                "id": "step2_analyze_files",
                "agent_type": "research",
                "description": "Analyze file patterns and identify issues",
                "inputs": {
                    "files": "{{step1_scan_files.data}}",
                    "date_threshold": "{{date_threshold}}",
                },
                "depends_on": ["step1_scan_files"],
            },
            {
                "id": "step3_recommendations",
                "agent_type": "sheets",
                "description": "Generate recommendations spreadsheet",
                "inputs": {
                    "title": "Content Audit - Folder {{folder_id}}",
                    "analysis": "{{step2_analyze_files.data}}",
                    "include_charts": True,
                },
                "depends_on": ["step2_analyze_files"],
            },
        ],
    }


def budget_tracker() -> Dict[str, Any]:
    """Budget Tracker - Sheets → Analysis → Notifications"""
    
    return {
        "name": "Budget Tracker",
        "description": "Track budget, analyze spending patterns, and send notifications",
        "version": "v1",
        "category": "finance",
        "tags": ["budget", "finance", "tracking"],
        "is_public": True,
        "variables": [
            {
                "name": "budget_sheet_id",
                "type": "string",
                "description": "Google Sheets ID with budget data",
                "required": True,
            },
            {
                "name": "threshold",
                "type": "number",
                "description": "Alert threshold (e.g., 80 for 80% budget usage)",
                "required": False,
                "default": 80,
            },
        ],
        "steps": [
            {
                "id": "step1_fetch_data",
                "agent_type": "sheets",
                "description": "Fetch current budget data",
                "inputs": {
                    "spreadsheet_id": "{{budget_sheet_id}}",
                    "action": "read",
                },
                "depends_on": [],
            },
            {
                "id": "step2_analyze_spending",
                "agent_type": "research",
                "description": "Analyze spending patterns",
                "inputs": {
                    "data": "{{step1_fetch_data.data}}",
                    "threshold": "{{threshold}}",
                },
                "depends_on": ["step1_fetch_data"],
            },
            {
                "id": "step3_update_sheet",
                "agent_type": "sheets",
                "description": "Update budget sheet with analysis",
                "inputs": {
                    "spreadsheet_id": "{{budget_sheet_id}}",
                    "action": "update",
                    "analysis": "{{step2_analyze_spending.data}}",
                },
                "depends_on": ["step2_analyze_spending"],
            },
        ],
    }
