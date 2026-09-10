"""Small V7 admission policy around the shared historical I4 implementation."""

from __future__ import annotations

from typing import Any, Callable

import numpy as np

from .physical_recursive_coarse import solve_physical_i4


class BoundedI4CostBlocked(RuntimeError):
    """Three hard-cost misses (or two no-direction calls) stop one route."""

    def __init__(self, facts: dict[str, Any]):
        self.facts = facts
        super().__init__(f"V7 I4 cost blocked: {facts}")


class BoundedI4Admission:
    """Run independent zero-start V7 RHS calls and retain scalar cost facts.

    The KSP and explicit residual implementation remains
    :func:`solve_physical_i4`; this object only supplies the V7 policy values,
    the shared outer stop callback, and the two consecutive-cost counters.
    """

    def __init__(
        self,
        action: Any,
        pc: Any,
        *,
        sample: Callable[[], Any],
        save: Callable[[str, dict[str, Any]], None],
        stop_requested: Callable[[], bool],
        residual_action: Any | None = None,
        macro_policy: bool = False,
    ) -> None:
        self.action = action
        self.pc = pc
        self.sample = sample
        self.save = save
        self.stop_requested = stop_requested
        self.residual_action = residual_action
        self.macro_policy = bool(macro_policy)
        self.calls = 0
        self.no_direction_streak = 0
        self.timeout_streak = 0
        self.last_facts: dict[str, Any] = {}
        # Keep only scalar summaries of the latest few calls.  Full vectors
        # are owned by the caller for one call and are never accumulated here.
        self.recent = []

    @staticmethod
    def _scalar_facts(facts: dict[str, Any]) -> dict[str, Any]:
        keys = (
            'status', 'target', 'final_true_residual', 'rhs_norm', 'iterations',
            'reason', 'seconds', 'actual_elapsed_seconds', 'requested_safe_return',
            'timeout_exceeded', 'stop_reason', 'legal_direction_count',
            'A4_matvec', 'B4_calls', 'explicit_A4', 'restart', 'max_it',
        )
        return {key: facts[key] for key in keys if key in facts}

    def __call__(self, rhs: Any) -> dict[str, Any]:
        self.calls += 1
        try:
            result = solve_physical_i4(
                rhs,
                self.action,
                self.pc,
                target=1e-4,
                sample=self.sample,
                save=self.save,
                stop_requested=self.stop_requested,
                residual_action=self.residual_action,
                max_it=4 if self.macro_policy else 16,
                restart=4 if self.macro_policy else 16,
                soft_seconds=25,
                hard_seconds=30,
                v7_policy=not self.macro_policy,
                macro_policy=self.macro_policy,
            )
        except RuntimeError as exc:
            if not getattr(exc, 'bounded_i4_no_legal_direction', False):
                raise
            self.no_direction_streak += 1
            self.last_facts = dict(status='INNER_BREAKDOWN_NO_LEGAL_DIRECTION',
                call=self.calls, no_direction_streak=self.no_direction_streak)
            if self.no_direction_streak >= 2:
                raise BoundedI4CostBlocked(dict(status='INNER_COST_BLOCKED',
                    reason='two_consecutive_no_legal_directions', call=self.calls,
                    no_direction_streak=self.no_direction_streak)) from exc
            raise

        facts = result['facts']
        self.last_facts = self._scalar_facts(facts)
        summary = {key: facts.get(key) for key in (
            'status', 'iterations', 'seconds', 'actual_elapsed_seconds',
            'final_true_residual', 'legal_direction_count', 'timeout_exceeded',
            'stop_reason')}
        summary['call'] = self.calls
        self.recent.append(summary)
        del self.recent[:-3]

        # Zero RHS is legal and separate; importantly it does not erase a
        # previously observed nonzero cost streak.
        if facts.get('status') == 'INNER_ZERO_RHS':
            return result
        self.no_direction_streak = (
            self.no_direction_streak + 1
            if facts.get('legal_direction_count', 0) == 0
            else 0
        )
        self.timeout_streak = (
            self.timeout_streak + 1
            if bool(facts.get('timeout_exceeded'))
            else 0
        )
        if self.no_direction_streak >= 2 or self.timeout_streak >= 3:
            reason = (
                'two_consecutive_no_legal_directions'
                if self.no_direction_streak >= 2
                else 'three_consecutive_timeouts'
            )
            self.save('bounded_i4_cost_blocked', dict(
                rhs=np.array(rhs.array, copy=True),
                solution=np.array(result['solution'].array, copy=True),
                applied=np.array(result['applied'].array, copy=True),
                residual=np.array(result['residual'].array, copy=True),
                facts=facts, recent=list(self.recent), reason=reason,
            ))
            for key in ('solution', 'applied', 'residual'):
                result[key].destroy()
                result[key] = None
            raise BoundedI4CostBlocked(dict(status='INNER_COST_BLOCKED', reason=reason,
                call=self.calls, no_direction_streak=self.no_direction_streak,
                timeout_streak=self.timeout_streak, recent=list(self.recent)))
        return result

    def snapshot(self) -> dict[str, Any]:
        return dict(calls=self.calls, no_direction_streak=self.no_direction_streak,
            timeout_streak=self.timeout_streak, recent=list(self.recent),
            last=dict(self.last_facts))


class RecycledI4Admission:
    """PETSc bridge for the opt-in V8/V9 one-round recycled I4 kernel.

    The bridge creates one private PETSc prototype and converts only the
    callback vectors needed by the array kernel.  It deliberately keeps the
    V7 :class:`BoundedI4Admission` untouched; old profiles therefore continue
    to use the historical PETSc KSP path and its existing streak semantics.
    """

    def __init__(
        self,
        action: Any,
        pc: Any,
        *,
        model_identity: Any,
        sample: Callable[[], Any],
        save: Callable[[str, dict[str, Any]], None],
        stop_requested: Callable[[], bool],
        residual_action: Any | None = None,
        constraint_check: Callable[[np.ndarray], Any] | None = None,
        q_constraint_check: Callable[[np.ndarray], Any] | None = None,
        u_constraint_check: Callable[[np.ndarray], Any] | None = None,
        independent_indices: np.ndarray | None = None,
        pool: Any | None = None,
        policy: str | None = None,
    ) -> None:
        from .physical_recycled_i4 import (
            BoundedGCROTI4,
            V8_FIXED_M8_RECYCLE8,
        )

        self.action = action
        self.pc = pc
        self.residual_action = action if residual_action is None else residual_action
        self.sample = sample
        self.save = save
        self.stop_requested = stop_requested
        self.policy = V8_FIXED_M8_RECYCLE8 if policy is None else str(policy)
        self.constraint_check = constraint_check
        self.q_constraint_check = q_constraint_check
        self.u_constraint_check = u_constraint_check
        self._requested_independent_indices = (None if independent_indices is None else
                                               np.asarray(independent_indices,
                                                          dtype=np.int64).copy())
        self._independent_indices: np.ndarray | None = None
        self._excluded_indices: np.ndarray | None = None
        self.calls = 0
        self.no_direction_streak = 0
        self.timeout_streak = 0
        self.last_facts: dict[str, Any] = {}
        self.recent: list[dict[str, Any]] = []
        self._prototype: Any | None = None
        self._local_size: int | None = None
        self._global_size: int | None = None
        self.destroyed = False
        self.engine = BoundedGCROTI4(
            self._array_action,
            self._array_pc,
            model_identity=model_identity,
            validation_action=self._array_residual_action,
            constraint_check=constraint_check,
            q_constraint_check=q_constraint_check,
            u_constraint_check=u_constraint_check,
            sample=sample,
            stop_requested=stop_requested,
            pool=pool,
            policy=self.policy,
        )

    @staticmethod
    def _scalar_facts(facts: dict[str, Any]) -> dict[str, Any]:
        keys = (
            'status', 'target', 'final_true_residual', 'rhs_norm', 'iterations',
            'reason', 'seconds', 'actual_elapsed_seconds', 'requested_safe_return',
            'timeout_exceeded', 'stop_reason', 'legal_direction_count',
            'A4_matvec', 'B4_calls', 'explicit_A4', 'pool_before', 'pool_after',
            'pool_update', 'completed_new_arnoldi_directions',
            'attempted_new_arnoldi_directions',
            'policy', 'effective_pool_rank', 'm_call',
            'requested_new_B4', 'completed_new_B4', 'discarded_new_B4',
            'requested_new_arnoldi_directions', 'actual_arnoldi_length',
            'discarded_new_arnoldi_directions', 'rejected_new_B4_callbacks',
            'work_policy_violation', 'implementation_blocked',
        )
        return {key: facts[key] for key in keys if key in facts}

    def _ensure_prototype(self, rhs: Any) -> None:
        if rhs.getComm().getSize() != 1:
            raise RuntimeError('V8 recycled I4 is qualified for MPI1 only')
        array = np.asarray(rhs.array)
        if array.ndim != 1 or array.dtype != np.dtype(np.complex128):
            raise RuntimeError('V8 recycled I4 requires a complex128 PETSc Vec')
        local_size = int(rhs.getLocalSize())
        global_size = int(rhs.getSize())
        if array.shape != (local_size,):
            raise RuntimeError('V8 PETSc Vec storage does not match its local size')
        if self._requested_independent_indices is None:
            indices = np.arange(local_size, dtype=np.int64)
        else:
            indices = self._requested_independent_indices
            if (indices.ndim != 1 or len(indices) == 0 or
                    np.any(indices < 0) or np.any(indices >= local_size) or
                    len(np.unique(indices)) != len(indices)):
                raise RuntimeError('V8 independent p4 index map is invalid')
        if self._prototype is None:
            self._independent_indices = indices.copy()
            self._excluded_indices = np.setdiff1d(
                np.arange(local_size, dtype=np.int64), indices, assume_unique=True)
            self._prototype = rhs.duplicate()
            self._prototype.set(0)
            self._local_size = local_size
            self._global_size = global_size
        elif (local_size != self._local_size or global_size != self._global_size or
              not np.array_equal(indices, self._independent_indices)):
            raise RuntimeError('V8 recycled I4 RHS size changed within one model')

    def _validate_full_array(self, value: Any, *, name: str) -> np.ndarray:
        """Validate a complete PETSc Vec before reducing to owned coordinates."""

        array = np.asarray(value)
        if self._local_size is None or self._excluded_indices is None:
            raise RuntimeError('V8 PETSc prototype is not initialized')
        if array.ndim != 1 or array.dtype != np.dtype(np.complex128):
            raise RuntimeError(f'V8 {name} must be a complex128 PETSc Vec array')
        if array.shape != (self._local_size,):
            raise RuntimeError(f'V8 {name} returned the wrong full Vec size')
        if not np.isfinite(array).all():
            raise RuntimeError(f'V8 {name} returned non-finite values')
        if (self._excluded_indices.size and
                not np.all(array[self._excluded_indices] == 0.0)):
            raise RuntimeError(f'V8 {name} has nonzero excluded slave entries')
        return array

    def _call_vec(self, function: Any, value: np.ndarray, *, name: str) -> np.ndarray:
        if self._prototype is None:
            raise RuntimeError('V8 PETSc prototype is not initialized')
        if self._independent_indices is None or value.shape != (len(self._independent_indices),):
            raise RuntimeError('V8 reduced p4 callback size is inconsistent')
        argument = self._prototype.duplicate()
        output = None
        try:
            argument.set(0)
            argument.array[self._independent_indices] = value
            output = function(argument)
            result_full = self._validate_full_array(output.array, name=name)
            result = result_full[self._independent_indices].copy()
            if result.ndim != 1 or result.shape != value.shape:
                raise RuntimeError(f'V8 {name} returned the wrong reduced Vec size')
            return result
        finally:
            if output is not None and output is not argument:
                output.destroy()
            argument.destroy()

    def _array_action(self, value: np.ndarray) -> np.ndarray:
        return self._call_vec(self.action, value, name='A4 callback')

    def _array_pc(self, value: np.ndarray) -> np.ndarray:
        return self._call_vec(self.pc, value, name='B4 callback')

    def _array_residual_action(self, value: np.ndarray) -> np.ndarray:
        return self._call_vec(self.residual_action, value, name='native A4 callback')

    def _as_petsc_result(self, result: dict[str, Any]) -> dict[str, Any]:
        vectors = []
        try:
            for name in ('solution', 'applied', 'residual'):
                vector = self._prototype.duplicate()
                vector.set(0)
                vector.array[self._independent_indices] = result[name]
                vectors.append(vector)
            return dict(solution=vectors[0], applied=vectors[1],
                        residual=vectors[2], facts=result['facts'])
        except BaseException:
            for vector in vectors:
                vector.destroy()
            raise

    def __call__(self, rhs: Any) -> dict[str, Any]:
        if self.destroyed:
            raise RuntimeError('V8 recycled I4 admission has been released')
        self._ensure_prototype(rhs)
        self.calls += 1
        rhs_full = self._validate_full_array(rhs.array, name='rhs')
        rhs_reduced = rhs_full[self._independent_indices].copy()
        result = self.engine.solve(rhs_reduced)
        facts = result['facts']
        if facts.get('implementation_blocked'):
            self.save('recycled_i4_work_policy_violation', dict(
                rhs=np.array(rhs.array, copy=True),
                facts=facts,
                policy=self.policy,
                reason='B4 callback was rejected before exceeding the fixed new-work cap'))
            for name in ('solution', 'applied', 'residual'):
                value = result.get(name)
                if value is not None and hasattr(value, 'destroy'):
                    value.destroy()
                result[name] = None
            raise RuntimeError(
                'recycled I4 implementation blocked: fixed new-work cap was exceeded')
        self.last_facts = self._scalar_facts(facts)
        summary = {key: facts.get(key) for key in (
            'status', 'iterations', 'seconds', 'actual_elapsed_seconds',
            'final_true_residual', 'legal_direction_count', 'timeout_exceeded',
            'stop_reason', 'pool_before', 'pool_after', 'pool_update')}
        summary['call'] = self.calls
        self.recent.append(summary)
        del self.recent[:-3]

        # Zero RHS is legal and must not erase either nonzero streak.
        if facts.get('status') == 'INNER_ZERO_RHS':
            return self._as_petsc_result(result)

        if facts.get('legal_direction_count', 0) == 0:
            self.no_direction_streak += 1
        else:
            self.no_direction_streak = 0
        if bool(facts.get('timeout_exceeded')):
            self.timeout_streak += 1
        else:
            self.timeout_streak = 0
        if self.no_direction_streak >= 2 or self.timeout_streak >= 3:
            reason = (
                'two_consecutive_no_legal_directions'
                if self.no_direction_streak >= 2 else 'three_consecutive_timeouts')
            self.save('bounded_i4_cost_blocked', dict(
                rhs=np.array(rhs.array, copy=True),
                solution=np.array(result['solution'], copy=True),
                applied=np.array(result['applied'], copy=True),
                residual=np.array(result['residual'], copy=True),
                facts=facts, recent=list(self.recent), reason=reason,
            ))
            raise BoundedI4CostBlocked(dict(
                status='INNER_COST_BLOCKED', reason=reason, call=self.calls,
                no_direction_streak=self.no_direction_streak,
                timeout_streak=self.timeout_streak, recent=list(self.recent)))
        return self._as_petsc_result(result)

    def native_exit_spot_check(self) -> dict[str, Any]:
        return self.engine.native_exit_spot_check()

    def reset(self, model_identity: Any | None = None) -> None:
        self.engine.reset(model_identity)
        self.no_direction_streak = 0
        self.timeout_streak = 0
        self.recent.clear()
        self.last_facts = {}

    def snapshot(self) -> dict[str, Any]:
        return dict(
            calls=self.calls,
            no_direction_streak=self.no_direction_streak,
            timeout_streak=self.timeout_streak,
            recent=list(self.recent), last=dict(self.last_facts),
            engine=self.engine.snapshot(),
        )

    def destroy(self) -> None:
        if not self.destroyed:
            self.engine.destroy()
            if self._prototype is not None:
                self._prototype.destroy()
                self._prototype = None
            self.destroyed = True
