import re
from typing import Optional, List
from pydantic import BaseModel

KNOWN_SERVICES = {
    "apple": ["apple.com", "icloud.com", "apple id", "apple"],
    "google": ["google.com", "google", "gmail.com", "youtube"],
    "microsoft": ["microsoft.com", "live.com", "outlook.com", "office.com", "xbox"],
    "telegram": ["telegram.org", "telegram"],
    "whatsapp": ["whatsapp.com", "whatsapp"],
    "discord": ["discord.com", "discordapp.com", "discord"],
    "github": ["github.com", "github"],
    "openai": ["openai.com", "chatgpt"],
    "anthropic": ["anthropic.com", "claude"],
    "twitter": ["twitter.com", "x.com", "twitter"],
    "steam": ["steampowered.com", "steam"],
    "binance": ["binance.com", "binance"],
    "okx": ["okx.com", "okex"],
    "amazon": ["amazon.com", "amazon.cn", "aws", "amazon"],
    "netflix": ["netflix.com", "netflix"],
    "paypal": ["paypal.com", "paypal"],
    "facebook": ["facebook.com", "meta.com", "instagram.com"],
    "tiktok": ["tiktok.com", "bytedance.com", "tiktok"],
    "uber": ["uber.com", "uber"],
    "spotify": ["spotify.com", "spotify"],
    "stripe": ["stripe.com", "stripe"]
}

class ExtractedOTP(BaseModel):
    code: str
    code_type: str = "numeric"        # numeric, alphanumeric, link
    service_name: str = "Unknown"
    verification_url: str = ""
    context_snippet: str = ""
    confidence: float = 1.0

def detect_service_name(from_address: str, subject: str, body_text: str) -> str:
    combined = f"{from_address} {subject}".lower()
    for service, keywords in KNOWN_SERVICES.items():
        for kw in keywords:
            if kw in combined:
                return service.capitalize()
    
    # Fallback to domain name from email
    if "@" in from_address:
        domain_part = from_address.split("@")[-1].split(">")[0].strip()
        main_domain = domain_part.split(".")[0]
        if len(main_domain) > 2 and main_domain not in ["mail", "mailer", "service", "notice", "noreply", "no-reply"]:
            return main_domain.capitalize()

    return "Unknown"

# Regex patterns for OTP codes
KEYWORD_PATTERNS = [
    # Chinese patterns
    r"(?:验证码|校验码|动态码|识别码|安全码|动态口令|激活码|确认码|PIN码)[^\d\w]{0,15}?([0-9]{4,8})",
    r"([0-9]{4,8})[^\d\w]{0,10}?(?:为您的验证码|是您的验证码|为本次验证码|是您的校验码|为登录验证码)",
    # English patterns
    r"(?:verification|security|confirmation|validation|login|auth|activation|access|one-time|otp|pin|passcode)\s+(?:code|password|pin)?\s*(?:is|:|-)?\s*([0-9]{4,8})",
    r"([0-9]{4,8})\s+is\s+your\s+(?:verification|security|confirmation|validation|login|otp|code)",
    r"(?:code|pin)\s*[:=：]\s*([0-9]{4,8})",
    r"(?:enter|use)\s+([0-9]{4,8})\s+to\s+(?:verify|login|confirm|authenticate)",
    # Format with dash/space e.g. 123-456, 123 456
    r"(?:verification|code|pin|security)[^\d]{1,10}?([0-9]{3}[\s-][0-9]{3})"
]

ALPHANUMERIC_PATTERNS = [
    r"(?:verification|security|confirmation|auth)\s+code\s*(?:is|:|-)?\s*([A-Z0-9]{5,8})\b",
    r"(?:code|pin)\s*[:=：]\s*([A-Z0-9]{5,8})\b",
]

LINK_PATTERNS = [
    r'(https?://[^\s<>"\']+(?:verify|confirmation|confirm|activation|activate|token=|magic-link|auth/)[^\s<>"\']*)'
]

def extract_otp_from_email(
    subject: str,
    body_text: str,
    from_address: str = "",
    body_html: str = ""
) -> List[ExtractedOTP]:
    results: List[ExtractedOTP] = []
    seen_codes = set()
    service_name = detect_service_name(from_address, subject, body_text)

    # Search in Subject first (often Apple, Telegram put code directly in subject e.g. "Your code is 123456" or "123-456 is your code")
    search_targets = [
        ("subject", subject),
        ("body", body_text)
    ]

    for source_name, text in search_targets:
        if not text:
            continue

        # 1. Check keyword-based numeric regex
        for pattern in KEYWORD_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                code_raw = m.group(1).replace("-", "").replace(" ", "").strip()
                if 4 <= len(code_raw) <= 8 and code_raw.isdigit():
                    if code_raw not in seen_codes:
                        seen_codes.add(code_raw)
                        snippet_start = max(0, m.start() - 30)
                        snippet_end = min(len(text), m.end() + 30)
                        snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
                        results.append(ExtractedOTP(
                            code=code_raw,
                            code_type="numeric",
                            service_name=service_name,
                            context_snippet=snippet,
                            confidence=0.95 if source_name == "subject" else 0.90
                        ))

        # 2. Check alphanumeric codes
        for pattern in ALPHANUMERIC_PATTERNS:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for m in matches:
                code_raw = m.group(1).strip().upper()
                # Ignore common words
                if code_raw not in seen_codes and not code_raw.isalpha() and 5 <= len(code_raw) <= 8:
                    seen_codes.add(code_raw)
                    snippet_start = max(0, m.start() - 30)
                    snippet_end = min(len(text), m.end() + 30)
                    snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
                    results.append(ExtractedOTP(
                        code=code_raw,
                        code_type="alphanumeric",
                        service_name=service_name,
                        context_snippet=snippet,
                        confidence=0.85
                    ))

    # 3. Fallback: If no code found yet, look for standalone 4-6 digit numbers if keywords exist in text
    if not results:
        has_keywords = any(kw in (subject + " " + body_text).lower() for kw in [
            "验证码", "code", "pin", "otp", "password", "security", "token", "auth"
        ])
        if has_keywords:
            candidates = re.findall(r"\b([0-9]{4,8})\b", body_text)
            for cand in candidates:
                # Filter out years like 2024, 2025, 2026, 1999
                if cand.startswith("19") or cand.startswith("20") and len(cand) == 4:
                    continue
                if cand not in seen_codes:
                    seen_codes.add(cand)
                    results.append(ExtractedOTP(
                        code=cand,
                        code_type="numeric",
                        service_name=service_name,
                        context_snippet="Fallback context extraction",
                        confidence=0.65
                    ))
                    break # Take the most likely one

    # 4. Check for Verification Links / Confirmation URLs
    full_text_for_links = body_text + ("\n" + body_html if body_html else "")
    for pattern in LINK_PATTERNS:
        matches = re.findall(pattern, full_text_for_links, re.IGNORECASE)
        for link in matches:
            clean_link = link.strip().rstrip(".)'\">]")
            if clean_link not in seen_codes:
                seen_codes.add(clean_link)
                results.append(ExtractedOTP(
                    code="[Link]",
                    code_type="link",
                    service_name=service_name,
                    verification_url=clean_link,
                    context_snippet=f"Verification Link for {service_name}",
                    confidence=0.90
                ))
                break # Only need 1 primary activation link

    return results
