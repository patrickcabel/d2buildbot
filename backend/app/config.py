from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_PATH = DATA_DIR / "app.db"
SECRET_KEY_FILE = BACKEND_DIR / ".secret_key"


def _public_base_url() -> str | None:
    """Render (and similar hosts) expose the public HTTPS URL via env."""
    for key in ("RENDER_EXTERNAL_URL", "PUBLIC_BASE_URL"):
        val = (os.environ.get(key) or "").rstrip("/")
        if val:
            return val
    return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bungie_api_key: str = ""
    bungie_client_id: str = ""
    bungie_client_secret: str = ""
    # Leave blank on Render — derived from RENDER_EXTERNAL_URL.
    bungie_redirect_uri: str = ""
    frontend_origin: str = ""
    youtube_api_key: str = ""
    token_encryption_key: str = ""
    # Directory with Vite build output (index.html + assets/). Empty = auto-detect.
    static_dir: str = ""

    @property
    def resolved_frontend_origin(self) -> str:
        if self.frontend_origin.strip():
            return self.frontend_origin.rstrip("/")
        return _public_base_url() or "http://localhost:5173"

    @property
    def resolved_bungie_redirect_uri(self) -> str:
        if self.bungie_redirect_uri.strip():
            return self.bungie_redirect_uri
        base = _public_base_url() or "https://localhost:8000"
        return f"{base}/api/auth/callback"

    @property
    def resolved_static_dir(self) -> Path | None:
        if self.static_dir.strip():
            path = Path(self.static_dir)
        else:
            path = BACKEND_DIR / "static"
        if path.is_dir() and (path / "index.html").exists():
            return path
        return None

    @property
    def fernet_key(self) -> bytes:
        """Return a stable Fernet key, generating and persisting one if needed."""
        if self.token_encryption_key:
            raw = self.token_encryption_key.encode()
            try:
                Fernet(raw)
                return raw
            except (ValueError, TypeError):
                # Render's generateValue (and other random secrets) aren't Fernet keys.
                return base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
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
