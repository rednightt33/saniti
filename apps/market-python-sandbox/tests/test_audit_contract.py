"""The sandbox's audit client against the one published Audit Store contract (audit-store/v1)."""
from __future__ import annotations

import json
from pathlib import Path

from app.audit import MEDIA
from app.audit_client import CONTRACT, FIELDS, OPERATIONS

CONTRACT_FILE = Path(__file__).resolve().parents[2] / "market-audit-store" / "openapi" / "audit-store-v1.json"
ROLES = {"PYTHON_SOURCE", "RUNTIME_MANIFEST", "EXECUTION_TRACE", "ERROR_DETAIL", "RAW_INPUT_PARQUET", "OUTPUT",
         "EXECUTION_MANIFEST", "VALIDATION_RESULT", "APPROVED_DATANEED_CONTRACT", "INPUT_BUNDLE_MANIFEST"}


def test_every_operation_field_role_and_media_type_the_client_uses_is_in_the_contract() -> None:
    contract = json.loads(CONTRACT_FILE.read_text())
    assert CONTRACT in contract["info"]["description"]
    schemas = contract["components"]["schemas"]
    for (method, path), model in OPERATIONS.items():
        operation = contract["paths"][path][method]
        if model is not None:
            ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
            assert ref.endswith(f"/{model}"), (path, ref)
    for model, fields in FIELDS.items():
        assert fields <= set(schemas[model]["properties"]), (model, fields - set(schemas[model]["properties"]))
    assert ROLES <= set(schemas["LinkIn"]["properties"]["role"]["enum"])
    media = set(schemas["ArtifactPrepare"]["properties"]["media_type"]["enum"])
    assert set(MEDIA.values()) | {"text/x-python", "application/json"} <= media
