"""
Turnstile验证服务类
"""
import os
import time
import requests
from .env_loader import load_register_env
from .proxy_manager import get_proxy_url

load_register_env()

DEFAULT_SOLVER_URL = "http://127.0.0.1:5072"
DEFAULT_TIMEOUT_SECONDS = 20


class TurnstileService:
    """Turnstile验证服务类"""

    def __init__(self, solver_url=None):
        """
        初始化Turnstile服务
        """
        self.yescaptcha_key = os.getenv('YESCAPTCHA_KEY', '').strip()
        env_solver_url = os.getenv('TURNSTILE_SOLVER_URL', '').strip()
        resolved_solver_url = (solver_url or env_solver_url or DEFAULT_SOLVER_URL).strip()
        # 统一移除末尾 /，避免拼接双斜杠
        self.solver_url = resolved_solver_url.rstrip("/")
        self.yescaptcha_api = "https://api.yescaptcha.com"
        self.request_timeout = int(os.getenv("TURNSTILE_SOLVER_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)))
        proxy_url = get_proxy_url()
        self.proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None

    def create_task(self, siteurl, sitekey):
        """
        创建Turnstile验证任务
        """
        if self.yescaptcha_key:
            # 使用 YesCaptcha API
            url = f"{self.yescaptcha_api}/createTask"
            payload = {
                "clientKey": self.yescaptcha_key,
                "task": {
                    "type": "TurnstileTaskProxyless",
                    "websiteURL": siteurl,
                    "websiteKey": sitekey
                }
            }
            response = requests.post(url, json=payload, timeout=self.request_timeout, proxies=self.proxies)
            response.raise_for_status()
            data = response.json()
            if data.get('errorId') != 0:
                raise Exception(f"YesCaptcha创建任务失败: {data.get('errorDescription')}")
            task_id = data.get('taskId')
            if not task_id:
                raise Exception("YesCaptcha 返回缺少 taskId")
            return task_id
        else:
            # 使用本地 Turnstile Solver
            url = f"{self.solver_url}/turnstile?url={siteurl}&sitekey={sitekey}"
            response = requests.get(url, timeout=self.request_timeout, proxies=self.proxies)
            response.raise_for_status()
            data = response.json()
            if data.get('errorId') not in (None, 0):
                raise Exception(f"Turnstile Solver 创建任务失败: {data.get('errorDescription')}")
            task_id = data.get('taskId')
            if not task_id:
                raise Exception("Turnstile Solver 返回缺少 taskId")
            return task_id

    def get_response(self, task_id, max_retries=30, initial_delay=5, retry_delay=2):
        """
        获取Turnstile验证响应
        """
        if not task_id:
            return None
        time.sleep(initial_delay)

        for _ in range(max_retries):
            try:
                if self.yescaptcha_key:
                    # 使用 YesCaptcha API
                    url = f"{self.yescaptcha_api}/getTaskResult"
                    payload = {
                        "clientKey": self.yescaptcha_key,
                        "taskId": task_id
                    }
                    response = requests.post(url, json=payload, timeout=self.request_timeout, proxies=self.proxies)
                    response.raise_for_status()
                    data = response.json()

                    if data.get('errorId') != 0:
                        print(f"YesCaptcha获取结果失败: {data.get('errorDescription')}")
                        return None

                    if data.get('status') == 'ready':
                        token = data.get('solution', {}).get('token')
                        if token:
                            return token
                        else:
                            print("YesCaptcha返回结果中没有token")
                            return None
                    elif data.get('status') == 'processing':
                        time.sleep(retry_delay)
                    else:
                        print(f"YesCaptcha未知状态: {data.get('status')}")
                        time.sleep(retry_delay)
                else:
                    # 使用本地 Turnstile Solver
                    url = f"{self.solver_url}/result?id={task_id}"
                    response = requests.get(url, timeout=self.request_timeout, proxies=self.proxies)
                    response.raise_for_status()
                    data = response.json()
                    if data.get('errorId') not in (None, 0):
                        print(f"Turnstile Solver 获取结果失败: {data.get('errorDescription')}")
                        return None

                    status = data.get('status')
                    if status == "ready":
                        captcha = data.get('solution', {}).get('token')
                        if captcha and captcha != "CAPTCHA_FAIL":
                            return captcha
                        return None
                    if status == "processing":
                        time.sleep(retry_delay)
                        continue

                    captcha = data.get('solution', {}).get('token')
                    if captcha and captcha != "CAPTCHA_FAIL":
                        return captcha
                    time.sleep(retry_delay)
            except Exception as e:
                print(f"获取Turnstile响应异常: {e}")
                time.sleep(retry_delay)

        return None
