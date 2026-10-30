"""python -m scripts.seed"""
from sqlmodel import Session, select

from app.db import engine, init_db
from app.models import Customer, Merchant

CUSTOMERS = [
    ("cust-rahul", "Rahul", "hi", 11, 4_500_000),
    ("cust-manjunath", "Manjunath", "kn", 8, 1_200_000),
    ("cust-karthik", "Karthik", "ta", 6, 900_000),
    ("cust-lakshmi", "Lakshmi", "te", 14, 3_000_000),
    ("cust-priya", "Priya Traders", "hi", 11, 9_000_000),
]


def main() -> None:
    init_db()
    with Session(engine) as s:
        if s.exec(select(Merchant)).first():
            print("already seeded")
            return
        m = Merchant(name="Sharma Electronics", auto_limit_paise=500_000)
        s.add(m)
        s.flush()
        for ref, name, lang, ontime, ltv in CUSTOMERS:
            s.add(Customer(merchant_id=m.id, external_ref=ref, name=name, language=lang,
                           on_time_payments=ontime, lifetime_value_paise=ltv))
        s.commit()
        print("seeded merchant + customers")


if __name__ == "__main__":
    main()
