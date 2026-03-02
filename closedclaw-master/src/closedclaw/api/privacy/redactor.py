"""
PII Redaction Pipeline Module

Replaces detected PII entities with typed, numbered placeholders.
Maintains a reversible redaction map for audit logging.

Example:
    Input: "Arush moved to Austin last year"
    Output: "[PERSON_1] moved to [CITY_1] last year"
    Map: {"[PERSON_1]": "Arush", "[CITY_1]": "Austin"}
"""

from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import logging
import re

from .detector import PIIDetector, DetectedEntity, get_detector

logger = logging.getLogger(__name__)


class RedactionStyle(str, Enum):
    """Styles for redacted text placeholders."""
    
    TYPED_NUMBERED = "typed_numbered"    # [PERSON_1], [EMAIL_1]
    TYPED_ONLY = "typed_only"            # [PERSON], [EMAIL]  
    GENERIC = "generic"                  # [REDACTED]
    HASH_SHORT = "hash_short"            # [#a1b2c3]
    MASKED = "masked"                    # ****


@dataclass
class RedactionMapping:
    """A single placeholder-to-original mapping."""
    
    placeholder: str
    original: str
    entity_type: str
    start: int
    end: int
    sensitivity: int
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "placeholder": self.placeholder,
            "original": self.original,
            "entity_type": self.entity_type,
            "position": {"start": self.start, "end": self.end},
            "sensitivity": self.sensitivity,
        }


@dataclass
class RedactionResult:
    """
    Result of a redaction operation.
    
    Contains the redacted text and all mappings needed to
    understand what was changed (for audit logging).
    """
    
    original_text: str
    redacted_text: str
    mappings: List[RedactionMapping] = field(default_factory=list)
    entities_blocked: List[DetectedEntity] = field(default_factory=list)
    max_sensitivity: int = 0
    
    @property
    def was_modified(self) -> bool:
        """Whether any redactions were applied."""
        return len(self.mappings) > 0 or len(self.entities_blocked) > 0
    
    @property
    def placeholder_map(self) -> Dict[str, str]:
        """Get placeholder -> original map (for local audit only)."""
        return {m.placeholder: m.original for m in self.mappings}
    
    @property
    def reverse_map(self) -> Dict[str, str]:
        """Get original -> placeholder map."""
        return {m.original: m.placeholder for m in self.mappings}
    
    @property
    def redaction_count(self) -> int:
        """Number of redactions applied."""
        return len(self.mappings)
    
    @property
    def blocked_count(self) -> int:
        """Number of entities that were completely blocked."""
        return len(self.entities_blocked)
    
    @property
    def entity_types_redacted(self) -> Set[str]:
        """Set of entity types that were redacted."""
        return {m.entity_type for m in self.mappings}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "original_length": len(self.original_text),
            "redacted_length": len(self.redacted_text),
            "was_modified": self.was_modified,
            "redaction_count": self.redaction_count,
            "blocked_count": self.blocked_count,
            "max_sensitivity": self.max_sensitivity,
            "entity_types": list(self.entity_types_redacted),
            "mappings": [m.to_dict() for m in self.mappings],
            "blocked_entities": [
                {"type": e.entity_type, "sensitivity": e.sensitivity_level}
                for e in self.entities_blocked
            ],
        }
    
    def get_audit_entry(self, include_originals: bool = False) -> Dict:
        """
        Get audit-safe entry for logging.
        
        By default, does NOT include original values (for privacy).
        Set include_originals=True only for local audit storage.
        """
        entry = {
            "redaction_count": self.redaction_count,
            "blocked_count": self.blocked_count,
            "entity_types": list(self.entity_types_redacted),
            "max_sensitivity": self.max_sensitivity,
        }
        
        if include_originals:
            entry["mappings"] = [m.to_dict() for m in self.mappings]
        else:
            # Only include placeholders and types, not original values
            entry["placeholders"] = [
                {"placeholder": m.placeholder, "type": m.entity_type}
                for m in self.mappings
            ]
        
        return entry


class PIIRedactor:
    """
    PII Redaction engine with typed placeholders.
    
    Replaces detected PII with numbered, typed placeholders
    while maintaining a complete mapping for audit purposes.
    
    Features:
    - Multiple redaction styles (typed, generic, masked, hashed)
    - Configurable entity filtering
    - Sensitivity-based blocking (complete removal)
    - Consistent placeholder numbering within a text
    - Reversible mappings for audit
    
    Usage:
        redactor = PIIRedactor()
        result = redactor.redact("John's email is john@example.com")
        print(result.redacted_text)
        # Output: "[PERSON_1]'s email is [EMAIL_1]"
    """
    
    # Entity type display names for placeholders
    ENTITY_DISPLAY_NAMES: Dict[str, str] = {
        "PERSON": "PERSON",
        "PHONE_NUMBER": "PHONE",
        "EMAIL_ADDRESS": "EMAIL",
        "CREDIT_CARD": "CARD",
        "US_SSN": "SSN",
        "US_PASSPORT": "PASSPORT",
        "US_DRIVER_LICENSE": "LICENSE",
        "US_BANK_NUMBER": "ACCOUNT",
        "IBAN_CODE": "IBAN",
        "IP_ADDRESS": "IP",
        "LOCATION": "LOCATION",
        "DATE_TIME": "DATE",
        "ORGANIZATION": "ORG",
        "URL": "URL",
        "DOMAIN_NAME": "DOMAIN",
        "CRYPTO": "CRYPTO",
        "NRP": "GROUP",
        "ADDRESS": "ADDRESS",
        "AGE": "AGE",
    }
    
    def __init__(
        self,
        detector: Optional[PIIDetector] = None,
        style: RedactionStyle = RedactionStyle.TYPED_NUMBERED,
        block_sensitivity: int = 3,
        redact_sensitivity: int = 1,
        entities_to_redact: Optional[List[str]] = None,
        entities_to_block: Optional[List[str]] = None,
    ):
        """
        Initialize the PII redactor.
        
        Args:
            detector: PIIDetector instance (uses shared singleton if None)
            style: Style for placeholder text
            block_sensitivity: Sensitivity level to completely block (remove context)
            redact_sensitivity: Minimum sensitivity to redact
            entities_to_redact: Specific entity types to redact (None = all)
            entities_to_block: Entity types to always block completely
        """
        self._detector = detector
        self.style = style
        self.block_sensitivity = block_sensitivity
        self.redact_sensitivity = redact_sensitivity
        self.entities_to_redact = set(entities_to_redact) if entities_to_redact else None
        self.entities_to_block = set(entities_to_block or [
            "US_SSN", "CREDIT_CARD", "US_BANK_NUMBER", "IBAN_CODE",
            "US_PASSPORT", "US_DRIVER_LICENSE", "CRYPTO", "AWS_ACCESS_KEY",
        ])
    
    @property
    def detector(self) -> PIIDetector:
        """Get the PII detector."""
        if self._detector is None:
            self._detector = get_detector()
        return self._detector
    
    def redact(
        self,
        text: str,
        entities_to_redact: Optional[List[str]] = None,
        min_sensitivity: Optional[int] = None,
        style: Optional[RedactionStyle] = None,
    ) -> RedactionResult:
        """
        Redact PII from the given text.
        
        Args:
            text: Text to redact
            entities_to_redact: Override entity types to redact
            min_sensitivity: Override minimum sensitivity threshold
            style: Override redaction style
            
        Returns:
            RedactionResult with redacted text and mappings
        """
        if not text or not text.strip():
            return RedactionResult(
                original_text=text,
                redacted_text=text,
            )
        
        # Get configuration
        entity_filter = (
            set(entities_to_redact) if entities_to_redact 
            else self.entities_to_redact
        )
        min_sens = min_sensitivity if min_sensitivity is not None else self.redact_sensitivity
        redact_style = style or self.style
        
        # Detect entities
        entities = self.detector.detect(text)
        
        if not entities:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
            )
        
        # Filter entities
        to_process: List[DetectedEntity] = []
        for entity in entities:
            # Skip if below sensitivity threshold
            if entity.sensitivity_level < min_sens:
                continue
            
            # Skip if not in entity filter (when specified)
            if entity_filter and entity.entity_type not in entity_filter:
                continue
            
            to_process.append(entity)
        
        if not to_process:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                max_sensitivity=max(e.sensitivity_level for e in entities) if entities else 0,
            )
        
        # Separate blocked vs redacted entities
        to_block: List[DetectedEntity] = []
        to_redact: List[DetectedEntity] = []
        
        for entity in to_process:
            if (entity.entity_type in self.entities_to_block or 
                entity.sensitivity_level >= self.block_sensitivity):
                to_block.append(entity)
            else:
                to_redact.append(entity)
        
        # Generate placeholders and build result
        mappings: List[RedactionMapping] = []
        entity_counters: Dict[str, int] = {}
        
        # Sort by position (reverse order for replacement)
        all_entities = to_block + to_redact
        all_entities.sort(key=lambda e: e.start, reverse=True)
        
        redacted_text = text
        
        for entity in all_entities:
            is_blocked = entity in to_block
            
            # Generate placeholder
            placeholder = self._generate_placeholder(
                entity, 
                entity_counters, 
                redact_style,
                is_blocked=is_blocked,
            )
            
            # Replace in text
            redacted_text = (
                redacted_text[:entity.start] + 
                placeholder + 
                redacted_text[entity.end:]
            )
            
            if is_blocked:
                # Don't store mapping for blocked entities (no reversal possible)
                continue
            
            # Store mapping
            mappings.append(RedactionMapping(
                placeholder=placeholder,
                original=entity.text,
                entity_type=entity.entity_type,
                start=entity.start,
                end=entity.end,
                sensitivity=entity.sensitivity_level,
            ))
        
        # Reverse mappings to be in text order
        mappings.reverse()
        
        return RedactionResult(
            original_text=text,
            redacted_text=redacted_text,
            mappings=mappings,
            entities_blocked=to_block,
            max_sensitivity=max(e.sensitivity_level for e in to_process),
        )
    
    def _generate_placeholder(
        self,
        entity: DetectedEntity,
        counters: Dict[str, int],
        style: RedactionStyle,
        is_blocked: bool = False,
    ) -> str:
        """Generate a placeholder string for the entity."""
        
        if is_blocked:
            # Blocked entities get special marker
            type_name = self.ENTITY_DISPLAY_NAMES.get(
                entity.entity_type, entity.entity_type
            )
            return f"[{type_name}_BLOCKED]"
        
        if style == RedactionStyle.GENERIC:
            return "[REDACTED]"
        
        elif style == RedactionStyle.MASKED:
            # Mask with asterisks of similar length
            return "*" * min(max(len(entity.text), 4), 12)
        
        elif style == RedactionStyle.HASH_SHORT:
            # Short hash of the original value
            hash_val = hashlib.sha256(entity.text.encode()).hexdigest()[:6]
            return f"[#{hash_val}]"
        
        elif style == RedactionStyle.TYPED_ONLY:
            type_name = self.ENTITY_DISPLAY_NAMES.get(
                entity.entity_type, entity.entity_type
            )
            return f"[{type_name}]"
        
        else:  # TYPED_NUMBERED (default)
            type_name = self.ENTITY_DISPLAY_NAMES.get(
                entity.entity_type, entity.entity_type
            )
            
            # Increment counter for this type
            if type_name not in counters:
                counters[type_name] = 0
            counters[type_name] += 1
            
            return f"[{type_name}_{counters[type_name]}]"
    
    def redact_batch(
        self,
        texts: List[str],
        **kwargs,
    ) -> List[RedactionResult]:
        """Redact PII from multiple texts."""
        return [self.redact(text, **kwargs) for text in texts]
    
    def redact_for_provider(
        self,
        text: str,
        provider: str,
        sensitivity_rules: Optional[Dict[int, str]] = None,
    ) -> RedactionResult:
        """
        Redact text based on provider-specific rules.
        
        Default rules:
        - Local (ollama): Only redact Level 3+
        - Cloud: Redact Level 1+, block Level 3+
        
        Args:
            text: Text to redact
            provider: Provider name (e.g., "openai", "ollama")
            sensitivity_rules: Custom sensitivity->action mapping
            
        Returns:
            RedactionResult
        """
        is_local = provider.lower() in {"ollama", "local", "llama"}
        
        if is_local:
            # Local providers get minimal redaction
            return self.redact(
                text,
                min_sensitivity=3,  # Only redact highly sensitive
            )
        else:
            # Cloud providers get full redaction
            return self.redact(
                text,
                min_sensitivity=1,  # Redact all personal info
            )
    
    def unredact(
        self,
        redacted_text: str,
        result: RedactionResult,
    ) -> str:
        """
        Reverse redaction using the mapping from a RedactionResult.
        
        Note: Blocked entities cannot be unredacted.
        
        Args:
            redacted_text: Text with placeholders
            result: Original RedactionResult with mappings
            
        Returns:
            Text with placeholders replaced by originals
        """
        unredacted = redacted_text
        
        # Sort mappings by placeholder to ensure consistent replacement
        for mapping in sorted(result.mappings, key=lambda m: len(m.placeholder), reverse=True):
            unredacted = unredacted.replace(mapping.placeholder, mapping.original)
        
        return unredacted
    
    def get_redaction_summary(
        self,
        result: RedactionResult,
    ) -> str:
        """Generate a human-readable summary of redactions applied."""
        if not result.was_modified:
            return "No redactions applied."
        
        lines = []
        
        if result.redaction_count > 0:
            lines.append(f"Redacted {result.redaction_count} item(s):")
            for mapping in result.mappings:
                lines.append(f"  • {mapping.entity_type}: '{mapping.original}' → {mapping.placeholder}")
        
        if result.blocked_count > 0:
            lines.append(f"Blocked {result.blocked_count} highly sensitive item(s):")
            for entity in result.entities_blocked:
                lines.append(f"  • {entity.entity_type} (Level {entity.sensitivity_level})")
        
        return "\n".join(lines)


# Singleton instance
_redactor_instance: Optional[PIIRedactor] = None


def get_redactor(**kwargs) -> PIIRedactor:
    """Get a shared PIIRedactor instance."""
    global _redactor_instance
    
    if _redactor_instance is None:
        _redactor_instance = PIIRedactor(**kwargs)
    
    return _redactor_instance


def reset_redactor() -> None:
    """Reset the singleton redactor instance."""
    global _redactor_instance
    _redactor_instance = None


# Convenience functions

def redact_text(
    text: str,
    min_sensitivity: int = 1,
) -> str:
    """
    Quick convenience function to redact text.
    
    Returns only the redacted text string.
    """
    return get_redactor().redact(text, min_sensitivity=min_sensitivity).redacted_text


def redact_with_map(
    text: str,
    min_sensitivity: int = 1,
) -> Tuple[str, Dict[str, str]]:
    """
    Redact text and return both redacted text and placeholder map.
    
    Returns (redacted_text, {placeholder: original})
    """
    result = get_redactor().redact(text, min_sensitivity=min_sensitivity)
    return result.redacted_text, result.placeholder_map
