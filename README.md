# Wapas

    python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
    pip install -r requirements.txt
    cp .env.example .env                                # fill in keys as you get them
    python -m scripts.seed
    uvicorn app.main:app --reload

Docs: http://localhost:8000/docs  |  Tests: `pytest -q`
Dev fallback (no Paytm needed): `POST /dev/simulate-failure`
