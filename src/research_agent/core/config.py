"""Configuration and settings management for Research Agent."""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """LLM configuration."""

    default_provider: str = "claude"
    generation_model: str = "claude-3-5-sonnet-20241022"
    planning_model: str = "claude-3-5-sonnet-20241022"
    synthesis_model: str = "claude-3-5-sonnet-20241022"
    
    # API keys from environment
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Local LLM configuration
    local_base_url: str = "http://localhost:11434"
    local_model: str = "llama2"
    
    # Generation settings
    generation_temperature: float = 0.7
    planning_temperature: float = 0.3
    synthesis_temperature: float = 0.5
    
    max_tokens_per_call: int = 2000
    
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_LLM_",
        env_file=".env",
        case_sensitive=False,
    )


class SandboxSettings(BaseSettings):
    """Sandbox execution configuration."""

    mode: str = "path-validation"  # "path-validation" or "podman"
    max_file_size_kb: int = 50
    max_line_count: int = 1000
    max_search_results: int = 100
    tool_timeout_seconds: int = 10
    max_concurrent_tools: int = 3
    network_enabled: bool = False
    
    # Environment variables to pass to tools
    allowed_env_vars: list[str] = ["PATH", "HOME", "LANG"]
    
    # Scratch directory
    scratch_dir: Optional[str] = None  # Auto-created if None
    scratch_size_mb: int = 100
    scratch_cleanup: bool = True
    
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_SANDBOX_",
        env_file=".env",
        case_sensitive=False,
    )


class ResearchSettings(BaseSettings):
    """Research run configuration."""

    max_exploratory_ideas: int = 20
    batch_size: int = 5
    batch_max_tokens: int = 8000
    max_tool_calls_per_idea: int = 10
    wall_clock_limit_seconds: int = 3600
    exploration_depth: str = "medium"  # "shallow", "medium", "deep"
    
    # Learning configuration
    memory_dedup_threshold: float = 0.8
    min_memory_confidence: float = 0.6
    learning_enabled: bool = True
    
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_",
        env_file=".env",
        case_sensitive=False,
    )


class StorageSettings(BaseSettings):
    """Storage and database configuration."""

    database_url: str = "sqlite:///.research-agent/research.db"
    memory_index_path: str = ".research-agent/memory-index.json"
    reports_dir: str = ".research-agent/runs/reports"
    runs_state_dir: str = ".research-agent/runs"
    
    # Database settings
    db_echo: bool = False  # Log SQL queries
    db_pool_size: int = 5
    db_max_overflow: int = 10
    
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_STORAGE_",
        env_file=".env",
        case_sensitive=False,
    )


class LoggingSettings(BaseSettings):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"  # "json" or "text"
    file_path: Optional[str] = ".research-agent/agent.log"
    
    model_config = SettingsConfigDict(
        env_prefix="RESEARCH_LOGGING_",
        env_file=".env",
        case_sensitive=False,
    )


class Settings(BaseSettings):
    """Main settings class combining all configuration."""

    # Component settings
    llm: LLMSettings = LLMSettings()
    sandbox: SandboxSettings = SandboxSettings()
    research: ResearchSettings = ResearchSettings()
    storage: StorageSettings = StorageSettings()
    logging: LoggingSettings = LoggingSettings()
    
    # Environment
    debug: bool = False
    project_root: Path = Path(__file__).parent.parent.parent.parent
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
    )
    
    def ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        Path(self.storage.reports_dir).mkdir(parents=True, exist_ok=True)
        Path(self.storage.runs_state_dir).mkdir(parents=True, exist_ok=True)
        if self.sandbox.scratch_dir:
            Path(self.sandbox.scratch_dir).mkdir(parents=True, exist_ok=True)
        if self.logging.file_path:
            Path(self.logging.file_path).parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
