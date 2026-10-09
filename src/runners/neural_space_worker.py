"""V35 fixed-space audit wiring; no optimizer or inverse is imported."""

from copy import deepcopy
import gc
import json
from pathlib import Path
import sys
from time import monotonic, monotonic_ns

import numpy as np
from scipy import linalg, sparse

from src.io.neural_space_campaign import (
    POLICY,
    unlabelled_open_allowed,
    require_oracle_policy,
)
from src.io.neural_wave_campaign import ROOT, digest, profile_paths, load_training_files
from src.io.neural_wave_backfit_store import check_boundary
from src.solvers.neural_wave_block import compensated_columns
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz
from src.solvers.neural_space_audit import original_readout, field_oracle, relative
from src.solvers.feinn_gqr import ReadoutStop

CHAIN = (
    "src/io/neural_space_campaign.py",
    "src/runners/neural_space_worker.py",
    "src/solvers/neural_space_audit.py",
    "src/solvers/feinn_gqr.py",
    "src/solvers/neural_wave_block_reconstruction.py",
    "src/runners/neural_space_verification.py",
    "src/postprocessing/neural_space_saved.py",
    "src/solvers/neural_space_qualification.py",
)


def bound_path(entry):
    p = ROOT / entry["path"]
    if digest(p) != entry["sha256"]:
        raise ValueError("FROZEN_SPACE_ARTIFACT_HASH_CHANGED: " + str(p))
    return p


def load_space(entry, n, *, qr):
    path = bound_path(entry)
    boundary = check_boundary(path)
    if boundary["columns"] != 1377 or boundary["reference_used_for_training"]:
        raise ValueError("ONLY_FINAL_V34_UNLABELLED_1377_SPACE")
    U = np.empty((n, 1377), complex, order="F")
    for chunk in boundary["chunks"]:
        with np.load(chunk["path"], allow_pickle=False) as z:
            values = z["u"]
            for first in range(0, values.shape[1], 8):
                U[
                    :,
                    chunk["start"] + first : chunk["start"]
                    + min(first + 8, values.shape[1]),
                ] = values[:, first : first + 8]
    with np.load(boundary["state"]["path"], allow_pickle=False) as z:
        saved = {k: np.array(z[k]) for k in ("a", "c", "r", "R")}
    Q = None
    if qr:
        Q = np.empty_like(U, order="F")
        R = np.zeros((1377, 1377), complex, order="F")
        # Reuse the frozen prefix factor only, never its older model/amplitudes.
        for chunk in boundary["anchor"]["chunks"]:
            with np.load(chunk["path"], allow_pickle=False) as z:
                lo, hi = chunk["start"], chunk["stop"]
                Q[:, lo:hi] = z["q"]
                R[:hi, lo:hi] = z["R_columns"]
        for event in boundary["qr_replay"]:
            lo, hi = event["start"], event["stop"]
            with np.load(event["path"], allow_pickle=False) as z:
                applied = np.array(z["applied"], order="F")
            Q, R = linalg.qr_delete(Q, R, lo, p=hi - lo, which="col", overwrite_qr=True)
            Q, R = linalg.qr_insert(
                Q, R, applied, lo, which="col", rcond=1e-12, overwrite_qru=True
            )
        if relative(R, saved["R"]) > 1e-10:
            raise ValueError("FINAL_QR_REPLAY_PAIR_FAILED")
    return U, Q, saved, boundary


def write_model(directory, original, arrays, manifest, *, oracle):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    state = directory / f"state_{monotonic_ns()}.npz"
    atomic_npz(state, **arrays)
    value = deepcopy(original)
    value.update(
        state=dict(path=str(state.resolve()), sha256=digest(state)),
        event=dict(
            kind="fixed_space_oracle" if oracle else "fixed_space_readout_audit"
        ),
        optimizer_state="NONE_FIXED_SPACE_AMPLITUDE_ONLY",
        source_sha=manifest["source_sha"],
        frozen_wave_chunks_unchanged=True,
    )
    value["binding"].update(
        source_sha=manifest["source_sha"], design_sha256=manifest["design_sha256"]
    )
    if oracle:
        value.update(POLICY)
    else:
        value.update(
            reference_used_for_training=False,
            reference_used_for_coefficient_fit=False,
            pde_only_solve=True,
            production_initialization_allowed=False,
            pde_only_solver_qualified=False,
            official_candidate_results=False,
        )
    pointer = directory / "committed.json"
    if pointer.exists():
        previous = directory / f"previous_{digest(pointer)}.json"
        if not previous.exists():
            atomic_json(previous, json.loads(pointer.read_text()))
    atomic_json(pointer, value)
    reread = check_boundary(directory / "committed.json")
    if oracle:
        require_oracle_policy(reread)
    return dict(
        path=str((directory / "committed.json").relative_to(ROOT)),
        sha256=digest(directory / "committed.json"),
    )


def unlabelled(action, packet, design, artifact, marker, manifest):
    from src.solvers.neural_wave_block_reconstruction import rebuild_stable

    records = {}
    previous = artifact / "initial_SVD_result.json"
    prior = json.loads(previous.read_text()) if previous.exists() else None
    if prior is not None and prior["bound_numerical_chain"][
        "src/solvers/neural_wave_block_reconstruction.py"
    ] != digest(ROOT / "src/solvers/neural_wave_block_reconstruction.py"):
        raise ValueError("PRIOR_COMBINATION_RECONSTRUCTION_SOURCE_CHANGED")
    for space_index, (name, entry) in enumerate(design["spaces"].items()):
        rng = np.random.default_rng(4213501 + space_index)
        if monotonic() >= manifest["worker_stop_monotonic"]:
            records[name] = dict(status="NOT_RUN_NUMERICAL_BUDGET")
            continue
        U, Q, saved, boundary = load_space(entry, action.size, qr=True)
        rows = []
        for i in range(3):
            if prior is not None:
                previous_record = prior["records"][name]
                row = previous_record["nonzero_combinations"][i]
                if (
                    previous_record["source_identity"] != entry
                    or row["index"] != i
                    or max(
                        row["complete_network_moment_relative"],
                        row["original_A_QR_relative"],
                    )
                    > 1e-10
                ):
                    raise ValueError("PRIOR_COMPLETE_COMBINATION_IDENTITY_FAILED")
                check_boundary(
                    artifact / name / f"witness_{i}" / "basis" / "committed.json"
                )
                rows.append(row)
                marker(
                    "healthy_nonzero_combination_reused",
                    dict(
                        space=name,
                        index=i,
                        original_source_sha=prior["source_sha"],
                        new_forward=0,
                    ),
                )
                continue
            a = (rng.standard_normal(1377) + 1j * rng.standard_normal(1377)) / np.sqrt(
                1377
            )
            c = compensated_columns(U, a)
            temp = artifact / name / f"witness_{i}" / "basis"
            write_model(
                temp,
                boundary,
                dict(saved, a=a, c=c, r=action.f - action.apply(c)),
                manifest,
                oracle=False,
            )
            actual, _, _ = rebuild_stable(temp, packet, marker)
            row = dict(
                index=i,
                complete_network_moment_relative=relative(actual, c),
                original_A_QR_relative=relative(
                    action.apply(actual), Q @ (saved["R"] @ a)
                ),
                denominator_definition="nonzero ||AUa|| for combination witness; original ||f|| for minimum residual",
            )
            if (
                max(
                    row["complete_network_moment_relative"],
                    row["original_A_QR_relative"],
                )
                > 1e-10
            ):
                raise ValueError("FROZEN_SPACE_NONZERO_COMBINATION_FAILED: " + str(row))
            rows.append(row)
            marker("unlabelled_nonzero_combination", dict(space=name, **row))
        arrays, stats = original_readout(U, Q, saved["R"], action.f, action.apply)
        old_r = action.f - action.apply(saved["c"])
        scales = np.asarray(stats["column_scales"])
        old_stationarity = float(
            np.linalg.norm(
                (saved["R"].conj().T @ (Q.conj().T @ old_r))
                / np.where(scales > 0, scales, 1)
            )
            / action.bnorm
        )
        if (
            relative(arrays["c"], saved["c"]) <= 1e-10
            and stats["normalized_first_order_optimality"] <= 1e-9
            and old_stationarity <= 1e-9
        ):
            # Exact byte reuse avoids reprocessing an unchanged healthy field.
            arrays = {k: saved[k] for k in ("a", "c", "r")}
            unchanged = True
        else:
            unchanged = False
        model = write_model(
            artifact / name / "basis",
            boundary,
            dict(arrays, R=saved["R"]),
            manifest,
            oracle=False,
        )
        stats.update(
            nonzero_combinations=rows,
            old_field_bitwise_reused=unchanged,
            old_normalized_first_order_optimality=old_stationarity,
            old_saved_residual_recomputed_pair=relative(saved["r"], old_r),
            retained_field_arrays_bitwise_equal=bool(
                np.array_equal(arrays["c"], saved["c"])
                and np.array_equal(arrays["r"], saved["r"])
            ),
            retained_native=float(
                np.linalg.norm(action.f - action.apply(arrays["c"])) / action.bnorm
            ),
            source_identity=entry,
            model=model,
            reference_used_for_training=False,
            pde_only_solve=True,
            combination_evidence_source_sha=prior["source_sha"]
            if prior is not None
            else manifest["source_sha"],
        )
        records[name] = stats
        atomic_json(artifact / name / "space_record.json", stats)
        marker(
            "unlabelled_space_frozen",
            dict(
                space=name, native=stats["retained_native"], rank=stats["retained_rank"]
            ),
        )
        del U, Q, saved, arrays
        gc.collect()
    return dict(
        records=records,
        reference_read_count=0,
        nonlinear_training_count=0,
        all_A_states_frozen_before_reference=True,
    )


def oracle(action, design, artifact, marker, manifest):
    profile = profile_paths(manifest["spec"])
    frozen = profile["artifacts"] / "v35_unlabelled_readout_audit/result.json"
    frozen_hash = digest(frozen)
    A = json.loads(frozen.read_text())
    reference_path = bound_path(design["reference"])
    if (
        design["reference"]["sha256"]
        != "0c3c0574a8c1eddcadfb56268e00c08e55d5cb15d44c0c76e873fcea0c467ff7"
    ):
        raise ValueError("ONLY_ORIGINAL_V1_P3_SCATTERED_REFERENCE")
    with np.load(reference_path, allow_pickle=False) as z:
        reference = np.array(z["c"])
        if relative(action.alpha(reference), z["alpha"]) > 1e-10:
            raise ValueError("SAME_P3_REFERENCE_PORT_IDENTITY")
    G = sparse.load_npz(bound_path(design["gram"]))
    if G.shape != (action.size, action.size):
        raise ValueError("ORIGINAL_MPC_GRAM_ORDER")
    records = {}
    for name, entry in design["spaces"].items():
        if monotonic() >= manifest["worker_stop_monotonic"]:
            records[name] = dict(status="NOT_RUN_NUMERICAL_BUDGET")
            continue
        if name not in A["records"] or "model" not in A["records"][name]:
            records[name] = dict(status="NOT_RUN_A_STATE_NOT_FROZEN")
            continue
        U, _, saved, boundary = load_space(entry, action.size, qr=False)
        try:
            arrays, stats = field_oracle(
                U,
                reference,
                G,
                deadline=manifest["worker_stop_monotonic"],
                heartbeat=marker,
            )
        except ReadoutStop as error:
            records[name] = dict(
                status="CONTROLLED_STOP_NUMERICAL_BUDGET", reason=str(error), **POLICY
            )
            atomic_json(artifact / name / "space_record.json", records[name])
            U = None
            saved = None
            gc.collect()
            continue
        model = write_model(
            artifact / name / "basis",
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
        raw = artifact / name / "projection_arrays.npz"
        atomic_npz(raw, **arrays)
        stats.update(
            model=model,
            projection_arrays=dict(path=str(raw.relative_to(ROOT)), sha256=digest(raw)),
            **POLICY,
        )
        records[name] = stats
        atomic_json(artifact / name / "space_record.json", stats)
        marker(
            "fixed_space_oracle_frozen",
            dict(space=name, E_G=stats["actual_E_G"], rank=stats["retained_rank"]),
        )
        del U, saved, arrays
        gc.collect()
    if digest(frozen) != frozen_hash:
        raise ValueError("A_STATE_CHANGED_AFTER_REFERENCE_EXPOSURE")
    return dict(records=records, bound_unlabelled_result_sha256=frozen_hash, **POLICY)


def run_stage(manifest, artifact, marker):
    spec = manifest["spec"]
    profile = profile_paths(spec)
    design = json.loads(profile["design"].read_text())
    if digest(profile["design"]) != manifest["design_sha256"]:
        raise ValueError("V35_DESIGN_CHANGED")
    if spec["role"] == "space_checks":
        from src.solvers.neural_space_qualification import qualify

        return qualify(artifact, manifest)
    if spec["role"] == "space_unlabelled":

        def firewall(event, args):
            if event == "open" and not unlabelled_open_allowed(
                args[0], design, artifact
            ):
                raise PermissionError(
                    "UNLABELLED_SPACE_LABEL_ACCESS_REJECTED: " + str(args[0])
                )

        sys.addaudithook(firewall)
    files = load_training_files(design)
    from src.solvers.feinn_native import load_native

    action = load_native(files["native"])
    if (action.size, action.nc, action.np) != (31968, 384, 40):
        raise ValueError("ORIGINAL_M5_COMPLETE_IDENTITY")
    # Conservative resident-bank plus small-factor and FE/packet scratch plan.
    # It is a shape bound for this audit, not a measured RSS or target estimate.
    planned = 13 * action.size * 1377 * 16 + 12 * 1377**2 * 16 + 2 * 2**30
    if planned > 12 * 2**30:
        raise MemoryError("FROZEN_SPACE_12GIB_PLANNING_LIMIT")
    marker(
        "frozen_space_memory_plan",
        dict(
            planned_bytes=planned,
            limit_bytes=12 * 2**30,
            actual_rss_measured_by_watchdog=True,
        ),
    )
    with np.load(files["moments_q30"], allow_pickle=False) as z:
        packet = {k: np.array(z[k]) for k in z.files}
    if not np.array_equal(packet["master_native_rows"], action.a["masters"]):
        raise ValueError("ORIGINAL_MASTER_ORDER_CHANGED")
    if spec["role"] == "space_unlabelled":
        result = unlabelled(action, packet, design, artifact, marker, manifest)
    elif spec["role"] == "space_oracle":
        result = oracle(action, design, artifact, marker, manifest)
    else:
        from src.runners.neural_space_verification import compare

        result = compare(action, packet, design, artifact, marker, manifest)
    result["bound_numerical_chain"] = {p: digest(ROOT / p) for p in CHAIN}
    return result
