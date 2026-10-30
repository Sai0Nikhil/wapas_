"""Persistent public storefront, stock reservations, verified payment and order status."""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import select

from . import audit, demand, inventory, payment_lifecycle
from .config import get_settings
from .db import session
from .gateway import get_gateway
from .merchant_os_models import Product
from .models import Customer, Payment, Store
from .commerce_models import StoreOrder, StoreOrderLine, StoreQR
from .store import _rate_ok
from .templates import LANG_NAMES, fmt_inr
from .qr import qr_png

router = APIRouter()
SHOP_PAGE = Path(__file__).parent / "static" / "commerce_shop.html"


@router.post("/api/paytm/payment-callback")
async def payment_link_callback(request: Request):
    """A signed webhook is only a wake-up hint; the provider status lookup settles the source."""
    form = dict(await request.form())
    provider = get_gateway()
    if not provider.verify_callback(form):
        raise HTTPException(400, "Invalid Paytm callback signature")
    link_id = str(form.get("LINKID") or form.get("linkId") or "")
    if not link_id:
        return {"ok": True, "status": "ignored"}
    with session() as s:
        payment = s.exec(select(Payment).where(
            Payment.provider_link_id == link_id,
            Payment.source_type.in_(("COUNTER_BILL", "KHATA_COLLECTION")),
        )).first()
        if payment is None:
            return {"ok": True, "status": "unknown"}
        payment_id = payment.id
    confirmed = provider.link_status(link_id)
    if confirmed.status.value not in {"SUCCESS", "FAILED"}:
        return {"ok": True, "status": confirmed.status.value}
    with session() as s:
        payment = s.get(Payment, payment_id)
        outcome = payment_lifecycle.apply_terminal_result(
            s, payment, confirmed, gateway_name=provider.name, expected_link_id=link_id,
        )
        s.commit()
    return {"ok": True, "status": outcome}


class CheckoutItem(BaseModel):
    product_id: str = Field(min_length=1, max_length=100)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class StoreCheckout(BaseModel):
    name: str = Field(min_length=2, max_length=60)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")
    language: str = Field(default="en", max_length=5)
    items: list[CheckoutItem] = Field(min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=12, max_length=120)
    order_token: str = Field(min_length=43, max_length=128)


def _amount(quantity: Decimal, unit_price_paise: int) -> int:
    if not quantity.is_finite() or quantity <= 0 or quantity != quantity.quantize(Decimal("0.001")):
        raise HTTPException(422, "Quantity must be positive with at most three decimal places")
    return int((quantity * Decimal(unit_price_paise)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _store_for_slug(s, slug: str) -> Store:
    store = s.exec(select(Store).where(Store.slug == slug)).first()
    if store is None:
        raise HTTPException(404, "Store not found")
    return store


def _order_response(order: StoreOrder, token: str, *, mode: str, checkout: dict | None = None) -> dict:
    payload = dict(checkout or {})
    payload.update({
        "ok": True, "mode": mode, "order_id": order.id,
        "customer_order_token": token,
        "result_url": f"/shop/result/{order.id}",
        "amount_paise": order.amount_paise,
        "amount": f"{order.amount_paise / 100:.2f}",
        "amount_fmt": fmt_inr(order.amount_paise),
        "status": order.status,
    })
    return payload


@router.get("/s/{store_slug}", response_class=HTMLResponse)
def public_store_page(store_slug: str):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", store_slug):
        raise HTTPException(404, "Store not found")
    return SHOP_PAGE.read_text(encoding="utf-8")


@router.get("/api/public/stores/{store_slug}/products")
def public_products(store_slug: str):
    with session() as s:
        store = _store_for_slug(s, store_slug)
        rows = inventory.list_products(s, merchant_id=store.merchant_id, store_id=store.id)
        products = []
        for product, balance in rows:
            if not product.is_service and balance.available <= 0:
                continue
            products.append({
                "id": product.id, "name": product.name, "category": product.category,
                "unit": product.unit, "unit_price_paise": product.unit_price_paise,
                "price_fmt": fmt_inr(product.unit_price_paise),
                "available": str(balance.available), "is_service": product.is_service,
            })
        return {"store": store.name, "store_slug": store.slug, "products": products}


@router.get("/api/public/stores/{store_slug}/search")
def public_store_search(store_slug: str, q: str, request: Request):
    query = demand.normalize_query(q)
    if len(query) < 2:
        raise HTTPException(422, "Search at least two characters")
    remote = request.client.host if request.client else "unknown"
    with session() as s:
        store = _store_for_slug(s, store_slug)
        if not _rate_ok("demand-search:" + store.id + ":" + remote, 40, 600):
            raise HTTPException(429, "Please wait before searching again")
        rows = inventory.list_products(s, merchant_id=store.merchant_id, store_id=store.id)
        active = [(product, balance) for product, balance in rows if product.status == "ACTIVE"]
        matched = [(product, balance) for product, balance in active if any(
            query in (value or "").casefold()
            for value in (product.name, product.category, product.sku, product.barcode)
        )]
        available = [(product, balance) for product, balance in matched
                     if product.is_service or balance.available > 0]
        if matched and not available:
            outcome = "OUT_OF_STOCK"
        elif not matched:
            outcome = "NO_MATCH"
        else:
            outcome = ""
        if outcome:
            # Store only a normalized query and an ephemeral bucketed hash. No
            # customer name, phone, or raw IP is retained in demand evidence.
            bucket = int(time.time() // 900)
            event_key = hashlib.sha256(f"{store.id}:{remote}:{query}:{bucket}".encode()).hexdigest()
            demand.record_outcome(s, merchant_id=store.merchant_id, store_id=store.id,
                                  query=query, outcome=outcome, event_key=event_key)
            s.commit()
        return {"query": query, "outcome": outcome or "MATCHED", "products": [{
            "id": product.id, "name": product.name, "category": product.category,
            "unit": product.unit, "unit_price_paise": product.unit_price_paise,
            "price_fmt": fmt_inr(product.unit_price_paise), "available": str(balance.available),
            "availability": "IN_STOCK" if product.is_service or balance.available > 0 else "OUT_OF_STOCK",
        } for product, balance in matched[:20]]}


@router.get("/api/public/stores/{store_slug}/qr.png")
def public_store_qr(store_slug: str):
    with session() as s:
        store = _store_for_slug(s, store_slug)
        target_url = get_settings().public_base_url.rstrip("/") + f"/s/{store.slug}"
        record = s.exec(select(StoreQR).where(
            StoreQR.merchant_id == store.merchant_id, StoreQR.store_id == store.id,
            StoreQR.status == "VERIFIED", StoreQR.target_url == target_url,
        )).first()
        if record is None:
            raise HTTPException(404, "Store QR is not verified")
        try:
            data = qr_png(target_url)
        except ImportError as e:
            raise HTTPException(503, "QR image support is not installed") from e
        return Response(data, media_type="image/png", headers={"Cache-Control": "public, max-age=3600"})


@router.post("/api/public/stores/{store_slug}/checkout", status_code=201)
def public_checkout(store_slug: str, body: StoreCheckout):
    if body.language not in LANG_NAMES:
        body.language = "en"
    if not (_rate_ok("phone:" + body.phone, 5, 600) and _rate_ok("all", 60, 60)):
        raise HTTPException(429, "Too many checkout attempts; please wait a few minutes")
    gateway = get_gateway()
    token_hash = hashlib.sha256(body.order_token.encode("utf-8")).hexdigest()
    order_id = "WAP" + str(int(time.time())) + uuid.uuid4().hex[:8].upper()
    with session() as s:
        store = _store_for_slug(s, store_slug)
        prior = s.exec(select(StoreOrder).where(
            StoreOrder.merchant_id == store.merchant_id,
            StoreOrder.store_id == store.id,
            StoreOrder.idempotency_key == body.idempotency_key,
        )).first()
        if prior:
            if not hmac.compare_digest(prior.token_hash, token_hash):
                raise HTTPException(409, "Checkout key was already used; start a new checkout")
            # Do not start a second Paytm transaction. The customer can safely refresh
            # the order result with the same local token.
            return JSONResponse(status_code=200, content=_order_response(prior, body.order_token, mode="existing"))

        customer_id = "shop_" + body.phone
        customer = s.get(Customer, customer_id)
        if customer is None:
            customer = Customer(id=customer_id, merchant_id=store.merchant_id, name=body.name.strip(),
                                phone=body.phone, language=body.language)
        else:
            customer.name, customer.language = body.name.strip(), body.language
        s.add(customer)
        s.flush()

        aggregated: dict[str, Decimal] = {}
        for item in body.items:
            aggregated[item.product_id] = aggregated.get(item.product_id, Decimal("0")) + item.quantity
        prepared = []
        total_paise = 0
        for product_id, quantity in aggregated.items():
            found = inventory.lookup_product(s, merchant_id=store.merchant_id, store_id=store.id,
                                             product_id=product_id)
            if found is None or found[0].status != "ACTIVE":
                raise HTTPException(400, "A selected product is no longer available")
            product, balance = found
            line_total = _amount(quantity, product.unit_price_paise)
            if not product.is_service and balance.available < quantity:
                raise HTTPException(409, f"Not enough {product.name} in stock")
            prepared.append((product, quantity, line_total))
            total_paise += line_total
        if total_paise <= 0:
            raise HTTPException(400, "Checkout total must be greater than zero")

        order = StoreOrder(
            id=order_id, merchant_id=store.merchant_id, store_id=store.id, customer_id=customer_id,
            token_hash=token_hash, idempotency_key=body.idempotency_key,
            status="PAYMENT_PENDING", fulfillment_state="UNFULFILLED", amount_paise=total_paise,
        )
        s.add(order)
        payment_id = f"pay_{order_id}"
        payment = Payment(
            id=payment_id, merchant_id=store.merchant_id, store_id=store.id,
            order_id=order_id, customer_id=customer_id,
            amount_paise=total_paise, bank="", method="", status="INIT_UNKNOWN",
            source_type="SHOP_ORDER", source_id=order_id, provider=gateway.name,
            provider_mid=get_settings().paytm_mid if gateway.name == "paytm" else "",
            provider_order_id=order_id, idempotency_key="shop-order-payment:" + order_id,
            created_at=datetime.now(timezone.utc),
        )
        s.add(payment)
        s.flush()
        order.payment_id = payment_id
        for product, quantity, line_total in prepared:
            reservation_id = "" if product.is_service else f"{order_id}:{product.id}"
            if reservation_id:
                inventory.reserve_stock(
                    s, merchant_id=store.merchant_id, store_id=store.id, product_id=product.id,
                    quantity=quantity, reservation_id=reservation_id, source_ref=order_id, source="shop_order",
                )
            s.add(StoreOrderLine(
                merchant_id=store.merchant_id, store_id=store.id, order_id=order_id,
                product_id=product.id, product_name=product.name, sku=product.sku,
                unit=product.unit, quantity=quantity, unit_price_paise=product.unit_price_paise,
                line_total_paise=line_total, reservation_id=reservation_id,
            ))
        audit.record(s, action="shop.order_created", entity_type="store_order", entity_id=order_id,
                     merchant_id=store.merchant_id, store_id=store.id, actor_type="customer",
                     actor_id=hashlib.sha256(customer_id.encode()).hexdigest()[:16],
                     source="public-storefront", idempotency_key="shop-order:" + order_id,
                     payload={"line_count": len(prepared), "amount_paise": total_paise})
        s.commit()

    callback_url = get_settings().public_base_url.rstrip("/") + "/api/paytm/txn-callback"
    result = gateway.initiate_checkout(order_id=order_id, amount_paise=total_paise,
                                       cust_id=customer_id, callback_url=callback_url)
    with session() as s:
        saved = s.get(StoreOrder, order_id)
        payment = s.get(Payment, f"pay_{order_id}")
        if payment.status != "INIT_UNKNOWN":
            s.commit()
            return _order_response(saved, body.order_token, mode="existing")
        if result.get("ok"):
            payment.status = "PENDING"
            s.add(payment)
            s.commit()
            return _order_response(saved, body.order_token, mode=gateway.name, checkout=result)
        if not result.get("uncertain"):
            if payment.status == "INIT_UNKNOWN":
                payment.status = "INIT_FAILED"
                saved.status = "PAYMENT_FAILED"
                saved.updated_at = datetime.now(timezone.utc)
                for line in s.exec(select(StoreOrderLine).where(
                    StoreOrderLine.order_id == order_id,
                    StoreOrderLine.merchant_id == saved.merchant_id,
                    StoreOrderLine.store_id == saved.store_id,
                )).all():
                    if line.reservation_id:
                        inventory.release_stock(s, merchant_id=saved.merchant_id, store_id=saved.store_id,
                                                reservation_id=line.reservation_id, source="payment_init_failed")
                s.add(payment)
                s.add(saved)
                audit.record(s, action="shop.payment_init_failed", entity_type="store_order", entity_id=order_id,
                             merchant_id=saved.merchant_id, store_id=saved.store_id, source="paytm-init",
                             idempotency_key="shop-init-failed:" + order_id,
                             payload={"error": result.get("error", "provider refused initiation")})
                s.commit()
            return _order_response(saved, body.order_token, mode="failed",
                                   checkout={"detail": "Could not start checkout; no payment was confirmed"})
        # Keep the order and reservation pending until the server-side status API resolves it.
        s.commit()
        pending = JSONResponse(status_code=202, content=_order_response(
            saved, body.order_token, mode="pending", checkout={"detail": "Checkout initiation is being verified"},
        ))
        return pending


@router.get("/api/public/orders/{order_id}")
def public_order_status(order_id: str, request: Request):
    token = request.headers.get("x-order-token", "")
    if len(token) < 43:
        raise HTTPException(401, "Order token required")
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    with session() as s:
        order = s.exec(select(StoreOrder).where(
            StoreOrder.id == order_id, StoreOrder.token_hash == token_hash,
        )).first()
        if order is None or not hmac.compare_digest(order.token_hash, token_hash):
            raise HTTPException(404, "Order not found")
        lines = s.exec(select(StoreOrderLine).where(
            StoreOrderLine.order_id == order.id, StoreOrderLine.merchant_id == order.merchant_id,
            StoreOrderLine.store_id == order.store_id,
        ).order_by(StoreOrderLine.created_at, StoreOrderLine.id)).all()
        return {
            "order_id": order.id, "status": order.status, "fulfillment_state": order.fulfillment_state,
            "amount_paise": order.amount_paise, "amount_fmt": fmt_inr(order.amount_paise),
            "created_at": order.created_at.isoformat(),
            "lines": [{"name": line.product_name, "quantity": str(line.quantity), "unit": line.unit,
                       "line_total_fmt": fmt_inr(line.line_total_paise)} for line in lines],
        }


def order_result_page(order_id: str) -> str:
    """Minimal customer view; the browser sends its token in a header, not in server logs."""
    slug = "default-store"
    try:
        with session() as s:
            order = s.get(StoreOrder, order_id)
            if order is not None:
                store = s.get(Store, order.store_id)
                if store is not None and store.slug:
                    slug = store.slug
    except Exception:
        pass
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Store order</title><style>body{{font-family:system-ui,Arial;background:#F7F6F2;color:#0B1220;display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}.c{{background:#fff;border:1px solid #D9D6CE;border-radius:18px;padding:28px;max-width:460px;width:92vw}}.muted{{color:#5F6773}}.state{{font-weight:700;color:#1746C8}}li{{margin:6px 0}}</style></head>
<body><div class="c"><h2>Store order</h2><p>Order {order_id}</p><p class="state" id="state">Checking payment status…</p><div id="items"></div><p id="fulfillment" class="muted"></p><a href="/s/{slug}">Back to store</a></div>
<script>(async()=>{{const id={order_id!r};const token=localStorage.getItem("wapas_order_token:"+id);if(!token){{document.getElementById("state").textContent="Open this order from the same browser used at checkout.";return;}}try{{const r=await fetch("/api/public/orders/"+encodeURIComponent(id),{{headers:{{"X-Order-Token":token}}}});if(!r.ok)throw new Error();const o=await r.json();const labels={{PAYMENT_PENDING:"Payment is still being confirmed",PAID:"Payment verified",PAYMENT_FAILED:"Payment was not completed",CANCELLED:"Order cancelled",SIMULATED:"Test checkout only; no real payment was verified"}};document.getElementById("state").textContent=labels[o.status]||o.status;document.getElementById("fulfillment").textContent="Fulfillment: "+o.fulfillment_state.replaceAll("_"," ");const itemList=document.createElement("ul");o.lines.forEach(x=>{{const line=document.createElement("li");line.textContent=String(x.quantity)+" "+String(x.unit)+" "+String(x.name)+" — ₹"+String(x.line_total_fmt);itemList.appendChild(line);}});const total=document.createElement("b");total.textContent="Total ₹"+String(o.amount_fmt);document.getElementById("items").replaceChildren(itemList,total);if(o.status==="PAYMENT_PENDING")setTimeout(()=>location.reload(),4000);}}catch{{document.getElementById("state").textContent="Order status is unavailable. Please refresh later.";}}}})();</script></body></html>"""
