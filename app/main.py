import sys
from pathlib import Path

# Ensure root directory is in sys.path
BASE_ROOT = Path(__file__).resolve().parent.parent
if str(BASE_ROOT) not in sys.path:
    sys.path.insert(0, str(BASE_ROOT))

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings, BASE_DIR
from app.db.database import init_db, cleanup_expired_emails, close_db
from app.servers.smtp_server import smtp_manager
from app.servers.imap_server import imap_manager
from app.api.router import api_router
from app.api.guest import guest_special_code_payload

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("mail_system")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing Mail Ingestion & OTP Platform...")
    await init_db()
    
    # Auto cleanup expired emails based on retention_days
    try:
        cleaned = await cleanup_expired_emails()
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired emails on startup.")
    except Exception as e:
        logger.warning(f"Error during retention cleanup: {e}")
    
    # Start background SMTP server
    smtp_manager.start()
    
    # Start background IMAP server
    await imap_manager.start()
    
    logger.info(f"System ready! Web Dashboard: http://{settings.server.host}:{settings.server.port}")
    yield
    
    # Shutdown
    logger.info("Shutting down servers...")
    smtp_manager.stop()
    await imap_manager.stop()
    await close_db()
    logger.info("Shutdown complete.")

app = FastAPI(
    title="邮件接收与智能取码平台 (MailCapture & OTP Hub)",
    description="自动化多邮箱聚合接收、MIME解析、智能提取验证码与虚拟IMAP/REST API对接平台",
    version="1.0.0",
    lifespan=lifespan
)

# GZip compression middleware (compresses responses > 500 bytes)
app.add_middleware(GZipMiddleware, minimum_size=500)

# CORS middleware for open API access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)

class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=86400"
        return response

# Mount static files
static_path = BASE_DIR / "app" / "static"
app.mount("/static", CachedStaticFiles(directory=str(static_path)), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = static_path / "index.html"
    return FileResponse(
        index_file,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    )

@app.get("/mailboxes/{email_address}", include_in_schema=False)
@app.get("/mail/{email_address}", include_in_schema=False)
@app.get("/m/{email_address}", include_in_schema=False)
async def serve_guest_mailbox_page(email_address: str, fmt: Optional[str] = Query(None, alias="format")):
    # 特殊取码格式：注册工具直连短链拿精简 JSON（与 iCloud 隐私邮箱面板 ?format=special 对齐）
    if (fmt or "").strip().lower() == "special":
        return await guest_special_code_payload(email_address)
    mailbox_html = static_path / "mailbox.html"
    return FileResponse(
        mailbox_html,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=False
    )
