/**
 * Closedclaw Cryptography Types (standalone crypto module)
 */

export type MemoryId = string;
export type KeyId = string;

export interface EncryptedMemory {
  id: MemoryId;
  ciphertext: Uint8Array;
  nonce: Uint8Array;
  authTag: Uint8Array;
  dekId: KeyId;
  contentHash: Uint8Array;
  encryptedAt: Date;
  aad?: Uint8Array;
}

export interface DecryptedMemory {
  id: MemoryId;
  plaintext: Uint8Array;
  integrityVerified: boolean;
  decryptedAt: Date;
}
