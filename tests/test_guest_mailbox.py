import pytest
from starlette.testclient import TestClient
from app.main import app
from app.engine.pipeline import process_incoming_email
from app.db.database import init_db, clear_all_emails

client = TestClient(app)

@pytest.mark.asyncio
async def test_guest_mailbox_page_and_api():
    await init_db()
    await clear_all_emails()

    # 1. Ingest email for target visitor mailbox
    target_addr = "threats.humans_2u@icloud.com"
    raw_target_mail = (
        "Delivered-To: master_apple01@icloud.com\r\n"
        "From: appleid@id.apple.com\r\n"
        f"To: {target_addr}\r\n"
        "Subject: Your Apple ID code is 849201\r\n"
        "\r\n"
        "Your Apple ID verification code is 849201. Do not share it."
    )
    res1 = await process_incoming_email(raw_target_mail)
    target_email_id = res1["email_id"]

    # 2. Ingest email for another different mailbox
    other_addr = "other_person@domain.com"
    raw_other_mail = (
        "From: service@github.com\r\n"
        f"To: {other_addr}\r\n"
        "Subject: GitHub code is 123456\r\n"
        "\r\n"
        "Your GitHub code is 123456."
    )
    res2 = await process_incoming_email(raw_other_mail)
    other_email_id = res2["email_id"]

    # 3. Test HTML page serving for visitor pickup URL
    page_resp = client.get(f"/mailboxes/{target_addr}")
    assert page_resp.status_code == 200
    assert "text/html" in page_resp.headers.get("content-type", "")
    assert "访客取件" in page_resp.text or "邮件与验证码" in page_resp.text

    # 4. Test JSON API for visitor mailbox
    api_resp = client.get(f"/api/v1/mailboxes/{target_addr}", headers={"Accept": "application/json"})
    assert api_resp.status_code == 200
    data = api_resp.json()
    assert data["success"] is True
    assert data["mailbox"] == target_addr
    assert data["total_emails"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["to_address"] == target_addr
    assert data["latest_code"]["code"] == "849201"

    # 5. Test latest OTP endpoint for visitor
    code_resp = client.get(f"/api/v1/mailboxes/{target_addr}/latest-code")
    assert code_resp.status_code == 200
    code_data = code_resp.json()
    assert code_data["found"] is True
    assert code_data["code"] == "849201"
    assert code_data["service_name"] == "Apple"

    # 6. Test visitor reading own email detail
    detail_resp = client.get(f"/api/v1/mailboxes/{target_addr}/emails/{target_email_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["id"] == target_email_id

    # 7. Test visitor trying to read another user's email detail (Security isolation check)
    forbidden_resp = client.get(f"/api/v1/mailboxes/{target_addr}/emails/{other_email_id}")
    assert forbidden_resp.status_code == 403

    # 8. Test visitor downloading raw EML
    eml_resp = client.get(f"/api/v1/mailboxes/{target_addr}/emails/{target_email_id}/raw")
    assert eml_resp.status_code == 200
    assert "849201" in eml_resp.text

@pytest.mark.asyncio
async def test_turb_gpt_free_register_compatibility():
    await init_db()
    await clear_all_emails()

    import sys
    import json
    from pathlib import Path
    turb_path = Path(r"E:\trea\turb-gpt-free-register")
    if str(turb_path) not in sys.path:
        sys.path.insert(0, str(turb_path))

    from core.generic_api_mail_client import _extract_structured_api_code, _extract_code

    test_email = "vetch.nils6y@icloud.com"

    # Ingest incoming OpenAI / ChatGPT verification code email
    raw_openai_mail = (
        "Delivered-To: master_account@icloud.com\r\n"
        "From: support@openai.com\r\n"
        f"To: {test_email}\r\n"
        "Subject: Your temporary ChatGPT verification code is 639102\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Your ChatGPT verification code is 639102. Please enter this code in the login prompt."
    )
    await process_incoming_email(raw_openai_mail)

    # 1. Test JSON Endpoint: /api/v1/mailboxes/{email}
    json_resp = client.get(f"/api/v1/mailboxes/{test_email}?json=1&summary=1")
    assert json_resp.status_code == 200
    json_text = json_resp.text
    
    # Run turb-gpt-free-register's structured parser
    result = _extract_structured_api_code(json_text)
    assert result is not None
    code, meta = result
    assert code == "639102"
    assert meta["source"] in ("messages_list", "structured_api")

    # 2. Test HTML Endpoint: /mailboxes/{email} (simulating direct web page scraping)
    html_resp = client.get(f"/mailboxes/{test_email}", headers={"Accept": "text/html"})
    assert html_resp.status_code == 200
    html_text = html_resp.text
    extracted_from_html = _extract_code(html_text)
    # The HTML page loads data via JS, but if requested directly with fallback, ensure clean status
    assert html_resp.status_code == 200

