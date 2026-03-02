/**
 * Closedclaw AES-256-GCM Encryption
 * 
 * Authenticated encryption for memory at rest.
 * Each memory chunk has its own unique 256-bit DEK.
 * 
 * Security properties:
 * - Confidentiality: AES-256 encryption
 * - Integrity: GCM authentication tag (128-bit)
 * - Authenticity: AEAD ensures ciphertext wasn't tampered
 */

import { gcm } from "@noble/ciphers/aes";
import { randomBytes } from "@noble/ciphers/webcrypto";
import { sha256 } from "@noble/hashes/sha256";
import { bytesToHex, hexToBytes } from "@noble/hashes/utils";
import type { EncryptedMemory, DecryptedMemory, MemoryId, KeyId } from "./types";

/** AES-256-GCM nonce size in bytes (96-bit recommended by NIST) */
export const NONCE_SIZE = 12;

/** AES-256 key size in bytes */
export const KEY_SIZE = 32;

/** GCM authentication tag size in bytes */
export const TAG_SIZE = 16;

/**
 * Generate a cryptographically secure random 256-bit key
 */
export function generateKey(): Uint8Array {
  return randomBytes(KEY_SIZE);
}

/**
 * Generate a cryptographically secure random nonce
 */
export function generateNonce(): Uint8Array {
  return randomBytes(NONCE_SIZE);
}

/**
 * Compute SHA-256 hash of data
 */
export function computeHash(data: Uint8Array): Uint8Array {
  return sha256(data);
}

/**
 * Convert hash to hex string for display/storage
 */
export function hashToHex(hash: Uint8Array): string {
  return bytesToHex(hash);
}

/**
 * Convert hex string back to hash bytes
 */
export function hexToHash(hex: string): Uint8Array {
  return hexToBytes(hex);
}

/**
 * Encrypt plaintext using AES-256-GCM
 * 
 * @param plaintext - Data to encrypt
 * @param key - 256-bit encryption key
 * @param nonce - 96-bit nonce (must be unique per key)
 * @param aad - Additional authenticated data (optional)
 * @returns Ciphertext with embedded authentication tag
 */
export function encryptAES256GCM(
  plaintext: Uint8Array,
  key: Uint8Array,
  nonce: Uint8Array,
  aad?: Uint8Array
): { ciphertext: Uint8Array; authTag: Uint8Array } {
  if (key.length !== KEY_SIZE) {
    throw new Error(`Invalid key size: expected ${KEY_SIZE} bytes, got ${key.length}`);
  }
  if (nonce.length !== NONCE_SIZE) {
    throw new Error(`Invalid nonce size: expected ${NONCE_SIZE} bytes, got ${nonce.length}`);
  }

  const cipher = gcm(key, nonce, aad);
  const encrypted = cipher.encrypt(plaintext);
  
  // GCM appends auth tag to ciphertext
  const ciphertext = encrypted.slice(0, -TAG_SIZE);
  const authTag = encrypted.slice(-TAG_SIZE);

  return { ciphertext, authTag };
}

/**
 * Decrypt ciphertext using AES-256-GCM
 * 
 * @param ciphertext - Encrypted data
 * @param authTag - Authentication tag
 * @param key - 256-bit decryption key
 * @param nonce - 96-bit nonce used during encryption
 * @param aad - Additional authenticated data (must match encryption)
 * @returns Decrypted plaintext
 * @throws Error if authentication fails (tampered data)
 */
export function decryptAES256GCM(
  ciphertext: Uint8Array,
  authTag: Uint8Array,
  key: Uint8Array,
  nonce: Uint8Array,
  aad?: Uint8Array
): Uint8Array {
  if (key.length !== KEY_SIZE) {
    throw new Error(`Invalid key size: expected ${KEY_SIZE} bytes, got ${key.length}`);
  }
  if (nonce.length !== NONCE_SIZE) {
    throw new Error(`Invalid nonce size: expected ${NONCE_SIZE} bytes, got ${nonce.length}`);
  }
  if (authTag.length !== TAG_SIZE) {
    throw new Error(`Invalid auth tag size: expected ${TAG_SIZE} bytes, got ${authTag.length}`);
  }

  // Reconstruct the encrypted blob with auth tag
  const encrypted = new Uint8Array(ciphertext.length + authTag.length);
  encrypted.set(ciphertext, 0);
  encrypted.set(authTag, ciphertext.length);

  const cipher = gcm(key, nonce, aad);
  
  try {
    return cipher.decrypt(encrypted);
  } catch {
    throw new Error("Decryption failed: authentication tag mismatch (data may be corrupted or tampered)");
  }
}

/**
 * Encrypt a memory chunk with full metadata
 * 
 * @param memoryId - Unique memory identifier
 * @param plaintext - Memory content to encrypt
 * @param dekId - DEK identifier
 * @param dekKey - DEK key material
 * @param aad - Optional additional authenticated data
 * @returns Complete encrypted memory record
 */
export function encryptMemory(
  memoryId: MemoryId,
  plaintext: Uint8Array,
  dekId: KeyId,
  dekKey: Uint8Array,
  aad?: Uint8Array
): EncryptedMemory {
  const nonce = generateNonce();
  const contentHash = computeHash(plaintext);
  const { ciphertext, authTag } = encryptAES256GCM(plaintext, dekKey, nonce, aad);

  return {
    id: memoryId,
    ciphertext,
    nonce,
    authTag,
    dekId,
    contentHash,
    encryptedAt: new Date(),
    aad,
  };
}

/**
 * Decrypt a memory chunk and verify integrity
 * 
 * @param encryptedMemory - Encrypted memory record
 * @param dekKey - DEK key material
 * @returns Decrypted memory with verification status
 */
export function decryptMemory(
  encryptedMemory: EncryptedMemory,
  dekKey: Uint8Array
): DecryptedMemory {
  const plaintext = decryptAES256GCM(
    encryptedMemory.ciphertext,
    encryptedMemory.authTag,
    dekKey,
    encryptedMemory.nonce,
    encryptedMemory.aad
  );

  // Verify content integrity
  const computedHash = computeHash(plaintext);
  const integrityVerified = constantTimeEqual(computedHash, encryptedMemory.contentHash);

  return {
    id: encryptedMemory.id,
    plaintext,
    integrityVerified,
    decryptedAt: new Date(),
  };
}

/**
 * Constant-time comparison to prevent timing attacks
 */
export function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) {
    return false;
  }
  
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= (a[i] ?? 0) ^ (b[i] ?? 0);
  }
  
  return result === 0;
}

/**
 * Secure memory wipe - overwrite key material with zeros
 * Note: In JS this is best-effort due to GC, but still reduces exposure window
 */
export function secureWipe(data: Uint8Array): void {
  data.fill(0);
}

/**
 * Convert string to Uint8Array (UTF-8)
 */
export function stringToBytes(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

/**
 * Convert Uint8Array to string (UTF-8)
 */
export function bytesToString(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}
