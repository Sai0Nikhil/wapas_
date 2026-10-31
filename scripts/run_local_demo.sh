#!/usr/bin/env bash
# ==============================================================================
# Wapas Merchant OS - Local Demo Runner
# Paytm Build for India AI Hackathon (Track 3: Autonomous AI Teammates)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/Seprate Version/wapas-merchant-os"
VENV_DIR="$ROOT_DIR/.venv"

echo "================================================================="
echo "   Wapas Merchant OS: Autonomous Kirana AI Teammates Demo"
echo "================================================================="

# 1. Verify virtualenv
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtualenv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    "$VENV_DIR/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt"
fi

# 2. Configure Disposable Development Environment
echo "[1/4] Configuring development environment..."
export WAPAS_ENV="development"
export GATEWAY="fake"
export PAYTM_TEST_ENABLED="false"
export PAYTM_LIVE_ENABLED="false"
export DATABASE_URL="sqlite:///$ROOT_DIR/wapas-development.db"
export PUBLIC_BASE_URL="http://localhost:8000"
export APPROVAL_SECRET="wapas-dev-approval-secret-key-32chars"

# 3. Seed Demo Data
echo "[2/4] Seeding Kirana products, users, Khata accounts, and recovery cases..."
cd "$BACKEND_DIR"
PYTHONPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" scripts/seed_demo_data.py

# 4. Verify Health with Doctor
echo "[3/4] Running system verification..."
PYTHONPATH="$BACKEND_DIR" "$VENV_DIR/bin/python" -m app.doctor || true

# 5. Start Server
echo "================================================================="
echo "   Server URL:  http://0.0.0.0:8000"
echo "   Swagger:     http://localhost:8000/docs"
echo "   Credentials: admin / password12345678 (Owner role)"
echo "                staff / password12345678 (Staff role)"
echo "   Flutter Run: cd wapas_app && flutter run"
echo "================================================================="
echo "[4/4] Starting FastAPI Uvicorn server..."
exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
