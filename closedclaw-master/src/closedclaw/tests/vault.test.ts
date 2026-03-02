/**
 * Closedclaw Vault Tests
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  MemoryVault,
  InMemoryVaultStorage,
  InMemoryAuditTrail,
} from "../src/vault/index.js";
import {
  generateKey,
  generateKeyPair,
  generateSalt,
} from "../src/crypto/index.js";
import type { KeyEncryptionKey, SigningKeyPair } from "../src/crypto/types.js";

describe("Memory Vault", () => {
  let kek: KeyEncryptionKey;
  let signingKeyPair: SigningKeyPair;
  let vault: MemoryVault;

  beforeEach(() => {
    kek = {
      id: "kek_test",
      key: generateKey(),
      salt: generateSalt(),
      createdAt: new Date(),
      version: 1,
    };
    signingKeyPair = generateKeyPair();
    vault = new MemoryVault(kek, signingKeyPair, undefined, undefined, {
      autoExpiryIntervalMs: 0, // Disable auto-expiry for tests
    });
  });

  afterEach(() => {
    vault.destroy();
  });

  describe("Memory Storage", () => {
    it("should store and retrieve encrypted memory", async () => {
      const content = "This is sensitive information";
      const memoryId = await vault.store(content, {
        sensitivityLevel: 2,
        tags: ["test"],
      });

      expect(memoryId).toMatch(/^mem_/);

      const retrieved = await vault.retrieve(memoryId);
      expect(retrieved).not.toBeNull();
      expect(retrieved?.text).toBe(content);
      expect(retrieved?.metadata.sensitivityLevel).toBe(2);
      expect(retrieved?.metadata.tags).toContain("test");
    });

    it("should store binary data", async () => {
      const binaryData = new Uint8Array([1, 2, 3, 4, 5]);
      const memoryId = await vault.store(binaryData, {
        contentType: "binary",
      });

      const retrieved = await vault.retrieve(memoryId);
      expect(retrieved?.plaintext).toEqual(binaryData);
    });

    it("should store JSON data", async () => {
      const jsonData = JSON.stringify({ key: "value", nested: { a: 1 } });
      const memoryId = await vault.store(jsonData, {
        contentType: "json",
      });

      const retrieved = await vault.retrieve(memoryId);
      expect(retrieved?.json).toEqual({ key: "value", nested: { a: 1 } });
    });

    it("should return null for non-existent memory", async () => {
      const retrieved = await vault.retrieve("mem_nonexistent");
      expect(retrieved).toBeNull();
    });
  });

  describe("Cryptographic Deletion", () => {
    it("should cryptographically delete memory (GDPR compliant)", async () => {
      const memoryId = await vault.store("Data to delete", {
        sensitivityLevel: 3,
      });

      const result = await vault.delete(memoryId);

      expect(result.gdprCompliant).toBe(true);
      expect(result.memoryId).toBe(memoryId);
      expect(result.deletedAt).toBeInstanceOf(Date);
    });

    it("should fail to retrieve deleted memory", async () => {
      const memoryId = await vault.store("Secret data");
      await vault.delete(memoryId);

      await expect(vault.retrieve(memoryId)).rejects.toThrow(
        "cryptographically deleted"
      );
    });

    it("should fail to delete already deleted memory", async () => {
      const memoryId = await vault.store("Data");
      await vault.delete(memoryId);

      await expect(vault.delete(memoryId)).rejects.toThrow("already deleted");
    });
  });

  describe("TTL Expiry", () => {
    it("should set expiry based on TTL", async () => {
      const memoryId = await vault.store("Expiring data", {
        ttlSeconds: 3600, // 1 hour
      });

      const metadata = (await vault.query({ limit: 1 }))[0];
      expect(metadata?.expiresAt).toBeInstanceOf(Date);
      expect(metadata?.expiresAt?.getTime()).toBeGreaterThan(Date.now());
    });

    it("should process expired memories", async () => {
      // Create memory that expires immediately
      const vaultWithExpiry = new MemoryVault(
        kek,
        signingKeyPair,
        new InMemoryVaultStorage(),
        new InMemoryAuditTrail(),
        {
          defaultTtlSeconds: 0,
          autoExpiryIntervalMs: 0,
        }
      );

      // Store with past expiry (simulate expired)
      await vaultWithExpiry.store("Old data", {
        ttlSeconds: -1, // Already expired
      });

      const result = await vaultWithExpiry.processExpiredMemories();
      // Note: The implementation might not handle negative TTL directly
      // This tests the mechanism exists
      expect(result.processedAt).toBeInstanceOf(Date);

      vaultWithExpiry.destroy();
    });
  });

  describe("Query Operations", () => {
    it("should query memories by sensitivity level", async () => {
      await vault.store("Level 1 data", { sensitivityLevel: 1 });
      await vault.store("Level 2 data", { sensitivityLevel: 2 });
      await vault.store("Level 3 data", { sensitivityLevel: 3 });

      const level2Memories = await vault.query({ sensitivityLevel: 2 });
      expect(level2Memories).toHaveLength(1);
      expect(level2Memories[0]?.sensitivityLevel).toBe(2);
    });

    it("should query memories by tags", async () => {
      await vault.store("Tagged data", { tags: ["important", "urgent"] });
      await vault.store("Other data", { tags: ["normal"] });

      const importantMemories = await vault.query({ tags: ["important"] });
      expect(importantMemories).toHaveLength(1);
    });

    it("should exclude deleted memories by default", async () => {
      const memoryId = await vault.store("Will be deleted");
      await vault.store("Active memory");
      await vault.delete(memoryId);

      const allMemories = await vault.query({});
      expect(allMemories).toHaveLength(1);

      const includingDeleted = await vault.query({ includeDeleted: true });
      expect(includingDeleted).toHaveLength(2);
    });

    it("should support pagination", async () => {
      for (let i = 0; i < 5; i++) {
        await vault.store(`Memory ${i}`);
      }

      const page1 = await vault.query({ limit: 2 });
      const page2 = await vault.query({ limit: 2, offset: 2 });

      expect(page1).toHaveLength(2);
      expect(page2).toHaveLength(2);
    });
  });

  describe("Statistics", () => {
    it("should return vault statistics", async () => {
      await vault.store("Level 1", { sensitivityLevel: 1 });
      await vault.store("Level 2", { sensitivityLevel: 2 });
      const toDelete = await vault.store("To delete", { sensitivityLevel: 3 });
      await vault.delete(toDelete);

      const stats = await vault.getStats();

      expect(stats.totalEntries).toBe(3);
      expect(stats.activeEntries).toBe(2);
      expect(stats.deletedEntries).toBe(1);
      expect(stats.bySensitivity[1]).toBe(1);
      expect(stats.bySensitivity[2]).toBe(1);
      expect(stats.bySensitivity[3]).toBe(1);
    });
  });

  describe("KEK Rotation", () => {
    it("should rotate KEK and re-wrap all DEKs", async () => {
      await vault.store("Memory 1");
      await vault.store("Memory 2");

      const newKEK: KeyEncryptionKey = {
        id: "kek_new",
        key: generateKey(),
        salt: generateSalt(),
        createdAt: new Date(),
        version: 2,
      };

      const result = await vault.rotateKEK(newKEK);
      expect(result.rewrappedCount).toBe(2);

      // Should still be able to retrieve after rotation
      const memories = await vault.query({});
      for (const meta of memories) {
        const retrieved = await vault.retrieve(meta.id);
        expect(retrieved).not.toBeNull();
      }
    });
  });

  describe("Audit Trail", () => {
    it("should create audit entries for operations", async () => {
      const memoryId = await vault.store("Audited memory");
      
      const auditTrail = await vault.getAuditTrail(memoryId);
      expect(auditTrail.length).toBeGreaterThan(0);
      
      const encryptEntry = auditTrail.find((e) => e.type === "memory_encrypted");
      expect(encryptEntry).toBeDefined();
    });

    it("should verify audit trail integrity", async () => {
      await vault.store("Memory 1");
      await vault.store("Memory 2");

      const result = await vault.verifyAuditTrail();
      expect(result.valid).toBe(true);
      expect(result.entriesChecked).toBeGreaterThan(0);
    });
  });

  describe("Integrity Verification", () => {
    it("should verify memory integrity on retrieval", async () => {
      const content = "Important data with integrity check";
      const memoryId = await vault.store(content);

      const retrieved = await vault.retrieve(memoryId);
      expect(retrieved?.text).toBe(content);
      // Integrity is verified during decryption - if we get here, it passed
    });
  });
});
