import hashlib
import hmac

from fetchkit.legacy_auth import signed_headers


def test_signed_headers_sign_timestamp_and_path():
    headers = signed_headers(b"s3cret", "invoices/7", now=1_700_000_000.4)
    assert headers["X-Billing-Timestamp"] == "1700000000"
    expected = hmac.new(b"s3cret", b"1700000000:invoices/7", hashlib.sha256).hexdigest()
    assert headers["X-Billing-Signature"] == expected
