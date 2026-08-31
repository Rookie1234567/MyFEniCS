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


class FullspaceSplitVolumeAction:
    """Sum exactly two owner-local physical volume form actions.

    The curl-curl action owns the full-space constraint identity rows.  The
    material-mass action leaves those rows zero, so the sum restores them once
    without allocating a third persistent vector.
    """

    def __init__(
        self,
        curl_curl_form: Any,
        material_mass_form: Any,
        function_space: Any,
        *,
        mpc: Any | None = None,
        jit_options: Mapping[str, Any] | None = None,
    ) -> None:
        from .fullspace_mpc_action import build_fullspace_mpc_form_action

        self._curl_action = build_fullspace_mpc_form_action(
            curl_curl_form,
            function_space,
            mpc=mpc,
            slave_row_identity=True,
            jit_options=jit_options,
        )
        try:
            self._mass_action = build_fullspace_mpc_form_action(
                material_mass_form,
                function_space,
                mpc=mpc,
                slave_row_identity=False,
                jit_options=jit_options,
            )
        except Exception:
            self._curl_action.destroy()
            self._curl_action = None
            raise
        self._apply_count = 0
        self._destroyed = False

    def apply(self, source: PETSc.Vec) -> PETSc.Vec:
        if self._destroyed:
            raise RuntimeError("split volume action has been destroyed")
        curl_result = self._curl_action.apply(source)
        mass_result = self._mass_action.apply(source)
        curl_result.axpy(PETSc.ScalarType(1.0), mass_result)
        self._apply_count += 1
        return curl_result

    @property
    def audit(self) -> Mapping[str, Any]:
        if self._destroyed:
            return MappingProxyType(
                {
                    "schema": "task038.fullspace-split-volume-action.v1",
                    "destroyed": True,
                    "apply_count": int(self._apply_count),
                }
            )
        return MappingProxyType(
            {
                "schema": "task038.fullspace-split-volume-action.v1",
                "operator": "A_curl_curl_plus_A_complex_material_mass",
                "component_count": 2,
                "components": {
                    "curl_curl": dict(self._curl_action.audit),
                    "complex_material_mass": dict(self._mass_action.audit),
                },
                "slave_row_identity_owner": "curl_curl",
                "constraint_identity_rows_exactly_once": True,
                "phase_application": (
                    "each_component_finalized_floquet_mpc_once_no_wrapper_reapply"
                ),
                "sum_output_buffer": "curl_curl_action_output",
                "third_persistent_sum_vector": False,
                "apply_count": int(self._apply_count),
                "destroyed": False,
            }
        )

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        self._mass_action.destroy()
        self._curl_action.destroy()
        self._mass_action = None
        self._curl_action = None


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


__all__ = ("FullspacePhysicalAction", "FullspaceSplitVolumeAction")
