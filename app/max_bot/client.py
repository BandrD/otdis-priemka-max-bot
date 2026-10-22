from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.ssl_util import build_ssl_context

logger = logging.getLogger(__name__)

MAX_TEXT_LIMIT = 4000


class RateLimiter:
    """Простой token-bucket (~30 rps глобально)."""

    def __init__(self, rps: float = 25.0) -> None:
        self.rate = rps
        self.tokens = rps
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            while True:
                now = time.monotonic()
                self.tokens = min(self.rate, self.tokens + (now - self.last) * self.rate)
                self.last = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                await asyncio.sleep((1 - self.tokens) / self.rate)


class MaxClient:
    def __init__(
        self,
        token: str,
        base_url: str = "https://platform-api2.max.ru",
        ca_path: Path | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not token:
            raise ValueError("MAX_BOT_TOKEN пуст")
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._limiter = RateLimiter()
        ssl_ctx = build_ssl_context(ca_path)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": token},
            timeout=timeout,
            verify=ssl_ctx,
        )
        self._plain = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()
        await self._plain.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        await self._limiter.wait()
        resp = await self._client.request(method, path, params=params, json=json)
        if resp.status_code >= 400:
            logger.error("MAX API %s %s -> %s %s", method, path, resp.status_code, resp.text[:500])
            resp.raise_for_status()
        if not resp.content:
            return {}
        return resp.json()

    async def get_me(self) -> dict[str, Any]:
        return await self._request("GET", "/me")

    async def get_updates(
        self,
        marker: int | None = None,
        *,
        limit: int = 100,
        timeout: int = 30,
        types: str | None = None,
    ) -> tuple[list[dict[str, Any]], int | None]:
        params: dict[str, Any] = {"limit": limit, "timeout": timeout}
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = types
        data = await self._request("GET", "/updates", params=params)
        updates = data.get("updates") or []
        return updates, data.get("marker")

    async def send_message(
        self,
        *,
        chat_id: int | None = None,
        user_id: int | None = None,
        text: str | None = None,
        format: str | None = "markdown",
        attachments: list[dict[str, Any]] | None = None,
        notify: bool = True,
        disable_link_preview: bool = False,
    ) -> dict[str, Any]:
        if chat_id is None and user_id is None:
            raise ValueError("нужен chat_id или user_id")
        params: dict[str, Any] = {"disable_link_preview": str(disable_link_preview).lower()}
        if chat_id is not None:
            params["chat_id"] = chat_id
        if user_id is not None:
            params["user_id"] = user_id
        body: dict[str, Any] = {"notify": notify}
        if text is not None:
            body["text"] = text[:MAX_TEXT_LIMIT]
        if format:
            body["format"] = format
        if attachments is not None:
            body["attachments"] = attachments
        return await self._request("POST", "/messages", params=params, json=body)

    async def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if notification is not None:
            body["notification"] = notification
        if message is not None:
            body["message"] = message
        return await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json=body or {"notification": "OK"},
        )
