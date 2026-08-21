"""
CEISA 4.0 Authentication Handler.

Handles login, token refresh, and token lifecycle management.
"""
import time
import logging
from dataclasses import dataclass, field
from typing import Optional
import httpx

from .config import config

logger = logging.getLogger("ceisa")


@dataclass
class CeisaToken:
    """Represents a CEISA API access token."""
    access_token: str
    expires_at: float  # Unix timestamp
    token_type: str = "bearer"
    expires_in: int = 900
    refresh_token: Optional[str] = None

    @property
    def is_expired(self) -> bool:
        """Check if token is expired (with 30s buffer)."""
        return time.time() >= (self.expires_at - 30)

    def to_dict(self) -> dict:
        return {
            "access_token": self.access_token,
            "expires_at": self.expires_at,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
        }

    @classmethod
    def from_response(cls, data: dict) -> "CeisaToken":
        """Create token from API login response."""
        now = time.time()
        expires_in = data.get("expires_in", 900)
        return cls(
            access_token=data["access_token"],
            token_type=data.get("token_type", "bearer"),
            expires_in=expires_in,
            expires_at=now + expires_in,
            refresh_token=data.get("refresh_token"),
        )


class CeisaAuth:
    """
    Manages CEISA API authentication lifecycle.

    Flow:
      1. Login with username/password → get access_token
      2. Use access_token as Bearer token for all subsequent requests
      3. Re-authenticate when token expires (every ~15 minutes)
    """

    def __init__(self, cfg: Optional[config.__class__] = None):
        self.cfg = config
        self._token: Optional[CeisaToken] = None
        self._client = httpx.AsyncClient(timeout=30.0)

    async def login(self) -> CeisaToken:
        """
        Authenticate with CEISA API and obtain access token.

        POST {auth_url}
        Body: {"username": "...", "password": "..."}

        Returns CeisaToken on success.
        Raises httpx.HTTPStatusError on failure.
        """
        payload = {
            "username": self.cfg.username,
            "password": self.cfg.password,
        }

        logger.info(f"CEISA login to {self.cfg.auth_url} ...")
        response = await self._client.post(
            self.cfg.auth_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            raise ValueError(f"CEISA login failed: {data.get('message', data)}")

        token = CeisaToken.from_response(data["item"])
        self._token = token
        logger.info(
            f"CEISA login OK — token expires in {token.expires_in}s "
            f"(at {time.strftime('%H:%M:%S', time.localtime(token.expires_at))})"
        )
        return token

    async def get_token(self) -> CeisaToken:
        """
        Get a valid access token, re-authenticating if expired.
        This is the main method route handlers should call.
        """
        if self._token is None or self._token.is_expired:
            return await self.login()
        return self._token

    async def get_auth_header(self) -> dict:
        """Get the Authorization header dict with a valid token."""
        token = await self.get_token()
        return {"Authorization": f"Bearer {token.access_token}"}

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# ── Module-level auth instance ────────────────────────────────────────────────────
_auth: Optional[CeisaAuth] = None


async def get_auth() -> CeisaAuth:
    """Get or create the module-level CEISA auth instance."""
    global _auth
    if _auth is None:
        _auth = CeisaAuth()
    return _auth
