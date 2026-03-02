/**
 * Vault tests
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  MemoryVault,
  InMemoryStorage,
  InMemoryAuditLog,
} from "../src/vault/vault.js";
import { generateKey, generateKeyPair } from "../src/index.js";
import type { KeyEncryptionKey, SigningKeyPair } from "../src/crypto/types.js";

describe("MemoryVault", () => {
  let kek: KeyEncryptionKey;
  let signingKeyPair: SigningKeyPair;
  let vault: MemoryVault;

  beforeEach(() => {
    kek = {
      id: "test-kek",
      key: generateKey(),
      createdAt: new Date(),
      version: 1,
      rotatedAt: null,
    };
    signingKeyPair = generateKeyPair();
    vault = new MemoryVault(kek, { autoProcessExpired: false }, signingKeyPair);
  });

  afterEach(async () => {
    vault.stopExpirationProcessor();
    await vault.clear();
  });

  describe("Store and Retrieve", () => {
    it("should store and retrieve memory", async () => {
      const content = new TextEncoder().encode("Test memory content");
      const storeResult = await vault.store(content, "test-provider", 1, null);

      expect(storeResult.success).toBe(true);
      expect(storeResult.encrypted).toBe(true);
      expect(storeResult.memoryId).toBeDefined();

      const retrieveResult = await vault.retrieve(storeResult.memoryId);
      expect(retrieveResult.success).toBe(true);
      expect(retrieveResult.content).toEqual(content);
      expect(retrieveResult.metadata?.provider).toBe("test-provider");
    });

    it("should return error for non-existent memory", async () => {
      const result = await vault.retrieve("non-existent-id");
      expect(result.success).toBe(false);
      expect(result.error).toBe("Memory not found");
    });

    it("should store with custom tags", async () => {
      const content = new TextEncoder().encode("Tagged content");
      const result = await vault.store(content, "provider", 1, null, {
        tags: ["important", "work"],
      });

      const retrieved = await vault.retrieve(result.memoryId);
      expect(retrieved.metadata?.tags).toEqual(["important", "work"]);
    });

    it("should track access count", async () => {
      const content = new TextEncoder().encode("Count test");
      const { memoryId } = await vault.store(content, "provider", 1, null);

      await vault.retrieve(memoryId);
      await vault.retrieve(memoryId);
      const result = await vault.retrieve(memoryId);

      expect(result.metadata?.accessCount).toBe(3);
    });
  });

  describe("Cryptographic Deletion", () => {
    it("should cryptographically delete memory", async () => {
      const content = new TextEncoder().encode("To be deleted");
      const { memoryId } = await vault.store(content, "provider", 2, null);

      const deleteResult = await vault.cryptographicDelete(memoryId);
      expect(deleteResult.success).toBe(true);
      expect(deleteResult.dekDestroyed).toBe(true);
      expect(deleteResult.contentWiped).toBe(true);
      expect(deleteResult.auditEntryCreated).toBe(true);

      const retrieveResult = await vault.retrieve(memoryId);
      expect(retrieveResult.success).toBe(false);
      expect(retrieveResult.error).toBe("Memory not found");
    });

    it("should return error when deleting non-existent memory", async () => {
      const result = await vault.cryptographicDelete("non-existent");
      expect(result.success).toBe(false);
      expect(result.error).toBe("Memory not found");
    });
  });

  describe("TTL Expiration", () => {
    it("should expire memory after TTL", async () => {
      const content = new TextEncoder().encode("Expiring content");
      const { memoryId } = await vault.store(content, "provider", 1, null, {
        ttlSeconds: -1,
      });

      const result = await vault.retrieve(memoryId);
      expect(result.success).toBe(false);
      expect(result.error).toBe("Memory expired");
    });

    it("should process expired memories", async () => {
      await vault.store(new TextEncoder().encode("Expired 1"), "p", 1, null, { ttlSeconds: -1 });
      await vault.store(new TextEncoder().encode("Expired 2"), "p", 1, null, { ttlSeconds: -1 });
      await vault.store(new TextEncoder().encode("Valid"), "p", 1, null, { ttlSeconds: 3600 });

      const results = await vault.processExpiredMemories();
      expect(results.length).toBe(2);
      expect(results.every((r) => r.success)).toBe(true);

      const stats = await vault.getStats();
      expect(stats.totalMemories).toBe(1);
    });

    it("should not expire memory with null TTL", async () => {
      const content = new TextEncoder().encode("No expiration");
      const { memoryId } = await vault.store(content, "provider", 1, null, {
        ttlSeconds: 0,
      });

      const result = await vault.retrieve(memoryId);
      expect(result.success).toBe(true);
      expect(result.metadata?.expiresAt).toBeNull();
    });
  });

  describe("KEK Rotation", () => {
    it("should rotate KEK and rewrap all DEKs", async () => {
      await vault.store(new TextEncoder().encode("Memory 1"), "p", 1, null);
      await vault.store(new TextEncoder().encode("Memory 2"), "p", 1, null);

      const newKek: KeyEncryptionKey = {
        id: "new-kek",
        key: generateKey(),
        createdAt: new Date(),
        version: 2,
        rotatedAt: null,
      };

      const result = await vault.rotateKEK(newKek);
      expect(result.success).toBe(true);
      expect(result.memoriesRewrapped).toBe(2);
      expect(result.failedMemories.length).toBe(0);

      const retrieveResult = await vault.retrieve(
        (await vault.search({}))[0].memoryId
      );
      expect(retrieveResult.success).toBe(true);
    });
  });

  describe("Audit Log", () => {
    it("should create audit entries for operations", async () => {
      const content = new TextEncoder().encode("Audited content");
      const { memoryId } = await vault.store(content, "provider", 1, null);
      await vault.retrieve(memoryId);
      await vault.cryptographicDelete(memoryId);

      const auditLog = await vault.getAuditLog();
      expect(auditLog.length).toBe(3);
      expect(auditLog[0].action).toBe("store");
      expect(auditLog[1].action).toBe("retrieve");
      expect(auditLog[2].action).toBe("delete");
    });

    it("should verify audit log chain integrity", async () => {
      await vault.store(new TextEncoder().encode("Entry 1"), "p", 1, null);
      await vault.store(new TextEncoder().encode("Entry 2"), "p", 1, null);

      const valid = await vault.verifyAuditLog();
      expect(valid).toBe(true);
    });

    it("should include hash chain in audit entries", async () => {
      await vault.store(new TextEncoder().encode("Test"), "p", 1, null);
      await vault.store(new TextEncoder().encode("Test 2"), "p", 1, null);

      const auditLog = await vault.getAuditLog();
      expect(auditLog[0].previousHash).toBe("0".repeat(64));
      expect(auditLog[1].previousHash).toBe(auditLog[0].hash);
    });
  });

  describe("Statistics", () => {
    it("should return vault statistics", async () => {
      await vault.store(new TextEncoder().encode("M1"), "provider-a", 1, null);
      await vault.store(new TextEncoder().encode("M2"), "provider-a", 2, null);
      await vault.store(new TextEncoder().encode("M3"), "provider-b", 1, null);

      const stats = await vault.getStats();
      expect(stats.totalMemories).toBe(3);
      expect(stats.memoriesByProvider["provider-a"]).toBe(2);
      expect(stats.memoriesByProvider["provider-b"]).toBe(1);
      expect(stats.memoriesBySensitivity[1]).toBe(2);
      expect(stats.memoriesBySensitivity[2]).toBe(1);
    });
  });

  describe("Search", () => {
    it("should filter by provider", async () => {
      await vault.store(new TextEncoder().encode("A1"), "alpha", 1, null);
      await vault.store(new TextEncoder().encode("A2"), "alpha", 1, null);
      await vault.store(new TextEncoder().encode("B1"), "beta", 1, null);

      const results = await vault.search({ provider: "alpha" });
      expect(results.length).toBe(2);
      expect(results.every((m) => m.provider === "alpha")).toBe(true);
    });

    it("should filter by sensitivity level", async () => {
      await vault.store(new TextEncoder().encode("Low"), "p", 0, null);
      await vault.store(new TextEncoder().encode("High"), "p", 3, null);

      const results = await vault.search({ sensitivityLevel: 3 });
      expect(results.length).toBe(1);
      expect(results[0].sensitivityLevel).toBe(3);
    });

    it("should filter by tags", async () => {
      await vault.store(new TextEncoder().encode("T1"), "p", 1, null, { tags: ["work"] });
      await vault.store(new TextEncoder().encode("T2"), "p", 1, null, { tags: ["personal"] });

      const results = await vault.search({ tags: ["work"] });
      expect(results.length).toBe(1);
    });

    it("should limit results", async () => {
      for (let i = 0; i < 10; i++) {
        await vault.store(new TextEncoder().encode(`M${i}`), "p", 1, null);
      }

      const results = await vault.search({ limit: 5 });
      expect(results.length).toBe(5);
    });
  });
});

describe("InMemoryStorage", () => {
  let storage: InMemoryStorage;

  beforeEach(() => {
    storage = new InMemoryStorage();
  });

  it("should store and retrieve entries", async () => {
    const entry = createMockEntry("test-1");
    await storage.store(entry);
    const retrieved = await storage.get("test-1");
    expect(retrieved).not.toBeNull();
    expect(retrieved?.metadata.memoryId).toBe("test-1");
  });

  it("should delete entries", async () => {
    const entry = createMockEntry("to-delete");
    await storage.store(entry);
    const deleted = await storage.delete("to-delete");
    expect(deleted).toBe(true);
    const retrieved = await storage.get("to-delete");
    expect(retrieved).toBeNull();
  });

  it("should count entries", async () => {
    await storage.store(createMockEntry("1"));
    await storage.store(createMockEntry("2"));
    const count = await storage.count();
    expect(count).toBe(2);
  });

  it("should get expired entries", async () => {
    const expired = createMockEntry("expired");
    expired.metadata.expiresAt = new Date(Date.now() - 1000);
    await storage.store(expired);

    const valid = createMockEntry("valid");
    valid.metadata.expiresAt = new Date(Date.now() + 60000);
    await storage.store(valid);

    const expiredIds = await storage.getExpired(new Date());
    expect(expiredIds).toEqual(["expired"]);
  });
});

describe("InMemoryAuditLog", () => {
  let auditLog: InMemoryAuditLog;

  beforeEach(() => {
    auditLog = new InMemoryAuditLog();
  });

  it("should append entries with hash chain", async () => {
    const entry1 = await auditLog.append({
      action: "store",
      timestamp: new Date().toISOString(),
      memoryId: "mem-1",
      metadata: {},
    });

    expect(entry1.previousHash).toBe("0".repeat(64));
    expect(entry1.hash).toBeDefined();

    const entry2 = await auditLog.append({
      action: "retrieve",
      timestamp: new Date().toISOString(),
      memoryId: "mem-1",
      metadata: {},
    });

    expect(entry2.previousHash).toBe(entry1.hash);
  });

  it("should verify chain integrity", async () => {
    await auditLog.append({
      action: "store",
      timestamp: new Date().toISOString(),
      memoryId: "mem-1",
      metadata: {},
    });
    await auditLog.append({
      action: "delete",
      timestamp: new Date().toISOString(),
      memoryId: "mem-1",
      metadata: {},
    });

    const valid = await auditLog.verifyChain();
    expect(valid).toBe(true);
  });

  it("should get latest entry", async () => {
    await auditLog.append({
      action: "first",
      timestamp: new Date().toISOString(),
      memoryId: "m1",
      metadata: {},
    });
    await auditLog.append({
      action: "second",
      timestamp: new Date().toISOString(),
      memoryId: "m2",
      metadata: {},
    });

    const latest = await auditLog.getLatest();
    expect(latest?.action).toBe("second");
  });
});

function createMockEntry(memoryId: string) {
  return {
    metadata: {
      memoryId,
      createdAt: new Date(),
      expiresAt: null,
      provider: "test",
      sensitivityLevel: 1 as const,
      tags: [],
      lastAccessedAt: new Date(),
      accessCount: 0,
      version: 1,
    },
    wrappedDEK: {
      dekId: "dek-1",
      kekId: "kek-1",
      encryptedKey: new Uint8Array(48),
      nonce: new Uint8Array(12),
      authTag: new Uint8Array(16),
      wrappedAt: new Date(),
      destroyed: false,
    },
    encryptedContent: new Uint8Array(32),
    nonce: new Uint8Array(12),
    authTag: new Uint8Array(16),
    consentReceipt: null,
  };
}
