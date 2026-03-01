	
⬡
closedclaw
Your Memory. Your Rules. Your Machine.
End-to-End Technical Design Document  v2.1
The AI Collective × AITX × DTI × UT Law Hackathon
Tracks 1 · 2 · 3  —  Memory Infrastructure · AI Companions · Personal Data Value


Track 1 — Memory Infrastructure
Track 2 — AI Companions
Track 3 — Personal Data Value


Core Layer
mem0 (modified)
Team Size
3 Engineers
Target
Individual Users


Table of Contents



SECTION 1
What Is closedclaw & Why It Exists


1. What Is closedclaw
1.1 The One-Line Definition
closedclaw in one sentence
closedclaw is a local middleware layer that wraps mem0 — giving every individual a private, portable, consent-gated AI memory that any tool can read from and write to, without the user changing how they already work.


closedclaw does not replace your AI assistant. It does not replace your chat app, your note-taking tool, or your LLM provider. It adds a thin, transparent layer underneath all of them so that your AI tools can finally remember you — privately, on your machine, on your terms.

1.2 The Problem It Solves
Today, every AI tool the user interacts with starts from zero. It has no memory of yesterday's conversation, no awareness of recurring preferences, no understanding of the user's context. The tools that do remember you solve this by storing your data on their servers, with no user visibility into what was stored, what was sent to the model, or how to get it back.

The individual user has no good option. They can use cloud AI tools that remember them but surrender control of their data entirely, or they can use stateless tools that respect their privacy but are frustrating to use because they have no continuity. closedclaw eliminates this false choice.

The Three Problems closedclaw Solves
1. Memory fragmentation: your data is scattered across ChatGPT, Claude, Notion AI, and every other tool. closedclaw gives you one local memory store every tool can use.2. Opacity: you have no idea what context is being sent to the LLM in any given request. closedclaw makes every context injection visible and auditable.3. Lack of control: you cannot tell your AI what it is and is not allowed to share. closedclaw lets you define exactly what flows where.


1.3 How It Addresses All Three Hackathon Tracks

Track 1 — Memory Infrastructure: closedclaw IS the memory infrastructure. It provides the secure local vault, the consent-driven pipeline, and the interoperability API that lets any tool read from and write to a user's memory. mem0 is the engine; closedclaw is the governance and integration layer built on top of it.


Track 2 — AI Companions with Purpose: closedclaw exposes a standard memory API that any AI agent (ClawdBot, custom LangChain agents, AutoGPT, or any tool using the OpenAI-compatible proxy) can query to get rich personal context. The memory store enables deeply personalized responses without the agent needing to store anything itself.


Track 3 — Personal Data, Personal Value: closedclaw's privacy and cryptography layer is the mechanism by which personal data becomes personal value rather than someone else's asset. The consent receipts, encryption, and audit log ensure the user's data works for them and only for them. The semantic insight layer mines the memory store for personal trends without sending data anywhere.


1.4 Design Constraints (Non-Negotiable)
Constraint
What It Means
Runs locally
The entire system runs on the user's laptop or desktop. No required cloud services. No subscription. One pip install and a config file.
Non-disruptive
The user should not have to change their workflow. closedclaw plugs in as an OpenAI-compatible proxy — tools that already use OpenAI just change their base URL.
Built on mem0
Memory storage, retrieval, and management are handled by a modified fork of mem0. We extend it; we do not rebuild it.
Integrable with anything
Any tool with an HTTP client can integrate with closedclaw. The API follows OpenAI conventions so existing SDKs work with zero code changes.
Individual-first
No multi-user, no enterprise, no SaaS. A single person, on their own computer, owning their own data. Complexity appropriate to that scope.
Debuggable by design
Each module is independently runnable and testable. The system is composed of simple, well-defined pieces that fail loudly and log clearly.
Actually shippable
The hackathon deliverable must be something a real person can download, run in under 5 minutes, and actually use.



SECTION 2
System Architecture


2. System Architecture
2.1 The Middleware Mental Model
Think of closedclaw as a smart router that sits between the user and every AI they interact with. It intercepts outbound requests, enriches them with relevant personal memory, applies the user's privacy rules, and then forwards the request to whichever LLM the user already uses. On the way back, it extracts anything worth remembering and adds it to the local vault — with the user's permission.

The user does not interact with closedclaw directly during normal use. It runs silently in the background. The only times it surfaces are when the user wants to inspect or manage their memory (via the dashboard), or when a privacy rule requires human consent before a sensitive memory is shared.

2.2 Component Map

Component
Role
Track
mem0 Core (modified)
Local vector + key-value memory store. Extended with sensitivity tagging, TTL fields, and a consent-aware write API
Track 1
Privacy Firewall
Per-request pipeline: retrieve → classify → redact → gate → forward. Enforces all user-defined rules before any context leaves the machine
Track 1 + 3
OpenAI-Compatible Proxy
Drop-in replacement endpoint for OpenAI API calls. Any existing app works by changing one URL. Handles the full enrichment pipeline transparently
Track 1 + 2
Memory API
REST endpoints for third-party tools to directly query, write, and manage memory. Authenticated with a local token. Follows a clean, documented schema
Track 1 + 2
Agent Bridge (ClawdBot)
A bundled reference agent that demonstrates full memory-aware conversation. Pluggable into any LangChain or LangGraph agent setup
Track 2
Insight Engine
Runs locally on the memory store to surface trends, summaries, and patterns. No data leaves the machine. Output is user-visible reports and prompts
Track 3
Crypto Layer
AES-256-GCM encryption for memory at rest; Ed25519 signed consent receipts; cryptographic deletion on TTL expiry
Track 3
Audit Log
Append-only log of every context injection event. Signed. Exportable. The user can always see exactly what was sent to any AI and when
Track 3
Dashboard (optional)
A lightweight local web UI for managing memory, reviewing audit logs, and configuring privacy rules. Not required for core function
All tracks


2.3 Data Flow: A Normal Request
When a user sends a message through any tool connected to closedclaw (via the proxy or direct API), the following happens in under 200ms on typical consumer hardware:

The tool sends an HTTP request to closedclaw's local proxy (localhost:8765/v1/chat/completions) instead of directly to OpenAI or Anthropic.
closedclaw extracts the latest user message and runs semantic search against the mem0 store to find the most relevant personal memories.
Each retrieved memory is scored for sensitivity (0–3). The Privacy Firewall evaluates each against the active rule set.
Memories that pass the firewall are formatted as context and injected into the system prompt. Memories that require redaction are redacted. Memories that require consent pause the pipeline and notify the user.
The enriched request is forwarded to the user's configured LLM provider (OpenAI, Anthropic, Ollama, Groq — any OpenAI-compatible endpoint).
The LLM response is returned to the tool. In the background, the Memory Extraction agent proposes new memories from the conversation. Sensitive ones wait for user approval; non-sensitive ones are stored immediately.
The Audit Logger records the full event: which memories were retrieved, what was redacted, which provider was called, and how many tokens of context were sent.

Latency Target
The full pipeline (retrieval + classification + redaction + prompt construction) targets under 150ms added latency on a modern laptop. Memory retrieval from the local SQLite store is fast; the bottleneck is the LLM call itself, which closedclaw does not slow down. Users will not notice the layer is there.


2.4 Integration Modes
closedclaw supports three integration modes, covering every possible way a user might want to connect their existing tools:

Mode
Description
Mode 1 — Proxy
Point any OpenAI SDK client to localhost:8765. Zero code changes. Works with ChatGPT wrappers, Continue.dev, anything using openai.ChatCompletion. The easiest integration — one environment variable change.
Mode 2 — Memory API
Third-party tools explicitly call /v1/memory/search and /v1/memory/add to integrate memory read/write into their own logic. For developers building memory-aware apps on top of closedclaw.
Mode 3 — Direct mem0
For developers who want to use the modified mem0 library directly in Python. Import closedclaw.memory and get a drop-in mem0 replacement with all the privacy extensions pre-wired.


2.5 What closedclaw Does NOT Do
Being explicit about scope prevents scope creep and keeps the system understandable:

It does not host or run an LLM. It routes to LLMs the user already has access to.
It does not replace mem0. It extends mem0 with governance, encryption, and integration features.
It does not provide multi-user or household memory sharing. One instance = one person.
It does not require the dashboard to function. The proxy and API work headlessly.
It does not require a paid LLM API. Users can configure Ollama as their provider for fully free, fully local operation.


SECTION 3
Memory Layer — Modified mem0  [Track 1]


3. Memory Layer — Modified mem0
This section covers Track 1: Memory Infrastructure. The modified mem0 library is the core of closedclaw's memory vault — a locally-running, privacy-aware, consent-gated memory store.


3.1 Why mem0 and What We Change
mem0 is an open-source memory layer for LLM applications. It handles the core hard problems of AI memory: deciding what to remember, extracting structured memories from conversations, storing them with vector embeddings for semantic retrieval, and surfacing the most relevant ones for a given query. We do not rebuild any of this.

What we add on top of mem0 is the governance layer: sensitivity classification on every memory, encryption at rest, TTL-based expiry, a consent-aware write path, and a richer metadata schema. We maintain a thin fork of mem0 that adds these fields to its data model and hooks into its add/search/delete lifecycle.

Layer
Capabilities
mem0 provides
Semantic search over memories; LLM-extracted memory from conversations; key-value and vector storage; memory update and deduplication logic; multi-provider embedding support
closedclaw adds
Sensitivity scoring (0–3); AES-256-GCM encryption at rest; TTL fields and cryptographic deletion; consent-gated write path; content hashing for audit; extended metadata schema; event hooks for privacy pipeline


3.2 Extended Memory Schema
We extend mem0's base memory object with the following additional fields. All fields are backward-compatible — a standard mem0 client reading the store will simply ignore the extensions:

closedclaw Memory Object (extends mem0 base):
  # Standard mem0 fields (unchanged)
  id:              str   — UUID v4
  memory:          str   — extracted memory text (encrypted at rest)
  user_id:         str   — owner identifier
  created_at:      datetime
  updated_at:      datetime


  # closedclaw extensions
  sensitivity:     int   — 0 (public) to 3 (highly sensitive)
  tags:            list  — semantic categories: ['health','finance','work'...]
  source:          str   — 'conversation'|'manual'|'imported'|'insight'
  expires_at:      datetime|None  — null = permanent
  content_hash:    str   — SHA-256 of plaintext (for consent receipts)
  encrypted:       bool  — whether memory field is AES-GCM ciphertext
  dek_enc:         str   — base64 AES-256-GCM encrypted data key
  access_count:    int   — number of times retrieved for context
  last_accessed:   datetime|None
  consent_required: bool — whether this memory always requires consent gate

3.3 Sensitivity Classification
Every memory is assigned a sensitivity score at write time. The score drives all downstream privacy decisions. Classification uses three signals in priority order:

User override: If the user has manually set a sensitivity level for this memory or a matching tag, that value takes precedence.
NER-based rules: spaCy + Presidio scan the memory text for entity types. MEDICAL_CONDITION, FINANCIAL_ACCOUNT, SSN, and LEGAL_MATTER auto-classify as Level 3. HOME_ADDRESS, RELATIONSHIP, and POLITICAL_OPINION auto-classify as Level 2.
Keyword heuristics: A curated keyword list provides a fast, LLM-free sensitivity floor for common cases (e.g. 'diagnosis' → 2, 'password' → 3, 'boss' → 1).

Level
Examples
Default Handling
Level 0 — Public
General preferences, publicly known facts, stated opinions with no identifiers
Any provider, no redaction required
Level 1 — General
Name, profession, general location, non-sensitive preferences
Cloud LLM allowed; name/email redacted by default
Level 2 — Personal
Address, relationships, finances (general), mental health, politics
Local LLM only by default; explicit permit rule required for cloud
Level 3 — Sensitive
Medical records, account credentials, legal matters, biometrics, SSN
Local LLM only; per-request user consent always required


3.4 Encryption at Rest
Memory text is encrypted using AES-256-GCM with a per-memory Data Encryption Key (DEK). The DEK is itself encrypted by a master Key Encryption Key (KEK) derived from the user's passphrase using Argon2id. The KEK is never stored on disk — only the encrypted DEKs are persisted. Embeddings are stored unencrypted (they are not reversible to plaintext without the original model).

3.5 Cryptographic Deletion (TTL / Right to Forget)
When a memory expires (TTL reached) or is manually deleted, closedclaw overwrites and deletes its DEK. The ciphertext remains in the database but is permanently unrecoverable — no DEK means no decryption, even with direct database file access. This satisfies GDPR Article 17 at the cryptographic layer, not just the database layer.

3.6 Writeback Policy
After every LLM response, mem0's memory extraction runs in the background to identify candidate new memories. Before writing, each candidate passes through the writeback policy:

Sensitivity is classified using the NER + keyword pipeline.
Level 0–1 candidates are written immediately (no user action required).
Level 2–3 candidates are held in a pending queue and surfaced to the user as a non-blocking notification: 'closedclaw wants to remember: [memory text]. Store it?' The user can approve, edit, or discard.
Any candidate flagged as a potential duplicate by mem0's deduplication logic is merged rather than stored as a new entry.


SECTION 4
Privacy Firewall


4. Privacy Firewall
4.1 Overview
The Privacy Firewall is the pipeline that every retrieved memory passes through before it can be attached to an outbound LLM request. It is the mechanism that makes closedclaw's core promise real: the user's data flows on the user's terms. Each stage is independent, testable, and configurable.

Pipeline Stage
What Happens
Stage 1: Retrieve
mem0 semantic search returns top-k memories for the query. Differential privacy noise applied to similarity scores to prevent inference attacks.
Stage 2: Classify
Each retrieved memory's sensitivity level is confirmed (or upgraded if new NER signals are found in context).
Stage 3: Rule Match
The policy engine evaluates each memory against the active rule set. Each memory gets an action: PERMIT, REDACT, BLOCK, or CONSENT_REQUIRED.
Stage 4: Redact
Memories with REDACT action pass through the PII pipeline. Named entities are replaced with typed placeholders. The redaction map is logged.
Stage 5: Consent Gate
Memories with CONSENT_REQUIRED action pause the pipeline. The user is notified and must approve before the request proceeds.
Stage 6: Inject
Approved, redacted context is formatted and injected into the system prompt. The prompt is forwarded to the configured LLM provider.
Stage 7: Audit
A signed audit log entry is written recording the full event: memories retrieved, actions taken, redactions applied, provider used, token count.


4.2 Policy Engine
The policy engine is a simple rule evaluator. Rules are stored as JSON files in ~/.closedclaw/policies/. Users can write rules by hand or use the dashboard Policy Manager UI. Each rule has conditions and an action. Rules are evaluated in priority order; the first match wins.

4.2.1 Rule Structure
Example Policy Rule (JSON):
{
  "id": "no-health-to-cloud",
  "name": "Block health memories from cloud LLMs",
  "priority": 100,
  "conditions": {
    "tags_include": ["health"],
    "provider_not": ["ollama"]
  },
  "action": "BLOCK"
}

Example Rule with Redaction:
{
  "id": "redact-names-general",
  "name": "Redact names from Level 1 memories",
  "priority": 50,
  "conditions": { "sensitivity_max": 1 },
  "action": "REDACT",
  "redact_entities": ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]
}

4.2.2 Default Rules (Shipped Out of the Box)
Default Rule
Behavior
Block all Level 3 from cloud
Any sensitivity-3 memory is blocked from any non-local provider. Hard default, user cannot disable without explicit override.
Redact names on Level 1
Person names and emails are redacted before Level 1 memories are sent to any provider.
Consent gate on Level 3
Any Level 3 memory requires explicit per-request consent before inclusion in any prompt.
Log all context injections
Every outbound context injection is logged regardless of other rule outcomes.
Block Level 2+ from cloud (soft)
Level 2 memories are blocked from cloud providers by default. Users can override with an explicit permit rule.


4.3 PII Redaction Pipeline
When a memory passes through the REDACT action, it is processed by Microsoft Presidio with spaCy as the NER backend. Identified entities are replaced by typed, numbered placeholders. The original-to-placeholder mapping is stored in the audit log for that request — visible only locally, never sent externally.

Input Text
Redacted Output
Action
Input
Redacted Output
Entities Removed
Arush moved to Austin last year
[PERSON_1] moved to [CITY_1] last year
PERSON, CITY
My therapist is Dr. Ana Torres
My therapist is Dr. [PERSON_1]
PERSON
I owe $8k on my Chase Sapphire
I owe [AMOUNT_1] on my [ACCOUNT_1]
AMOUNT, FINANCIAL_ACCT
My SSN ends in 6789
[SSN_BLOCKED — Level 3: context excluded]
SSN (full block)


4.4 Consent Gate
When any memory in the retrieved set requires consent, the pipeline pauses and a notification appears in the dashboard or as a desktop notification (via the OS notification API). The notification shows the user the memory in full, explains why consent is required, shows what redactions would be applied, and identifies the target LLM provider. The user approves or denies. The decision is logged as a signed consent receipt.


SECTION 5
Integration Layer & OpenAI Proxy  [Track 2]


5. Integration Layer & OpenAI Proxy
Track 2 — AI Companions with Purpose: The proxy and Memory API are what allow any AI companion, agent, or LLM tool to become memory-aware — without the tool needing to store anything or change its architecture.


5.1 The OpenAI-Compatible Proxy
The proxy is closedclaw's most important integration mechanism. It exposes a single endpoint that is fully compatible with the OpenAI Chat Completions API specification. Any application, script, or tool that uses the OpenAI Python SDK, Node SDK, or any HTTP client targeting the OpenAI API can be connected to closedclaw with a single environment variable change:

# Before (direct to OpenAI)
OPENAI_BASE_URL=https://api.openai.com/v1


# After (through closedclaw)
OPENAI_BASE_URL=http://localhost:8765/v1

The API key is forwarded through to the actual provider. closedclaw never stores or logs the API key. The user's existing tools — Continue.dev, Cursor, Open WebUI, custom scripts, anything — work identically, just with memory enrichment applied transparently.

5.2 Memory API Endpoints
For tools that want to explicitly integrate with memory (rather than just using the transparent proxy), closedclaw exposes a clean REST API. All endpoints require a local bearer token stored in ~/.closedclaw/token.

Endpoint
Purpose
Input
Output
GET /v1/memory
Semantic search over memories
?q=query&sensitivity_max=2&limit=5
Returns ranked memory chunks
POST /v1/memory
Add a memory manually
{ content, sensitivity, tags }
Returns memory ID + receipt
PATCH /v1/memory/:id
Update sensitivity, tags, TTL
{ sensitivity, expires_at }
Returns updated object
DELETE /v1/memory/:id
Cryptographic deletion
—
DEK destroyed, irrecoverable
GET /v1/memory/tags
List all tags in vault
—
Tags with memory counts
GET /v1/memory/export
Export identity bundle
?passphrase=X
Encrypted JSON bundle
POST /v1/memory/import
Import identity bundle
multipart bundle file
Returns import summary
GET /v1/audit
Retrieve audit log
?from=&to=&provider=
Array of signed entries
GET /v1/audit/verify
Verify hash chain integrity
—
{ valid: bool, entries: N }
GET /v1/consent/pending
List pending consent requests
—
Array of pending gates
POST /v1/consent/:id
Respond to consent gate
{ decision: approve|deny }
Returns consent receipt
GET /v1/status
System health check
—
Counts + provider status


5.3 ClawdBot — The Reference Agent (Track 2)
ClawdBot is a bundled reference implementation of a memory-aware AI companion built on closedclaw. It demonstrates what a Track 2 AI companion looks like when it has access to a rich, private memory store. It is not the product — it is a demonstration that ships alongside the product.

ClawdBot is implemented as a LangGraph state machine with access to four memory tools: search_memory, write_memory, request_consent, and reflect_on_memories (a tool that runs an in-context analysis of retrieved memories to surface patterns or contradictions). It is configured as the default agent in the closedclaw dashboard chat and can be replaced by any other LangGraph or LangChain agent.

5.3.1 Memory Tools Available to ClawdBot
Tool
Description
search_memory(query, sensitivity_max)
Semantic search over the local vault. The agent calls this with targeted queries based on what it needs to answer well. Returns top-k chunks with sensitivity badges.
write_memory(content, sensitivity, tags)
Propose storing a new memory. Triggers the writeback consent flow for sensitivity ≥ 2. Returns the stored memory ID.
request_consent(memory_id, reason)
Explicitly request user consent for a specific Level 3 memory. The agent calls this when it determines sensitive context is needed and the user has not yet consented.
reflect_on_memories(topic)
Retrieves all memories tagged with a topic and asks the LLM to synthesize a coherent summary, identify recurring patterns, and flag contradictions. Returns a structured reflection object.
get_memory_timeline(topic)
Retrieves memories for a topic ordered chronologically with timestamps. Enables the agent to reason about how something has changed over time.


5.4 Third-Party Integration Examples
The following shows how popular tools integrate with closedclaw, to illustrate the breadth of compatibility:

Tool
Integration Method
Continue.dev (VS Code)
Set OPENAI_BASE_URL in config.json. Cursor and Continue now have memory of your codebase preferences, past debugging sessions, and architectural decisions — privately.
Open WebUI
Set the OpenAI API base URL in settings. Open WebUI's chat interface now enriches every message with personal context from closedclaw.
LangChain agents
import ClosedClawMemory from closedclaw.langchain and use it as a drop-in replacement for ConversationBufferMemory.
Custom Python scripts
from closedclaw import memory — use the modified mem0 client directly. Full access to add, search, and delete with all privacy extensions.
n8n / Make (no-code)
Use the HTTP Request node pointed at localhost:8765. Build memory-aware automation workflows without writing code.
Any OpenAI SDK app
One environment variable: OPENAI_BASE_URL=http://localhost:8765/v1. Done. No other changes required.



SECTION 6
Cryptography, Privacy & Personal Value  [Track 3]


6. Cryptography, Privacy & Personal Value
Track 3 — Personal Data, Personal Value: The cryptography layer and the Insight Engine are what transform closedclaw from a privacy tool into a genuine personal value generator. The user's data works for them — as a source of self-knowledge, personal trends, and verifiable consent — not as a product for someone else.


6.1 Cryptography Primitives
Operation
Implementation
Memory encryption
AES-256-GCM — authenticated encryption. Each memory chunk has its own unique 256-bit key (DEK).
Key wrapping
Envelope encryption — DEKs are encrypted by the master KEK using AES-256-GCM.
Key derivation
Argon2id — memory-hard, GPU-resistant. User passphrase → KEK. 64MB memory, 3 iterations.
Digital signatures
Ed25519 — fast, secure. Used for consent receipts and audit log hash chain.
Content hashing
SHA-256 — used for memory content hashes in consent receipts and audit entries.
Deletion
DEK destruction — deleting the DEK renders ciphertext permanently irrecoverable.


6.2 Consent Receipts
A consent receipt is a machine-readable, cryptographically signed record of a specific decision the user made to share a specific memory with a specific AI provider. It is generated every time the Consent Gate approves a Level 2–3 memory for inclusion in a prompt.

Consent receipts are the core of closedclaw's legal relevance. They answer the question 'what did you consent to, and when?' with a verifiable, unforgeable document. This is directly applicable to GDPR data access rights, HIPAA audit requirements, and the UT Law angle on AI data governance.

6.2.1 Consent Receipt Schema
Consent Receipt (signed JSON):
  receipt_id:         UUID v4
  timestamp:          ISO 8601 ms precision
  memory_id:          Reference to the vault entry
  memory_hash:        SHA-256 of plaintext at time of consent
  provider:           LLM provider the memory was approved for
  redactions:         [{ entity_type, placeholder }]  — applied before send
  sensitivity_level:  0–3 at time of consent
  user_decision:      'approve' | 'approve_redacted' | 'deny'
  rule_triggered:     Policy rule ID that required consent
  user_pubkey:        Ed25519 public key
  signature:          Ed25519 over canonical JSON of above fields

6.3 Audit Log
The audit log is an append-only, hash-chained ledger. Every LLM request that passes through closedclaw generates one entry. Each entry contains a hash of the previous entry, making retroactive tampering detectable. Each entry is signed with the user's Ed25519 key.

The audit log answers the question that no current AI product can answer: 'exactly what did you tell the AI about me, and when?' Users can export their full audit history as a signed bundle and verify its integrity at any time.

6.4 The Insight Engine (Track 3 Core)
The Insight Engine is a scheduled, local-only process that periodically analyzes the memory store to generate personal value without sending any data anywhere. It runs on a configurable schedule (e.g., weekly) or on-demand from the dashboard.

The Insight Engine produces four types of output, all stored locally and shown only in the dashboard:

Life Summary: A natural-language summary of the user's recent experiences, decisions, and interests — drawn from the last N weeks of memories. Useful for journaling, reflection, or onboarding a new AI tool.
Trend Detection: Identifies recurring themes and patterns in the memory store. E.g., 'You've mentioned stress about work deadlines 12 times in the last 3 months.' The pattern is visible to the user; the underlying memories stay private.
Contradiction Alerts: Flags cases where stored memories appear to contradict each other (e.g., two memories that list different home cities). Useful for memory hygiene — the user can resolve which is current.
Memory Expiry Review: Surfaces memories approaching their TTL expiry and lets the user decide to extend or let them expire. Prevents accidental loss of memories the user wants to keep.

All Insight Engine processing uses the local LLM (Ollama) for any text generation steps. No personal memory text is sent to a cloud provider during insight generation.

6.5 Portable Identity
The user's entire memory state — vault contents, policy rules, consent receipts, and audit log — can be exported as a single encrypted JSON bundle. The bundle is signed with the user's Ed25519 key. It can be imported on any machine running closedclaw. This is the DTI (Decentralized Technology Initiative) alignment: the user's AI identity is portable and self-sovereign.

Operation
Details
Export
closedclaw export --output ~/my-identity.json — produces an AES-256-GCM encrypted bundle signed with the user's key
Import
closedclaw import --input ~/my-identity.json — verifies the signature, decrypts, and merges into the local vault (with deduplication)
Verification
Any third party with the user's public key can verify the bundle's integrity and the authenticity of each consent receipt — without seeing any memory content
Schema
identity.json follows a versioned open schema. Future closedclaw versions maintain backward compatibility. Community tools can build on the same schema.



SECTION 7
Dashboard & User Experience


7. Dashboard & User Experience
7.1 Philosophy: Invisible Unless Needed
The closedclaw dashboard is optional. The system runs perfectly without it. But for users who want visibility, control, or insight, the dashboard makes every aspect of the system inspectable and manageable through a clean local web UI.

The dashboard runs at localhost:8765/app and is served by the FastAPI backend. It is built with React and Tailwind CSS and communicates exclusively with the local API. There are no external calls from the frontend. It is accessible only from the local machine.

7.2 Dashboard Views

7.2.1 Chat (ClawdBot Interface)
A standard chat UI with one key difference: the Context Inspector panel on the right. For every message sent, the Inspector shows in real time which memories were retrieved, their sensitivity levels, what was redacted, which provider was used, and a direct link to the audit log entry. The user can see exactly what context the AI received — something no current AI product shows.

7.2.2 Memory Vault
A searchable, filterable grid of all stored memories. Each memory card shows the text, sensitivity badge (color-coded), tags, creation date, and expiry date. Cards can be clicked to edit sensitivity/tags/TTL, view access history, or permanently delete. Full-text search runs locally against decrypted content. Filtering by sensitivity, tag, source, and expiry status is supported.

7.2.3 Audit Log
A chronological timeline of every LLM request that passed through closedclaw. Each entry shows timestamp, summary, provider, context chunks used, and whether consent was required. The chain integrity status is shown at the top of the page. The export button generates a signed bundle. Clicking any entry shows the full detail view.

7.2.4 Policy Manager
A GUI for creating and managing privacy rules. Rules are built through a form with condition pickers and action selectors — no JSON editing required. The compliance profile selector activates HIPAA, GDPR, or COPPA mode with one click. A 'Test a Memory' panel lets users see exactly how the current rule set would handle a given hypothetical memory.

7.2.5 Insights
The output of the Insight Engine: life summaries, trend charts, contradiction alerts, and expiry reviews. All generated locally. The 'Run Insights Now' button triggers an on-demand analysis. Insights are stored locally and never sent anywhere.

7.2.6 Consent Notifications
Pending consent gate requests appear as a badge on the dashboard navigation and as OS-level desktop notifications. Clicking opens a full-screen modal with the memory, proposed redactions, target provider, and approve/deny buttons. Consent decisions are non-expiring by default — the user must explicitly respond.


SECTION 8
Installation, Setup & Distribution


8. Installation, Setup & Distribution
8.1 Design Goal: Under 5 Minutes from Zero to Running
A project that can't be installed by a real person is not a finished project. closedclaw's installation is designed for a technically literate individual (someone comfortable with a terminal) but does not require deep Python knowledge, Docker, or any cloud account.

Minimum Requirements
Python 3.11+ · 8GB RAM (16GB recommended for local LLM) · 2GB disk space · macOS, Linux, or Windows (WSL2) · An API key for OpenAI or Anthropic (OR Ollama for fully free/local operation)


8.2 Install Steps

# Step 1: Install closedclaw
pip install closedclaw

# Step 2: Initialize (creates ~/.closedclaw/ config directory)
closedclaw init

# Step 3: Configure your LLM provider
# Option A: Use OpenAI
closedclaw config set provider openai
closedclaw config set openai_api_key sk-...

# Option B: Use local Ollama (free, fully private)
ollama pull llama3.1   # one-time model download
closedclaw config set provider ollama

# Step 4: Start the server
closedclaw serve

# closedclaw is now running at http://localhost:8765
# Dashboard: http://localhost:8765/app
# OpenAI-compatible proxy: http://localhost:8765/v1

8.3 Connecting Your First Tool

# Example: Connect the OpenAI Python SDK
import openai
client = openai.OpenAI(
    base_url="http://localhost:8765/v1",
    api_key="your-openai-key"  # forwarded to OpenAI
)
# That's it. All existing code works unchanged.

8.4 Distribution Strategy
closedclaw is distributed as a standard Python package on PyPI. The repository is open source (MIT license) and hosted on GitHub. Distribution includes:

Distribution Channel
Details
PyPI package
pip install closedclaw — installs the server, CLI, and Python library. Single command, no Docker required.
GitHub repo
Full source code, MIT licensed, with a detailed README, example configs, and a quickstart guide.
Homebrew formula
brew install closedclaw — for macOS users who prefer Homebrew over pip.
Bundled frontend
The React dashboard is compiled and bundled into the Python package. No separate npm install required for end users.
Ollama integration
The installer can optionally download and configure Ollama for fully local operation. No API key required.
Demo mode
closedclaw serve --demo starts with a pre-populated memory store for demonstration purposes.


8.5 Auto-Start (Optional)
For users who want closedclaw to always be running in the background, the CLI provides an install-service command that registers closedclaw as a launchd service (macOS), systemd service (Linux), or Windows Service. Once installed, it starts automatically on login and runs silently in the background.

closedclaw install-service   # sets up auto-start
closedclaw uninstall-service  # removes auto-start


SECTION 9
Implementation Plan — 2 Weeks, 3 Engineers


9. Implementation Plan
9.1 Technology Stack
Every technology choice is made with three criteria: does it run locally with no external dependencies, is it well-maintained with good documentation, and does it minimize the number of things the team needs to learn simultaneously.

Technology
Role
Rationale
FastAPI + uvicorn
Backend API server
Async Python; auto-generates OpenAPI docs; simple to debug; great for the proxy
mem0 (modified fork)
Memory engine
The core — we extend its data model and hook into its lifecycle events
SQLite + sqlite-vec
Storage
Zero-dependency local vector search; single file database; easy to inspect
spaCy + Presidio
NER / PII detection
Best local PII detection; no API key required; fast on consumer hardware
Python cryptography
Encryption / signing
AES-GCM, Ed25519, Argon2id; well-audited; ships with pip
LangGraph
Agent loop (ClawdBot)
Human-in-the-loop nodes for consent gate; clean state machine model
Ollama
Local LLM + embeddings
One-command install; runs Llama 3.1 8B and nomic-embed-text locally
React 18 + TypeScript
Dashboard frontend
Strong typing; fast iteration; familiar to most web developers
Tailwind + shadcn/ui
UI styling
No design system setup; accessible components out of the box
Typer
CLI
Auto-generates help text; consistent with FastAPI ecosystem
pytest
Testing
Standard Python testing; each module tested independently


9.2 Module Breakdown & Build Order
Each module is independently runnable and has clear interfaces. The team can build in parallel and integrate at the end of each module set. There are no hidden dependencies between modules within the same week.

Week 1 — Core Infrastructure (Days 1–7)

Timeline
Module
Owner
Description
Days 1–2
Module: mem0 fork
Eng 1 + 2
Fork mem0 repo; add extended schema fields (sensitivity, TTL, dek_enc); implement AES-256-GCM encryption/decryption; implement cryptographic deletion. Deliverable: pip-installable closedclaw.memory with full test coverage.
Days 1–2
Module: FastAPI skeleton
Eng 3
Project structure; FastAPI app; SQLite init; /v1/status health check; authentication token middleware; hot-reload dev setup. Deliverable: running server with auth.
Days 3–4
Module: Privacy Firewall
Eng 1 + 2
spaCy + Presidio NER pipeline; sensitivity classifier; redaction pipeline with typed placeholders; rule engine JSON evaluator. Deliverable: standalone Python module, fully testable with mock memories.
Days 3–4
Module: OpenAI Proxy
Eng 3
Proxy endpoint /v1/chat/completions; request interception; context injection; forward to provider; response passthrough; streaming support. Deliverable: working proxy that adds a system message.
Days 5–6
Module: Full Pipeline
All
Wire mem0 → Firewall → Proxy together. Retrieval → classify → redact → inject → forward. Basic consent gate (sync, no UI yet). Deliverable: end-to-end query with memory context.
Day 7
Integration + Fixes
All
End-to-end test with real LLM provider. Fix any integration bugs. Basic React frontend scaffold (chat UI shell + status page). Internal demo run.


Week 2 — Cryptography, Agents, Polish (Days 8–14)

Timeline
Module
Owner
Description
Days 8–9
Module: Crypto Layer
Eng 1
Ed25519 keypair generation; consent receipt signing and verification; audit log hash chain; audit export bundle. Deliverable: signed receipts on every consent decision.
Days 8–9
Module: ClawdBot Agent
Eng 2
LangGraph agent with memory tools; human-in-the-loop consent gate node; reflect_on_memories tool; timeline tool. Deliverable: working conversational agent with full memory access.
Days 8–9
Module: Dashboard Views
Eng 3
Memory Vault viewer; Audit Log viewer; Consent Gate modal + WebSocket push. Deliverable: functional Vault and Audit views.
Days 10–11
Module: Insight Engine
Eng 2
Weekly analysis scheduler; Life Summary generation (local LLM); trend detection; contradiction flagging; expiry review. Deliverable: on-demand insights in the dashboard.
Days 10–11
Module: Policy Manager UI
Eng 3
Rule builder form; compliance profile selector; rule testing panel. Deliverable: full Policy Manager view.
Days 10–11
Module: Identity Export
Eng 1
Export/import CLI commands; encrypted bundle format; signature verification; Deliverable: working closedclaw export and import.
Days 12–13
Polish + Integration
All
Connect all dashboard views to live API; notification system for consent gate; error handling and loading states; README and install docs; demo mode data.
Day 14
Demo Prep
All
Scripted demo scenario; judge presentation; end-to-end rehearsal; stress test; final bug fixes.


9.3 Team Allocation Summary

Engineer
Role
Responsibilities
Engineer 1
Backend & Cryptography
mem0 fork, encryption layer, consent receipts, audit hash chain, identity export/import, policy engine backend
Engineer 2
ML & Agents
NER/Presidio redaction, sensitivity classifier, LangGraph ClawdBot, Insight Engine, memory tools, writeback pipeline
Engineer 3
Full-Stack & Integration
FastAPI skeleton, OpenAI proxy, React dashboard (all views), WebSocket, Consent Gate modal, API integration, CLI



SECTION 10
Demo Scenario & Hackathon Strategy


10. Demo Scenario & Hackathon Strategy
10.1 The 8-Minute Demo
The demo tells a story: what it actually feels like to have an AI that knows you deeply, without the fear that your most sensitive information is broadcast to a cloud. Every minute is scripted. Every demo step has a 'so what' that maps to a track.

Act
Script + Takeaway
Act 1 (1.5 min): The Setup — It Just Works
Open terminal. Run closedclaw serve. Open the dashboard. Show the pre-populated memory vault with memories at all sensitivity levels. Color-coded sensitivity badges. Then switch to Continue.dev in VS Code and show that it points to localhost:8765. One environment variable. Nothing else changed.The takeaway: this is real, it's running, and it took 30 seconds to set up.
Act 2 (2 min): The Context Inspector
Send a message through Continue.dev: 'Help me write a project README based on my work style.' The Context Inspector panel shows in real time which memories fired: work style memories (Level 1), past project descriptions (Level 0). Names redacted. Routed to cloud LLM. Show the audit log entry. The LLM response is noticeably personalized.The takeaway: memory works, redaction works, you can see everything.
Act 3 (2.5 min): The Consent Gate
Ask ClawdBot: 'Given my health situation, should I be taking on more stress at work?' The pipeline pauses. A full-screen consent modal appears showing a Level 3 health memory. Target: local LLM only. Proposed redactions shown. Click Approve. Watch the Context Inspector show the health memory going ONLY to the local Ollama model — the cloud API call log is empty.The takeaway: sensitive data literally cannot reach the cloud without you saying yes.
Act 4 (1.5 min): The Audit Receipt
Open the Audit Log. Show the entry for Act 3. Expand the consent receipt: signed JSON with Ed25519 signature, content hash, timestamp. Run 'Verify Chain Integrity' — passes. Export as a bundle.Hand to UT Law collaborator: 'This is a legally-relevant instrument — it proves what was consented to, when, and what was sent.' The takeaway: this is infrastructure for AI accountability, not just a privacy feature.
Act 5 (0.5 min): The Insight
Click 'Run Insights'. Show the Life Summary and one Trend Card ('You've mentioned work-life balance concerns 9 times in the last month'). All generated locally, never sent anywhere.The takeaway: your data works for you — actual value, actual insight, zero leakage.


10.2 Judge Personas
Audience
Messaging
Technical judges
Lead with: the modified mem0 fork as infrastructure (not a wrapper), the consent gate pause/resume pattern in LangGraph, the AES-GCM envelope encryption with cryptographic deletion, and the differential privacy on embedding retrieval. These are non-trivial engineering choices with clear reasoning.
UT Law judges
Lead with: consent receipts as legally-relevant instruments, the GDPR Art. 17 implementation at the cryptographic layer, HIPAA minimum-necessary compliance via sensitivity routing, and the proposal for an open AI Consent Receipt standard. Have a specific section in the pitch mapped to each regulatory citation.
DTI judges
Lead with: the portable identity bundle as a self-sovereign AI identity primitive, the open identity.json schema as a community standard proposal, and the import/export as the foundation for AI identity interoperability across platforms.
Product judges
Lead with: one environment variable change to connect any existing tool, the 5-minute install, the fact that the user's existing workflow does not change. Use the browser analogy: 'We didn't get rid of the internet, we built a browser that made it safe to use.'


10.3 Competitive Differentiators
Comparison
closedclaw Positioning
vs. RAG apps
RAG apps retrieve from a knowledge base. closedclaw governs what personal context flows to AI — with sensitivity classification, redaction, consent gating, and audit. Governance is the product, not retrieval.
vs. mem0 directly
mem0 is our engine. closedclaw is the privacy and governance layer on top. Like how SQLite is the engine and your app is the product — mem0 is the substrate, closedclaw is the system.
vs. cloud memory products
Those products store your memories on their servers. closedclaw's entire value proposition is that your memories never leave your machine unless you explicitly say so.
vs. local LLM wrappers
Local-only tools sacrifice capability for privacy. closedclaw gives you both — local for sensitive queries, cloud for everything else — with routing based on actual data sensitivity, not blanket policy.



SECTION 11
Legal & Compliance Framework  [UT Law]


11. Legal & Compliance Framework
11.1 Regulatory Alignment
Regulation
closedclaw Implementation
GDPR Art. 5 — Minimization
Policy engine enforces minimum necessary context; no more memories are sent than the query requires
GDPR Art. 17 — Right to Erasure
Cryptographic deletion — DEK destruction makes forensic recovery impossible, not just database deletion
GDPR Art. 20 — Portability
identity.json export provides a machine-readable, complete data portability package
CPRA — Sensitive Personal Info
Level 2–3 sensitivity classification maps directly to CPRA's 'sensitive personal information' category
HIPAA — Minimum Necessary
HIPAA compliance profile enforces Level 3 classification on all PHI; local-only routing mandatory
HIPAA — Audit Controls
Signed, hash-chained audit log with consent receipts satisfies HIPAA audit control requirements
EU AI Act — Transparency
Context Inspector + audit log provide the transparency documentation required for AI systems
COPPA
COPPA mode disables all memory writeback and restricts all external context sharing for minor profiles


11.2 The AI Consent Receipt Standard (Novel Contribution)
closedclaw proposes the AI Consent Receipt (AICR) — an open JSON-LD schema for documenting user consent to AI memory access. This is positioned as a community standard proposal, not just an internal implementation. The hackathon is the venue to introduce it.

The AICR schema is designed to be compatible with W3C Verifiable Credentials, enabling consent receipts to be stored in decentralized identity wallets and verified by third parties without revealing the underlying memory content. A user can prove to a regulator, auditor, or court what they consented to and when — cryptographically — without exposing any private data.

The UT Law collaboration angle: invite UT Law faculty or collaborators to co-author or review the AICR specification draft. Position closedclaw as both a technical project and a policy contribution to the emerging field of AI data governance.


SECTION 12
Future Roadmap


12. Future Roadmap
12.1 Post-Hackathon Priorities
Feature
Description
Browser Extension
Intercepts web-based AI tools (ChatGPT, Claude.ai, Perplexity) at the browser level. Injects memory context without any change to the web UI.
Mobile App
closedclaw sync for iOS/Android — a companion app that syncs (encrypted) memory from mobile AI usage back to the local vault.
Plugin SDK
A simple Python interface for building custom sensitivity classifiers, redaction recognizers, and insight generators that plug into the pipeline.
Community Policies
A community repository of shareable policy rule sets (e.g., 'healthcare worker profile', 'journalist profile') that users can import and apply.
Hardware Security
macOS Secure Enclave and Linux TPM integration for KEK storage — the master key is hardware-bound and cannot be exported even with root access.
AICR Standard v1.0
Publish the AI Consent Receipt specification as an open RFC and submit to relevant standards bodies (W3C Credentials CG, IETF SCITT).



Appendix A — Glossary
Term
Definition
AICR
AI Consent Receipt — the open consent documentation standard proposed by closedclaw
ClawdBot
The bundled reference AI companion agent that ships with closedclaw, demonstrating Track 2 capabilities
Consent Gate
The pipeline stage that pauses a request to ask for user permission before a sensitive memory is included
DEK
Data Encryption Key — a per-memory-chunk AES-256 key
Insight Engine
The local analysis process that mines the memory store for trends, summaries, and contradictions without sending data externally
KEK
Key Encryption Key — the master key derived from the user's passphrase; encrypts all DEKs; never stored on disk
mem0
The open-source memory library that closedclaw extends as its storage and retrieval engine
Privacy Firewall
The multi-stage pipeline (retrieve → classify → redact → gate → inject) that governs what context reaches the LLM
Sensitivity Level
A 0–3 score on every memory: 0=public, 1=general personal, 2=personal, 3=highly sensitive
TTL
Time To Live — an optional expiry on memories; when reached, the DEK is destroyed (cryptographic deletion)


Appendix B — Dependencies
Package
License
Use
fastapi
MIT
Backend API framework
uvicorn
BSD
ASGI server for FastAPI
mem0ai
Apache 2.0
Core memory engine (forked and extended)
spacy
MIT
NLP and NER pipeline
presidio-analyzer
MIT
PII detection (Microsoft)
cryptography
Apache 2.0 / BSD
AES-GCM, Ed25519, Argon2id
langgraph
MIT
Agent state machine for ClawdBot
sqlite-vec
Apache 2.0
Vector search extension for SQLite
ollama
MIT
Local LLM inference
typer
MIT
CLI framework
react + vite
MIT
Frontend framework
tailwindcss
MIT
Frontend styling
shadcn/ui
MIT
React component library


