"""Opt-in frozen-direction nonlinear witness, never an optimizer or completer."""

import json
from pathlib import Path
from time import perf_counter

import numpy as np

from src.solvers.feinn_discretization_audit import atomic_npz
from src.solvers.feinn_native import load_native
from src.solvers.feinn_saved_state import checked_entry
from src.solvers.neural_fe_action_packet import array_hash


def two_forwards(
    theta, delta, assign, forward, parameters, snapshot, restore, expected
):
    """The original boundary survives a forward error; trials never become models."""
    theta, delta = np.asarray(theta), np.asarray(delta)
    if theta.shape != delta.shape or not np.isfinite(delta).all():
        raise ValueError("FROZEN_PARAMETER_STEP_LAYOUT")
    buffers = snapshot()
    try:
        original = forward()
        identity = float(np.linalg.norm(original - expected) / np.linalg.norm(expected))
        if identity > 1e-10:
            raise ValueError("ORIGINAL_COMPLETE_C_FORWARD_IDENTITY")
        assign(theta + delta)
        actual = forward()
    finally:
        assign(theta)
        restore(buffers)
        if not np.array_equal(parameters(), theta):
            raise ValueError("WITNESS_PARAMETER_RESTORATION_FAILED")
    return (
        original,
        actual,
        dict(original_c_identity_relative=identity, theta_restored=True),
    )


def witness_gate():
    from src.runners.feinn_attribution_campaign import V18_WITNESS_RECORD
    from src.runners.feinn_common_descent_arrays import read_checked
    from src.solvers.feinn_common_descent import require

    pre = json.loads(V18_WITNESS_RECORD.read_text())
    gate = json.loads(read_checked(pre["A_checker"]).read_text())
    require(
        gate["C_admitted"] is True and gate["status"] == "COMPLETE",
        "BOTH_STATES_A_GATE_REQUIRED",
    )
    require(
        pre["states"] == ["M3600", "Mfinal"] and pre["rcond"] == 1e-10,
        "FIXED_WITNESS_INVENTORY",
    )
    require(
        pre["candidates"]
        == {key: gate["candidates"][key + "_1e-10"] for key in pre["states"]},
        "FROZEN_MAIN_CANDIDATES",
    )
    return pre, gate


def run(stage, design, pre, artifact, marker, manifest, load_index):
    from src.runners.feinn_native_constraint_arrays import POLICY
    from src.solvers.feinn_common_descent import atomic_json

    frozen, _ = witness_gate()
    cutoff = (
        manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - 150
    )

    def guard():
        if perf_counter() >= cutoff:
            raise RuntimeError("V18_NETWORK_WITNESS_SAVE_RESERVE")

    guard()
    packet = load_native(checked_entry(load_index("e1_fe")["files"]["native"]))
    if stage == "v18_native_network_restore":
        from petsc4py import PETSc
        from mpi4py import MPI

        if (
            PETSc.ScalarType != np.complex128
            or PETSc.IntType != np.int64
            or MPI.COMM_WORLD.size != 1
        ):
            raise RuntimeError("V18_FE_COMPLEX128_INT64_MPI1_REQUIRED")
        from src.solvers.feinn_saved_field_diagnostics import geometry, restore

        index = load_index("v18_native_network_witness")
        _, _, _, floquet, _, _, _ = geometry(design, packet)
        rows = {}
        with np.load(
            checked_entry(index["files"]["vectors"]), allow_pickle=False
        ) as arrays:
            for state in frozen["states"]:
                guard()
                c = np.array(arrays[state + "_c_actual"])
                _, defect = restore(floquet, packet, c)
                rows[state] = dict(MPC_relative=defect, c_sha256=array_hash(c))
        result = dict(
            status="INDEPENDENT_ACTUAL_NETWORK_FE_RESTORATION_COMPLETE",
            rows=rows,
            source_sha=manifest["source_sha"],
            original_witness=index["files"]["vectors"],
            A=0,
            AH=0,
            G=0,
            Gsolve=0,
            network_forward=0,
            **POLICY,
        )
        return result, {}
    if stage != "v18_native_network_witness":
        raise ValueError("ONLY_EXPLICIT_V18_WITNESS_STAGES")
    # Everything below is ML-only. The FE restoration branch stays Torch-free.
    import torch
    from scipy import sparse
    from src.runners.feinn_common_descent_arrays import extract, read_checked
    from src.solvers.feinn_phase_training import configure
    from src.solvers.feinn_riesz import SparseRiesz
    from src.solvers.feinn_saved_attribution import DiagnosticActions, frozen_fields
    from src.solvers.feinn_saved_state import model_state
    from src.solvers.feinn_torch import CompleteMomentMap
    from src.solvers.feinn_validation import parameters, assign, load_moments

    configure()
    native = load_index("e1_fe")
    G = sparse.load_npz(checked_entry(native["files"]["gram"]))
    moments = load_index("v8_phase_checks")["files"]["moments"]
    mapping = CompleteMomentMap(load_moments(checked_entry(moments)))
    if mapping.numeric_cache_bytes > 2 * 2**30 or mapping.size != packet.size:
        raise ValueError("WITNESS_CACHE_OR_COMPLETE_FE_LAYOUT")
    saved_fields = frozen_fields(load_index("v12_saved_state_freeze"), frozen["states"])
    old = load_index("v12_saved_field_attribution")["result"]
    factor = None
    ops = None
    arrays = {}
    rows = {}
    path = Path(artifact) / "nonlinear_witness_arrays.npz"

    def persist(status):
        atomic_npz(path, **arrays)
        record = dict(
            status=status,
            source_sha=manifest["source_sha"],
            A_checker=frozen["A_checker"],
            candidates=frozen["candidates"],
            rows=rows,
            actions=ops.record() if ops else dict(A=0, AH=0, Gsolve=0, G_matvec=0),
            complete_network_forwards=mapping.counts["forward"],
            JVP=0,
            VJP=mapping.counts["VJP"],
            Gram_factor_lifecycles=int(factor is not None),
            Gram_factor=factor.record if factor else None,
            detached_cache_bytes=mapping.numeric_cache_bytes,
            no_training=True,
            no_optimizer=True,
            no_Maxwell_factor=True,
            d_G=old["d_G"],
            d_G_new_solves=0,
            native_denominator=packet.bnorm,
            original_reference_scoring_only=True,
            **POLICY,
        )
        atomic_json(Path(artifact) / "partial_network_witness.json", record)
        return record

    try:
        guard()
        factor = SparseRiesz(G, design, marker)
        ops = DiagnosticActions(
            packet, G, factor, dict(A=6, AH=0, Gsolve=4, G_matvec=8), manifest
        )
        with np.load(read_checked(frozen["vectors"]), allow_pickle=False) as data:
            for state in frozen["states"]:
                guard()
                candidate = json.loads(
                    read_checked(frozen["candidates"][state]).read_text()
                )
                columns = candidate["columns"]
                if columns != list(range(8)):
                    raise ValueError("ORIGINAL_PDE8_COLUMN_ORDER")
                raw = extract(
                    data,
                    state,
                    ("P", "X", "GX", "Y", "WY", "theta", "r", "qr", "e", "Ge"),
                    frozen["array_layout"],
                    columns,
                )
                entry = pre["states"][state]
                model, saved = model_state(
                    design,
                    {
                        **entry["durable_final"],
                        "phase": True,
                        "reference_exposed": False,
                    },
                )
                theta = parameters(model)
                if (
                    not np.array_equal(theta, raw["theta"])
                    or array_hash(theta) != candidate["parameter_sha256"]
                ):
                    raise ValueError("FROZEN_WITNESS_PARAMETER_IDENTITY")
                if (
                    not np.array_equal(saved["complete_c"], saved_fields[state])
                    or array_hash(saved_fields[state]) != candidate["complete_c_sha256"]
                ):
                    raise ValueError("FROZEN_WITNESS_COMPLETE_C_IDENTITY")
                if saved["metadata"]["reference_used_for_training"] is not False:
                    raise ValueError("NO_SUPERVISED_MODEL_INPUT")
                alpha = np.asarray(candidate["alpha"])
                delta = raw["P"] @ alpha
                buffer_hash = {
                    name: array_hash(b.detach().numpy())
                    for name, b in model.named_buffers()
                }

                def snapshot():
                    return {
                        name: b.detach().clone() for name, b in model.named_buffers()
                    }

                def restore_buffers(values):
                    with torch.no_grad():
                        for name, b in model.named_buffers():
                            b.copy_(values[name])

                def forward():
                    guard()
                    if mapping.counts["forward"] >= 4:
                        raise RuntimeError("COMPLETE_FORWARD_CAP_4")
                    return mapping.forward(model, 8)

                c0, c1, proof = two_forwards(
                    theta,
                    delta,
                    lambda v: assign(model, v),
                    forward,
                    lambda: parameters(model),
                    snapshot,
                    restore_buffers,
                    saved_fields[state],
                )
                if buffer_hash != {
                    name: array_hash(b.detach().numpy())
                    for name, b in model.named_buffers()
                }:
                    raise ValueError("WITNESS_BUFFERS_NOT_RESTORED")
                cl = c0 + raw["X"] @ alpha
                r0, rl, r1 = [ops.A(c) - packet.f for c in (c0, cl, c1)]
                q0, q1 = ops.solve(r0), ops.solve(r1)
                Ge0 = ops.gm(raw["e"])
                Ge1 = Ge0 + ops.gm(c1 - c0)
                pairs = {
                    key: float(
                        np.linalg.norm(left - right)
                        / (np.linalg.norm(left) + np.linalg.norm(right))
                    )
                    for key, left, right in (
                        ("original_r", r0, raw["r"]),
                        ("original_qr", q0, raw["qr"]),
                        ("original_Ge", Ge0, raw["Ge"]),
                        ("linear_r", rl, raw["r"] + raw["Y"] @ alpha),
                    )
                }
                if max(pairs.values()) > 1e-10:
                    raise ValueError("WITNESS_ORIGINAL_OR_LINEAR_OPERATOR_IDENTITY")
                item = dict(
                    c_zero=c0,
                    c_linear=cl,
                    c_actual=c1,
                    r_zero=r0,
                    r_linear=rl,
                    r_actual=r1,
                    qr_zero=q0,
                    qr_linear=raw["qr"] + raw["WY"] @ alpha,
                    qr_actual=q1,
                    e_zero=raw["e"],
                    e_linear=raw["e"] + raw["X"] @ alpha,
                    e_actual=raw["e"] + c1 - c0,
                    Ge_zero=Ge0,
                    Ge_linear=Ge0 + raw["GX"] @ alpha,
                    Ge_actual=Ge1,
                    theta_zero=theta,
                    delta_theta=delta,
                    theta_trial=theta + delta,
                    theta_restored=parameters(model),
                )
                arrays.update({state + "_" + key: value for key, value in item.items()})
                rows[state] = dict(
                    **proof,
                    buffers_restored=True,
                    buffers_sha256=buffer_hash,
                    original_PT=entry["durable_final"],
                    original_source=entry["source_sha"],
                    theta_zero_sha256=array_hash(theta),
                    theta_trial_sha256=array_hash(theta + delta),
                    c_zero_sha256=array_hash(c0),
                    c_actual_sha256=array_hash(c1),
                    operator_pairings=pairs,
                    nonlinear_defect=float(
                        np.linalg.norm(c1 - cl) / np.linalg.norm(cl - c0)
                    ),
                )
                persist("NETWORK_WITNESS_PARTIAL")
                marker(
                    "committed_diagnostic_witness",
                    dict(state=state, nonlinear_defect=rows[state]["nonlinear_defect"]),
                )
                model = None
                del saved, raw
    finally:
        if factor is not None:
            factor.close()
        persist(
            "NETWORK_WITNESS_FROZEN" if len(rows) == 2 else "NETWORK_WITNESS_PARTIAL"
        )
    return persist("NETWORK_WITNESS_FROZEN"), dict(vectors=path)
