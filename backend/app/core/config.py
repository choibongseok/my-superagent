"""Application configuration."""

from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "AgentHQ"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://agenthq:password@localhost:5432/agenthq"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def fix_database_url(cls, v: str) -> str:
        """Convert postgres:// to postgresql+asyncpg:// for SQLAlchemy async.
        
        Also strips out psycopg2-specific parameters like sslmode that aren't
        compatible with asyncpg. For asyncpg, SSL is controlled via connect_args
        or by using ssl=true/false in the URL.
        """
        # First, convert the protocol
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        # Strip out sslmode parameter (psycopg2-specific, not compatible with asyncpg)
        # asyncpg uses ssl=true/false or ssl=require instead
        if "?sslmode=" in v:
            # Extract the sslmode value to potentially convert it
            import re
            sslmode_match = re.search(r'[?&]sslmode=([^&]+)', v)
            if sslmode_match:
                sslmode_value = sslmode_match.group(1)
                # Remove the sslmode parameter
                v = re.sub(r'[?&]sslmode=[^&]+&?', '', v)
                # Clean up any trailing ? or & 
                v = re.sub(r'[?&]$', '', v)
                
                # Convert to asyncpg SSL format if needed
                # sslmode=disable -> no ssl parameter needed (default)
                # sslmode=require -> add ssl=require
                # sslmode=prefer -> no ssl parameter (asyncpg will try SSL first)
                if sslmode_value not in ('disable', 'allow', 'prefer'):
                    # Add asyncpg-compatible SSL parameter
                    separator = '&' if '?' in v else '?'
                    v = f"{v}{separator}ssl=require"
        
        return v

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_DEFAULT_TTL: int = 300  # 5 minutes

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # JWT Authentication
    SECRET_KEY: str = Field(default="change-this-secret-key-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Google OAuth
    GOOGLE_CLIENT_ID: str = Field(default="")
    GOOGLE_CLIENT_SECRET: str = Field(default="")
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/callback"
    GOOGLE_SCOPES: str = (
        "https://www.googleapis.com/auth/documents,"
        "https://www.googleapis.com/auth/spreadsheets,"
        "https://www.googleapis.com/auth/presentations,"
        "https://www.googleapis.com/auth/drive.file"
    )
    
    # GitHub OAuth
    GITHUB_CLIENT_ID: str = Field(default="")
    GITHUB_CLIENT_SECRET: str = Field(default="")
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/github/callback"
    
    # Microsoft OAuth
    MICROSOFT_CLIENT_ID: str = Field(default="")
    MICROSOFT_CLIENT_SECRET: str = Field(default="")
    MICROSOFT_TENANT_ID: str = Field(default="common")  # "common" for multi-tenant
    MICROSOFT_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/microsoft/callback"

    # OpenAI
    OPENAI_API_KEY: str = Field(default="")
    OPENAI_MODEL: str = "gpt-4-turbo-preview"
    OPENAI_MAX_TOKENS: int = 4096
    OPENAI_TEMPERATURE: float = 0.7

    # Anthropic (Optional)
    ANTHROPIC_API_KEY: str = Field(default="")
    ANTHROPIC_MODEL: str = "claude-3-opus-20240229"

    # Google Cloud (Optional)
    GOOGLE_APPLICATION_CREDENTIALS: str = Field(default="")
    GCS_BUCKET_NAME: str = Field(default="")

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8080,tauri://localhost"
    CORS_ALLOW_CREDENTIALS: bool = True

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_PER_MINUTE: int = 100
    RATE_LIMIT_PER_HOUR: int = 1000
    
    # Per-endpoint rate limits (overrides)
    RATE_LIMIT_TASKS_CREATE: int = 10  # /api/v1/tasks/create -> 10/min
    RATE_LIMIT_RESEARCH: int = 20  # /api/v1/agents/research -> 20/min
    RATE_LIMIT_DOCS: int = 15  # /api/v1/agents/docs -> 15/min
    RATE_LIMIT_SHEETS: int = 15  # /api/v1/agents/sheets -> 15/min
    RATE_LIMIT_SLIDES: int = 10  # /api/v1/agents/slides -> 10/min
    RATE_LIMIT_FACT_CHECK: int = 30  # /api/v1/fact-check -> 30/min

    # Task Queue
    TASK_MAX_RETRIES: int = 3
    TASK_TIMEOUT_SECONDS: int = 300

    # Web Scraping
    USER_AGENT: str = "AgentHQ Bot/1.0"
    SCRAPING_TIMEOUT: int = 30
    MAX_CONCURRENT_REQUESTS: int = 10

    # Monitoring
    PROMETHEUS_PORT: int = 9090
    ENABLE_METRICS: bool = True

    # Email
    EMAIL_ENABLED: bool = Field(default=False)
    SMTP_HOST: str = Field(default="smtp.gmail.com")
    SMTP_PORT: int = Field(default=587)
    SMTP_USER: str = Field(default="")
    SMTP_PASSWORD: str = Field(default="")
    FROM_EMAIL: str = Field(default="noreply@agenthq.com")
    FROM_NAME: str = Field(default="AgentHQ")
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v):
        """Parse CORS origins from string to list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as list."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]
        return self.CORS_ORIGINS

    @property
    def google_scopes_list(self) -> List[str]:
        """Get Google scopes as list."""
        return [scope.strip() for scope in self.GOOGLE_SCOPES.split(",")]


# Global settings instance
settings = Settings()
