"""Paytm checksum (signature) helpers.

Same algorithm as Paytm's published checksum libraries: SHA-256 over
"<params>|<salt>", salt appended, then AES-128/256-CBC with Paytm's fixed IV
and the merchant key, base64-encoded. Written here because the PyPI package
no longer builds on current Python.
"""
import base64
import hashlib
import secrets
import string

from Crypto.Cipher import AES

_IV = b"@@@@&&&&####$$$$"
_BLOCK = 16
_ALPHABET = string.ascii_letters + string.digits


def _pad(s: str) -> bytes:
    n = _BLOCK - len(s.encode()) % _BLOCK
    return s.encode() + bytes([n]) * n


def _unpad(b: bytes) -> str:
    return b[: -b[-1]].decode()


def _encrypt(text: str, key: str) -> str:
    c = AES.new(key.encode(), AES.MODE_CBC, _IV)
    return base64.b64encode(c.encrypt(_pad(text))).decode()


def _decrypt(token: str, key: str) -> str:
    c = AES.new(key.encode(), AES.MODE_CBC, _IV)
    return _unpad(c.decrypt(base64.b64decode(token)))


def _hash(params: str, salt: str) -> str:
    return hashlib.sha256(f"{params}|{salt}".encode()).hexdigest() + salt


def params_string(params: dict) -> str:
    out = []
    for k in sorted(params):
        v = params[k]
        v = "" if v is None or str(v).lower() == "null" else str(v)
        out.append(v)
    return "|".join(out)


def generate_signature(params: str | dict, key: str) -> str:
    if isinstance(params, dict):
        params = params_string(params)
    salt = "".join(secrets.choice(_ALPHABET) for _ in range(4))
    return _encrypt(_hash(params, salt), key)


def verify_signature(params: str | dict, key: str, checksum: str) -> bool:
    if isinstance(params, dict):
        params = params_string({k: v for k, v in params.items() if k != "CHECKSUMHASH"})
    try:
        plain = _decrypt(checksum, key)
    except Exception:  # noqa: BLE001
        return False
    salt = plain[-4:]
    return secrets.compare_digest(plain, _hash(params, salt))
