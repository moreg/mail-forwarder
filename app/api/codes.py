import asyncio
import time
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from app.db.database import get_latest_code, get_codes

router = APIRouter(prefix="/codes", tags=["Verification Codes"])

@router.get("/latest")
async def get_latest_verification_code(
    to: Optional[str] = Query(None, description="接收邮箱别名/完整地址 (支持模糊匹配，如 user@domain.com 或 user)"),
    group: Optional[str] = Query(None, description="转发母账号/分组名称过滤 (如 apple01@icloud.com)"),
    service: Optional[str] = Query(None, description="特定服务名称过滤，例如 Apple, Google, Telegram"),
    after_id: Optional[int] = Query(None, description="仅返回 ID 大于此值的最新验证码"),
    timeout: int = Query(0, ge=0, le=60, description="长轮询等待超时秒数 (0~60秒)，在等待期间若有新码到达立即返回")
):
    """
    极速取码接口 (专为脚本、Bot与自动化任务设计)
    支持按收件别名(to)或转发母账号分组(group)取码，并支持长轮询挂起等待。
    """
    if not to and not group and not service:
        # Default empty to allows fetching any latest code
        pass

    start_time = time.time()
    
    while True:
        record = await get_latest_code(
            to_address=to,
            forwarded_by=group,
            service_name=service,
            after_id=after_id
        )
        if record:
            return {
                "success": True,
                "found": True,
                "code": record["code"],
                "code_type": record["code_type"],
                "service_name": record["service_name"],
                "verification_url": record.get("verification_url", ""),
                "to_address": record["to_address"],
                "forwarded_by": record.get("forwarded_by", ""),
                "group_name": record.get("group_name", ""),
                "from_address": record.get("from_address", ""),
                "subject": record.get("subject", ""),
                "created_at": record["created_at"],
                "context_snippet": record.get("context_snippet", ""),
                "email_id": record["email_id"],
                "code_id": record["id"]
            }

        elapsed = time.time() - start_time
        if elapsed >= timeout or timeout == 0:
            break

        # Wait 1 second before next poll check
        await asyncio.sleep(1.0)

    target_desc = f"'{to or group or '任意'}'"
    return {
        "success": True,
        "found": False,
        "code": None,
        "message": f"在指定时间 ({timeout}s) 内未找到匹配 {target_desc} 的新验证码"
    }

@router.get("")
async def list_verification_codes(
    to: Optional[str] = Query(None, description="收件人过滤"),
    group: Optional[str] = Query(None, description="转发母账号/分组过滤"),
    service: Optional[str] = Query(None, description="服务名称过滤"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """获取所有历史提取到的验证码列表"""
    codes = await get_codes(
        to_address=to,
        forwarded_by=group,
        service_name=service,
        limit=limit,
        offset=offset
    )
    return {
        "success": True,
        "total": len(codes),
        "data": codes
    }
