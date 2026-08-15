import json
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Response
from app.db.database import (
    get_emails, count_emails, get_email_by_id,
    mark_email_read, delete_email, clear_all_emails
)

router = APIRouter(prefix="/emails", tags=["Emails"])

@router.get("")
async def list_emails(
    to: Optional[str] = Query(None, description="收件人邮箱过滤"),
    from_addr: Optional[str] = Query(None, alias="from", description="发件人邮箱过滤"),
    search: Optional[str] = Query(None, description="全文关键字搜索 (主题/正文/发件人)"),
    is_read: Optional[bool] = Query(None, description="已读/未读过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(30, ge=1, le=100, description="每页条数")
):
    offset = (page - 1) * page_size
    items = await get_emails(
        to_address=to,
        from_address=from_addr,
        search=search,
        is_read=is_read,
        limit=page_size,
        offset=offset
    )
    total = await count_emails(
        to_address=to,
        from_address=from_addr,
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
    # Mark as read automatically when opened
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
async def batch_clear_emails(to: Optional[str] = Query(None, description="仅清空指定收件人的邮件")):
    deleted_count = await clear_all_emails(to_address=to)
    return {
        "success": True,
        "deleted_count": deleted_count
    }
