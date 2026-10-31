# Wapas Merchant OS

**Paytm Build for India AI Hackathon (Track 3: Autonomous AI Teammates: "AI that doesn't just respond, it gets the job done.")**

Wapas is an autonomous Merchant Operating System built for Indian Kirana stores. It connects real payment rails (Paytm UPI, Dynamic QR), offline store hardware (Paytm Soundbox, camera OCR, thermal receipts), and autonomous AI teammates (powered by Sarvam-105B) to monitor, protect, and recover lost merchant revenue 24/7.

---

## Repository Structure

- **`wapas_app/`**: The Flutter mobile application (Android, iOS, Web). Transformed from a prototype into a production-grade live client with zero hardcoded business data, Riverpod 3.x, layered `ApiClient`, and bilingual EN/HI error handling. See [wapas_app/README.md](wapas_app/README.md) for full architecture details.
- **`Seprate Version/wapas-merchant-os/`**: The FastAPI backend powering Wapas (`app/merchant_api.py`, `app/api.py`, `app/sarkar.py`, `app/auth.py`).
- **`scripts/run_local_demo.sh`**: One-click script to configure a disposable SQLite DB (`GATEWAY=fake`), seed Kirana demo data, and start Uvicorn.
- **`docs/demo-script.md`**: 3-minute hackathon demo walkthrough script for judges and presentations.
- **`docs/flutter-api-map.md`**: Complete screen-to-endpoint API contract mapping.

---

## Quick Start (Demo Mode)

### 1. Launch Backend with Seeded Demo Data
```bash
./scripts/run_local_demo.sh
```
- Server URL: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`
- Ready Probe: `http://localhost:8000/healthz`
- Demo Credentials:
  - **Owner:** `admin` / `password12345678`
  - **Staff:** `staff` / `password12345678`

### 2. Launch Mobile App
```bash
cd wapas_app
flutter pub get
flutter run
```

### 3. Run Tests
```bash
cd wapas_app
flutter analyze   # 0 issues
flutter test      # 22 tests passing
```
