"""Seeds demo accounts, Kirana catalogue items, Khata ledgers, and recovery cases."""
import sys
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from sqlmodel import select

from app.db import session, init_db
from app.models import Merchant, Store, Customer, Payment
from app.auth_models import User, MerchantMembership
from app.auth import create_user_membership
from app import inventory, khata, seed

def seed_all():
    init_db()
    
    # 1. Users
    with session() as s:
        existing_owner = s.exec(select(User).where(User.username == "admin")).first()
        if not existing_owner:
            print("Creating demo owner: admin / password12345678")
            user, mem = create_user_membership(
                username="admin",
                password="password12345678",
                merchant_id="merchant_default",
                store_id="store_default",
                role="OWNER",
            )
            s.commit()
        else:
            print("Owner user 'admin' already exists")

        existing_staff = s.exec(select(User).where(User.username == "staff")).first()
        if not existing_staff:
            print("Creating demo staff: staff / password12345678")
            user, mem = create_user_membership(
                username="staff",
                password="password12345678",
                merchant_id="merchant_default",
                store_id="store_default",
                role="STAFF",
            )
            s.commit()
        else:
            print("Staff user 'staff' already exists")

    # 2. Inventory Products
    products_to_seed = [
        ("prod_atta_5k", "Aashirvaad Shudh Chakki Atta 5kg", "kg", 24500, "8901030000001", Decimal("45"), Decimal("10")),
        ("prod_salt_1k", "Tata Salt Vacuum Evaporated 1kg", "packet", 2800, "8901030000002", Decimal("120"), Decimal("20")),
        ("prod_oil_1l", "Fortune Sunlite Sunflower Oil 1L", "litre", 14500, "8901030000003", Decimal("30"), Decimal("8")),
        ("prod_maggi_70g", "Maggi 2-Minute Noodles Masala 70g", "packet", 1400, "8901030000004", Decimal("200"), Decimal("30")),
        ("prod_butter_500g", "Amul Butter Pasteurized 500g", "pack", 27500, "8901030000005", Decimal("18"), Decimal("5")),
        ("prod_parleg_800g", "Parle-G Original Glucose Biscuits 800g", "pack", 8000, "8901030000006", Decimal("50"), Decimal("12")),
        ("prod_rice_5k", "India Gate Basmati Rice Feast 5kg", "kg", 46000, "8901030000007", Decimal("25"), Decimal("5")),
        ("prod_surf_1k", "Surf Excel Easy Wash Detergent 1kg", "kg", 14000, "8901030000008", Decimal("40"), Decimal("10")),
        ("prod_soap_125g", "Dettol Original Bathing Soap 125g", "bar", 5500, "8901030000009", Decimal("60"), Decimal("15")),
        ("prod_tea_500g", "Tata Tea Premium Desh Ki Chai 500g", "packet", 29000, "8901030000010", Decimal("35"), Decimal("10")),
        ("prod_mirch_100g", "MDH Deggi Mirch Powder 100g", "box", 9200, "8901030000011", Decimal("15"), Decimal("5")),
        ("prod_bhujia_400g", "Haldiram's Nagpur Bhujia Sev 400g", "pack", 11500, "8901030000012", Decimal("22"), Decimal("6")),
    ]

    with session() as s:
        for pid, name, unit, price, barcode, stock, threshold in products_to_seed:
            try:
                inventory.create_product(
                    s,
                    merchant_id="merchant_default",
                    store_id="store_default",
                    product_id=pid,
                    name=name,
                    unit=unit,
                    unit_price_paise=price,
                    barcode=barcode,
                    sku=pid,
                    opening_stock=stock,
                    low_stock_threshold=threshold,
                )
                print(f"Created product: {name}")
            except inventory.InventoryConflict:
                pass
            except Exception as e:
                print(f"Product {name} note: {e}")
        s.commit()

    # 3. Seed recovery cases if empty
    with session() as s:
        cust_count = s.exec(select(Customer)).first()
        if not cust_count:
            print("Seeding customer recovery cases...")
            seed.seed(s)
            seed.trigger_spike(s)
            s.commit()
            print("Seeded customer spike cases successfully!")

    # 4. Khata accounts
    khata_customers = [
        ("cust_ramesh", "Ramesh Kumar", "9876543210", 345000),
        ("cust_priya", "Priya Sharma", "9876543211", 120000),
        ("cust_suresh", "Suresh Patel", "9876543212", 85000),
        ("cust_anita", "Anita Reddy", "9876543213", 210000),
        ("cust_rajesh", "Rajesh Verma", "9876543214", 50000),
    ]

    with session() as s:
        for cid, name, phone, balance_paise in khata_customers:
            cust = s.get(Customer, cid)
            if not cust:
                cust = Customer(id=cid, name=name, phone=phone, language="hi-IN")
                s.add(cust)
                s.flush()
            
            # create or get khata account
            try:
                account = khata._customer_account(s, merchant_id="merchant_default", store_id="store_default", phone=phone, name=name)
                # add credit entry if empty
                bal = khata.balance_paise(s, merchant_id="merchant_default", store_id="store_default", account_id=account.id)
                if bal == 0 and balance_paise > 0:
                    entry = khata.KhataLedgerEntry(
                        merchant_id="merchant_default",
                        store_id="store_default",
                        account_id=account.id,
                        entry_type="CREDIT_GIVEN",
                        delta_paise=balance_paise,
                        source_type="manual_credit",
                        source_id=f"init_{cid}",
                        idempotency_key=f"init_khata_{cid}",
                        note="Opening Khata balance",
                        recording_basis="MERCHANT_SELECTED_CREDIT",
                    )
                    s.add(entry)
                    account.balance_paise = balance_paise
                    s.add(account)
                    print(f"Initialized Khata for {name}: ₹{balance_paise // 100}")
            except Exception as e:
                print(f"Khata init for {name}: {e}")
        s.commit()

    print("Demo data seeding completed successfully!")

if __name__ == "__main__":
    seed_all()
