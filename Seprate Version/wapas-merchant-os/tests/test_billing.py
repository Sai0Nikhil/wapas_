from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.billing import BillingError, create_draft, get_bill, issue_bill, remove_line, set_line
from app.inventory import InventoryConflict, create_product
from app.billing_models import Bill, BillLine


def _product(s, *, stock="5", price=101):
    return create_product(s, merchant_id="merchant_default", store_id="store_default",
                          product_id="tea", name="Tea", unit="each", unit_price_paise=price,
                          sku="TEA", opening_stock=Decimal(stock))


def test_counter_uses_canonical_price_and_issues_immutable_snapshot(db):
    with db.session() as s:
        _product(s, stock="5", price=101)
        bill = create_draft(s, merchant_id="merchant_default", store_id="store_default",
                            idempotency_key="counter-draft-001")
        bill_id = bill.id
        assert create_draft(s, merchant_id="merchant_default", store_id="store_default",
                            idempotency_key="counter-draft-001").id == bill.id
        bill, line = set_line(s, merchant_id="merchant_default", store_id="store_default",
                              bill_id=bill.id, product_id="tea", quantity="1.5")
        assert line.unit_price_paise == 101 and line.line_total_paise == 152
        assert bill.total_paise == 152

        from app.merchant_os_models import Product
        saved = s.get(Product, "tea")
        saved.unit_price_paise = 202
        s.add(saved)
        s.flush()

        issued = issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id)
        assert issued.state == "ISSUED" and issued.total_paise == 303 and issued.revision == 2
        issued, lines = get_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id)
        assert lines[0].unit_price_paise == 202 and lines[0].line_total_paise == 303
        assert issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id).id == bill.id
        with pytest.raises(BillingError, match="only a draft"):
            set_line(s, merchant_id="merchant_default", store_id="store_default",
                     bill_id=bill.id, product_id="tea", quantity="2")
        s.commit()
        lines[0].quantity = Decimal("2")
        s.add(lines[0])
        with pytest.raises(IntegrityError, match="issued bill lines are immutable"):
            s.flush()
        s.rollback()

    with db.session() as s:
        persisted = s.get(Bill, bill_id)
        assert persisted.state == "ISSUED" and persisted.total_paise == 303
        assert s.exec(select(BillLine).where(BillLine.bill_id == bill_id)).one().line_total_paise == 303


def test_counter_checks_stock_at_edit_and_issue_and_can_remove_draft_lines(db):
    with db.session() as s:
        _product(s, stock="1", price=500)
        bill = create_draft(s, merchant_id="merchant_default", store_id="store_default")
        with pytest.raises(InventoryConflict, match="insufficient"):
            set_line(s, merchant_id="merchant_default", store_id="store_default",
                     bill_id=bill.id, product_id="tea", quantity="2")
        bill, line = set_line(s, merchant_id="merchant_default", store_id="store_default",
                              bill_id=bill.id, product_id="tea", quantity="1")
        assert bill.total_paise == 500
        bill = remove_line(s, merchant_id="merchant_default", store_id="store_default",
                           bill_id=bill.id, line_id=line.id)
        assert bill.total_paise == 0
        with pytest.raises(BillingError, match="at least one"):
            issue_bill(s, merchant_id="merchant_default", store_id="store_default", bill_id=bill.id)
        s.rollback()
