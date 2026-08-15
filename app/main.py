import sys
from pathlib import Path

# Ensure root directory is in sys.path
BASE_ROOT = Path(__file__).resolve().parent.parent
if str(BASE_ROOT) not in sys.path:
    sys.path.insert(0, str(BASE_ROOT))

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings, BASE_DIR
from app.db.database import init_db, cleanup_expired_emails
from app.servers.smtp_server import smtp_manager
from app.servers.imap_server import imap_manager
from app.api.router import api_router

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
    logger.info("Shutdown complete.")

app = FastAPI(
    title="邮件接收与智能取码平台 (MailCapture & OTP Hub)",
    description="自动化多邮箱聚合接收、MIME解析、智能提取验证码与虚拟IMAP/REST API对接平台",
    version="1.0.0",
    lifespan=lifespan
)

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

# Mount static files
static_path = BASE_DIR / "app" / "static"
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = static_path / "index.html"
    return FileResponse(
        index_file,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"}
    )

@app.get("/mailboxes/{email_address}", include_in_schema=False)
async def serve_guest_mailbox_page(email_address: str):
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
