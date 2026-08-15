from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from app.db.database import get_forwarding_groups_hierarchy, clear_all_emails

router = APIRouter(prefix="/groups", tags=["Forwarding Groups"])

@router.get("")
async def list_forwarding_groups():
    """
    获取所有转发母邮箱分组及其下属收件别名的层级数据树
    专为控制台侧边栏与访客取件页面 (Visitor Pickup Page) 设计
    """
    groups = await get_forwarding_groups_hierarchy()
    return {
        "success": True,
        "total": len(groups),
        "data": groups
    }

@router.get("/{group_name}/aliases")
async def list_group_aliases(group_name: str):
    """获取指定转发母邮箱分组下的所有别名列表"""
    groups = await get_forwarding_groups_hierarchy()
    for g in groups:
        if g["group_id"].lower() == group_name.lower() or g["group_name"].lower() == group_name.lower():
            return {
                "success": True,
                "group": g["group_name"],
                "data": g["aliases"]
            }
    return {
        "success": True,
        "group": group_name,
        "data": []
    }

@router.delete("/{group_name}/emails")
async def clear_group_emails(group_name: str):
    """清空指定转发分组下的所有邮件与验证码"""
    deleted_count = await clear_all_emails(forwarded_by=group_name)
    return {
        "success": True,
        "group": group_name,
        "deleted_count": deleted_count
    }
