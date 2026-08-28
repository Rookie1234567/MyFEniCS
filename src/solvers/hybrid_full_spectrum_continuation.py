"""Small callback-owned bridge for the V7 full-spectrum identity stage."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from typing import Any

import numpy as np
from mpi4py import MPI

from .hybrid_full_spectrum_trace import build_canonical_full_spectrum_trace_transform
from .hybrid_side_impedance import (
    assemble_reduced_artificial_interface_tangential_mass,
)

__all__ = (
    "apply_owner_local_gamma_mass_covector",
    "run_v7_full_spectrum_transform_identity",
)

_TOL = 1.0e-10
_PLANE_ROWS = 7560
_CHANNELS = 72
_HARMONICS = 105


def _json_safe(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(item) for item in value]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    return str(value)


def _global_norm(values: np.ndarray, comm: MPI.Comm) -> float:
    local = float(np.vdot(values, values).real)
    total = float(comm.allreduce(local, op=MPI.SUM))
    return math.sqrt(max(total, 0.0))


def apply_owner_local_gamma_mass_covector(mass, layout, raw_owner_local):
    """Apply a sparse active-space mass to owner-local Gamma rows.

    The returned array follows ``layout.gamma_rows_local`` and is caller-owned.
    PETSc vectors created here are destroyed before returning.
    """

    raw = np.asarray(raw_owner_local, dtype=np.complex128)
    rows = np.asarray(layout.gamma_rows_local, dtype=np.int64)
    if raw.ndim != 1 or raw.size != rows.size:
        raise ValueError("Gamma raw values do not match the owner-local layout")
    if not np.isfinite(raw).all() or rows.size != np.unique(rows).size:
        raise ValueError("Gamma raw values or rows are invalid")
    first, last = map(int, mass.getOwnershipRange())
    if np.any(rows < first) or np.any(rows >= last):
        raise ValueError("Gamma rows are not owned by the mass matrix rank")
    source = target = None
    try:
        source = mass.createVecRight()
        target = mass.createVecLeft()
        if tuple(map(int, source.getOwnershipRange())) != (first, last):
            raise ValueError("mass column ownership does not match Gamma row ownership")
        if tuple(map(int, target.getOwnershipRange())) != (first, last):
            raise ValueError("mass output ownership does not match Gamma row ownership")
        source.array[:] = 0.0
        source.array[rows - first] = raw
        source.assemble()
        mass.mult(source, target)
        result = np.asarray(target.array[rows - first], dtype=np.complex128).copy()
        if not np.isfinite(result).all():
            raise ValueError("sparse Gamma mass covector is nonfinite")
        sparse_type = str(mass.getType())
        if "dense" in sparse_type.lower():
            raise ValueError("full-spectrum mass bridge requires a sparse PETSc Mat")
        audit = {
            "source_norm": float(source.norm()),
            "output_norm": float(target.norm()),
            "matmult_count": 1,
            "sparse_type": sparse_type,
            "nnz": int(mass.getInfo()["nz_used"]),
            "local_gamma_count": int(rows.size),
            "dense": False,
            "numeric_allgather": False,
        }
        return result, audit
    finally:
        if target is not None:
            target.destroy()
        if source is not None:
            source.destroy()


def _canonical_probe(layout) -> np.ndarray:
    raw = np.empty(len(layout.gamma_rows_local), dtype=np.complex128)
    for placement in layout.blocks:
        block = placement.block
        values = np.empty(len(block.canonical_keys), dtype=np.complex128)
        for index, key in enumerate(block.canonical_keys):
            digest = hashlib.sha256(str(key).encode()).digest()
            values[index] = (
                0.25 + (digest[0] + 1) / 512.0
                + 1j * (0.5 + (digest[1] + 1) / 512.0)
            )
        raw[np.asarray(placement.positions, dtype=np.int64)] = (
            block.canonical_to_raw @ values
        )
    if not np.isfinite(raw).all() or not np.any(raw):
        raise ValueError("canonical full-spectrum probe is invalid")
    return raw


def _factor_snapshot(action) -> dict[str, Any]:
    diagnostics = getattr(action, "diagnostics", {})
    lifecycle = diagnostics.get("factor_lifecycle")
    if not isinstance(lifecycle, Mapping):
        raise TypeError("V7 continuation requires factor lifecycle diagnostics")
    if int(lifecycle.get("ready", 0)) != 3 or bool(lifecycle.get("destroyed")):
        raise RuntimeError("V7 continuation requires three live group factors")
    return dict(lifecycle)


def _check_support_rows(mass, layout, support) -> int:
    active = np.asarray(support["active_support"], dtype=np.int64); first, last = map(int, mass.getOwnershipRange())
    expected = {int(row) for row in active if first <= int(row) < last}
    actual = {int(row) for row in layout.gamma_rows_local}
    if actual != expected:
        raise RuntimeError("Gamma layout owner rows differ from audited support rows")
    return len(actual)


def _side_identity(system, comm, layout, support, bare_operator, z_value, masses, transforms):
    mass = assemble_reduced_artificial_interface_tangential_mass(
        system.V,
        system.static_condensation.condensed,
        support,
        bare_operator=bare_operator,
    )
    masses.append(mass)
    local_count = _check_support_rows(mass.matrix, layout, support)
    transform = build_canonical_full_spectrum_trace_transform(system, layout, comm)
    transforms.append(transform)
    raw = _canonical_probe(layout)
    dual, mass_audit = apply_owner_local_gamma_mass_covector(mass.matrix, layout, raw)
    diagnostics = transform.identity_diagnostics(raw, dual)
    modal = transform.forward_primal(raw)
    coverage = diagnostics["coverage"]
    checks = {
        "block_roundtrip": diagnostics["block_roundtrip_max"] <= _TOL,
        "primal_roundtrip": diagnostics["primal_roundtrip_max"] <= _TOL,
        "dual_roundtrip": diagnostics["dual_roundtrip_max"] <= _TOL,
        "dft_roundtrip": diagnostics["dft_roundtrip_max"] <= _TOL,
        "parseval": diagnostics["parseval_pairing_relative_error"] <= _TOL,
        "phase_once": diagnostics["phase_once"] is True,
        "channels": (
            coverage["channel_count"] == _CHANNELS
            and len(diagnostics["channel_inventory"]) == _CHANNELS
        ),
        "harmonics": len(diagnostics["harmonic_inventory"]) == _HARMONICS,
        "plane_rows": coverage["global_plane_entries"] == _PLANE_ROWS,
        "numeric_allgather": diagnostics["numeric_allgather"] is False,
        "full_plane_replica": diagnostics["full_plane_numeric_replica"] is False,
        "resident_bound": (
            comm.size == 1 or diagnostics["max_numeric_buffer_entries"] < _PLANE_ROWS
        ),
    }
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(f"V7 {z_value} transform identity failed: {failed}")
    return {
        "z": float(z_value),
        "owner_local_gamma_count": local_count,
        "source_norm": _global_norm(raw, comm),
        "dual_source_norm": _global_norm(dual, comm),
        "output_norm": _global_norm(modal.values, comm),
        "absolute": {
            key: float(diagnostics[key])
            for key in (
                "block_roundtrip_max",
                "primal_roundtrip_max",
                "dual_roundtrip_max",
                "dft_roundtrip_max",
                "parseval_pairing_abs_error",
            )
        },
        "mass_audit": _json_safe(mass_audit),
        "artificial_z_trace_mass_audit": _json_safe(mass.audit),
        "transform_diagnostics": _json_safe(diagnostics),
        "checks": checks,
    }


def run_v7_full_spectrum_transform_identity(payload: Mapping[str, Any]):
    """Run the callback-owned lower/upper transform identity and return evidence."""

    if not isinstance(payload, Mapping):
        raise TypeError("V7 full-spectrum continuation payload must be a mapping")
    required = (
        "system",
        "bare_operator",
        "schur_action",
        "factor_lifecycle",
        "resource_callback",
        "lower_gamma_layout",
        "upper_gamma_layout",
        "interface_supports",
        "canonical_layout",
    )
    missing = [name for name in required if name not in payload]
    if missing:
        raise ValueError(f"V7 full-spectrum continuation payload lacks {missing}")
    callback = payload["resource_callback"]
    if not callable(callback):
        raise TypeError("V7 full-spectrum continuation requires resource callback")
    system = payload["system"]
    action = payload["schur_action"]
    bare_operator = payload["bare_operator"]
    factor_before = payload["factor_lifecycle"]
    if not isinstance(factor_before, Mapping) or int(factor_before.get("ready", 0)) != 3:
        raise RuntimeError("V7 continuation payload does not retain three factors")
    comm = system.local_mesh.mesh.comm
    z_values = system.local_mesh.z_values
    supports = payload["interface_supports"]
    if not isinstance(supports, Mapping):
        raise TypeError("V7 interface supports must be a mapping")
    lower_rows = {int(row) for row in payload["lower_gamma_layout"].gamma_rows_local}
    upper_rows = {int(row) for row in payload["upper_gamma_layout"].gamma_rows_local}
    lower_global = int(comm.allreduce(len(lower_rows), op=MPI.SUM))
    upper_global = int(comm.allreduce(len(upper_rows), op=MPI.SUM))
    joint_mapping = getattr(payload["canonical_layout"], "local_row_to_position", None)
    if not isinstance(joint_mapping, Mapping):
        raise TypeError("V7 canonical trace layout has no row-position mapping")
    joint_rows = {int(row): int(position) for row, position in joint_mapping.items()}
    if lower_global != _PLANE_ROWS or upper_global != _PLANE_ROWS:
        raise RuntimeError("V7 canonical trace plane counts are not 7560 each")
    if lower_rows & upper_rows or set(joint_rows) != lower_rows | upper_rows:
        raise RuntimeError("V7 canonical trace local row mapping is not the joint layout")
    positions = list(joint_rows.values())
    if (
        any(row not in range(_PLANE_ROWS) for row in (joint_rows[row] for row in lower_rows))
        or any(row not in range(_PLANE_ROWS, 2 * _PLANE_ROWS) for row in (joint_rows[row] for row in upper_rows))
        or len(set(positions)) != len(positions)
    ):
        raise RuntimeError("V7 canonical trace positions do not separate lower and upper")
    joint_global = int(comm.allreduce(len(joint_rows), op=MPI.SUM))
    if joint_global != 2 * _PLANE_ROWS:
        raise RuntimeError("V7 canonical trace joint layout does not contain 15120 rows")
    canonical_trace_audit = {
        "lower_global_count": lower_global,
        "upper_global_count": upper_global,
        "local_mapped_count": len(joint_rows),
        "joint_rows": joint_global,
        "pass": True,
    }
    resource_before = _json_safe(callback())
    _factor_snapshot(action)
    masses, transforms, sides = [], [], {}
    try:
        for name, z_index, layout_key in (
            ("lower", 2, "lower_gamma_layout"),
            ("upper", 4, "upper_gamma_layout"),
        ):
            if name not in supports:
                raise ValueError(f"V7 interface support is missing {name}")
            sides[name] = _side_identity(
                system,
                comm,
                payload[layout_key],
                supports[name],
                bare_operator,
                z_values[z_index],
                masses,
                transforms,
            )
    finally:
        for transform in reversed(transforms):
            transform.close()
        for mass in reversed(masses):
            mass.destroy()
    resource_after = _json_safe(callback())
    factor_after = _factor_snapshot(action)
    total_rows = sum(
        int(item["transform_diagnostics"]["coverage"]["global_plane_entries"])
        for item in sides.values()
    )
    if total_rows != 2 * _PLANE_ROWS:
        raise RuntimeError("V7 full-spectrum identity did not cover 15120 interface rows")
    return _json_safe(
        {
            "status": "completed_v7_full_spectrum_transform_identity",
            "classification": "V7_FULL_SPECTRUM_TRANSFORM_IDENTITY_PASS",
            "pass": True,
            "executed": True,
            "next_required_stage": "full_spectrum_two_source_screen_required",
            "sides": sides,
            "coverage": {
                "lower_rows": _PLANE_ROWS,
                "upper_rows": _PLANE_ROWS,
                "total_interface_rows": total_rows,
                "channel_count": _CHANNELS,
                "harmonic_count": _HARMONICS,
            },
            "canonical_trace_audit": canonical_trace_audit,
            "resource": {"before": resource_before, "after": resource_after},
            "factor_lifecycle": {
                "before": _json_safe(factor_before),
                "after": _json_safe(factor_after),
            },
            "numeric_allgather": False,
            "full_plane_numeric_replica": False,
        }
    )
