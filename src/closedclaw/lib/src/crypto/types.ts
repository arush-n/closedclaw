/**
 * Closedclaw Cryptography Types
 * 
 * Core type definitions for the cryptographic layer supporting:
 * - AES-256-GCM authenticated encryption
 * - Ed25519 digital signatures
 * - Envelope encryption (DEK/KEK)
 * - Argon2id key derivation
 * - Cryptographic deletion
 */

/** Unique identifier types */
export type MemoryId = string;
export type ReceiptId = string;
export type KeyId = string;
export type AuditEntryId = string;

/** Memory sensitivity levels (0-3) */
export type SensitivityLevel = 0 | 1 | 2 | 3;

/** User decision on consent */
export type UserDecision = "approve" | "approve_redacted" | "deny";

/**
 * Redaction entry - entity to redact before sharing
 */
export interface Redaction {
  /** Type of entity redacted (e.g., "email", "phone", "ssn") */
  entityType: string;
  /** Placeholder used (e.g., "[EMAIL]", "[PHONE]") */
  placeholder: string;
}

/**
 * Data Encryption Key (DEK) - unique per memory chunk
 * 256-bit key for AES-256-GCM encryption
 */
export interface DataEncryptionKey {
  /** Unique identifier for this DEK */
  id: KeyId;
  /** Raw 256-bit key material (32 bytes) */
  key: Uint8Array;
  /** Creation timestamp */
  createdAt: Date;
  /** Memory ID this DEK encrypts */
  memoryId: MemoryId;
  /** Whether this DEK has been destroyed (cryptographic deletion) */
  destroyed: boolean;
  /** TTL expiry timestamp (if set) */
  expiresAt?: Date;
}

/**
 * Key Encryption Key (KEK) - master key derived from user passphrase
 * Used to wrap/unwrap DEKs (envelope encryption)
 */
export interface KeyEncryptionKey {
  /** Unique identifier for this KEK */
  id: KeyId;
  /** Raw 256-bit key material (32 bytes) */
  key: Uint8Array;
  /** Salt used in Argon2id derivation */
  salt: Uint8Array;
  /** Creation timestamp */
  createdAt: Date;
  /** Version for key rotation */
  version: number;
}

/**
 * Wrapped DEK - DEK encrypted by KEK for secure storage
 */
export interface WrappedDEK {
  /** DEK identifier */
  dekId: KeyId;
  /** Memory ID this DEK encrypts */
  memoryId: MemoryId;
  /** Encrypted DEK (AES-256-GCM ciphertext) */
  encryptedKey: Uint8Array;
  /** Nonce used for DEK encryption */
  nonce: Uint8Array;
  /** Authentication tag */
  authTag: Uint8Array;
  /** KEK version used to wrap this DEK */
  kekVersion: number;
  /** Creation timestamp */
  createdAt: Date;
  /** TTL expiry timestamp (if set) */
  expiresAt?: Date;
  /** Whether this DEK has been destroyed */
  destroyed: boolean;
  /** Destruction timestamp (if destroyed) */
  destroyedAt?: Date;
}

/**
 * Encrypted memory chunk - ciphertext with metadata
 */
export interface EncryptedMemory {
  /** Unique memory identifier */
  id: MemoryId;
  /** AES-256-GCM ciphertext */
  ciphertext: Uint8Array;
  /** 96-bit nonce/IV */
  nonce: Uint8Array;
  /** 128-bit authentication tag */
  authTag: Uint8Array;
  /** DEK identifier used for encryption */
  dekId: KeyId;
  /** SHA-256 hash of original plaintext (for integrity verification) */
  contentHash: Uint8Array;
  /** Encryption timestamp */
  encryptedAt: Date;
  /** Additional authenticated data (not encrypted, but authenticated) */
  aad?: Uint8Array;
}

/**
 * Decrypted memory - plaintext with verification status
 */
export interface DecryptedMemory {
  /** Unique memory identifier */
  id: MemoryId;
  /** Plaintext content */
  plaintext: Uint8Array;
  /** Whether content hash matches original */
  integrityVerified: boolean;
  /** Decryption timestamp */
  decryptedAt: Date;
}

/**
 * Ed25519 key pair for digital signatures
 */
export interface SigningKeyPair {
  /** 32-byte public key */
  publicKey: Uint8Array;
  /** 32-byte private key */
  privateKey: Uint8Array;
  /** Key creation timestamp */
  createdAt: Date;
}

/**
 * Ed25519 signature with metadata
 */
export interface Signature {
  /** 64-byte Ed25519 signature */
  signature: Uint8Array;
  /** Public key of signer */
  signerPublicKey: Uint8Array;
  /** Timestamp of signing */
  signedAt: Date;
}

/**
 * Audit log entry with hash chain
 */
export interface AuditEntry {
  /** Unique audit entry identifier */
  id: AuditEntryId;
  /** Entry type */
  type: AuditEntryType;
  /** Timestamp */
  timestamp: string;
  /** Related entity ID (memory, consent receipt, etc.) */
  entityId: string;
  /** Entity type */
  entityType: "memory" | "consent_receipt" | "key" | "policy";
  /** Action performed */
  action: string;
  /** Additional metadata */
  metadata?: Record<string, unknown>;
  /** SHA-256 hash of this entry's content */
  entryHash: Uint8Array;
  /** SHA-256 hash of previous entry (hash chain) */
  previousHash: Uint8Array;
  /** Ed25519 signature over entry */
  signature: Uint8Array;
}

export type AuditEntryType =
  | "memory_encrypted"
  | "memory_decrypted"
  | "memory_deleted"
  | "dek_created"
  | "dek_destroyed"
  | "consent_granted"
  | "consent_denied"
  | "key_rotated"
  | "policy_changed";

/**
 * Argon2id key derivation parameters
 */
export interface Argon2idParams {
  /** Memory cost in KiB (default: 65536 = 64MB) */
  memoryCost: number;
  /** Time cost / iterations (default: 3) */
  timeCost: number;
  /** Degree of parallelism (default: 4) */
  parallelism: number;
  /** Output key length in bytes (default: 32 for 256-bit) */
  hashLength: number;
}

/**
 * Cryptographic deletion result
 */
export interface DeletionResult {
  /** Memory ID deleted */
  memoryId: MemoryId;
  /** DEK ID destroyed */
  dekId: KeyId;
  /** Whether ciphertext remains in database */
  ciphertextRetained: boolean;
  /** Deletion timestamp */
  deletedAt: Date;
  /** Audit entry for this deletion */
  auditEntry: AuditEntry;
  /** Compliant with GDPR Article 17 */
  gdprCompliant: boolean;
}

/**
 * Default Argon2id parameters (OWASP recommended)
 */
export const DEFAULT_ARGON2_PARAMS: Argon2idParams = {
  memoryCost: 65536, // 64 MB
  timeCost: 3,       // 3 iterations
  parallelism: 4,    // 4 parallel threads
  hashLength: 32,    // 256-bit output
};
