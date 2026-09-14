"""Exercise real control orchestration and atomic packets using tiny actions."""

from contextlib import contextmanager
import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.physical_intermediate_profile import CELL_CONDENSED_EXACT_PROFILE, profile_facts
from src.runners import physical_p4_cell_condensed_v18 as worker
from src.runners import physical_p4_schur_v14 as old
from src.solvers import p4_cell_condensed_inverse as core
from src.test.test_physical_schur_v14_q4_mock import _Vec
from src.test.test_task39extra_v18_stack_fixture import TinyRuntime


@pytest.mark.parametrize("fail_second_field", [False, True])
def test_control_saves_each_completed_rhs_before_extra_calls(tmp_path, monkeypatch, fail_second_field):
    runtime = TinyRuntime()
    runtime.directory = runtime.root = tmp_path
    runtime.source_sha = "a" * 40
    runtime.contract = profile_facts(CELL_CONDENSED_EXACT_PROFILE)
    factor = SimpleNamespace(solve_calls=0, numeric_calls=1, symbolic_calls=1,
                             info=lambda *_: {})
    cond = SimpleNamespace(interior_lu_by_class={"one": (np.eye(1), np.array([0]))},
                           trace_constraints=SimpleNamespace(owned_active_original_dofs=np.array([0, 1])),
                           matrix=object())
    inverse = SimpleNamespace(condensed=cond, _slave_original=np.array([], np.int64),
                              matrix_identity={"csr_sha256": "a" * 64}, last_port_solution=np.zeros(1),
                              last_audit={})
    def apply(rhs):
        factor.solve_calls += 1
        inverse.last_audit = {"factor_solve_count": factor.solve_calls}
        return _Vec(rhs.array / 2)
    inverse.apply = apply
    @contextmanager
    def stack(*_args, **_kwargs):
        yield {"inverse": inverse, "factor": factor, "condensed": cond,
               "operator_identity": {}, "stack_facts": {"factor": {},
                   "matrix_identity_after_factor": inverse.matrix_identity}}
    reviewed = []
    for i, stem in enumerate(worker._RHS_STEMS):
        reviewed.append(dict(stem=stem, logical_rhs=i, rhs=np.array([1+i, 2-i], complex),
                             reference_solution=np.array([1+i, 2-i], complex)/2,
                             **{k: "fixture" for k in ("input_json", "input_npz", "input_sha256",
                                "input_npz_sha256", "g_sha256", "reference_json", "reference_npz",
                                "reference_json_sha256", "reference_npz_sha256")}))
    fields = []
    def field(*_args):
        fields.append(True)
        if fail_second_field and len(fields) == 2:
            raise RuntimeError("injected metric failure")
        return [{"field_l2_relative": 0., "scaled_curl_relative": 0.}]
    def residual(_common, rhs, _solution, _alpha):
        zero = np.zeros_like(rhs.array)
        return {"native_A4_relative": 0.}, {"relative": 0.}, {
            "native_A4_residual": zero, "native_action": rhs.array.copy(),
            "augmented_top_residual": zero, "port_residual": np.zeros(1),
            "native_identity_reconstructed": zero}
    monkeypatch.setattr(worker, "cell_condensed_stack", stack)
    monkeypatch.setattr(worker, "_native_residual_packet", residual)
    monkeypatch.setattr(worker, "_controls_after_solve", lambda *_a, **_k: {})
    monkeypatch.setattr(old, "_prepare_reviewed_rhs", lambda *_: reviewed)
    monkeypatch.setattr(old, "_storage_rhs", lambda _space, values: _Vec(values))
    monkeypatch.setattr(old, "_field_metrics", field)
    monkeypatch.setattr(core, "petsc_csr_content_identity", lambda _: inverse.matrix_identity)
    common = {"levels": {"spaces": {4: object()}}}
    if fail_second_field:
        with pytest.raises(RuntimeError, match="injected metric failure"):
            worker._run_v18_p4_control(runtime, common, {}, root=tmp_path,
                                       stage="U2_EXACT_CONTROL", backend="exact")
        progress = json.loads((tmp_path / "v18_control_progress.json").read_text())
        assert len(progress["solve_records"]) == 1
        assert factor.solve_calls == 2
        assert not (tmp_path / "additional_rhs").exists()
    else:
        result = worker._run_v18_p4_control(runtime, common, {}, root=tmp_path,
                                            stage="U2_EXACT_CONTROL", backend="exact")
        assert result["stage_pass"]
        assert factor.solve_calls == 6
        assert len(result["solve_records"]) == len(result["additional_solve_records"]) == 3
        packet = json.loads((tmp_path / "rhs_packets" / f"{worker._RHS_STEMS[2]}.json").read_text())
        assert "alpha" in packet and "g" in packet and "x_storage" in packet
        assert packet["solve"]["packet_save_seconds"] >= 0
        assert any(event[0] == "u2_main_rhs_window_complete" for event in runtime.events)
    assert runtime.workspace == {}
