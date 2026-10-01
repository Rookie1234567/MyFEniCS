from __future__ import annotations

from pathlib import Path

from src.geometry.task40_nonseparable_plan import TASK40_F1_REFERENCE_METRIC_RUN_ID
from src.io.input_validation import load_and_resolve
from src.io.physical_intermediate_profile import (
    A4_TENSOR_H6_PROFILES,
    FUSED_KERNEL_PROFILES,
    PROFILES,
    TASK40_0P7NM_PROFILE,
    TASK40_REFERENCE_METRIC_PROFILE,
    profile_facts,
)
from src.runners.physical_dual_cell_condensed_lowmem_v20 import (
    _p6_raw_tensor_candidate_type,
)
from src.runners.task038_full3d_iterative import run_full3d_iterative


ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input/task40extra_0p7nm_engineering"
F1_INPUT = INPUT_DIR / "nonseparable_g1_p6_q4_reference_metric_f1.dat"
G1_INPUT = INPUT_DIR / "nonseparable_g1_p6_q4_review_v1.dat"


def test_reference_metric_profile_is_opt_in_and_inherits_task40_gates():
    assert TASK40_REFERENCE_METRIC_PROFILE in PROFILES
    assert TASK40_REFERENCE_METRIC_PROFILE in A4_TENSOR_H6_PROFILES
    assert TASK40_REFERENCE_METRIC_PROFILE in FUSED_KERNEL_PROFILES

    base = profile_facts(TASK40_0P7NM_PROFILE)
    candidate = profile_facts(TASK40_REFERENCE_METRIC_PROFILE)
    assert candidate["identity"] == TASK40_REFERENCE_METRIC_PROFILE
    assert candidate["resources"] == base["resources"]
    assert candidate["gates"]["task40_zero_swap_required"] is True
    assert candidate["route_selection"]["p6_raw_tensor_candidate"] == (
        "task40extra_p6_reference_integrals_exact_metric_v1"
    )


def test_f1_input_is_g1_m0_with_same_physical_model_identity():
    g1 = load_and_resolve(G1_INPUT)
    f1 = load_and_resolve(F1_INPUT)
    payload = f1.as_jsonable()

    assert payload["run_id"] == TASK40_F1_REFERENCE_METRIC_RUN_ID
    assert payload["comparison_group"] == "task40extra_0p7nm_nonseparable_n0_n6"
    assert payload["solver"]["preconditioner"] == TASK40_REFERENCE_METRIC_PROFILE
    assert f1.physical_model_sha256 == g1.physical_model_sha256


def test_f1_worker_dispatch_and_raw_tensor_candidate_are_task40_specific(
    monkeypatch, tmp_path
):
    payload = load_and_resolve(F1_INPUT).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        captured.update(kwargs)
        return {"dispatched": True}

    import src.runners.physical_dual_cell_condensed_lowmem_v20 as physical_worker

    monkeypatch.setattr(
        physical_worker, "_run_physical_dual_cell_condensed_lowmem", fake_worker
    )
    result = run_full3d_iterative(payload, tmp_path, source_sha="unit-test-sha")

    assert result == {"dispatched": True}
    assert captured["profile_identity"] == TASK40_REFERENCE_METRIC_PROFILE
    assert captured["batch_identity"] == TASK40_F1_REFERENCE_METRIC_RUN_ID
    assert _p6_raw_tensor_candidate_type(TASK40_REFERENCE_METRIC_PROFILE).__name__ == (
        "Task40ExtraP6ReferenceMetricCandidate"
    )
    assert _p6_raw_tensor_candidate_type(TASK40_0P7NM_PROFILE).__name__ == (
        "Task39ExtraP6RawTensorCandidate"
    )
