"""Run the local Counter flow in headless Chromium against a disposable database.

Requires Playwright's Python package and an installed Chromium browser. No provider
credentials or external integrations are used. Run: python scripts/counter_browser_smoke.py
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from io import BytesIO
from pathlib import Path
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_server(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("isolated Wapas server exited before becoming ready")
        try:
            with urlopen(url + "/login", timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise TimeoutError("isolated Wapas server did not become ready")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wapas-counter-e2e-") as temp:
        database = Path(temp) / "counter-e2e.db"
        port = _free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "DATABASE_URL": "sqlite:///" + database.as_posix(),
            "WAPAS_ENV": "development", "GATEWAY": "fake", "PAYTM_LIVE_ENABLED": "false",
            "WAPAS_ALLOW_PROTECTED_DB_WRITES": "false",
            "SARVAM_API_KEY": "", "WAPAS_VISION_ENABLED": "false",
            "VISION_BASE_URL": "", "VISION_API_KEY": "", "VISION_MODEL": "",
            "LLM_BASE_URL": "", "LLM_API_KEY": "", "LLM_MODEL": "",
            "TELEGRAM_BOT_TOKEN": "", "N8N_WEBHOOK_URL": "",
            "PUBLIC_BASE_URL": base_url,
        })
        # The parent process also imports the application below to create a session.
        # Keep it on the same disposable database as the server before importing settings.
        os.environ.update(env)
        process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        parent_db = None
        try:
            _wait_for_server(base_url, process)

            # Create a disposable owner and a valid app session directly in the temporary DB.
            sys.path.insert(0, str(ROOT))
            from app import auth, db
            parent_db = db
            from app.config import get_settings
            if database.as_posix().lower() not in get_settings().database_url.lower():
                raise RuntimeError("parent app settings do not point to the disposable browser database")
            import app.main  # register the complete SQLModel metadata in this process too

            owner, membership = auth.create_user_membership(
                username="counter-browser-smoke", password=secrets.token_urlsafe(32),
                merchant_id="merchant_default", store_id="store_default", role="OWNER",
            )
            session_token, csrf_token, _expires = auth.create_session(membership.id)

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    context = browser.new_context(viewport={"width": 1280, "height": 900})
                    try:
                        context.add_cookies([
                            {"name":"wapas_session", "value":session_token, "url":base_url, "httpOnly":True, "sameSite":"Strict"},
                            {"name":"wapas_csrf", "value":csrf_token, "url":base_url, "sameSite":"Strict"},
                        ])
                        page = context.new_page()
                        page.goto(base_url + "/", wait_until="domcontentloaded")
                        if page.title() != "Wapas · Owner console":
                            raise AssertionError("authenticated console did not load")
                        page.get_by_role("button", name="Counter", exact=True).click()
                        page.locator("#counter-start").wait_for()

                        headers = {"Origin":base_url, "X-Wapas-CSRF":csrf_token}
                        created = context.request.post(base_url + "/api/merchant/catalog/products", headers=headers, data={
                            "name":"Basmati rice", "sku":"RICE-E2E", "barcode":"8900000000001",
                            "unit":"bag", "unit_price_paise":12500, "opening_stock":"10",
                        })
                        if created.status != 201:
                            raise AssertionError("disposable test product creation failed")
                        product = created.json()

                        page.locator("#counter-start").click()
                        page.wait_for_function("() => document.querySelector('#counter-state')?.textContent === 'DRAFT'")

                        # Exercise scanner-keyboard input, duplicate suppression, and later quantity aggregation.
                        code = page.locator("#counter-barcode input[name=code]")
                        code.fill("8900000000001"); code.press("Enter")
                        page.locator("#counter-lines tr").first.wait_for()
                        qty = page.locator("#counter-lines tr").first.locator("td").nth(1)
                        if float(qty.inner_text()) != 1:
                            raise AssertionError(f"first scanner-keyboard event did not add one unit: quantity={qty.inner_text()!r}; message={page.locator('#counter-barcode-msg').inner_text()!r}")
                        code.fill("8900000000001"); code.press("Enter")
                        page.wait_for_timeout(100)
                        if float(qty.inner_text()) != 1:
                            raise AssertionError("rapid duplicate scanner event was not suppressed")
                        page.wait_for_timeout(700)
                        code.fill("8900000000001"); code.press("Enter")
                        page.wait_for_function("() => Number(document.querySelector('#counter-lines tr td:nth-child(2)')?.textContent) === 2")

                        # With vision disabled, a valid Parchi upload stays a manual review task.
                        image = BytesIO()
                        Image.new("RGB", (40, 30), "white").save(image, "PNG")
                        page.locator("#counter-parchi-form input[type=file]").set_input_files({
                            "name":"parchi.png", "mimeType":"image/png", "buffer":image.getvalue(),
                        })
                        page.locator("#counter-parchi-form button[type=submit]").click()
                        page.wait_for_function("() => document.querySelector('#counter-parchi-status')?.textContent.includes('NOT CONFIGURED')")
                        if page.locator("#counter-lines tr").count() != 1:
                            raise AssertionError("unconfigured Parchi recognition mutated the draft")

                        # Manual transcription resolves to saved catalogue data through the Counter line API.
                        page.locator("#counter-parchi-text").fill("2 Basmati rice")
                        page.locator("#counter-parchi-manual").click()
                        suggestion = page.locator("#counter-parchi-results .counter-suggestion").first
                        suggestion.wait_for()
                        suggestion.locator("select").select_option(product["id"])
                        suggestion.locator("input").fill("2")
                        suggestion.get_by_role("button", name="Add reviewed line to draft").click()
                        page.wait_for_function("() => Number(document.querySelector('#counter-lines tr td:nth-child(2)')?.textContent) === 4")

                        page.set_viewport_size({"width":390, "height":844})
                        columns = page.locator(".counter-input-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns")
                        if len(columns.split()) != 1:
                            raise AssertionError("Counter input cards did not collapse to one column at 390px")
                        if page.evaluate("document.documentElement.scrollWidth > window.innerWidth"):
                            overflow = page.evaluate("""() => [...document.querySelectorAll('body *')]
                              .map(el => ({tag:el.tagName,id:el.id,cls:String(el.className).slice(0,80),
                                left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right),
                                width:el.scrollWidth,client:el.clientWidth}))
                              .filter(el => el.right > innerWidth + 1 || el.left < -1 || el.width > el.client + 1)
                              .slice(0,12)""")
                            raise AssertionError(f"Counter page has horizontal overflow at 390px: {overflow}")

                        page.on("dialog", lambda dialog: dialog.accept())
                        page.locator("#counter-issue").click()
                        page.wait_for_function("() => document.querySelector('#counter-state')?.textContent === 'ISSUED'")
                        if "NOT_RECORDED" not in page.locator("#counter-payment").inner_text():
                            raise AssertionError("issued bill incorrectly claimed a payment")

                        # Public product names are merchant-controlled. They must remain text
                        # when rendered in the token-protected customer order page.
                        payload = '<img src=x onerror="window.wapasStoredXss=1">'
                        xss_product_response = context.request.post(
                            base_url + "/api/merchant/catalog/products", headers=headers, data={
                                "name":payload, "sku":"XSS-E2E", "barcode":"8900000000002",
                                "unit":"item", "unit_price_paise":100, "opening_stock":"2",
                            },
                        )
                        if xss_product_response.status != 201:
                            raise AssertionError("could not create disposable stored-XSS regression product")
                        xss_product = xss_product_response.json()
                        shop = context.new_page()
                        shop.goto(base_url + "/s/default-store", wait_until="domcontentloaded")
                        shop.locator(f'[data-add="{xss_product["id"]}"]').click()
                        shop.locator('input[name="name"]').fill("Disposable test buyer")
                        shop.locator('input[name="phone"]').fill("9000012345")
                        shop.locator("#pay").click()
                        shop.wait_for_url("**/fakecheckout/**")
                        shop.locator('button[value="success"]').click()
                        shop.wait_for_url("**/shop/result/**")
                        shop.locator("#items li").wait_for()
                        shop.wait_for_timeout(150)
                        if shop.locator("#items img").count() or shop.evaluate("window.wapasStoredXss === 1"):
                            raise AssertionError("catalogue product name executed as HTML in the public order page")
                        if payload not in shop.locator("#items").inner_text():
                            raise AssertionError("public order page did not preserve the product name as literal text")

                        print("Browser smoke: scanner quantity, duplicate guard, Parchi fallback, mobile layout, payment-state wording, and stored-XSS rendering passed.")
                        print("Browser camera, microphone permission, hardware scanner, and audio playback were not exercised.")
                    finally:
                        context.close()
                finally:
                    browser.close()
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            if parent_db is not None:
                parent_db.reset_engine()


if __name__ == "__main__":
    main()
