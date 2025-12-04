"""
Configuration management for CopForge.

Uses pydantic-settings for environment variable parsing and validation.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class TelemetrySettings(BaseSettings):
    """Telemetry configuration."""

    model_config = SettingsConfigDict(env_prefix="TELEMETRY_")

    # LangSmith (for LLM tracing)
    langsmith_enabled: bool = True
    langsmith_api_key: SecretStr | None = Field(default=None, alias="LANGCHAIN_API_KEY")
    langsmith_project: str = Field(default="copforge", alias="LANGCHAIN_PROJECT")
    langsmith_tracing: bool = Field(default=True, alias="LANGCHAIN_TRACING_V2")

    # OpenTelemetry (for infrastructure tracing)
    otel_enabled: bool = True
    otel_service_name: str = "copforge"
    otel_exporter_endpoint: str = "http://localhost:4317"
    otel_exporter_type: Literal["otlp", "console", "none"] = "otlp"


class A2ASettings(BaseSettings):
    """A2A Protocol configuration."""

    model_config = SettingsConfigDict(env_prefix="A2A_")

    # Ingest Agent
    ingest_agent_host: str = "127.0.0.1"
    ingest_agent_port: int = 8001
    ingest_agent_name: str = "CopForge Ingest Agent"
    ingest_agent_version: str = "0.1.0"


class MCPSettings(BaseSettings):
    """MCP Server configuration."""

    model_config = SettingsConfigDict(env_prefix="MCP_")

    # Firewall MCP Server
    firewall_host: str = "127.0.0.1"
    firewall_port: int = 8010

    # COP Fusion MCP Server
    cop_fusion_host: str = "127.0.0.1"
    cop_fusion_port: int = 8011


class LLMSettings(BaseSettings):
    """LLM provider configuration."""

    model_config = SettingsConfigDict(env_prefix="LLM_")

    # Default provider
    default_provider: Literal["openai", "anthropic"] = "openai"

    # OpenAI
    openai_api_key: SecretStr | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = "gpt-4o"

    # Anthropic
    anthropic_api_key: SecretStr | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = "claude-sonnet-4-20250514"


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application info
    app_name: str = "copforge"
    app_env: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Sub-configurations
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    a2a: A2ASettings = Field(default_factory=A2ASettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Global settings instance
settings = get_settings()
