"""Review V1's finite V4 stages; numerical algorithms live in solvers."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.io.task042_v4_gate import diagnostic_status, select_route, strict_from_norms
from src.runners.task042_coarse_stages import build_original
from src.runners.task042_experiment import digest, scalar_audit
from src.runners.task042_shared import ROOT, write_json
from src.solvers.coarse_inverse_protocol import (
    CoarseReturnRejected,
    CoarseRHS,
    StrictCoarseReturn,
)
from src.solvers.hcurl_assembly_time_condensation import owned_active_support_groups
from src.solvers.learned_coarse_data import (
    BorrowedMatrixAction,
    file_sha256,
    mapped_original_residual,
)
from src.solvers.learned_coarse_inverse import (
    IterativeCoarseBackend,
    OriginalEquationAudit,
    cell_declarations,
    native_numpy_apply,
)
from src.solvers.learned_geometry_overlap import (
    CellPortOverlapPC,
    cell_port_indices,
    overlap_budget,
)
from src.solvers.learned_two_level import (
    BalancedTwoLevelPC,
    algebra_audit,
    build_schur_encoding,
    error_space,
    space_budget,
)

CONFIG = ROOT / "input/task042_neural_coarse_inverse/two_level_v4.json"
INDEX = ROOT / "tmp/task042/v4/stage_index.json"
METRICS = (
    "native_residual_relative",
    "port_residual_relative",
    "internal_residual_relative",
    "native_identity_relative",
    "schur_port_identity_relative",
)


def norm(x):
    return float(np.linalg.norm(x))


def ratio(value, scale):
    # Exact-zero reference uses an explicitly labelled absolute check, never
    # a favorable fitted denominator. Nonzero scales stay strictly relative.
    return value / scale if scale else value


def completed(stage):
    proof = json.loads(INDEX.read_text())[stage]
    directory = Path(proof["directory"])
    for name, sha in proof["files_sha256"].items():
        if file_sha256(directory / name) != sha:
            raise ValueError("V4 prerequisite changed: " + stage + "/" + name)
    supervision = json.loads((directory / "run_summary.json").read_text())
    if supervision["leader_exit_code"] != 0 or not supervision["descendants_cleared"]:
        raise ValueError("V4 prerequisite not released")
    return directory, json.loads((directory / "numerical_summary.json").read_text())


def local_pc(runtime, directory, design, marker):
    matrix, action = runtime.p4_system.matrix, runtime.action
    cells = cell_declarations(action)
    cell_bytes = sum(d.payload_bytes for d in cells)
    count = len(runtime.p4_system.cell_recovery_maps)
    supports = owned_active_support_groups(
        runtime.p4_system, tuple(np.array([i], dtype=np.int64) for i in range(count))
    )
    patches = cell_port_indices(
        supports, runtime.p4_system.active_rows, runtime.p4_system.appended_rows
    )
    plan, _ = overlap_budget(action.reduced_size, patches, cell_bytes)
    frozen = design["geometry"]
    if file_sha256(ROOT / frozen["evidence_path"]) != frozen["evidence_sha256"]:
        raise ValueError("Frozen V3 geometry evidence changed")
    old = json.loads((ROOT / frozen["evidence_path"]).read_text())
    if (
        count != 252
        or runtime.p4_system.appended_rows != 80
        or [digest(p) for p in patches]
        != [g["patch_rows_sha256"] for g in old["geometry"]]
    ):
        raise ValueError("R-GEO-CELL80-v3 support changed")
    if (
        file_sha256(ROOT / "src/solvers/learned_geometry_overlap.py")
        != frozen["implementation_sha256"]
    ):
        raise ValueError("Frozen local PC implementation changed")
    plan.update(
        space_budget(
            action.reduced_size,
            128,
            plan["representation_bytes"],
            plan["all_factor_bytes"],
        )
    )
    plan.update(
        global_p4_factor_created=False,
        private_audit_csr=False,
        original_matrix_borrowed=True,
        local_PC="R-GEO-CELL80-v3",
        process_tree_planning_bytes=8 * 2**30,
    )
    write_json(directory / "preconstruction_budget.json", plan)
    marker("V4_capacity_admitted_before_any_local_factor", plan)
    pc = CellPortOverlapPC(
        action.reduced_size,
        patches,
        lambda indices: matrix.getValues(indices, indices),
        cell_factor_bytes=cell_bytes,
    )
    return pc, cells, cell_bytes


def action_pair(runtime, apply, native, vectors):
    rows = []
    action = runtime.action
    zero = np.zeros(action.condensed.full_rows, dtype=np.complex128)
    for vector in vectors:
        image = apply(vector)
        d = action.evaluate_native_residual(vector, zero, native)
        mapped = mapped_original_residual(action, -image)
        rows.append(
            {
                "Schur_independent_cell_relative": ratio(
                    norm(-image - d["schur_residual"]),
                    norm(image) + norm(d["schur_residual"]),
                ),
                "native_independent_map_relative": ratio(
                    norm(mapped - d["native_residual"]),
                    norm(mapped) + norm(d["native_residual"]),
                ),
                "native_identity_relative": d["native_identity_relative"],
                "schur_port_identity_relative": d["schur_port_identity_relative"],
            }
        )
    return {
        "passed": all(
            np.isfinite(v) and v <= 1e-10 for row in rows for v in row.values()
        ),
        "directions": rows,
        "limit": 1e-10,
        "private_audit_csr": False,
    }


def p0(runtime, local, apply, native, directory, artifact):
    rng = np.random.default_rng(420700)
    z = np.linalg.qr(
        rng.standard_normal((runtime.action.reduced_size, 4))
        + 1j * rng.standard_normal((runtime.action.reduced_size, 4))
    )[0]
    pair = action_pair(runtime, apply, native, (z[:, 0], 1j * z[:, 1], 1e-3 * z[:, 2]))
    z, u, r, encoding = build_schur_encoding(z, apply)
    pc = BalancedTwoLevelPC(local, apply, z, u, r)
    algebra = algebra_audit(pc, count=2)
    write_json(
        directory / "real_action_algebra.json",
        {"action_pair": pair, "encoding": encoding, "algebra": algebra},
    )
    if not pair["passed"] or not algebra["passed"]:
        raise ValueError("P0_REAL_ACTION_OR_TWO_LEVEL_ALGEBRA_BLOCKED")
    return {
        "status": "P0_PASSED",
        "action_pair": pair,
        "encoding": encoding,
        "algebra": algebra,
        "teacher_loaded": False,
    }


def load_train_metadata(profile, design):
    proof = profile["teacher_qualification"]
    directory = ROOT / proof["directory"]
    supervision = json.loads((directory / "run_summary.json").read_text())
    manifest = json.loads((directory / "run_manifest.json").read_text())
    numerical = json.loads((directory / "numerical_summary.json").read_text())
    path = Path(numerical["dataset_manifest"])
    if (
        file_sha256(path) != proof["manifest_sha256"]
        or manifest["source_sha"] != proof["source_sha"]
        or manifest["git_status"]
        or supervision["leader_exit_code"] != 0
        or not supervision["descendants_cleared"]
    ):
        raise ValueError("Teacher source/hash/release identity")
    data = json.loads(path.read_text())
    if (
        data["operator_sha256"] != profile["f1_qualification"]["operator_sha256"]
        or data["precision"] != "complex128"
        or data["status"] != "TEACHER_QUALIFIED"
    ):
        raise ValueError("Teacher operator/normalization qualification")
    train = data["splits"]["train"]
    if file_sha256(train["residuals_path"]) != train["residuals_sha256"]:
        raise ValueError("Train labels/audits changed")
    labels = json.loads(Path(train["residuals_path"]).read_text())
    selected = design["training_problems"]
    if len(selected) > 16 or len(
        {s["label"]["whole_problem"] for s in selected}
    ) != len(selected):
        raise ValueError("Independent train whole-problem inventory")
    verified_packets = set()
    for record in selected:
        original = labels[record["index"]]
        if (
            original["label"] != record["label"]
            or not original["passed"]
            or not all(
                np.isfinite(v) and v <= 1e-10 for v in original["metrics"].values()
            )
        ):
            raise ValueError("Selected teacher label/residual changed")
        packet = train["files"][record["batch_index"]]
        if packet != record["teacher_packet"]:
            raise ValueError("Selected train packet changed")
        if packet["path"] not in verified_packets:
            if file_sha256(packet["path"]) != packet["sha256"]:
                raise ValueError("Selected train packet changed")
            verified_packets.add(packet["path"])
    return data, path


class LowFrequencyAudit:
    def __init__(self, runtime, apply, native, rhs, marker, index):
        self.runtime, self.apply, self.native, self.rhs = runtime, apply, native, rhs
        self.marker, self.index = marker, index
        self.rows = []
        self.seconds = 0.0
        self.port_reference = None
        self.native_reference = None

    def __call__(self, iteration, reported, x, residual, raw):
        started = time.perf_counter()
        action = self.runtime.action
        d = action.evaluate_native_residual(
            x, self.rhs.fe, self.native, port_rhs=self.rhs.port
        )
        mapped = mapped_original_residual(action, residual)
        if self.port_reference is None:
            self.port_reference = d["port_operation_scale"]
            self.native_reference = d["native_rhs_operation_scale"]
        slaves = self.runtime.levels["floquets"][4].mpc.slaves
        row = {
            "iteration": int(iteration),
            "reported_Schur_absolute": float(reported),
            "explicit_Schur_absolute": norm(residual),
            "fixed_Schur_rhs_norm": norm(raw),
            "explicit_Schur_relative_rhs": ratio(norm(residual), norm(raw)),
            "native": scalar_audit(d),
            "port_absolute": norm(d["augmented_port_residual"]),
            "port_initial_reference_scale": self.port_reference,
            "port_fixed_reference_value": ratio(
                norm(d["augmented_port_residual"]), self.port_reference
            ),
            "port_fixed_reference_rule": "relative"
            if self.port_reference
            else "exact-zero initial reference: absolute",
            "mapped_native_difference_relative": ratio(
                norm(mapped - d["native_residual"]),
                d["native_identity_operation_scale"],
            ),
            "Schur_cell_action_difference_relative": ratio(
                norm(residual - d["schur_residual"]), norm(raw) + norm(raw - residual)
            ),
            "maximum_slave_storage": float(
                np.max(np.abs(d["storage_solution"][slaves]), initial=0)
            ),
            "finite": bool(
                np.isfinite(x).all() and np.isfinite(d["storage_solution"]).all()
            ),
        }
        self.rows.append(row)
        self.seconds += time.perf_counter() - started
        self.marker(
            "V4_restart_full_original_audit",
            {
                "index": self.index,
                "iteration": iteration,
                "native": d["native_residual_relative"],
                "Schur": row["explicit_Schur_relative_rhs"],
            },
        )
        if (
            not row["finite"]
            or row["maximum_slave_storage"]
            or any(
                row[k] > 1e-10
                for k in (
                    "mapped_native_difference_relative",
                    "Schur_cell_action_difference_relative",
                )
            )
            or any(
                d[k] > 1e-10
                for k in (
                    "native_identity_relative",
                    "schur_port_identity_relative",
                    "internal_residual_relative",
                )
            )
        ):
            raise ValueError("V4_INDEPENDENT_INTERFACE_OR_RECOVERY_BLOCKED")


def p1(
    runtime, local, cells, apply, native, profile, design, directory, artifact, marker
):
    _, gate = completed("V4-P0")
    if gate["status"] != "P0_PASSED":
        raise ValueError("P1 prerequisite")
    metadata_started = time.perf_counter()
    data, data_path = load_train_metadata(profile, design)
    metadata_verification_seconds = time.perf_counter() - metadata_started
    action = runtime.action
    rows = []
    snapshot_count = 0
    for record in design["training_problems"]:
        started = time.perf_counter()
        j = record["row_in_batch"]
        with np.load(record["teacher_packet"]["path"], allow_pickle=False) as packet:
            rhs = CoarseRHS(packet["rhs_fe"][j], packet["rhs_port"][j])
            star = packet["solution"][j].copy()
            raw_saved = packet["raw"][j].copy()
            scale = float(packet["normalization_scale"][j])
        raw = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        if (
            star.shape != (action.reduced_size,)
            or ratio(norm(raw - raw_saved), norm(raw)) > 1e-10
        ):
            raise ValueError("Teacher canonical normalization mismatch")
        reference_started = time.perf_counter()
        teacher_residual = raw - apply(star)
        reference = action.evaluate_native_residual(
            star, rhs.fe, native, port_rhs=rhs.port
        )
        if ratio(norm(teacher_residual), norm(raw)) > 1e-10 or any(
            reference[k] > 1e-10 for k in METRICS
        ):
            raise ValueError("Reused selected teacher not accurate")
        reference_seconds = time.perf_counter() - reference_started
        snapshots = []
        arrays = {}
        capture_seconds = 0.0

        def capture(
            iteration,
            x,
            *,
            star=star,
            raw=raw,
            teacher_residual=teacher_residual,
            snapshots=snapshots,
            arrays=arrays,
        ):
            nonlocal capture_seconds
            begin = time.perf_counter()
            error = star - x
            residual = raw - apply(x)
            image = apply(error)
            defect = ratio(
                norm(image - (residual - teacher_residual)),
                norm(image) + norm(residual) + norm(teacher_residual) + 2 * norm(raw),
            )
            if defect > 1e-10 or not np.isfinite(error).all():
                raise ValueError("True error/Schur residual relation failed")
            length = norm(error)
            row = {
                "iteration": iteration,
                "error_norm": length,
                "residual_norm": norm(residual),
                "S_error_relation_operation_relative": defect,
                "valid": length > 0.0,
                "omission_reason": None if length else "exact zero error",
            }
            snapshots.append(row)
            if length:
                arrays[f"error_{iteration:03d}"] = error.copy()
                arrays[f"x_{iteration:03d}"] = x.copy()
                arrays[f"residual_{iteration:03d}"] = residual.copy()
            capture_seconds += time.perf_counter() - begin

        observer = LowFrequencyAudit(
            runtime, apply, native, rhs, marker, record["index"]
        )
        backend = IterativeCoarseBackend(
            runtime.p4_system.matrix,
            action,
            local,
            runtime.operator_identity["csr_sha256"],
            cells,
            diagnostic_observer=observer,
            observer_stride=32,
            state_capture=capture,
            max_iterations=64,
        )
        before_pc = local.seconds
        backend.solve(
            rhs
        )  # local nonconvergence is valid sampling, never a coarse return
        valid = sum(s["valid"] for s in snapshots)
        path = artifact / f"training_{record['index']:03d}.npz"
        io_started = time.perf_counter()
        np.savez(path, **arrays)
        io_seconds = time.perf_counter() - io_started
        row = {
            **record,
            "normalized_RHS": True,
            "original_normalization_scale": scale,
            "reference_metrics": {k: reference[k] for k in METRICS},
            "reference_Schur_relative": ratio(norm(teacher_residual), norm(raw)),
            "snapshot_file": str(path),
            "snapshot_sha256": file_sha256(path),
            "snapshots": snapshots,
            "valid_count": valid,
            "family_weight": 1.0 / np.sqrt(valid) if valid else None,
            "phase_policy": "retain original normalized complex phase; each nonzero error / its 2-norm / sqrt(actual valid family snapshots)",
            "ksp_reason": backend.last_reason,
            "iterations": backend.history[-1]["iteration"],
            "reported_history": backend.history,
            "full_original_audits": observer.rows,
            "cost": {
                "problem_seconds_inclusive": time.perf_counter() - started,
                "teacher_recheck_seconds": reference_seconds,
                "capture_seconds_child": capture_seconds,
                "original_audit_seconds_child": observer.seconds,
                "local_PC_seconds_child": local.seconds - before_pc,
                "io_seconds": io_seconds,
                **backend.costs,
                "nested_timers_not_additive": True,
            },
        }
        rows.append(row)
        snapshot_count += valid
        write_json(
            directory / "training_snapshot_manifest.json",
            {
                "rows": rows,
                "snapshot_count": snapshot_count,
                "independent_families": len(rows),
                "dataset_manifest": str(data_path),
                "dataset_manifest_sha256": file_sha256(data_path),
                "teacher_source_sha": data["source_sha"],
            },
        )
        marker(
            "V4_train_trajectory_captured",
            {
                "train_index": record["index"],
                "valid_snapshots": valid,
                "iterations": row["iterations"],
            },
        )
    return {
        "status": "TRAINING_ERROR_SNAPSHOTS_COMPLETE",
        "rows": rows,
        "snapshot_count": snapshot_count,
        "independent_families": len(rows),
        "new_teacher_factor_created": False,
        "teacher_reused_only_original_train": True,
        "metadata_verification_seconds": metadata_verification_seconds,
    }


def p2(runtime, local, apply, native, profile, stage, directory, artifact):
    _, prior = completed("V4-P1")
    if prior["status"] != "TRAINING_ERROR_SNAPSHOTS_COMPLETE":
        raise ValueError("P2 prerequisite")
    started = time.perf_counter()
    space_seconds = 0.0
    snapshot_rank = None
    try:
        if stage == "V4-P2-ERROR":
            count = prior["snapshot_count"]
            if not count:
                raise ValueError("COARSE_SPACE_NUMERICAL_BLOCKED: no nonzero errors")
            matrix = np.empty(
                (runtime.action.reduced_size, count), dtype=np.complex128, order="F"
            )
            column = 0
            for row in prior["rows"]:
                if file_sha256(row["snapshot_file"]) != row["snapshot_sha256"]:
                    raise ValueError("Training snapshot identity changed")
                with np.load(row["snapshot_file"], allow_pickle=False) as packet:
                    for snapshot in row["snapshots"]:
                        if snapshot["valid"]:
                            matrix[:, column] = packet[
                                f"error_{snapshot['iteration']:03d}"
                            ] * (row["family_weight"] / snapshot["error_norm"])
                            column += 1
            z, spectrum = error_space(matrix)
            snapshot_rank = z.shape[1]
            del matrix
            np.savez(artifact / "error_basis.npz", z=z, singular_values=spectrum)
            provenance = {
                "P1_source_sha": prior["source_sha"],
                "independent_families": prior["independent_families"],
                "snapshot_count": count,
                "snapshot_effective_rank": snapshot_rank,
                "snapshot_singular_values": spectrum.tolist(),
                "error_basis_path": str(artifact / "error_basis.npz"),
                "error_basis_sha256": file_sha256(artifact / "error_basis.npz"),
            }
        else:
            _, errors = completed("V4-P2-ERROR")
            snapshot_rank = errors.get("snapshot_effective_rank") or 128
            proof = profile["oracle_qualification"]
            previous = ROOT / proof["directory"]
            manifest_path = Path(
                json.loads((previous / "numerical_summary.json").read_text())[
                    "oracle_manifest"
                ]
            )
            if file_sha256(manifest_path) != proof["manifest_sha256"]:
                raise ValueError("Old POD oracle manifest changed")
            oracle = json.loads(manifest_path.read_text())
            if file_sha256(oracle["basis_path"]) != oracle["basis_sha256"]:
                raise ValueError("Old Q checkpoint changed")
            with np.load(oracle["basis_path"], allow_pickle=False) as packet:
                z = np.asfortranarray(packet["q"][:, :snapshot_rank])
            provenance = {
                "old_basis_path": oracle["basis_path"],
                "old_basis_sha256": oracle["basis_sha256"],
                "old_oracle_source_sha": oracle["source_sha"],
                "old_training_pairs": 256,
                "old_native_U_R_loaded": False,
                "neural_weights_loaded": False,
                "target_rank_from_error_space": snapshot_rank,
                "target_rank_reason": "error snapshot effective rank; if no error directions, independent old-Q route uses original cap128",
            }
        space_seconds = time.perf_counter() - started
        encoding_started = time.perf_counter()
        z, u, r, encoding = build_schur_encoding(z, apply)
        encoding_seconds = time.perf_counter() - encoding_started
        pc = BalancedTwoLevelPC(local, apply, z, u, r)
        algebra_started = time.perf_counter()
        algebra = algebra_audit(pc, count=3)
        pair = action_pair(runtime, apply, native, (z[:, 0], 1j * z[:, -1]))
        algebra_seconds = time.perf_counter() - algebra_started
        result = {
            "candidate": "TWOLEVEL-ERROR-V4"
            if stage.endswith("ERROR")
            else "TWOLEVEL-OLDPOD-V4",
            "snapshot_effective_rank": snapshot_rank,
            "encoding": encoding,
            "algebra": algebra,
            "real_action_pair": pair,
            "effective_rank": z.shape[1],
            "representation_bytes": pc.representation_bytes,
            "R_factor_bytes": r.nbytes,
            "construction_seconds_inclusive": time.perf_counter() - started,
            "space_extraction_seconds": space_seconds,
            "Schur_encoding_seconds": encoding_seconds,
            "algebra_and_independent_audit_seconds": algebra_seconds,
            **provenance,
        }
        if not algebra["passed"] or not pair["passed"]:
            result.update(
                status="COARSE_SPACE_NUMERICAL_BLOCKED",
                blocked_reason="true-action two-level identity defect exceeds1e-10",
            )
        else:
            path = artifact / "basis.npz"
            io_started = time.perf_counter()
            np.savez(path, z=z, u=u, r=r)
            result.update(
                status="COARSE_SPACE_FROZEN_QUALIFIED",
                basis_path=str(path),
                basis_sha256=file_sha256(path),
                frozen_utc=datetime.now(timezone.utc).isoformat(),
                basis_io_seconds=time.perf_counter() - io_started,
            )
        write_json(directory / "coarse_space_algebra.json", result)
        return result
    except ValueError as error:
        if not str(error).startswith("COARSE_SPACE_NUMERICAL_BLOCKED"):
            raise
        result = {
            "status": "COARSE_SPACE_NUMERICAL_BLOCKED",
            "snapshot_effective_rank": snapshot_rank,
            "blocked_reason": str(error),
            "construction_seconds_inclusive": time.perf_counter() - started,
        }
        write_json(directory / "coarse_space_algebra.json", result)
        return result


def diagnostic_packets(design):
    old = ROOT / design["diagnostics"]["old_directory"]
    labels = json.loads((old / "coarse_results.json").read_text())
    for item in design["diagnostics"]["files"]:
        if file_sha256(ROOT / item["path"]) != item["sha256"]:
            raise ValueError("Consumed diagnostic RHS changed")
        with np.load(ROOT / item["path"], allow_pickle=False) as packet:
            rhs = CoarseRHS(packet["rhs_fe"], packet["rhs_port"])
        yield item["index"], labels[item["index"]]["label"], rhs


def validate_packets(
    runtime, pc, cells, apply, native, packets, directory, artifact, marker
):
    rows = []
    action = runtime.action
    for index, label, rhs in packets:
        history = LowFrequencyAudit(runtime, apply, native, rhs, marker, index)
        backend = IterativeCoarseBackend(
            runtime.p4_system.matrix,
            action,
            pc,
            runtime.operator_identity["csr_sha256"],
            cells,
            diagnostic_observer=history,
            observer_stride=32,
        )
        audit = OriginalEquationAudit(action, native)
        strict_audit_seconds = 0.0
        failure_io_seconds = 0.0

        def timed(callback):
            def run(state, load):
                nonlocal strict_audit_seconds
                started = time.perf_counter()
                try:
                    return callback(state, load)
                finally:
                    strict_audit_seconds += time.perf_counter() - started

            return run

        def failure(packet, *, index=index, rhs=rhs):
            nonlocal failure_io_seconds
            started = time.perf_counter()
            state = packet["state"]
            if state is not None:
                np.savez(
                    artifact / f"failure_{index:03d}.npz",
                    rhs_fe=rhs.fe,
                    rhs_port=rhs.port,
                    state_fe=state.fe,
                    state_port=state.port,
                )
            failure_io_seconds += time.perf_counter() - started

        verifier = StrictCoarseReturn(
            backend,
            witness_operator_sha256=runtime.operator_identity["csr_sha256"],
            original_a4=timed(audit.native),
            port_closure=timed(audit.port),
            recovery=timed(audit.recovery),
            slave_dofs=tuple(int(i) for i in runtime.levels["floquets"][4].mpc.slaves),
            failure_sink=failure,
        )
        before = pc.counters()
        started = time.perf_counter()
        passed = True
        try:
            verifier.solve(rhs)
        except CoarseReturnRejected:
            passed = False
        solve_seconds = time.perf_counter() - started
        final = history.rows[-1] if history.rows else None
        if final is not None and audit.last is not None:
            passed = passed and all(
                np.isfinite(audit.last[k]) and audit.last[k] <= 1e-10 for k in METRICS
            )
        after = pc.counters()
        counters = {
            k: after[k] - before[k]
            for k in before
            if isinstance(before[k], (int, float)) and not isinstance(before[k], bool)
        }
        if (counters["C_calls"], counters["B_calls"], counters["S_calls_in_B2"]) != (
            2 * counters["B2_calls"],
            counters["B2_calls"],
            counters["B2_calls"],
        ):
            raise ValueError("Two-level action counter contract failed")
        io_started = time.perf_counter()
        write_json(artifact / f"reported_history_{index:03d}.json", backend.history)
        write_json(artifact / f"full_audits_{index:03d}.json", history.rows)
        if audit.last is not None and backend.history:
            d = audit.last
            original_norms = {
                "native_absolute": norm(d["native_residual"]),
                "native_scale": d["native_rhs_operation_scale"],
                "port_absolute": norm(d["augmented_port_residual"]),
                "port_scale": d["port_operation_scale"],
                "internal_absolute": norm(d["internal_residual"]),
                "internal_scale": d["internal_operation_scale"],
                "native_identity_absolute": norm(d["native_identity_difference"]),
                "native_identity_scale": d["native_identity_operation_scale"],
                "Schur_port_identity_absolute": norm(
                    d["schur_port_identity_difference"]
                ),
                "Schur_port_identity_scale": d["schur_port_identity_operation_scale"],
                "submitted_recovery_absolute": norm(d["submitted_recovery_difference"]),
                "submitted_field_norm": norm(audit.cached_state.fe),
                "finite": bool(
                    np.isfinite(audit.cached_state.fe).all()
                    and np.isfinite(audit.cached_state.port).all()
                ),
                "maximum_slave_storage": float(
                    np.max(
                        np.abs(
                            audit.cached_state.fe[
                                runtime.levels["floquets"][4].mpc.slaves
                            ]
                        ),
                        initial=0,
                    )
                ),
            }
        else:
            original_norms = {
                key: 0.0
                for key in (
                    "native_absolute",
                    "native_scale",
                    "port_absolute",
                    "port_scale",
                    "internal_absolute",
                    "internal_scale",
                    "native_identity_absolute",
                    "native_identity_scale",
                    "Schur_port_identity_absolute",
                    "Schur_port_identity_scale",
                    "submitted_recovery_absolute",
                    "submitted_field_norm",
                    "maximum_slave_storage",
                )
            }
            original_norms["finite"] = True
        if passed != strict_from_norms(original_norms):
            raise ValueError("Independent norm gate disagrees with strict return")
        row = {
            "index": index,
            "label": label,
            "passed": passed,
            "strict_return": verifier.last_audit,
            "final": final,
            "final_original_norms": original_norms,
            "iterations": backend.history[-1]["iteration"] if backend.history else 0,
            "ksp_reason": backend.last_reason if backend.history else None,
            "initial_reduced_guess": "exact zero",
            "teacher_solution_accessed": False,
            "cost": {
                "solve_and_strict_return_seconds_inclusive": solve_seconds,
                "original_boundary_audit_seconds_child": history.seconds,
                "strict_return_audit_seconds": strict_audit_seconds,
                "failure_io_seconds_child": failure_io_seconds,
                "history_io_seconds": time.perf_counter() - io_started,
                "two_level": counters,
                "backend": backend.costs,
                "nested_timers_not_additive": True,
            },
            "reported_history_path": str(
                artifact / f"reported_history_{index:03d}.json"
            ),
            "reported_history_sha256": file_sha256(
                artifact / f"reported_history_{index:03d}.json"
            ),
            "full_audits_path": str(artifact / f"full_audits_{index:03d}.json"),
            "full_audits_sha256": file_sha256(
                artifact / f"full_audits_{index:03d}.json"
            ),
        }
        rows.append(row)
        write_json(directory / "coarse_results.json", rows)
        marker(
            "V4_strict_rhs_complete",
            {
                "index": index,
                "passed": passed,
                "iterations": row["iterations"],
                "native": final["native"]["native_residual_relative"] if final else 0.0,
            },
        )
    return rows


def p3(
    runtime, local, cells, apply, native, design, stage, directory, artifact, marker
):
    route = "ERROR" if stage.endswith("ERROR") else "OLDPOD"
    # BOTH spaces must be frozen/audited before any diagnostic selection.
    completed("V4-P2-ERROR")
    completed("V4-P2-OLDPOD")
    _, space = completed("V4-P2-" + route)
    if space["status"] != "COARSE_SPACE_FROZEN_QUALIFIED":
        return {
            "status": "COARSE_SPACE_NUMERICAL_BLOCKED",
            "route": route,
            "reason": space.get("blocked_reason"),
            "rows": [],
        }
    if file_sha256(space["basis_path"]) != space["basis_sha256"]:
        raise ValueError("Frozen Schur space changed")
    with np.load(space["basis_path"], allow_pickle=False) as packet:
        z, u, r = (np.asfortranarray(packet[key]) for key in ("z", "u", "r"))
    pc = BalancedTwoLevelPC(local, apply, z, u, r)
    rows = validate_packets(
        runtime,
        pc,
        cells,
        apply,
        native,
        diagnostic_packets(design),
        directory,
        artifact,
        marker,
    )
    return {
        "status": diagnostic_status(rows),
        "candidate": space["candidate"],
        "effective_rank": pc.rank,
        "basis_path": space["basis_path"],
        "basis_sha256": space["basis_sha256"],
        "P2_source_sha": space["source_sha"],
        "rows": rows,
        "fresh_test_consumed": False,
        "representation_bytes": pc.representation_bytes,
        "R_factor_bytes": r.nbytes,
    }


def fresh_packets(runtime):
    """Generate only after an immutable P3-based selection; no teacher reads."""
    from src.solvers.learned_coarse_inverse import manufacture

    action = runtime.action
    native = native_numpy_apply(runtime.p4)
    rng = np.random.default_rng(420620)
    interiors = np.concatenate([c.original_interiors for c in action._cells])
    slaves = runtime.levels["floquets"][4].mpc.slaves

    def random_vector(size):
        x = np.asarray(
            rng.standard_normal(size) + 1j * rng.standard_normal(size),
            dtype=np.complex128,
        )
        return x / norm(x)

    zero_fe = np.zeros(action.condensed.full_rows, dtype=np.complex128)
    zero_port = np.zeros(action.condensed.appended_rows, dtype=np.complex128)
    yield 0, {"whole_problem": "zero", "variant": "1"}, CoarseRHS(zero_fe, zero_port)
    internal = zero_fe.copy()
    internal[interiors] = random_vector(len(interiors))
    mixed = random_vector(len(zero_fe))
    mixed[slaves] = 0.0
    mixed /= norm(mixed)
    families = [
        ("seed420620_internal", internal, zero_port),
        ("seed420620_port", zero_fe, random_vector(len(zero_port))),
        ("seed420620_mixed", mixed, random_vector(len(zero_port))),
    ]
    for j in range(2):
        x = random_vector(action.reduced_size)
        gi = zero_fe.copy()
        gi[interiors] = random_vector(len(interiors)) * 0.01
        field = action.recover_storage(x, full_rhs=gi)
        g, p = manufacture(action, native, field, x[action.condensed.active_rows :])
        families.append((f"seed420620_manufactured{j}", g, p))
    index = 1
    for name, g, p in families:
        for variant, scale in (("1", 1), ("phase_i", 1j), ("amplitude_1e3", 1e3)):
            yield (
                index,
                {"whole_problem": name, "variant": variant, "seed": 420620},
                CoarseRHS(scale * g, scale * p),
            )
            index += 1


def p4(runtime, local, cells, apply, native, design, directory, artifact, marker):
    selection = ROOT / "tmp/task042/v4/selection.json"
    chosen = json.loads(selection.read_text())
    reports = {route: completed("V4-P3-" + route)[1] for route in ("OLDPOD", "ERROR")}
    if select_route(reports) != chosen["route"]:
        raise ValueError("Frozen candidate does not meet independent P3 selection gate")
    # Selection is frozen to diagnostic hashes before test generation.
    for stage in ("V4-P3-OLDPOD", "V4-P3-ERROR"):
        path, _ = completed(stage)
        if (
            file_sha256(path / "numerical_summary.json")
            != chosen["diagnostic_sha256"][stage]
        ):
            raise ValueError("Frozen selection diagnostic changed")
    _, space = completed(chosen["space_stage"])
    if (
        space["basis_sha256"] != chosen["basis_sha256"]
        or file_sha256(space["basis_path"]) != chosen["basis_sha256"]
    ):
        raise ValueError("Frozen selected checkpoint changed")
    consumption = ROOT / "tmp/task042/v4/fresh_consumption.json"
    with consumption.open("x") as stream:
        json.dump(
            {
                "utc": datetime.now(timezone.utc).isoformat(),
                "selection_sha256": file_sha256(selection),
                "basis_sha256": chosen["basis_sha256"],
                "seed": 420620,
                "consumed": True,
            },
            stream,
        )
    write_json(directory / "frozen_selection.json", chosen)
    with np.load(space["basis_path"], allow_pickle=False) as packet:
        z, u, r = (np.asfortranarray(packet[key]) for key in ("z", "u", "r"))
    pc = BalancedTwoLevelPC(local, apply, z, u, r)
    rows = validate_packets(
        runtime,
        pc,
        cells,
        apply,
        native,
        fresh_packets(runtime),
        directory,
        artifact,
        marker,
    )
    if len(rows) != 16:
        raise ValueError("Fresh test inventory differs")
    return {
        "status": "FIXED_OPERATOR_P4_QUALIFIED"
        if all(row["passed"] for row in rows)
        else "COARSE_INVERSE_NOT_QUALIFIED",
        "candidate": space["candidate"],
        "effective_rank": pc.rank,
        "basis_sha256": space["basis_sha256"],
        "rows": rows,
        "fresh_consumed": 16,
        "independent_nonzero_families": 5,
        "F5": False,
    }


def run_two_level_stage(cfg, comm, stage, directory, artifact, source, marker):
    design = json.loads(CONFIG.read_text())
    if file_sha256(ROOT / design["review_path"]) != design["review_sha256"]:
        raise ValueError("Formal V4 review changed")
    if INDEX.exists() and stage in json.loads(INDEX.read_text()):
        raise ValueError("V4 stage already completed; no numerical retry")
    profile = json.loads(
        (
            ROOT / "input/task042_neural_coarse_inverse/shared_profile_v1.json"
        ).read_text()
    )
    write_json(directory / "v4_design.json", design)
    write_json(
        directory / "v4_prerequisites.json",
        json.loads(INDEX.read_text()) if INDEX.exists() else {},
    )
    runtime, _f1, identity = build_original(cfg, comm, profile, marker)
    local = apply = None
    try:
        write_json(
            directory / "qualified_original_operator.json",
            {
                "identity": identity,
                "matrix": runtime.operator_identity,
                "full_p6_constructed": False,
            },
        )
        local, cells, cell_bytes = local_pc(runtime, directory, design, marker)
        apply = BorrowedMatrixAction(runtime.p4_system.matrix)
        native = native_numpy_apply(runtime.p4)
        write_json(
            directory / "candidate_construction.json",
            {
                "global_p4_factor_created": False,
                "private_audit_csr": False,
                "original_matrix_borrowed": True,
                "local_PC": "R-GEO-CELL80-v3",
                "patch_factor_bytes": local.factor_bytes,
                "cell_port_factor_bytes": cell_bytes,
                "local_setup_seconds": local.setup_seconds,
                "factor_rows": [len(p) for p in local.patches],
                "space_capacity": space_budget(
                    runtime.action.reduced_size,
                    128,
                    local.representation_bytes,
                    local.factor_bytes + cell_bytes,
                ),
            },
        )
        if stage == "V4-P0":
            result = p0(runtime, local, apply, native, directory, artifact)
        elif stage == "V4-P1":
            result = p1(
                runtime,
                local,
                cells,
                apply,
                native,
                profile,
                design,
                directory,
                artifact,
                marker,
            )
        elif stage in ("V4-P2-ERROR", "V4-P2-OLDPOD"):
            result = p2(
                runtime, local, apply, native, profile, stage, directory, artifact
            )
        elif stage in ("V4-P3-ERROR", "V4-P3-OLDPOD"):
            result = p3(
                runtime,
                local,
                cells,
                apply,
                native,
                design,
                stage,
                directory,
                artifact,
                marker,
            )
        elif stage == "V4-P4":
            result = p4(
                runtime,
                local,
                cells,
                apply,
                native,
                design,
                directory,
                artifact,
                marker,
            )
        else:
            raise ValueError("Unknown bounded V4 stage")
        result.update(
            global_p4_factor_created=False,
            private_audit_csr=False,
            original_operator_sha256=runtime.operator_identity["csr_sha256"],
            local_factor_bytes=local.factor_bytes + cell_bytes,
            local_setup_seconds=local.setup_seconds,
            exact_S_action_calls=apply.calls,
            exact_S_action_seconds_inclusive=apply.seconds,
            F5=False,
            GPU=False,
        )
        return result
    finally:
        started = time.perf_counter()
        if local is not None:
            local.factors.clear()
        if apply is not None:
            apply.destroy()
        runtime.destroy()
        marker(
            "V4_original_PC_and_operator_released",
            {"release_seconds": time.perf_counter() - started},
        )
