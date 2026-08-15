from typing import Optional
from fastapi import Header, Query, HTTPException, status
from app.core.config import settings

async def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    api_key: Optional[str] = Query(None, alias="api_key")
):
    """
    可选的安全鉴权依赖：
    若系统配置了 server.api_key，则必须通过 Header 'X-API-Key' 或 Query 参数 'api_key' 提供匹配的秘钥。
    若系统未配置 api_key（留空），则自动跳过鉴权（方便内网和本地快速开发）。
    """
    configured_key = settings.server.api_key.strip()
    if not configured_key:
        return True

    provided_key = x_api_key or api_key
    if not provided_key or provided_key != configured_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或缺失 API 访问密钥 (Invalid API Key)",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return True
