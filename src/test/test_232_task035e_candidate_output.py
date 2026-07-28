from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat

import numpy as np
import pytest

from benchmarks.task035e_candidate_output import (
    CANDIDATE_AUTHORITY_SCHEMA,
    CANDIDATE_OUTPUT_SCHEMA,
    CANDIDATE_OUTPUT_STATUS,
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
    candidate_config_sha256,
    main,
    write_candidate_output,
)
from src.adaptivity.hidden_auditor import (
    CANDIDATE_OUTPUT_SCHEMA as AUDITOR_OUTPUT_SCHEMA,
    canonical_json_sha256,
)
from src.adaptivity.hidden_auditor.package_reader import _validate_outputs


SOURCE_SHA = "6" * 40


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _write_candidate_run(tmp_path: Path) -> CandidateWatchdogInput:
    run_dir = tmp_path / "candidate-run"
    run_dir.mkdir(parents=True)
    config = {
        "case_name": "task035e_blind_path_a_cycle_3",
        "k0": float(2.0 * np.pi / 13.5),
        "mu_r": [1.0, 0.0],
        "mesh_target_size": 20.0,
        "polarization_kind": "s",
    }
    order_pairs = [
        *((m, 0) for m in (0, -1, -2, -3, -4, -5, -6, -7)),
        (-2, 1),
    ]
    orders = []
    r_total = 0.0
    t_total = 0.0
    r00_s = 0.0
    r00_p = 0.0
    for port_index, port in enumerate(("top", "bottom")):
        for order_index, (m, n) in enumerate(order_pairs):
            beta = 0.2 + 0.01 * order_index
            for polarization in ("s", "p"):
                scale = 1.0 if polarization == "s" else 1.0e-4
                power = scale * 1.0e-5 * (
                    1 + port_index * len(order_pairs) + order_index
                )
                amplitude = scale * complex(
                    0.01 * (order_index + 1),
                    -0.005 * (order_index + 1),
                )
                if port == "top":
                    r_total += power
                    if (m, n) == (0, 0) and polarization == "s":
                        r00_s = power
                    if (m, n) == (0, 0) and polarization == "p":
                        r00_p = power
                else:
                    t_total += power
                orders.append(
                    {
                        "side": port,
                        "m": m,
                        "n": n,
                        "polarization": polarization,
                        "propagating": True,
                        "power_carrying": True,
                        "kz": [
                            beta if port == "top" else -beta,
                            0.0,
                        ],
                        "beta": [beta, 0.0],
                        "outgoing_amplitude_at_boundary": [
                            amplitude.real,
                            amplitude.imag,
                        ],
                        "power_ratio": power,
                    }
                )
    a_volume = 1.0 - r_total - t_total
    dtn = {
        "metrics": {
            "power_source": "dtn_port_modal_amplitudes",
            "diffraction_total_power_source": "dtn_port_modal_amplitudes",
            "stage4_dtn_assembly": "auxiliary",
            "dtn_port_modal_amplitude_convention": "boundary amplitude",
            "R00_s": r00_s,
            "R00_p": r00_p,
            "R00_total": r00_s + r00_p,
            "R_total": r_total,
            "T_total": t_total,
        },
        "orders": orders,
    }
    dtn_path = run_dir / "dtn_port_diffraction_orders_3d.json"
    _write_json(dtn_path, dtn)

    volume = {
        "method": "volume_absorption",
        "status": "ok",
        "power_source": "volume_integral_Im_epsilon_E2",
        "A_volume_total": a_volume,
        "A_volume_grating": 0.8 * a_volume,
        "A_volume_substrate": 0.2 * a_volume,
    }
    volume_path = run_dir / "volume_absorption.json"
    _write_json(volume_path, volume)

    x = np.asarray([12.5])
    y = np.asarray([6.25])
    z = np.asarray([20.0, 80.0])
    shape = (2, 1, 1, 3)
    base = np.arange(np.prod(shape), dtype=float).reshape(shape) + 1.0
    e = 0.01 * base + 1j * 0.005 * base
    h = 0.001 * base - 1j * 0.0005 * base
    archive_path = run_dir / "full3d_reference_samples.npz"
    np.savez(
        archive_path,
        x_nm=x,
        y_nm=y,
        z_nm=z,
        E_V_per_m=e,
        H_A_per_m=h,
        interface_z_nm=z[[0]],
        E_t_interface_V_per_m=e[[0], :, :, :2],
        H_t_interface_A_per_m=h[[0], :, :, :2],
    )
    metadata = {
        "schema_version": 1,
        "archive": archive_path.name,
        "archive_sha256": _sha(archive_path),
        "archive_bytes": archive_path.stat().st_size,
        "array_shape_z_y_x_component": list(shape),
        "point_count": 2,
        "grid_convention": "periodic-cell-centered-x-y; exact-requested-z",
        "interface_plane_indices": [0],
        "middle_plane_indices": [1],
        "components": ["x", "y", "z"],
        "tangential_components": ["x", "y"],
        "electric_field_unit": "V/m",
        "magnetic_field_unit": "A/m",
    }
    metadata_path = run_dir / "full3d_reference_samples.json"
    _write_json(metadata_path, metadata)

    forest_sha = "1" * 64
    connectivity_sha = "2" * 64
    box_sha = "3" * 64
    degree_sha = "4" * 64
    entity_degree_sha = "5" * 64
    config_identity_sha = "6" * 64
    raw_active_dofs = 84_152
    active_dofs = 78_384
    matrix_rows = 23_018
    matrix_nnz = 15_291_778
    factor_nnz = 94_398_336
    solver_peak_bytes = 5 * 1024**3
    resource_cap_bytes = 10 * 1024**3
    plan = {
        "expected_forest": {"leaf_catalog_sha256": forest_sha},
        "cell_interior_degree_plan_sha256": degree_sha,
        "provenance": {
            "stage_action_sha256s": [],
        },
    }
    plan_path = run_dir / "blind-plan.json"
    _write_json(plan_path, plan)
    plan_sha = _sha(plan_path)
    matrix = {
        "matrix_rows": matrix_rows,
        "matrix_cols": matrix_rows,
        "matrix_nnz_used": float(matrix_nnz),
    }
    summary = {
        "config": config,
        "case_status": "completed",
        "official_result": True,
        "diagnostic_only": False,
        "postprocess_skipped": False,
        "polarization_kind": "s",
        "mpi_size": 8,
        "stage4_full3d_assembly_backend_actual": (
            "assembly_time_variable_p_condensed"
        ),
        "stage4_assembly_time_cell_static_condensation": True,
        "stage4_full3d_assembly_backend_qualification": {
            "status": "qualified"
        },
        "cell_static_condensation": {
            "full_global_matrix_allocated": False
        },
        "linear_solve_method": "direct_lu",
        "selected_parallel_lu_solver_type": "mumps",
        "actual_ksp_type": "preonly",
        "actual_pc_type": "lu",
        "actual_pc_factor_solver_type": "mumps",
        "linear_solve_petsc_options": {
            "ksp_type": "preonly",
            "pc_type": "lu",
            "pc_factor_mat_solver_type": "mumps",
        },
        "ksp_converged": True,
        "full3d_reference_exported": True,
        "full3d_reference_archive": str(archive_path),
        "full3d_reference_archive_sha256": _sha(archive_path),
        "full3d_reference_archive_bytes": archive_path.stat().st_size,
        "dtn_port_orders_json": dtn_path.name,
        "volume_absorption_file": volume_path.name,
        "R00_s": r00_s,
        "R00_p": r00_p,
        "R00_total": r00_s + r00_p,
        "R_total": r_total,
        "T_total": t_total,
        "A_balance": a_volume,
        "A_volume_total": a_volume,
        "linear_system_relative_residual": 1.0e-12,
        "num_raw_broken_active_fe_dofs": raw_active_dofs,
        "num_actual_conforming_active_fe_dofs": active_dofs,
        "matrix_stats": matrix,
        "stage4_dtn_factor_inventory": {
            "available": True,
            "factor_solver_type": "mumps",
            "matrix_stats": {
                "matrix_rows": matrix_rows,
                "matrix_nnz_used": float(factor_nnz),
            },
        },
        "stage4_local_h_constraint_audit": {
            "schema_version": (
                "task035e.stage4-multilevel-local-hp-"
                "reduction-authority.v1"
            ),
            "status": "stage4_local_h_reduction_authority_pass",
            "pass": True,
            "mesh": {
                "schema_version": (
                    "task035e.stage4-multilevel-local-h-mesh.v1"
                ),
                "status": "stage4_balanced_multilevel_local_h_mesh_pass",
                "pass": True,
                "plan_path": str(plan_path),
                "plan_file_sha256": plan_sha,
                "base_config_identity_sha256": config_identity_sha,
                "cell_interior_degree_plan_sha256": degree_sha,
                "forest": {
                    "schema_version": "task035d.dyadic-hexa-forest.v1",
                    "pass": True,
                    "leaf_catalog_sha256": forest_sha,
                },
                "carrier": {
                    "schema_version": (
                        "task035d.broken-dyadic-hexa-carrier.v1"
                    ),
                    "pass": True,
                    "leaf_catalog_sha256": forest_sha,
                    "canonical_connectivity_sha256": connectivity_sha,
                },
            },
            "degree_plan": {
                "schema_version": (
                    "task035e.local-h-variable-exact-sequence-plan.v1"
                ),
                "status": "local_h_variable_exact_sequence_plan_closed",
                "pass": True,
                "mesh_cell_box_catalog_sha256": box_sha,
                "cell_degree_plan_sha256": degree_sha,
                "geometry_canonical_entity_degree_sha256": (
                    entity_degree_sha
                ),
                "active_rows": raw_active_dofs,
            },
        },
    }
    summary_path = run_dir / "run_summary.json"
    _write_json(summary_path, summary)
    resource_policy = {
        "schema_version": (
            "task035e.blind-candidate-resource-policy.v1"
        ),
        "pass": True,
        "effective_job_cap_bytes": resource_cap_bytes,
    }

    def passed_gate(schema_version: str) -> dict[str, object]:
        return {
            "schema_version": schema_version,
            "pass": True,
            "checks": {"fixture_authority": True},
            "failures": [],
        }

    plan_gate = passed_gate(
        "task035e.blind-multilevel-plan-authority-gate.v1"
    )
    plan_gate.update(
        {
            "path": str(plan_path),
            "expected_file_sha256": plan_sha,
            "observed_file_sha256": plan_sha,
            "base_config_identity_sha256": config_identity_sha,
        }
    )
    live_resource = {
        "schema_version": (
            "task035e.blind-candidate-live-resource-gate.v1"
        ),
        "pass": True,
        "controlled_resource_stop": False,
        "stop_reason": None,
        "zero_swap_every_sample": True,
        "maximum_swap_authority_bytes": 0,
        "memory_cap_at_most_11_gib": True,
        "maximum_job_memory_authority_bytes": solver_peak_bytes,
        "effective_job_cap_respected": True,
        "minimum_headroom_20_percent_preserved": True,
        "policy": resource_policy,
    }
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "status": CANDIDATE_OUTPUT_STATUS,
        "degree": 6,
        "h_nm": 20.0,
        "polarization_kind": "s",
        "run_kind": "full-solve",
        "mpi_size": 8,
        "profile": "default",
        "stage4_full3d_assembly_backend_requested": (
            "assembly_time_variable_p_condensed"
        ),
        "stage4_full3d_assembly_backend_actual": (
            "assembly_time_variable_p_condensed"
        ),
        "source": {
            "commit_sha": SOURCE_SHA,
            "head_after_sha": SOURCE_SHA,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
            "status_after": "",
        },
        "task035e_reference_certifier": None,
        "task035e_blind_candidate": {
            "schema_version": CANDIDATE_AUTHORITY_SCHEMA,
            "selected": True,
            "output_role": "blind_current_solve",
            "trial_id": "path-a-trial",
            "cycle_index": 3,
            "source_sha": SOURCE_SHA,
            "config_sha256": candidate_config_sha256(config),
        },
        "task035e_blind_candidate_launch_gate": {
            "schema_version": "task035e.blind-candidate-launch-gate.v1",
            "selected": True,
            "plan": plan_gate,
            "solver": passed_gate(
                "task035e.blind-candidate-solver-gate.v1"
            ),
            "artifacts": passed_gate(
                "task035e.blind-candidate-artifact-gate.v1"
            ),
            "resource_policy": resource_policy,
            "live_resource_gate": live_resource,
        },
        "qualification": {"pass": True, "failures": []},
        "controlled_resource_stop": False,
        "return_code": 0,
        "terminated_for_memory": False,
        "terminated_for_timeout": False,
        "no_swap": True,
        "solver_summary_sha256": _sha(summary_path),
        "dtn_orders_sha256": _sha(dtn_path),
        "volume_absorption_sha256": _sha(volume_path),
        "reference_metadata_sha256": _sha(metadata_path),
        "calibration": {
            "exact_rows": matrix_rows,
            "exact_assembled_nnz": float(matrix_nnz),
            "factorization_or_solve_stage_seen": True,
        },
        "matrix_inventory": {"final": matrix},
        "raw_evidence": {
            "run_directory": str(run_dir),
            "solver_summary": str(summary_path),
            "dtn_orders": str(dtn_path),
            "volume_absorption": str(volume_path),
            "reference_metadata": str(metadata_path),
        },
        "solver_summary": summary,
    }
    record_path = run_dir / "watchdog_summary.json"
    _write_json(record_path, record)
    return CandidateWatchdogInput(record_path, _sha(record_path))


def _rewrite_record(
    record_input: CandidateWatchdogInput,
    mutator: object,
) -> CandidateWatchdogInput:
    record = json.loads(record_input.path.read_text(encoding="utf-8"))
    assert callable(mutator)
    mutator(record)
    _write_json(record_input.path, record)
    return CandidateWatchdogInput(record_input.path, _sha(record_input.path))


def test_candidate_adapter_emits_closed_full_spectrum_and_fields(
    tmp_path: Path,
) -> None:
    record = _write_candidate_run(tmp_path)
    adapted = adapt_candidate_output(record)

    assert CANDIDATE_OUTPUT_SCHEMA == AUDITOR_OUTPUT_SCHEMA
    assert set(adapted.payload) == {
        "schema_version",
        "orders",
        "scalar_observations",
        "complex_observations",
        "full_explicit_true_residual",
    }
    _validate_outputs(adapted.payload)
    orders = adapted.payload["orders"]
    assert len(orders) == 18
    assert {
        (row["port"], row["m"], row["n"])
        for row in orders
        if row["n"] == 1
    } == {("top", -2, 1), ("bottom", -2, 1)}
    assert all(
        {
            "cross_polarized_power",
            "cross_polarized_amplitude",
        }.issubset(row)
        for row in orders
    )
    scalar_names = {
        row["name"] for row in adapted.payload["scalar_observations"]
    }
    assert {
        "R00_s",
        "R00_p",
        "R00_total",
        "R_total",
        "T_total",
        "A_closure",
        "A_volume",
        "energy_closure",
        "interface_probe_l2",
        "volume_probe_l2",
    }.issubset(scalar_names)
    complex_names = {
        row["name"] for row in adapted.payload["complex_observations"]
    }
    assert {
        "interface_probe_complex",
        "volume_probe_complex",
        "interface/E_t/i0=0/i1=0/i2=0/i3=0",
        "volume/H/i0=0/i1=0/i2=0/i3=2",
    }.issubset(complex_names)
    assert adapted.record_sha256 == record.sha256
    assert adapted.source_sha == SOURCE_SHA
    assert adapted.output_sha256 == hashlib.sha256(
        json.dumps(
            adapted.payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    assert adapted.output_sha256 == canonical_json_sha256(adapted.payload)

    output = tmp_path / "candidate-output.json"
    receipt = write_candidate_output(output, adapted)
    assert receipt.output_sha256 == adapted.output_sha256
    assert stat.S_IMODE(output.stat().st_mode) == (
        stat.S_IRUSR | stat.S_IWUSR
    )
    assert json.loads(output.read_text(encoding="utf-8")) == adapted.payload


def test_candidate_adapter_rejects_artifact_tamper_and_missing_mode(
    tmp_path: Path,
) -> None:
    tampered = _write_candidate_run(tmp_path / "tampered")
    dtn_path = tampered.path.parent / "dtn_port_diffraction_orders_3d.json"
    dtn_path.write_text(
        dtn_path.read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    with pytest.raises(CandidateOutputError, match="SHA-256 mismatch"):
        adapt_candidate_output(tampered)

    missing = _write_candidate_run(tmp_path / "missing")
    dtn_path = missing.path.parent / "dtn_port_diffraction_orders_3d.json"
    dtn = json.loads(dtn_path.read_text(encoding="utf-8"))
    dtn["orders"] = [
        row
        for row in dtn["orders"]
        if not (
            row["side"] == "bottom"
            and row["m"] == -7
            and row["n"] == 0
            and row["polarization"] == "p"
        )
    ]
    _write_json(dtn_path, dtn)

    def rebind(record: dict[str, object]) -> None:
        record["dtn_orders_sha256"] = _sha(dtn_path)

    missing = _rewrite_record(missing, rebind)
    with pytest.raises(CandidateOutputError, match="lacks p"):
        adapt_candidate_output(missing)


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("source_dirty", "not stable and clean"),
        ("config", "config SHA-256 mismatch"),
        ("evaluator", "cannot become blind candidate"),
        ("status", "completed MPI8 variable-p"),
    ),
)
def test_candidate_adapter_rejects_identity_or_layer_drift(
    tmp_path: Path,
    mutation: str,
    message: str,
) -> None:
    record_input = _write_candidate_run(tmp_path)

    def mutate(record: dict[str, object]) -> None:
        if mutation == "source_dirty":
            record["source"]["tracked_source_dirty"] = True
        elif mutation == "config":
            record["task035e_blind_candidate"]["config_sha256"] = "f" * 64
        elif mutation == "evaluator":
            record["task035e_reference_certifier"] = {"selected": True}
        else:
            record["status"] = "full3d_reference_pass"

    changed = _rewrite_record(record_input, mutate)
    with pytest.raises(CandidateOutputError, match=message):
        adapt_candidate_output(changed)


def test_candidate_adapter_has_no_evaluator_or_auditor_import() -> None:
    source_path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "task035e_candidate_output.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(
        "reference_certifier" in name or "hidden_auditor" in name
        for name in imported
    )


def test_candidate_adapter_cli_is_hash_bound_and_immutable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _write_candidate_run(tmp_path)
    output = tmp_path / "candidate.json"
    assert main(
        [
            "--record",
            str(record.path),
            "--record-sha256",
            record.sha256,
            "--output",
            str(output),
        ]
    ) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "completed"
    assert receipt["source_sha"] == SOURCE_SHA
    assert output.is_file()

    assert main(
        [
            "--record",
            str(record.path),
            "--record-sha256",
            record.sha256,
            "--output",
            str(output),
        ]
    ) == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "failed"
    assert "overwrite" in failure["error"]
