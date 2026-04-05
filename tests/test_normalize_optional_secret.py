"""normalize_optional_secret_string (webhook HMAC env, etc.)."""

from jvspatial.env import normalize_optional_secret_string


def test_normalize_none_and_blank():
    assert normalize_optional_secret_string(None) is None
    assert normalize_optional_secret_string("") is None
    assert normalize_optional_secret_string("   ") is None


def test_normalize_null_placeholders():
    for raw in ("null", "NULL", "none", "None", "undefined", "(null)", "nil"):
        assert normalize_optional_secret_string(raw) is None


def test_normalize_preserves_real_secret():
    assert normalize_optional_secret_string(" abcd ") == "abcd"
