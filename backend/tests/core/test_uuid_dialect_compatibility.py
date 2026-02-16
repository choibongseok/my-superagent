"""UUID column compatibility tests across SQL dialects."""

from sqlalchemy import create_engine, inspect
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

# Import models for side-effect table registration on Base.metadata.
import app.models  # noqa: F401
from app.core.database import Base


def test_all_model_tables_compile_on_sqlite():
    """All registered tables should compile cleanly for SQLite."""
    sqlite_dialect = sqlite.dialect()

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=sqlite_dialect))
        assert "CREATE TABLE" in ddl


def test_sqlite_metadata_create_all_handles_uuid_columns():
    """SQLite metadata creation should succeed with UUID-mapped columns."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    table_names = set(inspect(engine).get_table_names())
    expected_tables = {
        "users",
        "tasks",
        "chats",
        "messages",
        "teams",
        "templates",
        "template_ratings",
        "workspaces",
        "workspace_members",
        "workspace_invitations",
    }

    assert expected_tables.issubset(table_names)


def test_postgres_ddl_keeps_native_uuid_type():
    """PostgreSQL DDL should keep native UUID columns."""
    postgres_dialect = postgresql.dialect()
    chat_table = Base.metadata.tables["chats"]

    ddl = str(CreateTable(chat_table).compile(dialect=postgres_dialect))

    assert " UUID " in ddl
