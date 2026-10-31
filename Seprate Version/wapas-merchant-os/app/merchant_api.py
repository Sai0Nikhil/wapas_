"""Owner-facing API for the canonical merchant catalogue and stock ledger."""
from datetime import datetime
from decimal import Decimal
import http.client
from ipaddress import ip_address
import base64
import binascii
import json
import socket
import ssl
import time
import csv
import io
import uuid
from urllib.parse import urlsplit, quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from . import audit, auth, billing, counter_inputs, demand, inventory, khata, sarkar
from .db import session
from .merchant_os_models import InventoryBalance, InventoryMovement, Product, now
from .commerce_models import StoreOrder, StoreOrderLine, StoreQR
from .khata_models import KhataLedgerEntry
from .sound_models import SoundDevice, SoundEvent
from .models import Customer, Payment, Store
from .payment_requests import request_counter_bill_payment, request_khata_payment
from .config import get_settings
from .qr import qr_png
from .tenant_context import current_identity, current_merchant_id, current_store_id

router = APIRouter()


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS connection that dials only addresses already checked by the caller."""

    def __init__(self, host: str, port: int, addresses, *, timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._pinned_addresses = tuple(str(address) for address in addresses)
        self._connect_deadline = time.monotonic() + timeout

    def connect(self):
        if self._tunnel_host:
            raise OSError("Proxied connections are not supported for pinned storefront checks")
        errors = []
        for address in self._pinned_addresses:
            remaining = self._connect_deadline - time.monotonic()
            if remaining <= 0:
                break
            raw = None
            try:
                raw = socket.create_connection((address, self.port), timeout=remaining)
                self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
                remaining = self._connect_deadline - time.monotonic()
                if remaining <= 0:
                    self.sock.close()
                    self.sock = None
                    raise TimeoutError("Pinned storefront connection timed out")
                self.sock.settimeout(remaining)
                return
            except OSError as exc:
                if raw is not None:
                    try:
                        raw.close()
                    except OSError:
                        pass
                errors.append(exc)
        if errors:
            raise OSError("Could not connect to a validated public address") from errors[-1]
        raise OSError("No validated public addresses were supplied")


def _fetch_public_storefront(url: str, host: str, port: int, addresses, *, timeout: float = 8.0):
    """Fetch a small JSON response without a second DNS lookup or redirect follow."""
    parsed = urlsplit(url)
    parsed_host = parsed.hostname or ""
    try:
        canonical_host = str(ip_address(parsed_host))
    except ValueError:
        try:
            canonical_host = parsed_host.rstrip(".").encode("idna").decode("ascii").casefold()
        except UnicodeError as exc:
            raise ValueError("Storefront verification host is invalid") from exc
    if (parsed.scheme != "https" or canonical_host != host.casefold()
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ValueError("Storefront verification URL does not match the validated HTTPS host")
    conn = _PinnedHTTPSConnection(host, port, addresses, timeout=timeout)
    request_path = parsed.path or "/"
    if parsed.query:
        request_path += "?" + parsed.query
    try:
        conn.request("GET", request_path, headers={"Accept": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            return response.status, None
        content_type = (response.getheader("Content-Type") or "").split(";", 1)[0].strip().casefold()
        if content_type != "application/json":
            raise ValueError("Storefront verification endpoint did not return JSON")
        body = response.read(2 * 1024 * 1024 + 1)
        if len(body) > 2 * 1024 * 1024:
            raise ValueError("Storefront verification response exceeded the size limit")
        return response.status, json.loads(body)
    finally:
        conn.close()


@router.get("/api/merchant/opportunities/pulse")
def opportunity_pulse(days: int = 30):
    try:
        with session() as s:
            return demand.opportunity_pulse(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), days=days,
            )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(default="", max_length=80)
    sku: str = Field(default="", max_length=64)
    barcode: str = Field(default="", max_length=64)
    image_url: str = Field(default="", max_length=500)
    unit: str = Field(default="each", min_length=1, max_length=24)
    unit_price_paise: int = Field(gt=0)
    opening_stock: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    low_stock_threshold: Decimal = Field(default=Decimal("0"), ge=0, max_digits=12, decimal_places=3)
    is_service: bool = False


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=80)
    sku: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    image_url: str | None = Field(default=None, max_length=500)
    unit: str | None = Field(default=None, min_length=1, max_length=24)
    unit_price_paise: int | None = Field(default=None, gt=0)
    low_stock_threshold: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=3)
    is_service: bool | None = None
    status: str | None = Field(default=None, pattern="^(ACTIVE|ARCHIVED)$")


class StockAdjustment(BaseModel):
    delta: Decimal = Field(allow_inf_nan=False, max_digits=12, decimal_places=3)
    reason: str = Field(min_length=3, max_length=240)
    idempotency_key: str = Field(default_factory=lambda: "stock_" + uuid.uuid4().hex, min_length=8, max_length=100)


class BillCreate(BaseModel):
    idempotency_key: str = Field(default_factory=lambda: "bill_" + uuid.uuid4().hex, min_length=8, max_length=100)
    customer_name: str = Field(default="", max_length=120)
    customer_phone: str = Field(default="", max_length=20)


class CollectionLinkRequest(BaseModel):
    idempotency_key: str = Field(min_length=12, max_length=300)


class BillLineSet(BaseModel):
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=3)


class CounterTextInput(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


async def _bounded_upload(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File is too large. Maximum size is {limit // (1024 * 1024)} MB.")
    return data


def _counter_candidate_result(s, items: list[dict]) -> list[dict]:
    return counter_inputs.resolve_candidates(s, merchant_id=current_merchant_id(),
                                             store_id=current_store_id(), raw_items=items)


class FulfillOrder(BaseModel):
    confirm: bool = False


class KhataBillCredit(BaseModel):
    due_at: datetime | None = None
    note: str = Field(default="", max_length=240)


class KhataRepayment(BaseModel):
    amount_paise: int = Field(gt=0)
    method: str = Field(pattern="^(CASH|OTHER)$")
    idempotency_key: str = Field(min_length=8, max_length=100)
    note: str = Field(default="", max_length=240)
    confirm_received: bool = False


class KhataCollectionRequest(BaseModel):
    amount_paise: int = Field(gt=0)
    idempotency_key: str = Field(min_length=12, max_length=300)


class KhataReversal(BaseModel):
    reason: str = Field(min_length=3, max_length=240)


class KhataManualEntry(BaseModel):
    account_id: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    entry_type: str = Field(default="CREDIT_GIVEN", pattern="^(CREDIT_GIVEN|REPAYMENT|DEBIT|CREDIT|UDHAAR|JAMA)$")
    amount_paise: int = Field(gt=0)
    payment_method: str = Field(default="CASH", pattern="^(CASH|OTHER|UPI|MANUAL)$")
    idempotency_key: str | None = None
    note: str = Field(default="", max_length=240)


class SoundDeviceRegister(BaseModel):
    device_key: str = Field(pattern=r"^[A-Za-z0-9_-]{20,80}$")


class SoundEventAck(BaseModel):
    device_key: str = Field(pattern=r"^[A-Za-z0-9_-]{20,80}$")
    event_ids: list[int] = Field(min_length=1, max_length=100)


class SarkarAsk(BaseModel):
    message: str = Field(default="", max_length=1000)
    audio_base64: str = Field(default="", max_length=14_000_000)
    mime_type: str = Field(default="audio/webm", max_length=100)


class SarkarActionConfirm(BaseModel):
    confirmation_token: str = Field(min_length=20, max_length=128)


class SarkarToolCall(BaseModel):
    arguments: dict = Field(default_factory=dict)


@router.post("/api/merchant/sarkar/ask")
def ask_sarkar(body: SarkarAsk):
    message = body.message.strip()
    trace = {"mode": "TEXT", "provider": "none", "latency_ms": 0}
    if body.audio_base64:
        cfg = get_settings()
        if not cfg.sarvam_enabled:
            raise HTTPException(503, "Voice input is not configured. Type the request instead.")
        try:
            audio_bytes = base64.b64decode(body.audio_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise HTTPException(422, "Audio payload is invalid") from exc
        if not audio_bytes or len(audio_bytes) > 8 * 1024 * 1024:
            raise HTTPException(413, "Voice clips must be under 8 MB")
        from . import voice
        started = time.perf_counter()
        try:
            transcription = voice.transcribe_full(audio_bytes, body.mime_type)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(502, "Voice transcription failed. Type the request instead.") from exc
        message = (transcription.get("transcript") or "").strip()
        trace = {"mode": "TURN_BASED_STT", "provider": "Sarvam", "model": "saaras:v3",
                 "language": transcription.get("language_code", ""),
                 "latency_ms": round((time.perf_counter() - started) * 1000)}
        if not message:
            raise HTTPException(422, "No speech was recognized. Type the request instead.")
    if not message:
        raise HTTPException(422, "Enter a request or record a voice clip")
    with session() as s:
        result = sarkar.ask(s, message)
    result["input"] = trace
    result["transcript"] = message if trace["mode"] == "TURN_BASED_STT" else ""
    result["speech_output"] = {"status": "NOT CONFIGURED" if not get_settings().sarvam_enabled else "NOT REQUESTED",
                               "mode": "turn-based; no live interruption"}
    return result


@router.get("/api/merchant/sarkar/tools")
def list_sarkar_tools():
    return sarkar.available_tools()


@router.post("/api/merchant/sarkar/tools/{tool_name}")
def call_sarkar_tool(tool_name: str, body: SarkarToolCall):
    with session() as s:
        result = sarkar.invoke_tool(s, tool_name, body.arguments)
        s.commit()
        return result


@router.post("/api/merchant/sarkar/actions/{action_id}/confirm")
def confirm_sarkar_action(action_id: str, body: SarkarActionConfirm):
    with session() as s:
        result = sarkar.invoke_tool(s, "confirm_stock_receipt",
                                    {"action_id": action_id, "confirmation_token": body.confirmation_token})
        s.commit()
        return result


def _bill_row(s, bill_id: str) -> dict:
    bill, lines = billing.get_bill(s, merchant_id=current_merchant_id(), store_id=current_store_id(), bill_id=bill_id)
    payment = s.exec(select(Payment).where(
        Payment.id == bill.payment_id, Payment.merchant_id == current_merchant_id(),
        Payment.store_id == current_store_id(),
    )).first() if bill.payment_id else None
    khata_entry = s.exec(select(KhataLedgerEntry).where(
        KhataLedgerEntry.merchant_id == current_merchant_id(), KhataLedgerEntry.store_id == current_store_id(),
        KhataLedgerEntry.source_type == "counter_bill", KhataLedgerEntry.source_id == bill.id,
        KhataLedgerEntry.entry_type == "CREDIT_GIVEN",
    )).first()
    return {
        "id": bill.id, "bill_number": bill.bill_number, "state": bill.state,
        "revision": bill.revision, "customer_name": bill.customer_name,
        "customer_phone": bill.customer_phone,
        "subtotal_paise": bill.subtotal_paise, "discount_paise": bill.discount_paise,
        "tax_paise": bill.tax_paise, "total_paise": bill.total_paise,
        "total_fmt": f"{bill.total_paise // 100:,}.{bill.total_paise % 100:02d}",
        "created_at": bill.created_at.isoformat(), "updated_at": bill.updated_at.isoformat(),
        "issued_at": bill.issued_at.isoformat() if bill.issued_at else None,
        "lines": [{
            "id": line.id, "product_id": line.product_id, "name": line.product_name,
            "sku": line.sku, "unit": line.unit, "quantity": str(line.quantity),
            "unit_price_paise": line.unit_price_paise, "line_total_paise": line.line_total_paise,
            "line_total_fmt": f"{line.line_total_paise // 100:,}.{line.line_total_paise % 100:02d}",
        } for line in lines],
        "payment_state": bill.payment_state,
        "payment_id": payment.id if payment else None,
        "payment_status": payment.status if payment else None,
        "payment_provider": payment.provider if payment else None,
        "payment_url": payment.provider_link_url if payment else "",
        "payment_idempotency_key": payment.idempotency_key if payment else "",
        "khata_state": "ON_KHATA" if khata_entry else "NOT_ON_KHATA",
    }


def _product_row(product, balance) -> dict:
    available = balance.available
    low = not product.is_service and available <= balance.low_stock_threshold
    return {
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "sku": product.sku,
        "barcode": product.barcode,
        "image_url": product.image_url,
        "unit": product.unit,
        "unit_price_paise": product.unit_price_paise,
        "price_fmt": f"{product.unit_price_paise // 100:,}.{product.unit_price_paise % 100:02d}",
        "on_hand": str(balance.on_hand),
        "reserved": str(balance.reserved),
        "available": str(available),
        "low_stock_threshold": str(balance.low_stock_threshold),
        "stock_state": "SERVICE" if product.is_service else ("LOW" if low else "IN_STOCK"),
        "status": product.status,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def _product_or_404(s, product_id: str):
    product = s.exec(select(Product).where(
        Product.id == product_id,
        Product.merchant_id == current_merchant_id(),
        Product.store_id == current_store_id(),
    )).first()
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/api/merchant/catalog/products")
def list_catalog_products():
    with session() as s:
        rows = inventory.list_products(s, merchant_id=current_merchant_id(), store_id=current_store_id())
        return [_product_row(product, balance) for product, balance in rows]


@router.get("/api/merchant/catalog/products/lookup")
def lookup_catalog_product(product_id: str = "", barcode: str = "", sku: str = ""):
    try:
        with session() as s:
            found = inventory.lookup_product(s, merchant_id=current_merchant_id(), store_id=current_store_id(),
                                              product_id=product_id, barcode=barcode, sku=sku)
            if found is None or found[0].status != "ACTIVE":
                raise HTTPException(404, "Product not found")
            return _product_row(*found)
    except inventory.InvalidInventoryOperation as e:
        raise HTTPException(422, str(e)) from e


@router.post("/api/merchant/catalog/products", status_code=201)
def create_catalog_product(body: ProductCreate):
    product_id = "prd_" + uuid.uuid4().hex
    with session() as s:
        try:
            product = inventory.create_product(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), product_id=product_id,
                name=body.name.strip(), sku=body.sku.strip(), barcode=body.barcode.strip(),
                unit=body.unit.strip(), unit_price_paise=body.unit_price_paise, opening_stock=body.opening_stock,
                low_stock_threshold=body.low_stock_threshold,
            )
            product.category = body.category.strip()
            product.image_url = body.image_url.strip()
            product.is_service = body.is_service
            s.add(product)
            audit.record(s, action="catalog.product_created", entity_type="product", entity_id=product.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="catalog:create:" + product.id,
                         payload={"name": product.name, "unit": product.unit,
                                  "unit_price_paise": product.unit_price_paise})
            s.commit()
            rows = inventory.list_products(s, merchant_id=current_merchant_id(), store_id=current_store_id())
            pair = next((row for row in rows if row[0].id == product.id), None)
            return _product_row(*pair)
        except inventory.InventoryError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.patch("/api/merchant/catalog/products/{product_id}")
def update_catalog_product(product_id: str, body: ProductUpdate):
    changes = body.model_dump(exclude_unset=True)
    if any(value is None for value in changes.values()):
        raise HTTPException(422, "Product fields cannot be null; use an empty string to clear text fields")
    with session() as s:
        product = _product_or_404(s, product_id)
        before = {key: getattr(product, key) for key in changes}
        for key, value in changes.items():
            if isinstance(value, str):
                value = value.strip()
            if key == "sku" and value == "":
                value = product.id
            setattr(product, key, value)
        product.updated_at = now()
        if "low_stock_threshold" in changes:
            balance = s.exec(select(InventoryBalance).where(
                InventoryBalance.merchant_id == current_merchant_id(),
                InventoryBalance.store_id == current_store_id(),
                InventoryBalance.product_id == product_id,
            )).one()
            balance.low_stock_threshold = changes["low_stock_threshold"]
            s.add(balance)
        try:
            s.add(product)
            s.flush()
        except IntegrityError as e:
            s.rollback()
            raise HTTPException(409, "SKU or barcode is already used by this store") from e
        audit.record(s, action="catalog.product_updated", entity_type="product", entity_id=product.id,
                     merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                     source="owner-console", idempotency_key="catalog:update:" + uuid.uuid4().hex,
                     before_ref=str(before), after_ref=str(changes),
                     payload={"fields": list(changes)})
        s.commit()
        balance = s.exec(select(InventoryBalance).where(
            InventoryBalance.merchant_id == current_merchant_id(),
            InventoryBalance.store_id == current_store_id(),
            InventoryBalance.product_id == product_id,
        )).one()
        return _product_row(product, balance)


@router.post("/api/merchant/catalog/products/{product_id}/stock-adjustments")
def adjust_catalog_stock(product_id: str, body: StockAdjustment):
    if body.delta == 0:
        raise HTTPException(422, "Stock adjustment must be non-zero")
    with session() as s:
        _product_or_404(s, product_id)
        try:
            inventory.adjust_stock(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), product_id=product_id,
                delta=body.delta, kind="adjustment", source_ref=body.idempotency_key,
                reason=body.reason.strip(), idempotency_key=body.idempotency_key,
            )
        except inventory.InventoryError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e
        movement = s.exec(select(InventoryMovement).where(
            InventoryMovement.merchant_id == current_merchant_id(),
            InventoryMovement.store_id == current_store_id(),
            InventoryMovement.idempotency_key == body.idempotency_key,
        )).first()
        if movement is None:
            s.rollback()
            raise HTTPException(500, "Stock movement was not recorded")
        audit.record(s, action="inventory.adjusted", entity_type="product", entity_id=product_id,
                     merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                     source="owner-console", idempotency_key="audit:" + body.idempotency_key,
                     payload={"movement_id": movement.id, "delta": str(body.delta), "reason": body.reason})
        s.commit()
        rows = inventory.list_products(s, merchant_id=current_merchant_id(), store_id=current_store_id())
        pair = next((row for row in rows if row[0].id == product_id), None)
        return {"product": _product_row(*pair), "movement_id": movement.id}


@router.get("/api/merchant/catalog/movements")
def list_catalog_movements(limit: int = 50):
    if not 1 <= limit <= 200:
        raise HTTPException(422, "limit must be between 1 and 200")
    with session() as s:
        movements = inventory.list_movements(s, merchant_id=current_merchant_id(), store_id=current_store_id(), limit=limit)
        return [{
            "id": movement.id,
            "product_id": movement.product_id,
            "kind": movement.kind,
            "quantity": str(movement.quantity),
            "on_hand_delta": str(movement.on_hand_delta),
            "reserved_delta": str(movement.reserved_delta),
            "source": movement.source,
            "source_ref": movement.source_ref,
            "reason": movement.reason,
            "created_at": movement.created_at.isoformat(),
        } for movement in movements]


@router.post("/api/merchant/bills", status_code=201)
def create_counter_bill(body: BillCreate):
    with session() as s:
        try:
            bill = billing.create_draft(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(),
                idempotency_key=body.idempotency_key,
                customer_name=body.customer_name.strip(), customer_phone=body.customer_phone.strip(),
            )
            audit.record(s, action="counter.draft_created", entity_type="bill", entity_id=bill.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="bill:create:" + body.idempotency_key,
                         payload={"bill_number": bill.bill_number})
            s.commit()
            return _bill_row(s, bill.id)
        except billing.BillingError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.get("/api/merchant/bills")
def list_counter_bills(limit: int = 30):
    try:
        with session() as s:
            bills = billing.list_bills(s, merchant_id=current_merchant_id(), store_id=current_store_id(), limit=limit)
            return [_bill_row(s, bill.id) for bill in bills]
    except billing.BillingError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/api/merchant/bills/{bill_id}")
def get_counter_bill(bill_id: str):
    with session() as s:
        try:
            return _bill_row(s, bill_id)
        except inventory.InventoryNotFound as e:
            raise HTTPException(404, str(e)) from e


@router.put("/api/merchant/bills/{bill_id}/lines/{product_id}")
def set_counter_line(bill_id: str, product_id: str, body: BillLineSet):
    with session() as s:
        try:
            bill, line = billing.set_line(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(),
                bill_id=bill_id, product_id=product_id, quantity=body.quantity,
            )
            audit.record(s, action="counter.line_set", entity_type="bill_line", entity_id=line.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="bill-line:" + uuid.uuid4().hex,
                         payload={"bill_id": bill.id, "product_id": product_id, "quantity": str(line.quantity),
                                  "unit_price_paise": line.unit_price_paise})
            s.commit()
            return _bill_row(s, bill.id)
        except (billing.BillingError, inventory.InventoryError) as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


async def _recognize_counter_image(bill_id: str, image: UploadFile, consent: bool, task: str):
    # Confirm the target draft and tenant before accepting any recognition output.
    with session() as s:
        try:
            bill, _ = billing.get_bill(s, merchant_id=current_merchant_id(),
                                       store_id=current_store_id(), bill_id=bill_id)
        except inventory.InventoryNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        if bill.state != "DRAFT":
            raise HTTPException(409, "Recognition is available only for an editable Counter draft.")
    raw = await _bounded_upload(image, counter_inputs.MAX_IMAGE_BYTES)
    normalized = counter_inputs.validate_image(raw, image.content_type or "")
    cfg = get_settings()
    if not cfg.vision_configured:
        return {"status": "NOT CONFIGURED", "message": "Vision recognition is not configured. Search the catalogue and add items manually.", "items": []}
    if not consent:
        return {"status": "CONSENT REQUIRED", "message": "This image has not been sent. Allow external image processing to request catalogue suggestions.", "items": []}
    try:
        extracted = counter_inputs._image_candidates(normalized, task)
        with session() as s:
            resolved = _counter_candidate_result(s, extracted)
        return {"status": "REVIEW REQUIRED", "message": "Check every recognized line and select saved catalogue items. Prices and stock come from Wapas; nothing has been added yet.", "items": resolved}
    except Exception as exc:  # provider timeout, malformed response, or unavailable service
        return {"status": "DEGRADED", "message": "Recognition could not complete. Nothing was added. Search the catalogue or transcribe the list manually.", "items": []}


@router.post("/api/merchant/bills/{bill_id}/input/photo")
async def counter_product_photo(bill_id: str, image: UploadFile = File(...),
                                consent_to_external_processing: bool = Form(False)):
    return await _recognize_counter_image(bill_id, image, consent_to_external_processing, "photo")


@router.post("/api/merchant/bills/{bill_id}/input/parchi")
async def counter_parchi(bill_id: str, image: UploadFile = File(...),
                         consent_to_external_processing: bool = Form(False)):
    return await _recognize_counter_image(bill_id, image, consent_to_external_processing, "parchi")


@router.post("/api/merchant/bills/{bill_id}/input/voice")
async def counter_voice(bill_id: str, audio: UploadFile = File(...),
                        consent_to_external_processing: bool = Form(False)):
    with session() as s:
        try:
            bill, _ = billing.get_bill(s, merchant_id=current_merchant_id(),
                                       store_id=current_store_id(), bill_id=bill_id)
        except inventory.InventoryNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        if bill.state != "DRAFT":
            raise HTTPException(409, "Voice input is available only for an editable Counter draft.")
    raw = await _bounded_upload(audio, counter_inputs.MAX_AUDIO_BYTES)
    mime = counter_inputs.validate_audio(raw, audio.content_type or "")
    if not get_settings().sarvam_enabled:
        return {"status": "NOT CONFIGURED", "message": "Voice transcription is not configured. Use the typed catalogue input.", "transcript": "", "items": []}
    if not consent_to_external_processing:
        return {"status": "CONSENT REQUIRED", "message": "This recording has not been sent. Allow external transcription to create suggestions.", "transcript": "", "items": []}
    try:
        transcript = counter_inputs.transcribe_counter_audio(raw, mime)
        proposed = counter_inputs.parse_voice_transcript(transcript)
        with session() as s:
            resolved = _counter_candidate_result(s, proposed)
        status = "REVIEW REQUIRED" if resolved else "NEEDS CLARIFICATION"
        message = ("Review the transcript and each catalogue match. Nothing has been added yet." if resolved else
                   "The transcript did not contain clear quantity and product pairs. Edit the transcript or add products manually.")
        return {"status": status, "message": message, "transcript": transcript, "items": resolved}
    except Exception as exc:  # provider timeout, malformed response, or unavailable service
        return {"status": "DEGRADED", "message": "Transcription failed. Nothing was added. Use the typed catalogue input.", "transcript": "", "items": []}


@router.post("/api/merchant/bills/{bill_id}/input/text")
def counter_text_input(bill_id: str, body: CounterTextInput):
    with session() as s:
        try:
            bill, _ = billing.get_bill(s, merchant_id=current_merchant_id(),
                                       store_id=current_store_id(), bill_id=bill_id)
        except inventory.InventoryNotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        if bill.state != "DRAFT":
            raise HTTPException(409, "Text suggestions are available only for an editable Counter draft.")
        parsed = counter_inputs.parse_manual_list(body.text)
        if not parsed:
            return {"status": "NEEDS CLARIFICATION", "message": "Use one explicit quantity and product name per line, such as ‘2 rice bags’. Nothing was added.", "items": []}
        items = _counter_candidate_result(s, parsed)
        return {"status": "REVIEW REQUIRED", "message": "Review each typed line and select a saved catalogue item. Nothing has been added yet.", "items": items}


@router.delete("/api/merchant/bills/{bill_id}/lines/{line_id}")
def delete_counter_line(bill_id: str, line_id: str):
    with session() as s:
        try:
            bill = billing.remove_line(s, merchant_id=current_merchant_id(), store_id=current_store_id(),
                                       bill_id=bill_id, line_id=line_id)
            audit.record(s, action="counter.line_removed", entity_type="bill", entity_id=bill.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="bill-line-remove:" + uuid.uuid4().hex,
                         payload={"line_id": line_id})
            s.commit()
            return _bill_row(s, bill.id)
        except (billing.BillingError, inventory.InventoryError) as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.post("/api/merchant/bills/{bill_id}/issue")
def issue_counter_bill(bill_id: str):
    with session() as s:
        try:
            bill = billing.issue_bill(s, merchant_id=current_merchant_id(), store_id=current_store_id(), bill_id=bill_id)
            audit.record(s, action="counter.bill_issued", entity_type="bill", entity_id=bill.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="bill:issue:" + bill.id,
                         payload={"bill_number": bill.bill_number, "total_paise": bill.total_paise})
            s.commit()
            return _bill_row(s, bill.id)
        except (billing.BillingError, inventory.InventoryError) as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.post("/api/merchant/bills/{bill_id}/payments")
def request_counter_payment(bill_id: str, body: CollectionLinkRequest):
    return request_counter_bill_payment(bill_id, body.idempotency_key)


@router.post("/api/merchant/bills/{bill_id}/cancel")
def cancel_counter_bill(bill_id: str):
    with session() as s:
        try:
            prior, _lines = billing.get_bill(s, merchant_id=current_merchant_id(),
                                             store_id=current_store_id(), bill_id=bill_id)
            previous_state = prior.state
            bill = billing.cancel_draft(s, merchant_id=current_merchant_id(), store_id=current_store_id(), bill_id=bill_id)
            audit.record(s, action="counter.bill_cancelled", entity_type="bill", entity_id=bill.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="bill:cancel:" + bill.id,
                         payload={"bill_number": bill.bill_number, "previous_state": previous_state})
            s.commit()
            return _bill_row(s, bill.id)
        except (billing.BillingError, inventory.InventoryError) as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


def _khata_account_row(account, customer, outstanding: int) -> dict:
    return {
        "id": account.id, "customer_id": customer.id, "name": customer.name,
        "phone": customer.phone, "outstanding_paise": outstanding,
        "outstanding_fmt": f"{outstanding // 100:,}.{outstanding % 100:02d}",
        "reminder_consent": account.reminder_consent,
        "created_at": account.created_at.isoformat(),
    }


def _khata_entry_row(entry, running_balance: int | None = None) -> dict:
    return {
        "id": entry.id, "entry_type": entry.entry_type, "delta_paise": entry.delta_paise,
        "amount_fmt": f"{abs(entry.delta_paise) // 100:,}.{abs(entry.delta_paise) % 100:02d}",
        "source_type": entry.source_type, "source_id": entry.source_id,
        "payment_method": entry.payment_method, "recording_basis": entry.recording_basis,
        "reverses_entry_id": entry.reverses_entry_id, "due_at": entry.due_at.isoformat() if entry.due_at else None,
        "note": entry.note, "created_at": entry.created_at.isoformat(),
        "running_balance_paise": running_balance,
    }


@router.get("/api/merchant/khata/accounts")
def list_khata_accounts(limit: int = 100):
    if not 1 <= limit <= 200:
        raise HTTPException(422, "limit must be between 1 and 200")
    with session() as s:
        rows = khata.list_accounts(s, merchant_id=current_merchant_id(), store_id=current_store_id(), limit=limit)
        return [{
            "id": row["id"], "customer_id": row["customer_id"], "name": row["name"],
            "phone": row["phone"], "outstanding_paise": row["outstanding_paise"],
            "outstanding_fmt": f"{row['outstanding_paise'] // 100:,}.{row['outstanding_paise'] % 100:02d}",
            "reminder_consent": row["reminder_consent"], "created_at": row["created_at"].isoformat(),
        } for row in rows]


@router.get("/api/merchant/khata/accounts/{account_id}")
def get_khata_account(account_id: str):
    with session() as s:
        try:
            account, customer, entries, balance = khata.account_history(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), account_id=account_id,
            )
            running = 0
            result = []
            for entry in entries:
                running += entry.delta_paise
                result.append(_khata_entry_row(entry, running))
            pending_payment = s.exec(select(Payment).where(
                Payment.merchant_id == current_merchant_id(), Payment.store_id == current_store_id(),
                Payment.source_type == "KHATA_COLLECTION", Payment.source_id == account_id,
                Payment.status.in_(("INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION")),
            ).order_by(Payment.created_at.desc())).first()
            return {"account": _khata_account_row(account, customer, balance), "entries": result,
                    "outstanding_paise": balance,
                    "pending_collection": ({
                        "payment_id": pending_payment.id, "status": pending_payment.status,
                        "provider": pending_payment.provider, "amount_paise": pending_payment.amount_paise,
                        "checkout_url": pending_payment.provider_link_url,
                        "idempotency_key": pending_payment.idempotency_key,
                    } if pending_payment else None)}
        except khata.KhataError as e:
            raise HTTPException(404, str(e)) from e


@router.post("/api/merchant/bills/{bill_id}/khata")
def add_bill_to_khata(bill_id: str, body: KhataBillCredit):
    with session() as s:
        try:
            account, entry = khata.add_bill_to_khata(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), bill_id=bill_id,
                due_at=body.due_at, note=body.note,
            )
            customer = s.get(Customer, account.customer_id)
            balance = khata.balance_paise(s, merchant_id=current_merchant_id(),
                                          store_id=current_store_id(), account_id=account.id)
            audit.record(s, action="khata.bill_added", entity_type="khata_account", entity_id=account.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="counter", idempotency_key="audit:khata-bill:" + bill_id,
                         payload={"entry_id": entry.id, "bill_id": bill_id, "amount_paise": entry.delta_paise})
            s.commit()
            return {"account": _khata_account_row(account, customer, balance),
                    "entry": _khata_entry_row(entry, balance), "payment_state": "NOT_RECORDED",
                    "credit_state": "ON_KHATA"}
        except khata.KhataError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.post("/api/merchant/khata/accounts/{account_id}/repayments")
def record_khata_repayment(account_id: str, body: KhataRepayment):
    with session() as s:
        pending = s.exec(select(Payment).where(
            Payment.merchant_id == current_merchant_id(), Payment.store_id == current_store_id(),
            Payment.source_type == "KHATA_COLLECTION", Payment.source_id == account_id,
            Payment.status.in_(("INIT_UNKNOWN", "PENDING", "PENDING_RECONCILIATION")),
        )).first()
        if pending:
            raise HTTPException(409, "A Paytm collection request is pending; verify it before recording another repayment")
        try:
            entry, balance = khata.record_repayment(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), account_id=account_id,
                amount_paise=body.amount_paise, method=body.method,
                idempotency_key=body.idempotency_key, note=body.note,
                received=body.confirm_received,
            )
            audit.record(s, action="khata.repayment_recorded", entity_type="khata_account", entity_id=account_id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="audit:khata-repayment:" + entry.id,
                         payload={"entry_id": entry.id, "amount_paise": -entry.delta_paise,
                                  "method": entry.payment_method, "recording_basis": entry.recording_basis})
            s.commit()
            return {"entry": _khata_entry_row(entry, balance), "outstanding_paise": balance,
                    "recording_basis": "MERCHANT_CONFIRMED_RECEIPT"}
        except khata.KhataError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.post("/api/merchant/khata/accounts/{account_id}/payment-links")
def request_khata_collection(account_id: str, body: KhataCollectionRequest):
    return request_khata_payment(account_id, body.amount_paise, body.idempotency_key)


@router.post("/api/merchant/khata/entries/{entry_id}/reverse")
def reverse_khata_entry(entry_id: str, body: KhataReversal):
    with session() as s:
        try:
            entry, balance = khata.reverse_entry(
                s, merchant_id=current_merchant_id(), store_id=current_store_id(), entry_id=entry_id,
                reason=body.reason,
            )
            audit.record(s, action="khata.entry_reversed", entity_type="khata_account", entity_id=entry.account_id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="owner-console", idempotency_key="audit:khata-reversal:" + entry.id,
                         payload={"reversal_entry_id": entry.id, "reverses_entry_id": entry.reverses_entry_id,
                                  "delta_paise": entry.delta_paise, "reason": body.reason})
            s.commit()
            return {"entry": _khata_entry_row(entry, balance), "outstanding_paise": balance}
        except khata.KhataError as e:
            s.rollback()
            raise HTTPException(409, str(e)) from e


@router.post("/api/merchant/khata/entries")
def add_khata_manual_entry(body: KhataManualEntry):
    with session() as s:
        try:
            account, entry, balance = khata.add_manual_entry(
                s,
                merchant_id=current_merchant_id(),
                store_id=current_store_id(),
                account_id=body.account_id,
                customer_phone=body.customer_phone,
                customer_name=body.customer_name,
                entry_type=body.entry_type,
                amount_paise=body.amount_paise,
                note=body.note,
                payment_method=body.payment_method,
                idempotency_key=body.idempotency_key,
            )
            customer = s.get(Customer, account.customer_id)
            audit.record(s, action="khata.manual_entry_added", entity_type="khata_account", entity_id=account.id,
                         merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                         source="manual_entry", idempotency_key="audit:khata-manual:" + entry.id,
                         payload={"entry_id": entry.id, "amount_paise": entry.delta_paise, "entry_type": entry.entry_type})
            s.commit()
            return {
                "account": _khata_account_row(account, customer, balance),
                "entry": _khata_entry_row(entry, balance),
                "outstanding_paise": balance,
            }
        except khata.KhataError as e:
            s.rollback()
            raise HTTPException(400, str(e)) from e


@router.get("/api/merchant/orders")
def list_merchant_orders(limit: int = 50):
    if not 1 <= limit <= 200:
        raise HTTPException(422, "limit must be between 1 and 200")
    with session() as s:
        orders = s.exec(select(StoreOrder).where(
            StoreOrder.merchant_id == current_merchant_id(), StoreOrder.store_id == current_store_id(),
        ).order_by(StoreOrder.created_at.desc()).limit(limit)).all()
        result = []
        for order in orders:
            lines = s.exec(select(StoreOrderLine).where(
                StoreOrderLine.order_id == order.id, StoreOrderLine.merchant_id == current_merchant_id(),
                StoreOrderLine.store_id == current_store_id(),
            ).order_by(StoreOrderLine.created_at)).all()
            result.append({
                "id": order.id, "status": order.status, "fulfillment_state": order.fulfillment_state,
                "amount_paise": order.amount_paise,
                "amount_fmt": f"{order.amount_paise // 100:,}.{order.amount_paise % 100:02d}",
                "created_at": order.created_at.isoformat(),
                "lines": [{"name": line.product_name, "quantity": str(line.quantity), "unit": line.unit}
                          for line in lines],
            })
        return result


@router.post("/api/merchant/orders/{order_id}/fulfill")
def fulfill_order(order_id: str, body: FulfillOrder):
    if not body.confirm:
        raise HTTPException(422, "Confirm fulfillment after handing over the goods")
    with session() as s:
        order = s.exec(select(StoreOrder).where(
            StoreOrder.id == order_id, StoreOrder.merchant_id == current_merchant_id(),
            StoreOrder.store_id == current_store_id(),
        )).first()
        if order is None:
            raise HTTPException(404, "Order not found")
        payment = s.exec(select(Payment).where(
            Payment.id == order.payment_id, Payment.merchant_id == current_merchant_id(),
            Payment.store_id == current_store_id(), Payment.source_type == "SHOP_ORDER",
            Payment.source_id == order.id, Payment.provider == "paytm", Payment.status == "SUCCESS",
            Payment.verified_at.is_not(None), Payment.amount_paise == order.amount_paise,
            Payment.currency == "INR",
        )).first()
        if order.status != "PAID" or payment is None:
            raise HTTPException(409, "Only a payment-verified order can be fulfilled")
        if order.fulfillment_state == "FULFILLED":
            return {"order_id": order.id, "fulfillment_state": order.fulfillment_state}
        order.fulfillment_state = "FULFILLED"
        order.fulfilled_at = now()
        order.updated_at = order.fulfilled_at
        s.add(order)
        audit.record(s, action="shop.order_fulfilled", entity_type="store_order", entity_id=order.id,
                     merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                     source="owner-console", idempotency_key="shop-fulfill:" + order.id,
                     payload={"fulfillment_state": "FULFILLED"})
        s.commit()
        return {"order_id": order.id, "fulfillment_state": order.fulfillment_state}


def _store_qr_payload(record: StoreQR | None, base_url: str, slug: str) -> dict:
    target = base_url.rstrip("/") + f"/s/{slug}"
    ready = bool(record and record.status == "VERIFIED" and record.target_url == target)
    return {
        "store_url": target,
        "status": "VERIFIED" if ready else "NOT_READY",
        "ready": ready,
        "verified_at": record.verified_at.isoformat() if ready and record.verified_at else None,
        "qr_path": f"/api/public/stores/{slug}/qr.png" if ready else "",
        "message": "Public storefront URL was reached and matched this store." if ready else
                   "Set a reachable HTTPS PUBLIC_BASE_URL, then verify the storefront before printing a QR.",
    }


@router.get("/api/merchant/storefront/qr")
def store_qr_status():
    cfg = get_settings()
    with session() as s:
        store = s.get(Store, current_store_id())
        if store is None or store.merchant_id != current_merchant_id():
            raise HTTPException(404, "Store not found")
        record = s.exec(select(StoreQR).where(StoreQR.merchant_id == current_merchant_id(),
                                              StoreQR.store_id == current_store_id())).first()
        return _store_qr_payload(record, cfg.public_base_url, store.slug)


@router.post("/api/merchant/storefront/qr/verify")
def verify_storefront_for_qr():
    cfg = get_settings()
    with session() as s:
        store = s.get(Store, current_store_id())
        if store is None or store.merchant_id != current_merchant_id():
            raise HTTPException(404, "Store not found")
        store_slug = store.slug
    try:
        parsed = urlsplit(cfg.public_base_url.rstrip("/"))
        host = parsed.hostname or ""
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(409, "Set PUBLIC_BASE_URL to a valid public HTTPS address before creating a store QR") from exc
    if (parsed.scheme != "https" or not host or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port not in (None, 443)
            or host.casefold() in {"localhost", "localhost.localdomain"}):
        raise HTTPException(409, "Set PUBLIC_BASE_URL to a reachable public HTTPS address before creating a store QR")

    try:
        literal = ip_address(host)
        addresses = [literal]
        host = str(literal)
    except ValueError:
        try:
            host = host.rstrip(".").encode("idna").decode("ascii").casefold()
            rows = socket.getaddrinfo(host, port or 443, type=socket.SOCK_STREAM)
            addresses = list(dict.fromkeys(ip_address(row[4][0]) for row in rows))
        except (OSError, UnicodeError, ValueError, IndexError) as exc:
            raise HTTPException(409, "PUBLIC_BASE_URL host did not resolve to a public internet address") from exc
    if not addresses or len(addresses) > 16 or any(not address.is_global for address in addresses):
        raise HTTPException(409, "PUBLIC_BASE_URL may not resolve to private, loopback, link-local, or reserved addresses")

    target = cfg.public_base_url.rstrip("/") + f"/s/{store_slug}"
    verify_url = cfg.public_base_url.rstrip("/") + f"/api/public/stores/{store_slug}/products"
    try:
        response_status, data = _fetch_public_storefront(verify_url, host, port or 443, addresses, timeout=8.0)
        if response_status != 200:
            raise HTTPException(502, "The public storefront endpoint did not return HTTP 200")
        products = data.get("products") if isinstance(data, dict) else None
        valid_products = isinstance(products, list) and len(products) <= 1000 and all(
            isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("name"), str)
            and isinstance(row.get("unit"), str) and isinstance(row.get("unit_price_paise"), int)
            and row["unit_price_paise"] >= 0 and isinstance(row.get("available"), str)
            and isinstance(row.get("is_service"), bool)
            for row in products
        )
        if not isinstance(data, dict) or not valid_products or not isinstance(data.get("store"), str):
            raise HTTPException(502, "The public storefront response does not match the expected product contract")
    except Exception as e:  # noqa: BLE001
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(502, "Could not verify the public storefront URL") from e
    if data.get("store_slug") != store_slug:
        raise HTTPException(409, "The configured public URL did not return this Wapas store")

    with session() as s:
        store = s.get(Store, current_store_id())
        if store is None or store.merchant_id != current_merchant_id():
            raise HTTPException(404, "Store not found")
        row = s.exec(select(StoreQR).where(StoreQR.merchant_id == current_merchant_id(),
                                           StoreQR.store_id == current_store_id())).first()
        if row is None:
            row = StoreQR(merchant_id=current_merchant_id(), store_id=current_store_id(),
                          target_url=target, verification_url=verify_url)
        if store.slug != store_slug:
            raise HTTPException(409, "The configured public URL did not return this Wapas store")
        row.target_url, row.verification_url = target, verify_url
        row.status, row.verified_at, row.updated_at = "VERIFIED", now(), now()
        s.add(row)
        audit.record(s, action="shop.qr_verified", entity_type="store", entity_id=current_store_id(),
                     merchant_id=current_merchant_id(), store_id=current_store_id(), actor_type="merchant", actor_id="local-owner",
                     source="public-storefront-check", idempotency_key="shop-qr-verify:" + row.id,
                     payload={"target_url": target, "verification_url": verify_url})
        s.commit()
        return _store_qr_payload(row, cfg.public_base_url, store.slug)


@router.get("/api/merchant/storefront/qr.png")
def download_store_qr():
    cfg = get_settings()
    with session() as s:
        store = s.get(Store, current_store_id())
        if store is None or store.merchant_id != current_merchant_id():
            raise HTTPException(404, "Store not found")
        record = s.exec(select(StoreQR).where(StoreQR.merchant_id == current_merchant_id(),
                                              StoreQR.store_id == current_store_id(),
                                              StoreQR.status == "VERIFIED")).first()
        if not record or record.target_url != cfg.public_base_url.rstrip("/") + f"/s/{store.slug}":
            raise HTTPException(409, "Verify the current public storefront URL before downloading its QR")
        try:
            data = qr_png(record.target_url)
        except ImportError as e:
            raise HTTPException(503, "QR image support is not installed") from e
        return Response(data, media_type="image/png",
                        headers={"Cache-Control": "no-store"})


@router.post("/api/merchant/sound/device")
def register_sound_device(body: SoundDeviceRegister):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        device = s.exec(select(SoundDevice).where(
            SoundDevice.merchant_id == merchant_id, SoundDevice.store_id == store_id,
            SoundDevice.device_key == body.device_key,
        )).first()
        latest = s.exec(select(SoundEvent.id).where(
            SoundEvent.merchant_id == merchant_id, SoundEvent.store_id == store_id,
        ).order_by(SoundEvent.id.desc()).limit(1)).first() or 0
        if device is None:
            device = SoundDevice(merchant_id=merchant_id, store_id=store_id,
                                 device_key=body.device_key, last_event_id=int(latest))
        elif int(latest) > device.last_event_id:
            # A reopened page starts at the latest event so missed notifications never
            # become surprise audio on a later login.
            device.last_event_id = int(latest)
            device.updated_at = now()
        s.add(device)
        s.commit()
        return {"device_key": device.device_key, "cursor": device.last_event_id,
                "sound_default": "MUTED"}


@router.get("/api/merchant/sound/events")
def list_sound_events(device_key: str, limit: int = 50):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    limit = max(1, min(limit, 100))
    with session() as s:
        device = s.exec(select(SoundDevice).where(
            SoundDevice.merchant_id == merchant_id, SoundDevice.store_id == store_id,
            SoundDevice.device_key == device_key,
        )).first()
        if device is None:
            raise HTTPException(404, "Sound device is not registered for this store")
        rows = s.exec(select(SoundEvent).where(
            SoundEvent.merchant_id == merchant_id, SoundEvent.store_id == store_id,
            SoundEvent.id > device.last_event_id,
        ).order_by(SoundEvent.id).limit(limit)).all()
        return {"events": [{
            "id": row.id, "payment_id": row.payment_id, "source_type": row.source_type,
            "source_id": row.source_id, "provider_order_id": row.provider_order_id,
            "provider_transaction_id": row.provider_transaction_id,
            "amount_paise": row.amount_paise, "currency": row.currency,
            "verified_at": row.verified_at.isoformat(),
        } for row in rows], "cursor": device.last_event_id}


@router.post("/api/merchant/sound/events/ack")
def acknowledge_sound_events(body: SoundEventAck):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        device = s.exec(select(SoundDevice).where(
            SoundDevice.merchant_id == merchant_id, SoundDevice.store_id == store_id,
            SoundDevice.device_key == body.device_key,
        )).first()
        if device is None:
            raise HTTPException(404, "Sound device is not registered for this store")
        rows = s.exec(select(SoundEvent.id).where(
            SoundEvent.merchant_id == merchant_id, SoundEvent.store_id == store_id,
            SoundEvent.id.in_(body.event_ids),
        )).all()
        if rows:
            device.last_event_id = max(device.last_event_id, max(int(row) for row in rows))
            device.updated_at = now()
            s.add(device)
            s.commit()
        return {"acknowledged_through": device.last_event_id}


class StaffCreateRequest(BaseModel):
    username: str = Field(min_length=3, max_length=120)
    password: str = Field(min_length=14, max_length=1024)
    role: str = Field(default="STAFF", max_length=20)


class StaffUpdateRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = Field(default=None, max_length=20)


@router.get("/api/merchant/staff")
def list_staff():
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    return {"staff": auth.list_store_members(merchant_id, store_id)}


@router.post("/api/merchant/staff", status_code=201)
def add_staff(body: StaffCreateRequest):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    identity = current_identity()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    try:
        user, membership = auth.create_staff_membership(
            username=body.username,
            password=body.password,
            merchant_id=merchant_id,
            store_id=store_id,
            role=body.role,
            actor_id=identity.user_id if identity else "",
        )
    except ValueError as exc:
        msg = str(exc)
        if "already a member" in msg or "already in use" in msg:
            raise HTTPException(409, msg) from exc
        raise HTTPException(400, msg) from exc

    return {
        "membership_id": membership.id,
        "user_id": user.id,
        "username": user.username,
        "role": membership.role,
        "is_active": membership.is_active,
        "created_at": membership.created_at.isoformat(),
    }


@router.patch("/api/merchant/staff/{membership_id}")
def update_staff(membership_id: str, body: StaffUpdateRequest):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    identity = current_identity()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    try:
        membership = auth.update_store_membership(
            membership_id=membership_id,
            merchant_id=merchant_id,
            store_id=store_id,
            is_active=body.is_active,
            role=body.role,
            actor_id=identity.user_id if identity else "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return {
        "membership_id": membership.id,
        "user_id": membership.user_id,
        "role": membership.role,
        "is_active": membership.is_active,
    }


@router.get("/api/merchant/bills/{bill_id}/receipt", response_class=HTMLResponse)
def get_bill_receipt(bill_id: str):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        bill = s.exec(select(billing.Bill).where(
            billing.Bill.id == bill_id, billing.Bill.merchant_id == merchant_id,
            billing.Bill.store_id == store_id,
        )).first()
        if not bill:
            raise HTTPException(404, "Bill not found")
        store = s.get(Store, store_id)
        store_name = store.name if store else "Store"
        lines = s.exec(select(billing.BillLine).where(
            billing.BillLine.bill_id == bill.id,
            billing.BillLine.merchant_id == merchant_id,
            billing.BillLine.store_id == store_id,
        ).order_by(billing.BillLine.created_at)).all()

        items_html = "".join(f"""
            <tr>
                <td style="padding:6px 0;">{line.product_name}<br><small style="color:#666">{line.quantity} {line.unit} × ₹{line.unit_price_paise/100:.2f}</small></td>
                <td style="text-align:right;vertical-align:top;padding:6px 0;">₹{line.line_total_paise/100:.2f}</td>
            </tr>
        """ for line in lines)

        wa_text = f"Receipt from {store_name}\nBill: {bill.bill_number}\nTotal: ₹{bill.total_paise/100:.2f}\nStatus: {bill.payment_state}"
        wa_link = f"https://wa.me/{bill.customer_phone}?text={quote(wa_text)}" if bill.customer_phone else ""

        return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Receipt - {bill.bill_number}</title>
<style>
  body {{ font-family: monospace, system-ui, sans-serif; background: #fafafa; margin: 0; padding: 16px; color: #111; }}
  .receipt {{ max-width: 380px; margin: 0 auto; background: #fff; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }}
  .header {{ text-align: center; border-bottom: 1px dashed #999; padding-bottom: 12px; margin-bottom: 12px; }}
  .header h2 {{ margin: 0 0 4px 0; font-size: 1.3rem; }}
  .header p {{ margin: 2px 0; font-size: 0.85rem; color: #555; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.9rem; }}
  .totals {{ border-top: 1px dashed #999; margin-top: 12px; padding-top: 8px; font-size: 0.95rem; }}
  .totals-row {{ display: flex; justify-content: space-between; margin: 4px 0; }}
  .total-bold {{ font-weight: bold; font-size: 1.1rem; border-top: 1px solid #111; padding-top: 6px; margin-top: 6px; }}
  .footer {{ text-align: center; margin-top: 16px; font-size: 0.8rem; color: #666; border-top: 1px dashed #999; padding-top: 10px; }}
  .actions {{ max-width: 380px; margin: 16px auto; display: flex; gap: 8px; }}
  .btn {{ flex: 1; padding: 10px; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; text-align: center; text-decoration: none; font-size: 0.9rem; }}
  .btn-print {{ background: #0f172a; color: #fff; }}
  .btn-wa {{ background: #25d366; color: #fff; }}
  @media print {{
    body {{ background: #fff; padding: 0; }}
    .receipt {{ border: none; box-shadow: none; padding: 0; max-width: 100%; }}
    .actions {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="receipt">
  <div class="header">
    <h2>{store_name}</h2>
    <p>Bill: {bill.bill_number}</p>
    <p>Date: {bill.created_at.strftime("%d/%m/%Y %H:%M")}</p>
    {"<p>Customer: " + bill.customer_name + (" (" + bill.customer_phone + ")" if bill.customer_phone else "") + "</p>" if bill.customer_name else ""}
  </div>
  <table>
    <tbody>
      {items_html}
    </tbody>
  </table>
  <div class="totals">
    <div class="totals-row"><span>Subtotal:</span><span>₹{bill.subtotal_paise/100:.2f}</span></div>
    {f'<div class="totals-row"><span>Discount:</span><span>-₹{bill.discount_paise/100:.2f}</span></div>' if bill.discount_paise else ''}
    {f'<div class="totals-row"><span>Tax:</span><span>+₹{bill.tax_paise/100:.2f}</span></div>' if bill.tax_paise else ''}
    <div class="totals-row total-bold"><span>Total:</span><span>₹{bill.total_paise/100:.2f}</span></div>
    <div class="totals-row" style="margin-top:6px;font-size:0.85rem;color:#444;">
      <span>Payment State:</span><span>{bill.payment_state}</span>
    </div>
  </div>
  <div class="footer">
    <p>Thank you for shopping with us!</p>
    <p>Powered by Wapas Merchant OS</p>
  </div>
</div>
<div class="actions">
  <button class="btn btn-print" onclick="window.print()">Print Receipt</button>
  {f'<a class="btn btn-wa" href="{wa_link}" target="_blank" rel="noopener">Share WhatsApp</a>' if wa_link else ''}
</div>
</body>
</html>"""


@router.get("/api/merchant/khata/aging")
def get_khata_aging():
    merchant_id, store_id = current_merchant_id(), current_store_id()
    identity = current_identity()
    if identity and identity.role != "OWNER":
        raise HTTPException(403, "Khata aging analysis requires OWNER role")
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        return khata.calculate_aging(s, merchant_id=merchant_id, store_id=store_id)


@router.get("/api/merchant/khata/accounts/{account_id}/statement.csv")
def export_khata_statement_csv(account_id: str):
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        try:
            account, customer, entries, balance = khata.account_history(
                s, merchant_id=merchant_id, store_id=store_id, account_id=account_id,
            )
        except khata.KhataError as exc:
            raise HTTPException(404, str(exc)) from exc
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Entry ID", "Type", "Basis", "Payment Method", "Debit (INR)", "Credit (INR)", "Note"])
        for e in entries:
            debit = f"{e.delta_paise/100:.2f}" if e.delta_paise > 0 else ""
            credit = f"{abs(e.delta_paise)/100:.2f}" if e.delta_paise < 0 else ""
            writer.writerow([
                e.created_at.isoformat(), e.id, e.entry_type, e.recording_basis,
                e.payment_method, debit, credit, e.note
            ])
        filename = f"statement_{customer.phone or account_id}.csv"
        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/api/merchant/reports/sales.csv")
def export_sales_csv():
    merchant_id, store_id = current_merchant_id(), current_store_id()
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        bills = s.exec(select(billing.Bill).where(
            billing.Bill.merchant_id == merchant_id,
            billing.Bill.store_id == store_id,
        ).order_by(billing.Bill.created_at.desc()).limit(1000)).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Bill Number", "Created At", "State", "Payment State", "Customer Name", "Customer Phone", "Subtotal (INR)", "Discount (INR)", "Tax (INR)", "Total (INR)"])
        for b in bills:
            writer.writerow([
                b.bill_number, b.created_at.isoformat(), b.state, b.payment_state,
                b.customer_name, b.customer_phone,
                f"{b.subtotal_paise/100:.2f}", f"{b.discount_paise/100:.2f}",
                f"{b.tax_paise/100:.2f}", f"{b.total_paise/100:.2f}"
            ])
        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="sales_report.csv"'})


@router.get("/api/merchant/reports/audit.csv")
def export_audit_csv():
    merchant_id, store_id = current_merchant_id(), current_store_id()
    identity = current_identity()
    if identity and identity.role != "OWNER":
        raise HTTPException(403, "Audit log export requires OWNER role")
    if not merchant_id or not store_id:
        raise HTTPException(401, "A signed-in store identity is required")
    with session() as s:
        events = s.exec(select(audit.AuditEvent).where(
            audit.AuditEvent.merchant_id == merchant_id,
            audit.AuditEvent.store_id == store_id,
        ).order_by(audit.AuditEvent.created_at.desc()).limit(2000)).all()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Timestamp", "Action", "Entity Type", "Entity ID", "Actor Type", "Actor ID", "Source"])
        for e in events:
            writer.writerow([
                e.created_at.isoformat(), e.action, e.entity_type, e.entity_id,
                e.actor_type, e.actor_id, e.source
            ])
        return Response(content=output.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="audit_log.csv"'})


