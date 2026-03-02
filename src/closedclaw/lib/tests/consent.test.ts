/**
 * Consent receipt tests
 */

import { describe, it, expect, beforeEach } from "vitest";
import {
  ConsentReceiptManager,
  ConsentGate,
  toCanonicalJSON,
  fromCanonicalJSON,
  signReceipt,
  verifyReceipt,
  createUnsignedReceipt,
} from "../src/consent/receipts.js";
import { generateKeyPair } from "../src/crypto/ed25519.js";
import type { SigningKeyPair } from "../src/crypto/types.js";
import type { UnsignedConsentReceipt } from "../src/consent/types.js";

describe("Consent Receipts", () => {
  let keyPair: SigningKeyPair;
  let manager: ConsentReceiptManager;
  const testContent = new TextEncoder().encode("User's personal data");
  const testMemoryId = "mem-12345";
  const testProvider = "test-provider";

  beforeEach(() => {
    keyPair = generateKeyPair();
    manager = new ConsentReceiptManager(keyPair);
  });

  describe("ConsentReceiptManager", () => {
    it("should create signed consent receipt", () => {
      const receipt = manager.createReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        2,
        "approve",
        "sensitivity-rule"
      );

      expect(receipt.memoryId).toBe(testMemoryId);
      expect(receipt.provider).toBe(testProvider);
      expect(receipt.userDecision).toBe("approve");
      expect(receipt.signature).toBeDefined();
      expect(receipt.signature.length).toBe(128);
    });

    it("should verify valid receipt", () => {
      const receipt = manager.createReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        2,
        "approve",
        "test-rule"
      );

      const result = manager.verify(receipt, testContent);
      expect(result.signatureValid).toBe(true);
      expect(result.memoryHashValid).toBe(true);
    });

    it("should detect invalid signature", () => {
      const receipt = manager.createReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        2,
        "approve",
        "test-rule"
      );

      receipt.signature = "0".repeat(128);
      const result = manager.verify(receipt);
      expect(result.signatureValid).toBe(false);
    });

    it("should detect memory content change", () => {
      const receipt = manager.createReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        2,
        "approve",
        "test-rule"
      );

      const modifiedContent = new TextEncoder().encode("Modified data");
      const result = manager.verify(receipt, modifiedContent);
      expect(result.signatureValid).toBe(true);
      expect(result.memoryHashValid).toBe(false);
    });

    it("should create denial receipt", () => {
      const receipt = manager.createDenialReceipt(
        testMemoryId,
        testContent,
        testProvider,
        3,
        "high-sensitivity"
      );

      expect(receipt.userDecision).toBe("deny");
      expect(receipt.redactions).toEqual([]);
    });

    it("should create redacted approval receipt", () => {
      const redactions = [
        { entityType: "email", placeholder: "[EMAIL]" },
        { entityType: "phone", placeholder: "[PHONE]" },
      ];

      const receipt = manager.createRedactedApprovalReceipt(
        testMemoryId,
        testContent,
        testProvider,
        redactions,
        2,
        "pii-detected"
      );

      expect(receipt.userDecision).toBe("approve_redacted");
      expect(receipt.redactions).toEqual(redactions);
    });

    it("should return public key", () => {
      const pubKey = manager.getPublicKey();
      expect(pubKey.length).toBe(32);

      const pubKeyHex = manager.getPublicKeyHex();
      expect(pubKeyHex.length).toBe(64);
    });
  });

  describe("Canonical JSON", () => {
    it("should produce deterministic JSON", () => {
      const unsigned = createUnsignedReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [{ entityType: "email", placeholder: "[EMAIL]" }],
        2,
        "approve",
        "test-rule",
        keyPair.publicKey
      );

      const json1 = toCanonicalJSON(unsigned);
      const json2 = toCanonicalJSON(unsigned);
      expect(json1).toBe(json2);
    });

    it("should round-trip through JSON", () => {
      const unsigned = createUnsignedReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        1,
        "approve",
        "test-rule",
        keyPair.publicKey
      );

      const json = toCanonicalJSON(unsigned);
      const recovered = fromCanonicalJSON(json);

      expect(recovered.memoryId).toBe(unsigned.memoryId);
      expect(recovered.provider).toBe(unsigned.provider);
      expect(recovered.userDecision).toBe(unsigned.userDecision);
    });
  });

  describe("Direct sign/verify", () => {
    it("should sign and verify receipt", () => {
      const unsigned = createUnsignedReceipt(
        testMemoryId,
        testContent,
        testProvider,
        [],
        2,
        "approve",
        "direct-test",
        keyPair.publicKey
      );

      const signed = signReceipt(unsigned, keyPair.privateKey);
      expect(signed.signature).toBeDefined();

      const result = verifyReceipt(signed, testContent);
      expect(result.signatureValid).toBe(true);
      expect(result.memoryHashValid).toBe(true);
    });
  });
});

describe("ConsentGate", () => {
  let gate: ConsentGate;

  beforeEach(() => {
    gate = new ConsentGate();
  });

  describe("Evaluation", () => {
    it("should require consent for high sensitivity", () => {
      const decision = gate.evaluate("Some data", 2, "provider");
      expect(decision.consentRequired).toBe(true);
    });

    it("should not require consent for low sensitivity", () => {
      const decision = gate.evaluate("Some data", 0, "provider");
      expect(decision.consentRequired).toBe(false);
    });

    it("should detect email patterns", () => {
      const decision = gate.evaluate("Contact me at user@example.com", 1, "provider");
      expect(decision.suggestedRedactions.length).toBeGreaterThan(0);
      expect(decision.suggestedRedactions.some((r) => r.entityType === "email")).toBe(true);
    });

    it("should detect phone patterns", () => {
      const decision = gate.evaluate("Call me at +1-555-123-4567", 1, "provider");
      expect(decision.suggestedRedactions.some((r) => r.entityType === "phone")).toBe(true);
    });

    it("should detect SSN patterns", () => {
      const decision = gate.evaluate("SSN: 123-45-6789", 1, "provider");
      expect(decision.suggestedRedactions.some((r) => r.entityType === "ssn")).toBe(true);
    });

    it("should detect credit card patterns", () => {
      const decision = gate.evaluate("Card: 4111-1111-1111-1111", 1, "provider");
      expect(decision.suggestedRedactions.some((r) => r.entityType === "creditCard")).toBe(true);
    });
  });

  describe("Redaction", () => {
    it("should apply email redaction", () => {
      const content = "Email: user@example.com";
      const redacted = gate.applyRedactions(content, [{ entityType: "email", placeholder: "[EMAIL]" }]);
      expect(redacted).toBe("Email: [EMAIL]");
    });

    it("should apply multiple redactions", () => {
      const content = "Email: user@example.com, Phone: +1-555-123-4567";
      const redacted = gate.applyRedactions(content, [
        { entityType: "email", placeholder: "[EMAIL]" },
        { entityType: "phone", placeholder: "[PHONE]" },
      ]);
      expect(redacted).toContain("[EMAIL]");
      expect(redacted).toContain("[PHONE]");
    });
  });

  describe("Rules", () => {
    it("should add custom rule", () => {
      gate.addRule({
        id: "custom-rule",
        description: "Custom test rule",
        sensitivityThreshold: 1,
        mandatory: true,
      });

      const decision = gate.evaluate("Test content", 1, "provider");
      expect(decision.triggeredRules.some((r) => r.id === "custom-rule")).toBe(true);
    });

    it("should remove rule", () => {
      gate.addRule({
        id: "removable-rule",
        description: "To be removed",
        sensitivityThreshold: 0,
        mandatory: false,
      });

      const removed = gate.removeRule("removable-rule");
      expect(removed).toBe(true);

      const config = gate.getConfig();
      expect(config.rules.some((r) => r.id === "removable-rule")).toBe(false);
    });
  });

  describe("Configuration", () => {
    it("should return config", () => {
      const config = gate.getConfig();
      expect(config.consentRequiredLevels).toBeDefined();
      expect(config.redactionPatterns).toBeDefined();
    });

    it("should accept custom config", () => {
      const customGate = new ConsentGate({
        consentRequiredLevels: [3],
        autoApproveBasicMemories: false,
      });

      const config = customGate.getConfig();
      expect(config.consentRequiredLevels).toEqual([3]);
      expect(config.autoApproveBasicMemories).toBe(false);
    });
  });
});
