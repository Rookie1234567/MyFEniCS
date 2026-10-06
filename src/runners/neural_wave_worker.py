"""One V30 stage per supervised process; FE and training roles stay isolated."""

import json
import os
from pathlib import Path
import sys
from time import monotonic, perf_counter
import traceback

import numpy as np

from src.io.neural_wave_campaign import (
    ROOT,
    DESIGN,
    ARTIFACTS,
    load_training_files,
    digest,
)
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz


def abi(mode):
    result = dict(
        python=sys.executable,
        mode=mode,
        activated=os.environ.get("TASK42EXTRA_ACTIVATION") == "1",
        threads={
            key: os.environ.get(key)
            for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
        },
        cpu_affinity=sorted(os.sched_getaffinity(0)),
        numpy=np.__version__,
        cuda_visible=os.environ.get("CUDA_VISIBLE_DEVICES"),
    )
    if not result["activated"] or len(result["cpu_affinity"]) != 1:
        raise RuntimeError("V30_ACTIVATION_OR_ONE_CORE_GATE_FAILED")
    if any(value != "1" for value in result["threads"].values()):
        raise RuntimeError("V30_MATH_THREAD_GATE_FAILED")
    if mode == "fe":
        from mpi4py import MPI
        from petsc4py import PETSc
        import dolfinx
        import basix

        if (
            MPI.COMM_WORLD.size != 1
            or PETSc.ScalarType != np.complex128
            or PETSc.IntType != np.int64
        ):
            raise RuntimeError("V30_M5_COMPLEX128_INT64_MPI1_ABI_REQUIRED")
        result.update(
            mpi_size=MPI.COMM_WORLD.size,
            petsc_scalar=str(PETSc.ScalarType),
            petsc_int=str(PETSc.IntType),
            dolfinx=dolfinx.__version__,
            basix=basix.__version__,
            torch_imported="torch" in sys.modules,
        )
        if result["torch_imported"]:
            raise RuntimeError("FE_ROLE_MUST_NOT_IMPORT_TORCH")
    elif mode == "ml":
        import torch

        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        result.update(
            torch=torch.__version__,
            torch_threads=torch.get_num_threads(),
            torch_interop=torch.get_num_interop_threads(),
            torch_default_dtype=str(torch.get_default_dtype()),
            neuron_and_derivative_dtype="float64/complex128 numpy; Torch independent tests only",
        )
    return result


def require_checks():
    file = ARTIFACTS / "v30_wave_checks" / "result.json"
    record = json.loads(file.read_text())
    if not record["implementation_qualified"]:
        raise ValueError("NEW_WAVE_IMPLEMENTATION_NOT_QUALIFIED")
    design = json.loads(DESIGN.read_text())
    if any(
        record["actual_" + name + "_sha256"] != design["files"][key]["sha256"]
        for name, key in [("native", "native"), ("moments", "moments_q30")]
    ):
        raise ValueError("PREVIOUS_FULL_MAPPING_INPUT_IDENTITY_CHANGED")
    return record


def verify(design, action, packet, artifact, marker):
    from src.solvers.neural_wave_reconstruction import rebuild
    from src.solvers.feinn_fem import build_model
    from src.solvers.feinn_reference import field_physics, _region_field_errors
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        destroy_same_mesh_physical_action,
    )

    states, reconstruction = {}, {}
    highfile = ARTIFACTS / "v30_wave_checks" / "moments_q60.npz"
    with np.load(highfile, allow_pickle=False) as arrays:
        high = {k: np.array(arrays[k]) for k in arrays.files}
    for stage, name in [
        ("v30_m5_fixed_wave", "FIXED_WAVE_GREEDY_CONTROL"),
        ("v30_m5_learned_wave", "LEARNED_WAVE_GREEDY"),
    ]:
        directory = ARTIFACTS / stage
        c, saved, boundary = rebuild(directory / "basis", packet, marker)
        higher, _, _ = rebuild(directory / "basis", high, marker)
        same = float(np.linalg.norm(c - saved) / max(np.linalg.norm(saved), 1e-30))
        drift = float(np.linalg.norm(c - higher) / max(np.linalg.norm(c), 1e-30))
        action_drift = float(np.linalg.norm(action.apply(c - higher)) / action.bnorm)
        reconstruction[name] = dict(
            complete_model_mapping_relative=same,
            coefficient_q30_q60_relative=drift,
            original_action_q30_q60_load_relative=action_drift,
            quadrature_pass=bool(max(drift, action_drift) <= 1e-8),
            model_reconstruction_pass=bool(same <= 1e-10),
            candidate_source_sha=boundary["binding"]["source_sha"],
            committed_boundary_sha256=digest(directory / "basis/committed.json"),
        )
        # Physics consumes the independently evaluated network, not producer c.
        states[name] = c
        atomic_npz(artifact / (stage + "_rebuild.npz"), c30=c, c60=higher, saved=saved)
    # Only here, after independently frozen/reconstructed models, is the V1
    # label loaded. This function is never imported by a training stage.
    index = json.loads(
        (ROOT / "benchmarks/artifacts/task42extra/index_e3_reference.json").read_text()
    )
    entry = index["files"]["reference"]
    if digest(entry["path"]) != entry["sha256"]:
        raise ValueError("SAME_P3_REFERENCE_HASH_FAILED")
    with np.load(entry["path"], allow_pickle=False) as arrays:
        reference, alpha = np.array(arrays["c"]), np.array(arrays["alpha"])
    if (
        np.linalg.norm(action.alpha(reference) - alpha)
        / max(np.linalg.norm(alpha), 1e-30)
        > 1e-10
    ):
        raise ValueError("REFERENCE_SAME_PORT_IDENTITY_FAILED")
    marker(
        "reference_loaded_after_candidate_freeze",
        dict(reference_sha256=entry["sha256"], new_reference_solve_count=0),
    )
    model = build_model(design["model"], marker=marker)
    try:
        for key, expected in design["native_identity"].items():
            if model["record"][key] != expected:
                raise ValueError("INDEPENDENT_FE_PHYSICAL_IDENTITY_CHANGED: " + key)
        physics, comparisons = field_physics(
            model, action, reference, states, artifact, marker
        )
        from src.postprocessing.neural_wave_audit import save_complete_field_samples

        raw_fields, mpc_checks = save_complete_field_samples(
            model, action, packet, reference, states, artifact, marker
        )
        physics["ordered_mode_sides"] = [m.side for m in model["bundle"]["modes"]]
        physics["original_mode_manifest"] = dict(
            schema="fullspace-dtn.mode-manifest.v1",
            profile="full3d_scalable_v1",
            mode_count=len(model["record"]["modes"]),
            modes=model["record"]["modes"],
        )
        physics["ordered_mode_k_vectors"] = np.asarray(
            [m.k_vector for m in model["bundle"]["modes"]]
        )
        physics["ordered_mode_e_vectors"] = np.asarray(
            [m.e_vector for m in model["bundle"]["modes"]]
        )
        physics["port_area_nm2"] = (model["cfg"].x_max - model["cfg"].x_min) * (
            model["cfg"].y_max - model["cfg"].y_min
        )
        high_physics, _ = field_physics(
            model,
            action,
            reference,
            states,
            artifact / "norm_q30",
            marker,
            norm_quadrature_degree=30,
        )
        regions = {
            name: _region_field_errors(model, action, reference, c)
            for name, c in states.items()
        }
        for name, comp in comparisons.items():
            rec = reconstruction[name]
            oldnorms = np.r_[
                physics["records"][name]["total_L2_scaled_curl_norms"],
                physics["records"][name]["scattered_L2_scaled_curl_norms"],
            ]
            newnorms = np.r_[
                high_physics["records"][name]["total_L2_scaled_curl_norms"],
                high_physics["records"][name]["scattered_L2_scaled_curl_norms"],
            ]
            rec["FE_norm_q15_q30_relative"] = float(
                np.linalg.norm(oldnorms - newnorms)
                / max(np.linalg.norm(oldnorms), 1e-30)
            )
            rec["quadrature_pass"] &= rec["FE_norm_q15_q30_relative"] <= 1e-8
            recovery = (
                max(
                    physics["records"][name]["audit"][k]
                    for k in ("port_full_rhs_relative", "port_operation_relative")
                )
                <= 1e-10
                and mpc_checks[name] <= 1e-10
            )
            joint = bool(
                comp["numerical_equation_pass"]
                and comp["field_reconstruction_pass"]
                and comp["power_check_pass"]
                and rec["quadrature_pass"]
                and rec["model_reconstruction_pass"]
                and physics["reference_pass"]
                and recovery
            )
            comp.update(
                m5_full_discrete_numerical_gate=joint,
                verifier_provisional_joint_pass=joint,
                quadrature_pass=rec["quadrature_pass"],
                model_reconstruction_pass=rec["model_reconstruction_pass"],
                qualified=False,
                pde_only_solver_qualified=False,
                official_candidate_results=False,
                qualification_scope="pending independent saved-array checker",
                production_initialization_allowed=False,
            )
        return dict(
            verification_complete=True,
            same_p3_reference_sha256=entry["sha256"],
            reference_solve_count=0,
            global_Maxwell_factor_count=0,
            global_Gram_factor_count=0,
            reference_loaded_only_by_verifier=True,
            reference_pass=physics["reference_pass"],
            reconstruction=reconstruction,
            raw_complete_fields=dict(
                path=str(raw_fields.relative_to(ROOT)), sha256=digest(raw_fields)
            ),
            independent_MPC_recovery_checks=mpc_checks,
            physics=physics,
            comparisons=comparisons,
            region_errors=regions,
            full_size_0p7_target_qualified=False,
            continuous_discretization_qualified=False,
        )
    finally:
        destroy_same_mesh_physical_action(model["bundle"])


def main():
    directory = ROOT / Path(sys.argv[1])
    manifest = json.loads((directory / "run_manifest.json").read_text())
    spec = manifest["spec"]
    artifact = ROOT / manifest["artifact"]
    start = perf_counter()

    def marker(stage, values):
        print(
            json.dumps(dict(stage=stage, values=values), default=lambda v: v.tolist()),
            flush=True,
        )
        with (directory / "events.jsonl").open("a") as stream:
            stream.write(
                json.dumps(
                    dict(stage=stage, values=values), default=lambda v: v.tolist()
                )
                + "\n"
            )

    try:
        atomic_json(directory / "abi.json", abi(spec["mode"]))
        design = json.loads(DESIGN.read_text())
        if digest(DESIGN) != manifest["design_sha256"]:
            raise ValueError("FROZEN_DESIGN_CHANGED_AFTER_LAUNCH")
        if spec["role"] in ("LEARNED_WAVE_GREEDY", "FIXED_WAVE_GREEDY_CONTROL"):
            from src.io.neural_wave_campaign import training_open_allowed

            def firewall(event, arguments):
                if event == "open" and not training_open_allowed(arguments[0], design):
                    raise PermissionError(
                        "UNLABELLED_TRAINING_FILE_ACCESS_REJECTED: " + str(arguments[0])
                    )

            sys.addaudithook(firewall)
            marker(
                "training_label_firewall_installed",
                dict(
                    reference_access_allowed=False,
                    legacy_weights_allowed=False,
                    Gram_packet_access_allowed=False,
                ),
            )
        files = load_training_files(design)
        from src.solvers.feinn_native import load_native

        action = load_native(files["native"])
        with np.load(files["moments_q30"], allow_pickle=False) as arrays:
            packet = {key: np.array(arrays[key]) for key in arrays.files}
        if action.size != 31968 or action.nc != 384 or action.np != 40:
            raise ValueError("ORIGINAL_M5_FULL_FE_IDENTITY_FAILED")
        if not np.array_equal(packet["master_native_rows"], action.a["masters"]):
            raise ValueError("COMPLETE_MOMENT_MASTER_ORDER_MISMATCH")
        if "reduced" in spec["stage"]:
            raise ValueError("REDUCED_CASE_REQUIRES_NEW_QUALIFIED_PHYSICAL_PACKETS")
        if spec["role"] == "checks":
            from src.solvers.neural_wave_qualification import qualify

            result = qualify(design["model"], action, packet, artifact, marker)
        elif spec["role"] == "fast_checks":
            require_checks()
            from src.solvers.neural_wave_factorized import compare_factorized
            from src.solvers.neural_wave_greedy import patch_inventory

            patches = [
                patch_inventory(design["model"]["geometry"], level)[
                    len(patch_inventory(design["model"]["geometry"], level)) // 2
                ]
                for level in range(3)
            ]
            result = compare_factorized(packet, patches)
            marker("complete_tensor_moment_pair", result)
        elif spec["role"] == "local_action_checks":
            require_checks()
            from src.solvers.neural_wave_local_qualification import qualify

            result = qualify(action, packet, design, marker)
            result["local_action_source_sha256"] = digest(
                ROOT / "src/solvers/neural_wave_local_action.py"
            )
            marker("complete_original_local_action_pair", result)
        elif spec["role"] == "projection_checks":
            require_checks()
            from src.solvers.neural_wave_projection_qualification import qualify

            result = qualify(
                action, packet, design,
                ARTIFACTS / "v30_m5_learned_wave/basis", artifact, marker,
            )
            for name in ("local_action", "projection"):
                result[name + "_source_sha256"] = digest(
                    ROOT / ("src/solvers/neural_wave_" + name + ".py")
                )
            marker("saved_unlabelled_projection_chain_pair", dict(
                qualified=result["implementation_qualified"],
                states=[v["saved_state"]["columns"] for v in result["checks"]],
            ))
        elif spec["role"] == "screening_checks":
            require_checks()
            from src.solvers.neural_wave_screening_qualification import CHAIN, qualify

            result = qualify(
                action, packet, design,
                ARTIFACTS / "v30_m5_learned_wave/basis", artifact, marker,
            )
            result["bound_numerical_chain_sha256"] = {
                path: digest(ROOT / path) for path in CHAIN
            }
            marker("bounded_independent_proposals_qualified", dict(
                implementation_qualified=result["implementation_qualified"],
                selected=result["complete_bounded_screening_selected"],
            ))
        elif spec["role"] == "calibration":
            from src.solvers.neural_wave_qualification import analytic_calibration

            if (
                digest(ARTIFACTS / "v30_wave_checks/moments_q60.npz")
                != manifest["qualifying_moments_q60_sha256"]
            ):
                raise ValueError("HEALTHY_HIGH_MOMENT_PACKET_HASH_CHANGED")

            with np.load(
                ARTIFACTS / "v30_wave_checks/moments_q60.npz", allow_pickle=False
            ) as arrays:
                high = {key: np.array(arrays[key]) for key in arrays.files}
            result = analytic_calibration(
                design["model"],
                0.7 if "0p7" in spec["stage"] else 5.0,
                artifact,
                marker,
                frozen_high=high,
            )
        elif spec["role"] == "verify":
            result = verify(design, action, packet, artifact, marker)
        elif spec["role"] == "saved_audit":
            from src.postprocessing.neural_wave_audit import check_saved_arrays

            paired = (
                "v30_m5_verify_final"
                if spec["stage"].endswith("_final")
                else "v30_m5_verify"
            )
            frozen_file = ARTIFACTS / paired / "result.json"
            frozen = json.loads(frozen_file.read_text())
            raw = ROOT / frozen["raw_complete_fields"]["path"]
            if digest(raw) != frozen["raw_complete_fields"]["sha256"]:
                raise ValueError("FROZEN_COMPLETE_FIELD_ARRAY_HASH_FAILED")
            with np.load(raw, allow_pickle=False) as arrays:
                samples = {key: np.array(arrays[key]) for key in arrays.files}
            result = check_saved_arrays(
                action,
                frozen["physics"],
                samples,
                frozen["reconstruction"],
                frozen["independent_MPC_recovery_checks"],
                dict(
                    model=design["model"],
                    mode_manifest_sha256=design["native_identity"][
                        "mode_manifest_sha256"
                    ],
                ),
            )
            result["bound_verifier_result_sha256"] = digest(frozen_file)
            result["bound_verifier_result_path"] = str(frozen_file.relative_to(ROOT))
            result["bound_complete_field_samples_sha256"] = digest(raw)
            result["candidate_source_sha"] = {
                name: frozen["reconstruction"][name]["candidate_source_sha"]
                for name in result["records"]
            }
            marker("saved_array_original_gate_recomputation", result)
        else:
            require_checks()
            fast = json.loads(
                (ARTIFACTS / "v30_wave_fast_checks/result.json").read_text()
            )
            if (
                not fast["passed"]
                or fast["actual_moments_sha256"]
                != design["files"]["moments_q30"]["sha256"]
            ):
                raise ValueError("TENSOR_MOMENT_KERNEL_NOT_QUALIFIED")
            for dependency in (
                "v30_wave_calibration_5nm",
                "v30_wave_calibration_0p7nm",
            ):
                if not (ARTIFACTS / dependency / "result.json").exists():
                    raise ValueError("INITIAL_ANALYTIC_CALIBRATION_NOT_RUN")
            from src.solvers.neural_wave_greedy import run_greedy

            design["strategy"]["native_target"] = spec["native_target"]
            binding = dict(
                route=spec["role"],
                source_sha=manifest["source_sha"],
                design_sha256=manifest["design_sha256"],
                native_sha256=design["files"]["native"]["sha256"],
                moments_sha256=design["files"]["moments_q30"]["sha256"],
                route_origin_monotonic=manifest["route_origin_monotonic"],
            )
            local_file = ARTIFACTS / "v30_wave_local_action_checks/result.json"
            projection_file = ARTIFACTS / "v30_wave_projection_checks/result.json"
            if projection_file.exists():
                projection_record = json.loads(projection_file.read_text())
                if (
                    not projection_record["implementation_qualified"]
                    or not projection_record["original_action_and_vjp_paired"]
                    or projection_record["projection_source_sha256"]
                    != digest(ROOT / "src/solvers/neural_wave_projection.py")
                ):
                    raise ValueError("CACHED_TWO_PASS_PROJECTION_NOT_QUALIFIED")
                local_file = projection_file
                binding["exact_two_pass_projection_reuse"] = True
                binding["projection_qualification_sha256"] = digest(projection_file)
            if local_file.exists():
                local_record = json.loads(local_file.read_text())
                if (
                    not local_record["implementation_qualified"]
                    or local_record["local_action_source_sha256"]
                    != digest(ROOT / "src/solvers/neural_wave_local_action.py")
                    or local_record["actual_native_sha256"]
                    != design["files"]["native"]["sha256"]
                    or local_record["actual_moments_sha256"]
                    != design["files"]["moments_q30"]["sha256"]
                ):
                    raise ValueError("LOCAL_INPUT_SUPPORT_ACTION_NOT_QUALIFIED")
                binding["exact_local_input_support_reuse"] = True
                binding["local_action_qualification_sha256"] = digest(local_file)
            screening_file = ARTIFACTS / "v30_wave_screening_checks/result.json"
            if screening_file.exists():
                from src.solvers.neural_wave_screening_qualification import CHAIN

                screened = json.loads(screening_file.read_text())
                if screened["bound_numerical_chain_sha256"] != {
                    path: digest(ROOT / path) for path in CHAIN
                }:
                    raise ValueError("BOUNDED_PROPOSAL_NUMERICAL_CHAIN_CHANGED")
                if screened["implementation_qualified"] and screened["complete_bounded_screening_selected"]:
                    binding["bounded_candidate_screening_widths"] = screened["selected_bounded_screening_widths"]
                binding["screening_qualification_sha256"] = digest(screening_file)
            result = run_greedy(
                action,
                packet,
                design,
                artifact,
                binding,
                manifest["worker_stop_monotonic"],
                marker,
            )
        result.update(
            source_sha=manifest["source_sha"],
            input_sha256=spec["input_sha256"],
            design_sha256=manifest["design_sha256"],
            worker_elapsed_seconds=perf_counter() - start,
            route_elapsed_seconds=monotonic() - manifest["route_origin_monotonic"],
            actual_native_sha256=design["files"]["native"]["sha256"],
            actual_moments_sha256=design["files"]["moments_q30"]["sha256"],
            full_size_0p7_target_qualified=False,
        )
        atomic_json(artifact / "result.json", result)
        marker(
            "stage_frozen",
            dict(stage=spec["stage"], result_sha256=digest(artifact / "result.json")),
        )
    except Exception as error:
        atomic_json(
            directory / "failure.json",
            dict(
                error=repr(error),
                traceback=traceback.format_exc(),
                elapsed_seconds=perf_counter() - start,
                source_sha=manifest["source_sha"],
            ),
        )
        raise


if __name__ == "__main__":
    main()
