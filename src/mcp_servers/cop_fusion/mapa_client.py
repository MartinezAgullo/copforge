"""
Mapa Client - HTTP client for mapa-puntos-interes API.
"""

import logging
import time
from typing import Any, cast

import requests

from src.core.telemetry import get_tracer, traced_operation

logger = logging.getLogger(__name__)
tracer = get_tracer("copforge.mcp.cop_fusion.mapa_client")


class MapaClientError(Exception):
    """Exception raised for Mapa API errors."""


class MapaClient:
    """HTTP client for mapa-puntos-interes REST API."""

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        timeout: int = 5,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/puntos"
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update(
            {"Content-Type": "application/json", "User-Agent": "CopForge/1.0"}
        )

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last_exception: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = self.session.request(
                    method=method, url=url, timeout=self.timeout, **kwargs
                )
                response.raise_for_status()
                return response
            except requests.exceptions.Timeout as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))
            except requests.exceptions.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise MapaClientError(f"Client error: {e.response.status_code}") from e
                last_exception = e
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2**attempt))
        raise MapaClientError(f"All {self.max_retries} attempts failed: {last_exception}")

    def health_check(self) -> tuple[bool, str]:
        with traced_operation(tracer, "mapa_health_check"):
            try:
                response = self._request_with_retry("GET", f"{self.base_url}/health")
                data = response.json()
                return True, f"Server OK - Uptime: {data.get('uptime', 'unknown')}s"
            except Exception as e:
                return False, f"Server unreachable: {e!s}"

    def get_all_puntos(self) -> list[dict[str, Any]]:
        with traced_operation(tracer, "mapa_get_all_puntos") as span:
            try:
                response = self._request_with_retry("GET", self.api_url)
                data = cast(dict[str, Any], response.json())
                puntos = cast(list[dict[str, Any]], data.get("data", []))
                span.set_attribute("mapa.puntos_count", len(puntos))
                return puntos
            except Exception as e:
                raise MapaClientError(f"Failed to get puntos: {e!s}") from e

    def find_by_elemento_identificado(self, elemento_id: str) -> dict[str, Any] | None:
        with traced_operation(tracer, "mapa_find_by_elemento", {"elemento_id": elemento_id}):
            try:
                all_puntos = self.get_all_puntos()
                for punto in all_puntos:
                    if punto.get("elemento_identificado") == elemento_id:
                        return punto
                return None
            except Exception as e:
                raise MapaClientError(f"Failed to find punto: {e!s}") from e

    def create_punto(self, punto_data: dict[str, Any]) -> dict[str, Any]:
        with traced_operation(tracer, "mapa_create_punto") as span:
            try:
                response = self._request_with_retry("POST", self.api_url, json=punto_data)
                data = cast(dict[str, Any], response.json())
                if not data.get("success"):
                    raise MapaClientError(f"Server returned success=false: {data.get('message')}")
                created = cast(dict[str, Any], data.get("data"))
                span.set_attribute("mapa.punto_id", created.get("id") if created else None)
                return created
            except Exception as e:
                raise MapaClientError(f"Failed to create punto: {e!s}") from e

    def update_punto(self, punto_id: int, punto_data: dict[str, Any]) -> dict[str, Any]:
        with traced_operation(tracer, "mapa_update_punto", {"punto_id": punto_id}):
            try:
                response = self._request_with_retry(
                    "PUT", f"{self.api_url}/{punto_id}", json=punto_data
                )
                data = cast(dict[str, Any], response.json())
                if not data.get("success"):
                    raise MapaClientError(f"Server returned success=false: {data.get('message')}")
                return cast(dict[str, Any], data.get("data"))
            except Exception as e:
                raise MapaClientError(f"Failed to update punto: {e!s}") from e

    def delete_punto(self, punto_id: int) -> bool:
        with traced_operation(tracer, "mapa_delete_punto", {"punto_id": punto_id}):
            try:
                response = self._request_with_retry("DELETE", f"{self.api_url}/{punto_id}")
                data = cast(dict[str, Any], response.json())
                return cast(bool, data.get("success", False))
            except Exception as e:
                raise MapaClientError(f"Failed to delete punto: {e!s}") from e

    def upsert_punto(self, punto_data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with traced_operation(tracer, "mapa_upsert_punto") as span:
            elemento_id = punto_data.get("elemento_identificado")
            if not elemento_id:
                raise MapaClientError("punto_data must include 'elemento_identificado'")
            existing = self.find_by_elemento_identificado(elemento_id)
            if existing:
                punto_id = existing["id"]
                update_data = punto_data.copy()
                for key in ["elemento_identificado", "tipo_elemento", "nombre", "created_at"]:
                    update_data.pop(key, None)
                updated = self.update_punto(punto_id, update_data)
                span.set_attribute("mapa.action", "updated")
                return updated, False
            else:
                created = self.create_punto(punto_data)
                span.set_attribute("mapa.action", "created")
                return created, True

    def batch_upsert(self, puntos_data: list[dict[str, Any]]) -> dict[str, Any]:
        with traced_operation(tracer, "mapa_batch_upsert", {"count": len(puntos_data)}) as span:
            stats: dict[str, Any] = {"created": 0, "updated": 0, "failed": 0, "errors": []}
            for punto_data in puntos_data:
                try:
                    _, was_created = self.upsert_punto(punto_data)
                    if was_created:
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1
                except Exception as e:
                    stats["failed"] += 1
                    elemento_id = punto_data.get("elemento_identificado", "unknown")
                    stats["errors"].append(f"{elemento_id}: {e!s}")
            span.set_attribute("mapa.created", stats["created"])
            span.set_attribute("mapa.updated", stats["updated"])
            return stats

    def close(self) -> None:
        self.session.close()


_mapa_client: MapaClient | None = None


def get_mapa_client(base_url: str = "http://localhost:3000", force_new: bool = False) -> MapaClient:
    global _mapa_client
    if _mapa_client is None or force_new:
        _mapa_client = MapaClient(base_url=base_url)
    return _mapa_client


def reset_mapa_client() -> None:
    global _mapa_client
    if _mapa_client is not None:
        _mapa_client.close()
        _mapa_client = None
