"""API endpoints for OAuth 2.0 Device Authorization Flow."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api import dependencies
from app.models.user import User
from app.schemas.device_flow import (
    DeviceActivationInfo,
    DeviceActivationRequest,
    DeviceApprovalRequest,
    DeviceAuthorizationRequest,
    DeviceAuthorizationResponse,
    DeviceTokenError,
    DeviceTokenRequest,
    DeviceTokenResponse,
)
from app.services.device_flow_service import DeviceFlowService

router = APIRouter()


@router.post(
    "/device/code",
    response_model=DeviceAuthorizationResponse,
    summary="Request Device Code",
    description="Step 1: Client requests device and user codes (RFC 8628 Section 3.1)",
)
def request_device_code(
    request: DeviceAuthorizationRequest,
    db: Session = Depends(dependencies.get_db),
):
    """Request a device code for device authorization flow.
    
    Use cases:
    - CLI tools
    - Smart TV apps
    - IoT devices
    - Any device with limited input capability
    
    Example:
        POST /api/v1/oauth/device/code
        {
            "client_id": "my-cli-app",
            "scope": "read write"
        }
        
        Response:
        {
            "device_code": "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS",
            "user_code": "WDJB-MJHT",
            "verification_uri": "https://agenthq.com/device",
            "verification_uri_complete": "https://agenthq.com/device?user_code=WDJB-MJHT",
            "expires_in": 600,
            "interval": 5
        }
    """
    try:
        device_code = DeviceFlowService.create_device_authorization(
            db=db,
            client_id=request.client_id,
            scope=request.scope,
        )
        
        return DeviceAuthorizationResponse(
            device_code=device_code.device_code,
            user_code=device_code.formatted_user_code,
            verification_uri=device_code.verification_uri,
            verification_uri_complete=device_code.verification_uri_complete,
            expires_in=int((device_code.expires_at - device_code.created_at).total_seconds()),
            interval=device_code.interval,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create device code: {str(e)}",
        )


@router.post(
    "/device/token",
    response_model=DeviceTokenResponse,
    responses={
        400: {"model": DeviceTokenError},
        428: {"model": DeviceTokenError},
    },
    summary="Poll for Device Token",
    description="Step 3: Client polls for access token (RFC 8628 Section 3.4)",
)
def poll_device_token(
    request: DeviceTokenRequest,
    db: Session = Depends(dependencies.get_db),
):
    """Poll for device token after user authorization.
    
    Client should poll at the interval specified in device code response.
    
    Error codes:
    - authorization_pending: User hasn't authorized yet (poll again)
    - slow_down: Client is polling too fast (increase interval)
    - expired_token: Device code has expired (start over)
    - access_denied: User denied authorization
    
    Example:
        POST /api/v1/oauth/device/token
        {
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": "GmRhmhcxhwAzkoEqiMEg_DnyEysNkuNhszIySk9eS"
        }
        
        Response (authorization_pending):
        HTTP 428
        {
            "error": "authorization_pending",
            "error_description": "User has not yet authorized the device"
        }
        
        Response (success):
        HTTP 200
        {
            "access_token": "eyJhbGci...",
            "token_type": "bearer",
            "expires_in": 2592000
        }
    """
    status_code, access_token = DeviceFlowService.poll_device_token(
        db=db,
        device_code=request.device_code,
    )
    
    if status_code == "success":
        return DeviceTokenResponse(access_token=access_token)
    
    # Return appropriate error
    error_messages = {
        "authorization_pending": "User has not yet authorized the device",
        "slow_down": "Client is polling too frequently, increase interval",
        "expired_token": "Device code has expired",
        "access_denied": "User denied authorization",
    }
    
    # Use HTTP 428 (Precondition Required) for pending
    # Use HTTP 400 for other errors
    http_status = (
        status.HTTP_428_PRECONDITION_REQUIRED
        if status_code == "authorization_pending"
        else status.HTTP_400_BAD_REQUEST
    )
    
    raise HTTPException(
        status_code=http_status,
        detail={
            "error": status_code,
            "error_description": error_messages.get(status_code, "Unknown error"),
        },
    )


@router.post(
    "/device/activate",
    response_model=DeviceActivationInfo,
    summary="Get Device Activation Info",
    description="Step 2a: User enters code to see device info",
)
def get_device_activation_info(
    request: DeviceActivationRequest,
    db: Session = Depends(dependencies.get_db),
):
    """Get information about device authorization request.
    
    Called by frontend when user enters user code.
    
    Example:
        POST /api/v1/oauth/device/activate
        {
            "user_code": "WDJB-MJHT"
        }
        
        Response:
        {
            "user_code": "WDJB-MJHT",
            "client_id": "my-cli-app",
            "scope": "read write",
            "created_at": "2026-03-02T16:00:00Z"
        }
    """
    device_code = DeviceFlowService.get_by_user_code(db, request.user_code)
    
    if not device_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid user code",
        )
    
    if device_code.is_expired:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="User code has expired",
        )
    
    if device_code.approved or device_code.denied:
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="User code has already been used",
        )
    
    return DeviceActivationInfo(
        user_code=device_code.formatted_user_code,
        client_id=device_code.client_id,
        scope=device_code.scope,
        created_at=device_code.created_at,
    )


@router.post(
    "/device/approve",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Approve/Deny Device",
    description="Step 2b: User approves or denies device authorization",
)
def approve_device(
    request: DeviceApprovalRequest,
    current_user: User = Depends(dependencies.get_current_user),
    db: Session = Depends(dependencies.get_db),
):
    """Approve or deny device authorization.
    
    Called by frontend after user authenticates and confirms.
    
    Example:
        POST /api/v1/oauth/device/approve
        Authorization: Bearer <user_jwt>
        {
            "user_code": "WDJB-MJHT",
            "approved": true
        }
    """
    device_code = DeviceFlowService.get_by_user_code(db, request.user_code)
    
    if not device_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid user code",
        )
    
    try:
        if request.approved:
            DeviceFlowService.approve_device(db, device_code, current_user)
        else:
            DeviceFlowService.deny_device(db, device_code)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    
    return None
