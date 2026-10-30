#!/usr/bin/env bash
# Wapas: setup + run on macOS / Linux. Safe to run again: it only installs what is missing.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || python3 -m venv .venv
. .venv/bin/activate
python -m pip install -q -r requirements.txt
[ -f .env ] || cp .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
