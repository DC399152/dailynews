from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_database_url: str = "sqlite:///./data/ai_daily_brief.db"
    app_workspace_dir: Path = Path("./workspace")
    app_log_level: str = "INFO"

    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = ""

    agent_max_turns: int = Field(default=12, ge=1, le=100)
    agent_max_tool_calls: int = Field(default=24, ge=1, le=200)
    agent_run_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    tool_timeout_seconds: int = Field(default=15, ge=1, le=300)

    tool_max_read_bytes: int = Field(default=1_000_000, ge=1)
    tool_max_write_bytes: int = Field(default=1_000_000, ge=1)
    tool_max_output_chars: int = Field(default=20_000, ge=1)
    fetch_max_response_bytes: int = Field(default=2_000_000, ge=1)
    fetch_max_article_chars: int = Field(default=20_000, ge=1)

    smtp_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
