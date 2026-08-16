import re
from functools import lru_cache
from typing import Optional, List, Tuple
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

# Static regex patterns for OTP codes (raw strings kept for backward-compatibility if imported)
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

# Pre-compiled static regex objects for maximum execution speed
COMPILED_ALPHANUMERIC_PATTERNS = [re.compile(p, re.IGNORECASE) for p in ALPHANUMERIC_PATTERNS]
COMPILED_LINK_PATTERNS = [re.compile(p, re.IGNORECASE) for p in LINK_PATTERNS]
COMPILED_FALLBACK_DIGITS = re.compile(r"\b([0-9]{4,8})\b")

from app.core.config import settings

def get_all_keyword_patterns(custom_keywords: Optional[List[str]] = None) -> List[str]:
    """动态合并默认正则与自定义关键词生成的正则模式字符串"""
    patterns = list(KEYWORD_PATTERNS)
    kws = custom_keywords if custom_keywords is not None else (settings.otp.keywords or [])
    for kw in kws:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        escaped_kw = re.escape(kw_clean)
        patterns.append(rf"(?:{escaped_kw})[^\d\w]{{0,15}}?([0-9]{{4,8}})")
        patterns.append(rf"([0-9]{{4,8}})[^\d\w]{{0,10}}?(?:{escaped_kw})")
        patterns.append(rf"(?:{escaped_kw})\s*[:=：\-]\s*([A-Z0-9]{{4,8}})\b")
    return patterns

@lru_cache(maxsize=128)
def _get_compiled_keyword_patterns(keywords_tuple: Tuple[str, ...]) -> List[re.Pattern]:
    """LRU 缓存的预编译关键词正则对象列表"""
    patterns = list(KEYWORD_PATTERNS)
    for kw in keywords_tuple:
        kw_clean = kw.strip()
        if not kw_clean:
            continue
        escaped_kw = re.escape(kw_clean)
        patterns.append(rf"(?:{escaped_kw})[^\d\w]{{0,15}}?([0-9]{{4,8}})")
        patterns.append(rf"([0-9]{{4,8}})[^\d\w]{{0,10}}?(?:{escaped_kw})")
        patterns.append(rf"(?:{escaped_kw})\s*[:=：\-]\s*([A-Z0-9]{{4,8}})\b")
    return [re.compile(p, re.IGNORECASE) for p in patterns]

def extract_otp_from_email(
    subject: str,
    body_text: str,
    from_address: str = "",
    body_html: str = "",
    custom_keywords: Optional[List[str]] = None
) -> List[ExtractedOTP]:
    results: List[ExtractedOTP] = []
    seen_codes = set()
    service_name = detect_service_name(from_address, subject, body_text)

    # 动态获取已预编译并带 LRU 缓存的关键词正则对象
    kws = tuple(custom_keywords) if custom_keywords is not None else tuple(settings.otp.keywords or [])
    compiled_keyword_patterns = _get_compiled_keyword_patterns(kws)

    # Search in Subject first (often Apple, Telegram put code directly in subject e.g. "Your code is 123456" or "123-456 is your code")
    search_targets = [
        ("subject", subject),
        ("body", body_text)
    ]

    for source_name, text in search_targets:
        if not text:
            continue

        # 1. Check keyword-based numeric & alphanumeric regex
        for pattern_re in compiled_keyword_patterns:
            matches = pattern_re.finditer(text)
            for m in matches:
                code_raw = m.group(1).replace("-", "").replace(" ", "").strip()
                if 4 <= len(code_raw) <= 8:
                    if code_raw.isdigit():
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
                    elif not code_raw.isalpha():
                        # 包含数字的字母数字混合码
                        if code_raw.upper() not in seen_codes:
                            seen_codes.add(code_raw.upper())
                            snippet_start = max(0, m.start() - 30)
                            snippet_end = min(len(text), m.end() + 30)
                            snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
                            results.append(ExtractedOTP(
                                code=code_raw.upper(),
                                code_type="alphanumeric",
                                service_name=service_name,
                                context_snippet=snippet,
                                confidence=0.88
                            ))

        # 2. Check alphanumeric codes
        for pattern_re in COMPILED_ALPHANUMERIC_PATTERNS:
            matches = pattern_re.finditer(text)
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
        configured_kws = custom_keywords if custom_keywords is not None else (settings.otp.keywords or [])
        fallback_kw_pool = set([k.lower().strip() for k in configured_kws if k.strip()] + [
            "验证码", "code", "pin", "otp", "password", "security", "token", "auth"
        ])
        has_keywords = any(kw in (subject + " " + body_text).lower() for kw in fallback_kw_pool)
        if has_keywords:
            candidates = COMPILED_FALLBACK_DIGITS.findall(body_text)
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
    for pattern_re in COMPILED_LINK_PATTERNS:
        matches = pattern_re.findall(full_text_for_links)
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
