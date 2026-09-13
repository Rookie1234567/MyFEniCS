"""Q6 must preserve incomplete evidence and independent cost/memory quantities."""

import json
from types import SimpleNamespace

import pytest

from src.runners import physical_p4_schur_v14 as runner
from src.test.test_physical_schur_v14_evidence import _predecessor_fixture, _resource_row


def _runtime(tmp_path, ledger, monkeypatch):
    path = tmp_path/'ledger.json'
    path.write_text(json.dumps(ledger))
    monkeypatch.setattr(runner, '_save_packet', lambda *args, **kwargs: {'path': 'synthetic_packet'})
    return SimpleNamespace(_ledger_path=path, directory=tmp_path,
                           marker=lambda *args: None)


def test_q6_unsettled_io_attempt_is_neither_zero_cost_nor_method_failure(tmp_path, monkeypatch):
    ledger = dict(batch_identity='review_v14', elapsed_seconds=0., stages={'Q0_CORE': {
        'active_attempt': 0, 'attempts': [dict(source_sha='a'*40, reserved_seconds=600.,
            run_directory=str(tmp_path/'interrupted'), status='RESERVED')]}})
    runtime = _runtime(tmp_path, ledger, monkeypatch)
    before = runtime._ledger_path.read_bytes()
    result = runner._q6_finalize(runtime)
    assert runtime._ledger_path.read_bytes() == before
    assert result['status'] == 'Q6_EVIDENCE_INCOMPLETE'
    assert not result['stage_pass'] and not result['official_result']
    assert result['ledger']['unsettled_cost_is_not_zero']
    assert result['stages']['Q0_CORE']['status'] == 'unsettled_attempt'
    assert result['stages']['Q0_CORE']['cost']['settled_seconds'] is None
    assert result['answers']['interface_approximation']['status'] == 'EVIDENCE_INCOMPLETE'
    assert result['answers']['next_choice']['status'] == 'COMPLETE_EXISTING_REVIEW_NO_NEW_METHOD'


@pytest.mark.parametrize('q2_rss, expected', [
    (540, 'MEANINGFUL_FIXED_CASE_MEMORY_REDUCTION'),
    (570, 'SMALL_OBSERVED_REDUCTION'),
    (600, 'NO_OBSERVED_MEMORY_REDUCTION'),
])
def test_q6_memory_categories_do_not_turn_q3_pass_into_full_p6_pass(tmp_path, monkeypatch, q2_rss, expected):
    ledger = dict(batch_identity='review_v14', elapsed_seconds=30., stages={})
    for stage, rss in [('Q1_FULL_DIRECT', 600), ('Q2_SCHUR_DIRECT', q2_rss), ('Q3_INTERFACE_CONTROL', 500)]:
        directory = tmp_path/stage
        (directory/'watchdog').mkdir(parents=True)
        worker = dict(source_sha='a'*40, abi={'scalar': 'complex128'}, rhs=['same three RHS'],
                      solve_records=[], official_result=False, stage_pass=True)
        (directory/'physical_p4_schur_v14_summary.json').write_text(json.dumps(worker))
        (directory/'run_summary.json').write_text(json.dumps({'workflow_clock_interval': {'budget_seconds': 10.}}))
        (directory/'watchdog/summary.json').write_text(json.dumps(dict(
            sampled_process_tree_rss_peak_bytes=rss, sampled_process_tree_pss_peak_bytes=rss-50,
            descendants_cleared=True, remaining_child_pids=[])))
        resource = _resource_row()
        resource.update(inventory_used_bytes=40, inventory_peak_bytes=40 if stage == 'Q1_FULL_DIRECT' else 50)
        (directory/'v14_worker_resources.jsonl').write_text(json.dumps(resource))
        ledger['stages'][stage] = dict(active_attempt=None, attempts=[dict(
            source_sha='a'*40, run_directory=str(directory), reserved_seconds=3600., settled_seconds=10.)])
    runtime = _runtime(tmp_path, ledger, monkeypatch)
    # Admission itself is independently exercised by the raw parent/RHS tests.
    monkeypatch.setattr(runner, '_v14_settled_stage_gate', lambda *args: {'qualified': True, 'reason': 'qualified'})
    result = runner._q6_finalize(runtime)
    exact = result['answers']['exact_schur_memory']
    assert exact['status'] == expected
    assert exact['resident_inventory_ratio'] == 1.25  # Keep the differing observation visible.
    assert result['answers']['interface_approximation']['Q3_admission']
    assert result['answers']['interface_approximation']['status'] == 'EVIDENCE_INCOMPLETE'
    assert result['answers']['full_p6'] == {'original_qualified': False, 'notch_qualified': False}
    assert not result['stage_pass']


def test_exact_stage_gate_recomputes_original_rhs_normalized_A4_error(tmp_path):
    worker, write, _ = _predecessor_fixture(tmp_path)
    run = tmp_path/'original'
    stage = 'Q1_FULL_DIRECT'
    source = worker['source_sha']
    mode = worker['operator_identity']['ordered_mode_sha256']
    resolved = json.loads((run/'resolved_config.json').read_text())
    original = resolved['provenance']['physical_model_sha256']
    stems = [row['stem'] for row in runner._Q1_Q2_RHS]
    worker.update(stage=stage, solve_records=[dict(
        stem=stem, augmented_residual={'native_A4_norm': 1e-12, 'rhs_norm': 1.},
        refinements=[], field_metrics={'fields': {
            name: {'absolute_error_norm': 1e-10, 'reference_norm': 1.}
            for name in ('L2', 'scaled_curl')}}) for stem in stems])
    write('reviewed_rhs_identity.json', dict(source_sha=source, ordered_stems=stems,
        records=[dict(fresh_mode_sha256=mode, fresh_physical_model_sha256=original,
                      fresh_A4y_relative_to_saved=1e-12) for stem in stems]))
    write('physical_p4_schur_v14_summary.json', worker)
    manifest = json.loads((run/'run_manifest.json').read_text())
    manifest['solver']['stage'] = resolved['solver']['stage'] = stage
    manifest['resolved_config_sha256'] = write('resolved_config.json', resolved)
    write('run_manifest.json', manifest)
    ledger_path = tmp_path/'ledger.json'
    ledger = json.loads(ledger_path.read_text())
    ledger['stages'][stage] = ledger['stages'].pop('Q4_ORIGINAL')
    ledger_path.write_text(json.dumps(ledger))
    runtime = SimpleNamespace(_ledger_path=ledger_path)
    assert runner._v14_settled_stage_gate(runtime, stage)['qualified']
    worker['solve_records'][0]['augmented_residual']['rhs_norm'] = 1e-4
    write('physical_p4_schur_v14_summary.json', worker)
    assert not runner._v14_settled_stage_gate(runtime, stage)['qualified']
