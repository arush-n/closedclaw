# closedclaw — Remaining Implementation Plan

**Generated:** 2026-02-28  
**Baseline:** Full audit of `src/plan.md` vs current codebase (~10,200 LOC Python backend + ~5,500 LOC TypeScript lib + ~3,500 LOC Next.js UI)

---

## Executive Summary

The backend (FastAPI + privacy pipeline + crypto + vector store) is **~90% complete**. The TypeScript crypto/consent/vault library is **100% complete**. The frontend dashboard is **~95% complete** — all six planned views are implemented with full CRUD, filtering, and backend integration. Remaining items are polish and expanded demo data.

### What's Done

| Component | Plan Section | Status |
|-----------|-------------|--------|
| mem0 fork with extended schema | §3 | ✅ Complete — `ClosedclawMemory` wraps mem0 with sensitivity, tags, TTL, consent fields |
| FastAPI skeleton + auth + health | §9 Week 1 | ✅ Complete — app.py, deps.py, routes/health.py |
| Privacy Firewall (full pipeline) | §4 | ✅ Complete — classifier.py, detector.py, redactor.py, firewall.py |
| OpenAI-compatible proxy | §5.1 | ✅ Complete — routes/proxy.py, streaming, multi-provider |
| Policy engine + default rules | §4.2 | ✅ Complete — 7 default rules, JSON format, priority evaluator |
| PII detection (Presidio + fallback) | §4.3 | ✅ Complete — 22 entity types, regex fallback |
| Sensitivity classifier (3-tier) | §3.3 | ✅ Complete — NER → keyword → override priority |
| PII redactor (5 styles) | §4.3 | ✅ Complete — typed placeholders, reversible mappings |
| Consent workflow (API + WebSocket) | §4.4 | ✅ Complete — routes/consent.py, ws_consent.py |
| Audit log (hash-chained, signed) | §6.3 | ✅ Complete — routes/audit.py, Ed25519 signing |
| Crypto layer (AES-GCM, Ed25519, Scrypt) | §6.1 | ✅ Complete — core/crypto.py, Python + TS implementations |
| SQLite vector store + mem0 adapter | §9.1 | ✅ Complete — sqlite_vec.py (1,382 LOC), mem0_adapter.py |
| Persistent storage (audit, consent) | §9 | ✅ Complete — core/storage.py (SQLite-backed) |
| CLI (serve, init, config, export, import) | §8 | ✅ Complete — cli.py (490 LOC) |
| Local LLM config (Ollama, hardware profiles) | §8 | ✅ Complete — core/local.py (607 LOC) |
| Memory chat via Ollama | §5.3 | ✅ Complete — routes/memory_chat.py |
| TS crypto library (AES, Ed25519, Argon2id, envelope) | §6.1 | ✅ Complete — lib/src/crypto/ |
| TS consent receipts library | §6.2 | ✅ Complete — lib/src/consent/ |
| TS vault library | §3 | ✅ Complete — lib/src/vault/ |
| Graph visualization UI | (bonus) | ✅ Complete — D3 force + canvas renderer |
| Chat sidebar UI | §7.2.1 | ✅ Complete — chat works with Context Inspector + ClawdBot toggle |

### What's NOT Done

| # | Feature | Plan Section | Priority | Status |
|---|---------|-------------|----------|--------|
| 1 | **Extended metadata persistence** | §3.2 | 🔴 Critical | ✅ Complete — `storage.py` has SQLite tables, `memory.py` reads/writes |
| 2 | **Encryption at rest wired into memory path** | §3.4 | 🔴 Critical | ✅ Complete — `memory.py` uses `EnvelopeEncryption` in add/load paths |
| 3 | **Server startup fix** (port binding failures) | §8 | 🔴 Critical | ✅ Complete — resolved import/port issues |
| 4 | **Context Inspector panel** | §7.2.1 | 🟡 High | ✅ Complete — `context-inspector.tsx` wired into `agent-message.tsx` |
| 5 | **Memory Vault view** | §7.2.2 | 🟡 High | ✅ Complete — `vault/page.tsx` with search + sensitivity filtering |
| 6 | **Audit Log view** | §7.2.3 | 🟡 High | ✅ Complete — `audit/page.tsx` with filters, chain verify, export |
| 7 | **Policy Manager view** | §7.2.4 | 🟡 High | ✅ Complete — `policies/page.tsx` with CRUD, compliance profiles, test |
| 8 | **Consent Notifications view** | §7.2.6 | 🟡 High | ✅ Complete — `consent/page.tsx` + `consent-center.tsx` with WebSocket |
| 9 | **Insights view + Insight Engine** | §7.2.5 + §6.4 | 🟠 Medium | ✅ Complete — backend + frontend with trends, contradictions, expiry |
| 10 | **ClawdBot LangGraph agent** | §5.3 | 🟠 Medium | ✅ Complete — fallback loop agent (no LangGraph dep), 5 tools, chat toggle |
| 11 | **Writeback policy (auto-extract memories)** | §3.6 | 🟠 Medium | ✅ Complete — `_run_writeback_policy()` in proxy.py |
| 12 | **Consent preference persistence** | §4.4 | 🟢 Low | ✅ Complete — `save_consent_preference()` wired, `get_auto_consent_decision()` added |
| 13 | **Differential privacy on retrieval scores** | §4.1 | 🟢 Low | ✅ Complete — Laplace noise in proxy enrichment path |
| 14 | **Dashboard navigation + layout shell** | §7.1 | 🟡 High | ✅ Complete — sidebar nav with all views |
| 15 | **Demo mode with pre-populated data** | §8.4 | 🟢 Low | ⚠️ Partial — `_load_demo_data()` seeds 5 memories |
| 16 | **Sidebar actions (Add Memory, etc.)** | §7.2.2 | 🟢 Low | ✅ Complete — Add Memory modal on graph page |

---

## Detailed Gap Analysis

### GAP 1 — Extended Metadata Not Persisted (Critical)

**Location:** `api/core/memory.py` — `_extended_metadata` is a plain Python `dict`  
**Impact:** Sensitivity levels, tags, access counts, consent flags, and TTL are **lost on every server restart**. This means the Privacy Firewall has no persistent sensitivity data to evaluate — the core privacy promise is broken across restarts.

**Fix:**
- Add an `extended_metadata` table to `core/storage.py` (SQLite) with columns: `memory_id`, `sensitivity`, `tags` (JSON), `source`, `expires_at`, `content_hash`, `encrypted`, `dek_enc`, `access_count`, `last_accessed`, `consent_required`
- Modify `ClosedclawMemory.add()`, `search()`, `get()`, `update()`, `delete()` to read/write extended metadata from SQLite
- Load all extended metadata into an in-memory cache on startup, write-through on mutations
- Alternatively, leverage the existing `SQLiteVecStore` metadata table which already has all these columns — wire `ClosedclawMemory` to use it

### GAP 2 — Encryption at Rest Not Wired (Critical)

**Location:** `api/core/crypto.py` has `EnvelopeEncryption` with `encrypt_memory()` / `decrypt_memory()` / `destroy_dek()` — but `api/core/memory.py` never calls them  
**Impact:** Memory content is stored in plaintext. The plan promises AES-256-GCM encryption per memory chunk. The code exists but isn't connected.

**Fix:**
- In `ClosedclawMemory.add()`: after mem0 extracts the memory text, call `EnvelopeEncryption.encrypt_memory()` before storing
- In `ClosedclawMemory.search()` / `get()`: call `decrypt_memory()` before returning results
- In `ClosedclawMemory.delete()`: call `destroy_dek()` for cryptographic deletion
- Store `dek_enc` (wrapped DEK) in the extended metadata table
- Handle the KEK lifecycle: derive from passphrase on server start, hold in memory, never persist

### GAP 3 — Server Startup Failures (Critical)

**Evidence:** Terminal history shows 15+ failed `uvicorn` start attempts with exit code 1  
**Impact:** The system cannot be demoed or used until this is resolved.

**Fix:**
- Capture the actual error output from `uvicorn closedclaw.api.app:app`
- Likely causes: port already in use (need cleanup), import errors (missing optional deps), or module path issues
- Add graceful startup error handling and port-in-use detection to `cli.py serve()`

---

### GAP 4 — Context Inspector Panel (High)

**Plan:** §7.2.1 — "For every message sent, the Inspector shows in real time which memories were retrieved, their sensitivity levels, what was redacted, which provider was used, and a direct link to the audit log entry."  
**Current:** The chat sidebar shows related memories but no inspection of the privacy pipeline.

**Implementation:**
- The proxy already returns `closedclaw_metadata` (memories used, redactions, provider, audit entry ID) in the response — this data is available
- Build a `ContextInspector` React component that renders:
  - Retrieved memories with sensitivity badges (color-coded Level 0-3)
  - Redaction map (entity → placeholder)
  - Provider name + token count
  - Link to audit entry
- Add it as a collapsible right panel in the chat view
- Connect via the `closedclaw_metadata` field in proxy responses

### GAP 5 — Memory Vault View (High)

**Plan:** §7.2.2 — "A searchable, filterable grid of all stored memories. Each memory card shows the text, sensitivity badge, tags, creation date, and expiry date."

**Implementation:**
- New route: `/vault` with `app/vault/page.tsx`
- Components needed:
  - `MemoryCard` — displays memory text, sensitivity badge (color-coded), tags as chips, dates, access count
  - `VaultSearch` — search bar with semantic search via `/v1/memory?q=`
  - `VaultFilters` — filter by sensitivity (0-3), tags, source, expiry status
  - `MemoryDetailModal` — edit sensitivity/tags/TTL, view access history, delete button
  - `BulkActions` — select multiple, bulk delete, bulk tag
- API endpoints already exist: `GET /v1/memory` (search), `GET /v1/memory/all` (list), `GET /v1/memory/tags`, `PATCH /v1/memory/{id}`, `DELETE /v1/memory/{id}`

### GAP 6 — Audit Log View (High)

**Plan:** §7.2.3 — "A chronological timeline of every LLM request. Chain integrity status at the top. Export button. Click for detail view."

**Implementation:**
- New route: `/audit` with `app/audit/page.tsx`
- Components needed:
  - `AuditTimeline` — chronological list of entries with timestamp, provider icon, summary, consent badge
  - `AuditEntryDetail` — expandable detail: memories used, redactions applied, consent receipts, full request metadata
  - `ChainIntegrityBanner` — calls `GET /v1/audit/verify`, shows pass/fail
  - `AuditExport` — button calling `GET /v1/audit/export`
  - Filter controls: date range, provider, consent-only
- API endpoints already exist: `GET /v1/audit`, `GET /v1/audit/verify`, `GET /v1/audit/export`, `GET /v1/audit/{id}`

### GAP 7 — Policy Manager View (High)

**Plan:** §7.2.4 — "A GUI for creating and managing privacy rules. Compliance profile selector (HIPAA/GDPR/COPPA). Test panel."

**Implementation:**
- New route: `/policies` with `app/policies/page.tsx`
- Components needed:
  - `PolicyList` — shows all active rules with priority, conditions, action badge
  - `PolicyEditor` — form-based rule builder: condition pickers (tags, sensitivity, provider), action selector (PERMIT/REDACT/BLOCK/CONSENT), priority slider
  - `ComplianceProfiles` — one-click buttons for HIPAA, GDPR, COPPA modes
  - `PolicyTestPanel` — enter hypothetical memory text, see how current rules would handle it
- Backend needs: 
  - `POST /v1/policies` — create new rule (write to `~/.closedclaw/policies/`)
  - `PUT /v1/policies/{id}` — update rule
  - `DELETE /v1/policies/{id}` — delete rule
  - `POST /v1/policies/test` — evaluate a test memory against current rules
  - `GET /v1/policies` — list all rules
  - These routes don't exist yet — need a new `routes/policies.py`

### GAP 8 — Consent Notifications View (High)

**Plan:** §7.2.6 — "Pending consent gate requests appear as a badge + OS-level desktop notifications. Full-screen modal with approve/deny."

**Implementation:**
- Components needed:
  - `ConsentBadge` — notification badge in the navigation bar showing pending count
  - `ConsentModal` — full-screen modal: memory text, proposed redactions, target provider, approve/deny buttons
  - `ConsentHistory` — list of past decisions with receipts
- WebSocket for real-time push already exists (`ws_consent.py`)
- Connect to `GET /v1/consent/pending` for list, `POST /v1/consent/{id}` for decisions
- Add WebSocket listener in the dashboard layout that triggers consent modals

### GAP 9 — Insight Engine + Insights View (Medium)

**Plan:** §6.4 — "Life Summary, Trend Detection, Contradiction Alerts, Memory Expiry Review. Runs locally on Ollama."

**Implementation:**
- Backend (`api/core/insights.py`):
  - `InsightEngine` class with four analysis methods
  - `generate_life_summary()` — retrieves recent N weeks of memories, sends to local LLM for summarization
  - `detect_trends()` — groups memories by tags/topics, counts frequency over time windows, identifies recurring themes
  - `find_contradictions()` — compares memories with overlapping tags for semantic contradictions (local LLM)
  - `review_expiring()` — queries memories approaching TTL expiry
  - Scheduler: run on configurable interval (default weekly) or on-demand
- Backend route (`routes/insights.py`):
  - `POST /v1/insights/run` — trigger on-demand analysis
  - `GET /v1/insights` — retrieve latest insight results
  - `GET /v1/insights/trends` — trend data for charts
  - `GET /v1/insights/expiring` — memories nearing expiry
- Frontend (`app/insights/page.tsx`):
  - `LifeSummary` — rendered markdown summary
  - `TrendCards` — topic frequency cards with counts
  - `ContradictionAlerts` — pairs of contradicting memories with explanation
  - `ExpiryReview` — list of expiring memories with extend/expire buttons
  - "Run Insights Now" button

### GAP 10 — ClawdBot LangGraph Agent (Medium)

**Plan:** §5.3 — "LangGraph state machine with memory tools: search_memory, write_memory, request_consent, reflect_on_memories, get_memory_timeline"

**Current:** `routes/memory_chat.py` has a basic Ollama chat with memory context, but NOT a LangGraph agent.

**Implementation:**
- New module `api/agents/clawdbot.py`:
  - LangGraph `StateGraph` with nodes: `route`, `search_memory`, `write_memory`, `request_consent`, `reflect`, `respond`
  - Human-in-the-loop node for consent gate (pause/resume via WebSocket)
  - 5 tools as defined in plan §5.3.1
- New module `api/agents/tools.py`:
  - `search_memory(query, sensitivity_max)` — wraps `ClosedclawMemory.search()`
  - `write_memory(content, sensitivity, tags)` — wraps writeback consent flow
  - `request_consent(memory_id, reason)` — triggers consent gate
  - `reflect_on_memories(topic)` — retrieves + synthesizes via LLM
  - `get_memory_timeline(topic)` — chronological memory retrieval
- Wire into the chat interface as an alternative to direct Ollama chat
- Dependencies: `langgraph`, `langchain-core`

### GAP 11 — Writeback Policy (Medium)

**Plan:** §3.6 — "After every LLM response, mem0's memory extraction runs in the background. Level 0-1 stored immediately. Level 2-3 held pending user approval."

**Current:** The proxy forwards requests and returns responses but does NOT extract memories from conversations.

**Implementation:**
- In `routes/proxy.py`, after receiving the LLM response:
  - Run `ClosedclawMemory.add()` with the conversation messages in a background task
  - mem0 internally decides what to extract
  - After extraction, classify each candidate memory's sensitivity
  - Level 0-1: store immediately
  - Level 2-3: add to pending consent queue, notify via WebSocket
- Use FastAPI `BackgroundTasks` to avoid adding latency to the response

### GAP 12 — Consent Preference Persistence (Low)

**Location:** `routes/consent.py` has two TODOs for `remember_for_provider` and `remember_for_tag`
**Fix:** Store these preferences in the SQLite persistent store; check them during future consent evaluations to auto-approve matching patterns.

### GAP 13 — Differential Privacy on Retrieval (Low)

**Plan:** §4.1 — "Differential privacy noise applied to similarity scores to prevent inference attacks"
**Fix:** In `firewall.py` Stage 1, add Laplacian noise to similarity scores after retrieval. Small change (~20 LOC).

### GAP 14 — Dashboard Navigation + Layout Shell (High)

**Current:** Single `/graph` page with no navigation to other views.

**Implementation:**
- Create a shared layout with sidebar navigation: Graph, Vault, Audit, Policies, Insights, Chat
- Consent badge in the nav bar (real-time via WebSocket)
- System status indicator (connected/disconnected)
- Each view gets its own route under `app/`

### GAP 15 — Demo Mode (Low)

**Plan:** §8.4 — `closedclaw serve --demo` with pre-populated memories  
**Current:** `cli.py` has `_load_demo_data()` that seeds 5 memories — partially done  
**Fix:** Expand demo data to cover all sensitivity levels, multiple tags, some consent-gated memories, and pre-populated audit entries to showcase the full system

### GAP 16 — Sidebar Actions (Low)

**Current:** Graph sidebar has icons for Add Memory, Documents, Spaces, etc. — all unconnected  
**Fix:** Wire "Add Memory" to open a modal calling `POST /v1/memory`. Remove irrelevant items (Billing, Spaces).

---

## Implementation Order

### Phase 1 — Fix Critical Backend Gaps (Days 1-2)

These MUST be done first — the system cannot be demoed without them.

| Task | Effort | Files |
|------|--------|-------|
| 1.1 Diagnose and fix server startup failures | 2h | `api/app.py`, `api/cli.py` |
| 1.2 Persist extended metadata in SQLite | 4h | `api/core/memory.py`, `api/core/storage.py` |
| 1.3 Wire encryption at rest into memory add/get/delete | 4h | `api/core/memory.py`, `api/core/crypto.py` |
| 1.4 Add policy CRUD endpoints | 3h | New: `api/routes/policies.py` |

### Phase 2 — Dashboard Shell + Core Views (Days 3-5)

Build the navigation infrastructure, then the most impactful views.

| Task | Effort | Files |
|------|--------|-------|
| 2.1 Dashboard layout shell with sidebar navigation | 4h | `ui/app/layout.tsx`, new nav component |
| 2.2 Memory Vault view (search, filter, CRUD) | 6h | New: `ui/app/vault/page.tsx`, components |
| 2.3 Audit Log view (timeline, verify, export) | 5h | New: `ui/app/audit/page.tsx`, components |
| 2.4 Context Inspector panel in chat | 4h | New component, modify chat sidebar |
| 2.5 Consent Notifications (badge, modal, WebSocket) | 5h | New components, modify layout |

### Phase 3 — Advanced Features (Days 6-8)

| Task | Effort | Files |
|------|--------|-------|
| 3.1 Policy Manager view (editor, compliance, test) | 6h | New: `ui/app/policies/page.tsx`, components |
| 3.2 Writeback policy (auto-extract + consent gating) | 4h | `api/routes/proxy.py`, `api/core/memory.py` |
| 3.3 Insight Engine backend | 5h | New: `api/core/insights.py`, `api/routes/insights.py` |
| 3.4 Insights dashboard view | 4h | New: `ui/app/insights/page.tsx`, components |

### Phase 4 — ClawdBot + Polish (Days 9-11)

| Task | Effort | Files |
|------|--------|-------|
| 4.1 ClawdBot LangGraph agent + tools | 8h | New: `api/agents/clawdbot.py`, `api/agents/tools.py` |
| 4.2 Wire ClawdBot into dashboard chat | 3h | `ui/components/chat/`, API routes |
| 4.3 Consent preference persistence | 2h | `api/routes/consent.py`, `api/core/storage.py` |
| 4.4 Differential privacy on retrieval | 1h | `api/privacy/firewall.py` |
| 4.5 Expand demo mode data | 2h | `api/cli.py` |
| 4.6 Fix sidebar actions (Add Memory modal) | 1h | `ui/components/graph/sidebar.tsx` |

### Phase 5 — Integration Testing + Demo Prep (Days 12-14)

| Task | Effort | Files |
|------|--------|-------|
| 5.1 End-to-end integration tests | 4h | `tests/` |
| 5.2 Demo scenario walkthrough (Acts 1-5 from plan §10.1) | 3h | Manual testing + fixes |
| 5.3 Error handling polish (loading states, error boundaries) | 3h | UI components |
| 5.4 README + quickstart guide updates | 2h | `README.md` |

---

## Total Estimated Effort

| Phase | Effort | Status |
|-------|--------|--------|
| Phase 1 — Critical Backend Fixes | ~13h | Not started |
| Phase 2 — Dashboard Shell + Core Views | ~24h | Not started |
| Phase 3 — Advanced Features | ~19h | Not started |
| Phase 4 — ClawdBot + Polish | ~17h | Not started |
| Phase 5 — Integration + Demo | ~12h | Not started |
| **Total** | **~85h** | — |

---

## Dependency Graph

```
Phase 1.1 (server fix) ──────────────────────────────────→ ALL
Phase 1.2 (metadata persist) ────→ Phase 2.2 (Vault view)
                                 ├→ Phase 3.2 (writeback)
                                 └→ Phase 3.3 (insights)
Phase 1.3 (encryption wired) ───→ Phase 2.2 (Vault view)
Phase 1.4 (policy CRUD API) ────→ Phase 3.1 (Policy Manager UI)
Phase 2.1 (nav shell) ──────────→ Phase 2.2, 2.3, 2.5, 3.1, 3.4
Phase 2.5 (consent notifications)→ Phase 3.2 (writeback consent flow)
Phase 3.3 (insight engine) ─────→ Phase 3.4 (insights view)
Phase 4.1 (ClawdBot agent) ────→ Phase 4.2 (wire into chat)
```

---

## File Map for New Code

```
src/closedclaw/
├── api/
│   ├── agents/                    # NEW — Phase 4
│   │   ├── __init__.py
│   │   ├── clawdbot.py           # LangGraph agent
│   │   └── tools.py              # Memory tools for agent
│   ├── core/
│   │   ├── insights.py           # NEW — Phase 3.3
│   │   └── (memory.py, storage.py, crypto.py — MODIFIED)
│   └── routes/
│       ├── policies.py           # NEW — Phase 1.4
│       ├── insights.py           # NEW — Phase 3.3
│       └── (proxy.py, consent.py — MODIFIED)
├── ui/
│   ├── app/
│   │   ├── vault/page.tsx        # NEW — Phase 2.2
│   │   ├── audit/page.tsx        # NEW — Phase 2.3
│   │   ├── policies/page.tsx     # NEW — Phase 3.1
│   │   ├── insights/page.tsx     # NEW — Phase 3.4
│   │   ├── chat/page.tsx         # NEW — Phase 2.4 (optional, or keep sidebar)
│   │   └── layout.tsx            # MODIFIED — Phase 2.1
│   └── components/
│       ├── layout/               # NEW — Phase 2.1
│       │   ├── app-sidebar.tsx   # Navigation sidebar
│       │   └── consent-badge.tsx # WebSocket badge
│       ├── vault/                # NEW — Phase 2.2
│       │   ├── memory-card.tsx
│       │   ├── vault-search.tsx
│       │   ├── vault-filters.tsx
│       │   └── memory-detail-modal.tsx
│       ├── audit/                # NEW — Phase 2.3
│       │   ├── audit-timeline.tsx
│       │   ├── audit-entry-detail.tsx
│       │   └── chain-integrity-banner.tsx
│       ├── consent/              # NEW — Phase 2.5
│       │   ├── consent-modal.tsx
│       │   └── consent-history.tsx
│       ├── policies/             # NEW — Phase 3.1
│       │   ├── policy-list.tsx
│       │   ├── policy-editor.tsx
│       │   ├── compliance-profiles.tsx
│       │   └── policy-test-panel.tsx
│       ├── insights/             # NEW — Phase 3.4
│       │   ├── life-summary.tsx
│       │   ├── trend-cards.tsx
│       │   ├── contradiction-alerts.tsx
│       │   └── expiry-review.tsx
│       └── chat/
│           └── context-inspector.tsx  # NEW — Phase 2.4
```
