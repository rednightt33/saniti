"""EXEC-INDEX-GROUP-HISTORY: the entity rows (indexes, sectors, groups) must be computed with IHSG's formula, only from
other symbols. These checks read the two scripts as text (no database, no imports), so a change to the IHSG raw read that
is not made in the entity read too fails here. The behaviour itself was checked on a local copy of dev data
(verification/index_group_history/stage4/README.md)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
IHSG = (ROOT / 'scripts/backfill_index_features.py').read_text()
ENTITY = (ROOT / 'scripts/backfill_index_entities.py').read_text()


def norm(text):
    return re.sub(r'\s+', '', text)


def ihsg_read():
    start = IHSG.index("db.execute('''WITH r AS MATERIALIZED")
    return norm(IHSG[start:IHSG.index('(lo,hi,ticker))', start)])


def entity_read():
    start = ENTITY.index("READ = '''")
    return norm(ENTITY[start:ENTITY.index("'''", start + 10)])


def test_gap_is_per_symbol_and_board_before_netting_in_both():
    window = norm('SUM("Buy Value") OVER w <> SUM("Sell Value") OVER w AS gap')
    partition = norm('WINDOW w AS (PARTITION BY "Date", "Symbol", "Market Board")')
    for text in (ihsg_read(), entity_read()):
        assert window in text and partition in text


def test_entity_sums_are_the_ihsg_sums():
    """Every aggregate of IHSG's per broker row (values, lots, nets, frequency and its coverage counts) is in the
    entity read's per broker step, which bulk5 (Feature 02/03/05) and hist6 (Feature 06) are both built from."""
    ihsg = ihsg_read()
    aggregates = re.findall(r'(?:SUM|COUNT|bool_or)\([^()]*\)(?:::bigint)?', ihsg.split('INSERTINTObulk5')[1].split('FROMr')[0])
    assert len(aggregates) >= 14, aggregates
    entity = re.sub(r'AS\w+', '', entity_read())
    missing = [a for a in aggregates if a not in entity and a.replace('COUNT(*)-', '') not in entity]
    assert not missing, f'IHSG aggregates not in the entity read: {missing}'


def test_strict_frequency_rule_is_ihsgs():
    """Feature 06 takes a broker row's frequency only when every source row of it has one (IHSG stage6); hist6 keeps
    that per broker before summing over brokers."""
    assert norm("CASE WHEN {}=frequency_source_rows THEN {} END") in norm(IHSG)
    assert norm('SUM(CASE WHEN nb = n THEN bf END)') in entity_read()
    assert norm('SUM(CASE WHEN ns = n THEN sf END)') in entity_read()


def test_ihsg_stays_on_its_own_script():
    assert "member_source <> 'ALL_SOURCE_SYMBOLS'" in ENTITY
    assert 'pit_valid_from' in ENTITY and 'pit_valid_to' in ENTITY
