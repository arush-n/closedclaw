/**
 * Browser-native Ed25519 keypair management via WebCrypto.
 *
 * Generates and persists an addon identity keypair in extension storage.
 * Used for the challenge-response handshake with the localhost server.
 */

const STORAGE_KEY_PRIV = "openclaw_ed25519_private";
const STORAGE_KEY_PUB = "openclaw_ed25519_public";

export interface AddonKeypair {
  privateKey: CryptoKey;
  publicKeyRaw: Uint8Array;
  publicKeyB64: string;
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = "";
  for (const b of bytes) binary += String.fromCharCode(b);
  return btoa(binary);
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

export async function getOrCreateKeypair(): Promise<AddonKeypair> {
  // Try loading from storage
  const stored = await chrome.storage.local.get([STORAGE_KEY_PRIV, STORAGE_KEY_PUB]);

  if (stored[STORAGE_KEY_PRIV] && stored[STORAGE_KEY_PUB]) {
    const privJwk = JSON.parse(stored[STORAGE_KEY_PRIV]);
    const privateKey = await crypto.subtle.importKey(
      "jwk",
      privJwk,
      { name: "Ed25519" },
      false,
      ["sign"]
    );
    const pubRaw = new Uint8Array(base64ToArrayBuffer(stored[STORAGE_KEY_PUB]));
    return {
      privateKey,
      publicKeyRaw: pubRaw,
      publicKeyB64: stored[STORAGE_KEY_PUB],
    };
  }

  // Generate new keypair
  const keypair = await crypto.subtle.generateKey(
    { name: "Ed25519" },
    true,
    ["sign", "verify"]
  );

  // Export private as JWK for storage
  const privJwk = await crypto.subtle.exportKey("jwk", keypair.privateKey);

  // Export public as raw bytes
  const pubRaw = await crypto.subtle.exportKey("raw", keypair.publicKey);
  const pubB64 = arrayBufferToBase64(pubRaw);

  // Re-import private as non-extractable
  const privateKey = await crypto.subtle.importKey(
    "jwk",
    privJwk,
    { name: "Ed25519" },
    false,
    ["sign"]
  );

  // Persist
  await chrome.storage.local.set({
    [STORAGE_KEY_PRIV]: JSON.stringify(privJwk),
    [STORAGE_KEY_PUB]: pubB64,
  });

  return {
    privateKey,
    publicKeyRaw: new Uint8Array(pubRaw),
    publicKeyB64: pubB64,
  };
}

export async function signChallenge(
  privateKey: CryptoKey,
  challengeB64: string
): Promise<string> {
  const challengeBytes = base64ToArrayBuffer(challengeB64);
  const sig = await crypto.subtle.sign("Ed25519", privateKey, challengeBytes);
  return arrayBufferToBase64(sig);
}
