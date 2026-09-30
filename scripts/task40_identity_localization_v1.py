#!/usr/bin/env python3
"""Watchdog-protected one-shot Task40 G0 iter8 local-operator diagnostic."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat"
OUTCOMES = ROOT / "docs/task40extra_0p7nm_engineering/outcomes"
COMPACT = OUTCOMES / "records/g0_attempt4_identity_gate_stop.json"
RUN = (
    ROOT / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/"
    "20260929T230709.246850Z"
)
RECORD = OUTCOMES / "records/identity_localization_v1.json"
ARTIFACT_ROOT = (
    ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/"
    "identity_localization_v1"
)
IDENTITY_LIMIT = 1.0e-10
WATCHDOG_WALL_SECONDS = 3600.0


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_array(value: np.ndarray) -> str:
    value = np.ascontiguousarray(value)
    digest = hashlib.sha256(repr((value.shape, str(value.dtype))).encode())
    digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def sha_matrix_bytes(value: np.ndarray) -> str:
    return hashlib.sha256(
        memoryview(np.ascontiguousarray(value)).cast("B")
    ).hexdigest()


def load_array(meta: dict, name: str, archive: Any) -> np.ndarray:
    return np.asarray(archive[meta[name]["array_key"]])


def as_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): as_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [as_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return as_json(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def write_record(payload: dict) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECORD.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(as_json(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(RECORD)


def vector_facts(value: np.ndarray, top_count: int = 6) -> dict:
    magnitude = np.abs(value)
    order = np.argsort(magnitude)[::-1]
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "sha256": sha_array(value),
        "norm_2": float(np.linalg.norm(value)),
        "max_abs": float(np.max(magnitude, initial=0.0)),
        "exact_nonzero_count": int(np.count_nonzero(value)),
        "count_abs_gt_1e-12": int(np.count_nonzero(magnitude > 1e-12)),
        "top_rows": [
            {
                "row": int(i),
                "value": [float(value[i].real), float(value[i].imag)],
                "abs": float(magnitude[i]),
            }
            for i in order[:top_count]
        ],
    }


def vector_difference(left: np.ndarray, right: np.ndarray) -> dict:
    return vector_facts(np.asarray(left) - np.asarray(right), top_count=5)


def _matrix_add(acc: dict, name: str, left: np.ndarray, right: np.ndarray,
                interior: np.ndarray, trace: np.ndarray) -> None:
    for support, rows, columns in (
        ("ii", interior, interior),
        ("it", interior, trace),
        ("ti", trace, interior),
        ("tt", trace, trace),
    ):
        a = left[np.ix_(rows, columns)]
        b = right[np.ix_(rows, columns)]
        key = (name, support)
        acc.setdefault(key, [0.0, 0.0, 0.0])
        acc[key][0] += float(np.linalg.norm(b - a) ** 2)
        acc[key][1] += float(np.linalg.norm(a) ** 2)
        acc[key][2] = max(
            acc[key][2], float(np.max(np.abs(b - a), initial=0.0))
        )


def _matrix_finish(acc: dict) -> dict:
    result = {}
    for (name, support), (diff_sq, ref_sq, max_abs) in sorted(acc.items()):
        result.setdefault(name, {})[support] = {
            "difference_fro_sum_squares_sqrt": float(np.sqrt(diff_sq)),
            "reference_fro_sum_squares_sqrt": float(np.sqrt(ref_sq)),
            "relative_difference": float(
                np.sqrt(diff_sq) / max(np.sqrt(ref_sq), np.finfo(float).tiny)
            ),
            "max_abs_difference": max_abs,
        }
    return result


def _artifact_hashes(compact: dict) -> dict:
    paths = {
        "worker_summary_sha256": RUN / "task40extra_nonseparable_0p7nm_p6q4_summary.json",
        "run_manifest_sha256": RUN / "run_manifest.json",
        "run_summary_sha256": RUN / "run_summary.json",
        "watchdog_summary_sha256": RUN / "watchdog/summary.json",
        "release_gate_packet_sha256": RUN / "release_gate_failure/v20_release_gate.json",
        "monitor_residuals_sha256": RUN / "monitor_residuals.jsonl",
        "iterations_sha256": RUN / "iterations.jsonl",
        "x2_retained_final_npz_sha256": RUN / "x2_retained_final.npz",
        "x2_terminal_residual_npz_sha256": RUN / "x2_residual_0008_0002.npz",
    }
    result = {}
    for key, path in paths.items():
        actual = sha_file(path)
        if actual != compact["artifacts"][key]:
            raise ValueError(f"attempt4 artifact hash mismatch: {key}")
        result[key] = actual
    return result


def worker() -> None:
    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem
    from dolfinx.la.petsc import create_vector

    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_physical_intermediate_runtime import (
        build_physical_intermediate_actions,
        destroy_physical_intermediate_actions,
        owned_slave_indices,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers.hcurl_assembly_time_condensation import (
        _canonical_axis_aligned_coordinates,
        _cell_integral_kernels,
        _orient_cell_tensor,
        _tabulate_raw_tensor_class,
    )
    from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate

    started = time.perf_counter()
    started_utc = datetime.now(timezone.utc).isoformat()
    source_sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    record: dict[str, Any] = {
        "schema": "task40extra.identity-localization.v1",
        "status": "R0_running",
        "source_sha": source_sha,
        "diagnostic_script_sha256": sha_file(Path(__file__).resolve()),
        "attempt4_identity": {},
        "R0": {},
        "R1": {},
        "resources": {},
    }
    levels = physical = None
    owned_vectors: list[Any] = []
    try:
        compact = json.loads(COMPACT.read_text(encoding="utf-8"))
        retained_meta = json.loads((RUN / "x2_retained_final.json").read_text())
        terminal_meta = json.loads((RUN / "x2_residual_0008_0002.json").read_text())
        if sha_file(INPUT) != compact["input_sha256"]:
            raise ValueError("G0 input hash differs from the frozen attempt4 record")
        hashes = _artifact_hashes(compact)
        if retained_meta["identity"]["source_sha"] != compact["source_sha"]:
            raise ValueError("attempt4 packet source SHA differs from its compact record")
        if retained_meta["identity"]["physical_model_sha256"] != compact[
            "physical_model_sha256"
        ]:
            raise ValueError("attempt4 physical identity differs from its compact record")
        if retained_meta["identity"]["expected_space_facts"]["appended_rows"] != compact[
            "setup_and_cost"
        ]["ordered_modes"]:
            raise ValueError("attempt4 port/mode count differs from its compact record")

        relevant_sources = (
            "src/geometry/mesh_builder_3d.py",
            "src/geometry/task40_nonseparable_plan.py",
            "src/solvers/common_3d_forms.py",
            "src/solvers/fullspace_dtn_action.py",
            "src/solvers/fullspace_mpc_action.py",
            "src/solvers/fullspace_physical_action.py",
            "src/solvers/fullspace_same_mesh_hcurl_pmg_physical.py",
            "src/solvers/hcurl_assembly_time_condensation.py",
            "src/solvers/p6_cell_condensed_action.py",
            "src/solvers/task39extra_p6_raw_tensor.py",
            "src/runners/physical_retained_outer_adapter.py",
        )
        source_changes = subprocess.run(
            [
                "git", "-C", str(ROOT), "diff", "--name-only",
                compact["source_sha"], source_sha, "--", *relevant_sources,
            ],
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        if source_changes:
            raise ValueError("p6 numerical source changed since attempt4")

        with np.load(RUN / "x2_retained_final.npz") as retained, np.load(
            RUN / "x2_residual_0008_0002.npz"
        ) as terminal:
            rm = retained_meta["residuals"]
            solution = load_array(rm, "storage_solution", retained).astype(np.complex128, copy=True)
            full_solution = load_array(retained_meta, "full_solution", retained).astype(np.complex128, copy=True)
            rhs = load_array(retained_meta, "original_rhs", retained).astype(np.complex128, copy=True)
            alpha = load_array(rm, "retained_alpha", retained).astype(np.complex128, copy=True)
            rhs_effective = load_array(rm, "native_effective_rhs", retained).astype(np.complex128, copy=True)
            native_saved = load_array(rm, "native_residual", retained).astype(np.complex128, copy=True)
            derived_saved = load_array(rm, "derived_native_residual", retained).astype(np.complex128, copy=True)
            delta_saved = load_array(rm, "native_identity_difference", retained).astype(np.complex128, copy=True)
            internal_saved = load_array(rm, "internal_residual", retained).astype(np.complex128, copy=True)
            port_saved = load_array(rm, "augmented_port_residual", retained).astype(np.complex128, copy=True)
            terminal_delta = load_array(
                terminal_meta["raw"], "native_identity_difference", terminal
            ).astype(np.complex128, copy=True)

        if not np.array_equal(solution, full_solution):
            raise ValueError("saved full field differs from recovered storage")
        if not np.array_equal(delta_saved, native_saved - derived_saved):
            raise ValueError("saved difference is not native minus derived")
        if not np.array_equal(delta_saved, terminal_delta):
            raise ValueError("retained and terminal iter8 vectors differ")
        if len(solution) != int(retained_meta["identity"]["expected_space_facts"]["full_rows"]):
            raise ValueError("saved full field length differs from attempt4")
        delta_norm = float(np.linalg.norm(delta_saved))
        rhs_norm = float(np.linalg.norm(rhs_effective))
        identity_scale = float(rm["native_identity_operation_scale"])
        record["attempt4_identity"] = {
            "compact_record_sha256": sha_file(COMPACT),
            "input_sha256": compact["input_sha256"],
            "source_sha": compact["source_sha"],
            "physical_model_sha256": compact["physical_model_sha256"],
            "ordered_mode_count": compact["setup_and_cost"]["ordered_modes"],
            "ordered_mode_sha256": retained_meta["identity"]["ordered_mode_sha256"],
            "all_compact_artifact_hashes_match": True,
            "p6_physical_sources_unchanged_since_attempt4": True,
            "attempt4_run_directory": str(RUN.relative_to(ROOT)),
        }
        record["R0"] = {
            "iteration": int(retained_meta["facts"]["iteration"]),
            "solution_sha256": sha_array(solution),
            "rhs_sha256": sha_array(rhs),
            "native_residual": vector_facts(native_saved),
            "derived_residual": vector_facts(derived_saved),
            "identity_difference": vector_facts(delta_saved),
            "saved_internal_residual": vector_facts(internal_saved),
            "eta_b_native_rhs": delta_norm / rhs_norm,
            "eta_id_operation_scale": delta_norm / identity_scale,
            "strict_limit": IDENTITY_LIMIT,
            "strict_gate_passed": delta_norm / identity_scale <= IDENTITY_LIMIT,
            "packet_consistency": "exact pass",
        }
        write_record(record)

        if MPI.COMM_WORLD.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise RuntimeError("diagnostic requires MPI1 complex128")
        if not str(sys.executable).endswith("/.venv/bin/python"):
            raise RuntimeError("qualified Task40 .venv Python is not active")
        threads = {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        }
        if any(value != "1" for value in threads.values()):
            raise RuntimeError(f"Task40 requires math threads=1: {threads}")
        record["environment"] = {
            "qualified_activation": os.environ.get(
                "_MYFENICS_WSL_QUALIFIED_ACTIVATION"
            ),
            "python": sys.executable,
            "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
            "petsc_int_type": str(np.dtype(PETSc.IntType)),
            "mpi_size": int(MPI.COMM_WORLD.size),
            "math_thread_environment": threads,
        }
        write_record(record)

        resolved = load_and_resolve(INPUT)
        if resolved.provenance["physical_model_sha256"] != compact["physical_model_sha256"]:
            raise ValueError("resolved physical model differs from attempt4")
        cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
        )
        physical = build_physical_intermediate_actions(
            levels, cfg, physical_only_degrees=(6,)
        )
        fine = physical["physical"][6]
        space = levels["spaces"][6]
        floquet = levels["floquets"][6]
        mesh = levels["mesh"]
        carrier = fine["dtn_action"].carrier
        cells = int(mesh.topology.index_map(mesh.topology.dim).size_local)
        index_map = space.dofmap.index_map
        if cells != 336 or index_map.size_global != len(solution):
            raise ValueError("G0 mesh/space differs from the saved 336-cell p6 field")
        if index_map.size_local != index_map.size_global or index_map.num_ghosts:
            raise ValueError("MPI1 p6 storage unexpectedly has ghosts")
        if fine["mode_sha256"] != retained_meta["identity"]["ordered_mode_sha256"]:
            raise ValueError("rebuilt DtN mode hash differs from attempt4")
        if len(carrier.entries) != len(alpha):
            raise ValueError("rebuilt carrier port count differs from attempt4")

        # Apply the existing MPC primal expansion to a private field copy.
        expanded_function = fem.Function(space)
        expanded_function.x.array[:] = solution
        expanded_function.x.scatter_forward()
        floquet.mpc.homogenize(expanded_function)
        floquet.mpc.backsubstitution(expanded_function)
        expanded_function.x.scatter_forward()
        expanded = np.asarray(expanded_function.x.array).copy()
        slaves = np.asarray(owned_slave_indices(space, floquet), dtype=np.int32)
        slave_norm = float(np.linalg.norm(delta_saved[slaves]))

        basix_element = space.element.basix_element
        interior = np.asarray(
            basix_element.entity_dofs[mesh.topology.dim][0], dtype=np.int32
        )
        trace = np.setdiff1d(
            np.arange(int(space.element.space_dimension), dtype=np.int32),
            interior,
            assume_unique=True,
        )
        if (len(interior), len(trace)) != (450, 432):
            raise ValueError("p6 local interior/trace partition differs from attempt4")
        interior_set = set(map(int, interior))
        tag_indices = np.asarray(levels["mesh_data"].cell_tags.indices, dtype=np.int32)
        tag_values = np.asarray(levels["mesh_data"].cell_tags.values, dtype=np.int32)
        tags = np.full(cells, -1, dtype=np.int32)
        tags[tag_indices] = tag_values
        if np.any(tags < 0):
            raise ValueError("G0 material tag map is incomplete")
        mesh.topology.create_entity_permutations()
        permutations = mesh.topology.get_cell_permutation_info()
        dofmap = space.dofmap
        local_to_global = dofmap.index_map.local_to_global

        entity_support = {}
        for dim, entities in enumerate(basix_element.entity_dofs):
            for entity, positions in enumerate(entities):
                for position in positions:
                    entity_support[int(position)] = [int(dim), int(entity)]
        top_rows = {
            int(item["row"]) for item in record["R0"]["identity_difference"]["top_rows"]
        }
        row_support = defaultdict(list)
        class_cells: dict[tuple, list[int]] = defaultdict(list)
        class_coordinates: dict[tuple, np.ndarray] = {}
        cell_data: dict[int, dict] = {}
        interior_location = {}
        interior_rows = set()
        for cell in range(cells):
            local = np.asarray(dofmap.cell_dofs(cell), dtype=np.int32)
            global_rows = np.asarray(local_to_global(local), dtype=np.int64)
            if not np.array_equal(local, global_rows):
                raise ValueError("MPI1 local/global storage row numbering differs")
            canonical, widths = _canonical_axis_aligned_coordinates(
                mesh, cell, tolerance=1.0e-11
            )
            key = (int(tags[cell]), *tuple(float(x) for x in widths))
            if key in class_coordinates and not np.array_equal(class_coordinates[key], canonical):
                raise ValueError("same rounded tensor class has inconsistent geometry")
            class_coordinates.setdefault(key, canonical)
            class_cells[key].append(cell)
            geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
            actual_coordinates = np.ascontiguousarray(
                mesh.geometry.x[geometry_dofs], dtype=np.float64
            ).reshape(8, 3)
            cell_data[cell] = {
                "rows": global_rows,
                "key": key,
                "actual": actual_coordinates,
                "rounded": canonical.reshape(8, 3),
                "widths_actual": np.ptp(actual_coordinates, axis=0),
                "widths_rounded": np.asarray(widths, dtype=np.float64),
                "permutation": int(permutations[cell]),
            }
            for local_i, row in enumerate(global_rows[interior]):
                row = int(row)
                if row in interior_location:
                    raise ValueError("an interior DoF is shared by multiple cells")
                interior_location[row] = (cell, local_i)
                interior_rows.add(row)
            for position, row in enumerate(global_rows):
                row = int(row)
                if row in top_rows:
                    row_support[row].append(
                        {
                            "cell": int(cell),
                            "tag": int(tags[cell]),
                            "local_position": int(position),
                            "role": "interior" if position in interior_set else "trace",
                            "entity_support": entity_support.get(position),
                            "permutation": int(permutations[cell]),
                        }
                    )
        if set(map(int, slaves)) & interior_rows:
            raise ValueError("MPC slave rows intersect cell interior rows")
        interior_mask = np.zeros(len(solution), dtype=bool)
        interior_mask[np.asarray(sorted(interior_rows), dtype=np.int64)] = True
        interior_field = np.zeros_like(expanded)
        interior_field[interior_mask] = expanded[interior_mask]
        trace_field = expanded - interior_field
        if not np.array_equal(interior_field + trace_field, expanded):
            raise ValueError("supplementary field split does not reconstruct the expanded saved field")
        record["R0"]["support"] = {
            "interior_row_count": len(interior_rows),
            "interior_delta_norm": float(np.linalg.norm(delta_saved[interior_mask])),
            "trace_and_slave_delta_norm": float(np.linalg.norm(delta_saved[~interior_mask])),
            "slave_row_count": int(slaves.size),
            "slave_delta_norm": slave_norm,
            "top_rows": [
                {
                    **item,
                    "incident_cells": row_support.get(int(item["row"]), []),
                }
                for item in record["R0"]["identity_difference"]["top_rows"]
            ],
        }
        record["status"] = "R0_complete_R1_running"
        write_record(record)

        form = fine["volume_action"].bilinear_form
        compiled = fem.form(form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
        kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
        component_actions = fine["volume_action"].component_actions
        component_compiled = {
            name: fem.form(
                component_actions[name]._bilinear_form,
                jit_options=dict(SAME_MESH_JIT_OPTIONS),
            )
            for name in ("curl", "material_mass")
        }
        component_kernels = {
            name: _cell_integral_kernels(
                component_compiled[name], sum_duplicate_cell_integrals=True
            )
            for name in component_compiled
        }
        candidate = Task39ExtraP6RawTensorCandidate(
            basix_element, cfg, form, compiled_form=compiled
        )
        candidate.validate_compiled_form(compiled, kernels)
        previous_hashes = retained_meta["identity"]["p6_build_audit"][
            "action_only_complete_tensor_identities"
        ]

        # Carrier blocks are carried by active rows; internal B/D support is
        # still measured explicitly and included in the direct internal check.
        B, D = [], []
        Hp = np.zeros((len(alpha), len(alpha)), dtype=np.complex128)
        # The production adapter calls evaluate_native_residual without a
        # port_rhs argument, whose documented default is the zero port vector.
        port_rhs = np.zeros(len(alpha), dtype=np.complex128)
        Bi_alpha = {
            cell: np.zeros(len(interior), dtype=np.complex128) for cell in range(cells)
        }
        Bi_count = Di_count = 0
        for port, entry in enumerate(carrier.entries):
            Hp[port, port] = complex(entry.normalization_h)
            br = np.asarray(entry.coupling_rows, dtype=np.int64)
            bv = np.asarray(entry.coupling_values, dtype=np.complex128)
            dr = np.asarray(entry.projection_rows, dtype=np.int64)
            dv = np.asarray(entry.projection_values, dtype=np.complex128)
            for rows in (br, dr):
                if np.any(rows < 0) or np.any(rows >= len(solution)):
                    raise ValueError("carrier row is outside the saved full-storage vector")
                if set(map(int, rows)) & set(map(int, slaves)):
                    raise ValueError("carrier row uses an MPC slave")
            B.append((br, bv))
            D.append((dr, dv))
            for row, value in zip(br, bv, strict=True):
                if int(row) in interior_location:
                    cell, local_i = interior_location[int(row)]
                    Bi_alpha[cell][local_i] += value * alpha[port]
                    Bi_count += int(value != 0.0)
            Di_count += sum(int(value != 0.0) for row, value in zip(dr, dv, strict=True)
                            if int(row) in interior_location)

        def apply_B(values: np.ndarray) -> np.ndarray:
            result = np.zeros(len(solution), dtype=np.complex128)
            for port, (rows, weights) in enumerate(B):
                np.add.at(result, rows, weights * values[port])
            return result

        def apply_D(field: np.ndarray) -> np.ndarray:
            return np.asarray(
                [np.dot(weights, field[rows]) for rows, weights in D],
                dtype=np.complex128,
            )

        raw_actions = {
            name: np.zeros(len(solution), dtype=np.complex128)
            for name in ("actual_mesh_ffcx", "rounded_ffcx", "rounded_fast")
        }
        raw_component_actions = {
            name: np.zeros(len(solution), dtype=np.complex128)
            for name in ("curl", "material_mass")
        }
        supplementary_fields = {
            "interior_field_only": interior_field,
            "trace_field_plus_saved_port": trace_field,
        }
        supplementary_raw_actions = {
            operator: {
                probe: np.zeros(len(solution), dtype=np.complex128)
                for probe in supplementary_fields
            }
            for operator in raw_actions
        }
        internal = {name: [None] * cells for name in raw_actions}
        matrix_accum: dict[tuple, list[float]] = {}
        class_facts = []
        top_actions, top_internal = [], []
        expected_hashes = raw_hash_matches = orientation_hash_matches = 0
        ffcx_seconds = component_ffcx_seconds = candidate_seconds = 0.0

        def add_local_action(target: np.ndarray, rows: np.ndarray, values: np.ndarray) -> None:
            np.add.at(target, rows, values)

        for class_key in sorted(class_cells, key=repr):
            tag = int(class_key[0])
            coords_rounded = class_coordinates[class_key]
            ffcx_rounded = _tabulate_raw_tensor_class(
                compiled, kernels, coords_rounded, tag=tag,
                dimension=int(space.element.space_dimension),
            )
            t0 = time.perf_counter()
            candidate_rounded = candidate.build(
                coords_rounded, tag=tag,
                dimension=int(space.element.space_dimension),
            )
            candidate_seconds += time.perf_counter() - t0
            candidate_hash = sha_matrix_bytes(candidate_rounded)
            orient_cache = {}
            class_matrix_accum: dict[tuple, list[float]] = {}
            class_action_sq = defaultdict(float)
            width_delta_max = jacobian_delta_max = det_delta_max = 0.0

            for cell in class_cells[class_key]:
                info = cell_data[cell]
                perm = info["permutation"]
                if perm not in orient_cache:
                    round_ffcx = ffcx_rounded.copy()
                    round_fast = candidate_rounded.copy()
                    packet = np.asarray([perm], dtype=np.uint32)
                    _orient_cell_tensor(space.element, round_ffcx, packet)
                    _orient_cell_tensor(space.element, round_fast, packet)
                    orient_cache[perm] = (round_ffcx, round_fast)
                    previous = previous_hashes.get(repr((*class_key, perm)))
                    expected_hashes += int(previous is not None)
                    raw_hash_matches += int(
                        previous is not None
                        and previous.get("raw_sha256") == candidate_hash
                    )
                    orientation_hash_matches += int(
                        previous is not None
                        and previous.get("oriented_sha256") == sha_matrix_bytes(round_fast)
                    )

                t0 = time.perf_counter()
                actual_raw = _tabulate_raw_tensor_class(
                    compiled, kernels,
                    np.ascontiguousarray(info["actual"].reshape(-1)),
                    tag=tag, dimension=int(space.element.space_dimension),
                )
                ffcx_seconds += time.perf_counter() - t0
                actual_j, actual_det = candidate._affine_jacobian(info["actual"])
                rounded_j, rounded_det = candidate._affine_jacobian(info["rounded"])
                width_delta = info["widths_rounded"] - info["widths_actual"]
                width_delta_max = max(
                    width_delta_max, float(np.max(np.abs(width_delta), initial=0.0))
                )
                jacobian_delta_max = max(
                    jacobian_delta_max, float(np.linalg.norm(actual_j - rounded_j))
                )
                det_delta_max = max(det_delta_max, abs(float(actual_det - rounded_det)))

                actual = actual_raw.copy()
                _orient_cell_tensor(
                    space.element, actual,
                    np.asarray([perm], dtype=np.uint32),
                )
                round_ffcx, round_fast = orient_cache[perm]
                rows = info["rows"]
                x = expanded[rows]
                rhs_i = rhs[rows[interior]]
                matrices = {
                    "actual_mesh_ffcx": actual,
                    "rounded_ffcx": round_ffcx,
                    "rounded_fast": round_fast,
                }
                local_actions = {
                    name: matrix @ x for name, matrix in matrices.items()
                }
                for name, local_action in local_actions.items():
                    matrix = matrices[name]
                    add_local_action(raw_actions[name], rows, local_action)
                    for probe_name, probe_field in supplementary_fields.items():
                        add_local_action(
                            supplementary_raw_actions[name][probe_name],
                            rows,
                            matrix @ probe_field[rows],
                        )
                    vii_xi = matrix[np.ix_(interior, interior)] @ x[interior]
                    vit_xt = matrix[np.ix_(interior, trace)] @ x[trace]
                    internal[name][cell] = (
                        rhs_i - vii_xi - vit_xt - Bi_alpha[cell]
                    )

                actual_coordinates = info["actual"].reshape(-1)
                for component_name in raw_component_actions:
                    component_started = time.perf_counter()
                    component_raw = _tabulate_raw_tensor_class(
                        component_compiled[component_name],
                        component_kernels[component_name],
                        np.ascontiguousarray(actual_coordinates),
                        tag=tag,
                        dimension=int(space.element.space_dimension),
                    )
                    component_ffcx_seconds += time.perf_counter() - component_started
                    _orient_cell_tensor(
                        space.element,
                        component_raw,
                        np.asarray([perm], dtype=np.uint32),
                    )
                    add_local_action(
                        raw_component_actions[component_name],
                        rows,
                        component_raw @ x,
                    )
                    del component_raw

                for label, left_name, right_name in (
                    ("geometry_rounding", "actual_mesh_ffcx", "rounded_ffcx"),
                    ("fast_formula", "rounded_ffcx", "rounded_fast"),
                    ("total_actual_vs_fast", "actual_mesh_ffcx", "rounded_fast"),
                ):
                    left, right = matrices[left_name], matrices[right_name]
                    for support, r, c in (
                        ("ii", interior, interior),
                        ("it", interior, trace),
                        ("ti", trace, interior),
                        ("tt", trace, trace),
                    ):
                        a = left[np.ix_(r, c)]
                        b = right[np.ix_(r, c)]
                        metric = (label, support)
                        values = class_matrix_accum.setdefault(metric, [0.0, 0.0, 0.0])
                        values[0] += float(np.linalg.norm(b - a) ** 2)
                        values[1] += float(np.linalg.norm(a) ** 2)
                        values[2] = max(
                            values[2], float(np.max(np.abs(b - a), initial=0.0))
                        )
                    delta_action = local_actions[right_name] - local_actions[left_name]
                    class_action_sq[label] += float(np.vdot(delta_action, delta_action).real)

                top_actions.append(
                    {
                        "cell": int(cell),
                        "tag": tag,
                        "actual_vs_rounded_action_norm": float(
                            np.linalg.norm(local_actions["actual_mesh_ffcx"] - local_actions["rounded_ffcx"])
                        ),
                        "rounded_ffcx_vs_fast_norm": float(
                            np.linalg.norm(local_actions["rounded_fast"] - local_actions["rounded_ffcx"])
                        ),
                        "actual_vs_fast_norm": float(
                            np.linalg.norm(local_actions["actual_mesh_ffcx"] - local_actions["rounded_fast"])
                        ),
                        "actual_widths_coordinate_units": info["widths_actual"].tolist(),
                        "rounded_widths_coordinate_units": info["widths_rounded"].tolist(),
                        "rounding_delta_coordinate_units": width_delta.tolist(),
                    }
                )
                top_internal.append(
                    {
                        "cell": int(cell),
                        "tag": tag,
                        **{
                            name: float(np.linalg.norm(internal[name][cell]))
                            for name in raw_actions
                        },
                    }
                )
                del actual_raw, actual

            matrix_facts = {}
            for (label, support), (diff_sq, ref_sq, max_abs) in class_matrix_accum.items():
                matrix_facts.setdefault(label, {})[support] = {
                    "difference_fro_sum_squares_sqrt": float(np.sqrt(diff_sq)),
                    "reference_fro_sum_squares_sqrt": float(np.sqrt(ref_sq)),
                    "relative_difference": float(
                        np.sqrt(diff_sq) / max(np.sqrt(ref_sq), np.finfo(float).tiny)
                    ),
                    "max_abs_difference": max_abs,
                }
            old_hashes_match = all(
                previous_hashes.get(repr((*class_key, int(perm))), {}).get("raw_sha256")
                == candidate_hash
                for perm in orient_cache
            )
            class_facts.append(
                {
                    "tag": tag,
                    "rounded_widths_coordinate_units": [
                        float(x) for x in np.ptp(coords_rounded.reshape(8, 3), axis=0)
                    ],
                    "cell_count": len(class_cells[class_key]),
                    "candidate_raw_hash_matches_attempt4": old_hashes_match,
                    "orientation_count": len(orient_cache),
                    "max_width_rounding_delta_coordinate_units": width_delta_max,
                    "max_jacobian_rounding_delta_coordinate_units": jacobian_delta_max,
                    "max_determinant_rounding_delta_coordinate_units_cubed": det_delta_max,
                    "matrix_difference_by_local_type": matrix_facts,
                    "local_action_difference_sum_squares_sqrt": {
                        name: float(np.sqrt(value))
                        for name, value in class_action_sq.items()
                    },
                }
            )
            del ffcx_rounded, candidate_rounded, orient_cache

        mpc_action = fine["volume_action"].component_actions["curl"]

        def restrict_dual(raw: np.ndarray) -> np.ndarray:
            out = raw.copy()
            np.add.at(
                out,
                mpc_action._master_indices,
                out[mpc_action._flat_slave_indices]
                * mpc_action._conjugated_master_coefficients,
            )
            out[mpc_action._slave_indices] = 0.0
            return out

        volumes = {name: restrict_dual(raw) for name, raw in raw_actions.items()}
        component_volumes = {
            name: restrict_dual(raw) for name, raw in raw_component_actions.items()
        }
        supplementary_volumes = {
            operator: {
                probe: restrict_dual(raw)
                for probe, raw in probes.items()
            }
            for operator, probes in supplementary_raw_actions.items()
        }
        source = create_vector([(index_map, dofmap.index_map_bs)])
        owned_vectors.append(source)
        source.array[:] = solution
        native_volume = fine["volume_action"].apply(source)
        owned_vectors.append(native_volume)
        native_dtn = source.duplicate()
        owned_vectors.append(native_dtn)
        native_full = source.duplicate()
        owned_vectors.append(native_full)
        fine["dtn_action"].apply(source, native_dtn)
        fine["physical_action"].apply(source, native_full)
        native_volume_array = np.asarray(native_volume.array_r).copy()
        native_dtn_array = np.asarray(native_dtn.array_r).copy()
        native_full_array = np.asarray(native_full.array_r).copy()
        native_component_arrays = {}
        native_component_seconds = {}
        for component_name, component_action in component_actions.items():
            component_started = time.perf_counter()
            component_result = component_action.apply(source)
            native_component_seconds[component_name] = time.perf_counter() - component_started
            owned_vectors.append(component_result)
            native_component_arrays[component_name] = np.asarray(
                component_result.array_r
            ).copy()

        d_x = apply_D(expanded)
        port_residual = port_rhs + d_x - Hp @ alpha
        b_alpha = apply_B(alpha)
        effective_rhs = rhs - apply_B(np.linalg.solve(Hp, port_rhs))
        dtn_carrier = apply_B(np.linalg.solve(Hp, d_x))
        b_hp_inv_ep = apply_B(np.linalg.solve(Hp, port_residual))

        raw_residuals = {}
        for name, volume in volumes.items():
            e_fe = rhs - volume - b_alpha
            derived = e_fe - b_hp_inv_ep
            native = effective_rhs - volume - dtn_carrier
            raw_residuals[name] = {
                "native": native,
                "derived": derived,
            }

        # Compare the independent raw reconstruction to both historical paths.
        residual_comparisons = {}
        for name, values in raw_residuals.items():
            residual_comparisons[name] = {
                "raw_native_vs_saved_native": vector_difference(
                    values["native"], native_saved
                ),
                "raw_derived_vs_saved_cached_schur": vector_difference(
                    values["derived"], derived_saved
                ),
            }
        actual_native_error = (
            raw_residuals["actual_mesh_ffcx"]["native"] - native_saved
        )
        actual_derived_error = (
            raw_residuals["actual_mesh_ffcx"]["derived"] - derived_saved
        )
        raw_gap = (
            raw_residuals["actual_mesh_ffcx"]["native"]
            - raw_residuals["actual_mesh_ffcx"]["derived"]
        )
        explained_saved_delta = raw_gap - actual_native_error + actual_derived_error

        geometry_vector = volumes["actual_mesh_ffcx"] - volumes["rounded_ffcx"]
        fast_vector = volumes["rounded_ffcx"] - volumes["rounded_fast"]
        accumulation_vector = native_volume_array - volumes["actual_mesh_ffcx"]
        actual_internal = np.concatenate(internal["actual_mesh_ffcx"])
        rounded_internal = np.concatenate(internal["rounded_ffcx"])
        fast_internal = np.concatenate(internal["rounded_fast"])
        probe_rhs = {
            "interior_field_only": np.zeros_like(rhs),
            "trace_field_plus_saved_port": rhs.copy(),
        }
        probe_alpha = {
            "interior_field_only": np.zeros_like(alpha),
            "trace_field_plus_saved_port": alpha.copy(),
        }
        probe_port_rhs = {
            name: port_rhs.copy() for name in supplementary_fields
        }
        if not np.array_equal(
            probe_rhs["interior_field_only"] + probe_rhs["trace_field_plus_saved_port"],
            rhs,
        ) or not np.array_equal(
            probe_alpha["interior_field_only"] + probe_alpha["trace_field_plus_saved_port"],
            alpha,
        ):
            raise ValueError("supplementary RHS/port split does not reconstruct the saved input")
        supplementary_records = {}
        supplementary_closure = {}
        for probe_name, probe_field in supplementary_fields.items():
            probe_records_by_operator = {}
            for operator_name in raw_actions:
                probe_volume = supplementary_volumes[operator_name][probe_name]
                probe_fe = (
                    probe_rhs[probe_name]
                    - probe_volume
                    - apply_B(probe_alpha[probe_name])
                )
                probe_port = (
                    probe_port_rhs[probe_name]
                    + apply_D(probe_field)
                    - Hp @ probe_alpha[probe_name]
                )
                probe_effective_rhs = probe_rhs[probe_name] - apply_B(
                    np.linalg.solve(Hp, probe_port_rhs[probe_name])
                )
                probe_native = probe_effective_rhs - probe_volume - apply_B(
                    np.linalg.solve(Hp, apply_D(probe_field))
                )
                probe_derived = probe_fe - apply_B(
                    np.linalg.solve(Hp, probe_port)
                )
                probe_records_by_operator[operator_name] = {
                    "fe_residual": vector_facts(probe_fe),
                    "port_residual": vector_facts(probe_port),
                    "native_residual": vector_facts(probe_native),
                    "derived_residual": vector_facts(probe_derived),
                    "native_minus_derived_algebraic_closure": vector_facts(
                        probe_native - probe_derived
                    ),
                }
            supplementary_records[probe_name] = {
                "field": vector_facts(probe_field),
                "field_is_private_mpc_expanded_copy": True,
                "slave_field_norm": float(np.linalg.norm(probe_field[slaves])),
                "port_amplitudes": vector_facts(probe_alpha[probe_name]),
                "fe_rhs": vector_facts(probe_rhs[probe_name]),
                "port_rhs": vector_facts(probe_port_rhs[probe_name]),
                "operator_only_split_not_an_independent_solve": True,
                "operator_residuals": probe_records_by_operator,
            }
        for operator_name in raw_actions:
            probe_names = tuple(supplementary_fields)
            # Keep the actual vectors for closure checks; vector_facts above is
            # only the compact serialization of each supplementary residual.
            probe_fe_vectors = []
            probe_port_vectors = []
            probe_native_vectors = []
            for probe_name in probe_names:
                probe_volume = supplementary_volumes[operator_name][probe_name]
                probe_fe_vectors.append(
                    probe_rhs[probe_name]
                    - probe_volume
                    - apply_B(probe_alpha[probe_name])
                )
                probe_port_vectors.append(
                    probe_port_rhs[probe_name]
                    + apply_D(supplementary_fields[probe_name])
                    - Hp @ probe_alpha[probe_name]
                )
                probe_native_vectors.append(
                    probe_rhs[probe_name]
                    - apply_B(np.linalg.solve(Hp, probe_port_rhs[probe_name]))
                    - probe_volume
                    - apply_B(
                        np.linalg.solve(Hp, apply_D(supplementary_fields[probe_name]))
                    )
                )
            supplementary_closure[operator_name] = {
                "fe_residual_sum_vs_full": vector_difference(
                    sum(probe_fe_vectors, np.zeros_like(rhs)),
                    rhs - volumes[operator_name] - b_alpha,
                ),
                "port_residual_sum_vs_full": vector_difference(
                    sum(probe_port_vectors, np.zeros_like(port_rhs)), port_residual
                ),
                "native_residual_sum_vs_full": vector_difference(
                    sum(probe_native_vectors, np.zeros_like(rhs)),
                    raw_residuals[operator_name]["native"],
                ),
                "status": "linear decomposition closure only",
            }
        raw_component_sum = sum(
            component_volumes.values(), np.zeros_like(rhs)
        )
        native_component_sum = sum(
            native_component_arrays.values(), np.zeros_like(rhs)
        )
        raw_A6_action = volumes["actual_mesh_ffcx"] + dtn_carrier
        native_component_A6 = native_component_sum + native_dtn_array

        record["R1"] = {
            "mesh": {
                "cells": cells,
                "coordinate_unit": "nm (the input mesh coordinate scale; values kept unchanged)",
                "lambda0_nm": float(cfg.lambda0),
                "k0_per_nm": float(cfg.k0),
                "material_tag_counts": {
                    str(tag): int(np.count_nonzero(tags == tag))
                    for tag in sorted(set(map(int, tags)))
                },
                "local_tensor_dimension": int(space.element.space_dimension),
                "interior_trace_dimensions": [len(interior), len(trace)],
                "rounded_geometry_class_count": len(class_cells),
            },
            "operator_comparison": {
                "actual_vs_rounded_ffcx": "actual mesh.geometry.x coordinates versus historical 12-digit rounded canonical geometry",
                "rounded_ffcx_vs_fast": "same rounded geometry and analyzed full-form quadrature",
                "classes": class_facts,
                "attempt4_candidate_hashes": {
                    "expected_oriented_classes": len(previous_hashes),
                    "matched_classes": expected_hashes,
                    "raw_hash_matches": raw_hash_matches,
                    "oriented_hash_matches": orientation_hash_matches,
                },
                "top_cell_action_contributions": sorted(
                    top_actions,
                    key=lambda row: row["actual_vs_fast_norm"],
                    reverse=True,
                )[:10],
                "actual_cell_ffcx_seconds": ffcx_seconds,
                "actual_component_ffcx_seconds": component_ffcx_seconds,
                "fast_candidate_class_seconds": candidate_seconds,
            },
            "operator_components": {
                "curl": {
                    "raw_actual_mesh_ffcx_action": vector_facts(component_volumes["curl"]),
                    "existing_native_action": vector_facts(native_component_arrays["curl"]),
                    "raw_ffcx_minus_native": vector_difference(
                        component_volumes["curl"], native_component_arrays["curl"]
                    ),
                },
                "material_mass": {
                    "raw_actual_mesh_ffcx_action": vector_facts(
                        component_volumes["material_mass"]
                    ),
                    "existing_native_action": vector_facts(
                        native_component_arrays["material_mass"]
                    ),
                    "raw_ffcx_minus_native": vector_difference(
                        component_volumes["material_mass"],
                        native_component_arrays["material_mass"],
                    ),
                },
                "dtn": {
                    "existing_native_action": vector_facts(native_dtn_array),
                    "carrier_BHpInverseD_action": vector_facts(dtn_carrier),
                    "native_minus_carrier": vector_difference(
                        native_dtn_array, dtn_carrier
                    ),
                },
                "volume_component_sum": {
                    "raw_curl_plus_mass_vs_raw_full_volume": vector_difference(
                        raw_component_sum, volumes["actual_mesh_ffcx"]
                    ),
                    "native_curl_plus_mass_vs_native_volume": vector_difference(
                        native_component_sum, native_volume_array
                    ),
                },
                "complete_A6": {
                    "raw_ffcx_volume_plus_carrier_dtn_action": vector_facts(
                        raw_A6_action
                    ),
                    "native_fullspace_physical_action": vector_facts(
                        native_full_array
                    ),
                    "native_component_sum_plus_dtn_vs_full_action": vector_difference(
                        native_component_A6, native_full_array
                    ),
                    "raw_complete_A6_vs_native_full_action": vector_difference(
                        raw_A6_action, native_full_array
                    ),
                    "native_component_apply_seconds": native_component_seconds,
                },
            },
            "supplementary_input_decomposition": {
                "method": (
                    "two operator-only pieces of the MPC-primal-expanded saved field: "
                    "cell-interior and trace-plus-saved-port; no new solve"
                ),
                "field_sum_equals_expanded_saved": np.array_equal(
                    interior_field + trace_field, expanded
                ),
                "rhs_partition": "zero interior RHS plus original full RHS on trace-plus-port piece",
                "port_rhs_partition": "both zero, matching production default",
                "port_amplitude_partition": "zero interior amplitude plus saved alpha on trace-plus-port piece",
                "inputs": supplementary_records,
                "closure_by_operator": supplementary_closure,
            },
            "full_vector_decomposition": {
                "augmented_port_rhs": {
                    "source": "production adapter omits port_rhs; evaluator defaults to zero",
                    **vector_facts(port_rhs),
                },
                "reconstructed_effective_rhs_vs_saved": vector_difference(
                    effective_rhs, rhs_effective
                ),
                "existing_native_physical_action_vs_saved_native": vector_difference(
                    rhs - native_full_array, native_saved
                ),
                "raw_actual_volume_vs_existing_native_volume": vector_facts(
                    accumulation_vector
                ),
                "geometry_rounding_volume_vector": vector_facts(geometry_vector),
                "fast_formula_volume_vector": vector_facts(fast_vector),
                "actual_dtn_action_vs_BHpInverseD": vector_facts(
                    native_dtn_array - dtn_carrier
                ),
                "existing_physical_action_vs_raw_volume_plus_carrier_dtn": vector_facts(
                    native_full_array - (volumes["actual_mesh_ffcx"] + dtn_carrier)
                ),
                "port_residual_vs_saved": vector_difference(port_residual, port_saved),
                "raw_native_and_derived_vs_saved": residual_comparisons,
                "actual_raw_native_error": vector_facts(actual_native_error),
                "actual_raw_derived_error_vs_cached_schur": vector_facts(actual_derived_error),
                "actual_raw_native_minus_derived": vector_facts(raw_gap),
                "saved_difference_reconstructed_from_raw_errors": vector_difference(
                    explained_saved_delta, delta_saved
                ),
                "same_V_native_minus_derived_is_algebraic_closure_only": True,
            },
            "independent_internal_recovery": {
                "method": "actual mesh-geometry FFCx Vii/Vit matvec on MPC-primal-expanded saved field; rhs_i - Vii*xi - Vit*xt - Bi*alpha; no cached LU/recovery/Schur",
                "actual_mesh_ffcx": vector_facts(actual_internal),
                "rounded_geometry_ffcx": vector_facts(rounded_internal),
                "rounded_fast_candidate": vector_facts(fast_internal),
                "saved_factor_path": vector_facts(internal_saved),
                "actual_ffcx_minus_saved": vector_facts(actual_internal - internal_saved),
                "candidate_minus_saved": vector_facts(fast_internal - internal_saved),
                "Bi_nonzero_entries": Bi_count,
                "Di_nonzero_entries": Di_count,
                "top_cell_residual_norms": sorted(
                    top_internal,
                    key=lambda row: row["actual_mesh_ffcx"],
                    reverse=True,
                )[:10],
            },
            "policy_decision": {
                "decision": "pending_review_§5.2_evidence_gates",
                "strict_limit": IDENTITY_LIMIT,
                "budget_limit": 1.0e-8,
                "tolerance_not_fitted_to_observed_error": True,
            },
        }
        record["status"] = "R0_R1_diagnostic_complete"
    except BaseException as error:
        record["status"] = "R0_saved_R1_diagnostic_failed"
        record["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        for vector in owned_vectors:
            try:
                vector.destroy()
            except Exception:
                pass
        if physical is not None:
            destroy_physical_intermediate_actions(physical)
        if levels is not None:
            levels.clear()
        record["resources"] = {
            "started_utc": started_utc,
            "worker_elapsed_wall_seconds": float(time.perf_counter() - started),
            "worker_process_max_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            ) * 1024,
            "worker_rss_scope": "worker process HWM; watchdog process-tree peak is authoritative",
        }
        write_record(record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker()
        return 0

    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        supervise,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_OBSERVE_ONLY

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=False)
    source_sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    authority = supervise(
        [sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
        ARTIFACT_ROOT / "watchdog",
        wall_seconds=WATCHDOG_WALL_SECONDS,
        interval=0.25,
        grace_seconds=30.0,
        hard_stop_immediate=True,
        stop_on_global_swap=False,
        allow_swap_observation=False,
        time_policy=V14_TIME_POLICY_OBSERVE_ONLY,
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
        worker_environment={
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
        },
        source_state={
            "source_sha": source_sha,
            "purpose": "one G0 p6 local-operator diagnostic; no KSP or factor",
        },
    )
    summary = ARTIFACT_ROOT / "watchdog/summary.json"
    record = (
        json.loads(RECORD.read_text(encoding="utf-8"))
        if RECORD.is_file()
        else {"schema": "task40extra.identity-localization.v1", "R0": {}, "R1": {}}
    )
    record.setdefault("resources", {})
    record["resources"]["watchdog"] = {
        "summary_path": str(summary.relative_to(ROOT)),
        "summary_sha256": sha_file(summary),
        "classification": authority.get("classification"),
        "leader_exit_code": authority.get("leader_exit_code"),
        "elapsed_seconds": authority.get("elapsed_seconds"),
        "process_tree_peak_rss_bytes": authority.get(
            "sampled_process_tree_rss_peak_bytes"
        ),
        "process_tree_peak_swap_bytes": authority.get(
            "sampled_process_tree_swap_peak_bytes"
        ),
        "process_tree_samples": authority.get("process_tree_samples"),
        "process_tree_all_status_readable": authority.get(
            "process_tree_all_status_readable"
        ),
        "process_tree_identity_coverage": authority.get(
            "process_tree_identity_coverage"
        ),
        "descendants_cleared": authority.get("descendants_cleared"),
        "memory_policy": authority.get("memory_policy"),
        "swap_policy": authority.get("swap_policy"),
        "global_swap_activity": authority.get("global_swap_activity"),
    }
    write_record(record)
    wrapper_path = ARTIFACT_ROOT / "watchdog_wrapper_result.json"
    wrapper_temporary = wrapper_path.with_suffix(".json.tmp")
    wrapper_temporary.write_text(
        json.dumps(as_json(authority), indent=2, sort_keys=True, allow_nan=False)
        + "\n",
        encoding="utf-8",
    )
    wrapper_temporary.replace(wrapper_path)
    return 0 if authority.get("classification") == "COMPLETED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
