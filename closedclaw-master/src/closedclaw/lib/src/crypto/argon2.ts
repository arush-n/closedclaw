/**
 * Closedclaw Argon2id Key Derivation
 * 
 * Derives KEK from user passphrase using memory-hard Argon2id.
 */

import { randomBytes } from "@noble/ciphers/webcrypto";
import { v4 as uuidv4 } from "uuid";
import type { KeyEncryptionKey, Argon2idParams } from "./types.js";

/** Salt size in bytes (128-bit minimum) */
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
 * Argon2 provider interface
 */
export interface Argon2Provider {
  hash(
    password: Uint8Array,
    salt: Uint8Array,
    params: Argon2idParams
  ): Promise<Uint8Array>;
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
 * Constant-time comparison
 */
function constantTimeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let result = 0;
  for (let i = 0; i < a.length; i++) {
    result |= (a[i] ?? 0) ^ (b[i] ?? 0);
  }
  return result === 0;
}

/**
 * WASM-based Argon2id implementation using hash-wasm
 */
export async function createWasmArgon2Provider(): Promise<Argon2Provider> {
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
  };
}

/**
 * Key Derivation Function for generating KEK from passphrase
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
   * Verify a passphrase against stored KEK
   */
  async verifyPassphrase(
    passphrase: string | Uint8Array,
    kek: KeyEncryptionKey
  ): Promise<boolean> {
    const passphraseBytes = typeof passphrase === "string"
      ? new TextEncoder().encode(passphrase)
      : passphrase;

    const computedKey = await this.provider.hash(passphraseBytes, kek.salt, this.params);
    return constantTimeEqual(computedKey, kek.key);
  }

  /**
   * Rotate KEK with new passphrase
   */
  async rotateKEK(
    newPassphrase: string | Uint8Array,
    oldKek: KeyEncryptionKey
  ): Promise<KeyEncryptionKey> {
    const newSalt = generateSalt();
    return this.deriveKEK(newPassphrase, newSalt, oldKek.version + 1);
  }

  getParams(): Argon2idParams {
    return { ...this.params };
  }
}

/**
 * Create a KeyDerivation instance with WASM provider
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
  minEntropy: number;
}

export const DEFAULT_PASSPHRASE_REQUIREMENTS: PassphraseRequirements = {
  minLength: 12,
  requireUppercase: true,
  requireLowercase: true,
  requireNumbers: true,
  requireSpecial: false,
  minEntropy: 60,
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

  const estimatedEntropy = estimateEntropy(passphrase);
  if (estimatedEntropy < requirements.minEntropy) {
    errors.push(`Passphrase entropy too low: ${estimatedEntropy.toFixed(0)} bits (minimum: ${requirements.minEntropy})`);
  }

  return { valid: errors.length === 0, errors };
}

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
