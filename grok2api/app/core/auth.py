"""认证模块 - API令牌验证"""

from typing import Optional, Dict
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.config import setting
from app.core.logger import logger
from app.services.api_keys import api_key_manager


# Bearer安全方案
security = HTTPBearer(auto_error=False)


def _build_error(message: str, code: str = "invalid_token") -> dict:
    """构建认证错误"""
    return {
        "error": {
            "message": message,
            "type": "authentication_error",
            "code": code
        }
    }


class AuthManager:
    """认证管理器 - 验证API令牌"""

    @staticmethod
    async def verify(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> Dict:
        """验证令牌，返回 Key 信息"""
        api_key = setting.grok_config.get("api_key")
        
        # 初始化检查
        if not hasattr(api_key_manager, '_keys'):
           await api_key_manager.init()

        # 检查令牌
        if not credentials:
            # 如果未设置全局Key且没有多Key，则跳过（开发模式）
            if not api_key and not api_key_manager.get_all_keys():
                logger.debug("[Auth] 未设置API_KEY，跳过验证")
                return {"key": None, "name": "Anonymous"}
                
            raise HTTPException(
                status_code=401,
                detail=_build_error("缺少认证令牌", "missing_token")
            )

        token = credentials.credentials
        
        # 验证令牌 (支持多 Key)
        key_info = api_key_manager.validate_key(token)
        
        if key_info:
            return key_info

        raise HTTPException(
            status_code=401,
            detail=_build_error(f"令牌无效，长度: {len(token)}", "invalid_token")
        )


# 全局实例
auth_manager = AuthManager()