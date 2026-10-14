"""One-materialized-matrix V7 p6 condensed N0 direct full solve.

The route reuses the reviewed p6 local-condensation and carrier machinery.  It
materializes only the augmented p6 trace/port AIJ, then keeps that exact PETSc
matrix alive through MUMPS symbolic analysis, numeric factorization, and solve.
No p4 operator, p4 factor, H6 hierarchy, or outer Krylov method is created.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

PROFILE_ID = "dual_condensed_balh_native_0p7nm_aniso_n0_p6_direct_full_v1"
RSS_HARD_LIMIT_BYTES = 1_800_000_000_000
ACTIVE_ROWS = 9_280_800
APPENDED_PORTS = 572
DIRECT_ROWS = ACTIVE_ROWS + APPENDED_PORTS
FULL_P6_ROWS = 32_061_312
ACTIVE_MODE_SHA256 = "946e0d294b99cb7f44817c3649029942ac325f345eb1770caa566183d2b04f3b"
PARENT_MODE_SHA256 = "7f023c73d7b63379955642dd062e47ba7004f3cdf0accf42684286c4af71dbfb"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return {
            "array_omitted": True,
            "dtype": str(value.dtype),
            "shape": [int(item) for item in value.shape],
            "finite": bool(np.isfinite(value).all())
            if np.issubdtype(value.dtype, np.number)
            else False,
        }
    if isinstance(value, (complex, np.complexfloating)):
        number = complex(value)
        return [float(number.real), float(number.imag)]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else {"nonfinite": repr(number)}
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"cannot serialize {type(value).__name__} in direct summary")


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(_json_safe(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _validate_resolved_profile(payload: Mapping[str, Any]) -> dict[str, Any]:
    from src.io.native_capacity_profile import (
        V7_ANISO_N0_P6_DIRECT_PROFILES,
        native_capacity_profile_identity,
        native_profile_facts,
    )
    from src.io.resolved_config import canonical_json_bytes

    method = payload.get("method")
    solver = payload.get("solver")
    derived = payload.get("derived")
    if not isinstance(method, Mapping) or method.get("kind") != "full3d_direct":
        raise ValueError("p6 direct runner requires method.kind=full3d_direct")
    if not isinstance(solver, Mapping) or not isinstance(derived, Mapping):
        raise TypeError("resolved p6 direct solver/derived identity is missing")
    identity = native_capacity_profile_identity(method.get("kind"), solver)
    if identity not in V7_ANISO_N0_P6_DIRECT_PROFILES:
        raise ValueError("p6 direct runner requires the explicit V7 direct profile")
    resolved_facts = derived.get("native_capacity_profile")
    expected_facts = native_profile_facts(identity)
    if not isinstance(resolved_facts, Mapping):
        raise TypeError("resolved derived.native_capacity_profile is missing")
    if canonical_json_bytes(dict(resolved_facts)) != canonical_json_bytes(expected_facts):
        raise ValueError("resolved direct profile facts differ from the frozen profile")
    if resolved_facts.get("identity") != identity:
        raise ValueError("resolved native profile identity differs from solver selection")
    if resolved_facts.get("resources", {}).get("rss_hard_limit_bytes") != RSS_HARD_LIMIT_BYTES:
        raise ValueError("resolved direct profile RSS hard limit is not 1.8e12 bytes")
    options = resolved_facts.get("component_options")
    if not isinstance(options, Mapping):
        raise TypeError("resolved p6 direct component options are missing")
    if options.get("functional_store_policy") != "disabled_no_functional_store_config":
        raise ValueError("V7 p6 direct route forbids functional-store reuse")
    if options.get("cross_mesh_fe_reuse") is not False:
        raise ValueError("V7 p6 direct route forbids cross-mesh FE reuse")
    return dict(resolved_facts)


def _persist_n0_inventory(
    directory: Path,
    parent_inventory: tuple[Any, Any, str],
    active_inventory: tuple[Any, Any, str],
    selection: Mapping[str, Any],
    indices: tuple[int, ...],
) -> dict[str, Any]:
    from src.solvers.fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    artifacts: dict[str, Any] = {}
    for label, inventory in (("parent", parent_inventory), ("active", active_inventory)):
        _modes, rows, expected_sha = inventory
        encoded = _canonical_json_bytes(
            {
                "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": len(rows),
                "modes": rows,
            }
        )
        digest = hashlib.sha256(encoded).hexdigest()
        if digest != expected_sha:
            raise ValueError(f"live N0 {label} mode inventory hash differs")
        path = directory / f"n0_{label}_mode_manifest.json"
        with path.open("xb") as stream:
            stream.write(encoded)
        artifacts[label] = {
            "filename": path.name,
            "sha256": digest,
            "bytes": len(encoded),
        }
    old_to_new = [-1] * len(parent_inventory[1])
    for new_index, old_index in enumerate(indices):
        old_to_new[int(old_index)] = int(new_index)

    def key(row):
        return [row["side"], int(row["m"]), int(row["n"]), row["polarization"]]

    mapping = {
        "schema": "task39extra.n0-mode-index-map.v1",
        "selection": dict(selection),
        "selected_parent_indices": list(indices),
        "old_to_new": old_to_new,
        "retained_keys": [key(row) for row in active_inventory[1]],
        "omitted_keys": [
            key(row) for index, row in enumerate(parent_inventory[1])
            if old_to_new[index] == -1
        ],
        "omitted_values_policy": "not measured; never filled with zero",
    }
    encoded = _canonical_json_bytes(mapping)
    path = directory / "n0_mode_index_map.json"
    with path.open("xb") as stream:
        stream.write(encoded)
    artifacts["index_map"] = {
        "filename": path.name,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }
    return artifacts


def _port_support_groups(setup: Mapping[str, Any], carrier: Any, cfg: Any):
    """Use the actual top/bottom boundary-cell layers as sparse port supports."""

    mesh = setup["mesh"]
    space = setup["spaces"][6]
    local_cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    coordinates = np.asarray(mesh.geometry.x)
    geometry_dofmap = np.asarray(mesh.geometry.dofmap)
    groups: dict[str, list[int]] = {"bottom": [], "top": []}
    for cell in range(local_cells):
        points = coordinates[geometry_dofmap[cell]]
        lower_z = float(np.min(points[:, 2]))
        upper_z = float(np.max(points[:, 2]))
        if np.isclose(lower_z, float(cfg.domain_z_min), rtol=0.0, atol=1.0e-12):
            groups["bottom"].append(cell)
        if np.isclose(upper_z, float(cfg.domain_z_max), rtol=0.0, atol=1.0e-12):
            groups["top"].append(cell)
    if len(groups["bottom"]) != 200 or len(groups["top"]) != 200:
        raise ValueError("V7 p6 port support must be the 200-cell top/bottom boundary layers")

    order = ("bottom", "top")
    side_group = {side: index for index, side in enumerate(order)}
    group_rows: list[int] = []
    entries_by_side: dict[str, list[Any]] = {side: [] for side in order}
    for entry in tuple(carrier.entries):
        identity = getattr(entry, "mode_identity", None)
        side = identity.get("side") if isinstance(identity, Mapping) else None
        if side not in side_group:
            raise ValueError("V7 carrier entry has no top/bottom mode identity")
        entries_by_side[side].append(entry)
        group_rows.append(side_group[side])
    if tuple(len(entries_by_side[side]) for side in order) != (286, 286):
        raise ValueError("V7 active carrier must contain 286 bottom and 286 top ports")

    support_rows: dict[str, np.ndarray] = {}
    for side in order:
        local_dofs = [
            np.asarray(space.dofmap.cell_dofs(cell), dtype=np.int32)
            for cell in groups[side]
        ]
        local = np.unique(np.concatenate(local_dofs))
        support_rows[side] = np.asarray(
            space.dofmap.index_map.local_to_global(local), dtype=np.int64
        )
        support_rows[side].sort()
        for entry in entries_by_side[side]:
            for field in ("coupling_rows", "projection_rows"):
                rows = np.asarray(getattr(entry, field), dtype=np.int64).reshape(-1)
                if rows.size and not np.all(np.isin(rows, support_rows[side], assume_unique=False)):
                    raise ValueError(
                        f"V7 {side} carrier {field} escapes its actual boundary-cell layer"
                    )
    return (
        tuple(np.asarray(groups[side], dtype=np.int64) for side in order),
        tuple(group_rows),
        {
            "support_cell_counts": {side: len(groups[side]) for side in order},
            "support_row_counts": {side: len(support_rows[side]) for side in order},
            "carrier_rows_within_actual_boundary_layers": True,
            "support_identity": "actual_mesh_geometry_top_bottom_cell_layers_v1",
        },
    )


def _factor_same_matrix(factor: Any, matrix: Any, rhs: Any, solution: Any, marker):
    """Run exactly one symbolic/numeric/solve sequence on one matrix object."""

    matrix_object_id = id(matrix)
    factor.symbolic(matrix)
    marker("p6_mumps_symbolic_complete", {
        "matrix_object_id": matrix_object_id,
        "symbolic_calls": int(factor.symbolic_calls),
        "numeric_calls": int(factor.numeric_calls),
        "solve_calls": int(factor.solve_calls),
        "ordering": factor.preferred_ordering,
        "mumps_info": factor.info(),
    })
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed after MUMPS symbolic")
    factor.numeric(matrix)
    marker("p6_mumps_numeric_complete", {
        "matrix_object_id": matrix_object_id,
        "symbolic_calls": int(factor.symbolic_calls),
        "numeric_calls": int(factor.numeric_calls),
        "solve_calls": int(factor.solve_calls),
        "mumps_info": factor.info(),
        "refinement_settings": factor.refinement_settings(),
    })
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed after MUMPS numeric")
    factor.solve(rhs, solution)
    if id(matrix) != matrix_object_id:
        raise RuntimeError("materialized matrix object changed before MUMPS solve")
    return matrix_object_id


def run_p6_condensed_direct(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str | None,
) -> dict[str, Any]:
    """Execute the one authorized V7 p6 condensed direct full solve."""

    from mpi4py import MPI
    from petsc4py import PETSc

    from src.common.config_3d import SimulationConfig3D
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.runners.physical_intermediate import WorkflowLedger
    from src.runners.v7_anisotropic_mesh_evidence import (
        actual_v7_anisotropic_mesh_evidence,
    )
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_n0_mode_inventory,
    )
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import (
        fine_volume_quadrature_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_physical_rhs,
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
        recover_p0_outputs,
    )
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor
    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.p4_cell_condensed_inverse import assemble_condensed_ports
    from src.solvers.p6_cell_condensed_action import (
        build_p6_cell_condensed_action_from_carrier,
    )

    directory = Path(run_directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    numerical_output = directory / "numerical_output"
    numerical_output.mkdir(exist_ok=True)
    phase_path_value = os.environ.get("PHYSICAL_WATCHDOG_PHASE_PATH")
    if not phase_path_value:
        raise RuntimeError("direct V7 route requires the existing native-capacity watchdog")
    phase_path = Path(phase_path_value)
    if not phase_path.is_absolute():
        raise RuntimeError("watchdog phase path must be absolute")
    ledger = WorkflowLedger(directory, phase_path)
    summary: dict[str, Any] = {
        "schema": "task39extra.v7-p6-condensed-direct-summary.v1",
        "status": "RUNNING",
        "result_classification": "NOT_QUALIFIED",
        "run_id": resolved_payload.get("run_id"),
        "profile": PROFILE_ID,
        "operator_scope": "n0_filtered_dtn_not_full_dtn",
        "full_dtn_status": "FULL_DTN_NOT_VERIFIED",
        "authority": "AUTHORITY_LIMITED",
        "source_sha": source_sha,
        "matrix_lifecycle": "one_materialized_PETSc_AIJ_same_object_symbolic_numeric_solve",
        "p4_operator": "NOT_BUILT",
        "p4_factor": "NOT_BUILT",
        "outer_ksp": "NOT_BUILT",
        "functional_store": "DISABLED",
        "checks": {},
    }
    levels = None
    bundle = None
    condensed = None
    action = None
    factor = None
    full_rhs = None
    rhs_vector = None
    solution_vector = None
    schur_action_vector = None
    schur_residual_vector = None
    saved_field = None
    native_facts = None
    output_facts = None
    try:
        profile_facts = _validate_resolved_profile(resolved_payload)
        inherited_store = sorted(
            key for key in os.environ if key.startswith("TASK39EXTRA_FUNCTIONAL_STORE")
        )
        if inherited_store:
            raise ValueError(
                "V7 direct route forbids functional-store environment: "
                + ", ".join(inherited_store)
            )
        expected_threads = {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "BLIS_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        }
        bad_threads = {
            name: os.environ.get(name)
            for name, expected in expected_threads.items()
            if os.environ.get(name) != expected
        }
        if bad_threads:
            raise ValueError(f"V7 math thread environment differs from one: {bad_threads}")
        if MPI.COMM_WORLD.size != 1 or PETSc.ScalarType is not np.complex128:
            raise RuntimeError("V7 p6 direct route requires complex128 MPI1")
        if np.dtype(PETSc.IntType) != np.dtype(np.int64):
            raise RuntimeError("V7 p6 direct route requires 64-bit PetscInt")
        cap_value = os.environ.get("PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES")
        if cap_value is not None and int(cap_value) != RSS_HARD_LIMIT_BYTES:
            raise RuntimeError("watchdog launch cap differs from the exact 1.8e12-byte RSS hard limit")
        cfg = simulation_config_3d_from_normalized(resolved_payload)
        if not isinstance(cfg, SimulationConfig3D):
            raise TypeError("resolved direct input did not create SimulationConfig3D")
        ledger.marker("p6_direct_resolved_profile_bound", {
            "profile": PROFILE_ID,
            "derived_profile_identity": profile_facts["identity"],
            "component_options": profile_facts["component_options"],
            "rss_hard_limit_bytes": profile_facts["resources"]["rss_hard_limit_bytes"],
            "native_execution": profile_facts["native_execution"],
            "run_config_created_from_validated_resolved_payload": True,
        })

        ledger.marker("p6_direct_mesh_setup_started", {
            "degrees_built": [6],
            "cross_mesh_fe_reuse": False,
            "functional_store": False,
        })
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=False
        )
        mesh_evidence = actual_v7_anisotropic_mesh_evidence(
            levels, cfg, required_space_degrees=(6,)
        )
        if mesh_evidence.get("status") != "PASS":
            raise ValueError("actual V7 anisotropic mesh evidence did not pass")
        summary["mesh_evidence"] = mesh_evidence
        ledger.marker("p6_direct_actual_mesh_qa_complete", mesh_evidence)

        parent_inventory = build_dynamic_mode_inventory(cfg)
        active_inventory, operator_selection, selected_parent_indices = build_n0_mode_inventory(
            parent_inventory, cfg
        )
        if (
            len(parent_inventory[0]) != 32_060
            or parent_inventory[2] != PARENT_MODE_SHA256
            or len(active_inventory[0]) != APPENDED_PORTS
            or active_inventory[2] != ACTIVE_MODE_SHA256
            or len(selected_parent_indices) != APPENDED_PORTS
        ):
            raise ValueError("actual p6 N0/parent inventory differs from the frozen V7 identity")
        inventory_artifacts = _persist_n0_inventory(
            directory,
            parent_inventory,
            active_inventory,
            operator_selection,
            selected_parent_indices,
        )
        summary["mode_inventory"] = {
            "parent_mode_count": len(parent_inventory[0]),
            "parent_mode_sha256": parent_inventory[2],
            "active_mode_count": len(active_inventory[0]),
            "active_mode_sha256": active_inventory[2],
            "selected_parent_indices_sha256": operator_selection[
                "selected_parent_indices_sha256"
            ],
            "quadrature_authority": "full_32060_parent_q160",
            "artifacts": inventory_artifacts,
        }
        ledger.marker("p6_direct_n0_inventory_complete", summary["mode_inventory"])

        volume_quadrature_metadata, _volume_quadrature_records = (
            fine_volume_quadrature_metadata(levels, cfg)
        )
        bundle = build_same_mesh_physical_action(
            levels,
            cfg,
            6,
            mode_inventory=active_inventory,
            quadrature_mode_inventory=parent_inventory,
            operator_selection=operator_selection,
            selected_parent_indices=selected_parent_indices,
            volume_quadrature_metadata=volume_quadrature_metadata,
            reuse_surface_vector=True,
            reuse_surface_geometry_cache=True,
            surface_geometry_cache_limit_bytes=4 * 1024**3,
            surface_weighted_moment_contraction="q160_weighted_moment_x_then_y_v1",
            prepare_surface_trace_contraction=True,
            surface_assembly_backend=(
                "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1"
            ),
            functional_store_config=None,
            stage_callback=ledger.marker,
            surface_progress_interval=1024,
        )
        if int(bundle["dtn_quadrature_degree"]) != 160:
            raise ValueError("live p6 surface carrier is not using parent q160")
        if (
            len(bundle["modes"]) != APPENDED_PORTS
            or bundle.get("mode_sha256") != ACTIVE_MODE_SHA256
            or len(bundle["dtn_action"].carrier.entries) != APPENDED_PORTS
        ):
            raise ValueError("live p6 carrier differs from the frozen 572-mode N0 identity")
        summary["operator_identity"] = {
            "degree": 6,
            "parent_quadrature_degree": int(bundle["dtn_quadrature_degree"]),
            "parent_mode_count": len(parent_inventory[0]),
            "parent_mode_sha256": parent_inventory[2],
            "active_mode_count": len(bundle["modes"]),
            "active_mode_sha256": bundle["mode_sha256"],
            "operator_selection": operator_selection,
            "functional_store": False,
            "cross_mesh_fe_reuse": False,
        }
        ledger.marker("p6_direct_surface_carrier_complete", summary["operator_identity"])

        form_started = perf_counter()
        from dolfinx import fem

        compiled_form = fem.form(bundle["volume_action"].bilinear_form)
        form_seconds = perf_counter() - form_started
        ledger.marker("p6_direct_volume_form_compiled", {
            "wall_seconds": form_seconds,
            "dtype": str(compiled_form.dtype),
            "degree": 6,
        })
        support_groups, support_group_by_row, support_facts = _port_support_groups(
            levels, bundle["dtn_action"].carrier, cfg
        )
        summary["port_support"] = support_facts
        condensed_started = perf_counter()
        condensed = build_unconstrained_assembly_time_condensation(
            compiled_form,
            levels["spaces"][6],
            levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][6].mpc,
            appended_global_rows=APPENDED_PORTS,
            appended_support_owned_cell_groups=support_groups,
            appended_support_group_by_row=support_group_by_row,
            dense_appended_block=True,
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            defer_final_assembly=True,
            retain_local_schur_for_matrix_free=True,
            materialize_global_matrix=True,
            geometry_identity_policy="raw_unrounded",
            share_identity_cache=True,
        )
        if condensed.matrix is None:
            raise RuntimeError("p6 direct condensation did not materialize its one PETSc AIJ")
        if (
            int(condensed.full_rows) != FULL_P6_ROWS
            or int(condensed.active_rows) != ACTIVE_ROWS
            or int(condensed.appended_rows) != APPENDED_PORTS
            or tuple(map(int, condensed.matrix.getSize())) != (DIRECT_ROWS, DIRECT_ROWS)
        ):
            raise ValueError(
                "actual p6 condensed dimensions differ from the frozen V7 direct target"
            )
        port_terms = assemble_condensed_ports(
            condensed, bundle["dtn_action"].carrier
        )
        del port_terms
        condensed.matrix.assemble()
        matrix = condensed.matrix
        matrix_object_id = id(matrix)
        matrix_info = dict(matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM))
        matrix_identity = dict(condensed.build_audit["port_condensed_matrix_identity"])
        condensed_seconds = perf_counter() - condensed_started
        summary["matrix"] = {
            "shape": list(matrix.getSize()),
            "full_p6_storage_rows": int(condensed.full_rows),
            "active_trace_rows": int(condensed.active_rows),
            "appended_port_rows": int(condensed.appended_rows),
            "local_interior_rows_eliminated": int(condensed.interior_rows),
            "actual_matrix_info_after_assembly": matrix_info,
            "petsc_stream_identity": matrix_identity,
            "port_matrix_signs": "[S_V,Bhat;-Dhat,Hhat]",
            "materialized_matrix_object_id": matrix_object_id,
            "assembly_wall_seconds": condensed_seconds,
            "global_full_p6_matrix": False,
            "full_trace_matrix": False,
            "dense_trace_dtn_matrix": False,
            "preallocation_scope": "actual_top_bottom_boundary_cell_support_plus_dense_572_port_block",
            "condensation_build_audit": condensed.build_audit,
        }
        ledger.marker("p6_direct_augmented_matrix_complete", {
            "shape": list(matrix.getSize()),
            "nz_used": matrix_info.get("nz_used"),
            "nz_allocated": matrix_info.get("nz_allocated"),
            "matrix_identity": matrix_identity,
            "matrix_object_id": matrix_object_id,
            "assembly_wall_seconds": condensed_seconds,
        })

        # The P6 action is explicitly action-only.  Give it a shallow,
        # non-owning metadata view so the sole owner keeps the same materialized
        # PETSc matrix throughout MUMPS and still destroys it exactly once.
        import copy

        action_view = copy.copy(condensed)
        action_view.matrix = None
        action = build_p6_cell_condensed_action_from_carrier(
            action_view,
            bundle["dtn_action"].carrier,
            owns_condensed=False,
            exact_carrier_diagonal_hp=True,
            omit_structural_zero_hlocal=True,
        )
        if action.condensed is not action_view or condensed.matrix is not matrix:
            raise RuntimeError("p6 action borrowed ownership or changed the direct matrix")
        summary["matrix_free_action"] = {
            "uses_materialized_matrix": False,
            "borrowed_action_view_has_no_matrix": action_view.matrix is None,
            "matrix_owner_remains_condensed_system": True,
            "owns_condensed": action.owns_condensed,
            "matrix_object_id": id(condensed.matrix),
        }
        ledger.marker("p6_direct_action_view_ready", summary["matrix_free_action"])

        full_rhs, rhs_facts = build_physical_rhs(bundle)
        if full_rhs.getSize() != int(condensed.full_rows):
            raise ValueError("physical p6 RHS differs from the condensed full-storage layout")
        full_rhs_array = np.asarray(full_rhs.getArray(readonly=True))
        if full_rhs_array.shape != (int(condensed.full_rows),):
            raise ValueError("MPI1 p6 RHS storage view differs from its global row count")
        reduced_rhs_array = action.reduce_rhs(
            full_rhs_array,
            rhs_is_mpc_dual=True,
        )
        rhs_vector = condensed.create_augmented_vector()
        if rhs_vector.getSize() != DIRECT_ROWS:
            raise ValueError("reduced p6 RHS vector size differs from the materialized matrix")
        rhs_vector.getArray()[:] = reduced_rhs_array
        rhs_vector.assemble()
        solution_vector = rhs_vector.duplicate()
        solution_vector.set(0.0 + 0.0j)
        solution_vector.assemble()
        del reduced_rhs_array
        ledger.marker("p6_direct_rhs_ready", {
            "rhs_generation": rhs_facts,
            "full_rhs_norm": float(full_rhs.norm()),
            "reduced_rhs_norm": float(rhs_vector.norm()),
            "initial_guess": "zero_direct_solution_vector",
            "same_matrix_object_id": id(matrix),
        })

        factor = _MumpsFactor(matrix)
        factor_settings = factor.symbolic_memory_settings()
        summary["factor"] = {
            "backend": "PETSc_MUMPS",
            "preferred_ordering": factor.preferred_ordering,
            "symbolic_memory_settings_before_analysis": factor_settings,
            "same_matrix_object_id": id(matrix),
            "predicted_memory_is_not_a_stop_gate": True,
        }
        solve_started = perf_counter()
        matrix_object_after_factor = _factor_same_matrix(
            factor,
            matrix,
            rhs_vector,
            solution_vector,
            ledger.marker,
        )
        summary["factor"].update(
            symbolic_calls=int(factor.symbolic_calls),
            numeric_calls=int(factor.numeric_calls),
            solve_calls=int(factor.solve_calls),
            solve_lifecycle_wall_seconds=perf_counter() - solve_started,
            matrix_object_id_after_solve=matrix_object_after_factor,
            matrix_object_unchanged=matrix_object_after_factor == matrix_object_id,
            mumps_info_after_solve=factor.info(),
            refinement_settings=factor.refinement_settings(),
        )
        post_matrix_info = dict(matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM))
        summary["matrix"]["actual_matrix_info_after_solve"] = post_matrix_info

        # Compare the direct solve with its own materialized condensed matrix.
        schur_action_vector = matrix.createVecLeft()
        schur_residual_vector = rhs_vector.duplicate()
        matrix.mult(solution_vector, schur_action_vector)
        rhs_vector.copy(schur_residual_vector)
        schur_residual_vector.axpy(PETSc.ScalarType(-1.0), schur_action_vector)
        schur_relative = float(schur_residual_vector.norm()) / max(
            float(rhs_vector.norm()), np.finfo(float).tiny
        )
        schur_residual_array = np.asarray(
            schur_residual_vector.getArray(readonly=True), dtype=np.complex128
        ).copy()
        solution_array = np.asarray(
            solution_vector.getArray(readonly=True), dtype=np.complex128
        )
        ledger.set_phase("solve")
        ledger.marker("p6_direct_materialized_solve_complete", {
            "solve_relative_residual": schur_relative,
            "matrix_object_id": id(matrix),
            "nz_used": post_matrix_info.get("nz_used"),
            "nz_allocated": post_matrix_info.get("nz_allocated"),
            "mumps_info": summary["factor"]["mumps_info_after_solve"],
        })

        def native_apply(storage_values: np.ndarray) -> np.ndarray:
            from dolfinx.la.petsc import create_vector

            vector = create_vector(
                [(levels["spaces"][6].dofmap.index_map,
                  int(levels["spaces"][6].dofmap.index_map_bs))]
            )
            output = None
            try:
                values = np.asarray(storage_values, dtype=np.complex128).reshape(-1)
                if vector.getSize() != values.size:
                    raise ValueError("native A6 storage vector has the wrong global size")
                vector.getArray()[:] = values
                vector.assemble()
                output = apply_owned(bundle["physical_action"], vector)
                return np.asarray(output.getArray(readonly=True), dtype=np.complex128).copy()
            finally:
                if output is not None:
                    output.destroy()
                vector.destroy()

        ledger.set_phase("recovery")
        native_started = perf_counter()
        native_facts = action.evaluate_native_residual(
            solution_array,
            full_rhs_array,
            native_apply,
            rhs_is_mpc_dual=True,
            reduced_residual=schur_residual_array,
        )
        native_seconds = perf_counter() - native_started
        native_relative = float(native_facts["native_residual_relative"])
        native_identity_relative = float(native_facts["native_identity_relative"])
        if not np.isfinite([native_relative, native_identity_relative, schur_relative]).all():
            raise FloatingPointError("direct p6 or native A6 residual facts are non-finite")
        summary["residuals"] = {
            "condensed_direct_relative": schur_relative,
            "original_A6_n0_relative": native_relative,
            "original_A6_n0_gate": 1.0e-6,
            "native_identity_relative": native_identity_relative,
            "native_identity_formula": native_facts["native_identity_formula"],
            "operator_scope": "A6_n0",
            "wall_seconds": native_seconds,
            "rhs_norm": native_facts["native_rhs_norm"],
            "finite": True,
        }
        summary["checks"].update(
            condensed_direct_residual_finite=True,
            original_A6_n0_finite=True,
            original_A6_n0_residual_pass=native_relative <= 1.0e-6,
            native_condensed_identity_finite=True,
            native_condensed_identity_relative=native_identity_relative,
        )
        ledger.marker("p6_direct_original_A6_n0_residual_complete", summary["residuals"])

        from dolfinx.la.petsc import create_vector

        recovered = np.asarray(native_facts["storage_solution"], dtype=np.complex128)
        if recovered.shape != (int(condensed.full_rows),) or not np.isfinite(recovered).all():
            raise ValueError("recovered full p6 storage is incomplete or non-finite")
        saved_field = create_vector(
            [(levels["spaces"][6].dofmap.index_map,
              int(levels["spaces"][6].dofmap.index_map_bs))]
        )
        if saved_field.getSize() != recovered.size:
            raise ValueError("recovered p6 field vector has the wrong global size")
        saved_field.getArray()[:] = recovered
        saved_field.assemble()
        del recovered

        from src.runners.v7_n0_output_audit import (
            saved_output_observation,
            truncation_action_observation,
        )

        truncation = truncation_action_observation(
            modes=bundle["modes"],
            entries=bundle["dtn_action"].carrier.entries,
            solution=np.asarray(saved_field.getArray(readonly=True)),
            residual=np.asarray(native_facts["native_residual"]),
            rhs_norm=float(full_rhs.norm()),
            incident_projections=bundle["incident_projections"],
        )
        summary["same_field_truncation"] = truncation
        ledger.marker("p6_direct_tail20_observation_complete", truncation)

        from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
        from src.solvers.hcurl_canonical_vector_dolfinx import (
            iter_canonical_full_fe_packets,
        )

        def canonical_export(field, output_dir):
            return write_canonical_packet_shard(
                output_dir / "canonical_solution.rank0000.jsonl",
                iter_canonical_full_fe_packets(
                    field.function_space, field, levels["floquets"][6]
                ),
                audit_packets=True,
            )

        output_facts = recover_p0_outputs(
            bundle,
            saved_field,
            numerical_output,
            canonical_export=canonical_export,
            export_all_port_modes=True,
            active_port_outputs_only=True,
        )
        auxiliary = np.asarray(output_facts.pop("auxiliary"), dtype=np.complex128)
        if auxiliary.shape != (APPENDED_PORTS,) or not np.isfinite(auxiliary).all():
            raise ValueError("direct p6 output did not recover all 572 finite modal amplitudes")
        auxiliary_sha = hashlib.sha256(memoryview(np.ascontiguousarray(auxiliary)).cast("B")).hexdigest()
        output_facts["auxiliary"] = {
            "count": int(auxiliary.size),
            "finite": True,
            "complex128_payload_sha256": auxiliary_sha,
        }
        rta_closure = output_facts["volume_metrics"].get("energy_closure_error_port_volume")
        if rta_closure is None or not np.isfinite(float(rta_closure)):
            raise ValueError("direct p6 output did not produce a finite port-volume energy closure")
        output_facts["energy_closure_error_port_volume"] = float(rta_closure)
        summary["official_result"] = output_facts
        summary["checks"].update(
            all_572_modal_amplitudes_finite=True,
            rta_port_volume_energy_closure_pass=abs(float(rta_closure)) <= 1.0e-5,
            physical_energy_gate=1.0e-5,
            field_export_finite=bool(output_facts["electric_finite"]),
            auxiliary_export_finite=bool(output_facts["auxiliary_finite"]),
        )
        output_audit = saved_output_observation(
            numerical_output, output_facts, cfg, truncation
        )
        summary["v7_output_audit"] = output_audit
        summary["matched_reference"] = {
            "status": "REFERENCE_AUTHORITY_LIMITED",
            "reference_availability": "REFERENCE_NOT_AVAILABLE",
            "reason": "same-material independent full-DtN reference and mesh convergence were not run",
        }
        summary["complete_solve"] = True
        summary["factor"]["same_matrix_lifecycle_verified"] = (
            factor.symbolic_calls == factor.numeric_calls == factor.solve_calls == 1
            and matrix_object_after_factor == matrix_object_id
        )
        summary["checks"]["same_materialized_matrix_symbolic_numeric_solve"] = bool(
            summary["factor"]["same_matrix_lifecycle_verified"]
        )
        required_checks = (
            "original_A6_n0_residual_pass",
            "all_572_modal_amplitudes_finite",
            "rta_port_volume_energy_closure_pass",
            "field_export_finite",
            "auxiliary_export_finite",
            "same_materialized_matrix_symbolic_numeric_solve",
        )
        passed = all(bool(summary["checks"].get(key)) for key in required_checks)
        summary["status"] = (
            "P6_CONDENSED_DIRECT_N0_COMPLETED_AUTHORITY_LIMITED"
            if passed
            else "P6_CONDENSED_DIRECT_N0_GATE_FAILED"
        )
        summary["result_classification"] = summary["status"]
        summary["passed"] = passed
        summary["errors"] = [] if passed else [
            key for key in required_checks if not summary["checks"].get(key)
        ]
        summary["elapsed_monotonic_seconds"] = time.monotonic() - ledger.started
        ledger.set_phase("complete")
        ledger.marker("P6_CONDENSED_DIRECT_N0_COMPLETED", {
            "passed": passed,
            "status": summary["status"],
            "operator_scope": summary["operator_scope"],
            "full_dtn_status": summary["full_dtn_status"],
            "a6_n0_relative": native_relative,
            "rta_energy_closure": float(rta_closure),
        })
        summary_path = directory / "p6_condensed_direct_summary.json"
        _atomic_json(summary_path, summary)
        return {
            "passed": passed,
            "errors": list(summary["errors"]),
            "summary": str(summary_path),
            "result_classification": summary["result_classification"],
            "complete_solve": True,
            "numerical_output_directory": str(numerical_output),
        }
    except BaseException as exc:
        summary.update(
            status="FAILED",
            result_classification="P6_CONDENSED_DIRECT_N0_FAILED",
            exception_type=type(exc).__name__,
            exception_message=str(exc),
            failed_stage=ledger.last_stage,
            failed_phase=ledger.phase,
            elapsed_monotonic_seconds=time.monotonic() - ledger.started,
        )
        try:
            _atomic_json(directory / "p6_condensed_direct_summary.json", summary)
        except (OSError, TypeError, ValueError) as write_error:
            print(
                f"failed to persist direct-solve failure summary: {write_error!r}",
                file=sys.stderr,
            )
        try:
            ledger.marker("P6_CONDENSED_DIRECT_N0_FAILED", {
                "exception_type": type(exc).__name__,
                "exception_message": str(exc),
                "failed_stage": ledger.last_stage,
            })
        except (OSError, RuntimeError, TypeError, ValueError) as marker_error:
            print(
                f"failed to persist direct-solve failure marker: {marker_error!r}",
                file=sys.stderr,
            )
        raise
    finally:
        for vector in (
            schur_residual_vector,
            schur_action_vector,
            solution_vector,
            rhs_vector,
            saved_field,
            full_rhs,
        ):
            if vector is not None:
                try:
                    vector.destroy()
                except Exception as cleanup_error:  # noqa: BLE001
                    print(
                        f"direct-solve PETSc vector cleanup failed: {cleanup_error!r}",
                        file=sys.stderr,
                    )
        if factor is not None:
            try:
                factor.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve MUMPS cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if action is not None:
            try:
                action.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve p6 action cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if condensed is not None:
            try:
                condensed.destroy()
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve condensed system cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )
        if bundle is not None:
            try:
                destroy_same_mesh_physical_action(bundle)
            except Exception as cleanup_error:  # noqa: BLE001
                print(
                    f"direct-solve physical bundle cleanup failed: {cleanup_error!r}",
                    file=sys.stderr,
                )


__all__ = ["PROFILE_ID", "run_p6_condensed_direct"]
