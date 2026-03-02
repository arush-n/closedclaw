/**
 * Closedclaw Ed25519 Digital Signatures
 * 
 * Used for consent receipt signatures and audit log hash chain.
 */

import { ed25519 } from "@noble/curves/ed25519";
import { randomBytes } from "@noble/ciphers/webcrypto";
import { sha256 } from "@noble/hashes/sha256";
import { bytesToHex, hexToBytes } from "@noble/hashes/utils";
import type { SigningKeyPair, Signature } from "./types.js";

/** Ed25519 key sizes */
export const PRIVATE_KEY_SIZE = 32;
export const PUBLIC_KEY_SIZE = 32;
export const SIGNATURE_SIZE = 64;

/**
 * Generate a new Ed25519 key pair
 */
export function generateKeyPair(): SigningKeyPair {
  const privateKeyBytes = randomBytes(PRIVATE_KEY_SIZE);
  const publicKeyBytes = ed25519.getPublicKey(privateKeyBytes);

  return {
    publicKey: publicKeyBytes,
    privateKey: privateKeyBytes,
    createdAt: new Date(),
  };
}

/**
 * Derive public key from private key
 */
export function derivePublicKey(privateKey: Uint8Array): Uint8Array {
  if (privateKey.length !== PRIVATE_KEY_SIZE) {
    throw new Error(`Invalid private key size: expected ${PRIVATE_KEY_SIZE} bytes`);
  }
  return ed25519.getPublicKey(privateKey);
}

/**
 * Sign a message using Ed25519
 */
export function sign(message: Uint8Array, privateKey: Uint8Array): Uint8Array {
  if (privateKey.length !== PRIVATE_KEY_SIZE) {
    throw new Error(`Invalid private key size: expected ${PRIVATE_KEY_SIZE} bytes`);
  }
  return ed25519.sign(message, privateKey);
}

/**
 * Sign with full metadata
 */
export function signWithMetadata(message: Uint8Array, privateKey: Uint8Array): Signature {
  const publicKey = derivePublicKey(privateKey);
  const signature = sign(message, privateKey);

  return {
    signature,
    signerPublicKey: publicKey,
    signedAt: new Date(),
  };
}

/**
 * Verify an Ed25519 signature
 */
export function verify(
  signature: Uint8Array,
  message: Uint8Array,
  publicKey: Uint8Array
): boolean {
  if (signature.length !== SIGNATURE_SIZE) {
    throw new Error(`Invalid signature size: expected ${SIGNATURE_SIZE} bytes`);
  }
  if (publicKey.length !== PUBLIC_KEY_SIZE) {
    throw new Error(`Invalid public key size: expected ${PUBLIC_KEY_SIZE} bytes`);
  }

  try {
    return ed25519.verify(signature, message, publicKey);
  } catch {
    return false;
  }
}

/**
 * Verify signature with metadata
 */
export function verifySignature(sig: Signature, message: Uint8Array): boolean {
  return verify(sig.signature, message, sig.signerPublicKey);
}

/**
 * Convert public key to hex string
 */
export function publicKeyToHex(publicKey: Uint8Array): string {
  return bytesToHex(publicKey);
}

/**
 * Convert hex string to public key
 */
export function hexToPublicKey(hex: string): Uint8Array {
  const bytes = hexToBytes(hex);
  if (bytes.length !== PUBLIC_KEY_SIZE) {
    throw new Error(`Invalid public key hex: expected ${PUBLIC_KEY_SIZE} bytes`);
  }
  return bytes;
}

/**
 * Convert signature to hex string
 */
export function signatureToHex(signature: Uint8Array): string {
  return bytesToHex(signature);
}

/**
 * Convert hex string to signature
 */
export function hexToSignature(hex: string): Uint8Array {
  const bytes = hexToBytes(hex);
  if (bytes.length !== SIGNATURE_SIZE) {
    throw new Error(`Invalid signature hex: expected ${SIGNATURE_SIZE} bytes`);
  }
  return bytes;
}

/**
 * Hash data before signing (for large messages)
 */
export function hashForSigning(data: Uint8Array): Uint8Array {
  return sha256(data);
}
