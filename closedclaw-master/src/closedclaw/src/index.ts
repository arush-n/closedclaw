/**
 * Closedclaw - Privacy-first personal data governance with cryptographic guarantees
 * 
 * Features:
 * - AES-256-GCM authenticated encryption for memory at rest
 * - Ed25519 digital signatures for consent receipts and audit logs
 * - Envelope encryption (KEK/DEK) for compartmentalized key management
 * - Argon2id key derivation for secure passphrase-to-key conversion
 * - Cryptographic deletion for GDPR Article 17 compliance
 * - Consent receipt system for AI data governance
 * - Audit trail with hash chain integrity
 * 
 * @example
 * ```typescript
 * import { createKeyDerivation, generateSalt, generateKeyPair, MemoryVault } from "@closedclaw/core";
 * 
 * // Initialize key derivation
 * const kdf = await createKeyDerivation();
 * const salt = generateSalt();
 * 
 * // Derive KEK from passphrase
 * const kek = await kdf.deriveKEK("user-passphrase", salt);
 * 
 * // Generate signing key pair
 * const signingKeyPair = generateKeyPair();
 * 
 * // Create vault
 * const vault = new MemoryVault(kek, signingKeyPair);
 * 
 * // Store encrypted memory
 * const memoryId = await vault.store("sensitive data", {
 *   sensitivityLevel: 2,
 *   ttlSeconds: 86400, // 24 hours
 * });
 * 
 * // Retrieve decrypted memory
 * const memory = await vault.retrieve(memoryId);
 * console.log(memory?.text);
 * 
 * // Cryptographically delete (GDPR Article 17 compliant)
 * await vault.delete(memoryId);
 * ```
 */

// Re-export all modules
export * from "./crypto/index";
export * from "./consent/index";
export * from "./vault/index";

// Version
export const VERSION = "0.1.0";
