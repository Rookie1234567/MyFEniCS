"""Frozen physical-inventory contract for the bounded p4 two-cell quotient.

This module only selects original modes and describes an explicit MPC wrap.
It never generates modes from a quotient period, changes incident angles, or
builds a physical incident load. Numerical qualification remains external.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
import hashlib
from typing import Any

import numpy as np

from .dtn_boundary_phase_gauge import deep_frozen_identity


SCHEMA = "task40extra.y-orbit-two-cell-context.research.v1"
PHYSICAL_GENERATOR_SHA256 = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
GLOBAL_MODE_COUNT = 532
GLOBAL_Y_CELLS = 4
REPLICATION_COUNT = 2
LOCAL_Y_CELLS = 2
SECTOR_MODE_COUNTS = (228, 304)
_ORIGINAL_AXES = tuple(tuple(value*(7.0/135.0) for value in axis) for axis in (
    (0, 16.5, 25, 33.5, 50), (0, 6.25, 12.5, 18.75, 25), (-10, 0, 40, 80, 120, 130),
))


def _identity_bytes(value: Any) -> bytes:
    # Reuse the existing exact ordered identity codec; no parallel serializer.
    from .fullspace_dtn_action import _canonical_json_bytes
    return _canonical_json_bytes(value)


def _config_sha256(cfg: Any) -> str:
    return hashlib.sha256(_identity_bytes(cfg.as_jsonable())).hexdigest()


def _axes(cfg: Any) -> tuple[tuple[float, ...], ...]:
    axes = tuple(tuple(float(x) for x in getattr(cfg, f"mesh_axis_{name}_values"))
                 for name in ("x", "y", "z"))
    if any(not np.isfinite(axis).all() or np.any(np.diff(axis) <= 0) for axis in axes):
        raise ValueError("quotient requires finite increasing explicit original axes")
    return axes


def _mode_key(mode: Any) -> tuple[str, int, int, str]:
    return str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)


def _validate_config_split(global_cfg: Any, assembly_cfg: Any, *, direct_profile=None) -> None:
    global_axes, local_axes = _axes(global_cfg), _axes(assembly_cfg)
    if direct_profile is None:
        expected_axes, global_counts, local_counts, replication_count = _ORIGINAL_AXES, (4, 4, 5), (4, 2, 5), REPLICATION_COUNT
    else:
        from .y_orbit_direct_profile import validate_direct_physical_config
        profile = validate_direct_physical_config(global_cfg, direct_profile)
        expected_axes, global_counts = profile.global_axes, profile.dimensions
        local_counts, replication_count = (profile.nx, 2, profile.nz), profile.replication_count
    if (global_axes != expected_axes
            or tuple(global_cfg.mesh_axis_cell_counts) != global_counts
            or tuple(assembly_cfg.mesh_axis_cell_counts) != local_counts
            or tuple(len(axis)-1 for axis in global_axes) != global_counts
            or tuple(len(axis)-1 for axis in local_axes) != local_counts
            or local_axes != (global_axes[0], global_axes[1][:3], global_axes[2])
            or not np.allclose(np.diff(global_axes[1]), np.diff(global_axes[1])[0], rtol=0, atol=1e-14)
            or global_axes[1][0] != 0.0
            or global_axes[1][-1] != float(global_cfg.period_y)
            or local_axes[1][-1] != float(assembly_cfg.period_y)
            or not np.isclose(float(assembly_cfg.period_y)*replication_count,
                              float(global_cfg.period_y), rtol=0, atol=1e-14)):
        raise ValueError("bounded quotient must preserve x/z and the first two uniform y cells")
    if (int(global_cfg.nedelec_degree) != 4 or int(assembly_cfg.nedelec_degree) != 4
            or global_cfg.nedelec_trace_degree is not None
            or global_cfg.nedelec_interior_degree is not None
            or assembly_cfg.nedelec_trace_degree is not None
            or assembly_cfg.nedelec_interior_degree is not None):
        raise ValueError("two-cell quotient contract requires the complete uniform p4 element")
    if (global_cfg.geometry_kind != "rectangular_block_grating"
            or global_cfg.cell_notch is not None or global_cfg.air_void_box_nm is not None
            or assembly_cfg.cell_notch is not None or assembly_cfg.air_void_box_nm is not None
            or float(global_cfg.grating_width_y) != float(global_cfg.period_y)
            or float(assembly_cfg.grating_width_y) != float(assembly_cfg.period_y)):
        raise ValueError("quotient reference requires the original full-y regular bar, without a repeated notch")
    # Only assembly geometry/provenance fields may differ. Everything else,
    # including incidence, k0, media, material coefficients, z planes and tags,
    # is compared directly using the existing complete configuration identity.
    permitted = {"period_y", "grating_width_y", "case_name", "mesh_axis_cell_counts", "mesh_axis_y_values",
                 "mesh_plan_id", "mesh_plan_sha256"}
    left, right = global_cfg.as_jsonable(), assembly_cfg.as_jsonable()
    # as_jsonable also contains derived geometry/mesh/wrap fields. Compare the
    # declared dataclass inputs to avoid treating those derived fields as new
    # independently adjustable physics.
    from dataclasses import fields
    for field in fields(global_cfg):
        if field.name not in permitted and _identity_bytes(left.get(field.name)) != _identity_bytes(right.get(field.name)):
            raise ValueError(f"quotient assembly changes frozen physical/config field {field.name}")
    if not left or not right:
        raise ValueError("quotient configuration identity is empty")
    if (complex(global_cfg.ky) != complex(assembly_cfg.ky)
            or complex(global_cfg.kx) != complex(assembly_cfg.kx)
            or complex(global_cfg.k0) != complex(assembly_cfg.k0)
            or complex(global_cfg.floquet_phase_x) != complex(assembly_cfg.floquet_phase_x)):
        raise ValueError("quotient must retain the original physical wavevector and x wrap")


def build_two_cell_assembly_config(global_cfg: Any, *, direct_profile=None) -> Any:
    """Copy the regular p4 reference config with its first two actual y cells.

    The local bar fills the same retained cells. Its width is clipped to the
    local period so the existing geometry guard remains valid; no coefficient
    is averaged. Actual per-cell tag/metric comparison is a separate Q1 gate.
    """
    axes = _axes(global_cfg)
    if direct_profile is None:
        counts = (4, 2, 5)
    else:
        from .y_orbit_direct_profile import validate_direct_physical_config
        profile = validate_direct_physical_config(global_cfg, direct_profile)
        counts = (profile.nx, 2, profile.nz)
    local_cfg = replace(
        global_cfg,
        period_y=axes[1][2],
        grating_width_y=axes[1][2],
        case_name=f"{global_cfg.case_name}_two_cell_quotient",
        mesh_axis_cell_counts=counts,
        mesh_axis_y_values=axes[1][:3],
        mesh_plan_id=SCHEMA,
        mesh_plan_sha256=None,
    )
    _validate_config_split(global_cfg, local_cfg, direct_profile=direct_profile)
    return local_cfg


@dataclass(frozen=True)
class YOrbitTwoCellQuotientContext:
    """Immutable metadata; mode objects remain owned by the global inventory."""

    twist_index: int
    theta: complex
    eta: complex
    tau: complex
    phase_x: complex
    global_config_sha256: str
    assembly_config_sha256: str
    physical_generator_manifest_sha256: str
    global_axes: tuple[tuple[float, ...], ...]
    local_axes: tuple[tuple[float, ...], ...]
    original_mode_indices: tuple[int, ...]
    original_mode_keys: tuple[tuple[str, int, int, str], ...]
    original_mode_rows: tuple[Mapping[str, Any], ...]
    local_branch_indices: tuple[int, ...]
    direct_profile_name: str | None = None

    @property
    def global_y_cells(self) -> int:
        return len(self.global_axes[1])-1

    @property
    def local_y_cells(self) -> int:
        return LOCAL_Y_CELLS

    @property
    def replication_count(self) -> int:
        return self.global_y_cells // self.local_y_cells

    @property
    def phase_override(self) -> tuple[complex, complex]:
        return self.phase_x, self.tau

    @property
    def global_q_indices(self) -> tuple[int, int]:
        return self.twist_index, self.twist_index + self.replication_count

    def identity(self) -> Mapping[str, Any]:
        return deep_frozen_identity({
            "schema": SCHEMA, "global_y_cells": self.global_y_cells,
            "local_y_cells": LOCAL_Y_CELLS, "replication_count": self.replication_count,
            "twist_index": self.twist_index, "theta": self.theta,
            "eta": self.eta, "tau": self.tau, "phase_x": self.phase_x,
            "phase_corner": self.phase_x*self.tau,
            "eta_source": "exp(i*(physical_ky*global_Ly+2*pi*b)/4)" if self.direct_profile_name is None else "exp(i*(physical_ky*global_Ly+2*pi*b)/Ny)",
            "global_q_indices": self.global_q_indices,
            "physical_generator_manifest_sha256": self.physical_generator_manifest_sha256,
            "global_mode_count": GLOBAL_MODE_COUNT, "sector_mode_count": len(self.original_mode_indices),
            "global_config_sha256": self.global_config_sha256,
            "assembly_config_sha256": self.assembly_config_sha256,
            "global_axes": self.global_axes, "local_axes": self.local_axes,
            "local_to_original_modes": tuple({
                "local_mode_index": local, "original_mode_index": original,
                "original_mode_key": key, "original_mode_row": row,
                "local_branch_index": branch,
            } for local, (original, key, row, branch) in enumerate(zip(
                self.original_mode_indices, self.original_mode_keys, self.original_mode_rows,
                self.local_branch_indices, strict=True))),
            "local_H_scale_from_global_plane_H": 1/self.replication_count,
            "physical_rhs_source": "dual_transport_of_original_global_MPC_load",
            "ordinary_local_incident_rhs_permitted": False,
            "qualification": "unqualified_research_metadata",
            **({} if self.direct_profile_name is None else {"direct_profile": self.direct_profile_name}),
        })

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_identity_bytes(self.identity())).hexdigest()

    def select_inventory(self, global_cfg: Any, assembly_cfg: Any,
                         inventory: Sequence[Any]) -> tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str]:
        """Verify the complete frozen physical manifest, then select original objects."""
        _validate_config_split(global_cfg, assembly_cfg, direct_profile=self.direct_profile_name)
        if (_config_sha256(global_cfg) != self.global_config_sha256
                or _config_sha256(assembly_cfg) != self.assembly_config_sha256):
            raise ValueError("quotient context/config identity changed after freezing")
        if len(inventory) != 3:
            raise ValueError("quotient requires the complete original modes/rows/hash inventory")
        modes, rows, digest = inventory
        modes, rows = tuple(modes), tuple(rows)
        from .fullspace_dtn_action import build_ordered_mode_manifest
        actual_rows, _encoded, actual_digest = build_ordered_mode_manifest(modes, global_cfg)
        if (len(modes) != GLOBAL_MODE_COUNT or len(rows) != GLOBAL_MODE_COUNT
                or str(digest) != PHYSICAL_GENERATOR_SHA256 or actual_digest != str(digest)
                or self.physical_generator_manifest_sha256 != str(digest)
                or _identity_bytes(rows) != _identity_bytes(actual_rows)):
            raise ValueError("quotient requires the unchanged full 532 physical generator manifest")
        replication_count = self.replication_count
        selected = tuple(i for i, mode in enumerate(modes) if (int(mode.n)-self.twist_index) % replication_count == 0)
        keys = tuple(_mode_key(modes[i]) for i in selected)
        branches = (tuple(((int(modes[i].n)-self.twist_index)//REPLICATION_COUNT) % LOCAL_Y_CELLS for i in selected)
                    if self.direct_profile_name is None else
                    tuple(((int(modes[i].n)-self.twist_index)//replication_count) % LOCAL_Y_CELLS for i in selected))
        theta = (complex(global_cfg.ky)*float(global_cfg.period_y)+2*np.pi*self.twist_index)/self.global_y_cells
        eta = complex(np.exp(1j*theta))
        if self.direct_profile_name is None:
            sector_counts = SECTOR_MODE_COUNTS
        else:
            from .y_orbit_direct_profile import direct_profile_metadata
            sector_counts = direct_profile_metadata(self.direct_profile_name).sector_port_counts
        if (self.twist_index not in range(replication_count) or len(selected) != sector_counts[self.twist_index]
                or selected != self.original_mode_indices or keys != self.original_mode_keys
                or branches != self.local_branch_indices
                or _identity_bytes(tuple(actual_rows[i] for i in selected)) != _identity_bytes(self.original_mode_rows)
                or self.global_axes != _axes(global_cfg) or self.local_axes != _axes(assembly_cfg)
                or self.theta != theta or self.eta != eta or self.tau != eta**2
                or self.phase_x != complex(global_cfg.floquet_phase_x)):
            raise ValueError("quotient twist/eta/sector/original mode mapping is inconsistent")
        return tuple(modes[i] for i in selected), tuple(rows[i] for i in selected), str(digest)


def build_two_cell_quotient_context(global_cfg: Any, assembly_cfg: Any,
                                    full_mode_inventory: Sequence[Any], *, twist_index: int, direct_profile=None) -> YOrbitTwoCellQuotientContext:
    """Freeze one b=0/1 sector; this function never calls a mode generator."""
    _validate_config_split(global_cfg, assembly_cfg, direct_profile=direct_profile)
    if direct_profile is None:
        replication_count, global_y_cells, profile_name = REPLICATION_COUNT, GLOBAL_Y_CELLS, None
    else:
        from .y_orbit_direct_profile import direct_profile_metadata
        profile = direct_profile_metadata(direct_profile)
        replication_count, global_y_cells, profile_name = profile.replication_count, profile.ny, profile.name
    if type(twist_index) is not int or twist_index not in range(replication_count):
        raise ValueError("two-cell twist_index must cover exactly the reviewed profile twists")
    if len(full_mode_inventory) != 3:
        raise ValueError("quotient requires the complete original modes/rows/hash inventory")
    modes, rows, digest = full_mode_inventory
    modes, rows = tuple(modes), tuple(rows)
    if len(modes) != GLOBAL_MODE_COUNT or len(rows) != GLOBAL_MODE_COUNT:
        raise ValueError("quotient requires all 532 original physical modes")
    b = int(twist_index)
    indices = tuple(i for i, mode in enumerate(modes) if (int(mode.n)-b) % replication_count == 0)
    theta = (complex(global_cfg.ky)*float(global_cfg.period_y)+2*np.pi*b)/global_y_cells
    eta = complex(np.exp(1j*theta))
    if not np.isfinite((theta, eta, eta**2)).all() or eta == 0:
        raise ValueError("two-cell explicit theta/eta/tau is zero or nonfinite")
    result = YOrbitTwoCellQuotientContext(
        b, theta, eta, eta**2, complex(global_cfg.floquet_phase_x),
        _config_sha256(global_cfg), _config_sha256(assembly_cfg), str(digest),
        _axes(global_cfg), _axes(assembly_cfg), indices,
        tuple(_mode_key(modes[i]) for i in indices),
        tuple(deep_frozen_identity(rows[i]) for i in indices),
        (tuple(((int(modes[i].n)-b)//REPLICATION_COUNT) % LOCAL_Y_CELLS for i in indices)
         if profile_name is None else
         tuple(((int(modes[i].n)-b)//replication_count) % LOCAL_Y_CELLS for i in indices)), profile_name,
    )
    result.select_inventory(global_cfg, assembly_cfg, (modes, rows, digest))
    return result
