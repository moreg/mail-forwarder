import json
import asyncio
import time
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse
from app.core.config import settings, BASE_DIR
from app.core.timeutil import utc_str_to_epoch as _utc_str_to_epoch
from app.core.timeutil import utc_str_to_rfc3339
from app.db.database import (
    get_emails, count_emails, get_email_by_id, get_latest_code, get_codes
)
from app.core.events import broadcaster

router = APIRouter(prefix="/mailboxes", tags=["Guest Mailbox"])

# 特殊取码格式（format=special）中 from 字段的固定值，与注册工具约定一致，
# 不随邮件实际发件人变化。
SPECIAL_CODE_FROM = "OpenAI"


async def guest_special_code_payload(email_address: str) -> dict:
    """特殊取码格式：与 iCloud 隐私邮箱面板短链 ?format=special 对齐，
    固定只返回 code/receivedAt/to/from 四个字段：code 为验证码、receivedAt 为
    收件时间（UTC RFC3339）、to 为当前邮箱、from 为固定值；暂无验证码时
    code/receivedAt 为空串，结构始终不变，便于注册工具用同一套结构轮询解析。"""
    record = await get_latest_code(to_address=email_address)
    if not record:
        return {"code": "", "receivedAt": "", "to": email_address, "from": SPECIAL_CODE_FROM}
    return {
        "code": record["code"],
        "receivedAt": utc_str_to_rfc3339(record["created_at"]) or "",
        "to": record.get("to_address") or email_address,
        "from": SPECIAL_CODE_FROM,
    }


def _guest_code_payload(record: dict) -> dict:
    """latest-code 响应体；time 为 epoch 秒，供取码客户端做新旧过滤。"""
    return {
        "success": True,
        "found": True,
        "code": record["code"],
        "code_type": record["code_type"],
        "service_name": record["service_name"],
        "verification_url": record.get("verification_url", ""),
        "to_address": record["to_address"],
        "from_address": record.get("from_address", ""),
        "subject": record.get("subject", ""),
        "created_at": record["created_at"],
        "time": _utc_str_to_epoch(record["created_at"]),
        "context_snippet": record.get("context_snippet", ""),
        "email_id": record["email_id"],
        "code_id": record["id"]
    }

@router.get("/{email_address}")
async def get_guest_mailbox_data(
    email_address: str,
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    search: Optional[str] = Query(None),
    fmt: Optional[str] = Query(None, alias="format")
):
    """
    访客邮箱接口：
    - 若浏览器直接访问 (Accept: text/html)，返回访客取件页面 HTML。
    - 若 API / 脚本请求，返回该邮箱的邮件列表及统计数据 JSON。
    - ?format=special 时优先返回特殊取码格式（code/receivedAt/to/from）。
    """
    # 特殊取码格式优先于 Accept 协商，注册工具直连短链即拿精简 JSON
    if (fmt or "").strip().lower() == "special":
        return await guest_special_code_payload(email_address)

    accept_header = request.headers.get("accept", "").lower()
    if "text/html" in accept_header:
        mailbox_html_file = BASE_DIR / "app" / "static" / "mailbox.html"
        return FileResponse(
            mailbox_html_file,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
        )

    offset = (page - 1) * page_size
    emails, total, latest_otp = await asyncio.gather(
        get_emails(
            to_address=email_address,
            search=search,
            limit=page_size,
            offset=offset
        ),
        count_emails(to_address=email_address, search=search),
        get_latest_code(to_address=email_address)
    )

    code_val = latest_otp["code"] if latest_otp else None
    created_at_val = latest_otp["created_at"] if latest_otp else (emails[0]["created_at"] if emails else None)
    # received_at / time 是取码客户端（generic_api 渠道）消费的新旧过滤字段，
    # 必须是 epoch 秒；created_at 保留 UTC 字符串供前端展示。
    epoch_val = _utc_str_to_epoch(created_at_val)
    service_val = latest_otp["service_name"] if latest_otp else None
    subject_val = latest_otp.get("subject") if latest_otp else (emails[0]["subject"] if emails else "")

    formatted_messages = []
    for e in emails:
        msg_item = dict(e)
        msg_item["code"] = e.get("latest_code") or ""
        msg_item["otp"] = e.get("latest_code") or ""
        msg_item["received_at"] = _utc_str_to_epoch(e.get("created_at")) or ""
        msg_item["time"] = msg_item["received_at"]
        formatted_messages.append(msg_item)

    return {
        "success": True,
        "mailbox": email_address,
        "code": code_val,
        "otp": code_val,
        "created_at": created_at_val,
        "received_at": epoch_val or "",
        "time": epoch_val or "",
        "service": service_val,
        "subject": subject_val,
        "total_emails": total,
        "page": page,
        "page_size": page_size,
        "latest_code": latest_otp,
        "messages": formatted_messages,
        "mails": formatted_messages,
        "items": formatted_messages,
        "data": formatted_messages
    }

@router.get("/{email_address}/latest-code")
async def get_guest_latest_code(
    email_address: str,
    service: Optional[str] = Query(None),
    after_id: Optional[int] = Query(None),
    timeout: int = Query(0, ge=0, le=60)
):
    """
    访客专属极速取码接口 (支持事件驱动瞬时响应与长轮询挂起)
    """
    # 1. 首次快速查询已有记录
    record = await get_latest_code(
        to_address=email_address,
        service_name=service,
        after_id=after_id
    )
    if record:
        return _guest_code_payload(record)

    if timeout <= 0:
        return {
            "success": True,
            "found": False,
            "code": None,
            "message": f"未收到匹配 '{email_address}' 的新验证码"
        }

    # 2. 响应式事件驱动挂起等待
    start_time = time.time()
    queue = broadcaster.subscribe()
    try:
        while True:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                break

            try:
                await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            record = await get_latest_code(
                to_address=email_address,
                service_name=service,
                after_id=after_id
            )
            if record:
                return _guest_code_payload(record)
    finally:
        broadcaster.unsubscribe(queue)

    return {
        "success": True,
        "found": False,
        "code": None,
        "message": f"在指定时间 ({timeout}s) 内未收到匹配 '{email_address}' 的新验证码"
    }

@router.get("/{email_address}/emails/{email_id}")
async def get_guest_single_email(email_address: str, email_id: int):
    """
    访客读取单封邮件详情 (带安全性校验：确保邮件收件人属于该邮箱)
    """
    item = await get_email_by_id(email_id)
    if not item:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # 安全性检查：收件人必须与 URL 中的 email_address 匹配（忽略大小写）
    if email_address.lower() not in item["to_address"].lower():
        raise HTTPException(status_code=403, detail="Access denied: Email does not belong to this mailbox")

    return {
        "success": True,
        "data": item
    }

@router.get("/{email_address}/emails/{email_id}/raw")
async def download_guest_raw_eml(email_address: str, email_id: int):
    """访客下载指定邮件的 EML 原始报文"""
    item = await get_email_by_id(email_id)
    if not item or not item.get("raw_eml"):
        raise HTTPException(status_code=404, detail="Raw EML not found")
    if email_address.lower() not in item["to_address"].lower():
        raise HTTPException(status_code=403, detail="Access denied")

    return Response(
        content=item["raw_eml"],
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="email_{email_id}.eml"'}
    )

@router.get("/{email_address}/stream")
async def guest_email_stream(email_address: str, request: Request):
    """
    访客专属实时 SSE 推送流：当有新邮件发往该邮箱时，秒级推送到前端页面
    """
    target_addr = email_address.strip().lower()

    async def event_generator():
        client_queue = broadcaster.subscribe()
        try:
            # First ping
            yield "event: ping\ndata: connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(client_queue.get(), timeout=15.0)
                    event_data = event.get("data", {}) if isinstance(event, dict) else {}
                    recipient = str(event_data.get("to_address", "")).lower()
                    if target_addr in recipient:
                        payload_json = json.dumps(event_data, ensure_ascii=False)
                        yield f"event: {event.get('event', 'new_email')}\ndata: {payload_json}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            broadcaster.unsubscribe(client_queue)

    return Response(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
