/**
 * Closedclaw Cryptography Module
 * 
 * Comprehensive cryptographic primitives for privacy-first personal data governance.
 * 
 * Features:
 * - AES-256-GCM authenticated encryption for memory at rest
 * - Ed25519 digital signatures for consent receipts and audit logs
 * - Envelope encryption (KEK/DEK) for compartmentalized key management
 * - Argon2id key derivation for secure passphrase-to-key conversion
 * - Cryptographic deletion for GDPR Article 17 compliance
 */

// Types
export * from "./types";

// AES-256-GCM Encryption
export {
  // Constants
  NONCE_SIZE,
  KEY_SIZE,
  TAG_SIZE,
  // Key/Nonce generation
  generateKey,
  generateNonce,
  // Hash utilities
  computeHash,
  hashToHex,
  hexToHash,
  // Low-level encryption
  encryptAES256GCM,
  decryptAES256GCM,
  // High-level memory encryption
  encryptMemory,
  decryptMemory,
  // Utilities
  constantTimeEqual,
  secureWipe,
  stringToBytes,
  bytesToString,
} from "./aes";

// Ed25519 Digital Signatures
export {
  // Constants
  PRIVATE_KEY_SIZE,
  PUBLIC_KEY_SIZE,
  SIGNATURE_SIZE,
  // Key generation
  generateKeyPair,
  derivePublicKey,
  // Signing
  sign,
  signWithMetadata,
  // Verification
  verify,
  verifySignature,
  // Utilities
  publicKeyToHex,
  hexToPublicKey,
  signatureToHex,
  hexToSignature,
  hashForSigning,
} from "./ed25519";

// Envelope Encryption (KEK/DEK)
export {
  // DEK operations
  createDEK,
  wrapDEK,
  unwrapDEK,
  destroyDEK,
  markWrappedDEKDestroyed,
  rewrapDEK,
  // TTL handling
  isDEKExpired,
  getExpiredDEKs,
  // Manager
  DEKManager,
} from "./envelope";

// Argon2id Key Derivation
export {
  // Constants
  SALT_SIZE,
  DEFAULT_PARAMS,
  // Salt generation
  generateSalt,
  // Provider
  createWasmArgon2Provider,
  // Key derivation
  KeyDerivation,
  createKeyDerivation,
  // Passphrase validation
  DEFAULT_PASSPHRASE_REQUIREMENTS,
  validatePassphrase,
  extractKEKMetadata,
} from "./argon2";

export type { Argon2Provider, PassphraseRequirements, StoredKEKMetadata } from "./argon2";
