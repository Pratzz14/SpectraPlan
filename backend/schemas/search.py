from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["compare", "bm25", "qdrant", "hybrid"] = "compare"
    dataset: Literal["technical", "website", "all", "inspection"] = "technical"
    limit: int = Field(default=6, ge=1, le=8)
    expand_synonyms: bool = True
    source_id: str | None = Field(default=None, min_length=1, max_length=60)

    @field_validator("query")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Enter a search query")
        return value.strip()
