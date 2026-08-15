import asyncio
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db, clear_all_emails
from app.engine.pipeline import process_incoming_email

@pytest.mark.asyncio
async def test_api_health_and_stats():
    await init_db()
    client = TestClient(app)
    response = client.get("/api/v1/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "total_emails" in data["data"]

@pytest.mark.asyncio
async def test_email_ingestion_and_code_query():
    await init_db()
    await clear_all_emails()
    client = TestClient(app)
    
    # 1. Ingest test email simulating iCloud forward
    raw_email = (
        "From: service@github.com\r\n"
        "To: myicloud_alias@domain.com\r\n"
        "Subject: GitHub Verification Code\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Your GitHub device verification code is 482910. It expires in 10 minutes."
    )
    
    res = await process_incoming_email(raw_content=raw_email)
    assert res["email_id"] > 0
    assert len(res["codes"]) == 1
    assert res["codes"][0]["code"] == "482910"
    assert res["codes"][0]["service_name"] == "Github"

    # 2. Query via REST API
    response = client.get("/api/v1/codes/latest?to=myicloud_alias@domain.com")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["found"] is True
    assert json_data["code"] == "482910"

    # 3. Query emails list by alias, sender, and service
    emails_resp = client.get("/api/v1/emails?to=myicloud_alias")
    assert emails_resp.status_code == 200
    assert emails_resp.json()["total"] >= 1

    # 4. Ingest second email from Apple
    apple_email = (
        "From: appleid@id.apple.com\r\n"
        "To: apple01@domain.com\r\n"
        "Subject: 您的 Apple ID 验证码是 948210\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "您好，您的 Apple ID 验证码是 948210。"
    )
    res_apple = await process_incoming_email(raw_content=apple_email)
    assert res_apple["email_id"] > 0

    # 5. Verify stats returns top_services and top_senders
    stats_resp = client.get("/api/v1/stats")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()["data"]
    assert "top_services" in stats_data
    assert "top_senders" in stats_data
    service_names = [s["service_name"] for s in stats_data["top_services"]]
    assert "Github" in service_names or "Apple" in service_names

    # 6. Verify service filter query
    apple_filter_resp = client.get("/api/v1/emails?service=Apple")
    assert apple_filter_resp.status_code == 200
    assert apple_filter_resp.json()["total"] == 1
    assert apple_filter_resp.json()["data"][0]["from_address"] == "appleid@id.apple.com"

    github_filter_resp = client.get("/api/v1/emails?service=Github")
    assert github_filter_resp.status_code == 200
    assert github_filter_resp.json()["total"] == 1
    assert github_filter_resp.json()["data"][0]["from_address"] == "service@github.com"

    sender_filter_resp = client.get("/api/v1/emails?from=appleid@id.apple.com")
    assert sender_filter_resp.status_code == 200
    assert sender_filter_resp.json()["total"] == 1

@pytest.mark.asyncio
async def test_authentication_flow():
    from app.core.config import settings
    await init_db()
    client = TestClient(app)

    # 1. Open mode (免鉴权)
    settings.server.admin_password = ""
    settings.server.api_key = ""
    status_res = client.get("/api/v1/auth/status")
    assert status_res.status_code == 200
    assert status_res.json()["auth_required"] is False

    # 2. Enable Auth
    settings.server.admin_password = "test_password_888"
    settings.server.api_key = "test_key_999"

    # Status should now indicate auth is required
    status_res = client.get("/api/v1/auth/status")
    assert status_res.status_code == 200
    assert status_res.json()["auth_required"] is True
    assert status_res.json()["logged_in"] is False

    # Protected endpoint should reject unauthenticated request
    rejected_res = client.get("/api/v1/stats")
    assert rejected_res.status_code == 401

    # Login with wrong password
    bad_login = client.post("/api/v1/auth/login", json={"password": "wrong_password"})
    assert bad_login.status_code == 401

    # Login with correct password
    good_login = client.post("/api/v1/auth/login", json={"password": "test_password_888"})
    assert good_login.status_code == 200
    token = good_login.json()["token"]
    assert token != ""

    # Access protected endpoint with Bearer Token
    authed_res = client.get("/api/v1/stats", headers={"Authorization": f"Bearer {token}"})
    assert authed_res.status_code == 200
    assert authed_res.json()["success"] is True

    # Access protected endpoint with X-API-Key
    key_res = client.get("/api/v1/stats", headers={"X-API-Key": "test_key_999"})
    assert key_res.status_code == 200

    # Reset back to open mode for subsequent test safety
    settings.server.admin_password = ""
    settings.server.api_key = ""

