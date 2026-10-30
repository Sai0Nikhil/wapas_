from decimal import Decimal

import pytest
from sqlmodel import select

# Import the domain tables before the shared fixture creates its schema.
from app.merchant_os_models import (InventoryBalance, InventoryMovement,
                                    InventoryReservation, Product)
from app.models import Merchant, Store
from app.inventory import (InventoryConflict, InventoryNotFound, adjust_stock,
                           complete_reservation, create_product, list_movements,
                           list_products, lookup_product, release_stock, reserve_stock, sell_stock)


def _product(session, *, product_id="tea", barcode="8901", stock="0", merchant="merchant_default",
             store="store_default", low_stock_threshold="0"):
    return create_product(session, merchant_id=merchant, store_id=store,
                          product_id=product_id, name="Tea", unit="kg", unit_price_paise=25000,
                          barcode=barcode, opening_stock=Decimal(stock),
                          low_stock_threshold=Decimal(low_stock_threshold))


def test_create_lookup_list_and_store_scoped_barcode_uniqueness(db):
    with db.session() as s:
        _product(s, low_stock_threshold="1.500")
        s.add(Merchant(id="merchant_other", name="Other Shop"))
        s.add(Store(id="store_other", merchant_id="merchant_other", name="Other Store", slug="other-store"))
        s.flush()
        # A barcode may be reused by a separate merchant, but not in this store.
        _product(s, product_id="other-tea", merchant="merchant_other", store="store_other")
        with pytest.raises(InventoryConflict):
            _product(s, product_id="tea-copy")
        found = lookup_product(s, merchant_id="merchant_default", store_id="store_default", barcode="8901")
        assert found and found[0].id == "tea" and found[0].status == "ACTIVE"
        assert found[0].low_stock_threshold == Decimal("1.500")
        assert found[1].on_hand == Decimal("0.000") and found[1].available == Decimal("0.000")
        assert lookup_product(s, merchant_id="merchant_other", store_id="store_other", barcode="8901")[0].id == "other-tea"
        rows = list_products(s, merchant_id="merchant_default", store_id="store_default")
        assert [row[0].id for row in rows] == ["tea"]
        s.commit()


def test_receipt_adjustment_sale_and_idempotent_movement(db):
    with db.session() as s:
        _product(s)
        bal = adjust_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                           delta=Decimal("5"), kind="receipt", source_ref="delivery-1", idempotency_key="receipt-1")
        assert bal.on_hand == Decimal("5.000") and bal.reserved == Decimal("0.000")
        # Replaying the same idempotency key does not apply the receipt twice.
        bal = adjust_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                           delta=Decimal("5"), kind="receipt", source_ref="delivery-1", idempotency_key="receipt-1")
        assert bal.on_hand == Decimal("5.000")
        bal = adjust_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                           delta=Decimal("-1"), kind="adjustment", source_ref="count-1", reason="Cycle count",
                           idempotency_key="count-1")
        assert bal.on_hand == Decimal("4.000")
        bal = sell_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                         quantity=Decimal("1.250"), source_ref="bill-1", idempotency_key="sale-1")
        assert bal.on_hand == Decimal("2.750")
        movements = s.exec(select(InventoryMovement).where(InventoryMovement.product_id == "tea")).all()
        assert [m.kind for m in movements] == ["receipt", "adjustment", "sale"]
        assert [m.kind for m in list_movements(s, merchant_id="merchant_default", store_id="store_default",
                                               product_id="tea")] == ["sale", "adjustment", "receipt"]
        s.commit()


def test_reserve_release_complete_and_no_oversell(db):
    with db.session() as s:
        _product(s, stock="5")
        held = reserve_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                             quantity=Decimal("3"), reservation_id="order-line-1", source_ref="order-1")
        assert held.state == "HELD"
        assert reserve_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                             quantity=Decimal("3"), reservation_id="order-line-1", source_ref="order-1").id == held.id
        with pytest.raises(InventoryConflict, match="insufficient available stock"):
            reserve_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                          quantity=Decimal("3"), reservation_id="order-line-2", source_ref="order-2")
        bal = release_stock(s, merchant_id="merchant_default", store_id="store_default",
                            reservation_id="order-line-1")
        assert bal.on_hand == Decimal("5.000") and bal.reserved == Decimal("0.000")
        # A repeated release is harmless.
        assert release_stock(s, merchant_id="merchant_default", store_id="store_default",
                             reservation_id="order-line-1").reserved == Decimal("0.000")
        reserve_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                      quantity=Decimal("2"), reservation_id="order-line-3", source_ref="order-3")
        bal = complete_reservation(s, merchant_id="merchant_default", store_id="store_default",
                                   reservation_id="order-line-3")
        assert bal.on_hand == Decimal("3.000") and bal.reserved == Decimal("0.000")
        assert complete_reservation(s, merchant_id="merchant_default", store_id="store_default",
                                    reservation_id="order-line-3").on_hand == Decimal("3.000")
        assert s.exec(select(InventoryReservation).where(InventoryReservation.id == "order-line-3")).one().state == "CONSUMED"
        s.commit()


def test_scope_checks_and_negative_stock_are_rejected(db):
    with db.session() as s:
        _product(s, stock="1")
        with pytest.raises(InventoryNotFound):
            list_products(s, merchant_id="merchant_missing", store_id="store_default")
        with pytest.raises(InventoryNotFound):
            lookup_product(s, merchant_id="merchant_default", store_id="store_missing", product_id="tea")
        assert lookup_product(s, merchant_id="merchant_default", store_id="store_default", product_id="secret-other-merchant") is None
        with pytest.raises(InventoryConflict):
            adjust_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                         delta=Decimal("-2"), kind="adjustment", source_ref="bad-count", reason="Incorrect count")
        with pytest.raises(InventoryConflict):
            sell_stock(s, merchant_id="merchant_default", store_id="store_default", product_id="tea",
                       quantity=Decimal("1.001"), source_ref="too-many")
        bal = lookup_product(s, merchant_id="merchant_default", store_id="store_default", product_id="tea")[1]
        assert bal.on_hand == Decimal("1.000") and bal.reserved == Decimal("0.000")
        s.commit()


def test_inventory_movements_are_append_only_in_sqlite(db):
    with db.session() as s:
        _product(s, stock="2")
        movement = s.exec(select(InventoryMovement).where(InventoryMovement.product_id == "tea")).one()
        movement.reason = "tampered"
        s.add(movement)
        with pytest.raises(ValueError, match="append-only"):
            s.flush()
        s.rollback()

    with db.session() as s:
        movement = s.exec(select(InventoryMovement).where(InventoryMovement.product_id == "tea")).one()
        assert movement.reason == ""
