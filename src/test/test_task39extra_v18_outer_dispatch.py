"""Exercise the actual outer runner with the new owning stack boundary."""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from src.runners import physical_p4_schur_v14 as v14
from src.test.test_physical_schur_v14_q4_mock import (
    _Runtime, _Vec, _patch_q4_dependencies,
)


@pytest.mark.parametrize("stage", ["U4_ORIGINAL", "U4_EXACT_FALLBACK", "U5_NOTCH"])
@pytest.mark.parametrize("fail", [False, True])
def test_new_stack_lives_through_final_evaluation(tmp_path, monkeypatch, stage, fail):
    import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical

    _Vec.live = []
    calls = _patch_q4_dependencies(monkeypatch, fail)
    runtime = _Runtime(tmp_path)
    runtime.time_policy = "observe_only"
    runtime.workflow_reserved_seconds = 43200.0
    runtime.contract["resources"].update(
        pc_soft_seconds=0, pc_hard_seconds=0,
        stage_budgets={stage: {"solve_seconds": 43200, "workflow_seconds": 43200}},
    )
    common = {
        "cfg": SimpleNamespace(cell_notch=(
            "positive_x_middle_y_z40_80" if stage == "U5_NOTCH" else None)),
        "fine": {
            "mode_sha256": "m",
            "dtn_action": SimpleNamespace(carrier=SimpleNamespace(global_rows=4)),
            "physical_action": SimpleNamespace(
                apply=lambda source, target: target.array.__setitem__(slice(None), source.array)),
        },
    }
    resolved = {"provenance": {"input_sha256": "i" * 64, "physical_model_sha256": "p" * 64}}
    lifecycle = {"alive": False, "entered": 0, "destroyed": 0, "postprocess": 0}

    @contextmanager
    def new_stack(_runtime, _common, _resolved, *, stage):
        lifecycle["alive"] = True
        lifecycle["entered"] += 1
        try:
            yield {
                "fint": object(), "internal_factor_count": 0,
                "operator_identity": {"ordered_mode_sha256": "m", "stage": stage},
                "operator_identity_sha256": "o" * 64,
                "stack_facts": {"retain_through_postprocess_v18": True,
                                "global_condensed_factor_count": 1},
            }
        finally:
            lifecycle["alive"] = False
            lifecycle["destroyed"] += 1

    def old_stack_forbidden(*_args, **_kwargs):
        pytest.fail("V18 dispatched the closed macro/interface stack")

    def recover(*_args, **_kwargs):
        assert lifecycle["alive"]
        assert lifecycle["destroyed"] == 0
        lifecycle["postprocess"] += 1
        return {"R": 0.3}

    monkeypatch.setattr(v14, "_v14_interface_live_stack", old_stack_forbidden)
    monkeypatch.setattr(physical, "recover_p0_outputs", recover)
    result = v14._v14_q4_q5_fullspace(
        runtime, common, resolved, stage=stage,
        predecessor={"required_stage": "U2_EXACT_CONTROL", "qualified": True},
        stack_factory=new_stack,
    )
    assert lifecycle == {"alive": False, "entered": 1, "destroyed": 1,
                         "postprocess": 0 if fail else 1}
    assert calls["checkpoints"] == [0, 32, 64]
    assert result["official_result"] is (not fail)
    assert result["interface_stack"]["retain_through_postprocess_v18"]
    assert result["solver"]["ksp_create_count"] == 1
    assert result["solver"]["restart"] == 32
    assert result["solver"]["max_it"] == 2048
    assert result["time_policy"] == "observe_only"
    assert runtime.workspace == {}
    assert all(vector.destroyed for vector in _Vec.live)
