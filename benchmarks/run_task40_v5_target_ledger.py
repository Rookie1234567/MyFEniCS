"""Write the real original-size AUTO mode inventory and bounded size ledger."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np

from benchmarks.postprocess_task40_p1_saved_fields_common_subcells import (
    _qualified_environment,
    _sha256,
    _write_json,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_q4_review_v5.dat"
OUTPUT_ROOT = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/target_ledger_v5"
MODE_OUTPUT = OUTPUT_ROOT / "original_size_auto_mode_manifest.json"
LEDGER_OUTPUT = OUTPUT_ROOT / "target_ledger.json"
SCALE_TO_ORIGINAL = Fraction(135, 7)
WORKFLOW_BUDGET_SECONDS = 172800.0


def _git_facts() -> dict[str, Any]:
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=ROOT, text=True
    ).strip()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).splitlines()
    if branch != "task40extra_0p7nm_engineering" or status:
        raise RuntimeError("TARGET_LEDGER requires the clean canonical Task40 branch")
    return {"branch": branch, "source_sha": head, "working_tree_clean": True}


def _target_config(cfg: Any) -> Any:
    scale = float(SCALE_TO_ORIGINAL)
    target = replace(
        cfg,
        period_x=50.0,
        period_y=25.0,
        z_min=-10.0,
        z_max=130.0,
        air_height=130.0,
        substrate_thickness=10.0,
        grating_height=120.0,
        grating_width_x=17.0,
        grating_width_y=25.0,
        air_void_box_nm=tuple(float(value) * scale for value in cfg.air_void_box_nm),
        stage4_dtn_order_policy="auto_propagating",
        diffraction_order_max_m=None,
        diffraction_order_max_n=None,
        reporting_diffraction_order_max_m=None,
        reporting_diffraction_order_max_n=None,
    )
    if not (
        target.lambda0 == 0.7
        and target.period_x == 50.0
        and target.period_y == 25.0
        and target.z_min == -10.0
        and target.z_max == 130.0
        and target.stage4_dtn_order_policy == "auto_propagating"
        and target.incident_phi_deg == 0.0
    ):
        raise ValueError("the original-size AUTO physical identity differs from Review V5")
    return target


def _target_mode_physical_identity(cfg: Any) -> dict[str, Any]:
    """Bind every external-mode parameter and label internal geometry scope."""

    return {
        "scope": "original_size_external_port_and_mode_inventory_only; internal grating/notch geometry does not enter the external-mode calculation",
        "geometry": {
            "period_x_nm": float(cfg.period_x),
            "period_y_nm": float(cfg.period_y),
            "z_min_nm": float(cfg.z_min),
            "z_max_nm": float(cfg.z_max),
            "grating_height_nm": float(cfg.grating_height),
            "grating_width_x_nm": float(cfg.grating_width_x),
            "grating_width_y_nm": float(cfg.grating_width_y),
            "air_void_box_nm": [float(value) for value in cfg.air_void_box_nm],
        },
        "wavelength_nm": float(cfg.lambda0),
        "materials": {
            "top_external_medium": {
                "label": "air/vacuum",
                "refractive_index": [float(cfg.n_air.real), float(cfg.n_air.imag)],
                "relative_permeability": [float(cfg.mu_r.real), float(cfg.mu_r.imag)],
            },
            "bottom_external_medium": {
                "label": "Si substrate",
                "refractive_index": [
                    float(cfg.substrate_index.real),
                    float(cfg.substrate_index.imag),
                ],
                "relative_permeability": [
                    float(cfg.mu_r.real), float(cfg.mu_r.imag)
                ],
            },
        },
        "incidence": {
            "theta_from_positive_z_deg": float(cfg.incident_theta_deg),
            "grazing_angle_deg": 90.0 - float(cfg.incident_theta_deg),
            "azimuth_deg": float(cfg.incident_phi_deg),
            "polarization": str(cfg.polarization_kind),
            "electric_amplitude": [
                float(complex(cfg.incident_amplitude).real),
                float(complex(cfg.incident_amplitude).imag),
            ],
        },
        "ports": {
            "top": {
                "side": "top",
                "reference_plane_z_nm": float(cfg.z_max),
                "external_material": "air/vacuum",
            },
            "bottom": {
                "side": "bottom",
                "reference_plane_z_nm": float(cfg.z_min),
                "external_material": "Si substrate",
            },
            "order_policy": str(cfg.stage4_dtn_order_policy),
            "maximum_abs_m": cfg.diffraction_order_max_m,
            "maximum_abs_n": cfg.diffraction_order_max_n,
        },
    }


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _target_resource_ledger(mode_count: int, host: dict[str, Any]) -> dict[str, Any]:
    x_segments = [
        math.ceil(Fraction(4 * 135, 7)),
        math.ceil(Fraction(3 * 135, 7)),
        math.ceil(Fraction(3 * 135, 7)),
        math.ceil(Fraction(4 * 135, 7)),
    ]
    nx, ny, nz = sum(x_segments), 4, 14
    cells = nx * ny * nz
    p6_full = 10_228_620
    p6_independent = 9_948_672
    p6_interior = 6_854_400
    p6_trace_base = p6_independent - p6_interior
    p4_trace_plus_ports_base = 1_314_304
    complex128_bytes = np.dtype(np.complex128).itemsize
    retained_p6 = p6_trace_base + mode_count
    from src.runners.physical_p4_schur_v14 import (
        _v14_outer_krylov_workspace_bytes,
    )
    from src.runners.physical_retained_outer_adapter import (
        _retained_outer_scratch_workspace_bytes,
    )

    outer_krylov_bytes = _v14_outer_krylov_workspace_bytes(
        retained_p6, restart=32
    )
    retained_scratch_bytes = _retained_outer_scratch_workspace_bytes(
        p6_full, retained_p6
    )
    fgmres_basis_vectors_per_group = 32 + 1
    fgmres_work_vector_count = 8
    local_tensor_dimension = 450 + 432

    def dense_complex128_bytes(rows: int, columns: int) -> int:
        return int(rows) * int(columns) * complex128_bytes

    local_block_objects = {
        "classification": "derived_single_instance_dense_shape_payloads_not_actual_sparse_storage_or_RSS",
        "dimensions": {
            "local_tensor": local_tensor_dimension,
            "interior": 450,
            "trace": 432,
        },
        "complex128_bytes_per_value": complex128_bytes,
        "one_raw_full_local_tensor": {
            "shape": [local_tensor_dimension, local_tensor_dimension],
            "bytes": dense_complex128_bytes(
                local_tensor_dimension, local_tensor_dimension
            ),
        },
        "one_interior_block_and_in_place_dense_LU_storage": {
            "shape": [450, 450],
            "bytes": dense_complex128_bytes(450, 450),
            "qualification": "dense shape-derived payload only; actual sparse factor fill and backend workspace remain unknown",
        },
        "one_schur_block": {
            "shape": [432, 432],
            "bytes": dense_complex128_bytes(432, 432),
        },
        "one_interior_trace_coupling": {
            "shape": [450, 432],
            "bytes": dense_complex128_bytes(450, 432),
        },
        "one_recovery_operator": {
            "shape": [450, 432],
            "bytes": dense_complex128_bytes(450, 432),
            "qualification": "single dense recovery-map instance; class count, sharing, and live overlap are unknown",
        },
        "single_local_interior_rhs_vector": {
            "shape": [450],
            "bytes": dense_complex128_bytes(450, 1),
        },
        "simultaneous_lifecycle_sum": "not inferred by adding these alternative/per-instance objects",
    }
    return {
        "status": "derived_candidate_not_mesh_or_pde_qualification",
        "candidate_geometry_nm": {
            "period_x": 50.0,
            "period_y": 25.0,
            "z_min": -10.0,
            "z_max": 130.0,
        },
        "candidate_mesh": {
            "rule": "ceil each original-size Gx784 x-interface segment divided by the 0.7nm-cell electrical-size scale; ny=4,nz=14 for counting only",
            "x_segment_counts": x_segments,
            "axis_cell_counts": [nx, ny, nz],
            "hexahedra": cells,
            "p6_full_storage_dofs": p6_full,
            "p6_periodic_independent_dofs": p6_independent,
            "p6_interior_dofs": p6_interior,
            "p6_trace_plus_actual_auto_ports": retained_p6,
            "p4_interface_plus_actual_auto_ports": p4_trace_plus_ports_base + mode_count,
            "p6_full_complex128_vector_bytes": p6_full * complex128_bytes,
            "p6_retained_complex128_vector_bytes": retained_p6 * complex128_bytes,
            "basis_counts_source": "Review V5 section 5.1 count-only candidate; AUTO port term replaced with the measured current generator count",
        },
        "mode_dependent_objects": {
            "actual_auto_mode_count": mode_count,
            "one_complex128_diagonal_H_bytes": mode_count * complex128_bytes,
            "one_full_dense_complex128_H_bytes": mode_count * mode_count * complex128_bytes,
            "both_H_and_Hhat_lifecycle": "not measured; ownership, reuse and simultaneous survival require C1/C2 evidence",
            "full_port_support_and_factor_cost": "unknown; not treated as zero",
        },
        "outer_vector_and_scratch_inventory": {
            "classification": "derived_by_existing_Task39_Task40_workspace_formulas",
            "candidate_p6_full_rows": p6_full,
            "retained_rows_with_actual_auto_M": retained_p6,
            "actual_auto_M": mode_count,
            "complex128_bytes_per_vector_entry": complex128_bytes,
            "fgmres_restart": 32,
            "fgmres_basis_groups": {
                "Krylov_basis_vectors": {
                    "count": fgmres_basis_vectors_per_group,
                    "bytes": dense_complex128_bytes(
                        fgmres_basis_vectors_per_group, retained_p6
                    ),
                },
                "preconditioned_basis_vectors": {
                    "count": fgmres_basis_vectors_per_group,
                    "bytes": dense_complex128_bytes(
                        fgmres_basis_vectors_per_group, retained_p6
                    ),
                },
            },
            "additional_work_vectors": {
                "count": fgmres_work_vector_count,
                "bytes": dense_complex128_bytes(
                    fgmres_work_vector_count, retained_p6
                ),
            },
            "total_krylov_vector_count": (
                2 * fgmres_basis_vectors_per_group + fgmres_work_vector_count
            ),
            "total_outer_krylov_bytes": outer_krylov_bytes,
            "outer_krylov_source_formula": "_v14_outer_krylov_workspace_bytes(retained_rows, restart=32) = (2*(restart+1)+8)*retained_rows*16",
            "retained_full_scratch_bytes": retained_scratch_bytes,
            "retained_full_scratch_source_formula": "_retained_outer_scratch_workspace_bytes(full_rows,retained_rows) = 24*full_rows*16 + 10*retained_rows*16",
            "retained_full_scratch_terms": {
                "full_space_24_vector_payload_bytes": dense_complex128_bytes(
                    24, p6_full
                ),
                "retained_space_10_vector_payload_bytes": dense_complex128_bytes(
                    10, retained_p6
                ),
            },
            "workspace_lifecycle_overlap": "source-derived payload estimates; not a simultaneous RSS sum",
        },
        "local_450_432_single_instance_inventory": local_block_objects,
        "remaining_local_and_factor_unknowns": {
            "unique_local_geometry_material_or_orientation_class_count": "unknown; not treated as one class",
            "actual_sparse_lu_fill_bytes_by_q": "unknown; no factorization",
            "backend_factor_workspace_and_all_q_overlap": "unknown; no backend setup",
        },
        "object_lifecycle": [
            {"object": "complete ordered AUTO modes and complex wave numbers", "status": "measured", "scope": "mode inventory only"},
            {"object": "count-only candidate mesh and basis dimensions", "status": "derived", "scope": "not generated; no FE mesh was built"},
            {"object": "AUTO H/Hhat diagonal versus dense storage", "status": "derived", "scope": "one object; excludes all other solver storage"},
            {"object": "cold JIT, quadrature, C/D, Di/XiB, projection matrices", "status": "unknown", "scope": "requires later bounded component measurements"},
            {"object": "all q factors, fill, workspace and simultaneous residency", "status": "unknown", "scope": "no factorization or backend run"},
            {"object": "outer Krylov vectors and retained full-scratch payload", "status": "derived", "scope": "uses actual AUTO M and existing restart=32 / retained-scratch formulas; lifecycle overlap remains unknown"},
            {"object": "450/432 local tensor, LU, Schur and recovery single-instance dense shapes", "status": "derived", "scope": "payload dimensions only; unique classes, sparse fill and lifetime remain unknown"},
            {"object": "full recovery/output and simultaneous object overlap", "status": "unknown", "scope": "no PDE solve"},
            {"object": "system baseline and physical-memory envelope", "status": "measured", "scope": "snapshot at TARGET_LEDGER generation time"},
            {"object": "end-to-end Gx784 plus comparison/checker time", "status": "not_run", "scope": f"enforced shared hard limit {WORKFLOW_BUDGET_SECONDS:.0f}s"},
        ],
        "system_snapshot": host,
        "acceptance_contract": {
            "maximum_total_physical_memory_bytes": 2_000_000_000_000,
            "swap_bytes": 0,
            "complete_necessary_workflow_seconds": WORKFLOW_BUDGET_SECONDS,
            "actual_pde": "not_run_by_TARGET_LEDGER",
            "unknown_costs_are_not_zero": True,
        },
    }


def build(output_root: Path = OUTPUT_ROOT) -> dict[str, Any]:
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"refusing to overwrite TARGET_LEDGER artifacts: {output_root}")
    git = _git_facts()
    environment = _qualified_environment()
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise RuntimeError("TARGET_LEDGER requires the repository-qualified activation")

    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        memory_envelope,
    )
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_ordered_mode_manifest,
    )

    specification = load_and_resolve(INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    target_cfg = _target_config(cfg)
    modes, rows, mode_digest = build_dynamic_mode_inventory(target_cfg)
    manifest_rows, manifest_bytes, manifest_digest = build_ordered_mode_manifest(
        modes, target_cfg
    )
    if manifest_digest != mode_digest or len(manifest_rows) != len(rows):
        raise ValueError("actual AUTO manifest digest is internally inconsistent")

    keys = [
        [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]
        for row in rows
    ]
    key_digest = hashlib.sha256(
        json.dumps(keys, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    classifications: dict[str, int] = {}
    positive_flux = 0
    for row in rows:
        classification = str(row["classification"])
        classifications[classification] = classifications.get(classification, 0) + 1
        flux = float(row["power_per_unit_amplitude"])
        if not math.isfinite(flux):
            raise ValueError("actual AUTO mode has a nonfinite power-per-amplitude value")
        positive_flux += int(flux > 0.0)
        gamma = row["gamma"]
        if not (math.isfinite(float(gamma.real)) and math.isfinite(float(gamma.imag))):
            raise ValueError("actual AUTO mode has a nonfinite complex gamma")

    source_files = (
        "src/common/modes_3d.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/dtn_port_3d.py",
        "benchmarks/run_task40_v5_target_ledger.py",
    )
    source_hashes = {name: _sha256(ROOT / name) for name in source_files}
    host = memory_envelope(PHYSICAL_MEMORY_PRESSURE_POLICY)
    host["capture_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    output_root.mkdir(parents=True, exist_ok=True)
    mode_path = output_root / "original_size_auto_mode_manifest.json"
    ledger_path = output_root / "target_ledger.json"
    mode_path.write_bytes(manifest_bytes)
    target_identity = _target_mode_physical_identity(target_cfg)
    target_identity_sha256 = _canonical_sha256(target_identity)
    original_size_inventory_identity = {
        "target_mode_physical_identity_sha256": target_identity_sha256,
        "ordered_mode_key_sha256": key_digest,
        "ordered_physical_mode_manifest_sha256": mode_digest,
        "mode_manifest_bytes_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
    }
    original_size_inventory_identity_sha256 = _canonical_sha256(
        original_size_inventory_identity
    )
    inventory = {
        "schema": "task40extra.target-ledger-v5.auto-inventory.v1",
        "status": "completed",
        "classification": "TARGET_LEDGER_MODE_MANIFEST_MEASURED",
        "generated_utc": host["capture_utc"],
        "run_identity": git,
        "input_path": str(INPUT),
        "input_sha256": _sha256(INPUT),
        "source_input_physical_model_sha256": specification.physical_model_sha256,
        "source_input_physical_model_sha256_scope": "resolved physical identity of the shrunken Gx784 source input; not the original-size identity",
        "generator": "src.solvers.fullspace_dtn_action.build_dynamic_mode_inventory -> src.common.modes_3d.outgoing_port_modes_3d",
        "generator_source_sha256": source_hashes,
        "selection_policy": "original-size physical AUTO, no manual order bounds, no FE assembly/factorization",
        "mode_count": len(rows),
        "ordered_mode_key_sha256": key_digest,
        "ordered_physical_manifest_sha256": mode_digest,
        "mode_manifest_path": str(mode_path),
        "mode_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "classification_counts": classifications,
        "positive_real_power_per_unit_amplitude_count": positive_flux,
        "maximum_absolute_mn": [
            max(abs(int(row["m"])) for row in rows),
            max(abs(int(row["n"])) for row in rows),
        ],
        "all_ordered_keys_and_complex_wavenumbers_in_manifest": True,
        "manifest_rows": len(rows),
        "manifest_byte_count": len(manifest_bytes),
        "legacy_inventory_comparison": {
            "historical_propagating_channel_count": 32060,
            "current_auto_count_matches_historical_count": len(rows) == 32060,
            "historical_ordered_key_digest": None,
            "conclusion": "count comparison only; no ordered-key equivalence can be claimed without the historical key digest",
        },
        "source_input_sha256": _sha256(INPUT),
        "target_mode_physical_identity": target_identity,
        "target_mode_physical_identity_sha256": target_identity_sha256,
        "original_size_ordered_mode_inventory_identity": original_size_inventory_identity,
        "original_size_ordered_mode_inventory_identity_sha256": original_size_inventory_identity_sha256,
        "fe_execution_scope": {
            "called_path": [
                "load_and_resolve(input)",
                "simulation_config_3d_from_normalized(shrunken_input_identity)",
                "_target_config(resolved_config)",
                "build_dynamic_mode_inventory(original_size_target_config)",
                "build_ordered_mode_manifest(modes, original_size_target_config)",
            ],
            "fe_mesh_or_space_build_call": False,
            "fe_form_assembly_call": False,
            "matrix_factorization_call": False,
            "pde_solve_call": False,
            "note": "dtn_port_3d may import dolfinx at module import time; this inventory does not call its FE mesh/space/assembly/factor/solve routines",
        },
    }
    _write_json(ledger_path, inventory)
    ledger = {
        "schema": "task40extra.target-ledger-v5.resources.v1",
        "status": "inventory_complete_capacity_unknown",
        "source_sha": git["source_sha"],
        "mode_inventory_path": str(mode_path),
        "mode_inventory_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "mode_count": len(rows),
        "key_digest": key_digest,
        "physical_mode_manifest_digest": mode_digest,
        "resource_ledger": _target_resource_ledger(len(rows), host),
        "mode_inventory_record_sha256": _sha256(ledger_path),
        "no_fe_assembly_factor_or_pde": True,
    }
    _write_json(output_root / "target_resource_ledger.json", ledger)
    return {"inventory": inventory, "resource_ledger": ledger}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args()
    result = build(args.output_root.resolve())
    print(
        json.dumps(
            {
                "mode_count": result["inventory"]["mode_count"],
                "ordered_mode_key_sha256": result["inventory"]["ordered_mode_key_sha256"],
                "physical_manifest_sha256": result["inventory"]["ordered_physical_manifest_sha256"],
                "mode_manifest_path": result["inventory"]["mode_manifest_path"],
                "target_mesh_candidate": result["resource_ledger"]["resource_ledger"]["candidate_mesh"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
