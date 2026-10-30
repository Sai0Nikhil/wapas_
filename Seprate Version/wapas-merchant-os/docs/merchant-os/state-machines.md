# Wapas Merchant OS — implemented state machines

Updated: 2026-10-29. These values are taken from the current models and domain services. Some older recovery states are described in the original recovery documentation.

## Counter bill

Bill lifecycle:

```text
DRAFT ──issue──> ISSUED ──eligible cancel──> CANCELLED
```

Draft lines can be changed or removed. Issue resolves current product prices and quantities, recomputes totals, records immutable line snapshots, and reserves physical stock. An issued bill cannot be edited or deleted. Cancellation is allowed only where the bill has no paid, pending/uncertain payment, or Khata credit; it releases held reservations. The transition to `CANCELLED` preserves the issued record.

The bill has a separate payment projection: `NOT_RECORDED`, `PENDING`, `PAID`, `FAILED`, or `SIMULATED`. Fake Counter success is `SIMULATED`, does not set a verified paid timestamp, and does not consume the stock reservation. A verified Paytm success sets `PAID` and consumes the reservation. A bill added to Khata has a credit ledger entry and cannot also use a Counter payment request.

## Payment record

The shared Payment model uses statuses including `INIT_UNKNOWN`, `PENDING`, `PENDING_RECONCILIATION`, `INIT_FAILED`, `SUCCESS`, `FAILED`, and `SIMULATED`. A provider callback is an input to reconciliation, not a terminal fact. Verified Paytm settlement requires the configured merchant identity, matching order/link ID, INR, exact amount, transaction identity, and a matching source record. Any mismatch or unresolved source leaves the payment pending reconciliation. Repeating the same terminal response is idempotent; a conflicting terminal result is not silently accepted.

Source effects are distinct:

- `SHOP_ORDER`: accepted successful settlement consumes the held reservation and sets the order to `PAID`; failure releases the reservation. Fake checkout is simulator evidence only.
- `COUNTER_BILL`: verified Paytm success consumes its reservation and marks the bill `PAID`; fake success marks it `SIMULATED` and leaves stock held.
- `KHATA_COLLECTION`: verified Paytm success appends one repayment entry; fake success is `SIMULATED` and does not change the ledger.
- `RECOVERY`: retains the existing recovery workflow and its own reconciliation behavior.

Only verified Paytm settlement for the supported source paths can create a SoundEvent.

## Shop order and fulfillment

```text
PAYMENT_PENDING ──verified success──> PAID
       │                                │
       ├──verified failure──> PAYMENT_FAILED
       └──separate fulfillment action──> FULFILLED (only after PAID)
```

Order payment status is `PAYMENT_PENDING`, `PAID`, `PAYMENT_FAILED`, or `CANCELLED`. Fulfillment is separately `UNFULFILLED` or `FULFILLED`. Stock is reserved at checkout, consumed on successful settlement, and released on a resolved failure. A fake checkout result exercises the state transition but does not prove that money moved. Fulfillment requires an explicit owner confirmation and a `PAID` order.

## Inventory reservation

```text
HELD ──complete──> CONSUMED
  └──release/expiry──> RELEASED
```

Held quantity reduces available stock without reducing on-hand stock. Completion and release are one-time transitions. Stock movements preserve the receipt, sale, adjustment, reservation, release, and consumption history. Writes validate nonnegative available stock and use transactional updates. Counter reservations are held at issue; Shop reservations at checkout.

## Khata

Ledger entry types include `CREDIT_GIVEN`, `REPAYMENT`, `OPENING_BALANCE`, `ADJUSTMENT`, and `REVERSAL`. A positive `delta_paise` increases the amount owed; a negative delta reduces it. The ledger is append-only, and one reversal may compensate a source entry. Account balance is guarded by a transactionally updated projection and can be checked from the entry sum.

Manual repayment requires explicit confirmation and is marked as a merchant-confirmed receipt. A pending Paytm collection blocks a separate manual repayment until reconciliation. A verified Paytm collection creates one idempotent `REPAYMENT` linked to the Payment. A fake collection does not create a repayment. An issued Counter bill added to Khata consumes its inventory reservation and creates one credit; paid or pending bills are rejected.

## Sarkar action

Read requests are routed deterministically to one of a small fixed set of saved-record readers. A stock receipt follows:

```text
no action ──prepare──> OPEN ──confirm exact token──> EXECUTED
                         ├──expiry──> EXPIRED
                         └──changed stock/payload──> INVALIDATED
```

Preparation binds product, quantity, actor, current browser session, exact payload hash, and a ten-minute expiry. The owner must confirm the one-time token. Execution rechecks product state and prior stock quantity, applies the movement, and writes audit in the same transaction. Duplicate, wrong-session, expired, replayed, or changed-state confirmations do not repeat the mutation.

## Demand and Sound Mode

Demand events are recorded only for public storefront `NO_MATCH` and `OUT_OF_STOCK` outcomes. Query text is normalized, repeats are deduplicated by store/query/15-minute bucket, and the Pulse requires repeated observations; it does not infer sales.

Sound devices begin muted. A newly registered device starts at the current latest event, so an old event is not played after reopening. Polling returns later merchant/store-scoped verified Paytm events; acknowledging advances the device cursor. Browser audio is played only after a user enables sound and playback succeeds. There is no SMS, Telegram, or WhatsApp alert in this feature slice.
