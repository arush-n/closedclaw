/**
 * Closedclaw Consent Receipt Manager
 */

import { v4 as uuidv4 } from "uuid";
import {
  sign,
  verify,
  hashForSigning,
  publicKeyToHex,
  signatureToHex,
  hexToPublicKey,
  hexToSignature,
} from "../crypto/ed25519.js";
import { computeHash, hashToHex, hexToHash } from "../crypto/aes.js";
import type { SigningKeyPair, SensitivityLevel, UserDecision, Redaction, MemoryId } from "../crypto/types.js";
import type {
  UnsignedConsentReceipt,
  SignedConsentReceipt,
  ConsentReceiptBinary,
  VerificationResult,
  PolicyRule,
  ConsentDecision,
  ConsentGateConfig,
} from "./types.js";

/**
 * Convert consent receipt to canonical JSON for signing
 */
export function toCanonicalJSON(receipt: UnsignedConsentReceipt): string {
  const ordered = {
    memoryHash: receipt.memoryHash,
    memoryId: receipt.memoryId,
    provider: receipt.provider,
    receiptId: receipt.receiptId,
    redactions: receipt.redactions.map((r) => ({
      entityType: r.entityType,
      placeholder: r.placeholder,
    })),
    ruleTriggered: receipt.ruleTriggered,
    sensitivityLevel: receipt.sensitivityLevel,
    timestamp: receipt.timestamp,
    userDecision: receipt.userDecision,
    userPubkey: receipt.userPubkey,
  };
  return JSON.stringify(ordered);
}

/**
 * Parse canonical JSON back to unsigned receipt
 */
export function fromCanonicalJSON(json: string): UnsignedConsentReceipt {
  const parsed = JSON.parse(json);
  return {
    receiptId: parsed.receiptId,
    timestamp: parsed.timestamp,
    memoryId: parsed.memoryId,
    memoryHash: parsed.memoryHash,
    provider: parsed.provider,
    redactions: parsed.redactions,
    sensitivityLevel: parsed.sensitivityLevel,
    userDecision: parsed.userDecision,
    ruleTriggered: parsed.ruleTriggered,
    userPubkey: parsed.userPubkey,
  };
}

/**
 * Create an unsigned consent receipt
 */
export function createUnsignedReceipt(
  memoryId: MemoryId,
  memoryContent: Uint8Array,
  provider: string,
  redactions: Redaction[],
  sensitivityLevel: SensitivityLevel,
  userDecision: UserDecision,
  ruleTriggered: string,
  userPubkey: Uint8Array
): UnsignedConsentReceipt {
  const memoryHash = computeHash(memoryContent);

  return {
    receiptId: uuidv4(),
    timestamp: new Date().toISOString(),
    memoryId,
    memoryHash: hashToHex(memoryHash),
    provider,
    redactions,
    sensitivityLevel,
    userDecision,
    ruleTriggered,
    userPubkey: publicKeyToHex(userPubkey),
  };
}

/**
 * Sign a consent receipt
 */
export function signReceipt(
  unsignedReceipt: UnsignedConsentReceipt,
  privateKey: Uint8Array
): SignedConsentReceipt {
  const canonicalJson = toCanonicalJSON(unsignedReceipt);
  const messageBytes = new TextEncoder().encode(canonicalJson);
  const messageHash = hashForSigning(messageBytes);
  const signature = sign(messageHash, privateKey);

  return {
    ...unsignedReceipt,
    signature: signatureToHex(signature),
  };
}

/**
 * Verify a signed consent receipt
 */
export function verifyReceipt(
  receipt: SignedConsentReceipt,
  currentMemoryContent?: Uint8Array
): VerificationResult {
  try {
    const { signature, ...unsignedPortion } = receipt;
    const canonicalJson = toCanonicalJSON(unsignedPortion);
    const messageBytes = new TextEncoder().encode(canonicalJson);
    const messageHash = hashForSigning(messageBytes);

    const signatureBytes = hexToSignature(signature);
    const publicKeyBytes = hexToPublicKey(receipt.userPubkey);
    const signatureValid = verify(signatureBytes, messageHash, publicKeyBytes);

    let memoryHashValid = true;
    if (currentMemoryContent) {
      const currentHash = hashToHex(computeHash(currentMemoryContent));
      memoryHashValid = currentHash === receipt.memoryHash;
    }

    return {
      signatureValid,
      memoryHashValid,
      expired: false,
      verifiedAt: new Date(),
    };
  } catch (error) {
    return {
      signatureValid: false,
      memoryHashValid: false,
      expired: false,
      verifiedAt: new Date(),
      error: error instanceof Error ? error.message : "Unknown verification error",
    };
  }
}

/**
 * Convert signed receipt to binary format
 */
export function receiptToBinary(receipt: SignedConsentReceipt): ConsentReceiptBinary {
  return {
    receiptId: receipt.receiptId,
    timestamp: new Date(receipt.timestamp),
    memoryId: receipt.memoryId,
    memoryHash: hexToHash(receipt.memoryHash),
    provider: receipt.provider,
    redactions: receipt.redactions,
    sensitivityLevel: receipt.sensitivityLevel,
    userDecision: receipt.userDecision,
    ruleTriggered: receipt.ruleTriggered,
    userPubkey: hexToPublicKey(receipt.userPubkey),
    signature: hexToSignature(receipt.signature),
  };
}

/**
 * Convert binary receipt back to signed receipt format
 */
export function binaryToReceipt(binary: ConsentReceiptBinary): SignedConsentReceipt {
  return {
    receiptId: binary.receiptId,
    timestamp: binary.timestamp.toISOString(),
    memoryId: binary.memoryId,
    memoryHash: hashToHex(binary.memoryHash),
    provider: binary.provider,
    redactions: binary.redactions,
    sensitivityLevel: binary.sensitivityLevel,
    userDecision: binary.userDecision,
    ruleTriggered: binary.ruleTriggered,
    userPubkey: publicKeyToHex(binary.userPubkey),
    signature: signatureToHex(binary.signature),
  };
}

/**
 * Consent Receipt Manager
 */
export class ConsentReceiptManager {
  private keyPair: SigningKeyPair;

  constructor(keyPair: SigningKeyPair) {
    this.keyPair = keyPair;
  }

  createReceipt(
    memoryId: MemoryId,
    memoryContent: Uint8Array,
    provider: string,
    redactions: Redaction[],
    sensitivityLevel: SensitivityLevel,
    userDecision: UserDecision,
    ruleTriggered: string
  ): SignedConsentReceipt {
    const unsigned = createUnsignedReceipt(
      memoryId,
      memoryContent,
      provider,
      redactions,
      sensitivityLevel,
      userDecision,
      ruleTriggered,
      this.keyPair.publicKey
    );
    return signReceipt(unsigned, this.keyPair.privateKey);
  }

  verify(receipt: SignedConsentReceipt, currentMemoryContent?: Uint8Array): VerificationResult {
    return verifyReceipt(receipt, currentMemoryContent);
  }

  createDenialReceipt(
    memoryId: MemoryId,
    memoryContent: Uint8Array,
    provider: string,
    sensitivityLevel: SensitivityLevel,
    ruleTriggered: string
  ): SignedConsentReceipt {
    return this.createReceipt(memoryId, memoryContent, provider, [], sensitivityLevel, "deny", ruleTriggered);
  }

  createRedactedApprovalReceipt(
    memoryId: MemoryId,
    memoryContent: Uint8Array,
    provider: string,
    redactions: Redaction[],
    sensitivityLevel: SensitivityLevel,
    ruleTriggered: string
  ): SignedConsentReceipt {
    return this.createReceipt(memoryId, memoryContent, provider, redactions, sensitivityLevel, "approve_redacted", ruleTriggered);
  }

  getPublicKey(): Uint8Array {
    return this.keyPair.publicKey;
  }

  getPublicKeyHex(): string {
    return publicKeyToHex(this.keyPair.publicKey);
  }
}

/**
 * Consent Gate - decides whether consent is required
 */
export class ConsentGate {
  private config: ConsentGateConfig;

  constructor(config: Partial<ConsentGateConfig> = {}) {
    this.config = {
      consentRequiredLevels: config.consentRequiredLevels ?? [2, 3],
      rules: config.rules ?? [],
      redactionPatterns: config.redactionPatterns ?? {
        email: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
        phone: /\+?[\d\s\-().]{10,}/g,
        ssn: /\d{3}-\d{2}-\d{4}/g,
        creditCard: /\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}/g,
        ipAddress: /\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}/g,
      },
      autoApproveBasicMemories: config.autoApproveBasicMemories ?? true,
      receiptTtlSeconds: config.receiptTtlSeconds ?? 0,
    };
  }

  evaluate(
    memoryContent: string,
    sensitivityLevel: SensitivityLevel,
    _provider: string
  ): ConsentDecision {
    const triggeredRules: PolicyRule[] = [];
    const suggestedRedactions: Redaction[] = [];

    const consentRequired = this.config.consentRequiredLevels.includes(sensitivityLevel);

    for (const rule of this.config.rules) {
      if (rule.sensitivityThreshold !== undefined && sensitivityLevel >= rule.sensitivityThreshold) {
        triggeredRules.push(rule);
      }
    }

    for (const [entityType, pattern] of Object.entries(this.config.redactionPatterns)) {
      const matches = memoryContent.match(pattern);
      if (matches) {
        for (const _match of matches) {
          suggestedRedactions.push({
            entityType,
            placeholder: `[${entityType.toUpperCase()}]`,
          });
        }
      }
    }

    return {
      consentRequired: consentRequired || triggeredRules.length > 0,
      triggeredRules,
      suggestedRedactions,
      sensitivityLevel,
    };
  }

  applyRedactions(content: string, redactions: Redaction[]): string {
    let redactedContent = content;
    for (const redaction of redactions) {
      const pattern = this.config.redactionPatterns[redaction.entityType];
      if (pattern) {
        redactedContent = redactedContent.replace(pattern, redaction.placeholder);
      }
    }
    return redactedContent;
  }

  addRule(rule: PolicyRule): void {
    this.config.rules.push(rule);
  }

  removeRule(ruleId: string): boolean {
    const index = this.config.rules.findIndex((r) => r.id === ruleId);
    if (index !== -1) {
      this.config.rules.splice(index, 1);
      return true;
    }
    return false;
  }

  getConfig(): ConsentGateConfig {
    return { ...this.config };
  }
}
