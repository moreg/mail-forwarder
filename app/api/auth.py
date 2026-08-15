from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, Query, Request
from app.core.auth import (
    is_auth_required, verify_credentials, generate_auth_token,
    verify_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    password: Optional[str] = ""
    api_key: Optional[str] = ""

@router.get("/status")
async def get_auth_status(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    token_query: Optional[str] = Query(None, alias="token"),
):
    """获取系统鉴权状态及当前请求是否已通过验证"""
    auth_req = is_auth_required()
    if not auth_req:
        return {
            "success": True,
            "auth_required": False,
            "logged_in": True
        }

    logged_in = False
    if x_api_key and verify_credentials(x_api_key):
        logged_in = True
    else:
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        elif token_query:
            token = token_query
        
        if token and (verify_token(token) or verify_credentials(token)):
            logged_in = True

    return {
        "success": True,
        "auth_required": True,
        "logged_in": logged_in
    }

@router.post("/login")
async def login(payload: LoginRequest):
    """管理员登录接口：提交管理员密码或 API Key 换取有效 Token"""
    if not is_auth_required():
        # 免鉴权模式直接返回成功 Token
        token = generate_auth_token()
        return {
            "success": True,
            "message": "免鉴权模式，登录成功",
            "token": token
        }

    candidate = (payload.password or payload.api_key or "").strip()
    if not verify_credentials(candidate):
        raise HTTPException(
            status_code=401,
            detail="密码或 API Key 错误，请重新输入"
        )

    token = generate_auth_token()
    return {
        "success": True,
        "message": "登录成功",
        "token": token
    }

@router.post("/logout")
async def logout():
    """退出登录"""
    return {
        "success": True,
        "message": "已退出登录"
    }
