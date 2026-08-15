import pytest
from app.engine.parser import parse_raw_email

def test_parse_plain_text_email():
    raw = (
        "From: noreply@apple.com\r\n"
        "To: myuser@mydomain.com\r\n"
        "Subject: Your Apple ID Code\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Your Apple ID verification code is: 849102. Do not share it with anyone."
    )
    parsed = parse_raw_email(raw)
    assert parsed.from_address == "noreply@apple.com"
    assert parsed.to_address == "myuser@mydomain.com"
    assert parsed.subject == "Your Apple ID Code"
    assert "849102" in parsed.body_text

def test_parse_html_multipart_email():
    raw = (
        "From: =?UTF-8?B?VVs=?= <service@telegram.org>\r\n"
        "To: target@mydomain.com\r\n"
        "Subject: =?UTF-8?B?55m75b2V6aqM6K+B56CB?= \r\n"
        "Content-Type: multipart/alternative; boundary=\"boundary123\"\r\n\r\n"
        "--boundary123\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "您的 Telegram 登录验证码是 93821。\r\n"
        "--boundary123\r\n"
        "Content-Type: text/html; charset=utf-8\r\n\r\n"
        "<div><p>您的 Telegram 登录验证码是 <b>93821</b>。</p></div>\r\n"
        "--boundary123--"
    )
    parsed = parse_raw_email(raw)
    assert "service@telegram.org" in parsed.from_address
    assert parsed.to_address == "target@mydomain.com"
    assert "登录验证码" in parsed.subject
    assert "93821" in parsed.body_text
    assert "<b>93821</b>" in parsed.body_html
