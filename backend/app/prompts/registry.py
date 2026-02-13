"""Prompt Registry for version management."""

import importlib
import json
import logging
import pkgutil
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PromptVersion(BaseModel):
    """Prompt version model."""

    version: str
    template: str
    variables: List[str]
    metadata: Dict[str, Any]
    created_at: datetime
    performance_score: Optional[float] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class PromptRegistry:
    """
    Registry for managing prompt templates and versions.

    Features:
        - Version management
        - A/B testing support
        - Performance tracking (via LangFuse)
        - Rollback capability
    """

    VERSION_NUMBER_PATTERN = re.compile(r"^v(\d+)$", re.IGNORECASE)
    DEFAULT_STORAGE_PATH = Path(__file__).resolve().parent / "templates"

    def __init__(self, storage_path: str | Path | None = None):
        resolved_storage_path = (
            Path(storage_path) if storage_path is not None else self.DEFAULT_STORAGE_PATH
        )
        self.storage_path = resolved_storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[str, List[PromptVersion]] = {}
        self._builtin_templates_loaded = False

    def register(
        self,
        name: str,
        template: str,
        variables: List[str],
        metadata: Optional[Dict[str, Any]] = None,
        version: Optional[str] = None,
        allow_overwrite: bool = False,
        persist: bool = True,
    ) -> PromptVersion:
        """Register a new prompt or version.

        Args:
            name: Prompt name.
            template: Prompt template text.
            variables: Prompt variables.
            metadata: Optional metadata.
            version: Optional explicit version label (e.g. v1).
            allow_overwrite: When True and the given version already exists,
                replace it in-place instead of raising an error.
            persist: When False, keep the version in memory/cache only.
        """
        versions = self.list_versions(name)

        # Auto-generate version if not provided.
        if version is None:
            version = self._next_version(versions)

        prompt_version = PromptVersion(
            version=version,
            template=template,
            variables=variables,
            metadata=metadata or {},
            created_at=datetime.now(),
        )

        existing_index = next(
            (i for i, current in enumerate(versions) if current.version == version),
            None,
        )

        if existing_index is not None:
            if not allow_overwrite:
                raise ValueError(
                    f"Prompt '{name}' version '{version}' already exists. "
                    "Set allow_overwrite=True to replace it."
                )
            versions[existing_index] = prompt_version
        else:
            versions.append(prompt_version)

        if persist:
            self._save_versions(name, versions)
        self._cache[name] = versions

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
        for prompt_version in versions:
            if prompt_version.version == version:
                return prompt_version

        return None

    def list_versions(self, name: str) -> List[PromptVersion]:
        """List all versions of a prompt."""
        if name in self._cache:
            return list(self._cache[name])

        file_path = self.storage_path / f"{name}.json"
        if not file_path.exists():
            return []

        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)

        versions = [PromptVersion(**value) for value in data]
        self._cache[name] = versions

        return list(versions)
    
    def update_performance_score(
        self,
        name: str,
        version: str,
        score: float,
    ) -> bool:
        """Update performance score for a specific prompt version.
        
        Args:
            name: Prompt name.
            version: Version identifier.
            score: Performance score (0.0-1.0 recommended, but not enforced).
            
        Returns:
            True if updated successfully, False if version not found.
        """
        versions = self.list_versions(name)
        
        for prompt_version in versions:
            if prompt_version.version == version:
                prompt_version.performance_score = score
                self._save_versions(name, versions)
                self._cache[name] = versions
                logger.info(
                    f"Updated performance score for '{name}' version '{version}': {score}"
                )
                return True
        
        logger.warning(
            f"Prompt '{name}' version '{version}' not found for score update"
        )
        return False
    
    def get_best_performing(
        self,
        name: str,
        min_score: Optional[float] = None,
    ) -> Optional[PromptVersion]:
        """Get the highest-performing version of a prompt.
        
        Args:
            name: Prompt name.
            min_score: Optional minimum score threshold. If provided, only
                versions with scores >= min_score are considered.
        
        Returns:
            Best performing prompt version, or None if no scored versions exist.
        """
        versions = self.list_versions(name)
        
        # Filter versions that have performance scores
        scored_versions = [
            v for v in versions 
            if v.performance_score is not None
        ]
        
        if not scored_versions:
            return None
        
        # Apply minimum score filter if provided
        if min_score is not None:
            scored_versions = [
                v for v in scored_versions 
                if v.performance_score >= min_score
            ]
        
        if not scored_versions:
            return None
        
        # Return version with highest score
        best_version = max(scored_versions, key=lambda v: v.performance_score)
        
        logger.debug(
            f"Best performing version for '{name}': {best_version.version} "
            f"(score: {best_version.performance_score})"
        )
        
        return best_version

    def get_performance_analytics(
        self,
        name: str,
    ) -> Dict[str, Any]:
        """Get performance analytics for all versions of a prompt.
        
        Args:
            name: Prompt name.
            
        Returns:
            Dictionary with performance statistics including:
            - version_count: Total number of versions
            - scored_versions: Number of versions with performance scores
            - best_version: Best performing version info
            - average_score: Average performance score across all scored versions
            - median_score: Median score for better central tendency
            - score_range: (min, max) score tuple
            - score_std_dev: Standard deviation of scores
            - percentiles: 25th, 50th, 75th, 90th percentile scores
        """
        versions = self.list_versions(name)
        
        if not versions:
            return {
                "version_count": 0,
                "scored_versions": 0,
                "best_version": None,
                "worst_version": None,
                "average_score": None,
                "median_score": None,
                "score_range": None,
                "score_std_dev": None,
                "percentiles": None,
                "score_distribution": {},
                "trend": None,
            }
        
        scored_versions = [
            v for v in versions 
            if v.performance_score is not None
        ]
        
        analytics = {
            "version_count": len(versions),
            "scored_versions": len(scored_versions),
        }
        
        if scored_versions:
            scores = sorted([v.performance_score for v in scored_versions])
            best = max(scored_versions, key=lambda v: v.performance_score)
            worst = min(scored_versions, key=lambda v: v.performance_score)
            
            # Calculate median
            n = len(scores)
            median = (
                scores[n // 2] if n % 2 == 1
                else (scores[n // 2 - 1] + scores[n // 2]) / 2
            )
            
            # Calculate standard deviation
            mean = sum(scores) / len(scores)
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            std_dev = variance ** 0.5
            
            # Calculate percentiles
            def percentile(data: List[float], p: float) -> float:
                """Calculate percentile using linear interpolation."""
                k = (len(data) - 1) * p
                f = int(k)
                c = k - f
                if f + 1 < len(data):
                    return data[f] + c * (data[f + 1] - data[f])
                return data[f]
            
            percentiles = {
                "p25": round(percentile(scores, 0.25), 3),
                "p50": round(percentile(scores, 0.50), 3),
                "p75": round(percentile(scores, 0.75), 3),
                "p90": round(percentile(scores, 0.90), 3),
            }
            
            # Detect trend (improving/declining) based on recent versions
            trend = None
            if len(scored_versions) >= 3:
                recent_scores = [
                    v.performance_score 
                    for v in sorted(scored_versions, key=lambda x: x.created_at)[-3:]
                ]
                if recent_scores[-1] > recent_scores[0]:
                    trend = "improving"
                elif recent_scores[-1] < recent_scores[0]:
                    trend = "declining"
                else:
                    trend = "stable"
            
            analytics.update({
                "best_version": {
                    "version": best.version,
                    "score": best.performance_score,
                    "created_at": best.created_at.isoformat(),
                },
                "worst_version": {
                    "version": worst.version,
                    "score": worst.performance_score,
                    "created_at": worst.created_at.isoformat(),
                },
                "average_score": round(mean, 3),
                "median_score": round(median, 3),
                "score_range": (min(scores), max(scores)),
                "score_std_dev": round(std_dev, 3),
                "percentiles": percentiles,
                "score_distribution": {
                    "excellent (>= 0.9)": len([s for s in scores if s >= 0.9]),
                    "good (0.7-0.9)": len([s for s in scores if 0.7 <= s < 0.9]),
                    "fair (0.5-0.7)": len([s for s in scores if 0.5 <= s < 0.7]),
                    "poor (< 0.5)": len([s for s in scores if s < 0.5]),
                },
                "trend": trend,
            })
        else:
            analytics.update({
                "best_version": None,
                "worst_version": None,
                "average_score": None,
                "median_score": None,
                "score_range": None,
                "score_std_dev": None,
                "percentiles": None,
                "score_distribution": {},
                "trend": None,
            })
        
        return analytics
    
    def load_builtin_templates(self) -> None:
        """Load built-in prompt templates once.

        Built-ins are Python modules under ``app.prompts.templates`` that register
        their defaults through the global ``prompt_registry`` instance at import time.
        """
        if self._builtin_templates_loaded:
            return

        try:
            templates_package = importlib.import_module("app.prompts.templates")
        except Exception:
            logger.exception("Failed to import built-in prompt templates package")
            return

        for _, module_name, is_pkg in pkgutil.iter_modules(templates_package.__path__):
            if is_pkg or module_name.startswith("_"):
                continue

            full_module_name = f"{templates_package.__name__}.{module_name}"
            try:
                importlib.import_module(full_module_name)
            except Exception:
                logger.exception("Failed to import prompt template module: %s", full_module_name)

        self._builtin_templates_loaded = True

    def _next_version(self, versions: List[PromptVersion]) -> str:
        """Generate next numeric version label (vN)."""
        highest_version_number = 0

        for version in versions:
            match = self.VERSION_NUMBER_PATTERN.match(version.version.strip())
            if not match:
                continue
            highest_version_number = max(highest_version_number, int(match.group(1)))

        return f"v{highest_version_number + 1}"

    def _save_versions(self, name: str, versions: List[PromptVersion]) -> None:
        """Persist all versions for a prompt name."""
        file_path = self.storage_path / f"{name}.json"

        with open(file_path, "w", encoding="utf-8") as file:
            json.dump(
                [version.model_dump(mode="json") for version in versions],
                file,
                indent=2,
                ensure_ascii=False,
            )


# Global registry instance
prompt_registry = PromptRegistry()
prompt_registry.load_builtin_templates()


__all__ = ["PromptRegistry", "PromptVersion", "prompt_registry"]
