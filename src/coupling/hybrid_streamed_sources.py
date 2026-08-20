"""One-mode physical sources for the V7 streamed Petrov producer."""

from __future__ import annotations

import gc
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np
from dolfinx import fem
from petsc4py import PETSc

from .hybrid_internal_modes import (
    _ReusableInterfaceSurfaceLoad,
    _ReusableModeTractionEvaluator,
)
from .modal_trace_projection import _trace_from_full_mode_vector
from ..modes.stable_propagation import scalar_cg_discrete_traction_beta


__all__ = (
    "StreamedPhysicalModalSourceProvider",
    "streamed_source_relative_error",
    "streamed_source_oracle_report",
)


class StreamedPhysicalModalSourceProvider:
    """Assemble one transient mode source without a full modal owner.

    The packet pair contains only one rank-local right/left mode row.  The
    reusable traction evaluator and trace-only surface load are retained, but
    no 480-column matrix, mode list, PETSc mode bundle, or exact factor is
    created.  The packet left trace is deliberately named
    ``packet_left_surface_dual`` because it is not silently identified with a
    full-owner ``P^H e_j`` column.
    """

    def __init__(self, system: Any, spaces: Any) -> None:
        if getattr(system, "side", None) not in {"bottom", "top"}:
            raise ValueError("Streamed physical source needs one bottom/top system")
        self.system = system
        self.spaces = spaces
        self._traction_evaluator = _ReusableModeTractionEvaluator(spaces)
        self._surface_load = _ReusableInterfaceSurfaceLoad(system)
        self._right_count = 0
        self._left_count = 0
        self._destroyed = False

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "destroyed": bool(self._destroyed),
            "mode_vectors_retained": False,
            "full_mode_count": 0,
            "full_traction_matrix_columns": 0,
            "trace_only_required": True,
            "right_source_count": int(self._right_count),
            "left_source_count": int(self._left_count),
            "left_dual_authority": "packet_left_surface_dual",
            "left_dual_full_owner_p_h_e_equivalence": "not_proven",
        }

    def _pair_function(self, pair: Mapping[str, Any], role: str) -> fem.Function:
        values = np.asarray(pair[f"{role}_local"], dtype=np.complex128)
        target = fem.Function(self.spaces.mixed)
        mode_vector = target.x.petsc_vec
        first, last = (int(value) for value in mode_vector.getOwnershipRange())
        if int(pair.get("global_size", mode_vector.getSize())) != int(
            mode_vector.getSize()
        ):
            raise ValueError("Streamed mode global size differs from side system")
        expected_range = tuple(int(value) for value in pair["ownership_range"])
        if expected_range != (first, last) or values.shape != (last - first,):
            raise ValueError("Streamed mode ownership does not match side system")
        if not np.isfinite(values).all():
            raise ValueError("Streamed mode source contains non-finite values")
        mode_vector.getArray()[:] = values
        target.x.scatter_forward()
        return target

    def _entries_to_vec(self, entries: Any, *, scale: complex) -> PETSc.Vec:
        if entries.full_vector is not None:
            entries.full_vector.destroy()
            raise RuntimeError("Streamed source unexpectedly retained a full vector")
        if not entries.tangential_surface_trace_only_verified:
            raise RuntimeError("Streamed source requires trace-only surface reduction")
        target = self.system.A.createVecRight()
        try:
            target.set(0.0)
            rows = np.asarray(entries.matrix_rows, dtype=PETSc.IntType)
            values = scale * np.asarray(entries.matrix_values, dtype=PETSc.ScalarType)
            target.setValues(rows, values, addv=PETSc.InsertMode.ADD_VALUES)
            target.assemble()
            return target
        except Exception:
            target.destroy()
            raise

    def __call__(
        self,
        system: Any,
        pair: Mapping[str, Any],
        *,
        branch: str,
        role: str,
        family: str,
    ) -> tuple[PETSc.Vec, dict[str, Any]]:
        if self._destroyed:
            raise RuntimeError("Streamed physical source provider is destroyed")
        if system is not self.system:
            raise ValueError("Streamed physical source received another system")
        if branch not in {"positive", "negative"}:
            raise ValueError("Streamed physical source branch is invalid")
        if role not in {"right", "left"}:
            raise ValueError("Streamed physical source role is invalid")
        if role == "right":
            if family not in {
                "positive_modal_traction",
                "negative_modal_traction",
            }:
                raise ValueError("Streamed right source must be a modal traction")
            mode_function = self._pair_function(pair, "right")
            mode_vector = mode_function.x.petsc_vec
            mode = SimpleNamespace(
                beta=complex(pair["beta"]),
                right=SimpleNamespace(right_full=mode_vector),
                direction="forward" if branch == "positive" else "backward",
            )
            try:
                direction = "forward" if branch == "positive" else "backward"
                discrete_beta = scalar_cg_discrete_traction_beta(
                    complex(pair["beta"]),
                    degree=int(self.system.cfg.nedelec_degree),
                    h_nm=float(self.system.cfg.mesh_target_size),
                    direction=direction,
                )
                traction = self._traction_evaluator.evaluate(
                    mode,
                    local_outward_normal_sign=(
                        self.system.local_mesh.local_interface_outward_normal_sign
                    ),
                    beta_override=discrete_beta,
                )
                entries = self._surface_load.assemble(
                    traction,
                    role=f"streamed_{branch}_traction_{int(pair['index'])}",
                )
                target = self._entries_to_vec(entries, scale=-1.0)
            finally:
                mode_function = None
            self._right_count += 1
            return target, {
                "source": "streamed_modal_traction_column",
                "family": family,
                "branch": branch,
                "mode_index": int(pair["index"]),
                "raw_beta": complex(pair["beta"]),
                "discrete_beta": complex(discrete_beta),
                "trace_only_verified": True,
                "full_mode_count": 0,
                "full_traction_matrix_columns": 0,
                "owned_vec_return": True,
            }

        if family in {"positive_modal_dual", "negative_modal_dual"}:
            raise RuntimeError(
                "Full-owner P^H modal dual is unavailable in streamed mode; "
                "use explicit packet_left_surface_dual after an oracle"
            )
        if family != "packet_left_surface_dual":
            raise ValueError("Streamed left source family is invalid")
        mode_function = self._pair_function(pair, "left")
        try:
            trace = _trace_from_full_mode_vector(
                mode_function.x.petsc_vec,
                self.spaces,
                name=f"task039_v7_streamed_{branch}_left_{int(pair['index'])}",
            )
            entries = self._surface_load.assemble(
                trace,
                role=f"streamed_{branch}_left_{int(pair['index'])}",
            )
            target = self._entries_to_vec(entries, scale=1.0)
        finally:
            mode_function = None
        self._left_count += 1
        return target, {
            "source": "packet_left_surface_dual",
            "family": family,
            "branch": branch,
            "mode_index": int(pair["index"]),
            "trace_only_verified": True,
            "full_owner_p_h_e_equivalence": "not_proven",
            "oracle_required": True,
            "owned_vec_return": True,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._traction_evaluator = None
        self._surface_load = None
        self.spaces = None
        self._destroyed = True
        gc.collect()


def streamed_source_relative_error(candidate: PETSc.Vec, reference: PETSc.Vec) -> float:
    """Compare two distributed source vectors without gathering values."""

    difference = candidate.duplicate()
    try:
        candidate.copy(difference)
        difference.axpy(PETSc.ScalarType(-1.0), reference)
        return float(difference.norm() / max(float(reference.norm()), 1.0e-30))
    finally:
        difference.destroy()


def streamed_source_oracle_report(
    candidate: PETSc.Vec,
    reference: PETSc.Vec,
    *,
    tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    """Return the measured streamed/full-owner comparison contract."""

    error = streamed_source_relative_error(candidate, reference)
    finite = bool(np.isfinite(error))
    return {
        "relative_error": float(error),
        "finite": finite,
        "tolerance": float(tolerance),
        "equivalent": bool(finite and error <= float(tolerance)),
    }
