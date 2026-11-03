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

    dashscope_api_key: SecretStr = SecretStr("")
    dashscope_base_url: str = "https://ws-xprw8y59epuehnse.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    qwen_extraction_model: str = "qwen3.7-flash"
    groq_api_key: SecretStr = SecretStr("")
    regolo_api_key: SecretStr = SecretStr("")
    llmtech_api_key: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "models/gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_max_output_tokens: int = Field(default=2048, ge=128, le=65536)
    gemini_thinking_level: Literal["low", "medium", "high"] = "medium"
    provider_name: Literal["auto", "gemini", "groq", "llmtech", "regolo"] = "auto"
    provider_order: str = "gemini,llmtech,groq"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "qwen/qwen3.8-27b"
    regolo_base_url: str = "https://api.regolo.ai/v1"
    regolo_model: str = "Llama-3.3-70B-Instruct"
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

    @field_validator("provider_base_url", "groq_base_url", "llmtech_base_url", "gemini_base_url", "regolo_base_url", "dashscope_base_url")
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

    @field_validator("provider_model", "groq_model", "llmtech_model", "gemini_model", "regolo_model")
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
        # Keep the original three-provider configuration valid while allowing
        # Regolo to be appended as an optional OpenAI-compatible fallback.
        if sorted(names) == ["groq", "llmtech"]:
            names.insert(0, "gemini")
        allowed = {"gemini", "llmtech", "groq", "regolo"}
        if len(names) not in {3, 4} or len(set(names)) != len(names) or not set(names) <= allowed:
            raise ValueError("PROVIDER_ORDER must contain three or four distinct supported providers")
        if not {"gemini", "llmtech", "groq"} <= set(names):
            raise ValueError("PROVIDER_ORDER must include gemini, llmtech and groq")
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
        if self.provider_name != "auto":
            return [self.provider_name]
        names = self.provider_order.split(",")
        if "regolo" not in names and self.usable_key(self.regolo_api_key):
            names.append("regolo")
        return names

    def for_provider(self, name: str) -> "Settings":
        if name not in {"gemini", "groq", "llmtech", "regolo", "auto"}:
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
            "your_groq_api_key_here", "your_llmtech_api_key_here", "your_gemini_api_key_here", "local-only-key", "your_key_here", "replace_me", "placeholder"
        }

    @property
    def provider_api_key(self) -> SecretStr:
        return getattr(self, f"{self.provider_name}_api_key") if self.provider_name != "auto" else getattr(self, f"{self.provider_names[0]}_api_key")

    @property
    def provider_configured(self) -> bool:
        return any(self.usable_key(getattr(self, f"{name}_api_key")) for name in self.provider_names)

    @property
    def gemini_configured(self) -> bool:
        return self.usable_key(self.gemini_api_key)
