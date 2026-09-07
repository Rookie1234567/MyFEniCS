"""Public profile registration and worker routing without numerical assembly."""

import json
from pathlib import Path

import pytest

from scripts.run_case import main
from src.io import load_and_resolve
from src.io.execution_plan import build_execution_plan, dry_run_payload, method_adapter_available
from src.runners.task038_input_worker import _dispatch_resolved_payload


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('name', ['original_13p5nm_p6h10.dat',
                                 'original_13p5nm_p6h10_p4_reference.dat',
                                 'original_13p5nm_p6h10_p6smooth_p4ref_p6smooth.dat'])
def test_real_dat_public_plan_dry_run_and_worker_route(name, tmp_path, monkeypatch, capsys):
    from src.runners import physical_intermediate

    path = ROOT / 'input/task39extra' / name
    specification = load_and_resolve(path)
    plan = build_execution_plan(specification, tmp_path, source_sha='a'*40)
    assert plan.adapter_available and plan.adapter_identity == 'task038.full3d_iterative'
    assert 'src.runners.task038_input_worker' in plan.argv
    assert dry_run_payload(specification)['resolved_method_adapter']['status'] == 'connected'
    assert main([str(path), '--dry-run']) == 0
    assert json.loads(capsys.readouterr().out)['resolved_method_adapter']['status'] == 'connected'
    calls = []
    def capture(payload, directory, *, source_sha):
        calls.append((payload, directory, source_sha))
        return {'passed': True}
    monkeypatch.setattr(physical_intermediate, 'run_physical_intermediate', capture)
    payload = specification.as_jsonable()
    assert _dispatch_resolved_payload(payload, expected_method='full3d_iterative',
        output_directory=tmp_path, expected_source_sha='a'*40) == (0, [])
    assert calls == [(payload, tmp_path, 'a'*40)]
    assert calls[0][0]['solver']['preconditioner'] == specification.solver['preconditioner']


def test_ordinary_and_unknown_profiles_remain_unavailable(tmp_path):
    old = load_and_resolve(ROOT / 'input/templates/full3d_iterative_example.dat')
    assert not build_execution_plan(old, tmp_path, source_sha='a'*40).adapter_available
    assert dry_run_payload(old)['resolved_method_adapter']['status'] == 'unavailable'
    for profile in (None, 'unknown_profile', 'physical_intermediate_p4_reference_v2'):
        assert not method_adapter_available('full3d_iterative', preconditioner=profile)
        payload = old.as_jsonable()
        payload['solver']['preconditioner'] = profile
        code, errors = _dispatch_resolved_payload(payload, expected_method='full3d_iterative',
            output_directory=tmp_path, expected_source_sha='a'*40)
        assert code == 4 and errors
