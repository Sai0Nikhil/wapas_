@echo off
REM Wapas: paste your API keys once (hidden input), then run the live check.
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
python -m pip install -q -r requirements.txt
python -m app.setup_keys
pause
