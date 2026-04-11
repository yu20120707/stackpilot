from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(..., validation_alias="APP_ENV")
    port: int = Field(..., validation_alias="PORT", ge=1, le=65535)
    log_level: str = Field(..., validation_alias="LOG_LEVEL")
    feishu_app_id: str = Field(..., validation_alias="FEISHU_APP_ID")
    feishu_app_secret: str = Field(..., validation_alias="FEISHU_APP_SECRET")
    feishu_base_url: str = Field(
        default="https://open.feishu.cn/open-apis",
        validation_alias="FEISHU_BASE_URL",
    )
    llm_base_url: str = Field(..., validation_alias="LLM_BASE_URL")
    llm_api_key: str = Field(..., validation_alias="LLM_API_KEY")
    llm_model: str = Field(..., validation_alias="LLM_MODEL")
    knowledge_dir: Path = Field(
        default=Path("data/knowledge"),
        validation_alias="KNOWLEDGE_DIR",
    )
    memory_dir: Path = Field(
        default=Path("data/memory"),
        validation_alias="MEMORY_DIR",
    )
    action_dir: Path = Field(
        default=Path("data/actions"),
        validation_alias="ACTION_DIR",
    )

    feishu_encrypt_key: str | None = Field(
        default=None,
        validation_alias="FEISHU_ENCRYPT_KEY",
    )
    feishu_verification_token: str | None = Field(
        default=None,
        validation_alias="FEISHU_VERIFICATION_TOKEN",
    )
    llm_timeout_seconds: int = Field(
        default=30,
        validation_alias="LLM_TIMEOUT_SECONDS",
        ge=1,
    )
    feishu_timeout_seconds: int = Field(
        default=30,
        validation_alias="FEISHU_TIMEOUT_SECONDS",
        ge=1,
    )
    max_thread_messages: int = Field(
        default=50,
        validation_alias="MAX_THREAD_MESSAGES",
        ge=1,
    )
    max_knowledge_hits: int = Field(
        default=5,
        validation_alias="MAX_KNOWLEDGE_HITS",
        ge=1,
    )

    @field_validator(
        "app_env",
        "log_level",
        "feishu_app_id",
        "feishu_app_secret",
        "feishu_base_url",
        "llm_base_url",
        "llm_api_key",
        "llm_model",
        mode="before",
    )
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @field_validator("feishu_encrypt_key", "feishu_verification_token", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("knowledge_dir", "memory_dir", "action_dir", mode="before")
    @classmethod
    def normalize_path_dir(cls, value: str | Path, info) -> Path:  # noqa: ANN001
        if isinstance(value, Path):
            return value
        normalized = value.strip()
        if not normalized:
            defaults = {
                "knowledge_dir": Path("data/knowledge"),
                "memory_dir": Path("data/memory"),
                "action_dir": Path("data/actions"),
            }
            return defaults[info.field_name]
        return Path(normalized)

    @property
    def resolved_knowledge_dir(self) -> Path:
        return self.knowledge_dir.resolve()

    @property
    def resolved_memory_dir(self) -> Path:
        return self.memory_dir.resolve()

    @property
    def resolved_action_dir(self) -> Path:
        return self.action_dir.resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
