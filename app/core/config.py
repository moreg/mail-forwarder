import os
from pathlib import Path
import yaml
from pydantic import BaseModel, Field

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    api_key: str = ""

class SmtpConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 2525
    domain: str = "localhost"
    max_message_size: int = 10485760

class ImapConfig(BaseModel):
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 1143
    auth_password: str = "password123"

class StorageConfig(BaseModel):
    db_path: str = "data/mailbox.db"
    save_raw_eml: bool = True
    retention_days: int = 30

class OtpConfig(BaseModel):
    keywords: list[str] = Field(default_factory=lambda: [
        "验证码", "校验码", "动态码", "激活码", "安全码", "动态口令",
        "verification code", "security code", "confirmation code",
        "one-time password", "otp", "pin code", "passcode", "auth code", "login code"
    ])

class Settings(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    smtp: SmtpConfig = Field(default_factory=SmtpConfig)
    imap: ImapConfig = Field(default_factory=ImapConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    otp: OtpConfig = Field(default_factory=OtpConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        if config_path is None:
            config_path = BASE_DIR / "config.yaml"
        else:
            config_path = Path(config_path)

        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            return cls(**data)
        return cls()

    @property
    def absolute_db_path(self) -> Path:
        p = Path(self.storage.db_path)
        if not p.is_absolute():
            p = BASE_DIR / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

settings = Settings.load()
