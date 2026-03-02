/**
 * Closedclaw Envelope Encryption (KEK/DEK)
 * 
 * Two-tier key hierarchy for compartmentalized encryption.
 */

import { v4 as uuidv4 } from "uuid";
import {
  encryptAES256GCM,
  decryptAES256GCM,
  generateKey,
  generateNonce,
  secureWipe,
  KEY_SIZE,
} from "./aes";
import type {
  DataEncryptionKey,
  KeyEncryptionKey,
  WrappedDEK,
  MemoryId,
  KeyId,
} from "./types";

/**
 * Create a new Data Encryption Key for a memory chunk
 */
export function createDEK(memoryId: MemoryId, expiresAt?: Date): DataEncryptionKey {
  return {
    id: `dek_${uuidv4()}`,
    key: generateKey(),
    createdAt: new Date(),
    memoryId,
    destroyed: false,
    expiresAt,
  };
}

/**
 * Wrap a DEK using the KEK (envelope encryption)
 */
export function wrapDEK(dek: DataEncryptionKey, kek: KeyEncryptionKey): WrappedDEK {
  if (dek.destroyed) {
    throw new Error("Cannot wrap a destroyed DEK");
  }
  if (kek.key.length !== KEY_SIZE) {
    throw new Error(`Invalid KEK size: expected ${KEY_SIZE} bytes`);
  }

  const nonce = generateNonce();
  const { ciphertext, authTag } = encryptAES256GCM(dek.key, kek.key, nonce);

  return {
    dekId: dek.id,
    memoryId: dek.memoryId,
    encryptedKey: ciphertext,
    nonce,
    authTag,
    kekVersion: kek.version,
    createdAt: dek.createdAt,
    expiresAt: dek.expiresAt,
    destroyed: false,
  };
}

/**
 * Unwrap a DEK using the KEK
 */
export function unwrapDEK(wrappedDek: WrappedDEK, kek: KeyEncryptionKey): DataEncryptionKey {
  if (wrappedDek.destroyed) {
    throw new Error("Cannot unwrap a destroyed DEK - data is permanently unrecoverable");
  }
  if (wrappedDek.kekVersion !== kek.version) {
    throw new Error(
      `KEK version mismatch: DEK wrapped with v${wrappedDek.kekVersion}, ` +
      `but provided KEK is v${kek.version}`
    );
  }

  const keyMaterial = decryptAES256GCM(
    wrappedDek.encryptedKey,
    wrappedDek.authTag,
    kek.key,
    wrappedDek.nonce
  );

  return {
    id: wrappedDek.dekId,
    key: keyMaterial,
    createdAt: wrappedDek.createdAt,
    memoryId: wrappedDek.memoryId,
    destroyed: false,
    expiresAt: wrappedDek.expiresAt,
  };
}

/**
 * Destroy a DEK (cryptographic deletion - GDPR Article 17)
 */
export function destroyDEK(dek: DataEncryptionKey): DataEncryptionKey {
  secureWipe(dek.key);
  return { ...dek, destroyed: true };
}

/**
 * Mark a wrapped DEK as destroyed
 */
export function markWrappedDEKDestroyed(wrappedDek: WrappedDEK): WrappedDEK {
  secureWipe(wrappedDek.encryptedKey);
  secureWipe(wrappedDek.nonce);
  secureWipe(wrappedDek.authTag);

  return {
    ...wrappedDek,
    destroyed: true,
    destroyedAt: new Date(),
  };
}

/**
 * Re-wrap a DEK with a new KEK (for key rotation)
 */
export function rewrapDEK(
  wrappedDek: WrappedDEK,
  oldKek: KeyEncryptionKey,
  newKek: KeyEncryptionKey
): WrappedDEK {
  const dek = unwrapDEK(wrappedDek, oldKek);
  const newWrappedDek = wrapDEK(dek, newKek);
  secureWipe(dek.key);
  return newWrappedDek;
}

/**
 * Check if a DEK has expired
 */
export function isDEKExpired(dek: DataEncryptionKey | WrappedDEK): boolean {
  if (!dek.expiresAt) return false;
  return new Date() >= dek.expiresAt;
}

/**
 * Get expired DEKs from a list
 */
export function getExpiredDEKs(deks: WrappedDEK[]): WrappedDEK[] {
  return deks.filter((dek) => !dek.destroyed && isDEKExpired(dek));
}

/**
 * DEK Manager for batch operations
 */
export class DEKManager {
  private deks: Map<KeyId, WrappedDEK> = new Map();
  private kek: KeyEncryptionKey;

  constructor(kek: KeyEncryptionKey) {
    this.kek = kek;
  }

  /** Create a new DEK and wrap it with the KEK */
  createAndWrap(memoryId: MemoryId, expiresAt?: Date): WrappedDEK {
    const dek = createDEK(memoryId, expiresAt);
    const wrappedDek = wrapDEK(dek, this.kek);
    this.deks.set(dek.id, wrappedDek);
    secureWipe(dek.key);
    return wrappedDek;
  }

  /** Create a DEK and store it (returns the DEK with key material) */
  createAndStore(memoryId: MemoryId, expiresAt?: Date): DataEncryptionKey {
    const dek = createDEK(memoryId, expiresAt);
    const wrappedDek = wrapDEK(dek, this.kek);
    this.deks.set(dek.id, wrappedDek);
    return dek;
  }

  /** Unwrap a DEK to access the key material */
  unwrap(wrappedDek: WrappedDEK): DataEncryptionKey {
    return unwrapDEK(wrappedDek, this.kek);
  }

  /** Re-wrap a DEK with a new KEK */
  rewrapWithNewKEK(wrappedDek: WrappedDEK, newKek: KeyEncryptionKey): WrappedDEK {
    return rewrapDEK(wrappedDek, this.kek, newKek);
  }

  retrieve(dekId: KeyId): DataEncryptionKey {
    const wrappedDek = this.deks.get(dekId);
    if (!wrappedDek) {
      throw new Error(`DEK not found: ${dekId}`);
    }
    return unwrapDEK(wrappedDek, this.kek);
  }

  destroy(dekId: KeyId): WrappedDEK {
    const wrappedDek = this.deks.get(dekId);
    if (!wrappedDek) {
      throw new Error(`DEK not found: ${dekId}`);
    }
    const destroyedDek = markWrappedDEKDestroyed(wrappedDek);
    this.deks.set(dekId, destroyedDek);
    return destroyedDek;
  }

  getByMemoryId(memoryId: MemoryId): WrappedDEK | undefined {
    for (const dek of Array.from(this.deks.values())) {
      if (dek.memoryId === memoryId) return dek;
    }
    return undefined;
  }

  processExpiredDEKs(): WrappedDEK[] {
    const expired = getExpiredDEKs(Array.from(this.deks.values()));
    const destroyed: WrappedDEK[] = [];
    for (const dek of expired) {
      const destroyedDek = this.destroy(dek.dekId);
      destroyed.push(destroyedDek);
    }
    return destroyed;
  }

  rotateKEK(newKek: KeyEncryptionKey): void {
    const oldKek = this.kek;
    for (const [dekId, wrappedDek] of Array.from(this.deks.entries())) {
      if (!wrappedDek.destroyed) {
        const rewrapped = rewrapDEK(wrappedDek, oldKek, newKek);
        this.deks.set(dekId, rewrapped);
      }
    }
    this.kek = newKek;
    secureWipe(oldKek.key);
  }

  exportAll(): WrappedDEK[] {
    return Array.from(this.deks.values());
  }

  importAll(wrappedDeks: WrappedDEK[]): void {
    for (const dek of wrappedDeks) {
      this.deks.set(dek.dekId, dek);
    }
  }
}
