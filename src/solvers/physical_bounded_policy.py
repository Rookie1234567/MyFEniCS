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
    ) -> None:
        self.action = action
        self.pc = pc
        self.sample = sample
        self.save = save
        self.stop_requested = stop_requested
        self.residual_action = residual_action
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
                max_it=16,
                restart=16,
                soft_seconds=25,
                hard_seconds=30,
                v7_policy=True,
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
