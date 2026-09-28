"""Write openapi/audit-store-v1.json, the one versioned Audit Store contract (python -m app.export_openapi).

The producer clients inside market-sql-governor and market-python-sandbox are checked against this file by their
contract tests, so a contract change fails their tests until the clients are updated (and redeployed)."""
from __future__ import annotations

import json
from pathlib import Path

from .config import Settings
from .main import create_app

TARGET = Path(__file__).resolve().parents[1] / "openapi" / "audit-store-v1.json"


def build() -> dict:
    settings = Settings.from_env({
        "AUDIT_DATABASE_URL": "postgresql://contract@localhost/contract", "AUDIT_STORE_READER_KEY": "r" * 40,
        "AUDIT_STORE_GOVERNOR_KEY": "g" * 40, "AUDIT_STORE_SANDBOX_KEY": "s" * 40,
        "AUDIT_LOCAL_OBJECT_DIR": "/tmp/audit-contract", "AUDIT_LOCAL_SIGNING_KEY": "k" * 40,
        "AUDIT_PUBLIC_BASE_URL": "http://localhost"})
    return create_app(settings, start_consumer=False).openapi()


if __name__ == "__main__":
    TARGET.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")
    print(TARGET)
