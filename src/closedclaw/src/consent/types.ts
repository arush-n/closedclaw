/**
 * Closedclaw Consent Receipt Types
 * 
 * Consent receipts are machine-readable, cryptographically signed records
 * of user decisions to share specific memories with specific AI providers.
 * 
 * Core artifact for:
 * - GDPR data access rights
 * - HIPAA audit requirements
 * - AI data governance compliance
 */

import type { MemoryId, SensitivityLevel, UserDecision, Redaction } from "../crypto/types";

/**
 * Consent receipt identifier
 */
export type ReceiptId = string;

/**
 * Provider identity for consent tracking
 */
export interface ProviderInfo {
  /** Provider identifier (e.g., "openai", "anthropic", "google") */
  id: string;
  /** Human-readable provider name */
  name: string;
  /** Model identifier if applicable */
  model?: string;
  /** API endpoint used */
  endpoint?: string;
}

/**
 * Policy rule that triggered consent requirement
 */
export interface PolicyRule {
  /** Unique rule identifier */
  id: string;
  /** Human-readable rule description */
  description: string;
  /** Sensitivity threshold that triggered this rule */
  sensitivityThreshold?: SensitivityLevel;
  /** Entity types this rule applies to */
  entityTypes?: string[];
  /** Whether this rule is mandatory (cannot be overridden) */
  mandatory: boolean;
}

/**
 * Unsigned consent receipt data (before signing)
 */
export interface UnsignedConsentReceipt {
  /** UUID v4 receipt identifier */
  receiptId: ReceiptId;
  /** ISO 8601 timestamp with millisecond precision */
  timestamp: string;
  /** Reference to the vault entry (memory) */
  memoryId: MemoryId;
  /** SHA-256 hash of plaintext at time of consent (hex) */
  memoryHash: string;
  /** LLM provider the memory was approved for */
  provider: string;
  /** Redactions applied before sending to provider */
  redactions: Redaction[];
  /** Sensitivity level at time of consent (0-3) */
  sensitivityLevel: SensitivityLevel;
  /** User's decision */
  userDecision: UserDecision;
  /** Policy rule ID that triggered consent requirement */
  ruleTriggered: string;
  /** User's Ed25519 public key (hex) */
  userPubkey: string;
}

/**
 * Signed consent receipt (complete, verifiable)
 */
export interface SignedConsentReceipt extends UnsignedConsentReceipt {
  /** Ed25519 signature over canonical JSON (hex) */
  signature: string;
}

/**
 * Consent receipt with binary fields (internal use)
 */
export interface ConsentReceiptBinary {
  /** UUID v4 receipt identifier */
  receiptId: ReceiptId;
  /** Timestamp */
  timestamp: Date;
  /** Reference to the vault entry */
  memoryId: MemoryId;
  /** SHA-256 hash of plaintext at time of consent */
  memoryHash: Uint8Array;
  /** Provider identifier */
  provider: string;
  /** Redactions applied */
  redactions: Redaction[];
  /** Sensitivity level (0-3) */
  sensitivityLevel: SensitivityLevel;
  /** User's decision */
  userDecision: UserDecision;
  /** Policy rule ID */
  ruleTriggered: string;
  /** User's Ed25519 public key */
  userPubkey: Uint8Array;
  /** Ed25519 signature */
  signature: Uint8Array;
}

/**
 * Consent verification result
 */
export interface VerificationResult {
  /** Whether the signature is valid */
  signatureValid: boolean;
  /** Whether the memory hash matches current memory */
  memoryHashValid: boolean;
  /** Whether the receipt is expired (if TTL set) */
  expired: boolean;
  /** Verification timestamp */
  verifiedAt: Date;
  /** Error message if verification failed */
  error?: string;
}

/**
 * Consent receipt query options
 */
export interface ConsentReceiptQuery {
  /** Filter by memory ID */
  memoryId?: MemoryId;
  /** Filter by provider */
  provider?: string;
  /** Filter by user decision */
  userDecision?: UserDecision;
  /** Filter by date range (start) */
  fromDate?: Date;
  /** Filter by date range (end) */
  toDate?: Date;
  /** Filter by sensitivity level */
  sensitivityLevel?: SensitivityLevel;
  /** Maximum results to return */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * Consent receipt storage interface
 */
export interface ConsentReceiptStore {
  /** Store a new consent receipt */
  store(receipt: SignedConsentReceipt): Promise<void>;
  
  /** Retrieve a consent receipt by ID */
  get(receiptId: ReceiptId): Promise<SignedConsentReceipt | null>;
  
  /** Query consent receipts */
  query(options: ConsentReceiptQuery): Promise<SignedConsentReceipt[]>;
  
  /** Get all receipts for a memory */
  getByMemory(memoryId: MemoryId): Promise<SignedConsentReceipt[]>;
  
  /** Get consent history for a provider */
  getByProvider(provider: string): Promise<SignedConsentReceipt[]>;
  
  /** Delete receipts for a memory (on memory deletion) */
  deleteByMemory(memoryId: MemoryId): Promise<number>;
  
  /** Count total receipts */
  count(): Promise<number>;
}

/**
 * Consent gate configuration
 */
export interface ConsentGateConfig {
  /** Sensitivity levels requiring user consent */
  consentRequiredLevels: SensitivityLevel[];
  /** Policy rules */
  rules: PolicyRule[];
  /** Default redaction patterns by entity type */
  redactionPatterns: Record<string, RegExp>;
  /** Whether to auto-approve Level 0-1 memories */
  autoApproveBasicMemories: boolean;
  /** TTL for consent receipts in seconds (0 = no expiry) */
  receiptTtlSeconds: number;
}

/**
 * Default consent gate configuration
 */
export const DEFAULT_CONSENT_GATE_CONFIG: ConsentGateConfig = {
  consentRequiredLevels: [2, 3], // Medium and high sensitivity require consent
  rules: [],
  redactionPatterns: {
    email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    phone: /\+?[\d\s\-().]{10,}/g,
    ssn: /\d{3}-\d{2}-\d{4}/g,
    creditCard: /\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}/g,
    ipAddress: /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/g,
  },
  autoApproveBasicMemories: true,
  receiptTtlSeconds: 0, // No expiry by default
};

/**
 * Consent gate decision
 */
export interface ConsentDecision {
  /** Whether consent is required for this memory */
  consentRequired: boolean;
  /** Policy rules that triggered consent requirement */
  triggeredRules: PolicyRule[];
  /** Suggested redactions */
  suggestedRedactions: Redaction[];
  /** Recommended sensitivity level */
  sensitivityLevel: SensitivityLevel;
}

/**
 * Export formats for consent receipts
 */
export type ExportFormat = "json" | "csv" | "pdf";

/**
 * Export options
 */
export interface ExportOptions {
  /** Export format */
  format: ExportFormat;
  /** Include signature verification status */
  includeVerification: boolean;
  /** Date range filter */
  dateRange?: {
    from: Date;
    to: Date;
  };
  /** Filter by providers */
  providers?: string[];
}
