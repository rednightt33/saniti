"""scripts/live_diff.py (the user, 2026-11-20, EXEC option A; LIVE_PROMOTION.md): the beta-live difference is derived at
run time. No git or network call here: the grouping of changed files and the release file comparison."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import live_diff as ld  # noqa: E402


def test_changed_files_group_by_area():
    assert ld.group_areas(['apps/edge-bff/app/main.py', 'apps/edge-bff/static/edge-app.js',
                           'database/migrations/20261121_001_x.sql', 'EXEC.md', 'scripts/live_diff.py',
                           '.railway/railway.ts', 'Dockerfile']) == {
        '.railway': ['.railway/railway.ts'], 'apps/edge-bff': ['apps/edge-bff/app/main.py', 'apps/edge-bff/static/edge-app.js'],
        'database/migrations': ['database/migrations/20261121_001_x.sql'], 'documents (root)': ['EXEC.md'],
        'root files': ['Dockerfile'], 'scripts': ['scripts/live_diff.py']}


def test_the_release_changes_name_what_moving_live_would_change_and_what_stays_off():
    live = {'items': [{'kind': 'indicator', 'id': 'I01', 'stage': 'released'},
                      {'kind': 'indicator', 'id': 'I02', 'stage': 'lab'}],
            'tabs': [{'id': 'terminal', 'stage': 'released'}]}
    beta = {'items': [{'kind': 'indicator', 'id': 'I01', 'stage': 'released'},
                      {'kind': 'indicator', 'id': 'I02', 'stage': 'released'},
                      {'kind': 'indicator', 'id': 'I54', 'stage': 'lab'}],
            'tabs': [{'id': 'terminal', 'stage': 'released'}, {'id': 'research', 'stage': 'lab'}]}
    out = ld.release_changes(live, beta)
    assert out['items'] == {'new': ['indicator:I54=lab'], 'changed': ['indicator:I02: lab -> released'], 'gone': [],
                            'lab_on_beta': ['indicator:I54'], 'preview_admin_only': []}
    assert out['tabs'] == {'new': ['research=lab'], 'changed': [], 'gone': [], 'lab_on_beta': ['research']}
    # EXEC-MU-ACCOUNTS "A preview release stage": a move to preview is named as reaching the live site for the admin only
    previewed = {**beta, 'items': beta['items'] + [{'kind': 'flow_indicator', 'id': 'FL53', 'stage': 'preview'}]}
    moved = ld.release_changes({**live, 'items': live['items'] + [{'kind': 'flow_indicator', 'id': 'FL53', 'stage': 'lab'}]},
                               previewed)
    assert moved['items']['changed'] == ['flow_indicator:FL53: lab -> preview', 'indicator:I02: lab -> released']
    assert moved['items']['preview_admin_only'] == ['flow_indicator:FL53']
    assert 'preview_admin_only' not in moved['tabs']
    # a live branch without a release file (or without tabs) reads as empty
    assert ld.release_changes(None, beta)['tabs']['new'] == ['research=lab', 'terminal=released']
