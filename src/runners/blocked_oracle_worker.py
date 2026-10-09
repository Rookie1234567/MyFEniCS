"""Thin V36 wiring around frozen-space I/O and existing physical verifier."""

import gc
import json
from time import monotonic, perf_counter

import numpy as np
from scipy import sparse

from src.io.neural_wave_campaign import ROOT, digest, profile_paths, load_training_files
from src.io.neural_space_campaign import POLICY
from src.runners.neural_space_worker import bound_path, load_space, write_model
from src.solvers.neural_space_blocked import (
    BasisStore,
    Timers,
    build_basis,
    reference_projection,
    panel_fallback,
)
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz

CHAIN = (
    "src/io/blocked_oracle_campaign.py",
    "src/runners/blocked_oracle_worker.py",
    "src/solvers/neural_space_blocked.py",
    "src/solvers/neural_space_blocked_checks.py",
    "src/runners/neural_space_worker.py",
    "src/runners/neural_space_verification.py",
    "src/runners/saved_field_supervision.py",
    "src/postprocessing/neural_space_saved.py",
    "src/solvers/neural_wave_block_reconstruction.py",
)


def space_name(stage):
    return (
        "LEARNED_COMPLEX_WAVE_BACKFIT"
        if "learned" in stage
        else "DETERMINISTIC_COMPLEX_WAVE_BACKFIT"
    )


def oracle(action, design, artifact, marker, manifest):
    name = space_name(manifest["spec"]["stage"])
    directory = artifact / name
    directory.mkdir(parents=True, exist_ok=True)
    old = bound_path(design["unlabelled_result"])
    old_hash = digest(old)
    entry = design["spaces"][name]
    A = json.loads(old.read_text())
    if A["records"][name]["source_identity"] != entry:
        raise ValueError("V35_ACCEPTED_A_SPACE_IDENTITY_MISMATCH")
    ready = directory / "space_record.json"
    if ready.exists() and "model" in json.loads(ready.read_text()):
        from src.io.neural_wave_backfit_store import check_boundary

        record = json.loads(ready.read_text())
        bound_path(record["model"])
        check_boundary(ROOT / record["model"]["path"])
        return dict(records={name: record}, healthy_oracle_reused=True, **POLICY)
    timers = Timers()
    with timers.phase("load_frozen_U_and_original_G"):
        U, _, saved, boundary = load_space(entry, action.size, qr=False)
        G = sparse.load_npz(bound_path(design["gram"]))
    if G.shape != (31968, 31968):
        raise ValueError("M5_ORIGINAL_CONSTRAINED_G_ORDER_CHANGED")
    binding = dict(
        original_space=entry,
        gram=design["gram"],
        columns=1377,
        rcond=1e-12,
        kernel_sha256=digest(ROOT / "src/solvers/neural_space_blocked.py"),
    )
    # Fixed first 128 columns: no reference-based column selection.
    prefix_file = directory / "prefix_profile.json"
    if not prefix_file.exists():
        began = perf_counter()
        pstore = BasisStore(
            directory / "prefix_basis", dict(binding, prefix_columns=128), marker
        )
        basis, profile, paction, ptimers = build_basis(
            U[:, :128],
            G,
            pstore,
            deadline=min(manifest["worker_stop_monotonic"], monotonic() + 600),
        )
        rng = np.random.default_rng(4213603)
        z = rng.normal(size=128) + 1j * rng.normal(size=128)
        num = np.linalg.norm(
            U[:, :128] @ z - basis["V"] @ (basis["T"] @ (z * basis["scales"]))
        )
        den = np.linalg.norm(U[:, :128] @ z)
        if num / den > 1e-10:
            raise ValueError("FIXED_128_PREFIX_TRANSFORM_FAILED")
        profile.update(
            fixed_prefix_columns=128,
            label_selected=False,
            nonzero_complex_transform_numerator=float(num),
            nonzero_complex_transform_denominator=float(den),
            nonzero_complex_transform_relative=float(num / den),
            phase_seconds_exclusive=ptimers.seconds,
            wall_seconds=perf_counter() - began,
            G_columns=paction.count,
            G_by_role=paction.by_role,
            kernel_sha256=binding["kernel_sha256"],
        )
        atomic_json(prefix_file, profile)
        marker(
            "fixed_128_prefix_qualified",
            dict(space=name, seconds=profile["wall_seconds"], method=profile["method"]),
        )
        del basis, paction
        gc.collect()
    else:
        profile = json.loads(prefix_file.read_text())
        if profile["kernel_sha256"] != binding["kernel_sha256"]:
            raise ValueError("PREFIX_KERNEL_CHANGED_REQUALIFICATION_REQUIRED")
    store = BasisStore(directory / "projection_boundaries", binding, marker)
    try:
        basis, stats, Gaction, timers = build_basis(
            U, G, store, deadline=manifest["worker_stop_monotonic"], timers=timers
        )
        # Only the already frozen basis is projected against the exposed label.
        with timers.phase("load_reference_after_basis_frozen"):
            reference_path = bound_path(design["reference"])
            if (
                design["reference"]["sha256"]
                != "0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7"
            ):
                raise ValueError("ONLY_ORIGINAL_V1_P3_REFERENCE")
            with np.load(reference_path, allow_pickle=False) as z:
                reference = np.array(z["c"])
                if (
                    np.linalg.norm(action.alpha(reference) - z["alpha"])
                    / np.linalg.norm(z["alpha"])
                    > 1e-10
                ):
                    raise ValueError("REFERENCE_SAME_PHYSICAL_PORT_IDENTITY")
        arrays, stats = reference_projection(
            U, reference, basis, stats, Gaction, timers
        )
        if (
            not stats["floating_numerical_qualified"]
            and basis["method"] == "HOUSEHOLDER_SMALL_GRAM"
        ):
            reason = dict(
                mapping=stats["actual_U_amplitude_pair_relative"],
                optimality=stats["retained_optimality"],
            )
            # Accuracy of mapping/stationarity triggers fallback, never E_G.
            marker("primary_export_stability_requires_panel_fallback", reason)
            basis, basis_stats = panel_fallback(U, Gaction, store, timers)
            basis_stats.update(
                primary_export_stability_failure=reason,
                primary_or_fallback_selected_without_reference_error=True,
            )
            with timers.phase("save"):
                store.save(
                    "G_BASIS_QUALIFIED",
                    {k: v for k, v in basis.items() if k != "method"},
                    basis_stats,
                )
            arrays, stats = reference_projection(
                U, reference, basis, basis_stats, Gaction, timers
            )
        with timers.phase("save_model_and_actual_oracle_field"):
            model = write_model(
                directory / "basis",
                boundary,
                dict(
                    a=arrays["a"],
                    c=arrays["c"],
                    r=action.f - action.apply(arrays["c"]),
                    R=saved["R"],
                ),
                manifest,
                oracle=True,
            )
            file = directory / "projection_arrays.npz"
            atomic_npz(file, **arrays)
            store.save(
                "ORACLE_FIELD_FROZEN",
                arrays,
                dict(model=model, E_G=stats["actual_E_G"], rank=stats["retained_rank"]),
            )
        stats.update(
            model=model,
            source_identity=entry,
            prefix_profile=dict(
                path=str(prefix_file.relative_to(ROOT)), sha256=digest(prefix_file)
            ),
            projection_arrays=dict(
                path=str(file.relative_to(ROOT)), sha256=digest(file)
            ),
            phase_seconds_exclusive=timers.seconds,
            loaded_columns_bytes=int(U.nbytes),
            **POLICY,
        )
        atomic_json(ready, stats)
        marker(
            "actual_oracle_field_frozen",
            dict(
                space=name,
                E_G=stats["actual_E_G"],
                rank=stats["retained_rank"],
                qualified=stats["floating_numerical_qualified"],
            ),
        )
    except Exception as error:
        # No secondary write can hide the original numerical/API exception.
        try:
            atomic_json(
                directory / "interruption.json",
                dict(
                    original_exception=repr(error),
                    latest_boundary=store.reopen()[0] if store.reopen() else None,
                    **POLICY,
                ),
            )
        except Exception as save_error:
            marker(
                "interruption_record_failed",
                dict(original_exception=repr(error), save_exception=repr(save_error)),
            )
        raise
    if digest(old) != old_hash:
        raise ValueError("ACCEPTED_V35_A_CHANGED_AFTER_LABEL_EXPOSURE")
    return dict(
        records={name: stats}, bound_unlabelled_result_sha256=old_hash, **POLICY
    )


def decision(design, marker):
    root = ROOT / "benchmarks/artifacts/task42extra/v36"
    records = {}
    for stem, name in (
        ("learned", "LEARNED_COMPLEX_WAVE_BACKFIT"),
        ("control", "DETERMINISTIC_COMPLEX_WAVE_BACKFIT"),
    ):
        result_file = root / f"v36_{stem}_space_oracle/result.json"
        verify_file = root / f"v36_{stem}_oracle_verify/result.json"
        if not result_file.exists() or not verify_file.exists():
            records[name] = dict(
                status="UNKNOWN_INCOMPLETE",
                oracle=result_file.exists(),
                verify=verify_file.exists(),
            )
            continue
        result = json.loads(result_file.read_text())["records"][name]
        verify = json.loads(verify_file.read_text())
        records[name] = dict(
            actual_E_G=result["actual_E_G"],
            rank=result["retained_rank"],
            full_space=result["full_column_space_retained"],
            floating_numerical_qualified=result["floating_numerical_qualified"],
            field_precision_conclusion=result["field_precision_conclusion"],
            verification=dict(
                path=str(verify_file.relative_to(ROOT)), sha256=digest(verify_file)
            ),
            joint_gate=verify["new_fields"]["records"][name + "_ORACLE"].get(
                "m5_full_discrete_numerical_gate", False
            ),
        )
    marker("bounded_neural_space_decision", records)
    return dict(
        records=records,
        candidate_decision="NO_SUPPORTED_NEXT_NEURAL_PRODUCTION_CANDIDATE",
        CURRENT_DENSE_WAVE_SOLVER_FAMILY_CLOSED=True,
        FEINN_MAIN_SOLVER_ON_HOLD=True,
        NO_VERIFIED_NN_INCREMENT=True,
        FULL_TARGET_NOT_QUALIFIED=True,
        new_training_count=0,
        cold_N1="UNKNOWN",
        historical_required_prefix_seconds=10186.178641493432,
        **POLICY,
    )


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    design = json.loads(profile_paths(spec)["design"].read_text())
    if digest(profile_paths(spec)["design"]) != manifest["design_sha256"]:
        raise ValueError("V36_DESIGN_CHANGED")
    if spec["role"] == "blocked_checks":
        from src.solvers.neural_space_blocked_checks import qualify
        from src.solvers.neural_space_blocked_checks import real_panel_interruption_case
        from src.solvers.neural_space_qualification import (
            qualify as writer_qualification,
        )

        result = qualify(artifact)
        result.update(
            actual_panel_recovery=real_panel_interruption_case(artifact),
            reused_writer_small_qualification=writer_qualification(
                artifact / "writer_fixture", manifest
            ),
            implementation_qualified=True,
        )
    elif spec["role"] == "blocked_decision":
        result = decision(design, marker)
    else:
        qualification = (
            profile_paths(spec)["artifacts"] / "v36_oracle_kernel_checks/result.json"
        )
        checked = json.loads(qualification.read_text())
        if checked.get("implementation_qualified") is not True or checked[
            "bound_numerical_chain"
        ]["src/solvers/neural_space_blocked.py"] != digest(
            ROOT / "src/solvers/neural_space_blocked.py"
        ):
            raise ValueError("BLOCKED_KERNEL_FROZEN_QUALIFICATION_REQUIRED")
        files = load_training_files(design)
        from src.solvers.feinn_native import load_native

        action = load_native(files["native"])
        if (action.size, action.nc, action.np) != (31968, 384, 40):
            raise ValueError("ORIGINAL_M5_COMPLETE_PHYSICAL_IDENTITY")
        planned = 9 * action.size * 1377 * 16 + 16 * 1377**2 * 16 + 2 * 2**30
        if planned > 12 * 2**30:
            raise MemoryError("BLOCKED_ORACLE_MEMORY_PLAN_EXCEEDED")
        marker(
            "blocked_oracle_memory_plan",
            dict(planned_bytes=planned, planning_limit_bytes=12 * 2**30),
        )
        if spec["role"] == "blocked_oracle":
            result = oracle(action, design, artifact, marker, manifest)
        else:
            from src.runners.neural_space_verification import compare_blocked

            with np.load(files["moments_q30"], allow_pickle=False) as z:
                packet = {k: np.array(z[k]) for k in z.files}
            result = compare_blocked(action, packet, design, artifact, marker, manifest)
    result["bound_numerical_chain"] = {p: digest(ROOT / p) for p in CHAIN}
    return result
