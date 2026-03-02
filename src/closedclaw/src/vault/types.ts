/**
 * Closedclaw Vault Types
 * 
 * Types for the encrypted memory vault with TTL-based cryptographic deletion.
 */

import type {
  MemoryId,
  KeyId,
  EncryptedMemory,
  WrappedDEK,
  AuditEntry,
  AuditEntryType,
  SensitivityLevel,
} from "../crypto/types";

/**
 * Memory metadata (not encrypted)
 */
export interface MemoryMetadata {
  /** Unique memory identifier */
  id: MemoryId;
  /** Creation timestamp */
  createdAt: Date;
  /** Last accessed timestamp */
  lastAccessedAt?: Date;
  /** Sensitivity level (0-3) */
  sensitivityLevel: SensitivityLevel;
  /** Associated DEK ID */
  dekId: KeyId;
  /** Content type (text, json, binary) */
  contentType: "text" | "json" | "binary";
  /** Original size in bytes (before encryption) */
  originalSize: number;
  /** TTL expiry timestamp (if set) */
  expiresAt?: Date;
  /** Tags for organization */
  tags?: string[];
  /** Source of the memory (api, mcp, local) */
  source?: string;
  /** Whether this memory has been deleted (DEK destroyed) */
  deleted: boolean;
  /** Deletion timestamp */
  deletedAt?: Date;
}

/**
 * Vault entry - combines encrypted memory with metadata
 */
export interface VaultEntry {
  /** Memory metadata */
  metadata: MemoryMetadata;
  /** Encrypted memory data */
  encryptedMemory: EncryptedMemory;
  /** Wrapped DEK for this memory */
  wrappedDEK: WrappedDEK;
}

/**
 * Vault entry with decrypted content (for operations)
 */
export interface DecryptedVaultEntry {
  /** Memory metadata */
  metadata: MemoryMetadata;
  /** Decrypted plaintext */
  plaintext: Uint8Array;
  /** Content as string (if text type) */
  text?: string;
  /** Content as JSON (if json type) */
  json?: unknown;
}

/**
 * Deletion result with GDPR compliance info
 */
export interface VaultDeletionResult {
  /** Memory ID deleted */
  memoryId: MemoryId;
  /** DEK ID destroyed */
  dekId: KeyId;
  /** Deletion timestamp */
  deletedAt: Date;
  /** Whether ciphertext is retained (but unrecoverable) */
  ciphertextRetained: boolean;
  /** GDPR Article 17 compliance flag */
  gdprCompliant: boolean;
  /** Audit entry for this deletion */
  auditEntryId: string;
}

/**
 * TTL expiry result
 */
export interface TTLExpiryResult {
  /** Number of memories expired */
  expiredCount: number;
  /** Memory IDs that were deleted */
  deletedMemoryIds: MemoryId[];
  /** Processing timestamp */
  processedAt: Date;
  /** Audit entries generated */
  auditEntries: AuditEntry[];
}

/**
 * Vault configuration
 */
export interface VaultConfig {
  /** Default TTL in seconds (0 = no expiry) */
  defaultTtlSeconds: number;
  /** Retain ciphertext after DEK destruction */
  retainCiphertextOnDelete: boolean;
  /** Enable audit logging */
  enableAudit: boolean;
  /** Sign audit entries with Ed25519 */
  signAuditEntries: boolean;
  /** Use hash chain for audit entries */
  hashChainAudit: boolean;
  /** Auto-process expired entries interval in ms (0 = disabled) */
  autoExpiryIntervalMs: number;
}

/**
 * Default vault configuration
 */
export const DEFAULT_VAULT_CONFIG: VaultConfig = {
  defaultTtlSeconds: 0,
  retainCiphertextOnDelete: true,
  enableAudit: true,
  signAuditEntries: true,
  hashChainAudit: true,
  autoExpiryIntervalMs: 60000, // Check every minute
};

/**
 * Vault statistics
 */
export interface VaultStats {
  /** Total number of entries */
  totalEntries: number;
  /** Number of active (not deleted) entries */
  activeEntries: number;
  /** Number of deleted entries (ciphertext retained) */
  deletedEntries: number;
  /** Number of entries expiring within 24h */
  expiringWithin24h: number;
  /** Total storage size in bytes */
  totalSizeBytes: number;
  /** Breakdown by sensitivity level */
  bySensitivity: Record<SensitivityLevel, number>;
}

/**
 * Vault query options
 */
export interface VaultQuery {
  /** Filter by tags */
  tags?: string[];
  /** Filter by sensitivity level */
  sensitivityLevel?: SensitivityLevel;
  /** Filter by source */
  source?: string;
  /** Include deleted entries */
  includeDeleted?: boolean;
  /** Filter by date range (created) */
  createdAfter?: Date;
  createdBefore?: Date;
  /** Limit results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * Vault storage backend interface
 */
export interface VaultStorageBackend {
  /** Store a vault entry */
  store(entry: VaultEntry): Promise<void>;
  
  /** Retrieve a vault entry by memory ID */
  get(memoryId: MemoryId): Promise<VaultEntry | null>;
  
  /** Query vault entries */
  query(options: VaultQuery): Promise<VaultEntry[]>;
  
  /** Update entry metadata */
  updateMetadata(memoryId: MemoryId, metadata: Partial<MemoryMetadata>): Promise<void>;
  
  /** Mark entry as deleted (but retain ciphertext) */
  markDeleted(memoryId: MemoryId): Promise<void>;
  
  /** Physically remove entry (if not retaining ciphertext) */
  remove(memoryId: MemoryId): Promise<void>;
  
  /** Get entries expiring before a given date */
  getExpiring(before: Date): Promise<VaultEntry[]>;
  
  /** Get statistics */
  getStats(): Promise<VaultStats>;
}

/**
 * Audit trail storage interface
 */
export interface AuditTrailBackend {
  /** Append an audit entry */
  append(entry: AuditEntry): Promise<void>;
  
  /** Get the latest entry (for hash chain) */
  getLatest(): Promise<AuditEntry | null>;
  
  /** Query audit entries */
  query(options: AuditQuery): Promise<AuditEntry[]>;
  
  /** Verify hash chain integrity */
  verifyChain(): Promise<ChainVerificationResult>;
  
  /** Get audit trail for a specific entity */
  getByEntity(entityId: string, entityType: string): Promise<AuditEntry[]>;
}

/**
 * Audit query options
 */
export interface AuditQuery {
  /** Filter by entry type */
  type?: AuditEntryType;
  /** Filter by entity ID */
  entityId?: string;
  /** Filter by entity type */
  entityType?: "memory" | "consent_receipt" | "key" | "policy";
  /** Filter by date range */
  fromDate?: Date;
  toDate?: Date;
  /** Limit results */
  limit?: number;
  /** Offset for pagination */
  offset?: number;
}

/**
 * Hash chain verification result
 */
export interface ChainVerificationResult {
  /** Whether the chain is valid */
  valid: boolean;
  /** Total entries checked */
  entriesChecked: number;
  /** Index of first invalid entry (if any) */
  firstInvalidIndex?: number;
  /** Error message if invalid */
  error?: string;
  /** Verification timestamp */
  verifiedAt: Date;
}
