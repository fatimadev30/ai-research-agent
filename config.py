"""Application configuration loaded from environment / Streamlit secrets."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import streamlit as st
except ImportError:
    st = None


def _load_dotenv_file() -> dict[str, str]:
    """Parse the project-root .env file (no external dependency)."""
    values: dict[str, str] = {}
    path = Path(__file__).resolve().parent / ".env"
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            values[key.strip()] = val.strip().strip('"').strip("'")
    except OSError:
        pass
    return values


_DOTENV = _load_dotenv_file()


def _get_secret(key: str, default: str = "") -> str:
    """Read a value from os.environ, the .env file, then Streamlit secrets."""
    val = os.environ.get(key, "")
    if val:
        return val
    val = _DOTENV.get(key, "")
    if val:
        return val
    if st is not None:
        try:
            return st.secrets.get(key, default)
        except Exception:
            pass
    return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    supabase_service_key: str
    tinyfish_api_key: str
    tinyfish_base_url: str
    google_client_secrets_path: str
    max_target_records: int
    default_batch_size: int
    default_concurrency: int
    request_timeout: int
    max_retries: int
    temp_dir: str

    @classmethod
    def load(cls) -> "Settings":
        return cls(
            supabase_url=_get_secret("SUPABASE_URL", _get_secret("VITE_SUPABASE_URL")),
            supabase_key=_get_secret("SUPABASE_ANON_KEY", _get_secret("VITE_SUPABASE_ANON_KEY")),
            supabase_service_key=_get_secret("SUPABASE_SERVICE_ROLE_KEY"),
            tinyfish_api_key=_get_secret("TINYFISH_API_KEY"),
            tinyfish_base_url=_get_secret("TINYFISH_BASE_URL", "https://api.tinyfish.ai"),
            google_client_secrets_path=_get_secret("GOOGLE_CLIENT_SECRETS_PATH", ""),
            max_target_records=int(_get_secret("MAX_TARGET_RECORDS", "500")),
            default_batch_size=int(_get_secret("DEFAULT_BATCH_SIZE", "20")),
            default_concurrency=int(_get_secret("DEFAULT_CONCURRENCY", "3")),
            request_timeout=int(_get_secret("REQUEST_TIMEOUT", "30")),
            max_retries=int(_get_secret("MAX_RETRIES", "3")),
            temp_dir=_get_secret("TEMP_DIR", "/tmp/research_agent"),
        )

    @property
    def has_tinyfish(self) -> bool:
        return bool(self.tinyfish_api_key)

    @property
    def has_supabase(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def has_google(self) -> bool:
        return bool(self.google_client_secrets_path) and os.path.exists(self.google_client_secrets_path)


def get_settings() -> Settings:
    return Settings.load()
