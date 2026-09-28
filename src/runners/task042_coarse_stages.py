"""Task042 sequential offline teacher and bounded representation stages."""

import json
import time
from pathlib import Path

import numpy as np
from scipy.linalg import solve_triangular

from src.runners.task042_shared import ARTIFACTS, ROOT, write_json
from src.solvers.coarse_inverse_protocol import CoarseRHS
from src.solvers.learned_coarse_data import (
    BorrowedMatrixAction,
    file_sha256,
    mapped_original_residual,
    offline_reference_factor,
    save_teacher_batches,
)
from src.solvers.learned_coarse_inverse import (
    BoundedBlockPC,
    cell_declarations,
    native_numpy_apply,
    reference_solve,
)
from src.solvers.learned_coarse_packets import frozen_split_packets
from src.solvers.learned_coarse_runtime import OriginalP4Runtime
from src.solvers.learned_reduced_correction import (
    complex_linear_real_matrix,
    oracle_feature_batch,
    streaming_snapshot_pod,
)


def prerequisite(profile):
    proof = profile["f1_qualification"]
    directory = ROOT / proof["directory"]
    for name, sha in proof["files_sha256"].items():
        if file_sha256(directory / name) != sha:
            raise ValueError("Qualified F1 provenance changed: " + name)
    checks = json.loads((directory / "component_checks.json").read_text())
    if checks["status"] != "PASS" or any(
        c.get("relative", 0.0) > c.get("limit", 1.0) or c.get("count", 1) <= 0
        for c in checks["checks"]
    ):
        raise ValueError("Real F1 interface prerequisite not qualified")
    manifest = json.loads((directory / "run_manifest.json").read_text())
    summary = json.loads((directory / "run_summary.json").read_text())
    if (
        manifest["source_sha"] != proof["source_sha"]
        or manifest["git_status"] != ""
        or not summary["descendants_cleared"]
        or summary["leader_exit_code"] != 0
    ):
        raise ValueError("F1 source/cleanup prerequisite differs")
    for name, sha in proof["artifacts_sha256"].items():
        if file_sha256(ARTIFACTS / directory.name / name) != sha:
            raise ValueError("Frozen F1 RHS/trajectory changed: " + name)
    identity = json.loads((directory / "operator_identity.json").read_text())
    return directory, identity


def build_original(cfg, comm, profile, marker):
    from benchmarks.run_task038_full3d_t5 import _mesh_identity
    from src.runners.task042_experiment import digest, mpc_identity

    f1, identity = prerequisite(profile)
    runtime = OriginalP4Runtime.build(
        cfg,
        comm,
        quadrature=identity["quadrature"],
        expected_sha=profile["f1_qualification"]["operator_sha256"],
        marker=marker,
    )
    try:
        actual = {
            "mesh": _mesh_identity(runtime.levels["mesh"]),
            "material_tags": {
                "indices_sha256": digest(runtime.levels["mesh_data"].cell_tags.indices),
                "values_sha256": digest(runtime.levels["mesh_data"].cell_tags.values),
            },
            "mode_sha256": runtime.p4["mode_sha256"],
            "mpc": mpc_identity(runtime.levels["floquets"][4].mpc),
            "full_rows": runtime.p4_system.full_rows,
            "reduced_rows": runtime.action.reduced_size,
            "ports": runtime.p4_system.appended_rows,
        }
        expected = {
            "mesh": identity["mesh"],
            "material_tags": identity["material_tags"],
            "mode_sha256": identity["mode_sha256"],
            "mpc": identity["mpc"]["4"],
            "full_rows": identity["p4_full_rows"],
            "reduced_rows": identity["p4_reduced_rows"],
            "ports": identity["ports"],
        }
        if actual != expected:
            raise ValueError(
                "P4-only original geometry/MPC/mode identity differs from F1"
            )
        marker("qualified_F1_original_A4_reused", actual)
        return runtime, f1, identity
    except BaseException:
        runtime.destroy()
        raise


def teacher(runtime, f1, directory, artifact, source, profile, marker):
    matrix, action = runtime.p4_system.matrix, runtime.action
    native = native_numpy_apply(runtime.p4)
    factor = offline_reference_factor(matrix, directory, marker)
    f1_artifacts = ARTIFACTS / f1.name
    dataset = {
        "schema": "task042.teacher.v1",
        "source_sha": source,
        "f1_qualification": profile["f1_qualification"],
        "operator_sha256": runtime.operator_identity["csr_sha256"],
        "normalization": "divide raw reduced RHS, solution and full/port RHS by ||raw||; zero scale=1",
        "precision": "complex128",
        "batch_max": 32,
        "splits": {},
        "teacher_global_p4_factor": True,
        "candidate_constructed": False,
        "split_policy": profile["teacher_design"],
        "shared_workstation": True,
    }
    try:
        reference = []
        for index in range(8):
            started = time.perf_counter()
            with np.load(
                f1_artifacts / f"rhs_{index:03d}.npz", allow_pickle=False
            ) as p:
                rhs = CoarseRHS(p["rhs_fe"], p["rhs_port"])
            x, refinements = reference_solve(matrix, action, rhs, factor)
            d = action.evaluate_native_residual(x, rhs.fe, native, port_rhs=rhs.port)
            metrics = {
                k: d[k]
                for k in (
                    "native_residual_relative",
                    "port_residual_relative",
                    "internal_residual_relative",
                    "native_identity_relative",
                    "schur_port_identity_relative",
                )
            }
            passed = all(np.isfinite(v) and v <= 1.0e-10 for v in metrics.values())
            reference.append(
                {
                    "index": index,
                    "metrics": metrics,
                    "refinements": refinements,
                    "passed": passed,
                    "seconds": time.perf_counter() - started,
                }
            )
            write_json(directory / "reference_results.json", reference)
            if not passed:
                raise ValueError("F1_REFERENCE_NOT_QUALIFIED")
        dataset["reference_inventory_passed"] = len(reference)
        for split, count in (("train", 256), ("validation", 64), ("heldout", 64)):
            started = time.perf_counter()
            records, files = save_teacher_batches(
                matrix,
                action,
                native,
                factor,
                frozen_split_packets(
                    action, native, split=split, f1_artifacts=f1_artifacts
                ),
                count,
                artifact / split,
            )
            if len(records) != count:
                raise RuntimeError("Teacher split inventory size differs")
            dataset["splits"][split] = {
                "count": count,
                "files": files,
                "residuals_path": str(artifact / split / "teacher_residuals.json"),
                "residuals_sha256": file_sha256(
                    artifact / split / "teacher_residuals.json"
                ),
                "seconds": time.perf_counter() - started,
                "worst_metrics": {
                    k: max(r["metrics"][k] for r in records)
                    for k in records[0]["metrics"]
                },
            }
            write_json(artifact / "dataset_manifest.json", dataset)
            marker(
                "teacher_split_complete",
                {
                    "split": split,
                    "count": count,
                    "worst_metrics": dataset["splits"][split]["worst_metrics"],
                },
            )
        dataset.update(
            status="TEACHER_QUALIFIED",
            factor_release="finally then worker exit before any candidate",
        )
        write_json(artifact / "dataset_manifest.json", dataset)
        return {
            "status": "TEACHER_QUALIFIED",
            "dataset_manifest": str(artifact / "dataset_manifest.json"),
            "dataset_manifest_sha256": file_sha256(artifact / "dataset_manifest.json"),
            "teacher_pairs": 384,
            "global_p4_factor_created": True,
            "candidate_constructed": False,
        }
    finally:
        factor.destroy()
        marker("offline_teacher_factor_destroyed", {})


def read_dataset(profile):
    proof = profile["teacher_qualification"]
    directory = ROOT / proof["directory"]
    summary = json.loads((directory / "run_summary.json").read_text())
    numerical = json.loads((directory / "numerical_summary.json").read_text())
    if (
        not summary["descendants_cleared"]
        or summary["leader_exit_code"] != 0
        or numerical["status"] != "TEACHER_QUALIFIED"
    ):
        raise ValueError("Teacher not released or numerically qualified")
    path = Path(numerical["dataset_manifest"])
    if file_sha256(path) != proof["manifest_sha256"]:
        raise ValueError("Teacher manifest changed")
    data = json.loads(path.read_text())
    if data["operator_sha256"] != profile["f1_qualification"]["operator_sha256"]:
        raise ValueError("Teacher operator mismatch")
    for split in data["splits"].values():
        if file_sha256(split["residuals_path"]) != split["residuals_sha256"]:
            raise ValueError("Teacher audits changed")
        for packet in split["files"]:
            if file_sha256(packet["path"]) != packet["sha256"]:
                raise ValueError("Teacher packets changed")
    return data, path


def oracle(runtime, directory, artifact, source, profile, marker):
    from src.runners.task042_experiment import scalar_audit

    dataset, dataset_path = read_dataset(profile)
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
        width=512,
    )
    try:
        errors = []
        from src.solvers.coarse_inverse_protocol import CoarseState
        from src.solvers.learned_coarse_inverse import OriginalEquationAudit

        f1_artifacts = ARTIFACTS / Path(profile["f1_qualification"]["directory"]).name
        failure_audits = []
        for path in sorted(f1_artifacts.glob("failure_*.npz")):
            with np.load(path, allow_pickle=False) as p:
                rhs = CoarseRHS(p["rhs_fe"], p["rhs_port"])
                state = CoarseState(p["state_fe"], p["state_port"])
            independent = OriginalEquationAudit(action, native)
            d = independent.evaluate(state, rhs)
            failure_audits.append(
                {
                    "packet": path.name,
                    "packet_sha256": file_sha256(path),
                    "metrics": scalar_audit(d),
                    "submitted_recovery_relative": independent.recovery(
                        state, rhs
                    ).relative(),
                }
            )
        write_json(directory / "f1_failure_full_audits.json", failure_audits)
        for index, packet in enumerate(dataset["splits"]["train"]["files"]):
            with np.load(packet["path"], allow_pickle=False) as p:
                error = np.stack(
                    [
                        x - b0.apply_array(r)
                        for r, x in zip(p["raw"], p["solution"], strict=True)
                    ]
                )
            path = artifact / f"errors_{index:03d}.npz"
            np.savez(path, error=error)
            errors.append(path)
        q, spectrum = streaming_snapshot_pod(errors, rank=128)
        images = np.stack(
            [mapped_original_residual(action, apply(q[:, j])) for j in range(128)],
            axis=1,
        )
        # Verify the map with independently applied original native A4, not
        # just with projected or assembled Schur equations.
        checks = []
        for packet in dataset["splits"]["validation"]["files"][:1]:
            with np.load(packet["path"], allow_pickle=False) as p:
                for j in range(3):
                    r = p["raw"][j]
                    z = b0.apply_array(r)
                    d = action.evaluate_native_residual(
                        z, p["rhs_fe"][j], native, port_rhs=p["rhs_port"][j]
                    )
                    actual = mapped_original_residual(action, r - apply(z))
                    ratio = float(
                        np.linalg.norm(actual - d["native_residual"])
                        / max(np.linalg.norm(actual), np.finfo(float).tiny)
                    )
                    checks.append(
                        {
                            "index": j,
                            "relative": ratio,
                            "limit": 1.0e-10,
                            "native": scalar_audit(d),
                        }
                    )
        for j in (0, 15, 127):
            d = action.evaluate_native_residual(
                q[:, j],
                np.zeros(action.condensed.full_rows, dtype=np.complex128),
                native,
            )
            ratio = float(
                np.linalg.norm(images[:, j] + d["native_residual"])
                / max(np.linalg.norm(images[:, j]), np.finfo(float).tiny)
            )
            checks.append({"basis_column": j, "relative": ratio, "limit": 1.0e-10})
        write_json(directory / "native_residual_map_checks.json", checks)
        if any(c["relative"] > 1.0e-10 for c in checks):
            raise ValueError("F2_NATIVE_RESIDUAL_MAP_NOT_QUALIFIED")
        diagnostics = []
        features128 = {}
        u128 = r128 = None
        for rank in (16, 32, 64, 128):
            started = time.perf_counter()
            qr = q[:, :rank]
            mr = images[:, :rank]
            u, r = np.linalg.qr(mr, mode="reduced")
            payload = (
                qr.nbytes
                + u.nbytes
                + r.nbytes
                + (6 * len(q) + 4 * len(u) + 10 * rank) * 16
            )
            if payload > 512 * 2**20:
                raise ValueError("representation budget exceeded")
            split_rows = {}
            for split in ("train", "validation"):
                measures = []
                collected = []
                for packet in dataset["splits"][split]["files"]:
                    with np.load(packet["path"], allow_pickle=False) as p:
                        rows, feature = oracle_feature_batch(
                            p["raw"],
                            p["solution"],
                            p["native_rhs_scale"],
                            b0,
                            qr,
                            mr,
                            u,
                            r,
                            apply,
                            lambda v: mapped_original_residual(action, v),
                        )
                    measures.extend(rows)
                    collected.append(feature)
                split_rows[split] = {
                    key: float(np.median([row[key] for row in measures]))
                    for key in measures[0]
                }
                if rank == 128:
                    features128.update(
                        {
                            split + "_" + key: np.concatenate(
                                [f[key] for f in collected]
                            )
                            for key in collected[0]
                        }
                    )
            positive = (
                split_rows["validation"]["error_projection_ratio"]
                <= profile["oracle_positive"]["median_error_ratio_max"]
                and split_rows["validation"]["best_native_residual_ratio"]
                <= profile["oracle_positive"]["median_native_ratio_max"]
            )
            diagnostics.append(
                {
                    "rank": rank,
                    "metrics": split_rows,
                    "positive": positive,
                    "representation_bytes": payload,
                    "seconds": time.perf_counter() - started,
                }
            )
            write_json(directory / "oracle_results.json", diagnostics)
            marker("oracle_rank_complete", diagnostics[-1])
            if rank == 128:
                u128, r128 = u, r
        positive = diagnostics[-1]["positive"]
        result = {
            "status": "REPRESENTATION_POSITIVE"
            if positive
            else "REPRESENTATION_NEGATIVE",
            "source_sha": source,
            "registered_deployment_rank": 128,
            "criteria": profile["oracle_positive"],
            "diagnostics": diagnostics,
            "dataset_manifest": str(dataset_path),
            "dataset_manifest_sha256": file_sha256(dataset_path),
            "teacher_source_sha": dataset["source_sha"],
            "heldout_used_for_selection": False,
            "global_p4_factor_created": False,
            "private_audit_csr": False,
            "patch_factor_bytes": b0.factor_bytes,
            "cell_port_factor_bytes": sum(d.payload_bytes for d in declarations),
            "native_image_map": "W*S4*Q, independently native A4 checked",
            "snapshot_eigenvalues": spectrum.tolist(),
            "shared_workstation": True,
        }
        if positive:
            basis = artifact / "basis.npz"
            np.savez(basis, q=q, u=u128, r=r128)
            features128["native_gram"] = images.conj().T @ images
            features128["initial_skip_weight"] = complex_linear_real_matrix(
                solve_triangular(r128, np.eye(128, dtype=np.complex128))
            )
            features = artifact / "training_features.npz"
            np.savez(features, **features128)
            result.update(
                basis_path=str(basis),
                basis_sha256=file_sha256(basis),
                features_path=str(features),
                features_sha256=file_sha256(features),
            )
        write_json(artifact / "oracle_manifest.json", result)
        return {
            "status": result["status"],
            "global_p4_factor_created": False,
            "oracle_manifest": str(artifact / "oracle_manifest.json"),
            "oracle_manifest_sha256": file_sha256(artifact / "oracle_manifest.json"),
            "diagnostics": diagnostics,
        }
    finally:
        b0.factors.clear()
        apply.destroy()


def run_coarse_stage(cfg, comm, stage, directory, artifact, source, marker):
    profile = json.loads(
        (
            ROOT / "input/task042_neural_coarse_inverse/shared_profile_v1.json"
        ).read_text()
    )
    runtime, f1, identity = build_original(cfg, comm, profile, marker)
    try:
        write_json(
            directory / "qualified_original_operator.json",
            {
                "identity": identity,
                "matrix": runtime.operator_identity,
                "full_p6_constructed": False,
                "prerequisite_f1_source": profile["f1_qualification"]["source_sha"],
            },
        )
        if stage == "F2-teacher":
            return teacher(runtime, f1, directory, artifact, source, profile, marker)
        if stage == "F2-oracle":
            return oracle(runtime, directory, artifact, source, profile, marker)
        if stage in ("F4-B0", "F4-LIN", "F4-NN"):
            return candidate_validation(
                runtime, directory, artifact, source, profile, stage, marker
            )
        raise ValueError("Unimplemented later coarse stage")
    finally:
        runtime.destroy()
        marker("original_p4_stack_destroyed", {})


def frozen_oracle(profile):
    proof = profile["oracle_qualification"]
    directory = ROOT / proof["directory"]
    numerical = json.loads((directory / "numerical_summary.json").read_text())
    supervision = json.loads((directory / "run_summary.json").read_text())
    if (
        numerical["status"] != "REPRESENTATION_POSITIVE"
        or not supervision["descendants_cleared"]
        or supervision["leader_exit_code"] != 0
    ):
        raise ValueError("Oracle not qualified or released")
    path = Path(numerical["oracle_manifest"])
    if file_sha256(path) != proof["manifest_sha256"]:
        raise ValueError("Oracle manifest changed")
    result = json.loads(path.read_text())
    for key in ("basis", "features"):
        if file_sha256(result[key + "_path"]) != result[key + "_sha256"]:
            raise ValueError("Oracle " + key + " changed")
    return result


def candidate_validation(runtime, directory, artifact, source, profile, stage, marker):
    from src.runners.task042_experiment import scalar_audit
    from src.solvers.coarse_inverse_protocol import (
        CoarseReturnRejected,
        StrictCoarseReturn,
    )
    from src.solvers.learned_coarse_inverse import (
        IterativeCoarseBackend,
        OriginalEquationAudit,
    )
    from src.solvers.learned_reduced_correction import ReducedCorrectionPC

    dataset, dataset_path = read_dataset(profile)
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
        width=512,
    )
    pc = b0
    weights = None
    metadata = {}
    rows = []
    try:
        if stage != "F4-B0":
            oracle = frozen_oracle(profile)
            with np.load(oracle["basis_path"], allow_pickle=False) as packet:
                q, u, r = (packet[name] for name in ("q", "u", "r"))
            if stage == "F4-NN":
                proof = profile["model_qualification"]
                previous = ROOT / proof["directory"]
                run = json.loads((previous / "run_summary.json").read_text())
                model = json.loads((previous / "numerical_summary.json").read_text())
                if (
                    not run["descendants_cleared"]
                    or run["leader_exit_code"] != 0
                    or model["status"] != "TRAINING_COMPLETED"
                ):
                    raise ValueError("NN training not completed or released")
                if file_sha256(model["model_path"]) != proof["frozen_model_sha256"]:
                    raise ValueError("Frozen model changed")
                with np.load(model["model_path"], allow_pickle=False) as packet:
                    weights = {name: packet[name] for name in packet.files}
                from src.solvers.learned_reduced_correction import numpy_mlp

                if (
                    file_sha256(model["inference_probe_path"])
                    != model["inference_probe_sha256"]
                ):
                    raise ValueError("Frozen Torch inference probe changed")
                with np.load(
                    model["inference_probe_path"], allow_pickle=False
                ) as probe:
                    predicted = numpy_mlp(probe["input"], weights)
                    delta = float(
                        np.linalg.norm(predicted - probe["output"])
                        / max(np.linalg.norm(probe["output"]), np.finfo(float).tiny)
                    )
                if delta > 1.0e-12:
                    raise ValueError(
                        "FE NumPy inference differs from frozen Torch FP64"
                    )
                metadata["fe_numpy_torch_relative_difference"] = delta
                metadata.update(
                    training_source_sha=model["source_sha"],
                    model_sha256=proof["frozen_model_sha256"],
                    selected_epoch=model["selected_epoch"],
                )
            pc = ReducedCorrectionPC(
                b0,
                q,
                u,
                r,
                apply,
                lambda v: mapped_original_residual(action, v),
                weights=weights,
            )
            del u
            metadata.update(
                basis_sha256=oracle["basis_sha256"],
                oracle_source_sha=oracle["source_sha"],
                rank=q.shape[1],
            )
        backend = IterativeCoarseBackend(
            matrix, action, pc, runtime.operator_identity["csr_sha256"], declarations
        )
        audit = OriginalEquationAudit(action, native)
        write_json(
            directory / "candidate_construction.json",
            dict(
                global_p4_factor_created=False,
                private_audit_csr=False,
                original_matrix_borrowed=True,
                patch_factor_bytes=b0.factor_bytes,
                cell_port_factor_bytes=sum(d.payload_bytes for d in declarations),
                factors=[
                    {"scope": d.scope, "rows": d.rows, "payload_bytes": d.payload_bytes}
                    for d in backend.plan.factors
                ],
                representation_bytes=backend.plan.representation_bytes,
                **metadata,
            ),
        )

        def failure(packet):
            s = packet["state"]
            r = packet["rhs"]
            np.savez(
                artifact / f"failure_{len(rows):03d}.npz",
                rhs_fe=r.fe,
                rhs_port=r.port,
                state_fe=np.zeros_like(r.fe) if s is None else s.fe,
                state_port=np.zeros_like(r.port) if s is None else s.port,
            )

        verifier = StrictCoarseReturn(
            backend,
            witness_operator_sha256=runtime.operator_identity["csr_sha256"],
            original_a4=audit.native,
            port_closure=audit.port,
            recovery=audit.recovery,
            slave_dofs=tuple(int(i) for i in runtime.levels["floquets"][4].mpc.slaves),
            failure_sink=failure,
        )
        count = 0
        labels = json.loads(
            Path(dataset["splits"]["heldout"]["residuals_path"]).read_text()
        )
        for packet in dataset["splits"]["heldout"]["files"]:
            with np.load(packet["path"], allow_pickle=False) as data:
                # Never access held-out teacher solutions, initial guesses or coefficients.
                fe = data["rhs_fe"]
                ports = data["rhs_port"]
                scales = data["normalization_scale"]
            for g, p, scale in zip(fe, ports, scales, strict=True):
                if count == 16:
                    break
                rhs = CoarseRHS(g * scale, p * scale)
                before_pc = pc.seconds
                before_apply = apply.seconds
                started = time.perf_counter()
                passed = True
                try:
                    verifier.solve(rhs)
                except CoarseReturnRejected:
                    passed = False
                d = dict(verifier.last_audit)
                d.update(
                    index=count,
                    label=labels[count]["label"],
                    passed=passed,
                    seconds=time.perf_counter() - started,
                    pc_seconds=pc.seconds - before_pc,
                    additional_A4_apply_seconds=apply.seconds - before_apply,
                    ksp_reason=backend.last_reason if d["backend_called"] else None,
                    # Exact-zero returns bypass the audit callbacks; do not
                    # attach the preceding nonzero RHS's cached measurements.
                    native_audit=scalar_audit(audit.last)
                    if d["backend_called"] and audit.last
                    else None,
                )
                rows.append(d)
                if d["backend_called"]:
                    np.savez(
                        artifact / f"trajectory_{count:03d}.npz",
                        **{f"r_{i:03d}": v for i, v in backend.trajectory},
                    )
                    write_json(artifact / f"history_{count:03d}.json", backend.history)
                count += 1
                write_json(directory / "coarse_results.json", rows)
                marker(
                    "strict_heldout_rhs_complete",
                    {k: v for k, v in d.items() if k != "native_audit"},
                )
            if count == 16:
                break
        if count != 16:
            raise ValueError("Insufficient unseen RHS inventory")
        status = (
            "F4_QUALIFIED"
            if all(r["passed"] for r in rows)
            else "COARSE_INVERSE_NOT_QUALIFIED"
        )
        return dict(
            status=status,
            rows=rows,
            heldout_consumed=16,
            global_p4_factor_created=False,
            candidate=stage,
            private_audit_csr=False,
            dataset_manifest_sha256=file_sha256(dataset_path),
            operator_sha256=runtime.operator_identity["csr_sha256"],
            **metadata,
        )
    finally:
        b0.factors.clear()
        apply.destroy()
