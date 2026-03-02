"""Device Authorization Flow models (RFC 8628)."""
from datetime import datetime, timedelta
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from backend.app.db.base_class import Base


class DeviceCode(Base):
    """Device code for OAuth Device Authorization Flow.
    
    Flow:
    1. Client requests device code
    2. User visits verification URL and enters user code
    3. Client polls token endpoint
    4. After user approval, client receives access token
    """
    __tablename__ = "device_codes"

    id = Column(Integer, primary_key=True, index=True)
    device_code = Column(String(128), unique=True, nullable=False, index=True)
    user_code = Column(String(8), unique=True, nullable=False, index=True)  # e.g., "ABCD-EFGH"
    verification_uri = Column(String(255), nullable=False)
    verification_uri_complete = Column(String(512))  # Optional: includes user code
    expires_at = Column(DateTime, nullable=False)
    interval = Column(Integer, default=5)  # Polling interval in seconds
    
    # Authorization state
    user_id = Column(Integer, nullable=True)  # Set when user approves
    approved = Column(Boolean, default=False)
    denied = Column(Boolean, default=False)
    access_token = Column(Text, nullable=True)  # Set after approval
    
    # Metadata
    client_id = Column(String(255), nullable=True)
    scope = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_polled_at = Column(DateTime, nullable=True)

    @property
    def is_expired(self) -> bool:
        """Check if device code has expired."""
        return datetime.utcnow() > self.expires_at

    @property
    def formatted_user_code(self) -> str:
        """Return user code in XXXX-XXXX format."""
        if len(self.user_code) == 8:
            return f"{self.user_code[:4]}-{self.user_code[4:]}"
        return self.user_code

    @classmethod
    def create_device_code(
        cls,
        device_code: str,
        user_code: str,
        verification_uri: str,
        expires_in: int = 600,  # 10 minutes default
        interval: int = 5,
        client_id: str = None,
        scope: str = None,
    ) -> "DeviceCode":
        """Create a new device code entry."""
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
        verification_uri_complete = f"{verification_uri}?user_code={user_code}"
        
        return cls(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            verification_uri_complete=verification_uri_complete,
            expires_at=expires_at,
            interval=interval,
            client_id=client_id,
            scope=scope,
        )
