@echo off
REM Wapas: setup + run on Windows. Safe to run again: it only installs what is missing.
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
python -m pip install -q -r requirements.txt
if not exist .env copy .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
