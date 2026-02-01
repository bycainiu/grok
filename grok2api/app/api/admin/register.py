"""注册机管理接口"""

import asyncio
import os
import subprocess
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel

from app.core.logger import logger
from app.api.admin.manage import verify_admin_session

router = APIRouter(tags=["注册机管理"])

# 常量 - 检测是否在 Docker 环境中
def _get_project_root():
    """获取项目根目录"""
    # 检查是否在 Docker 容器中
    # 方法1: 检查 /.dockerenv 文件
    if Path("/.dockerenv").exists():
        return Path("/app")
    # 方法2: 检查 /app/grok.py 是否存在（挂载的文件）
    if Path("/app/grok.py").exists():
        return Path("/app")
    # 本地开发环境
    return Path(__file__).parents[4]

PROJECT_ROOT = _get_project_root()
KEYS_DIR = PROJECT_ROOT / "keys"
REGISTER_LOG_DIR = PROJECT_ROOT / "logs" / "register"
REGISTER_PROCESS_FILE = PROJECT_ROOT / "data" / "register_process.json"
REGISTER_SCRIPT = PROJECT_ROOT / "grok.py"

# 确保目录存在
KEYS_DIR.mkdir(parents=True, exist_ok=True)
REGISTER_LOG_DIR.mkdir(parents=True, exist_ok=True)
REGISTER_PROCESS_FILE.parent.mkdir(parents=True, exist_ok=True)

# 注册机进程状态
_register_process: Optional[subprocess.Popen] = None
_register_status = {
    "running": False,
    "pid": None,
    "start_time": None,
    "stats": {
        "success_count": 0,
        "total_attempts": 0,
        "last_register_time": None
    }
}


# === 请求/响应模型 ===

class RegisterConfigRequest(BaseModel):
    """注册机配置请求"""
    worker_domain: str
    email_domain: str
    admin_password: str
    concurrent_threads: int = 8
    yescaptcha_key: Optional[str] = None


class RegisterStartRequest(BaseModel):
    """启动注册机请求"""
    config: RegisterConfigRequest


class RegisterConfigResponse(BaseModel):
    """注册机配置响应"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str


# === 辅助函数 ===

def _load_register_status() -> Dict[str, Any]:
    """加载注册机状态"""
    global _register_status
    try:
        if REGISTER_PROCESS_FILE.exists():
            with open(REGISTER_PROCESS_FILE, 'r', encoding='utf-8') as f:
                saved_status = json.load(f)
                # 合并保存的状态
                _register_status.update(saved_status)
    except Exception as e:
        logger.warning(f"加载注册机状态失败: {e}")
    return _register_status


def _save_register_status():
    """保存注册机状态"""
    try:
        with open(REGISTER_PROCESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_register_status, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"保存注册机状态失败: {e}")


def _load_config() -> Optional[Dict[str, Any]]:
    """加载注册机配置"""
    config_file = PROJECT_ROOT / ".env.register"
    if config_file.exists():
        config = {}
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        config[key.strip()] = value.strip()
            return config
        except Exception as e:
            logger.error(f"加载注册机配置失败: {e}")
    return None


def _save_config(config: Dict[str, Any]):
    """保存注册机配置"""
    config_file = PROJECT_ROOT / ".env.register"
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write("# Grok 注册机配置\n")
            f.write("# 由管理后台自动生成\n\n")
            for key, value in config.items():
                f.write(f"{key}={value}\n")
        logger.info("注册机配置已保存")
    except Exception as e:
        logger.error(f"保存注册机配置失败: {e}")
        raise


async def _read_generated_keys() -> List[Dict[str, Any]]:
    """读取已生成的账号"""
    keys_file = KEYS_DIR / "grok.txt"
    accounts_file = KEYS_DIR / "accounts.txt"

    tokens = []
    accounts = []

    if keys_file.exists():
        try:
            with open(keys_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        tokens.append(line)
        except Exception as e:
            logger.error(f"读取 SSO Token 失败: {e}")

    if accounts_file.exists():
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ':' in line:
                        parts = line.split(':')
                        if len(parts) >= 3:
                            accounts.append({
                                "email": parts[0],
                                "password": parts[1],
                                "sso": parts[2],
                                "sso_short": f"{parts[2][:15]}..." if len(parts[2]) > 15 else parts[2]
                            })
        except Exception as e:
            logger.error(f"读取账号列表失败: {e}")

    return {
        "tokens": tokens,
        "accounts": accounts,
        "token_count": len(tokens),
        "account_count": len(accounts)
    }


async def _read_register_log(lines: int = 100) -> List[str]:
    """读取注册机日志"""
    log_file = REGISTER_LOG_DIR / "register.log"
    if not log_file.exists():
        return []

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # 返回最后 N 行
            return [line.strip() for line in all_lines[-lines:] if line.strip()]
    except Exception as e:
        logger.error(f"读取注册机日志失败: {e}")
        return []


# === API 端点 ===

@router.get("/api/register/status")
async def get_register_status(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取注册机状态"""
    try:
        status = _load_register_status()

        # 检查进程是否实际在运行
        if status["running"] and status["pid"]:
            try:
                # 检查进程是否存在
                import psutil
                if not psutil.pid_exists(status["pid"]):
                    status["running"] = False
                    status["pid"] = None
                    _register_status.update(status)
                    _save_register_status()
            except ImportError:
                # 如果没有 psutil，跳过检查
                pass

        # 读取生成的账号
        keys_data = await _read_generated_keys()

        return {
            "success": True,
            "data": {
                **status,
                "keys": keys_data
            }
        }
    except Exception as e:
        logger.error(f"获取注册机状态失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取状态失败: {e}"})


@router.get("/api/register/config")
async def get_register_config(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取注册机配置"""
    try:
        config = _load_config()
        if not config:
            return {
                "success": True,
                "data": {
                    "worker_domain": "",
                    "email_domain": "",
                    "admin_password": "",
                    "concurrent_threads": 8,
                    "yescaptcha_key": ""
                }
            }

        return {
            "success": True,
            "data": {
                "worker_domain": config.get("WORKER_DOMAIN", ""),
                "email_domain": config.get("EMAIL_DOMAIN", ""),
                "admin_password": config.get("ADMIN_PASSWORD", ""),
                "concurrent_threads": int(config.get("CONCURRENT_THREADS", "8")),
                "yescaptcha_key": config.get("YESCAPTCHA_KEY", "")
            }
        }
    except Exception as e:
        logger.error(f"获取注册机配置失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取配置失败: {e}"})


@router.post("/api/register/config")
async def save_register_config(request: RegisterConfigRequest, _: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """保存注册机配置"""
    try:
        config = {
            "WORKER_DOMAIN": request.worker_domain,
            "EMAIL_DOMAIN": request.email_domain,
            "ADMIN_PASSWORD": request.admin_password,
            "CONCURRENT_THREADS": str(request.concurrent_threads)
        }
        if request.yescaptcha_key:
            config["YESCAPTCHA_KEY"] = request.yescaptcha_key

        _save_config(config)

        logger.info(f"注册机配置已更新: {request.worker_domain}")
        return {"success": True, "message": "配置已保存"}
    except Exception as e:
        logger.error(f"保存注册机配置失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"保存配置失败: {e}"})


@router.post("/api/register/start")
async def start_register(request: RegisterStartRequest, _: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """启动注册机"""
    global _register_status, _register_process

    try:
        # 检查是否已在运行
        if _register_status["running"]:
            return {"success": False, "message": "注册机已在运行中"}

        # 先保存配置
        config = {
            "WORKER_DOMAIN": request.config.worker_domain,
            "EMAIL_DOMAIN": request.config.email_domain,
            "ADMIN_PASSWORD": request.config.admin_password,
            "CONCURRENT_THREADS": str(request.config.concurrent_threads)
        }
        if request.config.yescaptcha_key:
            config["YESCAPTCHA_KEY"] = request.config.yescaptcha_key

        _save_config(config)

        # 启动注册机进程
        if not REGISTER_SCRIPT.exists():
            return {"success": False, "message": f"注册机脚本不存在: {REGISTER_SCRIPT}"}

        # 准备环境变量
        env = os.environ.copy()
        env["TURNSTILE_SOLVER_URL"] = "http://turnstile-solver:5072"
        env["WORKER_DOMAIN"] = request.config.worker_domain
        env["EMAIL_DOMAIN"] = request.config.email_domain
        env["ADMIN_PASSWORD"] = request.config.admin_password
        env["CONCURRENT_THREADS"] = str(request.config.concurrent_threads)
        if request.config.yescaptcha_key:
            env["YESCAPTCHA_KEY"] = request.config.yescaptcha_key

        # 准备日志文件
        log_file = REGISTER_LOG_DIR / "register.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # 启动进程
        process = subprocess.Popen(
            ["python", "grok.py"],
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )

        # 更新状态
        _register_status["running"] = True
        _register_status["pid"] = process.pid
        _register_status["start_time"] = datetime.now().isoformat()
        _register_status["stats"] = {
            "success_count": 0,
            "total_attempts": 0,
            "last_register_time": None
        }
        _save_register_status()

        # 启动日志读取任务
        asyncio.create_task(_monitor_register_process(process, log_file))

        logger.info(f"注册机已启动 (PID: {process.pid})")
        return {
            "success": True,
            "message": f"注册机已启动 (PID: {process.pid})",
            "data": {"pid": process.pid}
        }
    except Exception as e:
        logger.error(f"启动注册机失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"启动失败: {e}"})


@router.post("/api/register/stop")
async def stop_register(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """停止注册机"""
    global _register_status, _register_process

    try:
        if not _register_status["running"]:
            return {"success": False, "message": "注册机未运行"}

        pid = _register_status["pid"]
        if pid:
            try:
                import psutil
                process = psutil.Process(pid)
                process.terminate()
                # 等待最多5秒
                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    process.kill()
            except ImportError:
                # 没有 psutil，尝试使用 os.kill
                import signal
                os.kill(pid, signal.SIGTERM)
            except Exception as e:
                logger.warning(f"终止进程失败: {e}")

        # 更新状态
        _register_status["running"] = False
        _register_status["pid"] = None
        _save_register_status()

        logger.info("注册机已停止")
        return {"success": True, "message": "注册机已停止"}
    except Exception as e:
        logger.error(f"停止注册机失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"停止失败: {e}"})


@router.get("/api/register/logs")
async def get_register_logs(lines: int = 100, _: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取注册机日志"""
    try:
        logs = await _read_register_log(lines)
        return {
            "success": True,
            "data": {
                "logs": logs,
                "count": len(logs)
            }
        }
    except Exception as e:
        logger.error(f"获取注册机日志失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取日志失败: {e}"})


@router.get("/api/register/keys")
async def get_register_keys(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """获取已生成的账号列表"""
    try:
        keys_data = await _read_generated_keys()
        return {
            "success": True,
            "data": keys_data
        }
    except Exception as e:
        logger.error(f"获取账号列表失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取账号失败: {e}"})


@router.post("/api/register/keys/import")
async def import_keys_to_tokens(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """将生成的 Token 导入到 Token 管理"""
    try:
        keys_file = KEYS_DIR / "grok.txt"
        if not keys_file.exists():
            return {"success": False, "message": "没有可导入的 Token"}

        tokens = []
        with open(keys_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    tokens.append(line)

        if not tokens:
            return {"success": False, "message": "Token 文件为空"}

        # 导入到 token_manager
        from app.services.grok.token import token_manager
        from app.models.grok_models import TokenType

        await token_manager.add_token(tokens, TokenType.NORMAL)

        logger.info(f"已导入 {len(tokens)} 个 Token")
        return {
            "success": True,
            "message": f"成功导入 {len(tokens)} 个 Token",
            "data": {"count": len(tokens)}
        }
    except Exception as e:
        logger.error(f"导入 Token 失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"导入失败: {e}"})


@router.post("/api/register/keys/clear")
async def clear_register_keys(_: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """清空已生成的账号"""
    try:
        keys_file = KEYS_DIR / "grok.txt"
        accounts_file = KEYS_DIR / "accounts.txt"

        count = 0
        if keys_file.exists():
            keys_file.unlink()
            count += 1
        if accounts_file.exists():
            accounts_file.unlink()
            count += 1

        logger.info("已清空生成的账号文件")
        return {
            "success": True,
            "message": f"已清空 {count} 个文件"
        }
    except Exception as e:
        logger.error(f"清空账号失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"清空失败: {e}"})


# === 辅助任务 ===

async def _monitor_register_process(process: subprocess.Popen, log_file: Path):
    """监控注册机进程并记录日志"""
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            for line in process.stdout:
                line = line.strip()
                if line:
                    f.write(f"{line}\n")
                    f.flush()
                    # 解析日志更新统计
                    _parse_register_log(line)

        # 进程结束
        returncode = process.wait()
        logger.info(f"注册机进程已退出 (返回码: {returncode})")

        # 更新状态
        global _register_status
        _register_status["running"] = False
        _register_status["pid"] = None
        _save_register_status()

    except Exception as e:
        logger.error(f"监控注册机进程失败: {e}")


def _parse_register_log(line: str):
    """解析注册机日志更新统计"""
    global _register_status

    # 检测成功注册
    if "[✓]" in line or "注册成功" in line:
        _register_status["stats"]["success_count"] += 1
        _register_status["stats"]["last_register_time"] = datetime.now().isoformat()
        _register_status["stats"]["total_attempts"] += 1
        _save_register_status()
    elif "[-]" in line or "失败" in line:
        _register_status["stats"]["total_attempts"] += 1
        _save_register_status()
