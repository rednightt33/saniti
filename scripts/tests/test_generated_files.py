"""EXEC-GEN-CHECK (user 2026-11-14: "2. A"; ERRORS M435): every generated file in the repository has a check that it
equals what its generator writes now, and `.github/workflows/generated-files.yml` runs those checks (the tests marked
`generated_file`) on each push and pull request.

The generators are found, not listed: a script in a `scripts` folder (the repository's or an app's) whose name starts
with build, generate or snapshot, or that takes `--check`. Each one is named by a test file that carries the marker, or
is in EXEMPT with the reason it cannot or need not be checked. A new generator without a check fails here."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
MARKER = 'generated_file'
FROZEN = ('writes one migration that is applied; an applied migration is never edited (AGENTS.md, History rules), so a '
          'change is a new migration, not a rebuild')
EXEMPT = {
    'build_feature_vocabulary_seed': 'reads an export of the live database (--input), which is not in the repository',
    'generate_feature04_migration': FROZEN,
    'generate_feature04_v2_migration': FROZEN,
    'generate_feature04_v3_migration': FROZEN,
    'generate_high_alert_tool_migration': FROZEN,
    'generate_warehouse_summary_tool_migration': FROZEN,
    'restart_postgres': '--check is a dry run of a Railway restart, not a file comparison',
}


def tracked(*patterns):
    out = subprocess.run(['git', 'ls-files', *patterns], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def generators():
    """Scripts directly in a folder named `scripts` (not in node_modules), found by name or by a `--check` flag."""
    found = {}
    for path in tracked('*.py', '*.mjs', '*.js'):
        if path.parent.name != 'scripts' or 'node_modules' in path.parts:
            continue
        if re.match(r'(build|generate|snapshot)[_-]', path.name) or '--check' in path.read_text(errors='replace'):
            found[path.stem] = path
    return found


def marked_test_texts():
    texts = []
    for path in tracked('*test_*.py', '*.test.ts', '*.test.mjs'):
        if 'node_modules' in path.parts:
            continue
        text = path.read_text(errors='replace')
        if MARKER in text:
            texts.append(text)
    return texts


def test_every_generator_has_a_check_or_a_reason():
    gens, texts = generators(), marked_test_texts()
    missing = sorted(name for name in gens if name not in EXEMPT and not any(name in t for t in texts))
    assert not missing, (f'generators without a check: {missing}. Add a test marked @pytest.mark.{MARKER} that '
                         'compares the committed file with what the generator writes, or add the name to EXEMPT '
                         'with the reason it cannot be checked')


def test_every_exemption_names_a_generator_that_exists():
    stale = sorted(set(EXEMPT) - set(generators()))
    assert not stale, f'EXEMPT names scripts that are gone or no longer generators: {stale}; remove them'


def test_indicator_spec_is_current():
    """scripts/terminal_indicator_spec.py writes INDICATOR_SPEC.md and migration 20261025_102 (applied: its --check
    tells when a formula text changed and a new migration is due, INDICATORS_HANDOFF.md 7.3)."""
    run = subprocess.run([sys.executable, 'scripts/terminal_indicator_spec.py', '--check'], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, f'{run.stdout}{run.stderr} (run python3 scripts/terminal_indicator_spec.py)'


def test_feature_07_dictionary_is_current():
    run = subprocess.run([sys.executable, 'scripts/generate_feature_07_catalog.py', 'dictionary'], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    assert (ROOT / 'FEATURE_07_RADAR.md').read_text() == run.stdout, \
        'FEATURE_07_RADAR.md differs: run python3 scripts/generate_feature_07_catalog.py dictionary > FEATURE_07_RADAR.md'


def test_feature_05_06_dictionary_is_current():
    """ERRORS M436: the dictionary is the v1 text with the corrections of the applied m_vocab migrations (Feature_Catalog
    as it is on dev, read back 2026-11-14) plus the notes kept in the generator."""
    run = subprocess.run([sys.executable, 'scripts/generate_feature_05_06_catalog.py', 'dictionary'], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    assert (ROOT / 'FEATURE_05_06_FOREIGN_DOMESTIC.md').read_text() == run.stdout, (
        'FEATURE_05_06_FOREIGN_DOMESTIC.md differs: change the text in scripts/generate_feature_05_06_catalog.py (a catalog '
        'text by a new migration with an m_vocab table), then run it with `dictionary > FEATURE_05_06_FOREIGN_DOMESTIC.md`')


def test_feature_05_06_migration_output_is_the_applied_migration():
    """The generator's v1 text stays what 20261022_004 applied; a correction goes in a new migration, not here."""
    run = subprocess.run([sys.executable, 'scripts/generate_feature_05_06_catalog.py', 'migration'], cwd=ROOT,
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr
    applied = ROOT / 'database/migrations/20261022_004_catalog_feature_05_06.sql'
    assert applied.read_text() == run.stdout, (
        'the v1 text in scripts/generate_feature_05_06_catalog.py changed: an applied migration is frozen, so restore it '
        'and write the correction as a new migration with an m_vocab table')
