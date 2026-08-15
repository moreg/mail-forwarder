import asyncio
import logging
import sys
from aiosmtpd.controller import Controller
from aiosmtpd.smtp import Envelope, Session, SMTP
from app.core.config import settings
from app.engine.pipeline import process_incoming_email

logger = logging.getLogger("smtp_server")

class MailHandler:
    async def handle_DATA(self, server: SMTP, session: Session, envelope: Envelope) -> str:
        peer = session.peer
        logger.info(f"Incoming SMTP connection from {peer}, from: {envelope.mail_from}, to: {envelope.rcpt_tos}")
        
        try:
            content = envelope.content
            recipients = envelope.rcpt_tos or ["unknown@localhost"]
            sender = envelope.mail_from or ""

            for rcpt in recipients:
                await process_incoming_email(
                    raw_content=content,
                    recipient_override=rcpt,
                    sender_override=sender
                )
            
            return "250 Message accepted for delivery"
        except Exception as e:
            logger.error(f"Error processing incoming SMTP mail: {e}", exc_info=True)
            return "451 Requested action aborted: error in processing"

class SmtpServerManager:
    def __init__(self):
        self.controller = None

    def start(self):
        if not settings.smtp.enabled:
            logger.info("SMTP server is disabled in config.")
            return

        handler = MailHandler()
        # On Windows, aiosmtpd's internal readiness check connects to hostname;
        # connecting to 0.0.0.0 fails on Windows, so we bind to 127.0.0.1 for local or explicit IP.
        bind_host = settings.smtp.host
        if sys.platform == "win32" and bind_host == "0.0.0.0":
            bind_host = "127.0.0.1"

        self.controller = Controller(
            handler,
            hostname=bind_host,
            port=settings.smtp.port,
            ready_timeout=5.0
        )
        try:
            self.controller.start()
            logger.info(f"SMTP Server started on {bind_host}:{settings.smtp.port}")
        except Exception as e:
            logger.error(f"Failed to start SMTP Server on port {settings.smtp.port}: {e}")

    def stop(self):
        if self.controller:
            try:
                self.controller.stop()
                logger.info("SMTP Server stopped.")
            except Exception as e:
                logger.error(f"Error stopping SMTP Server: {e}")

smtp_manager = SmtpServerManager()
