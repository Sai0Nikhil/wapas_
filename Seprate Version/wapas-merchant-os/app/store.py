"""The merchant's own store. Customers pay through Paytm checkout (staging),
so the failures Wapas works on are real Paytm transactions.

Flow: /shop -> initiate transaction -> Paytm CheckoutJS -> Paytm POSTs the
result to /api/paytm/txn-callback -> checksum verified -> confirmed with the
Transaction Status API -> a FAILED payment opens a Wapas case.
"""
import re
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlmodel import select

from . import audit, evidence, executor, inventory, payment_events, payment_lifecycle
from .config import get_settings
from .db import session
from .gateway import get_gateway
from .models import Case, Customer, Payment
from .commerce_models import StoreOrder, StoreOrderLine
from .ports import PayStatus
from .templates import LANG_NAMES, fmt_inr
from .timeline import log_event
from .rate_limit import allow as _durable_rate_allow

router = APIRouter()

PRODUCTS = {
    "earbuds": ("Wireless earbuds", 234000),
    "charger": ("Fast phone charger", 125000),
    "bulbs": ("Smart LED bulbs (pack of 4)", 86000),
    "speaker": ("Bluetooth speaker", 690000),
}

# Paytm RESPCODE -> our failure reasons, from Paytm's response-codes PDF and the v3 status docs.
# (In that PDF, 501 is "Your Payment has declined by your bank".) Unknown codes fall back on the message.
RESPCODES = {"141": "USER_DROPPED", "227": "BANK_DECLINED", "235": "INSUFFICIENT_FUNDS", "295": "WRONG_VPA",
             "501": "BANK_DECLINED", "401": "BANK_DECLINED", "810": "USER_DROPPED"}


def failure_code(respcode: str, respmsg: str) -> str:
    if respcode in RESPCODES:
        return RESPCODES[respcode]
    m = (respmsg or "").lower()
    if "cancel" in m or "closed" in m or "abandon" in m or "not completed" in m:
        return "USER_DROPPED"
    if "insufficient" in m or "balance" in m:
        return "INSUFFICIENT_FUNDS"
    if "pin" in m:
        return "WRONG_PIN"
    return "BANK_DECLINED"


class CheckoutIn(BaseModel):
    product: str
    name: str = Field(min_length=2, max_length=60)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")
    language: str = "hi"


def _rate_ok(key: str, limit: int, window: float) -> bool:
    return _durable_rate_allow(key, limit=limit, window_seconds=window)


@router.post("/api/shop/checkout")
def checkout(body: CheckoutIn):
    if body.product not in PRODUCTS:
        raise HTTPException(400, "unknown product")
    # Public endpoint that creates real Paytm orders: bound it per phone and overall.
    if not (_rate_ok("phone:" + body.phone, 5, 600) and _rate_ok("all", 60, 60)):
        raise HTTPException(429, "Too many checkout attempts; please wait a few minutes")
    lang = body.language if body.language in LANG_NAMES else "en"
    title, amount = PRODUCTS[body.product]
    cust_id = "shop_" + body.phone
    order_id = f"WAP{int(time.time())}{uuid.uuid4().hex[:4].upper()}"
    with executor.LOCK, session() as s:
        c = s.get(Customer, cust_id)
        if c is None:
            s.add(Customer(id=cust_id, name=body.name.strip(), phone=body.phone, language=lang))
        else:
            c.name, c.language = body.name.strip(), lang
            s.add(c)
        # Durable from the first second: if the callback never comes (customer closed the page,
        # Paytm could not reach us, the laptop restarted), the reconciler still finds this order.
        gateway = get_gateway()
        s.add(Payment(id=f"pay_{order_id}", order_id=order_id, customer_id=cust_id,
                      merchant_id="merchant_default", store_id="store_default",
                      amount_paise=amount, source_type="RECOVERY", source_id=order_id,
                      provider=gateway.name, provider_mid=get_settings().paytm_mid if gateway.name == "paytm" else "",
                      provider_order_id=order_id, idempotency_key="recovery:" + order_id,
                      bank="", method="", status="PENDING", failure_code="", created_at=datetime.now(timezone.utc)))
        s.commit()
    cb = get_settings().public_base_url.rstrip("/") + "/api/paytm/txn-callback"
    res = get_gateway().initiate_checkout(order_id=order_id, amount_paise=amount, cust_id=cust_id, callback_url=cb)
    if not res.get("ok"):
        with executor.LOCK, session() as s:
            p = s.get(Payment, f"pay_{order_id}")
            p.status = "INIT_UNKNOWN" if res.get("uncertain") else "INIT_FAILED"
            s.add(p)
            s.commit()
        raise HTTPException(502, "Paytm initiate transaction failed: " + res.get("error", ""))
    res["product"] = title
    return res


def _record(s, *, order_id: str, status: PayStatus, bank: str, mode: str, respcode: str, respmsg: str,
            amount_paise: int, customer_id: str, verified_result=None, gateway_name: str = "") -> Payment | None:
    pid = f"pay_{order_id}"
    p = s.get(Payment, pid)
    if p is not None and p.status not in ("PENDING", "INIT_FAILED", "INIT_UNKNOWN", "PENDING_RECONCILIATION"):
        return None  # duplicate callback, or the reconciler got there first: already recorded
    if p is None:
        # A valid callback checksum is not proof that Wapas initiated this order. Never
        # create a payment (or a success event) from a callback-only order reference.
        log_event(s, "security", f"Ignored a Paytm result for unknown checkout order {order_id}")
        return None
    if status == PayStatus.SUCCESS and (amount_paise <= 0 or amount_paise != p.amount_paise):
        # The catalogue amount recorded before checkout is immutable. A success with a
        # missing or different provider amount remains unresolved for later reconciliation.
        evidence.record(s, "checkout_amount_mismatch", {
            "order_id": order_id, "expected_amount_paise": p.amount_paise,
            "reported_amount_paise": amount_paise,
        }, source="paytm:order-status", ok=False)
        log_event(s, "security", f"Checkout {order_id}: Paytm amount did not match the saved checkout amount")
        return None
    if p.source_type in {"SHOP_ORDER", "COUNTER_BILL", "KHATA_COLLECTION"} and verified_result is not None:
        outcome = payment_lifecycle.apply_terminal_result(
            s, p, verified_result, gateway_name=gateway_name,
            expected_order_id=p.provider_order_id or order_id,
        )
        if outcome in {"UNVERIFIED", "AMOUNT_MISMATCH", "SOURCE_MISSING", "RECONCILIATION_REQUIRED"}:
            log_event(s, "security", f"Checkout {order_id}: {outcome}; payment remains uncredited")
            return None
        p.bank, p.method = bank or "Unknown bank", mode or "UPI"
        p.failure_code = "" if status == PayStatus.SUCCESS else failure_code(respcode, respmsg)
        s.add(p)
        return p
    ok = status == PayStatus.SUCCESS
    if ok:
        if verified_result is not None:
            if not payment_events.record_verified_success(
                    s, p, verified_result, gateway_name=gateway_name,
                    expected_order_id=p.provider_order_id or order_id):
                log_event(s, "security", f"Checkout {order_id}: provider status could not be bound to this payment attempt")
                return None
        elif p.provider in {"paytm", "unknown"}:
            log_event(s, "security", f"Checkout {order_id}: success without a verified provider response was ignored")
            return None
        else:
            p.status = "SUCCESS"
    elif verified_result is not None:
        if not payment_events.record_terminal_failure(
                p, verified_result, gateway_name=gateway_name,
                expected_order_id=p.provider_order_id or order_id):
            log_event(s, "security", f"Checkout {order_id}: provider failure could not be bound to this payment attempt")
            return None
    else:
        p.status = "FAILED"
    p.bank, p.method = bank or "Unknown bank", mode or "UPI"
    p.failure_code = "" if ok else failure_code(respcode, respmsg)
    s.add(p)
    order = s.get(StoreOrder, order_id)
    if order is not None and order.status == "PAYMENT_PENDING":
        lines = s.exec(select(StoreOrderLine).where(
            StoreOrderLine.order_id == order_id,
            StoreOrderLine.merchant_id == order.merchant_id,
            StoreOrderLine.store_id == order.store_id,
        )).all()
        for line in lines:
            if not line.reservation_id:
                continue
            if ok:
                inventory.complete_reservation(s, merchant_id=order.merchant_id, store_id=order.store_id,
                                               reservation_id=line.reservation_id)
            else:
                inventory.release_stock(s, merchant_id=order.merchant_id, store_id=order.store_id,
                                        reservation_id=line.reservation_id, source="payment_failed")
        order.status = "PAID" if ok else "PAYMENT_FAILED"
        order.updated_at = datetime.now(timezone.utc)
        if ok:
            order.paid_at = order.updated_at
        s.add(order)
        audit.record(s, action="shop.payment_verified" if ok else "shop.payment_failed",
                     entity_type="store_order", entity_id=order_id,
                     merchant_id=order.merchant_id, store_id=order.store_id,
                     source="paytm-status" if get_gateway().name == "paytm" else "fake-gateway",
                     idempotency_key=f"shop-settlement:{order_id}:{order.status}",
                     payload={"status": order.status, "amount_paise": p.amount_paise})
    customer_id = p.customer_id
    cust = s.get(Customer, customer_id)
    who = cust.name if cust else customer_id
    if ok:
        log_event(s, "store", f"{who} paid ₹{fmt_inr(amount_paise)} at checkout ({p.bank})")
    else:
        s.add(Case(id=f"c_{order_id}", payment_id=pid, batch="live"))
        log_event(s, "signal", f"Real checkout failure: {who}, ₹{fmt_inr(amount_paise)}, {p.bank}, {respcode} {respmsg}".strip(), f"c_{order_id}")
    return p


def _close_unstarted_order(s, p: Payment) -> None:
    """Release stock only after status confirms the ambiguous init created no order."""
    order = s.get(StoreOrder, p.order_id)
    if order is None or order.status != "PAYMENT_PENDING":
        return
    lines = s.exec(select(StoreOrderLine).where(
        StoreOrderLine.order_id == order.id,
        StoreOrderLine.merchant_id == order.merchant_id,
        StoreOrderLine.store_id == order.store_id,
    )).all()
    for line in lines:
        if line.reservation_id:
            inventory.release_stock(s, merchant_id=order.merchant_id, store_id=order.store_id,
                                    reservation_id=line.reservation_id, source="init_not_found")
    order.status = "PAYMENT_FAILED"
    order.updated_at = datetime.now(timezone.utc)
    s.add(order)
    audit.record(s, action="shop.checkout_not_started", entity_type="store_order", entity_id=order.id,
                 merchant_id=order.merchant_id, store_id=order.store_id, source="paytm-status",
                 idempotency_key="shop-init-not-found:" + order.id,
                 payload={"payment_id": p.id})


@router.post("/api/paytm/txn-callback")
async def txn_callback(request: Request):
    form = dict(await request.form())
    gw = get_gateway()
    if not gw.verify_callback(dict(form)):
        with executor.LOCK, session() as s:
            log_event(s, "security", "Rejected a checkout callback with an invalid checksum")
            s.commit()
        raise HTTPException(400, "invalid checksum")
    order_id = str(form.get("ORDERID", ""))
    if not re.fullmatch(r"[A-Za-z0-9_\-@.]{3,50}", order_id):
        raise HTTPException(400, "bad order id")
    confirmed = gw.order_status(order_id)  # never trust the callback alone
    with executor.LOCK, session() as s:
        evidence.record(s, "checkout_callback", {"callback": {k: v for k, v in form.items() if k != "CHECKSUMHASH"},
                                                 "checksum_valid": True, "confirmed_status": confirmed.status.value,
                                                 "status_raw": confirmed.raw},
                        source="paytm:callback + /v3/order/status" if gw.name == "paytm" else "fake-gateway")
        s.commit()
    if confirmed.status == PayStatus.ERROR:
        status = PayStatus.PENDING
    elif confirmed.status in (PayStatus.SUCCESS, PayStatus.FAILED):
        status = confirmed.status
    else:
        status = PayStatus.PENDING
    # Callback fields are only hints. In particular, never use callback TXNAMOUNT
    # when the authenticated status response omitted its amount.
    amount = confirmed.amount_paise
    with executor.LOCK, session() as s:
        if status == PayStatus.PENDING:
            log_event(s, "signal", f"Checkout {order_id}: status not confirmed yet; the reconciler will re-check it")
        else:
            known = s.get(Payment, f"pay_{order_id}")
            _record(s, order_id=order_id, status=status, bank=str(form.get("BANKNAME", "")),
                    mode=str(form.get("PAYMENTMODE", "")), respcode=str(form.get("RESPCODE", "")),
                    respmsg=str(form.get("RESPMSG", "")), amount_paise=amount,
                    customer_id=known.customer_id if known else _customer_for(s, form),
                    verified_result=confirmed, gateway_name=gw.name)
        s.commit()
    return RedirectResponse(f"/shop/result/{order_id}", status_code=303)


# Paytm keeps polling the bank for up to 72 h and recommends status checks on a backing-off schedule.
SCHEDULE = [timedelta(seconds=60), timedelta(minutes=2), timedelta(minutes=5), timedelta(minutes=10),
            timedelta(minutes=15), timedelta(minutes=30), timedelta(hours=1), timedelta(hours=6), timedelta(hours=12),
            timedelta(hours=24), timedelta(hours=48), timedelta(hours=72)]
FIRST_CHECK = SCHEDULE[0]               # give Paytm's own callback a minute first
ABANDON_AFTER = timedelta(minutes=10)   # Paytm has no record of any attempt: the customer walked away
GIVE_UP = timedelta(hours=72)           # still unconfirmed after Paytm's own 72 h window: stop asking, open nothing


def _next_check(created: datetime, checks_done: int) -> datetime | None:
    return created + SCHEDULE[checks_done] if checks_done < len(SCHEDULE) else None


def reconcile(now: datetime | None = None, limit: int = 10) -> dict:
    """Re-check store orders whose outcome we have not confirmed, on Paytm's recommended schedule.
    Status calls run outside the lock. A callback is a hint; the status API is the truth."""
    now = now or datetime.now(timezone.utc)
    gw = get_gateway()
    with session() as s:
        rows = s.exec(select(Payment).where(Payment.status.in_(("PENDING", "INIT_UNKNOWN")),
                                             Payment.id.startswith("pay_WAP"))
                      .order_by(Payment.created_at).limit(200)).all()
        due = []
        for p in rows:
            if p.source_type in {"COUNTER_BILL", "KHATA_COLLECTION"} and not p.provider_link_id:
                continue  # the collection-link create result is ambiguous; retry by its same key instead
            nxt = _utc(p.next_check_at) if p.next_check_at else _next_check(_utc(p.created_at), p.status_checks)
            if nxt is None or nxt <= now:
                due.append((p.id, p.order_id, p.provider_link_id, now - _utc(p.created_at)))
            if len(due) >= limit:
                break
    checks = {}
    for payment_id, order_id, link_id, age in due:
        if age < FIRST_CHECK:
            continue
        status = gw.link_status(link_id) if link_id else gw.order_status(order_id)
        checks[payment_id] = (order_id, link_id, age, status)
    done = {"checked": len(checks), "recorded": 0, "abandoned": 0, "init_failed": 0,
            "unresolved": 0, "expired": 0}
    if not checks:
        return done
    with executor.LOCK, session() as s:
        for payment_id, (oid, link_id, age, st) in checks.items():
            p = s.get(Payment, payment_id)
            if not p or p.status not in ("PENDING", "INIT_UNKNOWN"):
                continue  # the callback got there first
            init_unknown = p.status == "INIT_UNKNOWN"
            raw = st.raw if isinstance(st.raw, dict) else {}
            info = raw.get("resultInfo", {})
            p.status_checks += 1
            p.next_check_at = _next_check(_utc(p.created_at), p.status_checks)
            s.add(p)
            evidence.record(s, "order_status_reconcile", {"order_id": oid, "mapped_status": st.status.value,
                                                          "age_seconds": int(age.total_seconds()), "raw": raw},
                            source=("paytm:link/fetchTransaction + /v3/order/status" if link_id else "paytm:/v3/order/status")
                            if gw.name == "paytm" else "fake-gateway",
                            ok=st.status != PayStatus.ERROR)
            if st.status in (PayStatus.SUCCESS, PayStatus.FAILED):
                if link_id:
                    outcome = payment_lifecycle.apply_terminal_result(
                        s, p, st, gateway_name=gw.name, expected_link_id=link_id,
                    )
                    recorded = outcome not in {"UNVERIFIED", "AMOUNT_MISMATCH", "SOURCE_MISSING",
                                               "RECONCILIATION_REQUIRED", "PENDING"}
                else:
                    recorded = _record(s, order_id=oid, status=st.status, bank=str(raw.get("bankName", "")),
                                       mode=str(raw.get("paymentMode", "")), respcode=str(info.get("resultCode", "")),
                                       respmsg=str(info.get("resultMsg", "")), amount_paise=st.amount_paise,
                                       customer_id=p.customer_id, verified_result=st, gateway_name=gw.name)
                if recorded:
                    done["recorded"] += 1
            elif st.status == PayStatus.NOT_FOUND and age >= ABANDON_AFTER:
                if link_id:
                    if age >= GIVE_UP:
                        p.status = "PENDING_RECONCILIATION"
                        p.next_check_at = None
                        s.add(p)
                        log_event(s, "signal", f"Payment Link {link_id} still unconfirmed after 72 h; owner reconciliation is required")
                        done["unresolved"] += 1
                    continue  # an unpaid Payment Link is not proof that the charge failed
                if init_unknown:
                    # No checkout token reached the browser and Paytm has no order.
                    # Close the ambiguous initiation without inventing a customer failure.
                    p.status = "INIT_FAILED"
                    s.add(p)
                    _close_unstarted_order(s, p)
                    done["init_failed"] += 1
                else:
                    _record(s, order_id=oid, status=PayStatus.FAILED, bank="", mode="", respcode="",
                            respmsg="Checkout abandoned: no payment attempt reached Paytm", amount_paise=0,
                            customer_id=p.customer_id)
                    done["abandoned"] += 1
            elif age >= GIVE_UP:
                # A timeout is not proof of payment failure. Stop automatic polling
                # after Paytm's status window but preserve the unresolved state.
                p.status = "PENDING_RECONCILIATION"
                p.next_check_at = None
                s.add(p)
                log_event(s, "signal", f"Checkout {oid} still unconfirmed after 72 h; owner reconciliation is required")
                done["unresolved"] += 1
        s.commit()
    return done


def _utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _customer_for(s, form) -> str:
    cid = "shop_unknown"
    if not s.get(Customer, cid):
        s.add(Customer(id=cid, name="Store customer", phone="9000000000", language="en"))
        s.flush()
    return cid


# ------------------------------------------------------------------ pages
SHOP = (__import__("pathlib").Path(__file__).parent / "static" / "shop.html")


@router.get("/shop", response_class=HTMLResponse)
def shop_page():
    return SHOP.read_text(encoding="utf-8")


@router.get("/api/shop/products")
def products():
    return [{"id": k, "title": t, "amount": a / 100, "amount_fmt": fmt_inr(a)} for k, (t, a) in PRODUCTS.items()]


@router.get("/shop/result/{order_id}", response_class=HTMLResponse)
def result_page(order_id: str):
    if not re.fullmatch(r"[A-Za-z0-9_\-@.]{3,50}", order_id):
        raise HTTPException(404)
    with session() as s:
        order = s.get(StoreOrder, order_id)
        if order is not None:
            from .commerce import order_result_page
            return order_result_page(order_id)
        p = s.get(Payment, f"pay_{order_id}")
    if p is None:
        raise HTTPException(404)
    if p.status in ("PENDING", "INIT_UNKNOWN", "PENDING_RECONCILIATION", "INIT_FAILED"):
        msg, cls = ("Payment status is not confirmed yet. Do not retry unless the store confirms the status.", "wait")
    elif p.status == "SUCCESS":
        msg, cls = f"Payment of ₹{fmt_inr(p.amount_paise)} received. Thank you!", "ok"
    else:
        msg, cls = f"Your payment of ₹{fmt_inr(p.amount_paise)} did not go through. No money was taken. You may get one secure Paytm link from the store to try again.", "fail"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Order {order_id}</title><style>body{{font-family:system-ui,Arial;background:#F7F6F2;color:#0B1220;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.c{{background:#fff;border:1px solid #D9D6CE;border-radius:18px;padding:28px;max-width:420px}}.ok{{color:#0F7A4B}}.fail{{color:#A4262C}}.wait{{color:#5F6773}}a{{color:#1746C8}}</style>
{'<meta http-equiv="refresh" content="3">' if cls == 'wait' and p.status != 'PENDING_RECONCILIATION' else ''}</head><body><div class="c"><h2>{get_settings().merchant_name}</h2>
<p class="{cls}">{msg}</p><p class="wait">Order {order_id}</p><a href="/shop">Back to the store</a></div></body></html>"""


FAKE_CHECKOUT = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Test checkout</title><style>body{{font-family:system-ui,Arial;background:#F7F6F2;margin:0;display:flex;min-height:100vh;align-items:center;justify-content:center}}
.c{{background:#fff;border:1px solid #D9D6CE;border-radius:18px;padding:24px;width:min(380px,92vw)}}.t{{background:#FFF4E0;color:#7A4300;font-size:11px;font-weight:700;letter-spacing:.1em;padding:4px 8px;border-radius:6px}}
button{{width:100%;padding:12px;margin-top:8px;border-radius:10px;border:1px solid #0B1220;font-size:15px;font-weight:600;background:#fff}}button.p{{background:#1746C8;color:#fff;border-color:#1746C8}}
select{{width:100%;padding:10px;border-radius:10px;margin-top:6px}}</style></head><body><div class="c"><span class="t">TEST CHECKOUT · FAKE GATEWAY</span>
<h2>₹{amount}</h2><form method="post" action="/fakecheckout/{order_id}"><label>Paying bank</label><select name="bank"><option>Bank A</option><option>Bank B</option><option>Bank C</option></select>
<button class="p" name="outcome" value="success">Pay</button><button name="outcome" value="bank">Fail: declined by bank (227)</button>
<button name="outcome" value="cancel">Fail: I closed the page (141)</button><button name="outcome" value="funds">Fail: insufficient balance (235)</button></form></div></body></html>"""


@router.get("/fakecheckout/{order_id}", response_class=HTMLResponse)
def fake_checkout(order_id: str):
    if not get_settings().demo_controls_enabled:
        raise HTTPException(403, "Demo controls are disabled in production")
    gw = get_gateway()
    if gw.name != "fake" or order_id not in gw.orders:
        raise HTTPException(404)
    return FAKE_CHECKOUT.format(amount=fmt_inr(gw.orders[order_id]["amount"]), order_id=order_id)


@router.post("/fakecheckout/{order_id}")
async def fake_checkout_submit(order_id: str, request: Request):
    if not get_settings().demo_controls_enabled:
        raise HTTPException(403, "Demo controls are disabled in production")
    gw = get_gateway()
    if gw.name != "fake" or order_id not in gw.orders:
        raise HTTPException(404)
    form = dict(await request.form())
    outcome = form.get("outcome", "success")
    txn = gw.finish_checkout(order_id, outcome == "success")
    code, msg = {"success": ("01", "Txn Success"), "bank": ("227", "Your payment has been declined by your bank"),
                 "cancel": ("141", "User has not completed transaction"),
                 "funds": ("235", "Insufficient balance")}.get(outcome, ("227", "Declined"))
    payload = {"ORDERID": order_id, "TXNID": txn, "TXNAMOUNT": f"{gw.orders[order_id]['amount'] / 100:.2f}",
               "STATUS": "TXN_SUCCESS" if outcome == "success" else "TXN_FAILURE", "RESPCODE": code, "RESPMSG": msg,
               "BANKNAME": form.get("bank", "Bank A"), "PAYMENTMODE": "UPI", "CHECKSUMHASH": "fake-ok"}
    # deliver exactly as Paytm would: a form POST to our callback
    from starlette.datastructures import FormData  # noqa: F401
    scope_req = _FakeFormRequest(payload)
    return await txn_callback(scope_req)


class _FakeFormRequest:
    def __init__(self, data):
        self._d = data

    async def form(self):
        return self._d
