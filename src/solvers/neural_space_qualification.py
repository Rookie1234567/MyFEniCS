"""Small independent whitened-SVD and actual atomic consumer qualifications."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import linalg

from src.io.neural_space_campaign import (
    POLICY,
    unlabelled_open_allowed,
    require_oracle_policy,
)
from src.io.input_loader import InputError
from src.io.neural_wave_campaign import ROOT
from src.solvers.neural_space_audit import field_oracle, original_readout, relative
from src.solvers.neural_wave_greedy import atomic_npz, atomic_json, sha


def qualify(artifact, manifest):
    from src.runners.neural_space_worker import write_model

    rng = np.random.default_rng(4213501)
    n, m = 19, 7
    x = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
    G = x.conj().T @ x + np.eye(n)
    C = linalg.cholesky(G, lower=False)
    base = rng.standard_normal((n, m)) + 1j * rng.standard_normal((n, m))
    reference = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    rows = []
    for kind in ("full", "duplicate", "near_rank_deficient", "different_scales"):
        U = base.copy()
        if kind == "duplicate":
            U[:, -1] = U[:, 0]
        if kind == "near_rank_deficient":
            U[:, -1] = U[:, 0] + 1e-14 * base[:, -1]
        if kind == "different_scales":
            U *= np.geomspace(1e-4, 1e4, m)
        arrays, stats = field_oracle(U, reference, G, deadline=perf_counter() + 60)
        scales = np.linalg.norm(C @ U, axis=0)
        z, _, rank, _ = linalg.lstsq(
            (C @ U) / scales, C @ reference, cond=1e-12, lapack_driver="gelsd"
        )
        independent = U @ (z / scales)
        pair = relative(arrays["c"], independent)
        if pair > 1e-10 or stats["retained_rank"] != rank:
            raise ValueError("INDEPENDENT_WHITENED_SVD_PAIR_FAILED")
        rows.append(
            dict(
                case=kind,
                relative=pair,
                rank=int(rank),
                G_orthogonality=stats["small_M_orthogonality_F"],
                rank_qualification=stats["field_precision_conclusion"],
            )
        )
    A = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
    f = rng.standard_normal(n) + 1j * rng.standard_normal(n)
    AU = A @ base
    Q, R = linalg.qr(AU, mode="economic")
    arrays, stats = original_readout(base, Q, R, f, lambda x: A @ x)
    ar = linalg.lstsq(AU, f, cond=1e-12, lapack_driver="gelsd")[0]
    if (
        relative(arrays["c"], base @ ar) > 1e-10
        or not stats["floating_numerical_qualified"]
    ):
        raise ValueError("NONHERMITIAN_ORIGINAL_LS_PAIR_FAILED")
    directory = Path(artifact) / "fixture"
    directory.mkdir(parents=True, exist_ok=True)
    chunk = directory / "chunk.npz"
    atomic_npz(
        chunk,
        u=base[:, :3],
        wave_q=np.zeros((1, 3)),
        q_real=np.zeros((1, 3)),
        decay_kappa=np.zeros((1, 3)),
        amplitude_map=np.eye(3),
        center=np.zeros(3),
        radius=np.ones(3),
        patch_level=np.asarray(0),
        patch_kind=np.asarray("global"),
    )
    ce = dict(path=str(chunk.resolve()), sha256=sha(chunk), start=0, stop=3)
    original = dict(
        schema="neural-wave.complex-backfit-boundary.v1",
        committed=True,
        chunks=[ce],
        anchor=dict(chunks=[ce]),
        qr_replay=[],
        columns=3,
        binding=dict(source_sha=manifest["source_sha"]),
        reference_used_for_training=False,
    )
    readout = dict(
        a=np.ones(3, complex),
        c=base[:, :3] @ np.ones(3),
        r=f - A @ (base[:, :3] @ np.ones(3)),
        R=R[:3, :3],
    )
    before = sha(chunk)
    receipt = write_model(directory / "model", original, readout, manifest, oracle=True)
    value = json.loads((ROOT / receipt["path"]).read_text())
    assert all(value.get(k) == v for k, v in POLICY.items()) and sha(chunk) == before
    design = dict(files={}, unlabelled_bound_files=[])
    denied = not unlabelled_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/reference_state.npz", design, directory
    )
    denied &= not unlabelled_open_allowed(
        ROOT / "benchmarks/artifacts/task42extra/unknown_label.npz", design, directory
    )
    if not denied:
        raise ValueError("UNLABELLED_REFERENCE_FIREWALL_FAILED")
    for field in POLICY:
        corrupt = dict(value)
        corrupt[field] = "PASS"
        atomic_json(directory / "corrupt.json", corrupt)
        reopened = json.loads((directory / "corrupt.json").read_text())
        try:
            require_oracle_policy(reopened)
        except InputError:
            pass
        else:
            raise ValueError("ORACLE_POLICY_DAMAGE_ACCEPTED")
    return dict(
        implementation_qualified=True,
        small_whitened_svd=rows,
        nonhermitian_original_pair=relative(arrays["c"], base @ ar),
        actual_writer_seal_reopen=True,
        policy_damage_negative_controls=len(POLICY),
        label_firewall_positive_negative=True,
        original_frozen_chunk_unchanged=True,
        new_FE_count=0,
        new_reference_solve_count=0,
        new_nonlinear_training_count=0,
    )
