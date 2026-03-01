/**
 * Closedclaw Cryptography Module
 * 
 * Comprehensive cryptographic primitives for privacy-first personal data governance.
 */

// Types
export * from "./types.js";

// AES-256-GCM Encryption
export {
  NONCE_SIZE,
  KEY_SIZE,
  TAG_SIZE,
  generateKey,
  generateNonce,
  computeHash,
  hashToHex,
  hexToHash,
  encryptAES256GCM,
  decryptAES256GCM,
  encryptMemory,
  decryptMemory,
  constantTimeEqual,
  secureWipe,
  stringToBytes,
  bytesToString,
} from "./aes.js";

// Ed25519 Digital Signatures
export {
  PRIVATE_KEY_SIZE,
  PUBLIC_KEY_SIZE,
  SIGNATURE_SIZE,
  generateKeyPair,
  derivePublicKey,
  sign,
  signWithMetadata,
  verify,
  verifySignature,
  publicKeyToHex,
  hexToPublicKey,
  signatureToHex,
  hexToSignature,
  hashForSigning,
} from "./ed25519.js";

// Envelope Encryption (KEK/DEK)
export {
  createDEK,
  wrapDEK,
  unwrapDEK,
  destroyDEK,
  markWrappedDEKDestroyed,
  rewrapDEK,
  isDEKExpired,
  getExpiredDEKs,
  DEKManager,
} from "./envelope.js";

// Argon2id Key Derivation
export {
  SALT_SIZE,
  DEFAULT_PARAMS,
  generateSalt,
  createWasmArgon2Provider,
  KeyDerivation,
  createKeyDerivation,
  DEFAULT_PASSPHRASE_REQUIREMENTS,
  validatePassphrase,
  extractKEKMetadata,
} from "./argon2.js";

export type { Argon2Provider, PassphraseRequirements, StoredKEKMetadata } from "./argon2.js";
