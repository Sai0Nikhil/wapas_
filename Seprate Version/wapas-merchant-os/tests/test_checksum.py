from app.gateway.checksum import generate_signature, verify_signature

KEY = "abcdefghijklmnop"


def test_roundtrip_string_and_dict():
    body = '{"mid":"X","orderId":"O1"}'
    assert verify_signature(body, KEY, generate_signature(body, KEY))
    params = {"ORDERID": "O1", "STATUS": "TXN_SUCCESS"}
    sig = generate_signature(params, KEY)
    assert verify_signature(dict(params, CHECKSUMHASH=sig), KEY, sig)


def test_tamper_and_wrong_key_rejected():
    body = '{"mid":"X","orderId":"O1"}'
    sig = generate_signature(body, KEY)
    assert not verify_signature(body.replace("O1", "O2"), KEY, sig)
    assert not verify_signature(body, "ponmlkjihgfedcba", sig)
    assert not verify_signature(body, KEY, "garbage")
