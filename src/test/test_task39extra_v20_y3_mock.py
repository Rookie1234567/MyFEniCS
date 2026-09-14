"""Exercise the actual Y3 orchestration with bounded non-PDE components."""

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners import physical_p4_schur_v14 as worker
from src.test.test_physical_schur_v14_q4_mock import (
    _PC, _Runtime, _Vec, _patch_q4_dependencies,
)


@pytest.mark.parametrize("failure", [None, "before_release", "after_release"])
def test_actual_y3_orchestration_gates_release_and_official_output(tmp_path, monkeypatch, failure):
    from src.solvers import fullspace_same_mesh_hcurl_pmg_physical as physical
    from src.solvers import physical_balanced_fgmres as fgmres

    _Vec.live = []
    _patch_q4_dependencies(monkeypatch, False)
    runtime = _Runtime(tmp_path)
    runtime.time_policy = "observe_only"
    runtime.contract["resources"]["stage_budgets"]["Y3_ORIGINAL"] = {
        "workflow_seconds": 43200, "solve_seconds": 43200,
    }
    order = []
    state = {"solve_finished": False, "native_count": 0, "pc_destroyed": False,
             "p6_released": False, "p4_released": False}
    underlying_marker = runtime.marker

    def marker(name, facts=None):
        order.append(name)
        underlying_marker(name, facts)

    runtime.marker = marker

    def native(source, target):
        target.array[:] = source.array
        if state["solve_finished"]:
            state["native_count"] += 1
            phase = "before_release" if state["native_count"] == 1 else "after_release"
            order.append("native_" + phase)
            if failure == phase:
                target.array[:] = 0

    common = {"cfg": SimpleNamespace(cell_notch=None), "fine": {
        "mode_sha256": "m", "physical_action": SimpleNamespace(apply=native),
        "dtn_action": SimpleNamespace(carrier=SimpleNamespace(global_rows=4)),
    }}
    resolved = {"provenance": {"input_sha256": "i" * 64, "physical_model_sha256": "p" * 64}}

    base_stack = worker._v14_interface_live_stack

    @contextmanager
    def stack_factory(*args, **kwargs):
        with base_stack(*args, **kwargs) as stack:
            def release():
                assert state["pc_destroyed"] and state["p6_released"]
                state["p4_released"] = True
                order.append("p4_release")
                return {"status": "RELEASED"}
            stack.update(release_after_final_residual=release,
                         stack_facts={"schema": "mock"}, internal_factor_count=0,
                         inverse=SimpleNamespace(solve_count=0))
            yield stack

    @contextmanager
    def balanced_adapter(*_args, **_kwargs):
        pc = _PC()
        def cleanup():
            state["pc_destroyed"] = True
            order.append("pc_destroy")
            pc.destroy()
            runtime._deferred_balanced_cleanup = None
        try:
            yield pc, {"h6": SimpleNamespace(apply_count=0), "light_facts": {}}
        finally:
            runtime._deferred_balanced_cleanup = cleanup

    monkeypatch.setattr(worker, "_v14_balanced_adapter", balanced_adapter)

    class Adapter:
        identity = {"fixture": True}
        checks = {"status": "PASS"}
        _final_packet_saved = False

        def __init__(self, _runtime, _common, _resolved, rhs, pc, **_kwargs):
            self.full_rhs, self.pc = rhs, pc
            self.rhs = rhs.duplicate()

        def setup_checks(self):
            order.append("setup_checks")

        def solve(self, **kwargs):
            def action(source):
                target = source.duplicate()
                native(source, target)
                return target
            result = fgmres.run_balanced_fgmres(self.full_rhs, action, self.pc, **kwargs)
            result["final_evaluation"] = dict.fromkeys((
                "port_closure_relative", "internal_residual_relative",
                "native_identity_relative", "schur_port_identity_relative"), 0.0)
            self._final_packet_saved = True
            marker("v20_complete_field_packet_saved")
            state["solve_finished"] = True
            return result

        def release_after_final_residual(self):
            assert self._final_packet_saved and state["pc_destroyed"]
            state["p6_released"] = True
            order.append("p6_release")
            self.destroy()
            return {"status": "RELEASED"}

        def facts(self):
            return {"fixture": True}

        def destroy(self):
            if self.rhs is not None:
                self.rhs.destroy()
                self.rhs = None
            self.pc = None

    def official(_bundle, solution, _directory, **kwargs):
        assert state["p4_released"] and state["p6_released"] and state["pc_destroyed"]
        assert state["native_count"] == 2
        assert kwargs["jit_options"] == {"cache_dir": "fixture-cache"}
        np.testing.assert_array_equal(solution.array, [1., 2., 3., 4.])
        order.append("official")
        return {"R": 0.3}

    monkeypatch.setattr(physical, "recover_p0_outputs", official)

    def run():
        return worker._v14_q4_q5_fullspace(
            runtime, common, resolved, stage="Y3_ORIGINAL", predecessor={},
            stack_factory=stack_factory, outer_adapter_factory=Adapter,
            release_after_final_residual=True,
            official_jit_options={"cache_dir": "fixture-cache"},
        )

    if failure == "before_release":
        with pytest.raises(worker.V20ReleaseGateStop):
            run()
        assert "official" not in order and "p4_release" not in order
        assert "v20_release_gate_failed" in order
    else:
        result = run()
        assert result["official_result"] is (failure is None)
        chain = ("v20_complete_field_packet_saved", "native_before_release",
                 "y3_independent_final_residual_complete", "pc_destroy", "p6_release",
                 "p4_release", "native_after_release", "v20_post_release_final_residual_complete")
        assert [order.index(name) for name in chain] == sorted(order.index(name) for name in chain)
        if failure is None:
            assert order.index("official") > order.index(chain[-1])
        else:
            assert "official" not in order
            assert result["post_release_explicit_relative_residual"] == 1.0
    assert all(vector.destroyed for vector in _Vec.live)
    assert runtime.workspace == {}
    assert runtime._deferred_balanced_cleanup is None
