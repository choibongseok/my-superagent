"""Service for template marketplace management."""

import logging
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

    async def delete_template(
        self, template_id: UUID, user_id: UUID
    ) -> bool:
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
                query = query.where(
                    func.jsonb_exists(Template.tags, f"tags.{tag}")
                )

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

        logger.info(
            f"Template search: {len(templates)} results (total: {total})"
        )

        return templates, total

    async def use_template(
        self, template_id: UUID, inputs: dict, user_id: UUID
    ) -> dict:
        """
        Use a template with inputs to generate prompt.

        Args:
            template_id: Template ID
            inputs: Input values for template variables
            user_id: User ID

        Returns:
            Dict with template_id, prompt, and suggested output_type
        """
        template = await self.get_template(template_id)

        if not template:
            raise ValueError(f"Template not found: {template_id}")

        # Increment usage count
        template.usage_count += 1
        await self.db.commit()

        # Replace variables in prompt template
        prompt = template.prompt_template
        for key, value in inputs.items():
            prompt = prompt.replace(f"{{{key}}}", str(value))

        logger.info(f"Template {template_id} used by user {user_id}")

        return {
            "template_id": str(template_id),
            "prompt": prompt,
            "output_type": template.category,
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
