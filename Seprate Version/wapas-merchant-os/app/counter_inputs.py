"""Safe, review-only adapters for non-typed Counter inputs.

The module returns suggestions only. Product identity, prices, stock, and bill
mutation remain owned by the existing inventory and billing services.
"""
import base64
import io
import json
import math
import re
import unicodedata
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation

import httpx
from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from . import inventory, voice
from .config import get_settings

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_AUDIO_BYTES = 12 * 1024 * 1024
MAX_PIXELS = 24_000_000
MAX_LINES = 20
IMAGE_MIMES = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
AUDIO_MIMES = {"audio/webm", "audio/ogg", "audio/wav", "audio/mpeg", "audio/mp4", "audio/aac"}
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def validate_image(data: bytes, content_type: str) -> bytes:
    """Decode and normalize a bounded raster image, stripping metadata."""
    if not data:
        raise HTTPException(422, "Choose an image file first.")
    if len(data) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Image is too large. Maximum size is 8 MB.")
    expected = IMAGE_MIMES.get((content_type or "").split(";", 1)[0].strip().lower())
    if not expected:
        raise HTTPException(415, "Use a JPEG, PNG, or WebP image.")
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != expected or getattr(image, "n_frames", 1) != 1:
                raise HTTPException(415, "The image content does not match its file type or is animated.")
            if image.width * image.height > MAX_PIXELS:
                raise HTTPException(413, "Image dimensions are too large to process safely.")
            image.load()
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((2048, 2048))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85, optimize=True)
            return out.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(422, "This image could not be decoded safely.") from exc


def validate_audio(data: bytes, content_type: str) -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    if not data:
        raise HTTPException(422, "Record or choose an audio clip first.")
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Audio is too large. Maximum size is 12 MB.")
    if mime not in AUDIO_MIMES:
        raise HTTPException(415, "Use a supported browser recording such as WebM, OGG, WAV, MP3, or MP4 audio.")
    return mime


def _image_candidates(image_data: bytes, task: str) -> list[dict]:
    cfg = get_settings()
    if not cfg.vision_configured:
        raise HTTPException(503, "Vision recognition is not configured. Search the catalogue and add the item manually.")
    task_text = (
        "Identify the single visible retail product. Return candidate name, optional quantity only if clearly visible, "
        "unit only if clearly printed, and confidence from 0 to 1."
        if task == "photo" else
        "Read a handwritten or printed shopping list. Return at most 20 lines, each with candidate product name, "
        "quantity only when clearly written, unit only when clearly written, and confidence from 0 to 1. "
        "Use null for uncertain quantities or units."
    )
    response = httpx.post(
        cfg.vision_base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {cfg.vision_api_key}"},
        json={"model": cfg.vision_model, "temperature": 0,
              "messages": [{"role": "user", "content": [
                  {"type": "text", "text": task_text + " Return JSON only: {\"items\":[{\"name\":string,\"quantity\":number|null,\"unit\":string|null,\"confidence\":number|null}]}"},
                  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_data).decode("ascii")}},
              ]}], "response_format": {"type": "json_object"}},
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
    if not isinstance(content, str) or len(content) > 20_000:
        raise ValueError("Vision provider returned an invalid response")
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
    parsed = json.loads(content)
    items = parsed.get("items") if isinstance(parsed, dict) else None
    if not isinstance(items, list):
        raise ValueError("Vision provider did not return item candidates")
    return items[:MAX_LINES]


def _norm(text: str) -> str:
    cleaned = "".join(
        c for c in (text or "").casefold()
        if not unicodedata.category(c).startswith(("P", "S"))
    )
    return " ".join(cleaned.split())


def _safe_quantity(value) -> str | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount > Decimal("10000") or amount.as_tuple().exponent < -3:
        return None
    return format(amount.normalize(), "f")


def resolve_candidates(s, *, merchant_id: str, store_id: str, raw_items: list[dict]) -> list[dict]:
    saved = inventory.list_products(s, merchant_id=merchant_id, store_id=store_id)
    active = [(product, balance) for product, balance in saved if product.status == "ACTIVE"]
    result = []
    for raw in raw_items[:MAX_LINES]:
        name = raw.get("name") if isinstance(raw, dict) else None
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()[:120]
        query = _norm(name)
        if not query:
            ranked = []
        else:
            ranked = sorted(((SequenceMatcher(None, query, _norm(p.name)).ratio(), p, b)
                             for p, b in active if _norm(p.name)), key=lambda row: (-row[0], row[1].name.casefold()))
        matches = [{"product_id": p.id, "name": p.name, "unit": p.unit,
                    "catalogue_match": round(score, 3)} for score, p, _ in ranked[:3] if score >= 0.25]
        top = matches[0]["catalogue_match"] if matches else 0.0
        ambiguous = (not matches or top < 0.55 or
                     (len(matches) > 1 and top - matches[1]["catalogue_match"] < 0.08))
        quantity = _safe_quantity(raw.get("quantity"))
        try:
            confidence = float(raw.get("confidence"))
            if not math.isfinite(confidence) or confidence < 0 or confidence > 1:
                confidence = None
        except (TypeError, ValueError):
            confidence = None
        result.append({
            "recognized_name": name, "quantity": quantity,
            "recognized_unit": str(raw.get("unit"))[:24] if raw.get("unit") else None,
            "provider_confidence": confidence,
            "candidates": matches,
            "needs_manual_review": True,
            "needs_clarification": ambiguous or quantity is None,
        })
    return result


_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
            "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
            "eleven": 11, "twelve": 12}
_NUMBER_WORDS = "|".join(_NUMBERS)
_VOICE_SEGMENT = re.compile(rf"^\s*(?:(?:add|put|include|sell)\s+)?(\d+(?:\.\d{{1,3}})?|{_NUMBER_WORDS})\s+(.+?)\s*$", re.I)


def parse_voice_transcript(transcript: str) -> list[dict]:
    """Parse only explicit quantity/name segments; never infer a missing quantity."""
    cleaned = " ".join((transcript or "").strip().split())
    cleaned = re.sub(r"^(?:please\s+)?(?:add|put|include|sell)\s+", "", cleaned, flags=re.I)
    # Split at conjunctions only when the following phrase begins with an explicit quantity.
    parts = re.split(rf"\s+and\s+(?=(?:\d|{_NUMBER_WORDS})\s)", cleaned, flags=re.I)
    if not 1 <= len(parts) <= MAX_LINES:
        return []
    items = []
    for part in parts:
        match = _VOICE_SEGMENT.fullmatch(part)
        if not match:
            return []
        amount, name = match.groups()
        amount = str(_NUMBERS.get(amount.casefold(), amount))
        quantity = _safe_quantity(amount)
        if not quantity:
            return []
        items.append({"name": name.strip(" .,!?"), "quantity": quantity, "unit": None, "confidence": None})
    return items


def parse_manual_list(text: str) -> list[dict]:
    """Parse manually transcribed lines such as `2 rice bags` without a provider."""
    cleaned = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    if not cleaned:
        return []
    parts = re.split(r"\n|;|,\s*(?=(?:\d|" + _NUMBER_WORDS + r")\s)", cleaned, flags=re.I)
    if len(parts) == 1:
        return parse_voice_transcript(cleaned)
    result = []
    for part in parts:
        parsed = parse_voice_transcript(part)
        if len(parsed) != 1:
            return []
        result.extend(parsed)
    return result[:MAX_LINES]


def transcribe_counter_audio(data: bytes, mime: str) -> str:
    """Use the existing Sarvam STT adapter, with bounded input at the route."""
    result = voice.transcribe_full(data, mime)
    text = result.get("transcript") if isinstance(result, dict) else ""
    return " ".join(str(text or "").split())[:2000]
