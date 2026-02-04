"""代理池管理器 - 从URL动态获取代理IP"""

import asyncio
import aiohttp
import time
from typing import Optional, List
from app.core.logger import logger
from app.core.proxy_secret import KdlSecretProxy


class ProxyPool:
    """代理池管理器"""
    
    def __init__(self):
        self._pool_url: Optional[str] = None
        self._static_proxy: Optional[str] = None
        self._current_proxy: Optional[str] = None
        self._last_fetch_time: float = 0
        self._fetch_interval: int = 300  # 5分钟刷新一次
        self._enabled: bool = False
        self._lock = asyncio.Lock()
        self._secret_provider: Optional[KdlSecretProxy] = None
        self._pool_scheme: str = "https"
        self._pool_username: str = ""
        self._pool_password: str = ""
    
    def configure(
        self,
        proxy_url: str,
        proxy_pool_url: str = "",
        proxy_pool_interval: int = 300,
        proxy_pool_scheme: str = "https",
        proxy_pool_username: str = "",
        proxy_pool_password: str = "",
    ):
        """配置代理池
        
        Args:
            proxy_url: 静态代理URL（socks5h://xxx 或 http://xxx）
            proxy_pool_url: 代理池API URL，返回单个代理地址
            proxy_pool_interval: 代理池刷新间隔（秒）
            proxy_pool_scheme: 代理池返回ip:port时使用的协议
            proxy_pool_username: 代理池鉴权用户名
            proxy_pool_password: 代理池鉴权密码
        """
        self._secret_provider = KdlSecretProxy.from_url(proxy_url) if proxy_url else None
        self._static_proxy = None if self._secret_provider else (self._normalize_proxy(proxy_url) if proxy_url else None)
        self._pool_scheme = (proxy_pool_scheme or "https").strip().lower()
        if self._pool_scheme == "socks5":
            self._pool_scheme = "socks5h"
        self._pool_username = (proxy_pool_username or "").strip()
        self._pool_password = (proxy_pool_password or "").strip()
        pool_url = proxy_pool_url.strip() if proxy_pool_url else None
        if pool_url and self._looks_like_proxy_url(pool_url):
            normalized_proxy = self._normalize_proxy(pool_url)
            if not self._static_proxy:
                self._static_proxy = normalized_proxy
                logger.warning("[ProxyPool] proxy_pool_url看起来是代理地址，已作为静态代理使用，请改用proxy_url")
            else:
                logger.warning("[ProxyPool] proxy_pool_url看起来是代理地址，已忽略（使用proxy_url）")
            pool_url = None
        self._pool_url = pool_url
        self._fetch_interval = proxy_pool_interval
        self._enabled = bool(self._pool_url)
        
        if self._enabled:
            logger.info(f"[ProxyPool] 代理池已启用: {self._pool_url}, 刷新间隔: {self._fetch_interval}s")
        elif self._secret_provider or self._static_proxy:
            if self._secret_provider:
                logger.info("[ProxyPool] 使用KDL动态代理")
            else:
                logger.info(f"[ProxyPool] 使用静态代理: {self._static_proxy}")
            self._current_proxy = self._static_proxy
        else:
            logger.info("[ProxyPool] 未配置代理")
    
    async def get_proxy(self) -> Optional[str]:
        """获取代理地址
        
        Returns:
            代理URL或None
        """
        # 如果未启用代理池，返回静态代理
        if not self._enabled:
            return await self._get_static_proxy()
        
        # 检查是否需要刷新
        now = time.time()
        if not self._current_proxy or (now - self._last_fetch_time) >= self._fetch_interval:
            async with self._lock:
                # 双重检查
                if not self._current_proxy or (now - self._last_fetch_time) >= self._fetch_interval:
                    await self._fetch_proxy()
        
        return self._current_proxy
    
    async def force_refresh(self) -> Optional[str]:
        """强制刷新代理（用于403错误重试）
        
        Returns:
            新的代理URL或None
        """
        if not self._enabled:
            if self._secret_provider:
                return await self._secret_provider.force_refresh()
            return self._static_proxy
        
        async with self._lock:
            await self._fetch_proxy()
        
        return self._current_proxy
    
    async def _fetch_proxy(self):
        """从代理池URL获取新的代理"""
        try:
            logger.debug(f"[ProxyPool] 正在从代理池获取新代理: {self._pool_url}")
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self._pool_url) as response:
                    if response.status == 200:
                        proxy_text = await response.text()
                        proxy = self._normalize_proxy(proxy_text.strip())
                        if not self._validate_proxy(proxy):
                            proxy = self._build_pool_proxy(proxy)
                        
                        # 验证代理格式
                        if self._validate_proxy(proxy):
                            self._current_proxy = proxy
                            self._last_fetch_time = time.time()
                            logger.info(f"[ProxyPool] 成功获取新代理: {proxy}")
                        else:
                            logger.error(f"[ProxyPool] 代理格式无效: {proxy}")
                            # 降级到静态代理
                            if not self._current_proxy:
                                self._current_proxy = await self._get_static_proxy()
                    else:
                        logger.error(f"[ProxyPool] 获取代理失败: HTTP {response.status}")
                        # 降级到静态代理
                        if not self._current_proxy:
                            self._current_proxy = await self._get_static_proxy()
        
        except asyncio.TimeoutError:
            logger.error("[ProxyPool] 获取代理超时")
            if not self._current_proxy:
                self._current_proxy = await self._get_static_proxy()
        
        except Exception as e:
            logger.error(f"[ProxyPool] 获取代理异常: {e}")
            # 降级到静态代理
            if not self._current_proxy:
                self._current_proxy = await self._get_static_proxy()
    
    def _validate_proxy(self, proxy: str) -> bool:
        """验证代理格式
        
        Args:
            proxy: 代理URL
        
        Returns:
            是否有效
        """
        if not proxy:
            return False
        
        # 支持的协议
        valid_protocols = ['http://', 'https://', 'socks5://', 'socks5h://']
        
        return any(proxy.startswith(proto) for proto in valid_protocols)

    def _normalize_proxy(self, proxy: str) -> str:
        """标准化代理URL（sock5/socks5 → socks5h://）"""
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

    def _looks_like_proxy_url(self, url: str) -> bool:
        """判断URL是否像代理地址（避免误把代理池API当代理）"""
        return url.startswith(("sock5://", "sock5h://", "socks5://", "socks5h://"))

    def _build_pool_proxy(self, proxy_text: str) -> str:
        """将代理池返回的ip:port拼成完整代理URL"""
        raw = (proxy_text or "").strip()
        if not raw:
            return raw
        if raw.startswith(("http://", "https://", "socks5://", "socks5h://")):
            return raw
        if ":" not in raw:
            return raw
        auth = ""
        if self._pool_username or self._pool_password:
            auth = f"{self._pool_username}:{self._pool_password}@"
        scheme = self._pool_scheme or "https"
        return f"{scheme}://{auth}{raw}"

    async def _get_static_proxy(self) -> Optional[str]:
        if self._secret_provider:
            return await self._secret_provider.get_proxy()
        return self._static_proxy
    
    def get_current_proxy(self) -> Optional[str]:
        """获取当前使用的代理（同步方法）
        
        Returns:
            当前代理URL或None
        """
        return self._current_proxy or self._static_proxy


# 全局代理池实例
proxy_pool = ProxyPool()
