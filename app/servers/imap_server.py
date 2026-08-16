import asyncio
import email
from email import policy
import logging
import re
import shlex
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from app.core.config import settings
from app.db.database import (
    get_emails, get_imap_mailbox_emails, get_email_by_id, count_emails, mark_email_read, delete_email, get_db_connection
)

logger = logging.getLogger("imap_server")

class ImapSession:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self.state = "NONAUTH"  # NONAUTH, AUTH, SELECTED, LOGOUT
        self.username: Optional[str] = None
        self.selected_mailbox: Optional[str] = None
        self.selected_emails: List[Dict[str, Any]] = []

    async def send_line(self, line: str):
        if not line.endswith("\r\n"):
            line += "\r\n"
        self.writer.write(line.encode("utf-8", errors="replace"))
        await self.writer.drain()

    async def send_literal(self, header_prefix: str, data_bytes: bytes, suffix: str = ""):
        header = f"{header_prefix}{{{len(data_bytes)}}}\r\n"
        self.writer.write(header.encode("utf-8"))
        self.writer.write(data_bytes)
        if suffix:
            self.writer.write(suffix.encode("utf-8"))
        await self.writer.drain()

    async def handle_client(self):
        try:
            # Send initial greeting
            await self.send_line("* OK [CAPABILITY IMAP4rev1 AUTH=PLAIN] Virtual IMAP Server Ready")
            
            while self.state != "LOGOUT":
                line_bytes = await self.reader.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

                await self.process_command(line)
        except Exception as e:
            logger.debug(f"IMAP Session exception: {e}")
        finally:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass

    async def process_command(self, line: str):
        parts = line.split(" ", 2)
        if len(parts) < 2:
            await self.send_line("* BAD Invalid command format")
            return

        tag = parts[0]
        cmd = parts[1].upper()
        args = parts[2] if len(parts) > 2 else ""

        # Handle UID commands e.g. "TAG UID FETCH 1 RFC822"
        is_uid = False
        if cmd == "UID" and args:
            uid_parts = args.split(" ", 1)
            cmd = "UID_" + uid_parts[0].upper()
            args = uid_parts[1] if len(uid_parts) > 1 else ""
            is_uid = True

        method_name = f"cmd_{cmd.lower()}"
        if hasattr(self, method_name):
            try:
                await getattr(self, method_name)(tag, args)
            except Exception as e:
                logger.error(f"Error handling IMAP command {cmd}: {e}", exc_info=True)
                await self.send_line(f"{tag} NO Command failed: {e}")
        else:
            await self.send_line(f"{tag} BAD Command not implemented: {cmd}")

    async def cmd_capability(self, tag: str, args: str):
        await self.send_line("* CAPABILITY IMAP4rev1 AUTH=PLAIN")
        await self.send_line(f"{tag} OK CAPABILITY completed")

    async def cmd_noop(self, tag: str, args: str):
        await self.send_line(f"{tag} OK NOOP completed")

    async def cmd_login(self, tag: str, args: str):
        try:
            tokens = shlex.split(args)
        except Exception:
            tokens = args.split()

        if len(tokens) < 2:
            await self.send_line(f"{tag} BAD LOGIN requires username and password")
            return

        username, password = tokens[0], tokens[1]
        configured_pass = settings.imap.auth_password

        if configured_pass and password != configured_pass and password != settings.server.api_key:
            await self.send_line(f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials")
            return

        self.username = username
        self.state = "AUTH"
        await self.send_line(f"{tag} OK [CAPABILITY IMAP4rev1] LOGIN successful")

    async def cmd_list(self, tag: str, args: str):
        await self.send_line('* LIST (\\HasNoChildren) "/" "INBOX"')
        await self.send_line(f"{tag} OK LIST completed")

    async def cmd_lsub(self, tag: str, args: str):
        await self.send_line('* LSUB (\\HasNoChildren) "/" "INBOX"')
        await self.send_line(f"{tag} OK LSUB completed")

    async def cmd_select(self, tag: str, args: str):
        await self._select_internal(tag, args, read_only=False)

    async def cmd_examine(self, tag: str, args: str):
        await self._select_internal(tag, args, read_only=True)

    async def _select_internal(self, tag: str, args: str, read_only: bool = False):
        if self.state not in ("AUTH", "SELECTED"):
            await self.send_line(f"{tag} NO Must be authenticated")
            return

        mailbox_name = args.strip().strip('"').strip("'")
        self.selected_mailbox = mailbox_name
        self.state = "SELECTED"

        target_to = self.username if (self.username and "@" in self.username) else None
        emails = await get_imap_mailbox_emails(to_address=target_to, limit=500)
        self.selected_emails = list(reversed(emails))

        count = len(self.selected_emails)
        recent_count = sum(1 for e in self.selected_emails if not e.get("is_read"))

        await self.send_line(f"* {count} EXISTS")
        await self.send_line(f"* {recent_count} RECENT")
        await self.send_line("* FLAGS (\\Seen \\Answered \\Flagged \\Deleted \\Draft)")
        await self.send_line("* OK [PERMANENTFLAGS (\\Seen \\Deleted \\*)] Flags permitted.")
        await self.send_line("* OK [UIDVALIDITY 1] UIDs valid")
        next_uid = (self.selected_emails[-1]["id"] + 1) if count > 0 else 1
        await self.send_line(f"* OK [UIDNEXT {next_uid}] Predicted next UID")
        mode = "READ-ONLY" if read_only else "READ-WRITE"
        await self.send_line(f"{tag} OK [{mode}] SELECT completed")

    async def cmd_status(self, tag: str, args: str):
        target_to = self.username if (self.username and "@" in self.username) else None
        emails = await get_imap_mailbox_emails(to_address=target_to, limit=500)
        count = len(emails)
        unseen = sum(1 for e in emails if not e.get("is_read"))
        await self.send_line(f'* STATUS "INBOX" (MESSAGES {count} UNSEEN {unseen} UIDVALIDITY 1)')
        await self.send_line(f"{tag} OK STATUS completed")

    async def cmd_search(self, tag: str, args: str, is_uid: bool = False):
        if self.state != "SELECTED":
            await self.send_line(f"{tag} NO Mailbox not selected")
            return

        target_to = self.username if (self.username and "@" in self.username) else None
        emails = await get_imap_mailbox_emails(to_address=target_to, limit=500)
        self.selected_emails = list(reversed(emails))


        matched_nums = []
        args_upper = args.upper()

        for idx, item in enumerate(self.selected_emails, start=1):
            val = item["id"] if is_uid else idx
            if "UNSEEN" in args_upper:
                if not item.get("is_read"):
                    matched_nums.append(str(val))
            elif "SEEN" in args_upper:
                if item.get("is_read"):
                    matched_nums.append(str(val))
            else:
                matched_nums.append(str(val))

        num_str = " ".join(matched_nums)
        await self.send_line(f"* SEARCH {num_str}".strip())
        await self.send_line(f"{tag} OK SEARCH completed")

    async def cmd_uid_search(self, tag: str, args: str):
        await self.cmd_search(tag, args, is_uid=True)

    async def cmd_fetch(self, tag: str, args: str, is_uid: bool = False):
        if self.state != "SELECTED":
            await self.send_line(f"{tag} NO Mailbox not selected")
            return

        parts = args.split(" ", 1)
        if not parts or not parts[0]:
            await self.send_line(f"{tag} BAD Missing fetch parameters")
            return

        seq_set = parts[0]
        items_req = parts[1].upper() if len(parts) > 1 else "(FLAGS)"

        target_items = []
        if is_uid:
            try:
                target_ids = [int(x) for x in re.findall(r"\d+", seq_set)]
                for idx, email_summary in enumerate(self.selected_emails, start=1):
                    if email_summary["id"] in target_ids or "*" in seq_set:
                        target_items.append((idx, email_summary))
            except Exception:
                pass
        else:
            if ":" in seq_set:
                start_str, end_str = seq_set.split(":", 1)
                start = int(start_str) if start_str.isdigit() else 1
                end = len(self.selected_emails) if end_str == "*" else int(end_str)
                for idx in range(start, min(end + 1, len(self.selected_emails) + 1)):
                    target_items.append((idx, self.selected_emails[idx - 1]))
            elif seq_set == "*":
                if self.selected_emails:
                    last_idx = len(self.selected_emails)
                    target_items.append((last_idx, self.selected_emails[-1]))
            elif seq_set.isdigit():
                idx = int(seq_set)
                if 1 <= idx <= len(self.selected_emails):
                    target_items.append((idx, self.selected_emails[idx - 1]))

        for seq_num, summary in target_items:
            full_email = await get_email_by_id(summary["id"])
            if not full_email:
                continue

            raw_eml_str = full_email.get("raw_eml", "")
            if not raw_eml_str:
                from_hdr = full_email["from_address"]
                to_hdr = full_email["to_address"]
                subj_hdr = full_email["subject"]
                date_hdr = full_email["created_at"]
                body_txt = full_email["body_text"]
                raw_eml_str = f"From: {from_hdr}\r\nTo: {to_hdr}\r\nSubject: {subj_hdr}\r\nDate: {date_hdr}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body_txt}"

            raw_bytes = raw_eml_str.encode("utf-8", errors="replace")
            flags_str = "\\Seen" if full_email.get("is_read") else ""
            uid_val = full_email["id"]
            rfc_size = len(raw_bytes)
            internal_date = full_email.get("created_at", "15-Aug-2026 00:00:00 +0000")

            if "RFC822" in items_req or "BODY[]" in items_req:
                prefix = f"* {seq_num} FETCH (UID {uid_val} RFC822.SIZE {rfc_size} FLAGS ({flags_str}) RFC822 "
                await self.send_literal(prefix, raw_bytes, ")\r\n")
            elif "BODY[HEADER]" in items_req or "RFC822.HEADER" in items_req:
                headers_part = raw_eml_str.split("\n\n")[0] + "\r\n\r\n"
                hdr_bytes = headers_part.encode("utf-8")
                prefix = f"* {seq_num} FETCH (UID {uid_val} RFC822.SIZE {rfc_size} FLAGS ({flags_str}) BODY[HEADER] "
                await self.send_literal(prefix, hdr_bytes, ")\r\n")
            elif "BODY[TEXT]" in items_req:
                body_bytes = full_email.get("body_text", "").encode("utf-8")
                prefix = f"* {seq_num} FETCH (UID {uid_val} RFC822.SIZE {rfc_size} FLAGS ({flags_str}) BODY[TEXT] "
                await self.send_literal(prefix, body_bytes, ")\r\n")
            else:
                await self.send_line(f"* {seq_num} FETCH (UID {uid_val} RFC822.SIZE {rfc_size} FLAGS ({flags_str}))")

        await self.send_line(f"{tag} OK FETCH completed")

    async def cmd_uid_fetch(self, tag: str, args: str):
        await self.cmd_fetch(tag, args, is_uid=True)

    async def cmd_store(self, tag: str, args: str, is_uid: bool = False):
        if self.state != "SELECTED":
            await self.send_line(f"{tag} NO Mailbox not selected")
            return

        parts = args.split(" ", 2)
        seq_num = parts[0]
        flag_action = parts[1].upper() if len(parts) > 1 else ""
        flags_spec = parts[2] if len(parts) > 2 else ""

        if "\\SEEN" in flags_spec.upper():
            if seq_num.isdigit():
                idx = int(seq_num)
                if 1 <= idx <= len(self.selected_emails):
                    email_id = self.selected_emails[idx - 1]["id"]
                    is_read = "+" in flag_action
                    await mark_email_read(email_id, is_read)
                    await self.send_line(f"* {idx} FETCH (FLAGS (\\Seen))")

        await self.send_line(f"{tag} OK STORE completed")

    async def cmd_uid_store(self, tag: str, args: str):
        await self.cmd_store(tag, args, is_uid=True)

    async def cmd_close(self, tag: str, args: str):
        self.state = "AUTH"
        self.selected_mailbox = None
        self.selected_emails = []
        await self.send_line(f"{tag} OK CLOSE completed")

    async def cmd_logout(self, tag: str, args: str):
        self.state = "LOGOUT"
        await self.send_line("* BYE IMAP4rev1 Server logging out")
        await self.send_line(f"{tag} OK LOGOUT completed")

class ImapServerManager:
    def __init__(self):
        self.server = None

    async def start(self):
        if not settings.imap.enabled:
            logger.info("IMAP server is disabled in config.")
            return

        async def client_connected(reader, writer):
            session = ImapSession(reader, writer)
            await session.handle_client()

        try:
            self.server = await asyncio.start_server(
                client_connected,
                host=settings.imap.host,
                port=settings.imap.port
            )
            logger.info(f"Virtual IMAP Server listening on {settings.imap.host}:{settings.imap.port}")
        except Exception as e:
            logger.error(f"Failed to start IMAP Server on port {settings.imap.port}: {e}")

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("IMAP Server stopped.")

imap_manager = ImapServerManager()
