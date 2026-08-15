import asyncio
import imaplib
import pytest
from app.core.config import settings
from app.db.database import init_db, clear_all_emails
from app.engine.pipeline import process_incoming_email
from app.servers.imap_server import imap_manager

@pytest.mark.asyncio
async def test_virtual_imap_server_integration():
    await init_db()
    await clear_all_emails()
    
    # Ingest a sample email
    sample_email = (
        "From: noreply@apple.com\r\n"
        "To: user_imap_test@domain.com\r\n"
        "Subject: Apple ID Verification Code\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Your code is 654321."
    )
    await process_incoming_email(raw_content=sample_email)

    # Start IMAP Server
    await imap_manager.start()
    await asyncio.sleep(0.3)

    try:
        def run_imap_client():
            # Connect to 127.0.0.1
            client = imaplib.IMAP4("127.0.0.1", settings.imap.port)
            # Login
            resp = client.login("user_imap_test@domain.com", settings.imap.auth_password)
            assert resp[0] == "OK"

            # Select INBOX
            resp, count = client.select("INBOX")
            assert resp == "OK"
            assert int(count[0]) >= 1

            # Search ALL
            resp, data = client.search(None, "ALL")
            assert resp == "OK"
            msg_ids = data[0].split()
            assert len(msg_ids) >= 1

            # Fetch RFC822
            latest_id = msg_ids[-1]
            resp, msg_data = client.fetch(latest_id, "(RFC822)")
            assert resp == "OK"
            raw_content = msg_data[0][1].decode("utf-8")
            assert "654321" in raw_content

            client.logout()

        await asyncio.to_thread(run_imap_client)
    finally:
        await imap_manager.stop()
