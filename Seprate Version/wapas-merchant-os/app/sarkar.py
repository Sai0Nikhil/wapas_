"""A deliberately small typed Sarkar router over the merchant domain services.

This first slice is deterministic: it supports read-only stock, Khata, order,
summary and demand tools, plus a one-time confirmed goods-receipt operation.
It never lets language-model text execute SQL or call a gateway.
"""
import hashlib
import hmac
import json
import re
import secrets
import uuid
import concurrent.futures
import contextvars
from dataclasses import dataclass
from datetime import date, datetime, time as day_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Type
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlmodel import select

from . import audit, demand, inventory, khata
from .billing_models import Bill
from .commerce_models import StoreOrder
from .config import get_settings
from .demand import normalize_query
from .merchant_os_models import Product
from .models import Payment
from .sarkar_models import SarkarAction
from .tenant_context import current_identity, current_merchant_id, current_store_id

ENGINE = "DETERMINISTIC_TYPED_ROUTER"
RECEIPT_RE = re.compile(
    r"^\s*(?:we\s+)?(?:received|got|restocked|add(?:ed)?)\s+"
    r"(\d+(?:\.\d{1,3})?)\s*(kg|kilos?|kilograms?|g|grams?|l|lit(?:re|er)s?|"
    r"units?|pieces?|pcs?)?\s+(?:of\s+)?(.+?)\s*[.!]?\s*$", re.I,
)
UNIT_ALIASES = {
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "g": "g", "gram": "g", "grams": "g", "l": "l", "litre": "l", "litres": "l",
    "liter": "l", "liters": "l", "unit": "each", "units": "each", "piece": "each",
    "pieces": "each", "pc": "each", "pcs": "each",
}


class _Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(_Input):
    pass


class QueryInput(_Input):
    query: str = Field(default="", max_length=120)


class LimitInput(_Input):
    limit: int = Field(default=20, ge=1, le=50)


class DaysInput(_Input):
    days: int = Field(default=7, ge=1, le=366)


class DemandInput(_Input):
    days: int = Field(default=30, ge=1, le=90)


class PaymentEvidenceInput(_Input):
    payment_id: str = Field(default="", max_length=100)
    source_type: str = Field(default="", max_length=32)
    source_id: str = Field(default="", max_length=100)

    @model_validator(mode="after")
    def exact_reference(self):
        if not self.payment_id and not (self.source_type and self.source_id):
            raise ValueError("provide a payment_id or both source_type and source_id")
        if bool(self.source_type) != bool(self.source_id):
            raise ValueError("source_type and source_id must be provided together")
        return self


class PeriodInput(_Input):
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def bounded_period(self):
        if bool(self.start_date) != bool(self.end_date):
            raise ValueError("start_date and end_date must be supplied together")
        if self.start_date and (self.end_date < self.start_date or (self.end_date - self.start_date).days > 365):
            raise ValueError("date range must be ordered and no longer than 366 days")
        return self


class KhataHistoryInput(_Input):
    account_id: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=50, ge=1, le=100)


class ReceiptInput(_Input):
    message: str = Field(min_length=1, max_length=1000)


class ConfirmReceiptInput(_Input):
    action_id: str = Field(min_length=1, max_length=80)
    confirmation_token: str = Field(min_length=20, max_length=128)


class ToolEnvelope(BaseModel):
    status: str
    message: str
    data: dict[str, Any]


class PreparedReceiptEnvelope(BaseModel):
    status: str
    engine: str = ENGINE
    message: str
    confirmation: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] | None = None
    tool_trace: list[dict[str, Any]] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    version: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable
    required_role: str
    permission: str
    ownership_rule: str
    classification: str
    approval_required: bool
    idempotency_required: bool
    timeout_seconds: float
    max_retries: int
    post_execution_verification: str

    def public_contract(self) -> dict:
        return {
            "name": self.name, "version": self.version,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "required_role": self.required_role, "permission": self.permission,
            "ownership_rule": self.ownership_rule, "classification": self.classification,
            "approval_required": self.approval_required,
            "idempotency_required": self.idempotency_required,
            "timeout_seconds": self.timeout_seconds, "max_retries": self.max_retries,
            "post_execution_verification": self.post_execution_verification,
        }


def _actor() -> tuple[str, str]:
    identity = current_identity()
    if identity:
        return identity.user_id, identity.session_hash
    if get_settings().app_env.lower() == "test":
        return "test-console", "test-console-session"
    raise HTTPException(401, "Sign in to use Sarkar")


def _tool(name: str, args: dict, result: dict) -> dict:
    return {"tool": name, "arguments": args, "result": result}


def _safe_trace_summary(name: str, spec: "ToolSpec", arguments: dict, result: dict) -> dict:
    """Build a compact persisted trace without copying customer/payment data."""
    encoded_arguments = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    counts = {}
    for key, value in data.items():
        if isinstance(value, list):
            counts[key + "_count"] = len(value)
        elif isinstance(value, dict) and isinstance(value.get("count"), int):
            counts[key + "_count"] = value["count"]
    confirmation = result.get("confirmation")
    summary = {
        "tool": name,
        "version": spec.version,
        "classification": spec.classification,
        "status": result.get("status", "UNKNOWN"),
        "input_fields": sorted(arguments),
        "input_sha256": hashlib.sha256(encoded_arguments.encode("utf-8")).hexdigest(),
        "output_fields": sorted(data),
        "output_counts": counts,
    }
    if confirmation:
        summary["approval_state"] = result.get("status")
    if isinstance(data.get("provenance"), str):
        summary["provenance"] = data["provenance"][:160]
    return summary


def _products(s) -> list[dict]:
    pairs = inventory.list_products(s, merchant_id=current_merchant_id(), store_id=current_store_id())
    return [{
        "id": product.id, "name": product.name, "sku": product.sku,
        "barcode": product.barcode, "unit": product.unit,
        "available": str(balance.available), "on_hand": str(balance.on_hand),
        "reserved": str(balance.reserved), "status": product.status,
        "stock_state": "SERVICE" if product.is_service else
            ("LOW" if balance.available <= balance.low_stock_threshold else "IN_STOCK"),
    } for product, balance in pairs if product.status == "ACTIVE"]


def _summary(s) -> dict:
    merchant_id, store_id = current_merchant_id(), current_store_id()
    tz = ZoneInfo(get_settings().timezone)
    today = datetime.now(tz).date()
    start = datetime.combine(today, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
    end = start + timedelta(days=1)
    bills = s.exec(select(Bill).where(Bill.merchant_id == merchant_id, Bill.store_id == store_id,
                                     Bill.state == "ISSUED", Bill.issued_at >= start, Bill.issued_at < end)).all()
    payments = s.exec(select(Payment).where(Payment.merchant_id == merchant_id, Payment.store_id == store_id,
                                            Payment.provider == "paytm", Payment.status == "SUCCESS",
                                            Payment.verified_at >= start, Payment.verified_at < end)).all()
    credits = s.exec(select(khata.KhataLedgerEntry).where(
        khata.KhataLedgerEntry.merchant_id == merchant_id,
        khata.KhataLedgerEntry.store_id == store_id,
        khata.KhataLedgerEntry.entry_type == "CREDIT_GIVEN",
        khata.KhataLedgerEntry.created_at >= start, khata.KhataLedgerEntry.created_at < end,
    )).all()
    return {
        "date": today.isoformat(),
        "counter_issued_count": len(bills),
        "counter_issued_total_paise": sum(bill.total_paise for bill in bills),
        "counter_total_note": "Issued bills are billed amounts, not necessarily collected payments.",
        "paytm_verified_payment_count": len(payments),
        "paytm_verified_total_paise": sum(payment.amount_paise for payment in payments),
        "khata_credit_added_count": len(credits),
        "khata_credit_added_paise": sum(entry.delta_paise for entry in credits),
        "provenance": "persisted issued bills, server-verified Paytm payments, and append-only Khata ledger",
    }


def _result(message: str, data: dict, status: str = "ANSWERED") -> dict:
    return ToolEnvelope(status=status, message=message, data=data).model_dump(mode="json")


def _read_stock_tool(s, args: QueryInput) -> dict:
    query = normalize_query(args.query)
    rows = _products(s)
    if query:
        rows = [row for row in rows if query in normalize_query(row["name"])
                or query in normalize_query(row.get("sku", ""))]
    return _result("Saved catalogue and stock balances.", {
        "products": rows, "provenance": "saved product and inventory balance records",
    })


def _read_khata_tool(s, args: EmptyInput) -> dict:
    identity = current_identity()
    if identity and identity.role != "OWNER":
        raise HTTPException(403, "Khata balances require the store owner role")
    rows = khata.list_accounts(s, merchant_id=current_merchant_id(), store_id=current_store_id(), limit=100)
    owing = [{"account_id": row["id"], "name": row["name"], "outstanding_paise": row["outstanding_paise"]}
             for row in rows if row["outstanding_paise"] > 0]
    return _result("Outstanding balances come from the append-only Khata ledger.", {
        "account_count": len(owing), "outstanding_total_paise": sum(row["outstanding_paise"] for row in owing),
        "accounts": owing, "provenance": "append-only Khata ledger balances",
    })


def _read_khata_history_tool(s, args: KhataHistoryInput) -> dict:
    identity = current_identity()
    if identity and identity.role != "OWNER":
        raise HTTPException(403, "Khata history requires the store owner role")
    try:
        account, customer, entries, balance = khata.account_history(
            s, merchant_id=current_merchant_id(), store_id=current_store_id(), account_id=args.account_id,
        )
    except khata.KhataError as exc:
        raise HTTPException(404, str(exc)) from exc
    recent = entries[-args.limit:]
    return _result("Khata history is read from the store-scoped immutable ledger.", {
        "account_id": account.id, "customer_name": customer.name, "outstanding_paise": balance,
        "entries": [{"entry_id": row.id, "entry_type": row.entry_type, "delta_paise": row.delta_paise,
                     "source_type": row.source_type, "source_id": row.source_id,
                     "recording_basis": row.recording_basis, "created_at": row.created_at.isoformat()}
                    for row in recent],
        "provenance": "append-only Khata ledger",
    })


def _read_orders_tool(s, args: LimitInput) -> dict:
    orders = s.exec(select(StoreOrder).where(
        StoreOrder.merchant_id == current_merchant_id(), StoreOrder.store_id == current_store_id(),
    ).order_by(StoreOrder.created_at.desc()).limit(args.limit)).all()
    result = []
    for order in orders:
        payment = s.exec(select(Payment).where(
            Payment.id == order.payment_id, Payment.merchant_id == current_merchant_id(),
            Payment.store_id == current_store_id(),
        )).first() if order.payment_id else None
        result.append({"order_id": order.id, "status": order.status,
                       "fulfillment_state": order.fulfillment_state, "amount_paise": order.amount_paise,
                       "created_at": order.created_at.isoformat(),
                       "payment_status": payment.status if payment else "NOT_LINKED",
                       "payment_verified_at": payment.verified_at.isoformat() if payment and payment.verified_at else None})
    return _result("Recent Shop orders and persisted payment/fulfillment states.", {
        "orders": result, "provenance": "store-scoped order and payment records",
    })


def _read_recent_bills_tool(s, args: LimitInput) -> dict:
    bills = s.exec(select(Bill).where(
        Bill.merchant_id == current_merchant_id(), Bill.store_id == current_store_id(),
    ).order_by(Bill.created_at.desc()).limit(args.limit)).all()
    rows = []
    for bill in bills:
        payment = s.exec(select(Payment).where(
            Payment.id == bill.payment_id, Payment.merchant_id == current_merchant_id(),
            Payment.store_id == current_store_id(),
        )).first() if bill.payment_id else None
        rows.append({"bill_id": bill.id, "bill_number": bill.bill_number, "state": bill.state,
                     "amount_paise": bill.total_paise, "payment_state": bill.payment_state,
                     "payment_status": payment.status if payment else "NOT_LINKED",
                     "created_at": bill.created_at.isoformat(),
                     "issued_at": bill.issued_at.isoformat() if bill.issued_at else None})
    return _result("Recent Counter bills and their saved collection states.", {
        "bills": rows, "provenance": "store-scoped Counter bill and Payment records",
    })


def _read_low_stock_tool(s, args: EmptyInput) -> dict:
    rows = [row for row in _products(s) if row["stock_state"] == "LOW"]
    return _result("Items at or below their saved low-stock threshold.", {
        "items": rows, "count": len(rows), "provenance": "saved inventory balances and thresholds",
    })


def _read_verified_payments_tool(s, args: PeriodInput) -> dict:
    tz = ZoneInfo(get_settings().timezone)
    today = datetime.now(tz).date()
    end_day = args.end_date or today
    start_day = args.start_date or (end_day - timedelta(days=6))
    start = datetime.combine(start_day, day_time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(end_day + timedelta(days=1), day_time.min, tzinfo=tz).astimezone(timezone.utc)
    rows = s.exec(select(Payment).where(
        Payment.merchant_id == current_merchant_id(), Payment.store_id == current_store_id(),
        Payment.provider == "paytm", Payment.status == "SUCCESS", Payment.verified_at.is_not(None),
        Payment.verified_at >= start, Payment.verified_at < end,
    ).order_by(Payment.verified_at.desc()).limit(500)).all()
    return _result("This total includes only persisted Paytm SUCCESS records with server verification timestamps.", {
        "start_date": start_day.isoformat(), "end_date": end_day.isoformat(),
        "payment_count": len(rows), "total_paise": sum(row.amount_paise for row in rows),
        "payments": [{"payment_id": row.id, "source_type": row.source_type,
                      "source_id": row.source_id, "amount_paise": row.amount_paise,
                      "currency": row.currency, "provider_transaction_id": row.provider_transaction_id,
                      "verified_at": row.verified_at.isoformat()} for row in rows],
        "provenance": "store-scoped, server-verified Paytm Payment records",
    })


def _payment_explanation(payment: Payment) -> str:
    if payment.status == "SUCCESS" and payment.verified_at:
        return "The saved Paytm status is SUCCESS and has a server verification timestamp."
    if payment.status == "PENDING":
        return "The provider status remains pending; this is not a verified settlement."
    if payment.status == "PENDING_RECONCILIATION":
        return "The latest provider result is unresolved and awaits scheduled reconciliation."
    if payment.status == "INIT_UNKNOWN":
        return "Link creation had an unknown outcome; retry or reconcile using the same saved idempotency key."
    if payment.status == "INIT_FAILED":
        return "Provider link creation failed; no payment is recorded."
    if payment.status == "FAILED":
        return "The saved provider result is failed; no payment is recorded."
    if payment.status == "SIMULATED" or payment.provider == "fake":
        return "This is a simulated test record and does not prove a real payment."
    return "The saved payment state is not sufficient to verify settlement."


def _read_pending_evidence_tool(s, args: PaymentEvidenceInput) -> dict:
    query = select(Payment).where(Payment.merchant_id == current_merchant_id(),
                                  Payment.store_id == current_store_id())
    if args.payment_id:
        query = query.where(Payment.id == args.payment_id)
    else:
        query = query.where(Payment.source_type == args.source_type, Payment.source_id == args.source_id)
    payments = s.exec(query.order_by(Payment.created_at.desc()).limit(2)).all()
    if not payments:
        raise HTTPException(404, "No payment matching that exact store-scoped reference was found")
    if len(payments) > 1 and not args.payment_id:
        raise HTTPException(409, "More than one payment matches that source. Provide a payment_id.")
    payment = payments[0]
    return _result(_payment_explanation(payment), {
        "payment_id": payment.id, "provider": payment.provider, "status": payment.status,
        "source_type": payment.source_type, "source_id": payment.source_id,
        "amount_paise": payment.amount_paise, "currency": payment.currency,
        "provider_order_id": payment.provider_order_id,
        "verified_at": payment.verified_at.isoformat() if payment.verified_at else None,
        "next_check_at": payment.next_check_at.isoformat() if payment.next_check_at else None,
        "status_checks": payment.status_checks, "failure_code": payment.failure_code,
        "provenance": "persisted source-bound Payment state; provider payload is not exposed",
    })


def _read_opportunity_tool(s, args: DemandInput) -> dict:
    result = demand.opportunity_pulse(s, merchant_id=current_merchant_id(),
                                      store_id=current_store_id(), days=args.days)
    return _result(result["message"], {
        **result,
        "meaning": "Repeat searches show interest only; they do not prove a purchase or guaranteed demand.",
        "provenance": "persisted public storefront search outcomes",
    })


def _match_products(s, query: str) -> list[tuple[Product, object]]:
    norm = normalize_query(query)
    pairs = inventory.list_products(s, merchant_id=current_merchant_id(), store_id=current_store_id())
    if not norm:
        return [(p, b) for p, b in pairs if p.status == "ACTIVE"]
    return [(p, b) for p, b in pairs if p.status == "ACTIVE" and
            (norm == normalize_query(p.name) or norm in normalize_query(p.name))]


def _prepare_receipt(s, message: str) -> dict | None:
    match = RECEIPT_RE.match(message)
    if not match:
        return None
    quantity, unit_raw, product_query = match.groups()
    product_query = product_query.strip().strip(" .,!?")
    try:
        delta = Decimal(quantity)
    except InvalidOperation:
        return {"status": "NEEDS_CLARIFICATION", "message": "Tell me the amount as a number, such as ‘received 5 kg rice’."}
    if delta <= 0 or delta > Decimal("10000"):
        return {"status": "NEEDS_CLARIFICATION", "message": "The receipt amount must be above zero and no more than 10,000 units."}
    matches = _match_products(s, product_query)
    if len(matches) != 1:
        candidates = [{"product_id": p.id, "name": p.name, "unit": p.unit} for p, _ in matches[:5]]
        if matches:
            return {"status": "NEEDS_CLARIFICATION", "message": "I found more than one matching product. Choose the exact catalogue item.",
                    "candidates": candidates}
        return {"status": "NEEDS_CLARIFICATION", "message": f"I could not find ‘{product_query}’ in this store’s catalogue. No stock was changed."}
    product, balance = matches[0]
    requested_unit = UNIT_ALIASES.get((unit_raw or "").casefold(), unit_raw or product.unit)
    actual_unit = UNIT_ALIASES.get(product.unit.casefold(), product.unit.casefold())
    if requested_unit != actual_unit:
        return {"status": "NEEDS_CLARIFICATION", "message": f"The catalogue uses {product.unit} for {product.name}; the request used {unit_raw}. No stock was changed."}

    identity = current_identity()
    if identity and identity.role != "OWNER":
        raise HTTPException(403, "Only the store owner can confirm stock receipts")
    actor_id, session_hash = _actor()
    merchant_id, store_id = current_merchant_id(), current_store_id()
    action_id = "sarkar_" + uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    payload = {
        "product_id": product.id, "product_name": product.name, "unit": product.unit,
        "quantity": str(delta), "before_on_hand": str(balance.on_hand),
        "before_reserved": str(balance.reserved), "before_available": str(balance.available),
        "reason": "Goods receipt confirmed through Sarkar",
    }
    payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload_hash = hashlib.sha256(payload_json.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=10)
    action = SarkarAction(
        id=action_id, merchant_id=merchant_id, store_id=store_id, actor_id=actor_id,
        session_hash=session_hash, action_type="STOCK_RECEIPT", payload_json=payload_json,
        payload_hash=payload_hash, confirmation_hash=hashlib.sha256(token.encode()).hexdigest(),
        expires_at=expires_at,
    )
    s.add(action)
    audit.record(s, action="sarkar.action_prepared", entity_type="sarkar_action", entity_id=action_id,
                 merchant_id=merchant_id, store_id=store_id, actor_type="merchant", actor_id=actor_id,
                 task_id=action_id, source="sarkar", idempotency_key="sarkar:prepare:" + action_id,
                 payload={"action_type": action.action_type, "product_id": product.id,
                          "quantity": str(delta), "unit": product.unit,
                          "before_on_hand": str(balance.on_hand), "before_reserved": str(balance.reserved),
                          "before_available": str(balance.available)})
    s.commit()
    trace = _tool("prepare_stock_receipt", payload, {
        "status": "NEEDS_CONFIRMATION", "action_id": action_id,
        "confirmation_token": token, "expires_at": expires_at.isoformat(),
    })
    return {
        "status": "NEEDS_CONFIRMATION", "engine": ENGINE,
        "message": f"I found {product.name}. Confirm adding {delta} {product.unit}; available stock is {balance.available} {product.unit} now.",
        "confirmation": {"action_id": action_id, "token": token, "expires_at": expires_at.isoformat(),
                         "product_name": product.name, "quantity": str(delta), "unit": product.unit,
                         "available_before": str(balance.available)},
        "tool_trace": [trace],
    }


def _prepare_receipt_handler(s, args: ReceiptInput) -> dict:
    result = _prepare_receipt(s, args.message)
    if result is None:
        return {"status": "NEEDS_CLARIFICATION", "engine": ENGINE,
                "message": "State the received quantity, unit, and one catalogue product name.", "tool_trace": []}
    return result


def _confirm_receipt_handler(s, args: ConfirmReceiptInput) -> dict:
    return confirm_action(s, args.action_id, args.confirmation_token)


def _tool_specs() -> dict[str, ToolSpec]:
    owner = "OWNER"
    staff = "STAFF"
    common = {"permission": "merchant.read", "ownership_rule": "authenticated merchant and current store context",
              "classification": "READ_ONLY", "approval_required": False,
              "idempotency_required": False, "timeout_seconds": 3.0, "max_retries": 0,
              "post_execution_verification": "validated response built from tenant-scoped persisted records"}
    specs = [
        ToolSpec("inspect_stock", "1.0", QueryInput, ToolEnvelope, _read_stock_tool, staff,
                 permission="merchant.catalog.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("inspect_khata", "1.0", EmptyInput, ToolEnvelope, _read_khata_tool, owner,
                 permission="merchant.khata.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("inspect_khata_history", "1.0", KhataHistoryInput, ToolEnvelope, _read_khata_history_tool, owner,
                 permission="merchant.khata.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("inspect_orders", "1.0", LimitInput, ToolEnvelope, _read_orders_tool, staff,
                 **common),
        ToolSpec("inspect_recent_bills", "1.0", LimitInput, ToolEnvelope, _read_recent_bills_tool, staff,
                 **common),
        ToolSpec("inspect_low_stock", "1.0", EmptyInput, ToolEnvelope, _read_low_stock_tool, staff,
                 **common),
        ToolSpec("summarize_verified_payments", "1.0", PeriodInput, ToolEnvelope, _read_verified_payments_tool, owner,
                 permission="merchant.payment.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("explain_payment_state", "1.0", PaymentEvidenceInput, ToolEnvelope, _read_pending_evidence_tool, owner,
                 permission="merchant.payment.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("inspect_business_summary", "1.0", EmptyInput, ToolEnvelope,
                 lambda s, _args: _result("Here is today’s saved business summary.", _summary(s)), owner,
                 permission="merchant.summary.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("inspect_unmet_demand", "1.0", DemandInput, ToolEnvelope, _read_opportunity_tool, staff,
                 permission="merchant.opportunity.read", **{k: v for k, v in common.items() if k != "permission"}),
        ToolSpec("prepare_stock_receipt", "1.0", ReceiptInput, PreparedReceiptEnvelope,
                 _prepare_receipt_handler, owner, "merchant.inventory.prepare", "authenticated merchant and current store context",
                 "MUTATION_PREPARATION", True, True, 3.0, 0,
                 "confirmation rechecks session, token, payload hash, product status, and saved on-hand quantity"),
        ToolSpec("confirm_stock_receipt", "1.0", ConfirmReceiptInput, ToolEnvelope,
                 _confirm_receipt_handler, owner, "merchant.inventory.confirm", "authenticated merchant and current store context",
                 "MUTATION", True, True, 3.0, 0,
                 "reload the stock balance and saved action result after the idempotent inventory movement"),
    ]
    return {spec.name: spec for spec in specs}


TOOL_REGISTRY = _tool_specs()


def available_tools() -> dict:
    identity = current_identity()
    role = identity.role if identity else ("OWNER" if get_settings().app_env.lower() == "test" else "STAFF")
    contracts = [spec.public_contract() for spec in TOOL_REGISTRY.values()
                 if role == "OWNER" or spec.required_role != "OWNER"]
    return {"engine": ENGINE, "tools": contracts}


def invoke_tool(s, name: str, arguments: dict | None = None) -> dict:
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        raise HTTPException(404, "Unknown Sarkar tool")
    identity = current_identity()
    _actor()
    if identity and spec.required_role == "OWNER" and identity.role != "OWNER":
        raise HTTPException(403, "This Sarkar tool requires the store owner role")
    if not current_merchant_id() or not current_store_id():
        raise HTTPException(401, "A signed-in store identity is required")
    try:
        parsed = spec.input_model.model_validate(arguments or {})
    except Exception as exc:
        raise HTTPException(422, "Tool arguments do not match the declared input schema") from exc
    timeout = spec.timeout_seconds if spec.timeout_seconds and spec.timeout_seconds > 0 else None
    if timeout is not None:
        ctx = contextvars.copy_context()
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = pool.submit(ctx.run, spec.handler, s, parsed)
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            pool.shutdown(wait=False, cancel_futures=True)
            raise HTTPException(504, f"Sarkar tool '{name}' execution exceeded deadline of {spec.timeout_seconds}s") from exc
        except Exception:
            pool.shutdown(wait=False, cancel_futures=True)
            raise
        else:
            pool.shutdown(wait=True)
    else:
        result = spec.handler(s, parsed)
    try:
        validated = spec.output_model.model_validate(result).model_dump(mode="json")
    except Exception as exc:
        raise HTTPException(500, "Sarkar tool returned a result outside its declared output schema") from exc
    correlation_id = ((validated.get("confirmation") or {}).get("action_id")
                      or parsed.model_dump().get("action_id")
                      or "sarkar_tool_" + uuid.uuid4().hex)
    trace_arguments = parsed.model_dump(mode="json")
    if "confirmation_token" in trace_arguments:
        trace_arguments["confirmation_token"] = "[REDACTED]"
    if isinstance(validated.get("tool_trace"), list):
        # Preserve the legacy trace display while adding version and correlation evidence.
        validated["tool_trace"] = [{
            "tool": name, "version": spec.version, "correlation_id": correlation_id,
            "arguments": trace_arguments,
            "result": ({"status": validated.get("status"), "action_id": (validated.get("confirmation") or {}).get("action_id")}
                       if spec.classification != "READ_ONLY" else validated.get("data", {})),
        }]
    else:
        validated["tool_trace"] = [{"tool": name, "version": spec.version,
                                    "correlation_id": correlation_id,
                                    "arguments": trace_arguments,
                                    "result": validated.get("data", {})}]
    validated["correlation_id"] = correlation_id
    validated.setdefault("engine", ENGINE)
    identity = current_identity()
    trace_summary = _safe_trace_summary(name, spec, trace_arguments, validated)
    audit.record(
        s, action="sarkar.tool_executed", entity_type="sarkar_tool", entity_id=correlation_id,
        merchant_id=current_merchant_id(), store_id=current_store_id(),
        actor_type="merchant", actor_id=identity.user_id if identity else _actor()[0],
        task_id=correlation_id, source="sarkar", idempotency_key=f"sarkar:tool:{name}:{correlation_id}",
        payload=trace_summary,
    )
    s.commit()
    return validated


def ask(s, message: str) -> dict:
    text = " ".join((message or "").strip().split())
    if not 1 <= len(text) <= 1000:
        raise HTTPException(422, "Message must contain 1–1,000 characters")
    lower = text.casefold()
    if RECEIPT_RE.match(text):
        return invoke_tool(s, "prepare_stock_receipt", {"message": text})
    if any(word in lower for word in ("demand", "opportunity", "pulse", "stockout", "stock out")):
        return invoke_tool(s, "inspect_unmet_demand", {"days": 30})
    if "low stock" in lower or "running low" in lower:
        return invoke_tool(s, "inspect_low_stock", {})
    if "payment" in lower and any(word in lower for word in ("verified", "collected", "received", "summary")):
        return invoke_tool(s, "summarize_verified_payments", {})
    if "payment" in lower and any(word in lower for word in ("pending", "why", "status", "stuck")):
        reference = re.search(r"(?:payment|reference)\s+([A-Za-z0-9_-]{4,100})", text, re.I)
        if reference:
            return invoke_tool(s, "explain_payment_state", {"payment_id": reference.group(1)})
        return {"status": "NEEDS_CLARIFICATION", "engine": ENGINE,
                "message": "Give me the exact payment ID to explain its persisted status. I will not infer that it was paid.",
                "tool_trace": []}
    if any(word in lower for word in ("khata", "dues", "outstanding", "owed")):
        return invoke_tool(s, "inspect_khata", {})
    if "order" in lower:
        return invoke_tool(s, "inspect_orders", {"limit": 50})
    if "bill" in lower or "counter" in lower:
        return invoke_tool(s, "inspect_recent_bills", {"limit": 20})
    if any(word in lower for word in ("summary", "today", "sales", "collected")):
        return invoke_tool(s, "inspect_business_summary", {})
    if any(word in lower for word in ("stock", "inventory", "catalogue", "catalog")):
        query_match = re.search(r"(?:stock|inventory|catalogue|catalog)(?:\s+(?:of|for|on))?\s+(.+)$", lower)
        query = query_match.group(1).strip(" ?.!" ) if query_match else ""
        return invoke_tool(s, "inspect_stock", {"query": query})
    return {"status": "NEEDS_CLARIFICATION", "engine": ENGINE,
            "message": "I can search stock, list low-stock items, read Counter bills and Shop orders, inspect Khata, summarize verified Paytm payments, explain a pending payment by ID, read Opportunity Pulse, or prepare a stock receipt for owner confirmation.",
            "tool_trace": []}


def confirm_action(s, action_id: str, token: str) -> dict:
    actor_id, session_hash = _actor()
    action = s.exec(select(SarkarAction).where(
        SarkarAction.id == action_id, SarkarAction.merchant_id == current_merchant_id(),
        SarkarAction.store_id == current_store_id(),
    )).first()
    if action is None:
        raise HTTPException(404, "Prepared action not found")
    if action.actor_id != actor_id or not hmac.compare_digest(action.session_hash, session_hash):
        raise HTTPException(403, "This confirmation belongs to a different user session")
    if action.status != "OPEN":
        raise HTTPException(409, "This prepared action is no longer open")
    now = datetime.now(timezone.utc)
    expires = action.expires_at.replace(tzinfo=timezone.utc) if action.expires_at.tzinfo is None else action.expires_at
    if expires <= now:
        action.status = "EXPIRED"
        s.add(action)
        s.commit()
        raise HTTPException(410, "This confirmation expired. Prepare the action again.")
    supplied_hash = hashlib.sha256((token or "").encode()).hexdigest()
    if not hmac.compare_digest(action.confirmation_hash, supplied_hash):
        raise HTTPException(403, "Confirmation token is invalid")
    if not hmac.compare_digest(hashlib.sha256(action.payload_json.encode()).hexdigest(), action.payload_hash):
        action.status = "INVALIDATED"
        s.add(action)
        s.commit()
        raise HTTPException(409, "Prepared action details changed; prepare it again")
    payload = json.loads(action.payload_json)
    found = inventory.lookup_product(s, merchant_id=action.merchant_id, store_id=action.store_id,
                                     product_id=payload["product_id"])
    if (found is None or found[0].status != "ACTIVE"
            or str(found[1].on_hand) != payload["before_on_hand"]
            or str(found[1].reserved) != payload["before_reserved"]
            or str(found[1].available) != payload["before_available"]):
        action.status = "INVALIDATED"
        s.add(action)
        s.commit()
        raise HTTPException(409, "Stock changed after the preview. Ask Sarkar to prepare a fresh action.")
    try:
        balance = inventory.adjust_stock(
            s, merchant_id=action.merchant_id, store_id=action.store_id,
            product_id=payload["product_id"], delta=Decimal(payload["quantity"]), kind="receipt",
            source_ref=action.id, reason=payload["reason"], idempotency_key="sarkar-stock:" + action.id,
        )
    except inventory.InventoryError as exc:
        action.status = "INVALIDATED"
        s.add(action)
        s.commit()
        raise HTTPException(409, str(exc)) from exc
    result = {"product_id": payload["product_id"], "product_name": payload["product_name"],
              "on_hand": str(balance.on_hand), "available": str(balance.available), "unit": payload["unit"]}
    action.status = "EXECUTED"
    action.result_json = json.dumps(result, sort_keys=True, separators=(",", ":"))
    action.executed_at = now
    s.add(action)
    audit.record(s, action="sarkar.stock_receipt_executed", entity_type="product",
                 entity_id=payload["product_id"], merchant_id=action.merchant_id, store_id=action.store_id,
                 actor_type="merchant", actor_id=actor_id, task_id=action.id, source="sarkar",
                 idempotency_key="sarkar:execute:" + action.id,
                 payload={"quantity": payload["quantity"], "unit": payload["unit"],
                          "action_id": action.id, "new_on_hand": str(balance.on_hand)})
    s.commit()
    return {"status": "EXECUTED", "engine": ENGINE, "message": f"Added {payload['quantity']} {payload['unit']} to {payload['product_name']}.",
            "data": result, "tool_trace": [_tool("execute_prepared_stock_receipt", {"action_id": action.id}, result)]}
