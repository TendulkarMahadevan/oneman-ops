"""Application settings. Loaded from the environment / .env and validated on startup."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./oneman.db"

    vultr_inference_api_key: str = ""
    vultr_inference_base_url: str = "https://api.vultrinference.com/v1"
    vultr_inference_model: str = ""
    llm_timeout_seconds: float = Field(default=45.0, gt=0)

    approval_required_over_usd: Decimal = Field(default=Decimal("5000"), gt=0)
    invoice_price_tolerance_pct: Decimal = Field(default=Decimal("2.0"), ge=0, le=100)
    low_confidence_threshold: float = Field(default=0.7, ge=0, le=1)

    score_weight_price: float = Field(default=0.5, ge=0, le=1)
    score_weight_lead_time: float = Field(default=0.3, ge=0, le=1)
    score_weight_rating: float = Field(default=0.2, ge=0, le=1)

    upload_dir: str = "uploads"
    max_upload_mb: int = Field(default=5, ge=1, le=50)

    cors_origins: str = ""

    @model_validator(mode="after")
    def _validate(self) -> "Settings":
        total = self.score_weight_price + self.score_weight_lead_time + self.score_weight_rating
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"SCORE_WEIGHT_* must sum to 1.0, got {total}")
        if self.vultr_inference_api_key and not self.vultr_inference_model:
            raise ValueError("VULTR_INFERENCE_MODEL is required when VULTR_INFERENCE_API_KEY is set")
        if not self.vultr_inference_base_url.startswith(("http://", "https://")):
            raise ValueError("VULTR_INFERENCE_BASE_URL must be an http(s) URL")
        return self

    @property
    def llm_configured(self) -> bool:
        return bool(self.vultr_inference_api_key and self.vultr_inference_model)

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
