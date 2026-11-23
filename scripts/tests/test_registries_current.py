"""ERRORS M329: the Backtest and Screener registries are generated from the Terminal's calc/indicators.ts; when that file
changes and they are not rebuilt, screener-worker refuses to start (startup_check_failed) and every deploy fails. Both
registry checks run here, without installed packages (node with --experimental-strip-types). The Screener's check also
covers apps/edge-bff/backtest/src/core/compare-lag.json, which its generator writes from the lag probe
(EXEC-BACKTEST-REVAMP K5 a)."""
import shutil
import subprocess
from pathlib import Path

import pytest

# EXEC-GEN-CHECK: checks of a generated file, run on every push by .github/workflows/generated-files.yml
pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
CHECKS = [('apps/backtest-worker', 'scripts/build-registry.mjs', './loader/register.mjs'),
          ('apps/edge-bff/screener', 'scripts/build-screener-registry.mjs', '../../backtest-worker/loader/register.mjs')]


@pytest.mark.skipif(not shutil.which('node'), reason='node is not installed')
@pytest.mark.parametrize('folder, script, loader', CHECKS)
def test_registry_is_current(folder, script, loader):
    run = subprocess.run(['node', '--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', loader, script, '--check'],
                         cwd=ROOT / folder, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, f'{folder}: {run.stdout}{run.stderr} (run `npm run registry` there)'


def test_flow_registry_is_current():
    """EXEC-TERMINAL-IND-EDIT (code review F10, 2026-11-05): the Terminal's Flow registry is generated from
    FLOW_INDICATORS_SPEC.xlsx (verification/terminal_api/flow_indicators/build_spec_workbook.py); nothing ran its --check,
    so a hand edit of flowRegistry.json or a spreadsheet change without a rebuild went unnoticed."""
    pytest.importorskip('openpyxl')
    run = subprocess.run(['python3', 'scripts/build_flow_registry.py', '--check'], cwd=ROOT, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, f'{run.stdout}{run.stderr}'


def test_flow_spec_workbook_is_current(tmp_path):
    """check of steps 2-3 (2026-11-23, F1): FLOW_INDICATORS_SPEC.xlsx is itself written by
    verification/terminal_api/flow_indicators/build_spec_workbook.py from user_input_20261030.xlsx, so a row added to the
    workbook by hand is lost at the next rebuild (and with it the Flow indicator's registry entry). The rebuilt workbook
    must hold the committed one's cells, sheet by sheet (INDICATOR_BETA_TO_LIVE.md "A lab Flow indicator" step 1)."""
    openpyxl = pytest.importorskip('openpyxl')
    folder = ROOT / 'verification' / 'terminal_api' / 'flow_indicators'
    out = tmp_path / 'FLOW_INDICATORS_SPEC.xlsx'
    run = subprocess.run(['python3', '-I', 'build_spec_workbook.py', 'user_input_20261030.xlsx', str(out)], cwd=folder,
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, f'{run.stdout}{run.stderr}'
    def cells(path):
        wb = openpyxl.load_workbook(path, data_only=True)
        return {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb.worksheets}
    built, committed = cells(out), cells(folder / 'FLOW_INDICATORS_SPEC.xlsx')
    assert sorted(built) == sorted(committed), (sorted(built), sorted(committed))
    for sheet in committed:
        assert built[sheet] == committed[sheet], (
            f'{sheet}: FLOW_INDICATORS_SPEC.xlsx differs from what build_spec_workbook.py writes; change the builder and '
            'rebuild (python3 -I build_spec_workbook.py user_input_20261030.xlsx FLOW_INDICATORS_SPEC.xlsx), never the workbook')
