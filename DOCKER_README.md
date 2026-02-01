# Grok 整合项目 - Docker 部署指南

本项目整合了三个核心服务：

1. **Turnstile Solver** - Turnstile CAPTCHA 求解器服务
2. **Grok Register** - Grok 账号自动注册机（集成在 Grok2API 管理后台）
3. **Grok2API** - Grok API 转换服务（OpenAI 兼容）

## 🚀 一键启动

### Windows 用户

双击运行 `start.bat` 即可自动启动所有服务。

### Linux/Mac 用户

```bash
chmod +x start.sh
./start.sh
```

启动后访问：
- **Grok2API**: http://localhost:8000
- **管理后台**: http://localhost:8000/login
- **Turnstile Solver**: http://localhost:5072

## 📋 使用注册机

### 1. 登录管理后台

访问 http://localhost:8000/login，使用默认账号登录：
- 用户名: `admin`
- 密码: `admin`

### 2. 进入注册机管理

点击顶部导航栏的 **"注册机管理"** 标签。

### 3. 配置邮箱服务

1. 点击 **"配置"** 按钮
2. 填写以下信息：
   - **Worker 域名**: 邮箱服务 API 地址（如 `https://your-worker.example.com`）
   - **邮箱域名**: 用于生成临时邮箱（如 `example.com`）
   - **管理员密码**: Worker 管理后台密码
   - **并发线程数**: 同时运行的注册线程数量（默认 8）
   - **YesCaptcha Key** (可选): 留空使用本地 Turnstile Solver
3. 点击 **"保存"**

### 4. 启动注册机

点击 **"启动注册机"** 按钮，注册机会在后台运行：
- 实时查看注册日志
- 监控成功注册数量
- 查看生成的账号

### 5. 导入 Token

注册成功后：
1. 点击 **"导入 Token"** 按钮
2. 系统会将生成的 SSO Token 自动导入到 Token 管理
3. 在 **"Token 管理"** 标签页中查看和使用

## 📁 项目结构

```
grok/
├── docker-compose.yml              # Docker Compose 配置
├── Dockerfile.turnstile-solver     # Turnstile Solver 镜像
├── requirements-solver.txt         # Solver 依赖
├── start.bat / start.sh            # 一键启动脚本
├── grok.py                         # Grok 注册机脚本
├── g/                              # 注册机配件
│   ├── __init__.py
│   ├── email_service.py            # 邮箱服务
│   └── turnstile_service.py        # Turnstile 服务
├── grok2api/                       # Grok2API 项目
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── api/admin/
│   │   │   ├── manage.py           # 管理接口
│   │   │   └── register.py         # 注册机接口 ✨
│   │   └── template/
│   │       └── admin.html          # 管理后台（含注册机管理）✨
│   └── main.py
├── keys/                           # 生成的账号密钥
└── logs/                           # 日志目录
```

## 🔧 注册机管理界面

### 状态卡片

| 指标 | 说明 |
|------|------|
| 运行状态 | 显示注册机是否运行中 |
| 成功注册 | 已成功注册的账号数量 |
| 生成 Token | 已生成的 SSO Token 数量 |
| 运行时长 | 注册机已运行的时间 |

### 控制按钮

| 按钮 | 功能 |
|------|------|
| 启动注册机 | 启动自动注册流程 |
| 停止注册机 | 停止注册机 |
| 清空生成的账号 | 删除所有已生成的账号文件 |
| 查看生成的账号 | 显示完整的账号列表（含密码和 SSO） |
| 导入 Token | 将生成的 Token 导入到 Token 管理 |

### 实时日志

左侧显示注册机实时日志，带颜色标识：
- 🟢 绿色：成功注册
- 🔴 红色：注册失败
- 🟡 黄色：进行中

### 账号列表

右侧显示已生成的账号，支持：
- 查看邮箱地址
- 查看密码
- 查看 SSO Token（前 15 位）

## 🛠️ 常用命令

```bash
# 启动所有服务
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 停止服务
docker-compose down

# 重建并启动
docker-compose up -d --build
```

## 🐛 故障排查

### Turnstile Solver 无法启动

```bash
# 查看详细日志
docker-compose logs turnstile-solver

# 检查端口占用
netstat -ano | findstr :5072  # Windows
lsof -i :5072                  # Linux/Mac
```

### 注册机无法启动

1. 检查配置是否完整
2. 查看 Turnstile Solver 是否正常运行
3. 检查邮箱服务是否可访问

```bash
# 查看 grok2api 日志
docker-compose logs grok2api
```

### 生成的 Token 无法使用

1. 检查 Token 是否已导入到 Token 管理
2. 在 Token 管理中测试 Token 可用性
3. 查看 Grok2API 日志排查问题

## 📝 注意事项

1. **邮箱服务**: 需要先部署 Worker 邮箱服务（如 [email-worker](https://github.com/dreamhunter2333/cloudflare_temp_email_worker)）
2. **Turnstile Solver**: 默认使用本地 Solver，也可配置 YesCaptcha 等 API
3. **并发限制**: 建议根据机器性能调整并发线程数
4. **数据持久化**: 生成的账号保存在 `keys/` 目录，重启不丢失

## 🔗 相关链接

- [Grok2API 原项目](https://github.com/Tomiya233/grok2api)
- Turnstile Solver API: http://localhost:5072
- Grok2API 管理后台: http://localhost:8000/login

## 📄 许可证

本项目仅供学习研究使用，请遵守相关服务条款。
