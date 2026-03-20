"""API Authentication and Authorization"""

import secrets
import hashlib
import time
from typing import Optional, Dict
from dataclasses import dataclass, field
from pathlib import Path
import json
import logging

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from brain.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@dataclass
class APIKey:
    """API Key information"""

    key_id: str
    key_hash: str  # SHA-256 hash of the actual key
    name: str
    created_at: float
    last_used: Optional[float] = None
    is_active: bool = True
    permissions: list = field(default_factory=lambda: ["read", "write"])

    def to_dict(self) -> dict:
        """Convert to dictionary (without sensitive data)"""
        return {
            "key_id": self.key_id,
            "name": self.name,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "is_active": self.is_active,
            "permissions": self.permissions,
        }


class APIKeyManager:
    """
    Manages API keys for authentication.

    Features:
    - Generate secure API keys
    - Validate keys
    - Store keys securely (hashed)
    - Track usage
    - Enable/disable keys
    """

    def __init__(self, keys_file: Optional[Path] = None):
        """
        Initialize API key manager.

        Args:
            keys_file: Path to JSON file storing API keys
        """
        self.keys_file = keys_file or settings.data_dir / "api_keys.json"
        self.keys: Dict[str, APIKey] = {}
        self._load_keys()

    def _load_keys(self):
        """Load API keys from disk"""
        if not self.keys_file.exists():
            logger.info("No API keys file found, starting with empty key store")
            return

        try:
            with open(self.keys_file, "r") as f:
                keys_data = json.load(f)

            for key_id, key_dict in keys_data.items():
                self.keys[key_id] = APIKey(
                    key_id=key_dict["key_id"],
                    key_hash=key_dict["key_hash"],
                    name=key_dict["name"],
                    created_at=key_dict["created_at"],
                    last_used=key_dict.get("last_used"),
                    is_active=key_dict.get("is_active", True),
                    permissions=key_dict.get("permissions", ["read", "write"]),
                )

            logger.info(f"Loaded {len(self.keys)} API keys")

        except Exception as e:
            logger.error(f"Error loading API keys: {e}")
            self.keys = {}

    def _save_keys(self):
        """Save API keys to disk"""
        try:
            # Ensure directory exists
            self.keys_file.parent.mkdir(parents=True, exist_ok=True)

            # Save keys (hashed, never plain text)
            keys_data = {
                key_id: {
                    "key_id": key.key_id,
                    "key_hash": key.key_hash,
                    "name": key.name,
                    "created_at": key.created_at,
                    "last_used": key.last_used,
                    "is_active": key.is_active,
                    "permissions": key.permissions,
                }
                for key_id, key in self.keys.items()
            }

            with open(self.keys_file, "w") as f:
                json.dump(keys_data, f, indent=2)

            logger.info(f"Saved {len(self.keys)} API keys")

        except Exception as e:
            logger.error(f"Error saving API keys: {e}")

    @staticmethod
    def _hash_key(key: str) -> str:
        """Hash an API key using SHA-256"""
        return hashlib.sha256(key.encode()).hexdigest()

    @staticmethod
    def _generate_key() -> tuple[str, str]:
        """
        Generate a new API key.

        Returns:
            tuple: (key_id, api_key)
                - key_id: Short identifier (8 chars)
                - api_key: Full key to give to user (32 chars)
        """
        # Format: brain_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
        key_id = secrets.token_urlsafe(6)[:8]  # Short ID for identification
        api_key = f"brain_{secrets.token_urlsafe(24)}"  # Full key for auth
        return key_id, api_key

    def create_key(self, name: str, permissions: Optional[list] = None) -> tuple[str, str]:
        """
        Create a new API key.

        Args:
            name: Human-readable name for the key
            permissions: List of permissions (default: ["read", "write"])

        Returns:
            tuple: (key_id, api_key) - SAVE THE API KEY, it won't be shown again!
        """
        key_id, api_key = self._generate_key()
        key_hash = self._hash_key(api_key)

        api_key_obj = APIKey(
            key_id=key_id,
            key_hash=key_hash,
            name=name,
            created_at=time.time(),
            permissions=permissions or ["read", "write"],
        )

        self.keys[key_id] = api_key_obj
        self._save_keys()

        logger.info(f"Created API key: {key_id} ({name})")

        return key_id, api_key

    def validate_key(self, api_key: str) -> Optional[APIKey]:
        """
        Validate an API key.

        Args:
            api_key: The API key to validate

        Returns:
            APIKey object if valid, None otherwise
        """
        key_hash = self._hash_key(api_key)

        for key_obj in self.keys.values():
            if key_obj.key_hash == key_hash:
                if not key_obj.is_active:
                    logger.warning(f"Attempted use of inactive key: {key_obj.key_id}")
                    return None

                # Update last used timestamp
                key_obj.last_used = time.time()
                self._save_keys()

                logger.debug(f"Validated API key: {key_obj.key_id}")
                return key_obj

        logger.warning("Invalid API key attempt")
        return None

    def list_keys(self) -> list[dict]:
        """
        List all API keys (without sensitive data).

        Returns:
            List of key information dicts
        """
        return [key.to_dict() for key in self.keys.values()]

    def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get API key by ID"""
        return self.keys.get(key_id)

    def revoke_key(self, key_id: str) -> bool:
        """
        Revoke (disable) an API key.

        Args:
            key_id: ID of the key to revoke

        Returns:
            True if successful, False if key not found
        """
        if key_id not in self.keys:
            return False

        self.keys[key_id].is_active = False
        self._save_keys()

        logger.info(f"Revoked API key: {key_id}")
        return True

    def delete_key(self, key_id: str) -> bool:
        """
        Delete an API key permanently.

        Args:
            key_id: ID of the key to delete

        Returns:
            True if successful, False if key not found
        """
        if key_id not in self.keys:
            return False

        del self.keys[key_id]
        self._save_keys()

        logger.info(f"Deleted API key: {key_id}")
        return True


# Global API key manager instance
api_key_manager = APIKeyManager()


# Dependency for FastAPI routes
async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[APIKey]:
    """
    FastAPI dependency to verify API key.

    Usage:
        @app.get("/protected")
        async def protected_route(api_key: APIKey = Depends(verify_api_key)):
            # Route code here

    Returns:
        APIKey object if authentication is disabled or key is valid

    Raises:
        HTTPException: If authentication is required and key is invalid
    """
    # If authentication is disabled, allow access
    if not settings.require_api_key:
        return None

    # Authentication required
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include it in the Authorization header as 'Bearer <key>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the key
    api_key_obj = api_key_manager.validate_key(credentials.credentials)

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key_obj


# Simplified dependency function for routes that require API key
async def require_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> APIKey:
    """
    FastAPI dependency for routes that require API key authentication.

    This is a wrapper around verify_api_key that always requires authentication,
    even if settings.require_api_key is False.

    Usage:
        @app.get("/protected", dependencies=[Depends(require_api_key)])
        async def protected_route():
            # Route code here

    Raises:
        HTTPException: If key is invalid or missing
    """
    # For now, if authentication is disabled globally, return a dummy key
    if not settings.require_api_key:
        return APIKey(
            key_id="dummy",
            key_hash="",
            name="No Authentication",
            created_at=time.time(),
            permissions=["read", "write"]
        )

    # Otherwise require valid credentials
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required. Include it in the Authorization header as 'Bearer <key>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate the key
    api_key_obj = api_key_manager.validate_key(credentials.credentials)

    if not api_key_obj:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return api_key_obj
