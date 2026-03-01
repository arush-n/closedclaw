/**
 * Closedclaw Vault Types
 */

import type { MemoryId, WrappedDEK, SensitivityLevel } from "../crypto/types.js";
import type { SignedConsentReceipt } from "../consent/types.js";

/**
 * Vault-specific audit entry with hash chain (uses hex strings for storage)
 */
export interface VaultAuditEntry {
  /** Unique audit entry identifier */
  id: string;
  /** Action performed */
  action: string;
  /** Timestamp (ISO string) */
  timestamp: string;
  /** Related memory ID */
  memoryId: MemoryId;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
  /** SHA-256 hash of this entry (hex) */
  hash: string;
  /** SHA-256 hash of previous entry (hex, for hash chain) */
  previousHash: string;
  /** Ed25519 signature (hex, optional) */
  signature?: string;
}

/**
 * Memory metadata stored alongside encrypted content
 */
export interface MemoryMetadata {
  memoryId: MemoryId;
  createdAt: Date;
  expiresAt: Date | null;
  provider: string;
  sensitivityLevel: SensitivityLevel;
  tags: string[];
  lastAccessedAt: Date;
  accessCount: number;
  version: number;
}

/**
 * Vault entry combining encrypted memory with metadata
 */
export interface VaultEntry {
  metadata: MemoryMetadata;
  wrappedDEK: WrappedDEK;
  encryptedContent: Uint8Array;
  nonce: Uint8Array;
  authTag: Uint8Array;
  consentReceipt: SignedConsentReceipt | null;
}

/**
 * Vault configuration
 */
export interface VaultConfig {
  defaultTtlSeconds: number;
  maxMemories: number;
  enableAuditLog: boolean;
  auditLogMaxEntries: number;
  autoProcessExpired: boolean;
  processExpiredIntervalMs: number;
}

/**
 * Vault storage backend interface
 */
export interface VaultStorageBackend {
  store(entry: VaultEntry): Promise<void>;
  get(memoryId: MemoryId): Promise<VaultEntry | null>;
  delete(memoryId: MemoryId): Promise<boolean>;
  list(filter?: MemoryFilter): Promise<MemoryMetadata[]>;
  getExpired(now: Date): Promise<MemoryId[]>;
  count(): Promise<number>;
  clear(): Promise<void>;
}

/**
 * Memory filter for listing
 */
export interface MemoryFilter {
  provider?: string;
  sensitivityLevel?: SensitivityLevel;
  tags?: string[];
  createdAfter?: Date;
  createdBefore?: Date;
  expiresAfter?: Date;
  expiresBefore?: Date;
  limit?: number;
  offset?: number;
}

/**
 * Vault statistics
 */
export interface VaultStats {
  totalMemories: number;
  memoriesByProvider: Record<string, number>;
  memoriesBySensitivity: Record<SensitivityLevel, number>;
  expiredCount: number;
  totalSize: number;
  auditLogEntries: number;
}

/**
 * Deletion result
 */
export interface DeletionResult {
  memoryId: MemoryId;
  success: boolean;
  dekDestroyed: boolean;
  contentWiped: boolean;
  auditEntryCreated: boolean;
  error?: string;
}

/**
 * KEK rotation result
 */
export interface KEKRotationResult {
  success: boolean;
  memoriesRewrapped: number;
  failedMemories: MemoryId[];
  rotatedAt: Date;
  auditEntryCreated: boolean;
  error?: string;
}

/**
 * Memory store operation result
 */
export interface StoreResult {
  memoryId: MemoryId;
  success: boolean;
  encrypted: boolean;
  consentReceiptId: string | null;
  error?: string;
}

/**
 * Memory retrieval result
 */
export interface RetrievalResult {
  memoryId: MemoryId;
  success: boolean;
  content: Uint8Array | null;
  metadata: MemoryMetadata | null;
  consentReceipt: SignedConsentReceipt | null;
  error?: string;
}

/**
 * Audit log interface
 */
export interface AuditLog {
  append(entry: Omit<VaultAuditEntry, "hash" | "previousHash">): Promise<VaultAuditEntry>;
  getEntries(from?: number, to?: number): Promise<VaultAuditEntry[]>;
  getLatest(): Promise<VaultAuditEntry | null>;
  verifyChain(): Promise<boolean>;
  getCount(): Promise<number>;
}
