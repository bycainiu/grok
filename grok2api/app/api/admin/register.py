"""注册机管理接口"""

import asyncio
import os
import subprocess
import json
import time
from typing import Dict, Any, List, Optional, Set
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Depends, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.core.logger import logger
from app.api.admin.manage import verify_admin_session

router = APIRouter(tags=["注册机管理"])

# WebSocket 连接管理器
class RegisterConnectionManager:
    """注册机 WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """接受新的 WebSocket 连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"[WebSocket] 新连接加入，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """断开 WebSocket 连接"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[WebSocket] 连接断开，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """向所有连接的客户端广播消息"""
        if not self.active_connections:
            return

        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"[WebSocket] 发送消息失败: {e}")
                disconnected.append(connection)

        # 清理断开的连接
        for connection in disconnected:
            self.disconnect(connection)

    async def send_status_update(self, status: Dict[str, Any]):
        """发送状态更新"""
        await self.broadcast({
            "type": "status_update",
            "data": status
        })

    async def send_log_update(self, log_lines: List[str]):
        """发送日志更新"""
        await self.broadcast({
            "type": "log_update",
            "data": {
                "logs": log_lines,
                "count": len(log_lines)
            }
        })

    async def send_stats_update(self, stats: Dict[str, Any]):
        """发送统计更新"""
        await self.broadcast({
            "type": "stats_update",
            "data": stats
        })


# 全局连接管理器实例
ws_manager = RegisterConnectionManager()

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
    # 本地开发环境：向上查找 grok.py 所在目录
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "grok.py").exists():
            return parent
    # 兜底：保持旧逻辑
    return Path(__file__).parents[4]


def _is_docker_environment() -> bool:
    """检测是否在 Docker 环境中运行"""
    # 方法1: 检查 /.dockerenv 文件
    if Path("/.dockerenv").exists():
        return True
    # 方法2: 检查 /proc/1/cgroup（Linux）
    try:
        with open("/proc/1/cgroup", "r") as f:
            return "docker" in f.read() or "kubepods" in f.read()
    except:
        pass
    # 方法3: 检查 grok.py 路径
    if Path("/app/grok.py").exists():
        return True
    return False


def _default_solver_url() -> str:
    """根据环境返回默认 Turnstile Solver URL"""
    return "http://turnstile-solver:5072" if _is_docker_environment() else "http://127.0.0.1:5072"


def _normalize_solver_url(solver_url: Optional[str]) -> str:
    """规范化 Turnstile Solver URL 并处理 Docker 兼容性"""
    candidate = (solver_url or "").strip()
    if not candidate:
        env_solver = os.getenv("TURNSTILE_SOLVER_URL", "").strip()
        candidate = env_solver or _default_solver_url()

    candidate = candidate.rstrip("/")

    if _is_docker_environment() and ("127.0.0.1" in candidate or "localhost" in candidate):
        logger.info(f"[环境检测] 检测到 Docker 环境，自动将 Solver URL 从 {candidate} 调整为 http://turnstile-solver:5072")
        return "http://turnstile-solver:5072"
    return candidate


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
_register_monitor_task: Optional[asyncio.Task] = None
_register_status = {
    "running": False,
    "pid": None,
    "start_time": None,
    "updated_at": 0.0,
    "stats": {
        "success_count": 0,
        "total_attempts": 0,
        "last_register_time": None
    }
}
_last_status_save_ts: float = 0.0


# === 请求/响应模型 ===

class RegisterConfigRequest(BaseModel):
    """注册机配置请求"""
    # DuckMail 配置
    duckmail_base_url: str = "https://api.duckmail.sbs"
    duckmail_api_key: str = ""
    # 域名选择
    email_domain: str = ""
    # 注册参数
    concurrent_threads: int = 3
    # Turnstile Solver 配置
    turnstile_solver_url: str = "http://127.0.0.1:5072"
    yescaptcha_key: Optional[str] = None
    # 代理配置
    proxy_url: Optional[str] = ""
    proxy_secret_id: Optional[str] = ""
    proxy_secret_key: Optional[str] = ""
    proxy_host: Optional[str] = ""
    proxy_port: Optional[str] = ""
    proxy_scheme: Optional[str] = "http"


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
                saved_status = _ensure_register_status_fields(saved_status)
                saved_ts = saved_status.get("updated_at") or 0.0
                current_ts = _register_status.get("updated_at") or 0.0
                # 仅当保存状态更新时才覆盖，避免回退
                if saved_ts > current_ts or current_ts == 0.0:
                    _register_status.update(saved_status)
        _register_status = _ensure_register_status_fields(_register_status)
    except Exception as e:
        logger.warning(f"加载注册机状态失败: {e}")
    return _register_status


def _save_register_status():
    """保存注册机状态"""
    try:
        global _register_status
        _register_status = _ensure_register_status_fields(_register_status)
        with open(REGISTER_PROCESS_FILE, 'w', encoding='utf-8') as f:
            json.dump(_register_status, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        logger.error(f"保存注册机状态失败: {e}")


def _maybe_save_register_status(force: bool = False, min_interval_seconds: float = 1.0) -> None:
    """按节流间隔保存注册机状态，避免频繁磁盘写入。"""
    global _last_status_save_ts
    now = time.time()
    if force or (now - _last_status_save_ts) >= min_interval_seconds:
        _save_register_status()
        _last_status_save_ts = now


def _touch_register_status() -> None:
    """更新注册机状态的更新时间戳"""
    _register_status["updated_at"] = time.time()


def _ensure_register_status_fields(status: Dict[str, Any]) -> Dict[str, Any]:
    """保证注册机状态字段完整"""
    status.setdefault("running", False)
    status.setdefault("pid", None)
    status.setdefault("start_time", None)
    status.setdefault("updated_at", 0.0)
    stats = status.setdefault("stats", {})
    stats.setdefault("success_count", 0)
    stats.setdefault("total_attempts", 0)
    stats.setdefault("last_register_time", None)
    return status


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
                    logger.warning(f"进程 {status['pid']} 不存在，更新状态为停止")
                    status["running"] = False
                    status["pid"] = None
                    _touch_register_status()
                    _register_status.update(status)
                    _save_register_status()
                else:
                    # 进程存在，尝试获取进程名称确认
                    try:
                        proc = psutil.Process(status["pid"])
                        proc_name = proc.name()
                        logger.debug(f"进程 {status['pid']} 运行中: {proc_name}")
                    except Exception as e:
                        logger.warning(f"无法获取进程 {status['pid']} 信息: {e}")
            except ImportError:
                # 如果没有 psutil，跳过检查
                logger.warning("psutil 未安装，无法验证进程状态")
            except Exception as e:
                logger.error(f"检查进程状态失败: {e}")

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

        # 根据环境设置默认的 Solver URL
        default_solver_url = _default_solver_url()

        if not config:
            return {
                "success": True,
                "data": {
                    "duckmail_base_url": "https://api.duckmail.sbs",
                    "duckmail_api_key": "",
                    "email_domain": "",
                    "concurrent_threads": 3,
                    "turnstile_solver_url": default_solver_url,
                    "yescaptcha_key": "",
                    "proxy_url": "",
                    "proxy_secret_id": "",
                    "proxy_secret_key": "",
                    "proxy_host": "",
                    "proxy_port": "",
                    "proxy_scheme": "http"
                }
            }

        solver_url = _normalize_solver_url(config.get("TURNSTILE_SOLVER_URL"))
        return {
            "success": True,
            "data": {
                "duckmail_base_url": config.get("DUCKMAIL_BASE_URL", "https://api.duckmail.sbs"),
                "duckmail_api_key": config.get("DUCKMAIL_API_KEY", ""),
                "email_domain": config.get("EMAIL_DOMAIN", ""),
                "concurrent_threads": int(config.get("CONCURRENT_THREADS", "3")),
                "turnstile_solver_url": solver_url or default_solver_url,
                "yescaptcha_key": config.get("YESCAPTCHA_KEY", ""),
                "proxy_url": config.get("PROXY_URL", ""),
                "proxy_secret_id": config.get("PROXY_SECRET_ID", ""),
                "proxy_secret_key": config.get("PROXY_SECRET_KEY", ""),
                "proxy_host": config.get("PROXY_HOST", ""),
                "proxy_port": config.get("PROXY_PORT", ""),
                "proxy_scheme": config.get("PROXY_SCHEME", "http")
            }
        }
    except Exception as e:
        logger.error(f"获取注册机配置失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取配置失败: {e}"})


@router.post("/api/register/config")
async def save_register_config(request: RegisterConfigRequest, _: bool = Depends(verify_admin_session)) -> Dict[str, Any]:
    """保存注册机配置"""
    try:
        solver_url = _normalize_solver_url(request.turnstile_solver_url)
        config = {
            "DUCKMAIL_BASE_URL": request.duckmail_base_url,
            "DUCKMAIL_API_KEY": request.duckmail_api_key,
            "EMAIL_DOMAIN": request.email_domain,
            "CONCURRENT_THREADS": str(request.concurrent_threads),
            "TURNSTILE_SOLVER_URL": solver_url,
            "PROXY_URL": (request.proxy_url or "").strip(),
            "PROXY_SECRET_ID": (request.proxy_secret_id or "").strip(),
            "PROXY_SECRET_KEY": (request.proxy_secret_key or "").strip(),
            "PROXY_HOST": (request.proxy_host or "").strip(),
            "PROXY_PORT": str(request.proxy_port or "").strip(),
            "PROXY_SCHEME": (request.proxy_scheme or "http").strip()
        }
        if request.yescaptcha_key:
            config["YESCAPTCHA_KEY"] = request.yescaptcha_key

        _save_config(config)

        logger.info(f"注册机配置已更新: {request.duckmail_base_url}")
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
        solver_url = _normalize_solver_url(request.config.turnstile_solver_url)
        config = {
            "DUCKMAIL_BASE_URL": request.config.duckmail_base_url,
            "DUCKMAIL_API_KEY": request.config.duckmail_api_key,
            "EMAIL_DOMAIN": request.config.email_domain,
            "CONCURRENT_THREADS": str(request.config.concurrent_threads),
            "TURNSTILE_SOLVER_URL": solver_url,
            "PROXY_URL": (request.config.proxy_url or "").strip(),
            "PROXY_SECRET_ID": (request.config.proxy_secret_id or "").strip(),
            "PROXY_SECRET_KEY": (request.config.proxy_secret_key or "").strip(),
            "PROXY_HOST": (request.config.proxy_host or "").strip(),
            "PROXY_PORT": str(request.config.proxy_port or "").strip(),
            "PROXY_SCHEME": (request.config.proxy_scheme or "http").strip()
        }
        if request.config.yescaptcha_key:
            config["YESCAPTCHA_KEY"] = request.config.yescaptcha_key

        _save_config(config)

        # 启动注册机进程
        if not REGISTER_SCRIPT.exists():
            return {"success": False, "message": f"注册机脚本不存在: {REGISTER_SCRIPT}"}

        # 准备环境变量
        env = os.environ.copy()
        # 自动调整 Turnstile Solver URL（Docker 环境自动使用服务名）
        env["TURNSTILE_SOLVER_URL"] = solver_url
        env["DUCKMAIL_BASE_URL"] = request.config.duckmail_base_url
        env["DUCKMAIL_API_KEY"] = request.config.duckmail_api_key
        env["EMAIL_DOMAIN"] = request.config.email_domain
        env["CONCURRENT_THREADS"] = str(request.config.concurrent_threads)
        env["PROXY_URL"] = (request.config.proxy_url or "").strip()
        env["PROXY_SECRET_ID"] = (request.config.proxy_secret_id or "").strip()
        env["PROXY_SECRET_KEY"] = (request.config.proxy_secret_key or "").strip()
        env["PROXY_HOST"] = (request.config.proxy_host or "").strip()
        env["PROXY_PORT"] = str(request.config.proxy_port or "").strip()
        env["PROXY_SCHEME"] = (request.config.proxy_scheme or "http").strip()
        if request.config.yescaptcha_key:
            env["YESCAPTCHA_KEY"] = request.config.yescaptcha_key

        logger.info(f"[环境检测] 最终使用的 Solver URL: {solver_url}")

        # 准备日志文件 (清空旧日志)
        log_file = REGISTER_LOG_DIR / "register.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"--- 注册机启动于 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")

        # 启动进程
        process = subprocess.Popen(
            ["python", "-u", "grok.py"],  # 添加 -u 参数禁用缓冲
            cwd=str(PROJECT_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1  # 行缓冲
        )
        logger.info(f"注册机进程已创建，PID: {process.pid}, 环境变量: CONCURRENT_THREADS={env.get('CONCURRENT_THREADS')}, EMAIL_DOMAIN={env.get('EMAIL_DOMAIN')}")

        # 更新状态
        _register_status["running"] = True
        _register_status["pid"] = process.pid
        _register_status["start_time"] = datetime.now().isoformat()
        _register_status["stats"] = {
            "success_count": 0,
            "total_attempts": 0,
            "last_register_time": None
        }
        _touch_register_status()
        _save_register_status()

        # 启动日志读取任务（保存到全局变量）
        global _register_monitor_task
        _register_monitor_task = asyncio.create_task(_monitor_register_process(process, log_file))
        logger.info(f"日志监控任务已创建: {_register_monitor_task}")

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
        _touch_register_status()
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
    global _register_status

    try:
        logger.info(f"开始监控注册机进程 (PID: {process.pid}), 日志文件: {log_file}")
        line_count = 0
        # 用于批量推送日志的缓冲区
        log_buffer: List[str] = []
        buffer_size = 5  # 每5行推送一次

        # 使用线程读取 stdout，避免阻塞事件循环
        queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def _reader():
            try:
                if process.stdout is None:
                    return
                for line in process.stdout:
                    loop.call_soon_threadsafe(queue.put_nowait, line)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        asyncio.create_task(asyncio.to_thread(_reader))

        # 使用 'a' 模式继续追加（因为上面 start_register 已经创建/清空了文件）
        with open(log_file, 'a', encoding='utf-8') as f:
            while True:
                line = await queue.get()
                if line is None:
                    break
                line = line.strip()
                if not line:
                    continue

                # 写入文件并立即 flush
                f.write(f"{line}\n")
                f.flush()
                # 同时输出到 logger（便于调试）
                logger.info(f"[注册机] {line}")
                line_count += 1

                # 添加到日志缓冲区
                log_buffer.append(line)

                # 每写入 buffer_size 行或到达特定计数时推送
                if len(log_buffer) >= buffer_size or line_count % 10 == 0:
                    # 实时推送日志到 WebSocket 客户端
                    if ws_manager.active_connections:
                        asyncio.create_task(ws_manager.send_log_update(log_buffer.copy()))
                    log_buffer.clear()

                # 每写入 10 行日志记录一次
                if line_count % 10 == 0:
                    logger.info(f"已记录 {line_count} 行日志")

                # 解析日志更新统计，并推送状态更新
                stats_updated = await _parse_register_log(line, broadcast=True)
                if stats_updated and ws_manager.active_connections:
                    # 推送完整状态更新
                    asyncio.create_task(ws_manager.send_status_update(_register_status.copy()))

        # 推送剩余的日志
        if log_buffer and ws_manager.active_connections:
            asyncio.create_task(ws_manager.send_log_update(log_buffer))

        # 进程结束（放到线程避免阻塞）
        returncode = await asyncio.to_thread(process.wait)
        logger.info(f"注册机进程已退出 (PID: {process.pid}, 返回码: {returncode})")

        # 更新状态并推送
        _register_status["running"] = False
        _register_status["pid"] = None
        _touch_register_status()
        _save_register_status()

        # 推送最终状态
        if ws_manager.active_connections:
            asyncio.create_task(ws_manager.send_status_update(_register_status.copy()))

    except Exception as e:
        logger.error(f"监控注册机进程失败: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def _parse_register_log(line: str, broadcast: bool = False) -> bool:
    """解析注册机日志更新统计

    Args:
        line: 日志行
        broadcast: 是否广播更新（用于WebSocket推送）

    Returns:
        bool: 是否更新了统计信息
    """
    global _register_status

    # 检测成功注册 (仅匹配主成功的消息，避免子步骤重复计数)
    if "注册成功 | SSO:" in line:
        try:
            # 提取 SSO Token
            sso = line.split("SSO:")[1].strip()
            # 如果后面还有内容（比如平均时间），提取出 SSO
            if " " in sso:
                sso = sso.split(" ")[0]
            
            if sso:
                # 导入到 token_manager
                from app.services.grok.token import token_manager
                from app.models.grok_models import TokenType
                
                # 异步添加 Token
                await token_manager.add_token([sso], TokenType.NORMAL)
                logger.info(f"[注册监测] 已自动同步新 Token: {sso[:15]}...")
        except Exception as e:
            logger.error(f"[注册监测] 自动同步 Token 失败: {e}")

        _register_status["stats"]["success_count"] += 1
        _register_status["stats"]["last_register_time"] = datetime.now().isoformat()
        _register_status["stats"]["total_attempts"] += 1
        _touch_register_status()
        _maybe_save_register_status(force=not broadcast)
        return True
    elif "[-]" in line or "失败" in line:
        _register_status["stats"]["total_attempts"] += 1
        _touch_register_status()
        _maybe_save_register_status(force=not broadcast)
        return True
    return False


# === DuckMail 邮箱服务 API ===

@router.post("/api/register/duckmail/domains")
async def get_duckmail_domains(
    base_url: str = "",
    api_key: str = "",
    _: bool = Depends(verify_admin_session)
) -> Dict[str, Any]:
    """获取 DuckMail 可用域名列表"""
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from g import DuckMailClient

        client = DuckMailClient(
            base_url=base_url or "https://api.duckmail.sbs",
            api_key=api_key
        )

        domains = client.get_available_domains()
        return {
            "success": True,
            "data": {
                "domains": domains,
                "count": len(domains),
                "base_url": base_url or "https://api.duckmail.sbs"
            }
        }
    except Exception as e:
        logger.error(f"获取域名列表失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"获取域名失败: {e}"})


@router.post("/api/register/duckmail/test")
async def test_duckmail_connection(
    base_url: str = "",
    api_key: str = "",
    _: bool = Depends(verify_admin_session)
) -> Dict[str, Any]:
    """测试 DuckMail 连接"""
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from g import DuckMailClient

        client = DuckMailClient(
            base_url=base_url or "https://api.duckmail.sbs",
            api_key=api_key
        )

        result = client.test_connection()
        return {
            "success": result["success"],
            "data": result
        }
    except Exception as e:
        logger.error(f"测试连接失败: {e}")
        raise HTTPException(status_code=500, detail={"error": f"测试失败: {e}"})


# === WebSocket 端点 ===

@router.websocket("/ws/register")
async def websocket_register_updates(websocket: WebSocket):
    """注册机状态和日志实时推送 WebSocket"""
    # 导入 _sessions 用于验证（延迟导入避免循环）
    from app.api.admin.manage import _sessions

    # 验证会话
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=1008, reason="Missing token")
        return

    # 验证 token 有效性
    if token not in _sessions:
        await websocket.close(code=1008, reason="Invalid token")
        return

    # 连接管理
    await ws_manager.connect(websocket)
    try:
        # 立即发送当前状态
        current_status = _load_register_status()
        keys_data = await _read_generated_keys()
        await websocket.send_json({
            "type": "status_update",
            "data": {
                **current_status,
                "keys": keys_data
            }
        })

        # 保持连接并接收心跳
        while True:
            try:
                # 接收客户端消息（用于心跳）
                message = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if message == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # 超时则发送心跳
                await websocket.send_text("ping")
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        logger.info("[WebSocket] 客户端主动断开连接")
    except Exception as e:
        logger.error(f"[WebSocket] 错误: {e}")
    finally:
        ws_manager.disconnect(websocket)


async def auto_import_generated_tokens():
    """自动将 keys/grok.txt 中的 Token 导入到系统中（用于启动时同步）"""
    try:
        keys_file = KEYS_DIR / "grok.txt"
        if not keys_file.exists():
            return

        tokens = []
        with open(keys_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    tokens.append(line)

        if not tokens:
            return

        # 导入到 token_manager
        from app.services.grok.token import token_manager
        from app.models.grok_models import TokenType

        # 获取当前已有的 tokens 避免重复
        current_tokens = token_manager.get_tokens()
        normal_tokens = current_tokens.get(TokenType.NORMAL.value, {})
        super_tokens = current_tokens.get(TokenType.SUPER.value, {})
        
        new_tokens = [t for t in tokens if t not in normal_tokens and t not in super_tokens]
        
        if new_tokens:
            await token_manager.add_token(new_tokens, TokenType.NORMAL)
            logger.info(f"[启动自检] 自动同步已导入 {len(new_tokens)} 个新生成 Token")
    except Exception as e:
        logger.error(f"[启动自检] 自动同步 Token 失败: {e}")

