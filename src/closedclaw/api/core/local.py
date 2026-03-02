"""
Local Engine Configuration for Closedclaw

Provides preconfigured model presets for running LLMs locally via Ollama.
Optimized for various hardware profiles from entry-level laptops to workstations.

All models are selected for:
- Fast inference on consumer hardware
- Low memory footprint (4-bit quantization preferred)
- Good instruction-following capabilities
- Privacy-first local execution
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Literal
import platform
import subprocess
import shutil
import logging
from functools import lru_cache
import time

logger = logging.getLogger(__name__)


class HardwareProfile(str, Enum):
    """Hardware capability profiles for model selection."""
    MINIMAL = "minimal"         # 8GB RAM, integrated GPU, older CPUs
    STANDARD = "standard"       # 16GB RAM, entry-level dedicated GPU
    PERFORMANCE = "performance" # 32GB+ RAM, modern GPU (M1/M2/M3, RTX 3060+)
    WORKSTATION = "workstation" # 64GB+ RAM, high-end GPU


_PROFILE_RANK: Dict[HardwareProfile, int] = {
    HardwareProfile.MINIMAL: 0,
    HardwareProfile.STANDARD: 1,
    HardwareProfile.PERFORMANCE: 2,
    HardwareProfile.WORKSTATION: 3,
}


@dataclass
class LocalModelConfig:
    """Configuration for a local Ollama model."""
    name: str                           # Display name
    ollama_model: str                   # Ollama model identifier (e.g., "llama3.2:3b-instruct-q4_K_M")
    parameters: str                     # Parameter count (e.g., "3B")
    quantization: str                   # Quantization level (e.g., "Q4_K_M")
    context_length: int                 # Max context window
    vram_required_gb: float            # Minimum VRAM/RAM needed
    hardware_profile: HardwareProfile  # Minimum hardware profile
    description: str                   # Human-readable description
    supports_vision: bool = False      # Vision capabilities
    supports_tools: bool = False       # Tool/function calling
    

@dataclass
class LocalEmbeddingConfig:
    """Configuration for a local embedding model."""
    name: str
    ollama_model: str
    embedding_dims: int
    hardware_profile: HardwareProfile
    description: str


# =============================================================================
# RECOMMENDED LOCAL LLM MODELS
# =============================================================================
# Prioritizing 3B parameter models with 4-bit quantization for universal compatibility

LOCAL_MODELS: Dict[str, LocalModelConfig] = {
    # =========================================================================
    # TIER 1: MINIMAL HARDWARE (8GB RAM, any laptop)
    # =========================================================================
    "llama3.2-3b-q4": LocalModelConfig(
        name="Llama 3.2 3B",
        ollama_model="llama3.2:latest",
        parameters="3B",
        quantization="Q4_K_M",
        context_length=8192,
        vram_required_gb=2.5,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Meta's latest 3B model. Best balance of speed and quality for entry-level hardware.",
        supports_tools=True,
    ),
    "phi3-mini-q4": LocalModelConfig(
        name="Phi-3 Mini (Q4)",
        ollama_model="phi3:mini-4k-instruct-q4_K_M",
        parameters="3.8B",
        quantization="Q4_K_M",
        context_length=4096,
        vram_required_gb=2.2,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Microsoft's efficient model. Excellent reasoning despite small size.",
    ),
    "qwen2.5-3b-q4": LocalModelConfig(
        name="Qwen 2.5 3B (Q4)",
        ollama_model="qwen2.5:3b-instruct-q4_K_M",
        parameters="3B",
        quantization="Q4_K_M",
        context_length=32768,
        vram_required_gb=2.3,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Alibaba's model with excellent multilingual support and long context.",
    ),
    "gemma2-2b-q4": LocalModelConfig(
        name="Gemma 2 2B (Q4)",
        ollama_model="gemma2:2b-instruct-q4_K_M",
        parameters="2B",
        quantization="Q4_K_M",
        context_length=8192,
        vram_required_gb=1.8,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Google's ultra-lightweight model. Fastest inference, good for quick tasks.",
    ),
    "tinyllama-1b": LocalModelConfig(
        name="TinyLlama 1.1B",
        ollama_model="tinyllama:1.1b-chat-v1.0-q4_K_M",
        parameters="1.1B",
        quantization="Q4_K_M",
        context_length=2048,
        vram_required_gb=0.8,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Ultra-lightweight for very constrained hardware. Basic chat capabilities.",
    ),
    
    # =========================================================================
    # TIER 2: STANDARD HARDWARE (16GB RAM, MacBook Air M1/M2, entry-level GPU)
    # =========================================================================
    "llama3.2-3b-q8": LocalModelConfig(
        name="Llama 3.2 3B (Q8)",
        ollama_model="llama3.2:3b-instruct-q8_0",
        parameters="3B",
        quantization="Q8_0",
        context_length=8192,
        vram_required_gb=4.0,
        hardware_profile=HardwareProfile.STANDARD,
        description="Higher quality 3B with 8-bit quantization. Recommended for MacBooks.",
        supports_tools=True,
    ),
    "mistral-7b-q4": LocalModelConfig(
        name="Mistral 7B (Q4)",
        ollama_model="mistral:7b-instruct-q4_K_M",
        parameters="7B",
        quantization="Q4_K_M",
        context_length=32768,
        vram_required_gb=4.5,
        hardware_profile=HardwareProfile.STANDARD,
        description="Mistral's instruction-tuned model. Great for complex reasoning.",
        supports_tools=True,
    ),
    "llama3.1-8b-q4": LocalModelConfig(
        name="Llama 3.1 8B (Q4)",
        ollama_model="llama3.1:8b-instruct-q4_K_M",
        parameters="8B",
        quantization="Q4_K_M",
        context_length=131072,
        vram_required_gb=5.0,
        hardware_profile=HardwareProfile.STANDARD,
        description="Meta's flagship 8B model with massive context. Best quality at this tier.",
        supports_tools=True,
    ),
    "qwen2.5-7b-q4": LocalModelConfig(
        name="Qwen 2.5 7B (Q4)",
        ollama_model="qwen2.5:7b-instruct-q4_K_M",
        parameters="7B",
        quantization="Q4_K_M",
        context_length=32768,
        vram_required_gb=4.8,
        hardware_profile=HardwareProfile.STANDARD,
        description="Excellent coding and multilingual capabilities.",
    ),
    "deepseek-r1-7b-q4": LocalModelConfig(
        name="DeepSeek R1 7B (Q4)",
        ollama_model="deepseek-r1:7b-qwen-distill-q4_K_M",
        parameters="7B",
        quantization="Q4_K_M",
        context_length=64000,
        vram_required_gb=4.5,
        hardware_profile=HardwareProfile.STANDARD,
        description="DeepSeek's reasoning-focused model. Strong analytical capabilities.",
    ),
    
    # =========================================================================
    # TIER 3: PERFORMANCE HARDWARE (32GB RAM, M2 Pro/Max, RTX 3060+)
    # =========================================================================
    "llama3.1-8b-q8": LocalModelConfig(
        name="Llama 3.1 8B (Q8)",
        ollama_model="llama3.1:8b-instruct-q8_0",
        parameters="8B",
        quantization="Q8_0",
        context_length=131072,
        vram_required_gb=9.0,
        hardware_profile=HardwareProfile.PERFORMANCE,
        description="High-quality 8B for performance hardware. Near full-precision quality.",
        supports_tools=True,
    ),
    "qwen2.5-14b-q4": LocalModelConfig(
        name="Qwen 2.5 14B (Q4)",
        ollama_model="qwen2.5:14b-instruct-q4_K_M",
        parameters="14B",
        quantization="Q4_K_M",
        context_length=32768,
        vram_required_gb=9.5,
        hardware_profile=HardwareProfile.PERFORMANCE,
        description="Larger Qwen model for complex tasks.",
    ),
    "mistral-nemo-12b-q4": LocalModelConfig(
        name="Mistral Nemo 12B (Q4)",
        ollama_model="mistral-nemo:12b-instruct-q4_K_M",
        parameters="12B",
        quantization="Q4_K_M",
        context_length=128000,
        vram_required_gb=8.0,
        hardware_profile=HardwareProfile.PERFORMANCE,
        description="Mistral's larger model with excellent context handling.",
        supports_tools=True,
    ),
    "llava-7b-q4": LocalModelConfig(
        name="LLaVA 7B (Q4) - Vision",
        ollama_model="llava:7b-v1.6-mistral-q4_K_M",
        parameters="7B",
        quantization="Q4_K_M",
        context_length=4096,
        vram_required_gb=5.5,
        hardware_profile=HardwareProfile.PERFORMANCE,
        description="Vision-language model for image understanding tasks.",
        supports_vision=True,
    ),
    
    # =========================================================================
    # TIER 4: WORKSTATION HARDWARE (64GB+ RAM, M3 Max/Ultra, RTX 4080+)
    # =========================================================================
    "llama3.1-70b-q4": LocalModelConfig(
        name="Llama 3.1 70B (Q4)",
        ollama_model="llama3.1:70b-instruct-q4_K_M",
        parameters="70B",
        quantization="Q4_K_M",
        context_length=131072,
        vram_required_gb=42.0,
        hardware_profile=HardwareProfile.WORKSTATION,
        description="Full-size Llama. Near-frontier quality for local inference.",
        supports_tools=True,
    ),
    "qwen2.5-72b-q4": LocalModelConfig(
        name="Qwen 2.5 72B (Q4)",
        ollama_model="qwen2.5:72b-instruct-q4_K_M",
        parameters="72B",
        quantization="Q4_K_M",
        context_length=32768,
        vram_required_gb=45.0,
        hardware_profile=HardwareProfile.WORKSTATION,
        description="Full-size Qwen. Exceptional multilingual and coding.",
    ),
}


# =============================================================================
# RECOMMENDED LOCAL EMBEDDING MODELS
# =============================================================================

LOCAL_EMBEDDING_MODELS: Dict[str, LocalEmbeddingConfig] = {
    # Default: Balanced choice for most users
    "nomic-embed-text": LocalEmbeddingConfig(
        name="Nomic Embed Text",
        ollama_model="nomic-embed-text",
        embedding_dims=768,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Default embedding model. Good quality, fast inference.",
    ),
    # Alternative: Smaller dimension for memory-constrained setups
    "mxbai-embed-large": LocalEmbeddingConfig(
        name="MXBai Embed Large",
        ollama_model="mxbai-embed-large",
        embedding_dims=1024,
        hardware_profile=HardwareProfile.MINIMAL,
        description="High-quality embeddings with good semantic understanding.",
    ),
    # Multilingual support
    "bge-m3": LocalEmbeddingConfig(
        name="BGE-M3 (Multilingual)",
        ollama_model="bge-m3",
        embedding_dims=1024,
        hardware_profile=HardwareProfile.STANDARD,
        description="Multilingual embeddings for non-English content.",
    ),
    # Ultra-lightweight
    "all-minilm": LocalEmbeddingConfig(
        name="All-MiniLM",
        ollama_model="all-minilm",
        embedding_dims=384,
        hardware_profile=HardwareProfile.MINIMAL,
        description="Ultra-fast, tiny embeddings. Good for very constrained hardware.",
    ),
}


# =============================================================================
# DEFAULT CONFIGURATIONS BY PROFILE
# =============================================================================

DEFAULT_MODEL_BY_PROFILE: Dict[HardwareProfile, str] = {
    HardwareProfile.MINIMAL: "llama3.2-3b-q4",
    HardwareProfile.STANDARD: "llama3.1-8b-q4",
    HardwareProfile.PERFORMANCE: "llama3.1-8b-q8",
    HardwareProfile.WORKSTATION: "llama3.1-70b-q4",
}

DEFAULT_EMBEDDING_BY_PROFILE: Dict[HardwareProfile, str] = {
    HardwareProfile.MINIMAL: "nomic-embed-text",
    HardwareProfile.STANDARD: "nomic-embed-text",
    HardwareProfile.PERFORMANCE: "mxbai-embed-large",
    HardwareProfile.WORKSTATION: "mxbai-embed-large",
}


@dataclass
class LocalEngineConfig:
    """
    Complete configuration for local LLM engine.
    
    This class manages all settings for running LLMs locally via Ollama,
    including model selection, hardware detection, and optimization settings.
    """
    # Hardware profile (affects model recommendations)
    hardware_profile: HardwareProfile = HardwareProfile.STANDARD
    
    # LLM Configuration
    llm_model_key: str = "llama3.2-3b-q4"  # Key into LOCAL_MODELS
    llm_temperature: float = 0.7
    llm_max_tokens: int = 2000
    llm_top_p: float = 0.9
    llm_top_k: int = 40
    
    # Embedding Configuration
    embedding_model_key: str = "nomic-embed-text"  # Key into LOCAL_EMBEDDING_MODELS
    
    # Ollama Server
    ollama_base_url: str = "http://localhost:11434"
    
    # Memory optimization
    num_gpu_layers: Optional[int] = None  # Auto-detect if None
    num_threads: Optional[int] = None     # Auto-detect if None
    batch_size: int = 512
    
    # Context management
    context_window: Optional[int] = None  # Use model default if None
    memory_context_budget: int = 4096     # Max tokens for memory context injection
    
    @property
    def llm_model(self) -> LocalModelConfig:
        """Get the configured LLM model."""
        if self.llm_model_key not in LOCAL_MODELS:
            raise ValueError(f"Unknown model: {self.llm_model_key}")
        return LOCAL_MODELS[self.llm_model_key]
    
    @property
    def embedding_model(self) -> LocalEmbeddingConfig:
        """Get the configured embedding model."""
        if self.embedding_model_key not in LOCAL_EMBEDDING_MODELS:
            raise ValueError(f"Unknown embedding model: {self.embedding_model_key}")
        return LOCAL_EMBEDDING_MODELS[self.embedding_model_key]
    
    @property
    def ollama_model_name(self) -> str:
        """Get the Ollama model identifier for the LLM."""
        return self.llm_model.ollama_model
    
    @property
    def ollama_embedding_model_name(self) -> str:
        """Get the Ollama model identifier for embeddings."""
        return self.embedding_model.ollama_model
    
    @property
    def embedding_dims(self) -> int:
        """Get the embedding dimension for the configured model."""
        return self.embedding_model.embedding_dims
    
    @classmethod
    def for_hardware_profile(cls, profile: HardwareProfile) -> "LocalEngineConfig":
        """Create a configuration optimized for a hardware profile."""
        return cls(
            hardware_profile=profile,
            llm_model_key=DEFAULT_MODEL_BY_PROFILE[profile],
            embedding_model_key=DEFAULT_EMBEDDING_BY_PROFILE[profile],
        )
    
    @classmethod
    def minimal(cls) -> "LocalEngineConfig":
        """Configuration for minimal hardware (8GB RAM laptops)."""
        return cls.for_hardware_profile(HardwareProfile.MINIMAL)
    
    @classmethod
    def standard(cls) -> "LocalEngineConfig":
        """Configuration for standard hardware (16GB RAM, MacBook Air)."""
        return cls.for_hardware_profile(HardwareProfile.STANDARD)
    
    @classmethod
    def performance(cls) -> "LocalEngineConfig":
        """Configuration for performance hardware (32GB RAM, M2 Pro/Max)."""
        return cls.for_hardware_profile(HardwareProfile.PERFORMANCE)
    
    @classmethod
    def workstation(cls) -> "LocalEngineConfig":
        """Configuration for workstation hardware (64GB+ RAM)."""
        return cls.for_hardware_profile(HardwareProfile.WORKSTATION)
    
    def get_models_for_profile(self) -> List[LocalModelConfig]:
        """Get all models compatible with the configured hardware profile."""
        compatible = []
        profile_rank = _PROFILE_RANK[self.hardware_profile]
        for model in LOCAL_MODELS.values():
            if _PROFILE_RANK[model.hardware_profile] <= profile_rank:
                compatible.append(model)
        return sorted(compatible, key=lambda m: m.vram_required_gb)


@lru_cache(maxsize=1)
def _detect_hardware_profile_cached() -> HardwareProfile:
    """Detect and cache hardware profile for process lifetime."""
    # Get total RAM
    total_ram_gb = 8.0

    try:
        if platform.system() == "Darwin":
            result = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                total_ram_gb = int(result.stdout.strip()) / (1024**3)
        elif platform.system() == "Linux":
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        total_ram_gb = int(line.split()[1]) / (1024**2)
                        break
        elif platform.system() == "Windows":
            result = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                total_ram_gb = int(result.stdout.strip()) / (1024**3)
    except Exception as e:
        logger.warning(f"Failed to detect RAM: {e}")

    if total_ram_gb >= 64:
        return HardwareProfile.WORKSTATION
    if total_ram_gb >= 32:
        return HardwareProfile.PERFORMANCE
    if total_ram_gb >= 16:
        return HardwareProfile.STANDARD
    return HardwareProfile.MINIMAL
    
    def to_mem0_llm_config(self) -> dict:
        """Convert to mem0 LLM configuration format."""
        return {
            "provider": "ollama",
            "config": {
                "model": self.ollama_model_name,
                "temperature": self.llm_temperature,
                "max_tokens": self.llm_max_tokens,
                "top_p": self.llm_top_p,
                "top_k": self.llm_top_k,
                "ollama_base_url": self.ollama_base_url,
            }
        }
    
    def to_mem0_embedder_config(self) -> dict:
        """Convert to mem0 embedder configuration format."""
        return {
            "provider": "ollama",
            "config": {
                "model": self.ollama_embedding_model_name,
                "embedding_dims": self.embedding_dims,
                "ollama_base_url": self.ollama_base_url,
            }
        }


# =============================================================================
# OLLAMA STATUS & MANAGEMENT
# =============================================================================

class OllamaManager:
    """
    Utility class for managing Ollama installation and models.
    
    Provides methods for:
    - Checking Ollama availability
    - Listing installed models
    - Pulling required models
    - Detecting hardware capabilities
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self._installed_models_cache: tuple[float, List[str]] = (0.0, [])
    
    def is_installed(self) -> bool:
        """Check if Ollama is installed on the system."""
        return shutil.which("ollama") is not None
    
    def is_running(self) -> bool:
        """Check if Ollama server is running."""
        try:
            import httpx
            response = httpx.get(f"{self.base_url}/api/version", timeout=2.0)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_installed_models(self) -> List[str]:
        """Get list of models installed in Ollama."""
        cache_ts, cache_models = self._installed_models_cache
        now = time.time()
        if cache_models and (now - cache_ts) < 5.0:
            return cache_models

        try:
            import httpx
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                self._installed_models_cache = (now, models)
                return models
        except Exception as e:
            logger.warning(f"Failed to get installed models: {e}")
        return []
    
    def pull_model(self, model: str) -> bool:
        """
        Pull a model from Ollama registry.
        
        Args:
            model: The model identifier (e.g., "llama3.2:3b-instruct-q4_K_M")
            
        Returns:
            True if successful, False otherwise.
        """
        try:
            result = subprocess.run(
                ["ollama", "pull", model],
                capture_output=True,
                text=True,
                timeout=600,  # 10 minutes timeout for large models
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Failed to pull model {model}: {e}")
            return False
    
    def ensure_model(self, model: str, installed_models: Optional[List[str]] = None) -> bool:
        """Ensure a model is installed, pulling if necessary."""
        installed = installed_models if installed_models is not None else self.get_installed_models()
        # Check if model is installed (handle version suffixes)
        model_base = model.split(":")[0]
        for installed_model in installed:
            if installed_model.startswith(model_base):
                return True
        
        logger.info(f"Pulling model: {model}")
        ok = self.pull_model(model)
        if ok:
            self._installed_models_cache = (0.0, [])
        return ok
    
    def detect_hardware_profile(self) -> HardwareProfile:
        """
        Detect the hardware profile based on system capabilities.
        
        Returns:
            HardwareProfile appropriate for the detected hardware.
        """
        return _detect_hardware_profile_cached()
    
    def get_recommended_config(self) -> LocalEngineConfig:
        """Get recommended configuration based on detected hardware."""
        profile = self.detect_hardware_profile()
        logger.info(f"Detected hardware profile: {profile.value}")
        return LocalEngineConfig.for_hardware_profile(profile)


@lru_cache(maxsize=1)
def get_local_engine_config() -> LocalEngineConfig:
    """
    Get the recommended local engine configuration.
    
    Detects hardware and returns an optimized configuration.
    """
    manager = OllamaManager()
    return manager.get_recommended_config()


def list_available_models(
    profile: Optional[HardwareProfile] = None,
    include_higher_tiers: bool = True,
) -> List[LocalModelConfig]:
    """
    List available local models, optionally filtered by hardware profile.
    
    Args:
        profile: Filter to models compatible with this profile
        include_higher_tiers: Include models from lower tiers as well
        
    Returns:
        List of compatible LocalModelConfig objects
    """
    if profile is None:
        return list(LOCAL_MODELS.values())

    compatible = []
    profile_rank = _PROFILE_RANK[profile]
    for model in LOCAL_MODELS.values():
        if include_higher_tiers:
            # Include if model's required profile is at or below our profile
            if _PROFILE_RANK[model.hardware_profile] <= profile_rank:
                compatible.append(model)
        else:
            # Only include exact match
            if model.hardware_profile == profile:
                compatible.append(model)
    
    return sorted(compatible, key=lambda m: m.vram_required_gb)
