"""
CEISA 4.0 Host-to-Host Integration Package.

Provides API client, authentication, and data mapping for CEISA 4.0 submission.

Usage:
    from ceisa import CeisaClient, CeisaMapper

    client = CeisaClient()
    result = await client.submit_document(entities)
    print(result.id_header, result.status)

Environment variables:
    CEISA_ENV=dev|prod          (default: dev)
    CEISA_USERNAME=<username>    (required)
    CEISA_PASSWORD=<password>    (required)
"""
from .config import config, CeisaConfig
from .auth import CeisaAuth, CeisaToken, get_auth
from .mapper import CeisaMapper
from .client import CeisaClient, CeisaAPIError, CeisaSubmissionResult

__all__ = [
    "config",
    "CeisaConfig",
    "CeisaAuth",
    "CeisaToken",
    "CeisaMapper",
    "CeisaClient",
    "CeisaAPIError",
    "CeisaSubmissionResult",
    "get_auth",
]
