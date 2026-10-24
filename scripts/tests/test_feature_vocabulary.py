from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_feature_vocabulary_seed import build,describe,semantic_hash,explain_formula
from sync_feature_vocabulary import validate_seed

def sample():
    return dict(feature_table='Feature_03_Stock_Broker_Daily_INDEX',feature_column='broker_concentration_hhi',
     version='v1',grain='ticker × board × date',definition='NULL by policy',calculation='NULL by policy',
     unit='HHI ratio 0-1',null_rule='Always NULL by policy',lookback_window='1 session',minimum_history='1 session',
     source_tables='Feature_02_Broker_Rolling_INDEX',source_columns='net_value_1d',
     analytical_interpretation='Not calculated for index',misuse_warning='Do not impute zero',ordinal_position=23)

def test_index_hhi_policy_is_explicit_not_zero():
    entry=build(sample())
    assert entry['formula']=='NULL (kebijakan INDEX)'
    assert 'Sengaja NULL' in entry['definition']

@pytest.mark.parametrize('field',['calculation','unit','null_rule','lookback_window','source_tables','definition'])
def test_source_semantic_drift_changes_hash_without_version_change(field):
    row=sample();changed=deepcopy(row);changed[field]+=' changed'
    assert row['version']==changed['version']
    assert semantic_hash(row)!=semantic_hash(changed)

def test_unknown_column_does_not_get_invented_definition():
    with pytest.raises(ValueError,match='No reviewed vocabulary template'):
        describe(6,'unknown_foreign_signal')

def test_percentage_point_change_and_percent_growth_have_different_meanings():
    share=describe(6,'foreign_buy_freq_share_change_5d_vs_prev20d')
    size=describe(6,'foreign_buy_value_per_freq_change_5d_vs_prev20d')
    assert 'poin persentase' in share[2]
    assert 'dalam persen' in size[2]

def test_high_is_highest_close_not_intraday_high():
    label,definition,meaning,_=describe(1,'high_20d')
    assert label=='Highest Close 20D'
    assert 'Penutupan tertinggi' in definition and 'bukan intraday high' in meaning

def test_frequency_coverage_is_source_rows_not_trade_count():
    assert describe(6,'buy_freq_known_rows')[3]=='quality'
    assert 'bukan jumlah transaksi' in describe(6,'buy_freq_known_rows')[2]

def test_partial_reviewed_inventory_rejected_before_create():
    with pytest.raises(RuntimeError,match='exactly cover'):
        validate_seed([build(sample())],[sample()])

def test_compact_formula_defines_cash_and_frequency_aliases():
    f=explain_formula('FB / BF',6,'index')
    assert 'FB=foreign_buy_1d' in f and 'BF=foreign_buy_freq_1d' in f

def test_lot_alias_names_actual_detail_source_not_a_nonexistent_feature6_field():
    f=explain_formula('FBL / BF',6,'index')
    assert 'Feature_05_Foreign_Domestic_Broker_Detail_INDEX.buy_lots' in f

def test_remote_runpy_entrypoint_imports_its_sibling_without_caller_path_setup():
    path=Path(__file__).resolve().parents[1]/'sync_feature_vocabulary.py'
    r=subprocess.run([sys.executable,'-I','-c',"import runpy,sys; runpy.run_path(sys.argv[1],run_name='entrypoint_import')",str(path)],capture_output=True,text=True)
    assert r.returncode==0,r.stderr
