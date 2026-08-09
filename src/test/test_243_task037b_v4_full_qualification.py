from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from petsc4py import PETSc

from benchmarks.canonical_vector_artifacts import (
    canonical_shard_manifest,
    write_canonical_manifest,
    write_canonical_packet_shard,
)
from benchmarks.task037b_v4_full_qualification_checker import check_v4_evidence
from src.solvers.hybrid_fem_modal_block_ldu import (
    HybridBlockLduFullSolveResult,
    create_action_block_ldu_preconditioner,
    solve_action_block_ldu_full,
)
from src.solvers.hybrid_fem_modal_iterative import (
    create_hybrid_assembled_block_action,
)
from src.test.test_242_task037b_v2_block_screen_runner import (
    _DenseFixedAction,
    _destroy_fixture,
    _tiny_fixture,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _complex_pair(value: complex) -> list[float]:
    return [float(value.real), float(value.imag)]


def _orders() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for side in ("bottom", "top"):
        for mode in range(40):
            rows.append(
                {
                    "side": side,
                    "m": mode,
                    "n": 0,
                    "polarization": "s",
                    "total_projection": _complex_pair(1.0 + 0.0j),
                    "incident_projection": _complex_pair(1.0 + 0.0j),
                    "outgoing_amplitude": _complex_pair(0.1 + 0.01j),
                    "outgoing_amplitude_at_boundary": _complex_pair(0.1 + 0.01j),
                    "power_ratio": 0.1 if mode < 6 else 0.0,
                    "R": 0.1,
                    "T": 0.2,
                }
            )
    return rows


def _write_canonical_role(root: Path, side: str, role: str) -> dict[str, object]:
    shard = root / f"{side}_{role}.jsonl"
    shard_meta = write_canonical_packet_shard(shard, [((0, 0), 1.0 + 0.0j)])
    shard_meta["local_duplicate_count"] = 0
    manifest = canonical_shard_manifest(
        role=f"{side}_{role}",
        mpi_size=1,
        shard_metadata=[shard_meta],
        extractor_audit={"global_summed_packet_count": 1},
    )
    manifest_path = root / f"{side}_{role}.manifest.json"
    manifest_sha = write_canonical_manifest(manifest_path, manifest)
    return {
        "manifest": manifest_path.name,
        "manifest_sha256": manifest_sha,
        "pass": True,
    }


def _write_bundle(
    root: Path,
    *,
    numerical: bool = True,
    post_linear: bool = False,
    post_linear_phase: str = "external_auxiliary",
) -> Path:
    root.mkdir()
    arrays = {
        "E_V_per_m": np.zeros((5, 20, 40, 3), dtype=np.complex128),
        "H_A_per_m": np.zeros((5, 20, 40, 3), dtype=np.complex128),
        "modal_amplitudes": np.zeros((240,), dtype=np.complex128),
        "bottom_q": np.ones((40,), dtype=np.complex128),
        "top_q": np.ones((40,), dtype=np.complex128),
    }
    npz_path = root / "own_grid.npz"
    np.savez_compressed(npz_path, **arrays)
    own_grid = {
        "path": npz_path.name,
        "sha256": _sha256(npz_path),
        "schema": "task037b.v4-own-grid-EH-modal-q.v1",
        "arrays": {
            name: {
                "shape": list(array.shape),
                "dtype": "complex128",
                "sha256": hashlib.sha256(
                    np.ascontiguousarray(array).tobytes()
                ).hexdigest(),
            }
            for name, array in arrays.items()
        },
    }
    roles = {
        side: {
            "roles": {
                role: _write_canonical_role(root, side, role)
                for role in ("active_trace", "full_fe")
            }
        }
        for side in ("bottom", "top")
    }
    orders = _orders()
    q = [_complex_pair(1.0 + 0.0j) for _ in range(40)]
    measured = bool(numerical and not post_linear)
    validation = {
        "official_record": "candidate_measured_not_official" if measured else "not_run",
        "R": 0.1 if measured else "not_run",
        "T": 0.2 if measured else "not_run",
        "A": 0.7 if measured else "not_run",
        "A_volume": {
            "A_volume_total": 0.7,
            "R_plus_T_plus_A_volume": 1.0,
            "energy_closure_error": 0.0,
            "local_regions": {"bottom": 0.1, "top": 0.1},
            "middle_modal_region": 0.5,
        }
        if measured
        else "not_run",
        "port_power": {
            "R_total": 0.1,
            "T_total": 0.2,
            "A_balance": 0.7,
        }
        if measured
        else "not_run",
        "orders": orders if measured else "not_run",
        "external_diffraction_orders": orders if measured else "not_run",
        "field": {"status": "measured_candidate_own_grid"} if measured else "not_run",
        "candidate_sample_grid": {"shape": [5, 20, 40, 3]} if measured else "not_run",
        "canonical_export": roles if measured else "not_run",
        "12_plus_12": "not_run",
        "Full3D": "not_run",
        "full3d_comparison": "not_run",
    }
    telemetry = {
        "history": [{"iteration": 0, "global_true_relative_residual": 1.0}],
        "own_grid": own_grid
        if measured or post_linear_phase == "own_physics_and_canonical"
        else {},
        "canonical_export": roles if measured else {},
    }
    record = {
        "record_schema": "task037b.v4-full-block-pc.v1",
        "qualification": {
            "integration_pass": True,
            "numerical_pass": numerical,
            "recovery_pass": bool(numerical and not post_linear),
            "own_physics_pass": bool(numerical and not post_linear),
            "canonical_pass": bool(numerical and not post_linear),
            "physics_pass": bool(numerical and not post_linear),
            "recovery_phase": post_linear_phase if post_linear else None,
        },
        "validation": validation,
        "v4_telemetry": telemetry,
        "status": (
            "task037b_v4_external_recovery_failed"
            if post_linear
            else "task037b_v4_full_solve_pass"
            if numerical
            else "task037b_v4_full_solve_numerical_negative"
        ),
    }
    solver_path = root / "solver_record.json"
    solver_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    history_sha = hashlib.sha256(
        json.dumps(telemetry["history"], sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    for name, payload in (
        ("memory_timeline.csv", "iteration\n0\n"),
        ("memory_stages.jsonl", "{}\n"),
        ("worker_stdout.txt", "candidate\n"),
    ):
        (root / name).write_text(payload, encoding="utf-8")
    authorities: dict[str, dict[str, str]] = {}
    h1 = {
        "h1_telemetry": {"modal_amplitudes": {"rows": 240, "sha256": "descriptor"}},
        "validation": {
            "external_auxiliary_amplitudes": {"bottom": q, "top": q},
            "external_diffraction_orders": orders,
            "port_power": {"R_total": 0.1, "T_total": 0.2, "A_balance": 0.7},
        },
        "physical_field_reconstruction": {
            "volume_absorption": {
                "A_volume_total": 0.7,
                "R_plus_T_plus_A_volume": 1.0,
                "energy_closure_error": 0.0,
                "local_regions": {"bottom": 0.1, "top": 0.1},
                "middle_modal_region": 0.5,
            }
        },
    }
    for name, payload in (
        ("h1_solver.json", h1),
        ("h1_summary.json", {"status": "authority_summary"}),
        ("full3d.json", {"status": "pinned_full3d"}),
        ("significant.json", {"status": "pinned_significant_reference"}),
    ):
        path = root / name
        path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        authorities[name] = {"path": path.name, "sha256": _sha256(path)}
    artifacts = {
        "solver_record_path": solver_path.name,
        "solver_record_sha256": _sha256(solver_path),
        "stages_path": "memory_stages.jsonl",
        "stages_sha256": _sha256(root / "memory_stages.jsonl"),
        "timeline_path": "memory_timeline.csv",
        "timeline_sha256": _sha256(root / "memory_timeline.csv"),
        "stdout_path": "worker_stdout.txt",
        "stdout_sha256": _sha256(root / "worker_stdout.txt"),
        "history_sha256": history_sha,
    }
    summary = {
        "schema_version": "task033.memory-watchdog.v2",
        "v4_contract_pass": True,
        "v4_artifacts": artifacts,
        "v4_authorities": {
            "h1_direct": authorities["h1_solver.json"],
            "h1_summary": authorities["h1_summary.json"],
            "full3d": authorities["full3d.json"],
            "significant_reference": authorities["significant.json"],
        },
    }
    summary_path = root / "summary.json"
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    return summary_path


def test_v4_checker_authority_gap_and_frozen_api(tmp_path: Path) -> None:
    summary_path = _write_bundle(tmp_path / "pass", numerical=True)
    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["evidence_integrity_pass"] is True
    assert result["authority_payload_gap"] is True
    assert result["comparisons"]["iterative_vs_full3d"]["status"] == (
        "not_run_dependency_gate"
    )
    assert result["comparisons"]["energy"]["status"] == "pass"
    assert set(result["comparisons"]["energy"]["fields"]) == {
        "R",
        "T",
        "A",
        "A_volume_total",
        "local_regions",
        "middle_modal_region",
        "R_plus_T_plus_A_volume",
        "energy_closure_error",
    }
    offline = result["comparisons"]["offline_resource"]
    assert offline["status"] == "measured"
    assert np.isfinite(offline["wall_seconds"]) and offline["wall_seconds"] >= 0.0
    assert (
        np.isfinite(offline["ru_maxrss_peak_mib"])
        and offline["ru_maxrss_peak_mib"] > 0.0
    )
    assert offline["ru_maxrss_semantics"] == (
        "historical checker-process peak on Linux"
    )
    assert offline["online_rss_included"] is False
    assert result["pass"] is False
    assert (
        "final_reported_relative_residual"
        in HybridBlockLduFullSolveResult.__dataclass_fields__
    )
    assert solve_action_block_ldu_full.__kwdefaults__["max_it"] == 700


def test_v4_checker_numerical_failure_is_official_fail_closed(tmp_path: Path) -> None:
    summary_path = _write_bundle(tmp_path / "negative", numerical=False)
    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["evidence_integrity_pass"] is True
    assert result["pass"] is False
    assert result["own_grid"]["status"] == "missing"
    assert result["canonical"]["status"] == "missing"


def test_v4_checker_accepts_post_linear_controlled_negative(tmp_path: Path) -> None:
    summary_path = _write_bundle(tmp_path / "post_linear", post_linear=True)
    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["evidence_integrity_pass"] is True
    assert result["recognized_controlled_negative"] is True
    assert result["comparisons"]["q"]["status"] == "not_run_dependency_gate"
    assert result["comparisons"]["modal"]["status"] == ("not_run_authority_payload_gap")
    assert result["comparisons"]["iterative_vs_full3d"]["status"] == (
        "not_run_dependency_gate"
    )


def test_v4_checker_accepts_own_phase_with_retained_grid(tmp_path: Path) -> None:
    summary_path = _write_bundle(
        tmp_path / "own_phase",
        post_linear=True,
        post_linear_phase="own_physics_and_canonical",
    )
    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["recognized_controlled_negative"] is True
    assert result["own_grid"]["arrays"]["bottom_q"]["pass"] is True
    assert result["canonical"]["status"] == "missing"


def test_v4_checker_tampered_artifact_fails_closed(tmp_path: Path) -> None:
    summary_path = _write_bundle(tmp_path / "tampered", numerical=True)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["v4_artifacts"]["solver_record_sha256"] = "0" * 64
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")
    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is False
    assert result["evidence_integrity_pass"] is False
    assert result["fail_closed"] is True


def test_v4_checker_missing_energy_payload_fails_closed(tmp_path: Path) -> None:
    summary_path = _write_bundle(tmp_path / "missing_energy", numerical=True)
    root = summary_path.parent
    solver_path = root / "solver_record.json"
    record = json.loads(solver_path.read_text(encoding="utf-8"))
    del record["validation"]["A_volume"]["local_regions"]
    solver_path.write_text(json.dumps(record, sort_keys=True), encoding="utf-8")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["v4_artifacts"]["solver_record_sha256"] = _sha256(solver_path)
    summary_path.write_text(json.dumps(summary, sort_keys=True), encoding="utf-8")

    result = check_v4_evidence(summary_path)
    assert result["candidate_evidence_pass"] is True
    assert result["comparisons"]["energy"]["status"] == "fail"
    assert "local_regions" in result["comparisons"]["energy"]["missing_candidate"]
    assert result["fail_closed"] is True


def test_v4_full_solve_retains_solution_and_deferred_lifecycle() -> None:
    fixture = _tiny_fixture()
    bottom_action = _DenseFixedAction(fixture["bottom"].A, fixture["inverse"])
    top_action = _DenseFixedAction(fixture["top"].A, fixture["inverse"])
    source_bottom = fixture["bottom"].A.createVecRight()
    source_top = fixture["top"].A.createVecRight()
    source_bottom.set(0.0)
    source_top.set(0.0)
    first, last = (int(value) for value in source_bottom.getOwnershipRange())
    source_bottom.getArray()[:] = np.asarray(
        [1.0 + 0.1j, -0.5 + 0.2j, 0.8 - 0.3j, 0.2 + 0.4j][first:last],
        dtype=PETSc.ScalarType,
    )
    first, last = (int(value) for value in source_top.getOwnershipRange())
    source_top.getArray()[:] = np.asarray(
        [-0.4 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j, -0.3 - 0.2j][first:last],
        dtype=PETSc.ScalarType,
    )
    action_matrix = None
    action_context = None
    preconditioner = None
    rhs = None
    result = None
    split_bottom = None
    split_top = None
    residual = None
    probe_bottom = None
    probe_top = None
    try:
        preconditioner = create_action_block_ldu_preconditioner(
            fixture["layout"],
            fixture["bottom"],
            fixture["top"],
            fixture["coupling"],
            bottom_action,
            top_action,
        )
        action_matrix, action_context = create_hybrid_assembled_block_action(
            fixture["bottom"], fixture["top"], fixture["coupling"]
        )
        rhs = fixture["layout"].pack(
            source_bottom,
            source_top,
            np.asarray([0.3 + 0.1j, -0.2 + 0.4j, 0.5 - 0.2j, -0.1 + 0.3j]),
        )
        build_bottom = bottom_action.apply_count
        build_top = top_action.apply_count
        result = solve_action_block_ldu_full(
            action_matrix,
            rhs,
            preconditioner,
            max_it=700,
        )
        iterations = result.iterations
        assert iterations > 0
        assert [row["iteration"] for row in result.history] == list(
            range(iterations + 1)
        )
        assert result.checkpoints
        assert result.checkpoints[-1]["iteration"] == iterations
        assert result.release["ksp_destroyed"] is True
        assert result.release["pc_context_destroyed"] is True
        assert result.release["action_modal_schur_retained_after_pc_destroyed"] is True
        assert result.release["solution_snapshot_retained"] is True
        assert result.release["borrowed_side_actions_retained"] is True
        assert result.inventory["global_A_materialized"] is False
        assert result.inventory["bottom_direct_factor_count"] == 0
        assert result.inventory["top_direct_factor_count"] == 0
        assert result.inventory["bottom_ilu_factor_count"] == 1
        assert result.inventory["top_ilu_factor_count"] == 1
        assert result.inventory["pc_owned_local_factor_count"] == 0
        pc_apply_count = result.inventory["pc_apply_count"]
        assert pc_apply_count > 0
        assert (
            result.inventory["bottom_action_apply_count"] - build_bottom
            == 2 * pc_apply_count
        )
        assert (
            result.inventory["top_action_apply_count"] - build_top == 2 * pc_apply_count
        )

        residual = rhs.duplicate()
        action_matrix.mult(result.solution, residual)
        residual.scale(PETSc.ScalarType(-1.0))
        residual.axpy(PETSc.ScalarType(1.0), rhs)
        assert residual.norm() / max(rhs.norm(), 1.0e-30) <= 1.0e-6

        split_bottom, split_top, split_modal = fixture["layout"].split(
            result.solution,
            fixture["bottom"].b,
            fixture["top"].b,
        )
        assert np.isfinite(split_bottom.norm())
        assert np.isfinite(split_top.norm())
        assert np.all(np.isfinite(split_modal))

        assert preconditioner.modal_schur is not None
        preconditioner.release_deferred_action_modal_schur()
        assert preconditioner.modal_schur is None
        assert preconditioner.inventory["modal_schur"]["destroyed"] is True

        probe_bottom = fixture["bottom"].A.createVecRight()
        probe_top = fixture["top"].A.createVecRight()
        probe_bottom.set(1.0)
        probe_top.set(1.0)
        target_bottom = probe_bottom.duplicate()
        target_top = probe_top.duplicate()
        bottom_action.apply(probe_bottom, target_bottom)
        top_action.apply(probe_top, target_top)
        assert np.all(np.isfinite(target_bottom.getArray(readonly=True)))
        assert np.all(np.isfinite(target_top.getArray(readonly=True)))
        target_bottom.destroy()
        target_top.destroy()

        result.destroy()
        assert np.isfinite(split_bottom.norm())
        assert np.isfinite(split_top.norm())
        assert np.all(np.isfinite(split_modal))
    finally:
        if result is not None and not result._destroyed:
            result.destroy()
        if preconditioner is not None:
            preconditioner.release_deferred_action_modal_schur()
            preconditioner.destroy()
        if residual is not None:
            residual.destroy()
        if split_bottom is not None:
            split_bottom.destroy()
        if split_top is not None:
            split_top.destroy()
        if probe_bottom is not None:
            probe_bottom.destroy()
        if probe_top is not None:
            probe_top.destroy()
        if rhs is not None:
            rhs.destroy()
        if action_matrix is not None:
            action_matrix.destroy()
        if action_context is not None:
            action_context.destroy()
        source_top.destroy()
        source_bottom.destroy()
        bottom_action.destroy()
        top_action.destroy()
        _destroy_fixture(fixture)


def test_v4_not_run_boundary_keeps_official_physics_closed() -> None:
    from benchmarks.run_task032_phase6_augmented import _v4_not_run_validation_boundary

    boundary = _v4_not_run_validation_boundary()
    expected = {
        "official_record",
        "R",
        "T",
        "A",
        "A_volume",
        "orders",
        "external_diffraction_orders",
        "field",
        "12_plus_12",
        "Full3D",
        "full3d_comparison",
        "candidate_sample_grid",
        "canonical_export",
    }
    assert set(boundary) == expected
    assert all(value == "not_run" for value in boundary.values())


@pytest.mark.parametrize(
    ("values", "expected"),
    (
        ((1.0e-6, 1.0e-8, 1.0e-8), True),
        ((1.0e-6 + 1.0e-12, 1.0e-8, 1.0e-8), False),
        ((1.0e-6, 1.0e-8 + 1.0e-12, 1.0e-8), False),
        ((1.0e-6, 1.0e-8, 1.0e-8 + 1.0e-12), False),
    ),
)
def test_v4_full_fe_threshold_boundaries(values, expected: bool) -> None:
    from benchmarks.run_task032_phase6_augmented import (
        _v4_full_fe_threshold_pass as runner_gate,
    )
    from benchmarks.run_task033_memory_watchdog import (
        _v4_full_fe_threshold_pass as evaluator_gate,
    )

    assert runner_gate(*values) is expected
    assert evaluator_gate(*values) is expected
