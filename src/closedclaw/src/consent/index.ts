/**
 * Closedclaw Consent Module
 * 
 * Cryptographically signed consent receipts for GDPR compliance
 * and AI data governance.
 */

// Types
export * from "./types";

// Receipt operations
export {
  // Canonical JSON
  toCanonicalJSON,
  fromCanonicalJSON,
  // Receipt creation
  createUnsignedReceipt,
  signReceipt,
  // Verification
  verifyReceipt,
  // Conversion
  receiptToBinary,
  binaryToReceipt,
  // Manager
  ConsentReceiptManager,
  // Gate
  ConsentGate,
} from "./receipts";
