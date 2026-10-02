"""Compact checker rejects forged qualification and violated MR inequality."""
import json,shutil
from pathlib import Path
import pytest
from benchmarks.check_task042_p1_image_records import check

@pytest.fixture
def records(tmp_path):
    root=Path(__file__).resolve().parents[2]/'docs/task042_neural_coarse_inverse/outcomes/records'
    for path in root.glob('*_v23.*'):
        if path.suffix in ('.json','.csv'):shutil.copyfile(path,tmp_path/path.name)
    return tmp_path

def test_recompute_original_equation_and_physics(records):
    result=check(records)
    assert result['image_qualified'] and result['PC_qualified']
    assert result['states']==6 and result['passed']==0

def test_reject_forged_complete_pass(records):
    path=records/'candidate_comparison_v23.csv'
    text=path.read_text();path.write_text(text.replace('False,False,UNQUALIFIED','False,True,UNQUALIFIED',1))
    with pytest.raises(AssertionError):check(records)

def test_reject_same_space_minimum_residual_violation(records):
    path=records/'coarse_compare_v23.json';row=json.loads(path.read_text())
    r=row['comparison']['warm'];r['MR_residual_norm']=r['G_residual_norm']+r['original_residual_norm']
    path.write_text(json.dumps(row))
    with pytest.raises(AssertionError):check(records)
