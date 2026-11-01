"""EXEC-IND-CARDS IC2: the indicator cards' formulas (apps/edge-bff/terminal/src/data/indNotes.json) equal their sources,
scripts/terminal_indicator_spec.py and FORMULAS.md; a change there needs `python3 scripts/build_indicator_notes.py`."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_indicator_notes_match_their_sources():
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/build_indicator_notes.py'), '--check'], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
