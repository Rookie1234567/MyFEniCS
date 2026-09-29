"""R3 V31 projection-layout component diagnostic on the frozen 990-cell model.

This bounded research tool compares legacy, natural-order, and natural-order plus
fixed z/y/x matmul projection on saved legal residuals. It performs no PDE solve,
outer KSP, p4 matrix, or p4 factorization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from collections.abc import Mapping
import resource
import subprocess
import sys
import time
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.io import load_and_resolve
from src.io.input_validation import simulation_config_3d_from_normalized
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
    build_same_mesh_physical_action,
    destroy_same_mesh_physical_action,
)
from src.solvers.physical_equivalent_fast import build_packed_physical_action
from src.solvers.physical_light_setup import build_light_h6_setup


DEFAULT_INPUT = ROOT / "input/task39extra/v30_workstation_guided_original_h7p5.dat"
DEFAULT_EARLY = ROOT / (
    "results/euv_grazing1_phi0/"
    "task39extra_v30_workstation_guided_original_h7p5_v1__full3d_iterative__mpi1__Mna/"
    "20260928T143049.147807Z/x2_residual_0000_0000.npz"
)
DEFAULT_LATE = ROOT / (
    "results/euv_grazing1_phi0/"
    "task39extra_v30_workstation_guided_original_h7p5_v1__full3d_iterative__mpi1__Mna/"
    "20260928T143049.147807Z/x2_residual_0126_0020.npz"
)
VARIANTS = (
    ("legacy", False, False),
    ("natural_order", True, False),
    ("natural_order_fixed_matmul", True, True),
)
SCHEDULE = (
    ("legacy", "natural_order", "natural_order_fixed_matmul"),
    ("natural_order_fixed_matmul", "natural_order", "legacy"),
    ("legacy", "natural_order", "natural_order_fixed_matmul"),
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, default=_json_default) + "\n"
    )
    temporary.replace(path)


def _relative_error(observed: np.ndarray, reference: np.ndarray) -> float:
    reference_norm = float(np.linalg.norm(reference))
    delta = float(np.linalg.norm(observed - reference))
    return delta if reference_norm == 0.0 else delta / reference_norm


def _load_residual(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    metadata_path = path.with_suffix(".json")
    metadata = json.loads(metadata_path.read_text())
    raw = metadata.get("raw", {}).get("native_residual", {})
    facts = metadata.get("facts", {})
    archive_facts = metadata.get("arrays", {})
    array_key = raw.get("array_key")
    if not isinstance(array_key, str):
        raise ValueError(f"native_residual array identity is missing: {metadata_path}")
    if raw.get("dtype") != "complex128" or raw.get("shape") != [667152]:
        raise ValueError(f"residual packet has an unexpected dtype/shape: {metadata_path}")
    if facts.get("rhs_is_mpc_dual") is not True:
        raise ValueError(f"residual packet lacks the MPC dual-space identity: {metadata_path}")
    if facts.get("strict_zero_slave_storage") is not True:
        raise ValueError(f"residual packet is not strict-zero-slave: {metadata_path}")
    recorded_path = Path(archive_facts.get("path", "")).resolve()
    if recorded_path != path.resolve():
        raise ValueError(f"residual archive path identity mismatch: {metadata_path}")
    archive_sha = _sha256_file(path)
    if archive_sha != archive_facts.get("sha256"):
        raise ValueError(f"residual archive SHA256 mismatch: {path}")
    with np.load(path, allow_pickle=False) as archive:
        values = np.asarray(archive[array_key], dtype=np.complex128).copy()
    if values.shape != (667152,) or not np.all(np.isfinite(values)):
        raise ValueError(f"residual vector has unexpected shape or values: {path}")
    return values, {
        "npz": str(path.resolve()),
        "npz_sha256": archive_sha,
        "metadata_json": str(metadata_path.resolve()),
        "metadata_sha256": _sha256_file(metadata_path),
        "array_key": array_key,
        "vector_sha256": _sha256_bytes(memoryview(values).cast("B")),
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "solution_source": facts.get("solution_source"),
        "rhs_is_mpc_dual": facts["rhs_is_mpc_dual"],
        "strict_zero_slave_storage": facts["strict_zero_slave_storage"],
    }


def _git_facts() -> dict[str, Any]:
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
        "head_sha_before_diagnostic": head,
        "tracked_worktree_diff_sha256": _sha256_bytes(diff),
        "solver_sha256": _sha256_file(ROOT / "src/solvers/fullspace_n1e_sum_factor.py"),
        "test_sha256": _sha256_file(ROOT / "src/test/test_362_partial_assembly.py"),
        "diagnostic_script_sha256": _sha256_file(Path(__file__).resolve()),
    }


def _timing_delta(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {
        key: float(after.get(key, 0.0) - before.get(key, 0.0))
        for key in sorted(set(before) | set(after))
    }


def _apply_b6(shell, source: PETSc.Vec) -> np.ndarray:
    borrowed = shell.action.apply(source)
    return borrowed.array.copy()


def _run_b6_h6_sample(shell, h6, source, target) -> dict[str, Any]:
    kernel = shell.action._local_kernel._sum_factorized
    before = dict(kernel.timing)
    wall_started, cpu_started = time.perf_counter(), time.process_time()
    b6 = _apply_b6(shell, source)
    b6_wall = time.perf_counter() - wall_started
    b6_cpu = time.process_time() - cpu_started
    after_b6 = dict(kernel.timing)

    wall_started, cpu_started = time.perf_counter(), time.process_time()
    facts = h6.apply_into(source, target)
    h6_values = target.array.copy()
    h6_wall = time.perf_counter() - wall_started
    h6_cpu = time.process_time() - cpu_started
    after_h6 = dict(kernel.timing)
    return {
        "b6_output": b6,
        "h6_output": h6_values,
        "b6_wall_seconds": float(b6_wall),
        "b6_cpu_seconds": float(b6_cpu),
        "h6_wall_seconds": float(h6_wall),
        "h6_cpu_seconds": float(h6_cpu),
        "b6_kernel_timing_seconds": _timing_delta(before, after_b6),
        "h6_kernel_timing_seconds": _timing_delta(after_b6, after_h6),
        "h6_matrix_mult_count": int(facts["matrix_mult_count"]),
    }


def _configure(kernel, name: str) -> None:
    settings = {item[0]: item[1:] for item in VARIANTS}
    natural, matmul = settings[name]
    kernel.configure_projection_layout_v31_candidate(
        natural_order_internal=natural,
        continuous_projection_matmul=matmul,
    )


def _compare_full_actions(
    levels,
    cfg,
    fine_bundle,
    p4_bundle,
    residuals: dict[str, np.ndarray],
) -> dict[str, Any]:
    common = {"levels": levels, "fine": fine_bundle, "p4": p4_bundle}
    a4_probe_source = "fixed_seed_nonzero_strict_slave_zero"
    candidate_bundles = {}
    vectors: dict[int, list[tuple[str, np.ndarray]]] = {
        6: [(name, value) for name, value in residuals.items()],
        4: [],
    }
    actions = {
        6: fine_bundle["physical_action"],
        4: p4_bundle["physical_action"],
    }
    layout_owners = {
        6: fine_bundle["volume_action"].component_actions["curl"],
        4: p4_bundle["volume_action"].component_actions["curl"],
    }
    try:
        for degree in (6, 4):
            candidate_bundles[degree] = build_packed_physical_action(
                common,
                cfg,
                degree=degree,
                contiguous_work=True,
                preallocated_work=False,
                sum_factorized_work=True,
                reuse_projection_work=False,
                shared_contractions=False,
                fuse_components=True,
                share_readonly_geometry=False,
            )
            if degree == 4:
                probe = layout_owners[4].matrix.createVecRight()
                rng = np.random.default_rng(39104)
                probe.array[:] = rng.normal(size=probe.getLocalSize()) + 1j * rng.normal(
                    size=probe.getLocalSize()
                )
                slaves = np.asarray(levels["floquets"][4].mpc.slaves, dtype=np.int64)
                if slaves.size:
                    probe.array[slaves] = 0.0
                vectors[4].append(("fixed_seed_probe", probe.array.copy()))
                probe.destroy()

        facts: dict[str, Any] = {}
        native_outputs: dict[int, dict[str, np.ndarray]] = {6: {}, 4: {}}
        native_times: dict[tuple[int, str], dict[str, Any]] = {}
        for degree in (6, 4):
            native_action = actions[degree]
            native_source = layout_owners[degree].matrix.createVecRight()
            native_target = layout_owners[degree].matrix.createVecLeft()
            try:
                for name, values in vectors[degree]:
                    if values.shape != (native_source.getLocalSize(),):
                        raise ValueError(
                            f"p{degree} probe layout differs from complete native action"
                        )
                    native_source.array[:] = values
                    source_before = native_source.array.copy()
                    native_action.apply(native_source, native_target)
                    native_wall_started, native_cpu_started = (
                        time.perf_counter(),
                        time.process_time(),
                    )
                    native_action.apply(native_source, native_target)
                    native_times[(degree, name)] = {
                        "wall_seconds": float(time.perf_counter() - native_wall_started),
                        "cpu_seconds": float(time.process_time() - native_cpu_started),
                        "warmup_calls_excluded": 1,
                    }
                    native_outputs[degree][name] = native_target.array.copy()
                    if not np.array_equal(native_source.array, source_before):
                        raise RuntimeError(f"native A{degree} modified its input")
            finally:
                native_source.destroy()
                native_target.destroy()

        for variant, natural, matmul in VARIANTS:
            by_degree: dict[str, Any] = {}
            for degree in (6, 4):
                candidate = candidate_bundles[degree]
                for local_kernel in candidate["kernels"]:
                    local_kernel._sum_factorized.configure_projection_layout_v31_candidate(
                        natural_order_internal=natural,
                        continuous_projection_matmul=matmul,
                    )
                candidate_action = candidate["physical_action"]
                source = layout_owners[degree].matrix.createVecRight()
                target = layout_owners[degree].matrix.createVecLeft()
                per_vector: dict[str, Any] = {}
                try:
                    for name, values in vectors[degree]:
                        source.array[:] = values
                        source_before = source.array.copy()
                        candidate_action.apply(source, target)
                        candidate_action.apply(source, target)
                        candidate_wall_started, candidate_cpu_started = (
                            time.perf_counter(),
                            time.process_time(),
                        )
                        candidate_action.apply(source, target)
                        observed = target.array.copy()
                        per_vector[name] = {
                            "relative_difference": _relative_error(
                                observed, native_outputs[degree][name]
                            ),
                            "absolute_difference_norm": float(
                                np.linalg.norm(observed - native_outputs[degree][name])
                            ),
                            "candidate_output_sha256": _sha256_bytes(
                                memoryview(np.ascontiguousarray(observed)).cast("B")
                            ),
                            "native_timing": native_times[(degree, name)],
                            "candidate_wall_seconds": float(
                                time.perf_counter() - candidate_wall_started
                            ),
                            "candidate_cpu_seconds": float(
                                time.process_time() - candidate_cpu_started
                            ),
                            "candidate_warmup_calls_excluded": 2,
                            "input_unchanged": bool(
                                np.array_equal(source.array, source_before)
                            ),
                        }
                        if not per_vector[name]["input_unchanged"]:
                            raise RuntimeError(
                                f"candidate A{degree} modified source {name}"
                            )
                finally:
                    source.destroy()
                    target.destroy()
                by_degree[f"A{degree}"] = {
                    "timing_scope": (
                        "one warmed diagnostic apply per action/vector; "
                        "not used for performance adoption"
                    ),
                    "vectors": per_vector,
                    "passes_1e-10": all(
                        value["relative_difference"] <= 1.0e-10
                        and value["input_unchanged"]
                        for value in per_vector.values()
                    ),
                    "candidate_kernel_audits": [
                        dict(kernel._sum_factorized.audit) for kernel in candidate["kernels"]
                    ],
                }
            facts[variant] = by_degree
        return {
            "action_roles": {
                "A6": "full physical action compared with independent native FFCx volume and DtN",
                "A4": "full physical verification action compared with independent native FFCx volume and DtN",
            },
            "A4_probe_source": a4_probe_source,
            "variants": facts,
        }
    finally:
        for candidate in candidate_bundles.values():
            candidate["physical_action"].destroy()


def _finalize_selection(output: dict[str, Any]) -> None:
    comparisons = output["b6_h6_pair"]["output_differences"]
    timings = output["b6_h6_pair"]["three_interleaved_rounds"]
    vector_names = tuple(output["saved_vectors"])
    algebraic_pass = all(
        comparisons[variant][name][op]["relative_difference_to_legacy"] <= 1.0e-10
        for variant, _, _ in VARIANTS
        for name in vector_names
        for op in ("b6", "h6")
    )
    power10_passes = bool(output["fresh_candidate_power10"]["passes"])
    full_action_pass = bool(output["complete_A6_A4"]["passes_1e-10"])
    output["algebraic_and_power10_gates"] = {
        "B6_and_fixed_window_H6_relative_difference_le_1e-10": bool(algebraic_pass),
        "fresh_candidate_power10_all_variants_pass": power10_passes,
        "complete_A6_A4_relative_difference_le_1e-10": full_action_pass,
    }

    timing_summary: dict[str, Any] = {}
    for variant, _, _ in VARIANTS:
        per_vector: dict[str, Any] = {}
        for vector_name in vector_names:
            selected_samples = [
                sample for sample in timings[variant]
                if sample["vector"] == vector_name
            ]
            per_vector[vector_name] = {}
            for operator in ("b6", "h6"):
                per_vector[vector_name][operator] = {}
                for metric in ("wall_seconds", "cpu_seconds"):
                    per_vector[vector_name][operator][metric] = float(
                        np.median(
                            [
                                sample[f"{operator}_{metric}"]
                                for sample in selected_samples
                            ]
                        )
                    )
        timing_summary[variant] = per_vector
    baseline = timing_summary["legacy"]
    performance_qualification: dict[str, Any] = {}
    for variant, _, _ in VARIANTS:
        ratios: dict[str, Any] = {}
        for vector_name in vector_names:
            ratios[vector_name] = {}
            for metric in ("wall_seconds", "cpu_seconds"):
                candidate_median = timing_summary[variant][vector_name]["h6"][metric]
                baseline_median = baseline[vector_name]["h6"][metric]
                ratios[vector_name][metric] = (
                    candidate_median / baseline_median
                    if baseline_median > 0.0
                    else None
                )
        baseline_by_key = {
            (sample["round"], sample["vector"]): sample
            for sample in timings["legacy"]
        }
        candidate_by_key = {
            (sample["round"], sample["vector"]): sample
            for sample in timings[variant]
        }
        paired = [
            (baseline_by_key[key], sample)
            for key, sample in candidate_by_key.items()
        ]
        paired_wall = [
            candidate["h6_wall_seconds"] < base["h6_wall_seconds"]
            for base, candidate in paired
        ]
        paired_cpu = [
            candidate["h6_cpu_seconds"] < base["h6_cpu_seconds"]
            for base, candidate in paired
        ]
        performance_qualification[variant] = {
            "h6_median_ratios_to_legacy": ratios,
            "paired_h6_wall_wins": int(sum(paired_wall)),
            "paired_h6_cpu_wins": int(sum(paired_cpu)),
            "reliable_h6_gain": bool(
                variant != "legacy"
                and all(
                    ratios[name][metric] is not None
                    and ratios[name][metric] <= 0.95
                    for name in vector_names
                    for metric in ("wall_seconds", "cpu_seconds")
                )
                and sum(paired_wall) >= 5
                and sum(paired_cpu) >= 5
            ),
        }
    reliable_candidates = [
        variant
        for variant in ("natural_order", "natural_order_fixed_matmul")
        if performance_qualification[variant]["reliable_h6_gain"]
    ]
    qualification_pass = algebraic_pass and power10_passes and full_action_pass
    selected = (
        min(
            reliable_candidates,
            key=lambda name: np.median(
                [sample["h6_wall_seconds"] for sample in timings[name]]
            ),
        )
        if qualification_pass and reliable_candidates
        else None
    )
    output["selection"] = {
        "status": "H6_CANDIDATE_SELECTED" if selected else "NOT_ADOPTED",
        "selected_variant": selected,
        "reason": (
            "candidate passed correctness and achieved at least 5% median "
            "H6 wall/CPU improvement on both saved vectors with at least "
            "5 of 6 paired wins"
            if selected
            else "no candidate met the algebraic/fresh-window gates and a "
            "repeatable H6 gain threshold"
        ),
        "r4": "REQUIRES_ONE_FORMAL_RUN" if selected else "NOT_RUN",
    }
    output["performance_summary"] = {
        "per_vector_h6_medians": timing_summary,
        "qualification": performance_qualification,
        "scope": (
            "three interleaved rounds; H6 is primary; A6/A4 single warmed "
            "apply timings are descriptive only"
        ),
    }
    output["status"] = "PASS" if qualification_pass else "FAIL"


def run(
    input_path: Path,
    early_path: Path,
    late_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise ValueError("V31 component diagnostic is qualified for MPI1 only")
    if any(
        os.environ.get(name) != "1"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("V31 component diagnostic requires three one-thread settings")
    input_path, early_path, late_path = (
        path.resolve() for path in (input_path, early_path, late_path)
    )
    early, early_fact = _load_residual(early_path)
    late, late_fact = _load_residual(late_path)
    residuals = {"early_iter0": early, "late_iter126": late}
    output: dict[str, Any] = {
        "schema": "task039extra.projection-layout-v31.components.v1",
        "status": "RUNNING",
        "diagnostic_only": True,
        "pde_solve": False,
        "outer_ksp": False,
        "p4_global_matrix_or_factor": False,
        "mpi_size": int(MPI.COMM_WORLD.size),
        "threads": {
            "OMP_NUM_THREADS": os.environ["OMP_NUM_THREADS"],
            "OPENBLAS_NUM_THREADS": os.environ["OPENBLAS_NUM_THREADS"],
            "MKL_NUM_THREADS": os.environ["MKL_NUM_THREADS"],
        },
        "command": "source scripts/activate_myfenics_wsl.sh && python -m "
        + " ".join(
            [
                "benchmarks.run_task39extra_v31_projection_layout",
                "--input", str(input_path),
                "--early-vector", str(early_path),
                "--late-vector", str(late_path),
                "--output", str(output_path.resolve()),
            ]
        ),
        "input_path": str(input_path),
        "input_sha256": _sha256_file(input_path),
        "saved_vectors": {"early_iter0": early_fact, "late_iter126": late_fact},
        "variant_order_by_round": [list(order) for order in SCHEDULE],
        "warmup_included_in_pair_samples": False,
        "maximum_interleaved_rounds": 3,
        "global_p4_factor_created": False,
        "source": _git_facts(),
    }
    _write_json(output_path, output)
    levels = None
    h6_bundle = fine_bundle = p4_bundle = None
    residual_vectors: list[PETSc.Vec] = []
    target_vectors: list[PETSc.Vec] = []
    try:
        resolved = load_and_resolve(input_path)
        output["physical_model_sha256"] = resolved.physical_model_sha256
        cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
        if int(cfg.nedelec_degree) != 6 or tuple(cfg.mesh_axis_cell_counts_requested) != (
            9,
            5,
            22,
        ):
            raise ValueError("input differs from frozen p6/h7.5 990-cell model")
        print("V31_DIAG stage=mesh_setup_started", flush=True)
        levels_started, levels_cpu = time.perf_counter(), time.process_time()
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=True
        )
        output["mesh_build"] = {
            "wall_seconds": float(time.perf_counter() - levels_started),
            "cpu_seconds": float(time.process_time() - levels_cpu),
            "cell_count": int(levels["mesh"].topology.index_map(3).size_global),
            "p6_rows": int(levels["spaces"][6].dofmap.index_map.size_global),
            "p4_rows": int(levels["spaces"][4].dofmap.index_map.size_global),
        }
        if output["mesh_build"]["cell_count"] != 990:
            raise ValueError("candidate diagnostic mesh is not 990 cells")

        def marker(_name: str, _facts: dict[str, Any]) -> None:
            return None

        print("V31_DIAG stage=fresh_h6_power10_setup_started", flush=True)
        setup_started, setup_cpu = time.perf_counter(), time.process_time()
        h6_bundle = build_light_h6_setup(
            levels,
            cfg,
            marker,
            packed_power10=True,
            packed_apply=True,
            preallocated_work=False,
            sum_factorized_work=True,
            sum_factorized_power10=True,
            direct_selected_backend=True,
            batched_target_grouping=True,
            reference_metric_diagonal=True,
        )
        output["h6_fresh_setup"] = {
            "wall_seconds": float(time.perf_counter() - setup_started),
            "cpu_seconds": float(time.process_time() - setup_cpu),
            "light_facts": h6_bundle["light_facts"],
        }
        shell, h6 = h6_bundle["p6_shell"], h6_bundle["h6"]
        kernel = shell.action._local_kernel._sum_factorized
        if (
            kernel is None
            or kernel.audit.get("backend") != "isotropic_sum_factorized_n1e_v26"
        ):
            raise RuntimeError("V30-selected H6 sum-factorized kernel is unavailable")
        # Reserve every fixed candidate buffer before timing; all variants then
        # use the same resident local workspace and the audit counts its bytes.
        kernel.configure_projection_layout_v31_candidate(
            natural_order_internal=True,
            continuous_projection_matmul=True,
        )
        kernel.configure_projection_layout_v31_candidate(
            natural_order_internal=False,
            continuous_projection_matmul=False,
        )
        output["candidate_workspace_after_reservation"] = dict(kernel.audit)
        print(
            "V31_DIAG stage=pair_started "
            f"cells={output['mesh_build']['cell_count']} "
            f"power10_mults={h6.power_matrix_mult_count}",
            flush=True,
        )
        source = shell.matrix.createVecRight()
        target = shell.matrix.createVecLeft()
        residual_vectors.extend((source, target))

        slave_dofs = np.asarray(levels["floquets"][6].mpc.slaves, dtype=np.int64)
        for label, values in residuals.items():
            if values.shape != (source.getLocalSize(),):
                raise ValueError(f"{label} saved vector has the wrong p6 size")
            if slave_dofs.size and np.count_nonzero(values[slave_dofs]):
                raise ValueError(f"{label} is not strict-zero-slave on this mesh")

        warmups = {}
        for variant, natural, matmul in VARIANTS:
            _configure(kernel, variant)
            source.array[:] = early
            started = time.perf_counter()
            warm_b6 = _apply_b6(shell, source)
            b6_wall = time.perf_counter() - started
            started = time.perf_counter()
            h6.apply_into(source, target)
            warm_h6 = target.array.copy()
            warmups[variant] = {
                "b6_wall_seconds": float(b6_wall),
                "h6_wall_seconds": float(time.perf_counter() - started),
                "b6_output_sha256": _sha256_bytes(memoryview(warm_b6).cast("B")),
                "h6_output_sha256": _sha256_bytes(memoryview(warm_h6).cast("B")),
                "included_in_samples": False,
            }
        timings: dict[str, list[dict[str, Any]]] = {
            variant[0]: [] for variant in VARIANTS
        }
        outputs: dict[str, dict[str, dict[str, np.ndarray]]] = {
            variant[0]: {label: {} for label in residuals} for variant in VARIANTS
        }
        for round_index, order in enumerate(SCHEDULE, start=1):
            for variant in order:
                _configure(kernel, variant)
                for vector_name, values in residuals.items():
                    source.array[:] = values
                    source_before = source.array.copy()
                    sample = _run_b6_h6_sample(shell, h6, source, target)
                    if not np.array_equal(source.array, source_before):
                        raise RuntimeError(f"{variant} modified saved vector {vector_name}")
                    b6_output = sample.pop("b6_output")
                    first_b6 = outputs[variant][vector_name].setdefault(
                        "b6", b6_output.copy()
                    )
                    if not np.array_equal(first_b6, b6_output):
                        raise RuntimeError("B6 output is not repeatable")
                    sample_b6_hash = _sha256_bytes(
                        memoryview(np.ascontiguousarray(b6_output)).cast("B")
                    )
                    h6_output = sample.pop("h6_output")
                    first_h6 = outputs[variant][vector_name].setdefault(
                        "h6", h6_output.copy()
                    )
                    if not np.array_equal(first_h6, h6_output):
                        raise RuntimeError("H6 output is not repeatable")
                    sample["b6_sha256"] = sample_b6_hash
                    sample["h6_sha256"] = _sha256_bytes(
                        memoryview(h6_output).cast("B")
                    )
                    sample["round"] = round_index
                    sample["vector"] = vector_name
                    timings[variant].append(sample)
        comparisons = {}
        for variant, _, _ in VARIANTS:
            comparisons[variant] = {}
            for vector_name in residuals:
                comparisons[variant][vector_name] = {}
                for operator in ("b6", "h6"):
                    baseline = outputs["legacy"][vector_name][operator]
                    observed = outputs[variant][vector_name][operator]
                    comparisons[variant][vector_name][operator] = {
                        "relative_difference_to_legacy": _relative_error(
                            observed, baseline
                        ),
                        "absolute_difference_norm": float(
                            np.linalg.norm(observed - baseline)
                        ),
                    }
        h6timing = {
            "warmups": warmups,
            "three_interleaved_rounds": timings,
            "output_differences": comparisons,
            "fresh_window": {
                "lambda_lo": float(h6.lambda_lo),
                "lambda_hi": float(h6.lambda_hi),
                "power10_matvec_count": int(h6.power_matrix_mult_count),
                "power10_seed_sha256": h6_bundle["light_facts"]["seed_sha256"],
                "inverse_sqrt_diagonal_sha256": h6_bundle["light_facts"][
                    "inverse_sqrt_diagonal_sha256"
                ],
            },
        }
        output["b6_h6_pair"] = h6timing
        _write_json(output_path, output)
        print("V31_DIAG stage=b6_h6_pair_complete", flush=True)

        from src.solvers.fullspace_lor_edge_geometric_mg_global import (
            FixedChebyshevJacobiPETSc,
        )
        from src.solvers.fullspace_lor_native_hx_fixture import (
            build_frozen_fullspace_primal_source,
        )
        seed, _seed_facts = build_frozen_fullspace_primal_source(
            levels["spaces"][6], levels["floquets"][6], cfg, "random"
        )
        seed_sha = _sha256_bytes(memoryview(seed.array).cast("B"))
        if seed_sha != h6_bundle["light_facts"]["seed_sha256"]:
            raise RuntimeError("fresh candidate power10 seed differs from V30 recipe")
        candidate_power10: dict[str, Any] = {}
        fresh_window_outputs: dict[str, dict[str, np.ndarray]] = {}
        try:
            for variant, natural, matmul in VARIANTS:
                _configure(kernel, variant)
                power_started, power_cpu = time.perf_counter(), time.process_time()
                candidate_smoother = FixedChebyshevJacobiPETSc(
                    shell.matrix, power_seed=seed
                )
                power_wall = time.perf_counter() - power_started
                power_process = time.process_time() - power_cpu
                candidate_values = {}
                try:
                    for vector_name, values in residuals.items():
                        source.array[:] = values
                        candidate_smoother.apply_into(source, target)
                        candidate_values[vector_name] = target.array.copy()
                    candidate_power10[variant] = {
                        "seed_sha256": seed_sha,
                        "power10_b6_matvec_count": int(
                            candidate_smoother.power_matrix_mult_count
                        ),
                        "lambda_lo": float(candidate_smoother.lambda_lo),
                        "lambda_hi": float(candidate_smoother.lambda_hi),
                        "power_history": list(candidate_smoother.power_history),
                        "power10_wall_seconds": float(power_wall),
                        "power10_cpu_seconds": float(power_process),
                    }
                    fresh_window_outputs[variant] = candidate_values
                finally:
                    candidate_smoother.destroy()
            legacy_outputs = fresh_window_outputs["legacy"]
            for variant in candidate_power10:
                candidate_power10[variant]["h6_outputs"] = {
                    vector_name: {
                        "sha256": _sha256_bytes(
                            memoryview(np.ascontiguousarray(value)).cast("B")
                        ),
                        "relative_difference_to_legacy_fresh_window": _relative_error(
                            value, legacy_outputs[vector_name]
                        ),
                    }
                    for vector_name, value in fresh_window_outputs[variant].items()
                }
        finally:
            seed.destroy()
        legacy_window = candidate_power10["legacy"]
        power10_passes = True
        for variant, facts in candidate_power10.items():
            hi_difference = abs(facts["lambda_hi"] - legacy_window["lambda_hi"]) / max(
                abs(legacy_window["lambda_hi"]), np.finfo(float).tiny
            )
            lo_difference = abs(facts["lambda_lo"] - legacy_window["lambda_lo"]) / max(
                abs(legacy_window["lambda_lo"]), np.finfo(float).tiny
            )
            output_differences = [
                value["relative_difference_to_legacy_fresh_window"]
                for value in facts["h6_outputs"].values()
            ]
            facts["window_relative_difference_to_legacy"] = {
                "lambda_lo": float(lo_difference),
                "lambda_hi": float(hi_difference),
            }
            facts["passes_fresh_power10_gate"] = bool(
                facts["power10_b6_matvec_count"] == 20
                and facts["seed_sha256"] == seed_sha
                and len(facts["power_history"]) == 10
                and all(np.isfinite(value) for value in facts["power_history"])
                and np.isfinite(facts["lambda_lo"])
                and np.isfinite(facts["lambda_hi"])
                and 0.0 < facts["lambda_lo"] < facts["lambda_hi"]
                and hi_difference <= 1.0e-10
                and lo_difference <= 1.0e-10
                and all(value <= 1.0e-10 for value in output_differences)
            )
            power10_passes = power10_passes and facts["passes_fresh_power10_gate"]
        output["fresh_candidate_power10"] = {
            "required_matvecs": 20,
            "same_random_seed_recipe": True,
            "same_reference_metric_diagonal": True,
            "passes": bool(power10_passes),
            "variants": candidate_power10,
        }
        _write_json(output_path, output)
        print("V31_DIAG stage=fresh_candidate_power10_complete", flush=True)

        print("V31_DIAG stage=complete_a6_a4_started", flush=True)
        full_started, full_cpu = time.perf_counter(), time.process_time()
        fine_bundle = build_same_mesh_physical_action(levels, cfg, 6)
        p4_bundle = build_same_mesh_physical_action(
            levels,
            cfg,
            4,
            mode_inventory=(
                fine_bundle["modes"],
                fine_bundle["mode_rows"],
                fine_bundle["mode_sha256"],
            ),
        )
        output["full_action_setup"] = {
            "wall_seconds": float(time.perf_counter() - full_started),
            "cpu_seconds": float(time.process_time() - full_cpu),
            "p4_global_matrix_or_factor": False,
            "A6_native_audit": dict(fine_bundle["physical_action"].audit),
            "A4_native_audit": dict(p4_bundle["physical_action"].audit),
        }
        print("V31_DIAG stage=complete_a6_a4_apply_started", flush=True)
        output["complete_A6_A4"] = _compare_full_actions(
            levels, cfg, fine_bundle, p4_bundle, residuals
        )
        output["complete_A6_A4"]["passes_1e-10"] = all(
            details["passes_1e-10"]
            for variant in output["complete_A6_A4"]["variants"].values()
            for details in variant.values()
        )
        _finalize_selection(output)
        output["resource"] = {
            "process_peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
            "candidate_workspace_audit": dict(kernel.audit),
        }
        _write_json(output_path, output)
        return output
    except BaseException as exc:
        output["status"] = "FAILED"
        output["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        _write_json(output_path, output)
        raise
    finally:
        if h6_bundle is not None:
            h6_bundle["h6"].destroy()
            h6_bundle["p6_shell"].destroy()
        if p4_bundle is not None:
            destroy_same_mesh_physical_action(p4_bundle)
        if fine_bundle is not None:
            destroy_same_mesh_physical_action(fine_bundle)
        for vector in residual_vectors:
            vector.destroy()


def complete_actions_only(
    input_path: Path,
    early_path: Path,
    late_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    if MPI.COMM_WORLD.size != 1:
        raise ValueError("V31 component diagnostic is qualified for MPI1 only")
    if any(
        os.environ.get(name) != "1"
        for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    ):
        raise ValueError("V31 component diagnostic requires three one-thread settings")
    if not output_path.is_file():
        raise ValueError("resume requires an existing B6/H6 component record")
    output = json.loads(output_path.read_text())
    if "b6_h6_pair" not in output or "fresh_candidate_power10" not in output:
        raise ValueError("saved record lacks completed B6/H6 or candidate power10")
    input_path, early_path, late_path = (
        path.resolve() for path in (input_path, early_path, late_path)
    )
    if _sha256_file(input_path) != output.get("input_sha256"):
        raise ValueError("resume input SHA differs from the saved B6/H6 record")
    output.setdefault("attempt_history", []).append(
        {
            "stage": "complete_A6_A4_first_attempt",
            "status": "FAILED",
            "error_type": "AttributeError",
            "error": "FullspacePhysicalAction has no matrix attribute; "
            "vector layout is now taken from its native volume component.",
            "b6_h6_and_power10_recorded_before_failure": True,
        }
    )
    early, early_fact = _load_residual(early_path)
    late, late_fact = _load_residual(late_path)
    output["resume_command"] = (
        "source scripts/activate_myfenics_wsl.sh && python -m "
        + " ".join(
            [
                "benchmarks.run_task39extra_v31_projection_layout",
                "--complete-actions-only",
                "--input", str(input_path),
                "--early-vector", str(early_path),
                "--late-vector", str(late_path),
                "--output", str(output_path.resolve()),
            ]
        )
    )
    output["saved_vectors"] = {
        "early_iter0": early_fact,
        "late_iter126": late_fact,
    }
    resolved = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(resolved.as_jsonable())
    levels = _build_same_mesh_levels(
        cfg, MPI.COMM_WORLD, (6, 4), include_positive_coefficients=False
    )
    if int(levels["mesh"].topology.index_map(3).size_global) != 990:
        raise ValueError("resume mesh differs from the frozen 990-cell model")
    fine_bundle = p4_bundle = None
    try:
        started, cpu_started = time.perf_counter(), time.process_time()
        fine_bundle = build_same_mesh_physical_action(levels, cfg, 6)
        p4_bundle = build_same_mesh_physical_action(
            levels,
            cfg,
            4,
            mode_inventory=(
                fine_bundle["modes"],
                fine_bundle["mode_rows"],
                fine_bundle["mode_sha256"],
            ),
        )
        output["full_action_setup"] = {
            "wall_seconds": float(time.perf_counter() - started),
            "cpu_seconds": float(time.process_time() - cpu_started),
            "p4_global_matrix_or_factor": False,
            "A6_native_audit": dict(fine_bundle["physical_action"].audit),
            "A4_native_audit": dict(p4_bundle["physical_action"].audit),
        }
        output["complete_A6_A4"] = _compare_full_actions(
            levels,
            cfg,
            fine_bundle,
            p4_bundle,
            {"early_iter0": early, "late_iter126": late},
        )
        output["complete_A6_A4"]["passes_1e-10"] = all(
            details["passes_1e-10"]
            for variant in output["complete_A6_A4"]["variants"].values()
            for details in variant.values()
        )
        _finalize_selection(output)
        output["resource"] = {
            "a6_a4_resume_process_peak_rss_bytes": int(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            ),
        }
        _write_json(output_path, output)
        return output
    except BaseException as exc:
        output.setdefault("attempt_history", []).append(
            {
                "stage": "complete_A6_A4_first_attempt",
                "status": "FAILED",
                "error_type": "AttributeError",
                "error": "FullspacePhysicalAction has no matrix attribute; "
                "diagnostic vector layout now comes from its native volume component.",
            }
        )
        output["resume_failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
        _write_json(output_path, output)
        raise
    finally:
        if p4_bundle is not None:
            destroy_same_mesh_physical_action(p4_bundle)
        if fine_bundle is not None:
            destroy_same_mesh_physical_action(fine_bundle)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--early-vector", type=Path, default=DEFAULT_EARLY)
    parser.add_argument("--late-vector", type=Path, default=DEFAULT_LATE)
    parser.add_argument("--complete-actions-only", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT
        / "docs/task039_extra_physical_multilevel/outcomes/records/"
        / "projection_layout_v31_components.json",
    )
    args = parser.parse_args()
    result = (
        complete_actions_only(
            args.input, args.early_vector, args.late_vector, args.output
        )
        if args.complete_actions_only
        else run(args.input, args.early_vector, args.late_vector, args.output)
    )
    print(
        "V31_COMPONENT_RESULT "
        f"{args.output} status={result['status']}",
        flush=True,
    )


if __name__ == "__main__":
    main()

