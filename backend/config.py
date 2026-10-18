"""Backend-only configuration. Paths are anchored to the project, not the CWD."""

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, PrivateAttr, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    groq_api_key: SecretStr = SecretStr("")
    llmtech_api_key: SecretStr = SecretStr("")
    provider_name: Literal["auto", "groq", "llmtech"] = "auto"
    provider_order: str = "llmtech,groq"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "qwen/qwen3.8-27b"
    llmtech_base_url: str = "https://api.llmtech.eu/v1"
    llmtech_model: str = "nvidia/Qwen3.8-27B-NVFP4"
    # Legacy single-provider overrides apply only in explicit/pinned mode.
    provider_base_url: str | None = None
    provider_model: str | None = None
    provider_probe_timeout_s: float = Field(default=8, gt=0, le=30)
    provider_health_ttl_s: float = Field(default=300, gt=0, le=3600)
    provider_failure_ttl_s: float = Field(default=30, gt=0, le=300)
    _provider_router: Any = PrivateAttr(default=None)
    provider_reasoning_effort: Literal["none", "default", "low", "medium", "high"] = "medium"
    provider_call_timeout_s: float = Field(default=30, gt=0, le=300)
    request_deadline_s: float = Field(default=90, gt=0, le=600)
    assessment_max_description_chars: int = Field(default=8000, ge=1, le=20000)
    provider_max_retries: int = Field(default=2, ge=0, le=2)
    provider_max_completion_tokens: int = Field(default=4096, ge=128, le=16384)
    extraction_max_completion_tokens: int = Field(default=3072, ge=128, le=16384)
    synthesis_max_completion_tokens: int = Field(default=4096, ge=128, le=16384)
    retrieval_semantic_min_score: float = Field(default=0.65, ge=0, le=1, allow_inf_nan=False)
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

    @field_validator("provider_base_url", "groq_base_url", "llmtech_base_url")
    @classmethod
    def validate_base_url(cls, value: str | None) -> str | None:
        from urllib.parse import urlsplit

        if value is None:
            return value
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

    @field_validator("provider_model", "groq_model", "llmtech_model")
    @classmethod
    def nonblank_model(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not value.strip():
            raise ValueError("Model ID must not be blank")
        return value.strip()

    @field_validator("provider_order")
    @classmethod
    def valid_order(cls, value: str) -> str:
        names = [v.strip().lower() for v in value.split(",")]
        if sorted(names) != ["groq", "llmtech"]:
            raise ValueError("PROVIDER_ORDER must contain llmtech and groq exactly once")
        return ",".join(names)

    @model_validator(mode="after")
    def resolve_legacy_identity(self):
        name = self.provider_names[0]
        if self.provider_name == "auto" or self.provider_base_url is None:
            self.provider_base_url = getattr(self, f"{name}_base_url")
        if self.provider_name == "auto" or self.provider_model is None:
            self.provider_model = getattr(self, f"{name}_model")
        return self

    @property
    def provider_names(self) -> list[str]:
        return self.provider_order.split(",") if self.provider_name == "auto" else [self.provider_name]

    def for_provider(self, name: str) -> "Settings":
        if name not in {"groq", "llmtech", "auto"}:
            raise ValueError("Unknown provider mode")
        values = self.model_dump()
        values.update(provider_name=name, provider_base_url=None, provider_model=None)
        if name == self.provider_name and name != "auto":
            values.update(provider_base_url=self.provider_base_url, provider_model=self.provider_model)
        return Settings(_env_file=None, **values)

    @staticmethod
    def usable_key(value: SecretStr) -> bool:
        key = value.get_secret_value().strip().lower()
        return bool(key) and key not in {
            "your_groq_api_key_here", "your_llmtech_api_key_here", "your_key_here", "replace_me", "placeholder"
        }

    @property
    def provider_api_key(self) -> SecretStr:
        return self.llmtech_api_key if self.provider_name == "llmtech" else self.groq_api_key

    @property
    def provider_configured(self) -> bool:
        return any(self.usable_key(getattr(self, f"{name}_api_key")) for name in self.provider_names)
