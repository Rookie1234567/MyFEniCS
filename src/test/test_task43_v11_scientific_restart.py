from __future__ import annotations

import copy
from functools import wraps
from functools import lru_cache
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import compare_round1_candidate as comparison
from benchmarks.task43_hp_adaptivity import candidate_checkpoints
from benchmarks.task43_hp_adaptivity import h100_anchor
from benchmarks.task43_hp_adaptivity import round1_candidates
from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    task43_v11_partial_terminal_record,
    write_v11_primary_field_sample,
    write_v11_primary_packet,
)
from src.postprocessing.physical_field_comparison import build_common_volume_quadrature


CONTRACT_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
)
SELECTION_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
)
ACCEPTANCE_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _raw_vectors(*, failed_condensed: bool = False) -> dict[str, np.ndarray]:
    residual = np.asarray([1.0 if failed_condensed else 0.0], dtype=np.complex128)
    return {
        "independent_A6_independent_active_residual_trace": np.zeros(1, dtype=np.complex128),
        "independent_A6_independent_active_residual_cell_interior": np.zeros(1, dtype=np.complex128),
        "independent_A6_independent_active_modal_lower_solver_gauge": np.zeros(612, dtype=np.complex128),
        "independent_A6_independent_active_rhs_trace": np.ones(1, dtype=np.complex128),
        "independent_A6_independent_active_rhs_cell_interior": np.ones(1, dtype=np.complex128),
        "full_active_reduced_trace_dtn_residual_Ax_minus_b_owned": -np.pad(residual, (0, 612)),
        "full_active_reduced_trace_dtn_residual_trace_metric_action": -residual.copy(),
        "full_active_reduced_trace_dtn_rhs_owned": np.ones(613, dtype=np.complex128),
        "full_active_reduced_trace_dtn_solution_owned": np.ones(613, dtype=np.complex128),
        "full_active_reduced_trace_dtn_rhs_trace_metric_action": np.zeros(1, dtype=np.complex128),
        "full_active_active_full_rhs": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
        "full_active_active_full_solution": np.zeros(3, dtype=np.complex128),
        "full_active_eliminated_active_interior_residual": np.zeros(3, dtype=np.complex128),
        "recovered_active_full_rhs_owned": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
        "recovered_active_full_solution_owned": np.zeros(3, dtype=np.complex128),
        "returned_trace_dtn_rhs": np.ones(613, dtype=np.complex128),
        "returned_trace_dtn_solution": np.ones(613, dtype=np.complex128),
        "returned_trace_dtn_b_minus_Ax": np.pad(residual, (0, 612)),
        "independent_A6_independent_active_modal_lower_solver_gauge_rhs": np.zeros(612, dtype=np.complex128),
        "normal_before_normal_correction_rhs": np.ones(613, dtype=np.complex128),
        "normal_after_normal_correction_rhs": np.ones(613, dtype=np.complex128),
        "normal_before_normal_correction_residual_b_minus_Ax": np.ones(613, dtype=np.complex128),
        "normal_after_normal_correction_residual_b_minus_Ax": np.pad(residual, (0, 612)),
        "normal_before_normal_correction_solution": np.zeros(613, dtype=np.complex128),
        "normal_after_normal_correction_solution": np.ones(613, dtype=np.complex128),
    }


def _raw_gate_arguments() -> dict:
    return {
        "active_trace_rows": 1,
        "active_interior_rows": 1,
        "independent_fe_dofs": 2,
        "active_full_rows": 3,
        "full_active_scope": {
            "active_full_rows": 3,
            "reduced_trace_dtn_rows": 613,
            "reduced_trace_dtn_owned_range": [0, 613],
            "mpi_size": 1,
        },
        "independent_a6_scope": {
            "trace_rows": 1,
            "active_interior_rows": 1,
            "modal_lower_rows": 612,
        },
        "normal_correction_count": 1,
        "normal_converged_reason": 2,
        "normal_correction_status": "passed",
        "extra_correction_count": 0,
    }


class _ObserverVector:
    def __init__(self, values):
        self.values = np.asarray(values, dtype=np.complex128).copy()

    def duplicate(self):
        return _ObserverVector(np.zeros_like(self.values))

    def copy(self, other):
        other.values[...] = self.values

    def axpy(self, scale, other):
        self.values += scale * other.values

    def getArray(self, *, readonly=False):
        return self.values

    def destroy(self):
        return None


class _ObserverMatrix:
    def mult(self, vector, result):
        result.values[...] = vector.values

    def getSize(self):
        return (613, 613)


class _ObserverReached(Exception):
    pass


def _invoke_actual_v11_observer(
    tmp_path: Path,
    monkeypatch,
    *,
    phase: str,
    outcome: str,
) -> tuple[Path, dict, list[str], dict]:
    """Run `_run_impl` through its real nested observer with cheap solver edges."""

    contract_path = CONTRACT_PATH.resolve()
    contract = _contract()
    contract_sha = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    if phase == "A1_q3":
        candidate_id = "round10_p_up"
        plan_path = Path(
            next(
                item["path"]
                for item in contract["inputs"]
                if item["role"] == "R10_authority_plan"
            )
        ).resolve()
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        candidate_action = "p_up"
    else:
        candidate_id = "v11_r9_h8"
        plan_path = tmp_path / "v11_r9_h8.json"
        seed = contract["phases"]["P4"]["seed"]
        plan = {
            "task43_candidate": {
                "candidate_id": candidate_id,
                "action": "h_refine",
                "provenance": {
                    "v11_seed": {
                        key: seed[key]
                        for key in (
                            "global_cell_id",
                            "lower_nm",
                            "upper_nm",
                            "parent_degree",
                        )
                    },
                    "marked_global_cell_ids_source": "v11_predeclared_seed8",
                },
            },
            "marked_root_boxes": [seed["global_cell_id"]],
            "trace_degree": 3,
            "cell_interior_degree": 6,
            "variable_trace_from_cell_degrees": True,
            "allow_no_refinement": False,
        }
        plan_path.write_text(json.dumps(plan), encoding="utf-8")
        candidate_action = "h_refine"
    plan_sha = hashlib.sha256(plan_path.read_bytes()).hexdigest()
    selection_item = next(
        item for item in contract["inputs"] if item["role"] == "R9_selection_transition"
    )
    selection_path = (Path.cwd() / selection_item["path"]).resolve()
    accepted_identity = {
        "candidate_id": candidate_id,
        "action": candidate_action,
        "plan_path": str(plan_path),
        "plan_sha256": plan_sha,
        "accepted_parent_selection_sha256": selection_item["sha256"],
    }
    recovery_binding = {
        "manifest_path": str(tmp_path / "v12_execution_recovery_manifest.json"),
        "manifest_sha256": "a" * 64,
        "contract_sha256": contract_sha,
        "p2_source_id": "D1" if phase == "R9_H8" else None,
        "support_root": str(tmp_path / "D1") if phase == "R9_H8" else None,
        "output_root": str(tmp_path / "D1" / "plan_output") if phase == "R9_H8" else None,
        "plan_output_path": str(plan_path) if phase == "R9_H8" else None,
        "audit_path": str(tmp_path / "D1" / "plan_output/plans/v11_r9_h8.audit.json") if phase == "R9_H8" else None,
        "bundle_path": str(tmp_path / "D1" / "plan_output/plan_audit.json") if phase == "R9_H8" else None,
    }
    run_root = tmp_path / phase / "run"
    phase_file = tmp_path / phase / "watchdog.phase"
    identity = {
        "worker_pid": 91,
        "worker_start_ticks": 1,
        "tracer_pid": 92,
        "tracer_start_ticks": 1,
        "direct_watchdog_parent_verified": True,
        "tracer_descends_from_watchdog": True,
        "worker_tid_affinities": [{"tid": 91, "cpu_list": [1]}],
        "phase_path": str(phase_file),
    }

    class _Ledger:
        def __init__(self, *args, **kwargs):
            return None

        def set_phase(self, *args, **kwargs):
            return None

        def marker(self, *args, **kwargs):
            return None

    class _Topology:
        dim = 3

        def index_map(self, _dimension):
            return SimpleNamespace(size_global=1)

        def create_connectivity(self, *_args):
            return None

    mesh = SimpleNamespace(topology=_Topology())
    audit = {
        "status": "passed",
        "pass": True,
        "root_cell_count": 1,
        "leaf_cell_count": 1,
        "hanging_patch_count": 0,
        "cell_interior_degree_counts": {"p6": 1},
        "variable_trace_from_cell_degrees": True,
        "allow_no_refinement": False,
        "forest": {"closure_split_counts": {}},
    }
    mesh_data = SimpleNamespace(
        mesh=mesh,
        local_h_context=SimpleNamespace(audit=audit),
    )
    modes = [
        SimpleNamespace(side=side, m=m, n=n, polarization=polarization)
        for side, m, n, polarization in sorted(h100_anchor.R13_MODE_KEYS)
    ]
    returned = np.ones(613, dtype=np.complex128)
    full_raw = {
        "reduced_trace_dtn_residual_Ax_minus_b_owned": np.zeros(613, dtype=np.complex128),
        "reduced_trace_dtn_residual_trace_metric_action": np.zeros(1, dtype=np.complex128),
        "reduced_trace_dtn_rhs_owned": returned.copy(),
        "reduced_trace_dtn_solution_owned": returned.copy(),
        "reduced_trace_dtn_rhs_trace_metric_action": np.ones(1, dtype=np.complex128),
        "active_full_rhs": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
        "active_full_solution": np.zeros(3, dtype=np.complex128),
        "eliminated_active_interior_residual": np.zeros(3, dtype=np.complex128),
    }
    a6_raw = {
        "independent_active_residual_trace": np.asarray(
            [1.0 if outcome == "raw_failure" else 0.0], dtype=np.complex128
        ),
        "independent_active_residual_cell_interior": np.zeros(1, dtype=np.complex128),
        "independent_active_modal_lower_solver_gauge": np.zeros(612, dtype=np.complex128),
        "independent_active_rhs_trace": np.ones(1, dtype=np.complex128),
        "independent_active_rhs_cell_interior": np.ones(1, dtype=np.complex128),
    }
    normal_vectors = {
        "before_normal_correction_rhs": returned.copy(),
        "before_normal_correction_solution": np.zeros(613, dtype=np.complex128),
        "before_normal_correction_residual_b_minus_Ax": np.ones(613, dtype=np.complex128),
        "after_normal_correction_rhs": returned.copy(),
        "after_normal_correction_solution": returned.copy(),
        "after_normal_correction_residual_b_minus_Ax": np.zeros(613, dtype=np.complex128),
    }
    view = SimpleNamespace(
        ksp=SimpleNamespace(
            getPC=lambda: SimpleNamespace(getFactorSolverType=lambda: "mumps")
        ),
        config=SimpleNamespace(),
        goal_context={"modes": modes},
        field=object(),
        mesh_data=mesh_data,
        reduction=SimpleNamespace(
            degree_plan=SimpleNamespace(audit={"trace_degree_values": [3]}),
            system=SimpleNamespace(
                active_trace_rows=1,
                entity_map=SimpleNamespace(
                    active_cell_interior_rows=1,
                    active_rows=3,
                ),
            ),
        ),
        A=_ObserverMatrix(),
        b=_ObserverVector(returned),
        x=_ObserverVector(returned),
        full_active_residual={
            **{
                "raw_vectors": full_raw,
                "raw_vector_scope": {
                    "reduced_trace_dtn_rows": 613,
                    "reduced_trace_dtn_owned_range": [0, 613],
                    "mpi_size": 1,
                },
            },
            "linear_system_relative_residual": 0.0,
        },
        normal_correction_raw_vectors=normal_vectors,
        primal_solver_telemetry={
            "normal_correction_count": 1,
            "normal_correction_audit": {
                "status": "passed",
                "correction_ksp": {"converged_reason": 2},
            },
        },
        port_metrics={},
    )
    captured_fields: list[str] = []

    def fake_field_capture(
        _field,
        _mesh_data,
        _cfg,
        _comm,
        _reference_axes,
        _profile,
        *,
        sample_fields,
        on_sample,
        **_kwargs,
    ):
        captured_fields.append("begin")
        samples = {}
        sample = {
            "points_nm": np.zeros((1, 3)),
            "weights_nm3": np.ones(1),
            "E_total": np.ones((1, 3), dtype=np.complex128),
        }
        if sample_fields:
            on_sample(8, sample)
            samples["q8"] = sample
            if outcome == "q10_failure":
                raise RuntimeError("synthetic q10 field-sampling failure")
            on_sample(10, sample)
            samples["q10"] = sample
        return {
            "axes_nm": {name: [0.0, 1.0] for name in ("x", "y", "z")},
            "mesh_identity": {"global_cells": 1},
            "samples": samples,
        }

    def fake_solver(_cfg, _output_root, **kwargs):
        kwargs["variable_p_live_observer"](view)
        raise _ObserverReached("fake solver returned immediately after the actual observer")

    monkeypatch.setattr(h100_anchor, "WorkflowLedger", _Ledger)
    monkeypatch.setattr(h100_anchor, "_log_stage", lambda *args, **kwargs: None)
    monkeypatch.setattr(h100_anchor, "_record_v11_identity_checkpoint", lambda **kwargs: None)
    monkeypatch.setattr(h100_anchor, "_check_v11_runtime_envelope", lambda *args, **kwargs: {"v11_watchdog_worker_identity": identity})
    monkeypatch.setattr(h100_anchor, "_require_v11_watchdog_worker_identity", lambda **kwargs: identity)
    monkeypatch.setattr(h100_anchor, "_validate_v11_primary_cli", lambda **kwargs: None)
    monkeypatch.setattr(
        h100_anchor,
        "_validate_accepted_candidate_inputs",
        lambda **kwargs: (plan, plan_sha, dict(accepted_identity)),
    )
    monkeypatch.setattr(h100_anchor, "_verify_v12_p2_source_binding", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        h100_anchor,
        "_v11_p4_preassembly_space_audit",
        lambda **kwargs: {"pass": True, "v12_p2_source_snapshot": {}},
    )
    monkeypatch.setattr(h100_anchor, "_h100_config", lambda **kwargs: SimpleNamespace())
    monkeypatch.setattr(h100_anchor, "_configure_direct_factor_backend", lambda *args, **kwargs: None)
    monkeypatch.setattr(h100_anchor, "_configure_v11_primary_endpoint", lambda _cfg, _phase, _contract: {})
    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", lambda *_args, **_kwargs: mesh_data)
    monkeypatch.setattr(h100_anchor, "build_stage4_local_h_mesh_data", lambda *_args, **_kwargs: mesh_data)
    monkeypatch.setattr(h100_anchor, "_mesh_axes", lambda *_args, **_kwargs: tuple(np.asarray([0.0, 1.0]) for _ in range(3)))
    monkeypatch.setattr(
        h100_anchor,
        "_assert_mesh_profile",
        lambda *_args, **_kwargs: {
            "leaf_catalog_sha256": "leaf",
            "root_catalog_sha256": "root",
            "closure_split_counts": {},
            "hanging_patch_count": 0,
        },
    )
    monkeypatch.setattr(
        h100_anchor,
        "resolve_stage4_full3d_assembly_backend",
        lambda *_args, **_kwargs: {"actual": h100_anchor.ASSEMBLY_TIME_VARIABLE_P_CONDENSED_BACKEND},
    )
    monkeypatch.setattr(
        h100_anchor,
        "_active_solution_storage",
        lambda _view: (
            {
                "recovered_p6_local_coefficients": np.asarray([1, 2, 3, 4], dtype=np.complex128),
                "recovered_p6_owned_coefficients": np.asarray([1, 2, 3], dtype=np.complex128),
                "mesh_geometry_coordinates_nm": np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64),
                "mesh_geometry_dofmap": np.asarray([0, 1, 2, 3], dtype=np.int32),
                "mesh_owned_cell_global_ids": np.asarray([8], dtype=np.int64),
                "mesh_cell_vertex_dofmap": np.asarray([[0, 1, 2, 3]], dtype=np.int32),
                "p6_function_space_dofmap": np.asarray([[0, 1, 2, 3]], dtype=np.int32),
                "p6_owned_global_dof_block_ids": np.asarray([0, 1, 2], dtype=np.int64),
                "p6_ghost_global_dof_block_ids": np.asarray([3], dtype=np.int64),
                "active_full_solution_owned": np.zeros(3, dtype=np.complex128),
                "active_full_rhs_owned": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
            },
            {
                "active_degree_plan_sha256": "degree-plan",
                "mesh_and_dof_order_sha256": "mesh-order",
                "independent_active_fe_dofs": 2,
                "active_rows": 3,
            },
        ),
    )
    monkeypatch.setattr(
        h100_anchor,
        "compute_stage4_independent_active_action",
        lambda *_args, **_kwargs: {
            "raw_vectors": a6_raw,
            "raw_vector_scope": {
                "trace_rows": 1,
                "active_interior_rows": 1,
                "modal_lower_rows": 612,
            },
            "full_solver_gauge_residual": {
                "relative_to_independent_rhs": 0.0,
                "finite": True,
            },
        },
    )
    monkeypatch.setattr(h100_anchor, "_field_capture", fake_field_capture)
    monkeypatch.setattr(h100_anchor, "_v11_endpoint_identity", lambda *_args, **kwargs: {"phase": kwargs["phase"]})
    monkeypatch.setattr(h100_anchor, "_v11_primary_q_response", lambda **_kwargs: {"pass": True, "gates": {}})
    monkeypatch.setattr(h100_anchor, "task43_profile_identity", lambda *args, **kwargs: {"profile": "synthetic"})
    monkeypatch.setattr(h100_anchor, "run_stage4b_block_grating_3d_case", fake_solver)
    monkeypatch.setattr(
        h100_anchor.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout="0" * 40 + "\n"),
    )
    failure_context: dict = {}

    try:
        h100_anchor._run_impl(
            h100_anchor._ROUND1_CANDIDATE_CASE,
            run_root,
            None,
            None,
            candidate_plan_path=plan_path,
            candidate_id=candidate_id,
            candidate_acceptance_contract=ACCEPTANCE_PATH.resolve(),
            candidate_parent_selection_record=selection_path,
            same_lu_solve_residual_correction_enabled=True,
            direct_factor_backend="mumps",
            v11_primary_diagnostic_phase=phase,
            v11_contract_path=contract_path,
            v11_contract_sha256=contract_sha,
            v12_recovery_binding=recovery_binding,
            _failure_context=failure_context,
        )
    except _ObserverReached:
        pass
    except RuntimeError as error:
        if outcome not in {"raw_failure", "q10_failure"}:
            raise
        if outcome == "raw_failure" and "raw residual gates failed" not in str(error):
            raise
        if outcome == "q10_failure" and "q10 field-sampling failure" not in str(error):
            raise
    else:
        raise AssertionError("fake solver should stop immediately after invoking the observer")
    return run_root, view, captured_fields, failure_context.get("captured", {})


@pytest.mark.parametrize(
    ("phase", "outcome", "capture_expected", "sample_keys"),
    (
        ("A1_q3", "success", True, {"q8", "q10"}),
        ("R9_H8", "success", True, set()),
        ("A1_q3", "raw_failure", False, set()),
        ("A1_q3", "q10_failure", True, {"q8"}),
    ),
)
def test_run_impl_real_v11_observer_preserves_primary_before_postprocessing(
    tmp_path, monkeypatch, phase, outcome, capture_expected, sample_keys
):
    if (
        phase == "A1_q3"
        and outcome == "success"
        and os.environ.get("TASK43_V11_ATTEMPT_ROOT")
    ):
        runtime_identity = h100_anchor._check_v11_runtime_envelope(
            h100_anchor.MPI.COMM_WORLD
        )
        (tmp_path / "recovery_runtime_identity.json").write_text(
            json.dumps(runtime_identity, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    run_root, view, captures, captured = _invoke_actual_v11_observer(
        tmp_path,
        monkeypatch,
        phase=phase,
        outcome=outcome,
    )
    packet_path = run_root / "primary_state.npz"
    checkpoint_path = run_root / "primary_raw_vector_audit.json"
    assert packet_path.is_file()
    assert checkpoint_path.is_file()
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["pass"] is (outcome != "raw_failure")
    assert captures == (["begin"] if capture_expected else [])
    assert set(captured.get("v11_primary_sample_records", {})) == sample_keys
    with np.load(packet_path, allow_pickle=False) as packet:
        packet_record = json.loads(
            packet["__task43_record_json__"].tobytes().decode("utf-8")
        )
        assert packet_record["identity"]["normal_correction_count"] == 1
        assert packet_record["identity"]["extra_correction_count"] == 0
        assert packet_record["identity"]["ordered_mode_count"] == 612
        assert packet_record["identity"]["ordered_mode_keys"] == [
            [mode.side, mode.m, mode.n, mode.polarization]
            for mode in view.goal_context["modes"]
        ]
    if outcome == "raw_failure":
        assert checkpoint["audit"]["pass"] is False
        assert "v11_primary_raw_gate_checkpoint" in captured
        assert not (run_root / "primary_field_sample_q8.npz").exists()
    elif outcome == "q10_failure":
        assert checkpoint["audit"]["pass"] is True
        assert (run_root / "primary_field_sample_q8.npz").is_file()
        assert not (run_root / "primary_field_sample_q10.npz").exists()
    else:
        assert checkpoint["audit"]["pass"] is True
        assert captured["ordered_mode_keys"] == [
            [mode.side, mode.m, mode.n, mode.polarization]
            for mode in view.goal_context["modes"]
        ]


def test_raw_vector_residual_recomputation_uses_saved_gram_action():
    arrays = _raw_vectors()
    arrays["full_active_reduced_trace_dtn_residual_Ax_minus_b_owned"][0] = 0.5
    arrays["returned_trace_dtn_b_minus_Ax"][0] = -0.5
    arrays["normal_after_normal_correction_residual_b_minus_Ax"][0] = -0.5
    arrays["full_active_reduced_trace_dtn_residual_trace_metric_action"][0] = 2.0
    arrays["full_active_reduced_trace_dtn_rhs_owned"][0] = 1.0
    arrays["full_active_reduced_trace_dtn_rhs_trace_metric_action"][0] = 4.0

    result = h100_anchor._v11_raw_vector_gates(arrays, **_raw_gate_arguments())

    expected_metric_relative = np.sqrt(0.5 * 2.0) / np.sqrt(4.0 + 612.0 + 1.0)
    euclidean_relative = 0.5 / np.sqrt(1.0 + 612.0 + 1.0)
    assert result["full_active_transformed"]["relative_residual"] == pytest.approx(
        expected_metric_relative
    )
    assert result["full_active_transformed"]["relative_residual"] != pytest.approx(
        euclidean_relative
    )
    assert result["full_active_transformed"]["trace_metric"] == "saved same-pass Gram inverse action"

    malformed = _raw_vectors()
    malformed["returned_trace_dtn_rhs"] = np.ones(1, dtype=np.complex128)
    with pytest.raises(ValueError, match="returned condensed RHS"):
        h100_anchor._v11_raw_vector_gates(malformed, **_raw_gate_arguments())


@pytest.mark.parametrize(
    ("failure", "error_match"),
    (
        (None, None),
        ("rhs", "full-active reduced RHS/solution/residual do not match"),
        ("solution", "full-active reduced RHS/solution/residual do not match"),
        ("residual_sign", "full-active reduced RHS/solution/residual do not match"),
        ("missing_solution", "missing full_active_reduced_trace_dtn_solution_owned"),
        ("zero_rhs", "RHS norm must be finite and strictly positive"),
        ("modal_rhs", "modal lower solver gauge RHS must be exactly zero"),
    ),
    ids=("valid", "rhs", "solution", "residual_sign", "missing_solution", "zero_rhs", "modal_rhs"),
)
def test_v13_raw_packet_same_state_and_zero_modal_rhs(
    tmp_path, monkeypatch, failure, error_match
):
    root = tmp_path / ("valid" if failure is None else failure)
    candidate_root, record, contract, contract_sha = _pending_fixture(root)
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(
        comparison,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    monkeypatch.setattr(
        comparison, "_verify_v12_p2_source_binding", lambda *args, **kwargs: {}
    )

    residual = 1.0e-20
    arrays = _raw_vectors()
    arrays["full_active_reduced_trace_dtn_residual_Ax_minus_b_owned"][0] = -residual
    arrays["full_active_reduced_trace_dtn_residual_trace_metric_action"][0] = (
        -4.0 * residual
    )
    arrays["full_active_reduced_trace_dtn_rhs_trace_metric_action"][0] = 4.0
    arrays["returned_trace_dtn_b_minus_Ax"][0] = residual
    arrays["normal_before_normal_correction_residual_b_minus_Ax"][...] = 0.0
    arrays["normal_before_normal_correction_residual_b_minus_Ax"][0] = 2.0 * residual
    arrays["normal_after_normal_correction_residual_b_minus_Ax"][0] = residual
    raw_audit = h100_anchor._v11_raw_vector_gates(
        arrays, **_raw_gate_arguments()
    )
    assert raw_audit["pass"] is True
    assert raw_audit["independent_A6"]["rhs_norm"] == pytest.approx(np.sqrt(2.0))

    if failure == "rhs":
        arrays["returned_trace_dtn_rhs"][0] = 2.0
    elif failure == "solution":
        arrays["returned_trace_dtn_solution"][0] = 2.0
    elif failure == "residual_sign":
        arrays["returned_trace_dtn_b_minus_Ax"][0] = -residual
        arrays["normal_after_normal_correction_residual_b_minus_Ax"][0] = -residual
    elif failure == "missing_solution":
        arrays.pop("full_active_reduced_trace_dtn_solution_owned")
    elif failure == "zero_rhs":
        for name in (
            "independent_A6_independent_active_rhs_trace",
            "independent_A6_independent_active_rhs_cell_interior",
            "full_active_reduced_trace_dtn_rhs_owned",
            "full_active_reduced_trace_dtn_rhs_trace_metric_action",
            "full_active_active_full_rhs",
            "recovered_active_full_rhs_owned",
            "returned_trace_dtn_rhs",
            "normal_before_normal_correction_rhs",
            "normal_after_normal_correction_rhs",
        ):
            arrays[name][...] = 0.0
    elif failure == "modal_rhs":
        arrays[
            "independent_A6_independent_active_modal_lower_solver_gauge_rhs"
        ][0] = 0.125

    if failure is not None:
        with pytest.raises(ValueError, match=error_match):
            h100_anchor._v11_raw_vector_gates(arrays, **_raw_gate_arguments())

    packet_path = candidate_root / "primary_state.npz"
    packet_path.unlink()
    packet = write_v11_primary_packet(
        packet_path,
        arrays,
        phase="R9_H8",
        identity=record["primary_packet"]["identity"],
    )
    record["primary_packet"] = packet
    terminal_path = candidate_root / "task43_v11_primary_terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["primary_packet"] = packet
    record["primary_raw_vector_audit"] = raw_audit
    raw_checkpoint_ref = record["primary_raw_vector_audit_checkpoint"]
    raw_checkpoint_path = Path(raw_checkpoint_ref["path"])
    raw_checkpoint_record = json.loads(
        raw_checkpoint_path.read_text(encoding="utf-8")
    )
    raw_checkpoint_record.update(
        {
            "audit": raw_audit,
            "gates": raw_audit["gates"],
            "pass": raw_audit["pass"],
        }
    )
    raw_checkpoint_ref = candidate_checkpoints.write_atomic_json(
        raw_checkpoint_path,
        raw_checkpoint_record,
        refuse_overwrite=False,
    )
    record["primary_raw_vector_audit_checkpoint"] = raw_checkpoint_ref
    terminal["primary_raw_vector_audit_checkpoint"] = raw_checkpoint_ref
    terminal_path.write_text(
        json.dumps(terminal, sort_keys=True), encoding="utf-8"
    )

    if failure is None:
        restored = comparison._validate_v11_pending_candidate(
            candidate_root,
            record=record,
            contract=contract,
            contract_sha256=contract_sha,
            recovery_binding=record["candidate_identity"]["v12_recovery_binding"],
        )
        assert restored[0] == candidate_root / "candidate_plan.json"
        return

    with pytest.raises(ValueError, match=error_match):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=record,
            contract=contract,
            contract_sha256=contract_sha,
            recovery_binding=record["candidate_identity"]["v12_recovery_binding"],
        )


def _pending_fixture(root: Path, *, failed_condensed: bool = False) -> tuple[Path, dict, dict, str]:
    artifact_prefix = root / "artifacts"
    p4 = {
        "root": "formal/R9_H8_attempt1",
        "script": "launch/R9_H8_attempt1.sh",
        "phase": "R9_H8",
        "candidate_id": "v11_r9_h8",
        "required_fe_bounds": {"parent_fe_dofs": 1, "target_exclusive_upper": 20},
    }
    p2_plan = Path("artifacts/support/p2/plans/v11_r9_h8.json")
    selection_file = root / "docs/selection.json"
    selection_file.parent.mkdir(parents=True)
    selection_file.write_text("selection\n", encoding="utf-8")
    selection_sha = hashlib.sha256(selection_file.read_bytes()).hexdigest()
    contract = {
        "artifact_prefix": str(artifact_prefix),
        "phases": {"P2": {"plan_output_path": str(p2_plan)}, "P4": p4},
        "inputs": [
            {
                "role": "R9_selection_transition",
                "path": "docs/selection.json",
                "sha256": selection_sha,
            }
        ],
    }
    contract_file = root / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
    contract_file.parent.mkdir(parents=True, exist_ok=True)
    contract_bytes = (json.dumps(contract, sort_keys=True) + "\n").encode()
    contract_file.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    candidate_root = artifact_prefix / p4["root"] / "run"
    attempt_root = candidate_root.parent
    candidate_root.mkdir(parents=True)
    p2_path = root / p2_plan
    p2_path.parent.mkdir(parents=True)
    support_root = p2_path.parent.parent.resolve()
    audit_path = p2_path.parent / "v11_r9_h8.audit.json"
    bundle_path = support_root / "plan_audit.json"
    a2_path = support_root / "A2_saved_primary_q_response.json"
    recovery_binding = {
        "manifest_path": str(
            (root / "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json").resolve()
        ),
        "manifest_sha256": "a" * 64,
        "contract_sha256": contract_sha,
        "p2_source_id": "D1",
        "support_root": str(support_root),
        "output_root": str(support_root),
        "plan_output_path": str(p2_path.resolve()),
        "audit_path": str(audit_path.resolve()),
        "bundle_path": str(bundle_path.resolve()),
    }
    plan = {
        "task43_candidate": {
            "candidate_id": "v11_r9_h8",
            "action": "h_refine",
            "provenance": {
                "accepted_parent_selection_sha256": selection_sha,
                "v12_recovery_binding": recovery_binding,
            },
        }
    }
    plan_bytes = (json.dumps(plan, sort_keys=True) + "\n").encode()
    p2_path.write_bytes(plan_bytes)
    run_plan_path = candidate_root / "candidate_plan.json"
    run_plan_path.write_bytes(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    audit = {
        "v12_recovery_binding": recovery_binding,
        "forest": {"root_cell_count": 1, "actual_leaf_cell_count": 1},
        "dofs": {
            "independent_trace_rows": 1,
            "active_cell_interior_rows": 1,
            "independent_active_fe_dofs": 2,
        },
        "degrees": {
            "cell_interior_histogram": {"p6": 1},
            "entity_degree_plan_sha256": "entity-plan",
        },
        "actual_geometry": {"mesh_box_catalog_sha256": "mesh-boxes"},
        "strict_fe_gate": {"pass": True},
    }
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    p2_audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    source_map = {"benchmarks/fake_source.py": "source-sha"}
    script_path = artifact_prefix / p4["script"]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    snapshots = attempt_root / "snapshots"
    snapshots.mkdir(parents=True)
    launch_snapshot = snapshots / "launch.sh"
    launch_snapshot.write_bytes(script_path.read_bytes())
    watchdog_dir = attempt_root / "watchdog"
    watchdog_dir.mkdir()
    (watchdog_dir / "summary.json").write_text(
        json.dumps(
            {
                "classification": "COMPLETED",
                "leader_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
            }
        ),
        encoding="utf-8",
    )
    (attempt_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
    (attempt_root / "watchdog_exit_code.txt").write_text("0\n", encoding="ascii")
    manifest = {
        "schema": "task43.v11.launch-input-manifest.v1",
        "contract_sha256": contract_sha,
        "recovery_manifest_sha256": recovery_binding["manifest_sha256"],
        "p2_source_id": recovery_binding["p2_source_id"],
        "launch_shell_sha256": hashlib.sha256(launch_snapshot.read_bytes()).hexdigest(),
        "source": [
            {"path": name, "sha256": digest}
            for name, digest in {
                **source_map,
                "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json": recovery_binding[
                    "manifest_sha256"
                ],
            }.items()
        ],
        "inputs": [
            {
                "path": str(selection_file.resolve()),
                "sha256": selection_sha,
            }
        ],
    }
    (snapshots / "launch_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )

    arrays = _raw_vectors(failed_condensed=failed_condensed)
    identity = {
        "phase": "R9_H8",
        "contract_sha256": contract_sha,
        "candidate_plan_sha256": plan_sha,
        "candidate_identity": {"candidate_id": "v11_r9_h8"},
        "independent_active_fe_dofs": 2,
        "raw_full_active_scope": _raw_gate_arguments()["full_active_scope"],
        "independent_A6_raw_vector_scope": _raw_gate_arguments()["independent_a6_scope"],
        "normal_correction_count": 1,
        "extra_correction_count": 0,
        "normal_correction_audit": {
            "status": "passed",
            "correction_ksp": {"converged_reason": 2},
        },
    }
    raw_recomputed = h100_anchor._v11_raw_vector_gates(arrays, **_raw_gate_arguments())
    candidate_identity = {
        "candidate_id": "v11_r9_h8",
        "v11_phase": "R9_H8",
        "v11_contract_sha256": contract_sha,
        "plan_sha256": plan_sha,
        "run_plan_path": str(run_plan_path.resolve()),
        "accepted_parent_selection_sha256": selection_sha,
        "v12_recovery_binding": recovery_binding,
    }
    watchdog_identity = {
        "worker_pid": 99999991,
        "worker_start_ticks": 1,
        "tracer_pid": 99999992,
        "tracer_start_ticks": 1,
        "direct_watchdog_parent_verified": True,
        "tracer_descends_from_watchdog": True,
        "worker_tid_affinities": [{"tid": 99999991, "cpu_list": [1]}],
    }
    source_identity = {
        "v11_primary_contract": {
            "contract_path": str(contract_file.resolve()),
            "contract_sha256": contract_sha,
            "phase": "R9_H8",
        },
        "file_sha256": source_map,
        "v11_watchdog_worker_identity": watchdog_identity,
        "v12_recovery_binding": recovery_binding,
    }
    identity.update(
        candidate_identity=candidate_identity,
        source_identity=source_identity,
        v12_recovery_binding=recovery_binding,
    )
    packet = write_v11_primary_packet(
        candidate_root / "primary_state.npz",
        arrays,
        phase="R9_H8",
        identity=identity,
    )
    actual = {
        "root_cell_count": 1,
        "leaf_cell_count": 1,
        "independent_trace_rows": 1,
        "active_cell_interior_rows": 1,
        "independent_active_fe_dofs": 2,
        "cell_interior_histogram": {"p6": 1},
        "entity_degree_plan_sha256": "entity-plan",
        "entity_map_sha256": "entity-map",
        "mesh_box_catalog_sha256": "mesh-boxes",
    }
    audit["degrees"]["entity_map_sha256"] = "entity-map"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    p2_audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    bundle_path.write_text(
        json.dumps(
            {
                "v12_recovery_binding": recovery_binding,
                "candidates": [{"strict_fe_gate": {"pass": True}}],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    a2_path.write_text(
        json.dumps(
            {
                "v12_recovery_binding": recovery_binding,
                "contract_sha256": contract_sha,
                "persisted_before_space_authority": True,
                "pass": True,
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    raw_checkpoint_path = candidate_root / "primary_raw_vector_audit.json"
    raw_checkpoint_record = {
        "schema": "task43.v11.primary_raw_vector_audit_checkpoint.v1",
        "classification": "measured_primary_raw_vector_gate_nonofficial",
        "identity": {"phase": "R9_H8", "contract_sha256": contract_sha},
        "audit": raw_recomputed,
        "gates": raw_recomputed["gates"],
        "pass": raw_recomputed["pass"],
        "official_result": False,
        "passed": False,
    }
    raw_checkpoint_path.write_text(
        json.dumps(raw_checkpoint_record, sort_keys=True), encoding="utf-8"
    )
    raw_checkpoint = {
        "path": str(raw_checkpoint_path.resolve()),
        "sha256": hashlib.sha256(raw_checkpoint_path.read_bytes()).hexdigest(),
    }
    record = {
        "schema": "task43.v11.primary-endpoint.v1",
        "phase": "R9_H8",
        "status": "SOLVED_PENDING_POSTPROCESS",
        "official_result": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "gates": {"pass": True},
        "pass": True,
        "passed": True,
        "candidate_identity": candidate_identity,
        "candidate_plan_sha256": plan_sha,
        "source_identity": source_identity,
        "solver": {"official_result": False},
        "field_samples": {"status": "not_run_pending_p5_common_union_sampling"},
        "primary_samples": {},
        "primary_packet": packet,
        "primary_raw_vector_audit": raw_recomputed,
        "primary_raw_vector_audit_checkpoint": raw_checkpoint,
        "p4_preassembly_space_audit": {
            "pass": True,
            "v12_recovery_binding": recovery_binding,
            "p2_plan_sha256": plan_sha,
            "p2_audit_sha256": p2_audit_sha,
            "actual": {
                **actual,
                "root_cell_count": 1,
                "leaf_cell_count": 1,
                "entity_map_sha256": "entity-map",
            },
        },
        "recovered_solution_storage": {
            "active_trace_rows": 1,
            "active_cell_interior_rows": 1,
        },
    }
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text("endpoint bytes\n", encoding="utf-8")
    terminal = {
        "schema": "task43.v11.primary-terminal.v1",
        "phase": "R9_H8",
        "status": "SOLVED_PENDING_POSTPROCESS",
        "official_result": False,
        "passed": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "contract_sha256": contract_sha,
        "v12_recovery_binding": recovery_binding,
        "candidate_identity": candidate_identity,
        "source_identity": source_identity,
        "endpoint_record_path": str(endpoint_path),
        "endpoint_record_sha256": hashlib.sha256(endpoint_path.read_bytes()).hexdigest(),
        "candidate_plan_sha256": plan_sha,
        "primary_packet": packet,
        "primary_raw_vector_audit_checkpoint": raw_checkpoint,
        "primary_samples": {},
    }
    (candidate_root / "task43_v11_primary_terminal.json").write_text(
        json.dumps(terminal, sort_keys=True), encoding="utf-8"
    )
    return candidate_root, record, contract, contract_sha


def _v13_saved_a2_input_fixture(root: Path) -> dict:
    inputs = []
    data_root = root / "saved_a2_inputs"
    data_root.mkdir(parents=True)

    def add_input(role: str, path: Path) -> None:
        inputs.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )

    resolved_config_path = data_root / "y6_config.json"
    resolved_config_path.write_text('{"fixture":"Y6_1"}\n', encoding="utf-8")
    add_input("Y6_1_resolved_config", resolved_config_path)
    returned_rhs = np.ones(121572, dtype=np.complex128)
    residual = np.zeros(121572, dtype=np.complex128)
    residual[0] = 1.0e-22
    raw_arrays = {
        "primary_native_A6_effective_rhs": np.ones(389832, dtype=np.complex128),
        "primary_independent_A6_residual": np.zeros(389832, dtype=np.complex128),
        "primary_zero_slave_carrier_residual": np.zeros(389832, dtype=np.complex128),
        "primary_augmented_port_residual": np.zeros(612, dtype=np.complex128),
        "primary_returned_trace_dtn_rhs": returned_rhs,
        "primary_returned_trace_dtn_solution": np.zeros(121572, dtype=np.complex128),
        "primary_returned_trace_dtn_b_minus_Ax": residual,
        "normal_correction_b_minus_Ax_snapshot_0": np.pad(
            np.asarray([2.0e-22], dtype=np.complex128), (0, 121571)
        ),
        "normal_correction_b_minus_Ax_snapshot_1": residual.copy(),
        "primary_full_physical_rhs": np.ones(389832, dtype=np.complex128),
        "primary_recovered_p6_storage": np.zeros(389832, dtype=np.complex128),
    }
    returned_rhs_norm = float(np.linalg.norm(returned_rhs))
    condensed_relative = float(np.linalg.norm(residual)) / returned_rhs_norm
    packet_identity = {
        "resolved_config_path": str(resolved_config_path.resolve()),
        "resolved_config_sha256": hashlib.sha256(
            resolved_config_path.read_bytes()
        ).hexdigest(),
        "operator_q": 19,
        "incident_port_q": 32,
        "mode_basis_scale_policy": None,
        "primary_solver_residual_metrics_before_extra": {
            "condensed_b_minus_Ax_relative": condensed_relative,
            "independent_A6_relative": 0.0,
            "full_active_space_transformed_relative": 0.0,
        },
    }
    packet_path = data_root / "primary_state.npz"
    packet = candidate_checkpoints.write_atomic_npz(
        packet_path,
        raw_arrays,
        schema="task43.v3.a2_primary_before_extra.v1",
        classification="measured_primary_state_before_extra_not_official",
        identity=packet_identity,
    )
    add_input("A2_primary_packet", packet_path)

    modal_path = data_root / "a2_modal_orders.json"
    modal_path.write_text(
        json.dumps(
            {
                "metrics": {
                    "R_total": 0.0,
                    "T_total": 1.0,
                    "R00_s": 0.0,
                    "R00_p": 0.0,
                    "R00_total": 0.0,
                },
                "rows": [{"fixture": "one validated modal row"}],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    add_input("A2_saved_modal_orders", modal_path)
    absorption_path = data_root / "a2_absorption.json"
    absorption_path.write_text(
        json.dumps({"A_volume_total": 0.0, "regions": {}}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    add_input("A2_saved_absorption", absorption_path)

    points = np.zeros((1, 3), dtype=np.float64)
    weights = np.asarray([350000.0], dtype=np.float64)
    comparison_quadrature = {}
    for order in (8, 10):
        key = f"q{order}"
        reference_path = data_root / f"y6_{key}.npz"
        with reference_path.open("wb") as stream:
            np.savez_compressed(
                stream,
                points_nm=points,
                weights_nm3=weights,
                Y6_1_E=np.zeros((1, 3), dtype=np.complex128),
                Y6_1_curl_E=np.zeros((1, 3), dtype=np.complex128),
            )
        reference_sha = hashlib.sha256(reference_path.read_bytes()).hexdigest()
        add_input(f"historical_joint_{key}", reference_path)
        comparison_quadrature[key] = {
            "sample_bundle": str(reference_path.resolve()),
            "sample_bundle_sha256": reference_sha,
        }
        sample_path = data_root / f"a2_{key}.npz"
        candidate_checkpoints.write_atomic_npz(
            sample_path,
            {
                "points_nm": points,
                "weights_nm3": weights,
                "E_total_code": np.zeros((1, 3), dtype=np.complex128),
                "curl_E_total_code": np.zeros((1, 3), dtype=np.complex128),
                "H_total_A_per_m": np.zeros((1, 3), dtype=np.complex128),
            },
            schema="task43.v3.a2_saved_field_sample.v1",
            classification="measured_saved_primary_field_sample_nonofficial",
            identity={"primary_before_extra_npz_sha256": packet["npz_sha256"]},
        )
        add_input(f"A2_{key}_saved_sample", sample_path)
    comparison_path = data_root / "historical_joint_comparison.json"
    comparison_path.write_text(
        json.dumps({"quadrature": comparison_quadrature}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    add_input("historical_joint_comparison", comparison_path)
    return {
        "inputs": inputs,
        "quadrature_response_thresholds": {
            "aggregate_absolute_max": 1.0e-6,
            "zero_order_s_p_and_each_channel_power_absolute_max": 1.0e-7,
            "four_boundary_amplitude_and_total_scattered_E_H_G_floor_normalized_max": 1.0e-5,
        },
    }


def test_v13_saved_a2_partial_checkpoint(tmp_path, monkeypatch):
    base = round1_candidates.base
    comparator = round1_candidates.candidate_comparator
    comparison_metrics = {
        "power_absolute_differences": {
            "R00_s": 0.0,
            "R00_p": 0.0,
            "R00_total": 0.0,
            "R_total": 0.0,
            "T_total": 0.0,
        },
        "maximum_individual_channel_power_ratio_absolute_difference": 0.0,
        "boundary_amplitude_groups": {
            f"group_{index}": {"relative_with_unit_incident_modal_floor": 0.0}
            for index in range(4)
        },
    }
    field_metrics = {
        name: {"relative_to_reference_or_floor": 0.0}
        for name in (
            "E_total_code",
            "H_total_A_per_m",
            "E_scattered_code",
            "H_scattered_A_per_m",
        )
    }
    field_metrics["G"] = {"relative_with_incident_floor": 0.0}
    historical_cfg = SimpleNamespace(
        magnetic_field_scale_A_per_m=1.0,
        k0=1.0,
        mu_r=1.0 + 0.0j,
    )

    for outcome in ("success", "q10_failure"):
        root = tmp_path / outcome
        contract = _v13_saved_a2_input_fixture(root)
        monkeypatch.setattr(round1_candidates, "ROOT", root)
        with monkeypatch.context() as local:
            local.setattr(round1_candidates, "_load_inventory_entry", lambda *_args: {})
            local.setattr(
                round1_candidates,
                "_configure_historical_direct_route",
                lambda *_args: historical_cfg,
            )
            local.setattr(
                round1_candidates,
                "_validated_rows",
                lambda *_args, **_kwargs: [{"fixture": "R13"}],
            )
            local.setattr(
                comparator,
                "_load_modal_case",
                lambda _label: {"label": "Y6_1", "record": {}},
            )
            local.setattr(base, "_validate_mode_physics", lambda *_args, **_kwargs: {"pass": True})
            local.setattr(
                comparator,
                "_post_selection_full_mode_physics",
                lambda case: {"label": case["label"], "pass": True},
            )
            local.setattr(
                base,
                "_modal_comparison",
                lambda *_args, **_kwargs: comparison_metrics,
            )
            original_q10_error = ValueError("q10 fixture field comparison failed")
            local.setattr(
                base,
                "_field_metrics",
                lambda *_args, **_kwargs: field_metrics,
            )

            checkpoint_root = root / "a2_substage_checkpoints"
            checkpoint_root.mkdir()
            refs = {}
            values_by_stage = {}

            def persist_substage(stage, values):
                values_by_stage[stage] = dict(values)
                reference = candidate_checkpoints.write_atomic_json(
                    checkpoint_root / f"{stage}.json",
                    {
                        "stage": stage,
                        "completed_substage_values": dict(values),
                        "overall_pass": False,
                        "official_result": False,
                        "selection_or_transition_authority": False,
                        "continuation": False,
                    },
                )
                refs[stage] = reference
                return reference

            if outcome == "success":
                response = round1_candidates._v11_saved_a2_primary_q_response(
                    contract,
                    checkpoint_callback=persist_substage,
                )
                assert response["pass"] is True
                assert response["substage_statuses"] == {
                    "raw": "CHECKPOINTED",
                    "modal": "CHECKPOINTED",
                    "q8": "CHECKPOINTED",
                    "q10": "CHECKPOINTED",
                }
                assert tuple(refs) == ("raw", "modal", "q8", "q10")
                assert values_by_stage["raw"]["A6_relative_to_native_effective_rhs"] == 0.0
                assert values_by_stage["raw"][
                    "full_active_zero_slave_carrier_plus_modal_port_euclidean_relative_to_native_effective_rhs"
                ] == 0.0
                assert values_by_stage["raw"][
                    "returned_condensed_relative_to_returned_rhs"
                ] == pytest.approx(
                    1.0e-22 / np.sqrt(121572), rel=1.0e-12, abs=0.0
                )
                assert values_by_stage["raw"]["normal_correction_relative_history"] == pytest.approx(
                    [2.0e-22 / np.sqrt(121572), 1.0e-22 / np.sqrt(121572)],
                    rel=1.0e-12,
                    abs=0.0,
                )
                assert values_by_stage["modal"]["ordered_rows_checked"] == 1
                assert values_by_stage["q8"]["sample_count"] == 1
                assert values_by_stage["q10"]["sample_count"] == 1
                for stage, reference in refs.items():
                    checkpoint_path = Path(reference["path"])
                    checkpoint_record = json.loads(
                        checkpoint_path.read_text(encoding="utf-8")
                    )
                    assert hashlib.sha256(checkpoint_path.read_bytes()).hexdigest() == reference[
                        "sha256"
                    ]
                    assert checkpoint_record["overall_pass"] is False
                    assert checkpoint_record["official_result"] is False
                    assert checkpoint_record["selection_or_transition_authority"] is False
                    assert checkpoint_record["continuation"] is False
                continue

            bytes_before_q10_failure = {}

            def fail_q10_after_q8(*_args, **_kwargs):
                bytes_before_q10_failure.update(
                    {
                        stage: Path(reference["path"]).read_bytes()
                        for stage, reference in refs.items()
                    }
                )
                raise original_q10_error

            field_call_count = {"count": 0}

            def fail_second_field_call(*args, **kwargs):
                field_call_count["count"] += 1
                if field_call_count["count"] == 2:
                    return fail_q10_after_q8(*args, **kwargs)
                return field_metrics

            local.setattr(base, "_field_metrics", fail_second_field_call)
            with pytest.raises(ValueError, match="q10 fixture field comparison failed") as caught:
                round1_candidates._v11_saved_a2_primary_q_response(
                    contract,
                    checkpoint_callback=persist_substage,
                )
            assert caught.value is original_q10_error
            failure_record = round1_candidates._v11_saved_a2_failure_response(
                caught.value, refs
            )
            assert failure_record["failure_stage"] == "q10"
            assert failure_record["error"] == "ValueError: q10 fixture field comparison failed"
            assert failure_record["substage_statuses"] == {
                "raw": "CHECKPOINTED",
                "modal": "CHECKPOINTED",
                "q8": "CHECKPOINTED",
                "q10": "FAILED",
            }
            assert failure_record["pass"] is False
            assert failure_record["passed"] is False
            assert failure_record["official_result"] is False
            assert failure_record["selection_or_transition_authority"] is False
            assert failure_record["continuation"] is False
            assert set(refs) == {"raw", "modal", "q8"}
            for stage, before in bytes_before_q10_failure.items():
                reference = refs[stage]
                checkpoint_path = Path(reference["path"])
                assert checkpoint_path.read_bytes() == before
                assert hashlib.sha256(before).hexdigest() == reference["sha256"]


def _prepare_v12_compare_fixture(root: Path, monkeypatch, *, failure: str | None = None):
    candidate_root, record, contract, _contract_sha = _pending_fixture(root)
    selection_path = root / "docs/selection.json"
    p2_plan_path = root / contract["phases"]["P2"]["plan_output_path"]
    p2_support = p2_plan_path.parent.parent.resolve()
    contract["phases"]["P4"]["quadrature"] = {
        "volume": 15,
        "incident_and_port": 28,
        "modes": "R13",
        "count": 612,
    }
    contract["phases"]["P5"] = {"comparison_output_root": "comparison/p5"}
    contract["fixed_h_diagnostic_thresholds"] = {
        "epsilon_J": 0.12716416232413652,
        "epsilon_G": 9.088158796603444e-06,
    }
    calibration_path = root / "docs/calibration.json"
    calibration_path.write_text(
        json.dumps(
            {
                "recorded_quadrature_and_cutoff_identity": {
                    "expected": {
                        "volume_rule": "default",
                        "cutoff_policy": "scale_homogeneous_relative_only_v1",
                        "cutoff_relative_tolerance": 1.0e-13,
                    }
                }
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    comparison_contract_path = root / "docs/comparison_contract.json"
    comparison_contract_path.write_text('{"schema":"fixture"}\n', encoding="utf-8")
    contract["inputs"].extend(
        (
            {
                "role": "reference_calibration",
                "path": str(calibration_path.relative_to(root)),
                "sha256": hashlib.sha256(calibration_path.read_bytes()).hexdigest(),
            },
            {
                "role": "frozen_comparison_contract",
                "path": str(comparison_contract_path.relative_to(root)),
                "sha256": hashlib.sha256(comparison_contract_path.read_bytes()).hexdigest(),
            },
        )
    )
    contract_path = root / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
    contract_bytes = (json.dumps(contract, sort_keys=True) + "\n").encode()
    contract_path.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()

    binding = record["candidate_identity"]["v12_recovery_binding"]
    manifest_path = Path(binding["manifest_path"])
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text('{"schema":"task43.v12.execution_recovery_manifest.v1"}\n', encoding="utf-8")
    binding["manifest_sha256"] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    binding["contract_sha256"] = contract_sha

    def bind(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "v12_recovery_binding" and isinstance(child, dict):
                    child.update(binding)
                else:
                    bind(child)
        elif isinstance(value, list):
            for child in value:
                bind(child)

    p2_plan = json.loads(p2_plan_path.read_text(encoding="utf-8"))
    bind(p2_plan)
    p2_plan_bytes = (json.dumps(p2_plan, sort_keys=True) + "\n").encode()
    p2_plan_path.write_bytes(p2_plan_bytes)
    p4_plan_path = candidate_root / "candidate_plan.json"
    p4_plan_path.write_bytes(p2_plan_bytes)
    p2_audit_path = p2_plan_path.parent / "v11_r9_h8.audit.json"
    p2_audit = json.loads(p2_audit_path.read_text(encoding="utf-8"))
    bind(p2_audit)
    p2_audit_path.write_text(json.dumps(p2_audit, sort_keys=True) + "\n", encoding="utf-8")
    bundle_path = p2_support / "plan_audit.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    bind(bundle)
    bundle_path.write_text(json.dumps(bundle, sort_keys=True) + "\n", encoding="utf-8")
    a2_path = p2_support / "A2_saved_primary_q_response.json"
    a2 = json.loads(a2_path.read_text(encoding="utf-8"))
    bind(a2)
    a2["contract_sha256"] = contract_sha
    a2_path.write_text(json.dumps(a2, sort_keys=True) + "\n", encoding="utf-8")

    record["candidate_plan_sha256"] = hashlib.sha256(p4_plan_path.read_bytes()).hexdigest()
    record["candidate_identity"]["plan_sha256"] = record["candidate_plan_sha256"]
    record["candidate_identity"]["v11_contract_sha256"] = contract_sha
    record["source_identity"]["v11_primary_contract"]["contract_sha256"] = contract_sha
    bind(record)
    p4_space = record["p4_preassembly_space_audit"]
    p4_space["p2_plan_sha256"] = hashlib.sha256(p2_plan_path.read_bytes()).hexdigest()
    p4_space["p2_audit_sha256"] = hashlib.sha256(p2_audit_path.read_bytes()).hexdigest()
    record["numerical_controls"] = {
        "volume_quadrature_degree": 15,
        "incident_and_port_quadrature_degree": 28,
        "volume_quadrature_rule": "default",
        "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
        "sparse_cutoff_relative_tolerance": 1.0e-13,
        "ordered_mode_count": 612,
        "port_amplitude_scale_policy": "boundary_magnitude_scaled_r5_v1",
        "mesh": {"global_cells": 1},
        "nedelec_degree": 6,
        "floquet_constraint_mode": "fixture",
    }
    record["recovered_solution_storage"].update(
        {
            "active_trace_rows": 1,
            "active_cell_interior_rows": 1,
            "independent_active_fe_dofs": 2,
        }
    )
    record["resolved_config"] = {"case_name": "synthetic_v12_p5"}
    record["power"] = {
        "channel_rows_sha256": "modal-placeholder",
        "aggregate": {
            key: 0.0
            for key in ("R_total", "T_total", "R00_s", "R00_p", "R00_total")
        },
        "A_volume_total": 1.0,
    }
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    terminal_path = candidate_root / "task43_v11_primary_terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    bind(terminal)
    terminal["contract_sha256"] = contract_sha
    terminal["candidate_plan_sha256"] = record["candidate_plan_sha256"]
    terminal["candidate_identity"] = record["candidate_identity"]
    terminal["source_identity"] = record["source_identity"]
    terminal["candidate_identity"]["plan_sha256"] = record["candidate_plan_sha256"]
    terminal["endpoint_record_path"] = str(endpoint_path.resolve())
    terminal["endpoint_record_sha256"] = hashlib.sha256(endpoint_path.read_bytes()).hexdigest()
    terminal_path.write_text(json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8")
    storage_path = candidate_root / "candidate_recovered_solution_storage.npz"
    np.savez_compressed(storage_path, recovered_p6_local_coefficients=np.asarray([1.0 + 0.0j]))
    orders_path = candidate_root / "solve/dtn_port_diffraction_orders_3d.json"
    orders_path.parent.mkdir(parents=True, exist_ok=True)
    orders_path.write_text(
        json.dumps({"orders": [], "classification": "synthetic_reader_fixture"}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    record["power"]["channel_rows_sha256"] = hashlib.sha256(orders_path.read_bytes()).hexdigest()
    endpoint_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    terminal["endpoint_record_sha256"] = hashlib.sha256(endpoint_path.read_bytes()).hexdigest()
    terminal_path.write_text(json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8")

    p2_joined_path = p2_support / "v12_p2_joined_terminal.json"
    p2_observation = p2_support / "root_observation.json"
    p2_observation.write_text('{"fixture":true}\n', encoding="utf-8")
    p2_launch_root = p2_support
    p2_snapshots = p2_launch_root / "snapshots"
    p2_snapshots.mkdir(parents=True, exist_ok=True)
    p2_shell = p2_snapshots / "launch.sh"
    p2_shell.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    p2_watchdog = p2_launch_root / "watchdog"
    p2_watchdog.mkdir(parents=True, exist_ok=True)
    (p2_watchdog / "summary.json").write_text(
        json.dumps(
            {
                "classification": "COMPLETED",
                "leader_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (p2_launch_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
    (p2_launch_root / "watchdog_exit_code.txt").write_text("0\n", encoding="ascii")
    fake_source = root / "benchmarks/fake_source.py"
    fake_source.parent.mkdir(parents=True, exist_ok=True)
    fake_source.write_text("fixture source\n", encoding="utf-8")
    fake_source_sha = hashlib.sha256(fake_source.read_bytes()).hexdigest()
    source_snapshot = {"benchmarks/fake_source.py": fake_source_sha}
    recovery = {
        "manifest": {"p2_sources": {"D1": {
            key: str(Path(binding[key]).relative_to(root))
            for key in ("support_root", "output_root", "plan_output_path", "audit_path", "bundle_path")
        }}},
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": binding["manifest_sha256"],
    }
    p2_products = {
        "plan": p2_plan_path,
        "audit": p2_audit_path,
        "a2_response": a2_path,
        "bundle": bundle_path,
    }
    p2_hashes = {
        key: {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for key, path in p2_products.items()
    }
    p2_joined_path.write_text(
        json.dumps(
            {
                "schema": "task43.v12.p2-root-joined-terminal.v1",
                "p2_source_id": "D1",
                "contract_sha256": contract_sha,
                "recovery_manifest_sha256": binding["manifest_sha256"],
                "status": "P2_COMPLETE_ROOT_VERIFIED",
                "launcher_exit_code": 0,
                "watchdog_exit_code": 0,
                "worker_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
                "source_head": "b" * 40,
                "products": p2_hashes,
                "root_observation_record": {
                    "path": str(p2_observation.resolve()),
                    "sha256": hashlib.sha256(p2_observation.read_bytes()).hexdigest(),
                },
                "gates": {
                    name: {
                        "pass": True,
                        "evidence": {
                            "path": str(p2_observation.resolve()),
                            "sha256": hashlib.sha256(p2_observation.read_bytes()).hexdigest(),
                        },
                    }
                    for name in ("source", "input", "resource", "trace")
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    p2_shell_sha = hashlib.sha256(p2_shell.read_bytes()).hexdigest()
    source_entries = [
        {
            "path": name,
            "sha256": digest,
            "snapshot": str(fake_source.resolve()),
        }
        for name, digest in source_snapshot.items()
    ]
    source_entries.append(
        {
            "path": "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json",
            "sha256": binding["manifest_sha256"],
            "snapshot": str(manifest_path.resolve()),
        }
    )
    p2_launch_manifest = {
        "schema": "task43.v11.launch-input-manifest.v1",
        "contract_sha256": contract_sha,
        "recovery_manifest_sha256": binding["manifest_sha256"],
        "p2_source_id": "D1",
        "launch_shell_sha256": p2_shell_sha,
        "head": "b" * 40,
        "source": source_entries,
    }
    (p2_snapshots / "launch_manifest.json").write_text(
        json.dumps(p2_launch_manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    (p2_support / "source_head.txt").write_text("b" * 40 + "\n", encoding="ascii")

    p4_attempt = candidate_root.parent
    p4_manifest_path = p4_attempt / "snapshots/launch_manifest.json"
    p4_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    contract_input_paths = [root / item["path"] for item in contract["inputs"]]
    p2_input_paths = [
        *p2_products.values(),
        p2_observation,
        p2_snapshots / "launch_manifest.json",
        p2_watchdog / "summary.json",
        p2_launch_root / "launcher_exit_code.txt",
        p2_launch_root / "watchdog_exit_code.txt",
        p2_joined_path,
        *contract_input_paths,
    ]
    p4_inputs = [
        {"path": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in p2_input_paths
    ]
    p4_source = [
        {"path": name, "sha256": digest}
        for name, digest in source_snapshot.items()
    ]
    p4_source.append(
        {
            "path": "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json",
            "sha256": binding["manifest_sha256"],
        }
    )
    p4_manifest_path.write_text(
        json.dumps(
            {
                "schema": "task43.v11.launch-input-manifest.v1",
                "contract_sha256": contract_sha,
                "recovery_manifest_sha256": binding["manifest_sha256"],
                "p2_source_id": "D1",
                "launch_shell_sha256": hashlib.sha256(
                    (p4_attempt / "snapshots/launch.sh").read_bytes()
                ).hexdigest(),
                "source": p4_source,
                "inputs": p4_inputs,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(h100_anchor, "_REPOSITORY_ROOT", root)
    monkeypatch.setattr(h100_anchor, "_V12_RECOVERY_MANIFEST_REL", manifest_path.relative_to(root))
    monkeypatch.setattr(
        h100_anchor,
        "_V12_P2_SOURCE_PATHS",
        recovery["manifest"]["p2_sources"],
    )
    monkeypatch.setattr(h100_anchor, "_v11_source_snapshot", lambda: source_snapshot)
    monkeypatch.setattr(comparison, "_v11_source_snapshot", lambda: source_snapshot)
    monkeypatch.setattr(comparison, "_load_v11_primary_contract", lambda _path: (contract, contract_sha))
    monkeypatch.setattr(comparison, "_load_v12_execution_recovery_manifest", lambda *_args, **_kwargs: recovery)
    terminal_read_drifted = False

    def resolve_p2_source(_recovery, *, candidate_plan_path):
        nonlocal terminal_read_drifted
        resolved = {
            "p2_source_id": "D1",
            **{key: str(Path(binding[key]).resolve()) for key in (
                "support_root", "output_root", "plan_output_path", "audit_path", "bundle_path"
            )},
        }
        if failure == "terminal_read_drift" and not terminal_read_drifted:
            terminal_read_drifted = True
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            terminal["synthetic_read_drift"] = True
            terminal_path.write_text(json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8")
        return resolved

    monkeypatch.setattr(comparison, "_resolve_v12_p2_source", resolve_p2_source)
    verified_paths = {}
    verify_calls = []

    def fake_verify(_binding, *, contract_sha256, p4_launch_manifest_path):
        verify_calls.append(str(p4_launch_manifest_path))
        assert contract_sha256 == contract_sha
        assert p4_launch_manifest_path == p4_manifest_path
        paths = [*p2_products.values(), p2_observation, p2_joined_path]
        snapshot = {
            str(path.resolve()): {
                "path": str(path.resolve()),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in paths
        }
        verified_paths.update(snapshot)
        return snapshot

    monkeypatch.setattr(comparison, "_verify_v12_p2_source_binding", fake_verify)
    monkeypatch.setattr(comparison, "_v11_input_snapshot", lambda *_args, **_kwargs: {"stable": True})
    monkeypatch.setattr(
        comparison,
        "_check_v11_runtime_envelope",
        lambda *_args, **_kwargs: {"v11_watchdog_worker_identity": {"phase_path": str(root / "phase")}},
    )
    monkeypatch.setattr(comparison, "_require_v11_watchdog_worker_identity", lambda **_kwargs: None)

    class _Ledger:
        def __init__(self, *_args, **_kwargs):
            pass

        def set_phase(self, *_args, **_kwargs):
            pass

        def marker(self, event, *_args, **_kwargs):
            if failure == "ledger_marker_failure" and event == "task43_v11_p5_union_comparison_complete":
                raise OSError("injected final ledger marker failure")

    monkeypatch.setattr(comparison, "WorkflowLedger", _Ledger)
    axes_by_label = {
        "R9": tuple(np.asarray(values, dtype=np.float64) for values in ([0, 50], [0, 50], [-10, 130])),
        "R9_H8": tuple(np.asarray(values, dtype=np.float64) for values in ([0, 25, 50], [0, 50], [-10, 130])),
        "Y6_1": tuple(np.asarray(values, dtype=np.float64) for values in ([0, 16.5, 50], [0, 50], [-10, 0, 130])),
    }

    def make_case(label, fe_dofs, *, p4=False):
        controls = {
            "volume_quadrature_degree": 15,
            "incident_and_port_quadrature_degree": 28,
            "volume_quadrature_rule": "default",
            "sparse_cutoff_policy": "scale_homogeneous_relative_only_v1",
            "sparse_cutoff_relative_tolerance": 1.0e-13,
            "ordered_mode_count": 612,
            "port_amplitude_scale_policy": "boundary_magnitude_scaled_r5_v1",
            "mesh": {"global_cells": 1},
            "nedelec_degree": 6,
        }
        case_record = {
            "numerical_controls": controls,
            "resolved_config": {"floquet_constraint_mode": "fixture"},
            "resolved_identity": {"nedelec_degree": 6, "ordered_mode_count": 612},
            "recovered_solution_storage": {
                "independent_active_fe_dofs": fe_dofs,
                "active_trace_rows": 1,
                "active_cell_interior_rows": max(0, fe_dofs - 1),
            },
        }
        if p4:
            case_record["p4_preassembly_space_audit"] = record["p4_preassembly_space_audit"]
        return {
            "label": label,
            "cfg": SimpleNamespace(),
            "mesh_data": SimpleNamespace(mesh=object()),
            "field": object(),
            "axes": axes_by_label[label],
            "record": case_record,
            "mode_payload": {"orders": [{} for _ in range(612)]},
            "power": {key: 0.0 for key in ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")},
            "mesh_identity": {},
            "v12_restoration_binding": {"same_array_values_dtype_and_shape": True},
        }

    reference_case = make_case("R9", 1)
    candidate_case = make_case("R9_H8", 2, p4=True)
    y6_case = make_case("Y6_1", 3)
    monkeypatch.setattr(comparison, "_load_accepted_parent", lambda _path: {"candidate_id": "round9_p_up", "run_root": str(root / "R9")})
    monkeypatch.setattr(
        comparison,
        "_restore_candidate",
        lambda path, *_args, **kwargs: candidate_case if kwargs.get("v11_contract") else reference_case,
    )
    monkeypatch.setattr(comparison, "_restore_case_fields", lambda *_args, **_kwargs: y6_case)
    monkeypatch.setattr(comparison.base, "_validate_recorded_quadrature_and_cutoff", lambda *_args, **_kwargs: {"pass": True})
    monkeypatch.setattr(comparison.base, "_validate_common_physics", lambda *_args, **_kwargs: {"pass": True})
    monkeypatch.setattr(comparison.base, "_validate_mode_physics", lambda *_args, **_kwargs: {"pass": True})
    monkeypatch.setattr(comparison, "_post_selection_full_mode_physics", lambda _case: {"pass": True})
    expected_keys = [
        (side, m, n, pol)
        for side in ("top", "bottom")
        for m in range(-4, 5)
        for n in range(-8, 9)
        for pol in ("s", "p")
    ]
    modal_rows = [
        {"alpha": [0.0], "gamma": [0.0], "beta": [1.0], "kz": [1.0], "refractive_index": [1.0], "power_ratio": 0.0}
        for _ in expected_keys
    ]
    monkeypatch.setattr(comparison.base, "_modal_identity", lambda _payload, _label: (expected_keys, np.ones(612, dtype=np.complex128), modal_rows))
    monkeypatch.setattr(comparison, "_v11_signed_mode_differences", lambda *_args: {})
    monkeypatch.setattr(
        comparison.base,
        "_modal_comparison",
        lambda *_args: {
            "power_absolute_differences": {key: 0.0 for key in ("R_total", "T_total", "A_volume", "R00_s", "R00_p", "R00_total")},
            "maximum_individual_channel_power_ratio_absolute_difference": 0.0,
            "boundary_amplitude_groups": {"top_s": {"relative_with_unit_incident_modal_floor": 0.0}},
        },
    )
    monkeypatch.setattr(
        comparison.base,
        "_field_metrics",
        lambda _reference, candidate, *_args: {
            **{
                key: {
                    "relative_to_reference_or_floor": float(candidate["E_total"][0, 0].real) * 1.0e-4
                }
                for key in ("E_total_code", "H_total_A_per_m", "E_scattered_code", "H_scattered_A_per_m")
            },
            "G": {
                "relative_with_incident_floor": float(candidate["E_total"][0, 0].real) * 1.0e-5,
                "difference_g_norm": 0.0,
            },
        },
    )
    sample_calls = []

    def sample_field(case, points):
        sample_calls.append((case["label"], int(points.shape[0])))
        if failure == "q10_failure" and len(sample_calls) == 6:
            raise OSError("injected synthetic q10 field failure")
        if failure == "input_drift" and len(sample_calls) == 1:
            p4_plan_path.write_text("drifted after initial P5 snapshot\n", encoding="utf-8")
        order = int(points[0, 0])
        value = (
            0.0
            if case["label"] == "Y6_1"
            else 1.0
            if case["label"] == "R9"
            else 2.0
            if order == 8
            else 0.5
        )
        return {"E_total": np.full((len(points), 3), value, dtype=np.complex128)}

    monkeypatch.setattr(comparison, "_sample_field", sample_field)
    monkeypatch.setattr(
        comparison.base,
        "_cell_slot_for_points",
        lambda *_args: (np.asarray([10], dtype=np.int64), np.asarray([0], dtype=np.int64)),
    )
    quadrature_calls = []

    def make_quadrature(axes, *, gauss_order):
        quadrature_calls.append((gauss_order, axes))
        return SimpleNamespace(
            points_nm=np.asarray([[float(gauss_order), 2.0, 3.0]], dtype=np.float64),
            weights_nm3=np.asarray([350000.0], dtype=np.float64),
            axis_breakpoints_nm=tuple(
                np.asarray(values, dtype=np.float64)
                for values in ((0.0, 16.5, 33.5, 50.0), (0.0, 15.0, 35.0, 50.0), (-10.0, 0.0, 120.0, 130.0))
            ),
            rule_sha256=f"rule-{gauss_order}",
            point_count=1,
            partition_box_count=1,
        )

    monkeypatch.setattr(comparison, "build_common_volume_quadrature", make_quadrature)
    return {
        "candidate_root": candidate_root,
        "selection_path": selection_path,
        "contract_path": contract_path,
        "manifest_path": manifest_path,
        "contract_sha256": contract_sha,
        "binding": binding,
        "p2_joined_path": p2_joined_path,
        "p4_manifest_path": p4_manifest_path,
        "verified_paths": verified_paths,
        "verify_calls": verify_calls,
        "sample_calls": sample_calls,
        "quadrature_calls": quadrature_calls,
        "p4_plan_path": p4_plan_path,
    }


@pytest.mark.parametrize(
    "failure",
    (None, "terminal_read_drift", "input_drift", "q10_failure", "ledger_marker_failure"),
)
def test_compare_v11_union_reads_bound_p2_p4_inputs_and_preserves_q8(
    tmp_path, monkeypatch, failure
):
    fixture = _prepare_v12_compare_fixture(
        tmp_path / str(failure or "success"), monkeypatch, failure=failure
    )
    monkeypatch.setattr(
        comparison,
        "MPI",
        SimpleNamespace(COMM_WORLD=SimpleNamespace(size=1)),
    )
    contract = json.loads(fixture["contract_path"].read_text(encoding="utf-8"))
    output_root = Path(contract["artifact_prefix"]) / contract["phases"]["P5"]["comparison_output_root"]
    if failure is None:
        result = comparison.compare_v11_union(
            fixture["candidate_root"],
            fixture["selection_path"],
            contract_path=fixture["contract_path"],
            recovery_manifest_path=fixture["manifest_path"],
            attempt_id="v11_r9_h8_union_attempt1",
        )
        assert result["status"] == "COMPLETE_DIAGNOSTIC_NOT_ACCEPTANCE"
        assert result["official_result"] is False
        assert result["selection_transition_written"] is False
        assert result["P2_source_id"] == "D1"
        assert result["reference_label"] == "Y6_1"
        assert result["quadrature_orders"] == [8, 10]
        assert result["fixed_thresholds"] == contract["fixed_h_diagnostic_thresholds"]
        assert result["actual_FE"] == {"R9": 1, "R9_H8": 2, "Delta_FE": 1}
        assert result["q10_primary_classification"]["Delta_J"] == pytest.approx(0.5)
        assert result["q10_primary_classification"]["Delta_FE"] == 1
        assert result["q10_primary_classification"]["classification"] == "POSITIVE_FIXED_REFERENCE_OUTPUT_RESPONSE"
        assert result["q8_robustness_classification"]["Delta_J"] == pytest.approx(-1.0)
        assert result["q8_robustness_classification"]["classification"] == "NEGATIVE_OR_TRADEOFF_RESPONSE"
        assert result["sampling_sensitivity"] == "SAMPLING_SENSITIVITY_UNRESOLVED"
        assert len(fixture["sample_calls"]) == 6
        assert len(fixture["quadrature_calls"]) == 2
        assert fixture["quadrature_calls"][0][0] == 8
        assert fixture["quadrature_calls"][1][0] == 10
        assert not np.array_equal(
            fixture["quadrature_calls"][0][1][0],
            fixture["quadrature_calls"][0][1][1],
        )
        joined_key = str(fixture["p2_joined_path"].resolve())
        assert joined_key in result["v12_p2_p4_input_identity_start"]
        assert result["v12_p2_p4_input_identity_start"] == result[
            "v12_p2_p4_input_identity_end"
        ]
        assert len(fixture["verify_calls"]) == 2
        assert (output_root / "v11_r9_h8_union_q8.npz").is_file()
        assert (output_root / "v11_r9_h8_union_q10.npz").is_file()
        return

    if failure == "terminal_read_drift":
        with pytest.raises(RuntimeError, match="terminal changed between source selection"):
            comparison.compare_v11_union(
                fixture["candidate_root"],
                fixture["selection_path"],
                contract_path=fixture["contract_path"],
                recovery_manifest_path=fixture["manifest_path"],
                attempt_id="v11_r9_h8_union_attempt1",
            )
        assert not output_root.exists()
        assert fixture["sample_calls"] == []
        return

    if failure == "ledger_marker_failure":
        with pytest.raises(OSError, match="final ledger marker failure"):
            comparison.compare_v11_union(
                fixture["candidate_root"],
                fixture["selection_path"],
                contract_path=fixture["contract_path"],
                recovery_manifest_path=fixture["manifest_path"],
                attempt_id="v11_r9_h8_union_attempt1",
            )
        comparison_record = json.loads(
            (output_root / "v11_r9_h8_union_comparison.json").read_text(encoding="utf-8")
        )
        failure_record = json.loads(
            (output_root / "v11_r9_h8_union_failure.json").read_text(encoding="utf-8")
        )
        assert comparison_record["official_result"] is False
        assert comparison_record["selection_transition_written"] is False
        assert failure_record["status"] == "ACTION_ENDPOINT_NOT_QUALIFIED"
        assert len(fixture["sample_calls"]) == 6
        assert (output_root / "v11_r9_h8_union_q8.npz").is_file()
        assert (output_root / "v11_r9_h8_union_q10.npz").is_file()
        return

    expected_error = "source/input identity changed" if failure == "input_drift" else "injected synthetic q10 field failure"
    with pytest.raises((RuntimeError, OSError), match=expected_error):
        comparison.compare_v11_union(
            fixture["candidate_root"],
            fixture["selection_path"],
            contract_path=fixture["contract_path"],
            recovery_manifest_path=fixture["manifest_path"],
            attempt_id="v11_r9_h8_union_attempt1",
        )
    assert (output_root / "v11_r9_h8_union_q8.npz").is_file()
    failure_record = json.loads(
        (output_root / "v11_r9_h8_union_failure.json").read_text(encoding="utf-8")
    )
    assert failure_record["official_result"] is False
    assert failure_record["selection_transition_written"] is False
    if failure == "input_drift":
        assert len(fixture["verify_calls"]) == 2
        assert len(fixture["sample_calls"]) == 6
    else:
        assert len(fixture["verify_calls"]) == 1


def test_v12_p2_joined_source_binding_rejects_root_terminal_failure(
    tmp_path, monkeypatch
):
    fixture = _prepare_v12_compare_fixture(tmp_path / "actual_joined", monkeypatch)
    snapshot = h100_anchor._verify_v12_p2_source_binding(
        fixture["binding"],
        contract_sha256=fixture["contract_sha256"],
        p4_launch_manifest_path=fixture["p4_manifest_path"],
    )
    joined_path = str(fixture["p2_joined_path"].resolve())
    assert joined_path in snapshot
    assert str(Path(fixture["binding"]["plan_output_path"]).resolve()) in snapshot
    joined = json.loads(fixture["p2_joined_path"].read_text(encoding="utf-8"))
    joined["status"] = "P2_COMPLETE_UNVERIFIED"
    fixture["p2_joined_path"].write_text(
        json.dumps(joined, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="root-verified successful attempt"):
        h100_anchor._verify_v12_p2_source_binding(
            fixture["binding"],
            contract_sha256=fixture["contract_sha256"],
            p4_launch_manifest_path=fixture["p4_manifest_path"],
        )


def test_v12_execution_manifest_rejects_changed_fixed_identity(tmp_path, monkeypatch):
    manifest_path = Path(
        "docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json"
    )
    baseline = json.loads(manifest_path.read_text(encoding="utf-8"))
    repository = tmp_path / "isolated_manifest_repo"
    manifest_rel = Path("docs/task43_hp_adaptivity/outcomes/records/v12_execution_recovery_manifest.json")
    isolated_path = repository / manifest_rel
    isolated_path.parent.mkdir(parents=True)
    monkeypatch.setattr(h100_anchor, "_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(h100_anchor, "_V12_RECOVERY_MANIFEST_REL", manifest_rel)

    isolated_path.write_text(json.dumps(baseline, sort_keys=True) + "\n", encoding="utf-8")
    accepted = h100_anchor._load_v12_execution_recovery_manifest(
        isolated_path,
        contract_sha256=h100_anchor._V12_OLD_CONTRACT_SHA256,
    )
    assert accepted["manifest"]["review_commit_sha"] == h100_anchor._V12_REVIEW_COMMIT_SHA256
    with pytest.raises(ValueError, match="unique tracked"):
        h100_anchor._load_v12_execution_recovery_manifest(
            isolated_path.with_name("another_manifest.json"),
            contract_sha256=h100_anchor._V12_OLD_CONTRACT_SHA256,
        )

    mutations = (
        ("review_commit_sha", lambda value: value.update(review_commit_sha="0" * 40)),
        ("old_contract_sha256", lambda value: value.update(old_contract_sha256="0" * 64)),
        (
            "slot_resource_limit",
            lambda value: value["support_slots"]["D1"].update(work_seconds=541),
        ),
        (
            "p2_plan_product",
            lambda value: value["p2_sources"]["D1"].update(
                plan_output_path="benchmarks/artifacts/task43/unlisted/plan.json"
            ),
        ),
        (
            "p2_support_root",
            lambda value: value["support_slots"]["P2R"].update(root="benchmarks/artifacts/task43/unlisted"),
        ),
    )
    for _label, mutate in mutations:
        changed = copy.deepcopy(baseline)
        mutate(changed)
        isolated_path.write_text(json.dumps(changed, sort_keys=True) + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="review, contract, support roots, or P2 paths"):
            h100_anchor._load_v12_execution_recovery_manifest(
                isolated_path,
                contract_sha256=h100_anchor._V12_OLD_CONTRACT_SHA256,
            )


def test_pending_candidate_restore_is_v11_contract_scoped(tmp_path, monkeypatch):
    scenarios = (
        "valid",
        "launcher_exit",
        "watchdog_exit",
        "source_mismatch",
        "plan_mismatch",
        "raw_gate_failure",
        "nonpositive_fe_growth",
        "fe_upper_bound",
        "terminal_failure",
    )
    for scenario in scenarios:
        root = tmp_path / scenario
        candidate_root, record, contract, contract_sha = _pending_fixture(
            root, failed_condensed=scenario == "raw_gate_failure"
        )
        monkeypatch.setattr(comparison, "ROOT", root)
        monkeypatch.setattr(
            comparison,
            "_v11_source_snapshot",
            lambda: {"benchmarks/fake_source.py": "source-sha"},
        )
        monkeypatch.setattr(
            comparison,
            "_verify_v12_p2_source_binding",
            lambda *args, **kwargs: {},
        )
        if scenario == "valid":
            p2_path = root / contract["phases"]["P2"]["plan_output_path"]
            resolved = comparison._validate_v11_pending_candidate(
                candidate_root,
                record=record,
                contract=contract,
                contract_sha256=contract_sha,
                recovery_binding=record["candidate_identity"]["v12_recovery_binding"],
            )
            assert resolved[0] == candidate_root / "candidate_plan.json"
            assert resolved[0] != p2_path
            assert resolved[2] == hashlib.sha256(p2_path.read_bytes()).hexdigest()
            continue
        attempt_root = candidate_root.parent
        if scenario == "launcher_exit":
            (attempt_root / "launcher_exit_code.txt").write_text("1\n", encoding="ascii")
        elif scenario == "watchdog_exit":
            (attempt_root / "watchdog_exit_code.txt").write_text("1\n", encoding="ascii")
        elif scenario == "source_mismatch":
            manifest_path = attempt_root / "snapshots/launch_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source"][0]["sha256"] = "changed-source"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        elif scenario == "plan_mismatch":
            (candidate_root / "candidate_plan.json").write_text("different plan\n", encoding="utf-8")
        elif scenario == "raw_gate_failure":
            assert record["primary_raw_vector_audit"]["pass"] is False
        elif scenario == "nonpositive_fe_growth":
            contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"] = 2
        elif scenario == "fe_upper_bound":
            contract["phases"]["P4"]["required_fe_bounds"]["target_exclusive_upper"] = 2
        elif scenario == "terminal_failure":
            terminal_path = candidate_root / "task43_v11_primary_terminal.json"
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            terminal["status"] = "FAILED"
            terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        with pytest.raises((ValueError, FileNotFoundError)):
            comparison._validate_v11_pending_candidate(
                candidate_root,
                record=record,
                contract=contract,
                contract_sha256=contract_sha,
                recovery_binding=record["candidate_identity"]["v12_recovery_binding"],
            )


@pytest.mark.parametrize(
    "mismatch", (None, "source_identity", "coefficients", "recovery_index")
)
def test_v12_actual_candidate_reader_rejects_mixed_storage_packet(
    tmp_path, monkeypatch, mismatch
):
    real_validate = comparison._validate_v11_pending_candidate
    real_restore = comparison._restore_candidate
    real_verify_p2 = comparison._verify_v12_p2_source_binding
    fixture = _prepare_v12_compare_fixture(
        tmp_path / f"reader_{mismatch or 'valid'}", monkeypatch
    )
    candidate_root = fixture["candidate_root"]
    record = json.loads(
        (candidate_root / "task43_round1_candidate_record.json").read_text(
            encoding="utf-8"
        )
    )
    contract = json.loads(fixture["contract_path"].read_text(encoding="utf-8"))
    contract_sha = fixture["contract_sha256"]
    recovery_binding = record["candidate_identity"]["v12_recovery_binding"]
    monkeypatch.setattr(comparison, "_validate_v11_pending_candidate", real_validate)
    monkeypatch.setattr(comparison, "_restore_candidate", real_restore)
    monkeypatch.setattr(comparison, "_verify_v12_p2_source_binding", real_verify_p2)
    fixture_root = Path(fixture["contract_path"]).parents[4]
    source_path = fixture_root / "benchmarks/fake_source.py"
    record["source_identity"]["file_sha256"] = {
        "benchmarks/fake_source.py": hashlib.sha256(source_path.read_bytes()).hexdigest()
    }

    storage_arrays = {
        "mesh_geometry_coordinates_nm": np.asarray([[0.0, 1.0, 2.0]], dtype=np.float64),
        "mesh_geometry_dofmap": np.asarray([[0, 1, 2]], dtype=np.int64),
        "mesh_owned_cell_global_ids": np.asarray([31], dtype=np.int64),
        "mesh_cell_vertex_dofmap": np.asarray([[3, 4, 5, 6]], dtype=np.int64),
        "p6_function_space_dofmap": np.asarray([[7, 8, 9]], dtype=np.int64),
        "p6_owned_global_dof_block_ids": np.asarray([10, 11], dtype=np.int64),
        "p6_ghost_global_dof_block_ids": np.asarray([12], dtype=np.int64),
        "recovered_p6_local_coefficients": np.asarray(
            [1.0 + 2.0j, 3.0 - 1.0j], dtype=np.complex128
        ),
    }
    storage_path = candidate_root / "candidate_recovered_solution_storage.npz"
    np.savez_compressed(storage_path, **storage_arrays)
    record["candidate_identity"]["acceptance_contract_sha256"] = hashlib.sha256(
        ACCEPTANCE_PATH.read_bytes()
    ).hexdigest()
    record["recovered_solution_storage"].update(
        {
            "sha256": hashlib.sha256(storage_path.read_bytes()).hexdigest(),
            "arrays": {
                name: h100_anchor._array_identity(values)
                for name, values in storage_arrays.items()
            },
        }
    )

    packet_arrays = _raw_vectors()
    for name, values in storage_arrays.items():
        packet_arrays[f"recovered_{name}"] = values.copy()
    if mismatch == "coefficients":
        packet_arrays["recovered_recovered_p6_local_coefficients"][0] += 1.0
    elif mismatch == "recovery_index":
        packet_arrays["recovered_p6_function_space_dofmap"][0, 0] += 1

    packet_source_identity = copy.deepcopy(record["source_identity"])
    if mismatch == "source_identity":
        packet_source_identity["fixture_mismatch"] = "different source identity"
    packet_identity = {
        "phase": "R9_H8",
        "contract_sha256": contract_sha,
        "candidate_plan_sha256": record["candidate_plan_sha256"],
        "candidate_identity": record["candidate_identity"],
        "source_identity": packet_source_identity,
        "v12_recovery_binding": recovery_binding,
        "independent_active_fe_dofs": 2,
        "raw_full_active_scope": _raw_gate_arguments()["full_active_scope"],
        "independent_A6_raw_vector_scope": _raw_gate_arguments()["independent_a6_scope"],
        "normal_correction_count": 1,
        "extra_correction_count": 0,
        "normal_correction_audit": {
            "status": "passed",
            "correction_ksp": {"converged_reason": 2},
        },
    }
    packet_path = candidate_root / "primary_state.npz"
    packet_path.unlink()
    packet = write_v11_primary_packet(
        packet_path,
        packet_arrays,
        phase="R9_H8",
        identity=packet_identity,
    )
    record["primary_packet"] = packet
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text(json.dumps(record, sort_keys=True) + "\n", encoding="utf-8")
    terminal_path = candidate_root / "task43_v11_primary_terminal.json"
    terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
    terminal["candidate_identity"] = record["candidate_identity"]
    terminal["source_identity"] = record["source_identity"]
    terminal["primary_packet"] = packet
    terminal["endpoint_record_sha256"] = hashlib.sha256(
        endpoint_path.read_bytes()
    ).hexdigest()
    terminal_path.write_text(json.dumps(terminal, sort_keys=True) + "\n", encoding="utf-8")

    actual_arrays = {
        "mesh_geometry_coordinates_nm": storage_arrays["mesh_geometry_coordinates_nm"],
        "mesh_geometry_dofmap": storage_arrays["mesh_geometry_dofmap"],
        "mesh_owned_cell_global_ids": storage_arrays["mesh_owned_cell_global_ids"],
        "mesh_cell_vertex_dofmap": storage_arrays["mesh_cell_vertex_dofmap"],
        "p6_function_space_cell_dofmap": storage_arrays[
            "p6_function_space_dofmap"
        ],
        "p6_owned_global_dof_block_ids": storage_arrays[
            "p6_owned_global_dof_block_ids"
        ],
        "p6_ghost_global_dof_block_ids": storage_arrays[
            "p6_ghost_global_dof_block_ids"
        ],
    }
    monkeypatch.setattr(comparison, "_h100_config", lambda **_kwargs: SimpleNamespace())
    monkeypatch.setattr(
        comparison,
        "build_stage4_local_h_mesh_data",
        lambda *_args, **_kwargs: SimpleNamespace(mesh=object()),
    )
    monkeypatch.setattr(
        comparison.base,
        "_axes_from_mesh",
        lambda _mesh: tuple(np.asarray([0.0, 1.0]) for _ in range(3)),
    )
    monkeypatch.setattr(
        comparison,
        "_assert_mesh_profile",
        lambda *_args, **_kwargs: record["numerical_controls"]["mesh"],
    )
    monkeypatch.setattr(comparison, "_create_nedelec_space", lambda *_args: object())
    monkeypatch.setattr(
        comparison.base, "_actual_mesh_identity", lambda *_args: actual_arrays
    )

    class _FakeField:
        def __init__(self):
            self.x = SimpleNamespace(
                array=np.zeros_like(
                    storage_arrays["recovered_p6_local_coefficients"]
                ),
                scatter_forward=lambda: None,
            )

    monkeypatch.setattr(comparison.fem, "Function", lambda *_args, **_kwargs: _FakeField())
    if mismatch == "source_identity":
        with pytest.raises(ValueError, match="embedded primary packet identity differs"):
            comparison._restore_candidate(
                candidate_root,
                tmp_path / "restored_source_mismatch",
                v11_contract=contract,
                v11_contract_sha256=contract_sha,
                v12_recovery_binding=recovery_binding,
            )
    elif mismatch in {"coefficients", "recovery_index"}:
        with pytest.raises(ValueError, match="differ from primary"):
            comparison._restore_candidate(
                candidate_root,
                tmp_path / f"restored_{mismatch}",
                v11_contract=contract,
                v11_contract_sha256=contract_sha,
                v12_recovery_binding=recovery_binding,
            )
    else:
        restored = comparison._restore_candidate(
            candidate_root,
            tmp_path / "restored_valid",
            v11_contract=contract,
            v11_contract_sha256=contract_sha,
            v12_recovery_binding=recovery_binding,
        )
        binding = restored["v12_restoration_binding"]
        assert binding["same_array_values_dtype_and_shape"] is True
        assert set(binding["recovery_array_identities"]) == set(storage_arrays)


def test_fixed_seed8_plan_rejects_nonroot_and_alternate_seed(monkeypatch):
    contract = _contract()
    phase = contract["phases"]["P4"]
    seed = phase["seed"]
    seed_box = tuple(map(float, (*seed["lower_nm"], *seed["upper_nm"])))
    parent = {
        "selected_candidate_id": "round9_p_up",
        "parent_independent_fe_dofs": phase["required_fe_bounds"]["parent_fe_dofs"],
        "parent_marked_root_boxes": [],
        "parent_boxes_by_global_id": {8: seed_box},
        "parent_forest": SimpleNamespace(root_boxes=(seed_box,)),
        "parent_degree_by_box": {seed_box: 5},
    }
    calls = []

    def build(_cfg, *, action, candidate_id, parent, comm_size):
        calls.append((action, candidate_id, parent["marked_global_cell_ids"], comm_size))
        return {"task43_candidate": {"provenance": {}}}, {"status": "plan_built"}

    monkeypatch.setattr(round1_candidates, "_build_next_round_plan", build)
    plan = round1_candidates._build_v11_seed8_plan(
        object(), parent=parent, comm_size=1, contract=contract
    )
    assert calls == [("h_refine", "v11_r9_h8", [8], 1)]
    assert plan["task43_candidate"]["provenance"]["full_dorfer_set_not_used"] is True

    nonroot_parent = copy.deepcopy(parent)
    nonroot_parent["parent_forest"] = SimpleNamespace(root_boxes=())
    with pytest.raises(ValueError, match="not an unrefined root"):
        round1_candidates._build_v11_seed8_plan(
            object(), parent=nonroot_parent, comm_size=1, contract=contract
        )
    alternate_seed_contract = copy.deepcopy(contract)
    alternate_seed_contract["phases"]["P4"]["seed"]["global_cell_id"] = 9
    with pytest.raises(ValueError, match="seed identity"):
        round1_candidates._build_v11_seed8_plan(
            object(), parent=parent, comm_size=1, contract=alternate_seed_contract
        )


def test_v12_observer_delegates_cache_and_restores_alias_after_errors(
    tmp_path, monkeypatch
):
    from src.adaptivity.hcurl_broken_cell_trace import (
        BrokenHexCellTraceConstraintMap,
        BrokenHexCellTraceMap,
    )
    from src.adaptivity.variable_p_entity_map import (
        VariablePCellDofMap,
        VariablePGlobalEntityMap,
    )

    def compute(value):
        return value * 3

    cached_compute = lru_cache(maxsize=4)(compute)
    monkeypatch.setattr(
        round1_candidates, "build_variable_p_reference_space", cached_compute
    )
    seen_aliases = []

    def repeated_call(value):
        observed = round1_candidates.build_variable_p_reference_space
        seen_aliases.append(observed)
        assert observed is not cached_compute
        assert observed.cache_info() == cached_compute.cache_info()
        return observed(value) + observed(value)

    output_root = tmp_path / "observer_success"
    output_root.mkdir()
    assert round1_candidates._v12_observed_call(
        output_root, "fixture_cache", repeated_call, 7
    ) == 42
    assert cached_compute.cache_info().misses == 1
    assert cached_compute.cache_info().hits == 1
    assert seen_aliases and all(alias is seen_aliases[0] for alias in seen_aliases)
    assert round1_candidates.build_variable_p_reference_space is cached_compute
    success_events = [
        json.loads(line)
        for line in (output_root / "authority_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert {event["event"] for event in success_events} == {"BEGIN", "END"}
    assert any(event.get("cache_after", {}).get("hits") == 1 for event in success_events)

    degree_map = round1_candidates.HexaEntityDegreeMap(
        edges=(5,) * 12,
        faces=(5,) * 6,
        cell=5,
    )
    entity_cell = VariablePCellDofMap(
        local_cell=0,
        global_cell=17,
        degree_map=degree_map,
        active_rows=np.asarray([0], dtype=np.int64),
        trace_rows=np.asarray([0], dtype=np.int64),
        interior_rows=np.asarray([], dtype=np.int64),
        cell_info=0,
        entity_ids={},
    )
    entity_result = VariablePGlobalEntityMap(
        mesh=None,
        global_degrees={},
        global_entity_rows={},
        local_entity_rows={},
        owned_cells=(entity_cell,),
        active_rows=1,
        active_trace_rows=1,
        active_cell_interior_rows=0,
        uniform_p6_rows=1,
        uniform_p6_trace_rows=1,
        audit={},
    )
    entity_calls = []

    @lru_cache(maxsize=2)
    def build_entity_map():
        entity_calls.append("built")
        return entity_result

    monkeypatch.setattr(
        round1_candidates,
        "build_variable_p_global_entity_map",
        build_entity_map,
        raising=False,
    )

    def call_entity_map():
        first = round1_candidates.build_variable_p_global_entity_map()
        second = round1_candidates.build_variable_p_global_entity_map()
        assert first is second
        return second

    entity_root = tmp_path / "observer_entity_map"
    entity_root.mkdir()
    observed_entity = round1_candidates._v12_observed_call(
        entity_root, "fixture_entity_map", call_entity_map
    )
    assert observed_entity is entity_result
    assert entity_calls == ["built"]
    assert build_entity_map.cache_info().misses == 1
    assert build_entity_map.cache_info().hits == 1
    assert round1_candidates.build_variable_p_global_entity_map is build_entity_map
    entity_events = [
        json.loads(line)
        for line in (entity_root / "authority_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    entity_summary = next(
        event["completed_work"]
        for event in entity_events
        if event["event"] == "END"
        and event["function"].endswith("build_entity_map")
    )
    assert entity_summary["result_kind"] == "entity_map"
    assert entity_summary["degree_map_source"] == "result.owned_cells"
    assert entity_summary["degree_map_count"] == 1

    trace_cell = BrokenHexCellTraceMap(
        local_cell=0,
        global_cell=17,
        canonical_leaf=2,
        independent_rows=np.asarray([0], dtype=np.int64),
        full_trace_from_independent=np.eye(1, dtype=np.complex128),
    )
    trace_result = BrokenHexCellTraceConstraintMap(
        entity_map=entity_result,
        authority=None,
        entity_blocks={},
        work_owned_entity_blocks=(),
        owned_cells=(trace_cell,),
        independent_trace_rows=1,
        component_gram=np.eye(1, dtype=np.complex128),
        audit={},
    )
    trace_calls = []

    @lru_cache(maxsize=2)
    def build_cell_trace_map():
        trace_calls.append("built")
        return trace_result

    monkeypatch.setattr(
        round1_candidates,
        "build_broken_hexa_cell_trace_constraint_map",
        build_cell_trace_map,
        raising=False,
    )

    def call_cell_trace_map():
        first = round1_candidates.build_broken_hexa_cell_trace_constraint_map()
        second = round1_candidates.build_broken_hexa_cell_trace_constraint_map()
        assert first is second
        return second

    trace_root = tmp_path / "observer_cell_trace_map"
    trace_root.mkdir()
    observed_trace = round1_candidates._v12_observed_call(
        trace_root, "fixture_cell_trace_map", call_cell_trace_map
    )
    assert observed_trace is trace_result
    assert trace_calls == ["built"]
    assert build_cell_trace_map.cache_info().misses == 1
    assert build_cell_trace_map.cache_info().hits == 1
    assert round1_candidates.build_broken_hexa_cell_trace_constraint_map is build_cell_trace_map
    trace_events = [
        json.loads(line)
        for line in (trace_root / "authority_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    trace_summary = next(
        event["completed_work"]
        for event in trace_events
        if event["event"] == "END"
        and event["function"].endswith("build_cell_trace_map")
    )
    assert trace_summary["result_kind"] == "cell_trace_constraint_map"
    assert trace_summary["result_owned_cell_type"].endswith("BrokenHexCellTraceMap")
    assert trace_summary["degree_map_source"] == "result.entity_map.owned_cells"
    assert trace_summary["degree_map_count"] == 1

    class ObservedFailure(RuntimeError):
        pass

    original_failure = ObservedFailure("original worker failure")

    def fail(_value):
        raise original_failure

    cached_failure = lru_cache(maxsize=4)(fail)
    monkeypatch.setattr(
        round1_candidates, "build_variable_p_reference_space", cached_failure
    )
    failing_aliases = []

    def failing_call(value):
        failing_aliases.append(
            round1_candidates.build_variable_p_reference_space
        )
        return round1_candidates.build_variable_p_reference_space(value)

    error_root = tmp_path / "observer_error"
    error_root.mkdir()
    with pytest.raises(ObservedFailure, match="original worker failure") as error_info:
        round1_candidates._v12_observed_call(
            error_root, "fixture_error", failing_call, 9
        )
    assert error_info.value is original_failure
    assert failing_aliases and failing_aliases[0] is not cached_failure
    assert round1_candidates.build_variable_p_reference_space is cached_failure
    error_events = [
        json.loads(line)
        for line in (error_root / "authority_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in error_events].count("BEGIN") == 2
    assert [event["event"] for event in error_events].count("ERROR") == 2
    assert all(
        event.get("unreturned_status") == "IN_PROGRESS_AT_STOP"
        for event in error_events
        if event["event"] == "BEGIN"
    )

    summary_error = RuntimeError("observer summary failure")

    class BrokenSummaryResult:
        @property
        def owned_cells(self):
            raise summary_error

    observer_error_root = tmp_path / "observer_summary_error"
    observer_error_root.mkdir()
    with pytest.raises(RuntimeError, match="observer summary failure") as observer_error:
        round1_candidates._v12_observed_call(
            observer_error_root,
            "fixture_observer_summary_error",
            lambda: BrokenSummaryResult(),
        )
    assert observer_error.value is summary_error
    observer_error_events = [
        json.loads(line)
        for line in (observer_error_root / "authority_observations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [event["event"] for event in observer_error_events] == [
        "BEGIN",
        "OBSERVER_ERROR",
    ]
    assert observer_error_events[-1]["classification"] == "observer_return_summary_failed"


def test_v11_primary_cli_forbids_extra_and_binds_q10_output(tmp_path, monkeypatch):
    contract = _contract()
    selection = Path("docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json").resolve()
    acceptance = Path("docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json").resolve()
    phase_args = (
        ("A1_q3", "benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json"),
        ("R9_H8", contract["phases"]["P2"]["plan_output_path"]),
    )
    for phase, relative_plan in phase_args:
        entry = contract["phases"]["P3" if phase == "A1_q3" else "P4"]
        run_root = Path(contract["artifact_prefix"]) / entry["root"] / "run"
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase=phase,
            run_root=run_root,
            candidate_id=entry.get("candidate_id", entry.get("space", {}).get("candidate_id")),
            candidate_plan_path=Path(relative_plan),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )
        with pytest.raises(ValueError, match="exactly one normal correction"):
            h100_anchor._validate_v11_primary_cli(
                contract=contract,
                phase=phase,
                run_root=run_root,
                candidate_id=entry.get("candidate_id", entry.get("space", {}).get("candidate_id")),
                candidate_plan_path=Path(relative_plan),
                candidate_parent_selection_record=selection,
                candidate_acceptance_contract=acceptance,
                normal_correction_enabled=True,
                extra_correction_enabled=True,
                direct_factor_backend="mumps",
            )
    with pytest.raises(ValueError, match="unsupported V11 primary phase"):
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase="unknown",
            run_root=Path(contract["artifact_prefix"]) / "invalid" / "run",
            candidate_id="round10_p_up",
            candidate_plan_path=Path(phase_args[0][1]),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )
    with pytest.raises(ValueError, match="unique contract root"):
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase="R9_H8",
            run_root=(
                Path(contract["artifact_prefix"])
                / contract["phases"]["P4"]["root"]
                / "wrong-run-root"
            ),
            candidate_id="v11_r9_h8",
            candidate_plan_path=Path(phase_args[1][1]),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )

    cfg = SimpleNamespace()
    q_identity = h100_anchor._configure_v11_primary_endpoint(cfg, "A1_q3", contract)
    assert (q_identity["volume_quadrature_degree"], q_identity["incident_and_port_quadrature_degree"]) == (19, 32)
    assert q_identity["R13_rectangle"]["count"] == 612

    # Exercise the real q8/q10 response loop with only its old frozen data reader stubbed.
    cfg.period_x = cfg.period_y = 50.0
    cfg.domain_z_min, cfg.domain_z_max = -10.0, 130.0
    cfg.k0 = 1.0
    cfg.magnetic_field_scale_A_per_m = 1.0
    cfg.mu_r = 1.0
    monkeypatch.setattr(
        h100_anchor,
        "_v2_legacy_r10_reference",
        lambda: {
            "payload": {},
            "A_volume_total": 0.1,
            "physical_configuration_sha256": "reference-physics",
            "discretization_sha256": "reference-space",
            "phase": "A1_q",
            "record_sha256": "record",
            "payload_sha256": "modes",
            "samples_sha256": "samples",
            "solver_source_compatibility": {"pass": True},
            "samples_path": Path("saved_samples.npz"),
        },
    )
    seen_orders = []
    monkeypatch.setattr(h100_anchor, "compare_r13_modal_outputs", lambda *args, **kwargs: {"pass_10_percent_perturbation_gate": True})
    monkeypatch.setattr(h100_anchor, "_v2_field_bundle_from_npz", lambda path, order, *args: {"order": order})
    monkeypatch.setattr(h100_anchor, "_v2_field_bundle_from_capture", lambda sample, *args: sample)

    def compare_fields(reference, candidate, **kwargs):
        seen_orders.append(reference["order"])
        return {"pass_10_percent_perturbation_gate": True}

    monkeypatch.setattr(h100_anchor, "compare_field_sample_bundles", compare_fields)
    response = h100_anchor._v11_primary_q_response(
        phase="A1_q3",
        cfg=cfg,
        candidate_identity={"candidate_id": "round10_p_up"},
        endpoint_identity={
            "physical_configuration": {
                "sha256": "candidate-physics",
                "discretization_identity": {"sha256": "candidate-space"},
            }
        },
        captured={"fields": {"samples": {"q8": {"order": 8}, "q10": {"order": 10}}}},
        port_payload={},
        A_volume_total=0.1,
    )
    assert seen_orders == [8, 10]
    assert set(response["field_comparisons"]) == {"q8", "q10"}
    assert response["pass"] is True

    rows = []
    for side, m, n, polarization in h100_anchor.R13_MODE_KEYS:
        rows.append(
            {
                "side": side,
                "m": m,
                "n": n,
                "polarization": polarization,
                "outgoing_amplitude_at_boundary": [0.0, 0.0],
                "power_carrying": False,
                "power_ratio": 0.0,
                "R": 0.0,
                "T": 0.0,
            }
        )
    port_payload = {
        "orders": rows,
        "metrics": {
            "R_total": 0.0,
            "T_total": 0.0,
            "R00_s": 0.0,
            "R00_p": 0.0,
            "R00_total": 0.0,
            "dtn_port_mode_count": 612,
        },
    }
    assert len(
        h100_anchor._v2_validated_rows(
            port_payload, label="P1 V11 mode sentinel", expected=h100_anchor.R13_MODE_KEYS
        )
    ) == 612
    nonfinite_payload = copy.deepcopy(port_payload)
    nonfinite_payload["orders"][0]["outgoing_amplitude_at_boundary"] = [float("nan"), 0.0]
    with pytest.raises(ValueError):
        h100_anchor._v2_validated_rows(
            nonfinite_payload,
            label="P1 V11 nonfinite mode sentinel",
            expected=h100_anchor.R13_MODE_KEYS,
        )

    # Exercise the production field-capture loop: q8 is durable before the q10
    # writer failure is propagated to the surrounding primary-terminal handler.
    axes = (np.asarray([0.0, 50.0]), np.asarray([0.0, 50.0]), np.asarray([-10.0, 130.0]))
    monkeypatch.setattr(
        h100_anchor,
        "prepare_cell_local_vector_field_export",
        lambda _field: SimpleNamespace(
            electric_dgq6=object(),
            curl_electric_dgq6=object(),
            source_degree=6,
            target_degree=6,
            representation="DGQ6",
        ),
    )
    monkeypatch.setattr(h100_anchor, "_mesh_axes", lambda _mesh, _comm: axes)
    monkeypatch.setattr(h100_anchor, "_assert_mesh_profile", lambda *_args, **_kwargs: {"pass": True})
    monkeypatch.setattr(
        h100_anchor,
        "build_common_volume_quadrature",
        lambda _axes, *, gauss_order: SimpleNamespace(
            points_nm=np.asarray([[float(gauss_order), 0.0, 0.0]]),
            weights_nm3=np.asarray([1.0]),
        ),
    )
    monkeypatch.setattr(
        h100_anchor,
        "sample_cell_local_vector_fields",
        lambda _fields, points: {
            "E_total": np.ones((len(points), 3), dtype=np.complex128),
            "curl_E_total": np.ones((len(points), 3), dtype=np.complex128),
        },
    )
    monkeypatch.setattr(
        h100_anchor,
        "magnetic_field_from_electric_curl",
        lambda curl, **_kwargs: np.asarray(curl),
    )

    class SerialComm:
        rank = 0

        @staticmethod
        def allgather(value):
            return [value]

    q8_path = tmp_path / "primary_field_sample_q8.npz"
    primary_path = tmp_path / "primary_state.npz"
    primary_packet = write_v11_primary_packet(
        primary_path,
        _raw_vectors(),
        phase="A1_q3",
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
    )
    sample_records = {}
    writes = []
    q8_sha_before_q10_failure = None

    def persist_sample(order, sample):
        nonlocal q8_sha_before_q10_failure
        writes.append(order)
        if order == 10:
            raise OSError("injected q10 output failure")
        write_v11_primary_field_sample(
            q8_path,
            order,
            sample,
            identity={"phase": "A1_q3", "contract_sha256": "fixture"},
            sample_records=sample_records,
        )
        q8_sha_before_q10_failure = hashlib.sha256(q8_path.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="field sample postprocessing failed collectively"):
        h100_anchor._field_capture(
            object(),
            SimpleNamespace(mesh=object()),
            SimpleNamespace(magnetic_field_scale_A_per_m=1.0, k0=1.0, mu_r=1.0),
            SerialComm(),
            reference_axes=None,
            geometry_profile="h100",
            sample_fields=True,
            on_sample=persist_sample,
        )
    assert writes == [8, 10]
    assert q8_path.is_file()
    assert q8_sha_before_q10_failure is not None
    failure_terminal = h100_anchor._write_v11_partial_terminal(
        tmp_path,
        phase="A1_q3",
        source_identity={"file_sha256": {"fake.py": "sha"}},
        captured={
            "v11_primary_packet": primary_packet,
            "v11_primary_sample_records": sample_records,
        },
        candidate_identity={"candidate_id": "round10_p_up"},
        error="field sample postprocessing failed collectively",
    )
    terminal = json.loads(Path(failure_terminal["path"]).read_text(encoding="utf-8"))
    assert terminal["primary_packet"]["npz_sha256"] == primary_packet["npz_sha256"]
    assert terminal["primary_samples"]["q8"]["npz_sha256"] == sample_records["q8"]["npz_sha256"]
    assert hashlib.sha256(q8_path.read_bytes()).hexdigest() == q8_sha_before_q10_failure


def test_v11_terminal_failure_is_incomplete_and_primary_only(tmp_path, monkeypatch):
    path = tmp_path / "run"
    path.mkdir()
    primary_packet = write_v11_primary_packet(
        path / "primary_state.npz",
        _raw_vectors(),
        phase="A1_q3",
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
    )
    sample_path = path / "primary_field_sample_q8.npz"
    sample = write_v11_primary_field_sample(
        sample_path,
        8,
        {"points_nm": np.zeros((2, 3)), "E_total": np.ones((2, 3))},
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
        sample_records={},
    )
    endpoint_path = path / "task43_round1_candidate_record.json"
    endpoint_path.write_text(
        json.dumps(
            {
                "schema": "task43.v11.primary-endpoint.v1",
                "status": "SOLVED_PRIMARY_Q_RESPONSE_PASS",
                "official_result": False,
                "selection_eligible": False,
                "selection_candidate": False,
                "candidate_selected": False,
                "continuation_all_false": True,
                "pass": True,
                "passed": True,
                "solver": {"official_result": False},
                "gates": {"pass": True, "status": "passed"},
                "primary_packet": primary_packet,
            }
        ),
        encoding="utf-8",
    )
    packet_hash = primary_packet["npz_sha256"]
    sample_hash = sample["npz_sha256"]
    result = h100_anchor._write_v11_partial_terminal(
        path,
        phase="A1_q3",
        source_identity={"file_sha256": {"fake.py": "sha"}},
        captured={
            "v11_primary_packet": primary_packet,
            "v11_primary_sample_records": {"q8": sample},
        },
        candidate_identity={"candidate_id": "round10_p_up"},
        error=RuntimeError("mesh sentinel"),
    )
    terminal = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert terminal["status"] == "FAILED"
    assert terminal["official_result"] is False
    assert terminal["passed"] is False
    assert terminal["selection_eligible"] is False
    assert terminal["continuation_all_false"] is True
    assert terminal["primary_packet"]["npz_sha256"] == packet_hash
    assert terminal["primary_samples"]["q8"]["npz_sha256"] == sample_hash
    demoted = json.loads(endpoint_path.read_text(encoding="utf-8"))
    assert demoted["pass"] is False
    assert demoted["passed"] is False
    assert demoted["gates"]["pass"] is False
    assert demoted["official_result"] is False
    assert result["sha256"] == hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest()

    root = tmp_path / "terminal_writer_failure"
    candidate_root, pending_record, contract, contract_sha = _pending_fixture(root)
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(
        comparison,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    monkeypatch.setattr(
        comparison,
        "_verify_v12_p2_source_binding",
        lambda *args, **kwargs: {},
    )
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text(
        json.dumps(
            {
                "schema": "task43.v11.primary-endpoint.v1",
                "phase": "R9_H8",
                "status": "SOLVED_PENDING_POSTPROCESS",
                "pass": True,
                "passed": True,
                "official_result": False,
                "selection_eligible": False,
                "selection_candidate": False,
                "candidate_selected": False,
                "continuation_all_false": True,
                "solver": {"official_result": False},
                "gates": {"pass": True, "status": "passed"},
            }
        ),
        encoding="utf-8",
    )
    primary_path = candidate_root / "primary_state.npz"
    primary_packet_sha = hashlib.sha256(primary_path.read_bytes()).hexdigest()
    q8_path = candidate_root / "primary_field_sample_q8_wrapper.npz"
    q8_sample = write_v11_primary_field_sample(
        q8_path,
        8,
        {"points_nm": np.zeros((2, 3)), "E_total": np.ones((2, 3))},
        identity={"phase": "R9_H8", "contract_sha256": contract_sha},
        sample_records={},
    )
    q8_sha = hashlib.sha256(q8_path.read_bytes()).hexdigest()
    success_terminal_path = candidate_root / "attempted_success_terminal.json"
    failed_terminal_writes = []
    original_replace = candidate_checkpoints._replace_atomically

    def fail_success_terminal_output(path_arg, writer):
        if Path(path_arg) == success_terminal_path:
            failed_terminal_writes.append(str(path_arg))
            raise OSError("injected successful terminal output failure")
        return original_replace(path_arg, writer)

    monkeypatch.setattr(candidate_checkpoints, "_replace_atomically", fail_success_terminal_output)
    endpoint_demotion_failures = []
    original_atomic_json = h100_anchor.write_atomic_json

    def fail_endpoint_demotion(path_arg, record_arg, **kwargs):
        if Path(path_arg) == endpoint_path:
            endpoint_demotion_failures.append(str(path_arg))
            raise OSError("injected partial-terminal endpoint demotion failure")
        return original_atomic_json(path_arg, record_arg, **kwargs)

    monkeypatch.setattr(h100_anchor, "write_atomic_json", fail_endpoint_demotion)
    source_identity = pending_record["source_identity"]
    candidate_identity = pending_record["candidate_identity"]

    def fake_run_impl(
        case,
        run_root,
        v11_primary_diagnostic_phase,
        _failure_context=None,
    ):
        assert case == "round1_candidate_mpi1"
        _failure_context.update(
            run_root=Path(run_root),
            run_root_acquired=True,
            phase=v11_primary_diagnostic_phase,
            source_identity=source_identity,
            captured={
                "v11_primary_packet": pending_record["primary_packet"],
                "v11_primary_sample_records": {"q8": q8_sample},
            },
            candidate_identity=candidate_identity,
        )
        return h100_anchor.write_v11_primary_terminal(
            success_terminal_path,
            phase=v11_primary_diagnostic_phase,
            status="SOLVED_PENDING_POSTPROCESS",
            source_identity=source_identity,
            candidate_identity=candidate_identity,
            contract_sha256=contract_sha,
            candidate_plan_sha256=pending_record["candidate_plan_sha256"],
            primary_packet=pending_record["primary_packet"],
            primary_samples={"q8": q8_sample},
            endpoint_record_path=endpoint_path,
        )

    with pytest.raises(OSError, match="successful terminal output failure"):
        h100_anchor._run_with_v3_failure_terminal(
            fake_run_impl,
            case="round1_candidate_mpi1",
            run_root=candidate_root,
            v11_primary_diagnostic_phase="R9_H8",
        )
    assert failed_terminal_writes == [str(success_terminal_path)]
    assert endpoint_demotion_failures == [str(endpoint_path)]
    assert hashlib.sha256(primary_path.read_bytes()).hexdigest() == primary_packet_sha
    assert hashlib.sha256(q8_path.read_bytes()).hexdigest() == q8_sha
    partial_path = candidate_root / "task43_v11_partial_terminal.json"
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    assert partial["primary_packet"]["npz_sha256"] == pending_record["primary_packet"]["npz_sha256"]
    assert partial["primary_samples"]["q8"]["npz_sha256"] == q8_sample["npz_sha256"]
    assert json.loads(endpoint_path.read_text(encoding="utf-8"))["pass"] is True

    attempt_root = candidate_root.parent
    (attempt_root / "launcher_exit_code.txt").write_text("1\n", encoding="ascii")
    with pytest.raises(ValueError, match="launcher_exit_code"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=pending_record,
            contract=contract,
            contract_sha256=contract_sha,
            recovery_binding=pending_record["candidate_identity"]["v12_recovery_binding"],
        )
    (attempt_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
    with pytest.raises(ValueError, match="success terminal is missing or conflicts"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=pending_record,
            contract=contract,
            contract_sha256=contract_sha,
            recovery_binding=pending_record["candidate_identity"]["v12_recovery_binding"],
        )


def test_v11_empty_root_guard_preserves_existing_file_hash(tmp_path):
    run_root = tmp_path / "nonempty"
    run_root.mkdir()
    marker = run_root / "previous_negative.json"
    marker.write_bytes(b"preserve-me\n")
    before_files = {
        child.relative_to(run_root).as_posix(): hashlib.sha256(
            child.read_bytes()
        ).hexdigest()
        for child in run_root.iterdir()
        if child.is_file()
    }

    class SerialComm:
        rank = 0

        @staticmethod
        def bcast(value, root=0):
            return value

        @staticmethod
        def Barrier():
            return None

    comm = SerialComm()
    acquired = []

    def fake_run_impl(
        case,
        run_root,
        v11_primary_diagnostic_phase,
        _failure_context=None,
    ):
        assert case == "round1_candidate_mpi1"
        assert v11_primary_diagnostic_phase == "A1_q3"
        h100_anchor._acquire_empty_run_root(run_root, comm)
        _failure_context["run_root_acquired"] = True
        acquired.append(True)

    with pytest.raises(RuntimeError, match="refusing to overwrite nonempty output root"):
        h100_anchor._run_with_v3_failure_terminal(
            fake_run_impl,
            case="round1_candidate_mpi1",
            run_root=run_root,
            v11_primary_diagnostic_phase="A1_q3",
        )
    assert acquired == []
    after_files = {
        child.relative_to(run_root).as_posix(): hashlib.sha256(
            child.read_bytes()
        ).hexdigest()
        for child in run_root.iterdir()
        if child.is_file()
    }
    assert after_files == before_files
    assert list(run_root.iterdir()) == [marker]
    assert not (run_root / "task43_v11_partial_terminal.json").exists()


def test_v11_common_points_identity_and_fe_bounds(tmp_path, monkeypatch):
    axes = (
        np.asarray([0.0, 50.0]),
        np.asarray([0.0, 50.0]),
        np.asarray([-10.0, 130.0]),
    )
    q8 = build_common_volume_quadrature([axes, axes, axes], gauss_order=8)
    q10 = build_common_volume_quadrature([axes, axes, axes], gauss_order=10)
    assert float(np.sum(q8.weights_nm3)) == pytest.approx(350000.0, abs=1.0e-8)
    assert float(np.sum(q10.weights_nm3)) == pytest.approx(350000.0, abs=1.0e-8)
    assert np.array_equal(q8.points_nm, build_common_volume_quadrature([axes] * 3, gauss_order=8).points_nm)
    assert np.array_equal(q8.weights_nm3, build_common_volume_quadrature([axes] * 3, gauss_order=8).weights_nm3)
    assert not np.array_equal(q8.points_nm, q10.points_nm)

    bounds = _contract()["phases"]["P4"]["required_fe_bounds"]
    assert int(bounds["strict_added_dofs_minimum"]) > 0
    root = tmp_path / "actual-fe-bound-gate"
    candidate_root, record, contract, contract_sha = _pending_fixture(root)
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(
        comparison,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    monkeypatch.setattr(
        comparison,
        "_verify_v12_p2_source_binding",
        lambda *args, **kwargs: {},
    )
    contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"] = 2
    with pytest.raises(ValueError, match="strict growth bounds"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=record,
            contract=contract,
            contract_sha256=contract_sha,
            recovery_binding=record["candidate_identity"]["v12_recovery_binding"],
        )


def test_main_reaches_v11_mesh_sentinel_with_watchdog_identity(tmp_path, monkeypatch):
    frozen = _contract()
    repository = tmp_path / "isolated_repo"
    contract = copy.deepcopy(frozen)
    contract["artifact_prefix"] = str(
        repository / "benchmarks/artifacts/task43/v11_science"
    )
    contract["phases"]["P2"]["plan_output_path"] = (
        "benchmarks/artifacts/task43/v11_science/recovery_v12/support/space_and_saved_primary_attempt2/plan_output/"
        "plans/v11_r9_h8.json"
    )
    contract["phases"]["P3"]["root"] = "support/p1_a1_q3_main_sentinel"
    contract["phases"]["P4"]["root"] = "support/p1_r9_h8_main_sentinel"

    selection_path = repository / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
    acceptance_path = repository / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text("isolated accepted R9 selection\n", encoding="utf-8")
    acceptance_path.write_text("isolated frozen acceptance\n", encoding="utf-8")
    selection_sha = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    acceptance_sha = hashlib.sha256(acceptance_path.read_bytes()).hexdigest()
    frozen_input_by_role = {item["role"]: item for item in frozen["inputs"]}

    r10_plan_path = repository / "benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json"
    r10_plan = {
        "task43_candidate": {
            "candidate_id": "round10_p_up",
            "action": "p_up",
            "provenance": {},
        }
    }
    r10_plan_path.parent.mkdir(parents=True, exist_ok=True)
    r10_plan_path.write_text(
        json.dumps(r10_plan, sort_keys=True) + "\n", encoding="utf-8"
    )
    r10_plan_sha = hashlib.sha256(r10_plan_path.read_bytes()).hexdigest()
    h_plan_path = repository / contract["phases"]["P2"]["plan_output_path"]
    h_plan = {
        "task43_candidate": {
            "candidate_id": "v11_r9_h8",
            "action": "h_refine",
            "provenance": {
                "marked_global_cell_ids_source": "v11_predeclared_seed8",
                "v11_seed": frozen["phases"]["P4"]["seed"],
                "accepted_parent_selection_sha256": selection_sha,
            },
        }
    }
    h_plan_path.parent.mkdir(parents=True, exist_ok=True)
    h_plan_path.write_text(json.dumps(h_plan, sort_keys=True) + "\n", encoding="utf-8")
    h_plan_sha = hashlib.sha256(h_plan_path.read_bytes()).hexdigest()

    contract["inputs"] = [
        {
            "role": "R9_selection_transition",
            "path": str(selection_path.relative_to(repository)),
            "sha256": selection_sha,
        },
        {
            "role": "frozen_acceptance_contract",
            "path": str(acceptance_path.relative_to(repository)),
            "sha256": acceptance_sha,
        },
        {
            "role": "R10_authority_plan",
            "path": str(r10_plan_path.relative_to(repository)),
            "sha256": r10_plan_sha,
        },
        frozen_input_by_role["R9_authority_plan"],
        frozen_input_by_role["seed_geometry_audit"],
    ]
    contract_path = repository / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_bytes = (json.dumps(contract, sort_keys=True) + "\n").encode()
    contract_path.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()

    monkeypatch.setattr(h100_anchor, "_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(
        h100_anchor,
        "_load_v11_primary_contract",
        lambda _path: (contract, contract_sha),
    )
    recovery_support = Path(
        "benchmarks/artifacts/task43/v11_science/recovery_v12/support/space_and_saved_primary_attempt2"
    )
    recovery_source_paths = {
        "D1": {
            "support_root": "benchmarks/artifacts/task43/v11_science/recovery_v12/support/authority_profile_attempt1",
            "output_root": "benchmarks/artifacts/task43/v11_science/recovery_v12/support/authority_profile_attempt1/plan_output",
            "plan_output_path": "benchmarks/artifacts/task43/v11_science/recovery_v12/support/authority_profile_attempt1/plan_output/plans/v11_r9_h8.json",
            "audit_path": "benchmarks/artifacts/task43/v11_science/recovery_v12/support/authority_profile_attempt1/plan_output/plans/v11_r9_h8.audit.json",
            "bundle_path": "benchmarks/artifacts/task43/v11_science/recovery_v12/support/authority_profile_attempt1/plan_output/plan_audit.json",
        },
        "P2R": {
            "support_root": recovery_support.as_posix(),
            "output_root": (recovery_support / "plan_output").as_posix(),
            "plan_output_path": (recovery_support / "plan_output/plans/v11_r9_h8.json").as_posix(),
            "audit_path": (recovery_support / "plan_output/plans/v11_r9_h8.audit.json").as_posix(),
            "bundle_path": (recovery_support / "plan_output/plan_audit.json").as_posix(),
        },
    }
    recovery_manifest_path = repository / h100_anchor._V12_RECOVERY_MANIFEST_REL
    recovery_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_manifest_path.write_text("{}\n", encoding="utf-8")
    recovery_context = {
        "manifest": {"p2_sources": recovery_source_paths},
        "manifest_path": str(recovery_manifest_path.resolve()),
        "manifest_sha256": hashlib.sha256(recovery_manifest_path.read_bytes()).hexdigest(),
    }
    p2_source = {
        "p2_source_id": "P2R",
        **{
            key: str((repository / value).resolve())
            for key, value in recovery_source_paths["P2R"].items()
        },
    }
    monkeypatch.setattr(h100_anchor, "_V12_P2_SOURCE_PATHS", recovery_source_paths)
    monkeypatch.setattr(
        h100_anchor,
        "_load_v12_execution_recovery_manifest",
        lambda *_args, **_kwargs: recovery_context,
    )
    monkeypatch.setattr(
        h100_anchor,
        "_resolve_v12_p2_source",
        lambda *_args, **_kwargs: p2_source,
    )
    monkeypatch.setattr(h100_anchor, "_verify_v12_p2_source_binding", lambda *_args, **_kwargs: {})

    class MeshSentinel(RuntimeError):
        pass

    def mesh_sentinel(*_args, **_kwargs):
        raise MeshSentinel("reached real h100 main mesh builder")

    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", mesh_sentinel)
    run_impl_controls = []
    extra_helper_calls = []

    def fail_if_extra_correction_called(*args, **kwargs):
        extra_helper_calls.append({"args": repr(args), "kwargs": repr(kwargs)})
        raise AssertionError("V11 main sentinel called the forbidden extra-correction helper")

    monkeypatch.setattr(h100_anchor, "_same_lu_tightening", fail_if_extra_correction_called)
    real_run_impl = h100_anchor._run_impl

    @wraps(real_run_impl)
    def observe_run_impl(*args, **kwargs):
        run_impl_controls.append(
            {
                "phase": kwargs.get("v11_primary_diagnostic_phase"),
                "same_lu_tightening_enabled": kwargs.get(
                    "same_lu_tightening_enabled"
                ),
                "same_lu_solve_residual_correction_enabled": kwargs.get(
                    "same_lu_solve_residual_correction_enabled"
                ),
            }
        )
        assert kwargs.get("same_lu_tightening_enabled") is False
        return real_run_impl(*args, **kwargs)

    monkeypatch.setattr(h100_anchor, "_run_impl", observe_run_impl)
    calls = []
    runtime_environments = []
    live_phase_path = Path(os.environ["PHYSICAL_WATCHDOG_PHASE_PATH"]).resolve()
    assert live_phase_path.is_absolute()
    assert live_phase_path.parent.is_dir()
    assert not live_phase_path.exists()

    def archive_phase(label: str, *, remove_live: bool) -> None:
        assert live_phase_path.is_file()
        archive_path = tmp_path / "watchdog_phase_archive" / f"{label}.json"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(live_phase_path, archive_path)
        if remove_live:
            live_phase_path.unlink()

    real_identity = h100_anchor._require_v11_watchdog_worker_identity

    def observe_identity(**kwargs):
        identity = real_identity(**kwargs)
        calls.append(identity)
        return identity

    monkeypatch.setattr(h100_anchor, "_require_v11_watchdog_worker_identity", observe_identity)
    real_runtime_envelope = h100_anchor._check_v11_runtime_envelope

    def observe_runtime_envelope(comm, **kwargs):
        environment = real_runtime_envelope(comm, **kwargs)
        runtime_environments.append(environment)
        return environment

    monkeypatch.setattr(h100_anchor, "_check_v11_runtime_envelope", observe_runtime_envelope)

    for phase, candidate_id, plan_path, plan, plan_sha, action in (
        ("A1_q3", "round10_p_up", r10_plan_path, r10_plan, r10_plan_sha, "p_up"),
        ("R9_H8", "v11_r9_h8", h_plan_path, h_plan, h_plan_sha, "h_refine"),
    ):
        run_root = (
            Path(contract["artifact_prefix"])
            / contract["phases"]["P3" if phase == "A1_q3" else "P4"]["root"]
            / "run"
        )
        def accepted_inputs(**_kwargs):
            return (
                plan,
                plan_sha,
                {
                    "action": action,
                    "accepted_parent_selection_sha256": selection_sha,
                    "acceptance_contract_sha256": acceptance_sha,
                },
            )

        monkeypatch.setattr(h100_anchor, "_validate_accepted_candidate_inputs", accepted_inputs)
        argv = [
            "--case",
            "round1_candidate_mpi1",
            "--run-root",
            str(run_root),
            "--candidate-plan",
            str(plan_path),
            "--candidate-id",
            candidate_id,
            "--candidate-acceptance-contract",
            str(acceptance_path),
            "--candidate-parent-selection-record",
            str(selection_path),
            "--primary-diagnostic-phase",
            phase,
            "--primary-diagnostic-contract",
            str(contract_path),
            "--execution-recovery-manifest",
            str(recovery_manifest_path),
            "--direct-factor-backend",
            "mumps",
            "--same-lu-solve-residual-correction",
        ]
        with pytest.raises(MeshSentinel, match="reached real h100 main mesh builder"):
            h100_anchor.main(argv)
        partial_path = run_root / "task43_v11_partial_terminal.json"
        assert partial_path.is_file()
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        assert partial["phase"] == phase
        assert partial["official_result"] is False
        assert partial["passed"] is False
        archive_phase(phase, remove_live=True)

    assert len(calls) >= 6
    assert [item["phase"] for item in run_impl_controls] == ["A1_q3", "R9_H8"]
    assert all(item["same_lu_tightening_enabled"] is False for item in run_impl_controls)
    assert extra_helper_calls == []
    assert all(item["direct_watchdog_parent_verified"] for item in calls)
    assert all(item["tracer_descends_from_watchdog"] for item in calls)
    assert all(
        all(tid["cpu_list"] == [1] for tid in item["worker_tid_affinities"])
        for item in calls
    )
    for key in (
        "worker_pid",
        "worker_parent_pid",
        "worker_start_ticks",
        "watchdog_pid",
        "watchdog_start_ticks",
        "tracer_pid",
        "tracer_start_ticks",
        "phase_path",
    ):
        assert len({item[key] for item in calls}) == 1

    # Run the actual P2 CLI through plan construction and ledger creation, then
    # stop at its existing mesh-authority audit boundary, all under tmp_path.
    monkeypatch.setattr(round1_candidates, "ROOT", repository)
    monkeypatch.setattr(round1_candidates, "DEFAULT_ACCEPTANCE", acceptance_path)
    monkeypatch.setattr(
        round1_candidates,
        "_check_v11_runtime_envelope",
        observe_runtime_envelope,
    )
    output_root = (repository / contract["phases"]["P2"]["plan_output_path"]).parent.parent
    shutil.rmtree(output_root)
    monkeypatch.setattr(round1_candidates, "DEFAULT_OUTPUT", output_root)
    monkeypatch.setattr(
        round1_candidates,
        "_load_v11_primary_contract",
        lambda _path: (contract, contract_sha),
    )
    monkeypatch.setattr(
        round1_candidates,
        "_load_v12_execution_recovery_manifest",
        lambda *_args, **_kwargs: recovery_context,
    )
    monkeypatch.setattr(
        round1_candidates,
        "_resolve_v12_p2_source",
        lambda _recovery, *, attempt_root: p2_source
        if Path(attempt_root).resolve() == Path(p2_source["support_root"]).resolve()
        else (_ for _ in ()).throw(ValueError("unexpected P2 selector")),
    )
    monkeypatch.setenv("TASK43_V11_ATTEMPT_ROOT", p2_source["support_root"])
    monkeypatch.setattr(
        round1_candidates,
        "_v11_input_snapshot",
        lambda _contract, roles: {role: {"path": "isolated", "sha256": "fixture"} for role in roles},
    )
    monkeypatch.setattr(
        round1_candidates,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    seed = contract["phases"]["P4"]["seed"]
    seed_box = tuple(map(float, (*seed["lower_nm"], *seed["upper_nm"])))
    r9_plan_item = frozen_input_by_role["R9_authority_plan"]
    seed_audit_item = frozen_input_by_role["seed_geometry_audit"]
    r9_plan_path = Path(r9_plan_item["path"]).resolve()
    r9_plan = json.loads(r9_plan_path.read_text(encoding="utf-8"))
    cfg_for_parent = round1_candidates._h100_config(
        kind="empty_h_active_p3",
        case_name="task43_v11_r9_h8_candidate_plan_mpi1",
        geometry_profile="initial_180",
    )
    parent_forest = round1_candidates._build_forest(
        cfg_for_parent,
        comm_size=1,
        marked_root_boxes=r9_plan["marked_root_boxes"],
        maximum_level=int(r9_plan["maximum_level"]),
        allow_no_refinement=bool(r9_plan["allow_no_refinement"]),
    )
    parent_degree_by_box = {
        tuple(map(float, (*row["lower"], *row["upper"])))
        : int(row["degree"])
        for row in r9_plan["cell_interior_degrees"]
    }
    assert len(parent_forest.root_boxes) == 180
    assert len(parent_forest.leaves) == 180
    assert set(parent_degree_by_box) == {cell.box for cell in parent_forest.leaves}
    seed_audit_path = Path(seed_audit_item["path"]).resolve()
    seed_audit = json.loads(seed_audit_path.read_text(encoding="utf-8"))
    assert seed_audit["seed"]["global_cell_id"] == 8
    assert tuple(
        map(
            float,
            (
                *seed_audit["seed"]["lower_nm"],
                *seed_audit["seed"]["upper_nm"],
            ),
        )
    ) == seed_box
    assert parent_degree_by_box[seed_box] == int(seed["parent_degree"])
    assert seed_box in parent_forest.root_boxes
    parent = {
        "selected_candidate_id": "round9_p_up",
        "parent_independent_fe_dofs": int(contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"]),
        "parent_marked_root_boxes": tuple(
            tuple(map(float, (*row["lower"], *row["upper"])))
            for row in r9_plan["marked_root_boxes"]
        ),
        "parent_boxes_by_global_id": {8: seed_box},
        "parent_forest": parent_forest,
        "parent_degree_by_box": parent_degree_by_box,
        "marked_global_cell_ids": [],
        "marked_boxes": (),
        "selection_path": str(selection_path),
        "selection_sha256": selection_sha,
        "parent_run_root": str(repository / "accepted_R9/run"),
        "parent_record_sha256": "1" * 64,
        "parent_storage_sha256": "2" * 64,
        "parent_plan_sha256": "3" * 64,
        "parent_comparison_path": str(repository / "accepted_R9/comparison.json"),
        "parent_comparison_sha256": "4" * 64,
    }

    mesh = SimpleNamespace(
        geometry=SimpleNamespace(
            x=np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], dtype=np.float64),
            dofmap=np.asarray([[0, 1, 2, 3]], dtype=np.int32),
        )
    )
    audit_configs = []
    actual_forests = []
    fake_authorities = []

    def fake_mesh_data(cfg, plan_path, *, comm):
        audit_configs.append(cfg)
        candidate_plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
        if actual_forests:
            forest = actual_forests[0]
        else:
            marked_boxes = [
                tuple(map(float, (*row["lower"], *row["upper"])))
                for row in candidate_plan["marked_root_boxes"]
            ]
            forest = round1_candidates._build_forest(
                cfg,
                comm_size=comm.size,
                marked_root_boxes=marked_boxes,
                maximum_level=int(candidate_plan["maximum_level"]),
                allow_no_refinement=bool(candidate_plan.get("allow_no_refinement", False)),
            )
            actual_forests.append(forest)
        degree_rows = candidate_plan["cell_interior_degrees"]
        degree_histogram = {}
        owned_cells = []
        for row in degree_rows:
            degree = int(row["degree"])
            label = f"p{degree}"
            degree_histogram[label] = degree_histogram.get(label, 0) + 1
            owned_cells.append(
                SimpleNamespace(
                    degree_map=round1_candidates.HexaEntityDegreeMap.uniform(degree)
                )
            )
        local_context = SimpleNamespace(
            audit={
                "root_cell_count": len(forest.root_boxes),
                "leaf_cell_count": len(forest.leaves),
                "hanging_patch_count": len(forest.hanging_faces),
                "forest": {
                    "closure_split_counts": dict(forest.audit["closure_split_counts"]),
                    "leaf_catalog_sha256": forest.audit["leaf_catalog_sha256"],
                },
            },
            forest=forest,
        )
        mesh_data = SimpleNamespace(
            mesh=mesh,
            mesh_cell_type_resolved="hexahedron",
            local_h_context=local_context,
        )
        entity_map = SimpleNamespace(
            owned_cells=owned_cells,
            active_cell_interior_rows=110472,
            uniform_p6_rows=400000,
            uniform_p6_trace_rows=100,
            active_rows=110473,
            audit={"full_p6_global_matrix_constructed": False},
        )
        degree_plan = SimpleNamespace(
            audit={
                "cell_degree_counts": degree_histogram,
                "cell_degree_plan_sha256": candidate_plan["cell_interior_degree_plan_sha256"],
                "runtime_global_entity_degree_sha256": "synthetic-runtime-entity-map",
                "mesh_cell_box_catalog_sha256": candidate_plan["root_cell_box_catalog_sha256"],
                "minimum_trace_degree": int(candidate_plan["trace_degree"]),
                "pass": True,
            },
            entity_map=entity_map,
        )
        fake_authorities.append(
            SimpleNamespace(
                audit={
                    "pass": True,
                    "raw_broken_active_fe_dofs": 120000,
                    "active_fe_dof_gate_policy": "synthetic native-authority boundary",
                    "active_fe_dof_gate_limit": 237600,
                    "active_fe_dof_gate_pass": True,
                    "physical_trace": {
                        "trace_degree_values": [int(candidate_plan["trace_degree"]) ]
                    },
                    "trace_constraints": {
                        "hanging_slave_rows": len(forest.hanging_faces),
                        "hanging_or_periodic_slave_rows_globally_numbered": False,
                    },
                },
                degree_plan=degree_plan,
                trace_constraints=SimpleNamespace(independent_trace_rows=1),
            )
        )
        return mesh_data

    monkeypatch.setattr(round1_candidates, "build_stage4_local_h_mesh_data", fake_mesh_data)
    monkeypatch.setattr(
        round1_candidates,
        "build_stage4_local_h_reduction_authority",
        lambda *_args, **_kwargs: fake_authorities[-1],
    )
    monkeypatch.setattr(
        round1_candidates,
        "_load_accepted_parent_state",
        lambda *_args, **_kwargs: parent_load_calls.append(True) or parent,
    )
    monkeypatch.setattr(round1_candidates, "DEFAULT_ACCEPTANCE", acceptance_path)

    def p2_arguments(selected_output_root):
        return [
            "--accepted-parent-selection-record",
            str(selection_path),
            "--primary-diagnostic-contract",
            str(contract_path),
            "--execution-recovery-manifest",
            str(recovery_manifest_path),
            "--output-root",
            str(selected_output_root),
        ]

    parent_load_calls = []
    failure_support = repository / "benchmarks/artifacts/task43/v11_science/recovery_v12/support/a2_q10_failure"
    failure_output_root = failure_support / "plan_output"
    failure_plan_path = failure_output_root / "plans/v11_r9_h8.json"
    failure_support.mkdir(parents=True, exist_ok=True)
    failure_p2_source = {
        "p2_source_id": "P2R",
        "support_root": str(failure_support.resolve()),
        "output_root": str(failure_output_root.resolve()),
        "plan_output_path": str(failure_plan_path.resolve()),
        "audit_path": str(
            (failure_output_root / "plans/v11_r9_h8.audit.json").resolve()
        ),
        "bundle_path": str((failure_output_root / "plan_audit.json").resolve()),
    }
    q10_error = ValueError("synthetic q10 saved-data comparison failure")

    def fail_after_q8_checkpoint(_contract, *, checkpoint_callback):
        for stage in ("raw", "modal", "q8"):
            checkpoint_callback(
                stage,
                {
                    "fixture_substage_value": stage,
                    "pass": True,
                    "official_result": False,
                },
            )
        raise q10_error

    monkeypatch.setattr(
        round1_candidates,
        "_resolve_v12_p2_source",
        lambda _recovery, *, attempt_root: failure_p2_source
        if Path(attempt_root).resolve() == Path(failure_p2_source["support_root"]).resolve()
        else (_ for _ in ()).throw(ValueError("unexpected failure P2 selector")),
    )
    monkeypatch.setenv("TASK43_V11_ATTEMPT_ROOT", failure_p2_source["support_root"])
    monkeypatch.setattr(
        round1_candidates,
        "_v11_saved_a2_primary_q_response",
        fail_after_q8_checkpoint,
    )
    with pytest.raises(
        RuntimeError,
        match="saved A2 primary raw/q response failed before space authority",
    ):
        round1_candidates.main(p2_arguments(failure_output_root))
    failed_a2_path = failure_output_root / "A2_saved_primary_q_response.json"
    failed_a2 = json.loads(failed_a2_path.read_text(encoding="utf-8"))
    assert failed_a2["error"] == "ValueError: synthetic q10 saved-data comparison failure"
    assert failed_a2["failure_stage"] == "q10"
    assert failed_a2["failure_origin"] == "saved_data_recomputation"
    assert failed_a2["pass"] is False
    assert failed_a2["passed"] is False
    assert failed_a2["official_result"] is False
    assert failed_a2["selection_or_transition_authority"] is False
    assert failed_a2["continuation"] is False
    assert failed_a2["substage_statuses"] == {
        "raw": "CHECKPOINTED",
        "modal": "CHECKPOINTED",
        "q8": "CHECKPOINTED",
        "q10": "FAILED",
    }
    failed_substage_root = failure_output_root / "A2_saved_primary_q_response_substages"
    for stage in ("raw", "modal", "q8"):
        stage_ref = failed_a2["substage_checkpoint_refs"][stage]
        stage_path = Path(stage_ref["path"])
        stage_record = json.loads(stage_path.read_text(encoding="utf-8"))
        assert hashlib.sha256(stage_path.read_bytes()).hexdigest() == stage_ref["sha256"]
        assert stage_record["completed_substage_values"]["fixture_substage_value"] == stage
        assert stage_record["identity"]["contract_sha256"] == contract_sha
        assert stage_record["identity"]["recovery_manifest_sha256"] == recovery_context[
            "manifest_sha256"
        ]
        assert stage_record["overall_pass"] is False
        assert stage_record["official_result"] is False
        assert stage_record["selection_or_transition_authority"] is False
        assert stage_record["continuation"] is False
    assert not (failed_substage_root / "q10.json").exists()
    assert not (failure_output_root / "plans").exists()
    assert parent_load_calls == []
    archive_phase("A2_q10_failure", remove_live=True)

    monkeypatch.setattr(
        round1_candidates,
        "_resolve_v12_p2_source",
        lambda _recovery, *, attempt_root: p2_source
        if Path(attempt_root).resolve() == Path(p2_source["support_root"]).resolve()
        else (_ for _ in ()).throw(ValueError("unexpected P2 selector")),
    )
    monkeypatch.setenv("TASK43_V11_ATTEMPT_ROOT", p2_source["support_root"])

    def complete_saved_a2(_contract, *, checkpoint_callback):
        refs = {}
        for stage in round1_candidates._V11_A2_CHECKPOINT_STAGES:
            refs[stage] = checkpoint_callback(
                stage,
                {
                    "fixture_substage_value": stage,
                    "pass": True,
                    "official_result": False,
                },
            )
        return {
            "schema": "task43.v11.saved_a2_primary_q_response.v1",
            "pass": True,
            "classification": "synthetic arithmetic boundary for main sentinel",
            "substage_checkpoint_refs": refs,
            "substage_statuses": {
                stage: "CHECKPOINTED" for stage in round1_candidates._V11_A2_CHECKPOINT_STAGES
            },
        }

    monkeypatch.setattr(
        round1_candidates,
        "_v11_saved_a2_primary_q_response",
        complete_saved_a2,
    )
    p2_status = round1_candidates.main(
        p2_arguments(output_root)
    )
    assert p2_status == 0
    assert parent_load_calls == [True]
    persisted_a2 = json.loads(
        (output_root / "A2_saved_primary_q_response.json").read_text(encoding="utf-8")
    )
    assert persisted_a2["substage_statuses"] == {
        stage: "CHECKPOINTED" for stage in round1_candidates._V11_A2_CHECKPOINT_STAGES
    }
    for stage in round1_candidates._V11_A2_CHECKPOINT_STAGES:
        stage_ref = persisted_a2["substage_checkpoint_refs"][stage]
        stage_path = Path(stage_ref["path"])
        stage_record = json.loads(stage_path.read_text(encoding="utf-8"))
        assert hashlib.sha256(stage_path.read_bytes()).hexdigest() == stage_ref["sha256"]
        assert stage_record["completed_substage_values"]["fixture_substage_value"] == stage
        assert stage_record["identity"]["input_sha256"]
        assert stage_record["identity"]["source_sha256"]
        assert stage_record["overall_pass"] is False
        assert stage_record["official_result"] is False
        assert stage_record["selection_or_transition_authority"] is False
        assert stage_record["continuation"] is False
    p2_plan_path = output_root / "plans/v11_r9_h8.json"
    assert p2_plan_path.is_file()
    actual_plan = json.loads(p2_plan_path.read_text(encoding="utf-8"))
    actual_audit = json.loads(
        (output_root / "plans/v11_r9_h8.audit.json").read_text(encoding="utf-8")
    )
    assert actual_plan["task43_candidate"]["provenance"]["v11_seed"]["global_cell_id"] == 8
    assert actual_audit["space_authority_detail"]["all_actual_leaves_inherit_parent_degree"] is True
    assert actual_audit["space_authority_detail"]["forced_closure_root_ids"]
    assert set(actual_audit["space_authority_detail"]["actual_refined_root_ids"]) == {
        *actual_audit["space_authority_detail"]["requested_root_ids"],
        *actual_audit["space_authority_detail"]["forced_closure_root_ids"],
    }
    assert actual_audit["strict_fe_gate"]["pass"] is True
    assert actual_audit["strict_fe_gate"]["candidate_independent_fe_dofs"] == 110473
    fe_bounds = contract["phases"]["P4"]["required_fe_bounds"]
    assert int(fe_bounds["parent_fe_dofs"]) == 110472
    assert int(fe_bounds["target_exclusive_upper"]) == 237600
    actual_space_gate = round1_candidates._v11_actual_space_gate(
        actual_audit,
        parent_fe_dofs=parent["parent_independent_fe_dofs"],
        fe_bounds=fe_bounds,
    )
    assert actual_space_gate["pass"] is True

    extra_requested_root_audit = copy.deepcopy(actual_audit)
    extra_detail = extra_requested_root_audit["space_authority_detail"]
    extra_root = extra_detail["forced_closure_root_ids"][0]
    extra_detail["requested_root_ids"].append(extra_root)
    extra_detail["requested_root_boxes"][str(extra_root)] = extra_detail[
        "forced_closure_root_boxes"
    ][str(extra_root)]
    extra_detail["forced_closure_root_ids"].remove(extra_root)
    extra_detail["forced_closure_root_boxes"].pop(str(extra_root))
    extra_detail["forced_closure_root_degrees"].pop(str(extra_root))
    with pytest.raises(RuntimeError, match="actual root/degree/Floquet/carrier authority"):
        round1_candidates._v11_actual_space_gate(
            extra_requested_root_audit,
            parent_fe_dofs=parent["parent_independent_fe_dofs"],
            fe_bounds=fe_bounds,
        )

    for boundary_fe_dofs in (110472, 237600):
        boundary_audit = copy.deepcopy(actual_audit)
        boundary_audit["dofs"]["independent_active_fe_dofs"] = boundary_fe_dofs
        boundary_gate = round1_candidates._v11_actual_space_gate(
            boundary_audit,
            parent_fe_dofs=parent["parent_independent_fe_dofs"],
            fe_bounds=fe_bounds,
        )
        assert boundary_gate["pass"] is False
        if boundary_fe_dofs == 110472:
            assert boundary_gate["added_dofs"] == 0
            assert boundary_gate["above_exclusive_lower_bound"] is False
        else:
            assert boundary_gate["below_exclusive_upper_bound"] is False
    assert boundary_gate["candidate_independent_fe_dofs"] == 237600
    assert boundary_gate["below_exclusive_upper_bound"] is False
    bundle = json.loads((output_root / "plan_audit.json").read_text(encoding="utf-8"))
    assert bundle["A2_saved_primary_q_response"]["persisted_before_space_authority"] is True
    pre_gate_audit = json.loads(
        (output_root / "actual_authority_before_fe_gate.json").read_text(encoding="utf-8")
    )
    assert pre_gate_audit["space_authority_detail"]["all_actual_leaves_inherit_parent_degree"] is True
    assert "strict_fe_gate" not in pre_gate_audit

    audit_kwargs = {
        "candidate_id": "v11_r9_h8",
        "comm": round1_candidates.MPI.COMM_WORLD,
        "parent_independent_fe_dofs": parent["parent_independent_fe_dofs"],
        "parent_root_degree_by_box": parent["parent_degree_by_box"],
    }
    degree_mismatch = copy.deepcopy(actual_plan)
    original_degree = degree_mismatch["cell_interior_degrees"][0]["degree"]
    degree_mismatch["cell_interior_degrees"][0]["degree"] = (
        5 if original_degree == 6 else 6
    )
    degree_mismatch_path = output_root / "plans/degree_mismatch.json"
    degree_mismatch_path.write_text(
        json.dumps(degree_mismatch, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="does not inherit its parent root degree"):
        round1_candidates._audit_plan(
            audit_configs[-1], plan_path=degree_mismatch_path, **audit_kwargs
        )

    outside_root = copy.deepcopy(actual_plan)
    outside_root["marked_root_boxes"].append(
        {"lower": [2.0, 2.0, 2.0], "upper": [3.0, 3.0, 3.0]}
    )
    outside_root_path = output_root / "plans/outside_root.json"
    outside_root_path.write_text(
        json.dumps(outside_root, sort_keys=True) + "\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="candidate requests a box outside"):
        round1_candidates._audit_plan(
            audit_configs[-1], plan_path=outside_root_path, **audit_kwargs
        )

    legacy_plan = copy.deepcopy(actual_plan)
    legacy_plan["task43_candidate"]["provenance"].pop("v11_seed", None)
    legacy_plan_path = output_root / "plans/legacy_without_parent_map.json"
    legacy_plan_path.write_text(
        json.dumps(legacy_plan, sort_keys=True) + "\n", encoding="utf-8"
    )
    legacy_audit = round1_candidates._audit_plan(
        audit_configs[-1],
        plan_path=legacy_plan_path,
        candidate_id="legacy_without_parent_map",
        comm=round1_candidates.MPI.COMM_WORLD,
        parent_independent_fe_dofs=parent["parent_independent_fe_dofs"],
        parent_root_degree_by_box=None,
    )
    assert legacy_audit["space_authority_detail"]["all_actual_leaves_inherit_parent_degree"] is None
    archive_phase("P2", remove_live=False)

    assert len(runtime_environments) == 4
    for environment in runtime_environments:
        assert environment["petsc_scalar_type"]
        assert environment["petsc_int_type"]
        assert all(value == "1" for value in environment["v11_math_threads"].values())
        assert environment["v11_worker_local_environment"] == {
            "HWLOC_COMPONENTS": "-x86",
            "OMPI_MCA_pml": "ob1",
        }
        assert environment["v11_mumps_available"] is True
        assert all(
            tid["cpu_list"] == [1]
            for tid in environment["v11_watchdog_worker_identity"]["worker_tid_affinities"]
        )
    runtime_evidence = {
        "schema": "task43.v11.p1.main_sentinel_runtime_identity.v1",
        "environments": runtime_environments,
        "worker_identity_checkpoints": calls,
        "run_impl_controls": run_impl_controls,
        "forbidden_extra_correction_helper_calls": extra_helper_calls,
        "phase_path": str(live_phase_path),
        "phase_archives": {
            label: str(tmp_path / "watchdog_phase_archive" / f"{label}.json")
            for label in ("A1_q3", "R9_H8", "A2_q10_failure", "P2")
        },
        "claim_scope": "actual pytest worker and WorkflowLedger observations through each real main mesh-before-solve sentinel only; no solver or PDE stage was entered; extra-correction absence after solve is not established by this sentinel and must be established from saved raw-vector/formal run evidence",
    }
    runtime_evidence_path = tmp_path / "main_sentinel_runtime_identity.json"
    runtime_evidence_path.write_text(
        json.dumps(runtime_evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def traced_child(label: str, exit_code: int) -> None:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(0.15); raise SystemExit(" + str(exit_code) + ")",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_path = Path(f"/proc/{child.pid}")
        deadline = time.monotonic() + 2.0
        start_ticks = None
        tracer_pid = 0
        while time.monotonic() < deadline and proc_path.is_dir():
            try:
                stat_fields = (proc_path / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
                status_lines = (proc_path / "status").read_text(encoding="ascii").splitlines()
                start_ticks = int(stat_fields[19])
                tracer_pid = int(
                    next(line for line in status_lines if line.startswith("TracerPid:")).split(":", 1)[1]
                )
            except (OSError, StopIteration, ValueError, IndexError):
                time.sleep(0.01)
                continue
            if tracer_pid > 0:
                break
            time.sleep(0.01)
        assert start_ticks is not None
        assert tracer_pid == calls[-1]["tracer_pid"]
        stdout, stderr = child.communicate(timeout=5.0)
        assert child.returncode == exit_code, (stdout, stderr)
        after_start_ticks = None
        if proc_path.is_dir():
            try:
                fields = (proc_path / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
                after_start_ticks = int(fields[19])
            except (OSError, ValueError, IndexError):
                after_start_ticks = None
        assert after_start_ticks != start_ticks
        evidence = {
            "schema": "task43.v11.p1.traced_child_cleanup.v1",
            "label": label,
            "worker_pid": os.getpid(),
            "watchdog_parent_pid": calls[-1]["watchdog_pid"],
            "worker_tracer_pid": calls[-1]["tracer_pid"],
            "child_pid": child.pid,
            "child_parent_pid": os.getpid(),
            "child_start_ticks": start_ticks,
            "child_tracer_pid": tracer_pid,
            "expected_exit_code": exit_code,
            "observed_exit_code": child.returncode,
            "child_reaped": after_start_ticks != start_ticks,
            "direct_watchdog_worker": False,
        }
        evidence_path = tmp_path / "traced_child_cleanup" / f"{label}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    traced_child("normal_exit", 0)
    traced_child("controlled_fault_exit", 7)
