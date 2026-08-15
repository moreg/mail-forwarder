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

    # 3. Query emails list
    emails_resp = client.get("/api/v1/emails?to=myicloud_alias")
    assert emails_resp.status_code == 200
    assert emails_resp.json()["total"] >= 1
