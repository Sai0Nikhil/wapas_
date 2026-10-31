# Wapas Backend API Requests & Gaps

This document logs missing or awkward backend endpoints identified while connecting the Flutter client (`wapas_app/`) to `wapas-merchant-os`.

---

## 1. Agent Activity Endpoint (`/api/merchant/agents/activity`)
- **Status:** MISSING from `wapas-merchant-os`
- **Context:** The hackathon requirements specify an Agent Activity screen showing morning brief, restock drafts, Khata reminder drafts, and autonomous recovery audit trail.
- **Requested Endpoint:**
  - `GET /api/merchant/agents/activity`
  - Query parameters: `status` (opt: `DRAFT`, `APPROVED`, `EXECUTED`), `limit` (default 50)
  - Desired response:
    ```json
    {
      "activities": [
        {
          "id": "act_123",
          "agent": "RecoveryAgent",
          "action": "DRAFT_RECOVERY_WHATSAPP",
          "target": "Suresh Gupta",
          "amount_paise": 145000,
          "status": "DRAFT_REVIEW_REQUIRED",
          "confidence": 0.94,
          "created_at": "2026-10-31T08:00:00Z",
          "audit_trail": "Signal detected from UPI gateway fail -> evaluated policy (FAIL_CLOSED) -> draft generated"
        }
      ]
    }
    ```
- **Flutter Client Workaround:**
  The Flutter app interfaces this through `AgentsRepo` with a clean interface. Until the backend exposes `/api/merchant/agents/activity`, `AgentsRepo` synthesizes recent activity from `/api/state` events and `/api/merchant/opportunities/pulse`.

---

## 2. Counter Voice Parse Compatibility
- **Status:** ADAPTED to `/api/merchant/sarkar/ask` and `/api/merchant/bills/{bill_id}/input/voice`
- **Context:** The old prototype in `wapas/app/` had a standalone `/khata/voice-parse` endpoint.
- **Merchant OS Standard:** In `wapas-merchant-os`, counter voice inputs are routed to:
  - `POST /api/merchant/bills/{bill_id}/input/voice` (for draft bill lines)
  - `POST /api/merchant/sarkar/ask` with `audio_base64` (for conversational khata commands and inquiries).
