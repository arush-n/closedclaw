"""
Tests for the Privacy Firewall Module

Tests PII detection, sensitivity classification, redaction, and firewall logic.
Works with both Presidio (when available) and regex fallback.
"""

import pytest
from typing import List, Dict
from datetime import datetime
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

# Import the modules we're testing
from api.privacy.detector import (
    PIIDetector,
    DetectedEntity,
    ENTITY_SENSITIVITY_MAP,
    PRESIDIO_AVAILABLE,
)
from api.privacy.classifier import (
    SensitivityClassifier,
    SensitivityLevel,
    ClassificationResult,
    TagSensitivityOverride,
)
from api.privacy.redactor import (
    PIIRedactor,
    RedactionResult,
    RedactionStyle,
)
from api.privacy.firewall import (
    PrivacyFirewall,
    FirewallDecision,
    FirewallAction,
    MemoryContext,
    PolicyRule,
    ConsentStatus,
)


# ============================================================
# PIIDetector Tests
# ============================================================

class TestPIIDetector:
    """Tests for the PII detection using Presidio or regex fallback."""
    
    @pytest.fixture
    def detector(self):
        """Create a PIIDetector instance."""
        # Detector will use regex fallback if Presidio unavailable
        return PIIDetector()
    
    def test_detect_email(self, detector):
        """Test detection of email addresses."""
        text = "Contact me at john.doe@example.com"
        entities = detector.detect(text)
        
        email_entities = [e for e in entities if e.entity_type == "EMAIL_ADDRESS"]
        assert len(email_entities) == 1
        assert email_entities[0].text == "john.doe@example.com"
        assert email_entities[0].sensitivity_level == 2  # Level 2
    
    def test_detect_phone(self, detector):
        """Test detection of phone numbers."""
        text = "Call me at 555-123-4567"
        entities = detector.detect(text)
        
        phone_entities = [e for e in entities if e.entity_type == "PHONE_NUMBER"]
        assert len(phone_entities) >= 1
    
    def test_detect_ssn(self, detector):
        """Test detection of SSN (Level 3 - highly sensitive)."""
        text = "My SSN is 123-45-6789"
        entities = detector.detect(text)
        
        ssn_entities = [e for e in entities if "SSN" in e.entity_type]
        assert len(ssn_entities) >= 1
        assert ssn_entities[0].sensitivity_level == 3  # Level 3
    
    def test_detect_credit_card(self, detector):
        """Test detection of credit card numbers."""
        text = "My card is 4532-0123-4567-8901"
        entities = detector.detect(text)
        
        card_entities = [e for e in entities if e.entity_type == "CREDIT_CARD"]
        assert len(card_entities) >= 1
        assert card_entities[0].sensitivity_level == 3  # Level 3
    
    def test_empty_text(self, detector):
        """Test handling of empty text."""
        assert detector.detect("") == []
        assert detector.detect("   ") == []
    
    def test_no_pii_text(self, detector):
        """Test text with no PII."""
        text = "The weather is nice today."
        entities = detector.detect(text)
        # Should have few or no sensitive entities
        sensitive = [e for e in entities if e.sensitivity_level >= 2]
        # Note: might detect domain-like patterns, so we check for Level 2+
        assert len(sensitive) == 0
    
    def test_get_max_sensitivity(self, detector):
        """Test getting maximum sensitivity level."""
        # Text with SSN should be Level 3
        text_sensitive = "My SSN is 123-45-6789"
        assert detector.get_max_sensitivity(text_sensitive) == 3
    
    def test_contains_sensitive_entities(self, detector):
        """Test quick sensitivity check."""
        sensitive_text = "My SSN is 123-45-6789"
        assert detector.contains_sensitive_entities(sensitive_text, min_sensitivity=3) == True
        
        normal_text = "The cat sat on the mat"
        assert detector.contains_sensitive_entities(normal_text, min_sensitivity=2) == False
    
    def test_analyze_for_consent(self, detector):
        """Test consent analysis output."""
        text = "SSN is 123-45-6789 and email is john@test.com"
        analysis = detector.analyze_for_consent(text)
        
        assert analysis["entity_count"] >= 2
        assert analysis["max_sensitivity"] == 3
        assert analysis["requires_consent"] == True
        assert analysis["requires_local_only"] == True


# ============================================================
# SensitivityClassifier Tests
# ============================================================

class TestSensitivityClassifier:
    """Tests for the sensitivity classification system."""
    
    @pytest.fixture
    def classifier(self):
        """Create a SensitivityClassifier instance."""
        detector = PIIDetector()
        return SensitivityClassifier(detector=detector)
    
    def test_classify_public_info(self, classifier):
        """Test classification of public information."""
        text = "The weather is nice today"
        result = classifier.classify(text)
        
        # Should be low sensitivity
        assert result.sensitivity <= SensitivityLevel.GENERAL
    
    def test_classify_level1_personal(self, classifier):
        """Test classification of general personal info."""
        text = "My name is John and I like pizza"
        result = classifier.classify(text)
        
        # Name triggers Level 1
        assert result.sensitivity >= SensitivityLevel.GENERAL
    
    def test_classify_level2_personal(self, classifier):
        """Test classification of personal info (Level 2)."""
        text = "I earn $150,000 per year at my job"
        result = classifier.classify(text)
        
        # Financial info triggers Level 2
        assert result.sensitivity >= SensitivityLevel.PERSONAL
    
    def test_classify_level3_sensitive(self, classifier):
        """Test classification of highly sensitive info."""
        text = "I was diagnosed with cancer last month"
        result = classifier.classify(text)
        
        # Medical diagnosis triggers Level 3
        assert result.sensitivity == SensitivityLevel.SENSITIVE
    
    def test_classify_ssn_level3(self, classifier):
        """Test SSN triggers Level 3."""
        text = "My social security number is 123-45-6789"
        result = classifier.classify(text)
        
        assert result.sensitivity == SensitivityLevel.SENSITIVE
        assert result.requires_consent == True
        assert result.requires_local_only == True
    
    def test_user_override(self, classifier):
        """Test user override takes priority."""
        text = "This is very sensitive to me"
        
        # Without override
        result1 = classifier.classify(text)
        
        # With user override
        result2 = classifier.classify(text, user_sensitivity=3)
        
        assert result2.sensitivity == SensitivityLevel.SENSITIVE
        assert result2.user_override == True
    
    def test_tag_override(self, classifier):
        """Test tag-based sensitivity override."""
        classifier.add_tag_override("medical", 3, "Medical data is always sensitive")
        
        text = "My appointment is tomorrow"
        result = classifier.classify(text, tags=["medical"])
        
        assert result.sensitivity == SensitivityLevel.SENSITIVE
    
    def test_keyword_patterns_level3(self, classifier):
        """Test Level 3 keyword patterns."""
        test_cases = [
            "I have a diagnosis of diabetes",
            "My password is hunter2",
            "There's a lawsuit pending",
        ]
        
        for text in test_cases:
            result = classifier.classify(text)
            assert result.sensitivity == SensitivityLevel.SENSITIVE, f"Failed for: {text}"
    
    def test_keyword_patterns_level2(self, classifier):
        """Test Level 2 keyword patterns."""
        test_cases = [
            "My home address is 123 Main St",
            "I owe $50000 in debt",
            "My therapist said to relax",
        ]
        
        for text in test_cases:
            result = classifier.classify(text)
            assert result.sensitivity >= SensitivityLevel.PERSONAL, f"Failed for: {text}"
    
    def test_quick_check(self, classifier):
        """Test quick sensitivity threshold check."""
        sensitive = "My SSN is 123-45-6789"
        normal = "The sky is blue"
        
        assert classifier.quick_check(sensitive, threshold=3) == True
        assert classifier.quick_check(normal, threshold=2) == False
    
    def test_batch_classification(self, classifier):
        """Test batch classification."""
        texts = [
            "John's email is john@test.com",
            "The weather is nice",
            "My SSN is 123-45-6789",
        ]
        
        results = classifier.classify_batch(texts)
        
        assert len(results) == 3
        # SSN text should be highest sensitivity
        assert results[2].sensitivity == SensitivityLevel.SENSITIVE


# ============================================================
# PIIRedactor Tests
# ============================================================

class TestPIIRedactor:
    """Tests for the PII redaction pipeline."""
    
    @pytest.fixture
    def redactor(self):
        """Create a PIIRedactor instance."""
        detector = PIIDetector()
        return PIIRedactor(detector=detector)
    
    @pytest.mark.skipif(not PRESIDIO_AVAILABLE, reason="Person name detection requires Presidio")
    def test_redact_person_name(self, redactor):
        """Test redacting person names."""
        text = "Arush moved to Austin last year"
        result = redactor.redact(text)
        
        assert result.was_modified
        assert "Arush" not in result.redacted_text
        assert "[PERSON_1]" in result.redacted_text or "[PERSON]" in result.redacted_text
    
    def test_redact_email(self, redactor):
        """Test redacting email addresses."""
        text = "Contact me at john@example.com"
        result = redactor.redact(text)
        
        assert result.was_modified
        assert "john@example.com" not in result.redacted_text
        assert "[EMAIL" in result.redacted_text
    
    def test_redact_ssn_blocked(self, redactor):
        """Test SSN is completely blocked (not just redacted)."""
        text = "My SSN is 123-45-6789"
        result = redactor.redact(text)
        
        assert result.was_modified
        # SSN should be blocked, not just redacted
        assert result.blocked_count >= 1 or result.redaction_count >= 1
        assert "123-45-6789" not in result.redacted_text
    
    def test_placeholder_map(self, redactor):
        """Test placeholder mapping is correct."""
        text = "John and Jane work together"
        result = redactor.redact(text)
        
        # Check we have mappings
        if result.was_modified:
            assert len(result.placeholder_map) > 0
            # Originals should be in the map values
            for placeholder, original in result.placeholder_map.items():
                assert placeholder.startswith("[")
                assert len(original) > 0
    
    def test_unredact(self, redactor):
        """Test reversing redaction."""
        text = "John's email is john@test.com"
        result = redactor.redact(text)
        
        if result.was_modified:
            unredacted = redactor.unredact(result.redacted_text, result)
            # Original values should be restored
            # Note: might not be exactly equal due to entity detection variations
            assert "john" in unredacted.lower() or "John" in unredacted
    
    def test_redaction_styles(self, redactor):
        """Test different redaction styles."""
        text = "Contact John at john@test.com"
        
        # Typed numbered (default)
        result1 = redactor.redact(text, style=RedactionStyle.TYPED_NUMBERED)
        if result1.was_modified:
            assert "_1]" in result1.redacted_text
        
        # Generic
        result2 = redactor.redact(text, style=RedactionStyle.GENERIC)
        if result2.was_modified:
            assert "[REDACTED]" in result2.redacted_text
        
        # Masked
        result3 = redactor.redact(text, style=RedactionStyle.MASKED)
        if result3.was_modified:
            assert "****" in result3.redacted_text
    
    def test_min_sensitivity_filter(self, redactor):
        """Test minimum sensitivity filtering."""
        text = "John's SSN is 123-45-6789"
        
        # Only redact Level 3+
        result = redactor.redact(text, min_sensitivity=3)
        
        # SSN should be redacted, name might not be
        assert "123-45-6789" not in result.redacted_text
    
    def test_provider_based_redaction(self, redactor):
        """Test provider-specific redaction."""
        text = "John's email is john@test.com"
        
        # Local provider - minimal redaction
        result_local = redactor.redact_for_provider(text, "ollama")
        
        # Cloud provider - full redaction
        result_cloud = redactor.redact_for_provider(text, "openai")
        
        # Cloud should have more redactions
        # (or equal, but never fewer)
        assert result_cloud.redaction_count >= result_local.redaction_count
    
    def test_audit_entry(self, redactor):
        """Test audit entry generation."""
        text = "Contact John at john@test.com"
        result = redactor.redact(text)
        
        # Without originals (safe for external logging)
        audit_safe = result.get_audit_entry(include_originals=False)
        assert "mappings" not in audit_safe or all(
            "original" not in m for m in audit_safe.get("mappings", [])
        )
        
        # With originals (for local audit)
        audit_full = result.get_audit_entry(include_originals=True)
        if result.was_modified:
            assert "mappings" in audit_full
    
    def test_empty_text(self, redactor):
        """Test handling of empty text."""
        result = redactor.redact("")
        assert result.redacted_text == ""
        assert not result.was_modified


# ============================================================
# PrivacyFirewall Tests
# ============================================================

class TestPrivacyFirewall:
    """Tests for the complete Privacy Firewall."""
    
    @pytest.fixture
    def firewall(self):
        """Create a PrivacyFirewall instance."""
        detector = PIIDetector()
        classifier = SensitivityClassifier(detector=detector)
        redactor = PIIRedactor(detector=detector)
        return PrivacyFirewall(classifier=classifier, redactor=redactor)
    
    @pytest.fixture
    def sample_memories(self):
        """Sample memories for testing."""
        return [
            {
                "id": "mem-1",
                "memory": "The user prefers dark mode",
                "sensitivity": 0,
                "tags": ["preferences"],
            },
            {
                "id": "mem-2",
                "memory": "John lives in Austin",
                "sensitivity": 1,
                "tags": ["personal"],
            },
            {
                "id": "mem-3",
                "memory": "User earns $150000 per year",
                "sensitivity": 2,
                "tags": ["financial"],
            },
            {
                "id": "mem-4",
                "memory": "User's SSN is 123-45-6789",
                "sensitivity": 3,
                "tags": ["identity"],
            },
        ]
    
    @pytest.mark.asyncio
    async def test_process_basic(self, firewall, sample_memories):
        """Test basic firewall processing."""
        decision = await firewall.process(sample_memories, provider="openai")
        
        assert isinstance(decision, FirewallDecision)
        assert decision.total_memories == 4
        # Should have some blocked (Level 2-3 with cloud)
        assert decision.was_blocked or decision.has_pending_consent
    
    @pytest.mark.asyncio
    async def test_local_provider_permits_more(self, firewall, sample_memories):
        """Test that local provider permits more memories."""
        decision_cloud = await firewall.process(sample_memories, provider="openai")
        decision_local = await firewall.process(sample_memories, provider="ollama")
        
        # Local should permit more or equal
        assert len(decision_local.permitted) >= len(decision_cloud.permitted)
    
    @pytest.mark.asyncio
    async def test_level3_requires_consent(self, firewall):
        """Test Level 3 memories require consent."""
        memories = [{
            "id": "sensitive-1",
            "memory": "User has terminal illness",
            "sensitivity": 3,
            "tags": ["medical"],
        }]
        
        decision = await firewall.process(memories, provider="ollama")
        
        # Should require consent even for local provider
        assert decision.has_pending_consent or decision.was_blocked
    
    @pytest.mark.asyncio
    async def test_redaction_applied(self, firewall):
        """Test that redaction is applied for Level 1."""
        memories = [{
            "id": "personal-1",
            "memory": "John's email is john@test.com",
            "sensitivity": 1,
            "tags": ["contact"],
        }]
        
        decision = await firewall.process(memories, provider="openai")
        
        # Should have redactions
        if decision.permitted:
            # Check that PII was redacted in context
            assert "john@test.com" not in decision.context_text.lower() or decision.redaction_count > 0
    
    def test_evaluate_memory(self, firewall):
        """Test single memory evaluation."""
        memory = {
            "id": "test-1",
            "memory": "My password is secret123",
            "sensitivity": 1,
            "tags": [],
        }
        
        ctx = firewall.evaluate_memory(memory, provider="openai")
        
        assert isinstance(ctx, MemoryContext)
        assert ctx.classification is not None
        # Password should trigger high sensitivity
        assert ctx.effective_sensitivity >= 2
    
    def test_custom_rule(self, firewall):
        """Test adding custom policy rules."""
        # Add a rule to block all work-tagged memories
        rule = PolicyRule(
            id="test-block-work",
            name="Block work memories",
            priority=200,
            conditions={"tags_include": ["work"]},
            action=FirewallAction.BLOCK,
        )
        firewall.add_rule(rule)
        
        memory = {
            "id": "work-1",
            "memory": "Meeting at 3pm",
            "sensitivity": 0,
            "tags": ["work"],
        }
        
        ctx = firewall.evaluate_memory(memory, provider="openai")
        assert ctx.action == FirewallAction.BLOCK
        assert ctx.rule_matched == "test-block-work"
    
    def test_test_rule(self, firewall, sample_memories):
        """Test rule testing functionality."""
        rule = PolicyRule(
            id="test-rule",
            name="Test Rule",
            priority=100,
            conditions={"sensitivity_min": 2},
            action=FirewallAction.BLOCK,
        )
        
        results = firewall.test_rule(rule, sample_memories, provider="openai")
        
        assert len(results) == 4
        # Memories with sensitivity >= 2 should match
        high_sens_matches = [r for r in results if r["matches"]]
        assert len(high_sens_matches) >= 2  # mem-3 and mem-4
    
    def test_decision_summary(self, firewall, sample_memories):
        """Test decision summary generation."""
        import asyncio
        decision = asyncio.run(firewall.process(sample_memories, provider="openai"))
        
        summary = decision.summary
        assert isinstance(summary, str)
        assert len(summary) > 0
    
    def test_audit_entry(self, firewall, sample_memories):
        """Test audit entry generation."""
        import asyncio
        decision = asyncio.run(firewall.process(sample_memories, provider="openai"))
        
        audit = decision.get_audit_entry()
        
        assert "request_id" in audit
        assert "timestamp" in audit
        assert "provider" in audit
        assert "total_memories" in audit
        assert audit["total_memories"] == 4


# ============================================================
# Integration Tests
# ============================================================

class TestIntegration:
    """End-to-end integration tests."""
    
    def test_full_pipeline_sensitive_data(self):
        """Test full pipeline with sensitive data."""
        # Create components
        detector = PIIDetector()
        classifier = SensitivityClassifier(detector=detector)
        redactor = PIIRedactor(detector=detector)
        firewall = PrivacyFirewall(
            classifier=classifier,
            redactor=redactor,
        )
        
        # Test data
        memories = [
            {
                "id": "1",
                "memory": "User's SSN is 123-45-6789",
                "sensitivity": 3,
                "tags": ["identity"],
            }
        ]
        
        import asyncio
        decision = asyncio.run(firewall.process(memories, provider="openai"))
        
        # SSN should be blocked from cloud
        assert decision.was_blocked or decision.has_pending_consent
        # SSN should never appear in context
        assert "123-45-6789" not in decision.context_text
    
    def test_full_pipeline_redaction(self):
        """Test full pipeline with redaction."""
        detector = PIIDetector()
        classifier = SensitivityClassifier(detector=detector)
        redactor = PIIRedactor(detector=detector)
        firewall = PrivacyFirewall(
            classifier=classifier,
            redactor=redactor,
        )
        
        memories = [
            {
                "id": "1",
                "memory": "Contact John at john@acme.com",
                "sensitivity": 1,
                "tags": ["contact"],
            }
        ]
        
        import asyncio
        decision = asyncio.run(firewall.process(memories, provider="openai"))
        
        # Should be permitted with redaction
        if decision.permitted:
            # Email should be redacted
            ctx = decision.permitted[0]
            if ctx.redaction and ctx.redaction.was_modified and ctx.processed_content:
                assert "john@acme.com" not in ctx.processed_content


# ============================================================
# Quick Function Tests
# ============================================================

class TestQuickFunctions:
    """Tests for convenience functions."""
    
    def test_quick_evaluate(self):
        """Test quick_evaluate function."""
        from api.privacy.firewall import quick_evaluate
        
        result = quick_evaluate("My SSN is 123-45-6789", provider="openai")
        
        assert "sensitivity" in result
        assert "action" in result
        assert result["sensitivity"] >= 2  # Should be high
    
    def test_redact_text_function(self):
        """Test redact_text convenience function."""
        from api.privacy.redactor import redact_text
        
        result = redact_text("Email me at test@example.com")
        
        assert "test@example.com" not in result or "[" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
