"""Backend-only configuration. Paths are anchored to the project, not the CWD."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: SecretStr = SecretStr("")
    llmtech_api_key: SecretStr = SecretStr("")
    provider_name: Literal["groq", "llmtech"] = "groq"
    provider_base_url: str = "https://api.groq.com/openai/v1"
    provider_model: str = "qwen/qwen3.8-27b"
    provider_reasoning_effort: Literal["none", "default", "low", "medium", "high"] = "medium"
    provider_call_timeout_s: float = Field(default=30, gt=0, le=300)
    request_deadline_s: float = Field(default=90, gt=0, le=600)
    provider_max_retries: int = Field(default=2, ge=0, le=2)
    provider_max_completion_tokens: int = Field(default=4096, ge=128, le=16384)
    source_dir: Path = Path("knowledge/original_sources")
    corpus_dir: Path = Path("knowledge")
    smoke_output_dir: Path = Path("outputs/provider_smoke")
    ingest_cache_dir: Path = Path("outputs/ingest/cache")
    embedding_cache_dir: Path = Path("outputs/embedding_models")
    web_corpus_dir: Path = Path("knowledge/web")
    ingest_concurrency: int = Field(default=1, ge=1, le=4)
    ingest_max_output_tokens: int = Field(default=1000, ge=256, le=16384)

    @field_validator("source_dir", "corpus_dir", "smoke_output_dir", "ingest_cache_dir", "embedding_cache_dir", "web_corpus_dir")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("provider_base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError("Use an HTTP(S) base URL without credentials, query or fragment")
        return value.rstrip("/")

    @field_validator("provider_model")
    @classmethod
    def nonblank_model(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Model ID must not be blank")
        return value.strip()

    @property
    def provider_api_key(self) -> SecretStr:
        return self.llmtech_api_key if self.provider_name == "llmtech" else self.groq_api_key

    @property
    def provider_configured(self) -> bool:
        key = self.provider_api_key.get_secret_value().strip()
        return bool(key) and key.lower() not in {
            "your_groq_api_key_here", "replace_me", "placeholder"
        }
