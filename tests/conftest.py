"""
Shared test fixtures for all tests.
"""

import pytest
from uuid import uuid4
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

# Import app first to ensure all models are registered
from backend.app.main import app
from backend.app.core.database import Base, get_db
from backend.app.core.security import create_access_token


# Create in-memory SQLite database for testing
SQLALCHEMY_TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture(scope="function")
def test_db() -> Session:
    """Create a fresh database for each test."""
    engine = create_engine(
        SQLALCHEMY_TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(scope="function")
def client(test_db: Session) -> TestClient:
    """Create a test client with database override."""
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db: Session):
    """Create a test user."""
    from backend.app.models.user import User
    
    user = User(
        id=uuid4(),
        email="test@example.com",
        full_name="Test User",
        is_active=True,
        is_admin=False
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user) -> str:
    """Create an access token for the test user."""
    return create_access_token(subject=str(test_user.id))


@pytest.fixture
def auth_headers(auth_token: str) -> dict:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def admin_user(test_db: Session):
    """Create an admin user."""
    from backend.app.models.user import User
    
    user = User(
        id=uuid4(),
        email="admin@example.com",
        full_name="Admin User",
        is_active=True,
        is_admin=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def admin_token(admin_user) -> str:
    """Create an access token for the admin user."""
    return create_access_token(subject=str(admin_user.id))


@pytest.fixture
def admin_headers(admin_token: str) -> dict:
    """Create authorization headers for admin."""
    return {"Authorization": f"Bearer {admin_token}"}
