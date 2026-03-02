"""Tests for OAuth 2.0 Device Authorization Flow."""
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.device_code import DeviceCode
from app.models.user import User
from app.services.device_flow_service import DeviceFlowService


class TestDeviceCodeRequest:
    """Test device code request endpoint."""

    def test_request_device_code_success(self, client: TestClient, db: Session):
        """Test successful device code request."""
        response = client.post(
            "/api/v1/oauth/device/code",
            json={"client_id": "test-cli", "scope": "read write"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "device_code" in data
        assert "user_code" in data
        assert "verification_uri" in data
        assert "verification_uri_complete" in data
        assert "expires_in" in data
        assert "interval" in data

        # Verify user code format (XXXX-XXXX)
        assert len(data["user_code"]) == 9  # 8 chars + 1 dash
        assert data["user_code"][4] == "-"

        # Verify device code is saved in database
        device_code_obj = db.query(DeviceCode).filter_by(
            device_code=data["device_code"]
        ).first()
        assert device_code_obj is not None
        assert device_code_obj.client_id == "test-cli"
        assert device_code_obj.scope == "read write"

    def test_request_device_code_without_optional_params(
        self, client: TestClient, db: Session
    ):
        """Test device code request without optional parameters."""
        response = client.post("/api/v1/oauth/device/code", json={})

        assert response.status_code == 200
        data = response.json()
        assert "device_code" in data
        assert "user_code" in data

    def test_user_code_uniqueness(self, client: TestClient, db: Session):
        """Test that user codes are unique."""
        # Request multiple device codes
        codes = set()
        for _ in range(10):
            response = client.post("/api/v1/oauth/device/code", json={})
            assert response.status_code == 200
            user_code = response.json()["user_code"]
            codes.add(user_code)

        # All codes should be unique
        assert len(codes) == 10


class TestDeviceActivation:
    """Test device activation endpoints."""

    def test_get_activation_info_success(
        self, client: TestClient, db: Session, test_user: User
    ):
        """Test getting activation info for valid user code."""
        # Create device code
        device_code = DeviceFlowService.create_device_authorization(
            db=db,
            client_id="test-app",
            scope="read",
        )

        # Get activation info
        response = client.post(
            "/api/v1/oauth/device/activate",
            json={"user_code": device_code.formatted_user_code},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["user_code"] == device_code.formatted_user_code
        assert data["client_id"] == "test-app"
        assert data["scope"] == "read"

    def test_get_activation_info_without_dash(
        self, client: TestClient, db: Session
    ):
        """Test activation with user code without dash."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        # Remove dash from user code
        user_code_no_dash = device_code.user_code

        response = client.post(
            "/api/v1/oauth/device/activate",
            json={"user_code": user_code_no_dash},
        )

        assert response.status_code == 200

    def test_get_activation_info_invalid_code(self, client: TestClient):
        """Test activation with invalid user code."""
        response = client.post(
            "/api/v1/oauth/device/activate",
            json={"user_code": "INVALID1"},
        )

        assert response.status_code == 404
        assert "Invalid user code" in response.json()["detail"]

    def test_get_activation_info_expired_code(
        self, client: TestClient, db: Session
    ):
        """Test activation with expired device code."""
        # Create device code with 0 second expiry
        device_code = DeviceFlowService.create_device_authorization(
            db=db, expires_in=0
        )

        # Wait a moment to ensure expiry
        time.sleep(0.1)

        response = client.post(
            "/api/v1/oauth/device/activate",
            json={"user_code": device_code.formatted_user_code},
        )

        assert response.status_code == 410
        assert "expired" in response.json()["detail"].lower()

    def test_approve_device_success(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Test successful device approval."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        response = client.post(
            "/api/v1/oauth/device/approve",
            json={
                "user_code": device_code.formatted_user_code,
                "approved": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify device code was approved
        db.refresh(device_code)
        assert device_code.approved is True
        assert device_code.user_id == test_user.id
        assert device_code.access_token is not None

    def test_deny_device_success(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Test successful device denial."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        response = client.post(
            "/api/v1/oauth/device/approve",
            json={
                "user_code": device_code.formatted_user_code,
                "approved": False,
            },
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify device code was denied
        db.refresh(device_code)
        assert device_code.denied is True
        assert device_code.access_token is None

    def test_approve_device_unauthorized(self, client: TestClient, db: Session):
        """Test device approval without authentication."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        response = client.post(
            "/api/v1/oauth/device/approve",
            json={
                "user_code": device_code.formatted_user_code,
                "approved": True,
            },
        )

        assert response.status_code == 401

    def test_approve_already_approved_device(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Test approving an already approved device."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        # Approve once
        DeviceFlowService.approve_device(db, device_code, test_user)

        # Try to approve again
        response = client.post(
            "/api/v1/oauth/device/approve",
            json={
                "user_code": device_code.formatted_user_code,
                "approved": True,
            },
            headers=auth_headers,
        )

        assert response.status_code == 400
        assert "already approved" in response.json()["detail"].lower()


class TestDeviceTokenPolling:
    """Test device token polling endpoint."""

    def test_poll_authorization_pending(self, client: TestClient, db: Session):
        """Test polling when authorization is pending."""
        device_code = DeviceFlowService.create_device_authorization(db=db)

        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        assert response.status_code == 428  # Precondition Required
        data = response.json()["detail"]
        assert data["error"] == "authorization_pending"

    def test_poll_slow_down(self, client: TestClient, db: Session):
        """Test slow_down error when polling too fast."""
        device_code = DeviceFlowService.create_device_authorization(
            db=db, interval=5
        )

        # First poll
        client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        # Second poll immediately (too fast)
        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["error"] == "slow_down"

    def test_poll_expired_token(self, client: TestClient, db: Session):
        """Test polling with expired device code."""
        device_code = DeviceFlowService.create_device_authorization(
            db=db, expires_in=0
        )

        time.sleep(0.1)

        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["error"] == "expired_token"

    def test_poll_access_denied(
        self, client: TestClient, db: Session, test_user: User
    ):
        """Test polling after user denied authorization."""
        device_code = DeviceFlowService.create_device_authorization(db=db)
        DeviceFlowService.deny_device(db, device_code)

        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["error"] == "access_denied"

    def test_poll_success_after_approval(
        self, client: TestClient, db: Session, test_user: User
    ):
        """Test successful token retrieval after approval."""
        device_code = DeviceFlowService.create_device_authorization(db=db)
        DeviceFlowService.approve_device(db, device_code, test_user)

        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code.device_code,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert "expires_in" in data

    def test_poll_invalid_device_code(self, client: TestClient):
        """Test polling with invalid device code."""
        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "invalid-device-code",
            },
        )

        assert response.status_code == 400
        data = response.json()["detail"]
        assert data["error"] == "expired_token"


class TestDeviceFlowService:
    """Test DeviceFlowService methods."""

    def test_generate_device_code_length(self):
        """Test device code generation length."""
        code = DeviceFlowService.generate_device_code()
        assert len(code) > 40  # Should be ~64 chars

    def test_generate_user_code_format(self):
        """Test user code format (8 uppercase alphanumeric)."""
        code = DeviceFlowService.generate_user_code()
        assert len(code) == 8
        assert code.isupper()
        assert code.isalnum()
        # Should not contain confusing characters
        assert "0" not in code
        assert "O" not in code
        assert "1" not in code
        assert "I" not in code
        assert "L" not in code

    def test_user_code_uniqueness(self, db: Session):
        """Test that generated user codes are unique."""
        codes = set()
        for _ in range(100):
            device_code = DeviceFlowService.create_device_authorization(db=db)
            codes.add(device_code.user_code)

        # All codes should be unique
        assert len(codes) == 100

    def test_cleanup_expired_codes(self, db: Session):
        """Test cleanup of expired device codes."""
        # Create expired device code
        expired_device = DeviceCode.create_device_code(
            device_code="expired123",
            user_code="EXPIRED1",
            verification_uri="http://example.com",
            expires_in=-1,  # Already expired
        )
        db.add(expired_device)

        # Create valid device code
        valid_device = DeviceFlowService.create_device_authorization(
            db=db, expires_in=600
        )

        db.commit()

        # Cleanup
        deleted_count = DeviceFlowService.cleanup_expired_codes(db)

        assert deleted_count == 1

        # Verify expired was deleted, valid remains
        assert (
            db.query(DeviceCode).filter_by(device_code=expired_device.device_code).first()
            is None
        )
        assert (
            db.query(DeviceCode).filter_by(device_code=valid_device.device_code).first()
            is not None
        )


class TestDeviceFlowEndToEnd:
    """End-to-end tests for device authorization flow."""

    def test_complete_device_flow(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Test complete device authorization flow from start to finish."""
        # Step 1: Client requests device code
        response = client.post(
            "/api/v1/oauth/device/code",
            json={"client_id": "my-cli", "scope": "read write"},
        )
        assert response.status_code == 200
        device_data = response.json()
        device_code = device_data["device_code"]
        user_code = device_data["user_code"]

        # Step 2: Client starts polling (authorization pending)
        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        assert response.status_code == 428
        assert response.json()["detail"]["error"] == "authorization_pending"

        # Step 3: User visits verification URL and enters code
        response = client.post(
            "/api/v1/oauth/device/activate",
            json={"user_code": user_code},
        )
        assert response.status_code == 200
        activation_data = response.json()
        assert activation_data["client_id"] == "my-cli"

        # Step 4: User approves device
        response = client.post(
            "/api/v1/oauth/device/approve",
            json={"user_code": user_code, "approved": True},
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Step 5: Client polls again (now succeeds)
        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        assert response.status_code == 200
        token_data = response.json()
        assert "access_token" in token_data
        assert token_data["token_type"] == "bearer"

    def test_device_flow_denial(
        self, client: TestClient, db: Session, test_user: User, auth_headers: dict
    ):
        """Test device flow when user denies authorization."""
        # Step 1: Client requests device code
        response = client.post("/api/v1/oauth/device/code", json={})
        device_data = response.json()
        device_code = device_data["device_code"]
        user_code = device_data["user_code"]

        # Step 2: User denies device
        response = client.post(
            "/api/v1/oauth/device/approve",
            json={"user_code": user_code, "approved": False},
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Step 3: Client polls and gets access_denied
        response = client.post(
            "/api/v1/oauth/device/token",
            json={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
            },
        )
        assert response.status_code == 400
        assert response.json()["detail"]["error"] == "access_denied"
