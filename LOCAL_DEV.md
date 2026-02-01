# 本地开发指南

## 快速开始

### 1. 安装依赖

```bash
# 安装 Python 依赖
pip install -r requirements.txt

# 额外依赖
pip install curl_cffi requests beautifulsoup4 psutil
```

### 2. 配置环境

创建 `.env.register` 文件：

```bash
# 复制示例配置
copy .env.register.example .env.register

# 编辑配置文件（填写你的配置）
notepad .env.register
```

配置示例：

```ini
DUCKMAIL_BASE_URL=https://api.duckmail.sbs
DUCKMAIL_API_KEY=
EMAIL_DOMAIN=baldur.edu.kg
CONCURRENT_THREADS=1
```

### 3. 启动方式

#### 方式一：使用启动脚本（推荐）

```bash
# Windows
start_local.bat

# Linux/Mac
chmod +x start.sh && ./start.sh
```

#### 方式二：手动启动

**启动 API 服务器：**

```bash
cd grok2api
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

访问：http://localhost:8000/login

**运行注册机（需要先配置）：**

```bash
# 确保已配置 .env.register
python grok.py
```

### 4. 测试组件

运行测试脚本：

```bash
python test_local.py
```

测试选项：
1. 测试 DuckMail 连接
2. 测试邮箱服务
3. 测试完整注册流程

## 目录结构

```
grok/
├── grok.py                      # 注册机主程序
├── g/                           # 注册机配件
│   ├── duckmail_client.py       # DuckMail API 客户端
│   ├── duckmail_email_service.py # DuckMail 邮箱服务
│   └── turnstile_service.py     # Turnstile 求解服务
├── grok2api/                    # API 服务
│   ├── app/
│   │   ├── api/admin/           # 管理接口
│   │   │   └── register.py      # 注册机管理
│   │   ├── template/            # 前端模板
│   │   └── main.py              # FastAPI 应用
│   └── requirements.txt
├── keys/                        # 存储生成的 SSO Token
├── logs/                        # 日志目录
│   └── register/                # 注册机日志
├── .env.register                # 注册机配置（需创建）
└── start_local.bat              # 本地启动脚本
```

## 调试技巧

### 查看注册机日志

日志文件位置：`logs/register/register.log`

实时查看：
```bash
# Windows (PowerShell)
Get-Content logs/register/register.log -Wait

# Linux/Mac
tail -f logs/register/register.log
```

### 测试 DuckMail

```python
# 测试连接
from g import DuckMailClient
client = DuckMailClient()
print(client.test_connection())

# 获取域名
domains = client.get_available_domains()
print(domains)
```

### 查看环境变量

```python
import os
from dotenv import load_dotenv

load_dotenv('.env.register')
print(os.getenv('EMAIL_DOMAIN'))
```

## 常见问题

### 1. DuckMail 连接失败

检查：
- 网络连接是否正常
- API 地址是否正确
- 是否需要 API 密钥

### 2. 邮箱创建失败

检查：
- 域名是否有效
- DuckMail 服务是否可用
- 查看详细错误日志

### 3. 验证码收不到

检查：
- 邮件是否发送成功
- DuckMail 是否收到邮件
- 邮件内容格式是否正确
- 正则表达式是否匹配

### 4. API 无法启动

检查：
- 端口 8000 是否被占用
- 依赖是否全部安装
- 查看错误日志

## 开发建议

1. **先测试组件**：使用 `test_local.py` 测试各个组件
2. **查看日志**：所有日志都会输出到控制台和文件
3. **单线程测试**：设置 `CONCURRENT_THREADS=1` 便于调试
4. **逐步验证**：先验证 DuckMail，再验证注册流程

## 提交代码

修改代码后：

```bash
git add .
git commit -m "描述你的修改"
git push origin main
```
