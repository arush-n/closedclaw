"""
Tests for SQLite-Vec Vector Store

Comprehensive test suite covering:
- Basic CRUD operations
- Vector search with different metrics
- Closedclaw extensions (sensitivity, TTL, audit)
- Edge cases and error handling
"""

import sys
sys.path.insert(0, r"c:\Users\rush\closedclaw\src\closedclaw")

import pytest
import tempfile
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np

from api.vector_stores.sqlite_vec import SQLiteVecStore, OutputData
from api.vector_stores.config import SQLiteVecConfig


# Test fixtures

@pytest.fixture
def in_memory_store():
    """Create an in-memory store for testing."""
    store = SQLiteVecStore(
        collection_name="test",
        path=None,  # In-memory
        embedding_dim=128,
        distance_metric="cosine"
    )
    yield store
    store.close()


@pytest.fixture
def file_store(tmp_path):
    """Create a file-based store for testing."""
    db_path = tmp_path / "test.db"
    store = SQLiteVecStore(
        collection_name="test",
        path=str(db_path),
        embedding_dim=128,
        distance_metric="cosine"
    )
    yield store
    store.close()


@pytest.fixture
def sample_vectors():
    """Generate sample vectors for testing."""
    np.random.seed(42)
    return [
        np.random.randn(128).tolist() for _ in range(10)
    ]


@pytest.fixture
def sample_payloads():
    """Generate sample payloads for testing."""
    return [
        {"text": f"Memory number {i}", "category": f"cat_{i % 3}"}
        for i in range(10)
    ]


# Basic CRUD Tests

class TestBasicOperations:
    """Test basic CRUD operations."""
    
    def test_insert_single_vector(self, in_memory_store, sample_vectors):
        """Test inserting a single vector."""
        vector = sample_vectors[0]
        payload = {"text": "Test memory"}
        
        ids = in_memory_store.insert(
            vectors=[vector],
            payloads=[payload]
        )
        
        assert len(ids) == 1
        assert isinstance(ids[0], str)
        
        # Verify retrieval
        result = in_memory_store.get(ids[0])
        assert result is not None
        assert result.payload["text"] == "Test memory"
    
    def test_insert_multiple_vectors(self, in_memory_store, sample_vectors, sample_payloads):
        """Test inserting multiple vectors."""
        ids = in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads
        )
        
        assert len(ids) == 10
        
        # Verify all retrievable
        for i, vid in enumerate(ids):
            result = in_memory_store.get(vid)
            assert result is not None
            assert result.payload["text"] == f"Memory number {i}"
    
    def test_insert_with_custom_ids(self, in_memory_store, sample_vectors):
        """Test inserting with custom IDs."""
        custom_ids = [f"custom-{i}" for i in range(3)]
        
        ids = in_memory_store.insert(
            vectors=sample_vectors[:3],
            ids=custom_ids
        )
        
        assert ids == custom_ids
        
        for cid in custom_ids:
            result = in_memory_store.get(cid)
            assert result is not None
    
    def test_delete_vector(self, in_memory_store, sample_vectors):
        """Test deleting a vector."""
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "To be deleted"}]
        )
        
        # Verify exists
        assert in_memory_store.get(ids[0]) is not None
        
        # Delete
        success = in_memory_store.delete(ids[0])
        assert success is True
        
        # Verify deleted
        assert in_memory_store.get(ids[0]) is None
    
    def test_delete_nonexistent(self, in_memory_store):
        """Test deleting a non-existent vector."""
        success = in_memory_store.delete("nonexistent-id")
        assert success is False
    
    def test_update_payload(self, in_memory_store, sample_vectors):
        """Test updating vector payload."""
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Original"}]
        )
        
        success = in_memory_store.update(
            ids[0],
            payload={"text": "Updated", "new_field": "value"}
        )
        
        assert success is True
        
        result = in_memory_store.get(ids[0])
        assert result.payload["text"] == "Updated"
        assert result.payload["new_field"] == "value"
    
    def test_update_nonexistent(self, in_memory_store):
        """Test updating a non-existent vector."""
        success = in_memory_store.update(
            "nonexistent-id",
            payload={"text": "Should fail"}
        )
        assert success is False


# Search Tests

class TestSearch:
    """Test vector search functionality."""
    
    def test_basic_search(self, in_memory_store, sample_vectors, sample_payloads):
        """Test basic similarity search."""
        in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads
        )
        
        # Search using the first vector - should return itself as most similar
        results = in_memory_store.search(
            query="",
            vectors=[sample_vectors[0]],
            limit=5
        )
        
        assert len(results) > 0
        assert len(results) <= 5
        assert all(isinstance(r, OutputData) for r in results)
        assert all(r.score is not None for r in results)
    
    def test_search_returns_sorted_results(self, in_memory_store):
        """Test that search results are sorted by similarity."""
        # Create vectors with known similarities
        base_vector = np.ones(128).tolist()
        similar_vector = (np.ones(128) * 0.9).tolist()
        different_vector = (np.ones(128) * -1).tolist()
        
        in_memory_store.insert(
            vectors=[base_vector, similar_vector, different_vector],
            payloads=[
                {"name": "base"},
                {"name": "similar"},
                {"name": "different"}
            ]
        )
        
        results = in_memory_store.search(
            query="",
            vectors=[base_vector],
            limit=3
        )
        
        # Results should be sorted by score (descending)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)
    
    def test_search_with_limit(self, in_memory_store, sample_vectors, sample_payloads):
        """Test search respects limit parameter."""
        in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads
        )
        
        results = in_memory_store.search(
            query="",
            vectors=[sample_vectors[0]],
            limit=3
        )
        
        assert len(results) == 3
    
    def test_search_with_filters(self, in_memory_store, sample_vectors, sample_payloads):
        """Test search with metadata filters."""
        in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads
        )
        
        results = in_memory_store.search(
            query="",
            vectors=[sample_vectors[0]],
            limit=10,
            filters={"category": "cat_0"}
        )
        
        # All results should have category "cat_0"
        assert all(r.payload.get("category") == "cat_0" for r in results)
    
    def test_search_empty_store(self, in_memory_store, sample_vectors):
        """Test search on empty store."""
        results = in_memory_store.search(
            query="",
            vectors=[sample_vectors[0]],
            limit=5
        )
        
        assert results == []


# Closedclaw Extension Tests

class TestClosedclawExtensions:
    """Test closedclaw-specific features."""
    
    def test_sensitivity_levels(self, in_memory_store, sample_vectors):
        """Test sensitivity level assignment and filtering."""
        in_memory_store.insert(
            vectors=sample_vectors[:4],
            payloads=[{"text": f"Level {i}"} for i in range(4)],
            sensitivities=[0, 1, 2, 3]
        )
        
        # Search with max sensitivity
        results = in_memory_store.search(
            query="",
            vectors=[sample_vectors[0]],
            limit=10,
            sensitivity_max=1
        )
        
        # Should only return level 0 and 1
        assert all(r.sensitivity <= 1 for r in results)
    
    def test_ttl_expiry(self, in_memory_store, sample_vectors):
        """Test TTL-based expiry."""
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=1)
        future = now + timedelta(hours=1)
        
        in_memory_store.insert(
            vectors=sample_vectors[:3],
            payloads=[
                {"text": "No expiry"},
                {"text": "Expired"},
                {"text": "Future"}
            ],
            expires_at_list=[None, past, future]
        )
        
        # List should exclude expired by default
        results = in_memory_store.list(include_expired=False)
        assert len(results) == 2
        assert all(r.payload["text"] != "Expired" for r in results)
        
        # Include expired
        results = in_memory_store.list(include_expired=True)
        # Note: expired entries may have been cleaned up already
    
    def test_audit_trail(self, in_memory_store, sample_vectors):
        """Test audit trail logging."""
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Audited memory"}]
        )
        
        # Access the memory
        in_memory_store.get(ids[0])
        in_memory_store.get(ids[0])
        
        # Check audit trail
        audit = in_memory_store.get_audit_trail(ids[0])
        
        # Should have insert + 2 access events
        assert len(audit) >= 3
        event_types = [a["event_type"] for a in audit]
        assert "insert" in event_types
        assert "access" in event_types
    
    def test_tags(self, in_memory_store, sample_vectors):
        """Test tag assignment."""
        in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Tagged memory"}],
            tags_list=[["health", "personal"]]
        )
        
        # Update tags
        result = in_memory_store.list()[0]
        memory_id = result.id
        
        in_memory_store.update(
            memory_id,
            tags=["health", "personal", "important"]
        )
        
        # Verify update
        updated = in_memory_store.get(memory_id)
        assert updated is not None
    
    def test_consent_required_flag(self, in_memory_store, sample_vectors):
        """Test consent required flag."""
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Sensitive memory"}],
            sensitivities=[3],
            consent_required_list=[True]
        )
        
        # Mark consent required
        success = in_memory_store.mark_consent_required(ids[0], True)
        assert success is True
    
    def test_extend_ttl(self, in_memory_store, sample_vectors):
        """Test TTL extension."""
        now = datetime.now(timezone.utc)
        original_expiry = now + timedelta(hours=1)
        new_expiry = now + timedelta(days=7)
        
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Expiring memory"}],
            expires_at_list=[original_expiry]
        )
        
        success = in_memory_store.extend_ttl(ids[0], new_expiry)
        assert success is True
        
        result = in_memory_store.get(ids[0])
        assert result.expires_at == new_expiry.isoformat()
    
    def test_get_expiring_soon(self, in_memory_store, sample_vectors):
        """Test getting entries expiring soon."""
        now = datetime.now(timezone.utc)
        
        in_memory_store.insert(
            vectors=sample_vectors[:3],
            payloads=[
                {"text": "Expiring in 2 hours"},
                {"text": "Expiring in 48 hours"},
                {"text": "No expiry"}
            ],
            expires_at_list=[
                now + timedelta(hours=2),
                now + timedelta(hours=48),
                None
            ]
        )
        
        # Get entries expiring in next 24 hours
        results = in_memory_store.get_expiring_soon(within_hours=24)
        
        assert len(results) == 1
        assert results[0].payload["text"] == "Expiring in 2 hours"


# Collection Management Tests

class TestCollectionManagement:
    """Test collection management operations."""
    
    def test_create_collection(self, in_memory_store):
        """Test creating a new collection."""
        store = in_memory_store.create_col("new_collection", vector_size=256)
        
        assert store.collection_name == "new_collection"
        assert store.embedding_dim == 256
    
    def test_list_collections(self, file_store, sample_vectors):
        """Test listing collections."""
        # Create multiple collections
        file_store.insert(vectors=[sample_vectors[0]], payloads=[{"text": "test"}])
        
        file_store.create_col("collection2")
        file_store.insert(vectors=[sample_vectors[0]], payloads=[{"text": "test2"}])
        
        collections = file_store.list_cols()
        assert len(collections) >= 2
    
    def test_collection_info(self, in_memory_store, sample_vectors, sample_payloads):
        """Test getting collection info."""
        in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads,
            sensitivities=[i % 4 for i in range(10)]
        )
        
        info = in_memory_store.col_info()
        
        assert info["name"] == "test"
        assert info["count"] == 10
        assert info["dimension"] == 128
        assert "sensitivity_distribution" in info
    
    def test_delete_collection(self, in_memory_store, sample_vectors):
        """Test deleting a collection."""
        in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "test"}]
        )
        
        success = in_memory_store.delete_col()
        assert success is True
        
        # Collection tables should be gone
        # Reinitialize to use again
        in_memory_store._init_database()
    
    def test_reset_collection(self, in_memory_store, sample_vectors):
        """Test resetting a collection."""
        in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "test"}]
        )
        
        in_memory_store.reset()
        
        # Should be empty
        results = in_memory_store.list()
        assert len(results) == 0


# Edge Cases and Error Handling

class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_dimension_mismatch_insert(self, in_memory_store):
        """Test error on dimension mismatch during insert."""
        wrong_dim_vector = [0.1] * 64  # Should be 128
        
        with pytest.raises(ValueError, match="dimension"):
            in_memory_store.insert(vectors=[wrong_dim_vector])
    
    def test_dimension_mismatch_search(self, in_memory_store, sample_vectors):
        """Test error on dimension mismatch during search."""
        in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "test"}]
        )
        
        wrong_dim_query = [0.1] * 64
        
        with pytest.raises(ValueError, match="dimension"):
            in_memory_store.search(query="", vectors=[wrong_dim_query])
    
    def test_empty_insert(self, in_memory_store):
        """Test inserting empty list."""
        ids = in_memory_store.insert(vectors=[])
        assert ids == []
    
    def test_empty_search(self, in_memory_store):
        """Test searching with empty vectors."""
        results = in_memory_store.search(query="", vectors=[])
        assert results == []
    
    def test_special_characters_in_payload(self, in_memory_store, sample_vectors):
        """Test handling special characters in payload."""
        special_payload = {
            "text": "Test with 'quotes' and \"double quotes\"",
            "unicode": "測試中文",
            "emoji": "🔒🧠",
            "newlines": "Line1\nLine2\rLine3"
        }
        
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[special_payload]
        )
        
        result = in_memory_store.get(ids[0])
        assert result.payload == special_payload
    
    def test_very_large_payload(self, in_memory_store, sample_vectors):
        """Test handling large payloads."""
        large_payload = {
            "text": "x" * 100000,  # 100KB text
            "array": list(range(1000))
        }
        
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[large_payload]
        )
        
        result = in_memory_store.get(ids[0])
        assert len(result.payload["text"]) == 100000


# Persistence Tests

class TestPersistence:
    """Test data persistence across sessions."""
    
    def test_file_persistence(self, tmp_path, sample_vectors, sample_payloads):
        """Test data persists to file."""
        db_path = tmp_path / "persist_test.db"
        
        # Create and populate store
        store1 = SQLiteVecStore(
            collection_name="persist",
            path=str(db_path),
            embedding_dim=128
        )
        
        ids = store1.insert(
            vectors=sample_vectors[:5],
            payloads=sample_payloads[:5]
        )
        store1.close()
        
        # Verify file exists
        assert db_path.exists()
        
        # Reopen and verify data
        store2 = SQLiteVecStore(
            collection_name="persist",
            path=str(db_path),
            embedding_dim=128
        )
        
        for i, vid in enumerate(ids):
            result = store2.get(vid)
            assert result is not None
            assert result.payload["text"] == f"Memory number {i}"
        
        store2.close()


# Statistics Tests

class TestStatistics:
    """Test statistics and monitoring."""
    
    def test_get_stats(self, in_memory_store, sample_vectors, sample_payloads):
        """Test getting detailed statistics."""
        in_memory_store.insert(
            vectors=sample_vectors,
            payloads=sample_payloads,
            sensitivities=[i % 4 for i in range(10)],
            sources=["manual", "conversation", "manual", "imported", "manual",
                    "conversation", "manual", "insight", "conversation", "manual"]
        )
        
        stats = in_memory_store.get_stats()
        
        assert stats["count"] == 10
        assert "sensitivity_distribution" in stats
        assert "source_distribution" in stats
        assert stats["source_distribution"]["manual"] >= 1
    
    def test_access_count_tracking(self, in_memory_store, sample_vectors):
        """Test access count is tracked."""
        ids = in_memory_store.insert(
            vectors=[sample_vectors[0]],
            payloads=[{"text": "Tracked"}]
        )
        
        # Access multiple times
        for _ in range(5):
            in_memory_store.get(ids[0])
        
        stats = in_memory_store.get_stats()
        
        # Check most_accessed
        if stats["most_accessed"]:
            most_accessed = stats["most_accessed"][0]
            assert most_accessed["id"] == ids[0]
            assert most_accessed["count"] >= 5


# Config Tests

class TestConfig:
    """Test configuration handling."""
    
    def test_config_validation(self):
        """Test config validation."""
        # Valid config
        config = SQLiteVecConfig(
            collection_name="test",
            distance_metric="cosine",
            embedding_dim=768
        )
        assert config.distance_metric == "cosine"
        
        # Invalid distance metric
        with pytest.raises(ValueError):
            SQLiteVecConfig(distance_metric="invalid")
        
        # Invalid embedding dim
        with pytest.raises(ValueError):
            SQLiteVecConfig(embedding_dim=-1)
    
    def test_config_from_params(self):
        """Test store initialization with various config options."""
        store = SQLiteVecStore(
            collection_name="custom",
            path=None,
            distance_metric="l2",
            embedding_dim=512,
            enable_encryption=True,
            enable_audit=False
        )
        
        assert store.config.distance_metric == "l2"
        assert store.config.embedding_dim == 512
        assert store.config.enable_encryption is True
        assert store.config.enable_audit is False
        
        store.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
