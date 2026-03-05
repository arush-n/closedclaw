"""
Closedclaw Configuration Module

Manages all configuration settings using pydantic-settings.
Supports environment variables and ~/.closedclaw/config.json.
"""

import os
import json
import secrets
import hmac
from pathlib import Path
from typing import Optional, Literal
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Default paths
CLOSEDCLAW_DIR = Path.home() / ".closedclaw"
CONFIG_FILE = CLOSEDCLAW_DIR / "config.json"
TOKEN_FILE = CLOSEDCLAW_DIR / "token"
DB_FILE = CLOSEDCLAW_DIR / "memory.db"
POLICIES_DIR = CLOSEDCLAW_DIR / "policies"
AUDIT_DIR = CLOSEDCLAW_DIR / "audit"


class LocalEngineSettings(BaseSettings):
    """
    Settings for local LLM engine (Ollama).
    
    Configures local model selection and hardware optimization.
    """
    model_config = SettingsConfigDict(
        env_prefix="CLOSEDCLAW_LOCAL_",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Enable/disable local engine
    enabled: bool = Field(default=True, description="Enable local LLM engine")
    
    # Hardware profile: minimal, standard, performance, workstation
    hardware_profile: Literal["minimal", "standard", "performance", "workstation"] = Field(
        default="standard",
        description="Hardware profile for model selection"
    )
    
    # LLM Model Configuration
    # Default to llama3.2-3b-q4 (3B params, 4-bit quant) for universal compatibility
    llm_model: str = Field(
        default="llama3.2-3b-q4",
        description="Local LLM model key (see local.py for options)"
    )
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=2000, ge=1, le=32768)
    llm_top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    llm_top_k: int = Field(default=40, ge=1, le=100)
    
    # Embedding Model Configuration
    embedding_model: str = Field(
        default="nomic-embed-text",
        description="Local embedding model key"
    )
    
    # Ollama server settings
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Ollama server URL"
    )
    
    # Memory optimization
    num_gpu_layers: Optional[int] = Field(
        default=None,
        description="Number of GPU layers (-1 for auto)"
    )
    num_threads: Optional[int] = Field(
        default=None,
        description="Number of CPU threads (None for auto)"
    )
    
    # Context management
    memory_context_budget: int = Field(
        default=4096,
        description="Max tokens for memory context injection"
    )
    
    # Auto-pull models if not installed
    auto_pull_models: bool = Field(
        default=True,
        description="Automatically pull models if not installed"
    )


class Settings(BaseSettings):
    """
    Closedclaw configuration settings.
    
    All settings can be overridden via environment variables prefixed with CLOSEDCLAW_
    """
    model_config = SettingsConfigDict(
        env_prefix="CLOSEDCLAW_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def __hash__(self) -> int:
        """Make Settings hashable for use with lru_cache and FastAPI Depends."""
        return id(self)

    def __eq__(self, other: object) -> bool:
        return self is other
    
    # Server settings
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8765, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")
    reload: bool = Field(default=False, description="Enable hot-reload")
    
    # LLM Provider settings
    provider: Literal["openai", "anthropic", "ollama", "groq", "together"] = Field(
        default="openai", 
        description="Default LLM provider"
    )
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1", 
        description="OpenAI API base URL"
    )
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    ollama_base_url: str = Field(
        default="http://localhost:11434", 
        description="Ollama server URL"
    )
    groq_api_key: Optional[str] = Field(default=None, description="Groq API key")
    together_api_key: Optional[str] = Field(default=None, description="Together API key")
    
    # Default model configurations
    default_model: str = Field(default="gpt-4o-mini", description="Default model to use")
    embedding_model: str = Field(
        default="text-embedding-3-small", 
        description="Embedding model (cloud provider)"
    )
    local_model: str = Field(
        default="llama3.2:latest", 
        description="Local Ollama model for privacy-sensitive operations"
    )
    
    # Local Engine Settings (nested config)
    local_engine: LocalEngineSettings = Field(
        default_factory=LocalEngineSettings,
        description="Local LLM engine configuration"
    )
    
    # Memory settings
    memory_db_path: Path = Field(default=DB_FILE, description="SQLite database path")
    vector_dimension: int = Field(default=768, description="Vector embedding dimension (768 for nomic-embed-text, 1536 for OpenAI)")
    max_memories_per_query: int = Field(default=10, description="Max memories to retrieve")
    
    # Privacy settings
    default_sensitivity: int = Field(
        default=1, 
        ge=0, 
        le=3, 
        description="Default sensitivity level for new memories (0-3)"
    )
    require_consent_level: int = Field(
        default=2, 
        ge=0, 
        le=3, 
        description="Sensitivity level requiring consent"
    )
    local_only_level: int = Field(
        default=2, 
        ge=0, 
        le=3, 
        description="Sensitivity level requiring local-only LLM"
    )
    enable_redaction: bool = Field(default=True, description="Enable PII redaction")
    
    # Crypto settings (always enabled — cannot be disabled)
    enable_encryption: bool = Field(default=True, description="Memory encryption (always on)")

    # Agent Swarm settings
    swarm_enabled: bool = Field(default=False, description="Enable the agent swarm system")
    swarm_max_agent_calls: int = Field(default=10, ge=1, le=50, description="Max agent calls per task")
    swarm_token_budget: int = Field(default=2000, ge=100, le=10000, description="Max tokens per swarm task")
    constitution_path: Optional[str] = Field(default=None, description="Path to constitution.json (default: ~/.closedclaw/constitution.json)")

    # Paths
    closedclaw_dir: Path = Field(default=CLOSEDCLAW_DIR, description="Config directory")
    policies_dir: Path = Field(default=POLICIES_DIR, description="Policies directory")
    audit_dir: Path = Field(default=AUDIT_DIR, description="Audit log directory")
    
    # Auth token (auto-generated if not set)
    auth_token: Optional[str] = Field(default=None, description="API authentication token")
    allow_provider_api_key_auth: bool = Field(
        default=False,
        description="Allow direct provider API keys as API auth credentials",
    )
    
    @field_validator("closedclaw_dir", "policies_dir", "audit_dir", "memory_db_path", mode="before")
    @classmethod
    def resolve_path(cls, v):
        if isinstance(v, str):
            return Path(v).expanduser().resolve()
        return v
    
    def ensure_directories(self):
        """Create required directories if they don't exist."""
        self.closedclaw_dir.mkdir(parents=True, exist_ok=True)
        self.policies_dir.mkdir(parents=True, exist_ok=True)
        self.audit_dir.mkdir(parents=True, exist_ok=True)
    
    def get_or_create_token(self) -> str:
        """Get existing token or generate a new one."""
        if self.auth_token:
            return self.auth_token
        
        token_file = self.closedclaw_dir / "token"
        if token_file.exists():
            return token_file.read_text().strip()
        
        # Generate new token
        self.ensure_directories()
        token = secrets.token_urlsafe(32)
        token_file.write_text(token)
        try:
            token_file.chmod(0o600)  # Read/write for owner only
        except OSError:
            # Windows ACLs may not honor POSIX chmod values.
            pass
        return token

    def is_local_auth_token(self, candidate: Optional[str]) -> bool:
        """Constant-time check for local auth token validity."""
        if not candidate:
            return False
        expected_token = self.get_or_create_token()
        return hmac.compare_digest(candidate, expected_token)
    
    # Fields that contain secrets and must be encrypted on disk
    _SENSITIVE_FIELDS = frozenset({
        "openai_api_key",
        "anthropic_api_key",
        "groq_api_key",
        "together_api_key",
    })

    def save(self):
        """Save current settings to config file. Sensitive fields are encrypted."""
        from closedclaw.api.core.crypto import encrypt_config_value

        self.ensure_directories()
        config_data = self.model_dump(
            exclude={"auth_token"},  # Don't save token in config
            exclude_none=True,
        )
        # Convert Path objects to strings for JSON
        for key, value in config_data.items():
            if isinstance(value, Path):
                config_data[key] = str(value)

        # Encrypt sensitive fields
        for field in self._SENSITIVE_FIELDS:
            if field in config_data and config_data[field]:
                config_data[field] = encrypt_config_value(str(config_data[field]))

        # Force encryption on
        config_data["enable_encryption"] = True

        with open(CONFIG_FILE, "w") as f:
            json.dump(config_data, f, indent=2)

    @classmethod
    def load(cls) -> "Settings":
        """Load settings from config file, merged with env vars. Decrypts sensitive fields."""
        from closedclaw.api.core.crypto import decrypt_config_value

        config_data = {}
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE) as f:
                config_data = json.load(f)

        # Decrypt sensitive fields
        for field in cls._SENSITIVE_FIELDS:
            if field in config_data and config_data[field]:
                config_data[field] = decrypt_config_value(str(config_data[field]))

        # Force encryption on regardless of stored value
        config_data["enable_encryption"] = True

        return cls(**config_data)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings.load()


def clear_settings_cache() -> None:
    """Invalidate the cached settings so the next call reloads from disk/env."""
    get_settings.cache_clear()


def init_closedclaw():
    """Initialize closedclaw directory structure and default config."""
    settings = get_settings()
    settings.ensure_directories()
    
    # Create default policies if none exist
    default_policies_file = settings.policies_dir / "default.json"
    if not default_policies_file.exists():
        from closedclaw.api.core.policies import DEFAULT_POLICIES
        with open(default_policies_file, "w") as f:
            json.dump(DEFAULT_POLICIES, f, indent=2)
    
    # Generate auth token
    settings.get_or_create_token()

    # Create default constitution if swarm enabled and file missing
    constitution_path = Path(settings.constitution_path) if settings.constitution_path else (settings.closedclaw_dir / "constitution.json")
    if not constitution_path.exists():
        from closedclaw.api.agents.swarm.constitution import Constitution
        Constitution(constitution_path)  # Creates default on init

    return settings


def init_local_engine(settings: Optional[Settings] = None, fast_startup: bool = False) -> dict:
    """
    Initialize the local LLM engine (Ollama).
    
    Checks Ollama availability, pulls required models if configured,
    and returns status information.
    
    Returns:
        dict with status information:
        - ollama_installed: bool
        - ollama_running: bool
        - models_available: list of installed model names
        - recommended_model: the recommended model for current hardware
        - hardware_profile: detected hardware profile
    """
    from closedclaw.api.core.local import OllamaManager, LocalEngineConfig
    
    if settings is None:
        settings = get_settings()
    
    manager = OllamaManager(base_url=settings.local_engine.ollama_base_url)
    
    status = {
        "ollama_installed": manager.is_installed(),
        "ollama_running": manager.is_running(),
        "models_available": [],
        "recommended_model": None,
        "hardware_profile": None,
        "embedding_model": settings.local_engine.embedding_model,
        "llm_model": settings.local_engine.llm_model,
    }
    
    if not status["ollama_installed"]:
        return status
    
    installed_models: list[str] = []
    if status["ollama_running"]:
        installed_models = manager.get_installed_models()
        status["models_available"] = installed_models
    
    # Fast startup mode skips heavier detection/model checks.
    if fast_startup:
        status["hardware_profile"] = settings.local_engine.hardware_profile
        status["recommended_model"] = settings.local_model
        return status

    # Detect hardware profile
    profile = manager.detect_hardware_profile()
    status["hardware_profile"] = profile.value
    
    # Get recommended config for detected hardware
    config = LocalEngineConfig.for_hardware_profile(profile)
    status["recommended_model"] = config.ollama_model_name
    
    # Auto-pull models if configured and Ollama running
    if settings.local_engine.auto_pull_models and status["ollama_running"]:
        from closedclaw.api.core.local import LOCAL_MODELS, LOCAL_EMBEDDING_MODELS
        updated = False

        def _has_model(models: list[str], model_name: str) -> bool:
            model_base = model_name.split(":")[0]
            return any(installed.startswith(model_base) for installed in models)
        
        # Ensure LLM model is available
        llm_model_key = settings.local_engine.llm_model
        if llm_model_key in LOCAL_MODELS:
            model_name = LOCAL_MODELS[llm_model_key].ollama_model
            if not _has_model(installed_models, model_name) and manager.ensure_model(model_name, installed_models):
                updated = True
        
        # Ensure embedding model is available
        embed_model_key = settings.local_engine.embedding_model
        if embed_model_key in LOCAL_EMBEDDING_MODELS:
            embed_model_name = LOCAL_EMBEDDING_MODELS[embed_model_key].ollama_model
            if not _has_model(installed_models, embed_model_name) and manager.ensure_model(embed_model_name, installed_models):
                updated = True
        
        # Refresh available models
        if updated:
            status["models_available"] = manager.get_installed_models()
    
    return status
