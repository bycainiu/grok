@echo off
REM 本地开发环境启动脚本
REM 用于调试和测试

echo ============================================
echo   Grok 本地开发环境启动
echo ============================================
echo.

REM 检查 Python 是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] Python 未安装，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [1/4] 安装依赖...
pip install -r requirements.txt
if errorlevel 1 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)

echo.
echo [2/4] 安装注册机额外依赖...
pip install curl_cffi requests beautifulsoup4
pip install psutil  # 用于进程管理

echo.
echo [3/4] 创建必要的目录...
if not exist "keys" mkdir keys
if not exist "logs" mkdir logs
if not exist "logs\register" mkdir logs\register

echo.
echo [4/4] 设置环境变量...
set DUCKMAIL_BASE_URL=https://api.duckmail.sbs
set DUCKMAIL_API_KEY=
set EMAIL_DOMAIN=baldur.edu.kg
set CONCURRENT_THREADS=1
set TURNSTILE_SOLVER_URL=http://localhost:5072

echo.
echo ============================================
echo   环境变量配置
echo ============================================
echo DUCKMAIL_BASE_URL=%DUCKMAIL_BASE_URL%
echo DUCKMAIL_API_KEY=%DUCKMAIL_API_KEY%
echo EMAIL_DOMAIN=%EMAIL_DOMAIN%
echo CONCURRENT_THREADS=%CONCURRENT_THREADS%
echo TURNSTILE_SOLVER_URL=%TURNSTILE_SOLVER_URL%
echo.

echo ============================================
echo   选择启动模式
echo ============================================
echo   1. 启动 API 服务器 (FastAPI)
echo   2. 运行注册机 (需要先配置 .env.register)
echo   3. 测试 DuckMail 连接
echo.

set /p choice="请选择 (1-3): "

if "%choice%"=="1" (
    echo.
    echo 启动 FastAPI 服务器...
    echo 访问: http://localhost:8000
    echo 管理后台: http://localhost:8000/login
    echo.
    cd grok2api
    python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
) else if "%choice%"=="2" (
    echo.
    echo 运行注册机...
    echo.
    python grok.py
) else if "%choice%"=="3" (
    echo.
    echo 测试 DuckMail 连接...
    echo.
    python -c "from g import DuckMailClient; client = DuckMailClient(); print(client.test_connection())"
) else (
    echo 无效选择
)

pause
