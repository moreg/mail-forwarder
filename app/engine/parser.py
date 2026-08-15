import email
from email import policy
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Any, Tuple, List, Optional
from bs4 import BeautifulSoup

def decode_mime_header(header_str: Optional[str]) -> str:
    if not header_str:
        return ""
    try:
        decoded_fragments = decode_header(header_str)
        parts = []
        for content, encoding in decoded_fragments:
            if isinstance(content, bytes):
                enc = encoding or "utf-8"
                try:
                    parts.append(content.decode(enc, errors="replace"))
                except Exception:
                    try:
                        parts.append(content.decode("gb18030", errors="replace"))
                    except Exception:
                        parts.append(content.decode("latin1", errors="replace"))
            else:
                parts.append(str(content))
        return "".join(parts).strip()
    except Exception:
        return str(header_str).strip()

def decode_payload_bytes(payload: bytes, charset: Optional[str]) -> str:
    charsets_to_try = [
        charset,
        "utf-8",
        "gb18030",
        "gbk",
        "gb2312",
        "big5",
        "iso-8859-1",
        "windows-1252",
        "latin1",
    ]
    for c in charsets_to_try:
        if not c:
            continue
        try:
            return payload.decode(c)
        except (UnicodeDecodeError, LookupError):
            continue
    return payload.decode("utf-8", errors="replace")

def clean_html_to_text(html_content: str) -> str:
    if not html_content:
        return ""
    try:
        soup = BeautifulSoup(html_content, "html.parser")
        # Remove script and style elements
        for script in soup(["script", "style", "head", "meta", "noscript"]):
            script.extract()
        text = soup.get_text(separator="\n")
        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = "\n".join(chunk for chunk in chunks if chunk)
        return text
    except Exception:
        return ""

class ParsedEmail:
    def __init__(
        self,
        message_id: str,
        from_address: str,
        from_name: str,
        to_address: str,
        to_name: str,
        subject: str,
        body_text: str,
        body_html: str,
        raw_eml: str,
        has_attachments: bool,
        attachments: List[dict[str, Any]],
        forwarded_by: str = "",
        group_name: str = ""
    ):
        self.message_id = message_id
        self.from_address = from_address
        self.from_name = from_name
        self.to_address = to_address
        self.to_name = to_name
        self.forwarded_by = forwarded_by
        self.group_name = group_name
        self.subject = subject
        self.body_text = body_text
        self.body_html = body_html
        self.raw_eml = raw_eml
        self.has_attachments = has_attachments
        self.attachments = attachments

def extract_forwarding_address(msg: Any, to_addr: str) -> str:
    """
    智能提取邮件中介转发来源（母账号/转发源，如 iCloud、Gmail、Outlook 等中转邮箱）
    """
    # 1. 优先检查 Resent-From (标准客户端规则转发)
    resent_from = msg.get("Resent-From")
    if resent_from:
        _, addr = parseaddr(resent_from)
        if addr and addr.lower() != to_addr.lower():
            return addr.strip().lower()

    # 2. 检查 Delivered-To (iCloud、Gmail 规则转发最常保留的原始投递母账号)
    delivered_to = msg.get("Delivered-To")
    if delivered_to:
        _, addr = parseaddr(delivered_to)
        if addr and addr.lower() != to_addr.lower():
            return addr.strip().lower()
        # 如果 delivered_to 存在且是常见的公网转发服务商 (如 icloud.com, me.com, gmail.com)
        if addr and any(domain in addr.lower() for domain in ["@icloud.com", "@me.com", "@mac.com", "@gmail.com", "@outlook.com", "@qq.com"]):
            return addr.strip().lower()

    # 3. 检查 X-Original-To / X-Delivered-To
    for h in ["X-Original-To", "X-Delivered-To", "X-Envelope-To"]:
        val = msg.get(h)
        if val:
            _, addr = parseaddr(val)
            if addr and addr.lower() != to_addr.lower():
                return addr.strip().lower()

    # 4. 检查 X-Forwarded-For / X-Forwarded-To
    fwd_for = msg.get("X-Forwarded-For") or msg.get("X-Forwarded-To")
    if fwd_for:
        import re
        matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', str(fwd_for))
        for m in matches:
            if m.lower() != to_addr.lower():
                return m.strip().lower()

    return ""

def parse_raw_email(raw_content: str | bytes, default_to: str = "", default_forwarded_by: str = "") -> ParsedEmail:
    if isinstance(raw_content, str):
        raw_bytes = raw_content.encode("utf-8", errors="replace")
        raw_str = raw_content
    else:
        raw_bytes = raw_content
        raw_str = decode_payload_bytes(raw_bytes, "utf-8")

    try:
        msg = email.message_from_bytes(raw_bytes, policy=policy.default)
    except Exception:
        msg = email.message_from_string(raw_str)

    message_id = msg.get("Message-ID", "") or ""
    subject = decode_mime_header(msg.get("Subject", ""))

    from_header = msg.get("From", "")
    from_name_raw, from_addr = parseaddr(from_header)
    from_name = decode_mime_header(from_name_raw) or from_addr

    to_header = msg.get("To", "")
    to_name_raw, to_addr = parseaddr(to_header)
    to_name = decode_mime_header(to_name_raw) or to_addr
    if not to_addr and default_to:
        to_addr = default_to

    # 提取转发来源（母账号）
    forwarded_by = default_forwarded_by or extract_forwarding_address(msg, to_addr)

    body_text_parts = []
    body_html_parts = []
    attachments = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))

            # Check if it is an attachment
            filename = part.get_filename()
            if filename:
                filename = decode_mime_header(filename)
                attachments.append({
                    "filename": filename,
                    "content_type": content_type,
                    "size": len(part.get_payload(decode=True) or b"")
                })
                continue

            if "attachment" in content_disposition:
                continue

            payload_bytes = part.get_payload(decode=True)
            if not payload_bytes:
                continue

            charset = part.get_content_charset()
            decoded_text = decode_payload_bytes(payload_bytes, charset)

            if content_type == "text/plain":
                body_text_parts.append(decoded_text)
            elif content_type == "text/html":
                body_html_parts.append(decoded_text)
    else:
        payload_bytes = msg.get_payload(decode=True)
        charset = msg.get_content_charset()
        if payload_bytes:
            decoded_text = decode_payload_bytes(payload_bytes, charset)
            if msg.get_content_type() == "text/html":
                body_html_parts.append(decoded_text)
            else:
                body_text_parts.append(decoded_text)
        else:
            body_text_parts.append(str(msg.get_payload() or ""))

    body_text = "\n".join(body_text_parts).strip()
    body_html = "\n".join(body_html_parts).strip()

    if not body_text and body_html:
        body_text = clean_html_to_text(body_html)

    return ParsedEmail(
        message_id=message_id,
        from_address=from_addr or from_header,
        from_name=from_name,
        to_address=to_addr or "unknown@localhost",
        to_name=to_name,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        raw_eml=raw_str,
        has_attachments=len(attachments) > 0,
        attachments=attachments,
        forwarded_by=forwarded_by,
        group_name=forwarded_by
    )
