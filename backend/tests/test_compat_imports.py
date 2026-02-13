"""Regression tests for compatibility imports used by legacy E2E tests."""

from app import database
from app.agents import DocsAgent, ResearchAgent, SheetsAgent, SlidesAgent


def test_legacy_database_module_exports_get_db():
    assert callable(database.get_db)


def test_agents_package_exports_core_agents():
    assert ResearchAgent is not None
    assert DocsAgent is not None
    assert SheetsAgent is not None
    assert SlidesAgent is not None
