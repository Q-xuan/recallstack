"""LLM client for repowiki (OpenAI-compatible).

Some OpenAI-compatible hubs reject requests whose TLS fingerprint matches the
Python OpenSSL stack (returning 401 "invalid token" even with a valid key),
while accepting curl and node. To stay portable across such hubs this client
defaults to shelling out to ``curl`` when available (independent TLS stack) and
falls back to an in-process ``httpx`` call otherwise. Set
``REPOWIKI_LLM_TRANSPORT=httpx`` to force the in-process path.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import time
from collections.abc import AsyncGenerator

import httpx

logger = logging.getLogger(__name__)

_LAST_CALL_TS = 0.0
_CALL_LOCK: asyncio.Lock | None = None
_CURL_PATH: str | None | bool = False  # False = not probed yet


class _HttpError(RuntimeError):
    """an HTTP-level error from the LLM endpoint, carrying its status code."""

    def __init__(self, status: int, message: str):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


def _call_lock() -> asyncio.Lock:
    """lazy-init the throttle lock (avoid binding a loop at import time)."""
    global _CALL_LOCK
    if _CALL_LOCK is None:
        _CALL_LOCK = asyncio.Lock()
    return _CALL_LOCK


def _curl_available() -> str | None:
    """cached probe for a usable curl binary."""
    global _CURL_PATH
    if _CURL_PATH is False:
        _CURL_PATH = shutil.which("curl")
    return _CURL_PATH or None


def _wire_model(model: str) -> str:
    """strip a litellm-style provider prefix for the wire (``openai/x`` -> ``x``)."""
    return model.split("/", 1)[-1] if "/" in model else model


def _backoff(attempt: int) -> float:
    return min(8.0, 1.0 * (2 ** attempt))


class LLMClient:
    """async LLM client for OpenAI-compatible endpoints (curl-first, httpx fallback)."""

    def __init__(self, model: str, api_key: str = "", api_base: str = ""):
        self.model = model
        self.api_key = api_key
        self.api_base = (api_base or "").rstrip("/")
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0.0

    def _endpoint(self) -> str:
        return f"{self.api_base}/chat/completions"

    def _use_curl(self) -> bool:
        transport = os.getenv("REPOWIKI_LLM_TRANSPORT", "auto").lower()
        if transport == "httpx":
            return False
        if transport == "curl":
            return True
        # auto: prefer curl when present (sidesteps Python TLS-fingerprint blocking)
        return _curl_available() is not None

    async def _throttle(self) -> None:
        """serialize calls and enforce a minimum gap so strict-RPM hubs don't reject bursts."""
        global _LAST_CALL_TS
        min_interval = float(os.getenv("REPOWIKI_LLM_MIN_INTERVAL", "1.5"))
        async with _call_lock():
            elapsed = time.monotonic() - _LAST_CALL_TS
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)
            _LAST_CALL_TS = time.monotonic()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def _post(self, body: dict, timeout: float) -> dict:
        if self._use_curl():
            return await self._post_curl(body, timeout)
        return await self._post_httpx(body, timeout)

    async def _post_curl(self, body: dict, timeout: float) -> dict:
        curl = _curl_available()
        if not curl:
            return await self._post_httpx(body, timeout)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        cmd = [
            curl, "-s", "-S", "-m", str(int(timeout) + 5),
            "-X", "POST", self._endpoint(),
            "-H", f"Authorization: Bearer {self.api_key}",
            "-H", "Content-Type: application/json",
            "--data-binary", "@-",
        ]

        def _run() -> subprocess.CompletedProcess:
            return subprocess.run(
                cmd, input=payload, capture_output=True, timeout=timeout + 15
            )

        try:
            proc = await asyncio.to_thread(_run)
        except subprocess.TimeoutExpired as e:
            raise _HttpError(0, "curl timeout") from e

        if proc.returncode != 0:
            raise _HttpError(
                0, f"curl exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace').strip()[:200]}"
            )
        try:
            data = json.loads(proc.stdout)  # json.loads accepts bytes and decodes UTF-8
        except json.JSONDecodeError as e:
            raise _HttpError(0, f"non-JSON response: {proc.stdout[:200]!r}") from e
        if isinstance(data, dict) and "error" in data:
            err = data["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            # agnes (and similar) return auth failures as 200 + error body
            raise _HttpError(401, msg)
        return data

    async def _post_httpx(self, body: dict, timeout: float) -> dict:
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._endpoint(), headers=self._headers(), json=body)
        except (httpx.ConnectError, httpx.ReadError, httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            raise _HttpError(0, str(e)) from e
        if resp.status_code != 200:
            raise _HttpError(resp.status_code, resp.text[:200])
        return resp.json()

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> str:
        """non-streaming completion, returns the full response text."""
        await self._throttle()
        timeout = float(os.getenv("REPOWIKI_LLM_TIMEOUT_SECONDS", "90"))
        retries = int(os.getenv("REPOWIKI_LLM_MAX_RETRIES", "1"))

        body: dict = {
            "model": _wire_model(self.model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            body["response_format"] = response_format

        last_err: object = None
        for attempt in range(retries + 1):
            try:
                data = await self._post(body, timeout)
            except _HttpError as e:
                last_err = e
                # auth/forbidden errors won't recover through retry
                if e.status in (401, 403):
                    break
                if attempt < retries:
                    await asyncio.sleep(_backoff(attempt))
                continue

            usage = data.get("usage") or {}
            self.total_input_tokens += usage.get("prompt_tokens", 0) or 0
            self.total_output_tokens += usage.get("completion_tokens", 0) or 0
            choices = data.get("choices") or [{}]
            return (choices[0].get("message") or {}).get("content") or ""

        logger.error("LLM call failed: %s", last_err)
        return f"[LLM Error: {last_err}]"

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """streaming completion, yields text chunks (SSE) via httpx.

        Streaming is not on the wiki-generation path; it stays on httpx. Hubs
        that block Python TLS will fail here — use the non-streaming path.
        """
        await self._throttle()
        timeout = float(os.getenv("REPOWIKI_LLM_TIMEOUT_SECONDS", "90"))
        body: dict = {
            "model": _wire_model(self.model),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", self._endpoint(), headers=self._headers(), json=body) as resp:
                    if resp.status_code != 200:
                        logger.error("LLM stream HTTP %s", resp.status_code)
                        yield f"[LLM Error: HTTP {resp.status_code}]"
                        return
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices") or [{}]
                        delta = choices[0].get("delta") or {}
                        if delta.get("content"):
                            yield delta["content"]
        except Exception as e:  # noqa: BLE001
            logger.error("LLM stream failed: %s", e)
            yield f"[LLM Error: {e}]"
