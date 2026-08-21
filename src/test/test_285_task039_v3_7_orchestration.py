"""Pure contracts for the pre-heavy Task39 V3-7 orchestration."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task039_v3_7_orchestration as orchestration
import benchmarks.task039_v3_7_watchdog as watchdog
from src.runners import task038_launcher
from benchmarks import run_task037b_hybrid_iterative as frozen_runner
from benchmarks.task037c_robustness import Task37cProfile
from benchmarks.task039_v3_7_orchestration import (
    V3_7_ABSOLUTE_HARD_BYTES,
    V3_7_PROFILE_ID,
    V5_H4_SETUP_ONLY_MARKERS,
    _json_safe,
    _record_v3_7_marker,
    _v5_blr_prefreeze_external_rhs,
    _v5_blr_rhs_vector,
    _v6_global_minimum_layer_labels,
    _v6_layer_graph_from_csr,
    _v6_reduce_layer_graph,
    _v7_streamed_packet_pair,
    _v3_7_cleanup_callback,
    _v3_7_object_ledger,
    _write_v3_7_candidate_authority,
    _write_v3_7_object_ledger,
    _write_v3_7_side_survey_checkpoint,
    load_v3_7_official_payload,
    load_v3_7_direct_inventory,
    run_v3_7_stage_sequence,
    run_v5_h4_exact_side_setup_only,
    v3_7_execution_dry_run,
    v3_7_profile_from_resolved,
    v3_7_watchdog_policy,
    validate_v3_7_resolved_identity,
)
from benchmarks.task039_hybrid_direct_identity import (
    _parse_orders,
    _same_external_key_set,
)
from src.io.input_validation import (
    load_and_resolve,
    task039_dynamic_external_mode_inventory,
)
from src.modes.mode_classification import _near_degenerate_partition_audit


INPUT = Path("input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat")


def _tiny_side_system(rhs_values=(0.0, 0.0)):
    matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setValue(0, 0, 1.0)
    matrix.setValue(1, 1, 1.0)
    matrix.assemble()
    rhs = matrix.createVecRight()
    for index, value in enumerate(rhs_values):
        rhs.setValue(index, PETSc.ScalarType(value))
    rhs.assemble()
    return SimpleNamespace(A=matrix, b=rhs), matrix, rhs


def test_v7_streamed_packet_pair_checks_frozen_modal_schedule_without_solver():
    schedule = orchestration.v6_port_modal_training_schedule(
        mode_count=480, external_count=296, source_count=512
    )

    class FakeContext:
        def __init__(self):
            self.calls = []

        def mode_pair(self, branch, column):
            self.calls.append((branch, column))
            return {"branch": branch, "column": column}

    context = FakeContext()
    modal_items = []
    for item in schedule:
        pair, branch = _v7_streamed_packet_pair(item, context)
        right_family = item["right_family"]
        left_family = item["left_family"]
        if right_family.endswith("modal_traction") and left_family.endswith(
            "modal_dual"
        ):
            modal_items.append(item)
            assert pair["branch"] == branch
            assert pair["column"] == item["right_selector"]["column"]
            assert item["right_selector"]["column"] == item["left_selector"]["column"]
    assert len(schedule) == 512
    assert modal_items
    assert len(context.calls) >= len(modal_items)

    branch_mismatch = json.loads(json.dumps(modal_items[0]))
    branch_mismatch["left_family"] = (
        "negative_modal_dual"
        if branch_mismatch["left_family"] == "positive_modal_dual"
        else "positive_modal_dual"
    )
    with pytest.raises(ValueError, match="inconsistent branch/column"):
        _v7_streamed_packet_pair(branch_mismatch, context)

    column_mismatch = json.loads(json.dumps(modal_items[0]))
    column_mismatch["left_selector"]["column"] += 1
    with pytest.raises(ValueError, match="inconsistent branch/column"):
        _v7_streamed_packet_pair(column_mismatch, context)


def _v6_gate_reports(
    *, preferred_residual=5.0e-4, random_residual=5.0e-3, physical_degenerate=True
):
    preferred_labels = orchestration.V6_PORT_MODAL_PREFERRED_LABELS
    reports = []
    for label in orchestration.V6_PORT_MODAL_HOLDOUT_LABELS:
        if label in preferred_labels:
            residual = preferred_residual
        elif label.startswith("fixed_random"):
            residual = random_residual
        else:
            residual = 5.0e-3
        reports.append(
            {
                "label": label,
                "finite": True,
                "degenerate_uninformative": (
                    physical_degenerate and label == "physical_side_rhs"
                ),
                "repeat_relative_error": 1.0e-12,
                "linearity_relative_error": 1.0e-12,
                "true_residual_relative": residual,
            }
        )
    return reports


def test_v6_layer_graph_counts_use_explicit_layer_labels() -> None:
    audit = _v6_layer_graph_from_csr(
        np.asarray([0, 2, 4, 6]),
        np.asarray([0, 1, 1, 2, 2, 0]),
        np.asarray([0, 1, 2]),
        np.asarray([0, 1, 2, 2]),
        layer_count=3,
    )
    assert audit["rows_by_layer"] == [1, 1, 1]
    assert audit["nnz_by_layer"] == [2, 2, 2]
    assert audit["same_layer_nnz"] == 3
    assert audit["adjacent_layer_nnz"] == 2
    assert audit["long_range_nnz"] == 1
    assert audit["layer_pair_nnz"] == [[1, 1, 0], [0, 1, 1], [1, 0, 1]]
    assert audit["block_half_bandwidth"] == 2
    assert audit["long_range_fraction"] == pytest.approx(1 / 6)
    assert "owned_cell_recovery_maps" in inspect.getdoc(
        orchestration._v6_layer_graph_audit
    )


def test_v6_layer_graph_collective_minimum_and_pair_counts() -> None:
    comm = MPI.COMM_WORLD
    if comm.size not in (2, 4):
        pytest.skip("run this tiny collective fixture with MPI2 or MPI4")
    global_rows = comm.size
    sentinel = np.iinfo(np.int32).max
    partial = np.full(global_rows, sentinel, dtype=np.int32)
    partial[comm.rank] = (comm.rank + 2) % 4
    partial[(comm.rank + 1) % global_rows] = (comm.rank + 3) % 4
    labels = _v6_global_minimum_layer_labels(partial, global_rows, comm)
    expected = np.full(global_rows, sentinel, dtype=np.int32)
    for catalog in comm.allgather(partial):
        expected = np.minimum(expected, catalog)
    assert np.array_equal(labels, expected)
    with pytest.raises(ValueError, match="does not cover"):
        _v6_global_minimum_layer_labels(
            np.full(global_rows, sentinel, dtype=np.int32), global_rows, comm
        )
    local = _v6_layer_graph_from_csr(
        np.asarray([0, 2]),
        np.asarray([comm.rank, (comm.rank + 1) % global_rows]),
        np.asarray([labels[comm.rank]]),
        labels,
        layer_count=4,
    )
    reduced = _v6_reduce_layer_graph(local, comm, global_rows=global_rows)
    assert reduced["nnz_global"] == 2 * comm.size
    assert reduced["nnz_total"] == 2 * comm.size
    assert sum(sum(row) for row in reduced["layer_pair_nnz"]) == 2 * comm.size
    assert (
        reduced["same_layer_nnz"]
        + reduced["adjacent_layer_nnz"]
        + reduced["long_range_nnz"]
        == reduced["nnz_total"]
    )
    assert reduced["block_half_bandwidth"] == max(
        comm.allgather(local["block_half_bandwidth"])
    )


def test_v6_layer_graph_rejects_unmapped_dense_label_serial() -> None:
    sentinel = np.iinfo(np.int32).max
    with pytest.raises(ValueError, match="does not cover"):
        _v6_global_minimum_layer_labels(
            np.asarray([0, sentinel], dtype=np.int32), 2, MPI.COMM_SELF
        )


def test_v3_7_profile_is_derived_from_official_one_degree_s_input() -> None:
    payload = load_v3_7_official_payload(INPUT)
    profile = v3_7_profile_from_resolved(payload)
    assert profile.profile_id == V3_7_PROFILE_ID
    assert profile.incident_grazing_deg == 1.0
    assert profile.incident_phi_deg == 0.0
    assert profile.polarization_kind == "s"
    assert profile.h_nm == 5.0
    assert profile.modal_h_nm == 5.0
    assert profile.requested_modes == 480
    assert profile.candidate_modes == 960
    assert profile.max_it == 4000

    wrong_angle = dict(payload)
    wrong_angle["incidence"] = dict(payload["incidence"], grazing_angle_deg=10.0)
    with pytest.raises(ValueError, match="official physical/discrete identity"):
        validate_v3_7_resolved_identity(wrong_angle)

    wrong_polarization = dict(payload)
    wrong_polarization["incidence"] = dict(payload["incidence"], polarization="S")
    with pytest.raises(ValueError):
        validate_v3_7_resolved_identity(wrong_polarization)


def test_qep_tolerance_is_explicit_and_profile_selected() -> None:
    assert frozen_runner.FROZEN_M10.qep_solver_tolerance == 1.0e-10
    assert Task37cProfile().qep_solver_tolerance == 1.0e-10
    profile = v3_7_profile_from_resolved(load_v3_7_official_payload(INPUT))
    assert profile.qep_solver_tolerance == 1.0e-13
    assert profile.retained_subspace_dual_rotation is True
    assert (
        getattr(frozen_runner.FROZEN_M10, "retained_subspace_dual_rotation", False)
        is False
    )
    assert getattr(Task37cProfile(), "retained_subspace_dual_rotation", False) is False
    source = inspect.getsource(frozen_runner.build_frozen_m10_setup)
    assert source.count("\n        tolerance=profile.qep_solver_tolerance") == 2
    assert (
        source.count("\n        qep_solver_tolerance=profile.qep_solver_tolerance") == 2
    )
    assert (
        source.count(
            "\n        retained_subspace_dual_rotation=bool(\n"
            '            getattr(profile, "retained_subspace_dual_rotation", False)\n'
            "        ),"
        )
        == 2
    )


def test_task039_qep_basis_audit_is_compact_and_fail_closed() -> None:
    basis = SimpleNamespace(
        near_degenerate_partition_audit={
            "status": "near_degenerate_block_partition_pass",
            "pass": True,
            "biorthogonality_identity_row_norm": 1.0e-9,
            "biorthogonality_identity_max_entry": 1.0e-10,
            "max_cross_block_overlap": 1.0e-10,
            "near_degenerate_tolerance": 1.0e-6,
            "block_rotation_tolerance": 1.0e-6,
            "group_members": list(range(480)),
        },
        retained_subspace_dual_rotation_audit=None,
        modes=[SimpleNamespace(left_polynomial_relative_residual=2.0e-15)],
    )
    report = frozen_runner._task039_qep_basis_audit(basis, side="forward")
    assert report["overall_pass"] is True
    assert "group_members" not in report["partition_audit"]

    failing_rotation = SimpleNamespace(
        near_degenerate_partition_audit={"pass": True},
        retained_subspace_dual_rotation_audit={"overall_pass": False},
        modes=[SimpleNamespace(left_polynomial_relative_residual=2.0e-15)],
    )
    with pytest.raises(RuntimeError, match="backward QEP basis audit failed"):
        frozen_runner._task039_qep_basis_audit(failing_rotation, side="backward")

    failing_residual = SimpleNamespace(
        near_degenerate_partition_audit={"pass": True},
        retained_subspace_dual_rotation_audit=None,
        modes=[SimpleNamespace(left_polynomial_relative_residual=1.0e-7)],
    )
    with pytest.raises(RuntimeError, match="forward QEP basis audit failed"):
        frozen_runner._task039_qep_basis_audit(failing_residual, side="forward")


def test_v3_7_partition_fixture_stays_outside_near_degenerate_envelope() -> None:
    beta_distance = 4.116479e-5
    betas = (1.0 + 0.0j, 1.0 + beta_distance + 0.0j)
    overlap = np.eye(2, dtype=np.complex128)
    overlap[0, 1] = 8.443521e-6
    audit = _near_degenerate_partition_audit(
        betas,
        ((0,), (1,)),
        overlap,
        near_degenerate_tolerance=1.0e-6,
        block_rotation_tolerance=1.0e-6,
    )
    assert audit["pass"] is False
    assert audit["status"] == "cross_block_biorthogonality_failure"
    assert audit["worst_cross_block_is_near_degenerate_candidate"] is False
    assert audit["max_cross_block_overlap"] == pytest.approx(8.443521e-6)
    assert audit["worst_cross_block_relative_beta_distance"] > 1.0e-5


def test_v3_7_watchdog_keeps_195_as_checkpoint_and_224gb_as_byte_hard_stop() -> None:
    payload = load_v3_7_official_payload(INPUT)
    policy = v3_7_watchdog_policy(payload)
    assert policy["critical_action"] == "record_checkpoint_only"
    assert policy["absolute_terminate_memory_bytes"] == V3_7_ABSOLUTE_HARD_BYTES
    assert policy["poll_interval_seconds"] == 0.25
    with pytest.raises(ValueError):
        v3_7_watchdog_policy(payload, poll_interval_seconds=0.251)


def test_v3_7_direct_modal_loader_checks_hash_bound_payload(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    values = np.arange(960, dtype=np.float64) + 1j * np.arange(960, dtype=np.float64)
    artifact = tmp_path / "task039_direct_payload.npz"
    np.savez(artifact, modal_amplitudes=values)
    descriptor = {
        "shape": [960],
        "dtype": "complex128",
        "sha256": hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest(),
    }
    inventory = {
        "verified_shard_count": 32,
        "payload": {
            "artifact": {"path": str(artifact)},
            "arrays": {"modal_amplitudes": descriptor},
        },
    }
    monkeypatch.setattr(
        orchestration,
        "load_task039_direct_solution_inventory",
        lambda *args, **kwargs: inventory,
    )
    manifest = {
        "model_id": "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
        "method": "hybrid_direct",
        "mpi_size": 8,
        "external_mode_inventory": task039_dynamic_external_mode_inventory(payload),
    }
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    producer, loaded = load_v3_7_direct_inventory(
        payload,
        run_dir,
        producer_source_sha="producer-sha",
    )
    assert producer["verified_shard_count"] == 32
    assert loaded.shape == (960,)


def test_v3_7_stage_sequence_requires_recovery_after_oracle_cleanup() -> None:
    events: list[str] = []

    class Solution:
        def duplicate(self) -> "Solution":
            events.append("duplicate")
            return Solution()

        def copy(self, other: "Solution") -> None:
            events.append("copy")

    def oracle(consume):
        events.append("oracle_start")
        consume(Solution(), {"pass": True})
        events.append("oracle_return")
        return {"pass": True}

    report = run_v3_7_stage_sequence(
        identity_stage=lambda: {"pass": True},
        correction_stage=lambda: {"pass": True},
        oracle_stage=oracle,
        snapshotter=lambda solution: solution.duplicate(),
        recovery_runner=lambda snapshot: events.append("recovery") or {"pass": True},
    )
    assert report["status"] == "completed"
    assert events.index("oracle_return") < events.index("recovery")
    assert report["solution_handoff"] == "recovery_after_oracle_cleanup"


def test_v3_7_stage_sequence_recovery_failure_is_not_completed() -> None:
    report = run_v3_7_stage_sequence(
        identity_stage=lambda: {"pass": True},
        correction_stage=lambda: {"pass": True},
        oracle_stage=lambda consume: (
            consume(object(), {"pass": True}) or {"pass": True}
        ),
        snapshotter=lambda solution: object(),
        recovery_runner=lambda snapshot: {"pass": False, "status": "physics_fail"},
    )
    assert report["status"] == "oracle_linear_pass_physics_fail"


def test_v5_setup_only_emits_unique_pre_cleanup_markers_and_no_solve(
    monkeypatch,
):
    events: list[str] = []
    marker_details: dict[str, dict] = {}
    action_kwargs_seen: list[dict] = []
    preconditioner_kwargs_seen: list[dict] = []
    timeline: list[str] = []

    class Resource:
        def __init__(self, name):
            self.name = name
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class Components:
        def __init__(self):
            self.F, self.C, self.D, self.H = (
                Resource(name) for name in ("F", "C", "D", "H")
            )

    class Action:
        def __init__(self, streaming):
            self.destroyed = False
            self.streaming = streaming
            self.matrices_released = False

            def mark_borrowed_matrices_released():
                events.append("matrices_released")
                if not self.streaming:
                    self.matrices_released = True

            self.woodbury = SimpleNamespace(
                mark_borrowed_matrices_released=mark_borrowed_matrices_released
            )

        @property
        def diagnostics(self):
            return {
                "direct_factor_count": 0 if self.destroyed else 1,
                "global_hybrid_direct_factor_count": 0,
                "destroyed": self.destroyed,
                "factor_only_storage": True,
                "woodbury": {
                    "F_C_H_matrices_released": self.matrices_released,
                    "F_H_released": True,
                    "F_H_matrices_released": True,
                    "borrowed_component_handles_released": True,
                    "C_action_owned": self.streaming,
                    "C_action_resident": self.streaming,
                    "C_action_released": False,
                    "W_resident": not self.streaming,
                    "streaming_w_storage": self.streaming,
                    "K_released": True,
                    "D_retained": True,
                },
            }

        def destroy(self):
            self.destroyed = True

    class Context:
        inventory = {"modal_schur": {"status": "measured"}}

        def destroy(self):
            events.append("modal_context_destroy")

    class FakePC:
        def setType(self, _value):
            pass

        def setPythonContext(self, _value):
            pass

    class FakeKSP:
        Type = SimpleNamespace(FGMRES="fgmres", GMRES="gmres")

        def __init__(self):
            self.kind = "unset"
            self.restart = None

        def create(self, _comm):
            return self

        def setOperators(self, _value):
            pass

        def setType(self, value):
            self.kind = value

        def setGMRESRestart(self, value):
            self.restart = value

        def setPCSide(self, _value):
            pass

        def getPC(self):
            return FakePC()

        def setUp(self):
            events.append("outer_setup")

        def getType(self):
            return self.kind

        def destroy(self):
            events.append("outer_destroy")

    fake_petsc = SimpleNamespace(
        KSP=FakeKSP,
        PC=SimpleNamespace(
            Side=SimpleNamespace(RIGHT="right"),
            Type=SimpleNamespace(PYTHON="python"),
        ),
    )
    monkeypatch.setattr(orchestration, "PETSc", fake_petsc)
    monkeypatch.setattr(
        orchestration,
        "_build_research_explicit_side_components",
        lambda _system: Components(),
    )
    monkeypatch.setattr(
        orchestration,
        "_v5_side_matrix_inventory",
        lambda _components: {
            name: {"status": "measured"} for name in ("F", "C", "D", "H")
        },
    )
    monkeypatch.setattr(
        orchestration,
        "_petsc_matrix_stats",
        lambda _matrix, assemble=False: {"status": "measured", "assemble": assemble},
    )

    def make_action(_f, _components, **kwargs):
        action_kwargs_seen.append(kwargs)
        streaming = kwargs["streaming_w_batch_size"] is not None
        if streaming:
            _components.C = None
        kwargs["lifecycle_callback"]("factor_setup_begin", {})
        kwargs["lifecycle_callback"]("factor_ready", {})
        return Action(streaming)

    monkeypatch.setattr(
        orchestration, "create_research_exact_side_lu_action", make_action
    )
    monkeypatch.setattr(
        orchestration,
        "create_research_exact_side_lu_block_ldu_preconditioner",
        lambda *_args, **kwargs: preconditioner_kwargs_seen.append(kwargs) or Context(),
    )
    monkeypatch.setattr(
        orchestration,
        "create_hybrid_assembled_block_action",
        lambda *_args: (Resource("operator"), Resource("operator_context")),
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: (
            timeline.append("collective_heap_cleanup")
            or {"collective_call_completed": True}
        ),
    )
    coupling_blocks = SimpleNamespace(
        projection=object(), positive_traction=object(), negative_traction=object()
    )
    setup = SimpleNamespace(
        bottom=object(),
        top=object(),
        coupling=SimpleNamespace(bottom=coupling_blocks, top=coupling_blocks),
    )
    markers: list[str] = []

    def record_marker(marker, detail):
        timeline.append(marker)
        markers.append(marker)
        marker_details.setdefault(marker, dict(detail))

    result = run_v5_h4_exact_side_setup_only(
        setup,
        SimpleNamespace(),
        comm=MPI.COMM_SELF,
        marker_callback=record_marker,
        streaming_w_batch_size=16,
    )
    assert result["status"] == "setup_only_completed"
    assert result["markers"] == list(V5_H4_SETUP_ONLY_MARKERS)
    assert markers == list(V5_H4_SETUP_ONLY_MARKERS[:-1])
    assert len(markers) == len(set(markers))
    assert timeline[0] == "collective_heap_cleanup"
    assert timeline.index("collective_heap_cleanup", 1) < timeline.index("top_F_ready")
    assert timeline.index("bottom_construction_cleanup") < timeline.index("top_F_ready")
    assert [item["factor_only_storage"] for item in action_kwargs_seen] == [
        True,
        True,
    ]
    assert [item["streaming_w_batch_size"] for item in action_kwargs_seen] == [
        16,
        16,
    ]
    contract = orchestration._load_v5_h4_sampled_column_contract()
    assert preconditioner_kwargs_seen[0]["sampled_columns"] == contract["columns"]
    assert (
        preconditioner_kwargs_seen[0]["sampled_column_contract_sha256"]
        == contract["sha256"]
    )
    assert result["sampled_column_contract"]["sha256"] == contract["sha256"]
    assert result["outer_ksp"]["type"] == "gmres"
    assert result["outer_ksp"]["restart"] == 10
    assert marker_details["bottom_F_ready"]["retained_through_woodbury_build"] is True
    assert (
        marker_details["bottom_F_ready"]["original_F_retained_for_modal_schur"] is False
    )
    assert marker_details["bottom_construction_cleanup"]["component_release"] == {
        "H": True,
        "C": False,
        "F": True,
        "D": False,
        "D_retained": True,
        "C_original_carrier_handle_transferred": True,
    }
    assert marker_details["bottom_construction_cleanup"]["retained_objects"] == {
        "side_action": True,
        "factor_matrix": True,
        "D": True,
        "W": False,
        "C_action": True,
    }
    assert marker_details["bottom_construction_cleanup"]["released_objects"] == {
        "F": True,
        "H": True,
        "C_original_carrier_handle_transferred": True,
        "C_action_resident": True,
        "C_action_owned": True,
        "C_matrix_released": False,
    }
    assert marker_details["bottom_construction_cleanup"]["action_diagnostics"] == {
        "direct_factor_count": 1,
        "global_hybrid_direct_factor_count": 0,
        "destroyed": False,
        "factor_only_storage": True,
        "woodbury": {
            "F_C_H_matrices_released": False,
            "F_H_released": True,
            "F_H_matrices_released": True,
            "borrowed_component_handles_released": True,
            "C_action_owned": True,
            "C_action_resident": True,
            "C_action_released": False,
            "W_resident": False,
            "streaming_w_storage": True,
            "K_released": True,
            "D_retained": True,
        },
    }
    assert result["solve"] == result["recovery"] == result["field_export"] == "not_run"
    assert result["setup_only_internal_cleanup"]["factor_count_after_cleanup"] == {
        "bottom": 0,
        "top": 0,
    }
    assert result["setup_only_internal_cleanup"]["exact_side_objects_destroyed"] is True
    assert events.count("matrices_released") == 2
    telemetry = result["telemetry"]
    assert all(
        telemetry[name]["path"] and telemetry[name]["status"]
        for name in (
            "process_tree_samples",
            "memory_stages",
            "memory_stage_markers",
        )
    )
    assert telemetry["memory_object_ledger"] == {
        "path": "numerical_output/memory_object_ledger.json",
        "schema": "task039.v3-7-memory-object-ledger.v1",
        "status": "finalized_in_worker_finalizer",
    }
    assert marker_details["modal_schur_build_begin"]["coupling_matrices"] == {
        side: {
            name: {"status": "measured", "assemble": False}
            for name in ("projection", "positive_traction", "negative_traction")
        }
        for side in ("bottom", "top")
    }
    assert "outer_setup" in events


def test_v5_diagnostic_final_cleanup_marker_follows_setup_release(
    tmp_path, monkeypatch
):
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    run_directory = tmp_path / "v5"
    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    events: list[str] = []

    monkeypatch.setattr(
        orchestration, "simulation_config_3d_from_normalized", lambda _payload: {}
    )
    monkeypatch.setattr(
        orchestration,
        "HybridAugmentedLayout",
        SimpleNamespace(build=lambda *_args: SimpleNamespace()),
    )
    monkeypatch.setattr(
        orchestration,
        "run_v5_h4_exact_side_setup_only",
        lambda *_args, **_kwargs: {
            "status": "setup_only_completed",
            "setup_only_internal_cleanup": {
                "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                "side_component_cleanup": {
                    "bottom": {"F": True, "C": True, "H": True, "D": True},
                    "top": {"F": True, "C": True, "H": True, "D": True},
                },
                "exact_side_objects_destroyed": True,
            },
            "side_actions": {
                "bottom": {"factor_only_storage": True},
                "top": {"factor_only_storage": True},
            },
            "telemetry": {"memory_object_ledger": {}},
        },
    )

    def release(_setup, _recovery, _comm):
        events.append("setup_release")
        return {"pass": True, "cleanup": {"collective_call_completed": True}}

    monkeypatch.setattr(orchestration, "release_frozen_m10_objects", release)
    monkeypatch.setattr(
        orchestration,
        "_record_v3_7_marker",
        lambda _ledger, marker, _detail: events.append(marker),
    )
    monkeypatch.setattr(
        orchestration.time, "sleep", lambda _seconds: events.append("wait")
    )
    identity = {
        "source_sha": "a" * 40,
        "physical_sha256": "b" * 64,
        "model_id": "task039_5nm_v4_1deg_s5_hybrid_iterative_m480",
    }
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: setup,
        v5_h4_setup_only=True,
        selected_mode_packet_manifest=tmp_path / "manifest.json",
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256="d" * 64,
        recovery_runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("V5 setup-only must not call recovery_runner")
        ),
    )
    marker_path = run_directory / "numerical_output/memory_stage_markers.raw.jsonl"
    rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
    assert result["status"] == "setup_only_completed"
    assert [row["stage"] for row in rows].count("all_setup_objects_cleanup") == 1
    assert rows[-1]["stage"] == "all_setup_objects_cleanup"
    assert rows[-1]["detail"]["setup_destroyed"] is True
    assert rows[-1]["detail"]["factor_count_after_cleanup"] == {
        "bottom": 0,
        "top": 0,
    }
    assert events.index("setup_release") < events.index("all_setup_objects_cleanup")
    assert events.index("all_setup_objects_cleanup") < events.index("wait")
    ledger = json.loads(
        (run_directory / "numerical_output/memory_object_ledger.json").read_text()
    )
    for name in ("exact_side_action", "exact_side_factors"):
        assert ledger["objects"][name]["destroyed"] is True
        assert ledger["objects"][name]["details"]["factor_only_storage"] is True


def test_v5_setup_release_error_does_not_emit_success_cleanup_marker(
    tmp_path, monkeypatch
):
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    run_directory = tmp_path / "v5-release-error"
    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    monkeypatch.setattr(
        orchestration, "simulation_config_3d_from_normalized", lambda _payload: {}
    )
    monkeypatch.setattr(
        orchestration,
        "HybridAugmentedLayout",
        SimpleNamespace(build=lambda *_args: SimpleNamespace()),
    )
    monkeypatch.setattr(
        orchestration,
        "run_v5_h4_exact_side_setup_only",
        lambda *_args, **_kwargs: {
            "status": "setup_only_completed",
            "telemetry": {"memory_object_ledger": {}},
        },
    )
    monkeypatch.setattr(
        orchestration,
        "release_frozen_m10_objects",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("release sentinel")),
    )
    identity = {
        "source_sha": "a" * 40,
        "physical_sha256": "b" * 64,
        "model_id": "task039_5nm_v4_1deg_s5_hybrid_iterative_m480",
    }
    with pytest.raises(RuntimeError, match="release sentinel"):
        orchestration.run_task039_v3_7_diagnostic(
            payload,
            run_directory,
            source_sha="c" * 40,
            comm=MPI.COMM_SELF,
            setup_builder=lambda **_kwargs: setup,
            v5_h4_setup_only=True,
            selected_mode_packet_manifest=tmp_path / "manifest.json",
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256="d" * 64,
        )
    marker_path = run_directory / "numerical_output/memory_stage_markers.raw.jsonl"
    rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
    assert all(row["stage"] != "all_setup_objects_cleanup" for row in rows)


@pytest.mark.parametrize(
    ("profile_kwargs", "spool_keyword", "profile_key", "expected_schema"),
    (
        (
            {"v6_h4_post_compaction_setup_only": True},
            "v6_h4_exact_spool_root",
            "v6_profile",
            "task039.v6-h4-post-compaction-setup-only.v1",
        ),
        (
            {"v7_h4_exact_side_limit_setup_only": True},
            "v7_h4_exact_side_exact_spool_root",
            "v7_profile",
            orchestration.V7_H4_EXACT_SIDE_LIMIT_SCHEMA,
        ),
    ),
)
def test_v6_and_v7_qep_zero_preserve_uncreated_packet_ledger_objects(
    tmp_path, monkeypatch, profile_kwargs, spool_keyword, profile_key, expected_schema
):
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
        qep_release={
            "qep_calls": 0,
            "packet_mmap_released": True,
            "packet_references_released": True,
        },
    )
    monkeypatch.setattr(
        orchestration, "simulation_config_3d_from_normalized", lambda _payload: {}
    )
    monkeypatch.setattr(
        orchestration,
        "HybridAugmentedLayout",
        SimpleNamespace(build=lambda *_args: SimpleNamespace()),
    )

    def exact_setup_result(*_args, **kwargs):
        result = {
            "status": "setup_only_completed",
            "setup_only_internal_cleanup": {
                "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                "side_component_cleanup": {},
                "exact_side_objects_destroyed": True,
            },
            "side_actions": {
                "bottom": {"factor_only_storage": True},
                "top": {"factor_only_storage": True},
            },
            "telemetry": {"memory_object_ledger": {}},
        }
        if kwargs.get("v6_profile"):
            result.update(
                {
                    "schema": "task039.v6-h4-post-compaction-setup-only.v1",
                    "v6_profile": {},
                }
            )
        return result

    monkeypatch.setattr(
        orchestration,
        "run_v5_h4_exact_side_setup_only",
        exact_setup_result,
    )
    monkeypatch.setattr(
        orchestration,
        "release_frozen_m10_objects",
        lambda *_args: {"pass": True, "cleanup": {"collective_call_completed": True}},
    )
    identity = {
        "source_sha": "a" * 40,
        "physical_sha256": "b" * 64,
        "model_id": "task039_5nm_v4_1deg_s5_hybrid_iterative_m480",
    }
    route_kwargs = dict(profile_kwargs)
    route_kwargs[spool_keyword] = tmp_path / "exact-spool"
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        tmp_path / "v6-qep-zero",
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: setup,
        selected_mode_packet_manifest=tmp_path / "manifest.json",
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256="d" * 64,
        **route_kwargs,
    )
    ledger = json.loads(
        (
            tmp_path / "v6-qep-zero/numerical_output/memory_object_ledger.json"
        ).read_text()
    )
    assert result[profile_key]["packet_qep_refs_released"] is True
    assert result["schema"] == expected_schema
    for name in ("qep_matrices", "selected_basis"):
        assert ledger["objects"][name]["created"] is False
        assert ledger["objects"][name]["released"] is True
        assert ledger["objects"][name]["destroyed"] is True
        assert ledger["objects"][name]["details"]["qep_release"]["qep_calls"] == 0


def test_v7_full_formal_uses_matched_h4_direct_authority_only(tmp_path, monkeypatch):
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    captured = {}
    monkeypatch.setattr(
        orchestration, "simulation_config_3d_from_normalized", lambda _payload: {}
    )
    monkeypatch.setattr(
        orchestration,
        "HybridAugmentedLayout",
        SimpleNamespace(build=lambda *_args: SimpleNamespace()),
    )
    monkeypatch.setattr(
        orchestration,
        "release_frozen_m10_objects",
        lambda *_args: {
            "pass": True,
            "cleanup": {"collective_call_completed": True},
        },
    )

    def fake_full_formal(**kwargs):
        captured["producer"] = dict(kwargs["producer"])
        return {
            "status": "full_formal_completed",
            "solve": {"ksp_type": "gmres", "restart": 10},
            "recovery": {"pass": True},
        }

    monkeypatch.setattr(
        orchestration, "_run_v7_h4_exact_side_full_formal", fake_full_formal
    )

    def fake_setup(_setup, _layout, **kwargs):
        kwargs["full_formal_runner"](
            setup=_setup,
            layout=_layout,
            operator=None,
            context=None,
            comm=MPI.COMM_SELF,
            marker_callback=kwargs["marker_callback"],
            release_before_recovery=lambda: {
                "pass": True,
                "factor_cleanup_pass": True,
                "actions_destroyed": True,
                "component_cleanup_pass": True,
                "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                "collective_heap_cleanup": {"collective_call_completed": True},
            },
        )
        return {
            "status": "full_formal_completed",
            "setup_only_internal_cleanup": {
                "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                "side_component_cleanup": {},
                "exact_side_objects_destroyed": True,
            },
            "side_actions": {
                "bottom": {"factor_only_storage": True},
                "top": {"factor_only_storage": True},
            },
            "telemetry": {"memory_object_ledger": {}},
            "v6_profile": {},
            "outer_ksp": {"solve_called": False, "type": "gmres", "restart": 10},
        }

    monkeypatch.setattr(orchestration, "run_v5_h4_exact_side_setup_only", fake_setup)
    identity = {
        "source_sha": "a" * 40,
        "physical_sha256": "b" * 64,
        "model_id": "task039_5nm_v4_1deg_s5_hybrid_iterative_m480",
    }
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        tmp_path / "v7-full-identity",
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: setup,
        v7_h4_exact_side_full_formal=True,
        v7_h4_exact_side_exact_spool_root=tmp_path / "exact-spool",
        selected_mode_packet_manifest=tmp_path / "manifest.json",
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256="d" * 64,
        recovery_runner=lambda *_args, **_kwargs: {"pass": True},
    )
    assert captured["producer"]["_hybrid_direct_authority_run_directory"] == Path(
        "results/task039_v4_h4_hybrid_direct_formal_mpi8_icntl14_1515f095"
    )
    assert captured["producer"]["_full3d_authority_run_directory"] is None
    assert captured["producer"]["consumer_source_sha"] == "c" * 40
    assert captured["producer"]["consumer_model_id"] == payload["model_id"]
    assert captured["producer"]["qualification_scope"] == "task039_v4_p6h4_m480_1deg_s"
    assert (
        captured["producer"]["qualification_method"]
        == "task039_v4_h4_exact_side_case_qualification"
    )
    assert captured["producer"]["direct_reference_payload_loaded"] is False
    assert result["schema"] == orchestration.V7_H4_EXACT_SIDE_FULL_FORMAL_SCHEMA
    assert result["outer_ksp"]["solve_called"] is True


@pytest.mark.parametrize(
    ("release", "expected_status", "recovery_expected"),
    (
        (
            {
                "factor_count_after_cleanup": {"bottom": 0, "top": 0},
                "factor_cleanup_pass": True,
                "actions_destroyed": True,
                "component_cleanup_pass": True,
                "component_cleanup": {
                    side: {name: True for name in ("H", "C", "F", "D")}
                    for side in ("bottom", "top")
                },
                "collective_heap_cleanup": {"collective_call_completed": True},
            },
            "full_formal_completed",
            True,
        ),
        (
            {
                "factor_count_after_cleanup": {"bottom": 0, "top": 1},
                "factor_cleanup_pass": False,
                "actions_destroyed": True,
                "component_cleanup_pass": False,
                "component_cleanup": {
                    "bottom": {name: True for name in ("H", "C", "F", "D")},
                    "top": {"H": True, "C": True, "F": True, "D": False},
                },
                "collective_heap_cleanup": {"collective_call_completed": False},
            },
            "full_formal_lifecycle_failure",
            False,
        ),
    ),
)
def test_v7_full_formal_release_gate_controls_recovery(
    monkeypatch, release, expected_status, recovery_expected
):
    snapshots = []

    class Vec:
        def duplicate(self):
            snapshot = Vec()
            snapshots.append(snapshot)
            return snapshot

        def copy(self, target):
            target.copied = True

        def destroy(self):
            self.destroyed = True

    iterative = SimpleNamespace(
        solution=Vec(),
        postsolve_audit={"pass": True, "ksp_type": "gmres", "restart": 10},
        converged_reason=1,
        iterations=2,
        block_relative_residuals={},
        timing={},
        inventory={"exact_factor_count": 0, "global_direct_factor_count": 0},
        destroy=lambda: None,
    )
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Vec())
    monkeypatch.setattr(
        orchestration,
        "solve_hybrid_block_ldu_iterative",
        lambda *_args, **kwargs: (
            kwargs["progress_callback"]({"multimetric_max_true_residual": 0.5})
            or iterative
        ),
    )
    recovery_calls = []
    markers = []

    def marker_callback(stage, _detail):
        markers.append(stage)

    result = orchestration._run_v7_h4_exact_side_full_formal(
        SimpleNamespace(),
        SimpleNamespace(),
        operator=None,
        context=None,
        comm=MPI.COMM_SELF,
        marker_callback=marker_callback,
        recovery_runner=lambda *_args: recovery_calls.append(True) or {"pass": True},
        producer={},
        run_directory=Path("."),
        release_before_recovery=lambda: release,
    )
    assert result["status"] == expected_status
    assert bool(recovery_calls) is recovery_expected
    assert markers.count("solution_snapshot_created") == 1
    assert markers.count("solution_snapshot_destroyed") == 1
    assert markers.count("recovery_physics_begin") == int(recovery_expected)
    assert markers.count("recovery_physics_end") == int(recovery_expected)
    assert snapshots and snapshots[0].destroyed is True
    if not recovery_expected:
        assert result["recovery"] == "not_run"


@pytest.mark.parametrize(
    ("status", "expected_exit"),
    (
        ("full_formal_completed", 0),
        ("full_formal_lifecycle_failure", 3),
        ("full_formal_recovery_failure", 3),
    ),
)
def test_v7_full_formal_main_exit_codes_are_status_sensitive(
    tmp_path, monkeypatch, capsys, status, expected_exit
):
    identity = tmp_path / "identity.json"
    identity.write_text(json.dumps({"model_id": "task039-test"}), encoding="utf-8")
    monkeypatch.setattr(
        orchestration,
        "MPI",
        SimpleNamespace(COMM_WORLD=SimpleNamespace(size=8, rank=0)),
    )
    monkeypatch.setattr(
        orchestration,
        "run_task039_v3_7_diagnostic",
        lambda *_args, **_kwargs: {"status": status},
    )
    exit_code = orchestration.main(
        [
            "--worker",
            "--launched-by-task038-watchdog",
            "--input",
            "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat",
            "--run-directory",
            str(tmp_path / "run"),
            "--source-sha",
            "a" * 40,
            "--v7-h4-exact-side-full-formal",
            "--selected-mode-packet-manifest",
            str(tmp_path / "manifest.json"),
            "--selected-mode-packet-identity",
            str(identity),
            "--selected-mode-packet-manifest-sha256",
            "b" * 64,
            "--v7-h4-exact-side-exact-spool-root",
            str(tmp_path / "spool"),
        ]
    )
    assert json.loads(capsys.readouterr().out)["status"] == status
    assert exit_code == expected_exit


def test_v3_7_candidate_authority_serializes_complex_orders_for_parser(
    tmp_path,
) -> None:
    class Physics:
        own_grid = {"path": "grid.npz"}
        external_orders = [
            {
                "side": "bottom",
                "m": 0,
                "n": 0,
                "polarization": "s",
                "power_ratio": np.float64(0.5),
                "outgoing_amplitude": 1.0 + 2.0j,
            }
        ]
        energy = {
            "R": 0.2,
            "T": 0.3,
            "A": 0.5,
            "A_volume": 0.5,
            "closure": 0.0,
        }
        traction = {"bottom": {"relative_dual": 0.0}, "top": {"relative_dual": 0.0}}
        interface_e_projection = {"combined_relative_residual": 0.0}
        canonical = {
            side: {
                "roles": {
                    role: {
                        "manifest": f"canonical/{side}_{role}.manifest.json",
                        "manifest_sha256": "c" * 64,
                    }
                    for role in ("active_trace", "full_fe")
                }
            }
            for side in ("bottom", "top")
        }

    run_directory = tmp_path / "run"
    _write_v3_7_candidate_authority(
        run_directory,
        Physics(),
        {
            "consumer_source_sha": "a" * 40,
            "consumer_model_id": "task039_5nm_v4_1deg_s5_hybrid_iterative_m480",
            "physical_model_sha256": "b" * 64,
            "qualification_scope": "task039_v4_p6h4_m480_1deg_s",
            "qualification_method": "task039_v4_h4_exact_side_case_qualification",
            "direct_reference_payload_loaded": False,
        },
        MPI.COMM_SELF,
    )
    authority = json.loads(
        (run_directory / "numerical_output" / "v3_7_hybrid_authority.json").read_text(
            encoding="utf-8"
        )
    )
    assert authority["external_orders"][0]["outgoing_amplitude"] == [1.0, 2.0]
    parsed = _parse_orders(authority["external_orders"], "candidate", expected_count=1)
    assert parsed[("bottom", 0, 0, "s")]["outgoing_amplitude"] == 1.0 + 2.0j
    assert _json_safe(np.asarray([1.0 + 2.0j])) == [[1.0, 2.0]]
    assert authority["model_id"] == "task039_5nm_v4_1deg_s5_hybrid_iterative_m480"
    assert authority["qualification_scope"] == "task039_v4_p6h4_m480_1deg_s"
    assert (
        authority["qualification_method"]
        == "task039_v4_h4_exact_side_case_qualification"
    )
    assert (
        authority["canonical"]["bottom"]["roles"]["full_fe"]["manifest_sha256"]
        == "c" * 64
    )


def test_v3_7_integrated_checker_runs_once_and_broadcasts(monkeypatch) -> None:
    class Comm:
        rank = 0
        shared = None

        def bcast(self, value, root):
            if value is not None:
                self.shared = value
            return self.shared

    comm = Comm()
    setup = SimpleNamespace(
        bottom=SimpleNamespace(
            b=None, local_mesh=SimpleNamespace(mesh=SimpleNamespace(comm=comm))
        ),
        top=SimpleNamespace(b=None),
    )
    layout = SimpleNamespace(split=lambda *_args: (object(), object(), object()))
    recovery = SimpleNamespace(
        recovery_pass=True,
        bottom_q=object(),
        top_q=object(),
        bottom_recovered=object(),
        top_recovered=object(),
        bottom_solution=object(),
        top_solution=object(),
        modal_solution=object(),
        destroy=lambda: None,
    )
    calls = []
    checker_outcome = {"pass": True}
    monkeypatch.setattr(
        orchestration, "recover_frozen_m10", lambda *_args, **_kwargs: recovery
    )
    monkeypatch.setattr(
        orchestration,
        "run_frozen_m10_physics",
        lambda *_args, **_kwargs: SimpleNamespace(physics_pass=True),
    )
    monkeypatch.setattr(
        orchestration, "_write_v3_7_candidate_authority", lambda *_args: None
    )
    monkeypatch.setattr(
        orchestration,
        "check_v3_7_integrated_physics",
        lambda *_args: calls.append("checker") or dict(checker_outcome),
    )
    first = orchestration.run_v3_7_recovery_runner(
        setup, layout, object(), Path("run"), {}, run_integrated_checker=True
    )
    comm.rank = 1
    second = orchestration.run_v3_7_recovery_runner(
        setup, layout, object(), Path("run"), {}, run_integrated_checker=True
    )
    assert calls == ["checker"]
    assert first["integrated_checker"] == second["integrated_checker"] == {"pass": True}
    comm.shared = None
    comm.rank = 0
    checker_outcome["pass"] = False
    failed = orchestration.run_v3_7_recovery_runner(
        setup, layout, object(), Path("run"), {}, run_integrated_checker=True
    )
    assert calls == ["checker", "checker"]
    assert failed["pass"] is False


def test_v3_7_external_key_gate_compares_sets_not_enumeration_order() -> None:
    keys = (
        ("bottom", 0, 0, "s"),
        ("top", 1, 0, "s"),
    )
    assert _same_external_key_set(keys, tuple(reversed(keys))) is True
    assert _same_external_key_set(keys, (keys[0], ("top", 2, 0, "s"))) is False
    assert _same_external_key_set(keys, keys[:1]) is False


def test_v3_7_ledger_is_atomic_noncollective_and_tracks_cleanup_boundary(
    tmp_path,
) -> None:
    class NoBarrierComm:
        rank = 0

        def barrier(self):
            raise AssertionError("marker checkpoint must not enter a barrier")

    ledger = _v3_7_object_ledger()
    _record_v3_7_marker(ledger, "qep_matrices_ready", {})
    _record_v3_7_marker(
        ledger,
        "modal_qep_temporaries_released",
        {"release_pass": True},
    )
    for marker in (
        "lift_columns_begin",
        "apply_columns_begin",
        "bottom_projection_begin",
        "top_projection_begin",
    ):
        _record_v3_7_marker(ledger, marker, {})
    _record_v3_7_marker(ledger, "identity_reference_materialization_end", {})
    _record_v3_7_marker(ledger, "borrowed_reference_cleanup_end", {})
    _record_v3_7_marker(ledger, "side_fixed_components_setup_end", {})
    _record_v3_7_marker(ledger, "side_survey_cleanup_end", {})
    _record_v3_7_marker(ledger, "one_cell_factor_destroyed", {})
    path = tmp_path / "numerical_output" / "memory_object_ledger.json"
    _write_v3_7_object_ledger(path, ledger, NoBarrierComm(), synchronize=False)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["objects"]["one_cell_factor"]["destroyed"] is True
    assert loaded["objects"]["qep_matrices"]["created"] is True
    assert loaded["objects"]["qep_matrices"]["destroyed"] is True
    assert loaded["objects"]["side_base_ilu"]["destroyed"] is True
    assert loaded["objects"]["independent_reference"]["destroyed"] is True
    for name in (
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
    ):
        assert loaded["objects"][name]["destroyed"] is True


def test_v3_7_formal_worker_injects_collective_cleanup_callback(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda comm: calls.append(comm) or {"collective_call_completed": True},
    )
    cleanup = _v3_7_cleanup_callback(MPI.COMM_SELF, None)
    assert cleanup()["collective_call_completed"] is True
    assert calls == [MPI.COMM_SELF]


def test_v3_7_dry_run_freezes_mpi8_worker_and_byte_watchdog(tmp_path) -> None:
    qualified_like = tmp_path / "qualified-python"
    qualified_like.symlink_to("/usr/bin/python3.12")
    plan = v3_7_execution_dry_run(
        INPUT,
        tmp_path / "run",
        source_sha="a" * 40,
        python_executable=qualified_like,
    )
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"][3] == str(qualified_like)
    assert "--worker" in plan["argv"]
    assert "--launched-by-task038-watchdog" in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 224000000000
    assert plan["watchdog"]["critical_action"] == "record_checkpoint_only"


def test_v5_h4_setup_only_plan_passes_identity_and_packet_args(tmp_path) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    manifest = tmp_path / "manifest.json"
    identity = tmp_path / "identity.json"
    sha = "d" * 64
    for plan_builder in (watchdog.v3_7_execution_dry_run, v3_7_execution_dry_run):
        plan = plan_builder(
            h4_input,
            tmp_path / "v5-plan",
            source_sha="a" * 40,
            v5_h4_setup_only=True,
            selected_mode_packet_manifest=manifest,
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256=sha,
        )
        assert plan["worker_contract"]["method"] == (
            "task039_v5_h4_exact_side_setup_only"
        )
        argv = plan["argv"]
        assert "--v5-h4-setup-only" in argv
        assert str(manifest.resolve()) in argv
        assert str(identity.resolve()) in argv
        assert sha in argv
    frozen_payload = json.loads(
        orchestration.V5_H4_SAMPLED_COLUMN_CONTRACT_PATH.read_text()
    )
    frozen_payload["contract"]["roles"]["extra"] = ["unexpected"]
    invalid_contract = tmp_path / "invalid-sampled-contract.json"
    invalid_contract.write_text(json.dumps(frozen_payload))
    with pytest.raises(ValueError, match="roles must cover"):
        orchestration._load_v5_h4_sampled_column_contract(invalid_contract)
    legacy = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "legacy-plan",
        source_sha="a" * 40,
    )
    assert "--v5-h4-setup-only" not in legacy["argv"]
    with pytest.raises(ValueError, match="exclusive"):
        watchdog.v3_7_execution_dry_run(
            h4_input,
            tmp_path / "conflict",
            source_sha="a" * 40,
            candidate_b_only=True,
            v5_h4_setup_only=True,
            selected_mode_packet_manifest=manifest,
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256=sha,
        )
    with pytest.raises(ValueError, match="exclusive"):
        watchdog.v3_7_execution_dry_run(
            h4_input,
            tmp_path / "both-v5-components",
            source_sha="a" * 40,
            v5_h4_setup_only=True,
            v5_h4_blr_side_only=True,
            selected_mode_packet_manifest=manifest,
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256=sha,
        )
    with pytest.raises(ValueError):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "wrong-identity",
            source_sha="a" * 40,
            v5_h4_setup_only=True,
            selected_mode_packet_manifest=manifest,
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256=sha,
        )
    parameters = inspect.signature(orchestration.run_task039_v3_7_diagnostic).parameters
    assert parameters["v5_h4_setup_only"].default is False
    assert parameters["v5_h4_blr_side_only"].default is False
    assert parameters["selected_mode_packet_manifest"].default is None
    assert parameters["selected_mode_packet_identity"].default is None
    assert parameters["selected_mode_packet_manifest_sha256"].default is None
    assert parameters["v5_streaming_w_batch_size"].default is None
    setup_parameters = inspect.signature(
        orchestration.run_v5_h4_exact_side_setup_only
    ).parameters
    assert setup_parameters["streaming_w_batch_size"].default is None
    assert '"setup_only_completed"' in inspect.getsource(orchestration.main)

    blr_plan = watchdog.v3_7_execution_dry_run(
        h4_input,
        tmp_path / "v5-blr-plan",
        source_sha="a" * 40,
        v5_h4_blr_side_only=True,
        v5_h4_blr_profile=orchestration.MUMPS_BLR_V5_H4_1E3_PROFILE,
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=sha,
    )
    assert "--v5-h4-blr-side-component" in blr_plan["argv"]
    assert "--v5-h4-setup-only" not in blr_plan["argv"]
    assert blr_plan["worker_contract"]["method"] == (
        "task039_v5_h4_mumps_blr_side_component"
    )
    assert blr_plan["worker_contract"]["mumps_blr_profile"] == (
        orchestration.MUMPS_BLR_V5_H4_1E3_PROFILE
    )
    assert "--v5-h4-blr-profile" in blr_plan["argv"]
    assert orchestration.MUMPS_BLR_V5_H4_1E3_PROFILE in blr_plan["argv"]
    default_blr_plan = watchdog.v3_7_execution_dry_run(
        h4_input,
        tmp_path / "v5-blr-default-plan",
        source_sha="a" * 40,
        v5_h4_blr_side_only=True,
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=sha,
    )
    assert default_blr_plan["worker_contract"]["mumps_blr_profile"] == (
        orchestration.MUMPS_BLR_V5_H4_PROFILE
    )
    assert "--v5-h4-blr-profile" not in default_blr_plan["argv"]
    assert "task039_v5_h4_mumps_blr_side_component" in inspect.getsource(
        task038_launcher._run_worker
    )
    launcher_source = inspect.getsource(task038_launcher._run_worker)
    assert "formal_v5_h4_fixed_budget" in launcher_source
    assert "v5_h4_fixed_budget_bottom_component_resource_authority" in launcher_source
    assert '"gate_basis": "candidate_setup_interval_only"' in launcher_source
    assert (
        '"online_and_overall_role": "evidence_only_not_advancement_gate"'
        in launcher_source
    )
    assert '"pass": None' in launcher_source
    orchestration_main_source = inspect.getsource(orchestration.main)
    assert "or args.v6_h4_post_compaction_setup_only" in orchestration_main_source
    assert "packet_identity = json.loads" in orchestration_main_source
    route_source = inspect.getsource(orchestration.run_v5_h4_mumps_blr_side_component)
    assert route_source.index("exact_diagnostics = exact_action.diagnostics") < (
        route_source.index("v5_blr_exact_reference_{side}_ready")
    )
    assert route_source.index("candidate_setup_diagnostics = action.diagnostics") < (
        route_source.index("v5_blr_candidate_{side}_ready")
    )


def test_v7_streamed_producer_orchestration_plan_forwards_packet_route(
    tmp_path,
) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    plan = orchestration.v3_7_execution_dry_run(
        h4_input,
        tmp_path / "v7-streamed-plan",
        source_sha="a" * 40,
        v7_h4_streamed_bottom_producer=True,
        selected_mode_packet_manifest=packet_root / "manifest.json",
        selected_mode_packet_identity=packet_root / "identity.json",
        selected_mode_packet_manifest_sha256="b" * 64,
    )
    argv = plan["argv"]
    assert argv.count("--v7-h4-streamed-bottom-producer") == 1
    route_flags = (
        "--candidate-b-only",
        "--candidate-c-only",
        "--candidate-d-only",
        "--candidate-d-qualified",
        "--candidate-e-side-only",
        "--v5-h4-setup-only",
        "--v5-h4-blr-side-component",
        "--v5-h4-fixed-budget-bottom-component",
        "--v6-h4-post-compaction-setup-only",
        "--v6-h4-port-modal-bottom-component",
        "--v7-h4-exact-side-limit-setup-only",
        "--v7-h4-exact-side-full-formal",
        "--v7-h4-streamed-bottom-producer",
    )
    assert sum(flag in argv for flag in route_flags) == 1
    assert all("exact-spool" not in argument for argument in argv)
    assert plan["worker_contract"]["method"] == (
        orchestration.V7_STREAMED_PETROV_METHOD
    )
    assert plan["worker_contract"]["profile_id"] == (
        orchestration.V7_STREAMED_PETROV_PROFILE_ID
    )
    assert plan["worker_contract"]["exact_spool_root"] is None
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        orchestration.V7_STREAMED_PETROV_HARD_STOP_BYTES
    )
    assert (
        "v7_h4_streamed_bottom_producer"
        in inspect.signature(orchestration.v3_7_execution_dry_run).parameters
    )
    assert (
        "v7_h4_streamed_bottom_producer"
        in inspect.signature(orchestration.launch_v3_7_with_task038_watchdog).parameters
    )
    with pytest.raises(ValueError, match="exclusive"):
        orchestration.v3_7_execution_dry_run(
            h4_input,
            tmp_path / "v7-streamed-conflict",
            source_sha="a" * 40,
            v5_h4_fixed_budget_bottom_only=True,
            v7_h4_streamed_bottom_producer=True,
            selected_mode_packet_manifest=packet_root / "manifest.json",
            selected_mode_packet_identity=packet_root / "identity.json",
            selected_mode_packet_manifest_sha256="b" * 64,
        )


def test_v7_streamed_consumer_orchestration_plan_forwards_basis_and_spool(
    tmp_path,
) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    basis_manifest = tmp_path / "basis-manifest.json"
    exact_spool = tmp_path / "exact-spool"
    basis_sha = "b" * 64
    packet_sha = "c" * 64
    for plan_builder in (watchdog.v3_7_execution_dry_run, v3_7_execution_dry_run):
        plan = plan_builder(
            h4_input,
            tmp_path / "v7-consumer-plan",
            source_sha="a" * 40,
            v7_h4_streamed_bottom_consumer=True,
            v7_h4_streamed_bottom_consumer_basis_manifest=basis_manifest,
            v7_h4_streamed_bottom_consumer_basis_manifest_sha256=basis_sha,
            v7_h4_streamed_bottom_consumer_exact_spool_root=exact_spool,
            selected_mode_packet_manifest=packet_root / "manifest.json",
            selected_mode_packet_identity=packet_root / "identity.json",
            selected_mode_packet_manifest_sha256=packet_sha,
        )
        argv = plan["argv"]
        assert argv.count("--v7-h4-streamed-bottom-consumer") == 1
        route_flags = (
            "--candidate-b-only",
            "--candidate-c-only",
            "--candidate-d-only",
            "--candidate-d-qualified",
            "--candidate-e-side-only",
            "--v5-h4-setup-only",
            "--v5-h4-blr-side-component",
            "--v5-h4-fixed-budget-bottom-component",
            "--v6-h4-post-compaction-setup-only",
            "--v6-h4-port-modal-bottom-component",
            "--v7-h4-exact-side-limit-setup-only",
            "--v7-h4-exact-side-full-formal",
            "--v7-h4-streamed-bottom-producer",
            "--v7-h4-streamed-bottom-consumer",
        )
        assert sum(flag in argv for flag in route_flags) == 1
        assert str(basis_manifest.resolve()) in argv
        assert basis_sha in argv
        assert str(exact_spool.resolve()) in argv
        assert plan["worker_contract"]["method"] == (
            "task039_v7_streamed_bottom_petrov_consumer"
        )
        assert plan["worker_contract"]["profile_id"] == (
            orchestration.V7_STREAMED_PETROV_CONSUMER_PROFILE_ID
        )
        assert plan["worker_contract"]["exact_spool_root"] == str(exact_spool.resolve())
        assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
            orchestration.V7_STREAMED_PETROV_CONSUMER_HARD_STOP_BYTES
        )


def test_v5_h4_blr_watchdog_main_dry_run_parses_real_flag(tmp_path, capsys) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    packet_root = Path("results/task039_v4_h4_m480_shared_packet_eaad0f94")
    run_directory = tmp_path / "v5-blr-main-dry-run"
    assert (
        watchdog.main(
            [
                "--dry-run",
                "--input",
                str(h4_input),
                "--run-directory",
                str(run_directory),
                "--source-sha",
                "a" * 40,
                "--v5-h4-blr-side-component",
                "--v5-h4-blr-profile",
                orchestration.MUMPS_BLR_V5_H4_1E3_PROFILE,
                "--selected-mode-packet-manifest",
                str(packet_root / "manifest.json"),
                "--selected-mode-packet-identity",
                str(packet_root / "identity.json"),
                "--selected-mode-packet-manifest-sha256",
                "2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"].count("--v5-h4-blr-side-component") == 1
    assert "--v5-h4-setup-only" not in plan["argv"]
    assert plan["worker_contract"]["method"] == (
        "task039_v5_h4_mumps_blr_side_component"
    )
    assert plan["worker_contract"]["mumps_blr_profile"] == (
        orchestration.MUMPS_BLR_V5_H4_1E3_PROFILE
    )
    assert not run_directory.exists()


def test_v5_h4_blr_parent_peak_uses_closed_parent_sample_interval(tmp_path) -> None:
    stages = tmp_path / "memory_stages.jsonl"
    samples = tmp_path / "process_tree_samples.jsonl"
    stages.write_text(
        "\n".join(
            json.dumps(
                {
                    "stage": stage,
                    "sample_elapsed_seconds": elapsed,
                    "sample_status": "measured",
                }
            )
            for stage, elapsed in (
                ("v5_blr_candidate_bottom_setup_begin", 10.0),
                ("v5_blr_candidate_bottom_setup_end", 20.0),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    samples.write_text(
        "\n".join(
            json.dumps(
                {
                    "elapsed_seconds": elapsed,
                    "rss_bytes": rss,
                    "sample_status": sample_status,
                }
            )
            for elapsed, rss, sample_status in (
                (9.0, 100 * 1024**3, "not_available"),
                (10.0, 4 * 1024**3, "measured"),
                (15.0, 100 * 1024**3, "not_available"),
                (16.0, 6 * 1024**3, "measured"),
                (20.0, 5 * 1024**3, "measured"),
                (21.0, 100 * 1024**3, "not_available"),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    result = task038_launcher._v5_h4_blr_candidate_interval_peak(
        stages, samples, "bottom"
    )
    assert result["status"] == "measured"
    assert result["peak_process_tree_rss_gib"] == 6.0
    assert result["time_basis"] == "parent_process_tree_sample_elapsed_seconds"


def test_v5_fixed_budget_parent_peak_uses_bottom_marker_alignment(tmp_path) -> None:
    stages = tmp_path / "memory_stages.jsonl"
    samples = tmp_path / "process_tree_samples.jsonl"
    stages.write_text(
        "\n".join(
            json.dumps(
                {
                    "stage": stage,
                    "sample_elapsed_seconds": elapsed,
                    "sample_status": "measured",
                }
            )
            for stage, elapsed in (
                ("v5_fixed_budget_candidate_bottom_setup_begin", 3.0),
                ("v5_fixed_budget_candidate_bottom_setup_end", 7.0),
                ("v5_fixed_budget_candidate_bottom_online_begin", 8.0),
                ("v5_fixed_budget_candidate_bottom_online_end", 12.0),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    samples.write_text(
        "\n".join(
            json.dumps(
                {
                    "elapsed_seconds": elapsed,
                    "rss_bytes": rss,
                    "sample_status": "measured",
                }
            )
            for elapsed, rss in (
                (3.0, 4 * 1024**3),
                (5.0, 7 * 1024**3),
                (7.0, 6 * 1024**3),
                (8.0, 8 * 1024**3),
                (10.0, 9 * 1024**3),
                (12.0, 6 * 1024**3),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    result = task038_launcher._v5_h4_blr_candidate_interval_peak(
        stages,
        samples,
        "bottom",
        marker_prefix="v5_fixed_budget_candidate",
    )
    assert result["status"] == "measured"
    assert result["peak_process_tree_rss_gib"] == 7.0
    assert result["pass"] is True
    online = task038_launcher._v5_h4_blr_candidate_interval_peak(
        stages,
        samples,
        "bottom",
        marker_prefix="v5_fixed_budget_candidate",
        begin_suffix="online_begin",
        end_suffix="online_end",
    )
    assert online["status"] == "measured"
    assert online["peak_process_tree_rss_gib"] == 9.0
    assert online["pass"] is True


def test_v6_parent_authority_separates_input_stop_from_effective_and_final_fields(
    tmp_path,
) -> None:
    stages = tmp_path / "memory_stages.jsonl"
    samples = tmp_path / "process_tree_samples.jsonl"
    ledger = tmp_path / "memory_object_ledger.json"
    stages.write_text(
        json.dumps(
            {
                "stage": "outer_ksp_setup_ready",
                "sample_elapsed_seconds": 4.0,
                "sample_status": "measured",
                "rss_bytes": 30 * 1024**3,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    samples.write_text(
        json.dumps(
            {
                "elapsed_seconds": 4.0,
                "rss_bytes": 40 * 1024**3,
                "swap_bytes": 0,
                "sample_status": "measured",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    ledger.write_text(
        json.dumps(
            {
                "objects": {
                    "exact_side_factors": {
                        "details": {
                            "factor_count_after_cleanup": {
                                "bottom": 0,
                                "top": 0,
                            }
                        }
                    },
                    "qep_matrices": {"destroyed": True},
                    "selected_basis": {"destroyed": True},
                }
            }
        ),
        encoding="utf-8",
    )
    authority = task038_launcher._v6_post_compaction_resource_authority(
        stages,
        samples,
        ledger,
        input_absolute_terminate_memory_bytes=224000000000,
        effective_absolute_terminate_memory_bytes=45118258790,
        setup_limit_gib=42.019652939,
        outer_ready_limit_gib=35.0,
        poll_interval_seconds=0.25,
    )
    assert authority["status"] == "measured"
    assert authority["input_absolute_terminate_memory_bytes"] == 224000000000
    assert authority["effective_absolute_terminate_memory_bytes"] == 45118258790
    assert authority["overall_process_tree"]["peak_process_tree_rss_gib"] == 40.0
    assert authority["outer_ksp_setup_ready"]["process_tree_rss_gib"] == 30.0
    assert authority["swap"]["zero_swap"] is True
    assert authority["final_lifecycle"]["factor_count_after_final_cleanup"] == {
        "bottom": 0,
        "top": 0,
    }
    assert authority["final_lifecycle"]["packet_qep_refs_released"] is True
    assert authority["resource_pass"] is True


@pytest.mark.parametrize(
    ("method", "effective_bytes", "telemetry_key"),
    (
        (
            "task039_v6_h4_post_compaction_setup_only",
            45118258790,
            "v6_h4_post_compaction_setup_telemetry",
        ),
        (
            "task039_v7_h4_exact_side_limit_setup_only",
            90236517581,
            "v7_h4_exact_side_limit_setup_telemetry",
        ),
        (
            "task039_v7_streamed_bottom_basis_producer",
            100262797312,
            "v7_h4_streamed_bottom_producer_telemetry",
        ),
        (
            "task039_v7_streamed_bottom_petrov_consumer",
            90236517581,
            "v7_h4_streamed_bottom_consumer_telemetry",
        ),
    ),
)
def test_v6_and_v7_run_worker_use_effective_byte_stop_without_mutating_input(
    monkeypatch, tmp_path, method, effective_bytes, telemetry_key
) -> None:
    specification = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    )
    input_bytes = 224000000000
    monkeypatch.setattr(
        task038_launcher,
        "_task039_memory_budget",
        lambda _execution=None: {
            "configured_warning_memory_gib": 170.0,
            "configured_critical_memory_gib": 195.0,
            "absolute_terminate_memory_bytes": input_bytes,
            "source": {"selected": "fixture"},
        },
    )

    class Process:
        pid = 12345

        def __init__(self):
            self.returncode = None

        def poll(self):
            return self.returncode

        def wait(self):
            return self.returncode

    process = Process()
    terminated: list[Process] = []
    plan = SimpleNamespace(
        argv=("contract-probe",),
        method=method,
        contract_probe=False,
        task039_trace_audit=False,
    )
    result = task038_launcher._run_worker(
        plan,
        specification,
        tmp_path,
        popen_factory=lambda *_args, **_kwargs: process,
        sample_factory=lambda _pid: {
            "memory_authority_bytes": effective_bytes,
            "process_tree": {
                "root_pid": process.pid,
                "rss_bytes": effective_bytes,
                "swap_bytes": 0,
                "all_status_readable": True,
                "smaps": {"complete": False},
            },
            "job_cgroup": {},
        },
        terminate_factory=lambda member: (
            terminated.append(member) or setattr(member, "returncode", -9) or {}
        ),
        monotonic=lambda: 0.0,
        sleep=lambda _seconds: None,
        poll_interval=0.25,
    )
    assert result["result_classification"] == "memory_terminate"
    assert terminated == [process]
    authority = result["resource_authority"]
    assert authority["task039_memory_budget"]["absolute_terminate_memory_bytes"] == (
        input_bytes
    )
    assert authority["absolute_terminate_memory_bytes"] == effective_bytes
    telemetry = authority[telemetry_key]
    assert (
        telemetry["method_override"]["input_absolute_terminate_memory_bytes"]
        == input_bytes
    )
    assert telemetry["method_override"][
        "effective_absolute_terminate_memory_bytes"
    ] == (effective_bytes)
    if telemetry_key == "v7_h4_exact_side_limit_setup_telemetry":
        assert telemetry["gate_contract"]["outer_ready_peak_limit_gib"] == 84.039305878
        assert telemetry["gate_contract"]["outer_ready_peak_limit_gib"] != 35.0
    if telemetry_key == "v7_h4_streamed_bottom_producer_telemetry":
        assert telemetry["gate_contract"][
            "peak_process_tree_rss_bytes_strictly_below"
        ] == (100262797312)
        assert telemetry["gate_contract"]["exact_spool_opened"] is False
    if telemetry_key == "v7_h4_streamed_bottom_consumer_telemetry":
        assert telemetry["gate_contract"]["candidate_setup_peak_limit_gib"] == (
            84.039305878
        )
        assert telemetry["gate_contract"]["swap_required"] == 0
        assert telemetry["gate_contract"]["exact_factor_count"] == 0
        assert telemetry["gate_contract"]["global_direct_factor_count"] == 0
        assert telemetry["gate_contract"]["nested_ksp_count"] == 0


def test_v3_7_worker_failure_persists_full_traceback(tmp_path) -> None:
    try:
        raise RuntimeError("traceback-contract")
    except RuntimeError:
        path = orchestration._write_v3_7_worker_traceback(tmp_path)
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "Traceback (most recent call last)" in text
    assert "RuntimeError: traceback-contract" in text


def test_v6_port_modal_resource_intervals_require_measured_samples(tmp_path) -> None:
    stages = tmp_path / "memory_stages.jsonl"
    samples = tmp_path / "process_tree_samples.jsonl"
    stage_rows = [
        {
            "stage": "v6_port_modal_bottom_construction_begin",
            "sample_elapsed_seconds": 1.0,
            "sample_status": "measured",
        },
        {
            "stage": "v6_port_modal_bottom_construction_end",
            "sample_elapsed_seconds": 3.0,
            "sample_status": "measured",
        },
        {
            "stage": "v6_port_modal_bottom_retained_apply_state_ready",
            "sample_elapsed_seconds": 4.0,
            "sample_status": "measured",
        },
        {
            "stage": "v6_port_modal_bottom_cleanup",
            "sample_elapsed_seconds": 6.0,
            "sample_status": "measured",
        },
    ]
    stage_rows = "\n".join(json.dumps(row) for row in stage_rows) + "\n"
    stages.write_text(stage_rows, encoding="utf-8")
    sample_rows = (
        "\n".join(
            json.dumps(
                {
                    "elapsed_seconds": elapsed,
                    "rss_bytes": 10 * 1024**3,
                    "sample_status": "measured",
                }
            )
            for elapsed in (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        )
        + "\n"
    )
    samples.write_text(sample_rows, encoding="utf-8")
    construction = task038_launcher._v5_h4_blr_candidate_interval_peak(
        stages,
        samples,
        "bottom",
        begin_stage="v6_port_modal_bottom_construction_begin",
        end_stage="v6_port_modal_bottom_construction_end",
        limit_gib=22.0,
    )
    retained = task038_launcher._v5_h4_blr_candidate_interval_peak(
        stages,
        samples,
        "bottom",
        begin_stage="v6_port_modal_bottom_retained_apply_state_ready",
        end_stage="v6_port_modal_bottom_cleanup",
        limit_gib=16.0,
    )
    for interval, begin, end in (
        (construction, 1.0, 3.0),
        (retained, 4.0, 6.0),
    ):
        assert interval["status"] == "measured"
        assert interval["begin_sample_elapsed_seconds"] == begin
        assert interval["end_sample_elapsed_seconds"] == end
        assert interval["sample_count"] > 0
        assert interval["pass"] is True


def test_v6_port_modal_holdout_gate_enforces_frozen_degeneracy_and_limits() -> None:
    reports = _v6_gate_reports()
    result = orchestration._v6_port_modal_holdout_gate(reports)
    assert result["pass"] is True
    assert result["mandatory_labels"] == [
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    ]
    assert result["degenerate_labels"] == ["physical_side_rhs"]
    assert result["preferred_residual_is_diagnostic"] is False

    preferred_fail = _v6_gate_reports(preferred_residual=2.0e-3)
    preferred_result = orchestration._v6_port_modal_holdout_gate(preferred_fail)
    assert preferred_result["true_residual_pass"] is True
    assert preferred_result["preferred_residual_pass"] is False
    assert preferred_result["pass"] is False

    random_fail = _v6_gate_reports(random_residual=2.0e-2)
    random_result = orchestration._v6_port_modal_holdout_gate(random_fail)
    assert random_result["true_residual_pass"] is False
    assert random_result["pass"] is False

    physical_required = _v6_gate_reports(physical_degenerate=False)
    physical_result = orchestration._v6_port_modal_holdout_gate(physical_required)
    assert physical_result["pass"] is True
    assert "physical_side_rhs" in physical_result["mandatory_labels"]

    random_degenerate = _v6_gate_reports()
    random_degenerate[4]["degenerate_uninformative"] = True
    with pytest.raises(ValueError, match="Only physical_side_rhs"):
        orchestration._v6_port_modal_holdout_gate(random_degenerate)


def test_v6_port_modal_holdout_gate_rejects_missing_or_duplicate_labels() -> None:
    missing = _v6_gate_reports()[:-1]
    with pytest.raises(ValueError, match="frozen six"):
        orchestration._v6_port_modal_holdout_gate(missing)

    duplicate = _v6_gate_reports()
    duplicate[1]["label"] = duplicate[0]["label"]
    with pytest.raises(ValueError, match="unique six"):
        orchestration._v6_port_modal_holdout_gate(duplicate)


def test_v5_h4_blr_parent_peak_missing_evidence_fails_closed(tmp_path) -> None:
    result = task038_launcher._v5_h4_blr_candidate_interval_peak(
        tmp_path / "missing-stages.jsonl",
        tmp_path / "missing-samples.jsonl",
        "bottom",
    )
    assert result["status"] == "not_available"
    assert result["peak_process_tree_rss_gib"] is None
    assert result["pass"] is False


def test_v5_h4_blr_parent_peak_without_interval_sample_fails_closed(tmp_path) -> None:
    stages = tmp_path / "memory_stages.jsonl"
    samples = tmp_path / "process_tree_samples.jsonl"
    stages.write_text(
        "\n".join(
            json.dumps(
                {
                    "stage": stage,
                    "sample_elapsed_seconds": elapsed,
                    "sample_status": "measured",
                }
            )
            for stage, elapsed in (
                ("v5_blr_candidate_top_setup_begin", 10.0),
                ("v5_blr_candidate_top_setup_end", 20.0),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    samples.write_text(
        json.dumps({"elapsed_seconds": 9.0, "rss_bytes": 4 * 1024**3}) + "\n",
        encoding="utf-8",
    )
    result = task038_launcher._v5_h4_blr_candidate_interval_peak(stages, samples, "top")
    assert result["status"] == "not_available"
    assert result["peak_process_tree_rss_gib"] is None
    assert result["pass"] is False


def test_v5_blr_reference_spool_hash_excludes_self_and_is_verified(tmp_path) -> None:
    _, matrix, vector = _tiny_side_system((1.0, 2.0))
    try:
        record = orchestration._write_v5_blr_reference_spool(
            tmp_path,
            "bottom",
            "probe",
            vector,
            "rhs",
            {"source": "fixture"},
        )
        assert "metadata_payload_sha256_excluding_self" in record
        loaded = orchestration._load_v5_blr_reference_spool(record, vector)
        loaded.destroy()
        metadata_path = Path(record["metadata_path"])
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["source_identity"]["tampered"] = True
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        with pytest.raises(ValueError, match="metadata payload hash"):
            orchestration._load_v5_blr_reference_spool(record, vector)
    finally:
        vector.destroy()
        matrix.destroy()


def test_v5_h4_blr_rhs_identity_is_deterministic_and_column_bounded() -> None:
    comm = PETSc.COMM_WORLD
    F = PETSc.Mat().createAIJ([4, 4], nnz=2, comm=comm)
    C = PETSc.Mat().createAIJ([4, 3], nnz=1, comm=comm)
    F.setUp()
    C.setUp()
    first, last = (int(value) for value in F.getOwnershipRange())
    for row in range(first, last):
        F.setValue(row, row, 2.0)
        C.setValue(row, row % 3, 1.0 + 0.1 * row)
    F.assemble()
    C.assemble()
    rhs_base = F.createVecLeft()
    rhs_base.set(1.0)
    rhs_base.assemble()
    system = SimpleNamespace(A=F, b=rhs_base)
    components = SimpleNamespace(F=F, C=C)
    coupling = SimpleNamespace(positive_traction=C, negative_traction=C)
    first_rhs = second_rhs = third_rhs = None
    try:
        first_rhs, first_meta = _v5_blr_rhs_vector(
            ("external_dtn_coupling", "C", 7), system, coupling, components
        )
        second_rhs, second_meta = _v5_blr_rhs_vector(
            ("external_dtn_coupling", "C", 7), system, coupling, components
        )
        third_rhs, third_meta = _v5_blr_rhs_vector(
            ("external_dtn_coupling", "C", 8), system, coupling, components
        )
        assert first_meta["resolved_column"] == 1
        assert third_meta["resolved_column"] == 2
        assert 0 <= first_meta["resolved_column"] < first_meta["column_count"]
        assert (
            first_meta["identity"]["global_sha256"]
            == second_meta["identity"]["global_sha256"]
        )
        assert first_meta["identity"]["global_size"] == 4
    finally:
        for vector in (first_rhs, second_rhs, third_rhs, rhs_base):
            if vector is not None:
                vector.destroy()
        C.destroy()
        F.destroy()


def test_v5_blr_external_rhs_survives_action_c_ownership_transfer() -> None:
    comm = PETSc.COMM_WORLD
    F = PETSc.Mat().createAIJ([4, 4], nnz=2, comm=comm)
    C = PETSc.Mat().createAIJ([4, 3], nnz=1, comm=comm)
    F.setUp()
    C.setUp()
    first, last = (int(value) for value in F.getOwnershipRange())
    for row in range(first, last):
        F.setValue(row, row, 2.0)
        C.setValue(row, row % 3, 1.0 + 0.1 * row)
    F.assemble()
    C.assemble()
    components = SimpleNamespace(F=F, C=C)
    system = SimpleNamespace(A=F, b=F.createVecLeft())
    prefrozen = None
    try:
        prefrozen = _v5_blr_prefreeze_external_rhs(
            ("external_dtn_coupling", "C", 7), system, components
        )
        components.C = None
        assert prefrozen[1]["source"] == "pre_action_components.C"
        assert prefrozen[1]["kind"] == "C"
        assert prefrozen[1]["prefrozen_before_action_ownership_transfer"] is True
        assert prefrozen[1]["resolved_column"] == 1
        assert np.isfinite(float(prefrozen[0].norm()))
    finally:
        if prefrozen is not None:
            prefrozen[0].destroy()
        system.b.destroy()
        C.destroy()
        F.destroy()


@pytest.mark.parametrize(
    ("exact_cleanup_counts", "expected_error", "failure_stage"),
    [
        ({"exact": 0, "compressed": 0, "global": 0}, None, None),
        (
            {"exact": 1, "compressed": 0, "global": 0},
            "did not release all factors",
            None,
        ),
        (
            {"exact": 0, "compressed": 0, "global": 0},
            "action creation failed",
            "action",
        ),
        ({"exact": 0, "compressed": 0, "global": 0}, "probe failed", "probe"),
    ],
)
def test_v5_h4_blr_injected_route_keeps_exact_candidate_lifecycle(
    tmp_path, monkeypatch, exact_cleanup_counts, expected_error, failure_stage
) -> None:
    class FakeVec:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class FakeOperator:
        def createVecLeft(self):
            return FakeVec()

    class FakeAction:
        def __init__(self, compressed):
            self.compressed = compressed
            self.operator = FakeOperator()
            self.woodbury = SimpleNamespace(
                mark_borrowed_matrices_released=lambda: None
            )
            self.diagnostics = {
                "exact_factor_count": 0 if compressed else 1,
                "compressed_factor_count": 1 if compressed else 0,
                "direct_factor_count": 1,
                "global_direct_factor_count": 0,
                "mumps_controls_verified": True,
            }

        def destroy(self):
            return None

    class FakeComponents:
        F = C = D = H = object()

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(bottom=SimpleNamespace(), top=SimpleNamespace()),
    )
    markers = []
    marker_details = {}
    factory_kinds = []
    prefrozen_calls = []
    prefrozen_vectors = []
    template_vectors = []
    destroy_calls = 0

    def fake_components(_system):
        return FakeComponents()

    def fake_action(*_args, compressed_factor_profile=None, **_kwargs):
        factory_kinds.append(compressed_factor_profile)
        _args[1].C = None
        if failure_stage == "action" and len(factory_kinds) == 1:
            raise RuntimeError("action creation failed")
        return FakeAction(compressed_factor_profile is not None)

    def fake_rhs(spec, *_args):
        return FakeVec(), {
            "label": spec[0],
            "source": spec[1],
            "seed": spec[2],
            "identity": {"global_sha256": spec[0]},
            "degenerate_uninformative": False,
        }

    def fake_prefreeze(spec, *_args):
        prefrozen_calls.append(spec[0])
        vector = FakeVec()
        prefrozen_vectors.append(vector)
        assert getattr(_args[-1], "C", None) is not None
        return vector, {
            "label": spec[0],
            "kind": spec[1],
            "source": "pre_action_components.C",
            "seed": spec[2],
            "resolved_column": 0,
            "column_count": 1,
            "identity": {"global_sha256": spec[0]},
            "degenerate_uninformative": False,
        }

    def fake_probe(_action, _system, _rhs, metadata, reference_vector=None, **kwargs):
        if (
            failure_stage == "probe"
            and reference_vector is None
            and metadata["label"] == "external_dtn_coupling"
        ):
            raise RuntimeError("probe failed")
        candidate = reference_vector is not None
        report = {
            **metadata,
            "finite": True,
            "true_residual_relative": 1.0e-4,
            "reference_relative_error": 1.0e-12 if candidate else None,
            "repeat_relative_error": 1.0e-12 if candidate else None,
            "linearity_relative_error": (
                1.0e-12
                if candidate and metadata["label"] == "fixed_random_repeat_0"
                else None
            ),
            "output": {"global_sha256": metadata["label"]},
        }
        return report, (FakeVec() if kwargs.get("retain_output") else None)

    monkeypatch.setattr(
        orchestration, "_build_research_explicit_side_components", fake_components
    )
    monkeypatch.setattr(
        orchestration, "create_research_exact_side_lu_action", fake_action
    )
    monkeypatch.setattr(orchestration, "_v5_blr_rhs_vector", fake_rhs)
    monkeypatch.setattr(orchestration, "_v5_blr_prefreeze_external_rhs", fake_prefreeze)
    monkeypatch.setattr(orchestration, "_v5_blr_probe", fake_probe)
    monkeypatch.setattr(
        orchestration,
        "_write_v5_blr_reference_spool",
        lambda *_args, **_kwargs: {
            "role": _args[4],
            "source_identity": _args[5],
        },
    )
    monkeypatch.setattr(
        orchestration,
        "_load_v5_blr_reference_spool",
        lambda _record, template: (template_vectors.append(template), FakeVec())[1],
    )
    monkeypatch.setattr(
        orchestration,
        "_destroy_v5_side_components",
        lambda *_args, **_kwargs: {
            "F": True,
            "C": True,
            "H": True,
            "D": True,
        },
    )
    monkeypatch.setattr(
        orchestration,
        "_v5_blr_destroy_side",
        lambda *_args, **_kwargs: _fake_v5_blr_destroy_side(),
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )

    def _fake_v5_blr_destroy_side():
        nonlocal destroy_calls
        destroy_calls += 1
        counts = (
            exact_cleanup_counts
            if destroy_calls == 1
            else {
                "exact": 0,
                "compressed": 0,
                "global": 0,
            }
        )
        return {
            "action": {
                "exact_factor_count": 0,
                "compressed_factor_count": 0,
                "direct_factor_count": 0,
                "global_direct_factor_count": 0,
            },
            "factor_count_after_cleanup": counts,
        }

    def _record_marker(marker, detail):
        markers.append(marker)
        marker_details[marker] = detail

    if expected_error is not None:
        with pytest.raises(RuntimeError, match=expected_error):
            orchestration.run_v5_h4_mumps_blr_side_component(
                setup,
                comm=MPI.COMM_SELF,
                marker_callback=_record_marker,
                run_directory=tmp_path,
                source_identity={"packet_identity": {"model_id": "h4"}},
            )
        assert "v5_blr_candidate_bottom_setup_begin" not in markers
        assert prefrozen_vectors and all(
            vector.destroyed for vector in prefrozen_vectors
        )
        return

    result = orchestration.run_v5_h4_mumps_blr_side_component(
        setup,
        comm=MPI.COMM_SELF,
        marker_callback=_record_marker,
        run_directory=tmp_path,
        source_identity={"packet_identity": {"model_id": "h4"}},
    )
    assert factory_kinds == [
        None,
        orchestration.MUMPS_BLR_V5_H4_PROFILE,
        None,
        orchestration.MUMPS_BLR_V5_H4_PROFILE,
    ]
    assert prefrozen_calls == ["external_dtn_coupling", "external_dtn_coupling"]
    assert all(vector.destroyed for vector in prefrozen_vectors)
    assert len(template_vectors) == 4 * len(orchestration.V5_H4_BLR_RHS_SPECS)
    assert all(vector.destroyed for vector in template_vectors)
    expected_labels = [spec[0] for spec in orchestration.V5_H4_BLR_RHS_SPECS]
    assert [
        item["label"] for item in result["sides"]["bottom"]["exact"]["probes"]
    ] == expected_labels
    assert [
        item["label"] for item in result["sides"]["top"]["exact"]["probes"]
    ] == expected_labels
    assert (
        result["sides"]["bottom"]["exact"]["probes"][3]["source"]
        == "pre_action_components.C"
    )
    assert (
        result["sides"]["top"]["exact"]["probes"][3]["source"]
        == "pre_action_components.C"
    )
    bottom_exact_cleanup = markers.index("v5_blr_exact_reference_bottom_cleanup")
    bottom_candidate_begin = markers.index("v5_blr_candidate_bottom_setup_begin")
    bottom_candidate_end = markers.index("v5_blr_candidate_bottom_setup_end")
    bottom_candidate_cleanup = markers.index("v5_blr_candidate_bottom_cleanup")
    assert bottom_exact_cleanup < bottom_candidate_begin < bottom_candidate_end
    assert bottom_candidate_end < bottom_candidate_cleanup
    assert (
        marker_details["v5_blr_exact_reference_bottom_cleanup"]["cleanup"][
            "factor_count_after_cleanup"
        ]
        == exact_cleanup_counts
    )
    assert result["status"] == "component_completed"
    assert result["gates"]["numerical_pass"] is True
    assert result["gates"]["resource_pass"] is None


def test_v5_h4_fixed_budget_plan_freezes_bottom_route_and_spool(tmp_path) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    manifest = tmp_path / "manifest.json"
    identity = tmp_path / "identity.json"
    spool = tmp_path / "exact-spool"
    plan = watchdog.v3_7_execution_dry_run(
        h4_input,
        tmp_path / "fixed-budget-plan",
        source_sha="a" * 40,
        v5_h4_fixed_budget_bottom_only=True,
        v5_h4_fixed_budget_exact_spool_root=spool,
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256="b" * 64,
    )
    argv = plan["argv"]
    assert argv.count("--v5-h4-fixed-budget-bottom-component") == 1
    assert str(spool.resolve()) in argv
    assert "--v5-h4-blr-side-component" not in argv
    assert "--v5-h4-setup-only" not in argv
    assert "--fixed-budget" not in argv
    assert plan["worker_contract"]["method"] == (
        orchestration.V5_H4_FIXED_BUDGET_SIDE_METHOD
    )
    assert plan["worker_contract"]["fixed_budget"] == 32
    with pytest.raises(ValueError, match="exclusive"):
        watchdog.v3_7_execution_dry_run(
            h4_input,
            tmp_path / "fixed-budget-conflict",
            source_sha="a" * 40,
            candidate_b_only=True,
            v5_h4_fixed_budget_bottom_only=True,
            v5_h4_fixed_budget_exact_spool_root=spool,
            selected_mode_packet_manifest=manifest,
            selected_mode_packet_identity=identity,
            selected_mode_packet_manifest_sha256="b" * 64,
        )


def test_v5_fixed_budget_spool_unwraps_packet_identity_and_manifest(tmp_path) -> None:
    root = tmp_path / "numerical_output" / "v5_blr_reference_spool" / "rank0000"
    root.mkdir(parents=True)
    packet = {"model_id": "task039_h4", "requested_modes": 480}
    wrapper = {
        "source_sha": "s" * 40,
        "packet_identity": packet,
        "manifest_sha256": "m" * 64,
    }
    for label, _kind, _seed in orchestration.V5_H4_BLR_RHS_SPECS:
        for role in ("rhs", "exact_output"):
            (root / f"bottom_{label}_{role}.json").write_text(
                json.dumps(
                    {
                        "side": "bottom",
                        "label": label,
                        "role": role,
                        "source_identity": {"packet_identity": wrapper},
                    }
                ),
                encoding="utf-8",
            )
    records = orchestration._load_v5_fixed_budget_spool_records(
        tmp_path / "numerical_output",
        MPI.COMM_SELF,
        packet_identity=packet,
        manifest_sha256="m" * 64,
    )
    assert list(records) == [spec[0] for spec in orchestration.V5_H4_BLR_RHS_SPECS]
    broken = root / "bottom_external_dtn_coupling_rhs.json"
    broken.write_text(
        broken.read_text(encoding="utf-8").replace("m" * 64, "x" * 64),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        orchestration._load_v5_fixed_budget_spool_records(
            tmp_path / "numerical_output",
            MPI.COMM_SELF,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )


def test_v5_fixed_budget_spool_remaps_source_shards_to_target_range(tmp_path) -> None:
    class FakeVec:
        def __init__(self, start, end, values=None):
            self.start = start
            self.end = end
            self.values = (
                np.zeros(end - start, dtype=np.complex128) if values is None else values
            )

        def getOwnershipRange(self):
            return self.start, self.end

        def getSize(self):
            return 7

        def duplicate(self):
            return FakeVec(self.start, self.end)

        def getArray(self):
            return self.values

        def assemble(self):
            return None

        def destroy(self):
            return None

    values = np.arange(7, dtype=np.complex128) + 1j
    shards = []
    for start, end in ((0, 3), (3, 7)):
        path = tmp_path / f"source-{start}.npy"
        np.save(path, values[start:end])
        shards.append(
            {
                "array_path": str(path),
                "ownership_range": [start, end],
                "local_size": end - start,
                "global_size": 7,
                "dtype": "complex128",
            }
        )
    loaded = orchestration._load_v5_blr_reference_spool_remapped(
        {"shards": shards}, FakeVec(2, 7)
    )
    np.testing.assert_array_equal(loaded.getArray(), values[2:])


def _write_tiny_v5_spool_catalog(
    tmp_path,
    *,
    ownership=(0, 4),
    partitions=None,
    global_size=None,
    packet=None,
    dtype="complex128",
    omit_seed=False,
):
    packet = {"model_id": "tiny-h4", "mode_count": 480} if packet is None else packet
    partitions = [ownership] if partitions is None else partitions
    global_size = partitions[-1][1] if global_size is None else global_size
    for source_rank, (start, end) in enumerate(partitions):
        root = tmp_path / "v5_blr_reference_spool" / f"rank{source_rank:04d}"
        root.mkdir(parents=True)
        for label, kind, seed in orchestration.V5_H4_BLR_RHS_SPECS:
            probe = {
                "label": label,
                "source": kind,
                "degenerate_uninformative": label == "physical_side_rhs",
                "identity": {
                    "dtype": "complex128",
                    "global_sha256": "g" * 64,
                    "global_size": global_size,
                    "source": kind,
                    "source_norm": 1.0,
                    "local_sha256": hashlib.sha256(
                        f"{source_rank}:{start}:{end}".encode()
                    ).hexdigest(),
                    "ownership_range": [start, end],
                },
            }
            if not omit_seed:
                probe["seed"] = seed
            for role in ("rhs", "exact_output"):
                values = np.arange(start, end, dtype=np.complex128)
                if dtype != "complex128":
                    values = values.real.astype(np.float64)
                array_path = root / f"bottom_{label}_{role}.npy"
                np.save(array_path, values)
                source_identity = {
                    "packet_identity": {
                        "packet_identity": packet,
                        "manifest_sha256": "m" * 64,
                        "source_sha": "s" * 40,
                    },
                    "probe_metadata": probe if role == "rhs" else {"label": label},
                }
                record = {
                    "side": "bottom",
                    "label": label,
                    "role": role,
                    "source_identity": source_identity,
                    "ownership_range": [start, end],
                    "global_size": global_size,
                    "local_size": end - start,
                    "dtype": dtype,
                    "array_path": str(array_path),
                    "array_sha256": hashlib.sha256(values.tobytes()).hexdigest(),
                }
                metadata = dict(record)
                record["metadata_payload_sha256_excluding_self"] = hashlib.sha256(
                    json.dumps(
                        metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    ).encode()
                ).hexdigest()
                (root / f"bottom_{label}_{role}.json").write_text(
                    json.dumps(record, sort_keys=True, separators=(",", ":")),
                    encoding="utf-8",
                )
    return tmp_path / "v5_blr_reference_spool"


def test_v5_fixed_budget_spool_catalog_rejects_gap_dtype_and_identity(tmp_path):
    packet = {"model_id": "tiny-h4", "mode_count": 480}
    gap_root = _write_tiny_v5_spool_catalog(
        tmp_path / "gap", ownership=(0, 3), global_size=4, packet=packet
    )
    with pytest.raises(ValueError, match="cover global size"):
        orchestration._load_v5_fixed_budget_spool_shards(
            gap_root.parent,
            MPI.COMM_SELF,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )
    dtype_root = _write_tiny_v5_spool_catalog(
        tmp_path / "dtype", packet=packet, dtype="float64"
    )
    with pytest.raises(ValueError, match="shape mismatch"):
        orchestration._load_v5_fixed_budget_spool_shards(
            dtype_root.parent,
            MPI.COMM_SELF,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )
    identity_root = _write_tiny_v5_spool_catalog(
        tmp_path / "identity", packet={"model_id": "other", "mode_count": 480}
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        orchestration._load_v5_fixed_budget_spool_shards(
            identity_root.parent,
            MPI.COMM_SELF,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )
    missing_seed_root = _write_tiny_v5_spool_catalog(
        tmp_path / "missing-seed", packet=packet, omit_seed=True
    )
    with pytest.raises(ValueError, match="seed metadata mismatch"):
        orchestration._load_v5_fixed_budget_spool_shards(
            missing_seed_root.parent,
            MPI.COMM_SELF,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )


@pytest.mark.parametrize(
    ("mutation", "error_match"),
    [
        ("overlap", "gap or overlap"),
        ("global_size", "ownership coverage mismatch"),
        ("array_sha", "array hash/shape mismatch"),
        ("metadata_self_hash", "metadata hash mismatch"),
    ],
)
def test_v5_fixed_budget_spool_catalog_mutations_fail_closed(
    tmp_path, mutation, error_match
):
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run catalog mutation smoke with MPI2")
    packet = {"model_id": "tiny-h4", "mode_count": 480}
    root = tmp_path / mutation
    if comm.rank == 0:
        _write_tiny_v5_spool_catalog(root, partitions=[(0, 4), (4, 8)], packet=packet)
        rank = 1 if mutation in {"overlap", "global_size", "metadata_self_hash"} else 0
        metadata_path = (
            root
            / "v5_blr_reference_spool"
            / f"rank{rank:04d}"
            / "bottom_external_dtn_coupling_rhs.json"
        )
        record = json.loads(metadata_path.read_text(encoding="utf-8"))
        refresh_metadata_hash = mutation != "metadata_self_hash"
        if mutation == "overlap":
            record["ownership_range"] = [3, 8]
            record["local_size"] = 5
        elif mutation == "global_size":
            record["global_size"] = 9
        elif mutation == "array_sha":
            record["array_sha256"] = "0" * 64
        else:
            record["global_size"] = 9
        if refresh_metadata_hash:
            record.pop("metadata_payload_sha256_excluding_self", None)
            record["metadata_payload_sha256_excluding_self"] = hashlib.sha256(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest()
        metadata_path.write_text(
            json.dumps(record, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
    root = Path(comm.bcast(str(root), root=0))
    with pytest.raises(ValueError, match=error_match):
        orchestration._load_v5_fixed_budget_spool_shards(
            root,
            comm,
            packet_identity=packet,
            manifest_sha256="m" * 64,
        )


def test_v5_fixed_budget_spool_catalog_mpi_remaps_target_ownership(tmp_path):
    comm = MPI.COMM_WORLD
    if comm.size not in (2, 4):
        pytest.skip("run this tiny ownership smoke with MPI2 or MPI4")
    packet = {"model_id": "tiny-h4", "mode_count": 480}
    partitions = (
        [(0, 4), (4, 8)] if comm.size == 2 else [(0, 2), (2, 4), (4, 6), (6, 8)]
    )
    root = tmp_path / "mpi-catalog"
    if comm.rank == 0:
        _write_tiny_v5_spool_catalog(root, partitions=partitions, packet=packet)
    root = Path(comm.bcast(str(root), root=0))
    records = orchestration._load_v5_fixed_budget_spool_shards(
        root,
        comm,
        packet_identity=packet,
        manifest_sha256="m" * 64,
    )
    assert records["external_dtn_coupling"]["exact_output"]["probe_metadata"] == {
        "label": "external_dtn_coupling"
    }
    targets = [(0, 3), (3, 8)] if comm.size == 2 else [(0, 1), (1, 3), (3, 6), (6, 8)]

    class TargetVec:
        def __init__(self, start, end):
            self.start = start
            self.end = end
            self.values = np.zeros(end - start, dtype=np.complex128)

        def getOwnershipRange(self):
            return self.start, self.end

        def getSize(self):
            return 8

        def duplicate(self):
            return TargetVec(self.start, self.end)

        def getArray(self):
            return self.values

        def assemble(self):
            return None

        def destroy(self):
            return None

    start, end = targets[comm.rank]
    loaded = orchestration._load_v5_blr_reference_spool_remapped(
        records["external_dtn_coupling"]["rhs"], TargetVec(start, end)
    )
    local_pass = np.array_equal(
        loaded.getArray(), np.arange(start, end, dtype=np.complex128)
    )
    assert comm.allreduce(local_pass, op=MPI.LAND)


def test_v5_fixed_budget_diagnostic_uses_side_builder_and_releases_side_system(
    tmp_path, monkeypatch
):
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    identity = {
        "source_sha": "s" * 40,
        "physical_sha256": "p" * 64,
        "model_id": "tiny-h4",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "rank_count": 1,
                "consumer_qep_required": False,
                "qep_workspace_persisted": False,
                "identity": identity,
            }
        ),
        encoding="utf-8",
    )
    collective_calls = []

    class SideSystem:
        _destroyed = False

        def destroy(self):
            self._destroyed = True

    side_system = SideSystem()

    def side_builder(**kwargs):
        assert kwargs["profile"].h_nm == 4.0
        return SimpleNamespace(bottom=side_system, side_only=True)

    monkeypatch.setattr(
        orchestration,
        "run_v5_h4_fixed_budget_bottom_component",
        lambda *_args, **_kwargs: {
            "status": "component_completed",
            "telemetry": {"memory_object_ledger": {}},
        },
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: (
            collective_calls.append(True) or {"collective_call_completed": True}
        ),
    )
    run_directory = tmp_path / "run"
    orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: pytest.fail("generic setup was called"),
        side_system_builder=side_builder,
        v5_h4_fixed_budget_bottom_only=True,
        v5_h4_fixed_budget_exact_spool_root=tmp_path,
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=hashlib.sha256(
            manifest.read_bytes()
        ).hexdigest(),
    )
    assert side_system._destroyed is True
    assert collective_calls == [True]
    marker_rows = [
        json.loads(line)
        for line in (
            run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    cleanup_rows = [
        row
        for row in marker_rows
        if row["marker"] == "v5_fixed_budget_bottom_side_setup_cleanup"
    ]
    assert len(cleanup_rows) == 1
    assert cleanup_rows[0]["detail"]["bottom_destroyed"] is True
    assert cleanup_rows[0]["detail"]["collective_cleanup_completed"] is True


def test_v6_port_modal_worker_route_stops_before_generic_setup(
    tmp_path, monkeypatch
) -> None:
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    identity = {
        "source_sha": "s" * 40,
        "physical_sha256": "p" * 64,
        "model_id": "tiny-h4",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "rank_count": 1,
                "consumer_qep_required": False,
                "qep_workspace_persisted": False,
                "identity": identity,
            }
        ),
        encoding="utf-8",
    )
    side_system = SimpleNamespace(destroyed=False)

    def destroy_side_system():
        side_system.destroyed = True

    side_system.destroy = destroy_side_system

    def side_builder(**kwargs):
        assert kwargs["profile"].h_nm == 4.0
        return SimpleNamespace(bottom=side_system, side_only=True)

    monkeypatch.setattr(
        orchestration,
        "run_v6_h4_port_modal_bottom_component",
        lambda *_args, **_kwargs: {
            "status": "component_completed",
            "telemetry": {"memory_object_ledger": {}},
            "top": "not_run",
        },
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        tmp_path / "run",
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: pytest.fail("generic setup was called"),
        side_system_builder=side_builder,
        v6_h4_port_modal_bottom_only=True,
        v6_h4_port_modal_exact_spool_root=tmp_path / "spool",
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=hashlib.sha256(
            manifest.read_bytes()
        ).hexdigest(),
    )
    assert result["status"] == "component_completed"
    assert result["top"] == "not_run"
    assert side_system.destroyed is True
    marker_rows = [
        json.loads(line)
        for line in (
            tmp_path / "run" / "numerical_output" / "memory_stage_markers.raw.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    assert any(
        row["marker"] == "v6_port_modal_bottom_side_setup_cleanup"
        for row in marker_rows
    )


def test_v7_streamed_worker_route_finalizes_side_setup_once(
    tmp_path, monkeypatch
) -> None:
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    identity = {
        "source_sha": "s" * 40,
        "physical_sha256": "p" * 64,
        "model_id": "tiny-h4",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "rank_count": 1,
                "consumer_qep_required": False,
                "qep_workspace_persisted": False,
                "identity": identity,
            }
        ),
        encoding="utf-8",
    )
    destroy_calls = []
    collective_calls = []

    class SideSystem:
        _destroyed = False

        def destroy(self):
            destroy_calls.append(True)
            self._destroyed = True

    side_system = SideSystem()

    def side_builder(**kwargs):
        assert kwargs["profile"].h_nm == 4.0
        return SimpleNamespace(bottom=side_system, side_only=True)

    monkeypatch.setattr(
        orchestration,
        "run_v7_h4_streamed_bottom_basis_producer",
        lambda *_args, **_kwargs: {
            "status": "producer_completed",
            "telemetry": {
                "memory_object_ledger": {
                    "path": "numerical_output/memory_object_ledger.json"
                }
            },
        },
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: (
            collective_calls.append(True) or {"collective_call_completed": True}
        ),
    )
    run_directory = tmp_path / "run"
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: pytest.fail("generic setup was called"),
        side_system_builder=side_builder,
        v7_h4_streamed_bottom_producer=True,
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=hashlib.sha256(
            manifest.read_bytes()
        ).hexdigest(),
    )
    assert result["status"] == "producer_completed"
    assert destroy_calls == [True]
    assert collective_calls == [True]
    assert result["telemetry"]["memory_object_ledger"]["sha256"]
    marker_rows = [
        json.loads(line)
        for line in (
            run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
        )
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    inventory_rows = [row for row in marker_rows if row["marker"] == "inventory_ready"]
    assert len(inventory_rows) == 1
    assert inventory_rows[0]["detail"]["direct_reference_payload_loaded"] is False
    assert marker_rows[-1]["marker"] == (
        "v7_streamed_bottom_producer_side_setup_cleanup"
    )
    assert marker_rows[-1]["detail"]["bottom_destroyed"] is True
    assert marker_rows[-1]["detail"]["collective_cleanup_completed"] is True
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "completed"
    assert ledger["objects"]["setup"]["destroyed"] is True


def test_v8_layer_block_component_releases_each_side_before_next(
    tmp_path, monkeypatch
) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("run this fake-side lifecycle contract in serial")

    def make_matrix():
        matrix = PETSc.Mat().createAIJ(size=(6, 6), nnz=3, comm=PETSc.COMM_SELF)
        for row in range(6):
            matrix.setValue(row, row, PETSc.ScalarType(2.0 + 0.1j))
            if row:
                matrix.setValue(row, row - 1, PETSc.ScalarType(0.2 - 0.1j))
            if row < 5:
                matrix.setValue(row, row + 1, PETSc.ScalarType(-0.3 + 0.2j))
        matrix.assemble()
        return matrix

    class Resource:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    systems = []
    resources = []
    timeline = []

    class System:
        def __init__(self):
            self.A = make_matrix()
            self.destroyed = False

        def destroy(self):
            self.A.destroy()
            self.destroyed = True
            timeline.append("system_destroy")

    def side_builder(**_kwargs):
        system = System()
        systems.append(system)
        return system

    def explicit_components(_system):
        components = SimpleNamespace(
            H=Resource(), C=Resource(), F=make_matrix(), D=Resource()
        )
        resources.append((components.H, components.C, components.D))
        return components

    monkeypatch.setattr(
        orchestration, "_build_research_explicit_side_components", explicit_components
    )
    monkeypatch.setattr(
        orchestration,
        "build_real_layer_labels",
        lambda _matrix, _system: (
            np.arange(6, dtype=np.int32),
            {"z_layer_boundaries": list(range(7))},
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: (
            timeline.append("collective_cleanup") or {"collective_call_completed": True}
        ),
    )
    events = []

    def record_event(marker, detail):
        if marker.endswith("_destroy"):
            assert systems[-1].destroyed is True
            assert detail["system_destroy_called"] is True
            assert timeline[-2:] == ["system_destroy", "collective_cleanup"]
        events.append((marker, detail))

    result = orchestration.run_v8_h4_layer_block_reconstruction_component(
        SimpleNamespace(),
        profile=SimpleNamespace(bottom_interface_nm=0.0, top_interface_nm=1.0),
        comm=MPI.COMM_SELF,
        marker_callback=record_event,
        side_system_builder=side_builder,
    )

    assert result["status"] == "component_completed"
    assert result["gate"]["overall_pass"] is True
    assert result["gate"]["sides_present_exact"] is True
    assert [marker for marker, _detail in events] == [
        "v8_layer_block_bottom_construction_begin",
        "v8_layer_block_bottom_operator_ready",
        "v8_layer_block_bottom_destroy",
        "v8_layer_block_top_construction_begin",
        "v8_layer_block_top_operator_ready",
        "v8_layer_block_top_destroy",
    ]
    assert all(system.destroyed for system in systems)
    assert all(
        resource.destroyed
        for resource_group in resources
        for resource in resource_group
    )
    for system in systems:
        system.A = None


def test_v8_layer_block_worker_route_finalizes_without_generic_setup(
    tmp_path, monkeypatch
) -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("run this fake-side worker contract in serial")

    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()

    def make_matrix():
        matrix = PETSc.Mat().createAIJ(size=(6, 6), nnz=3, comm=PETSc.COMM_SELF)
        for row in range(6):
            matrix.setValue(row, row, PETSc.ScalarType(2.0 + 0.1j))
            if row:
                matrix.setValue(row, row - 1, PETSc.ScalarType(0.2 - 0.1j))
            if row < 5:
                matrix.setValue(row, row + 1, PETSc.ScalarType(-0.3 + 0.2j))
        matrix.assemble()
        return matrix

    class Resource:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    class System:
        def __init__(self):
            self.A = make_matrix()
            self.destroyed = False

        def destroy(self):
            self.A.destroy()
            self.destroyed = True

    systems = []
    resources = []

    def side_builder(**_kwargs):
        system = System()
        systems.append(system)
        return system

    def explicit_components(_system):
        components = SimpleNamespace(
            H=Resource(), C=Resource(), F=make_matrix(), D=Resource()
        )
        resources.append((components.H, components.C, components.D))
        return components

    monkeypatch.setattr(
        orchestration,
        "simulation_config_3d_from_normalized",
        lambda _payload: SimpleNamespace(),
    )
    monkeypatch.setattr(
        orchestration, "_build_research_explicit_side_components", explicit_components
    )
    monkeypatch.setattr(
        orchestration,
        "build_real_layer_labels",
        lambda _matrix, _system: (
            np.arange(6, dtype=np.int32),
            {"z_layer_boundaries": list(range(7))},
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )
    run_directory = tmp_path / "v8-worker-route"
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: pytest.fail("generic setup was called"),
        side_system_builder=side_builder,
        v8_h4_layer_block_reconstruction=True,
    )

    assert result["status"] == "component_completed"
    assert result["gate"]["overall_pass"] is True
    assert result["selected_mode_packet_opened"] is False
    assert result["holdout_opened"] is False
    assert result["exact_spool_opened"] is False
    assert result["qep_count"] == 0
    assert result["factor_inventory"]["exact_factor_count"] == 0
    assert result["factor_inventory"]["global_direct_factor_count"] == 0
    assert all(system.destroyed for system in systems)
    assert all(resource.destroyed for group in resources for resource in group)
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "completed"


def test_v8_layer_block_plan_is_explicit_h4_and_packet_free(tmp_path) -> None:
    h4_input = Path(
        "input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat"
    )
    plan = orchestration.v3_7_execution_dry_run(
        h4_input,
        tmp_path / "v8-plan",
        source_sha="c" * 40,
        v8_h4_layer_block_reconstruction=True,
    )
    route_flags = {
        "--v5-h4-setup-only",
        "--v5-h4-blr-side-component",
        "--v5-h4-fixed-budget-bottom-component",
        "--v6-h4-post-compaction-setup-only",
        "--v6-h4-port-modal-bottom-component",
        "--v7-h4-exact-side-limit-setup-only",
        "--v7-h4-exact-side-full-formal",
        "--v7-h4-streamed-bottom-producer",
        "--v7-h4-streamed-bottom-consumer",
        "--v8-h4-layer-block-reconstruction",
    }
    assert [flag for flag in plan["argv"] if flag in route_flags] == [
        "--v8-h4-layer-block-reconstruction"
    ]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        V3_7_ABSOLUTE_HARD_BYTES
    )
    assert plan["watchdog"]["profile"] == "v8_h4_layer_block_reconstruction"
    assert plan["worker_contract"]["method"] == orchestration.V8_H4_LAYER_BLOCK_METHOD
    assert plan["worker_contract"]["profile_id"] == (
        orchestration.V8_H4_LAYER_BLOCK_PROFILE_ID
    )
    assert plan["worker_contract"]["exact_spool_root"] is None
    assert "--selected-mode-packet-manifest" not in plan["argv"]
    assert not (tmp_path / "v8-plan").exists()

    with pytest.raises(ValueError, match="exclusive"):
        orchestration.v3_7_execution_dry_run(
            h4_input,
            tmp_path / "v8-conflict",
            source_sha="c" * 40,
            v8_h4_layer_block_reconstruction=True,
            v6_h4_post_compaction_setup_only=True,
        )

    ordinary = orchestration.v3_7_execution_dry_run(
        Path("input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat"),
        tmp_path / "ordinary-plan",
        source_sha="c" * 40,
    )
    assert "--v8-h4-layer-block-reconstruction" not in ordinary["argv"]
    assert ordinary["watchdog"]["profile"] == "v3_7_default"


def test_v7_streamed_consumer_route_preserves_selected_and_basis_packets(
    tmp_path, monkeypatch
) -> None:
    payload = load_and_resolve(
        Path("input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat")
    ).as_jsonable()
    identity = {
        "source_sha": "s" * 40,
        "physical_sha256": "p" * 64,
        "model_id": "tiny-h4",
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "rank_count": 1,
                "consumer_qep_required": False,
                "qep_workspace_persisted": False,
                "identity": identity,
            }
        ),
        encoding="utf-8",
    )
    basis_manifest = tmp_path / "basis-manifest.json"
    side_system = SimpleNamespace(destroyed=False)
    side_system.destroy = lambda: setattr(side_system, "destroyed", True)

    def side_builder(**_kwargs):
        return SimpleNamespace(bottom=side_system, side_only=True)

    basis_packet = {
        "basis_manifest": str(basis_manifest),
        "basis_manifest_sha256": "b" * 64,
        "basis_packet_schema": "task039.v7.streamed.owner-row-basis.v1",
        "basis_mmap_retained_until_cleanup": True,
        "training_holdout_disjoint": True,
        "holdout_exact_spool_opened_after_basis_load": True,
        "consumer_qep_calls": 0,
    }
    consumer_source = inspect.getsource(
        orchestration.run_v7_h4_streamed_bottom_petrov_consumer
    )
    assert "target_ownership_ranges = comm.allgather" in consumer_source
    assert '"target_ownership_ranges": target_ownership_ranges' in consumer_source
    assert "global_size=target_global_rows" in consumer_source
    setup_begin = consumer_source.split("    try:", 1)[0]
    monkeypatch.setattr(
        orchestration,
        "run_v7_h4_streamed_bottom_petrov_consumer",
        lambda *_args, **_kwargs: {
            "status": "consumer_completed",
            "packet": basis_packet,
            "telemetry": {"memory_object_ledger": {}},
        },
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        tmp_path / "run",
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda **_kwargs: pytest.fail("generic setup was called"),
        side_system_builder=side_builder,
        v7_h4_streamed_bottom_consumer=True,
        v7_h4_streamed_bottom_consumer_basis_manifest=basis_manifest,
        v7_h4_streamed_bottom_consumer_basis_manifest_sha256="b" * 64,
        v7_h4_streamed_bottom_consumer_exact_spool_root=tmp_path / "spool",
        selected_mode_packet_manifest=manifest,
        selected_mode_packet_identity=identity,
        selected_mode_packet_manifest_sha256=hashlib.sha256(
            manifest.read_bytes()
        ).hexdigest(),
    )
    assert result["selected_mode_packet"]["manifest"] == str(manifest)
    assert result["selected_mode_packet"]["identity"] == identity
    assert result["packet"] == basis_packet
    for field in (
        "basis_packet_schema",
        "basis_mmap_retained_until_cleanup",
        "training_holdout_disjoint",
        "holdout_exact_spool_opened_after_basis_load",
        "consumer_qep_calls",
    ):
        assert result["packet"][field] == basis_packet[field]
    assert side_system.destroyed is True
    assert '"required_nested_ksp_count": 0' in setup_begin
    assert '"required_exact_factor_count": 0' in setup_begin
    assert '"required_global_direct_factor_count": 0' in setup_begin
    assert '"nested_ksp_count": 0' not in setup_begin
    assert '"exact_factor_count": 0' not in setup_begin
    assert '"global_direct_factor_count": 0' not in setup_begin


def test_v5_h4_fixed_budget_route_is_bottom_only_and_cleans_factors(
    tmp_path, monkeypatch
) -> None:
    class FakeVec:
        def destroy(self):
            return None

    class FakeOperator:
        def createVecLeft(self):
            return FakeVec()

    class FakeBase:
        diagnostics = {
            "factor_count": 1,
            "ksp_created": False,
            "lifecycle": {"factor_count_after_destroy": 0},
        }

        def destroy(self):
            return None

    class FakeFixed:
        def __init__(self):
            self.operator = FakeOperator()
            self.diagnostics = {
                "base_factor_count": 1,
                "local_direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "residual_correction_steps": 1,
            }

        def destroy(self):
            return None

    class FakeKrylov:
        def __init__(self):
            self.operator = FakeOperator()
            self.diagnostics = {
                "requested_budget": 32,
                "direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
            }

        def destroy(self):
            return None

    class FakeComponents:
        def __init__(self):
            self.F = object()
            self.C = object()
            self.D = object()
            self.H = object()
            self._destroyed = False

        def destroy(self):
            self._destroyed = True

    labels = [spec[0] for spec in orchestration.V5_H4_BLR_RHS_SPECS]
    spool = {}
    for label, kind, seed in orchestration.V5_H4_BLR_RHS_SPECS:
        metadata = {
            "label": label,
            "kind": kind,
            "seed": seed,
            "degenerate_uninformative": label == "physical_side_rhs",
        }
        shard = {
            "source_identity": {"probe_metadata": metadata},
        }
        spool[label] = {
            "rhs": {"shards": [shard], "probe_metadata": metadata},
            "exact_output": {"shards": [shard], "probe_metadata": metadata},
        }
    markers = []
    component_factory_calls = []
    explicit_builder_calls = []
    monkeypatch.setattr(
        orchestration,
        "_load_v5_fixed_budget_spool_shards",
        lambda *_args, **_kwargs: spool,
    )
    monkeypatch.setattr(
        orchestration,
        "create_hybrid_local_dtn_action_components",
        lambda system: component_factory_calls.append(system) or FakeComponents(),
    )
    monkeypatch.setattr(
        orchestration,
        "_build_research_explicit_side_components",
        lambda system: (
            explicit_builder_calls.append(system)
            or pytest.fail("fixed-budget route materialized explicit side components")
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "build_hybrid_whole_endcap_fixed_smoother_action",
        lambda _system, ilu_levels=0: FakeBase(),
    )
    monkeypatch.setattr(
        orchestration,
        "HybridLocalDtnWoodburyFixedAction",
        lambda *_args, **_kwargs: FakeFixed(),
    )
    monkeypatch.setattr(
        orchestration,
        "HybridLocalDtnWoodburyFixedBudgetKrylovAction",
        lambda *_args, **_kwargs: FakeKrylov(),
    )
    monkeypatch.setattr(
        orchestration,
        "_load_v5_blr_reference_spool_remapped",
        lambda _record, _template: FakeVec(),
    )
    monkeypatch.setattr(
        orchestration,
        "_v5_blr_probe",
        lambda _action, _system, _rhs, metadata, *_args, **_kwargs: (
            {
                **metadata,
                "finite": True,
                "true_residual_relative": 1.0e-4,
                "repeat_relative_error": 1.0e-12,
                "linearity_relative_error": (
                    1.0e-12 if metadata["label"] == "fixed_random_repeat_0" else None
                ),
                "reference_relative_error": 1.0e-12,
                "output": {"global_sha256": metadata["label"]},
            },
            None,
        ),
    )
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": True},
    )
    setup = SimpleNamespace(
        bottom=SimpleNamespace(
            A=FakeOperator(),
            inventory={"global_F_materialized": False},
        )
    )

    def run_component():
        return orchestration.run_v5_h4_fixed_budget_bottom_component(
            setup,
            comm=MPI.COMM_SELF,
            marker_callback=lambda marker, _detail: markers.append(marker),
            exact_spool_root=tmp_path,
            packet_identity={"model_id": "h4"},
            packet_manifest_sha256="b" * 64,
        )

    result = run_component()
    assert result["fixed_budget"] == 32
    assert result["sides"]["top"] == "not_run_by_bottom_first_contract"
    assert result["gates"]["numerical_pass"] is True
    assert result["gates"]["resource_pass"] is None
    assert markers.index(
        "v5_fixed_budget_candidate_bottom_setup_begin"
    ) < markers.index("v5_fixed_budget_candidate_bottom_setup_end")
    assert markers.index("v5_fixed_budget_candidate_bottom_setup_end") < markers.index(
        "v5_fixed_budget_candidate_bottom_online_begin"
    )
    assert markers.index(
        "v5_fixed_budget_candidate_bottom_online_begin"
    ) < markers.index("v5_fixed_budget_candidate_bottom_online_end")
    assert markers[-1] == "v5_fixed_budget_candidate_bottom_cleanup"
    assert (
        result["sides"]["bottom"]["candidate"]["cleanup"]["factor_count_after_cleanup"][
            "base"
        ]
        == 0
    )
    components = result["sides"]["bottom"]["candidate"]["cleanup"]["components"]
    assert components["carrier_destroyed"] is True
    assert components["scratch_released"] is True
    assert components["borrowed_matrices_destroyed"] is False
    assert components["borrowed_matrices_retained_by_setup"] == {
        "F": True,
        "C": True,
        "D": True,
        "H": True,
    }
    assert (
        result["sides"]["bottom"]["candidate"]["setup"]["inventory"][
            "global_F_materialized"
        ]
        is False
    )
    assert (
        result["sides"]["bottom"]["candidate"]["setup"]["inventory"][
            "no_new_explicit_component_matrix"
        ]
        is True
    )
    assert result["sides"]["bottom"]["candidate"]["setup"]["base_factor_count"] == 1
    assert component_factory_calls == [setup.bottom]
    assert explicit_builder_calls == []
    assert result["mandatory_labels"] == [
        label for label in labels if label != "physical_side_rhs"
    ]
    assert result["degenerate_labels"] == ["physical_side_rhs"]
    assert result["gates"]["advancement_pass"] is None
    assert result["packet_identity"] == {"model_id": "h4"}
    assert result["outer"] == "not_run"
    assert result["recovery"] == "not_run"

    spool["physical_side_rhs"]["rhs"]["probe_metadata"]["degenerate_uninformative"] = (
        False
    )
    markers.clear()
    result_non_degenerate = run_component()
    assert "physical_side_rhs" in result_non_degenerate["mandatory_labels"]
    assert result_non_degenerate["degenerate_labels"] == []
    assert len(result_non_degenerate["mandatory_labels"]) == 6
    assert len(component_factory_calls) == 2


def test_v3_8_candidate_e_dry_run_and_route_exclusivity(tmp_path) -> None:
    plan = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-e",
        source_sha="a" * 40,
        candidate_e_side_only=True,
    )
    assert "--candidate-e-side-only" in plan["argv"]
    assert plan["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_e_side_only"
    )
    with pytest.raises(ValueError, match="QEP-only"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-e-conflict",
            source_sha="a" * 40,
            candidate_b_only=True,
            candidate_e_side_only=True,
        )


@pytest.mark.parametrize(
    ("median", "worst", "complete", "expected"),
    (
        (0.1, 0.3, True, True),
        (0.100001, 0.3, True, False),
        (0.1, 0.300001, True, False),
        (0.1, 0.3, False, False),
    ),
)
def test_v3_8_candidate_e_side_gate(median, worst, complete, expected) -> None:
    assert (
        orchestration._candidate_e_side_gate(
            {
                "pass": complete,
                "rho_summary": {"median": median, "worst": worst},
            }
        )
        is expected
    )


def test_v3_8_candidate_e_branch_skips_global_stages_and_closes_ledger(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "candidate-e"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = (
        run_directory / "numerical_output" / "v3_8_candidate_e_side_checkpoint.json"
    )

    def campaign(*_args, **kwargs):
        called.append("candidate_e")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_e_side_fixed_setup_end", {})
        marker_callback("candidate_e_correction_actions_ready", {"live": 2})
        marker_callback("candidate_e_side_fixed_cleanup_end", {})
        return {
            "status": "measured",
            "pass": False,
            "training": {
                side: {"seed_ids": list(orchestration.V3_8_CANDIDATE_E_TRAINING_SEEDS)}
                for side in ("bottom", "top")
            },
            "side_reports": {
                side: {"rho_summary": {"median": 0.2, "worst": 0.4}}
                for side in ("bottom", "top")
            },
            "factor_inventory": {
                "per_side": {
                    side: {
                        "base_factor_count": 1,
                        "local_direct_factor_count": 0,
                        "global_hybrid_direct_factor_count": 0,
                    }
                    for side in ("bottom", "top")
                }
            },
        }, checkpoint

    def forbidden(*_args, **_kwargs):
        raise AssertionError("identity/oracle/recovery path was entered")

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_e_side_campaign", campaign)
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {},
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_e_side_only=True,
    )
    assert called == ["candidate_e", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-e-side-only.v1"
    assert result["direct_reference_payload_loaded"] is True
    assert result["candidate_e"]["training"]["bottom"]["seed_ids"] == list(
        orchestration.V3_8_CANDIDATE_E_TRAINING_SEEDS
    )
    for side in ("bottom", "top"):
        inventory = result["candidate_e"]["factor_inventory"]["per_side"][side]
        assert inventory["local_direct_factor_count"] == 0
        assert inventory["global_hybrid_direct_factor_count"] == 0
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


@pytest.mark.parametrize(
    ("pass_budget", "expected_budgets"),
    ((8, [8]), (16, [8, 16]), (None, [8, 16, 32])),
)
def test_v3_8_candidate_b_budget_order_and_single_wrapper(
    monkeypatch, pass_budget, expected_budgets
) -> None:
    created: list[int] = []
    destroyed: list[int] = []

    class Fixed:
        diagnostics = {
            "base_factor_count": 1,
            "local_direct_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
        }

    class Action:
        def __init__(self, _operator, fixed, *, budget):
            self.budget = budget
            self.right_preconditioner = fixed
            created.append(budget)

        @property
        def diagnostics(self):
            return {
                "direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "right_preconditioner_identity": "fake_fixed",
            }

        def destroy(self):
            destroyed.append(self.budget)

    def probe(_system, action, budget, _vectors, _metadata):
        passed = pass_budget is not None and budget >= pass_budget
        return {"rho_summary": {"candidate_B_pass": passed}}

    monkeypatch.setattr(
        orchestration, "HybridLocalDtnWoodburyFixedBudgetKrylovAction", Action
    )
    monkeypatch.setattr(orchestration, "_candidate_b_side_probe", probe)
    systems = {
        "bottom": SimpleNamespace(A=object()),
        "top": SimpleNamespace(A=object()),
    }
    fixed = {"bottom": Fixed(), "top": Fixed()}
    events: list[str] = []
    report = orchestration.run_v3_8_candidate_b_budget_sequence(
        systems,
        fixed,
        {"bottom": {}, "top": {}},
        {"bottom": {}, "top": {}},
        marker_callback=lambda marker, _detail: events.append(marker),
    )
    assert report["budgets_run"] == expected_budgets
    assert created == [budget for budget in expected_budgets for _ in (0, 1)]
    assert destroyed == created
    assert report["selected_budget"] == pass_budget
    assert report["factor_inventory"]["per_budget"]
    assert report["factor_inventory"]["simultaneous_total_base_factor_count"] == 2
    assert report["factor_inventory"]["simultaneous_total_direct_factor_count"] == 0
    assert (
        report["factor_inventory"][
            "simultaneous_total_global_hybrid_direct_factor_count"
        ]
        == 0
    )
    assert any(marker.endswith("_bottom_begin") for marker in events)
    assert any(marker.endswith("_top_end") for marker in events)


def test_v3_8_candidate_b_zero_probe_is_excluded_before_action() -> None:
    system, matrix, source = _tiny_side_system()

    class NoApply:
        diagnostics = {}

        def apply(self, *_args):
            raise AssertionError("zero Candidate-B probe must not call the action")

    try:
        report = orchestration._candidate_b_side_probe(
            system,
            NoApply(),
            8,
            {"physical_side_rhs": source},
            {},
        )
        item = report["vectors"]["physical_side_rhs"]
        assert item["status"] == "degenerate_uninformative"
        assert item["informative"] is False
        assert item["rho"] is None
        assert report["rho_summary"]["median"] is None
        assert report["rho_summary"]["worst"] is None
    finally:
        source.destroy()
        matrix.destroy()


def test_v3_8_candidate_b_plan_is_opt_in_and_checkpoint_is_hash_bound(tmp_path) -> None:
    default = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "default",
        source_sha="a" * 40,
        python_executable=sys.executable,
    )
    candidate = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_b_only=True,
    )
    assert "--candidate-b-only" not in default["argv"]
    assert "--candidate-b-only" in candidate["argv"]
    assert candidate["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_b_only"
    )
    candidate_c = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-c",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_c_only=True,
    )
    assert "--candidate-c-only" in candidate_c["argv"]
    assert candidate_c["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_c1_only"
    )
    candidate_d = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-d",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_d_only=True,
    )
    assert "--candidate-d-only" in candidate_d["argv"]
    assert candidate_d["worker_contract"]["method"] == (
        "USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D"
    )
    candidate_d_qualified = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-d-qualified",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_d_qualified=True,
    )
    assert "--candidate-d-qualified" in candidate_d_qualified["argv"]
    assert candidate_d_qualified["worker_contract"]["method"] == (
        "hybrid_iterative_exact_side_case_qualification"
    )
    with pytest.raises(ValueError, match="routes are exclusive"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-bc",
            source_sha="a" * 40,
            python_executable=sys.executable,
            candidate_b_only=True,
            candidate_c_only=True,
        )
    with pytest.raises(ValueError, match="routes are exclusive"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-bd",
            source_sha="a" * 40,
            python_executable=sys.executable,
            candidate_b_only=True,
            candidate_d_only=True,
        )
    with pytest.raises(ValueError, match="routes are exclusive"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-dd",
            source_sha="a" * 40,
            python_executable=sys.executable,
            candidate_d_only=True,
            candidate_d_qualified=True,
        )
    payload = load_v3_7_official_payload(INPUT)
    checkpoint_root = tmp_path / "checkpoint"
    checkpoint_root.mkdir()
    resolved_config = checkpoint_root / "resolved_config.json"
    resolved_config.write_text("{}\n", encoding="utf-8")
    producer = {
        "producer_source_sha": "p" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
        "verified_shard_count": 32,
        "inventory": {
            "source_sha": "p" * 40,
            "input_sha256": "i" * 64,
            "resolved_config_sha256": "r" * 64,
            "physical_model_sha256": "m" * 64,
            "verified_shard_count": 32,
            "payload": {"artifact": {"sha256": "d" * 64}},
        },
    }
    report = {
        "status": "measured",
        "pass": False,
        "selected_budget": None,
        "budgets_run": [8, 16, 32],
        "gate": {"median_limit": 0.1, "worst_limit": 0.3},
        "factor_inventory": {"per_budget": []},
        "budget_reports": [],
    }
    path = orchestration._write_v3_8_candidate_b_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        report=report,
        comm=MPI.COMM_SELF,
    )
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    assert (
        checkpoint["physical_identity"]["consumer_input_sha256"]
        == payload["provenance"]["input_sha256"]
    )
    assert checkpoint["physical_identity"]["producer_input_sha256"] == "i" * 64
    assert checkpoint["physical_identity"]["direct_payload_sha256"] == "d" * 64
    assert checkpoint["budgets_run"] == [8, 16, 32]

    failure = ValueError("array must not contain infs or NaNs")
    failure.candidate_b_progress = {"budget": 8, "side": "bottom"}
    failure.finite_audit = {
        "stage": "woodbury_apply_lu_solve",
        "vector": "lu_solve_input",
        "finite": False,
    }
    failure_path = orchestration._write_v3_8_candidate_b_failure_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        error=failure,
        comm=MPI.COMM_SELF,
    )
    failure_checkpoint = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure_checkpoint["status"] == "candidate_b_implementation_failure"
    assert failure_checkpoint["pass"] is None
    assert failure_checkpoint["budgets_run"] == []
    assert failure_checkpoint["failure"]["attempted_budget"] == 8
    assert failure_checkpoint["failure"]["attempted_side"] == "bottom"
    assert failure_checkpoint["failure"]["finite_audit"]["stage"] == (
        "woodbury_apply_lu_solve"
    )
    assert "rho" in failure_checkpoint["failure"]["unmeasured"]
    failure.candidate_c_progress = {"side": "bottom"}
    c_failure_path = orchestration._write_v3_8_candidate_c_failure_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        error=failure,
        comm=MPI.COMM_SELF,
    )
    c_failure_checkpoint = json.loads(c_failure_path.read_text(encoding="utf-8"))
    assert c_failure_checkpoint["status"] == "candidate_c1_implementation_failure"
    assert c_failure_checkpoint["pass"] is None
    assert c_failure_checkpoint["failure"]["attempted_side"] == "bottom"


def test_v3_8_candidate_c_side_gate_uses_frozen_limits() -> None:
    passed = {"pass": True, "rho_summary": {"median": 0.05, "worst": 0.2}}
    failed = {"pass": True, "rho_summary": {"median": 0.15, "worst": 0.2}}
    assert orchestration._candidate_c_side_gate(passed) is True
    assert orchestration._candidate_c_side_gate(failed) is False


def test_v3_8_candidate_d_releases_side_components_before_recovery(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    events: list[str] = []

    class Components:
        def __init__(self):
            self.bottom = object()
            self.top = object()
            self._destroyed = False

        @property
        def destroyed(self):
            return self._destroyed

        def destroy(self):
            events.append("components_destroy")
            self._destroyed = True

    components = Components()
    active_components = [components]
    monkeypatch.setattr(
        orchestration,
        "build_research_explicit_side_components",
        lambda *_args: active_components[0],
    )

    def heap_cleanup(_comm):
        events.append("collective_cleanup")
        return {"collective_call_completed": True}

    monkeypatch.setattr(orchestration, "collective_heap_cleanup", heap_cleanup)

    class Vec:
        def duplicate(self):
            events.append("snapshot_duplicate")
            return Vec()

        def copy(self, _destination):
            events.append("snapshot_copy")

        def destroy(self):
            events.append("snapshot_destroy")

    def oracle_runner(*_args, **kwargs):
        assert kwargs["reference"] is None
        assert kwargs["explicit_components"] is active_components[0]
        kwargs["solution_consumer"](Vec(), {})
        events.append("oracle_cleanup")
        return {
            "pass": True,
            "numerical_pass": True,
            "inventory_pass": True,
            "inventory": {
                "bottom_direct_factor_count": 1,
                "top_direct_factor_count": 1,
                "global_hybrid_direct_factor_count": 0,
            },
            "lifecycle": {
                "bottom_action_destroyed": True,
                "top_action_destroyed": True,
                "bottom_direct_factor_count_after_cleanup": 0,
                "top_direct_factor_count_after_cleanup": 0,
                "explicit_components_destroyed_by_oracle": False,
            },
        }

    def recovery_runner(*_args):
        assert components.destroyed is True
        events.append("recovery")
        return {"pass": True, "physics": "measured"}

    run_directory = tmp_path / "candidate-d"
    (run_directory / "numerical_output").mkdir(parents=True)
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    producer = orchestration._candidate_d_producer_metadata(
        payload, "c" * 40, lambda *_args: None
    )
    report, checkpoint = orchestration._run_v3_8_candidate_d_campaign(
        SimpleNamespace(
            bottom=SimpleNamespace(),
            top=SimpleNamespace(),
            coupling=SimpleNamespace(),
        ),
        SimpleNamespace(),
        None,
        resolved_payload=payload,
        producer=producer,
        run_directory=run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        marker_callback=lambda *_args: None,
        oracle_runner=oracle_runner,
        recovery_runner=recovery_runner,
    )
    assert report["pass"] is True
    assert events.index("oracle_cleanup") < events.index("components_destroy")
    assert events.index("components_destroy") < events.index("collective_cleanup")
    assert events.index("collective_cleanup") < events.index("recovery")
    assert events.index("recovery") < events.index("snapshot_destroy")
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["direct_reference_payload_loaded"] is False
    assert saved["exact_side_components_materialized"] is True
    assert saved["release_contract"]["exact_side_cleanup_before_recovery"] is True
    assert (
        saved["release_contract"]["cleanup"]["collective_heap_cleanup"][
            "collective_call_completed"
        ]
        is True
    )

    failed_components = Components()
    active_components[0] = failed_components
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": False},
    )
    failed_directory = tmp_path / "candidate-d-cleanup-failure"
    (failed_directory / "numerical_output").mkdir(parents=True)
    (failed_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    recovery_count_before = events.count("recovery")
    with pytest.raises(ValueError, match="exact-side cleanup failed"):
        orchestration._run_v3_8_candidate_d_campaign(
            SimpleNamespace(
                bottom=SimpleNamespace(),
                top=SimpleNamespace(),
                coupling=SimpleNamespace(),
            ),
            SimpleNamespace(),
            None,
            resolved_payload=payload,
            producer=producer,
            run_directory=failed_directory,
            source_sha="c" * 40,
            comm=MPI.COMM_SELF,
            marker_callback=lambda *_args: None,
            oracle_runner=oracle_runner,
            recovery_runner=recovery_runner,
        )
    assert events.count("recovery") == recovery_count_before
    assert not (
        failed_directory / "numerical_output" / "v3_8_candidate_d_checkpoint.json"
    ).exists()


def test_v3_8_candidate_b_branch_skips_v3_7_reference_oracle_recovery(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = run_directory / "numerical_output" / "v3_8_candidate_b_checkpoint.json"

    def campaign(*_args, **kwargs):
        called.append("candidate_b")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_b_side_fixed_setup_end", {})
        for side in ("bottom", "top"):
            marker_callback(f"candidate_b_budget_8_{side}_ready", {})
            marker_callback(f"candidate_b_budget_8_{side}_end", {})
        marker_callback("candidate_b_side_fixed_cleanup_end", {})
        return {"status": "measured", "pass": False}, checkpoint

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_b_campaign", campaign)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V3-7 identity/oracle/recovery path was entered")

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {
                    "source_sha": "p" * 40,
                    "input_sha256": "i" * 64,
                    "resolved_config_sha256": "r" * 64,
                    "physical_model_sha256": "m" * 64,
                    "payload": {"artifact": {"sha256": "d" * 64}},
                },
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_b_only=True,
    )
    assert called == ["candidate_b", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-b-only.v1"
    assert result["formal_run"]["oracle"] == "not_run_by_candidate_b_contract"
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["objects"]["side_base_ilu"]["created"] is True
    assert ledger["objects"]["side_base_ilu"]["completed"] is True
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["created"] is True
    assert ledger["objects"]["correction_wrappers"]["completed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


@pytest.mark.parametrize("qualified", [False, True], ids=["historical", "qualified"])
def test_v3_8_candidate_d_branch_skips_direct_reference_and_identity(
    tmp_path, monkeypatch, qualified
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = run_directory / "numerical_output" / "v3_8_candidate_d_checkpoint.json"

    def campaign(*_args, **kwargs):
        called.append("candidate_d")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_d_explicit_components_ready", {})
        marker_callback("candidate_d_explicit_components_destroyed", {})
        classification = (
            "hybrid_iterative_exact_side_case_qualification"
            if qualified
            else orchestration.V3_8_CANDIDATE_D_CLASSIFICATION
        )
        report = {
            "status": "attempted" if qualified else "measured",
            "classification": classification,
            "pass": False,
        }
        if qualified:
            report["qualification"] = {
                "qualification_target": "TASK039_V3_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS",
                "final_qualification_status": "pending_parent_resource_gate",
                "case_qualification_opt_in": True,
                "case_qualification_attempt": True,
                "qualification_scope": "task039_v3_p6h5_m480_1deg_s",
                "cleanup_local_direct_factor_count": {"bottom": 0, "top": 0},
            }
        orchestration._write_v3_8_candidate_d_checkpoint(
            kwargs["run_directory"],
            source_sha=kwargs["source_sha"],
            resolved_payload=kwargs["resolved_payload"],
            producer=kwargs["producer"],
            oracle={
                "pass": False,
                "inventory": {
                    "global_hybrid_direct_factor_count": 0,
                    "bottom_direct_factor_count": 1,
                    "top_direct_factor_count": 1,
                },
            },
            recovery=None,
            cleanup={
                "pass": False,
                "bottom_direct_factor_count_after_cleanup": 0,
                "top_direct_factor_count_after_cleanup": 0,
            },
            comm=kwargs["comm"],
            classification=classification,
            qualification=report.get("qualification"),
            status=report["status"],
        )
        return report, checkpoint

    def forbidden(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"{name} was called")

        return fail

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_d_campaign", campaign)

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=forbidden("inventory_loader"),
        reference_builder=forbidden("reference_builder"),
        identity_runner=forbidden("identity_runner"),
        oracle_runner=forbidden("oracle_runner"),
        recovery_runner=None,
        candidate_d_only=not qualified,
        candidate_d_qualified=qualified,
    )
    assert called == ["candidate_d", "rhs_destroy"]
    assert result["schema"] == (
        "task039.v3-8-candidate-d-qualified.v1"
        if qualified
        else "task039.v3-8-candidate-d-only.v1"
    )
    assert result["direct_reference_payload_loaded"] is False
    assert result["candidate_d"]["pass"] is False
    assert result["candidate_d"]["classification"] == (
        "hybrid_iterative_exact_side_case_qualification"
        if qualified
        else orchestration.V3_8_CANDIDATE_D_CLASSIFICATION
    )
    if qualified:
        assert result["candidate_d"]["status"] == "attempted"
        assert result["candidate_d"]["classification"] == (
            "hybrid_iterative_exact_side_case_qualification"
        )
        assert (
            result["candidate_d"]["qualification"]["case_qualification_attempt"] is True
        )
        assert result["candidate_d"]["qualification"]["qualification_target"] == (
            "TASK039_V3_CASE_QUALIFIED_EXPLICIT_OPT_IN_HYBRID_ITERATIVE_EXACT_SIDE_PASS"
        )
        assert result["candidate_d"]["qualification"]["final_qualification_status"] == (
            "pending_parent_resource_gate"
        )
        assert "case_qualified" not in result["candidate_d"]["qualification"]
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert saved["schema"] == "task039.v3-8-candidate-d-qualified-checkpoint.v1"
        assert saved["status"] == "attempted"
        assert saved["pass"] is False
        assert saved["qualification"]["final_qualification_status"] == (
            "pending_parent_resource_gate"
        )
        assert (
            saved["release_contract"]["cleanup"][
                "bottom_direct_factor_count_after_cleanup"
            ]
            == 0
        )
        assert (
            saved["release_contract"]["cleanup"][
                "top_direct_factor_count_after_cleanup"
            ]
            == 0
        )
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "completed"
    assert ledger["objects"]["setup"]["destroyed"] is True
    assert ledger["objects"]["candidate_d_explicit_components"]["destroyed"] is True
    assert ledger["objects"]["independent_reference"]["created"] is False


def test_v3_8_candidate_c_normal_return_finalizes_ledger(tmp_path, monkeypatch) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = (
        run_directory / "numerical_output" / "v3_8_candidate_c1_checkpoint.json"
    )

    def campaign(*_args, **kwargs):
        called.append("candidate_c")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_c_side_fixed_setup_end", {})
        marker_callback("candidate_c_side_fixed_cleanup_end", {})
        return {"status": "measured", "pass": False}, checkpoint

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_c_campaign", campaign)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V3-7 identity/oracle/recovery path was entered")

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {
                    "source_sha": "p" * 40,
                    "input_sha256": "i" * 64,
                    "resolved_config_sha256": "r" * 64,
                    "physical_model_sha256": "m" * 64,
                    "payload": {"artifact": {"sha256": "d" * 64}},
                },
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_c_only=True,
    )
    assert called == ["candidate_c", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-c1-only.v1"
    ledger_ref = result["telemetry"]["memory_object_ledger"]
    assert ledger_ref["path"] == "numerical_output/memory_object_ledger.json"
    assert ledger_ref["schema"] == "task039.v3-7-memory-object-ledger.v1"
    assert ledger_ref["status"] == "completed"
    ledger = json.loads(
        (run_directory / ledger_ref["path"]).read_text(encoding="utf-8")
    )
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["created"] is True
    assert ledger["objects"]["correction_wrappers"]["completed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


def test_v3_8_candidate_c_cleanup_fields_use_nested_lifecycle() -> None:
    fields = orchestration._candidate_c_cleanup_fields(
        {"destroyed": True},
        {
            "destroyed": True,
            "lifecycle": {"factor_count_after_destroy": 0, "factors_released": True},
        },
    )
    assert fields["fixed_destroyed"] is True
    assert fields["base_destroyed"] is True
    assert fields["base_factor_count_after_destroy"] == 0
    assert fields["base_factors_released"] is True


def test_v3_7_boot_markers_bound_setup_sentinel_failure(tmp_path) -> None:
    payload = load_v3_7_official_payload(INPUT)
    run_directory = tmp_path / "setup-sentinel"

    def setup_sentinel(*_args, **_kwargs):
        raise RuntimeError("V3_7_SETUP_SENTINEL_REACHED")

    with pytest.raises(RuntimeError, match="V3_7_SETUP_SENTINEL_REACHED"):
        orchestration.run_task039_v3_7_diagnostic(
            payload,
            run_directory,
            source_sha="a" * 40,
            comm=MPI.COMM_SELF,
            setup_builder=setup_sentinel,
            inventory_loader=lambda *_args, **_kwargs: (
                {},
                np.zeros(960, dtype=complex),
            ),
            recovery_runner=lambda *_args, **_kwargs: {"pass": True},
        )

    marker_path = run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
    markers = [
        json.loads(line)["stage"]
        for line in marker_path.read_text(encoding="utf-8").splitlines()
    ]
    assert markers == [
        "diagnostic_entry",
        "profile_ready",
        "watchdog_ready",
        "inventory_ready",
        "config_ready",
        "setup_begin",
    ]
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "exception"


def test_v3_7_direct_authority_is_not_blocked_by_full3d_secondary_error(
    tmp_path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate" / "numerical_output"
    candidate.mkdir(parents=True)
    (candidate / "v3_7_hybrid_authority.json").write_text("{}", encoding="utf-8")
    direct = tmp_path / "direct"
    full3d = tmp_path / "full3d"
    direct.mkdir()
    full3d.mkdir()
    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_direct",
        lambda *_args: {"pass": True, "classification": "direct_pass"},
    )
    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_full3d",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("secondary fixture")),
    )
    result = orchestration.check_v3_7_integrated_physics(
        candidate.parent, direct, full3d
    )
    assert result["pass"] is True
    assert result["full3d_secondary"]["status"] == "checker_error"

    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_direct",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("direct fixture")),
    )
    failed = orchestration.check_v3_7_integrated_physics(candidate.parent, direct)
    assert failed["pass"] is False
    assert failed["status"] == "checker_error"


def test_v3_7_one_cell_cleanup_does_not_invent_unseen_arrays() -> None:
    ledger = _v3_7_object_ledger()
    _record_v3_7_marker(ledger, "one_cell_factor_destroyed", {})
    for name in (
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
    ):
        assert ledger["objects"][name]["created"] is False
        assert ledger["objects"][name]["destroyed"] is False
        assert ledger["objects"][name]["status"] == "not_available"


def test_v3_7_side_probe_uses_nonzero_seed_and_preserves_probe_identity() -> None:
    system, matrix, rhs = _tiny_side_system()
    probe = matrix.createVecRight()
    try:
        probe.setValue(0, PETSc.ScalarType(1.0 + 0.5j))
        probe.setValue(1, PETSc.ScalarType(-0.25 + 0.75j))
        probe.assemble()
        before = orchestration._side_vector_identity(probe, "probe")
        residual, metadata = orchestration._short_side_ksp_residual(
            system,
            probe,
            max_it=1,
            source="side_unpreconditioned_gmres_it1",
        )
        try:
            after = orchestration._side_vector_identity(probe, "probe")
            assert before["global_sha256"] == after["global_sha256"]
            assert before["source_norm"] == pytest.approx(after["source_norm"])
            assert metadata["rhs_norm"] > 1.0e-30
            assert metadata["residual_source"] == "explicit_b_minus_Ax"
            assert metadata["explicit_residual_relative"] == pytest.approx(0.0)
        finally:
            residual.destroy()

        vectors, owned, vector_metadata = orchestration._side_survey_vectors(
            system, "bottom", None
        )
        try:
            assert vectors["physical_side_rhs"].norm() == pytest.approx(0.0)
            for label in ("early_krylov_residual_it1", "early_krylov_residual_it3"):
                assert vector_metadata[label]["probe_source"] == (
                    "global_index_seed_739"
                )
                assert vector_metadata[label]["probe_identity"]["source_norm"] > 1.0e-30
                assert vector_metadata[label]["residual_source"] == (
                    "explicit_b_minus_Ax"
                )
        finally:
            for vector in owned:
                vector.destroy()
    finally:
        probe.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_zero_iteration_side_probe_fails_closed() -> None:
    system, matrix, rhs = _tiny_side_system()
    probe = matrix.createVecRight()
    try:
        probe.setValue(0, PETSc.ScalarType(1.0))
        probe.setValue(1, PETSc.ScalarType(2.0))
        probe.assemble()
        with pytest.raises(RuntimeError, match="no residual iteration"):
            orchestration._short_side_ksp_residual(
                system,
                probe,
                max_it=0,
                source="side_unpreconditioned_gmres_it0",
            )
    finally:
        probe.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_side_probe_excludes_zero_rhs_from_rho_aggregate() -> None:
    system, matrix, rhs = _tiny_side_system()
    nonzero = matrix.createVecRight()
    try:
        nonzero.setValue(0, PETSc.ScalarType(1.0))
        nonzero.setValue(1, PETSc.ScalarType(-1.0))
        nonzero.assemble()

        class CopyAction:
            def apply(self, source, target) -> None:
                source.copy(target)

        report = orchestration._side_correction_probe(
            system,
            CopyAction(),
            1,
            {"physical_side_rhs": rhs, "seed": nonzero},
            {},
        )
        zero = report["vectors"]["physical_side_rhs"]
        assert zero["rho"] is None
        assert zero["status"] == "degenerate_uninformative"
        assert zero["informative"] is False
        assert report["vector_inventory"]["excluded_count"] == 1
        assert report["vector_inventory"]["informative_count"] == 1
        assert report["rho_summary"]["median"] == pytest.approx(0.0)
        assert report["rho_summary"]["worst"] == pytest.approx(0.0)
    finally:
        nonzero.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_identity_checkpoint_survives_correction_exception(tmp_path) -> None:
    run_directory = tmp_path / "identity-checkpoint"
    producer = {
        "producer_source_sha": "p" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    identity = {
        "pass": True,
        "vector_count": 1,
        "vectors": {
            "seed": {
                "relative_error": 2.0e-12,
                "limit": 1.0e-10,
                "blocks": {"bottom": {"relative_error": 1.0e-12, "limit": 1.0e-10}},
            }
        },
        "rhs_equality": {"pass": True},
        "coupling_isolation": {"pass": True},
        "direct_solution_residual": {
            "relative_error": 7.5e-10,
            "denominator": "max(norm(physical_rhs),1e-30)",
        },
    }
    marker_events: list[tuple[str, dict]] = []

    def identity_stage():
        checkpoint = orchestration._write_v3_7_identity_checkpoint(
            run_directory,
            source_sha="c" * 40,
            producer=producer,
            identity=identity,
            comm=MPI.COMM_SELF,
        )
        orchestration._emit_marker(
            lambda marker, detail: marker_events.append((marker, dict(detail))),
            "identity_audit_complete",
            path="numerical_output/v3_7_identity_checkpoint.json",
            **{"pass": True},
        )
        assert checkpoint.is_file()
        return identity

    with pytest.raises(RuntimeError, match="correction sentinel"):
        run_v3_7_stage_sequence(
            identity_stage=identity_stage,
            correction_stage=lambda: (_ for _ in ()).throw(
                RuntimeError("correction sentinel")
            ),
            oracle_stage=lambda _consume: {"pass": False},
        )

    checkpoint = json.loads(
        (
            run_directory / "numerical_output" / "v3_7_identity_checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    assert checkpoint["source_sha"] == "c" * 40
    assert checkpoint["pass"] is True
    assert checkpoint["direct_solution_residual"]["relative_error"] == pytest.approx(
        7.5e-10
    )
    assert marker_events == [
        (
            "identity_audit_complete",
            {
                "path": "numerical_output/v3_7_identity_checkpoint.json",
                "pass": True,
            },
        )
    ]


def test_v3_7_side_survey_checkpoint_survives_oracle_exception(tmp_path) -> None:
    run_directory = tmp_path / "side-checkpoint"
    producer = {
        "producer_source_sha": "p" * 40,
        "consumer_source_sha": "c" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    passes = []
    for correction_passes in (1, 2, 4, 8):
        passes.append(
            {
                "correction_passes": correction_passes,
                "pass": True,
                "bottom": {
                    "vector_inventory": {
                        "informative_labels": ["seed"],
                        "excluded_labels": ["physical_side_rhs"],
                        "informative_count": 1,
                        "excluded_count": 1,
                    },
                    "rho_summary": {
                        "median": 0.1,
                        "worst": 0.2,
                        "candidate_A_pass": True,
                    },
                },
                "top": {
                    "vector_inventory": {
                        "informative_labels": ["seed"],
                        "excluded_labels": [],
                        "informative_count": 1,
                        "excluded_count": 0,
                    },
                    "rho_summary": {
                        "median": 0.11,
                        "worst": 0.21,
                        "candidate_A_pass": True,
                    },
                },
            }
        )
    correction = {"status": "measured", "pass": True, "passes": passes}
    checkpoint_holder = {}

    def correction_stage():
        checkpoint_holder["path"] = _write_v3_7_side_survey_checkpoint(
            run_directory,
            source_sha="s" * 40,
            producer=producer,
            correction=correction,
            comm=MPI.COMM_SELF,
        )
        return correction

    with pytest.raises(RuntimeError, match="oracle sentinel"):
        run_v3_7_stage_sequence(
            identity_stage=lambda: {"pass": True},
            correction_stage=correction_stage,
            oracle_stage=lambda _consume: (_ for _ in ()).throw(
                RuntimeError("oracle sentinel")
            ),
        )
    checkpoint = checkpoint_holder["path"]
    assert checkpoint.is_file()
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["source_sha"] == "s" * 40
    assert saved["physical_identity"] == {
        "producer_source_sha": "p" * 40,
        "consumer_source_sha": "c" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    assert saved["survey_pass"] is True
    assert [item["correction_passes"] for item in saved["passes"]] == [1, 2, 4, 8]
    for item in saved["passes"]:
        assert item["bottom"]["informative_labels"] == ["seed"]
        assert item["bottom"]["excluded_labels"] == ["physical_side_rhs"]
        assert item["bottom"]["median"] == pytest.approx(0.1)
        assert item["bottom"]["worst"] == pytest.approx(0.2)
        assert item["bottom"]["candidate_A_pass"] is True
        assert item["top"]["informative_labels"] == ["seed"]
        assert item["top"]["median"] == pytest.approx(0.11)
        assert item["top"]["worst"] == pytest.approx(0.21)
        assert item["top"]["candidate_A_pass"] is True
