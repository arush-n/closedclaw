/**
 * @closedclaw/crypto
 *
 * Cryptographic privacy layer for personal data governance
 *
 * Features:
 * - AES-256-GCM encryption for memory at rest
 * - Ed25519 signed consent receipts
 * - Envelope encryption (KEK/DEK two-tier hierarchy)
 * - Argon2id passphrase-to-KEK derivation
 * - Cryptographic deletion on TTL expiry (GDPR Article 17)
 * - Tamper-evident audit log with hash chains
 */

// Crypto module - export all types with clear naming
export {
  // Types
  type MemoryId,
  type KeyId,
  type AuditEntryId,
  type SensitivityLevel,
  type UserDecision,
  type Redaction,
  type DataEncryptionKey,
  type KeyEncryptionKey,
  type WrappedDEK,
  type EncryptedMemory,
  type DecryptedMemory,
  type SigningKeyPair,
  type Signature,
  type AuditEntry,
  type Argon2idParams,
  type DeletionResult as CryptoDeletionResult,
  type ReceiptId as CryptoReceiptId,
  DEFAULT_ARGON2_PARAMS,
  // AES functions
  encryptAES256GCM,
  decryptAES256GCM,
  encryptMemory,
  decryptMemory,
  generateNonce,
  generateKey,
  computeHash,
  secureWipe,
  hashToHex,
  hexToHash,
  constantTimeEqual,
  stringToBytes,
  bytesToString,
  NONCE_SIZE,
  KEY_SIZE,
  TAG_SIZE,
  // Ed25519 functions
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
  hashForSigning,
  PRIVATE_KEY_SIZE,
  PUBLIC_KEY_SIZE,
  SIGNATURE_SIZE,
  // Envelope functions
  createDEK,
  wrapDEK,
  unwrapDEK,
  destroyDEK,
  markWrappedDEKDestroyed,
  rewrapDEK,
  isDEKExpired,
  getExpiredDEKs,
  DEKManager,
  // Argon2id functions
  createKeyDerivation,
  validatePassphrase,
  createWasmArgon2Provider,
  KeyDerivation,
} from "./crypto/index.js";

// Consent module
export {
  type ReceiptId,
  type UnsignedConsentReceipt,
  type SignedConsentReceipt,
  type ConsentReceiptBinary,
  type VerificationResult,
  type PolicyRule,
  type ConsentDecision,
  type ConsentGateConfig,
  type ConsentReceiptQuery,
  type ConsentReceiptStore,
  toCanonicalJSON,
  fromCanonicalJSON,
  createUnsignedReceipt,
  signReceipt,
  verifyReceipt,
  receiptToBinary,
  binaryToReceipt,
  ConsentReceiptManager,
  ConsentGate,
} from "./consent/index.js";

// Vault module
export {
  type MemoryMetadata,
  type VaultEntry,
  type VaultConfig,
  type VaultStorageBackend,
  type MemoryFilter,
  type VaultStats,
  type DeletionResult,
  type KEKRotationResult,
  type StoreResult,
  type RetrievalResult,
  type AuditLog,
  type VaultAuditEntry,
  InMemoryStorage,
  InMemoryAuditLog,
  MemoryVault,
} from "./vault/index.js";
