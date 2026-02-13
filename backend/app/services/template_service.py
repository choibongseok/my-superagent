"""Service for template marketplace management."""

import csv
import json
import logging
import re
from string import Formatter
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.template import Template, TemplateRating
from app.schemas.template import (
    TemplateCreate,
    TemplateSearchRequest,
    TemplateUpdate,
    TemplateRatingCreate,
    TemplateRatingUpdate,
)

logger = logging.getLogger(__name__)


class _TemplateContextDict(dict):
    """Dictionary wrapper supporting attribute-style access in format strings."""

    def __getattr__(self, key: str):
        try:
            return self[key]
        except KeyError as exc:  # pragma: no cover - exercised via Formatter errors
            raise AttributeError(key) from exc


def _to_template_context(value):
    """Recursively wrap mappings for dot-notation template rendering."""
    if isinstance(value, dict):
        return _TemplateContextDict(
            {key: _to_template_context(item) for key, item in value.items()}
        )

    if isinstance(value, list):
        return [_to_template_context(item) for item in value]

    return value


def _tokenize_case_transform(value: object) -> list[str]:
    """Split values into normalized lowercase word tokens for case transforms."""
    text = str(value)
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    text = re.sub(r"[^0-9A-Za-z]+", " ", text)
    return [token.lower() for token in text.strip().split() if token]


def _to_pascal_case(value: object) -> str:
    """Convert values to PascalCase using normalized word tokens."""
    return "".join(token.capitalize() for token in _tokenize_case_transform(value))


def _to_camel_case(value: object) -> str:
    """Convert values to camelCase using normalized word tokens."""
    pascal_case = _to_pascal_case(value)
    if not pascal_case:
        return ""

    return pascal_case[0].lower() + pascal_case[1:]


def _to_json(value: object, *, pretty: bool = False) -> str:
    """Serialize values to JSON for prompt rendering transforms."""
    if pretty:
        return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _truncate_text(value: object, max_length_spec: str) -> str:
    """Truncate text to a max length using an ellipsis when needed."""
    try:
        max_length = int(max_length_spec.strip())
    except ValueError as exc:
        raise ValueError("truncate expects an integer max length") from exc

    if max_length < 0:
        raise ValueError("truncate max length must be non-negative")

    text = str(value)
    if len(text) <= max_length:
        return text

    if max_length == 0:
        return ""

    if max_length == 1:
        return "…"

    return text[: max_length - 1].rstrip() + "…"


def _parse_transform_args(argument_spec: str) -> list[str]:
    """Parse comma-separated transform arguments, supporting CSV quoting."""
    try:
        parsed = next(csv.reader([argument_spec], skipinitialspace=True))
    except csv.Error as exc:  # pragma: no cover - handled by validation tests
        raise ValueError("Invalid transform arguments") from exc

    return parsed


def _replace_text(value: object, argument_spec: str) -> str:
    """Replace text using ``replace(search,replacement)`` transform arguments."""
    args = _parse_transform_args(argument_spec)
    if len(args) != 2:
        raise ValueError("replace expects exactly two arguments: search,replacement")

    search, replacement = args
    if search == "":
        raise ValueError("replace search argument must not be empty")

    return str(value).replace(search, replacement)


def _join_values(value: object, argument_spec: str) -> str:
    """Join iterable values into a single string.

    ``join()`` defaults to `", "` as separator.
    ``join(" | ")`` uses a custom separator.
    """
    args: list[str] = []
    if argument_spec.strip():
        args = _parse_transform_args(argument_spec)

    if len(args) > 1:
        raise ValueError("join expects zero or one argument: separator")

    separator = args[0] if args else ", "

    if isinstance(value, (str, bytes, bytearray)):
        raise ValueError("join expects an iterable value, not a string")

    try:
        iterator = iter(value)
    except TypeError as exc:
        raise ValueError("join expects an iterable value") from exc

    return separator.join(str(item) for item in iterator)


class TemplateService:
    """Service for template management."""

    def __init__(self, db: AsyncSession):
        """
        Initialize template service.

        Args:
            db: Database session
        """
        self.db = db

    async def create_template(
        self, template_data: TemplateCreate, author_id: UUID
    ) -> Template:
        """
        Create a new template.

        Args:
            template_data: Template creation data
            author_id: Author user ID

        Returns:
            Created template
        """
        template = Template(
            name=template_data.name,
            description=template_data.description,
            category=template_data.category,
            tags={"tags": template_data.tags} if template_data.tags else None,
            author_id=author_id,
            team_id=template_data.team_id,
            prompt_template=template_data.prompt_template,
            parameters=template_data.parameters,
            example_inputs=template_data.example_inputs,
            example_outputs=template_data.example_outputs,
            is_public=template_data.is_public,
        )

        self.db.add(template)
        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template created: {template.id} by user {author_id}")

        return template

    async def get_template(self, template_id: UUID) -> Optional[Template]:
        """
        Get template by ID.

        Args:
            template_id: Template ID

        Returns:
            Template or None if not found
        """
        result = await self.db.execute(
            select(Template).where(Template.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update_template(
        self,
        template_id: UUID,
        template_data: TemplateUpdate,
        user_id: UUID,
    ) -> Optional[Template]:
        """
        Update template.

        Args:
            template_id: Template ID
            template_data: Update data
            user_id: Requesting user ID

        Returns:
            Updated template or None if not found/unauthorized
        """
        template = await self.get_template(template_id)

        if not template or template.author_id != user_id:
            return None

        # Update fields
        update_data = template_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if field == "tags" and value is not None:
                setattr(template, field, {"tags": value})
            else:
                setattr(template, field, value)

        await self.db.commit()
        await self.db.refresh(template)

        logger.info(f"Template updated: {template_id}")

        return template

    async def delete_template(self, template_id: UUID, user_id: UUID) -> bool:
        """
        Delete template.

        Args:
            template_id: Template ID
            user_id: Requesting user ID

        Returns:
            True if deleted, False if not found/unauthorized
        """
        template = await self.get_template(template_id)

        if not template or template.author_id != user_id:
            return False

        await self.db.delete(template)
        await self.db.commit()

        logger.info(f"Template deleted: {template_id}")

        return True

    async def search_templates(
        self, search_request: TemplateSearchRequest, user_id: Optional[UUID] = None
    ) -> tuple[List[Template], int]:
        """
        Search templates with filters.

        Args:
            search_request: Search parameters
            user_id: Optional user ID for personalized results

        Returns:
            Tuple of (templates, total_count)
        """
        # Base query: public templates or user's own templates
        query = select(Template).where(
            or_(Template.is_public == True, Template.author_id == user_id)
            if user_id
            else Template.is_public == True
        )

        # Apply filters
        if search_request.query:
            query = query.where(
                or_(
                    Template.name.ilike(f"%{search_request.query}%"),
                    Template.description.ilike(f"%{search_request.query}%"),
                )
            )

        if search_request.category:
            query = query.where(Template.category == search_request.category)

        if search_request.tags:
            # Filter by tags (JSON array contains)
            for tag in search_request.tags:
                query = query.where(func.jsonb_exists(Template.tags, f"tags.{tag}"))

        if search_request.author_id:
            query = query.where(Template.author_id == search_request.author_id)

        if search_request.is_official is not None:
            query = query.where(Template.is_official == search_request.is_official)

        if search_request.is_featured is not None:
            query = query.where(Template.is_featured == search_request.is_featured)

        if search_request.min_rating is not None:
            query = query.where(Template.rating >= search_request.min_rating)

        # Count total
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply sorting
        sort_column = getattr(Template, search_request.sort_by, Template.usage_count)
        if search_request.sort_order == "desc":
            query = query.order_by(sort_column.desc())
        else:
            query = query.order_by(sort_column.asc())

        # Apply pagination
        query = query.limit(search_request.limit).offset(search_request.offset)

        # Execute query
        result = await self.db.execute(query)
        templates = list(result.scalars().all())

        logger.info(f"Template search: {len(templates)} results (total: {total})")

        return templates, total

    @staticmethod
    def _parse_field_expression(field_name: str) -> tuple[str, str | None, list[str]]:
        """Parse template field expressions.

        Supported syntax:
        - ``{field}``
        - ``{field|default value}``
        - ``{field->upper}``
        - ``{field|default value->strip->title}``
        - ``{summary->truncate(120)}``
        - ``{name->replace("Agent", "Assistant")}``

        Returns:
            Tuple of ``(field_path, default_value, transforms)``.
        """
        base_expression, *transform_parts = field_name.split("->")

        transforms = [part.strip() for part in transform_parts if part.strip()]

        if "|" not in base_expression:
            return base_expression.strip(), None, transforms

        field_path, default_value = base_expression.split("|", 1)
        return field_path.strip(), default_value.strip(), transforms

    @staticmethod
    def _apply_template_transforms(value: object, transforms: list[str]) -> object:
        """Apply text transforms declared in a template field expression."""
        if not transforms:
            return value

        available_transforms = {
            "strip": lambda raw: str(raw).strip(),
            "upper": lambda raw: str(raw).upper(),
            "lower": lambda raw: str(raw).lower(),
            "title": lambda raw: str(raw).title(),
            "capitalize": lambda raw: str(raw).capitalize(),
            "snake_case": lambda raw: "_".join(_tokenize_case_transform(raw)),
            "kebab_case": lambda raw: "-".join(_tokenize_case_transform(raw)),
            "dot_case": lambda raw: ".".join(_tokenize_case_transform(raw)),
            "constant_case": lambda raw: "_".join(
                _tokenize_case_transform(raw)
            ).upper(),
            "camel_case": _to_camel_case,
            "pascal_case": _to_pascal_case,
            "json": lambda raw: _to_json(raw, pretty=False),
            "json_pretty": lambda raw: _to_json(raw, pretty=True),
        }
        supported_transforms = sorted(
            [
                *available_transforms.keys(),
                "truncate(<max_length>)",
                "replace(<search>,<replacement>)",
                "join([separator])",
            ]
        )

        transformed = value
        for transform in transforms:
            normalized_transform = transform.lower()
            operation = available_transforms.get(normalized_transform)

            function_match = re.fullmatch(
                r"([a-z_]+)\((.*)\)", transform, flags=re.IGNORECASE
            )
            if operation is None and function_match is not None:
                transform_name = function_match.group(1).lower()
                argument_spec = function_match.group(2)

                if transform_name == "truncate":
                    operation = lambda raw, spec=argument_spec: _truncate_text(
                        raw, spec
                    )
                elif transform_name == "replace":
                    operation = lambda raw, spec=argument_spec: _replace_text(raw, spec)
                elif transform_name == "join":
                    operation = lambda raw, spec=argument_spec: _join_values(raw, spec)

            if operation is None:
                supported = ", ".join(supported_transforms)
                raise ValueError(
                    f"Unsupported template transform: {transform}. "
                    f"Supported transforms: {supported}"
                )

            try:
                transformed = operation(transformed)
            except Exception as exc:
                raise ValueError(
                    f"Failed to apply template transform '{transform}': {exc}"
                ) from exc

        return transformed

    @classmethod
    def _extract_template_variables(cls, prompt_template: str) -> set[str]:
        """Extract required top-level variables from a format-style template.

        Fields declared with ``|`` default syntax (e.g. ``{audience|general}``)
        are treated as optional and excluded from the required input set.
        Optional ``->transform`` directives do not affect required field
        detection.
        """
        variables: set[str] = set()
        for _, field_name, _, _ in Formatter().parse(prompt_template):
            if not field_name:
                continue

            resolved_field, default_value, _ = cls._parse_field_expression(field_name)
            if default_value is not None:
                continue

            # Handle nested field access like {user.name} or {user[name]}
            base_field = resolved_field.split(".", 1)[0].split("[", 1)[0]
            if base_field:
                variables.add(base_field)

        return variables

    @staticmethod
    def _should_apply_default(value: object) -> bool:
        """Return whether a resolved value should fall back to a template default."""
        if value is None:
            return True

        if isinstance(value, str) and value.strip() == "":
            return True

        return False

    @classmethod
    def _render_prompt_template(cls, prompt_template: str, inputs: dict) -> str:
        """Render prompt template and validate required inputs.

        Supports nested input interpolation via dot notation (``{user.name}``) and
        bracket access (``{items[0][title]}``) when ``inputs`` contains nested
        dictionaries/lists.

        Also supports optional defaults via ``field|default`` syntax (for example
        ``{audience|general audience}``) and text transforms via ``->`` (for
        example ``{audience->upper}``, ``{name|friend->title}``,
        ``{project_name->snake_case}``, ``{release_title->kebab_case}``,
        ``{service->dot_case}``, ``{build_target->constant_case}``,
        ``{variable->camel_case}``, ``{variable->pascal_case}``,
        ``{summary->truncate(120)}``, ``{title->replace("Agent", "Assistant")}``,
        ``{tags->join(" | ")}``, ``{payload->json}``, or
        ``{payload->json_pretty}``).
        """
        required_inputs = cls._extract_template_variables(prompt_template)
        missing_inputs = sorted(key for key in required_inputs if key not in inputs)
        if missing_inputs:
            missing = ", ".join(missing_inputs)
            raise ValueError(f"Missing template inputs: {missing}")

        formatter = Formatter()
        context = _to_template_context(inputs)
        rewritten_parts: list[str] = []
        resolved_values: dict[str, object] = {}

        for index, (literal, field_name, format_spec, conversion) in enumerate(
            formatter.parse(prompt_template)
        ):
            rewritten_parts.append(literal.replace("{", "{{").replace("}", "}}"))
            if field_name is None:
                continue

            resolved_field, default_value, transforms = cls._parse_field_expression(
                field_name
            )
            placeholder = f"__field_{index}__"

            rebuilt_field = "{" + placeholder
            if conversion:
                rebuilt_field += f"!{conversion}"
            if format_spec:
                rebuilt_field += f":{format_spec}"
            rebuilt_field += "}"
            rewritten_parts.append(rebuilt_field)

            try:
                value, _ = formatter.get_field(resolved_field, (), context)
            except (KeyError, ValueError, AttributeError, IndexError, TypeError) as exc:
                if default_value is None:
                    raise ValueError(f"Failed to render template: {exc}") from exc
                value = default_value
            else:
                if default_value is not None and cls._should_apply_default(value):
                    value = default_value

            value = cls._apply_template_transforms(value, transforms)
            resolved_values[placeholder] = value

        try:
            rewritten_template = "".join(rewritten_parts)
            return rewritten_template.format_map(_to_template_context(resolved_values))
        except (KeyError, ValueError, AttributeError, IndexError, TypeError) as exc:
            raise ValueError(f"Failed to render template: {exc}") from exc

    async def use_template(
        self,
        template_id: UUID,
        inputs: dict,
        user_id: UUID,
        output_type: str | None = None,
    ) -> dict:
        """
        Use a template with inputs to generate prompt.

        Args:
            template_id: Template ID
            inputs: Input values for template variables
            user_id: User ID
            output_type: Optional output type override

        Returns:
            Dict with template_id, prompt, and suggested output_type
        """
        template = await self.get_template(template_id)

        if not template:
            raise ValueError(f"Template not found: {template_id}")

        prompt = self._render_prompt_template(template.prompt_template, inputs)

        # Increment usage count only after successful prompt rendering
        template.usage_count += 1
        await self.db.commit()

        selected_output_type = (output_type or template.category).strip()

        logger.info(f"Template {template_id} used by user {user_id}")

        return {
            "template_id": str(template_id),
            "prompt": prompt,
            "output_type": selected_output_type,
        }

    # Rating methods

    async def create_rating(
        self,
        template_id: UUID,
        user_id: UUID,
        rating_data: TemplateRatingCreate,
    ) -> TemplateRating:
        """
        Create or update template rating.

        Args:
            template_id: Template ID
            user_id: User ID
            rating_data: Rating data

        Returns:
            Created/updated rating
        """
        # Check if rating exists
        result = await self.db.execute(
            select(TemplateRating).where(
                TemplateRating.template_id == template_id,
                TemplateRating.user_id == user_id,
            )
        )
        existing_rating = result.scalar_one_or_none()

        if existing_rating:
            # Update existing rating
            old_rating = existing_rating.rating
            existing_rating.rating = rating_data.rating
            existing_rating.review = rating_data.review
            rating = existing_rating
        else:
            # Create new rating
            rating = TemplateRating(
                template_id=template_id,
                user_id=user_id,
                rating=rating_data.rating,
                review=rating_data.review,
            )
            self.db.add(rating)
            old_rating = None

        await self.db.commit()
        await self.db.refresh(rating)

        # Update template rating average
        await self._update_template_rating(template_id)

        logger.info(f"Rating created/updated for template {template_id}")

        return rating

    async def _update_template_rating(self, template_id: UUID):
        """Update template's average rating and count."""
        result = await self.db.execute(
            select(
                func.avg(TemplateRating.rating),
                func.count(TemplateRating.id),
            ).where(TemplateRating.template_id == template_id)
        )
        avg_rating, count = result.one()

        template = await self.get_template(template_id)
        if template:
            template.rating = float(avg_rating or 0.0)
            template.rating_count = count or 0
            await self.db.commit()

    async def get_template_ratings(
        self, template_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[List[TemplateRating], int]:
        """
        Get ratings for template.

        Args:
            template_id: Template ID
            limit: Page limit
            offset: Page offset

        Returns:
            Tuple of (ratings, total_count)
        """
        # Count total
        count_result = await self.db.execute(
            select(func.count()).where(TemplateRating.template_id == template_id)
        )
        total = count_result.scalar() or 0

        # Get ratings
        result = await self.db.execute(
            select(TemplateRating)
            .where(TemplateRating.template_id == template_id)
            .order_by(TemplateRating.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        ratings = list(result.scalars().all())

        return ratings, total

    async def get_user_templates(
        self, user_id: UUID, limit: int = 20, offset: int = 0
    ) -> tuple[List[Template], int]:
        """
        Get templates created by user.

        Args:
            user_id: User ID
            limit: Page limit
            offset: Page offset

        Returns:
            Tuple of (templates, total_count)
        """
        # Count total
        count_result = await self.db.execute(
            select(func.count()).where(Template.author_id == user_id)
        )
        total = count_result.scalar() or 0

        # Get templates
        result = await self.db.execute(
            select(Template)
            .where(Template.author_id == user_id)
            .order_by(Template.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        templates = list(result.scalars().all())

        return templates, total


__all__ = ["TemplateService"]
