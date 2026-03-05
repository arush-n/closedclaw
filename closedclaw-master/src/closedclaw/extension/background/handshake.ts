/**
 * Challenge-response handshake with the localhost Openclaw server.
 *
 * Flow:
 *   1. POST /addon/register  → send Ed25519 public key, get session_id + challenge
 *   2. Sign challenge with WebCrypto Ed25519 private key
 *   3. POST /addon/auth      → send signed challenge, get session_token
 *   4. Store session_token for subsequent API calls
 */

import { getOrCreateKeypair, signChallenge, type AddonKeypair } from "./crypto";

const SERVER_BASE = "http://localhost:8765";

export interface SessionState {
  sessionToken: string | null;
  sessionId: string | null;
  expiresAt: number; // epoch ms
  keypair: AddonKeypair | null;
}

let currentSession: SessionState = {
  sessionToken: null,
  sessionId: null,
  expiresAt: 0,
  keypair: null,
};

export function getSession(): SessionState {
  return currentSession;
}

export function isAuthenticated(): boolean {
  return !!currentSession.sessionToken && Date.now() < currentSession.expiresAt;
}

export async function authenticate(): Promise<SessionState> {
  // If we have a valid session, return it
  if (isAuthenticated()) return currentSession;

  const keypair = await getOrCreateKeypair();
  currentSession.keypair = keypair;

  // Step 1: Register addon public key
  const regResp = await fetch(`${SERVER_BASE}/addon/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ public_key: keypair.publicKeyB64 }),
  });

  if (!regResp.ok) {
    throw new Error(`Registration failed: ${regResp.status}`);
  }

  const regData = await regResp.json();
  const { session_id, challenge } = regData;
  currentSession.sessionId = session_id;

  // Step 2: Sign the challenge
  const signature = await signChallenge(keypair.privateKey, challenge);

  // Step 3: Authenticate with signed challenge
  const authResp = await fetch(`${SERVER_BASE}/addon/auth`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge: challenge, signature }),
  });

  if (!authResp.ok) {
    throw new Error(`Authentication failed: ${authResp.status}`);
  }

  const authData = await authResp.json();
  currentSession.sessionToken = authData.session_token;
  // Default 55 min expiry (server uses 60 min, refresh early)
  currentSession.expiresAt = Date.now() + 55 * 60 * 1000;

  // Persist token
  await chrome.storage.local.set({
    openclaw_session_token: authData.session_token,
    openclaw_session_expires: currentSession.expiresAt,
  });

  return currentSession;
}

export async function logout(): Promise<void> {
  if (currentSession.sessionToken) {
    try {
      await fetch(`${SERVER_BASE}/addon/logout`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Addon-Session": currentSession.sessionToken,
        },
      });
    } catch {
      // Best-effort logout
    }
  }

  currentSession = {
    sessionToken: null,
    sessionId: null,
    expiresAt: 0,
    keypair: null,
  };

  await chrome.storage.local.remove([
    "openclaw_session_token",
    "openclaw_session_expires",
  ]);
}

export async function apiCall(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const session = await authenticate();
  if (!session.sessionToken) {
    throw new Error("Not authenticated");
  }

  const headers = new Headers(options.headers || {});
  headers.set("X-Addon-Session", session.sessionToken);
  headers.set("Content-Type", "application/json");

  return fetch(`${SERVER_BASE}${path}`, { ...options, headers });
}
