#!/bin/bash
# Grok 整合项目 - Linux/Mac 一键启动脚本
# 自动启动 Turnstile Solver 和 Grok2API（集成注册机管理）

set -e

echo "============================================"
echo "  Grok 整合项目 - 一键启动"
echo "============================================"
echo ""

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "[错误] Docker 未运行，请先启动 Docker"
    exit 1
fi

echo "[1/2] 构建镜像..."
docker-compose build

echo ""
echo "[2/2] 启动服务..."
docker-compose up -d

echo ""
echo "============================================"
echo "  启动完成！"
echo "============================================"
echo ""
echo "服务地址："
echo "  - Turnstile Solver: http://localhost:5072"
echo "  - Grok2API:         http://localhost:8000"
echo "  - 管理后台:         http://localhost:8000/login"
echo ""
echo "在管理后台的 [注册机管理] 标签页中："
echo "  1. 配置邮箱服务（Worker 域名、邮箱域名、管理员密码）"
echo "  2. 启动注册机"
echo "  3. 查看注册进度和生成的账号"
echo "  4. 导入 Token 到 Token 管理"
echo ""
echo "常用命令："
echo "  查看日志： docker-compose logs -f"
echo "  停止服务： docker-compose down"
echo "  重启服务： docker-compose restart"
echo ""
