from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
SECRET_KEY_FILE = BACKEND_DIR / ".secret_key"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    bungie_redirect_uri: str = "http://localhost:8000/api/auth/callback"
    frontend_origin: str = "http://localhost:5173"
    youtube_api_key: str = ""
    token_encryption_key: str = ""

    @property
    def fernet_key(self) -> bytes:
        """Return a stable Fernet key, generating and persisting one if needed."""
        if self.token_encryption_key:
            return self.token_encryption_key.encode()
        if SECRET_KEY_FILE.exists():
            return SECRET_KEY_FILE.read_bytes()
        key = Fernet.generate_key()
        SECRET_KEY_FILE.write_bytes(key)
        return key

    @property
    def is_bungie_configured(self) -> bool:
        return bool(self.bungie_api_key and self.bungie_client_id and self.bungie_client_secret)


@lru_cache
def get_settings() -> Settings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return Settings()
