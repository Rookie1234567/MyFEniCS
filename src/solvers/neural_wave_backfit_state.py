"""Restore the sole unlabelled V32 anchor and exact low-rank QR replay."""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from scipy import linalg

from src.io.neural_wave_campaign import ROOT, digest
from src.io.neural_wave_backfit_store import check_boundary
from src.solvers.neural_wave_block import compensated_columns
from src.solvers.neural_wave_moments import Patch


def load_anchor(action, design):
    item = design["anchor"]
    path = ROOT / item["boundary_path"]
    if digest(path) != item["boundary_sha256"]:
        raise ValueError("FIXED_FINAL_ANCHOR_HASH_FAILED")
    boundary = json.loads(path.read_text())
    if (
        boundary["columns"] != 1377
        or len(boundary["chunks"]) != 246
        or boundary["binding"]["route"] != "FIXED_MULTISCALE_WAVE_BLOCK"
        or boundary["reference_used_for_training"]
    ):
        raise ValueError("SOLE_UNLABELLED_FIXED_ANCHOR_REQUIRED")
    n, m = action.size, boundary["columns"]
    if 128 * n * m + 128 * m * m + 2 * 2**30 > 12 * 2**30:
        raise MemoryError("BACKFIT_TEMPORARY_PLAN_EXCEEDS_12GIB")
    space = SimpleNamespace(
        action=action,
        m=m,
        U=np.empty((n, m), complex, order="F"),
        Q=np.empty((n, m), complex, order="F"),
        R=np.zeros((m, m), complex, order="F"),
    )
    blocks, chunks, first = [], [], 0
    for i, entry in enumerate(boundary["chunks"]):
        file = path.parent / entry["path"]
        if digest(file) != entry["sha256"] or entry["start"] != first:
            raise ValueError("ANCHOR_MAP_COLUMN_HASH_OR_ORDER_FAILED")
        last = entry["stop"]
        with np.load(file, allow_pickle=False) as z:
            space.U[:, first:last], space.Q[:, first:last] = z["u"], z["q"]
            space.R[:last, first:last] = z["R_columns"]
            block = dict(
                block_id=i,
                start=first,
                stop=last,
                wave_q=np.array(z["wave_q"]),
                amplitude_map=np.array(z["amplitude_map"]),
                patch=Patch(
                    tuple(z["center"]),
                    tuple(z["radius"]),
                    int(z["patch_level"]),
                    str(z["patch_kind"]),
                ),
            )
            if block["amplitude_map"].shape != (3 * len(block["wave_q"]), last - first):
                raise ValueError("FROZEN_RAW_TO_RETAINED_MAP_FAILED")
        blocks.append(block)
        chunks.append(dict(entry, path=str(file.resolve())))
        first = last
    state = path.parent / boundary["state"]["path"]
    if digest(state) != boundary["state"]["sha256"] or first != m:
        raise ValueError("ANCHOR_MATCHED_STATE_HASH_FAILED")
    with np.load(state, allow_pickle=False) as z:
        space.a, space.c, space.r = (np.array(z[k]) for k in ("a", "c", "r"))
    residual = float(
        np.linalg.norm(action.f - action.apply(space.c) - space.r) / action.bnorm
    )
    coefficient = float(
        np.linalg.norm(compensated_columns(space.U, space.a) - space.c)
        / max(np.linalg.norm(space.c), 1e-30)
    )
    if max(residual, coefficient) > 1e-10:
        raise ValueError("ANCHOR_COMPLETE_STATE_PAIR_FAILED")
    return (
        space,
        blocks,
        dict(
            boundary_path=str(path.resolve()),
            boundary_sha256=digest(path),
            chunks=chunks,
        ),
        dict(
            native=float(np.linalg.norm(space.r) / action.bnorm),
            columns=m,
            blocks=len(blocks),
            residual_pair=residual,
            U_amplitude_pair=coefficient,
        ),
    )


def restore_backfit(space, blocks, directory, binding):
    file = Path(directory) / "committed.json"
    if not file.exists():
        return None
    boundary = check_boundary(file)
    for k in (
        "route",
        "native_sha256",
        "moments_sha256",
        "design_sha256",
        "anchor_sha256",
    ):
        if boundary["binding"][k] != binding[k]:
            raise ValueError("BACKFIT_RESUME_IDENTITY_CHANGED: " + k)
    # Exact deletion/insertion chain, not a new original-AU factorization.
    for event in boundary["qr_replay"]:
        first, last = event["start"], event["stop"]
        with np.load(event["path"], allow_pickle=False) as z:
            applied = np.array(z["applied"], order="F")
        q, r = linalg.qr_delete(space.Q, space.R, first, p=last - first, which="col")
        space.Q, space.R = linalg.qr_insert(
            q, r, applied, first, which="col", rcond=1e-12
        )
    for block, entry in zip(blocks, boundary["chunks"], strict=True):
        with np.load(entry["path"], allow_pickle=False) as z:
            space.U[:, block["start"] : block["stop"]] = z["u"]
            block["wave_q"] = np.array(z["wave_q"])
            if "decay_kappa" in block:
                block["decay_kappa"] = (np.array(z["decay_kappa"])
                                         if "decay_kappa" in z.files
                                         else np.zeros_like(block["wave_q"]))
            if not np.array_equal(block["amplitude_map"], z["amplitude_map"]):
                raise ValueError("FROZEN_MAP_CHANGED_ON_RESTORE")
    with np.load(boundary["state"]["path"], allow_pickle=False) as z:
        space.a, space.c, space.r = (np.array(z[k]) for k in ("a", "c", "r"))
        if (
            np.linalg.norm(space.R - z["R"]) / max(np.linalg.norm(z["R"]), 1e-30)
            > 1e-10
        ):
            raise ValueError("QR_REPLAY_STORED_R_FAILED")
    if (
        np.linalg.norm(space.action.f - space.action.apply(space.c) - space.r)
        / space.action.bnorm
        > 1e-10
        or np.linalg.norm(compensated_columns(space.U, space.a) - space.c)
        / max(np.linalg.norm(space.c), 1e-30)
        > 1e-10
    ):
        raise ValueError("RESTORED_COMPLETE_STATE_FAILED")
    return boundary
