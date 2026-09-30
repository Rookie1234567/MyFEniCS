"""Opt-in reference-exposed full-moment representation diagnosis only.

Never imported by the FE process or the three PDE-only route entrypoints.
"""

import json
import os
from pathlib import Path
import signal
from time import perf_counter

import numpy as np
from scipy import sparse
import torch

from src.solvers.feinn_error_geometry import reference_label
from src.solvers.feinn_native import load_native
from src.solvers.feinn_optimization import RouteStop, transactional_step
from src.solvers.feinn_torch import CompleteMomentMap, CoordinateField
from src.solvers.feinn_validation import assign, load_moments, parameters
from src.solvers.neural_fe_action_packet import array_hash
from src.runners.feinn_workflow import sha


LABELS = dict(
    reference_used_for_training=True,
    pde_only_solve=False,
    production_initialization_allowed=False,
    data_role="REFERENCE_EXPOSED_DIAGNOSTIC_ONLY",
)


class FitMetric:
    """J=Re(e*G e)/(2d), with real differential Re(g*dc)."""

    def __init__(self, G, reference):
        self.G = sparse.csr_matrix(G, dtype=np.complex128)
        self.reference = np.asarray(reference, dtype=np.complex128)
        self.denominator = float(np.vdot(reference, self.G @ reference).real)
        if (
            self.G.shape != (len(reference), len(reference))
            or not np.isfinite(self.denominator)
            or self.denominator <= 0
        ):
            raise ValueError("FIT_GRAM_REFERENCE_IDENTITY_FAILED")
        self.matvec_count = 1
        self.matvec_seconds = 0.0

    def value(self, c, gradient=False):
        e = np.asarray(c, dtype=np.complex128) - self.reference
        if e.shape != self.reference.shape or not np.isfinite(e).all():
            raise ValueError("FIT_COEFFICIENTS_INVALID")
        start = perf_counter()
        Ge = self.G @ e
        self.matvec_seconds += perf_counter() - start
        self.matvec_count += 1
        dot = np.vdot(e, Ge)
        if dot.real < -1e-14 or abs(dot.imag) > 1e-10 * max(abs(dot.real), 1e-30):
            raise ValueError("FIT_QUADRATIC_INVALID")
        return float(dot.real / (2 * self.denominator)), (
            Ge / self.denominator if gradient else None
        )


def load_problem(design, native_index, grad_index, reference_index):
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if (
        torch.version.cuda is not None
        or torch.get_num_threads() != 1
        or torch.get_num_interop_threads() != 1
        or len(os.sched_getaffinity(0)) != 1
    ):
        raise RuntimeError("CPU_ONLY_ONE_CORE_GATE_FAILED")
    packet = load_native(native_index["files"]["native"]["path"])
    reference, label = reference_label(native_index, reference_index, packet, used_for_training=True)
    if grad_index["result"]["status"] != "INTERFACE_PASS_ONLY":
        raise ValueError("COMPLETE_MOMENT_INTERFACE_NOT_QUALIFIED")
    moments_entry = grad_index["files"]["moments"]
    if (
        sha(moments_entry["path"]) != moments_entry["sha256"]
        or moments_entry["sha256"]
        != "0260c986bc7a71d6b8d6b0b695df4ca730d24654f5ad0705313a45205c28b69e"
    ):
        raise ValueError("MOMENT_IDENTITY_FAILED")
    G = sparse.load_npz(native_index["files"]["gram"]["path"])
    metric = FitMetric(G, reference)
    mapping = CompleteMomentMap(load_moments(moments_entry["path"]))
    model = CoordinateField(design["geometry"]["bounds_nm"], design["network"]["seed"])
    if mapping.size != packet.size or len(parameters(model)) != 8966:
        raise ValueError("FULL_MASTER_OR_NETWORK_IDENTITY_FAILED")
    label.update(
        moments_sha256=moments_entry["sha256"],
        background_sha256=array_hash(packet.a["background"]),
        masters_sha256=array_hash(packet.a["masters"]),
        parameter_initialization_sha256=array_hash(parameters(model)),
        reference_c_sha256=array_hash(reference),
    )
    return packet, metric, mapping, model, label


def _relative(left, right):
    return float(np.linalg.norm(left - right) / max(np.linalg.norm(right), 1e-12))


def fit_checks(design, native_index, grad_index, reference_index, artifact, marker):
    # Synthetic complex quadratic and exact-zero checks are independent of Torch.
    testG = sparse.csr_matrix(
        np.array([[3, 1 + 0.5j], [1 - 0.5j, 4]], dtype=np.complex128)
    )
    ref = np.array([1 + 2j, -0.5 + 0.2j], dtype=np.complex128)
    synthetic = FitMetric(testG, ref)
    zero, zero_g = synthetic.value(ref, True)
    if zero != 0 or np.any(zero_g):
        raise ValueError("FIT_ZERO_ERROR_TEST_FAILED")
    x = np.array([0.2 - 0.4j, 0.7 + 0.1j], dtype=np.complex128)
    j, g = synthetic.value(x, True)
    direction = np.array([0.6 + 0.2j, -0.3 + 0.5j], dtype=np.complex128)
    fd = (
        synthetic.value(x + 1e-6 * direction)[0]
        - synthetic.value(x - 1e-6 * direction)[0]
    ) / (2e-6)
    synthetic_error = abs(fd - np.vdot(g, direction).real) / max(abs(fd), 1e-12)
    if synthetic_error > 1e-8 or j <= 0:
        raise ValueError("FIT_SYNTHETIC_GRADIENT_FAILED")
    packet, metric, mapping, model, label = load_problem(
        design, native_index, grad_index, reference_index
    )
    rng = np.random.default_rng(421002)
    base = parameters(model) + 0.005 * rng.standard_normal(8966)
    assign(model, base)
    c8 = mapping.forward(model, 8)
    c1 = mapping.forward(model, 1)
    loss8, dual8 = metric.value(c8, True)
    loss1, dual1 = metric.value(c1, True)
    grad8 = mapping.vjp(model, dual8, 8)
    grad1 = mapping.vjp(model, dual1, 1)
    batch = dict(
        c_relative=_relative(c1, c8),
        loss_relative=abs(loss1 - loss8) / max(abs(loss8), 1e-12),
        gradient_relative=_relative(grad1, grad8),
    )
    if max(batch.values()) > 1e-10:
        raise ValueError("FIT_BATCH_1_8_FAILED")
    hidden_count = 8966 - (64 * 6 + 6)
    directions = [
        np.r_[grad8[:hidden_count], np.zeros(8966 - hidden_count)],
        np.r_[np.zeros(hidden_count), grad8[hidden_count:]],
        rng.standard_normal(8966),
    ]
    fd_rows = []
    for n, d in enumerate(directions):
        d /= np.linalg.norm(d)
        exact = float(np.dot(grad8, d))
        if abs(exact) <= 1e-10:
            raise ValueError("FIT_NONZERO_REAL_DIRECTION_REQUIRED")
        observations = []
        for h in (1e-4, 1e-5, 1e-6):
            assign(model, base + h * d)
            plus = metric.value(mapping.forward(model, 8))[0]
            assign(model, base - h * d)
            minus = metric.value(mapping.forward(model, 8))[0]
            observed = (plus - minus) / (2 * h)
            observations.append(
                dict(h=h, value=observed, relative=abs(observed - exact) / abs(exact))
            )
        fd_rows.append(dict(direction=n, analytic=exact, observations=observations))
        if min(row["relative"] for row in observations) > 1e-5:
            raise ValueError("FIT_REAL_PARAMETER_FD_FAILED")
    assign(model, base)
    before = parameters(model)

    def read():
        return parameters(model)

    def restore(x):
        assign(model, x)

    def failing_step(cb):
        assign(model, before + 1)
        cb()
        raise RuntimeError("injected rollback")

    try:
        transactional_step(failing_step, lambda: None, read, restore)
    except RuntimeError as error:
        if str(error) != "injected rollback":
            raise
    if not np.array_equal(before, parameters(model)):
        raise ValueError("FIT_TRANSACTION_FAILED")
    result = dict(
        status="REFERENCE_FIT_CHECKS_PASS",
        synthetic_error=synthetic_error,
        batch=batch,
        finite_differences=fd_rows,
        transaction_exception_restored=True,
        label_isolation=label,
        old_pde_only_routes_unchanged=True,
        no_Gsolve=True,
        no_Gram_factor=True,
        no_A_or_AH=True,
        **LABELS,
    )
    marker("reference_fit_checks", dict(status=result["status"], batch=batch))
    return result, {}


def run_fit(
    design,
    native_index,
    grad_index,
    reference_index,
    checks_index,
    artifact,
    marker,
    wall_seconds,
):
    began = perf_counter()
    if checks_index["result"]["status"] != "REFERENCE_FIT_CHECKS_PASS":
        raise ValueError("FIT_CHECKS_NOT_QUALIFIED")
    packet, metric, mapping, model, label = load_problem(
        design, native_index, grad_index, reference_index
    )
    if label != checks_index["result"]["label_isolation"]:
        raise ValueError("FIT_LABEL_IDENTITY_CHANGED_SINCE_CHECKS")
    initial = parameters(model)
    initial_c = mapping.forward(model, 8)
    if np.any(initial_c):
        raise ValueError("FIT_ZERO_SCATTERED_INITIALIZATION_FAILED")
    artifact = Path(artifact)
    history_path = artifact / "history.jsonl"
    history = history_path.open("w", buffering=1)
    counts = dict(
        complete_closures=0,
        closure_attempts=0,
        outer_attempts=0,
        committed_steps=0,
        Adam_updates=0,
        LBFGS_outer_steps=0,
        LBFGS_inner_iterations=0,
        native_audits=0,
    )
    audits = []
    trial_p = initial.copy()
    trial_c = initial_c.copy()
    trial_loss = metric.value(initial_c)[0]
    committed = initial.copy()
    stop_reason = "CLOSURE_BUDGET"
    closure_wall = 0.0
    last_audit_closure = -1
    deadline = began + min(10800, wall_seconds) - 120

    def emit(row):
        history.write(json.dumps(row, allow_nan=False) + "\n")

    def read():
        return parameters(model)

    def restore(x):
        assign(model, x)

    def coefficients():
        return mapping.forward(model, 8)

    def checkpoint(path, p, c, state):
        np.savez(
            path,
            parameters=p,
            c=c,
            closures=np.asarray(counts["complete_closures"]),
            committed_steps=np.asarray(counts["committed_steps"]),
            state_kind=np.asarray(state),
            parameter_only=np.asarray(True),
            reference_used_for_training=np.asarray(True),
            pde_only_solve=np.asarray(False),
            production_initialization_allowed=np.asarray(False),
            data_role=np.asarray("REFERENCE_EXPOSED_DIAGNOSTIC_ONLY"),
            reference_c_sha256=np.asarray(label["reference_c_sha256"]),
        )

    def audit(c, tag):
        nonlocal last_audit_closure
        if counts["native_audits"] >= 45:
            raise RuntimeError("FIT_NATIVE_AUDIT_LIMIT")
        row = dict(
            tag=tag,
            closure=counts["complete_closures"],
            fit_loss=metric.value(c)[0],
            E_G=float(np.sqrt(2 * metric.value(c)[0])),
            **packet.audit(c),
        )
        counts["native_audits"] += 1
        last_audit_closure = counts["complete_closures"]
        audits.append(row)
        emit(dict(kind="committed_audit", **row))
        print(
            json.dumps(
                dict(
                    kind="fit_audit",
                    closure=row["closure"],
                    E_G=row["E_G"],
                    native=row["native_relative"],
                )
            ),
            flush=True,
        )
        return row

    def terminate(_sig, _frame):
        nonlocal stop_reason
        stop_reason = "OWN_WATCHDOG_STOP"
        raise RouteStop

    old_signal = signal.signal(signal.SIGTERM, terminate)
    checkpoint(
        artifact / "zero_checkpoint.npz", initial, initial_c, "zero_parameter_only"
    )
    try:
        audit(initial_c, "zero_committed")

        def closure():
            nonlocal trial_p, trial_c, trial_loss, closure_wall, stop_reason
            if counts["complete_closures"] >= 4000 or perf_counter() >= deadline:
                stop_reason = (
                    "WALL_BUDGET" if perf_counter() >= deadline else "CLOSURE_BUDGET"
                )
                raise RouteStop
            t = perf_counter()
            counts["closure_attempts"] += 1
            trial_p = read()
            trial_c = coefficients()
            trial_loss, dual = metric.value(trial_c, True)
            grad = mapping.vjp(model, dual, 8)
            if not np.isfinite(trial_loss) or not np.isfinite(grad).all():
                stop_reason = "NONFINITE"
                raise RouteStop
            counts["complete_closures"] += 1
            closure_wall += perf_counter() - t
            if counts["complete_closures"] % 25 == 0:
                emit(
                    dict(
                        kind="closure",
                        closure=counts["complete_closures"],
                        loss=trial_loss,
                        E_G=float(np.sqrt(2 * trial_loss)),
                        parameter_gradient_norm=float(np.linalg.norm(grad)),
                        parameter_update_norm=float(
                            np.linalg.norm(trial_p - committed)
                        ),
                        committed_steps=counts["committed_steps"],
                        matvec_count=metric.matvec_count,
                        moment_counts=mapping.counts,
                        elapsed_seconds=perf_counter() - began,
                    )
                )
            return torch.tensor(trial_loss, dtype=torch.float64)

        adam = torch.optim.Adam(model.parameters(), lr=1e-3, weight_decay=0)
        for _ in range(500):
            counts["outer_attempts"] += 1
            closure()
            before = read()
            try:
                adam.step()
            except BaseException:
                restore(before)
                raise
            counts["committed_steps"] += 1
            counts["Adam_updates"] += 1
            committed = read()
            if counts["complete_closures"] % 100 == 0:
                c = coefficients()
                row = audit(c, "adam_committed")
                if row["E_G"] <= 1e-3:
                    stop_reason = "FIT_THRESHOLD_REACHED"
                    raise RouteStop
        checkpoint(
            artifact / "adam500_checkpoint.npz",
            committed,
            coefficients(),
            "adam500_parameter_only",
        )
        lbfgs = torch.optim.LBFGS(
            model.parameters(),
            lr=1,
            history_size=20,
            max_iter=20,
            max_eval=25,
            line_search_fn="strong_wolfe",
            tolerance_grad=1e-7,
            tolerance_change=1e-9,
        )
        while counts["complete_closures"] < 4000:
            counts["outer_attempts"] += 1
            before = read()
            transactional_step(lbfgs.step, closure, read, restore)
            counts["committed_steps"] += 1
            counts["LBFGS_outer_steps"] += 1
            counts["LBFGS_inner_iterations"] = int(
                lbfgs.state[list(model.parameters())[0]].get("n_iter", 0)
            )
            committed = read()
            if counts["complete_closures"] // 100 > last_audit_closure // 100:
                row = audit(coefficients(), "lbfgs_committed")
                if row["E_G"] <= 1e-3:
                    stop_reason = "FIT_THRESHOLD_REACHED"
                    break
            if np.array_equal(before, committed):
                stop_reason = "OPTIMIZER_STAGNATION"
                break
    except RouteStop:
        restore(committed)
    finally:
        restore(committed)
        final_c = coefficients()
        if last_audit_closure != counts["complete_closures"]:
            audit(final_c, "final_committed")
        checkpoint(
            artifact / "frozen_checkpoint.npz",
            committed,
            final_c,
            "final_committed_parameter_only",
        )
        checkpoint(
            artifact / "last_trial.npz", trial_p, trial_c, "last_trial_not_committed"
        )
        signal.signal(signal.SIGTERM, old_signal)
        history.close()
    if packet.counts["A"] or packet.counts["AH"]:
        raise ValueError("FIT_CLOSURE_USED_A_OR_AH")
    result = dict(
        status="REFERENCE_EXPOSED_FIT_FROZEN",
        route="FEINN-REFERENCE-FIT-G",
        stop_reason=stop_reason,
        counts=counts,
        initialization_sha256=array_hash(initial),
        final_parameters_sha256=array_hash(committed),
        final_c_sha256=array_hash(final_c),
        final_fit_loss=metric.value(final_c)[0],
        final_E_G=float(np.sqrt(2 * metric.value(final_c)[0])),
        d_ref=metric.denominator,
        final_audit=audits[-1],
        audits=audits,
        labels=label,
        parameter_only_checkpoint=True,
        consistent_optimizer_resume_supported=False,
        last_trial_is_final=False,
        Gram_factor_created=False,
        Gsolve_count=0,
        G_matvec_count=metric.matvec_count,
        G_matvec_seconds=metric.matvec_seconds,
        native_action_counts=packet.counts,
        moment_counts=mapping.counts,
        moment_costs=mapping.costs,
        full_FE_coefficients=packet.size,
        parameter_count=len(initial),
        wall_seconds=perf_counter() - began,
        closure_wall_seconds_nested=closure_wall,
        **LABELS,
    )
    files = dict(
        checkpoint=artifact / "frozen_checkpoint.npz",
        zero=artifact / "zero_checkpoint.npz",
        last_trial=artifact / "last_trial.npz",
        history=history_path,
    )
    adam_path = artifact / "adam500_checkpoint.npz"
    if adam_path.exists():
        files["adam500"] = adam_path
    return result, files


def reconstruct(design, native_index, grad_index, fit_index, artifact, marker):
    """Separate ML process: frozen parameter -> q15/q30 complete moments."""
    retained_only = (
        fit_index["result"]["status"]
        == "INTERRUPTED_FIT_ADAM500_RETAINED_SNAPSHOT"
    )
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    if len(os.sched_getaffinity(0)) != 1 or torch.version.cuda is not None:
        raise RuntimeError("CPU_ONLY_ONE_CORE_GATE_FAILED")
    entry = fit_index["files"]["checkpoint"]
    if sha(entry["path"]) != entry["sha256"]:
        raise ValueError("FIT_CHECKPOINT_CHANGED")
    with np.load(entry["path"], allow_pickle=False) as data:
        p = np.array(data["parameters"])
        saved = np.array(data["c"])
        if (
            not bool(data["reference_used_for_training"])
            or bool(data["pde_only_solve"])
            or bool(data["production_initialization_allowed"])
        ):
            raise ValueError("FIT_LABEL_POLICY_MISSING")
    model = CoordinateField(design["geometry"]["bounds_nm"], design["network"]["seed"])
    assign(model, p)
    q15 = CompleteMomentMap(load_moments(grad_index["files"]["moments"]["path"]))
    q30 = CompleteMomentMap(load_moments(native_index["files"]["moments_q30"]["path"]))
    actual = q15.forward(model, 8)
    higher = q30.forward(model, 8)
    saved_relative = _relative(actual, saved)
    quadrature_relative = _relative(higher, actual)
    if saved_relative > 1e-12:
        raise ValueError("FROZEN_PARAMETERS_DO_NOT_GENERATE_SAVED_FULL_FE_COEFFICIENTS")
    path = Path(artifact) / "reconstructed_full_coefficients.npz"
    np.savez(path, c_q15=actual, c_q30=higher)
    result = dict(
        status="RETAINED_ADAM500_NETWORK_RECONSTRUCTED"
        if retained_only
        else "FROZEN_NETWORK_RECONSTRUCTED",
        fit_checkpoint=entry,
        final_fit_parameters_retained=not retained_only,
        parameter_to_saved_c_relative=saved_relative,
        q30_to_q15_relative=quadrature_relative,
        quadrature_status="PASS" if quadrature_relative <= 1e-8 else "QUADRATURE_DRIFT",
        complete_moments=True,
        full_FE_coefficients=len(actual),
        MUMPS_symbolic_numeric_solve_count=0,
        **LABELS,
    )
    marker("frozen_network_reconstruction", result)
    return result, dict(reconstructed=path)


def retained_interrupted_snapshot(
    design, native_index, grad_index, reference_index, artifact, marker
):
    """Register only the saved Adam500 state after the unique fit disappeared.

    No optimizer is constructed or stepped here. The logged later L-BFGS states
    have no retained parameters and cannot be reconstructed from this snapshot.
    """
    root = Path(__file__).resolve().parents[2]
    record_path = (
        root
        / "docs/task042extra_feinn_5nm/outcomes/records/fit_interruption_v3.json"
    )
    interruption = json.loads(record_path.read_text())
    run_name = interruption["run_directory_name"]
    if (
        Path(run_name).name != run_name
        or not run_name.startswith("task42extra_v3_reference_fit_")
        or interruption["classification"]
        != "EXECUTION_SESSION_LOST_NO_FINAL_CHECKPOINT"
    ):
        raise ValueError("INTERRUPTED_FIT_RECORD_IDENTITY_FAILED")
    old_run = root / "results/task42extra" / run_name
    old_artifact = root / "benchmarks/artifacts/task42extra" / run_name
    if (
        root / "benchmarks/artifacts/task42extra/index_feinn_reference_fit_g.json"
    ).exists():
        raise ValueError("INTERRUPTED_FIT_ALREADY_HAS_FORMAL_FINAL_INDEX")
    paths = dict(
        manifest=old_run / "run_manifest.json",
        resources_jsonl=old_run / "supervision/resources.jsonl",
        history_jsonl=old_artifact / "history.jsonl",
        zero_checkpoint=old_artifact / "zero_checkpoint.npz",
        adam500_checkpoint=old_artifact / "adam500_checkpoint.npz",
    )
    if (
        (old_run / "run_summary.json").exists()
        or (old_artifact / "frozen_checkpoint.npz").exists()
        or (old_artifact / "last_trial.npz").exists()
    ):
        raise ValueError("INTERRUPTED_FIT_UNEXPECTED_FINAL_STATE")
    for key, path in paths.items():
        if sha(path) != interruption[key + "_sha256"]:
            raise ValueError(f"INTERRUPTED_FIT_RAW_HASH_CHANGED: {key}")
    original_manifest = json.loads(paths["manifest"].read_text())
    if (
        original_manifest["source_sha"]
        != interruption["original_fit_source_sha"]
        or original_manifest["stage"] != "FEINN-REFERENCE-FIT-G"
        or not original_manifest["reference_used_for_training"]
        or original_manifest["pde_only_solve"]
        or original_manifest["production_initialization_allowed"]
    ):
        raise ValueError("INTERRUPTED_FIT_MANIFEST_CHANGED")
    history = [json.loads(line) for line in paths["history_jsonl"].read_text().splitlines()]
    observed_closures = max(
        row["closure"] for row in history if row["kind"] == "closure"
    )
    last_audit = max(
        row["closure"] for row in history if row["kind"] == "committed_audit"
    )
    if (
        observed_closures != interruption["observed_complete_closures"]
        or last_audit != interruption["last_logged_committed_audit_closure"]
    ):
        raise ValueError("INTERRUPTED_FIT_HISTORY_CHANGED")
    packet, metric, mapping, model, label = load_problem(
        design, native_index, grad_index, reference_index
    )
    with np.load(paths["zero_checkpoint"], allow_pickle=False) as item:
        zero_p = np.array(item["parameters"])
        zero_c = np.array(item["c"])
        if int(item["closures"]) != 0 or str(item["state_kind"]) != "zero_parameter_only":
            raise ValueError("INTERRUPTED_FIT_ZERO_CHECKPOINT_INVALID")
    if (
        array_hash(zero_p) != label["parameter_initialization_sha256"]
        or np.any(zero_c)
    ):
        raise ValueError("INTERRUPTED_FIT_ZERO_INITIALIZATION_CHANGED")
    with np.load(paths["adam500_checkpoint"], allow_pickle=False) as item:
        p = np.array(item["parameters"])
        c = np.array(item["c"])
        if (
            p.shape != (8966,)
            or c.shape != (31968,)
            or int(item["closures"]) != 500
            or int(item["committed_steps"]) != 500
            or str(item["state_kind"]) != "adam500_parameter_only"
            or str(item["reference_c_sha256"]) != label["reference_c_sha256"]
            or not bool(item["reference_used_for_training"])
            or bool(item["pde_only_solve"])
            or bool(item["production_initialization_allowed"])
        ):
            raise ValueError("INTERRUPTED_FIT_ADAM500_CHECKPOINT_INVALID")
    assign(model, p)
    actual = mapping.forward(model, 8)
    identity_relative = _relative(actual, c)
    if identity_relative > 1e-12:
        raise ValueError("INTERRUPTED_FIT_PARAMETERS_DO_NOT_GENERATE_SAVED_C")
    loss = metric.value(c)[0]
    result = dict(
        status="INTERRUPTED_FIT_ADAM500_RETAINED_SNAPSHOT",
        route="FEINN-REFERENCE-FIT-G",
        stop_reason=interruption["classification"],
        original_fit_source_sha=interruption["original_fit_source_sha"],
        original_run_directory=str(old_run),
        interruption_record_sha256=sha(record_path),
        observed_complete_closures=observed_closures,
        last_logged_committed_audit_closure=last_audit,
        retained_committed_closure=500,
        later_parameters="NOT_RETAINED",
        final_checkpoint="NOT_RETAINED",
        optimizer_state="NOT_RETAINED",
        parameter_to_saved_c_relative=identity_relative,
        retained_parameters_sha256=array_hash(p),
        retained_c_sha256=array_hash(c),
        retained_fit_loss=loss,
        retained_E_G=float(np.sqrt(2 * loss)),
        retained_native_audit=packet.audit(c),
        no_training_or_optimizer_step=True,
        no_Gram_factor=True,
        Gsolve_count=0,
        MUMPS_symbolic_numeric_solve_count=0,
        **LABELS,
    )
    marker(
        "retained_interrupted_fit_snapshot",
        dict(
            retained_closure=500,
            observed_closures=observed_closures,
            retained_E_G=result["retained_E_G"],
        ),
    )
    return result, dict(
        checkpoint=paths["adam500_checkpoint"],
        zero=paths["zero_checkpoint"],
        history=paths["history_jsonl"],
    )
