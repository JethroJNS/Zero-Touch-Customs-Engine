import logging
from typing import Any, Dict, Optional
import httpx

from .config import config
from .auth import get_auth, CeisaAuth
from .mapper import CeisaMapper

logger = logging.getLogger("ceisa")


class CeisaAPIError(Exception):
    # Exception saat CEISA API returns error.

    def __init__(self, status: str, message: Any, response_data: Optional[Dict] = None):
        self.status = status
        self.message = message
        self.response_data = response_data
        super().__init__(f"CEISA API error [{status}]: {message}")


class CeisaSubmissionResult:
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
        self.id_header = id_header
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

    # Document Submission

    async def submit_document(
        self,
        entities,
        shipment_id: Optional[str] = None,
        document_override: Optional[Dict] = None,
    ) -> CeisaSubmissionResult:
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
        # Kirim document JSON ke CEISA API.
        auth = await get_auth()
        headers = await auth.get_auth_header()
        headers["Content-Type"] = "application/json"

        logger.info(f"CEISA POST {self.cfg.document_url}")
        response = await self._client.post(
            self.cfg.document_url,
            json=doc_json,
            headers=headers,
        )

        # Handle non-2xx sebagai error
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
            # Parse error messages dari validation failures
            logger.warning(f"CEISA submission returned: {status} — {message}")
            return CeisaSubmissionResult(
                success=False,
                id_header=id_header,
                status=status,
                message=message,
                raw_response=data,
                document_json=doc_json,
            )

    # Status Check

    async def get_status(self, id_header: str) -> Dict[str, Any]:
        if not id_header:
            raise ValueError("id_header is required")

        auth = await get_auth()
        headers = await auth.get_auth_header()

        status_url = f"{self.cfg.api_base_url}/document/{id_header}"
        logger.info(f"CEISA GET {status_url}")

        response = await self._client.get(status_url, headers=headers)
        response.raise_for_status()

        return response.json()

    # Validation

    async def validate_document(self, entities) -> CeisaSubmissionResult:
        # Validasi dokumen tanpa submit.
        doc_json = self._mapper.map_document(entities)
        logger.info(f"CEISA validate: nomorAju={doc_json.get('nomorAju', 'N/A')}")

        try:
            return await self._send_document(doc_json)
        except CeisaAPIError:
            raise
        except Exception as exc:
            logger.error(f"CEISA validation failed: {exc}")
            raise

    # Builder

    def build_document(self, entities) -> Dict[str, Any]:
        return self._mapper.map_document(entities)
