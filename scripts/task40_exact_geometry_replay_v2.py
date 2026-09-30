#!/usr/bin/env python3
"""Replay one saved Task40 p6 iterate through the exact-geometry local path.

This is a narrow evidence run: it rebuilds the production p6 local Schur
operator, evaluates one saved reduced iterate and its original RHS, persists
the complete vector packet, then checks three dominant local raw tensors.
It does not run an outer iteration, KSP, p4 factorization, H6 setup, or a
direct reference solve.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

INPUT = ROOT / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4.dat"
RUN = (
    ROOT / "results/task40extra_nonseparable_0p7nm/"
    "task40extra_0p7nm_nonseparable_g0_iterative_v1__full3d_iterative__mpi1__Mna/"
    "20260929T230709.246850Z"
)
COMPACT = ROOT / "docs/task40extra_0p7nm_engineering/outcomes/records/g0_attempt4_identity_gate_stop.json"
OUT = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/exact_geometry_iteration8_replay_v2"
STRICT_IDENTITY_LIMIT = 1.0e-10
STRICT_BLOCK_LIMIT = 1.0e-10


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_array(value: np.ndarray) -> str:
    value = np.ascontiguousarray(value)
    digest = hashlib.sha256(repr((value.shape, str(value.dtype))).encode())
    digest.update(memoryview(value).cast("B"))
    return digest.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    with temp.open("rb") as stream:
        os.fsync(stream.fileno())
    temp.replace(path)


def atomic_npz(path: Path, **arrays: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def _get_array(metadata: dict[str, Any], name: str, archive: Any) -> np.ndarray:
    entry = metadata[name]
    return np.asarray(archive[entry["array_key"]])


def _vec_facts(value: np.ndarray) -> dict[str, Any]:
    return {
        "shape": list(value.shape),
        "dtype": str(value.dtype),
        "sha256": sha_array(value),
        "norm_2": float(np.linalg.norm(value)),
        "max_abs": float(np.max(np.abs(value), initial=0.0)),
    }


def _relative(diff: np.ndarray, reference: np.ndarray) -> float:
    return float(
        np.linalg.norm(diff)
        / max(float(np.linalg.norm(reference)), np.finfo(float).tiny)
    )


def _watchdog_succeeded(result: Any) -> bool:
    return (
        isinstance(result, dict)
        and result.get("classification") == "COMPLETED"
        and result.get("leader_exit_code") == 0
    )


def _save_failure(record: dict[str, Any], error: BaseException) -> None:
    record["status"] = "failed"
    record["error"] = f"{type(error).__name__}: {error}"
    record["finished_utc"] = datetime.now(timezone.utc).isoformat()
    atomic_json(OUT / "replay_summary.json", record)


def worker() -> None:
    from mpi4py import MPI
    from petsc4py import PETSc
    from dolfinx import fem

    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_physical_intermediate_runtime import (
        fine_volume_quadrature_metadata,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from src.solvers.hcurl_assembly_time_condensation import (
        _cell_integral_kernels,
        _orient_cell_tensor,
        _tabulate_raw_tensor_class,
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.p6_cell_condensed_action import (
        build_p6_cell_condensed_action_from_carrier,
    )
    from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate

    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / "replay_summary.json").exists():
        raise FileExistsError(f"refusing to overwrite replay attempt: {OUT}")
    source_sha = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    record: dict[str, Any] = {
    "schema": "task40.exact_geometry_iteration8_replay.v2",
        "status": "running",
        "source_sha": source_sha,
        "script_sha256": sha_file(Path(__file__).resolve()),
        "started_utc": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "saved_iteration": 8,
            "exact_geometry": True,
            "production_raw_tensor_candidate": "Task39ExtraP6RawTensorCandidate",
            "outer_iterations": 0,
            "ksp": "not_run",
            "p4_factorization": "not_run",
            "h6": "not_run",
            "direct_reference": "not_run",
            "finite_precision_budget_B": "not_enabled",
        },
        "outputs": {},
    }
    atomic_json(OUT / "replay_summary.json", record)
    levels = fine = condensed = None
    try:
        if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
            raise RuntimeError("qualified Task40 activation is not active")
        if not str(sys.executable).endswith("/.venv/bin/python"):
            raise RuntimeError(f"unexpected Python interpreter: {sys.executable}")
        if MPI.COMM_WORLD.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
            raise RuntimeError("replay requires MPI1 and PETSc complex128")
        thread_env = {
            name: os.environ.get(name)
            for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        }
        if any(value != "1" for value in thread_env.values()):
            raise RuntimeError(f"math thread environment is not qualified: {thread_env}")
        record["environment"] = {
            "python": sys.executable,
            "activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
            "petsc_scalar_type": str(np.dtype(PETSc.ScalarType)),
            "petsc_int_type": str(np.dtype(PETSc.IntType)),
            "mpi_size": int(MPI.COMM_WORLD.size),
            "math_threads": thread_env,
        }

        compact = json.loads(COMPACT.read_text(encoding="utf-8"))
        input_sha = sha_file(INPUT)
        if input_sha != compact["input_sha256"]:
            raise ValueError("input hash differs from frozen Task40 attempt4")
        y_meta_path = RUN / "x2_y_0008.json"
        y_meta = json.loads(y_meta_path.read_text(encoding="utf-8"))
        y_path = RUN / "x2_y_0008.npz"
        if Path(y_meta["arrays"]["path"]).resolve() != y_path.resolve():
            raise ValueError("saved y metadata points to a different NPZ")
        y_npz_sha = sha_file(y_path)
        if y_npz_sha != y_meta["arrays"]["sha256"]:
            raise ValueError("saved y NPZ does not match its bound metadata hash")
        if y_meta["identity"]["degree"] != 6:
            raise ValueError("saved y metadata is not for p6")
        if y_meta["identity"]["expected_space_facts"]["active_rows"] != 68256:
            raise ValueError("saved y metadata has a different active trace size")
        if y_meta["identity"]["expected_space_facts"]["appended_rows"] != 80:
            raise ValueError("saved y metadata has a different port size")
        retained_path = RUN / "x2_retained_final.npz"
        retained_sha = sha_file(retained_path)
        if retained_sha != compact["artifacts"]["x2_retained_final_npz_sha256"]:
            raise ValueError("retained packet does not match frozen compact artifact hash")
        retained_meta = json.loads((RUN / "x2_retained_final.json").read_text(encoding="utf-8"))
        if retained_meta["identity"]["source_sha"] != compact["source_sha"]:
            raise ValueError("retained packet source SHA differs from frozen attempt4")
        if retained_meta["identity"]["physical_model_sha256"] != compact["physical_model_sha256"]:
            raise ValueError("retained packet physical identity differs from frozen attempt4")
        if y_meta["identity"]["ordered_mode_sha256"] != retained_meta["identity"]["ordered_mode_sha256"]:
            raise ValueError("saved y and retained packet use different ordered modes")
        with np.load(y_path) as saved_y:
            y = np.asarray(saved_y["array_0"], dtype=np.complex128).copy()
        with np.load(retained_path) as retained:
            rhs = _get_array(retained_meta, "original_rhs", retained).astype(np.complex128, copy=True)
        record["inputs"] = {
            "attempt4_compact_sha256": sha_file(COMPACT),
            "input_sha256": input_sha,
            "saved_y_metadata_sha256": sha_file(y_meta_path),
            "saved_y_metadata_bound_npz_sha256": y_npz_sha,
            "retained_npz_compact_bound_sha256": retained_sha,
            "saved_reduced_y": _vec_facts(y),
            "saved_original_rhs": _vec_facts(rhs),
            "saved_reduced_y_file_sha256": sha_file(RUN / "x2_y_0008.npz"),
            "saved_retained_packet_sha256": sha_file(RUN / "x2_retained_final.npz"),
            "old_identity_record_preserved": True,
            "old_rerun_02_record_preserved": True,
        }
        atomic_json(OUT / "replay_summary.json", record)

        resolved = load_and_resolve(INPUT)
        if resolved.physical_model_sha256 != compact["physical_model_sha256"]:
            raise ValueError("resolved physical model differs from frozen attempt4")
        cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
        )
        quadrature, _ = fine_volume_quadrature_metadata(levels, cfg)
        fine = build_same_mesh_physical_action(
            levels, cfg, 6, volume_quadrature_metadata=quadrature
        )
        space = levels["spaces"][6]
        carrier = fine["dtn_action"].carrier
        cells = int(levels["mesh"].topology.index_map(levels["mesh"].topology.dim).size_local)
        full_rows = int(space.dofmap.index_map.size_global)
        if cells != 336 or y.shape != (68256 + len(carrier.entries),):
            raise ValueError(
                f"saved geometry/iterate mismatch: cells={cells}, y={y.shape}, ports={len(carrier.entries)}"
            )
        if rhs.shape != (full_rows,) or full_rows != 229680:
            raise ValueError(f"saved RHS/full p6 dimensions differ: {rhs.shape}, rows={full_rows}")
        if len(carrier.entries) != 80:
            raise ValueError(f"expected 80 physical port rows, got {len(carrier.entries)}")
        if fine["mode_sha256"] != retained_meta["identity"]["ordered_mode_sha256"]:
            raise ValueError("rebuilt ordered port mode identity differs from the retained packet")

        prior_summary_path = RUN / "task40extra_nonseparable_0p7nm_p6q4_summary.json"
        prior_summary = json.loads(prior_summary_path.read_text(encoding="utf-8"))
        compiler_events = prior_summary["form_preparation"]["compiler_events"]
        p6_event = next(event for event in compiler_events if event.get("role") == "p6_condensation")
        jit_options = dict(p6_event["jit_options"])
        jit_cache = Path(jit_options["cache_dir"])
        module_facts = p6_event["module_file_facts"]
        if len(module_facts) != 1:
            raise ValueError("attempt4 p6 JIT event has an ambiguous module identity")
        module_path = Path(module_facts[0]["path"])
        if not module_path.is_file() or sha_file(module_path) != module_facts[0]["sha256"]:
            raise ValueError("identity-qualified attempt4 p6 JIT module is absent or changed")
        if module_path.parent != jit_cache:
            raise ValueError("attempt4 p6 JIT module is outside its recorded cache")
        cache_before = {
            str(path.relative_to(jit_cache)): sha_file(path)
            for path in sorted(jit_cache.rglob("*"))
            if path.is_file()
        }
        compiled = fem.form(
            fine["volume_action"].bilinear_form,
            form_compiler_options={"scalar_type": PETSc.ScalarType},
            jit_options=jit_options,
        )
        cache_after = {
            str(path.relative_to(jit_cache)): sha_file(path)
            for path in sorted(jit_cache.rglob("*"))
            if path.is_file()
        }
        if cache_after != cache_before:
            raise RuntimeError("p6 form did not reuse the identity-qualified JIT cache unchanged")
        if np.dtype(compiled.dtype) != np.dtype(np.complex128):
            raise TypeError("reused p6 compiled form is not complex128")
        record["jit_cache"] = {
            "path": str(jit_cache),
            "module_path": str(module_path),
            "module_sha256": module_facts[0]["sha256"],
            "jit_options": jit_options,
            "form_compiler_options": {"scalar_type": "complex128"},
            "inventory_unchanged_across_form_load": True,
            "identity_qualified_reuse": True,
        }
        evaluator = Task39ExtraP6RawTensorCandidate(
            space.element.basix_element,
            cfg,
            fine["volume_action"].bilinear_form,
            compiled_form=compiled,
        )
        condensed = build_unconstrained_assembly_time_condensation(
            compiled,
            space,
            levels["mesh_data"].cell_tags,
            mpc=levels["floquets"][6].mpc,
            appended_global_rows=len(carrier.entries),
            sum_duplicate_cell_integrals=True,
            strict_local_checks=True,
            materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True,
            share_identity_cache=True,
            preserve_exact_geometry=True,
            raw_tensor_evaluator=evaluator,
        )
        action = build_p6_cell_condensed_action_from_carrier(condensed, carrier)

        def native_apply(field: np.ndarray) -> np.ndarray:
            source = PETSc.Vec().createSeq(full_rows, comm=PETSc.COMM_SELF)
            target = PETSc.Vec().createSeq(full_rows, comm=PETSc.COMM_SELF)
            try:
                source.array[:] = field
                fine["physical_action"].apply(source, target)
                return target.array.copy()
            finally:
                source.destroy()
                target.destroy()

        # The stored Schur residual is intentionally not reused; it is freshly
        # evaluated from the exact-geometry local action for this saved y.
        evaluation = action.evaluate_native_residual(
            y,
            rhs,
            native_apply,
            rhs_is_mpc_dual=True,
            reduced_residual=None,
        )
        packet = {
            "saved_reduced_y": y,
            "original_rhs": rhs,
            **{
                name: np.asarray(evaluation[name])
                for name in (
                    "storage_solution",
                    "native_effective_rhs",
                    "native_residual",
                    "augmented_fe_residual",
                    "augmented_port_residual",
                    "internal_residual",
                    "schur_residual",
                    "schur_residual_injection",
                    "schur_port_residual",
                    "port_internal_correction",
                    "schur_port_identity_difference",
                    "derived_native_residual",
                    "native_identity_difference",
                    "hp_inverse_Dx",
                    "retained_alpha",
                )
            },
        }
        packet_path = OUT / "iteration8_exact_geometry_vectors.npz"
        atomic_npz(packet_path, **packet)
        record["residual_evaluation"] = {
            key: value
            for key, value in evaluation.items()
            if not isinstance(value, np.ndarray)
        }
        record["residual_evaluation"]["vectors_packet_sha256"] = sha_file(packet_path)
        record["residual_evaluation"]["vectors_saved_before_raw_spotchecks"] = True
        record["residual_evaluation"]["vector_facts"] = {
            name: _vec_facts(array)
            for name, array in packet.items()
        }
        record["status"] = "residual_saved_raw_checks_pending"
        atomic_json(OUT / "replay_summary.json", record)

        # Select the three dominant cells already identified by R1.  Their
        # identities are frozen here so a replay never scans/classifies cells.
        chosen_cells = (22, 21, 61)
        mesh = levels["mesh"]
        mesh.topology.create_entity_permutations()
        permutations = mesh.topology.get_cell_permutation_info()
        tags = np.full(cells, -1, dtype=np.int32)
        cell_tags = levels["mesh_data"].cell_tags
        tags[np.asarray(cell_tags.indices, dtype=np.int32)] = np.asarray(
            cell_tags.values, dtype=np.int32
        )
        if np.any(tags < 0):
            raise ValueError("incomplete cell tag map during local spot-check")
        basix = space.element.basix_element
        interior = np.asarray(basix.entity_dofs[3][0], dtype=np.int32)
        trace = np.setdiff1d(
            np.arange(int(space.element.space_dimension), dtype=np.int32),
            interior,
            assume_unique=True,
        )
        kernels = _cell_integral_kernels(
            compiled, sum_duplicate_cell_integrals=True
        )
        checks = []
        internal_segments: dict[tuple[int, ...], np.ndarray] = {}
        internal_offset = 0
        for action_cell in action._cells:
            cell_rows = np.asarray(action_cell.original_interiors, dtype=np.int64)
            cell_key = tuple(map(int, cell_rows))
            count = len(cell_rows)
            internal_segments[cell_key] = np.asarray(
                evaluation["internal_residual"][internal_offset:internal_offset + count]
            )
            internal_offset += count
        recovered = np.asarray(evaluation["storage_solution"], dtype=np.complex128)
        alpha = np.asarray(evaluation["retained_alpha"], dtype=np.complex128)
        local_dofmap = space.dofmap
        local_to_global = local_dofmap.index_map.local_to_global
        floquet = levels["floquets"][6]
        expanded_function = fem.Function(space)
        expanded_function.x.array[:] = recovered
        expanded_function.x.scatter_forward()
        floquet.mpc.homogenize(expanded_function)
        floquet.mpc.backsubstitution(expanded_function)
        expanded_function.x.scatter_forward()
        expanded = np.asarray(expanded_function.x.array, dtype=np.complex128).copy()
        for cell in chosen_cells:
            geometry_dofs = np.asarray(mesh.geometry.dofmap[cell], dtype=np.int32)
            actual_coordinates = np.ascontiguousarray(
                mesh.geometry.x[geometry_dofs], dtype=np.float64
            ).reshape(8, 3)
            widths = np.ptp(actual_coordinates, axis=0)
            tag = int(tags[cell])
            candidate_raw = evaluator.build(
                np.ascontiguousarray(actual_coordinates.reshape(-1)),
                tag=tag,
                dimension=int(space.element.space_dimension),
            )
            ffcx_raw = _tabulate_raw_tensor_class(
                compiled,
                kernels,
                np.ascontiguousarray(actual_coordinates.reshape(-1)),
                tag=tag,
                dimension=int(space.element.space_dimension),
            )
            permutation = np.asarray([permutations[cell]], dtype=np.uint32)
            candidate_oriented = candidate_raw.copy()
            ffcx_oriented = ffcx_raw.copy()
            _orient_cell_tensor(space.element, candidate_oriented, permutation)
            _orient_cell_tensor(space.element, ffcx_oriented, permutation)
            local_dofs = np.asarray(local_dofmap.cell_dofs(cell), dtype=np.int32)
            rows = np.asarray(local_to_global(local_dofs), dtype=np.int64)
            if not np.array_equal(rows, local_dofs):
                raise ValueError("MPI1 selected cell local/global row maps differ")
            local_field = expanded[rows]
            interior_rows = rows[interior]
            rhs_i = rhs[interior_rows]
            interior_row_to_position = {
                int(row): int(i) for i, row in enumerate(interior_rows)
            }
            bi_alpha = np.zeros(len(interior), dtype=np.complex128)
            for port, entry in enumerate(carrier.entries):
                b_rows = np.asarray(entry.coupling_rows, dtype=np.int64)
                b_values = np.asarray(entry.coupling_values, dtype=np.complex128)
                for row, value in zip(b_rows, b_values, strict=True):
                    position = interior_row_to_position.get(int(row))
                    if position is not None:
                        bi_alpha[position] += value * alpha[port]
            vii_ui = ffcx_oriented[np.ix_(interior, interior)] @ local_field[interior]
            vit_ut = ffcx_oriented[np.ix_(interior, trace)] @ local_field[trace]
            raw_internal_residual = rhs_i - vii_ui - vit_ut - bi_alpha
            raw_internal_scale = (
                float(np.linalg.norm(rhs_i))
                + float(np.linalg.norm(vii_ui))
                + float(np.linalg.norm(vit_ut))
                + float(np.linalg.norm(bi_alpha))
            )
            raw_internal_relative = float(
                np.linalg.norm(raw_internal_residual)
                / max(raw_internal_scale, np.finfo(float).tiny)
            )
            action_segment = internal_segments.get(tuple(map(int, interior_rows)))
            if action_segment is None:
                raise ValueError(f"production action has no internal residual segment for cell {cell}")
            action_internal_difference = _relative(
                raw_internal_residual - action_segment,
                np.asarray([raw_internal_scale], dtype=np.float64),
            )
            blocks = {}
            for label, rows, columns in (
                ("ii", interior, interior),
                ("it", interior, trace),
                ("ti", trace, interior),
                ("tt", trace, trace),
            ):
                expected = ffcx_oriented[np.ix_(rows, columns)]
                actual = candidate_oriented[np.ix_(rows, columns)]
                blocks[label] = {
                    "relative_frobenius_error": _relative(actual - expected, expected),
                    "max_abs_error": float(np.max(np.abs(actual - expected), initial=0.0)),
                }
            raw_error = _relative(candidate_raw - ffcx_raw, ffcx_raw)
            oriented_error = _relative(candidate_oriented - ffcx_oriented, ffcx_oriented)
            checks.append({
                "cell": int(cell),
                "tag": tag,
                "widths_exact": [float(v) for v in widths],
                "actual_geometry_coordinates_sha256": sha_array(actual_coordinates),
                "permutation": int(permutations[cell]),
                "raw_relative_frobenius_error": raw_error,
                "oriented_relative_frobenius_error": oriented_error,
                "blocks": blocks,
                "local_recovery_equation": {
                    "rhs_interior_norm": float(np.linalg.norm(rhs_i)),
                    "rhs_interior_nonzero_count": int(np.count_nonzero(rhs_i)),
                    "Vii_ui_norm": float(np.linalg.norm(vii_ui)),
                    "Vit_ut_norm": float(np.linalg.norm(vit_ut)),
                    "Bi_alpha_norm": float(np.linalg.norm(bi_alpha)),
                    "Bi_alpha_nonzero_count": int(np.count_nonzero(bi_alpha)),
                    "raw_internal_residual_relative": raw_internal_relative,
                    "difference_from_action_internal_residual_relative": action_internal_difference,
                    "pass": (
                        raw_internal_relative <= STRICT_BLOCK_LIMIT
                        and action_internal_difference <= STRICT_BLOCK_LIMIT
                        and np.count_nonzero(rhs_i) > 0
                        and np.count_nonzero(bi_alpha) > 0
                    ),
                },
                "pass": (
                    raw_error <= STRICT_BLOCK_LIMIT
                    and oriented_error <= STRICT_BLOCK_LIMIT
                    and all(
                        values["relative_frobenius_error"] <= STRICT_BLOCK_LIMIT
                        for values in blocks.values()
                    )
                    and raw_internal_relative <= STRICT_BLOCK_LIMIT
                    and action_internal_difference <= STRICT_BLOCK_LIMIT
                    and np.count_nonzero(rhs_i) > 0
                    and np.count_nonzero(bi_alpha) > 0
                ),
            })
        record["raw_tensor_spotchecks"] = {
            "reference": "independent FFCx tabulation on actual mesh geometry from the production compiled form",
            "checked_cells": checks,
            "count": len(checks),
            "all_passed": all(item["pass"] for item in checks),
        }
        metrics = record["residual_evaluation"]
        record["iteration8_port_residual"] = {
            "relative": metrics["port_residual_relative"],
            "norm": float(np.linalg.norm(evaluation["augmented_port_residual"])),
            "interpretation": "saved mid-iteration residual; reported separately and not a geometry gate",
            "final_solve_closure_gate_applied": False,
        }
        strict_pass = (
            metrics["native_identity_relative"] <= STRICT_IDENTITY_LIMIT
            and metrics["internal_residual_relative"] <= STRICT_IDENTITY_LIMIT
            and metrics["schur_port_identity_relative"] <= STRICT_IDENTITY_LIMIT
            and record["raw_tensor_spotchecks"]["all_passed"]
        )
        record["strict_geometry_replay_passed"] = bool(strict_pass)
        record["full_physical_residual_is_convergence_gate"] = False
        record["status"] = "strict_pass" if strict_pass else "strict_fail"
        record["finished_utc"] = datetime.now(timezone.utc).isoformat()
        atomic_json(OUT / "replay_summary.json", record)
    except BaseException as error:
        _save_failure(record, error)
        raise
    finally:
        if condensed is not None:
            destroy = getattr(condensed, "destroy", None)
            if callable(destroy):
                destroy()
        if fine is not None:
            destroy_same_mesh_physical_action(fine)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--self-check-watchdog-contract", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_check_watchdog_contract:
        mock = {"classification": "COMPLETED", "leader_exit_code": 0}
        assert _watchdog_succeeded(mock)
        assert not _watchdog_succeeded({"classification": "WORKER_FAILED", "leader_exit_code": 0})
        print("mock watchdog COMPLETED/leader_exit_code=0 contract passed")
        return
    if args.worker:
        worker()
        return
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        supervise,
    )
    from src.runners.physical_v14_budget import V14_TIME_POLICY_OBSERVE_ONLY

    if OUT.exists():
        raise FileExistsError(f"refusing to overwrite replay attempt: {OUT}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    result = supervise(
        [sys.executable, "-u", str(Path(__file__).resolve()), "--worker"],
        OUT / "watchdog",
        wall_seconds=18000.0,
        interval=0.5,
        grace_seconds=30,
        hard_stop_immediate=True,
        stop_on_global_swap=False,
        allow_swap_observation=False,
        time_policy=V14_TIME_POLICY_OBSERVE_ONLY,
        memory_policy=PHYSICAL_MEMORY_PRESSURE_POLICY,
        pss_sampling_policy="disabled_by_profile",
        phase_path=OUT / "watchdog" / "workflow_phase.json",
    )
    atomic_json(OUT / "watchdog_wrapper_result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    if not _watchdog_succeeded(result):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
