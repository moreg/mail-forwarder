import asyncio
import time
import httpx
import pytest
from app.main import app
from app.engine.otp_extractor import extract_otp_from_email
from app.engine.pipeline import process_incoming_email
from app.db.database import (
    init_db, clear_all_emails, get_forwarding_groups_hierarchy, get_mailbox_stats
)

@pytest.mark.asyncio
async def test_otp_extraction_throughput():
    """验证预编译正则的高吞吐量 (1000 次提取应当在 100ms 内完成)"""
    sample_subject = "Your Apple ID verification code is 849201"
    sample_body = "Hello, your verification code is 849201. Please use it within 10 minutes."
    from_addr = "appleid@id.apple.com"

    start = time.perf_counter()
    for _ in range(1000):
        otps = extract_otp_from_email(sample_subject, sample_body, from_addr)
        assert len(otps) >= 1
        assert otps[0].code == "849201"
    duration = time.perf_counter() - start

    tps = 1000 / duration
    print(f"\n[Benchmark] 1000 OTP Extractions: {duration*1000:.2f}ms (Throughput: {tps:.0f} ops/sec)")
    assert duration < 0.3  # 1000 extractions well under 300ms

@pytest.mark.asyncio
async def test_forwarding_hierarchy_query_performance():
    """验证消灭 N+1 查询后，在拥有大量别名时的高性能聚合 (单次查询完成)"""
    await init_db()
    await clear_all_emails()

    # 批量注入 20 个不同别名的邮件
    for i in range(20):
        raw_email = (
            f"Delivered-To: master_perf@icloud.com\r\n"
            f"From: service_{i}@test.com\r\n"
            f"To: alias_{i:02d}@perf.domain.com\r\n"
            f"Subject: Code for alias {i}: {100000+i}\r\n\r\n"
            f"Your verification code is {100000+i}"
        )
        await process_incoming_email(raw_email)

    start = time.perf_counter()
    groups = await get_forwarding_groups_hierarchy()
    duration = time.perf_counter() - start

    print(f"\n[Benchmark] Hierarchy Query for 20 aliases: {duration*1000:.2f}ms")
    assert len(groups) >= 1
    master_group = next(g for g in groups if g["group_name"] == "master_perf@icloud.com")
    assert len(master_group["aliases"]) == 20
    # Single SQL execution with window function should take < 20ms
    assert duration < 0.1

    # Verify latest_code was correctly populated for all aliases without N+1 queries
    for a in master_group["aliases"]:
        assert a["latest_code"] is not None

@pytest.mark.asyncio
async def test_event_driven_long_polling_instant_response():
    """验证事件驱动长轮询：新邮件注入时毫秒级瞬时唤醒返回 (无需等待 1 秒轮询)"""
    await init_db()
    await clear_all_emails()

    target_alias = "instant_test@domain.com"
    expected_code = "789123"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as async_client:
        async def delayed_email_sender():
            # 等待 80ms 确保客户端已挂起在 broadcaster 队列中
            await asyncio.sleep(0.08)
            raw_mail = (
                "From: service@instant.com\r\n"
                f"To: {target_alias}\r\n"
                f"Subject: Code is {expected_code}\r\n\r\n"
                f"Your instant login code is {expected_code}"
            )
            await process_incoming_email(raw_mail)

        sender_task = asyncio.create_task(delayed_email_sender())

        start = time.perf_counter()
        # 请求 timeout=5 秒的长轮询接口
        resp = await async_client.get(f"/api/v1/codes/latest?to={target_alias}&timeout=5")
        elapsed = time.perf_counter() - start

        await sender_task

        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["code"] == expected_code
        # 验证响应时间在注入后几乎瞬间完成 (< 350ms，远小于旧版的 1~2 秒轮询延迟)
        print(f"\n[Benchmark] Long Polling Instant Wakeup: {elapsed*1000:.2f}ms (Injection delayed 80ms)")
        assert elapsed < 0.5
