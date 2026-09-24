"""One H6-only pair for a stacked real/imaginary coefficient layout."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
H6_REFERENCE_DIR = (
    ROOT / "benchmarks/artifacts/task39extra/fused_operator_speed_v28"
)
if str(H6_REFERENCE_DIR) not in sys.path:
    sys.path.insert(0, str(H6_REFERENCE_DIR))

import s1_v28_fused_kernel_pair as pair


INPUT = ROOT / "input/task39extra/v28_fused_kernel_original_h7p5_post_repair.dat"


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(output: Path) -> dict:
    from mpi4py import MPI
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
        _build_same_mesh_levels,
    )
    from src.solvers.physical_light_setup import build_light_h6_setup
    from src.runners.physical_p4_schur_v14 import _new_storage_vector

    if MPI.COMM_WORLD.size != 1:
        raise ValueError("H6 transform pair is qualified for MPI1 only")
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    specification = load_and_resolve(INPUT)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    source = pair._source_identity()
    source["h6_transform_pair_script_sha256"] = _file_sha(Path(__file__))
    helper_path = Path(pair.__file__).resolve()
    source["helper_dependencies"] = [
        {
            "module": pair.__name__,
            "path": str(helper_path),
            "sha256": _file_sha(helper_path),
        }
    ]
    result = {
        "schema": "task039extra.v29.h6-stacked-real-imag-pair.v1",
        "classification": "component_pair_only_no_p4_factor_no_formal_pde",
        "input": {
            "path": str(INPUT),
            "input_sha256": specification.input_sha256,
            "physical_model_sha256": specification.physical_model_sha256,
        },
        "source": source,
        "candidate": {
            "strategy": "stack_real_then_imag_into_one_bounded_real_gemm",
            "sum_factorized_shared_contractions": False,
            "changes_h6_math": False,
        },
        "baseline": {
            "strategy": "two_real_gemms_for_real_and_imaginary_parts",
            "sum_factorized_shared_contractions": False,
        },
        "coarse_levels_built": [],
        "global_p4_matrix_or_factor": False,
        "official_pde": False,
        "memory_snapshot_scope": "single MPI1 process RSS/PSS/HWM snapshots; not tree peak",
        "memory_snapshots": {"before_setup": pair._memory()},
    }
    pair._save(output / "h6_transform_pair_partial.json", result)

    def phase(name: str) -> None:
        fact = {
            "phase": name,
            "elapsed_seconds": time.perf_counter() - started,
            "memory": pair._memory(),
        }
        pair._save(output / "workflow_phase.json", fact)
        print(f"H6_TRANSFORM_PHASE {name} elapsed={fact['elapsed_seconds']:.1f}s", flush=True)

    levels = rhs = None
    bundles = {}
    try:
        levels = _build_same_mesh_levels(
            cfg, MPI.COMM_WORLD, (6,), include_positive_coefficients=True
        )
        cell_count = int(
            levels["mesh"].topology.index_map(levels["mesh"].topology.dim).size_global
        )
        modes, _mode_rows, mode_sha = build_dynamic_mode_inventory(cfg)
        if cell_count != 990 or len(modes) != 80:
            raise ValueError(
                f"frozen H6 identity mismatch: cells={cell_count}, modes={len(modes)}"
            )
        levels["declared_degrees"] = (6,)
        levels["mode_sha256"] = mode_sha
        rhs = _new_storage_vector(levels["spaces"][6])
        witnesses, map_sha = pair._load_witnesses(
            specification, levels, mode_sha, rhs
        )
        result["p6_identity"] = {
            "cell_count": cell_count,
            "global_rows": int(levels["spaces"][6].dofmap.index_map.size_global),
            "mode_count": len(modes),
            "mode_sha256": mode_sha,
            "native_map_sha256": map_sha,
            "saved_witnesses": witnesses,
        }
        result["memory_snapshots"]["after_p6_identity"] = pair._memory()
        pair._save(output / "h6_transform_pair_partial.json", result)
        phase("p6_identity_and_saved_witnesses_verified")

        setup_records = {}
        for name, combine in (("baseline", False), ("candidate", True)):
            setup_wall, setup_cpu = time.perf_counter(), time.process_time()
            bundle = build_light_h6_setup(
                levels,
                cfg,
                lambda *_: None,
                packed_power10=True,
                packed_apply=True,
                preallocated_work=False,
                preallocated_power10=False,
                sum_factorized_work=True,
                sum_factorized_power10=True,
                shared_contractions=False,
                combine_real_imag_transforms=combine,
                direct_selected_backend=True,
            )
            bundles[name] = bundle
            facts = bundle["light_facts"]
            kernel = facts["kernel"]
            if (
                kernel["backend"] != "isotropic_sum_factorized_n1e_v26"
                or not facts["direct_selected_backend_used"]
                or bool(kernel["combined_real_imag_transform_opt_in"]) != combine
                or bool(facts["shared_contractions_opt_in"])
            ):
                raise ValueError(f"H6 {name} did not select the frozen pair route")
            setup_records[name] = {
                "setup_wall_seconds": time.perf_counter() - setup_wall,
                "setup_cpu_seconds": time.process_time() - setup_cpu,
                "seed_sha256": facts["seed_sha256"],
                "diagonal_sha256": facts["diagonal_sha256"],
                "inverse_sqrt_diagonal_sha256": facts[
                    "inverse_sqrt_diagonal_sha256"
                ],
                "power_history": facts["power_history"],
                "lambda_lo": facts["lambda_lo"],
                "lambda_hi": facts["lambda_hi"],
                "lambda_power10": facts["lambda_power10"],
                "kernel": kernel,
                "sum_factorized": pair._sf_snapshot(
                    pair._live_kernel(bundle)
                ),
            }
            result.setdefault("independent_setup", {})[name] = setup_records[name]
            result["memory_snapshots"][f"after_{name}_setup"] = pair._memory()
            pair._save(output / "h6_transform_pair_partial.json", result)
            phase(f"{name}_setup_complete")

        baseline_facts = setup_records["baseline"]
        candidate_facts = setup_records["candidate"]
        base_bundle, candidate_bundle = bundles["baseline"], bundles["candidate"]
        base_diagonal = base_bundle["p6_shell"].diagonal.array.copy()
        candidate_diagonal = candidate_bundle["p6_shell"].diagonal.array.copy()
        base_smoother, candidate_smoother = base_bundle["h6"], candidate_bundle["h6"]
        base_inverse = base_smoother._inv_sqrt.array.copy()
        candidate_inverse = candidate_smoother._inv_sqrt.array.copy()
        frozen = {
            "same_seed": baseline_facts["seed_sha256"]
            == candidate_facts["seed_sha256"],
            "independent_diagonal_relative": pair._relative(
                candidate_diagonal, base_diagonal
            ),
            "independent_inverse_sqrt_relative": pair._relative(
                candidate_inverse, base_inverse
            ),
            "independent_power_history_relative": pair._relative(
                candidate_facts["power_history"], baseline_facts["power_history"]
            ),
            "independent_window_relative_max": max(
                abs(float(candidate_facts[key]) - float(baseline_facts[key]))
                / max(abs(float(baseline_facts[key])), 1.0)
                for key in ("lambda_lo", "lambda_hi", "lambda_power10")
            ),
            "baseline_spectral_window": {
                key: baseline_facts[key]
                for key in ("lambda_lo", "lambda_hi", "lambda_power10")
            },
            "candidate_spectral_window": {
                key: candidate_facts[key]
                for key in ("lambda_lo", "lambda_hi", "lambda_power10")
            },
        }
        base_bundle["p6_shell"].diagonal.copy(candidate_bundle["p6_shell"].diagonal)
        base_smoother._inv_sqrt.copy(candidate_smoother._inv_sqrt)
        for key in ("lambda_lo", "lambda_hi", "lambda_power10", "power_history"):
            setattr(candidate_smoother, key, getattr(base_smoother, key))
        frozen.update(
            same_frozen_diagonal=pair._array_sha(
                candidate_bundle["p6_shell"].diagonal.array
            )
            == pair._array_sha(base_diagonal),
            same_frozen_inverse_sqrt=pair._array_sha(
                candidate_smoother._inv_sqrt.array
            )
            == pair._array_sha(base_inverse),
            same_frozen_window=all(
                getattr(candidate_smoother, key) == getattr(base_smoother, key)
                for key in ("lambda_lo", "lambda_hi", "lambda_power10", "power_history")
            ),
        )
        result["fixed_window"] = frozen
        result["memory_snapshots"]["before_apply_pair"] = pair._memory()
        pair._save(output / "h6_transform_pair_partial.json", result)
        phase("same_spectral_window_frozen_before_apply")

        late_witness = witnesses["late_i120"]
        with np.load(pair.WITNESSES[1][1], allow_pickle=False) as archive:
            rhs.array[:] = archive["array_0"]
        apply_result = pair._h6_apply_pair(
            base_bundle, candidate_bundle, rhs
        )
        result["late_i120_apply_pair"] = apply_result
        correct = (
            frozen["same_seed"]
            and frozen["independent_diagonal_relative"] <= 1.0e-12
            and frozen["independent_inverse_sqrt_relative"] <= pair.IDENTITY_LIMIT
            and frozen["independent_power_history_relative"] <= pair.IDENTITY_LIMIT
            and frozen["independent_window_relative_max"] <= pair.IDENTITY_LIMIT
            and frozen["same_frozen_diagonal"]
            and frozen["same_frozen_inverse_sqrt"]
            and frozen["same_frozen_window"]
            and apply_result["max_relative_output_difference"] <= pair.IDENTITY_LIMIT
            and all(
                row["baseline_input_unchanged"]
                and row["candidate_input_unchanged"]
                for row in apply_result["repeats"]
            )
        )
        faster = (
            apply_result["median_candidate_wall_seconds"]
            < apply_result["median_baseline_wall_seconds"]
        )
        result["status"] = (
            "QUALIFIED_OPERATOR_EQUIVALENCE" if correct else "MEASURED_NOT_QUALIFIED"
        )
        result["performance_decision"] = {
            "candidate_apply_faster": faster,
            "candidate_setup_wall_seconds": candidate_facts["setup_wall_seconds"],
            "baseline_setup_wall_seconds": baseline_facts["setup_wall_seconds"],
            "adopt_h6_transform": bool(correct and faster),
            "adoption_scope": "H6 only; A6 and p4 matrix/factor unchanged",
            "witness_iteration": int(late_witness["iteration"]),
        }
        result["memory_snapshots"]["before_release"] = pair._memory()
        result["elapsed_wall_seconds"] = time.perf_counter() - started
        pair._save(output / "h6_transform_pair_result.json", result)
        phase("h6_transform_pair_complete")
        return result
    finally:
        for bundle in bundles.values():
            bundle["h6"].destroy()
            bundle["p6_shell"].destroy()
        if rhs is not None:
            rhs.destroy()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    if not args.worker and output.exists() and any(output.iterdir()):
        raise FileExistsError(f"refusing to overwrite H6 pair output: {output}")
    output.mkdir(parents=True, exist_ok=True)
    if args.worker:
        try:
            result = run(output)
        except BaseException as error:
            pair._save(
                output / "h6_transform_pair_failure.json",
                {"status": "FAILED", "error_type": type(error).__name__, "error": str(error)},
            )
            raise
        return 0 if result["status"] == "QUALIFIED_OPERATOR_EQUIVALENCE" else 1

    from benchmarks.subreaper_watchdog import supervise
    from src.io.physical_intermediate_profile import FUSED_KERNEL_PROFILE, profile_facts
    from src.runners.workflow_timebase import CONSERVATIVE_REALTIME

    resources = profile_facts(FUSED_KERNEL_PROFILE)["resources"]
    authority = supervise(
        [
            "/usr/bin/mpiexec", "-n", "1", sys.executable,
            str(Path(__file__).resolve()), "--worker", "--output", str(output),
        ],
        output / "watchdog",
        wall_seconds=float(resources["workflow_seconds"]),
        grace_seconds=30.0,
        hard_stop_immediate=True,
        phase_path=output / "workflow_phase.json",
        timebase_guard=True,
        timebase_policy=CONSERVATIVE_REALTIME,
        stop_on_global_swap=False,
        allow_swap_observation=True,
        time_policy="observe_only",
        memory_policy=resources["watchdog_memory_policy"],
    )
    pair._save(output / "watchdog_wrapper_result.json", authority)
    return 0 if authority.get("leader_exit_code") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
