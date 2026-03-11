"""Workspace analysis service for Drive file management."""
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from sqlalchemy.orm import Session

from app.models.workspace_insight import WorkspaceInsight, WorkspaceCleanupLog
from app.core.google_auth import get_google_service

logger = logging.getLogger(__name__)


class WorkspaceAnalyzer:
    """Analyzes user's Drive workspace and provides insights."""
    
    def __init__(self, db: Session, user_id: int):
        self.db = db
        self.user_id = user_id
        self.drive_service = None
    
    async def analyze_workspace(self) -> WorkspaceInsight:
        """Perform comprehensive workspace analysis."""
        try:
            # Initialize Drive service
            self.drive_service = await get_google_service("drive", "v3", self.user_id, self.db)
            
            # Fetch all files
            files = await self._fetch_all_files()
            
            # Perform analyses
            total_size = sum(int(f.get("size", 0)) for f in files)
            duplicate_groups = await self._detect_duplicates(files)
            stale_files = await self._identify_stale_files(files)
            storage_breakdown = await self._analyze_storage(files)
            org_suggestions = await self._generate_organization_suggestions(files)
            
            # Create insight record
            insight = WorkspaceInsight(
                user_id=self.user_id,
                analyzed_at=datetime.utcnow(),
                total_files=len(files),
                total_size_bytes=total_size,
                duplicate_files=duplicate_groups,
                stale_files=stale_files,
                storage_breakdown=storage_breakdown,
                organization_suggestions=org_suggestions
            )
            
            self.db.add(insight)
            self.db.commit()
            self.db.refresh(insight)
            
            logger.info(f"Workspace analysis complete for user {self.user_id}: {len(files)} files, {len(duplicate_groups)} duplicate groups")
            return insight
            
        except HttpError as e:
            logger.error(f"Drive API error during workspace analysis: {e}")
            raise
        except Exception as e:
            logger.error(f"Error analyzing workspace: {e}")
            raise
    
    async def _fetch_all_files(self) -> List[Dict]:
        """Fetch all files from user's Drive."""
        files = []
        page_token = None
        
        try:
            while True:
                response = self.drive_service.files().list(
                    pageSize=100,
                    fields="nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, viewedByMeTime, parents, webViewLink)",
                    pageToken=page_token
                ).execute()
                
                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")
                
                if not page_token:
                    break
            
            return files
        except HttpError as e:
            logger.error(f"Error fetching files: {e}")
            return []
    
    async def _detect_duplicates(self, files: List[Dict]) -> List[Dict]:
        """Detect duplicate files by name and size."""
        # Group by name and size
        file_groups = defaultdict(list)
        
        for file in files:
            name = file.get("name", "")
            size = file.get("size", 0)
            key = f"{name}_{size}"
            file_groups[key].append({
                "id": file["id"],
                "name": name,
                "size": int(size) if size else 0,
                "modified": file.get("modifiedTime"),
                "link": file.get("webViewLink")
            })
        
        # Filter groups with 2+ files
        duplicate_groups = [
            {"files": group, "total_size": sum(f["size"] for f in group)}
            for group in file_groups.values()
            if len(group) >= 2
        ]
        
        return duplicate_groups
    
    async def _identify_stale_files(self, files: List[Dict], days: int = 90) -> List[Dict]:
        """Identify files not accessed in the specified number of days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        stale_files = []
        
        for file in files:
            # Check last viewed time, fall back to modified time
            last_viewed = file.get("viewedByMeTime") or file.get("modifiedTime")
            if not last_viewed:
                continue
            
            last_viewed_dt = datetime.fromisoformat(last_viewed.replace("Z", "+00:00"))
            
            if last_viewed_dt < cutoff_date:
                stale_files.append({
                    "id": file["id"],
                    "name": file.get("name"),
                    "size": int(file.get("size", 0)),
                    "last_accessed": last_viewed,
                    "days_stale": (datetime.utcnow() - last_viewed_dt).days,
                    "link": file.get("webViewLink")
                })
        
        # Sort by staleness
        stale_files.sort(key=lambda x: x["days_stale"], reverse=True)
        return stale_files[:100]  # Limit to top 100
    
    async def _analyze_storage(self, files: List[Dict]) -> Dict:
        """Analyze storage usage by file type."""
        storage_by_type = defaultdict(lambda: {"count": 0, "size": 0})
        
        for file in files:
            mime_type = file.get("mimeType", "unknown")
            size = int(file.get("size", 0))
            
            # Group similar MIME types
            if "spreadsheet" in mime_type:
                category = "spreadsheets"
            elif "document" in mime_type:
                category = "documents"
            elif "presentation" in mime_type:
                category = "presentations"
            elif "image" in mime_type:
                category = "images"
            elif "video" in mime_type:
                category = "videos"
            elif "folder" in mime_type:
                category = "folders"
            elif "pdf" in mime_type:
                category = "pdfs"
            else:
                category = "other"
            
            storage_by_type[category]["count"] += 1
            storage_by_type[category]["size"] += size
        
        # Convert to list and sort by size
        breakdown = [
            {"type": k, "count": v["count"], "size": v["size"]}
            for k, v in storage_by_type.items()
        ]
        breakdown.sort(key=lambda x: x["size"], reverse=True)
        
        return {"categories": breakdown}
    
    async def _generate_organization_suggestions(self, files: List[Dict]) -> List[Dict]:
        """Generate smart organization suggestions."""
        suggestions = []
        
        # Suggestion 1: Archive old files
        old_files = [f for f in files if self._is_old_file(f, days=180)]
        if old_files:
            suggestions.append({
                "type": "archive_old_files",
                "priority": "high",
                "description": f"Archive {len(old_files)} files older than 6 months",
                "action": "move_to_archive",
                "file_count": len(old_files),
                "space_saved_bytes": sum(int(f.get("size", 0)) for f in old_files)
            })
        
        # Suggestion 2: Group by year
        files_without_year_folder = [
            f for f in files
            if not self._is_in_year_folder(f) and f.get("mimeType") != "application/vnd.google-apps.folder"
        ]
        if len(files_without_year_folder) > 10:
            suggestions.append({
                "type": "organize_by_year",
                "priority": "medium",
                "description": f"Organize {len(files_without_year_folder)} files into year-based folders",
                "action": "create_year_folders",
                "file_count": len(files_without_year_folder)
            })
        
        # Suggestion 3: Remove duplicates
        duplicate_groups = await self._detect_duplicates(files)
        if duplicate_groups:
            total_duplicates = sum(len(g["files"]) - 1 for g in duplicate_groups)
            total_space = sum(g["total_size"] - g["files"][0]["size"] for g in duplicate_groups)
            suggestions.append({
                "type": "remove_duplicates",
                "priority": "medium",
                "description": f"Remove {total_duplicates} duplicate files",
                "action": "delete_duplicates",
                "file_count": total_duplicates,
                "space_saved_bytes": total_space
            })
        
        return suggestions
    
    def _is_old_file(self, file: Dict, days: int) -> bool:
        """Check if file is older than specified days."""
        modified = file.get("modifiedTime")
        if not modified:
            return False
        
        modified_dt = datetime.fromisoformat(modified.replace("Z", "+00:00"))
        cutoff = datetime.utcnow() - timedelta(days=days)
        return modified_dt < cutoff
    
    def _is_in_year_folder(self, file: Dict) -> bool:
        """Check if file is in a year-based folder (e.g., Archive/2024)."""
        # This is a simplified check; in production, you'd inspect parent folder names
        return False  # Placeholder
    
    async def organize_files(self, insight_id: int, suggestion_type: str) -> WorkspaceCleanupLog:
        """Execute organization based on a suggestion."""
        try:
            insight = self.db.query(WorkspaceInsight).filter(
                WorkspaceInsight.id == insight_id,
                WorkspaceInsight.user_id == self.user_id
            ).first()
            
            if not insight:
                raise ValueError("Insight not found")
            
            # Initialize Drive service
            self.drive_service = await get_google_service("drive", "v3", self.user_id, self.db)
            
            # Execute based on suggestion type
            if suggestion_type == "archive_old_files":
                result = await self._archive_old_files(insight)
            elif suggestion_type == "organize_by_year":
                result = await self._organize_by_year(insight)
            elif suggestion_type == "remove_duplicates":
                result = await self._remove_duplicates(insight)
            else:
                raise ValueError(f"Unknown suggestion type: {suggestion_type}")
            
            # Create cleanup log
            cleanup_log = WorkspaceCleanupLog(
                user_id=self.user_id,
                insight_id=insight_id,
                operation_type=suggestion_type,
                performed_at=datetime.utcnow(),
                files_affected=result["files_affected"],
                bytes_freed=result.get("bytes_freed", 0),
                details=result.get("details")
            )
            
            self.db.add(cleanup_log)
            self.db.commit()
            self.db.refresh(cleanup_log)
            
            logger.info(f"Workspace organization complete: {suggestion_type}, {result['files_affected']} files affected")
            return cleanup_log
            
        except Exception as e:
            logger.error(f"Error organizing files: {e}")
            # Log error
            cleanup_log = WorkspaceCleanupLog(
                user_id=self.user_id,
                insight_id=insight_id,
                operation_type=suggestion_type,
                performed_at=datetime.utcnow(),
                files_affected=0,
                error_message=str(e)
            )
            self.db.add(cleanup_log)
            self.db.commit()
            raise
    
    async def _archive_old_files(self, insight: WorkspaceInsight) -> Dict:
        """Move old files to Archive folder."""
        # Get or create Archive folder
        archive_folder = await self._get_or_create_folder("Archive")
        
        stale_files = insight.stale_files or []
        files_moved = 0
        bytes_freed = 0
        
        for file_info in stale_files[:50]:  # Limit to 50 files per operation
            try:
                # Move file to archive
                file_id = file_info["id"]
                self.drive_service.files().update(
                    fileId=file_id,
                    addParents=archive_folder["id"],
                    removeParents=",".join(file_info.get("parents", [])),
                    fields="id, parents"
                ).execute()
                
                files_moved += 1
                bytes_freed += file_info.get("size", 0)
            except HttpError as e:
                logger.warning(f"Failed to move file {file_id}: {e}")
        
        return {
            "files_affected": files_moved,
            "bytes_freed": bytes_freed,
            "details": {"archive_folder_id": archive_folder["id"]}
        }
    
    async def _organize_by_year(self, insight: WorkspaceInsight) -> Dict:
        """Organize files into year-based folders."""
        files = await self._fetch_all_files()
        files_moved = 0
        year_folders = {}
        
        for file in files[:50]:  # Limit to 50 files
            # Skip folders
            if file.get("mimeType") == "application/vnd.google-apps.folder":
                continue
            
            # Get file year from created date
            created = file.get("createdTime")
            if not created:
                continue
            
            year = datetime.fromisoformat(created.replace("Z", "+00:00")).year
            
            # Get or create year folder
            if year not in year_folders:
                year_folders[year] = await self._get_or_create_folder(f"Archive/{year}")
            
            try:
                # Move file
                self.drive_service.files().update(
                    fileId=file["id"],
                    addParents=year_folders[year]["id"],
                    removeParents=",".join(file.get("parents", [])),
                    fields="id, parents"
                ).execute()
                files_moved += 1
            except HttpError as e:
                logger.warning(f"Failed to move file {file['id']}: {e}")
        
        return {
            "files_affected": files_moved,
            "details": {"year_folders": list(year_folders.keys())}
        }
    
    async def _remove_duplicates(self, insight: WorkspaceInsight) -> Dict:
        """Remove duplicate files (keep newest)."""
        duplicate_groups = insight.duplicate_files or []
        files_deleted = 0
        bytes_freed = 0
        
        for group in duplicate_groups[:20]:  # Limit to 20 groups
            files = group["files"]
            
            # Sort by modified time, keep newest
            files.sort(key=lambda x: x.get("modified", ""), reverse=True)
            
            # Delete all except the first (newest)
            for file_to_delete in files[1:]:
                try:
                    self.drive_service.files().delete(fileId=file_to_delete["id"]).execute()
                    files_deleted += 1
                    bytes_freed += file_to_delete.get("size", 0)
                except HttpError as e:
                    logger.warning(f"Failed to delete file {file_to_delete['id']}: {e}")
        
        return {
            "files_affected": files_deleted,
            "bytes_freed": bytes_freed,
            "details": {"groups_processed": len(duplicate_groups[:20])}
        }
    
    async def _get_or_create_folder(self, folder_path: str) -> Dict:
        """Get or create a folder by path (e.g., 'Archive/2024')."""
        parts = folder_path.split("/")
        parent_id = "root"
        
        for part in parts:
            # Search for existing folder
            results = self.drive_service.files().list(
                q=f"name='{part}' and mimeType='application/vnd.google-apps.folder' and '{parent_id}' in parents",
                fields="files(id, name)"
            ).execute()
            
            folders = results.get("files", [])
            
            if folders:
                folder = folders[0]
            else:
                # Create folder
                folder_metadata = {
                    "name": part,
                    "mimeType": "application/vnd.google-apps.folder",
                    "parents": [parent_id]
                }
                folder = self.drive_service.files().create(
                    body=folder_metadata,
                    fields="id, name"
                ).execute()
            
            parent_id = folder["id"]
        
        return {"id": parent_id, "name": parts[-1]}
