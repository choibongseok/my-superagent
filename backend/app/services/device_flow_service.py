"""Service for OAuth 2.0 Device Authorization Flow."""
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.device_code import DeviceCode
from app.models.user import User
from app.core.security import create_access_token


class DeviceFlowService:
    """Handle OAuth 2.0 Device Authorization Flow operations."""

    @staticmethod
    def generate_device_code() -> str:
        """Generate a secure random device code (64 chars)."""
        return secrets.token_urlsafe(48)  # ~64 chars base64

    @staticmethod
    def generate_user_code(length: int = 8) -> str:
        """Generate a user-friendly code (uppercase letters, no ambiguous chars).
        
        Excludes: 0, O, 1, I, L to reduce user confusion.
        Format: XXXX-XXXX (dash added by model property)
        """
        alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # No 0,O,1,I,L
        return "".join(secrets.choice(alphabet) for _ in range(length))

    @staticmethod
    def create_device_authorization(
        db: Session,
        client_id: Optional[str] = None,
        scope: Optional[str] = None,
        expires_in: int = 600,  # 10 minutes
        interval: int = 5,
    ) -> DeviceCode:
        """Create a new device authorization request.
        
        Returns:
            DeviceCode with device_code, user_code, verification_uri
        """
        device_code = DeviceFlowService.generate_device_code()
        user_code = DeviceFlowService.generate_user_code()
        
        # Ensure uniqueness
        max_retries = 5
        for _ in range(max_retries):
            existing_device = db.query(DeviceCode).filter_by(device_code=device_code).first()
            existing_user = db.query(DeviceCode).filter_by(user_code=user_code).first()
            
            if not existing_device and not existing_user:
                break
            
            device_code = DeviceFlowService.generate_device_code()
            user_code = DeviceFlowService.generate_user_code()
        
        verification_uri = f"{settings.FRONTEND_URL}/device"
        
        device_code_obj = DeviceCode.create_device_code(
            device_code=device_code,
            user_code=user_code,
            verification_uri=verification_uri,
            expires_in=expires_in,
            interval=interval,
            client_id=client_id,
            scope=scope,
        )
        
        db.add(device_code_obj)
        db.commit()
        db.refresh(device_code_obj)
        
        return device_code_obj

    @staticmethod
    def get_device_code(db: Session, device_code: str) -> Optional[DeviceCode]:
        """Retrieve device code by device_code string."""
        return db.query(DeviceCode).filter_by(device_code=device_code).first()

    @staticmethod
    def get_by_user_code(db: Session, user_code: str) -> Optional[DeviceCode]:
        """Retrieve device code by user_code (for activation page)."""
        # Remove dash if present
        user_code = user_code.replace("-", "").upper()
        return db.query(DeviceCode).filter_by(user_code=user_code).first()

    @staticmethod
    def approve_device(
        db: Session,
        device_code_obj: DeviceCode,
        user: User,
    ) -> str:
        """Approve device authorization and generate access token.
        
        Returns:
            Access token string
        """
        if device_code_obj.is_expired:
            raise ValueError("Device code has expired")
        
        if device_code_obj.approved:
            raise ValueError("Device code already approved")
        
        if device_code_obj.denied:
            raise ValueError("Device code was denied")
        
        # Generate access token
        access_token = create_access_token(
            data={"sub": str(user.id)},
            expires_delta=timedelta(days=30),
        )
        
        # Update device code
        device_code_obj.user_id = user.id
        device_code_obj.approved = True
        device_code_obj.access_token = access_token
        
        db.commit()
        db.refresh(device_code_obj)
        
        return access_token

    @staticmethod
    def deny_device(db: Session, device_code_obj: DeviceCode):
        """Deny device authorization."""
        if device_code_obj.is_expired:
            raise ValueError("Device code has expired")
        
        if device_code_obj.approved:
            raise ValueError("Device code already approved")
        
        device_code_obj.denied = True
        db.commit()

    @staticmethod
    def poll_device_token(
        db: Session,
        device_code: str,
    ) -> Tuple[str, Optional[str]]:
        """Poll for device token.
        
        Returns:
            Tuple of (status, access_token)
            
        Status codes:
            - "authorization_pending": User hasn't approved yet
            - "slow_down": Client is polling too fast
            - "expired_token": Device code has expired
            - "access_denied": User denied authorization
            - "success": Token is ready
        """
        device_code_obj = DeviceFlowService.get_device_code(db, device_code)
        
        if not device_code_obj:
            return ("expired_token", None)
        
        if device_code_obj.is_expired:
            return ("expired_token", None)
        
        if device_code_obj.denied:
            return ("access_denied", None)
        
        # Check polling rate
        if device_code_obj.last_polled_at:
            time_since_last_poll = (datetime.utcnow() - device_code_obj.last_polled_at).total_seconds()
            if time_since_last_poll < device_code_obj.interval:
                # Client is polling too fast
                return ("slow_down", None)
        
        # Update last polled time
        device_code_obj.last_polled_at = datetime.utcnow()
        db.commit()
        
        if device_code_obj.approved and device_code_obj.access_token:
            return ("success", device_code_obj.access_token)
        
        return ("authorization_pending", None)

    @staticmethod
    def cleanup_expired_codes(db: Session) -> int:
        """Delete expired device codes.
        
        Returns:
            Number of deleted codes
        """
        expired_codes = db.query(DeviceCode).filter(
            DeviceCode.expires_at < datetime.utcnow()
        ).all()
        
        count = len(expired_codes)
        for code in expired_codes:
            db.delete(code)
        
        db.commit()
        return count
