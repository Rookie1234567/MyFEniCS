"""Only the three reviewed direct-calibration profiles, with cheap metadata.

Counts are derived admission facts, not resource or numerical qualification.
The physical modes are generated only from the full physical configuration.
No finite-element assembly, port JIT, factorization or solve occurs here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

SCHEMA = "task40extra.two-cell-direct-calibration-profile.v1"
SCALE = 7.0 / 135.0
PHYSICAL_MODE_COUNT = 532
PHYSICAL_GENERATOR_SHA256 = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
_X_OLD = (0, 16.5, 25, 33.5, 50)
_X_NEW = (0, 8.25, 16.5, 25, 33.5, 41.75, 50)
_Y_OLD = (0, 6.25, 12.5, 18.75, 25)
_Z_OLD = (-10, 0, 40, 80, 120, 130)
_Z_NEW = (-10, 0, 20, 40, 80, 100, 120, 130)


class DirectTwoCellProfile(str, Enum):
    X = "X"
    XZ = "XZ"
    Y = "Y"


def _storage(nx: int, ny: int, nz: int) -> int:
    return 3 * 64 * nx * ny * nz + 32 * (nx * ny + nx * nz + ny * nz) + 4 * (nx + ny + nz)


@dataclass(frozen=True)
class DirectTwoCellProfileMetadata:
    name: str
    dimensions: tuple[int, int, int]
    global_axes: tuple[tuple[float, ...], ...]
    q_port_counts: tuple[int, ...]

    @property
    def nx(self): return self.dimensions[0]
    @property
    def ny(self): return self.dimensions[1]
    @property
    def nz(self): return self.dimensions[2]
    @property
    def local_y_cells(self): return 2
    @property
    def replication_count(self): return self.ny // self.local_y_cells
    @property
    def local_axes(self): return (self.global_axes[0], self.global_axes[1][:3], self.global_axes[2])
    @property
    def cell_count(self): return self.nx * self.ny * self.nz
    @property
    def storage_rows(self): return _storage(*self.dimensions)
    @property
    def rows_per_q(self): return self.nx * (192 * self.nz + 32)
    @property
    def independent_rows(self): return self.ny * self.rows_per_q
    @property
    def interior_rows(self): return 108 * self.cell_count
    @property
    def trace_rows(self): return self.independent_rows - self.interior_rows
    @property
    def trace_rows_per_q(self): return self.nx * (84 * self.nz + 32)
    @property
    def local_cell_count(self): return self.nx * 2 * self.nz
    @property
    def local_storage_rows(self): return _storage(self.nx, 2, self.nz)
    @property
    def local_independent_rows(self): return 2 * self.rows_per_q
    @property
    def local_interior_rows(self): return 108 * self.local_cell_count
    @property
    def local_trace_rows(self): return 2 * self.trace_rows_per_q
    @property
    def sector_port_counts(self):
        return tuple(self.q_port_counts[b] + self.q_port_counts[b + self.replication_count]
                     for b in range(self.replication_count))
    @property
    def augmented_rows_per_q(self):
        return tuple(self.trace_rows_per_q + ports for ports in self.q_port_counts)
    @property
    def factor_allowance_per_q_bytes(self): return 128 * 1024**2
    @property
    def factor_allowance_aggregate_bytes(self): return self.ny * self.factor_allowance_per_q_bytes
    @property
    def evidence_reserve_bytes(self): return 128 * 1024**2

    def identity(self):
        names = ("name", "dimensions", "global_axes", "local_axes", "replication_count", "local_y_cells",
                 "cell_count", "storage_rows", "independent_rows", "interior_rows", "trace_rows", "rows_per_q",
                 "trace_rows_per_q", "local_cell_count", "local_storage_rows", "local_independent_rows",
                 "local_interior_rows", "local_trace_rows", "q_port_counts", "sector_port_counts",
                 "augmented_rows_per_q", "factor_allowance_per_q_bytes", "factor_allowance_aggregate_bytes",
                 "evidence_reserve_bytes")
        return {"schema": SCHEMA, **{name: getattr(self, name) for name in names},
                "physical_mode_count": PHYSICAL_MODE_COUNT, "complete_cell_dimension": 300,
                "complete_cell_interior_dimension": 108, "qualification": "derived_metadata_NOT_RUN",
                "factor_policy": ("unchanged_128MiB_per_q; Y_768MiB_aggregate_approved_research_policy_unknown_fill" if self.name == "Y"
                                  else "unchanged_128MiB_per_q; Y_768MiB_aggregate_requires_review_before_numeric"),
                "factor_fill_and_workspace": None, "ordinary_defaults_changed": False,
                "Y_fixed_512MiB_aggregate_alternative": "not_implemented_requires_separate_resource_policy_review",
                "notch_comparison": "new_uniform_y_aligned_notch" if self.name == "Y" else "same_physical_notch"}


def direct_profile_metadata(profile: DirectTwoCellProfile | str) -> DirectTwoCellProfileMetadata:
    try:
        selected = DirectTwoCellProfile(profile)
    except (TypeError, ValueError) as error:
        raise ValueError("direct profile must be exactly X, XZ or Y") from error
    if selected is DirectTwoCellProfile.X:
        axes, dimensions, ports = (_X_NEW, _Y_OLD, _Z_OLD), (6, 4, 5), (76, 152, 152, 152)
    elif selected is DirectTwoCellProfile.XZ:
        axes, dimensions, ports = (_X_NEW, _Y_OLD, _Z_NEW), (6, 4, 7), (76, 152, 152, 152)
    else:
        axes, dimensions, ports = (_X_OLD, tuple(25 * j / 6 for j in range(7)), _Z_OLD), (4, 6, 5), (76, 76, 76, 152, 76, 76)
    return DirectTwoCellProfileMetadata(selected.value, dimensions,
        tuple(tuple(value * SCALE for value in axis) for axis in axes), ports)


def direct_notch_box_and_count(profile):
    """Exact reviewed notch configuration; Y is a separate aligned3-cell test."""
    metadata = direct_profile_metadata(profile)
    values = ((25, 33.5, 25 / 6, 100 / 6, 40, 80) if metadata.name == "Y"
              else (25, 33.5, 6.25, 18.75, 40, 80))
    return tuple(value * SCALE for value in values), (3 if metadata.name == "Y" else 2)


def validate_direct_physical_config(cfg: Any, profile: DirectTwoCellProfile | str) -> DirectTwoCellProfileMetadata:
    """Reject a profile applied to different physical geometry or mode policy."""
    metadata = direct_profile_metadata(profile)
    axes = tuple(tuple(getattr(cfg, f"mesh_axis_{name}_values")) for name in ("x", "y", "z"))
    if (axes != metadata.global_axes or tuple(cfg.mesh_axis_cell_counts) != metadata.dimensions
            or int(cfg.nedelec_degree) != 4 or cfg.nedelec_trace_degree is not None
            or cfg.nedelec_interior_degree is not None or cfg.mesh_cell_type != "hexahedron"
            or cfg.geometry_kind != "rectangular_block_grating" or cfg.cell_notch is not None
            or cfg.air_void_box_nm is not None or float(cfg.lambda0) != .7
            or float(cfg.incident_phi_deg) != 5.0 or cfg.stage4_dtn_order_policy != "manual"
            or cfg.diffraction_zero_order_only or cfg.diffraction_order_max_m != 9 or cfg.diffraction_order_max_n != 3
            or float(cfg.period_x) != 50 * SCALE or float(cfg.period_y) != 25 * SCALE
            or float(cfg.grating_width_x) != 17 * SCALE or float(cfg.grating_width_y) != 25 * SCALE
            or float(cfg.grating_height) != 120 * SCALE or float(cfg.z_min) != -10 * SCALE
            or float(cfg.z_max) != 130 * SCALE):
        raise ValueError("direct profile requires unchanged scaled physical p4 phi5/M9/N3 regular reference")
    return metadata


def build_direct_profile_config(base_cfg: Any, profile: DirectTwoCellProfile | str) -> Any:
    """Change only reviewed mesh/order/provenance fields on an existing physical config."""
    metadata = direct_profile_metadata(profile)
    cfg = replace(base_cfg, case_name=f"y_orbit_direct_{metadata.name}_p4_regular", nedelec_degree=4,
                  nedelec_trace_degree=None, nedelec_interior_degree=None, mesh_cell_type="hexahedron",
                  mesh_spacing_mode="boundary_fitted", mesh_axis_cell_counts=metadata.dimensions,
                  mesh_axis_x_values=metadata.global_axes[0], mesh_axis_y_values=metadata.global_axes[1],
                  mesh_axis_z_values=metadata.global_axes[2], mesh_axis_z_profile=SCHEMA,
                  mesh_plan_id=f"{SCHEMA}.{metadata.name}", mesh_plan_sha256=None,
                  mesh_target_size=max(b-a for axis in metadata.global_axes for a,b in zip(axis, axis[1:])),
                  stage4_dtn_order_policy="manual", diffraction_zero_order_only=False,
                  diffraction_order_max_m=9, diffraction_order_max_n=3)
    validate_direct_physical_config(cfg, metadata.name)
    return cfg


def actual_direct_mode_inventory_counts(cfg: Any, profile: DirectTwoCellProfile | str) -> dict[str, Any]:
    """Call the real cheap physical generator; count every original alias without FE assembly."""
    from ..common.modes_3d import outgoing_port_modes_3d
    metadata = validate_direct_physical_config(cfg, profile)
    modes = tuple(outgoing_port_modes_3d(cfg))
    keys = tuple((str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)) for mode in modes)
    counts = tuple(sum(int(mode.n) % metadata.ny == q for mode in modes) for q in range(metadata.ny))
    if len(modes) != PHYSICAL_MODE_COUNT or len(set(keys)) != PHYSICAL_MODE_COUNT or counts != metadata.q_port_counts:
        raise ValueError("actual physical generator must preserve all532 original aliases and all q counts")
    return {"mode_count": len(modes), "ordered_mode_keys": keys, "q_port_counts": counts,
            "sector_port_counts": tuple(sum((int(mode.n)-b) % metadata.replication_count == 0 for mode in modes)
                                        for b in range(metadata.replication_count)),
            "source": "src.common.modes_3d.outgoing_port_modes_3d(full_physical_cfg)",
            "FE_assembly_performed": False, "manifest_digest_qualification": "external_complete_manifest_gate"}
