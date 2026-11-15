"""RADAR_FORMULAS.md describes the Radar code applied on dev (user 2026-11-15: "formula2 yang live saat ini di DEV harus
selalu terupdate MDnya, at least untuk bagian radar dulu"). Without a database: the function fingerprints written in the
document equal those of the newest applied migration defining each function (scripts/radar_formulas_doc.py --repo),
and the explanation was written for those fingerprints. The live comparison (thresholds, rule version, the functions as
dev holds them) runs every day in .github/workflows/database-schema-docs.yml (--write, then --check)."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.generated_file

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import radar_formulas_doc as doc  # noqa: E402


def test_the_document_names_the_applied_radar_code():
    run = subprocess.run([sys.executable, str(ROOT / 'scripts/radar_formulas_doc.py'), '--repo'],
                         capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_radar_function_is_found_in_the_applied_migrations():
    found = doc.applied()
    assert set(found) == set(doc.FUNCTIONS), sorted(set(doc.FUNCTIONS) - set(found))


def test_a_fingerprint_is_the_md5_of_the_body_between_the_dollar_quotes():
    sql = ("CREATE OR REPLACE FUNCTION public.refresh_feature_07_day(p_date date)\nRETURNS integer\nLANGUAGE plpgsql\n"
           "AS $function$\nBEGIN RETURN 1; END\n$function$;\n"
           "CREATE FUNCTION public.feature_07_rule_version() RETURNS text LANGUAGE sql IMMUTABLE AS $$ SELECT 'x'::text $$;")
    got = dict((fn, hashlib.md5(body.encode()).hexdigest()) for fn, _, body in doc.BODY.findall(sql))
    assert got == {'refresh_feature_07_day': hashlib.md5(b'\nBEGIN RETURN 1; END\n').hexdigest(),
                   'feature_07_rule_version': hashlib.md5(b" SELECT 'x'::text ").hexdigest()}


def test_a_changed_function_or_threshold_is_reported_with_the_way_out():
    rules = [['S1', 'A', 'standard', 'Foreign net 5D above 0', 0, None, 'decided', 'Heavy foreign accumulation', 1]]
    fps = {fn: 'a' * 32 for fn in doc.FUNCTIONS}
    explained = '<!-- explained-for: ' + ', '.join(f'{fn}={"a" * 32}' for fn in doc.FUNCTIONS) + ' -->'
    text = explained + '\n' + doc.section('radar-v1', rules, fps) + '\n'
    assert doc.problems(text, 'radar-v1', rules, fps) == []
    moved = dict(fps, refresh_feature_07_day='b' * 32)
    out = doc.problems(text, 'radar-v1', rules, moved)
    assert any('functions changed: refresh_feature_07_day' in p and '--write' in p for p in out)
    assert any('explanation was written for another version of refresh_feature_07_day' in p for p in out)
    higher = [rules[0][:4] + [5] + rules[0][5:]]
    assert any('thresholds' in p for p in doc.problems(text, 'radar-v1', higher, fps))
