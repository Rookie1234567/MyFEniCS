"""Actual common runner keeps the new retained adapter alive for physical output."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from src.runners import physical_p4_schur_v14 as v14
from src.test.test_physical_schur_v14_q4_mock import _Runtime, _Vec, _patch_q4_dependencies


@pytest.mark.parametrize("setup_failure", [False, True])
def test_one_setup_and_retained_krylov_pool_with_native_final_cleanup(tmp_path, monkeypatch, setup_failure):
    import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical
    import src.solvers.physical_balanced_fgmres as old_solver

    _Vec.live = []
    calls = _patch_q4_dependencies(monkeypatch, False)
    mocked_old_run = old_solver.run_balanced_fgmres
    monkeypatch.setattr(old_solver, "run_balanced_fgmres", lambda *_a, **_k: pytest.fail("closed full-space solver"))
    runtime = _Runtime(tmp_path)
    runtime.time_policy = "observe_only"
    runtime.workflow_reserved_seconds = 43200.0
    runtime.contract["resources"]["stage_budgets"] = {
        "X2_ORIGINAL": {"solve_seconds": 43200, "workflow_seconds": 43200}}
    common = {"cfg": SimpleNamespace(cell_notch=None), "fine": {
        "mode_sha256": "m", "dtn_action": SimpleNamespace(carrier=SimpleNamespace(global_rows=4)),
        "physical_action": SimpleNamespace(apply=lambda s, t: t.array.__setitem__(slice(None), s.array))}}
    resolved = {"provenance": {"input_sha256": "i" * 64, "physical_model_sha256": "p" * 64}}
    life = {"p4": False, "p6": False, "setup": 0, "solve": 0, "destroy": 0}

    @contextmanager
    def stack(*_args, **_kwargs):
        life["p4"] = True
        try:
            yield {"fint": object(), "inverse": SimpleNamespace(solve_count=0),
                   "internal_factor_count": 0, "stack_facts": {"global_condensed_factor_count": 1},
                   "operator_identity": {"ordered_mode_sha256": "m"}, "operator_identity_sha256": "o" * 64}
        finally:
            life["p4"] = False

    class Adapter:
        identity = {"global_s6_aij": False}

        def __init__(self, _r, _c, _resolved, rhs, pc, **_kwargs):
            life["p6"] = True
            self.full_rhs, self.pc = rhs, pc
            self.rhs = _Vec([1.0, 2.0])

        def setup_checks(self):
            life["setup"] += 1
            assert not any(row[0] == "begin_outer_solve" for row in runtime.events)
            if setup_failure:
                raise ValueError("injected X1 identity bug")

        def solve(self, **callbacks):
            life["solve"] += 1
            assert runtime.workspace["x2_outer_krylov"] == 74 * 2 * 16
            return mocked_old_run(self.full_rhs, lambda x: x.copy(), self.pc, **callbacks)

        def facts(self):
            return {"retained_dimension": 2}

        def destroy(self):
            life["destroy"] += 1
            life["p6"] = False
            self.rhs.destroy()

    def recover(*_args, **_kwargs):
        assert life["p6"] and life["p4"]
        return {"R": 0.3}

    monkeypatch.setattr(physical, "recover_p0_outputs", recover)
    kwargs = dict(stage="X2_ORIGINAL", predecessor={}, stack_factory=stack, outer_adapter_factory=Adapter)
    if setup_failure:
        with pytest.raises(ValueError, match="X1 identity"):
            v14._v14_q4_q5_fullspace(runtime, common, resolved, **kwargs)
    else:
        result = v14._v14_q4_q5_fullspace(runtime, common, resolved, **kwargs)
        assert result["official_result"]
        assert calls["reference"] == 1
        assert result["solver"]["retained_outer"]["retained_dimension"] == 2
    assert life == {"p4": False, "p6": False, "setup": 1, "solve": int(not setup_failure), "destroy": 1}
    assert runtime.workspace == {}
    assert all(value.destroyed for value in _Vec.live)
