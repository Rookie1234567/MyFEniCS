"""Bounded original-action QR refresh of retained neural columns, without labels.

This changes only the numerical readout of an existing wave space. It is not
an inverse of the FE operator, new wave training, or a relaxed rank threshold.
"""

import json
import os
from pathlib import Path
from time import monotonic, perf_counter

import numpy as np
from scipy import linalg

from src.solvers.neural_wave_block import BlockWaveSubspace, BlockBasisStore
from src.solvers.neural_wave_block_reconstruction import rebuild_stable
from src.solvers.neural_wave_greedy import atomic_json, atomic_npz, sha


def refresh_original_qr(space, deadline):
    """Reapply original A to each unchanged U column and refit fixed-rcond R.

    Unpivoted Householder QR preserves original column order and triangular chunk
    layout; the original small-R SVD still reveals rank at the fixed rcond. No
    normal equation, global Maxwell matrix, inverse, or Gram factor is formed.
    """
    n, m = space.action.size, space.m
    plan = int(
        space.U.nbytes
        + space.Q.nbytes
        + space.R.nbytes
        + 96 * n * m
        + 64 * m * m
        + 512 * 2**20
    )
    if not m or plan > 12 * 2**30:
        raise MemoryError("ORIGINAL_AU_QR_PLANNING_LINE_EXCEEDED")
    if monotonic() >= deadline - 150:
        raise TimeoutError("ORIGINAL_AU_QR_SAVE_RESERVE")
    old = (
        space.Q[:, :m].copy(),
        space.R[:m, :m].copy(),
        space.a,
        space.c,
        space.r,
        space.projection_null,
        space.effective_rank,
        space._small_basis_product,
        space._small_basis_product_columns,
    )
    before = float(np.linalg.norm(space.r) / space.action.bnorm)
    start = perf_counter()
    try:
        applied = np.empty((n, m), np.complex128, order="F")
        for j in range(m):
            if monotonic() >= deadline - 150:
                raise TimeoutError("ORIGINAL_AU_QR_SAVE_RESERVE")
            applied[:, j] = space.action.apply(space.U[:, j])
        if not np.isfinite(applied).all():
            raise ArithmeticError("ORIGINAL_AU_NONFINITE")
        q, r = linalg.qr(applied, mode="economic", check_finite=False)
        factor_pair = float(
            np.linalg.norm(applied - q @ r) / max(np.linalg.norm(applied), 1e-30)
        )
        if factor_pair > 1e-10:
            raise ArithmeticError("ORIGINAL_AU_QR_FACTOR_PAIR_FAILED")
        space.Q[:, :m], space.R[:m, :m] = q, r
        space._small_basis_product = None
        space._small_basis_product_columns = 0
        fit = space.fit_retained_amplitudes()
        after = float(np.linalg.norm(space.r) / space.action.bnorm)
        if after > before + 1e-10:
            raise ArithmeticError("ORIGINAL_AU_QR_RESIDUAL_INCREASE")
        return dict(
            qualified=True,
            columns=m,
            unchanged_rcond=space.rcond,
            before_native=before,
            after_native=after,
            factor_pair_relative=factor_pair,
            fit=fit,
            temporary_planning_bytes=plan,
            original_action_columns=m,
            column_order="UNCHANGED",
            global_Maxwell_factor_count=0,
            global_Gram_factor_count=0,
        )
    except Exception:
        (
            q,
            r,
            space.a,
            space.c,
            space.r,
            space.projection_null,
            space.effective_rank,
            space._small_basis_product,
            space._small_basis_product_columns,
        ) = old
        space.Q[:, :m], space.R[:m, :m] = q, r
        raise
    finally:
        space.seconds["orthogonalize"] += perf_counter() - start


def repair_saved_readout(
    action, packet, design, directory, artifact, source, design_hash, deadline, marker
):
    """Keep old files; qualify an atomic replacement before publishing it."""
    directory, artifact = Path(directory), Path(artifact)
    old_file = directory / "committed.json"
    old = json.loads(old_file.read_text())
    old_hash = sha(old_file)
    binding = dict(old["binding"], source_sha=source, design_sha256=design_hash)
    route_deadline = (
        old["binding"]["route_origin_monotonic"] + design["strategy"]["route_seconds"]
    )
    deadline = min(deadline, route_deadline - 1800)
    space = BlockWaveSubspace(action, 4096, rcond=1e-12)
    BlockBasisStore(directory, binding).restore(space, np.random.default_rng(0))
    costs = old["algorithm_state"]["cost_state"]
    for key in action.counts:
        action.counts[key] += costs["action_counts"][key]
        action.costs[key] += costs["action_seconds"][key]
    space.seconds.update(costs["qr_seconds"])
    result = dict(
        previous_boundary_sha256=old_hash,
        route=binding["route"],
        columns=space.m,
        reference_loaded=False,
        accepted_new_direction_count=0,
        source_sha=source,
    )
    try:
        refresh = refresh_original_qr(space, deadline)
    except (ArithmeticError, TimeoutError, MemoryError) as error:
        result.update(
            qualified=False,
            failure=str(error),
            current_boundary_unchanged=True,
            action_counts=dict(action.counts),
            action_seconds=dict(action.costs),
        )
        marker("original_AU_QR_refresh_rejected", result)
        return result
    suffix = str(int(monotonic() * 1e6))
    trial = artifact / ("trial_qr_" + suffix)
    trial.mkdir()
    chunks = []
    for entry in old["chunks"]:
        if monotonic() >= deadline - 150:
            raise TimeoutError("ORIGINAL_AU_QR_SAVE_RESERVE")
        original = directory / entry["path"]
        if sha(original) != entry["sha256"]:
            raise ValueError("ORIGINAL_BLOCK_CHANGED_DURING_REFRESH")
        first, last = entry["start"], entry["stop"]
        with np.load(original, allow_pickle=False) as z:
            arrays = {k: np.array(z[k]) for k in z.files}
        arrays.update(q=space.Q[:, first:last], R_columns=space.R[:last, first:last])
        file = trial / (original.stem + "_original_qr_" + suffix + ".npz")
        atomic_npz(file, **arrays)
        chunks.append(
            dict(
                entry,
                path=file.name,
                sha256=sha(file),
                source_sha=source,
                physical_wave_source_sha=entry["source_sha"],
                previous_chunk_sha256=entry["sha256"],
            )
        )
    state = trial / ("state_" + suffix + ".npz")
    atomic_npz(
        state,
        c=space.c,
        r=space.r,
        a=space.a,
        projection_null=space.projection_null,
        effective_rank=np.asarray(space.effective_rank),
    )
    candidate = json.loads(json.dumps(old))
    candidate.update(
        binding=binding,
        chunks=chunks,
        state=dict(path=state.name, sha256=sha(state)),
        committed=False,
        original_action_qr_refresh=refresh,
    )
    atomic_json(trial / "committed.json", candidate)
    start = perf_counter()
    rebuilt, saved, _ = rebuild_stable(trial, packet, marker)
    mapping = float(np.linalg.norm(rebuilt - saved) / max(np.linalg.norm(saved), 1e-30))
    result.update(
        refresh=refresh,
        complete_model_reconstruction_relative=mapping,
        model_reconstruction_seconds=perf_counter() - start,
        temporary_trial_path=str(trial),
        qualified=mapping <= 1e-10,
    )
    if not result["qualified"]:
        result.update(
            failure="REFRESHED_ACTUAL_MODEL_MAPPING_FAILED",
            current_boundary_unchanged=True,
        )
        marker("original_AU_QR_refresh_rejected", result)
        return result
    if monotonic() >= deadline - 120:
        result.update(
            qualified=False,
            failure="ORIGINAL_AU_QR_SAVE_RESERVE_AFTER_REBUILD",
            current_boundary_unchanged=True,
        )
        marker("original_AU_QR_refresh_rejected", result)
        return result
    candidate["committed"] = True
    candidate["remaining_seconds"] = deadline - monotonic()
    candidate["event"].update(
        native_relative=refresh["after_native"],
        audit=action.audit(space.c),
        small_full_action_pair_relative=refresh["fit"][
            "small_full_action_pair_relative"
        ],
        elapsed_seconds=monotonic() - binding["route_origin_monotonic"],
        boundary_kind="original_AU_QR_refresh_no_new_direction",
    )
    cost = candidate["algorithm_state"]["cost_state"]
    cost.update(
        action_counts=dict(action.counts),
        action_seconds=dict(action.costs),
        qr_seconds=dict(space.seconds),
    )
    # Interrupted trial primitives were not retained; do not reconstruct them.
    candidate["algorithm_state"]["primitive_history_complete"] = False
    atomic_json(directory / ("pre_original_qr_" + suffix + ".json"), old)
    for file in [trial / e["path"] for e in chunks] + [state]:
        os.replace(file, directory / file.name)
    atomic_json(old_file, candidate)  # Publish only after arrays and pointwise check.
    result.update(
        new_boundary_sha256=sha(old_file),
        current_boundary_unchanged=False,
        action_counts=dict(action.counts),
        action_seconds=dict(action.costs),
    )
    atomic_json(directory / ("original_qr_receipt_" + suffix + ".json"), result)
    marker("original_AU_QR_refresh_committed", result)
    return result
