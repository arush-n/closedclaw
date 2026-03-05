Openclaw: Technical Implementation Plan
Current Codebase Audit
Before building, here is what already exists and what is missing:

What Is Built (Closedclaw foundation)
Component	File	Status
MakerAgent	swarm/maker.py	Complete
AccessorAgent	swarm/accessor.py	Complete
GovernanceAgent	swarm/governance.py	Complete
SentinelAgent	swarm/sentinel.py	Complete
ArbitratorAgent	swarm/arbitrator.py	Complete
AuditorAgent	swarm/auditor.py	Complete
PIIRedactor	privacy/redactor.py	Complete
PrivacyFirewall	privacy/firewall.py	Complete
Ed25519 + AES-256-GCM crypto	core/crypto.py	Complete
SwarmCoordinator	swarm/coordinator.py	Complete
ToolRegistry + SwarmTools	swarm/tools.py	Complete
FastAPI server + all routes	api/app.py	Complete
TypeScript crypto/vault/consent lib	lib/src/	Complete
What Is Missing (Gaps to Fill)
Component	Team	Priority
InjectorAgent — prompt rule injection	Addon	High
AddonMemoryAgent — copyright + contextual requests	Addon	High
ProcessorAgent — secondary redaction pass	Tools	High
Server termination lock — password-gated shutdown	Core	High
Localhost handshake protocol — signed session tokens	Core	High
Browser extension integration routes — /addon/* API surface	Addon	Medium
Per-tool specialized agents	Tools	Medium
Browser extension manifest + content scripts	Browser	Medium
1. Tech Stack Recommendation
Backend (Localhost Server)
Layer	Technology	Rationale
API framework	FastAPI + uvicorn (already in use)	Async, fast, OpenAPI autodoc
Memory / vector store	sqlite-vec (already in use)	Embedded, no server process, encrypted at rest
LLM inference	Ollama (already in use)	Local-only, no data leaves device
Encryption	cryptography lib — AES-256-GCM + Ed25519 (already in use)	Zero external deps, FIPS-compatible
Key derivation	Scrypt (already in use) → migrate to Argon2id	Argon2id is memory-hard, more phishing-resistant
Process management	systemd / launchd service + SIGTERM intercept	Enables termination lock
Agent orchestration	Closedclaw swarm (already in use)	In-process, signed messaging
Browser Extension
Layer	Technology	Rationale
Extension framework	Manifest V3 (Chrome/Firefox/Safari)	Current standard, service-worker model
Crypto in-browser	WebCrypto API (browser native)	No external deps, FIPS-grade
Build	esbuild / Vite	Fast, tree-shakes dead code
Language	TypeScript (already in lib/)	Type-safe, existing crypto lib
Communication	WebExtension API → fetch to localhost:8765	Already compatible with existing server
Content script isolation	Shadow DOM + message passing	Prevents page JS from reading injected context
Security Primitives Summary

Browser Extension
  └─ WebCrypto: AES-256-GCM session key negotiation
  └─ Ed25519: addon identity keypair
  └─ Fetch → http://localhost:8765  (CORS locked to localhost)

Localhost Server
  └─ Ed25519 per-agent keypairs  (already: ~/.closedclaw/keys/agents/)
  └─ AES-256-GCM envelope encryption per memory  (already: core/crypto.py)
  └─ Argon2id passphrase → KEK derivation
  └─ Hash-chained audit log  (already: AuditorAgent)
  └─ Signed session token  (already: ~/.closedclaw/token)
  └─ Termination lock (NEW: SIGTERM interceptor + password gate)
2. Security Protocol: Localhost Handshake + Termination Lock
2a. Localhost Session Handshake
The existing ~/.closedclaw/token provides API bearer auth. This needs to be extended with a challenge-response handshake for the browser addon so it cannot be spoofed by a malicious web page.

Protocol (new, to implement in Phase 1):


Step 1 — Addon registers identity (one-time, on install)
  POST /addon/register
  Body: { addon_pubkey: Ed25519PublicKey_b64 }
  Response: { session_challenge: random_32_bytes_b64 }

Step 2 — Addon signs challenge
  POST /addon/auth
  Body: {
    session_challenge: <from step 1>,
    signature: Ed25519Sign(challenge, addon_private_key)
  }
  Response: {
    session_token: HMAC_SHA256(challenge + server_secret),
    expires_in: 3600
  }

Step 3 — All subsequent requests
  Header: X-Addon-Session: <session_token>
  Header: X-Addon-Nonce: <AES-GCM nonce>
  Body: AES-256-GCM encrypted payload (key = session_shared_key)
Implementation location: new file api/routes/addon.py, new middleware api/core/addon_auth.py.

2b. Server Termination Lock
The server intercepts SIGTERM / SIGINT and requires a password before shutdown. Prevents browser tab closes or system signals from killing the process inadvertently.

Implementation:


# api/core/termination_lock.py  (NEW FILE)

import signal, sys, getpass, hashlib

class TerminationLock:
    """Blocks SIGTERM/SIGINT until the correct shutdown password is provided."""

    def __init__(self, password_hash: bytes):
        self._hash = password_hash
        self._locked = True
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        if not self._locked:
            sys.exit(0)
        # Prompt via shutdown API endpoint — do NOT exit
        logger.warning("Termination blocked — send DELETE /server/shutdown with password")

    def unlock(self, password: str) -> bool:
        candidate = hashlib.argon2_hash(password)  # use argon2-cffi
        if candidate == self._hash:
            self._locked = False
            return True
        return False
Shutdown API (new endpoint in api/routes/health.py):


DELETE /server/shutdown
Body: { password: "..." }
→ validates via TerminationLock.unlock() → graceful uvicorn shutdown
3. Data Flow Diagram

╔══════════════════════════════════════════════════════════════════════╗
║  BROWSER                                                             ║
║  ┌─────────────────────────────────────────────────────────────┐    ║
║  │  Content Script (injected into every page)                  │    ║
║  │    1. Captures user input from <textarea> / chat UI         │    ║
║  │    2. AES-GCM encrypts payload with session key             │    ║
║  │    3. POST → http://localhost:8765/addon/process            │    ║
║  └─────────────────────────────────────────────────────────────┘    ║
║           │ encrypted + signed request                              ║
╚═══════════╪══════════════════════════════════════════════════════════╝
            │
╔═══════════╪══════════════════════════════════════════════════════════╗
║  LOCALHOST SERVER  (closedclaw / openclaw)                           ║
║           ▼                                                          ║
║  ┌─────────────────────────────────────────────────────────────┐    ║
║  │  POST /addon/process                                        │    ║
║  │    → AddonAuthMiddleware: verify session token + decrypt    │    ║
║  └──────────────────────┬──────────────────────────────────────┘    ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  InjectorAgent  (NEW)                          │        ║
║           │    • Loads active rules from Constitution       │        ║
║           │    • Loads user memory rules (Accessor)         │        ║
║           │    • Builds system prompt prefix with context   │        ║
║           │    • Stamps: user_id, provider, session_token   │        ║
║           └─────────────┬──────────────────────────────────┘        ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  AddonMemoryAgent  (NEW)                       │        ║
║           │    • Checks copyright flags on retrieved memory │        ║
║           │    • Marks memory-origin sources for citation   │        ║
║           │    • Requests consent for new memory capture    │        ║
║           └─────────────┬──────────────────────────────────┘        ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  ProcessorAgent  (NEW)                         │        ║
║           │    • Retrieves memories (delegates→Accessor)    │        ║
║           │    • Runs secondary redaction (PIIRedactor)     │        ║
║           │    • Applies provider-specific sensitivity rules│        ║
║           │    • Packages sanitized context block           │        ║
║           └─────────────┬──────────────────────────────────┘        ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  GovernanceAgent  (existing)                   │        ║
║           │    • PrivacyFirewall: permit / block / consent  │        ║
║           │    • Constitution compliance check              │        ║
║           └─────────────┬──────────────────────────────────┘        ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  AuditorAgent  (existing)                      │        ║
║           │    • Hash-chain audit entry appended            │        ║
║           │    • Ed25519 signature on context injection     │        ║
║           └─────────────┬──────────────────────────────────┘        ║
║                         │                                            ║
║           ┌─────────────▼──────────────────────────────────┐        ║
║           │  Response to Browser                           │        ║
║           │    { enriched_prompt, context_text,            │        ║
║           │      redaction_map, audit_id, consent_required }│        ║
║           └────────────────────────────────────────────────┘        ║
╚══════════════════════════════════════════════════════════════════════╝
            │ enriched response
╔═══════════╪══════════════════════════════════════════════════════════╗
║  BROWSER  ▼                                                          ║
║  ┌─────────────────────────────────────────────────────────────┐    ║
║  │  Content Script                                             │    ║
║  │    • Injects enriched_prompt invisibly into the AI chat     │    ║
║  │    • If consent_required → shows popup to user              │    ║
║  │    • Replaces user-facing text with de-redacted response    │    ║
║  └─────────────────────────────────────────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════════════╝
4. Milestone Roadmap
Phase 1 — Core Governance (Weeks 1–3)
Goal: All seven governance agents fully operational and tested. Security hardening on the server.

1.1 Termination Lock
Create api/core/termination_lock.py — SIGTERM/SIGINT interceptor
Add DELETE /server/shutdown endpoint with Argon2id password verification
Wire into app.py lifespan startup
1.2 Addon Handshake Protocol
Create api/routes/addon.py — POST /addon/register, POST /addon/auth
Create api/core/addon_auth.py — AddonSessionManager with HMAC-signed session tokens
Create AddonAuthMiddleware that decrypts per-request AES-GCM payloads
1.3 Migrate to Argon2id
In core/crypto.py: replace Scrypt with argon2-cffi's argon2.low_level.hash_secret_raw()
Parameters: time_cost=3, memory_cost=65536, parallelism=4, hash_len=32
1.4 Federated Consensus Tests
Write integration tests for the 2/3 vote system in SwarmCoordinator._federated_consensus()
Test conflict paths in ArbitratorAgent — constitutional vs LLM resolution
Deliverable: Server boots, all 7 agents sign messages correctly, shutdown requires password, addon sessions are established with challenge-response.

Phase 2 — Memory Processing & Addon Agents (Weeks 4–7)
Goal: Build the three missing agents: InjectorAgent, AddonMemoryAgent, ProcessorAgent.

2.1 InjectorAgent — api/agents/swarm/injector.py

class InjectorAgent(BaseAgent):
    AGENT_NAME = "injector"
    """
    Builds the system prompt prefix for every request.
    No LLM call — pure rule assembly.
    
    Outputs:
      - system_prefix: str  (injected before user prompt)
      - active_rules: List[str]
      - memory_context: str  (from AccessorAgent delegation)
    """

    async def handle(self, message, context):
        rules = self._constitution.get_active_rules()
        memory_context = context.get("context_text", "")
        user_id = context.get("user_id", "default")
        provider = context.get("provider", "ollama")

        prefix_lines = [
            f"[SYSTEM: Memory-enabled session for user {user_id}]",
            f"[PROVIDER: {provider}]",
        ]
        for rule in rules[:10]:
            prefix_lines.append(f"[RULE: {rule}]")
        if memory_context:
            prefix_lines.append(f"[CONTEXT: {memory_context[:1000]}]")

        prefix = "\n".join(prefix_lines)
        return self._make_response(
            recipient="coordinator",
            payload={
                "system_prefix": prefix,
                "active_rules": rules,
                "injected_context_len": len(memory_context),
                "llm_calls": 0,
                "context_updates": {"system_prefix": prefix},
            },
            in_reply_to=message.message_id,
        )
Add to coordinator factory + pipeline:


SwarmTaskType.ADDON_PROCESS: [
    "accessor",       # retrieve memories
    "governance",     # firewall
    "injector",       # build enriched prompt  (NEW)
    "addon_memory",   # copyright + consent    (NEW)
    "processor",      # secondary redaction    (NEW)
    "auditor",        # log injection
]
2.2 AddonMemoryAgent — api/agents/swarm/addon_memory.py

class AddonMemoryAgent(BaseAgent):
    AGENT_NAME = "addon_memory"
    """
    Handles copyright attribution and contextual memory requests from the addon.
    No LLM call for standard flow; 1 call for copyright ambiguity resolution.

    Responsibilities:
    - Tag memories that originated from copyrighted sources
    - Decide whether to cite or suppress source in response
    - Trigger consent if new memory capture is detected
    """
Key logic:

Scan retrieved_memories for source field — if source matches a known copyright registry (stored in constitution), attach citation flag
If the incoming request contains capture_new_memory: true, delegate to MakerAgent, then route to GovernanceAgent for consent check
Return copyright_citations: List[str] and consent_required: bool
2.3 ProcessorAgent — api/agents/swarm/processor.py

class ProcessorAgent(BaseAgent):
    AGENT_NAME = "processor"
    """
    Secondary redaction pass — applies provider-specific PII rules
    to the assembled context before it leaves the server.
    No LLM call.

    Responsibilities:
    - Apply redactor.redact_for_provider() on assembled context_text
    - Apply redactor on system_prefix if provider is cloud
    - Return sanitized_context and redaction_summary for audit
    """
Key logic (0 LLM calls):


from closedclaw.api.privacy.redactor import PIIRedactor

redactor = PIIRedactor()
result = redactor.redact_for_provider(
    text=context.get("context_text", ""),
    provider=context.get("provider", "ollama"),
)
# Store redaction_map in encrypted audit entry only — never send to cloud
2.4 Pipeline Registration
Update coordinator.py:

Add "injector", "addon_memory", "processor" to _create_agent()
Add ADDON_PROCESS task type to TASK_PIPELINES
Update DEFAULT_AGENT_TOOLS in tools.py for the three new agents
Deliverable: Full addon processing pipeline runs end-to-end. Context is injected, redacted, and audited before leaving the server.

Phase 3 — Browser Extension Integration (Weeks 8–11)
Goal: Functional browser extension for Chrome/Firefox that intercepts AI chat inputs and enriches them via the localhost server.

3.1 Extension Architecture

extension/
  manifest.json            (MV3)
  background/
    service_worker.ts      (manages sessions, token refresh)
    handshake.ts           (implements challenge-response with /addon/auth)
  content_scripts/
    interceptor.ts         (hooks into chat UI text submission)
    injector.ts            (inserts enriched prompt invisibly)
    consent_ui.ts          (renders consent popup via Shadow DOM)
  popup/
    popup.html/.ts         (settings, memory viewer, on/off toggle)
  lib/ → (existing closedclaw lib: crypto, consent, vault)
3.2 Content Script: Interceptor
The interceptor hooks EventTarget.prototype.addEventListener to catch submit/keydown Enter events before they reach the page's own handlers:


// content_scripts/interceptor.ts
document.addEventListener("submit", async (e) => {
    const textarea = findChatTextarea(); // site-specific selector
    if (!textarea) return;

    const originalText = textarea.value;
    e.preventDefault();
    e.stopImmediatePropagation();

    const enriched = await sendToLocalhost(originalText);
    if (enriched.consent_required) {
        await showConsentPopup(enriched);
    }

    textarea.value = enriched.enriched_prompt;
    // Re-dispatch submit
    textarea.dispatchEvent(new Event("submit", { bubbles: true }));
}, true); // capture phase — runs before page handlers
3.3 Localhost Communication

// background/handshake.ts
async function getSessionToken(): Promise<string> {
    // Step 1: register addon keypair (generated via WebCrypto, stored in extension storage)
    const { publicKey, privateKey } = await generateAddonKeypair();

    // Step 2: POST /addon/register → get challenge
    const { session_challenge } = await fetch("http://localhost:8765/addon/register", {
        method: "POST",
        body: JSON.stringify({ addon_pubkey: exportPublicKey(publicKey) })
    }).then(r => r.json());

    // Step 3: sign challenge → POST /addon/auth → get session_token
    const signature = await signChallenge(privateKey, session_challenge);
    const { session_token } = await fetch("http://localhost:8765/addon/auth", {
        method: "POST",
        body: JSON.stringify({ session_challenge, signature })
    }).then(r => r.json());

    return session_token;
}
3.4 Site-Specific Selectors
Create content_scripts/sites/ with per-site adapter modules:


sites/chatgpt.ts     → selector: "#prompt-textarea"
sites/claude.ts      → selector: ".ProseMirror"
sites/gemini.ts      → selector: "rich-textarea textarea"
sites/perplexity.ts  → selector: "textarea[placeholder]"
sites/generic.ts     → fallback: first textarea with visible area
Each adapter implements interface SiteAdapter { findTextarea(): HTMLElement | null; getSubmitTrigger(): () => void; }.

3.5 Consent UI
The consent popup must be isolated from the page's CSS and JS using Shadow DOM:


// content_scripts/consent_ui.ts
function showConsentPopup(data: EnrichedResponse): Promise<boolean> {
    const host = document.createElement("div");
    const shadow = host.attachShadow({ mode: "closed" });
    shadow.innerHTML = `<style>/* scoped styles */</style>
        <div class="consent-dialog">
            <h3>Memory Capture Request</h3>
            <p>${data.consent_reason}</p>
            <button id="allow">Allow</button>
            <button id="deny">Deny</button>
        </div>`;
    document.body.appendChild(host);
    return new Promise(resolve => {
        shadow.getElementById("allow")!.onclick = () => { host.remove(); resolve(true); };
        shadow.getElementById("deny")!.onclick = () => { host.remove(); resolve(false); };
    });
}
3.6 New Server Routes for Addon
Add to api/routes/addon.py:


POST /addon/register       — register addon Ed25519 pubkey
POST /addon/auth           — challenge-response, return session token
POST /addon/process        — main pipeline: encrypt→process→redact→return
POST /addon/memory/capture — explicit memory save request
GET  /addon/memory/query   — search memories from extension popup
GET  /addon/status         — health + active rules count
Deliverable: Extension installs, authenticates with server, intercepts ChatGPT/Claude inputs, enriches them with memory context, and handles consent UI.

Phase 4 — Multi-Agent Tooling (Weeks 12–16)
Goal: One specialized agent per tool category. Processor as a true agent. Full tool-agent permission matrix.

4.1 Tool Agent Taxonomy
Each "tool category" gets its own agent class that extends BaseAgent. The agent is responsible for validating inputs, executing the tool, and logging to audit.


Tools Team Agents:
  ┌─────────────────────────────────────────────────────┐
  │  WebSearchAgent     — web search with PII filtering  │
  │  CodeExecutorAgent  — sandboxed code runner          │
  │  FileAccessAgent    — local file read/write          │
  │  CalendarAgent      — event read/write               │
  │  EmailAgent         — read-only email parsing        │
  │  BrowserAgent       — page scraping via content script│
  │  NotificationAgent  — OS notification dispatch       │
  └─────────────────────────────────────────────────────┘
Each agent follows the same contract:


class WebSearchAgent(BaseAgent):
    AGENT_NAME = "tool_websearch"

    async def handle(self, message, context):
        # 1. Validate tool input (no PII in search query)
        # 2. Execute tool call
        # 3. Run result through ProcessorAgent (secondary redaction)
        # 4. Log to AuditorAgent
        # 5. Return sanitized result
4.2 ProcessorAgent as Full Pipeline Stage
Move from a simple redaction pass to a proper agent that:

Receives raw tool output
Delegates to AccessorAgent for relevant memory retrieval
Runs PIIRedactor.redact_for_provider() on tool output
Cross-references with SentinelAgent for hallucination risk (if provider is cloud)
Returns sanitized + memory-enriched result
New pipeline for tool calls:


SwarmTaskType.TOOL_CALL: [
    "governance",     # pre-check: is this tool call permitted?
    "tool_<name>",    # execute the specific tool agent
    "processor",      # secondary redaction on output
    "sentinel",       # verify output doesn't contradict memory
    "auditor",        # log tool invocation
]
4.3 Tool Permission Matrix
Extend DEFAULT_AGENT_TOOLS in swarm/tools.py with tool-agent permissions:

Agent	Tools Permitted
tool_websearch	memory_search, log_decision, store_working_memory
tool_code	log_decision, verify_signature
tool_file	memory_search, memory_write, log_decision
tool_calendar	memory_search, memory_write, log_decision
processor	memory_search, delegate_to_agent, log_decision
injector	check_constitution, store_working_memory, log_decision
addon_memory	memory_search, memory_write, request_vote, log_decision
4.4 Constitution Amendments for Tool Access
Add to the Constitution schema:


{
  "tool_policies": [
    { "tool": "web_search",    "requires_consent": false, "blocks_pii_in_query": true },
    { "tool": "file_access",   "requires_consent": true,  "allowed_paths": ["~/Documents"] },
    { "tool": "email_read",    "requires_consent": true,  "sensitivity_floor": 2 },
    { "tool": "code_execute",  "requires_consent": false, "sandboxed": true }
  ]
}
GovernanceAgent reads tool_policies before any tool pipeline is invoked.

4.5 MCP (Model Context Protocol) Tool Agents
The existing routes/mcp.py exposes MCP tool forwarding. In Phase 4, wrap each MCP tool in a dedicated agent so it passes through the governance + processor pipeline before results are returned. This prevents raw MCP tool outputs from bypassing PII redaction.

5. Summary Gap Closure Table
Gap	Phase	Files to Create / Modify
TerminationLock + shutdown endpoint	1	api/core/termination_lock.py (new), api/routes/health.py (add endpoint)
Argon2id migration	1	core/crypto.py
Addon handshake protocol	1	api/routes/addon.py (new), api/core/addon_auth.py (new)
InjectorAgent	2	api/agents/swarm/injector.py (new), coordinator.py
AddonMemoryAgent	2	api/agents/swarm/addon_memory.py (new), coordinator.py
ProcessorAgent	2	api/agents/swarm/processor.py (new), coordinator.py
ADDON_PROCESS pipeline	2	coordinator.py, swarm/models.py
Browser extension scaffold	3	extension/ (new top-level dir), manifest.json, content scripts
Site-specific adapters	3	extension/content_scripts/sites/*.ts
Consent Shadow DOM UI	3	extension/content_scripts/consent_ui.ts
Per-tool specialized agents	4	api/agents/tools/*.py (new files per tool)
Constitution tool policies	4	swarm/constitution.py, constitution JSON
MCP tool agent wrappers	4	routes/mcp.py, new agent wrappers
6. What Can Start Immediately
The highest-value items with zero new dependencies:

ProcessorAgent — all dependencies exist (PIIRedactor, AccessorAgent). Implement and add to coordinator.

InjectorAgent — pure rule assembly, 0 LLM calls. Constitution and AccessorAgent already provide all inputs.

TerminationLock — pure Python signal handling + argon2-cffi (add to pyproject.toml). Self-contained.

Addon routes — the FastAPI pattern is established. POST /addon/register and POST /addon/auth can be built by mirroring the consent route pattern in routes/consent.py and the crypto pattern in core/crypto.py.

The browser extension and multi-agent tooling depend on the above being stable first.

start implementing the plan from phase 1
Update Todos

Create TerminationLock (api/core/termination_lock.py) + shutdown endpoint

Create Addon handshake protocol (api/core/addon_auth.py)

Create Addon API routes (api/routes/addon.py)

Migrate EnvelopeEncryption to Argon2id (core/crypto.py)