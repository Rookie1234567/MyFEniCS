"""Small reusable core for the V19 PML-terminated multiplicative sweep.

The module contains only bounded maps, the fixed z partition, the quadratic
PML tensor pullback, and the residual-propagating sweep.  A local inverse is
passed in by the caller; this module does not assemble a matrix or choose a
solver.  In particular, the old two-slab :mod:`fullspace_sweep` candidate is
left untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from math import log, pi, sin
from types import SimpleNamespace
from typing import Any

import numpy as np


PML_SWEEP_PROFILE = "fullspace_pml_double_sweep_v19"
PML_LAYER_COUNT = 2
CORE_COUNT = 4
OVERLAP_LAYERS = 1
INTERFACE_TARGETS_NM = (25.0, 60.0, 95.0)
SWEEP_ORDER = (0, 1, 2, 3, 3, 2, 1, 0)
PML_TARGET_AMPLITUDE = 0.01
PML_WAVELENGTH_NM = 13.5
PML_GRAZING_ANGLE_DEG = 1.0


def _relative(left: np.ndarray, right: np.ndarray) -> float:
    left = np.asarray(left, dtype=np.complex128)
    right = np.asarray(right, dtype=np.complex128)
    return float(
        np.linalg.norm(left - right)
        / max(float(np.linalg.norm(right)), np.finfo(np.float64).tiny)
    )


def _array_sha(values: np.ndarray) -> str:
    array = np.ascontiguousarray(np.asarray(values, dtype=np.complex128))
    return sha256(memoryview(array).cast("B")).hexdigest()


def incident_normal_wavenumber(
    wavelength_nm: float = PML_WAVELENGTH_NM,
    grazing_angle_deg: float = PML_GRAZING_ANGLE_DEG,
) -> float:
    """Return ``k0*sin(grazing)`` in inverse nanometres."""

    wavelength_nm = float(wavelength_nm)
    grazing_angle_deg = float(grazing_angle_deg)
    if not np.isfinite(wavelength_nm) or wavelength_nm <= 0.0:
        raise ValueError("wavelength_nm must be finite and positive")
    if not np.isfinite(grazing_angle_deg) or not 0.0 < grazing_angle_deg <= 90.0:
        raise ValueError("grazing_angle_deg must lie in (0, 90]")
    return 2.0 * pi / wavelength_nm * sin(np.deg2rad(grazing_angle_deg))


def pml_sigma_max(
    thickness_nm: float,
    *,
    wavelength_nm: float = PML_WAVELENGTH_NM,
    grazing_angle_deg: float = PML_GRAZING_ANGLE_DEG,
) -> float:
    """Return the fixed quadratic-stretch coefficient for one layer stack."""

    thickness_nm = float(thickness_nm)
    if not np.isfinite(thickness_nm) or thickness_nm <= 0.0:
        raise ValueError("thickness_nm must be finite and positive")
    kz = incident_normal_wavenumber(wavelength_nm, grazing_angle_deg)
    return 3.0 * log(1.0 / PML_TARGET_AMPLITUDE) / (kz * thickness_nm)


def quadratic_stretch(
    distance_nm: float | np.ndarray,
    thickness_nm: float,
    *,
    wavelength_nm: float = PML_WAVELENGTH_NM,
    grazing_angle_deg: float = PML_GRAZING_ANGLE_DEG,
) -> complex | np.ndarray:
    """Return ``s(t)=1+i*sigma_max*(t/delta)**2`` in outward coordinates."""

    distance = np.asarray(distance_nm, dtype=np.float64)
    thickness = float(thickness_nm)
    if np.any(~np.isfinite(distance)) or np.any(distance < 0.0):
        raise ValueError("distance_nm must be finite and non-negative")
    if np.any(distance > thickness + 1.0e-12):
        raise ValueError("distance_nm must lie inside the PML thickness")
    value = 1.0 + 1j * pml_sigma_max(
        thickness,
        wavelength_nm=wavelength_nm,
        grazing_angle_deg=grazing_angle_deg,
    ) * (distance / thickness) ** 2
    return complex(value) if distance.ndim == 0 else np.asarray(value, dtype=np.complex128)


def stretched_distance(
    distance_nm: float | np.ndarray,
    thickness_nm: float,
    *,
    wavelength_nm: float = PML_WAVELENGTH_NM,
    grazing_angle_deg: float = PML_GRAZING_ANGLE_DEG,
) -> complex | np.ndarray:
    """Integrate the quadratic stretch from the physical interface outward."""

    distance = np.asarray(distance_nm, dtype=np.float64)
    thickness = float(thickness_nm)
    if np.any(~np.isfinite(distance)) or np.any(distance < 0.0):
        raise ValueError("distance_nm must be finite and non-negative")
    if np.any(distance > thickness + 1.0e-12):
        raise ValueError("distance_nm must lie inside the PML thickness")
    value = distance + 1j * pml_sigma_max(
        thickness,
        wavelength_nm=wavelength_nm,
        grazing_angle_deg=grazing_angle_deg,
    ) * distance**3 / (3.0 * thickness**2)
    return complex(value) if distance.ndim == 0 else np.asarray(value, dtype=np.complex128)


def pml_pullback_tensors(
    epsilon: complex | np.ndarray,
    mu: complex | np.ndarray,
    stretch: complex,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(epsilon_PML, mu_PML, mu_PML_inverse)`` using the Maxwell pullback.

    The transpose is intentionally not a conjugate transpose.  ``epsilon``
    and ``mu`` may be scalar or 3-by-3 matrices; no second Piola transform is
    applied here.
    """

    stretch = complex(stretch)
    if not np.isfinite(stretch):
        raise ValueError("stretch must be finite")
    eps = np.asarray(epsilon, dtype=np.complex128)
    permeability = np.asarray(mu, dtype=np.complex128)
    if eps.ndim == 0:
        eps = np.eye(3, dtype=np.complex128) * complex(eps)
    if permeability.ndim == 0:
        permeability = np.eye(3, dtype=np.complex128) * complex(permeability)
    if eps.shape != (3, 3) or permeability.shape != (3, 3):
        raise ValueError("epsilon and mu must be scalars or 3x3 matrices")
    jacobian = np.diag(np.asarray((1.0, 1.0, stretch), dtype=np.complex128))
    inverse = np.linalg.inv(jacobian)
    eps_pml = np.linalg.det(jacobian) * inverse @ eps @ inverse.T
    mu_pml = np.linalg.det(jacobian) * inverse @ permeability @ inverse.T
    mu_inverse = np.linalg.inv(mu_pml)
    if not all(np.all(np.isfinite(value)) for value in (eps_pml, mu_pml, mu_inverse)):
        raise ValueError("PML pullback tensors are non-finite")
    return eps_pml, mu_pml, mu_inverse


def build_local_pml_physical_form(
    subdomain: Any,
    cfg: Any,
    *,
    stretch_override: complex | None = None,
) -> tuple[Any, dict[str, Any]]:
    """Build the local Maxwell/PML UFL form for one materialized subdomain.

    The physical cells use the exact split ``curl-curl-k0**2*epsilon`` terms.
    PML cells use the same material tag continued through the cross-section and
    the explicit z-only pullback.  This helper deliberately does not assemble
    a matrix or impose a second global boundary model; the caller owns the
    local boundary treatment and must record it separately.  The optional
    ``stretch_override=1`` is a diagnostic-only unstretched Maxwell check on
    the same extended local mesh.
    """

    import ufl
    from dolfinx import mesh

    local_mesh = subdomain.local_mesh
    mesh_data = subdomain.local_mesh_data
    if stretch_override is not None and complex(stretch_override) != 1.0 + 0.0j:
        raise ValueError("the diagnostic stretch override is fixed to one")
    if local_mesh is None or mesh_data is None or subdomain.local_space is None:
        raise ValueError("local PML form requires a materialized subdomain")
    tdim = local_mesh.topology.dim
    cell_tags = mesh_data.cell_tags
    all_cells = np.asarray(cell_tags.indices, dtype=np.int32)
    all_values = np.asarray(cell_tags.values, dtype=np.int32)
    pml_cells = np.asarray(mesh_data.pml_cell_indices, dtype=np.int32)
    if pml_cells.size == 0:
        raise ValueError("local PML form requires artificial cells")
    pml_set = set(int(cell) for cell in pml_cells)
    physical_mask = np.asarray(
        [int(cell) not in pml_set for cell in all_cells], dtype=bool
    )
    side_tag_map = dict(getattr(mesh_data, "pml_side_tag_map", {}))
    if set(side_tag_map) != set(subdomain.pml_sides):
        raise ValueError("local PML side tags do not match the materialized plan")
    pml_tag_values = np.asarray(mesh_data.pml_cell_tag_values, dtype=np.int32)
    source_by_cell = {
        int(cell): int(value)
        for cell, value in zip(all_cells, all_values, strict=True)
    }
    pml_material_values: list[int] = []
    source_tags: dict[int, int] = {}
    for cell, side_tag in zip(pml_cells, pml_tag_values, strict=True):
        side = next(
            (name for name, value in side_tag_map.items() if int(value) == int(side_tag)),
            None,
        )
        if side is None:
            raise ValueError("PML cell has no side-tag authority")
        source_tag = source_by_cell[int(cell)]
        if source_tag not in {
            int(cfg.tags.air),
            int(cfg.tags.substrate),
            int(cfg.tags.grating),
        }:
            raise ValueError("PML cell has an unknown continued material tag")
        side_code = 1 if side == "left" else 2
        material_tag = 100000 + 1000 * side_code + source_tag
        pml_material_values.append(material_tag)
        source_tags[material_tag] = source_tag
    combined_cells = np.concatenate((all_cells[physical_mask], pml_cells)).astype(
        np.int32
    )
    combined_values = np.concatenate(
        (all_values[physical_mask], np.asarray(pml_material_values, dtype=np.int32))
    )
    cell_order = np.argsort(combined_cells)
    combined_tags = mesh.meshtags(
        local_mesh, tdim, combined_cells[cell_order], combined_values[cell_order]
    )
    u = ufl.TrialFunction(subdomain.local_space)
    v = ufl.TestFunction(subdomain.local_space)
    dx = ufl.Measure("dx", domain=local_mesh, subdomain_data=combined_tags)
    materials = {
        int(cfg.tags.air): (complex(cfg.eps_r), complex(cfg.mu_r)),
        int(cfg.tags.substrate): (
            complex(cfg.substrate_index**2),
            complex(cfg.mu_r),
        ),
        int(cfg.tags.grating): (
            complex(cfg.grating_index**2),
            complex(cfg.mu_r),
        ),
    }
    curl_u = ufl.curl(u)
    curl_v = ufl.curl(v)
    form = 0
    for tag, (epsilon, permeability) in materials.items():
        form += (
            (1.0 / permeability) * ufl.inner(curl_u, curl_v)
            - cfg.k0**2 * epsilon * ufl.inner(u, v)
        ) * dx(tag)
    x = ufl.SpatialCoordinate(local_mesh)
    pml_facts: list[dict[str, Any]] = []
    for side, side_tag in side_tag_map.items():
        side_cells = pml_cells[pml_tag_values == int(side_tag)]
        if side_cells.size == 0:
            continue
        z_values = np.asarray(
            getattr(mesh_data, "z_values_nm", ()), dtype=np.float64
        )
        physical_layer_start = int(
            getattr(mesh_data, "physical_layer_start", -1)
        )
        physical_layer_count = int(
            getattr(mesh_data, "physical_layer_count", -1)
        )
        interface_index = (
            physical_layer_start
            if side == "left"
            else physical_layer_start + physical_layer_count
        )
        if (
            z_values.ndim != 1
            or physical_layer_start < 0
            or physical_layer_count <= 0
            or not 0 <= interface_index < z_values.size
        ):
            raise ValueError("local PML mesh lacks physical facet endpoints")
        interface = float(z_values[interface_index])
        thickness = float(subdomain.pml_thicknesses_nm[side])
        if thickness <= 0.0:
            raise ValueError("materialized PML side has no positive thickness")
        distance = interface - x[2] if side == "left" else x[2] - interface
        sigma = pml_sigma_max(thickness)
        stretch = (
            1.0 + 1j * sigma * (distance / thickness) ** 2
            if stretch_override is None
            else complex(stretch_override)
        )
        stretch_fact = (
            "1+i*sigma_max*(distance/delta)^2"
            if stretch_override is None
            else f"constant({stretch.real:g}+{stretch.imag:g}j)"
        )
        pml_facts.append(
            {
                "side": side,
                "interface_z_nm": interface,
                "thickness_nm": thickness,
                "stretch": stretch_fact,
                "pullback": "diag(epsilon*s,epsilon*s,epsilon/s); mu inverse diag(1/(mu*s),1/(mu*s),s/mu)",
            }
        )
        mu_by_tag: dict[int, Any] = {}
        eps_by_tag: dict[int, Any] = {}
        for material_tag, source_tag in source_tags.items():
            side_code = 1 if side == "left" else 2
            if int(material_tag // 1000) != 100 + side_code:
                continue
            epsilon, permeability = materials[source_tag]
            mu_by_tag[material_tag] = ufl.as_matrix(
                (
                    (1.0 / (permeability * stretch), 0, 0),
                    (0, 1.0 / (permeability * stretch), 0),
                    (0, 0, stretch / permeability),
                )
            )
            eps_by_tag[material_tag] = ufl.as_matrix(
                (
                    (epsilon * stretch, 0, 0),
                    (0, epsilon * stretch, 0),
                    (0, 0, epsilon / stretch),
                )
            )
        for material_tag in sorted(mu_by_tag):
            form += (
                ufl.inner(mu_by_tag[material_tag] * curl_u, curl_v)
                - cfg.k0**2
                * ufl.inner(eps_by_tag[material_tag] * u, v)
            ) * dx(material_tag)
    return form, {
        "physical_operator": "curl-curl-k0^2 epsilon",
        "pml_operator": "same material with Maxwell coordinate pullback",
        "pml_sides": pml_facts,
        "pml_material_tag_count": len(source_tags),
        "artificial_outer_boundary": "zero_tangential",
        "global_dtn": "not part of local auxiliary form",
    }


class _LocalPMLMatrix:
    """Small matrix-like view adding the fixed zero-tangential outer rows."""

    def __init__(self, base: Any, boundary_rows: np.ndarray) -> None:
        self._base = base
        self._boundary_rows = np.ascontiguousarray(boundary_rows, dtype=np.int32)

    def mult(self, source: Any, target: Any) -> None:
        source_values = np.asarray(source.getArray(readonly=True))
        if self._boundary_rows.size and np.any(
            np.abs(source_values[self._boundary_rows]) > 0.0
        ):
            raise ValueError("zero-tangential local action received a nonzero boundary input")
        self._base.mult(source, target)
        if self._boundary_rows.size:
            target.getArray()[self._boundary_rows] = source_values[self._boundary_rows]

    def getType(self) -> str:
        return str(self._base.getType())


class LocalPMLPhysicalAction:
    """Matrix-free local Maxwell/PML action with fixed outer PEC rows."""

    def __init__(self, base: Any, boundary_rows: np.ndarray, facts: Mapping[str, Any]) -> None:
        self._base = base
        self.matrix = _LocalPMLMatrix(base.matrix, boundary_rows)
        self.audit = {
            **dict(facts),
            "artificial_outer_boundary": "zero_tangential",
            "boundary_row_count": int(np.asarray(boundary_rows).size),
            "boundary_rows_are_zero_input": True,
        }

    def destroy(self) -> None:
        self._base.destroy()


def build_local_pml_physical_action(
    subdomain: Any,
    cfg: Any,
    boundary_rows: Sequence[int],
    *,
    jit_options: Mapping[str, Any] | None = None,
    stretch_override: complex | None = None,
) -> tuple[Any, LocalPMLPhysicalAction, dict[str, Any]]:
    """Build the local PML form and matching matrix-free action.

    The action delegates element/MPC assembly to the existing owner-local
    action, then applies the same zero-tangential row semantics as the local
    assembled diagnostic.  Legal R0 inputs have zero values on these rows.
    """

    from .fullspace_mpc_action import build_fullspace_mpc_form_action

    form, facts = build_local_pml_physical_form(
        subdomain,
        cfg,
        stretch_override=stretch_override,
    )
    base = build_fullspace_mpc_form_action(
        form,
        subdomain.local_space,
        mpc=subdomain.local_floquet.mpc,
        jit_options=jit_options,
    )
    return form, LocalPMLPhysicalAction(base, np.asarray(boundary_rows), facts), facts


@dataclass(frozen=True)
class OwnerMap:
    """A bounded primal prolongation and its Hermitian dual restriction."""

    global_rows: np.ndarray
    phase: np.ndarray
    local_positions: np.ndarray | None = None
    local_size: int | None = None

    def __post_init__(self) -> None:
        rows = np.ascontiguousarray(self.global_rows, dtype=np.int64)
        phases = np.ascontiguousarray(self.phase, dtype=np.complex128)
        if rows.ndim != 1 or phases.ndim != 1 or rows.size != phases.size:
            raise ValueError("owner map rows and phase must be matching vectors")
        if np.any(rows < 0) or np.unique(rows).size != rows.size:
            raise ValueError("owner map rows must be unique and non-negative")
        if not np.all(np.isfinite(phases)) or np.any(np.abs(phases) == 0.0):
            raise ValueError("owner map phase must be finite and nonzero")
        positions = (
            np.arange(rows.size, dtype=np.int64)
            if self.local_positions is None
            else np.ascontiguousarray(self.local_positions, dtype=np.int64)
        )
        if positions.ndim != 1 or positions.size != rows.size or np.any(positions < 0):
            raise ValueError("owner map local positions are invalid")
        size = rows.size if self.local_size is None else int(self.local_size)
        if size < rows.size or np.any(positions >= size):
            raise ValueError("owner map local positions exceed local size")
        rows.setflags(write=False)
        phases.setflags(write=False)
        positions.setflags(write=False)
        object.__setattr__(self, "global_rows", rows)
        object.__setattr__(self, "phase", phases)
        object.__setattr__(self, "local_positions", positions)
        object.__setattr__(self, "local_size", size)

    def restrict_dual(self, global_dual: np.ndarray) -> np.ndarray:
        values = np.asarray(global_dual, dtype=np.complex128)
        if values.ndim != 1 or np.any(self.global_rows >= values.size):
            raise ValueError("global dual vector does not cover owner map")
        result = np.zeros(int(self.local_size), dtype=np.complex128)
        result[self.local_positions] = np.conjugate(self.phase) * values[self.global_rows]
        return result

    def prolong_primal(self, local_primal: np.ndarray, global_size: int) -> np.ndarray:
        values = np.asarray(local_primal, dtype=np.complex128)
        if values.ndim != 1 or values.size < int(self.local_size):
            raise ValueError("local primal vector does not match owner map")
        result = np.zeros(int(global_size), dtype=np.complex128)
        np.add.at(result, self.global_rows, self.phase * values[self.local_positions])
        return result

    def audit(self) -> dict[str, Any]:
        return {
            "global_row_count": int(self.global_rows.size),
            "local_size": int(self.local_size),
            "local_positions": self.local_positions.tolist(),
            "global_rows_sha256": sha256(
                np.ascontiguousarray(self.global_rows).view(np.uint8)
            ).hexdigest(),
            "phase_sha256": _array_sha(self.phase),
            "primal_map": "global[row] += phase * local",
            "dual_map": "local = conjugate(phase) * global[row]",
            "numeric_allgather": False,
        }


@dataclass(frozen=True)
class PMLSubdomain:
    """One core/overlap support and its artificial PML layer inventory."""

    subdomain_id: int
    core_layers: tuple[int, int]
    overlap_layers: tuple[int, int]
    core_global_rows: np.ndarray
    physical_map: OwnerMap
    core_positions_in_physical: np.ndarray
    weights: np.ndarray
    pml_layers: Mapping[str, tuple[int, ...]]
    pml_thicknesses_nm: Mapping[str, float]
    pml_local_row_count: int
    pml_sides: tuple[str, ...] = ()
    local_mesh: Any | None = None
    local_mesh_data: Any | None = None
    local_space: Any | None = None
    local_floquet: Any | None = None
    physical_local_rows: np.ndarray | None = None
    pml_only_local_rows: np.ndarray | None = None

    def __post_init__(self) -> None:
        core_rows = np.ascontiguousarray(self.core_global_rows, dtype=np.int64)
        positions = np.ascontiguousarray(self.core_positions_in_physical, dtype=np.int64)
        weights = np.ascontiguousarray(self.weights, dtype=np.float64)
        if positions.size != core_rows.size or np.any(positions < 0):
            raise ValueError("core/physical support is not closed")
        if np.any(positions >= self.physical_map.global_rows.size):
            raise ValueError("core positions exceed physical support")
        if weights.size != self.physical_map.global_rows.size or np.any(~np.isfinite(weights)):
            raise ValueError("PML PoU weights are not finite")
        if int(self.pml_local_row_count) < 0:
            raise ValueError("PML local row count must be non-negative")
        if int(self.physical_map.local_size) != int(self.physical_map.global_rows.size) + int(self.pml_local_row_count):
            raise ValueError("physical map local size does not include PML rows")
        if any(side not in {"left", "right"} for side in self.pml_sides):
            raise ValueError("PML sides must be left or right")
        if self.physical_local_rows is not None:
            physical_local_rows = np.ascontiguousarray(
                self.physical_local_rows, dtype=np.int64
            )
            physical_local_rows.setflags(write=False)
            object.__setattr__(self, "physical_local_rows", physical_local_rows)
        if self.pml_only_local_rows is not None:
            pml_only_local_rows = np.ascontiguousarray(
                self.pml_only_local_rows, dtype=np.int64
            )
            pml_only_local_rows.setflags(write=False)
            object.__setattr__(self, "pml_only_local_rows", pml_only_local_rows)
        core_rows.setflags(write=False)
        positions.setflags(write=False)
        weights.setflags(write=False)
        object.__setattr__(self, "core_global_rows", core_rows)
        object.__setattr__(self, "core_positions_in_physical", positions)
        object.__setattr__(self, "weights", weights)


@dataclass(frozen=True)
class PMLQuartilePlan:
    """Geometry-derived four-core owner plan for the fixed double sweep."""

    z_values_nm: np.ndarray
    interface_plane_indices: tuple[int, int, int]
    interface_z_nm: tuple[float, float, float]
    subdomains: tuple[PMLSubdomain, ...]
    global_size: int
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        values = np.ascontiguousarray(self.z_values_nm, dtype=np.float64)
        if values.ndim != 1 or values.size < 5 or np.any(np.diff(values) <= 0.0):
            raise ValueError("z_values_nm must be a strictly increasing axis")
        if len(self.subdomains) != CORE_COUNT:
            raise ValueError("V19 requires four non-empty subdomains")
        values.setflags(write=False)
        object.__setattr__(self, "z_values_nm", values)


def _nearest_lower_plane(z_values: np.ndarray, target: float, used: set[int]) -> int:
    candidates = [index for index in range(1, len(z_values) - 1) if index not in used]
    if not candidates:
        raise ValueError("not enough distinct internal z planes")
    return min(candidates, key=lambda index: (abs(float(z_values[index]) - target), float(z_values[index]), index))


def _union_rows(rows_by_layer: Sequence[np.ndarray], start: int, stop: int) -> np.ndarray:
    arrays = [np.asarray(rows, dtype=np.int64) for rows in rows_by_layer[start:stop]]
    if not arrays:
        raise ValueError("subdomain has no cells")
    values = np.unique(np.concatenate(arrays))
    if values.size == 0:
        raise ValueError("subdomain has no rows")
    return np.ascontiguousarray(values, dtype=np.int64)


def build_z_quartile_plan(
    z_values_nm: Sequence[float],
    rows_by_layer: Sequence[np.ndarray],
    *,
    phase_by_row: Mapping[int, complex] | None = None,
    pml_layer_count: int = PML_LAYER_COUNT,
) -> PMLQuartilePlan:
    """Build the fixed four-core plan from actual mesh layers and row supports.

    ``rows_by_layer`` contains the unique global row ids touched by each z
    layer.  It is metadata only; no numeric field is gathered.  Interface
    ties use the lower coordinate plane, and all four core intervals must be
    non-empty.
    """

    z_values = np.asarray(z_values_nm, dtype=np.float64)
    if z_values.ndim != 1 or z_values.size != len(rows_by_layer) + 1:
        raise ValueError("z axis and layer row inventory have incompatible sizes")
    if np.any(~np.isfinite(z_values)) or np.any(np.diff(z_values) <= 0.0):
        raise ValueError("z axis must be finite and strictly increasing")
    if len(rows_by_layer) < CORE_COUNT:
        raise ValueError("four non-empty cores require at least four layers")
    if int(pml_layer_count) != PML_LAYER_COUNT:
        raise ValueError("V19 fixes exactly two artificial PML layers")
    pml_rows_materialized = False
    used: set[int] = set()
    chosen: list[int] = []
    for target in INTERFACE_TARGETS_NM:
        index = _nearest_lower_plane(z_values, target, used)
        chosen.append(index)
        used.add(index)
    plane_indices = tuple(sorted(chosen))
    bounds = (0, *plane_indices, len(rows_by_layer))
    if any(right <= left for left, right in zip(bounds, bounds[1:])):
        raise ValueError("z quartile cores must be non-empty")
    phase_lookup = {} if phase_by_row is None else {int(key): complex(value) for key, value in phase_by_row.items()}
    core_rows = [
        _union_rows(rows_by_layer, bounds[index], bounds[index + 1])
        for index in range(CORE_COUNT)
    ]
    multiplicity: dict[int, int] = {}
    physical_rows = [
        _union_rows(
            rows_by_layer,
            max(0, bounds[index] - OVERLAP_LAYERS),
            min(len(rows_by_layer), bounds[index + 1] + OVERLAP_LAYERS),
        )
        for index in range(CORE_COUNT)
    ]
    weight_sum: dict[int, float] = {}
    for rows in physical_rows:
        for row in rows:
            multiplicity[int(row)] = multiplicity.get(int(row), 0) + 1
    for row, count in multiplicity.items():
        weight_sum[row] = 1.0 / float(count)
    subdomains: list[PMLSubdomain] = []
    for subdomain_id, (start, stop) in enumerate(zip(bounds[:-1], bounds[1:], strict=True)):
        overlap_start = max(0, start - OVERLAP_LAYERS)
        overlap_stop = min(len(rows_by_layer), stop + OVERLAP_LAYERS)
        extended_rows = _union_rows(rows_by_layer, overlap_start, overlap_stop)
        core = core_rows[subdomain_id]
        positions = np.searchsorted(extended_rows, core)
        if not np.array_equal(extended_rows[positions], core):
            raise RuntimeError("core rows are not contained in overlap physical support")
        phases_physical = np.asarray(
            [phase_lookup.get(int(row), 1.0 + 0.0j) for row in extended_rows],
            dtype=np.complex128,
        )
        # The artificial layers are new coordinates, not rows borrowed from
        # the source mesh.  Even when only one source layer is available at an
        # interior end, materialize_dolfinx_pml_quartile_plan extends that
        # adjacent layer width twice.  The plan therefore records only which
        # non-outer sides need PML, never a fabricated source-row inventory.
        left_layers = tuple(range(pml_layer_count)) if overlap_start > 0 else ()
        right_layers = (
            tuple(range(pml_layer_count))
            if overlap_stop < len(rows_by_layer)
            else ()
        )
        pml_row_count = 0
        thicknesses = {"left": 0.0, "right": 0.0}
        subdomains.append(
            PMLSubdomain(
                subdomain_id=subdomain_id,
                core_layers=(int(start), int(stop)),
                overlap_layers=(int(overlap_start), int(overlap_stop)),
                core_global_rows=core,
                physical_map=OwnerMap(
                    extended_rows,
                    phases_physical,
                    local_size=int(extended_rows.size + pml_row_count),
                ),
                core_positions_in_physical=positions,
                weights=np.asarray(
                    [weight_sum[int(row)] for row in extended_rows],
                    dtype=np.float64,
                ),
                pml_layers={"left": left_layers, "right": right_layers},
                pml_thicknesses_nm=thicknesses,
                pml_local_row_count=int(pml_row_count),
                pml_sides=tuple(
                    side
                    for side, layers in (("left", left_layers), ("right", right_layers))
                    if layers
                ),
            )
        )
    unique_rows = set(int(row) for rows in core_rows for row in rows)
    overlap_intersection_rows = [
        sorted(
            set(map(int, physical_rows[index]))
            & set(map(int, physical_rows[index + 1]))
        )
        for index in range(CORE_COUNT - 1)
    ]
    interface_trace_rows = [
        sorted(
            set(map(int, core_rows[index]))
            & set(map(int, core_rows[index + 1]))
        )
        for index in range(CORE_COUNT - 1)
    ]
    pou_accumulated: dict[int, float] = {}
    for subdomain in subdomains:
        for row, weight in zip(
            subdomain.physical_map.global_rows,
            subdomain.weights,
            strict=True,
        ):
            pou_accumulated[int(row)] = pou_accumulated.get(int(row), 0.0) + float(weight)
    pou_error = max(
        (abs(value - 1.0) for value in pou_accumulated.values()),
        default=0.0,
    )
    global_size = max(max(unique_rows) + 1, max(pou_accumulated) + 1)
    audit = {
        "profile": PML_SWEEP_PROFILE,
        "core_count": CORE_COUNT,
        "core_intervals_layers": [list(item.core_layers) for item in subdomains],
        "overlap_layers": [list(item.overlap_layers) for item in subdomains],
        "interface_plane_indices": list(plane_indices),
        "interface_z_nm": [float(z_values[index]) for index in plane_indices],
        "interface_target_z_nm": list(INTERFACE_TARGETS_NM),
        "interface_tie_rule": "nearest plane; lower z on equal distance",
        "interface_trace_row_counts": [len(rows) for rows in interface_trace_rows],
        "interface_trace_count_kind": (
            "raw adjacent-core cell-support intersection; includes MPC slave storage"
        ),
        "overlap_intersection_storage_row_counts": [
            len(rows) for rows in overlap_intersection_rows
        ],
        "core_row_counts": [int(item.core_global_rows.size) for item in subdomains],
        "physical_overlap_row_counts": [int(item.physical_map.global_rows.size) for item in subdomains],
        "pml_local_row_counts": [int(item.pml_local_row_count) for item in subdomains],
        "global_unique_core_row_count": len(unique_rows),
        "summed_core_map_entries": int(sum(item.core_global_rows.size for item in subdomains)),
        "summed_physical_overlap_map_entries": int(sum(item.physical_map.global_rows.size for item in subdomains)),
        "pml_layer_count": int(pml_layer_count),
        "pml_layer_cell_counts": {
            str(item.subdomain_id): {
                side: len(layers) for side, layers in item.pml_layers.items()
            }
            for item in subdomains
        },
        "pou_max_error": float(pou_error),
        "pou_support": "all overlap physical rows; PML rows excluded",
        "pml_rows_materialized": bool(pml_rows_materialized),
        "pml_rows_status": "requires_real_local_mesh_materialization",
        "pml_mesh_materials_copied": False,
        "pml_outer_boundary": "two artificial layers with zero tangential termination",
        "global_transfer_matrix": False,
        "numeric_allgather": False,
    }
    return PMLQuartilePlan(
        z_values_nm=z_values,
        interface_plane_indices=plane_indices,
        interface_z_nm=tuple(float(z_values[index]) for index in plane_indices),
        subdomains=tuple(subdomains),
        global_size=int(global_size),
        audit=audit,
    )


def count_unique_structural_pairs(
    cell_rows: Sequence[np.ndarray],
    global_size: int,
    *,
    row_replacements: Mapping[int, Sequence[int]] | None = None,
) -> int:
    """Count the exact directed AIJ structural pairs implied by cell supports.

    This is a structure-only audit.  It never stores matrix values or creates a
    PETSc matrix.  The row adjacency sets are deliberately local to this
    inventory call and are discarded before any later numerical stage.
    """

    size = int(global_size)
    if size <= 0:
        raise ValueError("global_size must be positive")
    replacements = {} if row_replacements is None else {
        int(row): tuple(int(master) for master in masters)
        for row, masters in row_replacements.items()
    }
    normalized_cells: list[np.ndarray] = []
    row_incidents: dict[int, list[int]] = {}
    for cell_id, support in enumerate(cell_rows):
        rows = np.unique(np.asarray(support, dtype=np.int64))
        if rows.ndim != 1 or np.any(rows < 0) or np.any(rows >= size):
            raise ValueError("cell support contains an invalid global row")
        normalized = np.asarray(
            sorted(
                {
                    int(master)
                    for row in rows
                    for master in replacements.get(int(row), (int(row),))
                }
            ),
            dtype=np.int64,
        )
        if np.any(normalized < 0) or np.any(normalized >= size):
            raise ValueError("MPC replacement contains an invalid global row")
        normalized_cells.append(normalized)
        for row in normalized:
            row_incidents.setdefault(int(row), []).append(cell_id)
    total = 0
    for incident_cells in row_incidents.values():
        columns: set[int] = set()
        for cell_id in incident_cells:
            columns.update(int(value) for value in normalized_cells[cell_id])
        total += len(columns)
    return int(total)


def mpc_global_row_replacements(
    function_space: Any,
    floquet_data: Any,
) -> dict[int, tuple[int, ...]]:
    """Return the exact nonzero slave-to-master row supports of one MPC."""

    mpc = floquet_data.mpc
    index_map = function_space.dofmap.index_map
    slaves = np.asarray(mpc.slaves, dtype=np.int32)
    coefficients, offsets = mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    replacements: dict[int, tuple[int, ...]] = {}
    for slave in slaves:
        masters = np.asarray(mpc.masters.links(int(slave)), dtype=np.int32)
        values = coefficients[int(offsets[int(slave)]) : int(offsets[int(slave) + 1])]
        if masters.size != values.size:
            raise RuntimeError("MPC master and coefficient rows have different lengths")
        nonzero = values != 0.0
        masters = masters[nonzero]
        slave_global = int(index_map.local_to_global(np.asarray([slave]))[0])
        master_global = tuple(
            int(value)
            for value in np.asarray(index_map.local_to_global(masters), dtype=np.int64)
        )
        if not master_global:
            raise RuntimeError("MPC slave has no nonzero master support")
        replacements[slave_global] = master_global
    return replacements


def build_structure_inventory(
    z_values_nm: Sequence[float],
    cell_rows: Sequence[np.ndarray],
    cell_layers: Sequence[int],
    *,
    count_structural_pairs: bool = True,
    row_replacements: Mapping[int, Sequence[int]] | None = None,
) -> dict[str, Any]:
    """Return geometry-derived row/map counts without numeric assembly."""

    if len(cell_rows) != len(cell_layers):
        raise ValueError("cell rows and layer ids must have equal length")
    z_values = np.asarray(z_values_nm, dtype=np.float64)
    rows_by_layer: list[list[np.ndarray]] = [[] for _ in range(len(z_values) - 1)]
    for rows, layer in zip(cell_rows, cell_layers, strict=True):
        layer = int(layer)
        if not 0 <= layer < len(rows_by_layer):
            raise ValueError("cell layer is outside z axis")
        rows_by_layer[layer].append(np.asarray(rows, dtype=np.int64))
    layer_rows = tuple(_union_rows(layer, 0, len(layer)) if layer else np.asarray([], dtype=np.int64) for layer in rows_by_layer)
    if any(rows.size == 0 for rows in layer_rows):
        raise ValueError("every z layer must contain at least one cell row support")
    plan = build_z_quartile_plan(
        z_values,
        layer_rows,
    )
    elemental_entries = int(sum(np.asarray(rows, dtype=np.int64).size ** 2 for rows in cell_rows))
    global_size = int(max(max(rows.max() for rows in layer_rows) + 1, 1))
    structural_pairs = (
        count_unique_structural_pairs(
            cell_rows,
            global_size,
            row_replacements=row_replacements,
        )
        if count_structural_pairs
        else None
    )
    facts = dict(plan.audit)
    facts.update(
        {
            "z_layer_count": int(len(layer_rows)),
            "z_layer_cell_counts": [int(sum(1 for layer in cell_layers if int(layer) == index)) for index in range(len(layer_rows))],
            "cell_count": int(len(cell_rows)),
            "elemental_stencil_entries": elemental_entries,
            "global_aij_nnz": structural_pairs,
            "global_aij_nnz_status": (
                "exact_union_of_cell_structures"
                if structural_pairs is not None
                else "not_requested"
            ),
            "mpc_row_replacement_count": 0
            if row_replacements is None
            else int(len(row_replacements)),
            "owner_local_rows_are_global_ids": True,
            "pml_rows_materialized": bool(plan.audit["pml_rows_materialized"]),
            "pml_rows_status": "requires_real_local_mesh_materialization",
        }
    )
    return facts


def build_dolfinx_structure_inventory(
    space: Any,
    z_values_nm: Sequence[float],
    *,
    floquet_data: Any | None = None,
    comm: Any | None = None,
) -> dict[str, Any]:
    """Derive the R0 row/map inventory from one existing DOLFINx space.

    Only cell row ids and small geometry metadata are exchanged.  No field,
    matrix, PETSc vector, or numeric coefficient is gathered.  R0 uses this
    helper on MPI1; the metadata exchange remains explicit if a later audit
    uses more ranks.
    """

    from dolfinx import mesh

    mesh_object = space.mesh
    communicator = mesh_object.comm if comm is None else comm
    z_values = np.asarray(z_values_nm, dtype=np.float64)
    topological_dimension = mesh_object.topology.dim
    cell_map = mesh_object.topology.index_map(topological_dimension)
    local_cells = np.arange(int(cell_map.size_local), dtype=np.int32)
    midpoints = mesh.compute_midpoints(mesh_object, topological_dimension, local_cells)
    layers = np.searchsorted(z_values, midpoints[:, 2], side="right") - 1
    layers = np.clip(layers, 0, len(z_values) - 2).astype(np.int32)
    local_rows: list[np.ndarray] = []
    for cell in local_cells:
        dofs = np.asarray(space.dofmap.cell_dofs(int(cell)), dtype=np.int64)
        global_rows = np.asarray(space.dofmap.index_map.local_to_global(dofs), dtype=np.int64)
        local_rows.append(np.unique(global_rows))
    gathered = communicator.allgather(
        {
            "rows": [rows.tolist() for rows in local_rows],
            "layers": layers.tolist(),
        }
    )
    all_rows: list[np.ndarray] = []
    all_layers: list[int] = []
    for packet in gathered:
        all_rows.extend(np.asarray(rows, dtype=np.int64) for rows in packet["rows"])
        all_layers.extend(int(layer) for layer in packet["layers"])
    replacements = (
        None
        if floquet_data is None
        else mpc_global_row_replacements(space, floquet_data)
    )
    facts = build_structure_inventory(
        z_values,
        all_rows,
        all_layers,
        row_replacements=replacements,
    )
    facts.update(
        {
            "mpi_size": int(communicator.size),
            "space_degree": int(space.element.basix_element.degree),
            "owner_global_row_count": int(space.dofmap.index_map.size_global),
            "owner_local_row_count": int(space.dofmap.index_map.size_local),
            "owner_local_ghost_count": int(space.dofmap.index_map.num_ghosts),
            "metadata_only_exchange": True,
            "mpc_row_replacement_count": 0
            if replacements is None
            else int(len(replacements)),
        }
    )
    return facts


def _grid_key(values: Sequence[float], tolerance: float) -> tuple[int, ...]:
    return tuple(int(np.rint(float(value) / tolerance)) for value in values)


def _cell_midpoint_data(mesh_object: Any) -> tuple[np.ndarray, np.ndarray]:
    from dolfinx import mesh

    tdim = mesh_object.topology.dim
    cell_map = mesh_object.topology.index_map(tdim)
    cells = np.arange(int(cell_map.size_local), dtype=np.int32)
    return cells, np.asarray(mesh.compute_midpoints(mesh_object, tdim, cells))


def _extended_local_z_axis(
    z_values_nm: np.ndarray,
    overlap_start: int,
    overlap_stop: int,
) -> tuple[np.ndarray, tuple[int, ...], tuple[int, ...], tuple[float, float]]:
    """Add two new cells outside each non-outer physical end of one slab."""

    physical = np.asarray(
        z_values_nm[int(overlap_start) : int(overlap_stop) + 1], dtype=np.float64
    )
    left: np.ndarray = np.asarray([], dtype=np.float64)
    right: np.ndarray = np.asarray([], dtype=np.float64)
    if int(overlap_start) > 0:
        width = float(z_values_nm[int(overlap_start)] - z_values_nm[int(overlap_start) - 1])
        left = float(z_values_nm[int(overlap_start)]) - width * np.asarray((2.0, 1.0))
    if int(overlap_stop) < len(z_values_nm) - 1:
        width = float(z_values_nm[int(overlap_stop) + 1] - z_values_nm[int(overlap_stop)])
        right = float(z_values_nm[int(overlap_stop)]) + width * np.asarray((1.0, 2.0))
    local_z = np.concatenate((left, physical, right))
    return (
        local_z,
        tuple(range(int(left.size))),
        tuple(range(int(left.size) + int(physical.size) - 1, int(local_z.size) - 1)),
        (
            float(physical[0] - left[0]) if left.size else 0.0,
            float(right[-1] - physical[-1]) if right.size else 0.0,
        ),
    )


def _physical_local_row_map(
    global_space: Any,
    global_floquet: Any,
    local_space: Any,
    local_floquet: Any,
    global_mesh: Any,
    local_mesh: Any,
    physical_local_cells: np.ndarray,
    tolerance: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Match physical rows by cell geometry and reference basis position."""

    global_cells, global_midpoints = _cell_midpoint_data(global_mesh)
    _local_cells, local_midpoints = _cell_midpoint_data(local_mesh)
    global_mesh.topology.create_entity_permutations()
    local_mesh.topology.create_entity_permutations()
    global_permutations = np.asarray(
        global_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    local_permutations = np.asarray(
        local_mesh.topology.get_cell_permutation_info(), dtype=np.uint32
    )
    global_by_key: dict[tuple[int, ...], int] = {}
    for cell, midpoint in zip(global_cells, global_midpoints, strict=True):
        key = _grid_key(midpoint, tolerance)
        if key in global_by_key:
            raise RuntimeError("global physical mesh has duplicate cell midpoint")
        global_by_key[key] = int(cell)

    mapping: dict[int, int] = {}
    for local_cell in np.asarray(physical_local_cells, dtype=np.int32):
        midpoint = local_midpoints[int(local_cell)]
        global_cell = global_by_key.get(_grid_key(midpoint, tolerance))
        if global_cell is None:
            raise RuntimeError("local physical cell is absent from the source mesh")
        if int(global_permutations[global_cell]) != int(
            local_permutations[int(local_cell)]
        ):
            raise RuntimeError(
                "physical/local cell orientation information is not identical"
            )
        global_dofs_local = np.asarray(
            global_space.dofmap.cell_dofs(global_cell), dtype=np.int32
        )
        local_dofs = np.asarray(
            local_space.dofmap.cell_dofs(int(local_cell)), dtype=np.int32
        )
        if global_dofs_local.size != local_dofs.size:
            raise RuntimeError("physical/local cell dof dimensions differ")
        global_rows = np.asarray(
            global_space.dofmap.index_map.local_to_global(global_dofs_local),
            dtype=np.int64,
        )
        for global_row, local_row in zip(global_rows, local_dofs, strict=True):
            previous = mapping.setdefault(int(global_row), int(local_row))
            if previous != int(local_row):
                raise RuntimeError("physical/local dof map is not single-valued")

    if not mapping:
        raise RuntimeError("physical/local dof map is empty")
    global_index_map = global_space.dofmap.index_map
    local_index_map = local_space.dofmap.index_map
    global_slave_rows = {
        int(global_index_map.local_to_global(np.asarray([row], dtype=np.int32))[0])
        for row in np.asarray(global_floquet.mpc.slaves, dtype=np.int32)
    }
    local_slave_rows = {
        int(row) for row in np.asarray(local_floquet.mpc.slaves, dtype=np.int32)
    }
    independent_pairs = [
        (global_row, local_row)
        for global_row, local_row in mapping.items()
        if int(global_row) not in global_slave_rows
        and int(local_row) not in local_slave_rows
    ]
    if not independent_pairs:
        raise RuntimeError("physical/local independent dof map is empty")
    independent_pairs.sort()
    global_rows = np.asarray(
        [global_row for global_row, _local_row in independent_pairs], dtype=np.int64
    )
    raw_local_rows = np.asarray(
        [local_row for _global_row, local_row in independent_pairs], dtype=np.int64
    )
    if np.unique(raw_local_rows).size != raw_local_rows.size:
        raise RuntimeError("physical/local independent map has duplicate local rows")
    local_owned_rows = np.setdiff1d(
        np.arange(int(local_index_map.size_local), dtype=np.int64),
        np.asarray(sorted(local_slave_rows), dtype=np.int64),
        assume_unique=False,
    )
    compact = {int(row): index for index, row in enumerate(local_owned_rows)}
    try:
        local_rows = np.asarray([compact[int(row)] for row in raw_local_rows], dtype=np.int64)
    except KeyError as exc:
        raise RuntimeError("physical/local map contains a non-owned row") from exc
    return global_rows, local_rows


def _copy_local_material_tags(
    global_mesh: Any,
    global_mesh_data: Any,
    local_mesh: Any,
    global_z_values: np.ndarray,
    local_z_values: np.ndarray,
    overlap_start: int,
    overlap_stop: int,
    physical_local_start: int,
    physical_layer_count: int,
    tolerance: float,
    pml_tag_base: int,
) -> tuple[Any, Any, np.ndarray, np.ndarray, list[int], list[int]]:
    """Copy physical cell tags and extend adjacent material tags into PML cells."""

    from dolfinx import mesh

    global_cells, global_midpoints = _cell_midpoint_data(global_mesh)
    global_tdim = global_mesh.topology.dim
    source_indices = np.asarray(global_mesh_data.cell_tags.indices, dtype=np.int32)
    source_values = np.asarray(global_mesh_data.cell_tags.values, dtype=np.int32)
    tags_by_cell = {
        int(cell): int(value) for cell, value in zip(source_indices, source_values, strict=True)
    }
    source_by_key: dict[tuple[int, int, int], int] = {}
    for cell, midpoint in zip(global_cells, global_midpoints, strict=True):
        layer = int(np.searchsorted(global_z_values, midpoint[2], side="right") - 1)
        key = (layer, *_grid_key(midpoint[:2], tolerance))
        if key in source_by_key:
            raise RuntimeError("source material tag inventory has duplicate x/y/layer")
        if int(cell) not in tags_by_cell:
            raise RuntimeError("source cell tag inventory is incomplete")
        source_by_key[key] = tags_by_cell[int(cell)]

    local_cells, local_midpoints = _cell_midpoint_data(local_mesh)
    local_values = np.empty(local_cells.size, dtype=np.int32)
    pml_cells: list[int] = []
    pml_kinds: list[int] = []
    pml_source_layers: list[int] = []
    for index, midpoint in zip(local_cells, local_midpoints, strict=True):
        local_layer = int(np.searchsorted(local_z_values, midpoint[2], side="right") - 1)
        if physical_local_start <= local_layer < physical_local_start + physical_layer_count:
            source_layer = int(overlap_start) + local_layer - physical_local_start
        elif local_layer < physical_local_start:
            source_layer = int(overlap_start)
            pml_cells.append(int(index))
            pml_kinds.append(int(pml_tag_base))
            pml_source_layers.append(source_layer)
        else:
            source_layer = int(overlap_stop) - 1
            pml_cells.append(int(index))
            pml_kinds.append(int(pml_tag_base + 1))
            pml_source_layers.append(source_layer)
        key = (source_layer, *_grid_key(midpoint[:2], tolerance))
        try:
            local_values[int(index)] = source_by_key[key]
        except KeyError as exc:
            raise RuntimeError("PML material continuation lacks a source cross-section") from exc

    material_tags = mesh.meshtags(
        local_mesh,
        global_tdim,
        local_cells,
        local_values,
    )
    pml_indices = np.asarray(pml_cells, dtype=np.int32)
    pml_values = np.asarray(pml_kinds, dtype=np.int32)
    pml_tags = mesh.meshtags(local_mesh, global_tdim, pml_indices, pml_values)
    return (
        material_tags,
        pml_tags,
        pml_indices,
        pml_values,
        local_values.tolist(),
        pml_source_layers,
    )


def materialize_dolfinx_pml_quartile_plan(
    plan: PMLQuartilePlan,
    global_space: Any,
    global_floquet: Any,
    global_mesh_data: Any,
    x_values_nm: Sequence[float],
    y_values_nm: Sequence[float],
    *,
    cfg: Any,
    degree: int | None = None,
    comm: Any | None = None,
) -> PMLQuartilePlan:
    """Build the actual auxiliary hexa meshes, spaces, MPCs, and owner maps.

    Physical cells are copied from the Stage-4 mesh.  Every non-outer slab end
    gets two genuinely new z layers.  Their material tags are copied from the
    adjacent physical cross-section; geometry classification is never rerun on
    the artificial coordinates.  The returned plan owns the local DOLFINx
    objects until :func:`destroy_materialized_pml_quartile_plan` is called.
    """

    from basix.ufl import element
    from dolfinx import default_real_type, fem
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.hybrid_local_mesh import _local_boundary_tags
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh

    communicator = global_space.mesh.comm if comm is None else comm
    if int(communicator.size) != 1:
        raise NotImplementedError("R0 local physical/PML mapping is qualified for MPI1 only")
    resolved_degree = (
        int(global_space.element.basix_element.degree)
        if degree is None
        else int(degree)
    )
    if resolved_degree != int(global_space.element.basix_element.degree):
        raise ValueError("local PML space must use the source Nedelec degree")
    x_values = np.asarray(x_values_nm, dtype=np.float64)
    y_values = np.asarray(y_values_nm, dtype=np.float64)
    z_values = np.asarray(plan.z_values_nm, dtype=np.float64)
    tolerance = 1.0e-9 * max(
        float(np.ptp(x_values)), float(np.ptp(y_values)), float(np.ptp(z_values)), 1.0
    )
    tag_values = [int(value) for value in vars(cfg.tags).values()]
    pml_tag_base = max(tag_values, default=0) + 100
    materialized: list[PMLSubdomain] = []
    local_mesh_facts: list[dict[str, Any]] = []
    for original in plan.subdomains:
        overlap_start, overlap_stop = map(int, original.overlap_layers)
        local_z, left_layers, right_layers, thicknesses = _extended_local_z_axis(
            z_values, overlap_start, overlap_stop
        )
        left_count = len(left_layers)
        physical_layer_count = overlap_stop - overlap_start
        physical_local_start = left_count
        local_mesh = _structured_hexa_mesh(
            communicator,
            x_values,
            y_values,
            local_z,
            preserve_input_partition=False,
        )
        local_mesh.name = f"{getattr(cfg, 'case_name', 'task038')}_pml_slab_{original.subdomain_id}"
        local_mesh.topology.create_connectivity(
            local_mesh.topology.dim - 1, local_mesh.topology.dim
        )
        local_cells, local_midpoints = _cell_midpoint_data(local_mesh)
        local_layers = np.searchsorted(local_z, local_midpoints[:, 2], side="right") - 1
        physical_mask = (
            (local_layers >= physical_local_start)
            & (local_layers < physical_local_start + physical_layer_count)
        )
        physical_local_cells = local_cells[physical_mask]
        pml_local_cells = local_cells[~physical_mask]
        if pml_local_cells.size == 0:
            raise RuntimeError("materialized slab has no artificial PML cells")
        (
            material_tags,
            pml_tags,
            pml_indices,
            pml_values,
            _,
            pml_source_layers,
        ) = _copy_local_material_tags(
            global_space.mesh,
            global_mesh_data,
            local_mesh,
            z_values,
            local_z,
            overlap_start,
            overlap_stop,
            physical_local_start,
            physical_layer_count,
            tolerance,
            pml_tag_base,
        )
        _facet_tags, _boundary_facets = _local_boundary_tags(
            local_mesh,
            cfg,
            z_min=float(local_z[0]),
            z_max=float(local_z[-1]),
        )
        facet_tags = _facet_tags
        local_mesh_data = SimpleNamespace(
            mesh=local_mesh,
            cell_tags=material_tags,
            facet_tags=facet_tags,
            pml_cell_tags=pml_tags,
            pml_cell_indices=pml_indices,
            pml_cell_tag_values=pml_values,
            z_values_nm=local_z,
            physical_layer_start=physical_local_start,
            physical_layer_count=physical_layer_count,
            pml_side_tag_map={
                side: int(pml_tag_base + (1 if side == "right" else 0))
                for side in original.pml_sides
            },
        )
        local_space = fem.functionspace(
            local_mesh,
            element(
                "N1curl",
                local_mesh.basix_cell(),
                resolved_degree,
                dtype=default_real_type,
            ),
        )
        local_floquet = build_double_floquet_mpc(local_space, local_mesh_data, cfg)
        global_rows, local_positions = _physical_local_row_map(
            global_space,
            global_floquet,
            local_space,
            local_floquet,
            global_space.mesh,
            local_mesh,
            physical_local_cells,
            tolerance,
        )
        raw_local_size = int(local_space.dofmap.index_map.size_local)
        all_local_rows = np.unique(
            np.concatenate(
                [
                    np.asarray(local_space.dofmap.cell_dofs(int(cell)), dtype=np.int64)
                    for cell in local_cells
                ]
            )
        )
        physical_storage_rows = np.unique(
            np.concatenate(
                [
                    np.asarray(
                        local_space.dofmap.cell_dofs(int(cell)), dtype=np.int64
                    )
                    for cell in physical_local_cells
                ]
            )
        )
        local_slave_rows = np.asarray(
            local_floquet.mpc.slaves, dtype=np.int64
        )
        independent_local_rows = np.setdiff1d(
            all_local_rows, local_slave_rows, assume_unique=False
        )
        physical_rows = np.setdiff1d(
            physical_storage_rows, local_slave_rows, assume_unique=False
        )
        pml_only_rows = np.setdiff1d(
            independent_local_rows, physical_rows, assume_unique=False
        )
        local_size = int(independent_local_rows.size)
        if np.any(all_local_rows >= raw_local_size) or global_rows.size != physical_rows.size:
            raise RuntimeError("local owner row inventory is not MPI-local and closed")
        compact_physical_rows = np.asarray(
            [
                int(np.searchsorted(independent_local_rows, row))
                for row in physical_rows
            ],
            dtype=np.int64,
        )
        if not np.array_equal(np.sort(local_positions), np.sort(compact_physical_rows)):
            raise RuntimeError("physical/local map does not cover the physical local dofs")
        global_slave_rows = {
            int(global_space.dofmap.index_map.local_to_global(np.asarray([row]))[0])
            for row in np.asarray(global_floquet.mpc.slaves, dtype=np.int32)
        }
        expected_keep = np.asarray(
            [int(row) not in global_slave_rows for row in original.physical_map.global_rows],
            dtype=bool,
        )
        expected_rows = original.physical_map.global_rows[expected_keep]
        if not np.array_equal(global_rows, expected_rows):
            raise RuntimeError("materialized physical map changed the source row support")
        local_map = OwnerMap(
            global_rows,
            original.physical_map.phase[expected_keep],
            local_positions=local_positions,
            local_size=local_size,
        )
        core = original.core_global_rows[
            np.asarray(
                [int(row) not in global_slave_rows for row in original.core_global_rows],
                dtype=bool,
            )
        ]
        core_positions = np.searchsorted(global_rows, core)
        if np.any(core_positions >= global_rows.size) or not np.array_equal(
            global_rows[core_positions], core
        ):
            raise RuntimeError("materialized map lost core physical rows")
        local_pml_layers = {"left": left_layers, "right": right_layers}
        materialized.append(
            PMLSubdomain(
                subdomain_id=original.subdomain_id,
                core_layers=original.core_layers,
                overlap_layers=original.overlap_layers,
                core_global_rows=core,
                physical_map=local_map,
                core_positions_in_physical=core_positions,
                weights=original.weights[expected_keep],
                pml_layers=local_pml_layers,
                pml_thicknesses_nm={"left": thicknesses[0], "right": thicknesses[1]},
                pml_local_row_count=int(pml_only_rows.size),
                pml_sides=original.pml_sides,
                local_mesh=local_mesh,
                local_mesh_data=local_mesh_data,
                local_space=local_space,
                local_floquet=local_floquet,
                physical_local_rows=compact_physical_rows,
                pml_only_local_rows=pml_only_rows,
            )
        )
        local_mesh_facts.append(
            {
                "subdomain_id": int(original.subdomain_id),
                "z_values_nm": local_z.tolist(),
                "physical_cell_count": int(physical_local_cells.size),
                "pml_cell_count": int(pml_local_cells.size),
                "pml_only_local_row_count": int(pml_only_rows.size),
                "pml_thicknesses_nm": {
                    "left": float(thicknesses[0]),
                    "right": float(thicknesses[1]),
                },
                "local_space_global_rows": int(local_space.dofmap.index_map.size_global),
                "local_space_raw_owned_rows": raw_local_size,
                "local_space_independent_rows": local_size,
                "physical_global_row_count": int(global_rows.size),
                "pml_tag_values": sorted(set(map(int, pml_values.tolist()))),
                "pml_material_source_layers": sorted(set(pml_source_layers)),
                "material_source": "adjacent physical x/y cross-section copied by z layer",
                "outer_boundary": "zero_tangential",
            }
        )
    audit = dict(plan.audit)
    audit.update(
        {
            "pml_rows_materialized": True,
            "pml_rows_status": "measured_dolfinx_local_mesh",
            "pml_mesh_materials_copied": True,
            "pml_layers_are_new_coordinates": True,
            "pml_local_mesh_facts": local_mesh_facts,
            "pml_local_row_counts": [item.pml_local_row_count for item in materialized],
            "local_mesh_mapping": "physical cell geometry plus reference basis position",
            "local_floquet_mpc_built": True,
            "pml_outer_boundary_condition": "zero_tangential",
            "global_aij_nnz": None,
            "global_aij_nnz_status": "not_assembled_R0_structure_only",
        }
    )
    return PMLQuartilePlan(
        z_values_nm=z_values,
        interface_plane_indices=plan.interface_plane_indices,
        interface_z_nm=plan.interface_z_nm,
        subdomains=tuple(materialized),
        global_size=plan.global_size,
        audit=audit,
    )


def destroy_materialized_pml_quartile_plan(plan: PMLQuartilePlan) -> None:
    """Release local MPC C++ owners; dolfinx_mpc has no ``destroy`` method."""

    for subdomain in plan.subdomains:
        floquet = subdomain.local_floquet
        mpc = None if floquet is None else getattr(floquet, "mpc", None)
        if mpc is not None:
            del mpc._cpp_object


@dataclass(frozen=True)
class SweepResult:
    """Result and compact ledger of one eight-visit multiplicative sweep."""

    correction: np.ndarray
    residual: np.ndarray
    ledger: tuple[Mapping[str, Any], ...]
    audit: Mapping[str, Any]


class PMLDoubleSweep:
    """Apply the fixed updated-residual order ``0,1,2,3,3,2,1,0``."""

    def __init__(self, plan: PMLQuartilePlan) -> None:
        if tuple(SWEEP_ORDER) != (0, 1, 2, 3, 3, 2, 1, 0):
            raise RuntimeError("V19 sweep order is not frozen")
        if plan.global_size <= 0:
            raise ValueError("PML sweep requires a positive global size")
        if plan.audit.get("pml_rows_materialized") is not True:
            raise ValueError(
                "PML sweep requires an explicit local PML row inventory"
            )
        self.plan = plan
        self.apply_count = 0

    def apply(
        self,
        residual: np.ndarray,
        solve_local: Callable[[PMLSubdomain, np.ndarray], np.ndarray],
        action: Callable[[np.ndarray], np.ndarray],
    ) -> SweepResult:
        caller_input = np.asarray(residual, dtype=np.complex128)
        caller_before = _array_sha(caller_input)
        source = np.ascontiguousarray(caller_input).copy()
        if source.ndim != 1 or source.size < self.plan.global_size:
            raise ValueError("residual does not cover the PML plan")
        current = source.copy()
        correction = np.zeros_like(source)
        ledger: list[Mapping[str, Any]] = []
        for visit, subdomain_id in enumerate(SWEEP_ORDER):
            subdomain = self.plan.subdomains[subdomain_id]
            local_rhs = subdomain.physical_map.restrict_dual(current)
            local_correction = np.asarray(solve_local(subdomain, local_rhs), dtype=np.complex128)
            if local_correction.ndim != 1 or local_correction.size != local_rhs.size:
                raise ValueError("local inverse returned an invalid vector")
            if not np.all(np.isfinite(local_correction)):
                raise ValueError("local inverse returned non-finite values")
            physical_positions = subdomain.physical_map.local_positions
            physical_correction = np.zeros_like(local_correction)
            physical_correction[physical_positions] = (
                local_correction[physical_positions] * subdomain.weights
            )
            delta = subdomain.physical_map.prolong_primal(
                physical_correction, source.size
            )
            action_delta = np.asarray(action(delta), dtype=np.complex128)
            if action_delta.shape != source.shape or not np.all(np.isfinite(action_delta)):
                raise ValueError("exact action returned an invalid delta")
            correction += delta
            current -= action_delta
            ledger.append(
                {
                    "visit": int(visit),
                    "subdomain": int(subdomain_id),
                    "residual_norm_before": float(np.linalg.norm(current + action_delta)),
                    "residual_norm_after": float(np.linalg.norm(current)),
                    "local_rhs_norm": float(np.linalg.norm(local_rhs)),
                    "correction_norm": float(np.linalg.norm(delta)),
                    "action_applied": True,
                }
            )
        self.apply_count += 1
        caller_after = _array_sha(caller_input)
        return SweepResult(
            correction=correction,
            residual=current,
            ledger=tuple(ledger),
            audit={
                "profile": PML_SWEEP_PROFILE,
                "sweep_order": list(SWEEP_ORDER),
                "local_visit_count": len(SWEEP_ORDER),
                "exact_action_count": len(SWEEP_ORDER),
                "apply_count": int(self.apply_count),
                "residual_updated_between_visits": True,
                "input_before_sha256": caller_before,
                "input_after_sha256": caller_after,
                "input_unchanged": bool(caller_before == caller_after),
                "finite": bool(np.all(np.isfinite(correction)) and np.all(np.isfinite(current))),
                "global_transfer_matrix": False,
                "numeric_allgather": False,
                "pml_only_local_boundary": True,
            },
        )


def pml_profile_facts(
    thickness_nm: float,
    *,
    wavelength_nm: float = PML_WAVELENGTH_NM,
    grazing_angle_deg: float = PML_GRAZING_ANGLE_DEG,
) -> dict[str, Any]:
    """Return the frozen, auditable PML profile and ideal outgoing decay."""

    thickness_nm = float(thickness_nm)
    kz = incident_normal_wavenumber(wavelength_nm, grazing_angle_deg)
    sigma = pml_sigma_max(
        thickness_nm,
        wavelength_nm=wavelength_nm,
        grazing_angle_deg=grazing_angle_deg,
    )
    stretched = stretched_distance(
        thickness_nm,
        thickness_nm,
        wavelength_nm=wavelength_nm,
        grazing_angle_deg=grazing_angle_deg,
    )
    decay = abs(np.exp(1j * kz * stretched))
    return {
        "stretch": "1+i*sigma_max*(t/delta)^2",
        "sigma_max": float(sigma),
        "kz_inc": float(kz),
        "thickness_nm": thickness_nm,
        "target_one_way_amplitude": PML_TARGET_AMPLITUDE,
        "outgoing_amplitude_at_thickness": float(decay),
        "sign_convention": "exp(-i*omega*t), outward exp(+i*kz*t)",
        "pullback": "det(J) J^-1 tensor J^-T; curl uses inv(mu_PML), mass uses epsilon_PML",
    }


__all__ = [
    "CORE_COUNT",
    "INTERFACE_TARGETS_NM",
    "OVERLAP_LAYERS",
    "PMLDoubleSweep",
    "PMLQuartilePlan",
    "PMLSubdomain",
    "PML_LAYER_COUNT",
    "PML_SWEEP_PROFILE",
    "OwnerMap",
    "SWEEP_ORDER",
    "count_unique_structural_pairs",
    "build_structure_inventory",
    "build_dolfinx_structure_inventory",
    "build_local_pml_physical_action",
    "build_local_pml_physical_form",
    "destroy_materialized_pml_quartile_plan",
    "materialize_dolfinx_pml_quartile_plan",
    "mpc_global_row_replacements",
    "build_z_quartile_plan",
    "incident_normal_wavenumber",
    "pml_pullback_tensors",
    "pml_profile_facts",
    "pml_sigma_max",
    "quadratic_stretch",
    "stretched_distance",
]
