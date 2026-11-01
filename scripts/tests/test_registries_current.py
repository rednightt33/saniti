"""ERRORS M329: the Backtest and Screener registries are generated from the Terminal's calc/indicators.ts; when that file
changes and they are not rebuilt, screener-worker refuses to start (startup_check_failed) and every deploy fails. Both
registry checks run here, without installed packages (node with --experimental-strip-types)."""
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKS = [('apps/backtest-worker', 'scripts/build-registry.mjs', './loader/register.mjs'),
          ('apps/edge-bff/screener', 'scripts/build-screener-registry.mjs', '../../backtest-worker/loader/register.mjs')]


@pytest.mark.skipif(not shutil.which('node'), reason='node is not installed')
@pytest.mark.parametrize('folder, script, loader', CHECKS)
def test_registry_is_current(folder, script, loader):
    run = subprocess.run(['node', '--experimental-strip-types', '--no-warnings=ExperimentalWarning', '--import', loader, script, '--check'],
                         cwd=ROOT / folder, capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, f'{folder}: {run.stdout}{run.stderr} (run `npm run registry` there)'
