"""Review V2 fixed-object stages; no training, factor oracle or KSP campaign."""

import json
import subprocess
import time
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.linalg import blas

from src.io.task042_v4_gate import strict_from_norms
from src.runners.task042_coarse_stages import build_original
from src.runners.task042_experiment import digest
from src.runners.task042_shared import ROOT, write_json
from src.runners.task042_two_level import action_pair, local_pc
from src.solvers.coarse_inverse_protocol import CoarseRHS, CoarseState
from src.solvers.learned_coarse_data import (
    BorrowedMatrixAction,
    file_sha256,
    mapped_original_residual,
)
from src.solvers.learned_coarse_inverse import (
    OriginalEquationAudit,
    cell_declarations,
    native_numpy_apply,
)
from src.solvers.learned_fixed_localization import (
    complement_probes,
    coverage,
    defect,
    diagnostic_budget,
    norm,
    relative,
    same_residual_actions,
)
from src.solvers.learned_two_level import BalancedTwoLevelPC

CONFIG = ROOT / "input/task042_neural_coarse_inverse/localization_v5.json"
INDEX = ROOT / "tmp/task042/v5/stage_index.json"


def verify_file(item):
    path = ROOT / item["path"]
    if file_sha256(path) != item["sha256"]:
        raise ValueError("V5 frozen artifact changed: " + item["path"])
    return path


def verify_run(proof):
    for item in proof["files"]:
        verify_file(item)
    directory = ROOT / proof["directory"]
    manifest = json.loads((directory / "run_manifest.json").read_text())
    summary = json.loads((directory / "run_summary.json").read_text())
    if manifest["source_sha"] != proof["source_sha"] or manifest["git_status"]:
        raise ValueError("frozen run source not clean/matched")
    if summary["leader_exit_code"] != 0 or not summary["descendants_cleared"]:
        raise ValueError("frozen run not released")
    return json.loads((directory / "numerical_summary.json").read_text())


def completed(stage):
    proof = json.loads(INDEX.read_text())[stage]
    directory = Path(proof["directory"])
    for name, sha in proof["files_sha256"].items():
        if file_sha256(directory / name) != sha:
            raise ValueError("V5 prerequisite changed")
    summary = json.loads((directory / "run_summary.json").read_text())
    if summary["leader_exit_code"] != 0 or not summary["descendants_cleared"]:
        raise ValueError("V5 prerequisite not released")
    return directory, json.loads((directory / "numerical_summary.json").read_text())


def canonical_from_storage(action, full, port):
    result = np.empty(action.reduced_size, dtype=np.complex128)
    constraints = action.condensed.trace_constraints
    for original in constraints.owned_active_original_dofs:
        result[constraints.original_to_active[int(original)]] = full[int(original)]
    result[action.condensed.active_rows :] = port
    return result


class Audits:
    def __init__(self, runtime, apply, native):
        self.runtime, self.apply, self.native = runtime, apply, native
        self.calls = 0
        self.seconds = 0.0

    def evaluate(self, x, rhs, raw, fixed_port, submitted=None):
        started = time.perf_counter()
        action = self.runtime.action
        field = (
            action.recover_storage(x, full_rhs=rhs.fe)
            if submitted is None
            else submitted
        )
        state = CoarseState(field, x[action.condensed.active_rows :].copy())
        witness = OriginalEquationAudit(action, self.native)
        d = witness.evaluate(state, rhs)
        image = self.apply(x)
        residual = raw - image
        mapped = mapped_original_residual(action, residual)
        values = {
            "native_absolute": norm(d["native_residual"]),
            "native_scale": d["native_rhs_operation_scale"],
            "port_absolute": norm(d["augmented_port_residual"]),
            "port_scale": d["port_operation_scale"],
            "internal_absolute": norm(d["internal_residual"]),
            "internal_scale": d["internal_operation_scale"],
            "native_identity_absolute": norm(d["native_identity_difference"]),
            "native_identity_scale": d["native_identity_operation_scale"],
            "Schur_port_identity_absolute": norm(d["schur_port_identity_difference"]),
            "Schur_port_identity_scale": d["schur_port_identity_operation_scale"],
            "submitted_recovery_absolute": norm(d["submitted_recovery_difference"]),
            "submitted_field_norm": norm(field),
            "maximum_slave_storage": float(
                np.max(
                    np.abs(field[self.runtime.levels["floquets"][4].mpc.slaves]),
                    initial=0,
                )
            ),
            "finite": bool(np.isfinite(field).all() and np.isfinite(x).all()),
        }
        checks = {
            "Schur_independent_operation_defect": defect(
                residual, d["schur_residual"], norm(raw), norm(image)
            ),
            "native_map_operation_defect": relative(
                norm(mapped - d["native_residual"]),
                d["native_identity_operation_scale"],
            ),
            "native_identity_relative": d["native_identity_relative"],
            "Schur_port_identity_relative": d["schur_port_identity_relative"],
            "internal_recovery_relative": d["internal_residual_relative"],
            "submitted_recovery_relative": relative(
                values["submitted_recovery_absolute"], norm(field)
            ),
        }
        if (
            not values["finite"]
            or values["maximum_slave_storage"]
            or max(checks.values()) > 1e-10
        ):
            raise ValueError(
                "V5 independent original action/recovery self-check failed"
            )
        if fixed_port is None:
            fixed_port = d["port_operation_scale"]
        row = {
            "original_norms": values,
            "checks": checks,
            "native_relative": relative(
                values["native_absolute"], values["native_scale"]
            ),
            "Schur_absolute": norm(residual),
            "Schur_rhs_norm": norm(raw),
            "Schur_relative_rhs": relative(norm(residual), norm(raw)),
            "port_absolute": values["port_absolute"],
            "port_operation_relative": d["port_residual_relative"],
            "port_initial_reference_scale": fixed_port,
            "port_fixed_reference_value": relative(values["port_absolute"], fixed_port),
            "port_fixed_reference_rule": "relative to original zero-start scale"
            if fixed_port
            else "exact-zero initial scale: absolute",
            "original_strict_metrics_pass": strict_from_norms(values),
            "full_field_norm": norm(field),
            "full_field_sha256": digest(field),
            "port_state_norm": norm(state.port),
            "diagnostic_only_no_solver_qualification": True,
        }
        self.calls += 1
        self.seconds += time.perf_counter() - started
        return row, residual


def d0(runtime, apply, native, directory, artifact, design, marker):
    verify_run(design["rhs_source_run"])
    rhs_rows = []
    rhs_cache = {}
    action = runtime.action
    audit = Audits(runtime, apply, native)
    for item in design["rhs"]:
        path = verify_file(item)
        with np.load(path, allow_pickle=False) as packet:
            rhs = CoarseRHS(packet["rhs_fe"], packet["rhs_port"])
        raw = action.reduce_rhs(rhs.fe, port_rhs=rhs.port, rhs_is_mpc_dual=True)
        zero = np.zeros(action.reduced_size, dtype=np.complex128)
        initial, _ = audit.evaluate(zero, rhs, raw, None)
        target = artifact / f"rhs_{item['index']:03d}.npz"
        np.savez(target, rhs_fe=rhs.fe, rhs_port=rhs.port, raw=raw)
        row = {
            **item,
            "reused_source_sha": design["rhs_source_run"]["source_sha"],
            "canonical_packet_path": str(target),
            "canonical_packet_sha256": file_sha256(target),
            "raw_sha256": digest(raw),
            "fe_sha256": digest(rhs.fe),
            "port_sha256": digest(rhs.port),
            "full_rhs_norm": norm(rhs.fe),
            "port_rhs_norm": norm(rhs.port),
            "Schur_rhs_norm": norm(raw),
            "initial_audit": initial,
            "normalization": design["state_normalization"],
        }
        rhs_rows.append(row)
        rhs_cache[item["index"]] = (rhs, raw, initial)
    states = []
    for item in design["state_order"]:
        row = dict(item)
        rhs, raw, initial = rhs_cache[item["rhs_index"]]
        fixed = initial["port_initial_reference_scale"]
        if item["origin"] == "ZERO":
            x = np.zeros(action.reduced_size, dtype=np.complex128)
            measured, residual = initial, raw.copy()
            row["original_source_sha"] = design["rhs_source_run"]["source_sha"]
            row["zero_start_full_field"] = (
                "original particular recovery, not assumed full zero"
            )
        else:
            old = verify_run(item["run"])
            old_row = next(r for r in old["rows"] if r["index"] == item["rhs_index"])
            label = next(
                r["label"] for r in rhs_rows if r["index"] == item["rhs_index"]
            )
            if (
                old_row["label"] != label
                or old_row["strict_return"]["operator_sha256"]
                != design["operator_sha256"]
            ):
                raise ValueError("historical state family/operator mismatch")
            row["original_source_sha"] = item["run"]["source_sha"]
            if item["packet"] is None or not (ROOT / item["packet"]["path"]).is_file():
                row.update(
                    status="missing",
                    reason="saved full state unavailable; no long KSP replay",
                )
                states.append(row)
                continue
            with np.load(verify_file(item["packet"]), allow_pickle=False) as packet:
                if not np.array_equal(packet["rhs_fe"], rhs.fe) or not np.array_equal(
                    packet["rhs_port"], rhs.port
                ):
                    raise ValueError("same-state RHS bytes/scale changed")
                full, port = packet["state_fe"], packet["state_port"]
            x = canonical_from_storage(action, full, port)
            measured, residual = audit.evaluate(x, rhs, raw, fixed, submitted=full)
            old_native = old_row.get("native", old_row.get("final", {}).get("native"))[
                "native_residual_relative"
            ]
            row["saved_native_relative"] = old_native
            row["recomputed_vs_saved_native_absolute_difference"] = abs(
                old_native - measured["native_relative"]
            )
            if row["recomputed_vs_saved_native_absolute_difference"] > 1e-10:
                raise ValueError("saved state/native scalar mismatch")
        target = artifact / (item["state_id"] + ".npz")
        np.savez(target, x=x, residual=residual)
        row.update(
            status="verified",
            canonical_state_path=str(target),
            canonical_state_sha256=file_sha256(target),
            x_sha256=digest(x),
            residual_sha256=digest(residual),
            x_norm=norm(x),
            residual_norm=norm(residual),
            label=next(r["label"] for r in rhs_rows if r["index"] == item["rhs_index"]),
            audit=measured,
            role="consumed diagnostic state; no fresh test",
            normalization=design["state_normalization"],
        )
        states.append(row)
        write_json(
            directory / "common_state_manifest.json",
            {"rhs": rhs_rows, "states": states},
        )
        marker(
            "V5_common_state_verified",
            {
                "state_id": item["state_id"],
                "native_relative": measured["native_relative"],
            },
        )
    witnesses = [raw for _, raw, _ in rhs_cache.values()]
    pair = action_pair(
        runtime,
        apply,
        native,
        (witnesses[0] / norm(witnesses[0]), 1j * witnesses[-1] / norm(witnesses[-1])),
    )
    if not pair["passed"]:
        raise ValueError("D0 real Schur/native pairing failed")
    result = {
        "status": "COMMON_STATES_VERIFIED",
        "registered_count": len(states),
        "available_count": sum(s["status"] == "verified" for s in states),
        "rhs": rhs_rows,
        "states": states,
        "spaces": design["spaces"],
        "real_action_pair": pair,
        "original_audit_calls": audit.calls,
        "original_audit_seconds_inclusive": audit.seconds,
        "teacher_loaded": False,
        "local_geometry_PC_constructed": False,
    }
    write_json(directory / "common_state_manifest.json", result)
    return result


def load_common():
    directory, summary = completed("V5-D0")
    if summary["status"] != "COMMON_STATES_VERIFIED":
        raise ValueError("D0 identity gate required")
    manifest = json.loads((directory / "common_state_manifest.json").read_text())
    return manifest


def state_arrays(state):
    if file_sha256(state["canonical_state_path"]) != state["canonical_state_sha256"]:
        raise ValueError("common state packet changed")
    with np.load(state["canonical_state_path"], allow_pickle=False) as packet:
        x, residual = packet["x"], packet["residual"]
    if digest(x) != state["x_sha256"] or digest(residual) != state["residual_sha256"]:
        raise ValueError("common vector identity changed")
    return x, residual


def rhs_arrays(item):
    if file_sha256(item["canonical_packet_path"]) != item["canonical_packet_sha256"]:
        raise ValueError("common RHS packet changed")
    with np.load(item["canonical_packet_path"], allow_pickle=False) as packet:
        return CoarseRHS(packet["rhs_fe"], packet["rhs_port"]), packet["raw"]


def frozen_space(design, route):
    proof = design["spaces"][route]
    record = verify_run(proof["run"])
    path = verify_file(proof["basis"])
    if (
        record["basis_sha256"] != proof["basis"]["sha256"]
        or record["effective_rank"] != proof["rank"]
    ):
        raise ValueError("frozen Z/U/R source/rank mismatch")
    with np.load(path, allow_pickle=False) as packet:
        z, u, r = (np.asfortranarray(packet[key]) for key in ("z", "u", "r"))
    rank = z.shape[1]
    orth = {
        name: norm(blas.zgemm(1.0, a, a, trans_a=2) - np.eye(rank)) / np.sqrt(rank)
        for name, a in (("Z", z), ("U", u))
    }
    if max(orth.values()) > 1e-10:
        raise ValueError("frozen Z/U orthogonality changed; no checkpoint replacement")
    return (z, u, r), {
        "basis": proof["basis"],
        "source_sha": proof["run"]["source_sha"],
        "effective_rank": rank,
        "orthogonality": orth,
        "checkpoint_modified": False,
    }


def teacher_row(path, key, row):
    """Select only one row from a stored .npy member, without 32-answer copies."""
    with ZipFile(path) as archive, archive.open(key + ".npy") as stream:
        version = np.lib.format.read_magic(stream)
        reader = (
            np.lib.format.read_array_header_1_0
            if version == (1, 0)
            else np.lib.format.read_array_header_2_0
        )
        shape, fortran, dtype = reader(stream)
        if fortran or dtype.hasobject or not 0 <= row < shape[0]:
            raise ValueError("teacher requires bounded non-object C-order rows")
        width = int(np.prod(shape[1:]))
        stream.seek(row * width * dtype.itemsize, 1)
        data = stream.read(width * dtype.itemsize)
        if len(data) != width * dtype.itemsize:
            raise ValueError("teacher selected row truncated")
        return np.frombuffer(data, dtype=dtype).copy().reshape(shape[1:])


def d1(runtime, apply, native, directory, design, marker):
    common = load_common()
    teacher = design["teacher"]
    references, missing = {}, {}
    audit = Audits(runtime, apply, native)
    allowed = (0, 10, 11)
    if teacher["allowed_rows"] != list(allowed):
        raise ValueError("offline exception only consumed teacher 0/10/11")
    batch_path = ROOT / teacher["batch"]["path"]
    if batch_path.is_file():
        verify_run(teacher["run"])
        manifest = json.loads(verify_file(teacher["manifest"]).read_text())
        labels = json.loads(verify_file(teacher["labels"]).read_text())
        if (
            manifest["operator_sha256"] != design["operator_sha256"]
            or manifest["precision"] != "complex128"
            or manifest["normalization"] != teacher["normalization"]
        ):
            raise ValueError("offline teacher operator/normalization changed")
        verify_file(teacher["batch"])
        for item in common["rhs"]:
            index = item["index"]
            if index not in allowed or labels[index]["label"] != item["label"]:
                raise ValueError("teacher family match failed")
            rhs, raw = rhs_arrays(item)
            scale = float(teacher_row(batch_path, "normalization_scale", index))
            star = teacher_row(batch_path, "solution", index) * scale
            g = teacher_row(batch_path, "rhs_fe", index) * scale
            port = teacher_row(batch_path, "rhs_port", index) * scale
            saved_raw = teacher_row(batch_path, "raw", index) * scale
            pairs = {
                "fe": defect(g, rhs.fe),
                "port": defect(port, rhs.port),
                "Schur": defect(saved_raw, raw),
            }
            if max(pairs.values()) > 1e-10:
                raise ValueError("offline consumed teacher RHS scaling mismatch")
            checked, rstar = audit.evaluate(
                star, rhs, raw, item["initial_audit"]["port_initial_reference_scale"]
            )
            if (
                not checked["original_strict_metrics_pass"]
                or checked["Schur_relative_rhs"] > 1e-10
            ):
                raise ValueError("offline reused teacher not accurate")
            references[index] = (
                star,
                rstar,
                {
                    "teacher_solution_sha256": digest(star),
                    "teacher_residual_sha256": digest(rstar),
                    "teacher_normalization_scale": scale,
                    "teacher_audit": checked,
                    "RHS_match": pairs,
                },
            )
    else:
        missing = {
            i: "existing consumed teacher batch missing; new factor not authorized"
            for i in allowed
        }
    rows = []
    for route in ("OLDPOD", "ERROR"):
        (z, u, r), space = frozen_space(design, route)
        for state in common["states"]:
            if state["status"] != "verified":
                continue
            x, residual = state_arrays(state)
            residual_record, _, _ = coverage(residual, u)
            row = {
                "route": route,
                "state_id": state["state_id"],
                "rhs_index": state["rhs_index"],
                "residual_sha256": state["residual_sha256"],
                "residual_coverage": residual_record,
                "space": space["basis"],
            }
            index = state["rhs_index"]
            if index in references:
                star, rstar, reference = references[index]
                error = star - x
                error_record, _, _ = coverage(error, z)
                se = apply(error)
                raw_norm = next(
                    a["Schur_rhs_norm"] for a in common["rhs"] if a["index"] == index
                )
                relation = defect(se, residual - rstar, 2 * raw_norm)
                if relation > 1e-10:
                    raise ValueError(
                        "true error/teacher-residual coordinate relation failed"
                    )
                row.update(
                    error_coverage=error_record,
                    teacher=reference,
                    error_sha256=digest(error),
                    S_error_relation_operation_defect=relation,
                    teacher_residual_norm=norm(rstar),
                    error_status="measured offline consumed exception",
                )
            else:
                row.update(
                    error_coverage=None,
                    error_status="not_available",
                    missing_reason=missing[index],
                )
            rows.append(row)
        del z, u, r
        marker(
            "V5_offline_space_coverage_complete",
            {"route": route, "teacher_count": len(references)},
        )
    del references
    result = {
        "status": "OFFLINE_COVERAGE_COMPLETE",
        "rows": rows,
        "teacher_exception_indices": list(allowed),
        "teacher_reference_count": 0 if missing else 3,
        "teacher_missing": missing,
        "new_reference_factor": False,
        "local_PC_constructed": False,
        "only_scalars_hashes_output": True,
        "teacher_vectors_or_coefficients_saved": False,
        "original_audit_calls": audit.calls,
        "original_audit_seconds_inclusive": audit.seconds,
    }
    write_json(directory / "offline_coverage.json", result)
    return result


class CountedLocal:
    """Instrument the unchanged geometric action without editing its source."""

    def __init__(self, local):
        self.borrowed = local
        self.calls = 0

    def apply_array(self, source):
        self.calls += 1
        return self.borrowed.apply_array(source)

    def __getattr__(self, name):
        return getattr(self.borrowed, name)


def diagnose(runtime, apply, native, local, directory, artifact, design, route, marker):
    common = load_common()  # D1 teacher output is deliberately never loaded.
    (z, u, r), space = frozen_space(design, route)
    counted = CountedLocal(local)
    pc = BalancedTwoLevelPC(counted, apply, z, u, r)
    audit = Audits(runtime, apply, native)
    pair = action_pair(runtime, apply, native, (z[:, 0], 1j * z[:, -1]))
    if not pair["passed"]:
        raise ValueError("fixed space real Schur/native pairing failed")
    rows, probe_inputs = [], []
    for state in common["states"]:
        if state["status"] != "verified":
            continue
        x, residual = state_arrays(state)
        item = next(a for a in common["rhs"] if a["index"] == state["rhs_index"])
        rhs, raw = rhs_arrays(item)
        if defect(raw - apply(x), residual, norm(raw)) > 1e-10:
            raise ValueError("same residual recomputation failed")
        started = time.perf_counter()
        report, corrections, arrays = same_residual_actions(pc, residual)
        algebra_seconds = time.perf_counter() - started
        corrected_audits = {}
        for name, correction in corrections.items():
            measured, remaining = audit.evaluate(
                x + correction,
                rhs,
                raw,
                item["initial_audit"]["port_initial_reference_scale"],
            )
            image = apply(correction)
            corrected_pair = defect(
                remaining, residual - image, norm(raw), norm(apply(x))
            )
            if corrected_pair > 1e-10:
                raise ValueError(
                    "corrected original Schur audit not on the same residual"
                )
            measured.update(
                rho_same_residual=relative(norm(remaining), norm(residual)),
                corrected_pair_defect=corrected_pair,
            )
            corrected_audits[name] = measured
            arrays["remaining_" + name] = remaining
        target = artifact / ("actions_" + state["state_id"] + ".npz")
        io_started = time.perf_counter()
        np.savez(target, **arrays)
        row = {
            "route": route,
            "state_id": state["state_id"],
            "rhs_index": state["rhs_index"],
            "residual_sha256": state["residual_sha256"],
            "state_sha256": state["x_sha256"],
            "report": report,
            "corrected_audits": corrected_audits,
            "arrays_path": str(target),
            "arrays_sha256": file_sha256(target),
            "algebra_seconds": algebra_seconds,
            "io_seconds": time.perf_counter() - io_started,
            "diagnostic_only": True,
        }
        rows.append(row)
        probe_inputs.append((state["state_id"], residual))
        write_json(directory / "same_residual_actions.json", rows)
        marker(
            "V5_same_residual_actions_complete",
            {
                "route": route,
                "state_id": state["state_id"],
                "rho_B_opt": report["directions"]["B"]["rho_opt"],
                "rho_B2_opt": report["directions"]["B2"]["rho_opt"],
                "rho_ZB": report["rho_ZB"],
            },
        )
        del corrections, arrays
    started = time.perf_counter()
    probes, probe_arrays = complement_probes(
        pc, probe_inputs, seed=design["probe_seed"]
    )
    probe_seconds = time.perf_counter() - started
    path = artifact / "complement_probes.npz"
    np.savez(path, **probe_arrays)
    probes.update(
        arrays_path=str(path),
        arrays_sha256=file_sha256(path),
        route=route,
        probe_seconds_inclusive=probe_seconds,
    )
    write_json(directory / "complement_probes.json", probes)
    result = {
        "status": "FIXED_OBJECT_DIAGNOSTICS_COMPLETE",
        "route": route,
        "state_count": len(rows),
        "space": space,
        "rows": rows,
        "complement": probes,
        "real_action_pair": pair,
        "teacher_loaded": False,
        "D1_reference_output_loaded": False,
        "local_PC": "R-GEO-CELL80-v3",
        "local_B_calls_including_audit": counted.calls,
        "local_B_seconds_including_audit": local.seconds,
        "two_level": pc.counters(),
        "original_audit_calls": audit.calls,
        "original_audit_seconds_inclusive": audit.seconds,
        "probe_seconds_inclusive": probe_seconds,
        "no_new_KSP": True,
        "factor_inventory": {
            "global_p4_factor_created": False,
            "original_S_borrowed": True,
            "private_audit_CSR": False,
            "geometry_patch_factor_bytes": local.factor_bytes,
            "R_payload_bytes": r.nbytes,
            "patch_count": len(local.patches),
            "maximum_patch_rows": max(len(a) for a in local.patches),
            "R_rows": pc.rank,
            "Z_U_payload_bytes": z.nbytes + u.nbytes,
            "Z_U_R_array_hashes": {
                key: digest(a) for key, a in (("Z", z), ("U", u), ("R", r))
            },
        },
    }
    write_json(directory / "fixed_diagnostics.json", result)
    return result


def run_localization_stage(cfg, comm, stage, directory, artifact, source, marker):
    design = json.loads(CONFIG.read_text())
    verify_file(design["review"])
    if (
        file_sha256(ROOT / design["geometry"]["evidence_path"])
        != design["geometry"]["evidence_sha256"]
    ):
        raise ValueError("frozen geometric identity changed")
    for filename, sha in design["frozen_source_blobs"].items():
        if file_sha256(ROOT / filename) != sha:
            raise ValueError("frozen numerical source changed: " + filename)
        if (
            subprocess.check_output(["git", "hash-object", filename], text=True).strip()
            != design["frozen_source_git_blobs"][filename]
        ):
            raise ValueError("frozen Git blob changed: " + filename)
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    if INDEX.exists() and stage in json.loads(INDEX.read_text()):
        raise ValueError("V5 stage already completed; no numerical repeat")
    if stage != "V5-D0":
        load_common()
    write_json(directory / "v5_design.json", design)
    profile = json.loads(
        (
            ROOT / "input/task042_neural_coarse_inverse/shared_profile_v1.json"
        ).read_text()
    )
    started = time.perf_counter()
    runtime, _, identity = build_original(cfg, comm, profile, marker)
    runtime_setup = time.perf_counter() - started
    local = apply = None
    result = {}
    try:
        write_json(
            directory / "qualified_original_operator.json",
            {
                "identity": identity,
                "matrix": runtime.operator_identity,
                "full_p6_constructed": False,
            },
        )
        frozen_geometry = json.loads(
            (ROOT / design["geometry"]["evidence_path"]).read_text()
        )
        capacity = diagnostic_budget(
            runtime.action.reduced_size,
            128,
            runtime.p4_system.full_rows,
            frozen_geometry["representation_bytes"],
            frozen_geometry["all_factor_bytes"],
        )
        write_json(directory / "diagnostic_preconstruction_budget.json", capacity)
        marker("V5_diagnostic_capacity_before_geometry_or_space_load", capacity)
        apply = BorrowedMatrixAction(runtime.p4_system.matrix)
        native = native_numpy_apply(runtime.p4)
        cell_bytes = sum(d.payload_bytes for d in cell_declarations(runtime.action))
        if stage == "V5-D0":
            result = d0(runtime, apply, native, directory, artifact, design, marker)
        elif stage == "V5-D1":
            result = d1(runtime, apply, native, directory, design, marker)
        elif stage in ("V5-OLDPOD", "V5-ERROR"):
            local, _, actual_cell_bytes = local_pc(runtime, directory, design, marker)
            if (
                actual_cell_bytes != cell_bytes
                or local.factor_bytes + cell_bytes
                != frozen_geometry["all_factor_bytes"]
            ):
                raise ValueError("frozen B factor payload changed")
            result = diagnose(
                runtime,
                apply,
                native,
                local,
                directory,
                artifact,
                design,
                stage.removeprefix("V5-"),
                marker,
            )
        else:
            raise ValueError("unknown V5 fixed-object stage")
        result.update(
            runtime_setup_seconds_inclusive=runtime_setup,
            diagnostic_capacity=capacity,
            global_p4_factor_created=False,
            private_audit_csr=False,
            original_operator_sha256=runtime.operator_identity["csr_sha256"],
            local_factor_payload_bytes=cell_bytes
            + (local.factor_bytes if local else 0),
            local_setup_seconds=local.setup_seconds if local else 0.0,
            exact_S_action_calls=apply.calls,
            exact_S_action_seconds_inclusive=apply.seconds,
            actual_numeric_source_sha=source,
            KSP_campaign=False,
            new_training=False,
            F5=False,
            GPU=False,
            fresh_pool_generated_or_read=False,
            costs_shared_workstation=True,
            timing_policy="runtime/setup and audit/probe parents inclusive; nested B/C/S children never added to parent",
        )
        return result
    finally:
        released = time.perf_counter()
        if local is not None:
            local.factors.clear()
        if apply is not None:
            apply.destroy()
        runtime.destroy()
        result["release_seconds"] = time.perf_counter() - released
        marker(
            "V5_original_local_objects_and_space_worker_released",
            {"release_seconds": result["release_seconds"]},
        )
