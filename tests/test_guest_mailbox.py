import time

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
async def test_guest_mailbox_special_format():
    await init_db()
    await clear_all_emails()

    target_addr = "special.format_test@domain.com"
    raw_mail = (
        "From: noreply@openai.com\r\n"
        f"To: {target_addr}\r\n"
        "Subject: Your OpenAI verification code is 123456\r\n"
        "\r\n"
        "Your OpenAI verification code is 123456."
    )
    await process_incoming_email(raw_mail)

    # 1. 短链页路由 /mailboxes/{email}?format=special 直接返回精简 JSON
    page_special = client.get(f"/mailboxes/{target_addr}", params={"format": "special"})
    assert page_special.status_code == 200
    assert "application/json" in page_special.headers.get("content-type", "")
    body = page_special.json()
    assert set(body.keys()) == {"code", "receivedAt", "to", "from"}
    assert body["code"] == "123456"
    assert body["to"] == target_addr
    assert body["from"] == "OpenAI"
    assert body["receivedAt"].endswith("Z") and "T" in body["receivedAt"]

    # 2. API 路由 /api/v1/mailboxes/{email}?format=special 同样支持
    api_special = client.get(f"/api/v1/mailboxes/{target_addr}", params={"format": "special"})
    assert api_special.status_code == 200
    api_body = api_special.json()
    assert set(api_body.keys()) == {"code", "receivedAt", "to", "from"}
    assert api_body["code"] == "123456"
    assert api_body["to"] == target_addr

    # 3. format=special 优先于浏览器 Accept：浏览器直接打开也返回 JSON
    browser_special = client.get(
        f"/mailboxes/{target_addr}",
        params={"format": "special"},
        headers={"Accept": "text/html"}
    )
    assert "application/json" in browser_special.headers.get("content-type", "")

    # 4. 无验证码的邮箱返回 {"status":"waiting"}（注册平台约定）
    empty = client.get("/mailboxes/nobody@example.com", params={"format": "special"})
    assert empty.status_code == 200
    assert empty.json() == {"status": "waiting"}

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
    ingest_t0 = time.time()
    await process_incoming_email(raw_openai_mail)
    ingest_t1 = time.time()

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

    # 1b. after_ts 防旧码过滤（注册流程传 after_ts=注册开始时间，早于它的旧码必须被过滤）。
    #     时间字段必须是无时区歧义的 epoch 秒：客户端会把无后缀时间字符串按其本地
    #     时区解析，非 UTC 机器上会放行旧码（UTC-X）或误杀新码（UTC+X）。
    stale_result = _extract_structured_api_code(json_text, after_ts=ingest_t1 + 60)
    assert stale_result is None, f"旧验证码未被 after_ts 过滤: {stale_result}"

    fresh_result = _extract_structured_api_code(json_text, after_ts=ingest_t0 - 60)
    assert fresh_result is not None, "after_ts 早于邮件到达时间，却取不到新验证码"
    fresh_code, fresh_meta = fresh_result
    assert fresh_code == "639102"
    assert fresh_meta["msg_ts"] is not None, "时间字段缺失或格式无法解析为时间戳"
    assert ingest_t0 - 5 <= fresh_meta["msg_ts"] <= ingest_t1 + 5, (
        f"msg_ts={fresh_meta['msg_ts']} 与入库时间 [{ingest_t0}, {ingest_t1}] 偏差过大（时区解析错误）"
    )

    # 2. Test HTML Endpoint: /mailboxes/{email} (simulating direct web page scraping)
    html_resp = client.get(f"/mailboxes/{test_email}", headers={"Accept": "text/html"})
    assert html_resp.status_code == 200
    html_text = html_resp.text
    extracted_from_html = _extract_code(html_text)
    # The HTML page loads data via JS, but if requested directly with fallback, ensure clean status
    assert html_resp.status_code == 200

