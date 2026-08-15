import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.core.events import broadcaster
from app.db.database import save_email, save_verification_code, get_email_by_id
from app.db.models import EmailCreate, VerificationCodeCreate
from app.engine.parser import parse_raw_email, ParsedEmail
from app.engine.otp_extractor import extract_otp_from_email

async def process_incoming_email(
    raw_content: str | bytes,
    recipient_override: Optional[str] = None,
    sender_override: Optional[str] = None,
    forwarded_by_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    统一邮件处理流水线：
    1. MIME 深度解析 (含转发来源母账号识别)
    2. 入库保存
    3. 提取验证码并关联入库
    4. 触发实时 SSE 广播
    """
    parsed: ParsedEmail = parse_raw_email(
        raw_content,
        default_to=recipient_override or "",
        default_forwarded_by=forwarded_by_override or ""
    )

    final_to = recipient_override if recipient_override else parsed.to_address
    final_from = sender_override if sender_override else parsed.from_address
    final_forwarded_by = forwarded_by_override if forwarded_by_override else parsed.forwarded_by

    email_create = EmailCreate(
        message_id=parsed.message_id,
        from_address=final_from,
        to_address=final_to,
        forwarded_by=final_forwarded_by,
        group_name=final_forwarded_by or "直接收件",
        subject=parsed.subject,
        body_text=parsed.body_text,
        body_html=parsed.body_html,
        raw_eml=parsed.raw_eml,
        has_attachments=parsed.has_attachments,
        attachments_json=json.dumps(parsed.attachments, ensure_ascii=False),
        received_at=datetime.now(timezone.utc)
    )

    email_id = await save_email(email_create)

    # Extract OTPs
    extracted_codes = extract_otp_from_email(
        subject=parsed.subject,
        body_text=parsed.body_text,
        from_address=final_from,
        body_html=parsed.body_html
    )

    saved_codes = []
    for otp in extracted_codes:
        code_create = VerificationCodeCreate(
            email_id=email_id,
            to_address=final_to,
            code=otp.code,
            code_type=otp.code_type,
            service_name=otp.service_name,
            verification_url=otp.verification_url,
            context_snippet=otp.context_snippet
        )
        code_id = await save_verification_code(code_create)
        saved_codes.append({
            "id": code_id,
            "code": otp.code,
            "code_type": otp.code_type,
            "service_name": otp.service_name,
            "verification_url": otp.verification_url,
            "context_snippet": otp.context_snippet
        })

    # Broadcast event to active Web UI / SSE clients
    event_data = {
        "id": email_id,
        "from_address": final_from,
        "to_address": final_to,
        "forwarded_by": final_forwarded_by,
        "group_name": final_forwarded_by or "直接收件",
        "subject": parsed.subject,
        "body_preview": (parsed.body_text[:120] + "...") if len(parsed.body_text) > 120 else parsed.body_text,
        "codes": saved_codes,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    }
    await broadcaster.broadcast("new_email", event_data)

    return {
        "email_id": email_id,
        "from_address": final_from,
        "to_address": final_to,
        "forwarded_by": final_forwarded_by,
        "group_name": final_forwarded_by or "直接收件",
        "subject": parsed.subject,
        "codes": saved_codes
    }
