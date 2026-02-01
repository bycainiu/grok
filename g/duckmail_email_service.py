"""
DuckMail 邮箱服务类
提供与 EmailService 相同的接口，用于注册机
"""
import os
import re
import time
from dotenv import load_dotenv
from .duckmail_client import DuckMailClient


class DuckMailEmailService:
    """DuckMail 邮箱服务类"""

    def __init__(self):
        """初始化 DuckMail 邮箱服务"""
        load_dotenv()

        self.base_url = os.getenv("DUCKMAIL_BASE_URL", "https://api.duckmail.sbs")
        self.api_key = os.getenv("DUCKMAIL_API_KEY", "")
        self.email_domain = os.getenv("EMAIL_DOMAIN", "")

        if not self.email_domain:
            raise ValueError("Missing required environment variable: EMAIL_DOMAIN")

        # 初始化 DuckMail 客户端
        self.client = DuckMailClient(
            base_url=self.base_url,
            api_key=self.api_key
        )

        # 当前线程使用的邮箱和 token
        self.current_email = None
        self.current_password = None
        self.current_token = None

    def create_email(self):
        """
        创建临时邮箱（使用 DuckMail 注册账号）

        Returns:
            tuple: (token, email_address)
                - token: 登录后的访问令牌
                - email_address: 注册的邮箱地址
        """
        try:
            # 使用 DuckMail 注册账号
            success = self.client.register_account(domain=self.email_domain)

            if not success:
                return None, None

            # 登录获取 token
            login_success = self.client.login()
            if not login_success:
                return None, None

            # 保存当前线程的邮箱信息
            self.current_email = self.client.email
            self.current_password = self.client.password
            self.current_token = self.client.token

            # 返回 token 和 email（与 EmailService 接口一致）
            return self.current_token, self.current_email

        except Exception as e:
            print(f"[-] DuckMail 创建邮箱失败: {e}")
            return None, None

    def fetch_first_email(self, token):
        """
        获取第一封邮件内容（验证码邮件）

        Args:
            token: 登录时获取的访问令牌

        Returns:
            str: 邮件原始内容，格式与 Worker 邮箱兼容，如果获取失败返回 None
        """
        try:
            # 使用客户端的 token（如果传入了新 token 则更新）
            if token and token != self.current_token:
                self.current_token = token
                self.client.token = token

            # 轮询获取验证码（DuckMail 返回 6 位纯数字）
            verify_code = self.client.get_verification_code(timeout=120, interval=3)

            if verify_code:
                # 格式化为 XXX-XXX 格式，与 Worker 邮箱兼容
                formatted_code = f"{verify_code[:3]}-{verify_code[3:]}"
                # 返回 HTML 格式，与 Worker 邮箱的原始格式匹配
                return f"<strong>{formatted_code}</strong>"
            else:
                return None

        except Exception as e:
            print(f"[-] DuckMail 获取邮件失败: {e}")
            return None
