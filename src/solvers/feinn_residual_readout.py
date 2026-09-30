"""ML-only native residual readout in an already qualified frozen space.

The loading interface deliberately has no reference-index argument. The
supervised V5 correction members are inaccessible to the main computation.
"""

from copy import deepcopy
import json
import os
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.runners.feinn_workflow import sha, replay_closure_deadline
from src.solvers.feinn_gqr import GramColumns, squared_norm
from src.solvers.feinn_native import load_native
from src.solvers.feinn_readout import frozen_hashes, write_readout
from src.solvers.feinn_restricted_residual import (
    POLICY,
    ROUTE,
    load_basis,
    original_readout,
    restricted_solve,
)
from src.solvers.feinn_torch import CompleteMomentMap, CoordinateField
from src.solvers.feinn_validation import load_moments, parameters
from src.solvers.neural_fe_action_packet import array_hash
from src.solvers.optimization_checkpoint import (
    atomic_json,
    atomic_write,
    load_checkpoint,
    parameter_order,
)

EXPECTED = {
    "native": "2dbd60267758c2c53ea62a722ee0b07fad16f3cfae3f772bb0ba4830f4e28215",
    "gram": "2c984449248c02f01f4a41a681d00015bbe779add0ef30f0141d9eccf75b01c9",
    "moments": "0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e",
    "columns": "03bb974a41d8043bc5f0c9add72d615bbff9467c4ec0d51b01975fab6943a0ed",
    "projection_arrays": "80e28887f2d77e6900514d4f09d57ac22baf8e1beb700b1b4461687ab0f6705d",
    "parameter_only_model": "9d81e01df9aab13bd4e03dfb2ceebbd0e9ba7b459365356ec5ca4abcaf6909eb",
    "checkpoint": "2d166478509bbf14638c7beb0afcff321a5330b37f34f72c2e8737477d9cd58c",
}


def relative(x, y):
    return float(np.linalg.norm(x - y) / max(np.linalg.norm(y), 1e-30))


def checked(entry, name):
    if entry["sha256"] != EXPECTED[name] or sha(entry["path"]) != EXPECTED[name]:
        raise ValueError("ARTIFACT_BLOCKED: " + name)
    return entry["path"]


def load_unlabelled(design, native, grad, columns, previous, deadline):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if torch.version.cuda is not None or len(os.sched_getaffinity(0)) != 1:
        raise RuntimeError("CPU_ONLY_ONE_CORE_GATE_FAILED")
    if previous["result"]["status"] != "FROZEN_HIDDEN_READOUT_COMPLETE":
        raise ValueError("QUALIFIED_V5_COMMITTED_MODEL_REQUIRED")
    from src.runners.feinn_workflow import ROOT

    if (
        sha(ROOT / "input/materials/si_optical_constants_v1.json")
        != design["materials"]["material_table_sha256"]
    ):
        raise ValueError("FROZEN_MATERIAL_IDENTITY_FAILED")
    packet = load_native(checked(native["files"]["native"], "native"))
    action = GramColumns(
        sparse.load_npz(checked(native["files"]["gram"], "gram")),
        limit=480,
        deadline=deadline,
    )
    mapping = CompleteMomentMap(
        load_moments(checked(grad["files"]["moments"], "moments"))
    )
    model = CoordinateField(design["geometry"]["bounds_nm"], design["network"]["seed"])
    state = load_checkpoint(
        checked(previous["files"]["parameter_only_model"], "parameter_only_model"),
        EXPECTED["parameter_only_model"],
    )
    if state["parameter_order"] != parameter_order(model) or "optimizer" in state:
        raise ValueError("PARAMETER_ONLY_V5_MODEL_REQUIRED")
    model.load_state_dict(state["model"], strict=True)
    with np.load(
        checked(previous["files"]["checkpoint"], "checkpoint"), allow_pickle=False
    ) as data:
        # Do not load its fitted c or any reference/error field in T0/T1.
        if not np.array_equal(parameters(model), data["parameters"]):
            raise ValueError("V5_NPZ_PT_PARAMETERS_MISMATCH")
        for name, value in model.named_buffers():
            if not np.array_equal(value.numpy(), data[name]):
                raise ValueError("V5_BUFFER_MISMATCH")
    for name, value in model.named_parameters():
        value.requires_grad_(name.startswith("envelopes.6."))
    with np.load(
        checked(columns["files"]["columns"], "columns"), allow_pickle=False
    ) as data:
        Phi = np.array(data["Phi"])
        if json.loads(str(data["hidden_hashes"])) != frozen_hashes(model):
            raise ValueError("V5_HIDDEN_COLUMN_IDENTITY_FAILED")
    basis = load_basis(
        checked(previous["files"]["projection_arrays"], "projection_arrays")
    )
    if (
        Phi.shape != (31968, 195)
        or basis["Q_eff"].shape != Phi.shape
        or mapping.size != packet.size
        or len(parameters(model)) != 8966
        or sum(p.numel() for p in model.parameters() if p.requires_grad) != 390
        or array_hash(Phi) != columns["result"]["Phi_sha256"]
    ):
        raise ValueError("FROZEN_SPACE_INVENTORY_FAILED")
    original_readout(np.ones(195, complex), basis)  # validate all retained directions
    if perf_counter() >= deadline:
        raise RuntimeError("READOUT_SAVE_WINDOW_REACHED_DURING_LOAD")
    return packet, action, mapping, model, Phi, basis


def directions():
    rng = np.random.default_rng(421601)
    return [
        rng.normal(size=195) + 1j * rng.normal(size=195),
        1j * rng.normal(size=195),
        rng.normal(size=195) + 1j * rng.normal(size=195),
    ]


def checks(design, native, grad, columns, previous, artifact, marker, manifest):
    began = perf_counter()
    packet, G, mapping, model, Phi, basis = load_unlabelled(
        design, native, grad, columns, previous, replay_closure_deadline(manifest)
    )
    initial_hash = frozen_hashes(model)
    rows = []
    rng = np.random.default_rng(421601)
    for j, y in enumerate(directions()):
        a = original_readout(y, basis)
        ideal = basis["Q_eff"] @ y
        via_phi = Phi @ a
        write_readout(model, a)
        actual = mapping.forward(model, 8)
        diff = actual - ideal
        Gi = G(ideal, "T0_random_norm")
        Gdiff = G(diff, "T0_mapping")
        norm = squared_norm(ideal, Gi)
        x = (rng.normal(size=packet.size) + 1j * rng.normal(size=packet.size)).astype(
            complex
        )
        Av, AHx = packet.apply(ideal), packet.apply(x, adjoint=True)
        dot_left, dot_right = np.vdot(x, Av), np.vdot(AHx, ideal)
        row = dict(
            Phi_Q_relative=relative(via_phi, ideal),
            network_Q_relative=relative(actual, ideal),
            network_G_relative=float(np.sqrt(squared_norm(diff, Gdiff) / norm)),
            reused_G_orthogonality_random_defect=abs(norm - np.vdot(y, y).real)
            / np.vdot(y, y).real,
            conjugate_transpose_operation_relative=float(
                abs(dot_left - dot_right)
                / (
                    np.linalg.norm(x) * np.linalg.norm(Av)
                    + np.linalg.norm(AHx) * np.linalg.norm(ideal)
                )
            ),
            all_three_component_readout_norms=np.linalg.norm(
                a.reshape(3, 65), axis=1
            ).tolist(),
        )
        if j == 0:
            row["batch1_8_relative"] = relative(mapping.forward(model, 1), actual)
        rows.append(row)
        marker("restricted_native_direction", row)
    good = all(
        r["Phi_Q_relative"] <= 1e-10
        and r["network_Q_relative"] <= 1e-10
        and r["network_G_relative"] <= 1e-9
        and r["conjugate_transpose_operation_relative"] <= 1e-10
        and r["reused_G_orthogonality_random_defect"] <= 1e-9
        for r in rows
    )
    good &= (
        rows[0]["batch1_8_relative"] <= 1e-10 and frozen_hashes(model) == initial_hash
    )
    result = dict(
        status="RESIDUAL_READOUT_CHECKS_PASS"
        if good
        else "RESIDUAL_READOUT_CHECKS_FAILED",
        directions=rows,
        seed=421601,
        projection_members_loaded=list(basis),
        target_reference_loaded=False,
        hidden_buffers_unchanged=frozen_hashes(model) == initial_hash,
        native_action_counts=packet.counts,
        G_action_columns=G.count,
        wall_seconds=perf_counter() - began,
        **POLICY,
    )
    path = Path(artifact) / "operator_readout_checks.json"
    atomic_json(path, result)
    return result, dict(checks=path)


def run(design, native, grad, columns, previous, qualified, artifact, marker, manifest):
    began = perf_counter()
    deadline = replay_closure_deadline(manifest)
    if qualified["result"]["status"] != "RESIDUAL_READOUT_CHECKS_PASS":
        raise ValueError("T0_QUALIFICATION_REQUIRED")
    packet, G, mapping, model, Phi, basis = load_unlabelled(
        design, native, grad, columns, previous, deadline
    )
    initial_hash = frozen_hashes(model)
    Qg = basis["Q_eff"]
    B = np.empty_like(Qg)
    for j in range(195):
        G.check()  # time only, no G action
        if packet.counts["A"] + qualified["result"]["native_action_counts"]["A"] >= 248:
            raise RuntimeError("READOUT_A_COLUMN_BUDGET_RESERVE")
        B[:, j] = packet.apply(Qg[:, j].copy())
        if (j + 1) % 10 == 0:
            marker("restricted_A_columns", dict(complete=j + 1, total=195))
    pairings = []
    for y in directions():
        By, AQy = B @ y, packet.apply(Qg @ y)
        pairings.append(
            float(np.linalg.norm(By - AQy) / (np.linalg.norm(By) + np.linalg.norm(AQy)))
        )
    G.check()
    arrays, stats = restricted_solve(B, packet.f)
    a = original_readout(arrays["y"], basis)
    ideal = Qg @ arrays["y"]
    linear = Phi @ a
    write_readout(model, a)
    actual = mapping.forward(model, 8)
    norm = squared_norm(ideal, G(ideal, "T1_ideal_field_norm"))
    pair = {}
    for name, other in (("Q_eff", ideal), ("Phi", linear)):
        diff = actual - other
        pair[name] = dict(
            euclidean_relative=relative(actual, other),
            G_relative=float(
                np.sqrt(squared_norm(diff, G(diff, "T1_writeback")) / norm)
            ),
        )
    actual_r = packet.apply(actual) - packet.f
    ideal_r = B @ arrays["y"] - packet.f
    stats.update(
        By_AQy_operation_relative=pairings,
        reconstruction=pair,
        network_residual_pairing=float(
            np.linalg.norm(actual_r - ideal_r) / packet.bnorm
        ),
        actual_native_relative=float(np.linalg.norm(actual_r) / packet.bnorm),
        hidden_buffers_unchanged=frozen_hashes(model) == initial_hash,
        readout_norm=float(np.linalg.norm(a)),
        readout_max=float(np.max(abs(a))),
        cancellation_amplification=float(
            np.linalg.norm(Phi, axis=0) @ abs(a) / np.linalg.norm(linear)
        ),
        original_native_audit=packet.audit(actual),
    )
    stable = (
        max(pairings) <= 1e-10
        and stats["QR_reconstruction_relative"] <= 1e-10
        and stats["QR_orthogonality_F"] <= 1e-10
        and stats["retained_optimality"] <= 1e-9
        and stats["residual_projection_defect"] <= 1e-8
        and stats["network_residual_pairing"] <= 1e-9
        and stats["hidden_buffers_unchanged"]
        and stats["rho"] <= 1 + 1e-9
    )
    writeback = all(
        x["euclidean_relative"] <= 1e-10 and x["G_relative"] <= 1e-9
        for x in pair.values()
    )
    status = (
        "FROZEN_FEATURE_RESIDUAL_FLOOR_MEASURED"
        if stable and writeback and stats["retained_rank"] == 195
        else "RESOLVED_SUBSPACE_ONLY"
        if stable and writeback
        else "READOUT_RECONSTRUCTION_UNSTABLE"
        if not writeback
        else "NUMERICAL_SPAN_UNRESOLVED"
    )
    metadata = dict(
        source_sha=manifest["source_sha"],
        input_sha256=manifest["input_sha256"],
        state_kind="parameter_only_reference_exposed_residual_readout",
        optimizer_state_saved=False,
        frozen_hashes=initial_hash,
        projection_members_loaded=list(basis),
        target_reference_loaded=False,
        **POLICY,
    )
    artifact = Path(artifact)
    pt = artifact / "frozen_model_parameter_only.pt"
    atomic_write(
        pt,
        lambda stream: torch.save(
            dict(
                model=deepcopy(model.state_dict()),
                parameter_order=parameter_order(model),
                metadata=metadata,
            ),
            stream,
        ),
    )
    cp = artifact / "frozen_checkpoint.npz"
    atomic_write(
        cp,
        lambda stream: np.savez(
            stream,
            parameters=parameters(model),
            c=actual,
            a1=a,
            **{k: v.detach().numpy().copy() for k, v in model.named_buffers()},
            source_sha=manifest["source_sha"],
            input_sha256=manifest["input_sha256"],
            model_sha256=sha(pt),
            state_kind=metadata["state_kind"],
            **POLICY,
        ),
    )
    proj = artifact / "residual_projection_arrays.npz"
    atomic_write(proj, lambda stream: np.savez(stream, **arrays))
    result = dict(
        status=status,
        route=ROUTE,
        projection=stats,
        target_reference_loaded=False,
        projection_members_loaded=list(basis),
        G_action_columns=G.count,
        G_action_columns_by_role=G.by_role,
        native_action_counts=packet.counts,
        optimizer_steps=0,
        Gsolve_count=0,
        Gram_factor_count=0,
        Maxwell_factor_count=0,
        wall_seconds=perf_counter() - began,
        numeric_cutoff_monotonic=deadline,
        exit_reserve_from_launch_seconds=manifest["supervision_budget_origin_monotonic"]
        + manifest["supervised_limit_seconds"]
        - perf_counter(),
        **POLICY,
    )
    record = artifact / "residual_projection.json"
    atomic_json(record, result)
    marker(
        "frozen_residual_readout",
        dict(status=status, rho=stats["rho"], rank=stats["retained_rank"]),
    )
    return result, dict(
        checkpoint=cp,
        parameter_only_model=pt,
        projection_arrays=proj,
        projection=record,
    )
