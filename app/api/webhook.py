from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Body
from app.engine.pipeline import process_incoming_email

router = APIRouter(prefix="/webhook", tags=["Inbound Webhook"])

@router.post("/inbound")
async def receive_inbound_webhook(request: Request):
    """
    通用邮件接收 Webhook 端点
    支持：
    1. Raw RFC822 EML (Content-Type: message/rfc822 或 text/plain)
    2. Cloudflare Email Worker / SendGrid / 自定义 JSON
       { "raw": "...", "to": "...", "from": "..." }
    3. Multipart 表单数据 (SendGrid/Mailgun 格式)
    """
    content_type = request.headers.get("content-type", "").lower()
    
    recipient_override = None
    sender_override = None
    forwarded_by_override = None
    raw_content = None

    if "application/json" in content_type:
        try:
            body_json = await request.json()
            raw_content = body_json.get("raw") or body_json.get("email") or body_json.get("content")
            recipient_override = body_json.get("to") or body_json.get("recipient")
            sender_override = body_json.get("from") or body_json.get("sender")
            forwarded_by_override = body_json.get("forwarded_by") or body_json.get("forwarder") or body_json.get("group")
            
            # If JSON doesn't contain raw EML but separate fields:
            if not raw_content and (body_json.get("subject") or body_json.get("body_text") or body_json.get("body_html")):
                subj = body_json.get("subject", "")
                text = body_json.get("body_text", "")
                html = body_json.get("body_html", "")
                raw_content = f"From: {sender_override or 'unknown'}\r\nTo: {recipient_override or 'unknown'}\r\nSubject: {subj}\r\nContent-Type: text/html; charset=utf-8\r\n\r\n{html or text}"
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON payload: {e}")

    elif "multipart/form-data" in content_type:
        try:
            form = await request.form()
            raw_content = form.get("email") or form.get("raw") or form.get("body-mime")
            recipient_override = form.get("to") or form.get("recipient")
            sender_override = form.get("from") or form.get("sender")
            forwarded_by_override = form.get("forwarded_by") or form.get("forwarder") or form.get("group")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid multipart form payload: {e}")
    else:
        # Assume raw stream
        raw_bytes = await request.body()
        raw_content = raw_bytes.decode("utf-8", errors="replace")

    if not raw_content:
        raise HTTPException(status_code=400, detail="No email content found in request payload")

    result = await process_incoming_email(
        raw_content=raw_content,
        recipient_override=str(recipient_override) if recipient_override else None,
        sender_override=str(sender_override) if sender_override else None,
        forwarded_by_override=str(forwarded_by_override) if forwarded_by_override else None
    )

    return {
        "success": True,
        "message": "Email successfully received and parsed",
        "result": result
    }
