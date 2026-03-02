/**
 * Closedclaw Memory Vault
 */

import { v4 as uuidv4 } from "uuid";
import { encryptAES256GCM, decryptAES256GCM, generateNonce, secureWipe, computeHash, hashToHex } from "../crypto/aes.js";
import { DEKManager, markWrappedDEKDestroyed } from "../crypto/envelope.js";
import { sign, hashForSigning, signatureToHex } from "../crypto/ed25519.js";
import type { KeyEncryptionKey, MemoryId, SigningKeyPair, SensitivityLevel } from "../crypto/types.js";
import type { SignedConsentReceipt } from "../consent/types.js";
import type {
  MemoryMetadata,
  VaultEntry,
  VaultConfig,
  VaultStorageBackend,
  MemoryFilter,
  VaultStats,
  DeletionResult,
  KEKRotationResult,
  StoreResult,
  RetrievalResult,
  AuditLog,
  VaultAuditEntry,
} from "./types.js";

/**
 * In-memory storage backend
 */
export class InMemoryStorage implements VaultStorageBackend {
  private entries: Map<MemoryId, VaultEntry> = new Map();

  async store(entry: VaultEntry): Promise<void> {
    this.entries.set(entry.metadata.memoryId, entry);
  }

  async get(memoryId: MemoryId): Promise<VaultEntry | null> {
    return this.entries.get(memoryId) ?? null;
  }

  async delete(memoryId: MemoryId): Promise<boolean> {
    return this.entries.delete(memoryId);
  }

  async list(filter?: MemoryFilter): Promise<MemoryMetadata[]> {
    let results = Array.from(this.entries.values()).map((e) => e.metadata);

    if (filter) {
      if (filter.provider) {
        results = results.filter((m) => m.provider === filter.provider);
      }
      if (filter.sensitivityLevel !== undefined) {
        results = results.filter((m) => m.sensitivityLevel === filter.sensitivityLevel);
      }
      if (filter.tags && filter.tags.length > 0) {
        results = results.filter((m) => filter.tags!.some((t) => m.tags.includes(t)));
      }
      if (filter.createdAfter) {
        results = results.filter((m) => m.createdAt >= filter.createdAfter!);
      }
      if (filter.createdBefore) {
        results = results.filter((m) => m.createdAt <= filter.createdBefore!);
      }
      if (filter.offset) {
        results = results.slice(filter.offset);
      }
      if (filter.limit) {
        results = results.slice(0, filter.limit);
      }
    }

    return results;
  }

  async getExpired(now: Date): Promise<MemoryId[]> {
    const expired: MemoryId[] = [];
    for (const [memoryId, entry] of this.entries) {
      if (entry.metadata.expiresAt && entry.metadata.expiresAt <= now) {
        expired.push(memoryId);
      }
    }
    return expired;
  }

  async count(): Promise<number> {
    return this.entries.size;
  }

  async clear(): Promise<void> {
    for (const entry of this.entries.values()) {
      secureWipe(entry.encryptedContent);
      secureWipe(entry.nonce);
      secureWipe(entry.authTag);
    }
    this.entries.clear();
  }
}

/**
 * In-memory audit log with hash chain
 */
export class InMemoryAuditLog implements AuditLog {
  private entries: VaultAuditEntry[] = [];
  private signingKey: Uint8Array | null;

  constructor(signingKey?: Uint8Array) {
    this.signingKey = signingKey ?? null;
  }

  async append(entry: Omit<VaultAuditEntry, "hash" | "previousHash">): Promise<VaultAuditEntry> {
    const previousHash = this.entries.length > 0
      ? this.entries[this.entries.length - 1].hash
      : "0".repeat(64);

    const hashInput = JSON.stringify({
      ...entry,
      previousHash,
    });
    const hashBytes = computeHash(new TextEncoder().encode(hashInput));
    const hash = hashToHex(hashBytes);

    let signature: string | undefined;
    if (this.signingKey) {
      const signatureBytes = sign(hashForSigning(hashBytes), this.signingKey);
      signature = signatureToHex(signatureBytes);
    }

    const fullEntry: VaultAuditEntry = {
      ...entry,
      hash,
      previousHash,
      signature,
    };

    this.entries.push(fullEntry);
    return fullEntry;
  }

  async getEntries(from?: number, to?: number): Promise<VaultAuditEntry[]> {
    return this.entries.slice(from ?? 0, to);
  }

  async getLatest(): Promise<VaultAuditEntry | null> {
    return this.entries.length > 0 ? this.entries[this.entries.length - 1] : null;
  }

  async verifyChain(): Promise<boolean> {
    if (this.entries.length === 0) return true;

    for (let i = 0; i < this.entries.length; i++) {
      const entry = this.entries[i];
      const expectedPrevHash = i === 0 ? "0".repeat(64) : this.entries[i - 1].hash;

      if (entry.previousHash !== expectedPrevHash) {
        return false;
      }

      const hashInput = JSON.stringify({
        id: entry.id,
        action: entry.action,
        timestamp: entry.timestamp,
        memoryId: entry.memoryId,
        metadata: entry.metadata,
        previousHash: entry.previousHash,
      });
      const computedHash = hashToHex(computeHash(new TextEncoder().encode(hashInput)));

      if (computedHash !== entry.hash) {
        return false;
      }
    }

    return true;
  }

  async getCount(): Promise<number> {
    return this.entries.length;
  }
}

/**
 * Memory Vault - main encrypted memory storage
 */
export class MemoryVault {
  private storage: VaultStorageBackend;
  private dekManager: DEKManager;
  private auditLog: AuditLog | null;
  private config: VaultConfig;
  private expirationTimer: ReturnType<typeof setInterval> | null = null;

  constructor(
    kek: KeyEncryptionKey,
    config: Partial<VaultConfig> = {},
    signingKeyPair?: SigningKeyPair,
    storage?: VaultStorageBackend,
    auditLog?: AuditLog
  ) {
    this.config = {
      defaultTtlSeconds: config.defaultTtlSeconds ?? 86400 * 30,
      maxMemories: config.maxMemories ?? 10000,
      enableAuditLog: config.enableAuditLog ?? true,
      auditLogMaxEntries: config.auditLogMaxEntries ?? 100000,
      autoProcessExpired: config.autoProcessExpired ?? true,
      processExpiredIntervalMs: config.processExpiredIntervalMs ?? 60000,
    };

    this.dekManager = new DEKManager(kek);
    this.storage = storage ?? new InMemoryStorage();
    this.auditLog = auditLog ?? (this.config.enableAuditLog
      ? new InMemoryAuditLog(signingKeyPair?.privateKey)
      : null);

    if (this.config.autoProcessExpired) {
      this.startExpirationProcessor();
    }
  }

  /**
   * Store encrypted memory
   */
  async store(
    content: Uint8Array,
    provider: string,
    sensitivityLevel: SensitivityLevel,
    consentReceipt: SignedConsentReceipt | null,
    options: {
      memoryId?: MemoryId;
      ttlSeconds?: number;
      tags?: string[];
    } = {}
  ): Promise<StoreResult> {
    const memoryId = options.memoryId ?? uuidv4();
    const now = new Date();
    const ttl = options.ttlSeconds ?? this.config.defaultTtlSeconds;
    // ttl > 0: expires in the future; ttl < 0: already expired (for testing); ttl === 0: never expires
    const expiresAt = ttl !== 0 ? new Date(now.getTime() + ttl * 1000) : null;

    try {
      const wrappedDEK = this.dekManager.createAndWrap(memoryId);
      const dek = this.dekManager.unwrap(wrappedDEK);
      const nonce = generateNonce();
      const encrypted = encryptAES256GCM(content, dek.key, nonce);
      secureWipe(dek.key);

      const metadata: MemoryMetadata = {
        memoryId,
        createdAt: now,
        expiresAt,
        provider,
        sensitivityLevel,
        tags: options.tags ?? [],
        lastAccessedAt: now,
        accessCount: 0,
        version: 1,
      };

      const entry: VaultEntry = {
        metadata,
        wrappedDEK,
        encryptedContent: encrypted.ciphertext,
        nonce,
        authTag: encrypted.authTag,
        consentReceipt,
      };

      await this.storage.store(entry);

      if (this.auditLog) {
        await this.auditLog.append({
          id: uuidv4(),
          action: "store",
          timestamp: now.toISOString(),
          memoryId,
          metadata: {
            provider,
            sensitivityLevel,
            hasConsent: consentReceipt !== null,
            ttlSeconds: ttl,
          },
        });
      }

      return {
        memoryId,
        success: true,
        encrypted: true,
        consentReceiptId: consentReceipt?.receiptId ?? null,
      };
    } catch (error) {
      return {
        memoryId,
        success: false,
        encrypted: false,
        consentReceiptId: null,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  /**
   * Retrieve and decrypt memory
   */
  async retrieve(memoryId: MemoryId): Promise<RetrievalResult> {
    try {
      const entry = await this.storage.get(memoryId);

      if (!entry) {
        return {
          memoryId,
          success: false,
          content: null,
          metadata: null,
          consentReceipt: null,
          error: "Memory not found",
        };
      }

      if (entry.metadata.expiresAt && entry.metadata.expiresAt <= new Date()) {
        await this.cryptographicDelete(memoryId);
        return {
          memoryId,
          success: false,
          content: null,
          metadata: null,
          consentReceipt: null,
          error: "Memory expired",
        };
      }

      const dek = this.dekManager.unwrap(entry.wrappedDEK);
      const decrypted = decryptAES256GCM(
        entry.encryptedContent,
        entry.authTag,
        dek.key,
        entry.nonce
      );
      secureWipe(dek.key);

      entry.metadata.lastAccessedAt = new Date();
      entry.metadata.accessCount++;
      await this.storage.store(entry);

      if (this.auditLog) {
        await this.auditLog.append({
          id: uuidv4(),
          action: "retrieve",
          timestamp: new Date().toISOString(),
          memoryId,
          metadata: {
            accessCount: entry.metadata.accessCount,
          },
        });
      }

      return {
        memoryId,
        success: true,
        content: decrypted,
        metadata: entry.metadata,
        consentReceipt: entry.consentReceipt,
      };
    } catch (error) {
      return {
        memoryId,
        success: false,
        content: null,
        metadata: null,
        consentReceipt: null,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  /**
   * Cryptographically delete memory (GDPR Article 17)
   */
  async cryptographicDelete(memoryId: MemoryId): Promise<DeletionResult> {
    try {
      const entry = await this.storage.get(memoryId);

      if (!entry) {
        return {
          memoryId,
          success: false,
          dekDestroyed: false,
          contentWiped: false,
          auditEntryCreated: false,
          error: "Memory not found",
        };
      }

      secureWipe(entry.encryptedContent);
      secureWipe(entry.nonce);
      secureWipe(entry.authTag);
      const contentWiped = true;

      const destroyedDEK = markWrappedDEKDestroyed(entry.wrappedDEK);
      secureWipe(destroyedDEK.encryptedKey);
      const dekDestroyed = true;

      await this.storage.delete(memoryId);

      let auditEntryCreated = false;
      if (this.auditLog) {
        await this.auditLog.append({
          id: uuidv4(),
          action: "delete",
          timestamp: new Date().toISOString(),
          memoryId,
          metadata: {
            provider: entry.metadata.provider,
            sensitivityLevel: entry.metadata.sensitivityLevel,
            originalCreatedAt: entry.metadata.createdAt.toISOString(),
            dekDestroyed: true,
            contentWiped: true,
          },
        });
        auditEntryCreated = true;
      }

      return {
        memoryId,
        success: true,
        dekDestroyed,
        contentWiped,
        auditEntryCreated,
      };
    } catch (error) {
      return {
        memoryId,
        success: false,
        dekDestroyed: false,
        contentWiped: false,
        auditEntryCreated: false,
        error: error instanceof Error ? error.message : "Unknown error",
      };
    }
  }

  /**
   * Process all expired memories
   */
  async processExpiredMemories(): Promise<DeletionResult[]> {
    const expired = await this.storage.getExpired(new Date());
    const results: DeletionResult[] = [];

    for (const memoryId of expired) {
      const result = await this.cryptographicDelete(memoryId);
      results.push(result);
    }

    return results;
  }

  /**
   * Rotate KEK and re-wrap all DEKs
   */
  async rotateKEK(newKEK: KeyEncryptionKey): Promise<KEKRotationResult> {
    const allMetadata = await this.storage.list();
    const failedMemories: MemoryId[] = [];
    let memoriesRewrapped = 0;

    for (const metadata of allMetadata) {
      try {
        const entry = await this.storage.get(metadata.memoryId);
        if (!entry) continue;

        const unwrappedDEK = this.dekManager.unwrap(entry.wrappedDEK);
        const newWrappedDEK = this.dekManager.rewrapWithNewKEK(entry.wrappedDEK, newKEK);

        entry.wrappedDEK = newWrappedDEK;
        entry.metadata.version++;
        await this.storage.store(entry);

        secureWipe(unwrappedDEK.key);
        memoriesRewrapped++;
      } catch {
        failedMemories.push(metadata.memoryId);
      }
    }

    this.dekManager = new DEKManager(newKEK);

    let auditEntryCreated = false;
    if (this.auditLog) {
      await this.auditLog.append({
        id: uuidv4(),
        action: "kek_rotation",
        timestamp: new Date().toISOString(),
        memoryId: "system",
        metadata: {
          memoriesRewrapped,
          failedMemories: failedMemories.length,
        },
      });
      auditEntryCreated = true;
    }

    return {
      success: failedMemories.length === 0,
      memoriesRewrapped,
      failedMemories,
      rotatedAt: new Date(),
      auditEntryCreated,
    };
  }

  /**
   * Get vault statistics
   */
  async getStats(): Promise<VaultStats> {
    const allMetadata = await this.storage.list();
    const memoriesByProvider: Record<string, number> = {};
    const memoriesBySensitivity: Record<SensitivityLevel, number> = { 0: 0, 1: 0, 2: 0, 3: 0 };
    const now = new Date();
    let expiredCount = 0;

    for (const metadata of allMetadata) {
      memoriesByProvider[metadata.provider] = (memoriesByProvider[metadata.provider] ?? 0) + 1;
      memoriesBySensitivity[metadata.sensitivityLevel]++;

      if (metadata.expiresAt && metadata.expiresAt <= now) {
        expiredCount++;
      }
    }

    return {
      totalMemories: allMetadata.length,
      memoriesByProvider,
      memoriesBySensitivity,
      expiredCount,
      totalSize: 0,
      auditLogEntries: this.auditLog ? await this.auditLog.getCount() : 0,
    };
  }

  /**
   * Search memories by filter
   */
  async search(filter: MemoryFilter): Promise<MemoryMetadata[]> {
    return this.storage.list(filter);
  }

  /**
   * Get audit log entries
   */
  async getAuditLog(from?: number, to?: number): Promise<VaultAuditEntry[]> {
    if (!this.auditLog) return [];
    return this.auditLog.getEntries(from, to);
  }

  /**
   * Verify audit log integrity
   */
  async verifyAuditLog(): Promise<boolean> {
    if (!this.auditLog) return true;
    return this.auditLog.verifyChain();
  }

  /**
   * Start automatic expiration processor
   */
  private startExpirationProcessor(): void {
    this.expirationTimer = setInterval(
      () => this.processExpiredMemories(),
      this.config.processExpiredIntervalMs
    );
  }

  /**
   * Stop automatic expiration processor
   */
  stopExpirationProcessor(): void {
    if (this.expirationTimer) {
      clearInterval(this.expirationTimer);
      this.expirationTimer = null;
    }
  }

  /**
   * Clear all data
   */
  async clear(): Promise<void> {
    this.stopExpirationProcessor();
    await this.storage.clear();
  }
}
