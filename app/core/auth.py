import hmac
import hashlib
import time
import base64
import secrets
from typing import Optional
from fastapi import Header, Query, Request, HTTPException
from app.core.config import settings

# Ephemeral secret for signing tokens during runtime
_SESSION_SECRET = secrets.token_hex(32)

def is_auth_required() -> bool:
    """如果配置了 admin_password 或 api_key，则开启鉴权保护"""
    return bool((settings.server.admin_password and settings.server.admin_password.strip()) or 
                (settings.server.api_key and settings.server.api_key.strip()))

def verify_credentials(secret_input: str) -> bool:
    """验证输入的密码或 API Key 是否正确"""
    if not secret_input:
        return False
    
    admin_pass = (settings.server.admin_password or "").strip()
    api_key = (settings.server.api_key or "").strip()

    if admin_pass and hmac.compare_digest(secret_input, admin_pass):
        return True
    if api_key and hmac.compare_digest(secret_input, api_key):
        return True
    return False

def generate_auth_token(expire_seconds: int = 86400 * 7) -> str:
    """生成带时间戳和 HMAC 签名的安全会话 Token (默认有效期 7 天)"""
    expire_time = int(time.time()) + expire_seconds
    payload_str = f"admin:{expire_time}"
    sig_hex = hmac.new(_SESSION_SECRET.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
    token_str = f"{payload_str}.{sig_hex}"
    return base64.urlsafe_b64encode(token_str.encode("utf-8")).decode("utf-8").rstrip("=")

def verify_token(token: str) -> bool:
    """验证会话 Token 的有效性及是否过期"""
    if not token:
        return False
    try:
        padded = token + "=" * (-len(token) % 4)
        token_str = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        parts = token_str.rsplit(".", 1)
        if len(parts) != 2:
            return False
        payload_str, sig_hex = parts
        expected_sig = hmac.new(_SESSION_SECRET.encode("utf-8"), payload_str.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig_hex, expected_sig):
            return False

        # Check expiration
        _, expire_str = payload_str.split(":", 1)
        if int(expire_str) < time.time():
            return False
        return True
    except Exception:
        return False

async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token_query: Optional[str] = Query(None, alias="token"),
    api_key_query: Optional[str] = Query(None, alias="api_key"),
) -> bool:
    """FastAPI 依赖注入：检验请求合法性"""
    if not is_auth_required():
        return True

    # 1. 检验 X-API-Key 或 query 中的 api_key
    if x_api_key and verify_credentials(x_api_key):
        return True
    if api_key_query and verify_credentials(api_key_query):
        return True

    # 2. 检验 Bearer Token 或 query 中的 token
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    elif token_query:
        token = token_query

    if token:
        if verify_token(token) or verify_credentials(token):
            return True

    raise HTTPException(
        status_code=401,
        detail="Unauthorized: Authentication required",
        headers={"WWW-Authenticate": "Bearer"}
    )
