"""J1 controls-only adapter for the V7 bounded BAL_H preconditioner.

This module deliberately owns no numerical method.  It reuses the formal
Route-A builder and evaluates exactly two saved V5 E1 inputs, one setup and
one complete BAL_H application per input.  The old recursive six-RHS/three-PC
campaign is not reachable from this entry point.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np

from .physical_intermediate import _jsonable
from .workflow_timebase import CONSERVATIVE_REALTIME, ClockBudget, clock_sample


G0_INVENTORY = Path("benchmarks/artifacts/task39extra/v6_recursive/g0_inventory.json")
G0_INVENTORY_SHA256 = "b47cbec33ea05842079e10dea486185703cfa541049d291ddb7fcf5369310a6c"
E1_AUDIT_SHA256 = "23087bc525adbe93ad2dd5911c4741596a3f4e30199f1f81a5e111df3ed45991"
CONTROL_LABELS = ("A2R160", "LIGHT448")
CONTROL_SOURCE_SHA = "c4e86cfe1e6ba88ca5d26df82942e82f190e7eda"
J1_CONTROL_LIMIT_SECONDS = 3600.0
J2_PC_LIMIT_SECONDS = 90.0
J2_EXCEPTION_OUTER_LIMIT = 8
J2_EXCEPTION_SECONDS = 600.0


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _checked_path(path: Path, expected: str) -> Path:
    if _digest(path) != expected:
        raise ValueError(f"J1 frozen evidence hash differs: {path}")
    return path


def load_j1_controls(inventory_path: Path = G0_INVENTORY) -> dict[str, Any]:
    """Load only q and the p6 native map from the hash-bound V5 E1 packets."""

    inventory_path = Path(inventory_path)
    if _digest(inventory_path) != G0_INVENTORY_SHA256:
        raise ValueError("J1 g0 inventory hash differs")
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("source_sha") != "4756b1e26ddde8befdb384f7f3f9e96603baca46":
        raise ValueError("J1 g0 inventory source differs")
    audit_path = Path("benchmarks/artifacts/task39extra/v5_balanced/c4e86cfe1e6ba88ca5d26df82942e82f190e7eda/e1_audit.json")
    _checked_path(audit_path, E1_AUDIT_SHA256)
    audit = json.loads(audit_path.read_text())
    if audit.get("source_sha") != CONTROL_SOURCE_SHA:
        raise ValueError("J1 V5 E1 source differs")
    raw_hashes = {row["path"]: row["sha256"] for row in audit["raw_hashes"]}
    checked = inventory["checked_file_hashes"]
    root = Path(inventory["six_calibration_rhs"][0]["input_json"]).parent
    if not root.is_dir():
        raise ValueError("J1 V5 E1 root is missing")

    # Importing load_packet also verifies the packet's referenced NPZ.  Only q
    # is copied out; e, reference_y, and the old PC output are never returned.
    from .physical_diagnostic_completion import load_packet

    q_inputs: dict[str, np.ndarray] = {}
    packet_facts: dict[str, dict[str, str]] = {}
    for label in CONTROL_LABELS:
        packet_path = root / f"{label}_balanced_input.json"
        packet_hash = raw_hashes.get(str(packet_path))
        if packet_hash is None:
            raise ValueError(f"J1 balanced packet is not in the E1 audit: {label}")
        _checked_path(packet_path, packet_hash)
        packet_descriptor = json.loads(packet_path.read_text())
        npz_path = Path(packet_descriptor["arrays"]["path"])
        npz_hash = raw_hashes.get(str(npz_path))
        if npz_hash is None:
            raise ValueError(f"J1 balanced NPZ is not in the E1 audit: {label}")
        _checked_path(npz_path, npz_hash)
        packet = load_packet(packet_path)
        q = np.asarray(packet["q"])
        if q.ndim != 1 or q.dtype != np.complex128 or not np.isfinite(q).all():
            raise ValueError(f"J1 q packet is not finite complex128: {label}")
        q_inputs[label] = np.array(q, copy=True)
        packet_facts[label] = dict(packet_json=packet_hash, packet_npz=npz_hash,
                                   q_sha256=hashlib.sha256(q.tobytes()).hexdigest())
        del packet

    map_json = root / "native_constraint_map_p6.json"
    map_npz = root / "native_constraint_map_p6.npz"
    _checked_path(map_json, raw_hashes[str(map_json)])
    _checked_path(map_npz, raw_hashes[str(map_npz)])
    p6_map = load_packet(map_json)
    if p6_map["independent_indices"].size != q_inputs[CONTROL_LABELS[0]].size:
        raise ValueError("J1 q and p6 native map dimensions differ")
    return dict(labels=CONTROL_LABELS, q=q_inputs, p6_map=p6_map,
                source_sha=CONTROL_SOURCE_SHA, inventory_sha256=G0_INVENTORY_SHA256,
                e1_audit_sha256=E1_AUDIT_SHA256, packets=packet_facts,
                source_root=str(root))


def _same_map(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key, value in left.items():
        if isinstance(value, np.ndarray):
            if key not in right or not np.array_equal(value, right[key]):
                return False
    return True


def _independent(value: Any, mapping: dict[str, Any]) -> np.ndarray:
    array = np.asarray(value.array if hasattr(value, "array") else value)
    return np.array(array[mapping["independent_indices"]], copy=True)


def _finite_and_constraints(value: np.ndarray, slaves: np.ndarray) -> dict[str, Any]:
    finite = bool(np.isfinite(value).all())
    slave_max = float(np.max(np.abs(value[slaves])) if slaves.size else 0.0)
    return dict(finite=finite, slave_max=slave_max, constraints_passed=finite and slave_max == 0.0)


def _append_json(path: Path, facts: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(_jsonable(facts), allow_nan=False, sort_keys=True) + "\n")
        stream.flush()


class _Appender:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def append(self, name: str, facts: dict[str, Any]) -> None:
        _append_json(self.directory / name, facts)


class _J1Ledger(_Appender):
    """Minimal formal-builder ledger; no outer solve or campaign state."""

    def __init__(self, directory: Path, marker: Callable[[str, dict[str, Any]], None]):
        super().__init__(directory)
        self._marker = marker

    def marker(self, name: str, facts: dict[str, Any]) -> None:
        self._marker(name, facts)

    def record_pc(self, facts: dict[str, Any]) -> None:
        self.append("pc_applies.jsonl", facts)


def _projected_seq2_finite_comparison(trace: Any, rhs: np.ndarray, *,
                                      sample: Callable[[], Any],
                                      save: Callable[[str, dict[str, Any]], None]) -> dict[str, Any]:
    """Compare current seq2, additive, and explicit two-group applies.

    The numerical formulas stay in ``ProjectedSequentialTraceFactorStore``;
    this control supplies one original-mesh RHS and records the three paths.
    The explicit path independently stages ``d0``, complete ``T``, and ``d1``
    so the compact seq2 wrapper is checked rather than compared to itself.
    This is a comparison witness, not a B qualification or an outer/I4 call.
    """

    store = getattr(trace, "joint", None)
    if store is None or not hasattr(store, "apply_additive"):
        raise ValueError("projected seq2 comparison requires the current projected store")
    if not callable(getattr(store, "complete_T", None)):
        raise ValueError("projected seq2 comparison requires the complete current T callback")
    rhs = np.asarray(rhs)
    if rhs.ndim != 1 or rhs.dtype != np.complex128 or not np.isfinite(rhs).all():
        raise ValueError("projected seq2 comparison RHS must be finite complex128")
    rhs_before = rhs.copy()
    coefficients = trace.FH(rhs)
    coefficient_before = [np.array(value, copy=True) for value in coefficients]
    coefficient_sha256 = hashlib.sha256(
        np.concatenate(coefficient_before).tobytes()).hexdigest()

    def delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
        keys = set(after) | set(before)
        return {key: after.get(key, 0) - before.get(key, 0)
                for key in sorted(keys)}

    started = time.perf_counter()
    sequential_trace_before = dict(trace.counts)
    sequential_store_before = dict(store.counts)
    sequential_started = time.perf_counter()
    sequential_coefficients = store.apply(coefficients, sample)
    sequential = trace.F(sequential_coefficients)
    sequential_elapsed = time.perf_counter() - sequential_started
    sequential_store_delta = delta(store.counts, sequential_store_before)
    sequential_trace_delta = delta(trace.counts, sequential_trace_before)
    sequential_facts = dict(store.last_facts)

    additive_trace_before = dict(trace.counts)
    additive_store_before = dict(store.counts)
    additive_started = time.perf_counter()
    additive_coefficients = store.apply_additive(coefficients)
    additive = trace.F(additive_coefficients)
    additive_elapsed = time.perf_counter() - additive_started
    additive_store_delta = delta(store.counts, additive_store_before)
    additive_trace_delta = delta(trace.counts, additive_trace_before)

    explicit_trace_before = dict(trace.counts)
    explicit_store_before = dict(store.counts)
    explicit_started = time.perf_counter()
    explicit_path = store.apply_explicit_sequential(coefficients, sample)
    explicit = trace.F(explicit_path['coefficients'])
    explicit_elapsed = time.perf_counter() - explicit_started
    explicit_store_delta = delta(store.counts, explicit_store_before)
    explicit_trace_delta = delta(trace.counts, explicit_trace_before)
    elapsed = time.perf_counter() - started

    sequential = np.asarray(sequential)
    additive = np.asarray(additive)
    explicit = np.asarray(explicit)
    if (sequential.shape != rhs.shape or additive.shape != rhs.shape or
            explicit.shape != rhs.shape or
            not np.isfinite(sequential).all() or
            not np.isfinite(additive).all() or
            not np.isfinite(explicit).all()):
        raise ValueError("projected seq2 comparison returned a nonfinite or mismatched output")
    input_unchanged = (
        np.array_equal(rhs, rhs_before) and
        all(np.array_equal(value, before)
            for value, before in zip(coefficients, coefficient_before, strict=True)))
    output_difference = float(np.linalg.norm(sequential - additive) /
                              max(np.linalg.norm(sequential) + np.linalg.norm(additive),
                                  np.finfo(float).tiny))
    seq2_explicit_error = float(np.linalg.norm(sequential - explicit) /
                                max(np.linalg.norm(sequential) + np.linalg.norm(explicit),
                                    np.finfo(float).tiny))
    mapping = getattr(trace, 'mapping', {})
    slaves = np.asarray(mapping.get('slaves', np.empty(0, dtype=np.int64)), dtype=np.int64)
    if slaves.size and (np.any(slaves < 0) or np.any(slaves >= rhs.size)):
        raise ValueError('projected seq2 comparison slave map is outside the RHS')
    slave_max = {
        name: (float(np.max(np.abs(value[slaves]))) if slaves.size else 0.0)
        for name, value in (('rhs', rhs), ('seq2', sequential),
                            ('additive', additive), ('explicit', explicit))
    }
    slave_limit = 1e-12
    slave_passed = all(value <= slave_limit for value in slave_max.values())
    finite = bool(np.isfinite(sequential).all() and
                  np.isfinite(additive).all() and np.isfinite(explicit).all())
    gate_failures = []
    if not finite:
        gate_failures.append('nonfinite')
    if not input_unchanged:
        gate_failures.append('input_mutated')
    if not np.isfinite(seq2_explicit_error) or seq2_explicit_error > 1e-10:
        gate_failures.append('seq2_explicit_mismatch')
    if not slave_passed:
        gate_failures.append('slave_constraint')
    summary = dict(
        status=('FINITE_COMPARISON_COMPLETED' if not gate_failures
                else 'FINITE_COMPARISON_REJECTED'),
        scope='one current original-mesh p4 RHS; no outer solve and no I4',
        formula='M0 + M1 - M1*T*M0',
        T_expression='F^H A4 (I-CU A4) F',
        input_unchanged=input_unchanged,
        coefficient_sha256=coefficient_sha256,
        finite=finite,
        slave=dict(max_abs=slave_max, limit=slave_limit, passed=slave_passed),
        sequential_facts=sequential_facts,
        explicit_facts=dict(explicit_path['facts']),
        sequential_store_counts=sequential_store_delta,
        sequential_trace_counts=sequential_trace_delta,
        additive_store_counts=additive_store_delta,
        additive_trace_counts=additive_trace_delta,
        explicit_store_counts=explicit_store_delta,
        explicit_trace_counts=explicit_trace_delta,
        sequential_T_calls=int(sequential_store_delta.get('T_completed', 0)),
        additive_T_calls=int(additive_store_delta.get('T_completed', 0)),
        explicit_T_calls=int(explicit_store_delta.get('T_completed', 0)),
        output_difference_relative=output_difference,
        seq2_explicit_relative=seq2_explicit_error,
        timings_seconds=dict(seq2=sequential_elapsed, additive=additive_elapsed,
                             explicit=explicit_elapsed, total=elapsed),
        gate_failures=gate_failures,
    )
    save('projected_seq2_finite_comparison', dict(
        **summary, rhs=rhs.copy(), sequential=sequential.copy(),
        additive=additive.copy(), explicit=explicit.copy()))
    if gate_failures:
        raise ValueError('projected seq2 finite comparison gate failed: ' + ','.join(gate_failures))
    return summary


def run_j1_controls(
    cfg: Any,
    comm: Any,
    inventory_path: Path,
    directory: Path,
    *,
    sample: Callable[[], Any],
    marker: Callable[[str, dict[str, Any]], None],
    source_sha: dict[str, Any],
    input_path: Path,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Build once and run the two complete J1 control applications."""

    from .physical_diagnosis_worker import save_packet
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.physical_bounded_runtime import (
        audit_bounded_exit,
        bounded_terminal_snapshot,
        build_formal_bounded,
        destroy_bounded_physical_solver,
    )

    directory = Path(directory)
    records = directory / "records"
    records.mkdir(exist_ok=True)
    controls = load_j1_controls(Path(inventory_path))
    ledger = _J1Ledger(directory, marker)
    append = ledger.append
    save = lambda name, facts: save_packet(records, name, facts)
    identity = contract['profile']
    summary: dict[str, Any] = dict(
        schema="task39extra.review-v7-j1-controls.v1",
        status="STARTED",
        source_sha=source_sha,
        input_path=str(Path(input_path)),
        input_sha256=hashlib.sha256(Path(input_path).read_bytes()).hexdigest(),
        profile=identity,
        control_source=controls["source_sha"],
        labels=list(CONTROL_LABELS),
        setup_count=0,
        complete_pc_calls=0,
        I4_calls=0,
        one_apply_contraction_gate="NOT_APPLIED_BY_CONTRACT",
    )
    bundle: dict[str, Any] | None = None
    setup_clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
    try:
        bundle, balanced_apply, policy = build_formal_bounded(
            cfg, comm, contract, sample=sample, ledger=ledger, directory=records,
            identity=identity, save=save, append=append,
            stop_requested=lambda: False, capture_vectors=True,
            retain_inexact_vectors=True)
        current_p6_map = native_map_arrays(
            bundle['levels']['spaces'][6], bundle['levels']['floquets'][6])
        if not _same_map(current_p6_map, controls["p6_map"]):
            raise ValueError("J1 rebuilt p6 native map differs from V5 E1 map")
        p6_indices = current_p6_map["independent_indices"]
        if contract.get('route') == 'PROJECTED_SEQ2_16':
            q_vec = level_vector(bundle['levels'], 6)
            p4_rhs = None
            try:
                q_vec.set(0)
                q_vec.array[current_p6_map['independent_indices']] = controls['q']['A2R160']
                p4_rhs = bundle['actions']['transfers'][(6, 4)].apply_adjoint(q_vec)
                comparison = _projected_seq2_finite_comparison(
                    bundle['trace_assets']['trace'], p4_rhs.array,
                    sample=sample, save=save)
                summary['projected_seq2_finite_comparison'] = comparison
            finally:
                q_vec.destroy()
                if p4_rhs is not None:
                    p4_rhs.destroy()
        summary["setup_count"] = 1
        summary["setup_conservative_seconds"] = setup_clock.update(clock_sample())["budget_seconds"]

        # Freeze the lifetime counters after setup and the one finite B
        # comparison.  The two subsequent BAL_H calls are charged by delta
        # from this snapshot; do not reset the live counters here.
        summary["setup_costs"] = bounded_terminal_snapshot(bundle)
        save("setup_costs", summary["setup_costs"])
        p4_map = bundle["trace_assets"]["mapping"]
        save("j1_input_binding", dict(
            source_sha=controls["source_sha"], inventory_sha256=controls["inventory_sha256"],
            e1_audit_sha256=controls["e1_audit_sha256"], packets=controls["packets"],
            p6_map_json_sha256=_digest(Path(controls["source_root"]) / "native_constraint_map_p6.json"),
            p6_independent_count=int(p6_indices.size),
            note="only q enters PC; e/reference_y/old PC outputs are not inputs"))

        for label in CONTROL_LABELS:
            sample()
            q_vec = level_vector(bundle["levels"], 6)
            z = a6z = s_vec = a6s = g2_recomputed = None
            pc_clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
            try:
                q_vec.set(0)
                q_vec.array[p6_indices] = controls["q"][label]
                q_before = q_vec.array.copy()
                z = balanced_apply(q_vec)
                pc_interval = pc_clock.update(clock_sample())
                captured = dict(bundle["pc"].last_apply_vectors)
                inexact = bundle["inexact_ledger"]
                last = inexact.last
                if last is None or len(last.get("call_vectors", ())) != 2:
                    raise RuntimeError("J1 formal PC did not retain both g1/g2 call vectors")

                # Recompute A6 z and g2 from the saved smoother output.  The
                # recomputed g2 is a correctness check, never another PC call.
                action_clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
                a6z = apply_owned(bundle["fine"]["physical_action"], z)
                a6z_interval = action_clock.update(clock_sample())
                s_vec = level_vector(bundle["levels"], 6)
                s_vec.array[:] = captured["s"]
                a6s = apply_owned(bundle["fine"]["physical_action"], s_vec)
                g2_recomputed = bundle["actions"]["transfers"][(6, 4)].apply_adjoint(a6s)
                saved_g2 = last["call_vectors"][1]["g"]
                g2_relative = float(np.linalg.norm(g2_recomputed.array - saved_g2.array) /
                                    max(float(saved_g2.norm()), np.finfo(float).tiny))

                balance = inexact.audit_last()
                if balance is None:
                    raise RuntimeError("J1 missing final inexact balance audit")
                call_vectors = last["call_vectors"]
                eps1 = call_vectors[0]["eps"]
                eps2 = call_vectors[1]["eps"]
                g1 = call_vectors[0]["g"]
                g2 = call_vectors[1]["g"]
                finite = all(np.isfinite(np.asarray(value.array)).all()
                             for value in (q_vec, z, a6z, g1, g2, eps1, eps2))
                p6_checks = {
                    "q": _finite_and_constraints(q_vec.array, current_p6_map["slaves"]),
                    "z": _finite_and_constraints(z.array, current_p6_map["slaves"]),
                    "A6z": _finite_and_constraints(a6z.array, current_p6_map["slaves"]),
                }
                p4_checks = {
                    name: _finite_and_constraints(value.array, p4_map["slaves"])
                    for name, value in (("g1", g1), ("g2", g2),
                                        ("eps1", eps1), ("eps2", eps2))
                }
                facts = dict(
                    label=label,
                    q=controls["q"][label], z=_independent(z, current_p6_map),
                    A6z=_independent(a6z, current_p6_map),
                    g1=_independent(g1, p4_map), g2=_independent(g2, p4_map),
                    eps1=_independent(eps1, p4_map), eps2=_independent(eps2, p4_map),
                    finite=finite, input_unchanged=bool(np.array_equal(q_vec.array, q_before)),
                    p6_checks=p6_checks, p4_checks=p4_checks,
                    g2_recompute=dict(relative=g2_relative, limit=1e-10,
                                      passed=bool(g2_relative <= 1e-10)),
                    balance=balance,
                    inexact_summary=dict(last["summary"]),
                    pc_cost=dict(pc_interval, A6z_recompute=a6z_interval,
                                 outer=bundle["pc"].last_apply_facts,
                                 lifetime=bounded_terminal_snapshot(bundle)),
                    complete=True,
                )
                gate_failures=[]
                if not finite: gate_failures.append("nonfinite")
                if not facts["input_unchanged"]: gate_failures.append("input_mutated")
                if not all(item["constraints_passed"] for item in p6_checks.values()):
                    gate_failures.append("p6_constraints")
                if not all(item["constraints_passed"] for item in p4_checks.values()):
                    gate_failures.append("p4_constraints")
                if not facts["g2_recompute"]["passed"]: gate_failures.append("g2_recompute")
                if balance.get("closure_relative", float("inf")) > 1e-8:
                    gate_failures.append("inexact_balance")
                facts["gate_failures"] = gate_failures
                save(label + "_j1_control", facts)
                if gate_failures:
                    append("j1_controls.jsonl", dict(label=label, status="FAILED_GATE",
                        failures=gate_failures, seconds=pc_interval["budget_seconds"]))
                    raise ValueError("J1 common correctness gate failed: " + ",".join(gate_failures))
                append("j1_controls.jsonl", dict(label=label, status="COMPLETE",
                    seconds=pc_interval["budget_seconds"], g2_relative=g2_relative,
                    balance=balance, complete_pc_calls=summary["complete_pc_calls"] + 1))
                summary["complete_pc_calls"] += 1
                summary["I4_calls"] += 2
                summary.setdefault("pc_seconds", {})[label] = pc_interval["budget_seconds"]
            finally:
                for value in (g2_recomputed, a6s, s_vec, a6z, z, q_vec):
                    if value is not None:
                        value.destroy()

        summary["j2_gate"] = dict(
            one_complete_pc_le_90=any(value <= J2_PC_LIMIT_SECONDS
                                      for value in summary["pc_seconds"].values()),
            both_pc_over_90=all(value > J2_PC_LIMIT_SECONDS
                                 for value in summary["pc_seconds"].values()),
            exception_only=(J2_EXCEPTION_OUTER_LIMIT, J2_EXCEPTION_SECONDS),
            status=("J2_ADMISSION_OPEN" if any(value <= J2_PC_LIMIT_SECONDS
                                                for value in summary["pc_seconds"].values())
                    else "J2_REVIEW_REQUIRED"),
        )
        summary["bounded_terminal"] = audit_bounded_exit(bundle, _Appender(directory))
        summary["status"] = (
            "B_FINITE_COMPARISON_AND_CONTROLS_COMPLETED"
            if contract.get('route') == 'PROJECTED_SEQ2_16'
            else "J1_CONTROLS_COMPLETED")
        append("j1_controls_summary.json", summary)
        return summary
    except BaseException as exc:
        summary.update(
            status=("B_FINITE_COMPARISON_AND_CONTROLS_FAILED"
                    if contract.get('route') == 'PROJECTED_SEQ2_16'
                    else "J1_CONTROLS_FAILED"),
            exception_type=type(exc).__name__,
                       exception_message=str(exc))
        if bundle is not None:
            try:
                summary["failure_costs"] = bounded_terminal_snapshot(bundle)
            except BaseException as snapshot_error:
                summary["failure_costs_error"] = f"{type(snapshot_error).__name__}: {snapshot_error}"
        append("j1_controls_summary.json", summary)
        raise
    finally:
        if bundle is not None:
            destroy_bounded_physical_solver(bundle)


__all__ = ["CONTROL_LABELS", "G0_INVENTORY", "J1_CONTROL_LIMIT_SECONDS",
           "load_j1_controls", "run_j1_controls"]
