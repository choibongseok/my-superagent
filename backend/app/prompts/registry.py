"""Prompt Registry for version management."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class PromptVersion(BaseModel):
    """Prompt version model."""
    version: str
    template: str
    variables: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    performance_score: Optional[float] = None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PromptRegistry:
    """
    Registry for managing prompt templates and versions.

    Features:
        - Version management
        - A/B testing support
        - Performance tracking (via LangFuse)
        - Rollback capability
    """

    def __init__(self, storage_path: str = "backend/app/prompts/templates"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[PromptVersion]] = {}

    def register(
        self,
        name: str,
        template: str,
        variables: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
    ) -> PromptVersion:
        """Register new prompt or version."""
        # Auto-generate version if not provided
        if version is None:
            existing = self.list_versions(name)
            version = f"v{len(existing) + 1}"

        prompt_version = PromptVersion(
            version=version,
            template=template,
            variables=variables,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

        # Save to file
        self._save_version(name, prompt_version)

        # Update cache
        if name not in self._cache:
            self._cache[name] = []
        self._cache[name].append(prompt_version)

        return prompt_version

    def get(
        self,
        name: str,
        version: Optional[str] = None,
    ) -> Optional[PromptVersion]:
        """Get prompt by name and version."""
        versions = self.list_versions(name)

        if not versions:
            return None

        if version is None:
            # Return latest version
            return versions[-1]

        # Find specific version
        for v in versions:
            if v.version == version:
                return v

        return None

    def list_versions(self, name: str) -> List[PromptVersion]:
        """List all versions of a prompt."""
        if name in self._cache:
            return self._cache[name]

        # Load from file
        file_path = self.storage_path / f"{name}.json"
        if not file_path.exists():
            return []

        with open(file_path, "r") as f:
            data = json.load(f)

        versions = [PromptVersion(**v) for v in data]
        self._cache[name] = versions

        return versions

    def _save_version(self, name: str, version: PromptVersion):
        """Save prompt version to file."""
        versions = self.list_versions(name)
        versions.append(version)

        file_path = self.storage_path / f"{name}.json"
        with open(file_path, "w") as f:
            json.dump(
                [v.dict() for v in versions],
                f,
                indent=2,
                default=str,
            )


# Global registry instance
prompt_registry = PromptRegistry()


__all__ = ["PromptRegistry", "PromptVersion", "prompt_registry"]
