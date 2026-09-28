"""The Governor's audit client against the one published Audit Store contract (audit-store/v1). A contract change
that removes or renames what this client sends fails here, so the client is updated before the service is
redeployed."""
from __future__ import annotations

import json
from pathlib import Path

from app.audit_archive import DatasetArchiver  # noqa: F401 - the archiver uses the roles checked below
from app.audit_client import CONTRACT, FIELDS, OPERATIONS

CONTRACT_FILE = Path(__file__).resolve().parents[2] / "market-audit-store" / "openapi" / "audit-store-v1.json"
ROLES = {"RAW_INPUT_PARQUET", "EXTRACTION_MANIFEST"}


def test_every_operation_and_field_the_client_uses_is_in_the_contract() -> None:
    contract = json.loads(CONTRACT_FILE.read_text())
    assert CONTRACT in contract["info"]["description"]
    schemas = contract["components"]["schemas"]
    for (method, path), model in OPERATIONS.items():
        operation = contract["paths"][path][method]
        if model is not None:
            ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith(f"/{model}"), (path, ref)
    for model, fields in FIELDS.items():
        assert fields <= set(schemas[model]["properties"]), model
    assert ROLES <= set(schemas["LinkIn"]["properties"]["role"]["enum"])
    assert "application/vnd.apache.parquet" in schemas["ArtifactPrepare"]["properties"]["media_type"]["enum"]
