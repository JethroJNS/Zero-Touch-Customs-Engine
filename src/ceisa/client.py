"""
CEISA 4.0 API Client.

Provides high-level methods for submitting documents and checking status.
"""
import logging
from typing import Any, Dict, Optional
import httpx

from .config import config
from .auth import get_auth, CeisaAuth
from .mapper import CeisaMapper

logger = logging.getLogger("ceisa")


class CeisaAPIError(Exception):
    """Raised when CEISA API returns an error."""

    def __init__(self, status: str, message: Any, response_data: Optional[Dict] = None):
        self.status = status
        self.message = message
        self.response_data = response_data
        super().__init__(f"CEISA API error [{status}]: {message}")


class CeisaSubmissionResult:
    """Result of a CEISA document submission."""

    def __init__(
        self,
        success: bool,
        id_header: Optional[str] = None,
        status: Optional[str] = None,
        message: Optional[str] = None,
        raw_response: Optional[Dict] = None,
        document_json: Optional[Dict] = None,
    ):
        self.success = success
        self.id_header = id_header  # UUID from CEISA on success
        self.status = status
        self.message = message
        self.raw_response = raw_response or {}
        self.document_json = document_json or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "id_header": self.id_header,
            "status": self.status,
            "message": self.message,
            "raw_response": self.raw_response,
        }


class CeisaClient:
    """
    High-level CEISA 4.0 API client.

    Usage:
        client = CeisaClient()

        # Submit a document
        result = await client.submit_document(
            entities=shipment_entities,
            shipment_id="CD-ABC12345",
        )

        # Check submission status
        status = await client.get_status(result.id_header)

    Environment:
        Set CEISA_ENV=prod for production.
        Set CEISA_USERNAME and CEISA_PASSWORD in .env.
    """

    def __init__(self):
        self.cfg = config
        self._mapper = CeisaMapper()
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()

    # ── Document Submission ─────────────────────────────────────────────────

    async def submit_document(
        self,
        entities,
        shipment_id: Optional[str] = None,
        document_override: Optional[Dict] = None,
    ) -> CeisaSubmissionResult:
        """
        Submit a PIB/PEB document to CEISA API.

        Args:
            entities: ShipmentEntities from the OCR extraction engine.
            shipment_id: Optional reference for logging.
            document_override: Optional CEISA JSON dict (bypasses mapper).

        Returns:
            CeisaSubmissionResult with id_header on success.

        Raises:
            CeisaAPIError: If API returns non-OK status.
            httpx.HTTPStatusError: On network errors.
        """
        if not self.cfg.is_configured:
            return CeisaSubmissionResult(
                success=False,
                status="error",
                message="CEISA credentials not configured. "
                        "Set CEISA_USERNAME and CEISA_PASSWORD in .env file.",
            )

        # Build CEISA JSON document
        if document_override:
            doc_json = document_override
        else:
            doc_json = self._mapper.map_document(entities)

        logger.info(
            f"CEISA submit: nomorAju={doc_json.get('nomorAju', 'N/A')}, "
            f"items={len(doc_json.get('barang', []))}, "
            f"shipment={shipment_id}"
        )

        try:
            return await self._send_document(doc_json)
        except CeisaAPIError:
            raise
        except Exception as exc:
            logger.error(f"CEISA submission failed: {exc}")
            raise

    async def _send_document(self, doc_json: Dict) -> CeisaSubmissionResult:
        """Send the document JSON to CEISA API."""
        auth = await get_auth()
        headers = await auth.get_auth_header()
        headers["Content-Type"] = "application/json"

        logger.info(f"CEISA POST {self.cfg.document_url}")
        response = await self._client.post(
            self.cfg.document_url,
            json=doc_json,
            headers=headers,
        )

        # Handle non-2xx as error
        if response.status_code >= 400:
            try:
                error_body = response.json()
            except Exception:
                error_body = {"raw": response.text}

            raise CeisaAPIError(
                status="HTTP",
                message=f"HTTP {response.status_code}: {response.text[:200]}",
                response_data=error_body,
            )

        data = response.json()
        status = data.get("status", "")
        message = data.get("message", "")
        id_header = data.get("idHeader") or data.get("id_header")

        if status in ("OK", "SUCCESS", "success"):
            logger.info(f"CEISA submission OK: idHeader={id_header}")
            return CeisaSubmissionResult(
                success=True,
                id_header=id_header,
                status=status,
                message=message,
                raw_response=data,
                document_json=doc_json,
            )
        else:
            # Parse error messages from validation failures
            logger.warning(f"CEISA submission returned: {status} — {message}")
            return CeisaSubmissionResult(
                success=False,
                id_header=id_header,
                status=status,
                message=message,
                raw_response=data,
                document_json=doc_json,
            )

    # ── Status Check ────────────────────────────────────────────────────────

    async def get_status(self, id_header: str) -> Dict[str, Any]:
        """
        Get the status of a submitted document.

        Args:
            id_header: The UUID returned from submit_document().

        Returns:
            Status response dict from CEISA API.
        """
        if not id_header:
            raise ValueError("id_header is required")

        auth = await get_auth()
        headers = await auth.get_auth_header()

        status_url = f"{self.cfg.api_base_url}/document/{id_header}"
        logger.info(f"CEISA GET {status_url}")

        response = await self._client.get(status_url, headers=headers)
        response.raise_for_status()

        return response.json()

    # ── Validation ──────────────────────────────────────────────────────────

    async def validate_document(self, entities) -> CeisaSubmissionResult:
        """
        Validate a document (without actually submitting).

        Same as submit_document but intended for pre-submission checks.
        Returns result without persisting to CEISA.
        """
        doc_json = self._mapper.map_document(entities)
        logger.info(f"CEISA validate: nomorAju={doc_json.get('nomorAju', 'N/A')}")

        try:
            return await self._send_document(doc_json)
        except CeisaAPIError:
            raise
        except Exception as exc:
            logger.error(f"CEISA validation failed: {exc}")
            raise

    # ── Builder ──────────────────────────────────────────────────────────────

    def build_document(self, entities) -> Dict[str, Any]:
        """
        Build the CEISA JSON document without sending.

        Useful for preview before actual submission.
        """
        return self._mapper.map_document(entities)
