"""Merchant-scoped, transactional catalogue and stock operations."""
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from .models import Merchant, Store
from .merchant_os_models import InventoryBalance, InventoryMovement, InventoryReservation, Product, now


class InventoryError(Exception):
    """Base class for safe inventory-domain failures."""


class InventoryNotFound(InventoryError):
    """The requested record is not present in the caller's merchant/store scope."""


class InventoryConflict(InventoryError):
    """The requested operation conflicts with stock, identity, or terminal state."""


class InvalidInventoryOperation(InventoryError):
    """The operation has invalid quantity, price, or source information."""


def _decimal(value, *, allow_zero: bool = False) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidInventoryOperation("quantity must be a decimal number") from exc
    if not amount.is_finite() or (amount < 0 if allow_zero else amount <= 0):
        raise InvalidInventoryOperation("quantity must be positive")
    if amount != amount.quantize(Decimal("0.001")):
        raise InvalidInventoryOperation("quantity supports at most three decimal places")
    return amount


def _require_scope(session: Session, merchant_id: str, store_id: str) -> None:
    merchant = session.get(Merchant, merchant_id)
    store = session.get(Store, store_id)
    if merchant is None or store is None or store.merchant_id != merchant_id:
        raise InventoryNotFound("merchant or store not found")


def _get_product(session: Session, *, merchant_id: str, store_id: str, product_id: str,
                 active_only: bool = False) -> Product:
    query = select(Product).where(
        Product.id == product_id,
        Product.merchant_id == merchant_id,
        Product.store_id == store_id,
    )
    if active_only:
        query = query.where(Product.status == "ACTIVE")
    product = session.exec(query).first()
    if product is None:
        raise InventoryNotFound("product not found")
    return product


def _get_balance(session: Session, *, merchant_id: str, store_id: str,
                  product_id: str) -> InventoryBalance:
    balance = session.exec(select(InventoryBalance).where(
        InventoryBalance.merchant_id == merchant_id,
        InventoryBalance.store_id == store_id,
        InventoryBalance.product_id == product_id,
    )).first()
    if balance is None:
        raise InventoryNotFound("inventory balance not found")
    return balance


def _refresh_balance(session: Session, balance: InventoryBalance) -> InventoryBalance:
    session.refresh(balance)
    return balance


def _movement_for_key(session: Session, idempotency_key: str | None) -> InventoryMovement | None:
    if not idempotency_key:
        return None
    return session.exec(select(InventoryMovement).where(
        InventoryMovement.idempotency_key == idempotency_key,
    )).first()


def _assert_same_movement(existing: InventoryMovement, *, merchant_id: str, store_id: str,
                          product_id: str, kind: str, quantity: Decimal, on_hand_delta: Decimal,
                          reserved_delta: Decimal, source_ref: str) -> None:
    if (existing.merchant_id, existing.store_id, existing.product_id, existing.kind,
            existing.quantity, existing.on_hand_delta, existing.reserved_delta, existing.source_ref) != (
            merchant_id, store_id, product_id, kind, quantity, on_hand_delta, reserved_delta, source_ref):
        raise InventoryConflict("idempotency key was already used for a different inventory action")


def _add_movement(session: Session, *, merchant_id: str, store_id: str, product_id: str,
                  kind: str, quantity: Decimal, on_hand_delta: Decimal, reserved_delta: Decimal,
                  source: str, source_ref: str, reason: str = "",
                  idempotency_key: str | None = None) -> InventoryMovement:
    movement = InventoryMovement(
        merchant_id=merchant_id, store_id=store_id, product_id=product_id, kind=kind,
        quantity=quantity, on_hand_delta=on_hand_delta, reserved_delta=reserved_delta,
        source=source, source_ref=source_ref, reason=reason,
        idempotency_key=idempotency_key,
    )
    session.add(movement)
    session.flush()
    return movement


def create_product(session: Session, *, merchant_id: str, store_id: str, product_id: str,
                   name: str, unit: str, unit_price_paise: int, barcode: str = "", sku: str = "",
                   opening_stock: Decimal = Decimal("0"),
                   low_stock_threshold: Decimal = Decimal("0")) -> Product:
    """Create a scoped product and its initial balance; optional opening stock is audited."""
    _require_scope(session, merchant_id, store_id)
    opening = _decimal(opening_stock, allow_zero=True)
    threshold = _decimal(low_stock_threshold, allow_zero=True)
    product_id = product_id.strip()
    name, unit, barcode, sku = name.strip(), unit.strip(), barcode.strip(), sku.strip() or product_id
    if not product_id or not name or not unit:
        raise InvalidInventoryOperation("product ID, name, and unit are required")
    if not isinstance(unit_price_paise, int) or unit_price_paise < 0:
        raise InvalidInventoryOperation("unit price must be a nonnegative integer in paise")

    try:
        with session.begin_nested():
            product = Product(
                id=product_id, merchant_id=merchant_id, store_id=store_id,
                name=name, unit=unit, unit_price_paise=unit_price_paise,
                barcode=barcode, sku=sku, low_stock_threshold=threshold,
            )
            session.add(product)
            session.flush()
            balance = InventoryBalance(
                merchant_id=merchant_id, store_id=store_id, product_id=product_id,
                on_hand=opening, reserved=Decimal("0"), low_stock_threshold=threshold,
            )
            session.add(balance)
            if opening:
                _add_movement(
                    session, merchant_id=merchant_id, store_id=store_id, product_id=product_id,
                    kind="opening_stock", quantity=opening, on_hand_delta=opening,
                    reserved_delta=Decimal("0"), source="opening_stock", source_ref=product_id,
                    idempotency_key=f"opening:{merchant_id}:{store_id}:{product_id}",
                )
        return product
    except IntegrityError as exc:
        raise InventoryConflict("product ID, SKU, or barcode already exists in this store") from exc


def list_products(session: Session, *, merchant_id: str, store_id: str,
                  active_only: bool = True) -> list[tuple[Product, InventoryBalance]]:
    """Return products and their durable balances, always scoped to one merchant/store."""
    _require_scope(session, merchant_id, store_id)
    query = select(Product, InventoryBalance).join(
        InventoryBalance,
        (InventoryBalance.product_id == Product.id)
        & (InventoryBalance.merchant_id == Product.merchant_id)
        & (InventoryBalance.store_id == Product.store_id),
    ).where(Product.merchant_id == merchant_id, Product.store_id == store_id)
    if active_only:
        query = query.where(Product.status == "ACTIVE")
    return list(session.exec(query.order_by(Product.name, Product.id)).all())


def list_movements(session: Session, *, merchant_id: str, store_id: str,
                   product_id: str | None = None, limit: int = 100) -> list[InventoryMovement]:
    """Return the newest owner-visible stock ledger entries within one store."""
    _require_scope(session, merchant_id, store_id)
    if not 1 <= limit <= 500:
        raise InvalidInventoryOperation("movement limit must be between 1 and 500")
    query = select(InventoryMovement).where(
        InventoryMovement.merchant_id == merchant_id,
        InventoryMovement.store_id == store_id,
    )
    if product_id:
        query = query.where(InventoryMovement.product_id == product_id)
    return list(session.exec(query.order_by(InventoryMovement.created_at.desc(),
                                           InventoryMovement.id.desc()).limit(limit)).all())


def lookup_product(session: Session, *, merchant_id: str, store_id: str,
                   product_id: str = "", barcode: str = "", sku: str = "") -> tuple[Product, InventoryBalance] | None:
    """Look up one product by ID, barcode, or SKU without revealing cross-tenant rows."""
    _require_scope(session, merchant_id, store_id)
    keys = [bool(product_id), bool(barcode), bool(sku)]
    if sum(keys) != 1:
        raise InvalidInventoryOperation("provide exactly one product ID, barcode, or SKU")
    query = select(Product).where(Product.merchant_id == merchant_id, Product.store_id == store_id)
    if product_id:
        query = query.where(Product.id == product_id)
    elif barcode:
        query = query.where(Product.barcode == barcode.strip())
    else:
        query = query.where(Product.sku == sku.strip())
    product = session.exec(query).first()
    if product is None:
        return None
    balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product.id)
    return product, balance


def adjust_stock(session: Session, *, merchant_id: str, store_id: str, product_id: str,
                 delta, kind: str, source_ref: str, reason: str = "",
                 idempotency_key: str | None = None) -> InventoryBalance:
    """Receive or adjust on-hand stock, appending one immutable movement."""
    _get_product(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
    try:
        signed_delta = Decimal(str(delta))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidInventoryOperation("stock delta must be a decimal number") from exc
    if not signed_delta.is_finite() or signed_delta == 0:
        raise InvalidInventoryOperation("stock delta must be nonzero")
    if signed_delta != signed_delta.quantize(Decimal("0.001")):
        raise InvalidInventoryOperation("quantity supports at most three decimal places")
    if kind not in {"receipt", "adjustment", "damage", "correction"}:
        raise InvalidInventoryOperation("unsupported stock adjustment kind")
    if kind == "receipt" and signed_delta < 0:
        raise InvalidInventoryOperation("a receipt must add stock")
    if kind == "damage" and signed_delta > 0:
        raise InvalidInventoryOperation("a damage movement must reduce stock")
    if not source_ref.strip():
        raise InvalidInventoryOperation("source reference is required")
    if kind in {"adjustment", "damage", "correction"} and not reason.strip():
        raise InvalidInventoryOperation("a reason is required for this stock change")

    quantity = abs(signed_delta)
    with session.begin_nested():
        existing = _movement_for_key(session, idempotency_key)
        if existing:
            _assert_same_movement(existing, merchant_id=merchant_id, store_id=store_id,
                                  product_id=product_id, kind=kind, quantity=quantity,
                                  on_hand_delta=signed_delta, reserved_delta=Decimal("0"),
                                  source_ref=source_ref)
            return _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
        balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
        result = session.exec(update(InventoryBalance).where(
            InventoryBalance.id == balance.id,
            InventoryBalance.merchant_id == merchant_id,
            InventoryBalance.store_id == store_id,
            InventoryBalance.on_hand + signed_delta >= InventoryBalance.reserved,
        ).values(on_hand=InventoryBalance.on_hand + signed_delta, updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("stock adjustment would make available stock negative")
        _add_movement(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id,
                      kind=kind, quantity=quantity, on_hand_delta=signed_delta,
                      reserved_delta=Decimal("0"), source=kind, source_ref=source_ref,
                      reason=reason.strip(), idempotency_key=idempotency_key)
        return _refresh_balance(session, balance)


def reserve_stock(session: Session, *, merchant_id: str, store_id: str, product_id: str,
                  quantity, reservation_id: str, source_ref: str, source: str = "order") -> InventoryReservation:
    """Hold available stock under a durable reservation; replaying the ID is safe."""
    amount = _decimal(quantity)
    reservation_id, source_ref, source = reservation_id.strip(), source_ref.strip(), source.strip()
    if not reservation_id or not source_ref or not source:
        raise InvalidInventoryOperation("reservation ID, source, and source reference are required")
    _get_product(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id, active_only=True)
    with session.begin_nested():
        existing_reservation = session.get(InventoryReservation, reservation_id)
        if existing_reservation:
            same = (existing_reservation.merchant_id == merchant_id
                    and existing_reservation.store_id == store_id
                    and existing_reservation.product_id == product_id
                    and existing_reservation.quantity == amount
                    and existing_reservation.source_ref == source_ref
                    and existing_reservation.source == source)
            if not same:
                raise InventoryConflict("reservation ID was already used for a different reservation")
            return existing_reservation
        balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
        result = session.exec(update(InventoryBalance).where(
            InventoryBalance.id == balance.id,
            InventoryBalance.merchant_id == merchant_id,
            InventoryBalance.store_id == store_id,
            InventoryBalance.on_hand - InventoryBalance.reserved >= amount,
        ).values(reserved=InventoryBalance.reserved + amount, updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("insufficient available stock")
        reservation = InventoryReservation(
            id=reservation_id, merchant_id=merchant_id, store_id=store_id,
            product_id=product_id, quantity=amount, source=source, source_ref=source_ref,
        )
        session.add(reservation)
        session.flush()
        _add_movement(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id,
                      kind="reserve", quantity=amount, on_hand_delta=Decimal("0"),
                      reserved_delta=amount, source=source, source_ref=source_ref,
                      idempotency_key=f"reserve:{reservation_id}")
        return reservation


def _reservation(session: Session, *, merchant_id: str, store_id: str,
                 reservation_id: str) -> InventoryReservation:
    reservation = session.exec(select(InventoryReservation).where(
        InventoryReservation.id == reservation_id,
        InventoryReservation.merchant_id == merchant_id,
        InventoryReservation.store_id == store_id,
    )).first()
    if reservation is None:
        raise InventoryNotFound("reservation not found")
    return reservation


def release_stock(session: Session, *, merchant_id: str, store_id: str,
                  reservation_id: str, source: str = "order_cancelled") -> InventoryBalance:
    """Release a HELD reservation once; a repeated release returns the same balance."""
    with session.begin_nested():
        reservation = _reservation(session, merchant_id=merchant_id, store_id=store_id,
                                   reservation_id=reservation_id)
        if reservation.state == "RELEASED":
            return _get_balance(session, merchant_id=merchant_id, store_id=store_id,
                                 product_id=reservation.product_id)
        if reservation.state != "HELD":
            raise InventoryConflict("only a held reservation can be released")
        result = session.exec(update(InventoryReservation).where(
            InventoryReservation.id == reservation.id,
            InventoryReservation.merchant_id == merchant_id,
            InventoryReservation.store_id == store_id,
            InventoryReservation.state == "HELD",
        ).values(state="RELEASED", updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("reservation is no longer held")
        balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id,
                               product_id=reservation.product_id)
        result = session.exec(update(InventoryBalance).where(
            InventoryBalance.id == balance.id,
            InventoryBalance.merchant_id == merchant_id,
            InventoryBalance.store_id == store_id,
            InventoryBalance.reserved >= reservation.quantity,
        ).values(reserved=InventoryBalance.reserved - reservation.quantity, updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("reservation balance is inconsistent")
        _add_movement(session, merchant_id=merchant_id, store_id=store_id,
                      product_id=reservation.product_id, kind="release", quantity=reservation.quantity,
                      on_hand_delta=Decimal("0"), reserved_delta=-reservation.quantity,
                      source=source, source_ref=reservation.source_ref,
                      idempotency_key=f"release:{reservation_id}")
        return _refresh_balance(session, balance)


def complete_reservation(session: Session, *, merchant_id: str, store_id: str,
                          reservation_id: str) -> InventoryBalance:
    """Consume a held reservation once, reducing both on-hand and reserved stock."""
    with session.begin_nested():
        reservation = _reservation(session, merchant_id=merchant_id, store_id=store_id,
                                   reservation_id=reservation_id)
        if reservation.state == "CONSUMED":
            return _get_balance(session, merchant_id=merchant_id, store_id=store_id,
                                 product_id=reservation.product_id)
        if reservation.state != "HELD":
            raise InventoryConflict("only a held reservation can be completed")
        result = session.exec(update(InventoryReservation).where(
            InventoryReservation.id == reservation.id,
            InventoryReservation.merchant_id == merchant_id,
            InventoryReservation.store_id == store_id,
            InventoryReservation.state == "HELD",
        ).values(state="CONSUMED", updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("reservation is no longer held")
        balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id,
                               product_id=reservation.product_id)
        result = session.exec(update(InventoryBalance).where(
            InventoryBalance.id == balance.id,
            InventoryBalance.merchant_id == merchant_id,
            InventoryBalance.store_id == store_id,
            InventoryBalance.reserved >= reservation.quantity,
            InventoryBalance.on_hand >= reservation.quantity,
        ).values(on_hand=InventoryBalance.on_hand - reservation.quantity,
                 reserved=InventoryBalance.reserved - reservation.quantity, updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("reservation balance is inconsistent")
        _add_movement(session, merchant_id=merchant_id, store_id=store_id,
                      product_id=reservation.product_id, kind="completed_sale", quantity=reservation.quantity,
                      on_hand_delta=-reservation.quantity, reserved_delta=-reservation.quantity,
                      source=reservation.source, source_ref=reservation.source_ref,
                      idempotency_key=f"consume:{reservation_id}")
        return _refresh_balance(session, balance)


def sell_stock(session: Session, *, merchant_id: str, store_id: str, product_id: str,
               quantity, source_ref: str, source: str = "counter",
               idempotency_key: str | None = None) -> InventoryBalance:
    """Record a direct sale from available stock, leaving reserved units untouched."""
    amount = _decimal(quantity)
    if not source_ref.strip() or not source.strip():
        raise InvalidInventoryOperation("sale source and source reference are required")
    _get_product(session, merchant_id=merchant_id, store_id=store_id,
                 product_id=product_id, active_only=True)
    with session.begin_nested():
        existing = _movement_for_key(session, idempotency_key)
        if existing:
            _assert_same_movement(existing, merchant_id=merchant_id, store_id=store_id,
                                  product_id=product_id, kind="sale", quantity=amount,
                                  on_hand_delta=-amount, reserved_delta=Decimal("0"),
                                  source_ref=source_ref)
            return _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
        balance = _get_balance(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id)
        result = session.exec(update(InventoryBalance).where(
            InventoryBalance.id == balance.id,
            InventoryBalance.merchant_id == merchant_id,
            InventoryBalance.store_id == store_id,
            InventoryBalance.on_hand - InventoryBalance.reserved >= amount,
        ).values(on_hand=InventoryBalance.on_hand - amount, updated_at=now()))
        if result.rowcount != 1:
            raise InventoryConflict("insufficient available stock")
        _add_movement(session, merchant_id=merchant_id, store_id=store_id, product_id=product_id,
                      kind="sale", quantity=amount, on_hand_delta=-amount,
                      reserved_delta=Decimal("0"), source=source, source_ref=source_ref,
                      idempotency_key=idempotency_key)
        return _refresh_balance(session, balance)
