"""A stand-in for Paytm with the same interface, for tests and offline demos.

Links point at our own /pay/<link_id> page, so a phone on the same network
can "pay" during the demo. Failure switches let us inject faults on stage.
"""
import threading
import uuid

from ..ports import LinkResult, PayStatus, StatusResult


class FakeGateway:
    name = "fake"

    def __init__(self, settings):
        self.base = settings.public_base_url.rstrip("/")
        self._lock = threading.Lock()
        self.links: dict[str, dict] = {}
        self.by_key: dict[str, str] = {}
        self.fail_status_calls = False   # simulate a status-API timeout
        self.fail_create_calls = False   # simulate link-creation errors
        self.create_calls = 0
        self.orders: dict[str, dict] = {}   # store checkout orders: order_id -> {amount, status, txn}

    # --- gateway interface ---------------------------------------------
    def create_link(self, *, idempotency_key, amount_paise, customer_name, customer_phone,
                    description, callback_url) -> LinkResult:
        with self._lock:
            self.create_calls += 1
            if self.fail_create_calls:
                return LinkResult(ok=False, error="gateway unavailable (injected)")
            if idempotency_key in self.by_key:  # same key -> same link, never a second one
                lid = self.by_key[idempotency_key]
                return LinkResult(ok=True, link_id=lid, short_url=self.links[lid]["url"])
            lid = "LNK" + uuid.uuid4().hex[:10].upper()
            url = f"{self.base}/pay/{lid}"
            self.links[lid] = {"amount": amount_paise, "status": PayStatus.PENDING, "txn": "",
                               "url": url, "name": customer_name, "desc": description}
            self.by_key[idempotency_key] = lid
            return LinkResult(ok=True, link_id=lid, short_url=url)

    def link_status(self, link_id) -> StatusResult:
        if self.fail_status_calls:
            return StatusResult(PayStatus.ERROR, raw={"error": "timeout (injected)"})
        link = self.links.get(link_id)
        if not link:
            return StatusResult(PayStatus.NOT_FOUND)
        return StatusResult(link["status"], txn_id=link["txn"], amount_paise=link.get("paid", link["amount"]) if link["txn"] else 0)

    def verify_callback(self, payload: dict) -> bool:
        return payload.get("CHECKSUMHASH") == "fake-ok"

    def initiate_checkout(self, *, order_id, amount_paise, cust_id, callback_url) -> dict:
        with self._lock:
            self.orders[order_id] = {"amount": amount_paise, "status": PayStatus.PENDING, "txn": ""}
        return {"ok": True, "mode": "fake", "order_id": order_id, "url": f"/fakecheckout/{order_id}"}

    def finish_checkout(self, order_id: str, success: bool) -> str:
        with self._lock:
            o = self.orders[order_id]
            o["status"] = PayStatus.SUCCESS if success else PayStatus.FAILED
            o["txn"] = "TXN" + uuid.uuid4().hex[:12].upper()
            return o["txn"]

    def order_status(self, order_id: str) -> StatusResult:
        if self.fail_status_calls:
            return StatusResult(PayStatus.ERROR, raw={"error": "timeout (injected)"})
        o = self.orders.get(order_id)
        if not o:
            return StatusResult(PayStatus.NOT_FOUND)
        return StatusResult(o["status"], txn_id=o["txn"], amount_paise=o["amount"])

    # --- demo controls ---------------------------------------------------
    def reset(self) -> None:
        with self._lock:
            self.links.clear()
            self.by_key.clear()
            self.orders.clear()
            self.fail_status_calls = self.fail_create_calls = False
            self.create_calls = 0

    def pay(self, link_id: str, amount_paise: int | None = None) -> bool:
        """amount_paise lets the demo inject a verification mismatch (Paytm reporting a different amount)."""
        with self._lock:
            link = self.links.get(link_id)
            if not link or link["status"] == PayStatus.SUCCESS:
                return False
            link["status"] = PayStatus.SUCCESS
            link["txn"] = "TXN" + uuid.uuid4().hex[:12].upper()
            link["paid"] = amount_paise if amount_paise is not None else link["amount"]
            return True

    def callback_payload(self, link_id: str) -> dict:
        link = self.links[link_id]
        return {"LINKID": link_id, "STATUS": "TXN_SUCCESS" if link["status"] == PayStatus.SUCCESS else "PENDING",
                "TXNID": link["txn"], "CHECKSUMHASH": "fake-ok"}
