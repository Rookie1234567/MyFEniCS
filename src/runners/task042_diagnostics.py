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
        if stage == "V3-overlap":
            return overlap(runtime, directory, artifact, design, marker)
        raise ValueError("Unknown V3 diagnostic stage")
    finally:
        runtime.destroy()
        marker("original_p4_stack_destroyed", {})


def overlap(runtime, directory, artifact, design, marker):
    from src.geometry.tetra_mesh_audit import canonical_owned_cell_ids
    from src.solvers.coarse_inverse_protocol import (
        CoarseReturnRejected,
        StrictCoarseReturn,
    )
    from src.solvers.hcurl_assembly_time_condensation import owned_active_support_groups
    from src.solvers.learned_coarse_inverse import (
        IterativeCoarseBackend,
        OriginalEquationAudit,
    )
    from src.solvers.learned_geometry_overlap import (
        CellPortOverlapPC,
        cell_port_indices,
        overlap_budget,
    )

    verify_bound_files(design["consumed_files"])
    proof = design["reuse_prerequisite"]
    previous = ROOT / proof["directory"]
    if file_sha256(previous / "reused_diagnostics.json") != proof["sha256"]:
        raise ValueError("V3 reuse evidence changed")
    previous_run = json.loads((previous / "run_summary.json").read_text())
    if not previous_run["descendants_cleared"] or previous_run["leader_exit_code"] != 0:
        raise ValueError("Reuse worker not released")
    matrix, action = runtime.p4_system.matrix, runtime.action
    native = native_numpy_apply(runtime.p4)
    apply = BorrowedMatrixAction(matrix)
    declarations = cell_declarations(action)
    cell_bytes = sum(d.payload_bytes for d in declarations)
    system = runtime.p4_system
    count = len(system.cell_recovery_maps)
    groups = tuple(np.array([i], dtype=np.int64) for i in range(count))
    supports = owned_active_support_groups(system, groups)
    patches = cell_port_indices(supports, system.active_rows, system.appended_rows)
    budget, _multiplicity = overlap_budget(action.reduced_size, patches, cell_bytes)
    if count != 252 or system.appended_rows != 80 or budget["max_patch_rows"] > 272:
        raise ValueError(
            "Frozen one-cell/all80-port patch geometry exceeds preregistered bound"
        )
    ids, geometry, _keys = canonical_owned_cell_ids(runtime.levels["mesh"])
    if len(geometry) != count:
        raise ValueError("FE geometry and condensed recovery cells differ")
    from src.runners.task042_experiment import digest

    geometry_audit = [
        {
            "local_cell": int(record.local_index),
            "canonical_cell": int(key),
            "bounds_min_nm": np.min(record.coordinates, axis=0).tolist(),
            "bounds_max_nm": np.max(record.coordinates, axis=0).tolist(),
            "trace_rows": len(support),
            "trace_rows_sha256": digest(support),
            "patch_rows_sha256": digest(patch),
        }
        for key, record, support, patch in zip(
            ids, geometry, supports, patches, strict=True
        )
    ]
    budget.update(
        global_p4_factor_created=False,
        private_audit_csr=False,
        temporary_object_policy="One principal dense block at a time; borrowed exact Schur/native action",
        process_tree_planning_bytes=design["structure"]["process_tree_planning_bytes"],
        numerical_histories_bytes_bound=3 * 257 * 4096,
        geometry=geometry_audit,
        original_MPC=system.trace_constraints.build_audit,
    )
    # Persist a complete validated allocation plan before the FIRST local LU.
    write_json(directory / "preconstruction_budget.json", budget)
    marker(
        "geometric_all_factor_budget_admitted",
        {k: v for k, v in budget.items() if k != "geometry"},
    )
    pc = None
    rows = []
    try:
        pc = CellPortOverlapPC(
            action.reduced_size,
            patches,
            lambda indices: matrix.getValues(indices, indices),
            cell_factor_bytes=cell_bytes,
        )
        write_json(
            directory / "candidate_construction.json",
            {
                "candidate": "R-GEO-CELL80-v3",
                "global_p4_factor_created": False,
                "private_audit_csr": False,
                "original_matrix_borrowed": True,
                "patch_factor_bytes": pc.factor_bytes,
                "cell_port_factor_bytes": cell_bytes,
                "representation_bytes": pc.representation_bytes,
                "setup_seconds": pc.setup_seconds,
                "factor_rows": [len(a) for a in patches],
                "restriction": "coordinate restriction in canonical MPC master/port space",
                "prolongation": "sum coordinate extensions, then divide each row by support multiplicity",
                "ports": "all80 in every subdomain, multiplicity252; unchanged original dense DtN port block",
                "geometry_support": "existing owned_active_support_groups on singleton physical FE cells",
                "teacher_solutions_accessed": False,
                "low_rank_space_loaded": False,
            },
        )
        old_name = design["previous_runs"]["R-B0"]
        old_artifact = ARTIFACTS / old_name
        old_results = json.loads(
            (ROOT / "results/task042" / old_name / "coarse_results.json").read_text()
        )
        for index in design["diagnostic_indices"]:
            # Only consume RHS arrays. Old states/teacher solutions are NOT initial guesses.
            with np.load(
                old_artifact / f"failure_{index:03d}.npz", allow_pickle=False
            ) as p:
                rhs = CoarseRHS(p["rhs_fe"], p["rhs_port"])
            history = []
            observation_seconds = 0.0
            probe_pc_seconds = 0.0

            def observer(
                iteration,
                reported,
                x,
                residual,
                raw,
                *,
                rhs=rhs,
                history=history,
                index=index,
            ):
                nonlocal observation_seconds, probe_pc_seconds
                started = time.perf_counter()
                d = action.evaluate_native_residual(
                    x, rhs.fe, native, port_rhs=rhs.port
                )
                mapped = mapped_original_residual(action, residual)
                row = {
                    "iteration": iteration,
                    "reported_absolute": reported,
                    "explicit_Schur_absolute": magnitude(residual),
                    "explicit_Schur_relative_rhs": magnitude(residual) / magnitude(raw),
                    "mapped_native_relative_rhs": magnitude(mapped)
                    / d["native_rhs_operation_scale"],
                    "native": scalar_audit(d),
                    "mapped_native_difference_relative": magnitude(
                        mapped - d["native_residual"]
                    )
                    / d["native_rhs_operation_scale"],
                    "Schur_cell_action_difference_relative": magnitude(
                        residual - d["schur_residual"]
                    )
                    / magnitude(raw),
                }
                if iteration % 32 == 0:
                    before = pc.seconds
                    row["pc"] = pc_probe(pc, residual, apply, action)
                    probe_pc_seconds += pc.seconds - before
                history.append(row)
                if iteration % 32 == 0:
                    write_json(artifact / f"full_history_{index:03d}.json", history)
                    marker(
                        "geometric_restart_audit",
                        {
                            "index": index,
                            "iteration": iteration,
                            "native": d["native_residual_relative"],
                            "port": d["port_residual_relative"],
                        },
                    )
                observation_seconds += time.perf_counter() - started

            backend = IterativeCoarseBackend(
                matrix,
                action,
                pc,
                runtime.operator_identity["csr_sha256"],
                declarations,
                diagnostic_observer=observer,
            )
            audit = OriginalEquationAudit(action, native)

            def failure(packet, *, rhs=rhs, index=index):
                state = packet["state"]
                if state is not None:
                    np.savez(
                        artifact / f"failure_{index:03d}.npz",
                        rhs_fe=rhs.fe,
                        rhs_port=rhs.port,
                        state_fe=state.fe,
                        state_port=state.port,
                    )

            verifier = StrictCoarseReturn(
                backend,
                witness_operator_sha256=runtime.operator_identity["csr_sha256"],
                original_a4=audit.native,
                port_closure=audit.port,
                recovery=audit.recovery,
                slave_dofs=tuple(
                    int(i) for i in runtime.levels["floquets"][4].mpc.slaves
                ),
                failure_sink=failure,
            )
            started = time.perf_counter()
            before_pc = pc.seconds
            passed = True
            try:
                verifier.solve(rhs)
            except CoarseReturnRejected:
                passed = False
            if not history or audit.last is None:
                raise ValueError(
                    "Numerical diagnostic did not produce a complete state"
                )
            write_json(artifact / f"full_history_{index:03d}.json", history)
            np.savez(
                artifact / f"trajectory_{index:03d}.npz",
                **{f"r_{i:03d}": v for i, v in backend.trajectory},
            )
            result = {
                "index": index,
                "label": old_results[index]["label"],
                "passed": passed,
                "strict_return": verifier.last_audit,
                "native": scalar_audit(audit.last),
                "ksp_reason": backend.last_reason,
                "iterations": history[-1]["iteration"],
                "seconds": time.perf_counter() - started,
                "observation_seconds": observation_seconds,
                "numerical_pc_seconds": pc.seconds - before_pc - probe_pc_seconds,
                "diagnostic_pc_seconds": probe_pc_seconds,
                "full_history_path": str(artifact / f"full_history_{index:03d}.json"),
                "full_history_sha256": file_sha256(
                    artifact / f"full_history_{index:03d}.json"
                ),
                "initial_guess": "exact reduced zero, original local particular recovery; no old/teacher solution",
                "rhs_role": "consumed diagnostic, not fresh qualification",
            }
            rows.append(result)
            write_json(directory / "coarse_results.json", rows)
            marker("geometric_rhs_complete", result)
        return {
            "status": "BOUNDED_STRUCTURAL_DIAGNOSTIC_COMPLETE",
            "candidate": "R-GEO-CELL80-v3",
            "rows": rows,
            "global_p4_factor_created": False,
            "private_audit_csr": False,
            "fresh_qualification": False,
            "F5_authorized": False,
            "factor_bytes": pc.factor_bytes + cell_bytes,
            "representation_bytes": pc.representation_bytes,
        }
    finally:
        if pc is not None:
            pc.factors.clear()
        apply.destroy()
