import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class CeisaConfig:

    # Environment
    env: str = "dev"

    # Base URLs
    auth_url: str = "https://apisdev-gw.beacukai.go.id/nle-oauth/v1/user/login"
    api_base_url: str = "https://apisdev-gw.beacukai.go.id/openapi"
    document_url: str = "https://apisdev-gw.beacukai.go.id/openapi/document"

    # Credentials (set via .env)
    username: str = ""
    password: str = ""

    # Token setting
    token_expires_in: int = 900

    def __post_init__(self):
        # Allow override via environment variables
        self.env = os.getenv("CEISA_ENV", self.env)

        if self.env == "prod":
            self.auth_url = "https://apis-gw.beacukai.go.id/nle-oauth/v1/user/login"
            self.api_base_url = "https://apis-gw.beacukai.go.id/openapi"
            self.document_url = "https://apis-gw.beacukai.go.id/openapi/document"

        self.username = os.getenv("CEISA_USERNAME", "")
        self.password = os.getenv("CEISA_PASSWORD", "")

    @property
    def is_configured(self) -> bool:
        return bool(self.username and self.password)


# Singleton config instance
config = CeisaConfig()
