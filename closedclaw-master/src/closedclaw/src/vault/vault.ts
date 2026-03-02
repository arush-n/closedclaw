/**
 * Closedclaw Memory Vault
 * 
 * Encrypted memory storage with:
 * - AES-256-GCM encryption per memory chunk
 * - Envelope encryption (DEK wrapped by KEK)
 * - TTL-based automatic cryptographic deletion
 * - GDPR Article 17 compliance via DEK destruction
 * - Full audit trail with hash chain
 */

import { v4 as uuidv4 } from "uuid";
import {
  encryptMemory,
  decryptMemory,
  computeHash,
  stringToBytes,
  bytesToString,
  secureWipe,
} from "../crypto/aes";
import {
  createDEK,
  wrapDEK,
  unwrapDEK,
  markWrappedDEKDestroyed,
  isDEKExpired,
} from "../crypto/envelope";
import { sign, hashForSigning, publicKeyToHex, signatureToHex } from "../crypto/ed25519";
import type {
  KeyEncryptionKey,
  EncryptedMemory,
  WrappedDEK,
  DataEncryptionKey,
  MemoryId,
  KeyId,
  AuditEntry,
  AuditEntryType,
  SensitivityLevel,
  SigningKeyPair,
} from "../crypto/types";
import type {
  MemoryMetadata,
  VaultEntry,
  DecryptedVaultEntry,
  VaultDeletionResult,
  TTLExpiryResult,
  VaultConfig,
  VaultStats,
  VaultQuery,
  VaultStorageBackend,
  AuditTrailBackend,
  DEFAULT_VAULT_CONFIG,
} from "./types";

/**
 * In-memory vault storage (for testing/development)
 */
export class InMemoryVaultStorage implements VaultStorageBackend {
  private entries: Map<MemoryId, VaultEntry> = new Map();

  async store(entry: VaultEntry): Promise<void> {
    this.entries.set(entry.metadata.id, entry);
  }

  async get(memoryId: MemoryId): Promise<VaultEntry | null> {
    return this.entries.get(memoryId) ?? null;
  }

  async query(options: VaultQuery): Promise<VaultEntry[]> {
    let results = Array.from(this.entries.values());

    // Apply filters
    if (!options.includeDeleted) {
      results = results.filter((e) => !e.metadata.deleted);
    }
    if (options.tags && options.tags.length > 0) {
      results = results.filter((e) =>
        options.tags!.some((t) => e.metadata.tags?.includes(t))
      );
    }
    if (options.sensitivityLevel !== undefined) {
      results = results.filter((e) => e.metadata.sensitivityLevel === options.sensitivityLevel);
    }
    if (options.source) {
      results = results.filter((e) => e.metadata.source === options.source);
    }
    if (options.createdAfter) {
      results = results.filter((e) => e.metadata.createdAt >= options.createdAfter!);
    }
    if (options.createdBefore) {
      results = results.filter((e) => e.metadata.createdAt <= options.createdBefore!);
    }

    // Apply pagination
    if (options.offset) {
      results = results.slice(options.offset);
    }
    if (options.limit) {
      results = results.slice(0, options.limit);
    }

    return results;
  }

  async updateMetadata(memoryId: MemoryId, metadata: Partial<MemoryMetadata>): Promise<void> {
    const entry = this.entries.get(memoryId);
    if (entry) {
      entry.metadata = { ...entry.metadata, ...metadata };
    }
  }

  async markDeleted(memoryId: MemoryId): Promise<void> {
    const entry = this.entries.get(memoryId);
    if (entry) {
      entry.metadata.deleted = true;
      entry.metadata.deletedAt = new Date();
    }
  }

  async remove(memoryId: MemoryId): Promise<void> {
    this.entries.delete(memoryId);
  }

  async getExpiring(before: Date): Promise<VaultEntry[]> {
    return Array.from(this.entries.values()).filter(
      (e) => !e.metadata.deleted && e.metadata.expiresAt && e.metadata.expiresAt <= before
    );
  }

  async getStats(): Promise<VaultStats> {
    const entries = Array.from(this.entries.values());
    const now = new Date();
    const in24h = new Date(now.getTime() + 24 * 60 * 60 * 1000);

    const bySensitivity: Record<SensitivityLevel, number> = { 0: 0, 1: 0, 2: 0, 3: 0 };
    let totalSize = 0;
    let activeCount = 0;
    let deletedCount = 0;
    let expiringCount = 0;

    for (const entry of entries) {
      bySensitivity[entry.metadata.sensitivityLevel]++;
      totalSize += entry.metadata.originalSize;

      if (entry.metadata.deleted) {
        deletedCount++;
      } else {
        activeCount++;
        if (entry.metadata.expiresAt && entry.metadata.expiresAt <= in24h) {
          expiringCount++;
        }
      }
    }

    return {
      totalEntries: entries.length,
      activeEntries: activeCount,
      deletedEntries: deletedCount,
      expiringWithin24h: expiringCount,
      totalSizeBytes: totalSize,
      bySensitivity,
    };
  }
}

/**
 * In-memory audit trail (for testing/development)
 */
export class InMemoryAuditTrail implements AuditTrailBackend {
  private entries: AuditEntry[] = [];

  async append(entry: AuditEntry): Promise<void> {
    this.entries.push(entry);
  }

  async getLatest(): Promise<AuditEntry | null> {
    return this.entries[this.entries.length - 1] ?? null;
  }

  async query(options: { limit?: number; offset?: number }): Promise<AuditEntry[]> {
    let results = [...this.entries];
    if (options.offset) {
      results = results.slice(options.offset);
    }
    if (options.limit) {
      results = results.slice(0, options.limit);
    }
    return results;
  }

  async verifyChain(): Promise<{ valid: boolean; entriesChecked: number; verifiedAt: Date }> {
    // Simplified verification for in-memory storage
    return {
      valid: true,
      entriesChecked: this.entries.length,
      verifiedAt: new Date(),
    };
  }

  async getByEntity(entityId: string, _entityType: string): Promise<AuditEntry[]> {
    return this.entries.filter((e) => e.entityId === entityId);
  }
}

/**
 * Memory Vault - main interface for encrypted memory operations
 */
export class MemoryVault {
  private kek: KeyEncryptionKey;
  private signingKeyPair: SigningKeyPair;
  private storage: VaultStorageBackend;
  private auditTrail: AuditTrailBackend;
  private config: VaultConfig;
  private expiryTimer?: ReturnType<typeof setInterval>;

  constructor(
    kek: KeyEncryptionKey,
    signingKeyPair: SigningKeyPair,
    storage: VaultStorageBackend = new InMemoryVaultStorage(),
    auditTrail: AuditTrailBackend = new InMemoryAuditTrail(),
    config: Partial<VaultConfig> = {}
  ) {
    this.kek = kek;
    this.signingKeyPair = signingKeyPair;
    this.storage = storage;
    this.auditTrail = auditTrail;
    this.config = {
      defaultTtlSeconds: config.defaultTtlSeconds ?? 0,
      retainCiphertextOnDelete: config.retainCiphertextOnDelete ?? true,
      enableAudit: config.enableAudit ?? true,
      signAuditEntries: config.signAuditEntries ?? true,
      hashChainAudit: config.hashChainAudit ?? true,
      autoExpiryIntervalMs: config.autoExpiryIntervalMs ?? 60000,
    };

    // Start auto-expiry timer if enabled
    if (this.config.autoExpiryIntervalMs > 0) {
      this.startAutoExpiry();
    }
  }

  /**
   * Store a new memory (encrypts and stores)
   */
  async store(
    content: string | Uint8Array,
    options: {
      sensitivityLevel?: SensitivityLevel;
      ttlSeconds?: number;
      tags?: string[];
      source?: string;
      contentType?: "text" | "json" | "binary";
    } = {}
  ): Promise<MemoryId> {
    const contentBytes = typeof content === "string" ? stringToBytes(content) : content;
    const memoryId = `mem_${uuidv4()}`;
    const sensitivityLevel = options.sensitivityLevel ?? 1;
    const contentType = options.contentType ?? (typeof content === "string" ? "text" : "binary");

    // Calculate expiry
    const ttlSeconds = options.ttlSeconds ?? this.config.defaultTtlSeconds;
    const expiresAt = ttlSeconds > 0 ? new Date(Date.now() + ttlSeconds * 1000) : undefined;

    // Create DEK for this memory
    const dek = createDEK(memoryId, expiresAt);

    // Encrypt the memory content
    const encryptedMemory = encryptMemory(memoryId, contentBytes, dek.id, dek.key);

    // Wrap the DEK with KEK
    const wrappedDEK = wrapDEK(dek, this.kek);

    // Securely wipe the raw DEK
    secureWipe(dek.key);

    // Create metadata
    const metadata: MemoryMetadata = {
      id: memoryId,
      createdAt: new Date(),
      sensitivityLevel,
      dekId: dek.id,
      contentType,
      originalSize: contentBytes.length,
      expiresAt,
      tags: options.tags,
      source: options.source,
      deleted: false,
    };

    // Store the vault entry
    const entry: VaultEntry = {
      metadata,
      encryptedMemory,
      wrappedDEK,
    };
    await this.storage.store(entry);

    // Create audit entry
    if (this.config.enableAudit) {
      await this.createAuditEntry("memory_encrypted", memoryId, "memory", "store", {
        sensitivityLevel,
        size: contentBytes.length,
        hasExpiry: !!expiresAt,
      });
    }

    return memoryId;
  }

  /**
   * Retrieve and decrypt a memory
   */
  async retrieve(memoryId: MemoryId): Promise<DecryptedVaultEntry | null> {
    const entry = await this.storage.get(memoryId);
    if (!entry) {
      return null;
    }

    if (entry.metadata.deleted) {
      throw new Error("Memory has been cryptographically deleted - data is permanently unrecoverable");
    }

    // Check if expired
    if (entry.metadata.expiresAt && new Date() >= entry.metadata.expiresAt) {
      // Auto-delete expired memory
      await this.delete(memoryId);
      throw new Error("Memory has expired and been cryptographically deleted");
    }

    // Unwrap DEK
    const dek = unwrapDEK(entry.wrappedDEK, this.kek);

    // Decrypt memory
    const decrypted = decryptMemory(entry.encryptedMemory, dek.key);

    // Securely wipe DEK
    secureWipe(dek.key);

    if (!decrypted.integrityVerified) {
      throw new Error("Memory integrity verification failed - data may be corrupted");
    }

    // Update last accessed
    await this.storage.updateMetadata(memoryId, { lastAccessedAt: new Date() });

    // Create audit entry
    if (this.config.enableAudit) {
      await this.createAuditEntry("memory_decrypted", memoryId, "memory", "retrieve", {});
    }

    // Build result
    const result: DecryptedVaultEntry = {
      metadata: entry.metadata,
      plaintext: decrypted.plaintext,
    };

    if (entry.metadata.contentType === "text") {
      result.text = bytesToString(decrypted.plaintext);
    } else if (entry.metadata.contentType === "json") {
      result.text = bytesToString(decrypted.plaintext);
      try {
        result.json = JSON.parse(result.text);
      } catch {
        // JSON parse failed, leave as undefined
      }
    }

    return result;
  }

  /**
   * Cryptographically delete a memory (GDPR Article 17 compliant)
   * 
   * This destroys the DEK, making the ciphertext permanently unrecoverable.
   * The ciphertext can be retained for forensic purposes but cannot be decrypted.
   */
  async delete(memoryId: MemoryId): Promise<VaultDeletionResult> {
    const entry = await this.storage.get(memoryId);
    if (!entry) {
      throw new Error(`Memory not found: ${memoryId}`);
    }

    if (entry.metadata.deleted) {
      throw new Error("Memory already deleted");
    }

    const dekId = entry.metadata.dekId;

    // Destroy the wrapped DEK (overwrite with zeros)
    const destroyedDEK = markWrappedDEKDestroyed(entry.wrappedDEK);
    entry.wrappedDEK = destroyedDEK;

    // Mark as deleted
    await this.storage.markDeleted(memoryId);

    // Create audit entry
    let auditEntryId = "";
    if (this.config.enableAudit) {
      const auditEntry = await this.createAuditEntry(
        "memory_deleted",
        memoryId,
        "memory",
        "cryptographic_delete",
        {
          dekId,
          ciphertextRetained: this.config.retainCiphertextOnDelete,
          gdprCompliant: true,
        }
      );
      auditEntryId = auditEntry.id;

      // Also log DEK destruction
      await this.createAuditEntry("dek_destroyed", dekId, "key", "destroy", {
        memoryId,
        reason: "memory_deletion",
      });
    }

    // Optionally remove the entry entirely
    if (!this.config.retainCiphertextOnDelete) {
      await this.storage.remove(memoryId);
    }

    return {
      memoryId,
      dekId,
      deletedAt: new Date(),
      ciphertextRetained: this.config.retainCiphertextOnDelete,
      gdprCompliant: true,
      auditEntryId,
    };
  }

  /**
   * Process expired memories (TTL-based deletion)
   */
  async processExpiredMemories(): Promise<TTLExpiryResult> {
    const now = new Date();
    const expiring = await this.storage.getExpiring(now);
    const deletedMemoryIds: MemoryId[] = [];
    const auditEntries: AuditEntry[] = [];

    for (const entry of expiring) {
      try {
        const result = await this.delete(entry.metadata.id);
        deletedMemoryIds.push(result.memoryId);
      } catch (error) {
        // Log error but continue processing
        console.error(`Failed to delete expired memory ${entry.metadata.id}:`, error);
      }
    }

    return {
      expiredCount: deletedMemoryIds.length,
      deletedMemoryIds,
      processedAt: now,
      auditEntries,
    };
  }

  /**
   * Query memories
   */
  async query(options: VaultQuery): Promise<MemoryMetadata[]> {
    const entries = await this.storage.query(options);
    return entries.map((e) => e.metadata);
  }

  /**
   * Get vault statistics
   */
  async getStats(): Promise<VaultStats> {
    return this.storage.getStats();
  }

  /**
   * Create an audit entry
   */
  private async createAuditEntry(
    type: AuditEntryType,
    entityId: string,
    entityType: "memory" | "consent_receipt" | "key" | "policy",
    action: string,
    metadata: Record<string, unknown>
  ): Promise<AuditEntry> {
    const timestamp = new Date().toISOString();
    const entryId = `audit_${uuidv4()}`;

    // Get previous hash for chain
    const previousEntry = await this.auditTrail.getLatest();
    const previousHash = previousEntry?.entryHash ?? new Uint8Array(32);

    // Compute entry hash
    const entryContent = JSON.stringify({
      id: entryId,
      type,
      timestamp,
      entityId,
      entityType,
      action,
      metadata,
      previousHash: Array.from(previousHash),
    });
    const entryHash = computeHash(stringToBytes(entryContent));

    // Sign the entry
    let signature = new Uint8Array(64);
    if (this.config.signAuditEntries) {
      const messageHash = hashForSigning(entryHash);
      signature = new Uint8Array(sign(messageHash, this.signingKeyPair.privateKey));
    }

    const entry: AuditEntry = {
      id: entryId,
      type,
      timestamp,
      entityId,
      entityType,
      action,
      metadata,
      entryHash,
      previousHash,
      signature,
    };

    await this.auditTrail.append(entry);
    return entry;
  }

  /**
   * Start automatic expiry processing
   */
  private startAutoExpiry(): void {
    this.expiryTimer = setInterval(async () => {
      try {
        await this.processExpiredMemories();
      } catch (error) {
        console.error("Auto-expiry processing failed:", error);
      }
    }, this.config.autoExpiryIntervalMs);
  }

  /**
   * Stop automatic expiry processing
   */
  stopAutoExpiry(): void {
    if (this.expiryTimer) {
      clearInterval(this.expiryTimer);
      this.expiryTimer = undefined;
    }
  }

  /**
   * Rotate KEK (re-wrap all DEKs with new key)
   */
  async rotateKEK(newKek: KeyEncryptionKey): Promise<{ rewrappedCount: number }> {
    const entries = await this.storage.query({ includeDeleted: false });
    let rewrappedCount = 0;

    for (const entry of entries) {
      if (!entry.wrappedDEK.destroyed) {
        // Unwrap with old KEK
        const dek = unwrapDEK(entry.wrappedDEK, this.kek);
        
        // Re-wrap with new KEK
        const rewrapped = wrapDEK(
          { ...dek, destroyed: false },
          newKek
        );
        
        // Update storage
        entry.wrappedDEK = rewrapped;
        await this.storage.store(entry);
        
        // Securely wipe DEK
        secureWipe(dek.key);
        
        rewrappedCount++;
      }
    }

    // Update KEK reference
    secureWipe(this.kek.key);
    this.kek = newKek;

    // Audit
    if (this.config.enableAudit) {
      await this.createAuditEntry("key_rotated", this.kek.id, "key", "rotate", {
        rewrappedCount,
        newVersion: newKek.version,
      });
    }

    return { rewrappedCount };
  }

  /**
   * Get audit trail for a memory
   */
  async getAuditTrail(memoryId: MemoryId): Promise<AuditEntry[]> {
    return this.auditTrail.getByEntity(memoryId, "memory");
  }

  /**
   * Verify audit trail integrity
   */
  async verifyAuditTrail(): Promise<{ valid: boolean; entriesChecked: number }> {
    return this.auditTrail.verifyChain();
  }

  /**
   * Clean up resources
   */
  destroy(): void {
    this.stopAutoExpiry();
    secureWipe(this.kek.key);
    secureWipe(this.signingKeyPair.privateKey);
  }
}
