import os, json, random, string, time, re, struct, datetime
import threading
import concurrent.futures
from urllib.parse import urljoin, urlparse

# 尝试导入 curl_cffi，如果失败则使用标准 requests
try:
    from curl_cffi import requests
    USE_CURL_CFFI = True
    print(f"[+] 使用 curl_cffi 进行请求")
except ImportError:
    import requests as _requests
    # 创建一个兼容的接口
    class RequestsWrapper:
        """包装标准 requests 库以兼容 curl_cffi 接口"""
        @staticmethod
        def Session(*args, **kwargs):
            impersonate = kwargs.pop('impersonate', None)
            class Session:
                def __init__(self):
                    self.session = _requests.Session()
                def get(self, *args, **kwargs):
                    return self.session.get(*args, **kwargs)
                def post(self, *args, **kwargs):
                    return self.session.post(*args, **kwargs)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    self.session.close()
            return Session()

    requests = RequestsWrapper()
    USE_CURL_CFFI = False
    print(f"[-] curl_cffi 未安装，使用标准 requests 库")

from bs4 import BeautifulSoup

from g import DuckMailEmailService, TurnstileService
from g.proxy_manager import get_proxy_url

# 基础配置
site_url = "https://accounts.x.ai"
user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
_proxy_url = get_proxy_url()
PROXIES = {"http": _proxy_url, "https": _proxy_url} if _proxy_url else None

# 动态获取的全局变量
config = {
    "site_key": "0x4AAAAAAAhr9JGVDZbrZOo0",
    "action_id": None,
    "state_tree": "%5B%22%22%2C%7B%22children%22%3A%5B%22(app)%22%2C%7B%22children%22%3A%5B%22(auth)%22%2C%7B%22children%22%3A%5B%22sign-up%22%2C%7B%22children%22%3A%5B%22__PAGE__%22%2C%7B%7D%2C%22%2Fsign-up%22%2C%22refresh%22%5D%7D%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%5D%7D%2Cnull%2Cnull%2Ctrue%5D"
}

post_lock = threading.Lock()
file_lock = threading.Lock()
success_count = 0
start_time = time.time()

def generate_random_name() -> str:
    length = random.randint(4, 6)
    return random.choice(string.ascii_uppercase) + ''.join(random.choice(string.ascii_lowercase) for _ in range(length - 1))

def generate_random_string(length: int = 15) -> str:
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))

def encode_grpc_message(field_id, string_value):
    key = (field_id << 3) | 2
    value_bytes = string_value.encode('utf-8')
    length = len(value_bytes)
    payload = struct.pack('B', key) + struct.pack('B', length) + value_bytes
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def encode_grpc_message_verify(email, code):
    p1 = struct.pack('B', (1 << 3) | 2) + struct.pack('B', len(email)) + email.encode('utf-8')
    p2 = struct.pack('B', (2 << 3) | 2) + struct.pack('B', len(code)) + code.encode('utf-8')
    payload = p1 + p2
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def generate_random_birthdate():
    """生成随机出生日期（20-40岁之间）"""
    today = datetime.date.today()
    # 随机年龄 20-40 岁
    age = random.randint(20, 40)
    birth_year = today.year - age
    birth_month = random.randint(1, 12)
    birth_day = random.randint(1, 28)  # 避免月份天数问题
    return f"{birth_year}-{birth_month:02d}-{birth_day:02d}T16:00:00.000Z"

def set_birth_date(session, sso_token):
    """设置出生日期 - REST API"""
    url = "https://grok.com/rest/auth/set-birth-date"
    cookie_str = f"sso={sso_token}; sso-rw={sso_token}"
    headers = {
        "content-type": "application/json",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
        "user-agent": user_agent,
        "cookie": cookie_str
    }
    payload = {"birthDate": generate_random_birthdate()}
    try:
        res = session.post(url, json=payload, headers=headers, timeout=15)
        # print(f"[debug] set_birth_date {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[!] set_birth_date 异常: {e}")
        return False

def set_tos_accepted(session, sso_token):
    """设置 TOS 接受版本 - gRPC API (accounts.x.ai)"""
    url = "https://accounts.x.ai/auth_mgmt.AuthManagement/SetTosAcceptedVersion"
    # 编码: field 2 (tos_version) = 1
    payload = struct.pack('B', (2 << 3) | 0) + struct.pack('B', 1)  # field 2, varint, value=1
    data = b'\x00' + struct.pack('>I', len(payload)) + payload
    cookie_str = f"sso={sso_token}; sso-rw={sso_token}"
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "x-user-agent": "connect-es/2.1.1",
        "origin": "https://accounts.x.ai",
        "referer": "https://accounts.x.ai/accept-tos",
        "user-agent": user_agent,
        "cookie": cookie_str
    }
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] set_tos_accepted 异常: {e}")
        return False

def encode_grpc_nsfw_settings():
    field1_content = bytes([0x10, 0x01])
    field1 = bytes([0x0a, len(field1_content)]) + field1_content
    nsfw_string = b"always_show_nsfw_content"
    field2_inner = bytes([0x0a, len(nsfw_string)]) + nsfw_string
    field2 = bytes([0x12, len(field2_inner)]) + field2_inner
    payload = field1 + field2
    return b'\x00' + struct.pack('>I', len(payload)) + payload

def update_nsfw_settings(session, sso_token):
    """更新 NSFW 设置 - gRPC API"""
    url = "https://grok.com/auth_mgmt.AuthManagement/UpdateUserFeatureControls"
    data = encode_grpc_nsfw_settings()
    cookie_str = f"sso={sso_token}; sso-rw={sso_token}"
    headers = {
        "content-type": "application/grpc-web+proto",
        "x-grpc-web": "1",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
        "user-agent": user_agent,
        "cookie": cookie_str
    }
    try:
        res = session.post(url, data=data, headers=headers, timeout=15)
        return res.status_code == 200
    except Exception as e:
        print(f"[!] update_nsfw 异常: {e}")
        return False

def send_email_code_grpc(session, email):
    url = f"{site_url}/auth_mgmt.AuthManagement/CreateEmailValidationCode"
    data = encode_grpc_message(1, email)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        print(f"[debug] {email} 正在发送验证码请求...")
        res = session.post(url, data=data, headers=headers, timeout=30)
        print(f"[debug] {email} 请求结束，状态码: {res.status_code}")
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} 发送验证码异常: {e}")
        return False

def verify_email_code_grpc(session, email, code):
    url = f"{site_url}/auth_mgmt.AuthManagement/VerifyEmailValidationCode"
    data = encode_grpc_message_verify(email, code)
    headers = {"content-type": "application/grpc-web+proto", "x-grpc-web": "1", "x-user-agent": "connect-es/2.1.1", "origin": site_url, "referer": f"{site_url}/sign-up?redirect=grok-com"}
    try:
        print(f"[debug] {email} 验证码: {code}, 状态码检查...")
        res = session.post(url, data=data, headers=headers, timeout=15)
        # print(f"[debug] {email} 验证响应状态: {res.status_code}, 内容长度: {len(res.content)}")
        return res.status_code == 200
    except Exception as e:
        print(f"[-] {email} 验证验证码异常: {e}")
        return False

def register_single_thread():
    # 错峰启动，防止瞬时并发过高
    time.sleep(random.uniform(0, 5))

    try:
        email_service = DuckMailEmailService()
        turnstile_service = TurnstileService()
    except Exception as e:
        print(f"[-] 服务初始化失败: {e}")
        return
    
    # 修正：直接从 config 获取
    final_action_id = config["action_id"]
    if not final_action_id:
        print("[-] 线程退出：缺少 Action ID")
        return
    
    while True:
        try:
            with requests.Session(impersonate="chrome120", proxies=PROXIES) as session:
                # 预热连接
                try:
                    print(f"[debug] {threading.get_ident()} 预热连接...")
                    session.get(site_url, timeout=10)
                    print(f"[debug] {threading.get_ident()} 预热完成")
                except Exception as e:
                    print(f"[-] {threading.get_ident()} 预热失败: {e}")

                password = generate_random_string()

                # print(f"[debug] 线程-{threading.get_ident()} 正在请求创建邮箱...")
                try:
                    jwt, email = email_service.create_email()
                except Exception as e:
                    print(f"[-] 邮箱服务抛出异常: {e}")
                    jwt, email = None, None

                if not email:
                    print(f"[-] 线程-{threading.get_ident()} 邮箱创建返回空，可能接口挂了或超时，等待 5s...")
                    time.sleep(5); continue

                print(f"[*] 开始注册: {email}")

                # Step 1: 发送验证码
                if not send_email_code_grpc(session, email):
                    print(f"[-] [{email}] 发送验证码失败")
                    time.sleep(5); continue

                # Step 2: 获取验证码
                print(f"[*] [{email}] 等待验证码...")
                verify_code = None
                for attempt in range(30):
                    if attempt % 5 == 0:  # 每 5 秒打印一次
                        print(f"[debug] [{email}] 轮询验证码 {attempt+1}/30...")
                    content = email_service.fetch_first_email(jwt)
                    if content:
                        match = re.search(r">([A-Z0-9]{3}-[A-Z0-9]{3})<", content)
                        if match:
                            verify_code = match.group(1).replace("-", "")
                            print(f"[+] [{email}] 收到验证码: {verify_code}")
                            break
                    time.sleep(1)
                if not verify_code:
                    print(f"[-] [{email}] 未收到验证码（等待30秒后超时）")
                    continue

                # Step 3: 验证验证码
                print(f"[*] [{email}] 验证验证码...")
                if not verify_email_code_grpc(session, email, verify_code):
                    print(f"[-] [{email}] 验证码无效")
                    continue
                print(f"[+] [{email}] 验证码验证成功")

                # Step 4: 注册重试循环
                for attempt in range(3):
                    print(f"[debug] [{email}] CAPTCHA 求解尝试 {attempt+1}/3...")
                    try:
                        task_id = turnstile_service.create_task(site_url, config["site_key"])
                    except Exception as e:
                        print(f"[-] [{email}] 创建 CAPTCHA 任务失败: {e}")
                        continue
                    if not task_id:
                        print(f"[-] [{email}] CAPTCHA 任务创建失败（空 task_id）")
                        continue
                    print(f"[debug] [{email}] CAPTCHA 任务ID: {task_id}")
                    token = turnstile_service.get_response(task_id)

                    if not token or token == "CAPTCHA_FAIL":
                        print(f"[-] [{email}] CAPTCHA 失败，重试...")
                        continue
                    print(f"[+] [{email}] CAPTCHA 求解成功")

                    headers = {
                        "user-agent": user_agent, "accept": "text/x-component", "content-type": "text/plain;charset=UTF-8",
                        "origin": site_url, "referer": f"{site_url}/sign-up", "cookie": f"__cf_bm={session.cookies.get('__cf_bm','')}",
                        "next-router-state-tree": config["state_tree"], "next-action": final_action_id
                    }
                    payload = [{
                        "emailValidationCode": verify_code,
                        "createUserAndSessionRequest": {
                            "email": email, "givenName": generate_random_name(), "familyName": generate_random_name(),
                            "clearTextPassword": password, "tosAcceptedVersion": "$undefined"
                        },
                        "turnstileToken": token, "promptOnDuplicateEmail": True
                    }]

                    print(f"[debug] [{email}] 提交注册请求...")
                    with post_lock:
                        res = session.post(f"{site_url}/sign-up", json=payload, headers=headers)
                    print(f"[debug] [{email}] 提交响应状态码: {res.status_code}")

                    if res.status_code == 200:
                        print(f"[+] [{email}] 注册请求成功，获取 SSO Token...")
                        match = re.search(r'(https://[^" \s]+set-cookie\?q=[^:" \s]+)1:', res.text)
                        if match:
                            verify_url = match.group(1)
                            print(f"[debug] [{email}] 验证 URL: {verify_url}")
                            session.get(verify_url, allow_redirects=True)
                            sso = session.cookies.get("sso")
                            if sso:
                                with file_lock:
                                    with open("keys/grok.txt", "a") as f: f.write(sso + "\n")
                                    with open("keys/accounts.txt", "a") as f: f.write(f"{email}:{password}:{sso}\n")
                                    global success_count
                                    success_count += 1
                                    avg = (time.time() - start_time) / success_count
                                    print(f"[✓] [{email}] 注册成功 | SSO: {sso}")
                                
                                # 注册成功后，执行账号初始化
                                print(f"[*] [{email}] 正在初始化账号设置...")
                                try:
                                    # 1. 接受 TOS
                                    if set_tos_accepted(session, sso):
                                        print(f"[✓] [{email}] TOS 接受成功")
                                    
                                    # 2. 设置生日
                                    if set_birth_date(session, sso):
                                        print(f"[✓] [{email}] 生日设置成功")
                                        
                                        # 3. 开启 NSFW (生日设置成功后才能开启)
                                        if update_nsfw_settings(session, sso):
                                            print(f"[✓] [{email}] NSFW 开启成功")
                                except Exception as e:
                                    print(f"[!] [{email}] 账号初始化异常: {e}")
                                
                                break  # 跳出 for 循环，继续 while True 注册下一个
                            else:
                                print(f"[-] [{email}] 未获取到 SSO Token")
                        else:
                            print(f"[-] [{email}] 未找到验证 URL")
                    else:
                        print(f"[-] [{email}] 提交失败 ({res.status_code})")
                        print(f"[-] [{email}] 响应内容: {res.text[:200]}")
                    time.sleep(3) # 失败稍微等一下
                else:
                    # 如果重试 3 次都失败 (for 循环没有被 break)
                    print(f"[-] [{email}] 放弃，换号")
                    time.sleep(5)

        except Exception as e:
            # 捕获所有异常防止线程退出
            import traceback
            print(f"[-] 异常: {str(e)}")
            print(f"[-] 异常堆栈:\n{traceback.format_exc()}")
            time.sleep(5)

def main():
    print("=" * 60 + "\nGrok 注册机\n" + "=" * 60)
    
    # 1. 扫描参数
    print("[*] 正在初始化...")
    start_url = f"{site_url}/sign-up"
    with requests.Session(impersonate="chrome120", proxies=PROXIES) as s:
        try:
            html = s.get(start_url).text
            # Key
            key_match = re.search(r'sitekey":"(0x4[a-zA-Z0-9_-]+)"', html)
            if key_match: config["site_key"] = key_match.group(1)
            # Tree
            tree_match = re.search(r'next-router-state-tree":"([^"]+)"', html)
            if tree_match: config["state_tree"] = tree_match.group(1)
            # Action ID
            soup = BeautifulSoup(html, 'html.parser')
            js_urls = [urljoin(start_url, script['src']) for script in soup.find_all('script', src=True) if '_next/static' in script['src']]
            for js_url in js_urls:
                js_content = s.get(js_url).text
                match = re.search(r'7f[a-fA-F0-9]{40}', js_content)
                if match:
                    config["action_id"] = match.group(0)
                    print(f"[+] Action ID: {config['action_id']}")
                    break
        except Exception as e:
            print(f"[-] 初始化扫描失败: {e}")
            return

    if not config["action_id"]:
        print("[-] 错误: 未找到 Action ID")
        return

    # 2. 启动
    # 从环境变量读取并发数，如果不存在则使用默认值 8
    concurrent_threads = os.getenv("CONCURRENT_THREADS")
    if concurrent_threads:
        try:
            t = int(concurrent_threads)
        except:
            t = 8
    else:
        t = 8

    print(f"[*] 启动 {t} 个线程...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=t) as executor:
        # 只提交与线程数相等的任务，让它们在内部无限循环
        futures = [executor.submit(register_single_thread) for _ in range(t)]
        concurrent.futures.wait(futures)

if __name__ == "__main__":
    main()