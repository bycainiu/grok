# Grok 整合项目

[![Deploy on Zeabur](https://zeabur.com/button.svg)](https://zeabur.com/deploy?repository=git://github.com/bycainiu/grok.git)

## 快速部署

### Zeabur 一键部署

点击上方按钮，或访问 https://zeabur.com 导入本仓库即可。

### Docker 本地部署

```bash
git clone https://github.com/bycainiu/grok.git
cd grok

# Windows
start.bat

# Linux/Mac
chmod +x start.sh && ./start.sh
```

访问 http://localhost 开始使用。

## 功能特性

- ✅ **Turnstile Solver** - 自动求解 CAPTCHA
- ✅ **Grok 注册机** - 自动批量注册账号
- ✅ **Web 管理界面** - 可视化管理控制台
- ✅ **Docker 一键部署** - 开箱即用
- ✅ **Token 管理** - 自动导入和管理 SSO Token

## 使用说明

1. 登录管理后台 (`/login`)
2. 进入「注册机管理」标签
3. 配置邮箱服务并启动注册机
4. 导入 Token 到 Token 管理

详细文档请查看 [DOCKER_README.md](DOCKER_README.md)

## 技术栈

- **后端**: FastAPI + Python
- **前端**: Tailwind CSS + Vanilla JS
- **容器**: Docker + Docker Compose
- **浏览器自动化**: Patchright
