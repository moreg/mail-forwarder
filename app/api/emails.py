import json
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Response
from app.db.database import (
    get_emails, count_emails, get_email_by_id,
    mark_email_read, delete_email, clear_all_emails, delete_mailboxes
)
from pydantic import BaseModel

class BatchDeleteMailboxesRequest(BaseModel):
    mailboxes: list[str]

router = APIRouter(prefix="/emails", tags=["Emails"])

@router.get("")
async def list_emails(
    to: Optional[str] = Query(None, description="收件人邮箱过滤"),
    from_addr: Optional[str] = Query(None, alias="from", description="发件人邮箱过滤"),
    group: Optional[str] = Query(None, description="按转发母账号/分组过滤 (如 apple01@icloud.com 或 直接收件)"),
    service: Optional[str] = Query(None, description="按识别到的服务商分类过滤 (例如 Apple, Google, Telegram)"),
    search: Optional[str] = Query(None, description="全文关键字搜索 (主题/正文/发件人/转发源)"),
    is_read: Optional[bool] = Query(None, description="已读/未读过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(30, ge=1, le=100, description="每页条数")
):
    offset = (page - 1) * page_size
    items = await get_emails(
        to_address=to,
        from_address=from_addr,
        forwarded_by=group,
        service_name=service,
        search=search,
        is_read=is_read,
        limit=page_size,
        offset=offset
    )
    total = await count_emails(
        to_address=to,
        from_address=from_addr,
        forwarded_by=group,
        service_name=service,
        search=search,
        is_read=is_read
    )
    return {
        "success": True,
        "page": page,
        "page_size": page_size,
        "total": total,
        "data": items
    }

@router.get("/{email_id}")
async def get_single_email(email_id: int):
    item = await get_email_by_id(email_id)
    if not item:
        raise HTTPException(status_code=404, detail="Email not found")
    # Only mark as read in DB if it was unread to avoid unnecessary disk write/commits
    if not item.get("is_read"):
        await mark_email_read(email_id, True)
        item["is_read"] = 1
    return {
        "success": True,
        "data": item
    }

@router.get("/{email_id}/raw")
async def download_raw_eml(email_id: int):
    item = await get_email_by_id(email_id)
    if not item or not item.get("raw_eml"):
        raise HTTPException(status_code=404, detail="Raw EML not found")
    return Response(
        content=item["raw_eml"],
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="email_{email_id}.eml"'}
    )

@router.post("/{email_id}/read")
async def toggle_read_status(email_id: int, is_read: bool = Query(True)):
    success = await mark_email_read(email_id, is_read)
    return {"success": success}

@router.delete("/{email_id}")
async def delete_single_email(email_id: int):
    success = await delete_email(email_id)
    return {"success": success}

@router.delete("")
async def batch_clear_emails(
    to: Optional[str] = Query(None, description="仅清空指定收件人的邮件"),
    group: Optional[str] = Query(None, description="仅清空指定转发分组的邮件")
):
    deleted_count = await clear_all_emails(to_address=to, forwarded_by=group)
    return {
        "success": True,
        "deleted_count": deleted_count
    }

@router.post("/batch-delete-mailboxes")
async def batch_delete_mailboxes_endpoint(req: BatchDeleteMailboxesRequest):
    """批量删除指定的收件人邮箱及其所有关联邮件与验证码"""
    if not req.mailboxes:
        return {"success": True, "deleted_count": 0, "message": "未指定要删除的邮箱"}
    deleted_count = await delete_mailboxes(req.mailboxes)
    return {
        "success": True,
        "deleted_count": deleted_count,
        "deleted_mailboxes": req.mailboxes
    }
