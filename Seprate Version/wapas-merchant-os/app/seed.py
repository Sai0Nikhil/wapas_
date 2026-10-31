"""Synthetic merchant data for Wapas Store, Bengaluru.

The transaction stream is simulated (a hackathon cannot see a real merchant's
traffic). Recovery actions and verification go through the gateway: the fake
one offline, Paytm's test environment when GATEWAY=paytm.
"""
import random
from datetime import datetime, timedelta, timezone

from sqlmodel import delete, select

from . import detect
from .khata_models import KhataAccount, KhataLedgerEntry
from .models import (ActionRecord, Case, Customer, Decision, Event, Message, Outcome, Payment,
                     PolicyResult)
from .ports import CaseState
from .timeline import log_event

BANKS = ["Bank A", "Bank B", "Bank C", "Bank D"]
FIRST = {
    "hi": ["Amit", "Neha", "Rohit", "Pooja", "Vikas", "Sunita", "Rajesh", "Kavita", "Manish", "Ritu", "Sanjay", "Anita"],
    "kn": ["Prakash", "Shwetha", "Naveen", "Kavya", "Girish", "Rashmi", "Mahesh", "Divya", "Harish", "Pavithra"],
    "ta": ["Senthil", "Priya", "Murugan", "Divya", "Arjun", "Revathi", "Bala", "Kaviya", "Vijay", "Nithya"],
    "te": ["Srinivas", "Swathi", "Venkat", "Bhavana", "Ramesh", "Sravani", "Kiran", "Madhavi", "Naresh", "Keerthi"],
    "en": ["Rohan", "Aisha", "Neil", "Tara", "Kabir", "Maya"],
}
LAST = {"hi": ["Sharma", "Verma", "Gupta", "Singh", "Agarwal", "Mishra"],
        "kn": ["Gowda", "Rao", "Hegde", "Shetty", "Murthy"],
        "ta": ["Iyer", "Pillai", "Subramanian", "Raman", "Krishnan"],
        "te": ["Reddy", "Naidu", "Rao", "Chowdary", "Varma"],
        "en": ["D'Souza", "Menon", "Kapoor", "Fernandes"]}
LANG_MIX = [("hi", 35), ("kn", 25), ("ta", 15), ("te", 15), ("en", 10)]

# The 14 failed payments of the live incident (matches the deck, slide 5 and 6).
CAST = [
    # order, name, lang, amount_inr, on_time, late, flags
    ("A118", "Rahul Sharma", "hi", 2340, 11, 0, {}),
    ("A121", "Priya Traders", "hi", 8400, 11, 0, {"vip": True}),
    ("A124", "Deepak Verma", "hi", 6900, 6, 1, {}),
    ("A127", "Manjunath Rao", "kn", 1780, 7, 0, {}),
    ("A129", "Karthik Subramanian", "ta", 1250, 5, 0, {}),
    ("A131", "Lakshmi Naidu", "te", 860, 9, 0, {}),
    ("A133", "Anjali Gupta", "hi", 3150, 4, 0, {}),
    ("A135", "Suresh Gowda", "kn", 2499, 8, 1, {}),
    ("A137", "Meena Krishnan", "ta", 1990, 3, 0, {}),
    ("A139", "Ravi Teja", "te", 4200, 6, 0, {}),
    ("A141", "Imran Khan", "hi", 1540, 3, 1, {}),
    ("A143", "Arun Kumar", "ta", 1120, 5, 0, {"opted_out": True}),
    ("A145", "Sneha Iyer", "en", 640, 2, 0, {"opted_out": True}),
    ("A147", "Kiran Reddy", "te", 3050, 6, 0, {"duplicate": True}),
]


def _now():
    return datetime.now(timezone.utc)


def _pick_lang(rng):
    r = rng.randint(1, 100)
    acc = 0
    for lang, w in LANG_MIX:
        acc += w
        if r <= acc:
            return lang
    return "en"


def reset(s) -> None:
    for model in (Message, Outcome, ActionRecord, PolicyResult, Decision, Case, Event, Payment, Customer, KhataLedgerEntry, KhataAccount):
        s.exec(delete(model))
    s.commit()
    detect.clear_recovery()


def seed(s, n_customers: int = 200, seed_value: int = 7) -> None:
    """Customers plus 7 days of normal traffic (about 2% failures on every bank)."""
    rng = random.Random(seed_value)
    now = _now()
    for i in range(n_customers):
        lang = _pick_lang(rng)
        name = f"{rng.choice(FIRST[lang])} {rng.choice(LAST[lang])}"
        on_time = rng.randint(0, 14)
        late = rng.choice([0, 0, 0, 1, 1, 2, 4])
        s.add(Customer(id=f"cu{i:03d}", name=name, phone=f"9{rng.randint(100000000, 999999999)}",
                       language=lang, on_time_count=on_time, late_count=late))
    for order, name, lang, amt, on_time, late, flags in CAST:
        s.add(Customer(id=f"cast_{order}", name=name, phone=f"98{rng.randint(10000000, 99999999)}",
                       language=lang, on_time_count=on_time, late_count=late,
                       opted_out=flags.get("opted_out", False), vip=flags.get("vip", False)))

    # Seed 5 standard Kirana Khata accounts with active customer debt
    khata_customers = [
        ("cust_ramesh", "Ramesh Kumar", "9876543220", 345000),
        ("cust_priya", "Priya Sharma", "9876543221", 120000),
        ("cust_suresh", "Suresh Patel", "9876543222", 85000),
        ("cust_anita", "Anita Reddy", "9876543223", 210000),
        ("cust_rajesh", "Rajesh Verma", "9876543224", 50000),
    ]
    for cid, name, phone, balance_paise in khata_customers:
        cust = s.get(Customer, cid)
        if not cust:
            cust = Customer(id=cid, merchant_id="merchant_default", name=name, phone=phone, language="hi")
            s.add(cust)
            s.flush()
        else:
            cust.name = name
            cust.phone = phone
            s.add(cust)
        acc = s.exec(select(KhataAccount).where(
            KhataAccount.merchant_id == "merchant_default",
            KhataAccount.store_id == "store_default",
            KhataAccount.customer_id == cid,
        )).first()
        if not acc:
            acc = KhataAccount(id="khata_" + cid, merchant_id="merchant_default", store_id="store_default",
                                customer_id=cid, balance_paise=balance_paise)
            s.add(acc)
            s.flush()
            entry = KhataLedgerEntry(
                merchant_id="merchant_default", store_id="store_default",
                account_id=acc.id, entry_type="CREDIT_GIVEN", delta_paise=balance_paise,
                source_type="manual_credit", source_id=f"init_{cid}", idempotency_key=f"init_khata_{cid}",
                note="Opening Khata balance", recording_basis="MERCHANT_SELECTED_CREDIT",
            )
            s.add(entry)
        else:
            acc.balance_paise = balance_paise
            s.add(acc)
    s.commit()
    ids = [f"cu{i:03d}" for i in range(n_customers)] + [f"cast_{c[0]}" for c in CAST]
    k = 0
    for day in range(7, 0, -1):
        for _ in range(90):
            k += 1
            t = now - timedelta(days=day, minutes=rng.randint(0, 900))
            failed = rng.random() < 0.02
            s.add(Payment(id=f"h{k:05d}", order_id=f"H{k:05d}", customer_id=rng.choice(ids),
                          amount_paise=rng.randint(300, 9000) * 100, bank=rng.choice(BANKS),
                          status="FAILED" if failed else "SUCCESS",
                          failure_code=rng.choice(["INSUFFICIENT_FUNDS", "WRONG_PIN", "BANK_TIMEOUT"]) if failed else "",
                          created_at=t))
    s.commit()
    log_event(s, "seed", f"Seeded {len(ids)} customers and {k} payments over 7 days")
    s.commit()


def trigger_spike(s, seed_value: int = 11) -> list[str]:
    """Bank A starts failing: 14 of 20 payments fail within 15 minutes. Opens 14 cases."""
    rng = random.Random(seed_value)
    now = _now()
    detect.clear_recovery("Bank A")
    case_ids = []
    ok_customers = [c.id for c in s.exec(select(Customer).where(Customer.id.startswith("cu"))).all()]
    for j in range(6):  # a few payments still succeed
        s.add(Payment(id=f"sp_ok{j}_{int(now.timestamp())}", order_id=f"S{j}{int(now.timestamp()) % 100000}",
                      customer_id=rng.choice(ok_customers), amount_paise=rng.randint(500, 4000) * 100,
                      bank="Bank A", status="SUCCESS", created_at=now - timedelta(minutes=rng.randint(1, 14))))
    for idx, (order, name, lang, amt, on_time, late, flags) in enumerate(CAST):
        pid = f"p_{order}_{int(now.timestamp())}"
        created = now - timedelta(minutes=14 - idx)
        if flags.get("duplicate"):
            # The same order already failed 20 minutes ago and got a link then.
            prior_pid = pid + "_prior"
            s.add(Payment(id=prior_pid, order_id=order, customer_id=f"cast_{order}", amount_paise=amt * 100,
                          bank="Bank C", status="FAILED", failure_code="BANK_TIMEOUT", created_at=now - timedelta(minutes=20)))
            prior = Case(id=f"c_{order}_prior", payment_id=prior_pid, batch="earlier", diagnosis="bank_side",
                         confidence=0.72, state=CaseState.SENT.value, messages_sent=1,
                         opened_at=now - timedelta(minutes=20))
            s.add(prior)
            s.add(ActionRecord(case_id=prior.id, kind="payment_link", idempotency_key=f"{prior.id}:link",
                               link_id="LNKEARLIER01", short_url="(sent earlier)", state="SENT",
                               sent_at=now - timedelta(minutes=19)))
        s.add(Payment(id=pid, order_id=order, customer_id=f"cast_{order}", amount_paise=amt * 100, bank="Bank A",
                      status="FAILED", failure_code="BANK_TIMEOUT", created_at=created))
        cid = f"c_{order}"
        old = s.get(Case, cid)
        if old:
            cid = f"c_{order}_{int(now.timestamp())}"
        s.add(Case(id=cid, payment_id=pid, batch="live", opened_at=created))
        case_ids.append(cid)
    s.commit()
    log_event(s, "signal", "Bank A: 14 of 20 UPI payments failed in the last 15 minutes")
    s.commit()
    return case_ids
