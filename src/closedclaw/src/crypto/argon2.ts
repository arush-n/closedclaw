/**
 * Closedclaw Argon2id Key Derivation
 * 
 * Derives the Key Encryption Key (KEK) from user passphrase.
 * 
 * Argon2id properties:
 * - Memory-hard: Resistant to GPU/ASIC attacks
 * - Time-hard: Configurable iterations
 * - Data-dependent & data-independent passes: Best of both Argon2d and Argon2i
 * 
 * Default parameters (OWASP 2024 recommendations):
 * - Memory: 64 MB
 * - Iterations: 3
 * - Parallelism: 4
 * - Output: 256-bit (32 bytes)
 */

import { randomBytes } from "@noble/ciphers/webcrypto";
import { v4 as uuidv4 } from "uuid";
import type { KeyEncryptionKey, Argon2idParams, DEFAULT_ARGON2_PARAMS } from "./types";

/** Salt size in bytes (128-bit minimum recommended) */
export const SALT_SIZE = 16;

/** Output key size in bytes (256-bit) */
export const KEY_SIZE = 32;

/**
 * Generate a cryptographically secure random salt
 */
export function generateSalt(): Uint8Array {
  return randomBytes(SALT_SIZE);
}

/**
 * Argon2id implementation using WebCrypto-compatible approach
 * 
 * Note: Browser/Node.js native Argon2 support varies. This implementation
 * provides a consistent interface that can be backed by:
 * - argon2-browser (WASM-based, browser-compatible)
 * - @node-rs/argon2 (native, Node.js only)
 * - hash-wasm (pure WASM, universal)
 */
export interface Argon2Provider {
  hash(
    password: Uint8Array,
    salt: Uint8Array,
    params: Argon2idParams
  ): Promise<Uint8Array>;
  
  verify(
    password: Uint8Array,
    hash: Uint8Array,
    salt: Uint8Array,
    params: Argon2idParams
  ): Promise<boolean>;
}

/**
 * Default Argon2 parameters per OWASP 2024
 */
export const DEFAULT_PARAMS: Argon2idParams = {
  memoryCost: 65536,  // 64 MB
  timeCost: 3,        // 3 iterations
  parallelism: 4,     // 4 threads
  hashLength: 32,     // 256-bit output
};

/**
 * WASM-based Argon2id implementation using hash-wasm
 * This is the recommended provider for cross-platform compatibility
 */
export async function createWasmArgon2Provider(): Promise<Argon2Provider> {
  // Dynamic import to avoid bundling issues
  const hashWasm = await import("hash-wasm");
  
  return {
    async hash(
      password: Uint8Array,
      salt: Uint8Array,
      params: Argon2idParams
    ): Promise<Uint8Array> {
      const result = await hashWasm.argon2id({
        password,
        salt,
        parallelism: params.parallelism,
        iterations: params.timeCost,
        memorySize: params.memoryCost,
        hashLength: params.hashLength,
        outputType: "binary",
      });
      return new Uint8Array(result);
    },

    async verify(
      password: Uint8Array,
      expectedHash: Uint8Array,
      salt: Uint8Array,
      params: Argon2idParams
    ): Promise<boolean> {
      const computedHash = await this.hash(password, salt, params);
      return constantTimeEqual(computedHash, expectedHash);
    },
  };
}

/**
 * Constant-time comparison to prevent timing attacks
 */
function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
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
 * Key Derivation Function (KDF) for generating KEK from passphrase
 */
export class KeyDerivation {
  private provider: Argon2Provider;
  private params: Argon2idParams;

  constructor(provider: Argon2Provider, params: Argon2idParams = DEFAULT_PARAMS) {
    this.provider = provider;
    this.params = params;
  }

  /**
   * Derive a KEK from user passphrase
   * 
   * @param passphrase - User's passphrase (string or bytes)
   * @param salt - Random salt (generate with generateSalt())
   * @param version - Key version (default: 1)
   * @returns KEK ready for envelope encryption
   */
  async deriveKEK(
    passphrase: string | Uint8Array,
    salt: Uint8Array,
    version: number = 1
  ): Promise<KeyEncryptionKey> {
    const passphraseBytes = typeof passphrase === "string"
      ? new TextEncoder().encode(passphrase)
      : passphrase;

    const keyMaterial = await this.provider.hash(passphraseBytes, salt, this.params);

    return {
      id: `kek_${uuidv4()}`,
      key: keyMaterial,
      salt,
      createdAt: new Date(),
      version,
    };
  }

  /**
   * Verify a passphrase against stored KEK parameters
   * 
   * @param passphrase - User's passphrase to verify
   * @param kek - Existing KEK to verify against
   * @returns true if passphrase is correct
   */
  async verifyPassphrase(
    passphrase: string | Uint8Array,
    kek: KeyEncryptionKey
  ): Promise<boolean> {
    const passphraseBytes = typeof passphrase === "string"
      ? new TextEncoder().encode(passphrase)
      : passphrase;

    return this.provider.verify(passphraseBytes, kek.key, kek.salt, this.params);
  }

  /**
   * Rotate KEK with new passphrase
   * 
   * @param newPassphrase - New passphrase
   * @param oldKek - Existing KEK (for version increment)
   * @returns New KEK with incremented version
   */
  async rotateKEK(
    newPassphrase: string | Uint8Array,
    oldKek: KeyEncryptionKey
  ): Promise<KeyEncryptionKey> {
    const newSalt = generateSalt();
    return this.deriveKEK(newPassphrase, newSalt, oldKek.version + 1);
  }

  /**
   * Get current parameters
   */
  getParams(): Argon2idParams {
    return { ...this.params };
  }
}

/**
 * Create a KeyDerivation instance with default WASM provider
 */
export async function createKeyDerivation(
  params: Argon2idParams = DEFAULT_PARAMS
): Promise<KeyDerivation> {
  const provider = await createWasmArgon2Provider();
  return new KeyDerivation(provider, params);
}

/**
 * Passphrase strength requirements
 */
export interface PassphraseRequirements {
  minLength: number;
  requireUppercase: boolean;
  requireLowercase: boolean;
  requireNumbers: boolean;
  requireSpecial: boolean;
  minEntropy: number; // bits
}

/**
 * Default passphrase requirements
 */
export const DEFAULT_PASSPHRASE_REQUIREMENTS: PassphraseRequirements = {
  minLength: 12,
  requireUppercase: true,
  requireLowercase: true,
  requireNumbers: true,
  requireSpecial: false,
  minEntropy: 60, // 60 bits minimum
};

/**
 * Validate passphrase strength
 */
export function validatePassphrase(
  passphrase: string,
  requirements: PassphraseRequirements = DEFAULT_PASSPHRASE_REQUIREMENTS
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (passphrase.length < requirements.minLength) {
    errors.push(`Passphrase must be at least ${requirements.minLength} characters`);
  }

  if (requirements.requireUppercase && !/[A-Z]/.test(passphrase)) {
    errors.push("Passphrase must contain at least one uppercase letter");
  }

  if (requirements.requireLowercase && !/[a-z]/.test(passphrase)) {
    errors.push("Passphrase must contain at least one lowercase letter");
  }

  if (requirements.requireNumbers && !/[0-9]/.test(passphrase)) {
    errors.push("Passphrase must contain at least one number");
  }

  if (requirements.requireSpecial && !/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(passphrase)) {
    errors.push("Passphrase must contain at least one special character");
  }

  // Simple entropy estimation (not cryptographically rigorous, but useful for UX)
  const estimatedEntropy = estimateEntropy(passphrase);
  if (estimatedEntropy < requirements.minEntropy) {
    errors.push(`Passphrase entropy too low: ${estimatedEntropy.toFixed(0)} bits (minimum: ${requirements.minEntropy})`);
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}

/**
 * Estimate passphrase entropy (simple heuristic)
 */
function estimateEntropy(passphrase: string): number {
  let charsetSize = 0;
  
  if (/[a-z]/.test(passphrase)) charsetSize += 26;
  if (/[A-Z]/.test(passphrase)) charsetSize += 26;
  if (/[0-9]/.test(passphrase)) charsetSize += 10;
  if (/[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(passphrase)) charsetSize += 32;
  if (/\s/.test(passphrase)) charsetSize += 1;

  if (charsetSize === 0) return 0;
  
  return passphrase.length * Math.log2(charsetSize);
}

/**
 * Stored KEK metadata (without key material)
 * Safe to persist - does not contain the actual KEK
 */
export interface StoredKEKMetadata {
  id: string;
  salt: Uint8Array;
  version: number;
  createdAt: Date;
  params: Argon2idParams;
}

/**
 * Extract metadata from KEK for storage
 */
export function extractKEKMetadata(
  kek: KeyEncryptionKey,
  params: Argon2idParams
): StoredKEKMetadata {
  return {
    id: kek.id,
    salt: kek.salt,
    version: kek.version,
    createdAt: kek.createdAt,
    params,
  };
}
