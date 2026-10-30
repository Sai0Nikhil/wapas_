# Payment lifecycle and Sound Mode — implemented boundary

Updated: 2026-10-29. This describes current implementation and its tested local behavior. It does not claim a live Paytm integration.

## Canonical payment facts

- `Payment` is the persistent attempt record with expected amount in paise, currency, merchant/store, source type and ID, provider order/link/transaction references, idempotency key, and status.
- Merchant OS sources include `COUNTER_BILL`, `SHOP_ORDER`, and `KHATA_COLLECTION`; existing recovery uses `RECOVERY`.
- Provider states include `INIT_UNKNOWN`, `PENDING`, `PENDING_RECONCILIATION`, `INIT_FAILED`, `SUCCESS`, `FAILED`, and `SIMULATED` for explicit Counter/Khata demo results. Unknown/ambiguous status remains unresolved.
- The fake gateway is a test simulator, not a record that money moved. Counter and Khata show `SIMULATED` and do not make verified collection/ledger changes. A fake Shop checkout can exercise the order/stock transition and must still be represented to users as simulated.

## Verification and settlement

Callbacks are hints. Callback handlers validate authenticity where supported, retrieve provider-side status, and pass the result through the shared settlement path. Before accepting a Paytm terminal result, code checks configured MID, expected order or link ID, currency, exact amount, transaction ID, and source reference against the persisted Payment and business record. A redirect, callback body alone, or client-submitted success cannot establish payment.

For a verified Paytm result, the caller applies the source-specific effect, updates Payment, appends audit, and inserts the SoundEvent in one database transaction:

1. `SHOP_ORDER`: complete the held inventory reservations and set payment status; fulfillment remains separate.
2. `COUNTER_BILL`: complete its stock reservations and mark the bill paid once.
3. `KHATA_COLLECTION`: append one Paytm-verified repayment linked to that Payment.
4. `RECOVERY`: use the existing recovery settlement path.

Wrong amount, identity/source mismatch, ambiguous status, stale attempt, and duplicate/conflicting terminal result are not silently accepted. Fake or non-Paytm success does not create a Paytm SoundEvent. The fake Shop state transition remains demo-only.

## Sound Mode event and delivery

- The outbox stores merchant/store, payment/source references, verified amount/currency, provider transaction reference, idempotency key, and verified timestamp. It stores no credentials.
- A unique SoundEvent is written during the verified settlement transaction. It becomes available only after that transaction commits.
- The signed-in owner registers a device key scoped to merchant/store. A newly registered or reopened device starts at the latest event to avoid playing old payments unexpectedly.
- Polling returns events after that cursor. Acknowledgement advances the device cursor; an event is not announced twice by replay.
- Sound is muted by default. The UI reports playback only when browser audio playback succeeds. A blocked browser does not change payment state.
- No client payment state, fake gateway result, or failed/mismatched status can create a Paytm SoundEvent.

## Local evidence and limits

Tests cover exact source, merchant/order/amount/currency binding; wrong and ambiguous status; fake silence; one-time source effect; outbox idempotency; and device cursor behavior. No Paytm test/live transaction, real callback, real alert, or browser audio test was performed in this implementation cycle. See [verification matrix](verification-matrix.md).
