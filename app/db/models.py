from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field

class EmailCreate(BaseModel):
    message_id: str = ""
    from_address: str
    to_address: str
    subject: str = ""
    body_text: str = ""
    body_html: str = ""
    raw_eml: str = ""
    has_attachments: bool = False
    attachments_json: str = "[]"
    received_at: Optional[datetime] = None

class EmailItem(BaseModel):
    id: int
    message_id: str
    from_address: str
    to_address: str
    subject: str
    body_text: str
    body_html: str
    has_attachments: bool
    attachments_json: str
    is_read: bool
    created_at: str

class VerificationCodeCreate(BaseModel):
    email_id: int
    to_address: str
    code: str
    code_type: str = "numeric"        # numeric, alphanumeric, link
    service_name: str = "Unknown"     # Apple, Google, GitHub, etc.
    verification_url: str = ""
    context_snippet: str = ""

class VerificationCodeItem(BaseModel):
    id: int
    email_id: int
    to_address: str
    code: str
    code_type: str
    service_name: str
    verification_url: str
    context_snippet: str
    created_at: str
    email_subject: Optional[str] = None
    email_from: Optional[str] = None
