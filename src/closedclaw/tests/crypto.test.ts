/**
 * Closedclaw Crypto Tests
 * 
 * Comprehensive test suite for cryptographic primitives.
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  // AES-256-GCM
  generateKey,
  generateNonce,
  encryptAES256GCM,
  decryptAES256GCM,
  encryptMemory,
  decryptMemory,
  computeHash,
  constantTimeEqual,
  secureWipe,
  stringToBytes,
  bytesToString,
  KEY_SIZE,
  NONCE_SIZE,
  TAG_SIZE,
} from "../src/crypto/aes.js";
import {
  // Ed25519
  generateKeyPair,
  derivePublicKey,
  sign,
  verify,
  signWithMetadata,
  verifySignature,
  publicKeyToHex,
  hexToPublicKey,
  signatureToHex,
  hexToSignature,
  PRIVATE_KEY_SIZE,
  PUBLIC_KEY_SIZE,
  SIGNATURE_SIZE,
} from "../src/crypto/ed25519.js";
import {
  // Envelope encryption
  createDEK,
  wrapDEK,
  unwrapDEK,
  destroyDEK,
  markWrappedDEKDestroyed,
  rewrapDEK,
  isDEKExpired,
  DEKManager,
} from "../src/crypto/envelope.js";
import type { KeyEncryptionKey } from "../src/crypto/types.js";

describe("AES-256-GCM Encryption", () => {
  describe("Key Generation", () => {
    it("should generate a 256-bit key", () => {
      const key = generateKey();
      expect(key).toBeInstanceOf(Uint8Array);
      expect(key.length).toBe(KEY_SIZE);
    });

    it("should generate unique keys", () => {
      const key1 = generateKey();
      const key2 = generateKey();
      expect(constantTimeEqual(key1, key2)).toBe(false);
    });
  });

  describe("Nonce Generation", () => {
    it("should generate a 96-bit nonce", () => {
      const nonce = generateNonce();
      expect(nonce).toBeInstanceOf(Uint8Array);
      expect(nonce.length).toBe(NONCE_SIZE);
    });

    it("should generate unique nonces", () => {
      const nonce1 = generateNonce();
      const nonce2 = generateNonce();
      expect(constantTimeEqual(nonce1, nonce2)).toBe(false);
    });
  });

  describe("Encryption/Decryption", () => {
    it("should encrypt and decrypt data correctly", () => {
      const key = generateKey();
      const nonce = generateNonce();
      const plaintext = stringToBytes("Hello, World!");

      const { ciphertext, authTag } = encryptAES256GCM(plaintext, key, nonce);
      expect(ciphertext).toBeInstanceOf(Uint8Array);
      expect(authTag.length).toBe(TAG_SIZE);

      const decrypted = decryptAES256GCM(ciphertext, authTag, key, nonce);
      expect(bytesToString(decrypted)).toBe("Hello, World!");
    });

    it("should fail decryption with wrong key", () => {
      const key1 = generateKey();
      const key2 = generateKey();
      const nonce = generateNonce();
      const plaintext = stringToBytes("Secret data");

      const { ciphertext, authTag } = encryptAES256GCM(plaintext, key1, nonce);

      expect(() => {
        decryptAES256GCM(ciphertext, authTag, key2, nonce);
      }).toThrow();
    });

    it("should fail decryption with tampered ciphertext", () => {
      const key = generateKey();
      const nonce = generateNonce();
      const plaintext = stringToBytes("Sensitive information");

      const { ciphertext, authTag } = encryptAES256GCM(plaintext, key, nonce);

      // Tamper with ciphertext
      ciphertext[0] = (ciphertext[0] ?? 0) ^ 0xff;

      expect(() => {
        decryptAES256GCM(ciphertext, authTag, key, nonce);
      }).toThrow();
    });

    it("should support additional authenticated data (AAD)", () => {
      const key = generateKey();
      const nonce = generateNonce();
      const plaintext = stringToBytes("Protected data");
      const aad = stringToBytes("metadata");

      const { ciphertext, authTag } = encryptAES256GCM(plaintext, key, nonce, aad);
      const decrypted = decryptAES256GCM(ciphertext, authTag, key, nonce, aad);
      
      expect(bytesToString(decrypted)).toBe("Protected data");
    });

    it("should fail with wrong AAD", () => {
      const key = generateKey();
      const nonce = generateNonce();
      const plaintext = stringToBytes("Protected data");
      const aad1 = stringToBytes("metadata1");
      const aad2 = stringToBytes("metadata2");

      const { ciphertext, authTag } = encryptAES256GCM(plaintext, key, nonce, aad1);

      expect(() => {
        decryptAES256GCM(ciphertext, authTag, key, nonce, aad2);
      }).toThrow();
    });
  });

  describe("Memory Encryption", () => {
    it("should encrypt and decrypt memory with integrity verification", () => {
      const dekKey = generateKey();
      const dekId = "dek_test_123";
      const memoryId = "mem_test_456";
      const plaintext = stringToBytes("Memory content to protect");

      const encrypted = encryptMemory(memoryId, plaintext, dekId, dekKey);
      expect(encrypted.id).toBe(memoryId);
      expect(encrypted.dekId).toBe(dekId);
      expect(encrypted.contentHash).toBeInstanceOf(Uint8Array);

      const decrypted = decryptMemory(encrypted, dekKey);
      expect(decrypted.integrityVerified).toBe(true);
      expect(bytesToString(decrypted.plaintext)).toBe("Memory content to protect");
    });
  });

  describe("Hash Functions", () => {
    it("should compute deterministic SHA-256 hashes", () => {
      const data = stringToBytes("test data");
      const hash1 = computeHash(data);
      const hash2 = computeHash(data);

      expect(hash1.length).toBe(32); // 256 bits
      expect(constantTimeEqual(hash1, hash2)).toBe(true);
    });

    it("should produce different hashes for different data", () => {
      const hash1 = computeHash(stringToBytes("data1"));
      const hash2 = computeHash(stringToBytes("data2"));

      expect(constantTimeEqual(hash1, hash2)).toBe(false);
    });
  });

  describe("Utility Functions", () => {
    it("should securely wipe data", () => {
      const data = generateKey();
      const original = new Uint8Array(data);
      
      secureWipe(data);
      
      expect(constantTimeEqual(data, original)).toBe(false);
      expect(data.every((b) => b === 0)).toBe(true);
    });

    it("should convert strings to bytes and back", () => {
      const original = "Hello, 世界! 🌍";
      const bytes = stringToBytes(original);
      const restored = bytesToString(bytes);
      
      expect(restored).toBe(original);
    });
  });
});

describe("Ed25519 Digital Signatures", () => {
  describe("Key Generation", () => {
    it("should generate valid key pair", () => {
      const keyPair = generateKeyPair();
      
      expect(keyPair.privateKey.length).toBe(PRIVATE_KEY_SIZE);
      expect(keyPair.publicKey.length).toBe(PUBLIC_KEY_SIZE);
      expect(keyPair.createdAt).toBeInstanceOf(Date);
    });

    it("should derive public key from private key", () => {
      const keyPair = generateKeyPair();
      const derivedPubKey = derivePublicKey(keyPair.privateKey);
      
      expect(constantTimeEqual(derivedPubKey, keyPair.publicKey)).toBe(true);
    });
  });

  describe("Signing and Verification", () => {
    it("should sign and verify messages", () => {
      const keyPair = generateKeyPair();
      const message = stringToBytes("Message to sign");
      
      const signature = sign(message, keyPair.privateKey);
      expect(signature.length).toBe(SIGNATURE_SIZE);
      
      const isValid = verify(signature, message, keyPair.publicKey);
      expect(isValid).toBe(true);
    });

    it("should fail verification with wrong public key", () => {
      const keyPair1 = generateKeyPair();
      const keyPair2 = generateKeyPair();
      const message = stringToBytes("Message");
      
      const signature = sign(message, keyPair1.privateKey);
      const isValid = verify(signature, message, keyPair2.publicKey);
      
      expect(isValid).toBe(false);
    });

    it("should fail verification with tampered message", () => {
      const keyPair = generateKeyPair();
      const message = stringToBytes("Original message");
      const tamperedMessage = stringToBytes("Tampered message");
      
      const signature = sign(message, keyPair.privateKey);
      const isValid = verify(signature, tamperedMessage, keyPair.publicKey);
      
      expect(isValid).toBe(false);
    });

    it("should sign with metadata", () => {
      const keyPair = generateKeyPair();
      const message = stringToBytes("Message with metadata");
      
      const sig = signWithMetadata(message, keyPair.privateKey);
      
      expect(sig.signature.length).toBe(SIGNATURE_SIZE);
      expect(constantTimeEqual(sig.signerPublicKey, keyPair.publicKey)).toBe(true);
      expect(sig.signedAt).toBeInstanceOf(Date);
      
      const isValid = verifySignature(sig, message);
      expect(isValid).toBe(true);
    });
  });

  describe("Hex Conversion", () => {
    it("should convert public key to hex and back", () => {
      const keyPair = generateKeyPair();
      const hex = publicKeyToHex(keyPair.publicKey);
      const restored = hexToPublicKey(hex);
      
      expect(hex.length).toBe(PUBLIC_KEY_SIZE * 2);
      expect(constantTimeEqual(restored, keyPair.publicKey)).toBe(true);
    });

    it("should convert signature to hex and back", () => {
      const keyPair = generateKeyPair();
      const message = stringToBytes("Test");
      const signature = sign(message, keyPair.privateKey);
      
      const hex = signatureToHex(signature);
      const restored = hexToSignature(hex);
      
      expect(hex.length).toBe(SIGNATURE_SIZE * 2);
      expect(constantTimeEqual(restored, signature)).toBe(true);
    });
  });
});

describe("Envelope Encryption (KEK/DEK)", () => {
  let mockKEK: KeyEncryptionKey;

  beforeEach(() => {
    mockKEK = {
      id: "kek_test",
      key: generateKey(),
      salt: new Uint8Array(16),
      createdAt: new Date(),
      version: 1,
    };
  });

  describe("DEK Operations", () => {
    it("should create a DEK with unique ID", () => {
      const dek = createDEK("mem_test");
      
      expect(dek.id).toMatch(/^dek_/);
      expect(dek.key.length).toBe(KEY_SIZE);
      expect(dek.memoryId).toBe("mem_test");
      expect(dek.destroyed).toBe(false);
    });

    it("should create DEK with expiry", () => {
      const expiresAt = new Date(Date.now() + 3600000); // 1 hour
      const dek = createDEK("mem_test", expiresAt);
      
      expect(dek.expiresAt).toEqual(expiresAt);
    });
  });

  describe("DEK Wrapping/Unwrapping", () => {
    it("should wrap and unwrap DEK correctly", () => {
      const dek = createDEK("mem_test");
      const originalKey = new Uint8Array(dek.key);
      
      const wrapped = wrapDEK(dek, mockKEK);
      expect(wrapped.dekId).toBe(dek.id);
      expect(wrapped.kekVersion).toBe(mockKEK.version);
      
      const unwrapped = unwrapDEK(wrapped, mockKEK);
      expect(constantTimeEqual(unwrapped.key, originalKey)).toBe(true);
    });

    it("should fail to wrap destroyed DEK", () => {
      const dek = createDEK("mem_test");
      const destroyed = destroyDEK(dek);
      
      expect(() => wrapDEK(destroyed, mockKEK)).toThrow("Cannot wrap a destroyed DEK");
    });

    it("should fail to unwrap with wrong KEK version", () => {
      const dek = createDEK("mem_test");
      const wrapped = wrapDEK(dek, mockKEK);
      
      const wrongVersionKEK = { ...mockKEK, version: 2 };
      
      expect(() => unwrapDEK(wrapped, wrongVersionKEK)).toThrow("KEK version mismatch");
    });
  });

  describe("DEK Destruction (Cryptographic Deletion)", () => {
    it("should destroy DEK by wiping key material", () => {
      const dek = createDEK("mem_test");
      const destroyed = destroyDEK(dek);
      
      expect(destroyed.destroyed).toBe(true);
      expect(destroyed.key.every((b) => b === 0)).toBe(true);
    });

    it("should mark wrapped DEK as destroyed", () => {
      const dek = createDEK("mem_test");
      const wrapped = wrapDEK(dek, mockKEK);
      const destroyed = markWrappedDEKDestroyed(wrapped);
      
      expect(destroyed.destroyed).toBe(true);
      expect(destroyed.destroyedAt).toBeInstanceOf(Date);
      expect(destroyed.encryptedKey.every((b) => b === 0)).toBe(true);
    });

    it("should fail to unwrap destroyed DEK", () => {
      const dek = createDEK("mem_test");
      const wrapped = wrapDEK(dek, mockKEK);
      const destroyed = markWrappedDEKDestroyed(wrapped);
      
      expect(() => unwrapDEK(destroyed, mockKEK)).toThrow("permanently unrecoverable");
    });
  });

  describe("DEK Re-wrapping (Key Rotation)", () => {
    it("should re-wrap DEK with new KEK", () => {
      const dek = createDEK("mem_test");
      const originalKey = new Uint8Array(dek.key);
      const wrapped = wrapDEK(dek, mockKEK);
      
      const newKEK: KeyEncryptionKey = {
        id: "kek_new",
        key: generateKey(),
        salt: new Uint8Array(16),
        createdAt: new Date(),
        version: 2,
      };
      
      const rewrapped = rewrapDEK(wrapped, mockKEK, newKEK);
      expect(rewrapped.kekVersion).toBe(2);
      
      const unwrapped = unwrapDEK(rewrapped, newKEK);
      expect(constantTimeEqual(unwrapped.key, originalKey)).toBe(true);
    });
  });

  describe("TTL Expiry", () => {
    it("should detect expired DEK", () => {
      const pastDate = new Date(Date.now() - 1000);
      const dek = createDEK("mem_test", pastDate);
      
      expect(isDEKExpired(dek)).toBe(true);
    });

    it("should not mark non-expired DEK as expired", () => {
      const futureDate = new Date(Date.now() + 3600000);
      const dek = createDEK("mem_test", futureDate);
      
      expect(isDEKExpired(dek)).toBe(false);
    });

    it("should not mark DEK without expiry as expired", () => {
      const dek = createDEK("mem_test");
      
      expect(isDEKExpired(dek)).toBe(false);
    });
  });

  describe("DEK Manager", () => {
    it("should manage DEK lifecycle", () => {
      const manager = new DEKManager(mockKEK);
      
      // Create and store
      const dek = manager.createAndStore("mem_test");
      expect(dek.id).toMatch(/^dek_/);
      
      // Retrieve
      const retrieved = manager.retrieve(dek.id);
      expect(retrieved.memoryId).toBe("mem_test");
      
      // Destroy
      const destroyed = manager.destroy(dek.id);
      expect(destroyed.destroyed).toBe(true);
      
      // Should fail to retrieve destroyed DEK
      expect(() => manager.retrieve(dek.id)).toThrow("permanently unrecoverable");
    });

    it("should export and import DEKs", () => {
      const manager = new DEKManager(mockKEK);
      manager.createAndStore("mem_1");
      manager.createAndStore("mem_2");
      
      const exported = manager.exportAll();
      expect(exported.length).toBe(2);
      
      const newManager = new DEKManager(mockKEK);
      newManager.importAll(exported);
      
      const newExported = newManager.exportAll();
      expect(newExported.length).toBe(2);
    });
  });
});
