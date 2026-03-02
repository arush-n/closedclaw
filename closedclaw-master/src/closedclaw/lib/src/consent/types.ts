/**
 * Closedclaw Consent Receipt Types
 */

import type { MemoryId, SensitivityLevel, UserDecision, Redaction } from "../crypto/types.js";

export type ReceiptId = string;

/**
 * Unsigned consent receipt data (before signing)
 */
export interface UnsignedConsentReceipt {
  receiptId: ReceiptId;
  timestamp: string;
  memoryId: MemoryId;
  memoryHash: string;
  provider: string;
  redactions: Redaction[];
  sensitivityLevel: SensitivityLevel;
  userDecision: UserDecision;
  ruleTriggered: string;
  userPubkey: string;
}

/**
 * Signed consent receipt (complete, verifiable)
 */
export interface SignedConsentReceipt extends UnsignedConsentReceipt {
  signature: string;
}

/**
 * Consent receipt with binary fields
 */
export interface ConsentReceiptBinary {
  receiptId: ReceiptId;
  timestamp: Date;
  memoryId: MemoryId;
  memoryHash: Uint8Array;
  provider: string;
  redactions: Redaction[];
  sensitivityLevel: SensitivityLevel;
  userDecision: UserDecision;
  ruleTriggered: string;
  userPubkey: Uint8Array;
  signature: Uint8Array;
}

/**
 * Consent verification result
 */
export interface VerificationResult {
  signatureValid: boolean;
  memoryHashValid: boolean;
  expired: boolean;
  verifiedAt: Date;
  error?: string;
}

/**
 * Policy rule that triggered consent requirement
 */
export interface PolicyRule {
  id: string;
  description: string;
  sensitivityThreshold?: SensitivityLevel;
  entityTypes?: string[];
  mandatory: boolean;
}

/**
 * Consent gate decision
 */
export interface ConsentDecision {
  consentRequired: boolean;
  triggeredRules: PolicyRule[];
  suggestedRedactions: Redaction[];
  sensitivityLevel: SensitivityLevel;
}

/**
 * Consent gate configuration
 */
export interface ConsentGateConfig {
  consentRequiredLevels: SensitivityLevel[];
  rules: PolicyRule[];
  redactionPatterns: Record<string, RegExp>;
  autoApproveBasicMemories: boolean;
  receiptTtlSeconds: number;
}

/**
 * Consent receipt query options
 */
export interface ConsentReceiptQuery {
  memoryId?: MemoryId;
  provider?: string;
  userDecision?: UserDecision;
  fromDate?: Date;
  toDate?: Date;
  sensitivityLevel?: SensitivityLevel;
  limit?: number;
  offset?: number;
}

/**
 * Consent receipt storage interface
 */
export interface ConsentReceiptStore {
  store(receipt: SignedConsentReceipt): Promise<void>;
  get(receiptId: ReceiptId): Promise<SignedConsentReceipt | null>;
  query(options: ConsentReceiptQuery): Promise<SignedConsentReceipt[]>;
  getByMemory(memoryId: MemoryId): Promise<SignedConsentReceipt[]>;
  getByProvider(provider: string): Promise<SignedConsentReceipt[]>;
  deleteByMemory(memoryId: MemoryId): Promise<number>;
  count(): Promise<number>;
}
