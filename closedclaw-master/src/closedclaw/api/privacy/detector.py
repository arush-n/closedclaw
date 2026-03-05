"""
PII Detection Module using Microsoft Presidio + spaCy

Provides local, offline PII/NER detection without any API calls.
Supports multiple entity types relevant to personal AI memory.

Falls back to regex-based detection if Presidio/spaCy unavailable.
"""

from typing import List, Dict, Optional, Set, Any
from dataclasses import dataclass, field
from enum import Enum
import logging
import re

logger = logging.getLogger(__name__)

# Try to import Presidio - fall back to regex if not available or incompatible
PRESIDIO_AVAILABLE = False
try:
    from presidio_analyzer import AnalyzerEngine, RecognizerResult
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    PRESIDIO_AVAILABLE = True
except Exception as e:
    logger.warning(f"Presidio unavailable/incompatible - using regex-based PII detection: {e}")
    AnalyzerEngine = None
    RecognizerResult = None
    NlpEngineProvider = None


class EntityType(str, Enum):
    """Supported PII entity types with sensitivity implications."""
    
    # Level 3 - Highly Sensitive (always require consent)
    SSN = "US_SSN"
    PASSPORT = "US_PASSPORT"
    DRIVER_LICENSE = "US_DRIVER_LICENSE"
    BANK_ACCOUNT = "US_BANK_NUMBER"
    CREDIT_CARD = "CREDIT_CARD"
    IBAN = "IBAN_CODE"
    CRYPTO_WALLET = "CRYPTO"
    MEDICAL_LICENSE = "MEDICAL_LICENSE"
    IP_ADDRESS = "IP_ADDRESS"
    
    # Level 2 - Personal (local-only by default)
    PHONE = "PHONE_NUMBER"
    EMAIL = "EMAIL_ADDRESS"
    LOCATION = "LOCATION"
    DATE_OF_BIRTH = "DATE_TIME"  # When contextually a DOB
    ADDRESS = "ADDRESS"
    AGE = "AGE"
    
    # Level 1 - General Personal
    PERSON = "PERSON"
    ORGANIZATION = "ORGANIZATION"
    DATE = "DATE_TIME"
    NRP = "NRP"  # Nationality, religious, political group
    
    # Level 0 - Public/Informational
    URL = "URL"
    DOMAIN = "DOMAIN_NAME"


# Mapping entity types to default sensitivity levels
ENTITY_SENSITIVITY_MAP: Dict[str, int] = {
    # Level 3 - Highly Sensitive
    "US_SSN": 3,
    "SSN": 3,
    "US_PASSPORT": 3,
    "US_DRIVER_LICENSE": 3,
    "US_BANK_NUMBER": 3,
    "CREDIT_CARD": 3,
    "IBAN_CODE": 3,
    "CRYPTO": 3,
    "MEDICAL_LICENSE": 3,
    "IP_ADDRESS": 3,
    "AWS_ACCESS_KEY": 3,
    "AZURE_AUTH_TOKEN": 3,
    
    # Level 2 - Personal
    "PHONE_NUMBER": 2,
    "EMAIL_ADDRESS": 2,
    "LOCATION": 2,
    "ADDRESS": 2,
    "AGE": 2,
    
    # Level 1 - General Personal
    "PERSON": 1,
    "ORGANIZATION": 1,
    "DATE_TIME": 1,
    "NRP": 2,  # Actually sensitive due to protected categories
    
    # Level 0 - Public
    "URL": 0,
    "DOMAIN_NAME": 0,
}


# Regex patterns for fallback PII detection
REGEX_PATTERNS: Dict[str, re.Pattern] = {
    # Level 3 - Highly Sensitive
    "US_SSN": re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
    "CREDIT_CARD": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    "US_BANK_NUMBER": re.compile(r"\b\d{8,17}\b"),
    "IP_ADDRESS": re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
    
    # Level 2 - Personal  
    "EMAIL_ADDRESS": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
    "PHONE_NUMBER": re.compile(r"\b(?:\+1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
    
    # Level 1 - General (simple heuristics)
    "URL": re.compile(r"https?://[^\s]+"),
    "DOMAIN_NAME": re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b"),
}


@dataclass
class DetectedEntity:
    """A detected PII entity with metadata."""
    
    entity_type: str
    text: str
    start: int
    end: int
    score: float
    sensitivity_level: int = field(default=1)
    
    @classmethod
    def from_presidio_result(
        cls, 
        result: Any, 
        original_text: str
    ) -> "DetectedEntity":
        """Create from a Presidio RecognizerResult."""
        if result is None:
            raise ValueError("RecognizerResult cannot be None")
        entity_text = original_text[result.start:result.end]
        sensitivity = ENTITY_SENSITIVITY_MAP.get(result.entity_type, 1)
        
        return cls(
            entity_type=result.entity_type,
            text=entity_text,
            start=result.start,
            end=result.end,
            score=result.score,
            sensitivity_level=sensitivity,
        )
    
    @classmethod
    def from_regex_match(
        cls,
        match: re.Match,
        entity_type: str,
    ) -> "DetectedEntity":
        """Create from a regex match."""
        sensitivity = ENTITY_SENSITIVITY_MAP.get(entity_type, 1)
        
        return cls(
            entity_type=entity_type,
            text=match.group(),
            start=match.start(),
            end=match.end(),
            score=0.8,  # Regex matches get a reasonable confidence
            sensitivity_level=sensitivity,
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "entity_type": self.entity_type,
            "text": self.text,
            "start": self.start,
            "end": self.end,
            "score": self.score,
            "sensitivity_level": self.sensitivity_level,
        }


class PIIDetector:
    """
    PII/NER detection engine using Presidio + spaCy.
    
    Runs entirely locally without any API calls.
    Supports CUDA acceleration when available.
    
    Usage:
        detector = PIIDetector()
        entities = detector.detect("My SSN is 123-45-6789")
    """
    
    # Default entity types to detect
    DEFAULT_ENTITIES: List[str] = [
        "PERSON",
        "PHONE_NUMBER", 
        "EMAIL_ADDRESS",
        "CREDIT_CARD",
        "CRYPTO",
        "US_SSN",
        "US_PASSPORT",
        "US_DRIVER_LICENSE",
        "US_BANK_NUMBER",
        "IBAN_CODE",
        "IP_ADDRESS",
        "LOCATION",
        "DATE_TIME",
        "NRP",
        "ORGANIZATION",
        "URL",
        "DOMAIN_NAME",
    ]
    
    def __init__(
        self,
        spacy_model: str = "en_core_web_lg",
        entities: Optional[List[str]] = None,
        score_threshold: float = 0.5,
        use_gpu: bool = True,
    ):
        """
        Initialize the PII detector.
        
        Args:
            spacy_model: spaCy model to use (en_core_web_lg recommended)
            entities: List of entity types to detect (defaults to all supported)
            score_threshold: Minimum confidence score to include (0.0-1.0)
            use_gpu: Whether to use CUDA if available
        """
        self.spacy_model = spacy_model
        self.entities = entities or self.DEFAULT_ENTITIES
        self.score_threshold = score_threshold
        self._analyzer: Optional[Any] = None
        self._initialized = False
        self._use_regex_fallback = not PRESIDIO_AVAILABLE
        
        # GPU configuration (only relevant when using Presidio)
        self.use_gpu = use_gpu
        if use_gpu and PRESIDIO_AVAILABLE:
            try:
                import spacy
                if spacy.prefer_gpu():
                    logger.info("PII Detector: GPU acceleration enabled")
                else:
                    logger.info("PII Detector: Running on CPU (no GPU available)")
            except Exception as e:
                logger.warning(f"GPU setup failed, using CPU: {e}")
        
        if self._use_regex_fallback:
            logger.info("PII Detector: Using regex-based fallback (Presidio unavailable)")
    
    def _initialize(self) -> None:
        """Lazy initialization of the Presidio analyzer (if available)."""
        if self._initialized:
            return
        
        if self._use_regex_fallback:
            # Regex mode - no initialization needed
            self._initialized = True
            logger.info("PII Detector: Regex fallback ready")
            return
            
        logger.info(f"Initializing PII Detector with model: {self.spacy_model}")
        
        try:
            # Configure spaCy NLP engine for Presidio
            nlp_config = {
                "nlp_engine_name": "spacy",
                "models": [
                    {"lang_code": "en", "model_name": self.spacy_model}
                ],
            }
            
            # Create NLP engine (type ignored - runtime check via PRESIDIO_AVAILABLE)
            nlp_engine = NlpEngineProvider(nlp_configuration=nlp_config).create_engine()  # type: ignore[misc]
            
            # Create Presidio analyzer
            self._analyzer = AnalyzerEngine(  # type: ignore[misc]
                nlp_engine=nlp_engine,
                supported_languages=["en"],
            )
            
            self._initialized = True
            logger.info("PII Detector initialized successfully")
            
        except Exception as e:
            logger.warning(f"Presidio init failed, falling back to regex: {e}")
            self._use_regex_fallback = True
            self._initialized = True
    
    @property
    def analyzer(self) -> Any:
        """Get the Presidio analyzer, initializing if needed."""
        if not self._initialized:
            self._initialize()
        return self._analyzer
    
    def _detect_with_regex(self, text: str) -> List[DetectedEntity]:
        """Fallback regex-based PII detection."""
        detected: List[DetectedEntity] = []
        
        for entity_type, pattern in REGEX_PATTERNS.items():
            for match in pattern.finditer(text):
                entity = DetectedEntity.from_regex_match(match, entity_type)
                detected.append(entity)
        
        # Remove overlapping detections (keep the more sensitive one)
        detected = self._remove_overlaps(detected)
        
        # Sort by position
        detected.sort(key=lambda e: e.start)
        
        return detected
    
    def _remove_overlaps(self, entities: List[DetectedEntity]) -> List[DetectedEntity]:
        """Remove overlapping entities, keeping the most sensitive."""
        if not entities:
            return []
        
        # Sort by start position
        sorted_entities = sorted(entities, key=lambda e: (e.start, -e.sensitivity_level))
        result: List[DetectedEntity] = []
        
        for entity in sorted_entities:
            # Check if this overlaps with the last added entity
            if result and entity.start < result[-1].end:
                # Overlapping - keep the more sensitive one
                if entity.sensitivity_level > result[-1].sensitivity_level:
                    result[-1] = entity
            else:
                result.append(entity)
        
        return result
    
    def detect(
        self,
        text: str,
        entities: Optional[List[str]] = None,
        language: str = "en",
    ) -> List[DetectedEntity]:
        """
        Detect PII entities in the given text.
        
        Args:
            text: Text to analyze
            entities: Specific entity types to detect (defaults to all)
            language: Language code
            
        Returns:
            List of detected entities with sensitivity levels
        """
        if not text or not text.strip():
            return []
        
        # Ensure initialized
        if not self._initialized:
            self._initialize()
        
        entities_to_detect = entities or self.entities
        
        # Use regex fallback if Presidio not available
        if self._use_regex_fallback:
            detected = self._detect_with_regex(text)
            # Filter by requested entities
            if entities_to_detect:
                entity_set = set(entities_to_detect)
                detected = [e for e in detected if e.entity_type in entity_set]
            return detected
        
        try:
            # Run Presidio analysis
            results = self.analyzer.analyze(
                text=text,
                entities=entities_to_detect,
                language=language,
            )
            
            # Filter by score threshold and convert to our format
            detected: List[DetectedEntity] = []
            for result in results:
                if result.score >= self.score_threshold:
                    entity = DetectedEntity.from_presidio_result(result, text)
                    detected.append(entity)
            
            # Sort by position in text
            detected.sort(key=lambda e: e.start)
            
            return detected
            
        except Exception as e:
            logger.error(f"PII detection failed: {e}")
            # Fall back to regex
            return self._detect_with_regex(text)
    
    async def detect_with_ollama(
        self,
        text: str,
        entities: Optional[List[str]] = None,
    ) -> List[DetectedEntity]:
        """
        Enhanced detection using local Ollama LLM + regex/Presidio.

        Merges results from the standard pipeline with Ollama-based detection.
        Falls back to standard detection if Ollama is unavailable.
        """
        standard = self.detect(text, entities)

        try:
            from .ollama_redactor import get_ollama_redaction_engine
            engine = get_ollama_redaction_engine()
            if not await engine.is_available():
                return standard
            ollama_entities = await engine.detect_pii(text)
        except Exception as exc:
            logger.debug("Ollama-enhanced detection unavailable: %s", exc)
            return standard

        if not ollama_entities:
            return standard

        # Merge: add Ollama entities that don't overlap with existing ones
        merged = list(standard)
        for oe in ollama_entities:
            overlaps = any(
                not (oe.end <= se.start or oe.start >= se.end)
                for se in standard
            )
            if not overlaps:
                merged.append(oe)

        merged.sort(key=lambda e: e.start)
        return merged

    def detect_batch(
        self,
        texts: List[str],
        entities: Optional[List[str]] = None,
    ) -> List[List[DetectedEntity]]:
        """
        Detect PII entities in multiple texts.
        
        Args:
            texts: List of texts to analyze
            entities: Specific entity types to detect
            
        Returns:
            List of entity lists, one per input text
        """
        return [self.detect(text, entities) for text in texts]
    
    def get_entity_types(self, text: str) -> Set[str]:
        """
        Get just the set of entity types present in text.
        
        Useful for quick sensitivity classification without full detection.
        """
        entities = self.detect(text)
        return {e.entity_type for e in entities}
    
    def get_max_sensitivity(self, text: str) -> int:
        """
        Get the maximum sensitivity level of any entity in the text.
        
        Returns 0 if no entities detected.
        """
        entities = self.detect(text)
        if not entities:
            return 0
        return max(e.sensitivity_level for e in entities)
    
    def contains_sensitive_entities(
        self, 
        text: str, 
        min_sensitivity: int = 2
    ) -> bool:
        """
        Quick check if text contains entities at or above sensitivity level.
        
        Args:
            text: Text to check
            min_sensitivity: Minimum sensitivity level to flag (default: 2)
            
        Returns:
            True if sensitive entities found
        """
        entities = self.detect(text)
        return any(e.sensitivity_level >= min_sensitivity for e in entities)
    
    def get_supported_entities(self) -> List[str]:
        """Get list of all supported entity types."""
        if self._use_regex_fallback:
            return list(REGEX_PATTERNS.keys())
        if not self._initialized:
            self._initialize()
        if self._use_regex_fallback:
            return list(REGEX_PATTERNS.keys())
        return self.analyzer.get_supported_entities()
    
    def analyze_for_consent(
        self, 
        text: str
    ) -> Dict[str, Any]:
        """
        Analyze text and determine if consent is required.
        
        Returns a detailed analysis suitable for consent gate decisions.
        """
        entities = self.detect(text)
        
        # Group entities by sensitivity level
        by_level: Dict[int, List[DetectedEntity]] = {0: [], 1: [], 2: [], 3: []}
        for entity in entities:
            level = entity.sensitivity_level
            by_level[level].append(entity)
        
        max_sensitivity = max((e.sensitivity_level for e in entities), default=0)
        
        return {
            "text_length": len(text),
            "entity_count": len(entities),
            "max_sensitivity": max_sensitivity,
            "requires_consent": max_sensitivity >= 3,
            "requires_local_only": max_sensitivity >= 2,
            "entities_by_level": {
                level: [e.to_dict() for e in ents] 
                for level, ents in by_level.items()
            },
            "entity_types": list({e.entity_type for e in entities}),
        }


# Singleton instance for shared use
_detector_instance: Optional[PIIDetector] = None


def get_detector(
    spacy_model: str = "en_core_web_lg",
    **kwargs
) -> PIIDetector:
    """
    Get a shared PIIDetector instance.
    
    Uses singleton pattern to avoid reloading spaCy model repeatedly.
    """
    global _detector_instance
    
    if _detector_instance is None:
        _detector_instance = PIIDetector(spacy_model=spacy_model, **kwargs)
    
    return _detector_instance


def reset_detector() -> None:
    """Reset the singleton detector instance."""
    global _detector_instance
    _detector_instance = None
