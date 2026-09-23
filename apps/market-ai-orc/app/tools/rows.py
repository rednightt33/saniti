from __future__ import annotations

import base64
import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

from .registry import ToolError


def load_exact(text: str) -> Any:
    """Parse PostgreSQL JSON output without float rounding of numeric values."""
    return json.loads(text, parse_float=Decimal)


def jsonable(value: Any) -> Any:
    """Non-integer numbers become exact decimal strings; everything else is already JSON."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    return value


def as_row(record: dict[str, Any], columns: list[str]) -> list[Any]:
    """Align one JSON row object to the declared column order; a missing column is an error."""
    missing = [name for name in columns if name not in record]
    if missing:
        raise ToolError(f"Database row did not contain declared columns: {missing[:3]}")
    return [jsonable(record[name]) for name in columns]


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class CursorCodec:
    """Opaque, tamper-evident continuation tokens: they carry key values, never SQL."""

    def __init__(self, secret: bytes) -> None:
        self._secret = secret

    def _mac(self, payload: bytes) -> bytes:
        return hmac.new(self._secret, payload, hashlib.sha256).digest()[:16]

    def encode(self, catalog: str, key_values: list[Any]) -> str:
        payload = json.dumps({"v": 1, "c": catalog, "k": key_values}, separators=(",", ":")).encode()
        return f"{_b64(payload)}.{_b64(self._mac(payload))}"

    def decode(self, token: str, catalog: str, key_length: int) -> list[Any]:
        invalid = ToolError(
            "The cursor is invalid for this catalog. Use the exact next_cursor returned by the "
            "previous page, or pass null to start from the first page."
        )
        try:
            payload_text, mac_text = token.split(".", 1)
            payload = _unb64(payload_text)
            if not hmac.compare_digest(self._mac(payload), _unb64(mac_text)):
                raise invalid
            data = json.loads(payload)
        except (ValueError, TypeError) as exc:
            raise invalid from exc
        keys = data.get("k") if isinstance(data, dict) else None
        if (
            data.get("v") != 1 or data.get("c") != catalog or not isinstance(keys, list)
            or len(keys) != key_length
            or not all(isinstance(value, (str, int)) and not isinstance(value, bool) for value in keys)
        ):
            raise invalid
        return keys
