/**
 * Crypto module tests
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  encryptAES256GCM,
  decryptAES256GCM,
  encryptMemory,
  decryptMemory,
  generateNonce,
  generateKey,
  computeHash,
  secureWipe,
  hashToHex,
} from "../src/crypto/aes.js";
import {
  generateKeyPair,
  sign,
  verify,
  signWithMetadata,
  hashForSigning,
  publicKeyToHex,
  hexToPublicKey,
  signatureToHex,
  hexToSignature,
} from "../src/crypto/ed25519.js";
import {
  createDEK,
  wrapDEK,
  unwrapDEK,
  destroyDEK,
  markWrappedDEKDestroyed,
  DEKManager,
} from "../src/crypto/envelope.js";
import type { KeyEncryptionKey } from "../src/crypto/types.js";

describe("AES-256-GCM Encryption", () => {
  const testData = new TextEncoder().encode("Hello, World! This is test data.");
  let key: Uint8Array;
  let nonce: Uint8Array;

  beforeEach(() => {
    key = generateKey();
    nonce = generateNonce();
  });

  it("should generate 256-bit key", () => {
    expect(key.length).toBe(32);
  });

  it("should generate 96-bit nonce", () => {
    expect(nonce.length).toBe(12);
  });

  it("should encrypt and decrypt data", () => {
    const encrypted = encryptAES256GCM(testData, key, nonce);
    // Note: decryptAES256GCM signature is (ciphertext, authTag, key, nonce)
    const decrypted = decryptAES256GCM(encrypted.ciphertext, encrypted.authTag, key, nonce);
    expect(decrypted).toEqual(testData);
  });

  it("should produce different ciphertext for same data with different nonces", () => {
    const nonce1 = generateNonce();
    const nonce2 = generateNonce();
    const encrypted1 = encryptAES256GCM(testData, key, nonce1);
    const encrypted2 = encryptAES256GCM(testData, key, nonce2);
    expect(encrypted1.ciphertext).not.toEqual(encrypted2.ciphertext);
  });

  it("should fail decryption with wrong key", () => {
    const wrongKey = generateKey();
    const encrypted = encryptAES256GCM(testData, key, nonce);
    expect(() => decryptAES256GCM(encrypted.ciphertext, encrypted.authTag, wrongKey, nonce)).toThrow();
  });

  it("should fail decryption with tampered ciphertext", () => {
    const encrypted = encryptAES256GCM(testData, key, nonce);
    encrypted.ciphertext[0] ^= 0xff;
    expect(() => decryptAES256GCM(encrypted.ciphertext, encrypted.authTag, key, nonce)).toThrow();
  });

  it("should fail decryption with tampered auth tag", () => {
    const encrypted = encryptAES256GCM(testData, key, nonce);
    encrypted.authTag[0] ^= 0xff;
    expect(() => decryptAES256GCM(encrypted.ciphertext, encrypted.authTag, key, nonce)).toThrow();
  });
});

describe("Memory Encryption", () => {
  it("should encrypt and decrypt memory with DEK", () => {
    const content = new TextEncoder().encode("Sensitive user data");
    const dekKey = generateKey();
    const memoryId = "test-memory-1";
    const dekId = "test-dek-1";

    const encrypted = encryptMemory(memoryId, content, dekId, dekKey);
    expect(encrypted.id).toBe(memoryId);
    expect(encrypted.dekId).toBe(dekId);
    
    const decrypted = decryptMemory(encrypted, dekKey);
    expect(decrypted.plaintext).toEqual(content);
    expect(decrypted.integrityVerified).toBe(true);
  });
});

describe("SHA-256 Hashing", () => {
  it("should compute consistent hash", () => {
    const data = new TextEncoder().encode("test data");
    const hash1 = computeHash(data);
    const hash2 = computeHash(data);
    expect(hash1).toEqual(hash2);
  });

  it("should produce 256-bit hash", () => {
    const data = new TextEncoder().encode("test");
    const hash = computeHash(data);
    expect(hash.length).toBe(32);
  });

  it("should convert hash to hex", () => {
    const data = new TextEncoder().encode("test");
    const hash = computeHash(data);
    const hex = hashToHex(hash);
    expect(hex).toMatch(/^[0-9a-f]{64}$/);
  });
});

describe("Secure Wipe", () => {
  it("should zero out buffer", () => {
    const buffer = new Uint8Array([1, 2, 3, 4, 5]);
    secureWipe(buffer);
    expect(buffer.every((b) => b === 0)).toBe(true);
  });
});

describe("Ed25519 Signatures", () => {
  let keyPair: { publicKey: Uint8Array; privateKey: Uint8Array; createdAt: Date };
  const testMessage = new TextEncoder().encode("Message to sign");

  beforeEach(() => {
    keyPair = generateKeyPair();
  });

  it("should generate 32-byte public key", () => {
    expect(keyPair.publicKey.length).toBe(32);
  });

  it("should generate 32-byte private key (seed)", () => {
    // @noble/curves Ed25519 uses 32-byte seed
    expect(keyPair.privateKey.length).toBe(32);
  });

  it("should sign and verify message", () => {
    const messageHash = hashForSigning(testMessage);
    const signature = sign(messageHash, keyPair.privateKey);
    expect(signature.length).toBe(64);

    const valid = verify(signature, messageHash, keyPair.publicKey);
    expect(valid).toBe(true);
  });

  it("should reject invalid signature", () => {
    const messageHash = hashForSigning(testMessage);
    const signature = sign(messageHash, keyPair.privateKey);
    signature[0] ^= 0xff;
    const valid = verify(signature, messageHash, keyPair.publicKey);
    expect(valid).toBe(false);
  });

  it("should reject wrong public key", () => {
    const messageHash = hashForSigning(testMessage);
    const signature = sign(messageHash, keyPair.privateKey);
    const wrongKeyPair = generateKeyPair();
    const valid = verify(signature, messageHash, wrongKeyPair.publicKey);
    expect(valid).toBe(false);
  });

  it("should sign with metadata", () => {
    const result = signWithMetadata(testMessage, keyPair.privateKey);
    expect(result.signature.length).toBe(64);
    expect(result.signedAt).toBeInstanceOf(Date);
    expect(result.signerPublicKey.length).toBe(32);
  });

  it("should convert keys to hex and back", () => {
    const hex = publicKeyToHex(keyPair.publicKey);
    expect(hex).toMatch(/^[0-9a-f]{64}$/);
    const recovered = hexToPublicKey(hex);
    expect(recovered).toEqual(keyPair.publicKey);
  });

  it("should convert signature to hex and back", () => {
    const messageHash = hashForSigning(testMessage);
    const signature = sign(messageHash, keyPair.privateKey);
    const hex = signatureToHex(signature);
    expect(hex).toMatch(/^[0-9a-f]{128}$/);
    const recovered = hexToSignature(hex);
    expect(recovered).toEqual(signature);
  });
});

describe("Envelope Encryption", () => {
  let kek: KeyEncryptionKey;

  beforeEach(() => {
    kek = {
      id: "test-kek-1",
      key: generateKey(),
      createdAt: new Date(),
      version: 1,
      rotatedAt: null,
    };
  });

  it("should create DEK with unique ID", () => {
    const dek1 = createDEK("mem-1");
    const dek2 = createDEK("mem-2");
    expect(dek1.id).not.toBe(dek2.id);
    expect(dek1.key.length).toBe(32);
  });

  it("should wrap and unwrap DEK", () => {
    const dek = createDEK("mem-test");
    const wrapped = wrapDEK(dek, kek);

    expect(wrapped.dekId).toBe(dek.id);
    expect(wrapped.kekVersion).toBe(kek.version);
    expect(wrapped.encryptedKey.length).toBeGreaterThan(0);

    const unwrapped = unwrapDEK(wrapped, kek);
    expect(unwrapped.id).toBe(dek.id);
    expect(unwrapped.key).toEqual(dek.key);
    expect(unwrapped.destroyed).toBe(false);
  });

  it("should fail unwrap with wrong KEK", () => {
    const dek = createDEK("mem-test");
    const wrapped = wrapDEK(dek, kek);

    const wrongKek: KeyEncryptionKey = {
      id: "wrong-kek",
      key: generateKey(),
      createdAt: new Date(),
      version: 2,
      rotatedAt: null,
    };

    expect(() => unwrapDEK(wrapped, wrongKek)).toThrow();
  });

  it("should destroy DEK", () => {
    const dek = createDEK("mem-destroy");
    const destroyed = destroyDEK(dek);
    expect(destroyed.destroyed).toBe(true);
    expect(destroyed.key.every((b) => b === 0)).toBe(true);
  });

  it("should mark wrapped DEK as destroyed", () => {
    const dek = createDEK("mem-test");
    const wrapped = wrapDEK(dek, kek);
    const destroyed = markWrappedDEKDestroyed(wrapped);
    expect(destroyed.destroyed).toBe(true);
  });

  it("should fail unwrap of destroyed wrapped DEK", () => {
    const dek = createDEK("mem-test");
    const wrapped = wrapDEK(dek, kek);
    const destroyed = markWrappedDEKDestroyed(wrapped);
    expect(() => unwrapDEK(destroyed, kek)).toThrow("Cannot unwrap a destroyed DEK");
  });
});

describe("DEKManager", () => {
  let kek: KeyEncryptionKey;
  let manager: DEKManager;

  beforeEach(() => {
    kek = {
      id: "manager-kek",
      key: generateKey(),
      createdAt: new Date(),
      version: 1,
      rotatedAt: null,
    };
    manager = new DEKManager(kek);
  });

  it("should create and wrap DEK", () => {
    const wrapped = manager.createAndWrap("mem-1");
    expect(wrapped.kekVersion).toBe(kek.version);
    expect(wrapped.encryptedKey.length).toBeGreaterThan(0);
  });

  it("should unwrap DEK", () => {
    const wrapped = manager.createAndWrap("mem-1");
    const dek = manager.unwrap(wrapped);
    expect(dek.key.length).toBe(32);
    expect(dek.destroyed).toBe(false);
  });

  it("should rewrap DEK with new KEK", () => {
    const wrapped = manager.createAndWrap("mem-1");
    const newKek: KeyEncryptionKey = {
      id: "new-kek",
      key: generateKey(),
      createdAt: new Date(),
      version: 2,
      rotatedAt: null,
    };

    const rewrapped = manager.rewrapWithNewKEK(wrapped, newKek);
    expect(rewrapped.kekVersion).toBe(newKek.version);
    expect(rewrapped.dekId).toBe(wrapped.dekId);

    const newManager = new DEKManager(newKek);
    const dek = newManager.unwrap(rewrapped);
    expect(dek.key.length).toBe(32);
  });
});
