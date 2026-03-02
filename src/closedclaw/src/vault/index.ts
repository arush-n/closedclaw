/**
 * Closedclaw Vault Module
 * 
 * Encrypted memory storage with cryptographic deletion.
 */

// Types
export * from "./types";

// Vault implementation
export {
  InMemoryVaultStorage,
  InMemoryAuditTrail,
  MemoryVault,
} from "./vault";
