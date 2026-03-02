/**
 * Closedclaw Consent Module
 */

export * from "./types.js";

export {
  toCanonicalJSON,
  fromCanonicalJSON,
  createUnsignedReceipt,
  signReceipt,
  verifyReceipt,
  receiptToBinary,
  binaryToReceipt,
  ConsentReceiptManager,
  ConsentGate,
} from "./receipts.js";
