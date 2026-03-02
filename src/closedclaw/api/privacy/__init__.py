"""
Closedclaw Privacy Firewall Module

NER/PII detection, sensitivity classification, and redaction pipeline
using spaCy + Microsoft Presidio for local, private analysis.
"""

from .detector import PIIDetector, DetectedEntity
from .classifier import SensitivityClassifier, SensitivityLevel
from .redactor import PIIRedactor, RedactionResult
from .firewall import PrivacyFirewall, FirewallDecision, MemoryContext

__all__ = [
    "PIIDetector",
    "DetectedEntity", 
    "SensitivityClassifier",
    "SensitivityLevel",
    "PIIRedactor",
    "RedactionResult",
    "PrivacyFirewall",
    "FirewallDecision",
    "MemoryContext",
]
