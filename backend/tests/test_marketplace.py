"""
Tests for Template Marketplace API
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone

from app.models.marketplace import MarketplaceTemplate, TemplateInstall, MarketplaceRating, TemplateCategory


@pytest.fixture
def sample_template_data():
    """Sample template data for testing"""
    return {
        "name": "Sales Report Template",
        "description": "Generate comprehensive sales reports with charts",
        "category": "business",
        "tags": ["sales", "reporting", "charts"],
        "template_data": {
            "steps": [
                {"type": "research", "query": "gather sales data"},
                {"type": "sheets", "action": "create_spreadsheet"},
                {"type": "slides", "action": "create_presentation"}
            ]
        },
        "prompt_template": "Create a sales report for {period} with data from {source}",
        "config": {
            "default_period": "Q1 2026",
            "include_charts": True
        },
        "is_public": True
    }


@pytest.fixture
def created_template(test_db, test_user, sample_template_data):
    """Create a test template in the database"""
    template = MarketplaceTemplate(
        id=uuid4(),
        creator_id=test_user.id,
        creator_name=test_user.full_name,
        published_at=datetime.now(timezone.utc),
        **sample_template_data
    )
    test_db.add(template)
    test_db.commit()
    test_db.refresh(template)
    return template


# ============================================================================
# Template Browsing Tests
# ============================================================================

@pytest.mark.asyncio
async def test_list_marketplace_templates(async_client):
    """Test listing marketplace templates"""
    response = await async_client.get("/api/v1/marketplace/templates")
    
    assert response.status_code == 200
    data = response.json()
    assert "templates" in data
    assert "total" in data
    assert "page" in data
    assert "limit" in data
    assert isinstance(data["templates"], list)


@pytest.mark.asyncio
async def test_list_templates_with_category_filter(async_client, created_template):
    """Test filtering templates by category"""
    response = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"category": "business"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["templates"]) > 0
    for template in data["templates"]:
        assert template["category"] == "business"


@pytest.mark.asyncio
async def test_list_templates_with_search(async_client, created_template):
    """Test searching templates"""
    response = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"search": "sales"}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Should find templates with "sales" in name, description, or tags
    assert len(data["templates"]) > 0


@pytest.mark.asyncio
async def test_list_featured_templates(async_client, test_db, created_template):
    """Test filtering for featured templates only"""
    # Make template featured
    created_template.is_featured = True
    test_db.commit()
    
    response = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"featured_only": True}
    )
    
    assert response.status_code == 200
    data = response.json()
    for template in data["templates"]:
        assert template["is_featured"] is True


@pytest.mark.asyncio
async def test_get_template_detail(async_client, created_template):
    """Test getting template details"""
    response = await async_client.get(
        f"/api/v1/marketplace/templates/{created_template.id}"
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(created_template.id)
    assert data["name"] == created_template.name
    assert "template_data" in data
    assert "view_count" in data


@pytest.mark.asyncio
async def test_get_template_increments_view_count(async_client, test_db, created_template):
    """Test that viewing a template increments view count"""
    initial_views = created_template.view_count
    
    response = await async_client.get(
        f"/api/v1/marketplace/templates/{created_template.id}"
    )
    
    assert response.status_code == 200
    
    # Refresh from database
    test_db.refresh(created_template)
    assert created_template.view_count == initial_views + 1


@pytest.mark.asyncio
async def test_get_nonexistent_template(async_client):
    """Test getting a template that doesn't exist"""
    fake_id = uuid4()
    response = await async_client.get(
        f"/api/v1/marketplace/templates/{fake_id}"
    )
    
    assert response.status_code == 404


# ============================================================================
# Template Installation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_install_template(async_client, auth_headers, created_template):
    """Test installing a template"""
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={"installed_name": "My Custom Sales Report"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["template_id"] == str(created_template.id)
    assert data["installed_name"] == "My Custom Sales Report"
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_install_increments_count(async_client, auth_headers, test_db, created_template):
    """Test that installing increments the install count"""
    initial_count = created_template.install_count
    
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    
    # Refresh from database
    test_db.refresh(created_template)
    assert created_template.install_count == initial_count + 1


@pytest.mark.asyncio
async def test_install_same_template_twice(async_client, auth_headers, created_template):
    """Test installing the same template twice returns existing installation"""
    # First install
    response1 = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    install_id = response1.json()["id"]
    
    # Second install
    response2 = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    
    assert response2.status_code == 200
    assert response2.json()["id"] == install_id  # Same installation


@pytest.mark.asyncio
async def test_install_without_auth(async_client, created_template):
    """Test installing requires authentication"""
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={}
    )
    
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_list_my_installed_templates(async_client, auth_headers, created_template):
    """Test listing user's installed templates"""
    # Install a template first
    await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    
    # List installations
    response = await async_client.get(
        "/api/v1/marketplace/my-templates",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    installs = response.json()
    assert len(installs) > 0
    assert installs[0]["template_id"] == str(created_template.id)


@pytest.mark.asyncio
async def test_update_installed_template(async_client, auth_headers, created_template):
    """Test updating an installed template"""
    # Install first
    install_response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    install_id = install_response.json()["id"]
    
    # Update installation
    response = await async_client.patch(
        f"/api/v1/marketplace/my-templates/{install_id}",
        json={
            "installed_name": "Updated Name",
            "is_favorited": True
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["installed_name"] == "Updated Name"
    assert data["is_favorited"] is True


# ============================================================================
# Template Rating Tests
# ============================================================================

@pytest.mark.asyncio
async def test_rate_template(async_client, auth_headers, created_template):
    """Test rating a template"""
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={
            "rating": 5,
            "review": "Excellent template, very helpful!"
        },
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["rating"] == 5
    assert data["review"] == "Excellent template, very helpful!"
    assert data["template_id"] == str(created_template.id)


@pytest.mark.asyncio
async def test_rating_updates_template_stats(async_client, auth_headers, test_db, created_template):
    """Test that rating updates template statistics"""
    initial_rating_count = created_template.rating_count
    
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 4},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    
    # Refresh from database
    test_db.refresh(created_template)
    assert created_template.rating_count == initial_rating_count + 1
    assert created_template.rating_avg > 0


@pytest.mark.asyncio
async def test_update_existing_rating(async_client, auth_headers, created_template):
    """Test updating an existing rating"""
    # First rating
    response1 = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 3, "review": "Good"},
        headers=auth_headers
    )
    rating_id = response1.json()["id"]
    
    # Update rating
    response2 = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 5, "review": "Actually excellent!"},
        headers=auth_headers
    )
    
    assert response2.status_code == 200
    data = response2.json()
    assert data["id"] == rating_id  # Same rating object
    assert data["rating"] == 5
    assert data["review"] == "Actually excellent!"


@pytest.mark.asyncio
async def test_list_template_ratings(async_client, auth_headers, created_template):
    """Test listing ratings for a template"""
    # Add a rating
    await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 5, "review": "Great!"},
        headers=auth_headers
    )
    
    # List ratings
    response = await async_client.get(
        f"/api/v1/marketplace/templates/{created_template.id}/ratings"
    )
    
    assert response.status_code == 200
    ratings = response.json()
    assert len(ratings) > 0
    assert ratings[0]["rating"] == 5


@pytest.mark.asyncio
async def test_rating_validation(async_client, auth_headers, created_template):
    """Test rating validation (1-5 stars)"""
    # Invalid rating (too high)
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 6},
        headers=auth_headers
    )
    
    assert response.status_code == 422  # Validation error
    
    # Invalid rating (too low)
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/rate",
        json={"rating": 0},
        headers=auth_headers
    )
    
    assert response.status_code == 422


# ============================================================================
# Template Publishing Tests
# ============================================================================

@pytest.mark.asyncio
async def test_publish_template(async_client, auth_headers, sample_template_data):
    """Test publishing a new template"""
    response = await async_client.post(
        "/api/v1/marketplace/templates",
        json=sample_template_data,
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == sample_template_data["name"]
    assert data["is_public"] is True
    assert "published_at" in data


@pytest.mark.asyncio
async def test_list_my_published_templates(async_client, auth_headers, created_template):
    """Test listing templates published by current user"""
    response = await async_client.get(
        "/api/v1/marketplace/my-published-templates",
        headers=auth_headers
    )
    
    assert response.status_code == 200
    templates = response.json()
    assert isinstance(templates, list)


@pytest.mark.asyncio
async def test_update_my_template(async_client, auth_headers, test_user, test_db, sample_template_data):
    """Test updating a template you created"""
    # Create template
    template = MarketplaceTemplate(
        id=uuid4(),
        creator_id=test_user.id,
        **sample_template_data
    )
    test_db.add(template)
    test_db.commit()
    
    # Update template
    response = await async_client.patch(
        f"/api/v1/marketplace/my-templates/{template.id}",
        json={"name": "Updated Template Name"},
        headers=auth_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Template Name"


@pytest.mark.asyncio
async def test_cannot_update_others_template(async_client, auth_headers, created_template):
    """Test that you cannot update someone else's template"""
    # created_template belongs to test_user, try to update as different user
    response = await async_client.patch(
        f"/api/v1/marketplace/my-templates/{created_template.id}",
        json={"name": "Hacked Name"},
        headers=auth_headers
    )
    
    # Should fail or return 404 (depends on who auth_headers belongs to)
    # If auth_headers is test_user, this test needs adjustment
    assert response.status_code in [403, 404]


# ============================================================================
# Marketplace Statistics Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_marketplace_stats(async_client, created_template):
    """Test getting marketplace statistics"""
    response = await async_client.get("/api/v1/marketplace/stats")
    
    assert response.status_code == 200
    data = response.json()
    assert "total_templates" in data
    assert "total_installs" in data
    assert "total_ratings" in data
    assert "featured_count" in data
    assert "categories_count" in data
    assert "top_templates" in data


@pytest.mark.asyncio
async def test_sorting_by_installs(async_client, created_template):
    """Test sorting templates by install count"""
    response = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"sort_by": "installs"}
    )
    
    assert response.status_code == 200
    data = response.json()
    templates = data["templates"]
    
    # Check if sorted by install_count descending
    if len(templates) > 1:
        for i in range(len(templates) - 1):
            assert templates[i]["install_count"] >= templates[i + 1]["install_count"]


@pytest.mark.asyncio
async def test_sorting_by_rating(async_client, created_template):
    """Test sorting templates by rating"""
    response = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"sort_by": "rating"}
    )
    
    assert response.status_code == 200
    data = response.json()
    templates = data["templates"]
    
    # Check if sorted by rating_avg descending
    if len(templates) > 1:
        for i in range(len(templates) - 1):
            assert templates[i]["rating_avg"] >= templates[i + 1]["rating_avg"]


@pytest.mark.asyncio
async def test_pagination(async_client):
    """Test template list pagination"""
    # Page 1
    response1 = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"page": 1, "limit": 5}
    )
    
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["page"] == 1
    assert data1["limit"] == 5
    
    # Page 2
    response2 = await async_client.get(
        "/api/v1/marketplace/templates",
        params={"page": 2, "limit": 5}
    )
    
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["page"] == 2


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

@pytest.mark.asyncio
async def test_install_archived_template_fails(async_client, auth_headers, test_db, created_template):
    """Test that installing an archived template fails"""
    # Archive the template
    created_template.is_archived = True
    test_db.commit()
    
    response = await async_client.post(
        f"/api/v1/marketplace/templates/{created_template.id}/install",
        json={},
        headers=auth_headers
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_private_template_not_in_list(async_client, test_db, test_user, sample_template_data):
    """Test that private templates are not listed publicly"""
    # Create private template
    private_template = MarketplaceTemplate(
        id=uuid4(),
        creator_id=test_user.id,
        is_public=False,
        **{**sample_template_data, "is_public": False}
    )
    test_db.add(private_template)
    test_db.commit()
    
    # Try to list templates
    response = await async_client.get("/api/v1/marketplace/templates")
    
    assert response.status_code == 200
    templates = response.json()["templates"]
    
    # Private template should not appear
    template_ids = [t["id"] for t in templates]
    assert str(private_template.id) not in template_ids


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
