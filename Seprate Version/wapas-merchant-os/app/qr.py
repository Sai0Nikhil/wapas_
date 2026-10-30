"""Generate PNG QR images for already-verified storefront URLs."""
from io import BytesIO


def qr_png(target_url: str) -> bytes:
    import qrcode

    image = qrcode.make(target_url)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
