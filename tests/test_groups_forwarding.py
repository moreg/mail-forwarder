import pytest
from starlette.testclient import TestClient
from app.main import app
from app.engine.parser import parse_raw_email
from app.engine.pipeline import process_incoming_email
from app.db.database import init_db, get_forwarding_groups_hierarchy, clear_all_emails

client = TestClient(app)

@pytest.mark.asyncio
async def test_parse_forwarding_headers():
    await init_db()
    await clear_all_emails()
    # 1. Test iCloud style Delivered-To forwarding
    raw_icloud_fwd = (
        "Delivered-To: master_apple01@icloud.com\r\n"
        "From: noreply@apple.com\r\n"
        "To: dev_alias1@customdomain.com\r\n"
        "Subject: Your Apple ID code is 958201\r\n"
        "\r\n"
        "Your Apple ID verification code is 958201."
    )
    parsed1 = parse_raw_email(raw_icloud_fwd)
    assert parsed1.forwarded_by == "master_apple01@icloud.com"
    assert parsed1.to_address == "dev_alias1@customdomain.com"
    assert parsed1.from_address == "noreply@apple.com"

    # 2. Test Resent-From header
    raw_resent_fwd = (
        "Resent-From: Admin Team <admin_fwd@company.com>\r\n"
        "From: support@github.com\r\n"
        "To: bot_dev@customdomain.com\r\n"
        "Subject: GitHub code: 382910\r\n"
        "\r\n"
        "Here is your code: 382910"
    )
    parsed2 = parse_raw_email(raw_resent_fwd)
    assert parsed2.forwarded_by == "admin_fwd@company.com"
    assert parsed2.to_address == "bot_dev@customdomain.com"

    # 3. Test direct email without forwarding headers
    raw_direct = (
        "From: service@google.com\r\n"
        "To: direct_user@customdomain.com\r\n"
        "Subject: Google Code\r\n"
        "\r\n"
        "G-123456 is your code."
    )
    parsed3 = parse_raw_email(raw_direct)
    assert parsed3.forwarded_by == ""
    assert parsed3.to_address == "direct_user@customdomain.com"

@pytest.mark.asyncio
async def test_group_hierarchy_and_filtering_api():
    # 1. Ingest emails from Master Group 1 (apple01@icloud.com) with two aliases
    raw_mail1 = (
        "Delivered-To: apple01@icloud.com\r\n"
        "From: appleid@id.apple.com\r\n"
        "To: dev_a@mydomain.com\r\n"
        "Subject: Apple Code for Dev A\r\n"
        "\r\n"
        "Your code is 111111"
    )
    await process_incoming_email(raw_mail1)

    raw_mail2 = (
        "Delivered-To: apple01@icloud.com\r\n"
        "From: appleid@id.apple.com\r\n"
        "To: dev_b@mydomain.com\r\n"
        "Subject: Apple Code for Dev B\r\n"
        "\r\n"
        "Your code is 222222"
    )
    await process_incoming_email(raw_mail2)

    # 2. Ingest email from Master Group 2 (apple02@icloud.com)
    raw_mail3 = (
        "Delivered-To: apple02@icloud.com\r\n"
        "From: appleid@id.apple.com\r\n"
        "To: dev_c@mydomain.com\r\n"
        "Subject: Apple Code for Dev C\r\n"
        "\r\n"
        "Your code is 333333"
    )
    await process_incoming_email(raw_mail3)

    # 3. Ingest direct email
    raw_mail4 = (
        "From: login@telegram.org\r\n"
        "To: tg_direct@mydomain.com\r\n"
        "Subject: Telegram login code: 444444\r\n"
        "\r\n"
        "Your login code is 444444"
    )
    await process_incoming_email(raw_mail4)

    # 4. Test GET /api/v1/groups API
    resp = client.get("/api/v1/groups")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    groups = data["data"]

    # Verify groups exist
    group_map = {g["group_name"]: g for g in groups}
    assert "apple01@icloud.com" in group_map
    assert "apple02@icloud.com" in group_map
    assert "直接收件" in group_map

    # Check apple01 group structure
    apple01_group = group_map["apple01@icloud.com"]
    assert apple01_group["total_emails"] == 2
    aliases = [a["to_address"] for a in apple01_group["aliases"]]
    assert "dev_a@mydomain.com" in aliases
    assert "dev_b@mydomain.com" in aliases

    # 5. Test GET /api/v1/groups/{group_name}/aliases
    alias_resp = client.get("/api/v1/groups/apple01@icloud.com/aliases")
    assert alias_resp.status_code == 200
    alias_data = alias_resp.json()
    assert len(alias_data["data"]) == 2

    # 6. Test GET /api/v1/emails?group=apple01@icloud.com
    emails_resp = client.get("/api/v1/emails?group=apple01@icloud.com")
    assert emails_resp.status_code == 200
    emails_data = emails_resp.json()
    assert emails_data["total"] == 2
    for e in emails_data["data"]:
        assert e["forwarded_by"] == "apple01@icloud.com"

    # 7. Test GET /api/v1/codes/latest with group filter
    code_resp = client.get("/api/v1/codes/latest?group=apple01@icloud.com")
    assert code_resp.status_code == 200
    code_data = code_resp.json()
    assert code_data["found"] is True
    assert code_data["code"] in ["111111", "222222"]
    assert code_data["forwarded_by"] == "apple01@icloud.com"

    # 8. Test DELETE /api/v1/groups/{group_name}/emails
    del_resp = client.delete("/api/v1/groups/apple01@icloud.com/emails")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted_count"] == 2

    # Verify apple01 group emails are cleared while apple02 remains
    stats_resp = client.get("/api/v1/stats")
    stats_data = stats_resp.json()["data"]
    rem_groups = {g["group_name"]: g for g in stats_data["groups"]}
    assert "apple01@icloud.com" not in rem_groups
    assert "apple02@icloud.com" in rem_groups

@pytest.mark.asyncio
async def test_webhook_forwarded_by_and_direct_filtering():
    await init_db()
    await clear_all_emails()

    # 1. Ingest via Webhook JSON with explicit forwarded_by
    webhook_payload = {
        "from": "security@apple.com",
        "to": "test_alias@mydomain.com",
        "forwarded_by": "custom_forwarder@icloud.com",
        "subject": "Apple Code: 998877",
        "body_text": "Your Apple ID verification code is 998877"
    }
    resp = client.post("/api/v1/webhook/inbound", json=webhook_payload)
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 2. Ingest another direct email
    direct_payload = {
        "from": "support@telegram.org",
        "to": "direct_alias@mydomain.com",
        "subject": "Telegram Code: 556677",
        "body_text": "Your Telegram login code is 556677"
    }
    resp2 = client.post("/api/v1/webhook/inbound", json=direct_payload)
    assert resp2.status_code == 200

    # 3. Query direct group
    direct_resp = client.get("/api/v1/emails?group=直接收件")
    assert direct_resp.status_code == 200
    assert direct_resp.json()["total"] == 1
    assert direct_resp.json()["data"][0]["to_address"] == "direct_alias@mydomain.com"

    # 4. Query custom_forwarder group
    fwd_resp = client.get("/api/v1/emails?group=custom_forwarder@icloud.com")
    assert fwd_resp.status_code == 200
    assert fwd_resp.json()["total"] == 1
    assert fwd_resp.json()["data"][0]["forwarded_by"] == "custom_forwarder@icloud.com"
    assert fwd_resp.json()["data"][0]["to_address"] == "test_alias@mydomain.com"

