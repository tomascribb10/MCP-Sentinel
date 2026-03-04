"""
sentinel_cli.client
====================
HTTP client for the sentinel-admin-api.

Reads configuration from environment variables:
  SENTINEL_API_URL   Admin API base URL (default: http://localhost:8001)
  SENTINEL_USER      Username for auto-login (optional)
  SENTINEL_PASSWORD  Password for auto-login (optional)

JWT token is cached in ~/.sentinel/token between sessions.
"""

import os
import pathlib
import sys

import httpx

TOKEN_FILE = pathlib.Path.home() / ".sentinel" / "token"
DEFAULT_API_URL = "http://localhost:8001"


class APIError(Exception):
    """Raised when the Admin API returns a non-2xx response."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"HTTP {status_code}: {detail}")


class AdminAPIClient:
    """Thin synchronous wrapper around the sentinel-admin-api REST endpoints."""

    def __init__(self, api_url: str | None = None) -> None:
        self.base_url = (
            api_url or os.environ.get("SENTINEL_API_URL", DEFAULT_API_URL)
        ).rstrip("/")
        self._token: str | None = self._load_token()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _load_token(self) -> str | None:
        if TOKEN_FILE.exists():
            return TOKEN_FILE.read_text().strip() or None
        return None

    def _save_token(self, token: str) -> None:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(token)

    def clear_token(self) -> None:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
        self._token = None

    def login(self, username: str, password: str) -> None:
        resp = httpx.post(
            f"{self.base_url}/auth/login",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        self._raise_for_status(resp)
        token = resp.json()["access_token"]
        self._save_token(token)
        self._token = token

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.is_success:
            return
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise APIError(resp.status_code, detail)

    def get(self, path: str, params: dict | None = None):
        resp = httpx.get(
            f"{self.base_url}{path}", headers=self._headers(), params=params
        )
        self._raise_for_status(resp)
        return resp.json()

    def post(self, path: str, data: dict | None = None):
        resp = httpx.post(
            f"{self.base_url}{path}", headers=self._headers(), json=data
        )
        self._raise_for_status(resp)
        if resp.status_code == 204:
            return {}
        return resp.json()

    def patch(self, path: str, data: dict):
        resp = httpx.patch(
            f"{self.base_url}{path}", headers=self._headers(), json=data
        )
        self._raise_for_status(resp)
        return resp.json()

    def delete(self, path: str) -> None:
        resp = httpx.delete(f"{self.base_url}{path}", headers=self._headers())
        self._raise_for_status(resp)
