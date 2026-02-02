"""DuckMail 邮箱服务客户端"""

import os
import random
import string
import time
import requests
from typing import Optional, Callable
from .env_loader import load_register_env

load_register_env()


class DuckMailClient:
    """DuckMail 邮箱服务客户端"""

    def __init__(
        self,
        base_url: str = "https://api.duckmail.sbs",
        api_key: str = "",
        proxy: str = "",
        verify_ssl: bool = True,
        log_callback: Optional[Callable] = None,
    ):
        """
        初始化 DuckMail 客户端

        Args:
            base_url: DuckMail API 地址
            api_key: API 密钥
            proxy: 代理地址
            verify_ssl: 是否验证 SSL
            log_callback: 日志回调函数
        """
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.proxies = {"http": proxy, "https": proxy} if proxy else None
        self.verify_ssl = verify_ssl
        self.log_callback = log_callback

        # 账户信息
        self.email: Optional[str] = None
        self.password: Optional[str] = None
        self.account_id: Optional[str] = None
        self.token: Optional[str] = None

    def _log(self, level: str, message: str) -> None:
        """记录日志"""
        if self.log_callback:
            try:
                self.log_callback(level, message)
            except Exception:
                pass

    def _request(self, method: str, url: str, **kwargs):
        """发送 HTTP 请求"""
        full_url = url if url.startswith("http") else f"{self.base_url}{url}"

        # 添加 API Key
        headers = kwargs.pop("headers", {})
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            res = requests.request(
                method,
                full_url,
                headers=headers,
                proxies=self.proxies,
                verify=self.verify_ssl,
                timeout=kwargs.pop("timeout", 15),
                **kwargs,
            )
            self._log("info", f"[{method}] {full_url} -> {res.status_code}")
            return res
        except Exception as e:
            self._log("error", f"请求失败: {e}")
            raise

    def get_available_domains(self) -> list:
        """
        获取可用的域名列表

        Returns:
            域名列表，如 ["duck.com", "mail.com"]
        """
        try:
            self._log("info", "正在获取可用域名...")
            res = self._request("GET", "/domains")

            if res.status_code == 200:
                data = res.json() if res.content else {}
                domains = data.get("hydra:member", [])
                domain_list = [d.get("domain") for d in domains if d.get("domain")]
                self._log("info", f"获取到 {len(domain_list)} 个可用域名")
                return domain_list
            else:
                self._log("error", f"获取域名失败: HTTP {res.status_code}")
                return []
        except Exception as e:
            self._log("error", f"获取域名异常: {e}")
            return []

    def register_account(self, domain: Optional[str] = None) -> bool:
        """
        注册新的邮箱账号

        Args:
            domain: 邮箱域名，如果为 None 则自动选择第一个可用域名

        Returns:
            是否注册成功
        """
        # 获取域名
        if not domain:
            domains = self.get_available_domains()
            if domains:
                domain = domains[0]
            else:
                domain = "duck.com"

        self._log("info", f"使用域名: {domain}")

        # 生成随机邮箱和密码
        rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        timestamp = str(int(time.time()))[-4:]
        self.email = f"t{timestamp}{rand}@{domain}"
        self.password = f"Pwd{rand}{timestamp}"

        self._log("info", f"生成邮箱: {self.email}")
        self._log("info", f"生成密码: {self.password}")

        try:
            self._log("info", "正在注册邮箱...")
            res = self._request(
                "POST",
                "/accounts",
                json={"address": self.email, "password": self.password}
            )

            if res.status_code in (200, 201):
                data = res.json() if res.content else {}
                self.account_id = data.get("id")
                self._log("info", f"✅ 注册成功! 账户ID: {self.account_id}")
                return True
            else:
                self._log("error", f"注册失败: HTTP {res.status_code}")
                return False
        except Exception as e:
            self._log("error", f"注册异常: {e}")
            return False

    def login(self) -> bool:
        """
        登录获取访问令牌

        Returns:
            是否登录成功
        """
        if not self.email or not self.password:
            self._log("error", "邮箱或密码未设置")
            return False

        try:
            self._log("info", f"正在登录: {self.email}")
            res = self._request(
                "POST",
                "/token",
                json={"address": self.email, "password": self.password}
            )

            if res.status_code == 200:
                data = res.json() if res.content else {}
                token = data.get("token")
                if token:
                    self.token = token
                    self._log("info", "✅ 登录成功")
                    return True
                else:
                    self._log("error", "响应中未找到 Token")
            else:
                self._log("error", f"登录失败: HTTP {res.status_code}")
                return False
        except Exception as e:
            self._log("error", f"登录异常: {e}")
            return False

    def get_messages(self, limit: int = 10) -> list:
        """
        获取邮件列表

        Args:
            limit: 最多获取的邮件数量

        Returns:
            邮件列表
        """
        if not self.token:
            if not self.login():
                return []

        try:
            self._log("info", f"[{self.email}] 正在获取邮件列表...")
            res = self._request(
                "GET",
                "/messages",
                headers={"Authorization": f"Bearer {self.token}"}
            )

            if res.status_code == 200:
                data = res.json() if res.content else {}
                messages = data.get("hydra:member", [])
                self._log("info", f"[{self.email}] 收到 {len(messages)} 封邮件")
                return messages[:limit]
            else:
                self._log("error", f"[{self.email}] 获取邮件失败: HTTP {res.status_code}")
                return []
        except Exception as e:
            self._log("error", f"[{self.email}] 获取邮件异常: {e}")
            return []

    def get_message_detail(self, message_id: str) -> dict:
        """
        获取单个邮件详情

        Args:
            message_id: 邮件ID

        Returns:
            邮件详情字典，失败返回空字典
        """
        if not self.token:
            if not self.login():
                return {}

        try:
            res = self._request(
                "GET",
                f"/messages/{message_id}",
                headers={"Authorization": f"Bearer {self.token}"}
            )

            if res.status_code == 200:
                return res.json() if res.content else {}
            else:
                self._log("error", f"[{self.email}] 获取邮件详情失败: HTTP {res.status_code}")
                return {}
        except Exception as e:
            self._log("error", f"[{self.email}] 获取邮件详情异常: {e}")
            return {}

    def get_verification_code(self, timeout: int = 120, interval: int = 5) -> Optional[str]:
        """
        轮询获取验证码

        Args:
            timeout: 超时时间（秒）
            interval: 轮询间隔（秒）

        Returns:
            验证码字符串，如果超时则返回 None
        """
        import re

        start_time = time.time()
        max_retries = timeout // interval

        self._log("info", f"[{self.email}] 开始轮询验证码 (超时 {timeout}秒)")

        for attempt in range(1, max_retries + 1):
            elapsed = int(time.time() - start_time)
            self._log("info", f"[{self.email}] [{elapsed}s] 第 {attempt}/{max_retries} 次检查...")

            messages = self.get_messages(limit=5)

            for idx, msg in enumerate(messages, 1):
                subject = msg.get("subject", "")

                # 打印完整的邮件结构（第一次）
                if idx == 1 and attempt == 1:
                    import json
                    self._log("info", f"[{self.email}] 邮件完整结构: {json.dumps(msg, indent=2, ensure_ascii=False)[:500]}")

                # 先尝试从列表中获取内容
                content = msg.get("text", "") or msg.get("html", "")

                # 如果列表中没有内容，尝试获取详情
                if not content:
                    message_id = msg.get("id", "")
                    if message_id:
                        detail = self.get_message_detail(message_id)
                        if detail:
                            content = detail.get("text", "") or detail.get("html", "")
                            if content:
                                self._log("info", f"[{self.email}] 从详情获取到内容，长度={len(content)}")

                # 记录邮件信息
                self._log("info", f"[{self.email}] 邮件 {idx}: 主题='{subject}', 内容长度={len(content)}")

                # 打印邮件内容前 200 字符用于调试
                if content:
                    preview = content[:200].replace('\n', ' ')
                    self._log("info", f"[{self.email}] 内容预览: {preview}...")

                # 查找验证码（格式: XXX-XXX，字母和数字混合）
                # xAI 验证码格式如: Y5J-7UN, HV8-LMR
                code_match = re.search(r'\b[A-Z0-9]{3}-[A-Z0-9]{3}\b', content)
                if code_match:
                    code = code_match.group()
                    self._log("info", f"[{self.email}] ✅ 找到验证码: {code}")
                    return code
                else:
                    self._log("info", f"[{self.email}] 邮件 {idx} 中未找到验证码")

            if attempt < max_retries:
                self._log("info", f"[{self.email}] 等待 {interval} 秒后重试...")
                time.sleep(interval)

        self._log("error", f"[{self.email}] 获取验证码超时 ({timeout}秒)")
        return None

    def test_connection(self) -> dict:
        """
        测试连接是否正常

        Returns:
            测试结果字典
        """
        result = {
            "success": False,
            "api_accessible": False,
            "domains_available": 0,
            "error": None
        }

        try:
            # 测试 API 可访问性
            res = self._request("GET", "/domains")
            result["api_accessible"] = res.status_code == 200

            if res.status_code == 200:
                domains = self.get_available_domains()
                result["domains_available"] = len(domains)
                result["success"] = len(domains) > 0

                if len(domains) == 0:
                    result["error"] = "没有可用域名"
            else:
                result["error"] = f"API 返回错误: HTTP {res.status_code}"
        except Exception as e:
            result["error"] = str(e)

        return result
