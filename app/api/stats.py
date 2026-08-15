from fastapi import APIRouter
from app.db.database import get_mailbox_stats
from app.core.config import settings

router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("")
async def get_system_statistics():
    stats = await get_mailbox_stats()
    stats["config"] = {
        "smtp_enabled": settings.smtp.enabled,
        "smtp_port": settings.smtp.port,
        "imap_enabled": settings.imap.enabled,
        "imap_port": settings.imap.port,
        "api_port": settings.server.port
    }
    return {
        "success": True,
        "data": stats
    }
