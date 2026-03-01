"""
SQLite-Vec Configuration

Configuration for the SQLite + sqlite-vec vector store implementation.
"""

from typing import Any, Dict, Optional, Literal
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SQLiteVecConfig(BaseModel):
    """
    Configuration for SQLite-Vec vector store.
    
    Attributes:
        collection_name: Name of the collection (maps to table prefix)
        path: Path to SQLite database file
        distance_metric: Vector distance metric ('cosine', 'l2', 'inner_product')
        embedding_dim: Dimension of embedding vectors
        enable_encryption: Whether to encrypt memory content at rest
        enable_audit: Whether to log access events for audit trail
        ttl_check_interval: Seconds between TTL expiry checks (0 = disabled)
    """
    collection_name: str = Field(
        default="mem0", 
        description="Name of the collection (table prefix)"
    )
    path: Optional[str] = Field(
        default=None, 
        description="Path to SQLite database file. None = in-memory."
    )
    distance_metric: Literal["cosine", "l2", "inner_product"] = Field(
        default="cosine",
        description="Vector distance metric for similarity search"
    )
    embedding_dim: int = Field(
        default=768, 
        description="Dimension of embedding vectors"
    )
    
    # Closedclaw extensions
    enable_encryption: bool = Field(
        default=True,
        description="Encrypt memory content at rest using AES-256-GCM"
    )
    enable_audit: bool = Field(
        default=True,
        description="Log all access events for audit trail"
    )
    ttl_check_interval: int = Field(
        default=3600,
        description="Seconds between TTL expiry checks (0 = disabled)"
    )
    max_results_default: int = Field(
        default=10,
        description="Default max results for search queries"
    )
    
    # Performance tuning
    cache_vectors: bool = Field(
        default=True,
        description="Keep frequently accessed vectors in memory"
    )
    cache_size_mb: int = Field(
        default=100,
        description="Maximum cache size in megabytes"
    )
    batch_size: int = Field(
        default=100,
        description="Batch size for bulk operations"
    )
    
    @model_validator(mode="before")
    @classmethod
    def validate_distance_metric(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        metric = values.get("distance_metric")
        if metric and metric not in ["cosine", "l2", "inner_product"]:
            raise ValueError(
                f"Invalid distance_metric '{metric}'. "
                "Must be one of: 'cosine', 'l2', 'inner_product'"
            )
        return values
    
    @model_validator(mode="before")
    @classmethod
    def validate_embedding_dim(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        dim = values.get("embedding_dim")
        if dim and (dim < 1 or dim > 65536):
            raise ValueError(
                f"Invalid embedding_dim {dim}. Must be between 1 and 65536."
            )
        return values
    
    @model_validator(mode="before")
    @classmethod
    def validate_extra_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        allowed_fields = set(cls.model_fields.keys())
        input_fields = set(values.keys())
        extra_fields = input_fields - allowed_fields
        if extra_fields:
            raise ValueError(
                f"Extra fields not allowed: {', '.join(extra_fields)}. "
                f"Please input only the following fields: {', '.join(allowed_fields)}"
            )
        return values
    
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    def get_db_path(self) -> Optional[Path]:
        """Get resolved database path."""
        if self.path is None:
            return None
        return Path(self.path).expanduser().resolve()
    
    def get_table_prefix(self) -> str:
        """Get sanitized table prefix from collection name."""
        # Sanitize collection name for use as SQL table prefix
        safe_name = "".join(c if c.isalnum() or c == "_" else "_" for c in self.collection_name)
        return safe_name[:64]  # Limit length
