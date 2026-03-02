"""
Mem0 Compatibility Adapter

Provides a mem0-compatible interface for the SQLiteVecStore, allowing it
to be used as a drop-in replacement for any mem0 vector store.

Usage:
    from closedclaw.api.vector_stores.mem0_adapter import Mem0SQLiteVecStore
    
    # Use in mem0 config
    config = {
        "vector_store": {
            "provider": "sqlite_vec",
            "config": {
                "collection_name": "memories",
                "path": "~/.closedclaw/memory.db"
            }
        }
    }
"""

from typing import Any, Dict, List, Literal, Optional

from .sqlite_vec import SQLiteVecStore, OutputData
from .config import SQLiteVecConfig


class Mem0SQLiteVecStore:
    """
    Mem0-compatible adapter for SQLiteVecStore.
    
    Implements the exact interface expected by mem0's VectorStoreBase,
    wrapping our SQLiteVecStore implementation.
    """
    
    def __init__(
        self,
        collection_name: str = "mem0",
        path: Optional[str] = None,
        distance_strategy: str = "cosine",
        embedding_model_dims: int = 768,
        **kwargs
    ):
        """
        Initialize the mem0-compatible store.
        
        Args:
            collection_name: Name of the collection
            path: Path to database file
            distance_strategy: Distance metric ('cosine', 'euclidean'/'l2', 'inner_product')
            embedding_model_dims: Embedding vector dimension
            **kwargs: Additional SQLiteVecConfig options
        """
        # Map mem0 distance_strategy names to sqlite_vec names
        distance_map = {
            "euclidean": "l2",
            "cosine": "cosine",
            "inner_product": "inner_product"
        }
        distance_metric: Literal["cosine", "l2", "inner_product"] = distance_map.get(distance_strategy, distance_strategy)  # type: ignore[assignment]
        
        self._store = SQLiteVecStore(
            collection_name=collection_name,
            path=path,
            distance_metric=distance_metric,
            embedding_dim=embedding_model_dims,
            **kwargs
        )
        
        self.collection_name = collection_name
        self.path = path
        self.distance_strategy = distance_strategy
        self.embedding_model_dims = embedding_model_dims
    
    def create_col(self, name: str, vector_size: Optional[int] = None, distance: Optional[str] = None):
        """Create a new collection."""
        # Map distance name if provided
        if distance:
            distance_map = {
                "euclidean": "l2",
                "cosine": "cosine",
                "inner_product": "inner_product"
            }
            distance = distance_map.get(distance, distance)
        
        return self._store.create_col(name, vector_size, distance)
    
    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None
    ):
        """
        Insert vectors into the collection.
        
        Note: This is the mem0-compatible interface. For closedclaw extensions
        like sensitivity and TTL, use the underlying _store.insert() directly.
        """
        return self._store.insert(vectors=vectors, payloads=payloads, ids=ids)
    
    def search(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[OutputData]:
        """Search for similar vectors."""
        return self._store.search(
            query=query,
            vectors=vectors,
            limit=limit,
            filters=filters
        )
    
    def delete(self, vector_id: str):
        """Delete a vector by ID."""
        return self._store.delete(vector_id)
    
    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict[str, Any]] = None
    ):
        """Update a vector and its payload."""
        return self._store.update(vector_id, vector=vector, payload=payload)
    
    def get(self, vector_id: str) -> Optional[OutputData]:
        """Retrieve a vector by ID."""
        return self._store.get(vector_id)
    
    def list_cols(self) -> List[str]:
        """List all collections."""
        return self._store.list_cols()
    
    def delete_col(self):
        """Delete the collection."""
        return self._store.delete_col()
    
    def col_info(self) -> Dict[str, Any]:
        """Get information about the collection."""
        return self._store.col_info()
    
    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100
    ) -> List[OutputData]:
        """List all vectors in the collection."""
        return self._store.list(filters=filters, limit=limit)
    
    def reset(self):
        """Reset the collection."""
        return self._store.reset()
    
    # Closedclaw extension methods (accessible through adapter)
    
    def insert_with_sensitivity(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        sensitivities: Optional[List[int]] = None,
        tags_list: Optional[List[List[str]]] = None,
        **kwargs
    ) -> List[str]:
        """
        Insert vectors with closedclaw extensions.
        
        Args:
            vectors: Embedding vectors
            payloads: Metadata payloads
            ids: Custom IDs  
            sensitivities: Sensitivity levels (0-3)
            tags_list: Tags for each entry
            **kwargs: Additional closedclaw options
        """
        return self._store.insert(
            vectors=vectors,
            payloads=payloads,
            ids=ids,
            sensitivities=sensitivities,
            tags_list=tags_list,
            **kwargs
        )
    
    def search_with_sensitivity(
        self,
        query: str,
        vectors: List[List[float]],
        limit: int = 5,
        filters: Optional[Dict[str, Any]] = None,
        sensitivity_max: Optional[int] = None
    ) -> List[OutputData]:
        """
        Search with sensitivity filtering.
        
        Args:
            query: Query string
            vectors: Query vectors
            limit: Maximum results
            filters: Metadata filters
            sensitivity_max: Maximum sensitivity level to include
        """
        return self._store.search(
            query=query,
            vectors=vectors,
            limit=limit,
            filters=filters,
            sensitivity_max=sensitivity_max
        )
    
    def get_audit_trail(self, memory_id: str, limit: int = 100):
        """Get audit trail for a memory."""
        return self._store.get_audit_trail(memory_id, limit)
    
    def get_expiring_soon(self, within_hours: int = 24):
        """Get entries expiring soon."""
        return self._store.get_expiring_soon(within_hours)
    
    def extend_ttl(self, vector_id: str, new_expires_at):
        """Extend TTL of an entry."""
        return self._store.extend_ttl(vector_id, new_expires_at)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get store statistics."""
        return self._store.get_stats()
    
    @property
    def native_store(self) -> SQLiteVecStore:
        """Access the underlying SQLiteVecStore for full features."""
        return self._store
    
    def close(self):
        """Close the store."""
        self._store.close()


# Factory function for mem0 integration
def create_sqlite_vec_store(config: Dict[str, Any]) -> Mem0SQLiteVecStore:
    """
    Factory function to create a SQLiteVecStore from mem0 config.
    
    Args:
        config: Configuration dict with keys:
            - collection_name: Collection name
            - path: Database path
            - distance_strategy: Distance metric
            - embedding_model_dims: Vector dimension
    
    Returns:
        Configured Mem0SQLiteVecStore instance
    """
    return Mem0SQLiteVecStore(**config)
