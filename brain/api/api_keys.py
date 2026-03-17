"""API Key Management Endpoints"""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from brain.api.auth import api_key_manager, APIKey, verify_api_key

router = APIRouter()


# Request/Response Models
class CreateAPIKeyRequest(BaseModel):
    """Request to create a new API key"""

    name: str = Field(..., description="Human-readable name for the key")
    permissions: List[str] = Field(
        default=["read", "write"], description="List of permissions for this key"
    )


class CreateAPIKeyResponse(BaseModel):
    """Response after creating an API key"""

    key_id: str
    api_key: str  # ONLY shown once!
    name: str
    created_at: float
    permissions: List[str]
    warning: str = "Save this API key securely. It won't be shown again!"


class APIKeyInfo(BaseModel):
    """API key information (without sensitive data)"""

    key_id: str
    name: str
    created_at: float
    last_used: Optional[float]
    is_active: bool
    permissions: List[str]


class APIKeysListResponse(BaseModel):
    """List of API keys"""

    keys: List[APIKeyInfo]
    total: int


# Endpoints
@router.post("/api-keys", response_model=CreateAPIKeyResponse)
async def create_api_key(
    request: CreateAPIKeyRequest,
    current_key: Optional[APIKey] = Depends(verify_api_key),
):
    """
    Create a new API key.

    **Important**: The API key will only be shown once in the response.
    Save it securely - you won't be able to retrieve it later!

    Permissions:
    - `read`: Can make GET requests
    - `write`: Can make POST/PUT/DELETE requests
    - `admin`: Can manage API keys (create, revoke, delete)
    """
    try:
        key_id, api_key = api_key_manager.create_key(
            name=request.name, permissions=request.permissions
        )

        key_obj = api_key_manager.get_key(key_id)

        return CreateAPIKeyResponse(
            key_id=key_id,
            api_key=api_key,
            name=key_obj.name,
            created_at=key_obj.created_at,
            permissions=key_obj.permissions,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create API key: {e}")


@router.get("/api-keys", response_model=APIKeysListResponse)
async def list_api_keys(current_key: Optional[APIKey] = Depends(verify_api_key)):
    """
    List all API keys (without showing the actual keys).

    Useful for:
    - Auditing active keys
    - Checking last usage
    - Identifying keys to revoke
    """
    try:
        keys = api_key_manager.list_keys()

        return APIKeysListResponse(
            keys=[
                APIKeyInfo(
                    key_id=k["key_id"],
                    name=k["name"],
                    created_at=k["created_at"],
                    last_used=k["last_used"],
                    is_active=k["is_active"],
                    permissions=k["permissions"],
                )
                for k in keys
            ],
            total=len(keys),
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list API keys: {e}")


@router.get("/api-keys/{key_id}", response_model=APIKeyInfo)
async def get_api_key(
    key_id: str,
    current_key: Optional[APIKey] = Depends(verify_api_key),
):
    """Get information about a specific API key"""
    key_obj = api_key_manager.get_key(key_id)

    if not key_obj:
        raise HTTPException(status_code=404, detail="API key not found")

    return APIKeyInfo(
        key_id=key_obj.key_id,
        name=key_obj.name,
        created_at=key_obj.created_at,
        last_used=key_obj.last_used,
        is_active=key_obj.is_active,
        permissions=key_obj.permissions,
    )


@router.post("/api-keys/{key_id}/revoke")
async def revoke_api_key(
    key_id: str,
    current_key: Optional[APIKey] = Depends(verify_api_key),
):
    """
    Revoke (disable) an API key.

    The key will remain in the database but won't work for authentication.
    Can be useful for temporarily disabling a key without losing its history.
    """
    success = api_key_manager.revoke_key(key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {
        "status": "revoked",
        "key_id": key_id,
        "message": "API key has been revoked and can no longer be used",
    }


@router.delete("/api-keys/{key_id}")
async def delete_api_key(
    key_id: str,
    current_key: Optional[APIKey] = Depends(verify_api_key),
):
    """
    Permanently delete an API key.

    **Warning**: This action cannot be undone!
    The key and its history will be completely removed.
    """
    success = api_key_manager.delete_key(key_id)

    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    return {
        "status": "deleted",
        "key_id": key_id,
        "message": "API key has been permanently deleted",
    }


@router.get("/api-keys/validate/current")
async def validate_current_key(current_key: Optional[APIKey] = Depends(verify_api_key)):
    """
    Validate the current API key.

    Useful for:
    - Testing if a key is valid
    - Checking key permissions
    - Debugging authentication issues

    Returns key information if valid, 401 if invalid.
    """
    if not current_key:
        return {
            "status": "no_auth_required",
            "message": "API authentication is currently disabled",
        }

    return {
        "status": "valid",
        "key_id": current_key.key_id,
        "name": current_key.name,
        "permissions": current_key.permissions,
        "last_used": current_key.last_used,
    }
