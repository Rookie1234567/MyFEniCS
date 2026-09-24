"""Connect the fixed interface inverse directly to the existing BAL_H action."""

from copy import deepcopy
from dataclasses import dataclass
import time
from typing import Any, Mapping

import numpy as np

from .physical_balanced_coupling import PhysicalBalancedCoupling
from .physical_inexact_balance import InexactBalanceLedger
from .fullspace_physical_intermediate import _copy as _copy_vector


@dataclass(frozen=True)
class P4ResidualRepairPolicy:
    """Bounded, opt-in same-factor refinement for one logical p4 action.

    The ordinary route remains exactly the historical one-solve path.  When
    enabled, the caller supplies the independent native ``A4`` action and
    this solver may apply the already-built condensed factor to the native
    residual at most twice.
    """

    enabled: bool = False
    residual_limit: float = 1.0e-10
    max_extra_solves: int = 0
    exhaustion_policy: str = 'raise'

    def __post_init__(self) -> None:
        if not np.isfinite(self.residual_limit) or self.residual_limit <= 0.0:
            raise ValueError("p4 residual limit must be a positive finite value")
        if int(self.max_extra_solves) != self.max_extra_solves:
            raise ValueError("p4 extra solve count must be integral")
        if not 0 <= int(self.max_extra_solves) <= 2:
            raise ValueError("p4 extra solve count must be between zero and two")
        if not self.enabled and int(self.max_extra_solves) != 0:
            raise ValueError("disabled p4 repair cannot reserve extra solves")
        if self.exhaustion_policy not in ('raise', 'continue_outer_best_finite'):
            raise ValueError("unknown p4 repair exhaustion policy")
        if self.exhaustion_policy == 'continue_outer_best_finite' and (
            not self.enabled or int(self.max_extra_solves) != 2
        ):
            raise ValueError(
                "continue_outer_best_finite requires enabled repair and two extra solves"
            )


class P4ResidualRepairRejected(RuntimeError):
    """Raised when an enabled bounded repair still misses the native gate."""

    def __init__(self, facts: Mapping[str, Any]):
        self.facts = dict(facts)
        super().__init__(f"bounded p4 residual repair failed: {self.facts}")


def _repair_policy(value: P4ResidualRepairPolicy | Mapping[str, Any] | None) -> P4ResidualRepairPolicy:
    if value is None:
        return P4ResidualRepairPolicy()
    if isinstance(value, P4ResidualRepairPolicy):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("p4 repair policy must be a P4ResidualRepairPolicy or mapping")
    return P4ResidualRepairPolicy(
        enabled=bool(value.get("enabled", False)),
        residual_limit=float(value.get("residual_limit", 1.0e-10)),
        max_extra_solves=int(value.get("max_extra_solves", 0)),
        exhaustion_policy=str(value.get("exhaustion_policy", 'raise')),
    )


def _array_view(value: Any) -> np.ndarray:
    getter = getattr(value, "getArray", None)
    if callable(getter):
        try:
            array = getter(readonly=True)
        except TypeError:
            # Lightweight fixtures may expose the older no-keyword API.  Keep
            # the view read-only even on that compatibility path.
            array = getter()
    else:
        array = getattr(value, "array", None)
        if array is None:
            raise TypeError("repair vector does not expose an array")
    view = np.asarray(array).view()
    view.setflags(write=False)
    return view


def _array_copy(value: Any) -> np.ndarray:
    return _array_view(value).copy()


class InterfaceBalancedCoupling:
    """Borrow the operators and record both actual inexact p4 residuals.

    All operator callbacks and transfer methods return owned PETSc vectors.
    ``transfer`` is the qualified slave-zero algebraic P/P^H adapter.  No
    reference, initial guess, old I4 wrapper, or residual-minimization step
    enters this composition.
    """

    def __init__(self, fine_action, p4_action, transfer, fint, h6, *, save,
                 checkpoint=lambda: None, capture_vectors=False,
                 repair_policy: P4ResidualRepairPolicy | Mapping[str, Any] | None = None,
                 repair_vector_sink=None, repair_vector_capture=None,
                 logical_apply_hook=None,
                 p4_action_implementation='native_ffcx_full_A4',
                 p4_action_oracle='native_ffcx_full_A4'):
        self.p4_action, self.transfer, self.fint = p4_action, transfer, fint
        self.p4_action_implementation = str(p4_action_implementation)
        self.p4_action_oracle = str(p4_action_oracle)
        self.coarse_calls = []
        self.native_A4_count = 0
        self.native_A4_seconds = 0.0
        self.successful_logical_apply_count = 0
        self._pc_apply_sequence = 0
        self._logical_call_sequence = 0
        self.repair_policy = _repair_policy(repair_policy)
        self.repair_vector_sink = repair_vector_sink
        self.repair_vector_capture = repair_vector_capture
        self.logical_apply_hook = logical_apply_hook
        self.capture_vectors = bool(capture_vectors)
        self._last_repair_vectors = []
        self._destroyed = False
        self.ledger = InexactBalanceLedger(
            fine_action, transfer.apply_adjoint, save=save,
            checkpoint=checkpoint, every=32, mode='BAL_H',
            retain_call_vectors=capture_vectors)
        self.balanced = PhysicalBalancedCoupling(
            fine_action, self._coarse, h6, transfer.apply_adjoint,
            route='BAL_H', checkpoint=checkpoint, inexact_ledger=self.ledger,
            capture_vectors=capture_vectors)

    def _port_state(self):
        value = getattr(self.fint, 'last_port_solution', None)
        if value is None:
            return None
        array = np.asarray(value, dtype=np.complex128)
        if array.ndim != 1:
            raise ValueError('p4 port state must be a one-dimensional array')
        return array.copy()

    def _set_port_state(self, value):
        if value is None:
            return
        setattr(
            self.fint,
            'last_port_solution',
            np.asarray(value, dtype=np.complex128).copy(),
        )

    def _save_repair_evidence(self, name, facts):
        if self.repair_vector_sink is not None:
            self.repair_vector_sink(facts)
        else:
            self.ledger.save(name, facts)

    def _reject_nonfinite(self, *, logical_call, phase, g, correction=None,
                          port=None, applied=None, residual=None, interface=None,
                          delta=None):
        facts = {
            'schema': 'task039extra.v24.p4-nonfinite-evidence.v1',
            'logical_call': int(logical_call),
            'logical_call_sequence': int(self._logical_call_sequence),
            'pc_apply_sequence': int(self._pc_apply_sequence),
            'phase': str(phase),
            'g': _array_copy(g),
            'correction': None if correction is None else _array_copy(correction),
            'alpha': None if port is None else np.asarray(port).copy(),
            'native_applied': None if applied is None else _array_copy(applied),
            'native_A4_residual': None if residual is None else _array_copy(residual),
            'delta_correction': None if delta is None else _array_copy(delta),
            'interface_facts': deepcopy(interface) if interface is not None else None,
        }
        self._save_repair_evidence(
            f'p4_nonfinite_{logical_call}_{phase}', facts
        )
        raise FloatingPointError(
            f'non-finite p4 repair state before native/repair: {phase}'
        )

    def _repair_snapshot(self, *, logical_call, phase, g, correction, port,
                         applied, residual, relative, interface):
        if (
            self.repair_vector_sink is None
            and not self.capture_vectors
            and self.repair_vector_capture is None
        ):
            return
        scalar = {
            'schema': 'task039extra.v24.p4-repair-vector.v1',
            'logical_call': int(logical_call),
            'logical_call_sequence': int(self._logical_call_sequence),
            'pc_apply_sequence': int(self._pc_apply_sequence),
            'phase': str(phase),
            'g_norm': float(np.linalg.norm(_array_view(g))),
            'correction_norm': float(np.linalg.norm(_array_view(correction))),
            'alpha_norm': None if port is None else float(np.linalg.norm(port)),
            'native_applied_norm': float(np.linalg.norm(_array_view(applied))),
            'native_A4_residual_norm': float(np.linalg.norm(_array_view(residual))),
            'native_A4_relative_residual': float(relative),
            'interface_facts': deepcopy(interface),
        }
        soft_return = (
            self.repair_policy.exhaustion_policy == 'continue_outer_best_finite'
        )
        capture_selected = False
        if self.repair_vector_capture is not None:
            capture_selected = bool(self.repair_vector_capture(scalar))
        # A normal formal call only emits scalar accounting.  The first raw
        # vector becomes durable only when it actually crosses the native
        # threshold; correction snapshots are necessarily full packets.
        full_packet = self.capture_vectors or capture_selected or (
            self.repair_vector_sink is not None
            and (
                phase != 'raw'
                or not np.isfinite(relative)
                or relative > self.repair_policy.residual_limit
            )
        )
        if soft_return and phase not in ('raw', 'selected'):
            full_packet = False
            capture_selected = False
        if self.repair_vector_sink is not None:
            payload = dict(scalar)
            if full_packet:
                payload.update(
                    g=_array_copy(g),
                    correction=_array_copy(correction),
                    alpha=None if port is None else np.asarray(port).copy(),
                    native_applied=_array_copy(applied),
                    native_A4_residual=_array_copy(residual),
                )
            self.repair_vector_sink(payload)
        if (self.capture_vectors or capture_selected) and (
            not soft_return or phase in ('raw', 'selected')
        ):
            self._last_repair_vectors.append({
                **scalar,
                'g': _array_copy(g),
                'correction': _array_copy(correction),
                'alpha': None if port is None else np.asarray(port).copy(),
                'native_applied': _array_copy(applied),
                'native_A4_residual': _array_copy(residual),
            })

    @staticmethod
    def _factor_solve_delta(interface):
        value = interface.get('factor_solve_call_delta')
        if value is None:
            value = interface.get('factor_solve_delta')
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _coarse(self, fine_rhs):
        g = self.transfer.apply_adjoint(fine_rhs)
        correction = applied = residual = None
        started = time.perf_counter()
        logical_call = len(self.coarse_calls) + 1
        self._logical_call_sequence += 1
        logical_call_sequence = self._logical_call_sequence
        interfaces = []
        repair_records = []
        best_state = None
        best_snapshot_peak_local_bytes = 0
        port_total = None
        native_actions = 0
        native_A4_seconds = 0.0
        extra_solves = 0
        try:
            begin_logical = getattr(self.fint, 'begin_logical_apply', None)
            if callable(begin_logical):
                begin_logical()
            if not np.isfinite(_array_view(g)).all():
                self._reject_nonfinite(
                    logical_call=logical_call, phase='rhs', g=g
                )
            correction, interface = self.fint.apply_with_facts(g)
            interfaces.append(deepcopy(interface))
            port_total = self._port_state()
            if not np.isfinite(_array_view(correction)).all():
                self._reject_nonfinite(
                    logical_call=logical_call, phase='solution', g=g,
                    correction=correction, port=port_total, interface=interface,
                )
            if port_total is not None and not np.isfinite(port_total).all():
                self._reject_nonfinite(
                    logical_call=logical_call, phase='alpha', g=g,
                    correction=correction, port=port_total, interface=interface,
                )
            self.native_A4_count += 1
            native_actions += 1
            native_started = time.perf_counter()
            try:
                applied = self.p4_action(correction)
            finally:
                elapsed = time.perf_counter() - native_started
                native_A4_seconds += elapsed
                self.native_A4_seconds += elapsed
            if not np.isfinite(_array_view(applied)).all():
                self._reject_nonfinite(
                    logical_call=logical_call, phase='native_applied', g=g,
                    correction=correction, port=port_total, applied=applied,
                    interface=interface,
                )
            residual = g.copy()
            residual.axpy(-1., applied)
            if not np.isfinite(_array_view(residual)).all():
                self._reject_nonfinite(
                    logical_call=logical_call, phase='native_residual', g=g,
                    correction=correction, port=port_total, applied=applied,
                    residual=residual, interface=interface,
                )
            rhs_norm = float(g.norm())
            residual_norm = float(residual.norm())
            denominator = max(rhs_norm, np.finfo(float).tiny)
            relative = residual_norm / denominator
            repair_records.append({
                'index': 0,
                'phase': 'raw',
                'relative_residual': relative,
                'residual_norm': residual_norm,
                'rhs_norm': rhs_norm,
                'factor_solve_call_delta': self._factor_solve_delta(interface),
            })
            soft_return = (
                self.repair_policy.exhaustion_policy == 'continue_outer_best_finite'
            )
            if soft_return and np.isfinite(relative) and relative > self.repair_policy.residual_limit:
                best_state = {
                    'attempt': 0,
                    'relative': relative,
                    'correction': _copy_vector(correction),
                    'applied': _copy_vector(applied),
                    'residual': _copy_vector(residual),
                    'port': None if port_total is None else port_total.copy(),
                    'interface': deepcopy(interface),
                }
                best_snapshot_peak_local_bytes = sum(
                    _array_view(best_state[key]).nbytes
                    for key in ('correction', 'applied', 'residual')
                ) + (0 if best_state['port'] is None else best_state['port'].nbytes)
            self._repair_snapshot(
                logical_call=logical_call, phase='raw', g=g,
                correction=correction, port=port_total, applied=applied,
                residual=residual, relative=relative, interface=interface,
            )

            policy = self.repair_policy
            while policy.enabled and relative > policy.residual_limit:
                if not np.isfinite(relative):
                    break
                if extra_solves >= policy.max_extra_solves:
                    break
                repair_started = time.perf_counter()
                delta = delta_applied = next_residual = None
                try:
                    delta, delta_interface = self.fint.apply_with_facts(residual)
                    interfaces.append(deepcopy(delta_interface))
                    extra_solves += 1
                    delta_port = self._port_state()
                    if not np.isfinite(_array_view(delta)).all():
                        self._reject_nonfinite(
                            logical_call=logical_call,
                            phase=f'correction_{extra_solves}_solution',
                            g=g, correction=correction, port=port_total,
                            residual=residual, interface=delta_interface,
                            delta=delta,
                        )
                    if delta_port is not None and not np.isfinite(delta_port).all():
                        self._reject_nonfinite(
                            logical_call=logical_call,
                            phase=f'correction_{extra_solves}_alpha',
                            g=g, correction=correction, port=port_total,
                            residual=residual, interface=delta_interface,
                            delta=delta,
                        )
                    correction.axpy(1., delta)
                    if delta_port is not None:
                        if port_total is None:
                            port_total = np.zeros_like(delta_port)
                        if port_total.shape != delta_port.shape:
                            raise ValueError('p4 correction changed the port-state shape')
                        port_total += delta_port
                        self._set_port_state(port_total)
                    # Reapply the independent native operator to the total
                    # correction.  Applying A4(delta) and adding it here
                    # would hide a native-action omission and would leave the
                    # public native count wrong.
                    self.native_A4_count += 1
                    native_actions += 1
                    native_started = time.perf_counter()
                    try:
                        delta_applied = self.p4_action(correction)
                    finally:
                        elapsed = time.perf_counter() - native_started
                        native_A4_seconds += elapsed
                        self.native_A4_seconds += elapsed
                    if not np.isfinite(_array_view(delta_applied)).all():
                        self._reject_nonfinite(
                            logical_call=logical_call,
                            phase=f'correction_{extra_solves}_native_applied',
                            g=g, correction=correction, port=port_total,
                            applied=delta_applied, residual=residual,
                            interface=delta_interface, delta=delta,
                        )
                    next_residual = g.copy()
                    next_residual.axpy(-1., delta_applied)
                    if not np.isfinite(_array_view(next_residual)).all():
                        self._reject_nonfinite(
                            logical_call=logical_call,
                            phase=f'correction_{extra_solves}_native_residual',
                            g=g, correction=correction, port=port_total,
                            applied=delta_applied, residual=next_residual,
                            interface=delta_interface, delta=delta,
                        )
                    next_norm = float(next_residual.norm())
                    relative = next_norm / denominator
                    repair_records.append({
                        'index': extra_solves,
                        'phase': 'correction',
                        'relative_residual': relative,
                        'residual_norm': next_norm,
                        'rhs_norm': rhs_norm,
                        'factor_solve_call_delta': self._factor_solve_delta(delta_interface),
                        'elapsed_seconds': time.perf_counter() - repair_started,
                    })
                    self._repair_snapshot(
                        logical_call=logical_call,
                        phase=f'correction_{extra_solves}',
                        g=g, correction=correction, port=port_total,
                        applied=delta_applied, residual=next_residual,
                        relative=relative, interface=delta_interface,
                    )
                    if soft_return and np.isfinite(relative) and relative > policy.residual_limit and (
                        best_state is None or relative < best_state['relative']
                    ):
                        if best_state is not None:
                            for key in ('correction', 'applied', 'residual'):
                                best_state[key].destroy()
                        best_state = {
                            'attempt': int(extra_solves),
                            'relative': relative,
                            'correction': _copy_vector(correction),
                            'applied': _copy_vector(delta_applied),
                            'residual': _copy_vector(next_residual),
                            'port': None if port_total is None else port_total.copy(),
                            'interface': deepcopy(delta_interface),
                        }
                        best_snapshot_peak_local_bytes = max(
                            best_snapshot_peak_local_bytes,
                            sum(
                                _array_view(best_state[key]).nbytes
                                for key in ('correction', 'applied', 'residual')
                            ) + (0 if best_state['port'] is None else best_state['port'].nbytes),
                        )
                    applied.destroy()
                    residual.destroy()
                    applied, residual = delta_applied, next_residual
                    delta_applied = next_residual = None
                finally:
                    if delta_applied is not None:
                        delta_applied.destroy()
                    if next_residual is not None:
                        next_residual.destroy()
                    if delta is not None:
                        delta.destroy()

            if soft_return and np.isfinite(relative) and relative <= policy.residual_limit:
                if best_state is not None:
                    for key in ('correction', 'applied', 'residual'):
                        best_state[key].destroy()
                    best_state = None
            last_attempt_relative = float(relative)
            selected_attempt = len(repair_records) - 1
            minimum_relative = min(
                float(item['relative_residual']) for item in repair_records
            )
            unmet_continue = bool(
                soft_return
                and np.isfinite(relative)
                and relative > policy.residual_limit
            )
            if unmet_continue:
                if best_state is None:
                    raise FloatingPointError(
                        'p4 repair exhausted without a finite complete state'
                    )
                for value in (correction, applied, residual):
                    value.destroy()
                selected_attempt = int(best_state['attempt'])
                relative = float(best_state['relative'])
                correction, applied, residual = (
                    best_state['correction'],
                    best_state['applied'],
                    best_state['residual'],
                )
                best_state['correction'] = None
                best_state['applied'] = None
                best_state['residual'] = None
                port_total = best_state['port']
                self._set_port_state(port_total)
            status = (
                'NONFINITE_REJECT' if not np.isfinite(relative) else
                'COARSE_TARGET_UNMET_CONTINUE' if unmet_continue else
                ('REFINED_TARGET_MET' if extra_solves else 'NOT_NEEDED')
            ) if soft_return else (
                'NOT_NEEDED' if not policy.enabled or extra_solves == 0 and relative <= policy.residual_limit else (
                    'PASS' if relative <= policy.residual_limit else 'BOUNDED_REPAIR_EXHAUSTED'
                )
            )
            repair = {
                'schema': 'task039extra.v24.bounded-p4-repair.v1',
                'a4_action_implementation': self.p4_action_implementation,
                'a4_action_oracle': self.p4_action_oracle,
                'enabled': bool(policy.enabled),
                'residual_limit': float(policy.residual_limit),
                'max_extra_solves': int(policy.max_extra_solves),
                'initial_relative_residual': float(repair_records[0]['relative_residual']),
                'final_relative_residual': float(relative),
                'extra_solve_count': int(extra_solves),
                'logical_p4_apply_count': 1,
                'actual_mat_solve_count': None,
                'native_A4_action_count': int(native_actions),
                'records': repair_records,
                'status': status,
                'elapsed_seconds': time.perf_counter() - started,
            }
            if soft_return:
                repair.update(
                    selected_attempt=int(selected_attempt),
                    last_attempt_rho=last_attempt_relative,
                    returned_rho=float(relative),
                    min_rho=float(minimum_relative),
                    selection_policy='minimum_rho_tie_earliest',
                    best_snapshot_peak_vector_count=(
                        3 if best_snapshot_peak_local_bytes else 0
                    ),
                    best_snapshot_peak_local_bytes=int(best_snapshot_peak_local_bytes),
                    best_snapshot_lifetime=(
                        'one bounded snapshot; transferred to the returned state '
                        'when selected, otherwise released after a passing refinement'
                        if unmet_continue or best_snapshot_peak_local_bytes else
                        'not allocated because the raw residual met the target'
                    ),
                    selected_evidence_copy_local_bytes=int(
                        _array_view(g).nbytes
                        + _array_view(correction).nbytes
                        + _array_view(applied).nbytes
                        + _array_view(residual).nbytes
                        + (0 if port_total is None else port_total.nbytes)
                    ) if unmet_continue else 0,
                )
            repair.update(
                logical_call_sequence=int(logical_call_sequence),
                pc_apply_sequence=int(self._pc_apply_sequence),
            )
            solve_deltas = [self._factor_solve_delta(item) for item in interfaces]
            repair['actual_mat_solve_count'] = (
                int(sum(solve_deltas))
                if all(value is not None for value in solve_deltas)
                else None
            )
            if policy.enabled and not unmet_continue and (
                not np.isfinite(relative) or relative > policy.residual_limit
            ):
                self._save_repair_evidence(f'p4_repair_failure_{logical_call}', {
                    'schema': 'task039extra.v24.p4-repair-failure.v1',
                    'logical_call': int(logical_call),
                    'logical_call_sequence': int(logical_call_sequence),
                    'pc_apply_sequence': int(self._pc_apply_sequence),
                    'repair': repair,
                })
                raise P4ResidualRepairRejected(repair)

            if unmet_continue:
                selected_interface = best_state['interface']
                selected_phase = 'raw' if selected_attempt == 0 else f'correction_{selected_attempt}'
                selected_scalar = {
                    'schema': 'task039extra.v27.p4-selected-best-finite.v1',
                    'logical_call': int(logical_call),
                    'logical_call_sequence': int(logical_call_sequence),
                    'pc_apply_sequence': int(self._pc_apply_sequence),
                    'phase': 'selected',
                    'source_phase': selected_phase,
                    'selected_attempt': int(selected_attempt),
                    'last_attempt_rho': float(last_attempt_relative),
                    'returned_rho': float(relative),
                    'min_rho': float(minimum_relative),
                    'interface_facts': deepcopy(selected_interface),
                }
                if self.repair_vector_sink is not None:
                    self.repair_vector_sink({
                        **selected_scalar,
                        'g': _array_copy(g),
                        'correction': _array_copy(correction),
                        'alpha': None if port_total is None else port_total.copy(),
                        'native_applied': _array_copy(applied),
                        'native_A4_residual': _array_copy(residual),
                    })
                capture_selected = bool(
                    self.repair_vector_capture is not None
                    and self.repair_vector_capture(selected_scalar)
                )
                if self.capture_vectors or capture_selected:
                    self._last_repair_vectors.append({
                        **selected_scalar,
                        'g': _array_copy(g),
                        'correction': _array_copy(correction),
                        'alpha': None if port_total is None else np.asarray(port_total).copy(),
                        'native_applied': _array_copy(applied),
                        'native_A4_residual': _array_copy(residual),
                    })

            interface_facts = deepcopy(interfaces[0])
            interface_facts['logical_p4_apply_count'] = 1
            interface_facts['factor_solve_call_delta_total'] = repair['actual_mat_solve_count']
            interface_facts['repair_call_facts'] = interfaces[1:]
            facts = {
                'interface_facts': interface_facts,
                'rhs_norm': rhs_norm,
                'native_A4_residual_norm': float(residual.norm()),
                'native_A4_relative_residual': float(relative),
                'a4_action_implementation': self.p4_action_implementation,
                'a4_action_oracle': self.p4_action_oracle,
                'fint_and_native_A4_seconds': time.perf_counter() - started,
                'native_A4_actions': int(native_actions),
                'native_A4_seconds': float(native_A4_seconds),
                'p4_logical_apply_count': 1,
                'p4_mat_solve_count': repair['actual_mat_solve_count'],
                'repair': repair,
            }
            self.ledger.record(g, applied, residual, facts)
            output = self.transfer.apply_primal(correction)
            complete_logical = getattr(self.fint, 'complete_logical_apply', None)
            if callable(complete_logical):
                complete_logical()
            self.successful_logical_apply_count += 1
            facts['p4_logical_apply_cumulative_count'] = int(
                self.successful_logical_apply_count
            )
            facts['p4_logical_apply_sequence'] = int(logical_call_sequence)
            facts['p4_pc_apply_sequence'] = int(self._pc_apply_sequence)
            self.coarse_calls.append(facts)
            if self.logical_apply_hook is not None:
                try:
                    self.logical_apply_hook(
                        facts,
                        tuple(self._last_repair_vectors),
                    )
                except BaseException:
                    output.destroy()
                    raise
            return output
        finally:
            for vector in (residual, applied, correction, g):
                if vector is not None:
                    vector.destroy()
            if best_state is not None:
                for key in ('correction', 'applied', 'residual'):
                    if best_state[key] is not None:
                        best_state[key].destroy()

    def apply(self, source):
        self.coarse_calls = []
        self._last_repair_vectors = []
        self._pc_apply_sequence += 1
        if not np.isfinite(_array_view(source)).all():
            self._save_repair_evidence(
                'p4_nonfinite_source',
                {
                    'schema': 'task039extra.v24.p4-nonfinite-evidence.v1',
                    'logical_call': 1,
                    'logical_call_sequence': int(self._logical_call_sequence + 1),
                    'pc_apply_sequence': int(self._pc_apply_sequence),
                    'phase': 'source_rhs',
                    'g': _array_copy(source),
                },
            )
            raise FloatingPointError(
                'non-finite p4 repair state before native/repair: source_rhs'
            )
        return self.balanced.apply(source)

    @property
    def apply_count(self):
        return self.balanced.apply_count

    @property
    def a4_check_action_count(self):
        """Complete A4 applications; ``native_A4_count`` is the legacy alias."""
        return self.native_A4_count

    @property
    def a4_check_seconds(self):
        """Time spent by the selected complete A4 implementation."""
        return self.native_A4_seconds

    @property
    def last_apply_facts(self):
        return self.balanced.last_apply_facts

    @property
    def last_apply_vectors(self):
        vectors = dict(self.balanced.last_apply_vectors)
        if self._last_repair_vectors:
            vectors['p4_repair_calls'] = tuple(self._last_repair_vectors)
        return vectors

    def destroy(self):
        ledger = self.ledger
        if ledger is not None:
            ledger.destroy()
        # These compact scalar facts remain useful after cleanup, especially
        # when a second coarse call or a resource boundary interrupts the PC.
        # They own no PETSc vectors or large arrays.
        balanced = self.balanced
        if balanced is not None:
            balanced.last_apply_vectors.clear()
            # The callbacks are bound methods/closures over the full p6/p4
            # graph.  Clearing them is part of destruction, not an optional
            # memory-ledger optimization: otherwise a released BAL_H object
            # can remain reachable through the balanced coupling.
            balanced.A = None
            balanced.C = None
            balanced.S = None
            balanced.PH = None
            balanced.checkpoint = None
            balanced.inexact_ledger = None
        # Keep the small scalar balanced shell so the established
        # ``apply_count``/``last_apply_facts`` accessors remain readable after
        # cleanup.  Its numerical callbacks and ledger have been severed.
        self._destroyed = True
        self.ledger = None
        self.p4_action = None
        self.p4_action_implementation = None
        self.p4_action_oracle = None
        self.transfer = None
        self.fint = None
        self.repair_vector_sink = None
        self.repair_vector_capture = None
        self.logical_apply_hook = None
        self._last_repair_vectors = []


__all__ = [
    'InterfaceBalancedCoupling',
    'P4ResidualRepairPolicy',
    'P4ResidualRepairRejected',
]
