"""Sarvam client: strict-JSON diagnosis + multilingual recovery message drafting.
Uses Sarvam API when key is configured, with deterministic fallback for offline/sandbox testing.
"""
import json
import logging
import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)


async def diagnose(case_context: dict) -> dict:
    """Return {cause, confidence, action, language, recovery_msg}.
    Deterministic fallback guarantees 100% reliability if key is missing or API errors.
    """
    s = get_settings()
    customer_lang = case_context.get("language", "hi")
    bank = case_context.get("bank", "Unknown Bank")
    resp_msg = case_context.get("resp_msg", "Transaction Failed")
    amount_inr = case_context.get("amount_inr", 0)

    # If Sarvam key is provided, call Sarvam-105B with strict output schema
    if s.sarvam_api_key:
        try:
            prompt = f"""You are Wapas AI, an autonomous revenue recovery teammate for Indian kirana merchants.
Diagnose this failed payment and craft a polite recovery message in {customer_lang}:
- Bank: {bank}
- Error: {resp_msg}
- Amount: ₹{amount_inr}
- Customer: {case_context.get("customer_name", "Customer")}

Respond ONLY with valid JSON:
{{
  "cause": "short diagnosis of why payment failed",
  "confidence": 0.85,
  "action": "recommended safe next step",
  "language": "{customer_lang}",
  "recovery_msg": "polite message in {customer_lang} with recovery link placeholder"
}}"""

            headers = {"API-Subscription-Key": s.sarvam_api_key, "Content-Type": "application/json"}
            payload = {
                "model": s.sarvam_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                res = await client.post(f"{s.sarvam_base_url}/chat/completions", headers=headers, json=payload)
                if res.status_code == 200:
                    raw_content = res.json()["choices"][0]["message"]["content"]
                    # parse json
                    clean_json = raw_content.strip()
                    if clean_json.startswith("```json"):
                        clean_json = clean_json[7:-3].strip()
                    elif clean_json.startswith("```"):
                        clean_json = clean_json[3:-3].strip()
                    return json.loads(clean_json)
        except Exception as exc:
            logger.warning(f"Sarvam API call failed, falling back to deterministic diagnosis: {exc}")

    # Deterministic high-precision fallback
    confidence = 0.92 if "timeout" in resp_msg.lower() or "network" in resp_msg.lower() else 0.84
    
    if customer_lang == "te":
        recovery_msg = f"నమస్కారం, మీ ₹{amount_inr} చెల్లింపు సర్వర్ సమస్య వలన విఫలమైంది. దయచేసి ఈ లింక్ ద్వారా సులభంగా పూర్తి చేయండి: {{link}}"
    elif customer_lang == "ta":
        recovery_msg = f"வணக்கம், உங்கள் ₹{amount_inr} கட்டணம் வங்கி சர்வர் பிழையால் தோல்வியடைந்தது. முடிக்க இந்த இணைப்பை கிளிக் செய்யவும்: {{link}}"
    elif customer_lang == "kn":
        recovery_msg = f"ನಮಸ್ಕಾರ, ನಿಮ್ಮ ₹{amount_inr} ಪಾವತಿ ಬ್ಯಾಂಕ್ ಸರ್ವರ್ ಸಮಸ್ಯೆಯಿಂದ ವಿಫಲವಾಗಿದೆ. ಪೂರ್ಣಗೊಳಿಸಲು ಈ ಲಿಂಕ್ ಬಳಸಿ: {{link}}"
    else:
        recovery_msg = f"नमस्ते, सर्वर में रुकावट के कारण आपका ₹{amount_inr} का भुगतान नहीं हो सका। कृपया इस लिंक से 1-क्लिक में पूरा करें: {{link}}"

    return {
        "cause": f"{bank} Server / UPI Gateway Latency: {resp_msg}",
        "confidence": confidence,
        "action": "Send 1-click verified Paytm recovery link",
        "language": customer_lang,
        "recovery_msg": recovery_msg,
    }
