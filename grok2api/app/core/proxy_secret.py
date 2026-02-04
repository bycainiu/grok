"""KDL secret token proxy helper."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import aiohttp

from app.core.logger import logger


DEFAULT_KDL_API = "https://auth.kdlapi.com/api/get_secret_token"
DEFAULT_TOKEN_REFRESH_BUFFER = 3 * 60


@dataclass
class KdlSecretConfig:
    secret_id: str
    secret_key: str
    host: str
    port: int
    scheme: str = "http"
    api_url: str = DEFAULT_KDL_API


class KdlSecretProxy:
    """Resolve KDL secret token into proxy url with caching."""

    def __init__(self, config: KdlSecretConfig, cache_path: Optional[Path] = None) -> None:
        self._config = config
        self._cache_path = cache_path or (Path(__file__).parents[2] / "data" / "kdl_secret.json")
        self._secret_token: Optional[str] = None
        self._expire_seconds: float = 0.0
        self._issued_at: float = 0.0
        self._load_cache()

    @classmethod
    def from_url(cls, raw_url: str) -> Optional["KdlSecretProxy"]:
        """Parse kdl://secret_id:secret_key@host:port?scheme=http."""
        if not raw_url or not raw_url.startswith("kdl://"):
            return None

        parsed = urlparse(raw_url)
        if not parsed.username or not parsed.password or not parsed.hostname or not parsed.port:
            logger.warning("[Proxy] kdl url missing username/password/host/port")
            return None

        query = parse_qs(parsed.query or "")
        scheme = (query.get("scheme", ["http"])[0] or "http").lower()
        if scheme == "socks5":
            scheme = "socks5h"
        if scheme not in ("http", "https", "socks5", "socks5h"):
            logger.warning(f"[Proxy] kdl url unsupported scheme: {scheme}")
            return None

        config = KdlSecretConfig(
            secret_id=parsed.username,
            secret_key=parsed.password,
            host=parsed.hostname,
            port=int(parsed.port),
            scheme=scheme,
        )
        return cls(config)

    async def get_proxy(self) -> Optional[str]:
        if self._is_token_valid():
            return self._build_proxy_url(self._secret_token)
        await self._refresh_token()
        if not self._secret_token:
            return None
        return self._build_proxy_url(self._secret_token)

    async def force_refresh(self) -> Optional[str]:
        await self._refresh_token(force=True)
        if not self._secret_token:
            return None
        return self._build_proxy_url(self._secret_token)

    def _build_proxy_url(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        return f"{self._config.scheme}://{self._config.secret_id}:{token}@{self._config.host}:{self._config.port}"

    def _is_token_valid(self) -> bool:
        if not self._secret_token or not self._issued_at or not self._expire_seconds:
            return False
        now = time.time()
        return (self._issued_at + self._expire_seconds - DEFAULT_TOKEN_REFRESH_BUFFER) > now

    def _load_cache(self) -> None:
        try:
            if not self._cache_path.exists():
                return
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            if data.get("secret_id") != self._config.secret_id:
                return
            self._secret_token = data.get("secret_token") or None
            self._expire_seconds = float(data.get("expire") or 0.0)
            self._issued_at = float(data.get("issued_at") or 0.0)
        except Exception as e:
            logger.warning(f"[Proxy] failed to load kdl cache: {e}")

    def _save_cache(self) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "secret_id": self._config.secret_id,
                "secret_token": self._secret_token,
                "expire": self._expire_seconds,
                "issued_at": self._issued_at,
            }
            self._cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except Exception as e:
            logger.warning(f"[Proxy] failed to save kdl cache: {e}")

    async def _refresh_token(self, force: bool = False) -> None:
        if not force and self._is_token_valid():
            return

        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(
                    self._config.api_url,
                    data={"secret_id": self._config.secret_id, "secret_key": self._config.secret_key},
                ) as response:
                    if response.status != 200:
                        raise RuntimeError(f"HTTP {response.status}")
                    data = await response.json()
        except Exception as e:
            logger.error(f"[Proxy] kdl token fetch failed: {e}")
            return

        try:
            if data.get("code") != 0:
                raise RuntimeError(data.get("msg") or "unknown error")
            token = data["data"]["secret_token"]
            expire = float(data["data"]["expire"])
            self._secret_token = token
            self._expire_seconds = expire
            self._issued_at = time.time()
            self._save_cache()
        except Exception as e:
            logger.error(f"[Proxy] kdl token parse failed: {e}")
            return
