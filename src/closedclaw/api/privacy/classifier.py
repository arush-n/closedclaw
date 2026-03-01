"""
Sensitivity Classification Module

Classifies memory content into sensitivity levels (0-3) using:
1. User overrides (highest priority)
2. NER-based rules via Presidio/spaCy
3. Keyword heuristics (fast, LLM-free fallback)

Sensitivity Levels:
- 0: Public - General preferences, publicly known facts
- 1: General Personal - Name, profession, general location
- 2: Personal - Address, relationships, finances, mental health
- 3: Highly Sensitive - Medical records, credentials, legal matters, SSN
"""

from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import IntEnum
import re
import logging

from .detector import PIIDetector, DetectedEntity, get_detector

logger = logging.getLogger(__name__)


class SensitivityLevel(IntEnum):
    """Memory sensitivity levels with clear semantics."""
    
    PUBLIC = 0       # Any provider, no redaction required
    GENERAL = 1      # Cloud LLM allowed; basic redaction
    PERSONAL = 2     # Local LLM only by default; explicit permit required for cloud
    SENSITIVE = 3    # Local LLM only; per-request user consent always required
    
    @property
    def label(self) -> str:
        """Human-readable label for the sensitivity level."""
        labels = {
            0: "Public",
            1: "General Personal",
            2: "Personal",
            3: "Highly Sensitive",
        }
        return labels.get(self.value, "Unknown")
    
    @property
    def requires_consent(self) -> bool:
        """Whether this level requires explicit user consent."""
        return self.value >= 3
    
    @property
    def requires_local_only(self) -> bool:
        """Whether this level requires local-only LLM by default."""
        return self.value >= 2
    
    @property
    def requires_redaction(self) -> bool:
        """Whether this level should have PII redacted by default."""
        return self.value >= 1


# Keyword patterns for sensitivity classification (compiled regex)
# Priority order: Level 3 keywords take precedence

LEVEL_3_PATTERNS: List[re.Pattern] = [
    # Medical/Health
    re.compile(r"\b(diagnosis|diagnosed|prognosis|cancer|hiv|aids|std|sti|tumor|biopsy|chemotherapy|radiation therapy|mental illness|psychiatric|suicide|self[- ]harm|eating disorder|addiction|rehab|detox|terminal illness|terminal|illness|disease)\b", re.I),
    re.compile(r"\b(prescription|medication|antidepressant|ssri|opioid|controlled substance|medical record|patient record|hipaa)\b", re.I),
    
    # Financial Credentials
    re.compile(r"\b(ssn|social security|tax id|ein|account number|routing number|pin code|cvv|security code|password|passphrase|secret key|private key|api[- ]?key|access[- ]?token)\b", re.I),
    re.compile(r"\b(bitcoin|ethereum|crypto wallet|seed phrase|recovery phrase|mnemonic)\b", re.I),
    
    # Legal
    re.compile(r"\b(lawsuit|litigation|subpoena|court order|arrest|criminal record|felony|misdemeanor|indictment|settlement agreement|nda breach|attorney[- ]client|privileged)\b", re.I),
    
    # Identity Documents  
    re.compile(r"\b(passport number|driver'?s? license|license number|visa number|green card|immigration status|undocumented)\b", re.I),
    
    # Biometric
    re.compile(r"\b(fingerprint|retina|iris scan|facial recognition|biometric|dna|genetic|genome)\b", re.I),
]

LEVEL_2_PATTERNS: List[re.Pattern] = [
    # Personal Address/Location
    re.compile(r"\b(home address|street address|apartment|apt\.|suite|zip code|postal code|my address is|i live at)\b", re.I),
    
    # Relationships
    re.compile(r"\b(spouse|husband|wife|partner|girlfriend|boyfriend|ex[- ]?(wife|husband|partner)|divorce|separated|affair|cheating|custody)\b", re.I),
    re.compile(r"\b(my (mom|dad|mother|father|brother|sister|son|daughter|child|children|kids?) (is|are|has|have|said|told))\b", re.I),
    
    # Financial General
    re.compile(r"\b(salary|income|debt|owe|loan|mortgage|bankruptcy|credit score|net worth|investment|401k|ira|pension)\b", re.I),
    re.compile(r"\b(i (earn|make|owe|paid|spent) \$?\d+)\b", re.I),
    re.compile(r"\$\d{4,}", re.I),  # Dollar amounts $1000+
    
    # Mental Health (less acute than Level 3)
    re.compile(r"\b(therapist|therapy|counseling|anxiety|depression|stressed|burnout|panic attack)\b", re.I),
    
    # Politics/Religion (protected categories)
    re.compile(r"\b(voted for|political party|democrat|republican|liberal|conservative|pro[- ]?(life|choice)|my religion|atheist|muslim|christian|jewish|hindu|buddhist)\b", re.I),
    
    # Employment Sensitive
    re.compile(r"\b(fired|terminated|laid off|performance review|hr complaint|hostile work|harassment|discrimination)\b", re.I),
]

LEVEL_1_PATTERNS: List[re.Pattern] = [
    # Basic Personal Info
    re.compile(r"\b(my name is|i am called|nickname|born in|i work at|my job is|i'm a|profession)\b", re.I),
    re.compile(r"\b(email|phone number|cell number|mobile number)\b", re.I),
    
    # Preferences
    re.compile(r"\b(i (like|love|hate|prefer|enjoy|dislike)|my favorite|i always|i never)\b", re.I),
    
    # General Location
    re.compile(r"\b(i live in|from|located in|based in|moved to)\s+(a|the)?\s*\w+\b", re.I),
    
    # Work General
    re.compile(r"\b(my boss|coworker|colleague|manager|team|project|deadline|meeting)\b", re.I),
]


@dataclass
class ClassificationResult:
    """Result of sensitivity classification."""
    
    sensitivity: SensitivityLevel
    confidence: float  # 0.0 to 1.0
    reasons: List[str] = field(default_factory=list)
    entities: List[DetectedEntity] = field(default_factory=list)
    matched_patterns: List[str] = field(default_factory=list)
    user_override: bool = False
    
    @property
    def level(self) -> int:
        """Numeric sensitivity level."""
        return int(self.sensitivity)
    
    @property
    def requires_consent(self) -> bool:
        return self.sensitivity.requires_consent
    
    @property
    def requires_local_only(self) -> bool:
        return self.sensitivity.requires_local_only
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sensitivity": self.level,
            "sensitivity_label": self.sensitivity.label,
            "confidence": self.confidence,
            "reasons": self.reasons,
            "entities": [e.to_dict() for e in self.entities],
            "matched_patterns": self.matched_patterns,
            "user_override": self.user_override,
            "requires_consent": self.requires_consent,
            "requires_local_only": self.requires_local_only,
        }


@dataclass 
class TagSensitivityOverride:
    """User-defined sensitivity override for tags."""
    tag: str
    sensitivity: int
    reason: str = ""


class SensitivityClassifier:
    """
    Classifies text content into sensitivity levels (0-3).
    
    Uses a three-tier priority system:
    1. User overrides (explicit user rules for tags/content)
    2. NER-based rules (Presidio entity detection)
    3. Keyword heuristics (pattern matching fallback)
    
    The classifier always returns the HIGHEST sensitivity level
    found from any source.
    
    Usage:
        classifier = SensitivityClassifier()
        result = classifier.classify("My SSN is 123-45-6789")
        print(result.sensitivity)  # SensitivityLevel.SENSITIVE (3)
    """
    
    def __init__(
        self,
        detector: Optional[PIIDetector] = None,
        tag_overrides: Optional[List[TagSensitivityOverride]] = None,
        default_sensitivity: int = 1,
    ):
        """
        Initialize the sensitivity classifier.
        
        Args:
            detector: PIIDetector instance (uses shared singleton if None)
            tag_overrides: User-defined sensitivity overrides for specific tags
            default_sensitivity: Default level when no signals found
        """
        self._detector = detector
        self._tag_overrides: Dict[str, TagSensitivityOverride] = {}
        self.default_sensitivity = default_sensitivity
        
        if tag_overrides:
            for override in tag_overrides:
                self._tag_overrides[override.tag.lower()] = override
    
    @property
    def detector(self) -> PIIDetector:
        """Get the PII detector, using shared instance if not set."""
        if self._detector is None:
            self._detector = get_detector()
        return self._detector
    
    def add_tag_override(
        self, 
        tag: str, 
        sensitivity: int,
        reason: str = "User override"
    ) -> None:
        """Add a user-defined sensitivity override for a tag."""
        self._tag_overrides[tag.lower()] = TagSensitivityOverride(
            tag=tag,
            sensitivity=sensitivity,
            reason=reason,
        )
    
    def remove_tag_override(self, tag: str) -> bool:
        """Remove a tag override. Returns True if it existed."""
        return self._tag_overrides.pop(tag.lower(), None) is not None
    
    def get_tag_overrides(self) -> Dict[str, TagSensitivityOverride]:
        """Get all current tag overrides."""
        return self._tag_overrides.copy()
    
    def classify(
        self,
        text: str,
        tags: Optional[List[str]] = None,
        user_sensitivity: Optional[int] = None,
    ) -> ClassificationResult:
        """
        Classify the sensitivity of the given text.
        
        Args:
            text: Text to classify
            tags: Optional list of tags associated with the text
            user_sensitivity: Explicit user-set sensitivity (takes priority)
            
        Returns:
            ClassificationResult with level, confidence, and reasons
        """
        reasons: List[str] = []
        matched_patterns: List[str] = []
        
        # Track sensitivities from each source
        sensitivities: List[Tuple[int, str, float]] = []  # (level, reason, confidence)
        
        # 1. User override takes highest priority
        if user_sensitivity is not None:
            sensitivities.append((
                user_sensitivity,
                "User-specified sensitivity level",
                1.0
            ))
        
        # 2. Check tag overrides
        if tags:
            for tag in tags:
                tag_lower = tag.lower()
                if tag_lower in self._tag_overrides:
                    override = self._tag_overrides[tag_lower]
                    sensitivities.append((
                        override.sensitivity,
                        f"Tag override: '{tag}' - {override.reason}",
                        0.95
                    ))
        
        # 3. NER-based classification
        entities = self.detector.detect(text)
        if entities:
            max_entity_level = max(e.sensitivity_level for e in entities)
            high_sensitivity_entities = [
                e for e in entities 
                if e.sensitivity_level == max_entity_level
            ]
            entity_types = [e.entity_type for e in high_sensitivity_entities]
            
            sensitivities.append((
                max_entity_level,
                f"Detected entities: {', '.join(entity_types)}",
                max(e.score for e in high_sensitivity_entities)
            ))
        
        # 4. Keyword pattern matching
        pattern_level, pattern_matches = self._check_patterns(text)
        if pattern_level > 0:
            sensitivities.append((
                pattern_level,
                f"Keyword patterns: {', '.join(pattern_matches[:3])}",
                0.8
            ))
            matched_patterns = pattern_matches
        
        # Determine final sensitivity (highest found)
        if sensitivities:
            # Sort by sensitivity level descending
            sensitivities.sort(key=lambda x: x[0], reverse=True)
            final_level = sensitivities[0][0]
            
            # Collect all reasons at the final level
            for level, reason, conf in sensitivities:
                if level == final_level:
                    reasons.append(reason)
            
            # Confidence is the maximum from matching sources
            confidence = max(conf for lvl, _, conf in sensitivities if lvl == final_level)
        else:
            # No signals found - use default
            final_level = self.default_sensitivity
            confidence = 0.5
            reasons.append(f"Default classification (no specific signals)")
        
        # Clamp to valid range
        final_level = max(0, min(3, final_level))
        
        return ClassificationResult(
            sensitivity=SensitivityLevel(final_level),
            confidence=confidence,
            reasons=reasons,
            entities=entities,
            matched_patterns=matched_patterns,
            user_override=user_sensitivity is not None,
        )
    
    def _check_patterns(self, text: str) -> Tuple[int, List[str]]:
        """
        Check text against keyword patterns.
        
        Returns (sensitivity_level, list_of_matched_pattern_descriptions)
        """
        matched: List[str] = []
        max_level = 0
        
        # Check Level 3 patterns first
        for pattern in LEVEL_3_PATTERNS:
            match = pattern.search(text)
            if match:
                matched.append(f"L3:{match.group()}")
                max_level = max(max_level, 3)
        
        # Check Level 2 patterns
        for pattern in LEVEL_2_PATTERNS:
            match = pattern.search(text)
            if match:
                matched.append(f"L2:{match.group()}")
                max_level = max(max_level, 2)
        
        # Check Level 1 patterns
        for pattern in LEVEL_1_PATTERNS:
            match = pattern.search(text)
            if match:
                matched.append(f"L1:{match.group()}")
                max_level = max(max_level, 1)
        
        return max_level, matched
    
    def classify_batch(
        self,
        texts: List[str],
        tags_list: Optional[List[Optional[List[str]]]] = None,
    ) -> List[ClassificationResult]:
        """
        Classify multiple texts at once.
        
        Args:
            texts: List of texts to classify
            tags_list: Optional list of tag lists (one per text)
            
        Returns:
            List of ClassificationResults
        """
        if tags_list is None:
            tags_list = [None for _ in range(len(texts))]
        
        return [
            self.classify(text, tags)
            for text, tags in zip(texts, tags_list)
        ]
    
    def quick_check(
        self, 
        text: str,
        threshold: int = 2
    ) -> bool:
        """
        Quick check if text exceeds a sensitivity threshold.
        
        Faster than full classify() - uses pattern matching first
        and only runs NER if patterns don't exceed threshold.
        
        Args:
            text: Text to check
            threshold: Sensitivity level to check against
            
        Returns:
            True if sensitivity >= threshold
        """
        # Check patterns first (fast)
        pattern_level, _ = self._check_patterns(text)
        if pattern_level >= threshold:
            return True
        
        # Only run NER if patterns didn't exceed threshold
        max_entity_level = self.detector.get_max_sensitivity(text)
        return max_entity_level >= threshold
    
    def get_consent_requirements(
        self,
        text: str,
        tags: Optional[List[str]] = None,
    ) -> Dict:
        """
        Get detailed consent requirements for text.
        
        Returns info needed for consent gate decisions.
        """
        result = self.classify(text, tags)
        
        return {
            "sensitivity": result.level,
            "sensitivity_label": result.sensitivity.label,
            "requires_consent": result.requires_consent,
            "requires_local_only": result.requires_local_only,
            "reasons": result.reasons,
            "high_sensitivity_entities": [
                e.to_dict() for e in result.entities 
                if e.sensitivity_level >= 2
            ],
            "recommendation": self._get_recommendation(result),
        }
    
    def _get_recommendation(self, result: ClassificationResult) -> str:
        """Generate a human-readable recommendation."""
        if result.sensitivity == SensitivityLevel.SENSITIVE:
            return "This content contains highly sensitive information. Consent is required before sharing with any AI provider. Local-only processing recommended."
        elif result.sensitivity == SensitivityLevel.PERSONAL:
            return "This content contains personal information. Local-only LLM recommended. Cloud providers require explicit policy permit."
        elif result.sensitivity == SensitivityLevel.GENERAL:
            return "This content contains general personal information. Basic redaction will be applied before sharing."
        else:
            return "This content appears safe for general use with any provider."


# Convenience functions

def classify_text(
    text: str,
    tags: Optional[List[str]] = None,
) -> ClassificationResult:
    """
    Convenience function to classify text sensitivity.
    
    Uses a shared classifier instance.
    """
    classifier = SensitivityClassifier()
    return classifier.classify(text, tags)


def get_sensitivity_level(text: str) -> int:
    """
    Quick convenience function to get just the sensitivity level.
    
    Returns integer 0-3.
    """
    return classify_text(text).level


def requires_consent(text: str) -> bool:
    """Check if text requires user consent before sharing."""
    return classify_text(text).requires_consent


def requires_local_only(text: str) -> bool:
    """Check if text should only be processed locally."""
    return classify_text(text).requires_local_only
