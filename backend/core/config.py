"""Backend-only configuration. Paths are anchored to the project, not the CWD."""

from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    provider_name: Literal["dashscope"] = "dashscope"
    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    provider_model: str = "qwen3.8-flash"
    provider_base_url: str | None = None
    qwen_extraction_model: str = "qwen3.8-flash"
    provider_call_timeout_s: float = Field(default=90, gt=0, le=300)
    request_deadline_s: float = Field(default=240, gt=0, le=600)
    assessment_max_description_chars: int = Field(default=8000, ge=1, le=20000)
    provider_max_retries: int = Field(default=2, ge=0, le=2)
    provider_max_completion_tokens: int = Field(default=4096, ge=128, le=16384)
    extraction_max_completion_tokens: int = Field(default=3072, ge=128, le=16384)
    synthesis_max_completion_tokens: int = Field(default=4096, ge=128, le=16384)
    retrieval_semantic_min_score: float = Field(default=0.65, ge=0, le=1, allow_inf_nan=False)
    source_dir: Path = Path("knowledge/original_sources")
    corpus_dir: Path = Path("knowledge")
    smoke_output_dir: Path = Path("outputs/provider_smoke")
    explainability_db_path: Path = Path("outputs/assessment/explainability.sqlite")
    ingest_cache_dir: Path = Path("outputs/ingest/cache")
    embedding_cache_dir: Path = Path("outputs/embedding_models")
    web_corpus_dir: Path = Path("knowledge/web")
    knowledge_extraction_attempts: int = Field(default=3, ge=1, le=5)
    knowledge_retry_delay_s: float = Field(default=1, ge=0, le=10)
    knowledge_ocr_tessdata: str | None = None
    knowledge_ocr_language: str = "eng"
    knowledge_ocr_timeout_s: float = Field(default=60, gt=0, le=180)
    knowledge_work_dir: Path = Path("outputs/pdf_knowledge")
    knowledge_upload_max_bytes: int = Field(default=52428800, ge=1024, le=209715200)
    ingest_concurrency: int = Field(default=1, ge=1, le=4)
    ingest_max_output_tokens: int = Field(default=1000, ge=256, le=16384)

    @field_validator("source_dir", "corpus_dir", "smoke_output_dir", "explainability_db_path", "ingest_cache_dir", "embedding_cache_dir", "web_corpus_dir", "knowledge_work_dir")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value.resolve() if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @field_validator("provider_base_url", "dashscope_base_url")
    @classmethod
    def validate_base_url(cls, value):
        from urllib.parse import urlsplit
        if value is None: return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Use an HTTP(S) URL without credentials, query or fragment")
        return value.rstrip("/")

    @field_validator("provider_model", "qwen_extraction_model")
    @classmethod
    def nonblank_model(cls, value):
        if not value.strip(): raise ValueError("Model ID must not be blank")
        return value.strip()

    @model_validator(mode="after")
    def resolve_endpoint(self):
        if self.provider_base_url is None: self.provider_base_url = self.dashscope_base_url
        return self

    @staticmethod
    def usable_key(value):
        key = value.get_secret_value().strip().lower()
        return bool(key) and not key.startswith("your_") and key not in {"replace_me", "placeholder", "local-only-key"}

    @property
    def provider_api_key(self):
        return self.dashscope_api_key

    @property
    def provider_configured(self):
        return self.usable_key(self.dashscope_api_key)
