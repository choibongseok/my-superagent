"""Prompt Registry for version management."""

import importlib
import json
import logging
import pkgutil
import re
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path
from string import Formatter
from typing import Any, Dict, Iterable, List, Mapping, Optional

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

        self._validate_template_variables(name=name, template=template, variables=variables)

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

    def _get_prompt_or_raise(
        self,
        name: str,
        *,
        version: str | None = None,
    ) -> PromptVersion:
        """Return prompt version or raise a descriptive not-found error."""
        prompt_version = self.get(name, version=version)
        if prompt_version is None:
            version_suffix = "" if version is None else f" version '{version}'"
            raise ValueError(f"Prompt '{name}'{version_suffix} was not found")

        return prompt_version

    def _render_prompt_version(
        self,
        *,
        name: str,
        prompt_version: PromptVersion,
        provided_variables: Mapping[str, Any],
        strict: bool,
        default_variables: Mapping[str, Any] | None = None,
        error_context: str = "",
    ) -> str:
        """Render one prompt version after variable validation."""
        required_variables = prompt_version.variables
        required_variable_set = set(required_variables)

        if default_variables is None:
            normalized_defaults: dict[str, Any] = {}
        else:
            if not isinstance(default_variables, Mapping):
                raise TypeError("default_variables must be a mapping")

            normalized_defaults = dict(default_variables)
            unexpected_default_variables = sorted(
                set(normalized_defaults) - required_variable_set
            )
            if unexpected_default_variables:
                unexpected_display = ", ".join(unexpected_default_variables)
                raise ValueError(
                    f"Unexpected default prompt variables for '{name}'{error_context}: "
                    f"{unexpected_display}"
                )

        merged_variables = {**normalized_defaults, **provided_variables}

        missing_variables = [
            required
            for required in required_variables
            if required not in merged_variables
        ]
        if missing_variables:
            missing_display = ", ".join(missing_variables)
            raise ValueError(
                f"Missing prompt variables for '{name}'{error_context}: {missing_display}"
            )

        if strict:
            unexpected_variables = sorted(set(provided_variables) - required_variable_set)
            if unexpected_variables:
                unexpected_display = ", ".join(unexpected_variables)
                raise ValueError(
                    f"Unexpected prompt variables for '{name}'{error_context}: "
                    f"{unexpected_display}"
                )

        format_values = {
            variable_name: merged_variables[variable_name]
            for variable_name in required_variables
        }

        try:
            return prompt_version.template.format(**format_values)
        except KeyError as error:
            missing_variable = str(error).strip("'")
            raise ValueError(
                "Prompt template references undeclared variable "
                f"'{missing_variable}' for '{name}'"
            ) from error

    def render(
        self,
        name: str,
        variables: Mapping[str, Any] | None = None,
        *,
        version: str | None = None,
        strict: bool = True,
        default_variables: Mapping[str, Any] | None = None,
    ) -> str:
        """Render a prompt template with runtime variables.

        Args:
            name: Prompt name.
            variables: Mapping of template variable values.
            version: Optional version label; defaults to latest.
            strict: When ``True``, reject unexpected variables that are not
                declared by the prompt version.
            default_variables: Optional fallback values used when ``variables``
                omits one or more required placeholders.

        Returns:
            Rendered prompt text.

        Raises:
            ValueError: When the prompt/version is missing or required variables
                are not provided.
        """
        prompt_version = self._get_prompt_or_raise(name, version=version)
        return self._render_prompt_version(
            name=name,
            prompt_version=prompt_version,
            provided_variables=dict(variables or {}),
            strict=strict,
            default_variables=default_variables,
        )

    def render_many(
        self,
        name: str,
        variable_sets: Iterable[Mapping[str, Any]],
        *,
        version: str | None = None,
        strict: bool = True,
        default_variables: Mapping[str, Any] | None = None,
    ) -> List[str]:
        """Render one prompt against multiple variable mappings.

        Args:
            name: Prompt name.
            variable_sets: Sequence of variable mappings to render.
            version: Optional version label; defaults to latest.
            strict: When ``True``, reject unexpected variables in each mapping.
            default_variables: Optional fallback values shared by each mapping.

        Returns:
            List of rendered prompt strings preserving input order.

        Raises:
            ValueError: When the prompt/version is missing or a mapping misses
                required variables.
            TypeError: When ``variable_sets`` contains non-mapping items.
        """
        prompt_version = self._get_prompt_or_raise(name, version=version)

        rendered_prompts: List[str] = []
        for index, values in enumerate(variable_sets):
            if not isinstance(values, Mapping):
                raise TypeError(
                    "render_many expects each variable set to be a mapping"
                )

            rendered_prompts.append(
                self._render_prompt_version(
                    name=name,
                    prompt_version=prompt_version,
                    provided_variables=dict(values),
                    strict=strict,
                    default_variables=default_variables,
                    error_context=f" at index {index}",
                )
            )

        return rendered_prompts

    def render_many_safe(
        self,
        name: str,
        variable_sets: Iterable[Mapping[str, Any]],
        *,
        version: str | None = None,
        strict: bool = True,
        default_variables: Mapping[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """Render many variable sets while collecting per-item failures.

        Unlike :meth:`render_many`, this helper never raises for per-item
        rendering issues. Instead, each row includes ``ok`` and either
        ``rendered`` output or an ``error`` message.

        Raises:
            ValueError: When the prompt/version is missing.
            TypeError: When ``default_variables`` is not a mapping.
        """
        prompt_version = self._get_prompt_or_raise(name, version=version)

        results: List[Dict[str, Any]] = []
        for index, values in enumerate(variable_sets):
            if not isinstance(values, Mapping):
                results.append(
                    {
                        "index": index,
                        "ok": False,
                        "rendered": None,
                        "error": "render_many_safe expects each variable set to be a mapping",
                    }
                )
                continue

            try:
                rendered = self._render_prompt_version(
                    name=name,
                    prompt_version=prompt_version,
                    provided_variables=dict(values),
                    strict=strict,
                    default_variables=default_variables,
                    error_context=f" at index {index}",
                )
            except Exception as error:
                results.append(
                    {
                        "index": index,
                        "ok": False,
                        "rendered": None,
                        "error": str(error),
                    }
                )
            else:
                results.append(
                    {
                        "index": index,
                        "ok": True,
                        "rendered": rendered,
                        "error": None,
                    }
                )

        return results

    def rollback(
        self,
        name: str,
        target_version: str,
        *,
        new_version: str | None = None,
        metadata: dict[str, Any] | None = None,
        persist: bool = True,
    ) -> PromptVersion:
        """Rollback a prompt to a previous version by cloning it as a new latest.

        This method preserves existing history and creates a new version that
        copies the target template and variables.
        """
        target = self.get(name, version=target_version)
        if target is None:
            raise ValueError(
                f"Prompt '{name}' version '{target_version}' was not found for rollback"
            )

        rollback_metadata: dict[str, Any] = {
            **target.metadata,
            **(metadata or {}),
            "rollback_from_version": target.version,
            "rollback_performed_at": datetime.now().isoformat(),
        }

        return self.register(
            name=name,
            template=target.template,
            variables=list(target.variables),
            metadata=rollback_metadata,
            version=new_version,
            persist=persist,
        )

    def delete_version(
        self,
        name: str,
        version: str,
        *,
        persist: bool = True,
    ) -> bool:
        """Delete one version from a prompt history.

        Args:
            name: Prompt name.
            version: Version label to delete.
            persist: When False, update in-memory cache only.

        Returns:
            True when a version was deleted, False when no matching version
            existed.
        """
        versions = self.list_versions(name)

        remaining_versions = [
            prompt_version
            for prompt_version in versions
            if prompt_version.version != version
        ]

        if len(remaining_versions) == len(versions):
            return False

        if persist:
            self._persist_versions_or_remove_file(name, remaining_versions)

        if remaining_versions:
            self._cache[name] = remaining_versions
        else:
            self._cache.pop(name, None)

        return True

    def delete_prompt(
        self,
        name: str,
        *,
        persist: bool = True,
    ) -> int:
        """Delete all versions for a prompt name.

        Args:
            name: Prompt name.
            persist: When False, clear in-memory cache only.

        Returns:
            Number of versions removed.
        """
        versions = self.list_versions(name)
        removed_count = len(versions)

        if removed_count == 0:
            return 0

        if persist:
            self._persist_versions_or_remove_file(name, [])

        self._cache.pop(name, None)
        return removed_count

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

    def list_prompt_names(
        self,
        *,
        prefix: str | None = None,
        pattern: str | None = None,
        offset: int | None = None,
        limit: int | None = None,
        descending: bool = False,
        include_version_count: bool = False,
        include_latest_version: bool = False,
        min_version_count: int | None = None,
        max_version_count: int | None = None,
    ) -> List[str] | List[Dict[str, Any]]:
        """List known prompt names from both cache and persisted storage.

        Args:
            prefix: Optional prompt-name prefix filter.
            pattern: Optional glob filter applied via :func:`fnmatchcase`.
            offset: Optional number of sorted names to skip.
            limit: Optional maximum number of names to return.
            descending: Return names in descending lexicographic order.
            include_version_count: Include per-prompt version counts.
            include_latest_version: Include latest version labels.
            min_version_count: Optional inclusive lower bound for version count.
            max_version_count: Optional inclusive upper bound for version count.

        Returns:
            Sorted prompt names, or metadata rows when include_* options are used.
        """
        if prefix is not None and not isinstance(prefix, str):
            raise ValueError("prefix must be a string")

        if pattern is not None and not isinstance(pattern, str):
            raise ValueError("pattern must be a string")

        if offset is not None and offset < 0:
            raise ValueError("offset must be greater than or equal to 0")

        if limit is not None and limit <= 0:
            raise ValueError("limit must be greater than 0")

        if not isinstance(descending, bool):
            raise ValueError("descending must be a boolean")

        if not isinstance(include_version_count, bool):
            raise ValueError("include_version_count must be a boolean")

        if not isinstance(include_latest_version, bool):
            raise ValueError("include_latest_version must be a boolean")

        if min_version_count is not None:
            if isinstance(min_version_count, bool) or not isinstance(
                min_version_count, int
            ):
                raise ValueError("min_version_count must be an integer")
            if min_version_count <= 0:
                raise ValueError("min_version_count must be greater than 0")

        if max_version_count is not None:
            if isinstance(max_version_count, bool) or not isinstance(
                max_version_count, int
            ):
                raise ValueError("max_version_count must be an integer")
            if max_version_count <= 0:
                raise ValueError("max_version_count must be greater than 0")

        if (
            min_version_count is not None
            and max_version_count is not None
            and min_version_count > max_version_count
        ):
            raise ValueError("min_version_count cannot be greater than max_version_count")

        names = set(self._cache.keys())
        names.update(path.stem for path in self.storage_path.glob("*.json"))

        if prefix:
            names = {name for name in names if name.startswith(prefix)}

        if pattern:
            names = {name for name in names if fnmatchcase(name, pattern)}

        include_metadata = include_version_count or include_latest_version
        needs_version_lookups = (
            include_metadata
            or min_version_count is not None
            or max_version_count is not None
        )

        versions_by_name: Dict[str, List[PromptVersion]] = {}
        if needs_version_lookups:
            filtered_names = set()
            for name in names:
                versions = self.list_versions(name)
                version_count = len(versions)

                if min_version_count is not None and version_count < min_version_count:
                    continue

                if max_version_count is not None and version_count > max_version_count:
                    continue

                filtered_names.add(name)
                versions_by_name[name] = versions

            names = filtered_names

        sorted_names = sorted(names, reverse=descending)

        if offset:
            sorted_names = sorted_names[offset:]

        if limit is not None:
            sorted_names = sorted_names[:limit]

        if not include_metadata:
            return sorted_names

        rows: List[Dict[str, Any]] = []
        for name in sorted_names:
            versions = versions_by_name.get(name)
            if versions is None:
                versions = self.list_versions(name)

            row: Dict[str, Any] = {"name": name}

            if include_version_count:
                row["version_count"] = len(versions)

            if include_latest_version:
                row["latest_version"] = versions[-1].version if versions else None

            rows.append(row)

        return rows

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

    @staticmethod
    def _extract_template_variables(template: str) -> set[str]:
        """Extract top-level variable names referenced by a template string."""
        variables: set[str] = set()

        for _, field_name, _, _ in Formatter().parse(template):
            if field_name is None:
                continue

            normalized_field = field_name.strip()
            if not normalized_field:
                raise ValueError(
                    "Prompt templates must use named placeholders; positional "
                    "fields like '{}' are not supported"
                )

            base_variable = normalized_field.split(".", 1)[0].split("[", 1)[0]
            if base_variable.isdigit():
                raise ValueError(
                    "Prompt templates must use named placeholders; positional "
                    "indexes like '{0}' are not supported"
                )

            variables.add(base_variable)

        return variables

    def _validate_template_variables(
        self,
        *,
        name: str,
        template: str,
        variables: list[str],
    ) -> None:
        """Validate template placeholders are declared in the variables list."""
        declared_variables = set(variables)
        referenced_variables = self._extract_template_variables(template)

        undeclared_variables = sorted(referenced_variables - declared_variables)
        if undeclared_variables:
            undeclared_display = ", ".join(undeclared_variables)
            raise ValueError(
                f"Prompt '{name}' template references undeclared variables: "
                f"{undeclared_display}"
            )

    def _next_version(self, versions: List[PromptVersion]) -> str:
        """Generate next numeric version label (vN)."""
        highest_version_number = 0

        for version in versions:
            match = self.VERSION_NUMBER_PATTERN.match(version.version.strip())
            if not match:
                continue
            highest_version_number = max(highest_version_number, int(match.group(1)))

        return f"v{highest_version_number + 1}"

    def _persist_versions_or_remove_file(
        self,
        name: str,
        versions: List[PromptVersion],
    ) -> None:
        """Persist versions or remove prompt storage when no versions remain."""
        file_path = self.storage_path / f"{name}.json"

        if versions:
            self._save_versions(name, versions)
            return

        if file_path.exists():
            file_path.unlink()

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
