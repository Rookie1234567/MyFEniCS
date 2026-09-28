"""Explicit V3 consumed-artifact diagnostics; no teacher/factor fallback."""

import json
import time

import numpy as np

from src.runners.task042_coarse_stages import build_original, frozen_oracle
from src.runners.task042_experiment import scalar_audit
from src.runners.task042_shared import ARTIFACTS, ROOT, write_json
from src.solvers.coarse_inverse_protocol import CoarseRHS
from src.solvers.learned_coarse_data import (
    BorrowedMatrixAction,
    file_sha256,
    mapped_original_residual,
)
from src.solvers.learned_coarse_inverse import (
    BoundedBlockPC,
    cell_declarations,
    native_numpy_apply,
)
from src.solvers.learned_reduced_correction import ReducedCorrectionPC


def magnitude(values):
    return float(np.linalg.norm(values))


def pc_probe(pc, residual, apply, action):
    """Measure an auxiliary action, never feed its result into a KSP iterate."""
    started = time.perf_counter()
    z = pc.apply_array(residual)
    image = apply(z)
    native_r = mapped_original_residual(action, residual)
    native_image = mapped_original_residual(action, image)
    tiny = np.finfo(float).tiny
    denominator = float(np.vdot(native_image, native_image).real)
    step = np.vdot(native_image, native_r) / denominator if denominator else 0j
    return {
        "correction_norm": magnitude(z),
        "correction_over_residual": magnitude(z) / max(magnitude(residual), tiny),
        "Schur_image_over_residual": magnitude(image) / max(magnitude(residual), tiny),
        "native_image_over_residual": magnitude(native_image)
        / max(magnitude(native_r), tiny),
        "native_one_step_residual_ratio": magnitude(native_r - native_image)
        / max(magnitude(native_r), tiny),
        "native_optimal_scalar_residual_ratio": magnitude(
            native_r - step * native_image
        )
        / max(magnitude(native_r), tiny),
        "optimal_scalar_real": float(np.real(step)),
        "optimal_scalar_imag": float(np.imag(step)),
        "probe_seconds": time.perf_counter() - started,
    }


def verify_bound_files(proof):
    for item in proof:
        if file_sha256(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Consumed artifact identity changed: " + item["path"])


def reuse(runtime, directory, artifact, profile, design, marker):
    verify_bound_files(design["consumed_files"])
    matrix, action = runtime.p4_system.matrix, runtime.action
    native = native_numpy_apply(runtime.p4)
    apply = BorrowedMatrixAction(matrix)
    declarations = cell_declarations(action)
    b0 = BoundedBlockPC(
        matrix.getSize()[0],
        lambda a, b: matrix.getValues(
            np.arange(a, b, dtype=np.int64), np.arange(a, b, dtype=np.int64)
        ),
        cell_factor_bytes=sum(d.payload_bytes for d in declarations),
    )
    rows = []
    try:
        oracle = frozen_oracle(profile)
        with np.load(oracle["basis_path"], allow_pickle=False) as p:
            q, u, r = (p[name] for name in ("q", "u", "r"))
        weights = None
        for candidate, previous_name in design["previous_runs"].items():
            previous = ROOT / "results/task042" / previous_name
            old_artifact = ARTIFACTS / previous_name
            old_results = json.loads((previous / "coarse_results.json").read_text())
            if candidate == "R-NN":
                model = json.loads(
                    (
                        ROOT
                        / profile["model_qualification"]["directory"]
                        / "numerical_summary.json"
                    ).read_text()
                )
                if (
                    file_sha256(model["model_path"])
                    != profile["model_qualification"]["frozen_model_sha256"]
                ):
                    raise ValueError("Frozen NN model changed")
                with np.load(model["model_path"], allow_pickle=False) as p:
                    weights = {name: p[name] for name in p.files}
            pc = (
                b0
                if candidate == "R-B0"
                else ReducedCorrectionPC(
                    b0,
                    q,
                    u,
                    r,
                    apply,
                    lambda v: mapped_original_residual(action, v),
                    weights=weights,
                )
            )
            for index in design["diagnostic_indices"]:
                with np.load(
                    old_artifact / f"failure_{index:03d}.npz", allow_pickle=False
                ) as p:
                    rhs = CoarseRHS(p["rhs_fe"], p["rhs_port"])
                    state_fe, state_port = p["state_fe"], p["state_port"]
                constraints = action.condensed.trace_constraints
                x = np.zeros(action.reduced_size, dtype=np.complex128)
                for original in constraints.owned_active_original_dofs:
                    x[constraints.original_to_active[int(original)]] = state_fe[
                        int(original)
                    ]
                x[action.condensed.active_rows :] = state_port
                raw = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
                residual = raw - apply(x)
                d = action.evaluate_native_residual(
                    x, rhs.fe, native, port_rhs=rhs.port
                )
                mapped = mapped_original_residual(action, residual)
                history = json.loads(
                    (old_artifact / f"history_{index:03d}.json").read_text()
                )
                history_by_i = {h["iteration"]: h["reported"] for h in history}
                snapshots = []
                with np.load(
                    old_artifact / f"trajectory_{index:03d}.npz", allow_pickle=False
                ) as p:
                    for name in sorted(p.files):
                        iteration = int(name.split("_")[1])
                        v = p[name]
                        snapshots.append(
                            {
                                "iteration": iteration,
                                "reported_absolute": history_by_i[iteration],
                                "explicit_absolute": magnitude(v),
                                "explicit_relative_rhs": magnitude(v) / magnitude(raw),
                                "mapped_native_relative": magnitude(
                                    mapped_original_residual(action, v)
                                )
                                / d["native_rhs_operation_scale"],
                                "pc": pc_probe(pc, v, apply, action),
                            }
                        )
                boundaries = []
                for boundary in range(32, 257, 32):
                    boundaries.append(
                        {
                            "restart_end": boundary,
                            "reported_samples": [
                                h
                                for h in history
                                if boundary - 1 <= h["iteration"] <= boundary + 1
                            ],
                        }
                    )
                row = {
                    "candidate": candidate,
                    "index": index,
                    "label": old_results[index]["label"],
                    "original_source_sha": json.loads(
                        (previous / "run_manifest.json").read_text()
                    )["source_sha"],
                    "original_result": old_results[index],
                    "native": scalar_audit(d),
                    "explicit_Schur_absolute": magnitude(residual),
                    "explicit_Schur_relative_rhs": magnitude(residual) / magnitude(raw),
                    "reported_Schur_absolute": history[-1]["reported"],
                    "Schur_rhs_norm": magnitude(raw),
                    "Schur_port_absolute": magnitude(
                        residual[action.condensed.active_rows :]
                    ),
                    "Schur_cell_action_difference_relative": magnitude(
                        residual - d["schur_residual"]
                    )
                    / magnitude(raw),
                    "mapped_native_difference_relative": magnitude(
                        mapped - d["native_residual"]
                    )
                    / d["native_rhs_operation_scale"],
                    "submitted_recovery_difference_relative": magnitude(
                        state_fe - d["storage_solution"]
                    )
                    / max(magnitude(state_fe), np.finfo(float).tiny),
                    "snapshots": snapshots,
                    "restart_boundaries": boundaries,
                    "complete_reported_history": history,
                    "missing_explicit_restart_states": "Only 0/32/128/256 residual vectors were captured in V2; other explicit pre/post restart states not recorded.",
                }
                rows.append(row)
                write_json(directory / "reused_diagnostics.json", rows)
                marker(
                    "consumed_artifact_audit_complete",
                    {
                        "candidate": candidate,
                        "index": index,
                        "native": d["native_residual_relative"],
                        "map_difference": row["mapped_native_difference_relative"],
                    },
                )
            del pc
        return {
            "status": "CONSUMED_ARTIFACT_DIAGNOSIS_COMPLETE",
            "rows": rows,
            "global_p4_factor_created": False,
            "private_audit_csr": False,
            "old_results_reclassified": False,
            "solver_reexecuted": False,
        }
    finally:
        b0.factors.clear()
        apply.destroy()


def run_diagnostic_stage(cfg, comm, stage, directory, artifact, source, marker):
    profile = json.loads(
        (
            ROOT / "input/task042_neural_coarse_inverse/shared_profile_v1.json"
        ).read_text()
    )
    design = json.loads(
        (ROOT / "input/task042_neural_coarse_inverse/diagnostic_v3.json").read_text()
    )
    runtime, _f1, identity = build_original(cfg, comm, profile, marker)
    try:
        write_json(
            directory / "qualified_original_operator.json",
            {
                "identity": identity,
                "matrix": runtime.operator_identity,
                "full_p6_constructed": False,
            },
        )
        if stage == "V3-reuse":
            return reuse(runtime, directory, artifact, profile, design, marker)
        raise ValueError(
            "V3-overlap requires separately committed, preregistered implementation"
        )
    finally:
        runtime.destroy()
        marker("original_p4_stack_destroyed", {})
