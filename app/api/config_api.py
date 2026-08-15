import yaml
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from app.core.config import settings, BASE_DIR
from app.engine.pipeline import process_incoming_email

router = APIRouter(prefix="/config", tags=["Configuration"])

class ConfigUpdateModel(BaseModel):
    api_key: Optional[str] = None
    imap_password: Optional[str] = None
    otp_keywords: Optional[List[str]] = None
    save_raw_eml: Optional[bool] = None

class TestEmailInjectModel(BaseModel):
    from_address: str = "service@apple.com"
    to_address: str = "my_user@mydomain.com"
    subject: str = "您的 Apple ID 验证码是 928301"
    body_text: str = "您好，您本次登录的 Apple ID 验证码为 928301，请在 10 分钟内完成验证。切勿将验证码告知他人。"
    body_html: Optional[str] = ""

@router.get("")
async def get_current_configuration():
    return {
        "success": True,
        "data": {
            "server": {
                "host": settings.server.host,
                "port": settings.server.port,
                "api_key": settings.server.api_key
            },
            "smtp": {
                "enabled": settings.smtp.enabled,
                "host": settings.smtp.host,
                "port": settings.smtp.port,
                "domain": settings.smtp.domain
            },
            "imap": {
                "enabled": settings.imap.enabled,
                "host": settings.imap.host,
                "port": settings.imap.port,
                "auth_password": settings.imap.auth_password
            },
            "storage": {
                "db_path": settings.storage.db_path,
                "save_raw_eml": settings.storage.save_raw_eml,
                "retention_days": settings.storage.retention_days
            },
            "otp": {
                "keywords": settings.otp.keywords
            }
        }
    }

@router.post("")
async def update_configuration(payload: ConfigUpdateModel):
    if payload.api_key is not None:
        settings.server.api_key = payload.api_key
    if payload.imap_password is not None:
        settings.imap.auth_password = payload.imap_password
    if payload.otp_keywords is not None:
        settings.otp.keywords = payload.otp_keywords
    if payload.save_raw_eml is not None:
        settings.storage.save_raw_eml = payload.save_raw_eml

    # Persist to config.yaml
    config_file = BASE_DIR / "config.yaml"
    try:
        config_data = {
            "server": settings.server.model_dump(),
            "smtp": settings.smtp.model_dump(),
            "imap": settings.imap.model_dump(),
            "storage": settings.storage.model_dump(),
            "otp": settings.otp.model_dump()
        }
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.safe_dump(config_data, f, allow_unicode=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置文件失败: {e}")

    return {
        "success": True,
        "message": "配置已成功保存并实时生效"
    }

@router.post("/test-inject")
async def inject_test_email(payload: TestEmailInjectModel):
    """用于在 UI 上一键模拟发送测试邮件，实时检验解析与取码效果"""
    raw_content = (
        f"From: {payload.from_address}\r\n"
        f"To: {payload.to_address}\r\n"
        f"Subject: {payload.subject}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"{payload.body_text}"
    )
    res = await process_incoming_email(
        raw_content=raw_content,
        recipient_override=payload.to_address,
        sender_override=payload.from_address
    )
    return {
        "success": True,
        "message": "测试邮件已成功注入系统",
        "result": res
    }
