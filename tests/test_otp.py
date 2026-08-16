import pytest
from app.engine.otp_extractor import extract_otp_from_email, detect_service_name

def test_apple_id_code_extraction():
    subject = "Your Apple ID Code is 839210"
    body = "Please enter 839210 to sign in to your Apple ID account."
    from_addr = "appleid@id.apple.com"
    otps = extract_otp_from_email(subject, body, from_addr)
    assert len(otps) >= 1
    assert otps[0].code == "839210"
    assert otps[0].service_name == "Apple"

def test_chinese_sms_style_otp():
    subject = "【腾讯云】验证码通知"
    body = "您正在进行敏感操作，验证码为：681923，请在5分钟内输入，切勿泄露给他人。"
    from_addr = "service@tencent.com"
    otps = extract_otp_from_email(subject, body, from_addr)
    assert len(otps) >= 1
    assert otps[0].code == "681923"

def test_telegram_code():
    subject = "Telegram login code: 58219"
    body = "Dear user, here is your Telegram login code: 58219. Do not give this code to anyone."
    from_addr = "login@telegram.org"
    otps = extract_otp_from_email(subject, body, from_addr)
    assert len(otps) >= 1
    assert otps[0].code == "58219"
    assert otps[0].service_name == "Telegram"

def test_google_code_format():
    subject = "Google 身份验证"
    body = "G-948201 是您的 Google 验证码。"
    from_addr = "no-reply@accounts.google.com"
    otps = extract_otp_from_email(subject, body, from_addr)
    assert len(otps) >= 1
    assert "948201" in [o.code for o in otps]
    assert otps[0].service_name == "Google"

def test_magic_link_extraction():
    subject = "Confirm your subscription"
    body = "Click the link below to verify your email address:\nhttps://auth.openai.com/verify-email?token=abcdef123456"
    from_addr = "noreply@tm.openai.com"
    otps = extract_otp_from_email(subject, body, from_addr)
    assert len(otps) >= 1
    assert any(o.code_type == "link" for o in otps)
    assert "https://auth.openai.com/verify-email" in otps[0].verification_url

def test_custom_otp_keywords():
    # 测试自定义特殊关键词比如 "通行码" / "提取口令"
    subject = "系统通知"
    body = "您申请的通行码为：778899，请妥善保管。"
    from_addr = "notice@customservice.com"
    otps = extract_otp_from_email(subject, body, from_addr, custom_keywords=["通行码", "提取口令"])
    assert len(otps) >= 1
    assert otps[0].code == "778899"

