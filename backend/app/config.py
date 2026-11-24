from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    lm_studio_url: str = "http://127.0.0.1:1234/v1"
    lm_studio_model: str = ""
    lm_temperature: float = 0.1
    lm_timeout: float = 600.0
    lm_disable_thinking: bool = True

    # auto: connector > local LM Studio > public fallback
    # local: LM Studio only; public: public LLM only
    llm_provider: str = "auto"
    public_llm_enabled: bool = True
    public_llm_url: str = "https://text.pollinations.ai/openai"
    public_llm_model: str = "openai-fast"
    public_llm_label: str = "Pollinations"
    public_llm_api_key: str = ""
    public_llm_timeout: float = 120.0
    local_probe_timeout: float = 1.5

    max_sources: int = 6
    fetch_timeout: float = 20.0
    enable_bing_news: bool = True
    max_custom_sources: int = 10

    require_connector: bool = False
    session_ttl_seconds: int = 43200
    pairing_ttl_seconds: int = 600
    session_cookie_name: str = "source_overlap_session"
    session_cookie_secure: bool = False

    cache_ttl_seconds: int = 86400
    cache_dir: Path = BASE_DIR / ".cache"
    frontend_dist: Path = BASE_DIR.parent / "frontend" / "dist"
    project_url: str = "https://github.com/dcallif/source-overlap"

    user_agent: str = (
        "SourceOverlap/0.1 (personal research tool; "
        "+https://github.com/anomalyco/opencode)"
    )


settings = Settings()
settings.cache_dir.mkdir(parents=True, exist_ok=True)
