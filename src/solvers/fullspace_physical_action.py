"""Thin matrix-free composition of the current volume and dynamic DtN actions.

The composite is deliberately narrower than the Stage-4 solver: it owns one
volume form action and one dynamic Fourier-DtN action, writes into a caller
owned PETSc vector, and never constructs a global AIJ, Schur, KSP, or T4
interface-transmission object.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from petsc4py import PETSc


class FullspacePhysicalAction:
    """Compose ``A_volume`` and the current dynamic ``A_DtN`` action."""

    def __init__(self, volume_action: Any, dtn_action: Any) -> None:
        if volume_action is None or dtn_action is None:
            raise ValueError("physical action requires volume and dynamic DtN actions")
        self._volume_action = volume_action
        self._dtn_action = dtn_action
        self._apply_count = 0
        self._destroyed = False

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        """Write ``(A_volume + A_DtN) source`` into ``target``.

        The DtN action clears ``target`` as part of its documented apply
        contract.  The volume action returns its owned reusable output buffer;
        it is accumulated before the next volume apply and is not destroyed by
        this wrapper.
        """

        if self._destroyed:
            raise RuntimeError("full physical action has been destroyed")
        self._dtn_action.apply(source, target)
        volume_result = self._volume_action.apply(source)
        target.axpy(PETSc.ScalarType(1.0), volume_result)
        self._apply_count += 1

    def compose_physical_rhs(
        self,
        base_incident_traction: PETSc.Vec,
        mode_amplitudes: Any,
        target: PETSc.Vec,
    ) -> None:
        """Forward the current DtN physical-RHS composition contract."""

        if self._destroyed:
            raise RuntimeError("full physical action has been destroyed")
        self._dtn_action.compose_physical_rhs(
            base_incident_traction, mode_amplitudes, target
        )

    def mult(
        self, _matrix: PETSc.Mat | None, source: PETSc.Vec, target: PETSc.Vec
    ) -> None:
        self.apply(source, target)

    @property
    def audit(self) -> Mapping[str, Any]:
        volume_audit = getattr(self._volume_action, "audit", {})
        dtn_audit = getattr(self._dtn_action, "audit", {})
        return MappingProxyType(
            {
                "schema": "task038.fullspace-physical-action.v1",
                "operator": "A_volume_plus_dynamic_DtN",
                "volume_action": dict(volume_audit),
                "dtn_action": dict(dtn_audit),
                "t4_transmission_included": False,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "apply_count": int(self._apply_count),
            }
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._dtn_action.destroy()
        self._volume_action.destroy()
        self._dtn_action = None
        self._volume_action = None


__all__ = ("FullspacePhysicalAction",)
