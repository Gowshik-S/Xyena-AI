from typing import Any

import httpx

from .settings import get_settings


class GSTIntegrationError(RuntimeError):
    pass


class GSTClient:
    async def fetch_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        settings = get_settings()
        if settings.gst_base_url is None or settings.gst_service_token is None:
            return None
        headers = {
            "Authorization": f"Bearer {settings.gst_service_token.get_secret_value()}"
        }
        try:
            async with httpx.AsyncClient(
                base_url=settings.gst_base_url.rstrip("/"),
                headers=headers,
                timeout=20,
            ) as client:
                response = await client.get(f"/api/v1/invoices/{invoice_id}")
                response.raise_for_status()
                value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GSTIntegrationError("Could not fetch the authoritative GST invoice.") from exc
        if not isinstance(value, dict):
            raise GSTIntegrationError("GST invoice API returned an invalid document.")
        return value


gst_client = GSTClient()
