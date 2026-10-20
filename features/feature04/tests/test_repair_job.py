"""Real DB checks for the separate Git-based prepare/apply job entrypoint."""
import hashlib
import json
import os
import sys

import pytest
from test_selected_date_repair import ROOT, DATES, database, repair, snapshot

sys.path.insert(0, str(ROOT / 'scripts'))
import run_fixed_income_repair_job as job


def setup_job(monkeypatch, database, tmp_path):
    monkeypatch.setattr(job, 'repair', repair)
    monkeypatch.setattr(os.path, 'ismount', lambda path: path == tmp_path)
    for name, value in {'FI_REPAIR_STAGE': 'prepare', 'FI_REPAIR_RUN': 'integration',
                        'FI_REPAIR_STORAGE': str(tmp_path), 'FI_REPAIR_MARKETS': 'ID US',
                        'FI_REPAIR_DATES': ' '.join(str(day) for day in DATES),
                        'DATABASE_URL': database.info.dsn}.items():
        monkeypatch.setenv(name, value)
    return tmp_path / 'integration'


def test_git_job_prepare_is_read_only_then_apply_persists_and_restart_does_not_replay(database, tmp_path, monkeypatch):
    directory = setup_job(monkeypatch, database, tmp_path)
    before = snapshot(database)
    job.main()
    assert snapshot(database) == before
    result = json.loads((directory / 'prepare-result.json').read_text())
    assert result['status'] == 'PREPARED_READ_ONLY'
    job.main()
    assert snapshot(database) == before
    monkeypatch.setenv('FI_REPAIR_STAGE', 'apply')
    monkeypatch.setenv('FI_REPAIR_EXPECTED_SHA256', result['plan_sha256'])
    monkeypatch.setenv('FI_REPAIR_MIGRATION_SHA256', hashlib.sha256(
        (ROOT / 'database/migrations/20261013_011_verify_fixed_income_sessions.sql').read_bytes()).hexdigest())
    job.main()
    assert json.loads((directory / 'apply-result.json').read_text())['post_commit_verified'] is True
    assert (directory / 'pre-migration-backup.json').exists() and (directory / 'before.json').exists()
    after = snapshot(database)
    job.main()
    assert snapshot(database) == after


def test_git_job_rejects_missing_persistent_storage_before_opening_database(monkeypatch, tmp_path):
    monkeypatch.setenv('FI_REPAIR_STAGE', 'prepare')
    monkeypatch.setenv('FI_REPAIR_RUN', 'integration')
    monkeypatch.setenv('FI_REPAIR_STORAGE', str(tmp_path))
    with pytest.raises(ValueError, match='persistent repair volume'):
        job.main()
