"""Run scripts/audit_feature_catalog_semantics.py on orc-test-runner (AGENTS.md: after a Feature change)."""
import audit_feature_catalog_semantics as audit

try:
    audit.main()
    print("VERDICT PASS", flush=True)
except Exception as exc:  # noqa: BLE001
    print("VERDICT FAIL " + str(exc)[:3000], flush=True)
finally:
    print("JOB_DONE", flush=True)
