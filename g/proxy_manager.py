"""Proxy manager for register workflow."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests

from .env_loader import load_register_env

DEFAULT_KDL_API = "https://auth.kdlapi.com/api/get_secret_token"
TOKEN_REFRESH_BUFFER = 3 * 60
SECRET_PATH = Path(__file__).resolve().parents[1] / ".secret"

load_register_env()


def get_proxy_url() -> str:
    """Resolve proxy url from env (direct or KDL secret)."""
    proxy_url = os.getenv("PROXY_URL", "").strip()
    if proxy_url:
        return _resolve_proxy_url(proxy_url) or ""

    secret_id = os.getenv("PROXY_SECRET_ID", "").strip()
    secret_key = os.getenv("PROXY_SECRET_KEY", "").strip()
    host = os.getenv("PROXY_HOST", "").strip()
    port = os.getenv("PROXY_PORT", "").strip()
    scheme = (os.getenv("PROXY_SCHEME", "http") or "http").strip().lower()
    if secret_id and secret_key and host and port:
        return _build_kdl_proxy(secret_id, secret_key, host, port, scheme) or ""

    return ""


def _resolve_proxy_url(proxy_url: str) -> Optional[str]:
    proxy_url = proxy_url.strip()
    if proxy_url.startswith("kdl://"):
        return _parse_kdl_url(proxy_url)
    return _normalize_proxy(proxy_url)


def _normalize_proxy(proxy: str) -> str:
    if not proxy:
        return proxy
    proxy = proxy.strip()
    if proxy.startswith("sock5h://"):
        proxy = proxy.replace("sock5h://", "socks5h://", 1)
    if proxy.startswith("sock5://"):
        proxy = proxy.replace("sock5://", "socks5://", 1)
    if proxy.startswith("socks5://"):
        return proxy.replace("socks5://", "socks5h://", 1)
    return proxy


def _parse_kdl_url(raw_url: str) -> Optional[str]:
    parsed = urlparse(raw_url)
    if not parsed.username or not parsed.password or not parsed.hostname or not parsed.port:
        return None
    query = parse_qs(parsed.query or "")
    scheme = (query.get("scheme", ["http"])[0] or "http").lower()
    return _build_kdl_proxy(parsed.username, parsed.password, parsed.hostname, parsed.port, scheme)


def _build_kdl_proxy(secret_id: str, secret_key: str, host: str, port: str, scheme: str) -> Optional[str]:
    if scheme == "socks5":
        scheme = "socks5h"
    if scheme not in ("http", "https", "socks5", "socks5h"):
        scheme = "http"

    token = _get_secret_token_cached(secret_id, secret_key)
    if not token:
        return None
    return f"{scheme}://{secret_id}:{token}@{host}:{port}"


def _get_secret_token_cached(secret_id: str, secret_key: str) -> Optional[str]:
    cached = _read_secret_cache()
    if cached and cached.get("secret_id") == secret_id:
        issued_at = float(cached.get("issued_at") or 0.0)
        expire = float(cached.get("expire") or 0.0)
        token = cached.get("secret_token") or ""
        if token and (issued_at + expire - TOKEN_REFRESH_BUFFER) > time.time():
            return token

    token, expire = _fetch_secret_token(secret_id, secret_key)
    if not token:
        return None
    _save_secret_cache(secret_id, token, expire)
    return token


def _fetch_secret_token(secret_id: str, secret_key: str) -> tuple[Optional[str], float]:
    try:
        response = requests.post(
            DEFAULT_KDL_API,
            data={"secret_id": secret_id, "secret_key": secret_key},
            timeout=10,
        )
        if response.status_code != 200:
            return None, 0.0
        data = response.json()
        if data.get("code") != 0:
            return None, 0.0
        token = data["data"]["secret_token"]
        expire = float(data["data"]["expire"])
        return token, expire
    except Exception:
        return None, 0.0


def _read_secret_cache() -> Optional[dict]:
    try:
        if not SECRET_PATH.exists():
            return None
        return json.loads(SECRET_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_secret_cache(secret_id: str, token: str, expire: float) -> None:
    try:
        payload = {
            "secret_id": secret_id,
            "secret_token": token,
            "expire": expire,
            "issued_at": time.time(),
        }
        SECRET_PATH.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass
