# 多阶段构建 - 用于 Zeabur 部署
# 构建 Grok2API 主服务

FROM python:3.11-slim AS builder

WORKDIR /build

# 安装依赖
COPY grok2api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# 运行阶段
FROM python:3.11-slim

WORKDIR /app

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制依赖
COPY --from=builder /install /usr/local

# 复制应用代码
COPY grok2api/app/ ./app/
COPY grok2api/main.py .
COPY grok2api/docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# 复制注册机文件
COPY grok.py .
COPY g/ ./g/

# 创建目录
RUN mkdir -p /app/data/temp/image /app/data/temp/video /app/keys /app/logs/register

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
