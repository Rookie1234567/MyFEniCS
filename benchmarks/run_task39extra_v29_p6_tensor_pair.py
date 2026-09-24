"""Compare the p6 blocked raw-tensor candidate on the live 990-cell mesh.

This component run builds the exact fine mesh/form and local tensor classes,
but it does not build a p4 matrix/factor, solve a PDE, or enter outer KSP.
"""

from __future__ import annotations

import argparse
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
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lu_factor, lu_solve

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_physical_intermediate_runtime import (
    fine_volume_quadrature_metadata,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
from src.solvers.hcurl_assembly_time_condensation import (
    _canonical_axis_aligned_coordinates,
    _cell_integral_kernels,
    _cell_tag_array,
    _tabulate_raw_tensor_class,
)
from src.solvers.task39extra_p6_raw_tensor import Task39ExtraP6RawTensorCandidate


DEFAULT_INPUT = ROOT / "input/task39extra/v28_fused_kernel_original_h7p5.dat"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha256(array: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(array)).cast("B")).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _git_facts() -> dict[str, str]:
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    diff = subprocess.run(
        ["git", "diff", "--binary", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    return {
        "head_sha": head,
        "tracked_worktree_diff_sha256": hashlib.sha256(diff).hexdigest(),
        "candidate_solver_sha256": _sha256(
            ROOT / "src/solvers/task39extra_p6_raw_tensor.py"
        ),
        "pair_runner_sha256": _sha256(Path(__file__).resolve()),
    }


def _form_with_metadata(form: Any, metadata: dict[str, Any]):
    import ufl

    return ufl.Form(
        tuple(
            integral.reconstruct(
                metadata={**(integral.metadata() or {}), **metadata}
            )
            for integral in form.integrals()
        )
    )


def _relative_error(observed: np.ndarray, reference: np.ndarray) -> float:
    denominator = max(float(np.linalg.norm(reference)), np.finfo(float).tiny)
    return float(np.linalg.norm(observed - reference) / denominator)


def _local_checks(
    native: np.ndarray,
    candidate: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    seed: int,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    dimension = native.shape[0]
    vector = rng.normal(size=dimension) + 1j * rng.normal(size=dimension)
    internal_rhs = rng.normal(size=len(interior_positions)) + 1j * rng.normal(
        size=len(interior_positions)
    )
    trace = rng.normal(size=len(trace_positions)) + 1j * rng.normal(
        size=len(trace_positions)
    )
    matrix_relative = _relative_error(candidate, native)
    action_relative = _relative_error(candidate @ vector, native @ vector)

    def schur_and_recovery(matrix: np.ndarray):
        Aii = matrix[np.ix_(interior_positions, interior_positions)]
        Ait = matrix[np.ix_(interior_positions, trace_positions)]
        Ati = matrix[np.ix_(trace_positions, interior_positions)]
        Att = matrix[np.ix_(trace_positions, trace_positions)]
        factor = lu_factor(Aii, check_finite=False)
        interior_from_trace = -lu_solve(factor, Ait, check_finite=False)
        schur = Att + Ati @ interior_from_trace
        recovered = lu_solve(
            factor,
            internal_rhs - Ait @ trace,
            check_finite=False,
        )
        closure = _relative_error(Aii @ recovered + Ait @ trace, internal_rhs)
        return schur, interior_from_trace, recovered, closure

    native_schur, native_recovery, native_solution, native_closure = schur_and_recovery(native)
    candidate_schur, candidate_recovery, candidate_solution, candidate_closure = schur_and_recovery(candidate)
    return {
        "matrix_frobenius_relative": matrix_relative,
        "action_relative": action_relative,
        "schur_relative": _relative_error(candidate_schur, native_schur),
        "recovery_map_relative": _relative_error(candidate_recovery, native_recovery),
        "nonzero_rhs_recovery_solution_relative": _relative_error(
            candidate_solution, native_solution
        ),
        "native_nonzero_rhs_recovery_closure": native_closure,
        "candidate_nonzero_rhs_recovery_closure": candidate_closure,
    }


def run(input_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists() or output_path.with_suffix(output_path.suffix + ".partial").exists():
        raise FileExistsError(f"refusing to overwrite p6 tensor evidence at {output_path}")
    if MPI.COMM_WORLD.size != 1:
        raise RuntimeError("the reviewed p6 tensor component pair is MPI1-only")
    source_sha = _git_facts()
    result: dict[str, Any] = {
        "schema": "task39extra.v29.p6-raw-tensor-pair.v1",
        "status": "STARTED",
        "official_pde": False,
        "global_p4_matrix_or_factor": False,
        "input_path": str(input_path.resolve()),
        "input_sha256": _sha256(input_path),
        "source": source_sha,
        "classes_completed": [],
        "qualification": {"adopt_candidate": False},
    }
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    _write_json(partial_path, result)
    try:
        resolved = load_and_resolve(input_path)
        result["physical_model_sha256"] = resolved.physical_model_sha256
        cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
        if int(cfg.nedelec_degree) != 6 or tuple(cfg.mesh_axis_cell_counts_requested) != (9, 5, 22):
            raise ValueError("p6 tensor pair input differs from the frozen 990-cell h7.5 mesh")

        started = time.perf_counter()
        levels = _build_same_mesh_levels(
            cfg,
            MPI.COMM_WORLD,
            (6,),
            include_positive_coefficients=False,
        )
        result["mesh_build_seconds"] = float(time.perf_counter() - started)
        result["owned_cell_count"] = int(levels["mesh"].topology.index_map(3).size_local)

        quadrature_metadata, quadrature_records = fine_volume_quadrature_metadata(
            levels, cfg
        )
        result["official_split_quadrature_metadata"] = [dict(item) for item in quadrature_metadata]
        result["official_split_quadrature_records"] = list(quadrature_records)

        import ufl
        from dolfinx import fem
        from src.solvers.common_3d_forms import _build_physical_volume_terms

        space = levels["spaces"][6]
        mesh = levels["mesh"]
        dx = ufl.Measure("dx", domain=mesh, subdomain_data=levels["mesh_data"].cell_tags)
        curl_form, mass_form = _build_physical_volume_terms(
            cfg, ufl.TrialFunction(space), ufl.TestFunction(space), dx
        )
        curl_form = _form_with_metadata(curl_form, dict(quadrature_metadata[0]))
        mass_form = _form_with_metadata(mass_form, dict(quadrature_metadata[1]))
        full_form = curl_form + mass_form
        form_started = time.perf_counter()
        compiled = fem.form(full_form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
        result["complete_form_compile_seconds"] = float(time.perf_counter() - form_started)
        result["ufcx_form_signature"] = compiled.module.ffi.string(
            compiled.ufcx_form.signature
        ).decode("ascii")
        kernels = _cell_integral_kernels(
            compiled, sum_duplicate_cell_integrals=True
        )
        result["ffcx_kernel_inventory"] = {
            str(tag): len(value) if isinstance(value, (tuple, list)) else 1
            for tag, value in sorted(kernels.items())
        }
        builder = Task39ExtraP6RawTensorCandidate(
            space.element.basix_element,
            cfg,
            full_form,
            compiled_form=compiled,
        )
        result["candidate_analysis"] = builder.audit()

        tags = _cell_tag_array(
            levels["mesh_data"].cell_tags,
            int(mesh.topology.index_map(3).size_local),
        )
        local_classes: dict[tuple[Any, ...], np.ndarray] = {}
        for cell in range(len(tags)):
            coordinates, widths = _canonical_axis_aligned_coordinates(
                mesh, cell, tolerance=1.0e-11
            )
            key = (int(tags[cell]), *widths)
            previous = local_classes.get(key)
            if previous is not None and not np.array_equal(previous, coordinates):
                raise RuntimeError(f"live mesh class {key!r} has inconsistent canonical geometry")
            local_classes.setdefault(key, coordinates)
        result["raw_class_count"] = len(local_classes)
        result["cell_count_to_raw_class_ratio"] = float(
            len(tags) / max(len(local_classes), 1)
        )

        basix_element = space.element.basix_element
        interior = np.asarray(basix_element.entity_dofs[3][0], dtype=np.int32)
        trace = np.setdiff1d(np.arange(int(space.element.space_dimension), dtype=np.int32), interior)
        started_pair = time.perf_counter()
        passed = True
        for index, key in enumerate(sorted(local_classes), start=1):
            tag, *widths = key
            coordinates = local_classes[key]
            native_started = time.perf_counter()
            native = _tabulate_raw_tensor_class(
                compiled,
                kernels,
                coordinates,
                tag=int(tag),
                dimension=int(space.element.space_dimension),
            )
            native_seconds = float(time.perf_counter() - native_started)
            candidate_started = time.perf_counter()
            candidate = builder(
                compiled,
                kernels,
                coordinates,
                tag=int(tag),
                dimension=int(space.element.space_dimension),
            )
            candidate_seconds = float(time.perf_counter() - candidate_started)
            checks = _local_checks(native, candidate, interior, trace, 39000 + index)
            class_pass = (
                checks["matrix_frobenius_relative"] <= 1.0e-10
                and checks["action_relative"] <= 1.0e-10
                and checks["schur_relative"] <= 1.0e-8
                and checks["recovery_map_relative"] <= 1.0e-8
                and checks["nonzero_rhs_recovery_solution_relative"] <= 1.0e-8
                and checks["native_nonzero_rhs_recovery_closure"] <= 1.0e-8
                and checks["candidate_nonzero_rhs_recovery_closure"] <= 1.0e-8
            )
            passed = passed and class_pass
            record = {
                "index": index,
                "class_key": {"tag": int(tag), "cell_widths": [float(x) for x in widths]},
                "native_ffcx_seconds": native_seconds,
                "candidate_seconds": candidate_seconds,
                "native_matrix_sha256": _array_sha256(native),
                "candidate_matrix_sha256": _array_sha256(candidate),
                "checks": checks,
                "passed": class_pass,
            }
            result["classes_completed"].append(record)
            result["elapsed_pair_seconds"] = float(time.perf_counter() - started_pair)
            result["qualification"] = {
                "all_completed_classes_pass": passed,
                "matrix_relative_limit": 1.0e-10,
                "action_relative_limit": 1.0e-10,
                "schur_and_recovery_limit": 1.0e-8,
                "adopt_candidate": False,
            }
            _write_json(partial_path, result)
            print(
                "P3_CLASS "
                f"{index}/{len(local_classes)} tag={tag} widths={tuple(widths)} "
                f"native={native_seconds:.6f}s candidate={candidate_seconds:.6f}s "
                f"matrix_rel={checks['matrix_frobenius_relative']:.3e} "
                f"schur_rel={checks['schur_relative']:.3e} pass={class_pass}",
                flush=True,
            )
            del native, candidate

        candidate_times = [row["candidate_seconds"] for row in result["classes_completed"]]
        native_times = [row["native_ffcx_seconds"] for row in result["classes_completed"]]
        result["timing_summary"] = {
            "native_all_classes_seconds": float(sum(native_times)),
            "candidate_all_classes_seconds": float(sum(candidate_times)),
            "all_class_ratio_candidate_over_native": float(
                sum(candidate_times) / max(sum(native_times), np.finfo(float).tiny)
            ),
            "native_seconds_by_class": native_times,
            "candidate_seconds_by_class": candidate_times,
        }
        result["candidate_analysis"] = builder.audit()
        representative = result["classes_completed"][0]
        representative_key = sorted(local_classes)[0]
        representative_coordinates = local_classes[representative_key]
        representative_tag = int(representative_key[0])
        representative_pairs = [
            {
                "repeat": 1,
                "native_ffcx_seconds": representative["native_ffcx_seconds"],
                "candidate_seconds": representative["candidate_seconds"],
                "first_call": "native_then_candidate",
            }
        ]
        for repeat, order in (
            (2, ("candidate", "native")),
            (3, ("native", "candidate")),
        ):
            sample = {"repeat": repeat, "first_call": f"{order[0]}_then_{order[1]}"}
            for implementation in order:
                call_started = time.perf_counter()
                if implementation == "native":
                    tensor = _tabulate_raw_tensor_class(
                        compiled,
                        kernels,
                        representative_coordinates,
                        tag=representative_tag,
                        dimension=int(space.element.space_dimension),
                    )
                    sample["native_ffcx_seconds"] = float(
                        time.perf_counter() - call_started
                    )
                else:
                    tensor = builder(
                        compiled,
                        kernels,
                        representative_coordinates,
                        tag=representative_tag,
                        dimension=int(space.element.space_dimension),
                    )
                    sample["candidate_seconds"] = float(
                        time.perf_counter() - call_started
                    )
                del tensor
            representative_pairs.append(sample)
        result["representative_paired_timing"] = {
            "class_key": dict(representative["class_key"]),
            "samples": representative_pairs,
            "native_median_seconds": float(
                np.median([row["native_ffcx_seconds"] for row in representative_pairs])
            ),
            "candidate_median_seconds": float(
                np.median([row["candidate_seconds"] for row in representative_pairs])
            ),
        }
        result["candidate_workspace_bytes_upper"] = int(builder.workspace_bytes_upper)
        result["process_peak_rss_bytes"] = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
        numerical_pass = bool(
            passed and len(result["classes_completed"]) == len(local_classes)
        )
        all_class_speed_gain = bool(
            result["timing_summary"]["candidate_all_classes_seconds"]
            < result["timing_summary"]["native_all_classes_seconds"]
        )
        representative_speed_gain = bool(
            result["representative_paired_timing"]["candidate_median_seconds"]
            < result["representative_paired_timing"]["native_median_seconds"]
        )
        result["qualification"] = {
            "numerically_qualified": numerical_pass,
            "all_completed_classes_pass": numerical_pass,
            "all_class_speed_gain": all_class_speed_gain,
            "representative_speed_gain": representative_speed_gain,
            "matrix_relative_limit": 1.0e-10,
            "action_relative_limit": 1.0e-10,
            "schur_and_recovery_limit": 1.0e-8,
            "adopt_candidate": bool(
                numerical_pass and all_class_speed_gain and representative_speed_gain
            ),
        }
        result["status"] = (
            "QUALIFIED"
            if result["qualification"]["adopt_candidate"]
            else "NOT_QUALIFIED"
        )
        result["official_pde"] = False
        _write_json(output_path, result)
        partial_path.unlink()
        return result
    except BaseException as error:
        result["status"] = "FAILED_OR_UNSUPPORTED"
        result["failure"] = f"{type(error).__name__}: {error}"
        _write_json(partial_path, result)
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.input, args.output)
    print(
        "P3_RESULT "
        f"{args.output} status={result['status']} "
        f"adopt_candidate={result['qualification']['adopt_candidate']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
