import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Any, AsyncGenerator
import aiosqlite
from app.core.config import settings
from app.db.models import EmailCreate, VerificationCodeCreate

DB_PATH = settings.absolute_db_path

CREATE_TABLES_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT DEFAULT '',
    from_address TEXT NOT NULL,
    to_address TEXT NOT NULL,
    subject TEXT DEFAULT '',
    body_text TEXT DEFAULT '',
    body_html TEXT DEFAULT '',
    raw_eml TEXT DEFAULT '',
    has_attachments INTEGER DEFAULT 0,
    attachments_json TEXT DEFAULT '[]',
    is_read INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS verification_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email_id INTEGER NOT NULL,
    to_address TEXT NOT NULL,
    code TEXT NOT NULL,
    code_type TEXT DEFAULT 'numeric',
    service_name TEXT DEFAULT 'Unknown',
    verification_url TEXT DEFAULT '',
    context_snippet TEXT DEFAULT '',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(email_id) REFERENCES emails(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_value TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_emails_to ON emails(to_address);
CREATE INDEX IF NOT EXISTS idx_emails_created ON emails(created_at);
CREATE INDEX IF NOT EXISTS idx_emails_is_read ON emails(is_read);
CREATE INDEX IF NOT EXISTS idx_codes_to ON verification_codes(to_address);
CREATE INDEX IF NOT EXISTS idx_codes_created ON verification_codes(created_at);
"""

@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA foreign_keys = ON;")
    try:
        yield db
    finally:
        await db.close()

async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with get_db_connection() as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()

async def cleanup_expired_emails() -> int:
    """自动清理超出保留天数的旧邮件"""
    retention_days = settings.storage.retention_days
    if retention_days <= 0:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        cursor = await db.execute("DELETE FROM emails WHERE created_at < ?", (cutoff,))
        await db.commit()
        return cursor.rowcount

async def save_email(email: EmailCreate) -> int:
    created_at_str = (email.received_at or datetime.now(timezone.utc)).strftime("%Y-%m-%d %H:%M:%S")
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO emails (
                message_id, from_address, to_address, subject,
                body_text, body_html, raw_eml, has_attachments,
                attachments_json, is_read, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
            """,
            (
                email.message_id,
                email.from_address,
                email.to_address,
                email.subject,
                email.body_text,
                email.body_html,
                email.raw_eml,
                1 if email.has_attachments else 0,
                email.attachments_json,
                created_at_str
            )
        )
        await db.commit()
        return cursor.lastrowid

async def save_verification_code(code: VerificationCodeCreate) -> int:
    async with get_db_connection() as db:
        cursor = await db.execute(
            """
            INSERT INTO verification_codes (
                email_id, to_address, code, code_type,
                service_name, verification_url, context_snippet
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                code.email_id,
                code.to_address,
                code.code,
                code.code_type,
                code.service_name,
                code.verification_url,
                code.context_snippet
            )
        )
        await db.commit()
        return cursor.lastrowid

async def get_emails(
    to_address: Optional[str] = None,
    from_address: Optional[str] = None,
    search: Optional[str] = None,
    is_read: Optional[bool] = None,
    limit: int = 50,
    offset: int = 0
) -> list[dict[str, Any]]:
    query = """
        SELECT e.id, e.message_id, e.from_address, e.to_address, e.subject,
               e.body_text, e.has_attachments, e.attachments_json, e.is_read, e.created_at,
               (SELECT code FROM verification_codes vc WHERE vc.email_id = e.id ORDER BY vc.id DESC LIMIT 1) as latest_code,
               (SELECT service_name FROM verification_codes vc WHERE vc.email_id = e.id ORDER BY vc.id DESC LIMIT 1) as service_name
        FROM emails e
        WHERE 1=1
    """
    params: list[Any] = []

    if to_address:
        query += " AND e.to_address LIKE ?"
        params.append(f"%{to_address}%")

    if from_address:
        query += " AND e.from_address LIKE ?"
        params.append(f"%{from_address}%")

    if search:
        query += " AND (e.subject LIKE ? OR e.body_text LIKE ? OR e.from_address LIKE ?)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])

    if is_read is not None:
        query += " AND e.is_read = ?"
        params.append(1 if is_read else 0)

    query += " ORDER BY e.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with get_db_connection() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def count_emails(
    to_address: Optional[str] = None,
    from_address: Optional[str] = None,
    search: Optional[str] = None,
    is_read: Optional[bool] = None
) -> int:
    query = "SELECT COUNT(*) as cnt FROM emails WHERE 1=1"
    params: list[Any] = []

    if to_address:
        query += " AND to_address LIKE ?"
        params.append(f"%{to_address}%")
    if from_address:
        query += " AND from_address LIKE ?"
        params.append(f"%{from_address}%")
    if search:
        query += " AND (subject LIKE ? OR body_text LIKE ? OR from_address LIKE ?)"
        pattern = f"%{search}%"
        params.extend([pattern, pattern, pattern])
    if is_read is not None:
        query += " AND is_read = ?"
        params.append(1 if is_read else 0)

    async with get_db_connection() as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return row["cnt"] if row else 0

async def get_email_by_id(email_id: int) -> Optional[dict[str, Any]]:
    async with get_db_connection() as db:
        async with db.execute("SELECT * FROM emails WHERE id = ?", (email_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            async with db.execute("SELECT * FROM verification_codes WHERE email_id = ?", (email_id,)) as code_cursor:
                code_rows = await code_cursor.fetchall()
                res["codes"] = [dict(c) for c in code_rows]
            return res

async def mark_email_read(email_id: int, is_read: bool = True) -> bool:
    async with get_db_connection() as db:
        await db.execute("UPDATE emails SET is_read = ? WHERE id = ?", (1 if is_read else 0, email_id))
        await db.commit()
        return True

async def delete_email(email_id: int) -> bool:
    async with get_db_connection() as db:
        await db.execute("DELETE FROM emails WHERE id = ?", (email_id,))
        await db.commit()
        return True

async def clear_all_emails(to_address: Optional[str] = None) -> int:
    async with get_db_connection() as db:
        if to_address:
            cursor = await db.execute("DELETE FROM emails WHERE to_address LIKE ?", (f"%{to_address}%",))
        else:
            cursor = await db.execute("DELETE FROM emails")
        await db.commit()
        return cursor.rowcount

async def get_latest_code(
    to_address: str,
    service_name: Optional[str] = None,
    after_id: Optional[int] = None
) -> Optional[dict[str, Any]]:
    query = """
        SELECT vc.*, e.subject, e.from_address
        FROM verification_codes vc
        JOIN emails e ON vc.email_id = e.id
        WHERE vc.to_address LIKE ?
    """
    params: list[Any] = [f"%{to_address}%"]

    if service_name:
        query += " AND vc.service_name LIKE ?"
        params.append(f"%{service_name}%")

    if after_id is not None:
        query += " AND vc.id > ?"
        params.append(after_id)

    query += " ORDER BY vc.id DESC LIMIT 1"

    async with get_db_connection() as db:
        async with db.execute(query, params) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

async def get_codes(
    to_address: Optional[str] = None,
    service_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> list[dict[str, Any]]:
    query = """
        SELECT vc.*, e.subject, e.from_address
        FROM verification_codes vc
        JOIN emails e ON vc.email_id = e.id
        WHERE 1=1
    """
    params: list[Any] = []

    if to_address:
        query += " AND vc.to_address LIKE ?"
        params.append(f"%{to_address}%")
    if service_name:
        query += " AND vc.service_name LIKE ?"
        params.append(f"%{service_name}%")

    query += " ORDER BY vc.id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with get_db_connection() as db:
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

async def get_mailbox_stats() -> dict[str, Any]:
    async with get_db_connection() as db:
        async with db.execute("SELECT COUNT(*) as total_emails, SUM(CASE WHEN is_read = 0 THEN 1 ELSE 0 END) as unread_emails FROM emails") as cursor:
            email_stats = await cursor.fetchone()
        async with db.execute("SELECT COUNT(*) as total_codes FROM verification_codes") as cursor:
            code_stats = await cursor.fetchone()
        async with db.execute("SELECT COUNT(DISTINCT to_address) as unique_inboxes FROM emails") as cursor:
            inbox_stats = await cursor.fetchone()
        
        async with db.execute("SELECT to_address, COUNT(*) as count, MAX(created_at) as last_seen FROM emails GROUP BY to_address ORDER BY count DESC LIMIT 10") as cursor:
            inboxes_rows = await cursor.fetchall()

        return {
            "total_emails": email_stats["total_emails"] if email_stats else 0,
            "unread_emails": email_stats["unread_emails"] if email_stats and email_stats["unread_emails"] else 0,
            "total_codes": code_stats["total_codes"] if code_stats else 0,
            "unique_inboxes": inbox_stats["unique_inboxes"] if inbox_stats else 0,
            "top_inboxes": [dict(r) for r in inboxes_rows]
        }
