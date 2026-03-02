/**
 * Closedclaw Consent Receipt Tests
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  toCanonicalJSON,
  fromCanonicalJSON,
  createUnsignedReceipt,
  signReceipt,
  verifyReceipt,
  receiptToBinary,
  binaryToReceipt,
  ConsentReceiptManager,
  ConsentGate,
} from "../src/consent/index.js";
import { generateKeyPair, stringToBytes } from "../src/crypto/index.js";
import type { SigningKeyPair, Redaction, SensitivityLevel } from "../src/crypto/types.js";

describe("Consent Receipts", () => {
  let keyPair: SigningKeyPair;

  beforeEach(() => {
    keyPair = generateKeyPair();
  });

  describe("Canonical JSON", () => {
    it("should produce deterministic JSON representation", () => {
      const memoryContent = stringToBytes("test content");
      const receipt = createUnsignedReceipt(
        "mem_123",
        memoryContent,
        "openai",
        [],
        2,
        "approve",
        "rule_001",
        keyPair.publicKey
      );

      const json1 = toCanonicalJSON(receipt);
      const json2 = toCanonicalJSON(receipt);

      expect(json1).toBe(json2);
    });

    it("should parse canonical JSON back to receipt", () => {
      const memoryContent = stringToBytes("test content");
      const original = createUnsignedReceipt(
        "mem_123",
        memoryContent,
        "anthropic",
        [{ entityType: "email", placeholder: "[EMAIL]" }],
        3,
        "approve_redacted",
        "rule_002",
        keyPair.publicKey
      );

      const json = toCanonicalJSON(original);
      const parsed = fromCanonicalJSON(json);

      expect(parsed.receiptId).toBe(original.receiptId);
      expect(parsed.memoryId).toBe(original.memoryId);
      expect(parsed.provider).toBe(original.provider);
      expect(parsed.redactions).toEqual(original.redactions);
    });
  });

  describe("Receipt Creation and Signing", () => {
    it("should create and sign a consent receipt", () => {
      const memoryContent = stringToBytes("My email is test@example.com");
      const redactions: Redaction[] = [
        { entityType: "email", placeholder: "[EMAIL]" },
      ];

      const unsigned = createUnsignedReceipt(
        "mem_456",
        memoryContent,
        "openai",
        redactions,
        2,
        "approve_redacted",
        "rule_sensitivity_2",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);

      expect(signed.signature).toBeDefined();
      expect(signed.signature.length).toBe(128); // 64 bytes in hex
    });

    it("should verify a valid consent receipt", () => {
      const memoryContent = stringToBytes("test data");
      const unsigned = createUnsignedReceipt(
        "mem_789",
        memoryContent,
        "google",
        [],
        1,
        "approve",
        "rule_auto",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);
      const result = verifyReceipt(signed, memoryContent);

      expect(result.signatureValid).toBe(true);
      expect(result.memoryHashValid).toBe(true);
      expect(result.error).toBeUndefined();
    });

    it("should detect tampered receipt", () => {
      const memoryContent = stringToBytes("original content");
      const unsigned = createUnsignedReceipt(
        "mem_abc",
        memoryContent,
        "openai",
        [],
        2,
        "approve",
        "rule_001",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);
      
      // Tamper with the receipt
      const tampered = { ...signed, provider: "anthropic" };
      const result = verifyReceipt(tampered);

      expect(result.signatureValid).toBe(false);
    });

    it("should detect memory content change", () => {
      const originalContent = stringToBytes("original");
      const modifiedContent = stringToBytes("modified");

      const unsigned = createUnsignedReceipt(
        "mem_def",
        originalContent,
        "openai",
        [],
        1,
        "approve",
        "rule_001",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);
      const result = verifyReceipt(signed, modifiedContent);

      expect(result.signatureValid).toBe(true);
      expect(result.memoryHashValid).toBe(false);
    });
  });

  describe("Binary Conversion", () => {
    it("should convert receipt to binary and back", () => {
      const memoryContent = stringToBytes("test");
      const unsigned = createUnsignedReceipt(
        "mem_bin",
        memoryContent,
        "openai",
        [{ entityType: "phone", placeholder: "[PHONE]" }],
        2,
        "approve_redacted",
        "rule_pii",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);
      const binary = receiptToBinary(signed);
      const restored = binaryToReceipt(binary);

      expect(restored.receiptId).toBe(signed.receiptId);
      expect(restored.memoryHash).toBe(signed.memoryHash);
      expect(restored.signature).toBe(signed.signature);
    });
  });

  describe("ConsentReceiptManager", () => {
    it("should create signed receipts", () => {
      const manager = new ConsentReceiptManager(keyPair);
      const memoryContent = stringToBytes("sensitive info");

      const receipt = manager.createReceipt(
        "mem_mgr_1",
        memoryContent,
        "anthropic",
        [],
        2,
        "approve",
        "rule_consent"
      );

      expect(receipt.signature).toBeDefined();
      expect(manager.verify(receipt).signatureValid).toBe(true);
    });

    it("should create denial receipts", () => {
      const manager = new ConsentReceiptManager(keyPair);
      const memoryContent = stringToBytes("highly sensitive");

      const receipt = manager.createDenialReceipt(
        "mem_denied",
        memoryContent,
        "openai",
        3,
        "rule_high_sensitivity"
      );

      expect(receipt.userDecision).toBe("deny");
      expect(receipt.redactions).toEqual([]);
    });

    it("should create redacted approval receipts", () => {
      const manager = new ConsentReceiptManager(keyPair);
      const memoryContent = stringToBytes("email@test.com and 555-1234");
      const redactions: Redaction[] = [
        { entityType: "email", placeholder: "[EMAIL]" },
        { entityType: "phone", placeholder: "[PHONE]" },
      ];

      const receipt = manager.createRedactedApprovalReceipt(
        "mem_redacted",
        memoryContent,
        "openai",
        redactions,
        2,
        "rule_pii"
      );

      expect(receipt.userDecision).toBe("approve_redacted");
      expect(receipt.redactions).toHaveLength(2);
    });
  });

  describe("ConsentGate", () => {
    it("should require consent for high sensitivity memories", () => {
      const gate = new ConsentGate({
        consentRequiredLevels: [2, 3],
      });

      const decision = gate.evaluate("test content", 2, "openai");
      expect(decision.consentRequired).toBe(true);
    });

    it("should not require consent for low sensitivity memories", () => {
      const gate = new ConsentGate({
        consentRequiredLevels: [2, 3],
      });

      const decision = gate.evaluate("test content", 1, "openai");
      expect(decision.consentRequired).toBe(false);
    });

    it("should detect PII for redaction", () => {
      const gate = new ConsentGate();

      const decision = gate.evaluate(
        "Contact me at john@example.com or 555-123-4567",
        1,
        "openai"
      );

      expect(decision.suggestedRedactions.length).toBeGreaterThan(0);
      const entityTypes = decision.suggestedRedactions.map((r) => r.entityType);
      expect(entityTypes).toContain("email");
      expect(entityTypes).toContain("phone");
    });

    it("should apply redactions to content", () => {
      const gate = new ConsentGate();
      const content = "Email: test@example.com, Phone: 555-123-4567";
      const redactions: Redaction[] = [
        { entityType: "email", placeholder: "[EMAIL]" },
        { entityType: "phone", placeholder: "[PHONE]" },
      ];

      const redacted = gate.applyRedactions(content, redactions);

      expect(redacted).toContain("[EMAIL]");
      expect(redacted).toContain("[PHONE]");
      expect(redacted).not.toContain("test@example.com");
    });

    it("should manage policy rules", () => {
      const gate = new ConsentGate();

      gate.addRule({
        id: "rule_test",
        description: "Test rule",
        sensitivityThreshold: 2,
        mandatory: true,
      });

      const config = gate.getConfig();
      expect(config.rules).toHaveLength(1);

      const removed = gate.removeRule("rule_test");
      expect(removed).toBe(true);
      expect(gate.getConfig().rules).toHaveLength(0);
    });
  });
});
