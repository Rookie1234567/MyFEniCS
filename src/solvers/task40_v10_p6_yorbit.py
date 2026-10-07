"""P6 two-cell y-orbit coordinates and complete inverse.

The FE unknown remains the complete original periodic-domain vector. Native
entity moment maps, a two-cell Bloch fold, and local p6 q blocks construct only
the reference inverse; no global dense FE operator is formed here.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

import numpy as np
from scipy import sparse

from src.geometry.task40_nonseparable_plan import (
    TASK40_Q_ASSEMBLY_BOUNDED_V16,
    TASK40_Q_ASSEMBLY_LEGACY,
    TASK40_Q_ASSEMBLY_PREALLOCATED_V13,
    TASK40_V13_Q_ASSEMBLY_STRATEGIES,
)
from .augmented_reference_correction import STRICT_ONLY, q_solve_limit

SCHEMA = "task40extra.y-orbit-full3d-reference.v1"
LIMITS = {"mapping": 1e-12, "operator": 1e-11, "residual": 1e-10}
SOURCE_LINEAGE = {
    "commit": "3f4fb69b20d33d382975bb96db73b44bba583ebd",
    "entities_blob": "23f148ad7c5bef5faf7d63f775eeb6d555981211",
    "transport_blob": "dd9c4252582738e9c1a9112ad6a7984ec138205e",
    "inverse_blob": "c8f652bbdc79f269bae3ab9e39dc480701ae02a5",
    "branch_coordinates_blob": "ae34450f8b8f7326c60649567df061701536fdd0",
    "trace_restriction_blob": "ff902477322a1067b376ea015a95f2dfcb162fde",
    "local_adaptation": "p6 inventory, local mainline MUMPS, and carrier interfaces",
}
@dataclass
class YOrbitEntities:
    """Complete geometric native moment blocks, with no global R/F/Q matrix.

    Vector/panel transport uses the same entity/cell transforms as the original
    full-map builder. Native primal and dual transforms remain distinct.
    """
    independent: np.ndarray
    full_rows: int
    ny: int
    width: int
    bases: tuple
    records: dict
    slots: dict
    dimension_counts: dict
    y_widths: np.ndarray
    _inverses: dict = field(default_factory=dict)
    _transform_bank: Any = field(default=None, repr=False)
    _collection_identity: Any = field(default=None, repr=False)
    _template_keys: dict = field(default_factory=dict, repr=False)
    _actual_state_witnesses: dict = field(default_factory=dict, repr=False)

    def actual_state_witness(self, record_key):
        """Actual geometry/incidence witness, stored independently of bank keys."""
        if self._transform_bank is None or record_key not in self._actual_state_witnesses:
            raise ValueError("record has no banked actual geometry/orientation witness")
        dimension, coordinates, cell, local_entity, positions, info = self._actual_state_witnesses[record_key]
        return {"dimension": dimension, "native_coordinates": [list(point) for point in coordinates],
                "cell": cell, "local_entity": local_entity, "positions": list(positions), "cell_info": info}

    def transform_key(self, record_key):
        if self._transform_bank is None or record_key not in self._template_keys:
            raise ValueError("record has no shared actual orientation key")
        return self._transform_bank.validate_borrow(self._template_keys[record_key], self.records[record_key][1])

    def named_backing_arrays(self, role):
        """Exact named borrowers for the optional run-local owner receipt."""
        arrays = {f"{role}.independent": self.independent,
                  f"{role}.y_widths": self.y_widths}
        for index, (key, (rows, matrix)) in enumerate(self.records.items(), 1):
            arrays[f"{role}.record.{index:06d}.rows"] = rows
            arrays[f"{role}.record.{index:06d}.matrix"] = matrix
            if key in self._inverses:
                arrays[f"{role}.record.{index:06d}.inverse"] = self._inverses[key]
        return arrays

    def future_legacy_inverse_reserve(self):
        """Bound unmaterialized edge/face inverses that are outside the bank."""
        pending = []
        by_dimension = {1: 0, 2: 0}
        for key, (_rows, matrix) in self.records.items():
            dimension = int(key[1][0])
            if key in self._template_keys:
                if dimension != 3:
                    raise ValueError("only cell-interior transforms may borrow the V12 bank")
                continue
            if dimension == 3 and self._transform_bank is not None:
                raise ValueError("p6 cell-interior transform was not admitted to the shared bank")
            if dimension not in (1, 2, 3):
                raise ValueError("unknown geometric entity dimension in inverse reserve")
            if key not in self._inverses:
                pending.append(int(matrix.nbytes))
                by_dimension[dimension] = by_dimension.get(dimension, 0) + 1
        return {
            "future_legacy_inverse_count": len(pending),
            "future_legacy_inverse_payload_bytes": sum(pending),
            "future_legacy_single_inverse_workspace_bytes": max(
                (3 * payload for payload in pending), default=0
            ),
            "future_legacy_inverse_count_by_dimension": {
                str(dimension): count for dimension, count in sorted(by_dimension.items())
            },
            "scope": "unmaterialized edge/face legacy inverses; existing inverses are already resident",
        }

    def transform(self, values, *, direction):
        values = np.asarray(values,dtype=np.complex128)
        n=len(self.independent)
        if (values.ndim not in (1,2) or values.shape[0]!=n
                or (values.ndim==2 and values.shape[1]>32) or not np.isfinite(values).all()):
            raise ValueError("complete native/canonical vector or <=32-column panel required")
        if direction not in ("primal_to_canonical","primal_from_canonical",
                             "dual_to_canonical","dual_from_canonical",
                             "functional_to_canonical","functional_from_canonical"):
            raise ValueError("explicit primal/dual direction required")
        result=np.empty_like(values)
        for orbit in range(self.ny):
            for base in self.bases:
                rows,matrix=self.records[(orbit,base)]
                banked = self._transform_bank is not None and (orbit, base) in self._template_keys
                if banked:
                    self.transform_key((orbit,base))
                first,size=self.slots[base]
                canonical=slice(orbit*self.width+first,orbit*self.width+first+size)
                if direction in ("primal_to_canonical","dual_from_canonical","functional_from_canonical"):
                    key=(orbit,base)
                    if key not in self._inverses:
                        if not banked:
                            inverse=np.linalg.inv(matrix)
                            if np.linalg.norm(inverse@matrix-np.eye(size))/np.sqrt(size)>LIMITS["mapping"]:
                                raise ValueError("original entity moment inverse failed")
                        else:
                            inverse=self._transform_bank.inverse(matrix)
                        self._inverses[key]=inverse
                    elif (banked and
                          self._inverses[key] is not self._transform_bank.inverse(matrix)):
                        raise ValueError("entity inverse is not the borrowed shared template")
                    matrix=self._inverses[key]
                if direction=="primal_to_canonical":result[canonical]=matrix@values[rows]
                elif direction=="primal_from_canonical":result[rows]=matrix@values[canonical]
                elif direction=="dual_to_canonical":result[canonical]=matrix.conj().T@values[rows]
                elif direction=="dual_from_canonical":result[rows]=matrix.conj().T@values[canonical]
                elif direction=="functional_to_canonical":result[canonical]=matrix.T@values[rows]
                else:result[rows]=matrix.T@values[canonical]
        return result


def collect_y_orbit_entities(space, floquet, cfg, axes, *, transform_bank=None):
    """Full-FE canonical geometric orbit map; no raw-row spatial assumptions."""
    from src.solvers.hcurl_canonical_vector_dolfinx import (
        _entity_coordinates, _physical_entity_transform, _topology_data,
    )
    if transform_bank is not None:
        from src.solvers.y_orbit_transform_bank import TransformKey, YOrbitTransformBank

        if not isinstance(transform_bank, YOrbitTransformBank) or transform_bank.mapping_limit != LIMITS["mapping"]:
            raise ValueError("shared bank must retain the original mapping gate")
        basis_identity = transform_bank.bind_space(space, cfg.nedelec_degree)

    if space.mesh.comm.size != 1 or space.dofmap.index_map_bs != 1:
        raise ValueError("probe is qualified only for serial scalar-blocked H(curl)")
    topology, cell_info, owned = _topology_data(space)
    full_rows = int(space.dofmap.index_map.size_local)
    independent = np.setdiff1d(np.arange(full_rows), np.asarray(floquet.mpc.slaves))
    row_of = {int(value): index for index, value in enumerate(independent)}
    grid = tuple(np.asarray(axes[name], dtype=float) for name in ("x", "y", "z"))
    ny = len(grid[1]) - 1
    tolerance = 1e-9
    records = {}
    template_keys = {}
    actual_state_witnesses = {}
    covered = set()
    dimension_counts = {}

    def grid_key(coordinates, dimension):
        indexed = []
        for point in coordinates:
            index = []
            for values, value in zip(grid, point, strict=True):
                matches = np.flatnonzero(np.abs(values - value) <= tolerance)
                if len(matches) != 1:
                    raise ValueError("entity has no unique actual tensor-grid index")
                index.append(int(matches[0]))
            indexed.append(tuple(index))
        anchor = min(point[1] for point in indexed)
        if anchor >= ny:
            raise ValueError("uneliminated y-max entity cannot own an orbit")
        base = (dimension, tuple(sorted((ix, iy - anchor, iz) for ix, iy, iz in indexed)))
        return anchor, base

    def add_entity(ids, canonical_to_native, coordinates, dimension, template_key=None, *,
                   source_cell=None, source_local_entity=None, source_positions=None):
        active = [int(value) in row_of for value in ids]
        if not any(active):
            return
        if not all(active):
            raise ValueError("partly eliminated entity requires an explicit MPC block map")
        if any(int(value) in covered for value in ids):
            raise ValueError("native full-FE DOF appears in multiple canonical entities")
        covered.update(map(int, ids))
        orbit, base = grid_key(coordinates, dimension)
        if (orbit, base) in records:
            raise ValueError("duplicate geometric entity orbit")
        records[(orbit, base)] = (np.asarray([row_of[int(v)] for v in ids]), canonical_to_native)
        if template_key is not None:
            if transform_bank is None:
                raise ValueError("a banked entity key requires its run-local owner")
            template_keys[(orbit, base)] = transform_bank.validate_borrow(template_key, canonical_to_native)
            # These values come from actual collection data, not TransformKey.
            # Tuples retain exact float64 values without another ndarray owner.
            actual_state_witnesses[(orbit, base)] = (
                int(dimension), tuple(tuple(map(float, point)) for point in coordinates),
                int(source_cell), None if source_local_entity is None else int(source_local_entity),
                tuple(map(int, source_positions)), int(cell_info[source_cell]))
        dimension_counts[dimension] = dimension_counts.get(dimension, 0) + len(ids)

    dof_layout = space.dofmap.dof_layout
    for dimension in (1, 2):
        entity_map = topology.index_map(dimension)
        to_cell = topology.connectivity(dimension, topology.dim)
        to_entity = topology.connectivity(topology.dim, dimension)
        for entity in range(int(entity_map.size_local)):
            cell = int(to_cell.links(entity)[0])
            local_entity = np.flatnonzero(np.asarray(to_entity.links(cell)) == entity)
            if len(local_entity) != 1:
                raise ValueError("cell/entity incidence is not unique")
            positions = np.asarray(dof_layout.entity_dofs(dimension, int(local_entity[0])))
            ids = np.asarray(space.dofmap.cell_dofs(cell))[positions]
            coords = _entity_coordinates(space, dimension, entity)
            # V12 shares only exact internal cell blocks. Trace transforms keep
            # the already-qualified geometry-aware legacy construction.
            transform, _state = _physical_entity_transform(
                coords, dimension, cfg.nedelec_degree, tolerance
            )
            add_entity(ids, transform, coords, dimension,
                       source_cell=cell, source_local_entity=int(local_entity[0]),
                       source_positions=positions)
    interior = np.asarray(space.element.basix_element.entity_dofs[3][0], dtype=np.int32)
    cell_dim = int(space.element.space_dimension)
    interior_channels = tuple(map(int, interior)) if transform_bank is not None else None
    for cell in range(int(owned[0])):
        if transform_bank is not None:
            active = [int(value) in row_of for value in np.asarray(space.dofmap.cell_dofs(cell))[interior]]
            if not any(active):
                continue
            if not all(active):
                raise ValueError("partly eliminated entity requires an explicit MPC block map")
        # Same canonical-cell Tt_apply semantics as the inherited full-FE adapter.
        def cell_builder():
            raw_to_canonical = np.eye(cell_dim, dtype=float).ravel()
            space.element.Tt_apply(raw_to_canonical, np.asarray([cell_info[cell]], dtype=np.uint32), cell_dim)
            raw_to_canonical = raw_to_canonical.reshape(cell_dim, cell_dim)[np.ix_(interior, interior)]
            return np.linalg.inv(raw_to_canonical).astype(np.complex128)

        if transform_bank is None:
            transform = cell_builder()
        else:
            key = TransformKey(basis_identity, 3, (len(interior), len(interior)),
                               interior_channels, ("cell_info", int(cell_info[cell])),
                               ("actual_element.Tt_apply", "full_cell_dimension", cell_dim,
                                "inverse_of_raw_to_canonical_interior_block"))
            transform = transform_bank.matrix(
                key, cell_builder,
                workspace_bytes=(cell_dim * cell_dim * 8 + 4 * len(interior) * len(interior) * 16),
            )
        cell_coordinates = _entity_coordinates(space, 3, cell)
        add_entity(np.asarray(space.dofmap.cell_dofs(cell))[interior], transform,
                   cell_coordinates, 3, template_key=None if transform_bank is None else key,
                   source_cell=cell, source_local_entity=None, source_positions=interior)
    if covered != set(map(int, independent)) or dimension_counts.get(3, 0) == 0:
        raise ValueError("full-FE map must cover every independent row and cell interior")
    bases = sorted(base for orbit, base in records if orbit == 0)
    slots = {}
    width = 0
    for base in bases:
        rows, _ = records[(0, base)]
        slots[base] = (width, len(rows))
        width += len(rows)
    if width * ny != len(independent) or len(records) != ny * len(bases):
        raise ValueError("y orbit multiplicities do not cover the complete FE space")
    result = YOrbitEntities(independent,full_rows,ny,width,tuple(bases),records,slots,
                            dimension_counts,np.diff(grid[1]), _transform_bank=transform_bank,
                            _template_keys=template_keys, _actual_state_witnesses=actual_state_witnesses)
    if transform_bank is not None:
        # Object references are private, run-local provenance, never artifact IDs.
        # Reusing a banked collection from another MPC/space/config fails closed.
        result._collection_identity = (space, floquet, cfg,
                                       tuple((name, tuple(map(float, axes[name]))) for name in ("x", "y", "z")))
    return result

@dataclass
class Task40V10FullLayout:
    """Complete FE storage with a small cell-index DFT only."""

    entities: YOrbitEntities
    cfg: Any
    expected_inventory: Mapping[str, int] | None = None

    def __post_init__(self) -> None:
        actual = {
            "ny": self.entities.ny,
            "width": self.entities.width,
            "independent_rows": len(self.entities.independent),
            "storage_rows": self.entities.full_rows,
            "interior_rows": int(self.entities.dimension_counts.get(3, 0)),
        }
        if (
            actual["ny"] != 4
            or actual["width"] * 4 != actual["independent_rows"]
            or actual["interior_rows"] <= 0
        ):
            raise ValueError(f"four-cell full FE orbit inventory mismatch: {actual}")
        if self.expected_inventory is not None:
            mismatches = {
                key: {"expected": value, "actual": actual.get(key)}
                for key, value in self.expected_inventory.items()
                if actual.get(key) != value
            }
            if mismatches:
                raise ValueError(f"full FE runtime inventory mismatch: {mismatches}")
        self.full_rows = self.entities.full_rows
        self.independent = self.entities.independent
        self.independent_rows = len(self.independent)
        self.ny = self.entities.ny
        self.width = self.entities.width
        self.phase_y = complex(self.cfg.floquet_phase_y)
        theta = (
            complex(self.cfg.ky).real * float(self.cfg.period_y)
            + 2 * np.pi * np.arange(self.ny)
        ) / self.ny
        self.cell_dft = np.exp(1j * np.arange(self.ny)[:, None] * theta[None, :])
        self.cell_dft /= np.sqrt(self.ny)
        if (
            abs(complex(self.cfg.ky).imag) > 1e-12
            or abs(abs(self.phase_y) - 1.0) > 1e-12
            or np.linalg.norm(self.cell_dft.conj().T @ self.cell_dft - np.eye(self.ny)) > 1e-12
        ):
            raise ValueError("full p6 reference layout requires a unitary real-Bloch DFT")
        self.audit = {
            "full_storage_rows": self.full_rows,
            "independent_rows": self.independent_rows,
            "ny": self.ny,
            "all_q": list(range(self.ny)),
            "rows_per_q": self.width,
            "dimension_counts": dict(self.entities.dimension_counts),
            "full_F_Q_created": False,
        }

    def _dft(self, values: Any, *, adjoint: bool) -> np.ndarray:
        array = np.asarray(values, dtype=np.complex128)
        if array.shape != (self.independent_rows,) or not np.isfinite(array).all():
            raise ValueError("complete finite p6 FE vector required")
        matrix = self.cell_dft.conj().T if adjoint else self.cell_dft
        return (matrix @ array.reshape(self.ny, self.width)).reshape(-1)

    def dual_to_modal(self, rhs: Any) -> np.ndarray:
        canonical = self.entities.transform(rhs, direction="dual_to_canonical")
        return self._dft(canonical, adjoint=True)

    def primal_to_modal(self, solution: Any) -> np.ndarray:
        canonical = self.entities.transform(solution, direction="primal_to_canonical")
        return self._dft(canonical, adjoint=True)

    def primal_from_modal(self, values: Any) -> np.ndarray:
        canonical = self._dft(values, adjoint=False)
        return self.entities.transform(canonical, direction="primal_from_canonical")


class TwoCellNativeTransport:
    """Dual fold and primal lift between four full cells and two local cells."""

    def __init__(
        self,
        full: YOrbitEntities,
        local: YOrbitEntities,
        *,
        twist_index: int,
        eta: complex,
        cfg: Any,
    ) -> None:
        if type(twist_index) is not int or twist_index not in (0, 1):
            raise ValueError("the two p6 twist sectors are explicitly indexed 0 and 1")
        if (
            full.ny != 4
            or local.ny != 2
            or full.width != local.width
            or len(full.independent) != full.ny * full.width
            or len(local.independent) != local.ny * local.width
            or full.bases != local.bases
            or full.slots != local.slots
            or full.dimension_counts.get(3, 0) <= 0
            or local.dimension_counts.get(3, 0) <= 0
        ):
            raise ValueError("complete full/two-cell entity orbit inventories do not match")
        self.full, self.local = full, local
        self.b, self.K = twist_index, 2
        self.eta = complex(eta)
        self.tau = self.eta**2
        self.ny = full.ny
        expected_eta = np.exp(
            1j * (complex(cfg.ky).real * float(cfg.period_y) + 2 * np.pi * self.b) / self.ny
        )
        phase = complex(cfg.floquet_phase_y)
        if (
            abs(complex(cfg.ky).imag) > 1e-12
            or abs(self.eta - expected_eta) > 1e-12
            or abs(self.tau**self.K - phase) > 1e-12
            or abs(abs(self.eta) - 1.0) > 1e-12
            or not np.array_equal(full.y_widths[:2], local.y_widths)
        ):
            raise ValueError("p6 twist must preserve the exact global Bloch phase and cell metrics")
        self.audit = {
            "twist_index": self.b,
            "global_q_branches": [self.b, self.b + self.K],
            "eta": [self.eta.real, self.eta.imag],
            "tau": [self.tau.real, self.tau.imag],
            "all_internal_channels_retained": True,
        }

    def _fold_canonical(self, values: np.ndarray, *, dual: bool) -> np.ndarray:
        array = np.asarray(values, dtype=np.complex128)
        if array.shape[0] != len(self.full.independent):
            raise ValueError("full vector does not cover all independent p6 FE rows")
        panels = array.reshape((4, self.full.width) + array.shape[1:])
        result = np.empty((2, self.local.width) + array.shape[1:], dtype=np.complex128)
        phase = np.conj(self.tau) if dual else self.tau
        for cell in range(2):
            result[cell] = (panels[cell] + phase * panels[2 + cell]) / np.sqrt(2.0)
        return result.reshape((len(self.local.independent),) + array.shape[1:])

    def fold_dual(self, full_native: Any) -> np.ndarray:
        canonical = self.full.transform(full_native, direction="dual_to_canonical")
        folded = self._fold_canonical(canonical, dual=True)
        return self.local.transform(folded, direction="dual_from_canonical")

    def lift_primal(self, local_native: Any) -> np.ndarray:
        canonical = self.local.transform(local_native, direction="primal_to_canonical")
        panels = canonical.reshape((2, self.local.width) + canonical.shape[1:])
        full = np.empty((4, self.full.width) + canonical.shape[1:], dtype=np.complex128)
        for copy in range(2):
            full[2 * copy : 2 * copy + 2] = self.tau**copy * panels / np.sqrt(2.0)
        native = full.reshape((len(self.full.independent),) + canonical.shape[1:])
        return self.full.transform(native, direction="primal_from_canonical")

    def extract_primal(self, full_native: Any) -> np.ndarray:
        """Project a primal field onto this twist sector for reconstruction checks."""
        canonical = self.full.transform(full_native, direction="primal_to_canonical")
        folded = self._fold_canonical(canonical, dual=True)
        return self.local.transform(folded, direction="primal_from_canonical")

    def lift_dual(self, local_native: Any) -> np.ndarray:
        """Apply the adjoint of ``extract_primal`` to a local dual action.

        Primal fields and dual residuals use different entity transforms.  In
        canonical coordinates the two local cells fold with ``conj(tau)``;
        the adjoint lift therefore contributes ``tau`` to the second global
        copy, then converts the canonical result back with the full dual map.
        """
        canonical = self.local.transform(local_native, direction="dual_to_canonical")
        panels = canonical.reshape((2, self.local.width) + canonical.shape[1:])
        full = np.zeros((4, self.full.width) + canonical.shape[1:], dtype=np.complex128)
        for cell in range(2):
            full[cell] += panels[cell] / np.sqrt(2.0)
            full[2 + cell] += self.tau * panels[cell] / np.sqrt(2.0)
        native = full.reshape((len(self.full.independent),) + canonical.shape[1:])
        return self.full.transform(native, direction="dual_from_canonical")


@dataclass(frozen=True)
class Task40V10SectorContext:
    twist_index: int
    eta: complex
    tau: complex
    global_q_indices: tuple[int, int]
    local_axes: Mapping[str, tuple[float, ...]]
    original_mode_indices: np.ndarray
    local_branch_indices: np.ndarray
    expected_alias_counts: tuple[int, int] | None = None


class TwoCellBranchCoordinates:
    """Local p6 trace/port coordinate maps for both q branches of one twist."""

    def __init__(
        self,
        trace: Mapping[str, Any],
        *,
        trace_rows: int,
        local_modes: tuple[Any, ...],
        local_h: np.ndarray,
        context: Task40V10SectorContext,
        global_h: np.ndarray,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
    ) -> None:
        if not callable(allocation_gate):
            raise TypeError("branch coordinates require the live allocation gate")
        self.trace = trace
        self.context = context
        self.width = int(trace["trace_width"])
        self.trace_rows = int(trace_rows)
        self.ports = len(local_modes)
        self.rows = self.trace_rows + self.ports
        self.index_dtype = np.dtype(np.int32)
        if (
            int(trace["ny"]) != 2
            or self.width * 2 != self.trace_rows
            or len(local_h) != self.ports
            or len(context.original_mode_indices) != self.ports
        ):
            raise ValueError("two-cell trace/port dimensions do not match the runtime inventory")
        expected_h = np.asarray(global_h, dtype=np.float64)[context.original_mode_indices] / 2.0
        local_h = np.asarray(local_h, dtype=np.float64)
        if (
            not np.isfinite(local_h).all()
            or np.any(local_h <= 0)
            or not np.allclose(local_h, expected_h, rtol=1e-12, atol=0.0)
        ):
            raise ValueError("local p6 original H must equal its global mode value divided by two")
        self.scale = 1.0 / np.sqrt(local_h)
        branches = np.asarray(context.local_branch_indices, dtype=np.int8)
        self.aliases = tuple(np.flatnonzero(branches == branch) for branch in (0, 1))
        if sum(map(len, self.aliases)) != self.ports or not np.array_equal(
            np.sort(np.concatenate(self.aliases)), np.arange(self.ports)
        ):
            raise ValueError("local q branches must partition every retained mode alias")
        if context.expected_alias_counts is not None and tuple(map(len, self.aliases)) != context.expected_alias_counts:
            raise ValueError(
                f"local p6 mode aliases differ: {tuple(map(len, self.aliases))}"
            )
        gate = allocation_gate
        r_t, f_t = trace["R_t"], trace["F_t"]
        gate(
            "task40_v10_p6_trace_quotient_product",
            {
                "additional_payload_bytes": 4 * sum(
                    array.nbytes
                    for matrix in (r_t, f_t)
                    for array in (matrix.data, matrix.indices, matrix.indptr)
                ),
                "workspace_bytes": 16 * 1024**2,
                "all_p6_trace_channels_retained": True,
            },
        )
        self.qt = (r_t @ f_t).tocsr()
        if self.qt.shape != (self.trace_rows, 2 * self.width):
            raise ValueError("native p6 trace quotient map has the wrong shape")
        self.audit = {
            "global_q_indices": list(context.global_q_indices),
            "alias_counts": [len(value) for value in self.aliases],
            "original_H_scale_verified": True,
            "positive_H_coordinates": True,
        }

    def q_map(self, branch: int, *, allocation_gate: Callable[[str, Mapping[str, Any]], None]):
        if type(branch) is not int or branch not in (0, 1):
            raise ValueError("both local p6 q branches require explicit indices")
        ids = self.aliases[branch]
        allocation_gate(
            "task40_v10_p6_local_branch_q_map",
            {
                "additional_payload_bytes": 3 * sum(
                    array.nbytes for array in (self.qt.data, self.qt.indices, self.qt.indptr)
                ) + 64 * len(ids),
                "workspace_bytes": 2 * sum(
                    array.nbytes for array in (self.qt.data, self.qt.indices, self.qt.indptr)
                ),
                "branch": branch,
            },
        )
        port_map = sparse.csr_matrix(
            (self.scale[ids].astype(np.complex128), (ids, np.arange(len(ids)))),
            shape=(self.ports, len(ids)),
        )
        return sparse.block_diag(
            (self.qt[:, branch * self.width : (branch + 1) * self.width], port_map),
            format="csr",
        )


def project_reduced_contribution(
    left: sparse.csr_matrix,
    right: sparse.csr_matrix,
    rows: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    label: str,
) -> sparse.csr_matrix:
    """Project one exact p6 contribution without forming its whole operator."""
    rows = np.asarray(rows)
    columns = np.asarray(columns)
    values = np.asarray(values)
    if (
        rows.ndim != 1
        or columns.ndim != 1
        or rows.dtype.kind not in "iu"
        or columns.dtype.kind not in "iu"
        or values.shape != (len(rows), len(columns))
        or values.dtype != np.dtype(np.complex128)
        or not np.isfinite(values).all()
        or (len(rows) and (rows.min() < 0 or rows.max() >= left.shape[0]))
        or (len(columns) and (columns.min() < 0 or columns.max() >= right.shape[0]))
    ):
        raise ValueError(f"invalid p6 contribution {label}")
    lrows = left[rows, :].tocsr()
    rrows = right[columns, :].tocsr()
    l_support = np.unique(lrows.indices)
    r_support = np.unique(rrows.indices)
    shape = (left.shape[1], right.shape[1])
    if not len(l_support) or not len(r_support):
        return sparse.csr_matrix(shape, dtype=np.complex128)
    dense_bytes = 16 * (
        len(rows) * len(l_support)
        + len(columns) * len(r_support)
        + len(l_support) * len(r_support)
    )
    allocation_gate(
        "task40_v10_p6_project/" + label,
        {
            "additional_payload_bytes": dense_bytes,
            "workspace_bytes": dense_bytes,
            "left_support": len(l_support),
            "right_support": len(r_support),
            "global_q_factor_count": 0,
        },
    )
    l = lrows[:, l_support].toarray()
    r = rrows[:, r_support].toarray()
    projected = l.conj().T @ values @ r
    ii, jj = np.nonzero(projected)
    result = sparse.coo_matrix(
        (projected[ii, jj], (l_support[ii], r_support[jj])),
        shape=shape,
        dtype=np.complex128,
    ).tocsr()
    return result


class CompleteTwoCellInverse:
    """All-q p6 reference inverse with full dual folding and storage recovery."""

    def __init__(
        self,
        sectors: tuple[Mapping[str, Any], Mapping[str, Any]],
        full_layout: Task40V10FullLayout,
        factors: Any,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
        reference_pc_strategy: str = STRICT_ONLY,
    ) -> None:
        if len(sectors) != 2 or [s["context"].twist_index for s in sectors] != [0, 1]:
            raise ValueError("both ordered p6 twist sectors are required")
        indices = sorted(
            int(mode)
            for sector in sectors
            for mode in sector["context"].original_mode_indices
        )
        mode_count = len(indices)
        if indices != list(range(mode_count)) or any(
            len(sector["context"].original_mode_indices) != len(sector["bundle"]["modes"])
            for sector in sectors
        ):
            raise ValueError("both p6 sectors must partition every physical mode exactly once")
        if set(factors.factors) != set(range(4)):
            raise ValueError("all four p6 q factors must remain live")
        self.sectors = sectors
        self.layout = full_layout
        self.factors = factors
        self.gate = allocation_gate
        self.reference_pc_strategy = str(reference_pc_strategy)
        self.q_solve_limit = q_solve_limit(self.reference_pc_strategy)
        self.mode_count = mode_count
        self.calls = 0
        self.last_port_solution = None
        self.last_local_solutions = None
        self.last_solve_audit = None
        self.destroyed = False

    def apply_augmented(self, rhs: Any, port_rhs: Any | None = None) -> tuple[np.ndarray, np.ndarray]:
        if self.destroyed:
            raise RuntimeError("p6 complete two-cell inverse has been destroyed")
        full_rhs = np.asarray(rhs, dtype=np.complex128)
        ports = (
            np.zeros(self.mode_count, dtype=np.complex128)
            if port_rhs is None
            else np.asarray(port_rhs, dtype=np.complex128)
        )
        if (
            full_rhs.shape != (self.layout.independent_rows,)
            or ports.shape != (self.mode_count,)
            or not np.isfinite(full_rhs).all()
            or not np.isfinite(ports).all()
        ):
            raise ValueError("complete finite full FE and port RHS vectors are required")
        self.gate(
            "task40_v10_p6_complete_dual_fold_and_recovery",
            {
                "additional_payload_bytes": 16 * (
                    2 * self.layout.independent_rows
                    + sum(3 * sector["action"].condensed.full_rows for sector in self.sectors)
                ),
                "workspace_bytes": 16 * 2**20,
                "all_interior_and_alias_channels": True,
            },
        )
        result = np.zeros(self.layout.independent_rows, dtype=np.complex128)
        mode_count = len(ports)
        alpha = np.empty(mode_count, dtype=np.complex128)
        local_audit = []
        for sector in self.sectors:
            transport = sector["transport"]
            action = sector["action"]
            coordinates = sector["coordinates"]
            context = sector["context"]
            condensed = action.condensed
            ids = np.asarray(context.original_mode_indices, dtype=np.int64)
            local_rhs = np.zeros(condensed.full_rows, dtype=np.complex128)
            local_independent_rows = np.asarray(transport.local.independent, dtype=np.int64)
            local_rhs[local_independent_rows] = transport.fold_dual(full_rhs)
            local_port_rhs = ports[ids] / np.sqrt(2.0)
            reduced_rhs = action.reduce_rhs(
                local_rhs,
                port_rhs=local_port_rhs,
                rhs_is_mpc_dual=True,
            )
            native_solution = np.zeros(action.reduced_size, dtype=np.complex128)
            q_residual_records = []
            for branch in (0, 1):
                q = int(context.global_q_indices[branch])
                q_map = coordinates.q_map(branch, allocation_gate=self.gate)
                modal_rhs = np.asarray(q_map.conj().T @ reduced_rhs, dtype=np.complex128)
                modal_solution = self.factors.solve(q, modal_rhs)
                modal_residual = np.asarray(
                    self.factors.csr_matrices[q] @ modal_solution - modal_rhs,
                    dtype=np.complex128,
                )
                if self.reference_pc_strategy == (
                    "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
                ):
                    from .augmented_reference_correction import stable_euclidean_norm

                    modal_rhs_norm = stable_euclidean_norm(modal_rhs)
                    modal_residual_norm = stable_euclidean_norm(modal_residual)
                    modal_residual_relative = (
                        modal_residual_norm / modal_rhs_norm
                        if modal_rhs_norm > 0.0
                        else (0.0 if modal_residual_norm == 0.0 else float("inf"))
                    )
                else:
                    modal_rhs_norm = float(np.linalg.norm(modal_rhs))
                    modal_residual_norm = float(np.linalg.norm(modal_residual))
                    modal_residual_relative = modal_residual_norm / max(
                        modal_rhs_norm, np.finfo(np.float64).tiny
                    )
                if (
                    not np.isfinite(modal_residual_relative)
                    or modal_residual_relative > self.q_solve_limit
                ):
                    raise FloatingPointError(
                        f"Task40 V10 q={q} inverse residual failed: "
                        f"{modal_residual_relative} > {self.q_solve_limit}"
                    )
                q_residual_records.append(
                    {
                        "q": q,
                        "branch": branch,
                        "rows": int(modal_rhs.size),
                        "rhs_norm": modal_rhs_norm,
                        "true_residual_norm": modal_residual_norm,
                        "true_residual_relative": modal_residual_relative,
                        "limit": self.q_solve_limit,
                        "strict_limit": 1.0e-10,
                        "strict_passed": bool(modal_residual_relative <= 1.0e-10),
                        "bounded_inexact_only": bool(
                            modal_residual_relative > 1.0e-10
                            and modal_residual_relative <= self.q_solve_limit
                        ),
                    }
                )
                native_solution += np.asarray(q_map @ modal_solution, dtype=np.complex128)
            recovered = action.recover_storage(
                native_solution,
                full_rhs=local_rhs,
                expand_trace=False,
            )
            local_independent = recovered[local_independent_rows]
            result += transport.lift_primal(local_independent)
            alpha[ids] = native_solution[condensed.active_rows :] / np.sqrt(2.0)
            local_audit.append(
                {
                    "twist": context.twist_index,
                    "q_indices": list(context.global_q_indices),
                    "FE_rhs_norm": float(np.linalg.norm(local_rhs)),
                    "port_rhs_norm": float(np.linalg.norm(local_port_rhs)),
                    "reduced_solution_norm": float(np.linalg.norm(native_solution)),
                    "recovered_storage_norm": float(np.linalg.norm(recovered)),
                    "q_true_residuals": q_residual_records,
                    "maximum_q_true_residual_relative": max(
                        (row["true_residual_relative"] for row in q_residual_records),
                        default=0.0,
                    ),
                }
            )
        if not np.isfinite(result).all() or not np.isfinite(alpha).all():
            raise FloatingPointError("complete p6 two-cell recovery produced nonfinite values")
        self.last_port_solution = alpha.copy()
        self.last_local_solutions = None
        self.last_solve_audit = local_audit
        self.calls += 1
        return result, alpha

    def apply_array(self, rhs: Any) -> np.ndarray:
        return self.apply_augmented(rhs)[0]

    def destroy(self) -> None:
        self.last_port_solution = None
        self.last_local_solutions = None
        self.last_solve_audit = None
        self.sectors = ()
        self.layout = None
        self.factors = None
        self.destroyed = True


def trace_layout_coordinates(
    entities: YOrbitEntities,
    system: Any,
    *,
    cell_phase_y: complex,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> dict[str, Any]:
    """Restrict native entity maps to active trace rows and both local cells."""
    full = np.asarray(entities.independent, dtype=np.int64)
    active = np.asarray(system.trace_constraints.owned_active_original_dofs, dtype=np.int64)
    interior = np.concatenate(
        [cell.interior_original_dofs for cell in system.cell_recovery_maps]
    )
    if (
        entities.full_rows != system.full_rows
        or len(np.unique(active)) != system.active_rows
        or len(np.unique(interior)) != system.active_interior_rows
        or len(interior) != system.active_interior_rows
        or len(np.intersect1d(active, interior))
        or not np.array_equal(np.sort(np.concatenate((active, interior))), np.sort(full))
    ):
        raise ValueError("complete native p6 trace/interior/full-FE partition disagrees")
    if entities.ny != 2 or system.active_rows % 2:
        raise ValueError("local p6 trace must contain both complete y-cell orbits")
    if not callable(allocation_gate):
        raise TypeError("trace-coordinate construction requires the live allocation gate")

    active_row = {int(original): index for index, original in enumerate(active)}
    trace_bases = tuple(base for base in entities.bases if int(base[0]) in (1, 2))
    slots: dict[Any, tuple[int, int]] = {}
    width = 0
    for base in trace_bases:
        rows, _matrix = entities.records[(0, base)]
        slots[base] = (width, len(rows))
        width += len(rows)
    if width * entities.ny != system.active_rows:
        raise ValueError("complete local p6 trace entities do not cover all active rows")

    r_rows: list[int] = []
    r_cols: list[int] = []
    r_values: list[complex] = []
    ri_rows: list[int] = []
    ri_cols: list[int] = []
    ri_values: list[complex] = []
    for orbit in range(entities.ny):
        for base in trace_bases:
            native_rows, transform = entities.records[(orbit, base)]
            original_rows = entities.independent[np.asarray(native_rows, dtype=np.int64)]
            try:
                output_rows = np.asarray([active_row[int(value)] for value in original_rows])
            except KeyError as exc:
                raise ValueError("an edge/face entity is not entirely an active trace block") from exc
            first, size = slots[base]
            if transform.shape != (size, size):
                raise ValueError("trace entity transform has an inconsistent p6 block size")
            inverse = np.linalg.inv(transform)
            for i, row in enumerate(output_rows):
                for j in range(size):
                    value = transform[i, j]
                    inverse_value = inverse[j, i]
                    if value != 0:
                        r_rows.append(int(row))
                        r_cols.append(orbit * width + first + j)
                        r_values.append(complex(value))
                    if inverse_value != 0:
                        ri_rows.append(orbit * width + first + j)
                        ri_cols.append(int(row))
                        ri_values.append(complex(inverse_value))
    shape = (system.active_rows, entities.ny * width)
    allocation_gate(
        "task40_v10_p6_trace_entity_map",
        {
            "additional_payload_bytes": 16 * (len(r_values) + len(ri_values))
            + 8 * (len(r_rows) + len(r_cols) + len(ri_rows) + len(ri_cols)),
            "workspace_bytes": 16 * (system.active_rows + entities.ny * width),
            "trace_rows": system.active_rows,
            "trace_width": width,
        },
    )
    r_t = sparse.csr_matrix((r_values, (r_rows, r_cols)), shape=shape)
    r_inverse = sparse.csr_matrix(
        (ri_values, (ri_rows, ri_cols)), shape=(shape[1], shape[0])
    )
    eta = complex(cell_phase_y)
    if not np.isfinite(eta) or abs(abs(eta) - 1.0) > LIMITS["mapping"]:
        raise ValueError("local p6 cell eigenphase must be finite and unit modulus")
    f_rows: list[int] = []
    f_cols: list[int] = []
    f_values: list[complex] = []
    for orbit in range(entities.ny):
        for branch in range(entities.ny):
            value = eta * np.exp(2j * np.pi * branch / entities.ny)
            value = value**orbit / np.sqrt(entities.ny)
            for slot in range(width):
                f_rows.append(orbit * width + slot)
                f_cols.append(branch * width + slot)
                f_values.append(complex(value))
    f_t = sparse.csr_matrix(
        (f_values, (f_rows, f_cols)), shape=(entities.ny * width,) * 2
    )
    identity = sparse.eye(system.active_rows, dtype=np.complex128, format="csr")
    scale = np.sqrt(system.active_rows)
    defects = {
        "left_inverse_relative": float(sparse.linalg.norm(r_inverse @ r_t - identity) / scale),
        "right_inverse_relative": float(sparse.linalg.norm(r_t @ r_inverse - identity) / scale),
        "fourier_unitarity_relative": float(
            sparse.linalg.norm(f_t.conj().T @ f_t - sparse.eye(f_t.shape[0])) / scale
        ),
    }
    if any(not np.isfinite(value) or value > LIMITS["mapping"] for value in defects.values()):
        raise ValueError("native p6 trace/DFT inverse gate failed")
    return {
        "R_t": r_t,
        "R_t_inverse": r_inverse,
        "F_t": f_t,
        "trace_width": width,
        "ny": entities.ny,
        "audit": {
            **defects,
            "complete_trace_rows": system.active_rows,
            "primal_map": "Q_t=R_t F_t",
            "dual_map": "Q_t^H",
            "primal_inverse": "F_t^H R_t_inverse",
        },
    }


def build_task40_v10_sector_contexts(
    modes: tuple[Any, ...],
    cfg: Any,
    axes: Mapping[str, tuple[float, ...]],
    *,
    expected_q_counts: tuple[int, int, int, int] | None = None,
    expected_sector_counts: tuple[int, int] | None = None,
) -> tuple[Task40V10SectorContext, Task40V10SectorContext]:
    """Assign every frozen global mode to one of the four physical q phases."""
    dy = float(axes["y"][1] - axes["y"][0])
    expected = np.asarray(
        [
            np.exp(
                1j
                * (
                    complex(cfg.ky).real * float(cfg.period_y)
                    + 2 * np.pi * q
                )
                / 4
            )
            for q in range(4)
        ],
        dtype=np.complex128,
    )
    assignments = []
    for mode in modes:
        actual = np.exp(1j * complex(mode.gamma) * dy)
        errors = np.abs(expected - actual)
        q = int(np.argmin(errors))
        if not np.isfinite(actual) or errors[q] > 1e-12:
            raise ValueError(
                f"mode {getattr(mode, 'mode_key', None)!r} has no exact p6 cell q phase"
            )
        assignments.append(q)
    assignments = np.asarray(assignments, dtype=np.int8)
    counts = tuple(int(np.count_nonzero(assignments == q)) for q in range(4))
    if sum(counts) != len(modes):
        raise ValueError("global q phase assignment did not cover every physical mode")
    if expected_q_counts is not None and counts != expected_q_counts:
        raise ValueError(f"global q alias inventory mismatch: {counts}")
    contexts = []
    local_axes = {
        "x": tuple(map(float, axes["x"])),
        "y": tuple(map(float, axes["y"][:3])),
        "z": tuple(map(float, axes["z"])),
    }
    for twist in (0, 1):
        qids = (twist, twist + 2)
        indices = np.flatnonzero((assignments == qids[0]) | (assignments == qids[1]))
        branches = ((assignments[indices] - twist) // 2).astype(np.int8)
        eta = complex(expected[twist])
        alias_counts = None
        if expected_q_counts is not None:
            alias_counts = (expected_q_counts[qids[0]], expected_q_counts[qids[1]])
        contexts.append(
            Task40V10SectorContext(
                twist_index=twist,
                eta=eta,
                tau=eta**2,
                global_q_indices=qids,
                local_axes=local_axes,
                original_mode_indices=indices,
                local_branch_indices=branches,
                expected_alias_counts=alias_counts,
            )
        )
    actual_sector_counts = tuple(len(value.original_mode_indices) for value in contexts)
    if expected_sector_counts is not None and actual_sector_counts != expected_sector_counts:
        raise ValueError(f"p6 twist-sector port counts differ: {actual_sector_counts}")
    return tuple(contexts)


Q_ASSEMBLY_LEGACY = TASK40_Q_ASSEMBLY_LEGACY
Q_ASSEMBLY_PREALLOCATED_V13 = TASK40_Q_ASSEMBLY_PREALLOCATED_V13
Q_ASSEMBLY_BOUNDED_V16 = TASK40_Q_ASSEMBLY_BOUNDED_V16
Q_ASSEMBLY_STRATEGIES = TASK40_V13_Q_ASSEMBLY_STRATEGIES | frozenset(
    {Q_ASSEMBLY_BOUNDED_V16}
)
V16_Q_STAGING_BUDGET_BYTES = 256 * 1024**2
V16_PYTHON_OVERHEAD_RESERVE_BYTES = 32 * 1024**2
V16_PROJECTION_OVERHEAD_RESERVE_BYTES = V16_PYTHON_OVERHEAD_RESERVE_BYTES
V16_HHAT_BLOCK_COLUMNS = 64


class V16StagingLimitError(MemoryError):
    """A reviewed V16 bounded-staging gate stopped before exceeding its limit."""

    def __init__(self, label: str, required_bytes: int, limit_bytes: int) -> None:
        self.label = str(label)
        self.required_bytes = int(required_bytes)
        self.limit_bytes = int(limit_bytes)
        super().__init__(
            f"V16 staging limit at {self.label}: "
            f"required {self.required_bytes} bytes exceeds {self.limit_bytes} bytes"
        )

    def evidence(self) -> dict[str, Any]:
        return {
            "condition": "V16_BOUNDED_STAGING_LIMIT",
            "label": self.label,
            "required_bytes": self.required_bytes,
            "limit_bytes": self.limit_bytes,
        }


def _pattern_block_shapes(q_maps):
    return {
        (p, q): (int(q_maps[p].shape[1]), int(q_maps[q].shape[1]))
        for p in (0, 1)
        for q in (0, 1)
    }


def _selected_csr_nnz(matrix: sparse.csr_matrix, rows: np.ndarray) -> int:
    indptr = matrix.indptr
    return sum(int(indptr[int(row) + 1] - indptr[int(row)]) for row in rows)


def _accumulate_term_into_pattern(
    target: sparse.csr_matrix,
    term: sparse.csr_matrix,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    label: str,
) -> None:
    if target.shape != term.shape or not target.has_canonical_format:
        raise ValueError("preallocated q matrix pattern is not canonical or shape matched")
    index_bytes = int(target.indices.dtype.itemsize)
    allocation_gate(
        "task40_v13_q_pattern_value_accumulation/" + label,
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": 2 * int(term.nnz) * index_bytes,
            "term_nnz": int(term.nnz),
            "preallocated_target_nnz": int(target.nnz),
            "global_csr_reallocation": False,
        },
    )
    for row in range(term.shape[0]):
        term_start, term_end = int(term.indptr[row]), int(term.indptr[row + 1])
        if term_start == term_end:
            continue
        target_start, target_end = int(target.indptr[row]), int(target.indptr[row + 1])
        target_columns = target.indices[target_start:target_end]
        term_columns = term.indices[term_start:term_end]
        positions = np.searchsorted(target_columns, term_columns)
        if (
            np.any(positions >= len(target_columns))
            or not np.array_equal(target_columns[positions], term_columns)
        ):
            raise ValueError(f"q sparse pattern omitted a projected value at {label}")
        target.data[target_start + positions] += term.data[term_start:term_end]


def _assemble_preallocated_q_patterns(
    action: Any,
    q_maps: tuple[sparse.csr_matrix, sparse.csr_matrix],
    context: Task40V10SectorContext,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> tuple[dict[tuple[int, int], sparse.csr_matrix], dict[str, Any]]:
    import time

    shapes = _pattern_block_shapes(q_maps)
    container_rows = sum(shape[0] for shape in shapes.values())
    allocation_gate(
        "task40_v13_q_pattern_row_containers",
        {
            "additional_payload_bytes": 256 * int(container_rows),
            "workspace_bytes": 256 * int(container_rows),
            "row_set_count": int(container_rows),
            "allocation_semantics": "conservative Python set containers for one CSR pattern pass",
        },
    )
    row_columns = {
        key: [set() for _ in range(shape[0])] for key, shape in shapes.items()
    }
    pattern_started = time.perf_counter()
    layout_count = 0
    projected_superset_pairs = {key: 0 for key in shapes}

    for rows, columns, label in action.iter_reduced_contribution_layouts():
        rows = np.asarray(rows)
        columns = np.asarray(columns)
        if (
            rows.ndim != 1
            or columns.ndim != 1
            or rows.dtype.kind not in "iu"
            or columns.dtype.kind not in "iu"
            or (rows.size and (int(rows.min()) < 0 or int(rows.max()) >= q_maps[0].shape[0]))
            or (columns.size and (int(columns.min()) < 0 or int(columns.max()) >= q_maps[0].shape[0]))
        ):
            raise ValueError(f"invalid q pattern contribution layout {label}")
        layout_count += 1
        for p in (0, 1):
            left = q_maps[p]
            left_nnz = _selected_csr_nnz(left, rows)
            for q in (0, 1):
                right = q_maps[q]
                right_nnz = _selected_csr_nnz(right, columns)
                row_ptr_bytes = (len(rows) + len(columns) + 2) * int(left.indptr.dtype.itemsize)
                support_workspace = (
                    left_nnz * (int(left.data.dtype.itemsize) + int(left.indices.dtype.itemsize))
                    + right_nnz * (int(right.data.dtype.itemsize) + int(right.indices.dtype.itemsize))
                    + row_ptr_bytes
                    + (left_nnz + right_nnz) * int(left.indices.dtype.itemsize)
                )
                allocation_gate(
                    "task40_v13_q_pattern_support/" + str(label) + f"/p{p}q{q}",
                    {
                        "additional_payload_bytes": 0,
                        "workspace_bytes": support_workspace,
                        "selected_left_nnz_upper": left_nnz,
                        "selected_right_nnz_upper": right_nnz,
                        "metadata_only_no_local_schur_solve": True,
                    },
                )
                left_rows = left[rows, :].tocsr()
                right_rows = right[columns, :].tocsr()
                left_support = np.unique(left_rows.indices)
                right_support = np.unique(right_rows.indices)
                block_rows = row_columns[p, q]
                new_entries = sum(
                    1
                    for row in left_support
                    for column in right_support
                    if int(column) not in block_rows[int(row)]
                )
                allocation_gate(
                    "task40_v13_q_pattern_entries/" + str(label) + f"/p{p}q{q}",
                    {
                        "additional_payload_bytes": 128 * int(new_entries),
                        "workspace_bytes": 0,
                        "new_structural_entries_upper": int(new_entries),
                        "support_rows": int(len(left_support)),
                        "support_columns": int(len(right_support)),
                        "pattern_is_conservative_superset": True,
                    },
                )
                for row in left_support:
                    block_rows[int(row)].update(map(int, right_support))
                projected_superset_pairs[p, q] += int(len(left_support) * len(right_support))
                del left_rows, right_rows, left_support, right_support
        del rows, columns

    pattern_seconds = time.perf_counter() - pattern_started
    pattern_entries = {
        key: sum(len(columns) for columns in rows)
        for key, rows in row_columns.items()
    }
    index_dtype = np.int32 if max(max(shape) for shape in shapes.values()) < (1 << 31) else np.int64
    index_bytes = int(np.dtype(index_dtype).itemsize)
    total_pattern_bytes = sum(
        nnz * (index_bytes + np.dtype(np.complex128).itemsize)
        + (shapes[key][0] + 1) * index_bytes
        for key, nnz in pattern_entries.items()
    )
    max_row_entries = max(
        (len(columns) for rows in row_columns.values() for columns in rows), default=0
    )
    allocation_gate(
        "task40_v13_q_pattern_csr_materialization",
        {
            "additional_payload_bytes": int(total_pattern_bytes),
            "workspace_bytes": int(32 * max_row_entries),
            "pattern_payload_bytes": int(total_pattern_bytes),
            "row_set_python_overhead_already_live": True,
            "pattern_entries_by_block": {f"{p}{q}": int(value) for (p, q), value in pattern_entries.items()},
        },
    )
    blocks: dict[tuple[int, int], sparse.csr_matrix] = {}
    for key, shape in shapes.items():
        rows = row_columns[key]
        nnz = pattern_entries[key]
        if nnz > int(np.iinfo(index_dtype).max):
            raise OverflowError("Task40 V13 q pattern exceeds its CSR index dtype")
        indptr = np.empty(shape[0] + 1, dtype=index_dtype)
        indptr[0] = 0
        for row, columns in enumerate(rows):
            indptr[row + 1] = indptr[row] + len(columns)
        indices = np.empty(nnz, dtype=index_dtype)
        data = np.zeros(nnz, dtype=np.complex128)
        cursor = 0
        for columns in rows:
            ordered = sorted(columns)
            count = len(ordered)
            indices[cursor : cursor + count] = ordered
            cursor += count
        blocks[key] = sparse.csr_matrix(
            (data, indices, indptr), shape=shape, copy=False
        )
    del row_columns

    numeric_started = time.perf_counter()
    numeric_contribution_count = 0
    contribution_generation_seconds = 0.0
    local_projection_seconds = 0.0
    global_accumulation_seconds = 0.0
    projection_call_count = 0
    accumulation_call_count = 0
    contribution_iterator = iter(
        action.iter_reduced_contributions(allocation_gate=allocation_gate)
    )
    while True:
        generation_started = time.perf_counter()
        try:
            rows, columns, values, label = next(contribution_iterator)
        except StopIteration:
            break
        contribution_generation_seconds += time.perf_counter() - generation_started
        numeric_contribution_count += 1
        for p in (0, 1):
            for q in (0, 1):
                projection_started = time.perf_counter()
                term = project_reduced_contribution(
                    q_maps[p],
                    q_maps[q],
                    rows,
                    columns,
                    values,
                    allocation_gate=allocation_gate,
                    label=f"{label}/p{p}q{q}",
                )
                local_projection_seconds += time.perf_counter() - projection_started
                projection_call_count += 1
                accumulation_started = time.perf_counter()
                _accumulate_term_into_pattern(
                    blocks[p, q],
                    term,
                    allocation_gate=allocation_gate,
                    label=f"{label}/p{p}q{q}",
                )
                global_accumulation_seconds += time.perf_counter() - accumulation_started
                accumulation_call_count += 1
                del term
        del rows, columns, values

    numeric_seconds = time.perf_counter() - numeric_started
    return blocks, {
        "assembly_strategy": Q_ASSEMBLY_PREALLOCATED_V13,
        "pattern_layout_count": layout_count,
        "numeric_contribution_count": numeric_contribution_count,
        "pattern_entries_by_block": {f"{p}{q}": int(value) for (p, q), value in pattern_entries.items()},
        "projected_superset_pairs_by_block": {
            f"{p}{q}": int(value) for (p, q), value in projected_superset_pairs.items()
        },
        "pattern_seconds": float(pattern_seconds),
        "numeric_projection_and_accumulation_seconds": float(numeric_seconds),
        "contribution_generation_seconds": float(contribution_generation_seconds),
        "local_projection_seconds": float(local_projection_seconds),
        "global_sparse_accumulation_seconds": float(global_accumulation_seconds),
        "local_projection_call_count": projection_call_count,
        "global_sparse_accumulation_call_count": accumulation_call_count,
        "global_csr_reallocations_during_numeric_pass": 0,
        "conservative_pattern_preserves_all_contribution_values": True,
    }


def _v16_csr_payload_bytes(matrix: sparse.csr_matrix) -> int:
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _v16_layout_array_bytes(rows: np.ndarray, columns: np.ndarray) -> int:
    return int(rows.nbytes + columns.nbytes)


def _v16_checked_csr_layout(
    shape: tuple[int, int], row_counts: Any
) -> tuple[int, int]:
    """Check all int32 CSR bounds with Python integers before CSR allocation."""
    rows, columns = (int(shape[0]), int(shape[1]))
    limit = int(np.iinfo(np.int32).max)
    if min(rows, columns) < 0 or max(rows, columns) > limit:
        raise OverflowError("V16 CSR shape exceeds qualified PETSc int32 range")
    total_nnz = 0
    for row, raw_count in enumerate(row_counts):
        count = int(raw_count)
        if count < 0 or count > columns:
            raise ValueError(f"V16 CSR row {row} count is outside its column range")
        total_nnz += count
        if total_nnz > limit:
            raise OverflowError("V16 CSR NNZ/indptr exceeds qualified PETSc int32 range")
    csr_payload = (rows + 1) * np.dtype(np.int32).itemsize + total_nnz * (
        np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize
    )
    return total_nnz, int(csr_payload)


def _assemble_v16_bitset_pattern(
    action: Any,
    q_maps: tuple[sparse.csr_matrix, sparse.csr_matrix],
    block_key: tuple[int, int],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> tuple[sparse.csr_matrix, dict[str, Any]]:
    """Build one conservative CSR pattern with one bounded row bitset.

    A bit is a structural column in one row. Only one q-block bitset is live
    at once; four final CSR matrices are accounted separately from staging.
    This avoids both V13's Python row sets and a contribution-wide COO list.
    """
    p, q = block_key
    left, right = q_maps[p], q_maps[q]
    shape = (int(left.shape[1]), int(right.shape[1]))
    int32_limit = int(np.iinfo(np.int32).max)
    if max(shape) > int32_limit:
        raise OverflowError("V16 q block shape exceeds qualified PETSc int32 range")
    byte_columns = (shape[1] + 7) // 8
    bitset_bytes = int(shape[0] * byte_columns)
    reserve = V16_PYTHON_OVERHEAD_RESERVE_BYTES
    if bitset_bytes + reserve > V16_Q_STAGING_BUDGET_BYTES:
        raise V16StagingLimitError(
            f"pattern_bitset/p{p}q{q}",
            bitset_bytes + reserve,
            V16_Q_STAGING_BUDGET_BYTES,
        )
    allocation_gate(
        f"task40_v16_q_pattern_bitset/p{p}q{q}",
        {
            "additional_payload_bytes": bitset_bytes,
            "workspace_bytes": reserve,
            "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
            "staging_live_bytes_upper": bitset_bytes + reserve,
            "pattern_shape": list(shape),
            "pattern_bitset_bytes": bitset_bytes,
            "python_overhead_reserve_bytes": reserve,
            "pattern_representation": "one_uint8_row_bitset_for_one_q_block",
        },
    )
    pattern = np.zeros((shape[0], byte_columns), dtype=np.uint8)
    pattern_started = __import__("time").perf_counter()
    layout_count = 0
    projected_superset_pairs = 0
    peak_staging = bitset_bytes + reserve
    index_bytes = max(int(left.indices.dtype.itemsize), int(right.indices.dtype.itemsize))

    for rows, columns, label in action.iter_reduced_contribution_layouts(
        hhat_block_columns=V16_HHAT_BLOCK_COLUMNS
    ):
        rows = np.asarray(rows)
        columns = np.asarray(columns)
        if (
            rows.ndim != 1
            or columns.ndim != 1
            or rows.dtype.kind not in "iu"
            or columns.dtype.kind not in "iu"
            or (rows.size and (int(rows.min()) < 0 or int(rows.max()) >= left.shape[0]))
            or (columns.size and (int(columns.min()) < 0 or int(columns.max()) >= right.shape[0]))
        ):
            raise ValueError(f"invalid V16 q pattern contribution layout {label}")
        layout_count += 1
        left_nnz = _selected_csr_nnz(left, rows)
        right_nnz = _selected_csr_nnz(right, columns)
        left_slice_bytes = left_nnz * (
            int(left.data.dtype.itemsize) + int(left.indices.dtype.itemsize)
        ) + (len(rows) + 1) * int(left.indptr.dtype.itemsize)
        right_slice_bytes = right_nnz * (
            int(right.data.dtype.itemsize) + int(right.indices.dtype.itemsize)
        ) + (len(columns) + 1) * int(right.indptr.dtype.itemsize)
        support_scratch = (
            4 * (left_nnz + right_nnz) * index_bytes
            + 2 * right_nnz * index_bytes
            + right_nnz
            + _v16_layout_array_bytes(rows, columns)
            + reserve
        )
        live_staging = bitset_bytes + left_slice_bytes + right_slice_bytes + support_scratch
        peak_staging = max(peak_staging, live_staging)
        if live_staging > V16_Q_STAGING_BUDGET_BYTES:
            raise V16StagingLimitError(
                f"pattern_support/p{p}q{q}/{label}",
                live_staging,
                V16_Q_STAGING_BUDGET_BYTES,
            )
        allocation_gate(
            f"task40_v16_q_pattern_support/{label}/p{p}q{q}",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": left_slice_bytes + right_slice_bytes + support_scratch,
                "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
                "staging_live_bytes_upper": live_staging,
                "selected_left_nnz_upper": left_nnz,
                "selected_right_nnz_upper": right_nnz,
                "metadata_only_no_local_schur_solve": True,
            },
        )
        left_rows = left[rows, :].tocsr()
        right_rows = right[columns, :].tocsr()
        left_support = np.unique(left_rows.indices)
        right_support = np.unique(right_rows.indices)
        byte_ids = np.right_shift(right_support, 3)
        bit_values = np.left_shift(
            np.uint8(1), np.bitwise_and(right_support, 7).astype(np.uint8, copy=False)
        )
        for row in left_support:
            np.bitwise_or.at(pattern[int(row)], byte_ids, bit_values)
        projected_superset_pairs += int(len(left_support) * len(right_support))
        del left_rows, right_rows, left_support, right_support, byte_ids, bit_values
        del rows, columns

    pattern_seconds = __import__("time").perf_counter() - pattern_started
    row_count_bytes = 4 * shape[0]
    row_decode_scratch = byte_columns + shape[1] + 8 * shape[1]
    row_stage = bitset_bytes + row_count_bytes + row_decode_scratch + reserve
    peak_staging = max(peak_staging, row_stage)
    if row_stage > V16_Q_STAGING_BUDGET_BYTES:
        raise V16StagingLimitError(
            f"pattern_row_counts/p{p}q{q}",
            row_stage,
            V16_Q_STAGING_BUDGET_BYTES,
        )
    allocation_gate(
        f"task40_v16_q_pattern_row_counts/p{p}q{q}",
        {
            "additional_payload_bytes": row_count_bytes,
            "workspace_bytes": row_decode_scratch + reserve,
            "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
            "staging_live_bytes_upper": row_stage,
            "row_count_dtype": "int32",
            "row_decode_strategy": "one_row_unpackbits_at_a_time",
        },
    )
    row_counts = np.empty(shape[0], dtype=np.int32)
    for row in range(shape[0]):
        unpacked = np.unpackbits(pattern[row], bitorder="little", count=shape[1])
        count = int(np.count_nonzero(unpacked))
        if count > int(np.iinfo(np.int32).max):
            raise OverflowError("V16 CSR row count exceeds signed int32 range")
        row_counts[row] = count
        del unpacked
    # The qualified Task40 PETSc ABI is signed int32. Check shape, every
    # Python-int prefix sum, total NNZ, and indptr endpoint before CSR arrays.
    total_nnz, csr_payload = _v16_checked_csr_layout(shape, row_counts)
    index_dtype = np.int32
    index_limit = int(np.iinfo(index_dtype).max)
    final_stage = bitset_bytes + row_count_bytes + row_decode_scratch + reserve
    peak_staging = max(peak_staging, final_stage)
    if final_stage > V16_Q_STAGING_BUDGET_BYTES:
        raise V16StagingLimitError(
            f"pattern_csr_materialization/p{p}q{q}",
            final_stage,
            V16_Q_STAGING_BUDGET_BYTES,
        )
    allocation_gate(
        f"task40_v16_q_pattern_csr_materialization/p{p}q{q}",
        {
            "additional_payload_bytes": csr_payload,
            "workspace_bytes": row_count_bytes + row_decode_scratch + reserve,
            "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
            "staging_live_bytes_upper": final_stage,
            "pattern_payload_bytes": csr_payload,
            "pattern_nnz": total_nnz,
            "row_set_count": 0,
            "full_coo_list_count": 0,
        },
    )
    indptr = np.empty(shape[0] + 1, dtype=index_dtype)
    indptr[0] = 0
    running = 0
    for row, count in enumerate(row_counts):
        running += int(count)
        indptr[row + 1] = running
    indices = np.empty(total_nnz, dtype=index_dtype)
    data = np.zeros(total_nnz, dtype=np.complex128)
    for row in range(shape[0]):
        unpacked = np.unpackbits(pattern[row], bitorder="little", count=shape[1])
        columns = np.flatnonzero(unpacked)
        start, stop = int(indptr[row]), int(indptr[row + 1])
        if len(columns) != stop - start:
            raise RuntimeError("V16 CSR row expansion differs from its checked row count")
        if columns.size and int(columns.max()) > index_limit:
            raise OverflowError("V16 CSR column index exceeds its selected dtype")
        indices[start:stop] = columns
        del unpacked, columns
    matrix = sparse.csr_matrix((data, indices, indptr), shape=shape, copy=False)
    if not matrix.has_canonical_format or not matrix.has_sorted_indices:
        raise RuntimeError("V16 bitset pattern did not produce canonical sorted CSR")
    return matrix, {
        "layout_count": layout_count,
        "pattern_nnz": total_nnz,
        "pattern_payload_bytes": csr_payload,
        "pattern_bitset_bytes": bitset_bytes,
        "projected_superset_pairs": projected_superset_pairs,
        "pattern_seconds": float(pattern_seconds),
        "staging_peak_bytes": int(peak_staging),
        "index_dtype": np.dtype(index_dtype).str,
    }



def _project_accumulate_v16(
    target: sparse.csr_matrix,
    left: sparse.csr_matrix,
    right: sparse.csr_matrix,
    rows: np.ndarray,
    columns: np.ndarray,
    values: np.ndarray,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    label: str,
) -> tuple[float, float, int]:
    """Project one local contribution and add only its nonempty rows to CSR."""
    import time

    rows = np.asarray(rows)
    columns = np.asarray(columns)
    values = np.asarray(values)
    if (
        rows.ndim != 1
        or columns.ndim != 1
        or rows.dtype.kind not in "iu"
        or columns.dtype.kind not in "iu"
        or values.shape != (len(rows), len(columns))
        or values.dtype != np.dtype(np.complex128)
        or not np.isfinite(values).all()
        or (len(rows) and (int(rows.min()) < 0 or int(rows.max()) >= left.shape[0]))
        or (len(columns) and (int(columns.min()) < 0 or int(columns.max()) >= right.shape[0]))
    ):
        raise ValueError(f"invalid V16 p6 contribution {label}")
    if target.shape != (left.shape[1], right.shape[1]) or not target.has_canonical_format:
        raise ValueError("V16 target CSR is not canonical or shape matched")

    left_nnz = _selected_csr_nnz(left, rows)
    right_nnz = _selected_csr_nnz(right, columns)
    left_index_bytes = int(left.indices.dtype.itemsize)
    right_index_bytes = int(right.indices.dtype.itemsize)
    left_payload = left_nnz * (int(left.data.dtype.itemsize) + left_index_bytes) + (
        len(rows) + 1
    ) * int(left.indptr.dtype.itemsize)
    right_payload = right_nnz * (int(right.data.dtype.itemsize) + right_index_bytes) + (
        len(columns) + 1
    ) * int(right.indptr.dtype.itemsize)
    left_support = min(int(left.shape[1]), left_nnz)
    right_support = min(int(right.shape[1]), right_nnz)
    index_bytes = max(left_index_bytes, right_index_bytes, int(target.indices.dtype.itemsize))
    support_scratch = 4 * (left_nnz + right_nnz) * index_bytes
    support_scratch += 2 * (left_nnz + right_nnz) * 8
    dense_workspace = 16 * (
        2 * len(rows) * left_support
        + left_support * len(columns)
        + len(columns) * right_support
        + left_support * right_support
    )
    row_index_scratch = right_support * (
        3 * np.dtype(np.intp).itemsize + int(target.indices.dtype.itemsize) + 1 + 16
    ) + 128
    staging = (
        int(values.nbytes)
        + _v16_layout_array_bytes(rows, columns)
        + left_payload
        + right_payload
        + support_scratch
        + dense_workspace
        + row_index_scratch
        + V16_PROJECTION_OVERHEAD_RESERVE_BYTES
    )
    if staging > V16_Q_STAGING_BUDGET_BYTES:
        raise V16StagingLimitError(
            f"projection/{label}", staging, V16_Q_STAGING_BUDGET_BYTES
        )
    allocation_gate(
        "task40_v16_q_projection_support/" + label,
        {
            "additional_payload_bytes": 0,
            "workspace_bytes": staging,
            "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
            "staging_live_bytes_upper": staging,
            "selected_left_nnz_upper": left_nnz,
            "selected_right_nnz_upper": right_nnz,
            "left_support_upper": left_support,
            "right_support_upper": right_support,
            "projection_algorithm": "one_local_dense_projection_then_direct_nonempty_csr_rows",
            "includes_left_conjugate_copy": True,
            "includes_matmul_intermediate_and_local_term_temporaries": True,
        },
    )

    left_rows = left[rows, :].tocsr()
    right_rows = right[columns, :].tocsr()
    left_support_ids = np.unique(left_rows.indices)
    right_support_ids = np.unique(right_rows.indices)
    if not len(left_support_ids) or not len(right_support_ids):
        return 0.0, 0.0, staging

    projection_started = time.perf_counter()
    left_dense = left_rows[:, left_support_ids].toarray()
    right_dense = right_rows[:, right_support_ids].toarray()
    left_conjugate = left_dense.conj()
    left_product = left_conjugate.T @ values
    projected = left_product @ right_dense
    projection_seconds = time.perf_counter() - projection_started
    del left_rows, right_rows, left_dense, right_dense, left_conjugate, left_product

    accumulation_started = time.perf_counter()
    for local_row, global_row_value in enumerate(left_support_ids):
        row_values = projected[local_row]
        nonzero_columns = np.flatnonzero(row_values)
        if not len(nonzero_columns):
            continue
        global_columns = right_support_ids[nonzero_columns]
        target_start = int(target.indptr[int(global_row_value)])
        target_stop = int(target.indptr[int(global_row_value) + 1])
        target_columns = target.indices[target_start:target_stop]
        positions = np.searchsorted(target_columns, global_columns)
        if (
            np.any(positions >= len(target_columns))
            or not np.array_equal(target_columns[positions], global_columns)
        ):
            raise ValueError(
                f"V16 q bitset pattern omitted a projected value at {label}"
            )
        target.data[target_start + positions] += row_values[nonzero_columns]
        del nonzero_columns, global_columns, positions
    accumulation_seconds = time.perf_counter() - accumulation_started
    del projected, left_support_ids, right_support_ids
    return projection_seconds, accumulation_seconds, staging


def _assemble_bounded_v16_q_patterns(
    action: Any,
    q_maps: tuple[sparse.csr_matrix, sparse.csr_matrix],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> tuple[dict[tuple[int, int], sparse.csr_matrix], dict[str, Any]]:
    """Bounded V16 pattern staging followed by direct CSR value accumulation."""
    import time

    blocks: dict[tuple[int, int], sparse.csr_matrix] = {}
    patterns: dict[str, Any] = {}
    pattern_started = time.perf_counter()
    for key in ((0, 0), (0, 1), (1, 0), (1, 1)):
        matrix, facts = _assemble_v16_bitset_pattern(
            action, q_maps, key, allocation_gate=allocation_gate
        )
        blocks[key] = matrix
        patterns[f"{key[0]}{key[1]}"] = facts
    pattern_seconds = time.perf_counter() - pattern_started

    numeric_started = time.perf_counter()
    contribution_generation_seconds = 0.0
    projection_seconds = 0.0
    accumulation_seconds = 0.0
    contribution_count = 0
    projection_call_count = 0
    accumulation_call_count = 0
    numeric_staging_peak = 0
    contribution_staging_peak = 0

    def v16_contribution_gate(label: str, facts: Mapping[str, Any]) -> None:
        nonlocal contribution_staging_peak
        payload = int(facts.get("matrix_payload_bytes", facts.get("additional_payload_bytes", 0)))
        workspace = int(facts.get("workspace_bytes", 0))
        staging = payload + workspace + V16_PYTHON_OVERHEAD_RESERVE_BYTES
        contribution_staging_peak = max(contribution_staging_peak, staging)
        if staging > V16_Q_STAGING_BUDGET_BYTES:
            raise V16StagingLimitError(
                label, staging, V16_Q_STAGING_BUDGET_BYTES
            )
        allocation_gate(
            label,
            {
                **dict(facts),
                "staging_budget_bytes": V16_Q_STAGING_BUDGET_BYTES,
                "staging_live_bytes_upper": staging,
                "python_overhead_reserve_bytes": V16_PYTHON_OVERHEAD_RESERVE_BYTES,
            },
        )

    contribution_iterator = iter(
        action.iter_reduced_contributions(
            allocation_gate=v16_contribution_gate,
            hhat_block_columns=V16_HHAT_BLOCK_COLUMNS,
        )
    )
    while True:
        generation_started = time.perf_counter()
        try:
            rows, columns, values, label = next(contribution_iterator)
        except StopIteration:
            break
        contribution_generation_seconds += time.perf_counter() - generation_started
        contribution_count += 1
        for p in (0, 1):
            for q in (0, 1):
                projection_s, accumulation_s, staging_peak = _project_accumulate_v16(
                    blocks[p, q],
                    q_maps[p],
                    q_maps[q],
                    rows,
                    columns,
                    values,
                    allocation_gate=allocation_gate,
                    label=f"{label}/p{p}q{q}",
                )
                projection_seconds += projection_s
                accumulation_seconds += accumulation_s
                numeric_staging_peak = max(numeric_staging_peak, staging_peak)
                projection_call_count += 1
                accumulation_call_count += 1
        del rows, columns, values

    stored_pattern_slots = {
        f"{p}{q}": int(matrix.nnz) for (p, q), matrix in blocks.items()
    }
    numeric_nonzero_entries = {
        f"{p}{q}": int(np.count_nonzero(matrix.data))
        for (p, q), matrix in blocks.items()
    }
    exact_zero_slots_retained = {
        key: int(stored_pattern_slots[key] - numeric_nonzero_entries[key])
        for key in stored_pattern_slots
    }
    # Keep the preallocated backing arrays unchanged. SciPy's prune may retain
    # the old owner or copy depending on its size heuristic; that copy path has
    # not been admitted here, so report exact zeros and stored owners separately.
    final_nnz = {
        f"{p}{q}": int(matrix.nnz) for (p, q), matrix in blocks.items()
    }
    final_csr_bytes = {
        f"{p}{q}": _v16_csr_payload_bytes(matrix)
        for (p, q), matrix in blocks.items()
    }
    numeric_parent_seconds = float(time.perf_counter() - numeric_started)
    max_staging = max(
        max(int(row["staging_peak_bytes"]) for row in patterns.values()),
        contribution_staging_peak,
        numeric_staging_peak,
    )
    if max_staging > V16_Q_STAGING_BUDGET_BYTES:
        raise V16StagingLimitError(
            "four_block_peak", max_staging, V16_Q_STAGING_BUDGET_BYTES
        )
    return blocks, {
        "assembly_strategy": Q_ASSEMBLY_BOUNDED_V16,
        "pattern_algorithm": "one_row_bitset_per_q_block_then_direct_preallocated_csr_accumulation",
        "staging_budget_bytes_total_all_q_blocks": V16_Q_STAGING_BUDGET_BYTES,
        "staging_budget_scope": "maximum_concurrent_across_all_four_blocks_including_support_and_projection_temporaries",
        "pattern_seconds": float(pattern_seconds),
        "numeric_parent_seconds": numeric_parent_seconds,
        "pattern_stage_peak_bytes_by_block": {
            key: int(value["staging_peak_bytes"]) for key, value in patterns.items()
        },
        "contribution_generation_stage_peak_bytes": int(contribution_staging_peak),
        "projection_stage_peak_bytes": int(numeric_staging_peak),
        "staging_peak_bytes_total_all_blocks": int(max_staging),
        "pattern_facts_by_block": patterns,
        "final_csr_payload_bytes_by_block": final_csr_bytes,
        "final_csr_payload_bytes_total": int(sum(final_csr_bytes.values())),
        "stored_pattern_slots_by_block": stored_pattern_slots,
        "numeric_nonzero_entries_by_block": numeric_nonzero_entries,
        "exact_zero_slots_retained_by_block": exact_zero_slots_retained,
        "final_nnz_by_block": final_nnz,
        "exact_zero_cleanup": "not_applied; original CSR backing arrays retained",
        "no_compaction_owner_copy_created": True,
        "flush_merge_temporary_bytes": 0,
        "full_coo_list_count": 0,
        "python_row_set_count": 0,
        "global_csr_reallocations_during_numeric_pass": 0,
        "numeric_contribution_count": contribution_count,
        "numeric_projection_and_accumulation_seconds": numeric_parent_seconds,
        "contribution_generation_seconds": float(contribution_generation_seconds),
        "local_projection_seconds": float(projection_seconds),
        "global_sparse_accumulation_seconds": float(accumulation_seconds),
        "local_projection_call_count": projection_call_count,
        "global_sparse_accumulation_call_count": accumulation_call_count,
        "block_shapes": {
            f"{p}{q}": list(matrix.shape) for (p, q), matrix in blocks.items()
        },
        "timing_scope": {
            "assembly_total_seconds": "parent interval including q-map construction and bounded pattern generation",
            "pattern_seconds": "pattern metadata/pattern CSR parent interval, outside numeric_parent_seconds",
            "numeric_parent_seconds": "parent interval including contribution generation, projection, accumulation, exact-zero cleanup, and loop overhead",
            "child_intervals_are_nonoverlapping_and_already_inside_numeric_parent": True,
            "parent_and_child_intervals_must_not_be_added": True,
        },
    }
def assemble_task40_v10_sector_blocks(
    action: Any,
    coordinates: TwoCellBranchCoordinates,
    context: Task40V10SectorContext,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    assembly_strategy: str = Q_ASSEMBLY_LEGACY,
    return_all_blocks: bool = False,
) -> tuple[dict[Any, sparse.csr_matrix], dict[str, Any]]:
    """Assemble all four q blocks using the explicit legacy, V13, or V16 strategy."""
    import time

    if not callable(allocation_gate):
        raise TypeError("q-block assembly requires the live allocation gate")
    if assembly_strategy not in Q_ASSEMBLY_STRATEGIES:
        raise ValueError(f"unknown Task40 q assembly strategy: {assembly_strategy!r}")
    started = time.perf_counter()
    q_maps = tuple(
        coordinates.q_map(branch, allocation_gate=allocation_gate)
        for branch in (0, 1)
    )
    if assembly_strategy == Q_ASSEMBLY_BOUNDED_V16:
        blocks, strategy_audit = _assemble_bounded_v16_q_patterns(
            action, q_maps, allocation_gate=allocation_gate
        )
    elif assembly_strategy == Q_ASSEMBLY_PREALLOCATED_V13:
        blocks, strategy_audit = _assemble_preallocated_q_patterns(
            action, q_maps, context, allocation_gate=allocation_gate
        )
    else:
        blocks: dict[tuple[int, int], sparse.csr_matrix] = {}
        for p in (0, 1):
            for q in (0, 1):
                blocks[p, q] = sparse.csr_matrix(
                    (q_maps[p].shape[1], q_maps[q].shape[1]),
                    dtype=np.complex128,
                )
        numeric_started = time.perf_counter()
        contribution_count = 0
        contribution_generation_seconds = 0.0
        local_projection_seconds = 0.0
        global_accumulation_seconds = 0.0
        projection_call_count = 0
        accumulation_call_count = 0
        contribution_iterator = iter(
            action.iter_reduced_contributions(allocation_gate=allocation_gate)
        )
        while True:
            generation_started = time.perf_counter()
            try:
                rows, columns, values, label = next(contribution_iterator)
            except StopIteration:
                break
            contribution_generation_seconds += time.perf_counter() - generation_started
            contribution_count += 1
            for p in (0, 1):
                for q in (0, 1):
                    projection_started = time.perf_counter()
                    term = project_reduced_contribution(
                        q_maps[p],
                        q_maps[q],
                        rows,
                        columns,
                        values,
                        allocation_gate=allocation_gate,
                        label=f"{label}/p{p}q{q}",
                    )
                    local_projection_seconds += time.perf_counter() - projection_started
                    projection_call_count += 1
                    accumulation_started = time.perf_counter()
                    blocks[p, q] = (blocks[p, q] + term).tocsr()
                    global_accumulation_seconds += time.perf_counter() - accumulation_started
                    accumulation_call_count += 1
                    del term
            del rows, columns, values
        strategy_audit = {
            "assembly_strategy": Q_ASSEMBLY_LEGACY,
            "numeric_contribution_count": contribution_count,
            "numeric_projection_and_accumulation_seconds": float(
                time.perf_counter() - numeric_started
            ),
            "contribution_generation_seconds": float(contribution_generation_seconds),
            "local_projection_seconds": float(local_projection_seconds),
            "global_sparse_accumulation_seconds": float(global_accumulation_seconds),
            "local_projection_call_count": projection_call_count,
            "global_sparse_accumulation_call_count": accumulation_call_count,
            "global_csr_reallocation_count_upper": 4 * contribution_count,
        }

    diagonal_scale = max(
        sparse.linalg.norm(blocks[0, 0]),
        sparse.linalg.norm(blocks[1, 1]),
        np.finfo(float).tiny,
    )
    off_diagonal = {
        "q0_q1_relative": float(sparse.linalg.norm(blocks[0, 1]) / diagonal_scale),
        "q1_q0_relative": float(sparse.linalg.norm(blocks[1, 0]) / diagonal_scale),
    }
    if max(off_diagonal.values()) > LIMITS["operator"]:
        raise ValueError(f"regular p6 action is not diagonal in local q branches: {off_diagonal}")
    result = {
        int(context.global_q_indices[branch]): blocks[branch, branch]
        for branch in (0, 1)
    }
    for q, matrix in result.items():
        if q not in range(4) or matrix.shape[0] != matrix.shape[1]:
            raise ValueError(f"global q={q} augmented matrix shape mismatch: {matrix.shape}")
        if not matrix.has_canonical_format or not np.isfinite(matrix.data).all():
            raise ValueError(f"global q={q} matrix is not finite canonical CSR")

    audit = {
        "global_q_indices": list(context.global_q_indices),
        "block_shapes": {
            f"{p}{q}": list(blocks[p, q].shape)
            for p in (0, 1)
            for q in (0, 1)
        },
        "off_diagonal_relative": off_diagonal,
        "all_internal_channels_retained": True,
        "fourier_diagonalization_passed": True,
        "assembly_total_seconds": float(time.perf_counter() - started),
        "timing_scope": {
            "assembly_total_seconds": "parent interval including q-map construction and selected strategy",
            "numeric_projection_and_accumulation_seconds": "parent numeric interval including contribution generation, local projection, sparse accumulation, and loop overhead",
            "child_intervals_are_nonoverlapping_and_already_inside_numeric_parent": True,
            "pattern_seconds": "candidate-only pattern metadata and CSR construction before numeric contribution traversal",
        },
        **strategy_audit,
    }
    if return_all_blocks:
        return blocks, audit
    return result, audit


def compare_task40_v10_sector_assembly(
    action: Any,
    coordinates: TwoCellBranchCoordinates,
    context: Task40V10SectorContext,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    candidate_strategy: str = Q_ASSEMBLY_PREALLOCATED_V13,
) -> dict[str, Any]:
    """Compare legacy CSR with one registered candidate without co-retaining oracles."""
    import gc
    import hashlib
    import tempfile
    import time
    from pathlib import Path

    from scipy.linalg.blas import dznrm2

    if not callable(allocation_gate):
        raise TypeError("q-block comparison requires a live allocation gate")
    if candidate_strategy not in {Q_ASSEMBLY_PREALLOCATED_V13, Q_ASSEMBLY_BOUNDED_V16}:
        raise ValueError(f"unsupported q-assembly comparison strategy: {candidate_strategy!r}")
    candidate_version = "v16" if candidate_strategy == Q_ASSEMBLY_BOUNDED_V16 else "v13"
    pair_started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix=f"task40-{candidate_version}-q-assembly-pair-") as scratch:
        scratch_path = Path(scratch)
        legacy, legacy_audit = assemble_task40_v10_sector_blocks(
            action,
            coordinates,
            context,
            allocation_gate=allocation_gate,
            assembly_strategy=Q_ASSEMBLY_LEGACY,
            return_all_blocks=True,
        )
        candidate_free_memory_payload = 0
        legacy_payload = 0
        legacy_hashes = {}
        scratch_bytes = 0
        block_keys = tuple((p, q) for p in (0, 1) for q in (0, 1))
        for p, q in block_keys:
            matrix = legacy[p, q]
            if not matrix.has_canonical_format or not np.isfinite(matrix.data).all():
                raise ValueError(f"legacy q block {(p, q)} is not finite canonical CSR")
            legacy_payload += int(
                matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
            )
            candidate_free_memory_payload = max(
                candidate_free_memory_payload,
                int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes),
            )
            digest = hashlib.sha256()
            digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.indptr, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.indices, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.data, dtype=np.complex128).tobytes())
            legacy_hashes[f"{p}{q}"] = digest.hexdigest()
            path = scratch_path / f"legacy_{p}{q}.npz"
            np.savez(
                path,
                data=matrix.data,
                indices=matrix.indices,
                indptr=matrix.indptr,
                shape=np.asarray(matrix.shape, dtype=np.int64),
            )
            scratch_bytes += int(path.stat().st_size)
        legacy_offdiagonal = dict(legacy_audit["off_diagonal_relative"])
        del matrix, legacy
        gc.collect()

        allocation_gate(
            f"task40_{candidate_version}_q_pair_single_legacy_block_reload",
            {
                "additional_payload_bytes": candidate_free_memory_payload,
                "workspace_bytes": 2 * candidate_free_memory_payload,
                "spooled_legacy_matrix_bytes": scratch_bytes,
                "legacy_full_csr_oracle_released": True,
                "comparison_memory_is_one_block_at_a_time": True,
            },
        )
        candidate, candidate_audit = assemble_task40_v10_sector_blocks(
            action,
            coordinates,
            context,
            allocation_gate=allocation_gate,
            assembly_strategy=candidate_strategy,
            return_all_blocks=True,
        )
        candidate_offdiagonal = dict(candidate_audit["off_diagonal_relative"])
        candidate_payload = sum(
            int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)
            for matrix in candidate.values()
        )
        candidate_hashes = {}
        branch_inputs = {
            q: np.exp(1j * (np.arange(candidate[q, q].shape[1]) + 1) * np.sqrt(2.0))
            for q in (0, 1)
        }
        legacy_branch_outputs = {
            p: np.zeros(candidate[p, p].shape[0], dtype=np.complex128)
            for p in (0, 1)
        }
        candidate_branch_outputs = {
            p: np.zeros(candidate[p, p].shape[0], dtype=np.complex128)
            for p in (0, 1)
        }
        diagonal_scale = max(
            sparse.linalg.norm(candidate[0, 0]),
            sparse.linalg.norm(candidate[1, 1]),
            np.finfo(float).tiny,
        )
        block_facts = {}
        max_numeric_relative = 0.0
        max_action_relative = 0.0
        for p, q in block_keys:
            matrix = candidate[p, q]
            digest = hashlib.sha256()
            digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.indptr, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.indices, dtype=np.int64).tobytes())
            digest.update(np.asarray(matrix.data, dtype=np.complex128).tobytes())
            candidate_hashes[f"{p}{q}"] = digest.hexdigest()

            with np.load(scratch_path / f"legacy_{p}{q}.npz") as saved:
                legacy_matrix = sparse.csr_matrix(
                    (saved["data"], saved["indices"], saved["indptr"]),
                    shape=tuple(map(int, saved["shape"])),
                    copy=False,
                )
                difference = (matrix - legacy_matrix).tocsr()
                difference.sum_duplicates()
                difference.eliminate_zeros()
                difference_norm = float(sparse.linalg.norm(difference))
                numeric_relative = difference_norm / float(diagonal_scale)
                x = branch_inputs[q]
                legacy_y = legacy_matrix @ x
                candidate_y = matrix @ x
                action_delta = candidate_y - legacy_y
                action_delta_norm = float(dznrm2(action_delta))
                action_scale = max(
                    float(sparse.linalg.norm(candidate[p, p])) * float(dznrm2(x)),
                    float(diagonal_scale) * float(dznrm2(x)),
                    np.finfo(float).tiny,
                )
                action_relative = action_delta_norm / action_scale
                legacy_branch_outputs[p] += legacy_y
                candidate_branch_outputs[p] += candidate_y
                max_numeric_relative = max(max_numeric_relative, numeric_relative)
                max_action_relative = max(max_action_relative, action_relative)
                block_facts[f"{p}{q}"] = {
                    "shape": list(matrix.shape),
                    "legacy_nnz": int(legacy_matrix.nnz),
                    "candidate_nnz": int(matrix.nnz),
                    "legacy_csr_sha256": legacy_hashes[f"{p}{q}"],
                    "candidate_csr_sha256": candidate_hashes[f"{p}{q}"],
                    "max_abs_difference": float(
                        np.max(np.abs(difference.data), initial=0.0)
                    ),
                    "difference_frobenius_norm": difference_norm,
                    "difference_relative_to_diagonal": numeric_relative,
                    "action_difference_norm": action_delta_norm,
                    "action_difference_relative_to_diagonal": action_relative,
                    "off_diagonal": p != q,
                }
            del legacy_matrix, difference, legacy_y, candidate_y, action_delta

        branch_action_facts = {}
        for p in (0, 1):
            delta = candidate_branch_outputs[p] - legacy_branch_outputs[p]
            delta_norm = float(dznrm2(delta))
            scale = max(
                float(dznrm2(legacy_branch_outputs[p])),
                float(diagonal_scale)
                * sum(float(dznrm2(branch_inputs[q])) for q in (0, 1)),
                np.finfo(float).tiny,
            )
            relative = delta_norm / scale
            max_action_relative = max(max_action_relative, relative)
            branch_action_facts[str(p)] = {
                "difference_norm": delta_norm,
                "difference_relative_to_diagonal": relative,
            }
        equivalent = bool(
            max_numeric_relative <= LIMITS["operator"]
            and max_action_relative <= LIMITS["operator"]
            and max(legacy_offdiagonal.values()) <= LIMITS["operator"]
            and max(candidate_offdiagonal.values()) <= LIMITS["operator"]
            and set(block_facts) == {"00", "01", "10", "11"}
        )
        legacy_seconds = float(legacy_audit["assembly_total_seconds"])
        candidate_seconds = float(candidate_audit["assembly_total_seconds"])
        faster = candidate_seconds < legacy_seconds
        return {
            "schema": f"task40extra.review_{candidate_version}_q_assembly_pair.v1",
            "candidate_strategy": candidate_strategy,
            "global_q_indices": list(context.global_q_indices),
            "block_shapes": dict(candidate_audit["block_shapes"]),
            "legacy_assembly_seconds": legacy_seconds,
            "candidate_assembly_seconds": candidate_seconds,
            "pair_wall_seconds": float(time.perf_counter() - pair_started),
            "legacy_strategy_audit": legacy_audit,
            "candidate_strategy_audit": candidate_audit,
            "legacy_off_diagonal_relative": legacy_offdiagonal,
            "candidate_off_diagonal_relative": candidate_offdiagonal,
            "block_comparisons": block_facts,
            "full_branch_action_comparisons": branch_action_facts,
            "max_csr_difference_relative_to_diagonal": max_numeric_relative,
            "max_action_difference_relative_to_diagonal": max_action_relative,
            "legacy_csr_payload_bytes": legacy_payload,
            "candidate_csr_payload_bytes": candidate_payload,
            "staged_legacy_spool_bytes": scratch_bytes,
            "legacy_csr_oracle_released_before_candidate_assembly": True,
            "comparison_workspace_within_allocation_gate": True,
            "all_four_blocks_independently_compared": set(block_facts)
            == {"00", "01", "10", "11"},
            "numerically_equivalent_at_original_operator_gate": equivalent,
            "candidate_full_assembly_faster": faster,
            "candidate_selected_for_next_formal_case": bool(
                equivalent
                and (candidate_strategy == Q_ASSEMBLY_BOUNDED_V16 or faster)
            ),
            "selection_rule": (
                "V16 is retained when complete four-block CSR/action and off-diagonal gates pass; "
                "paired time is reported independently"
                if candidate_strategy == Q_ASSEMBLY_BOUNDED_V16
                else "select V13 only when complete four-block CSR/action and off-diagonal "
                "gates pass and its paired full assembly elapsed is strictly lower"
            ),
        }


def _summarize_task40_b0_q_assembly_pairs(
    profile: Any,
    reports: list[Mapping[str, Any]],
    covered_q: set[int],
    *,
    candidate_strategy: str = Q_ASSEMBLY_PREALLOCATED_V13,
) -> dict[str, Any]:
    """Validate and aggregate two real sector-pair reports without FE objects."""
    expected_qs = set(range(int(profile.q_count)))
    if covered_q != expected_qs or len(reports) != 2:
        raise ValueError(
            "B0 paired q assembly did not independently cover all four global q blocks"
        )
    expected_shapes = tuple(map(int, profile.augmented_rows_per_q))
    for pair in reports:
        if not isinstance(pair.get("block_shapes"), Mapping):
            raise ValueError("paired q assembly report omitted all four block shapes")
        if set(pair["block_shapes"]) != {"00", "01", "10", "11"}:
            raise ValueError("paired q assembly report does not cover every (p,q) block")
        if set(pair.get("block_comparisons", {})) != {"00", "01", "10", "11"}:
            raise ValueError("paired q assembly report omitted a numeric block comparison")
        for branch, q in enumerate(pair["global_q_indices"]):
            shape = pair["block_shapes"][f"{branch}{branch}"]
            if shape != [expected_shapes[int(q)], expected_shapes[int(q)]]:
                raise ValueError(
                    f"paired q assembly shape for q={q} differs from B0 profile: {shape}"
                )
    legacy_seconds = float(sum(pair["legacy_assembly_seconds"] for pair in reports))
    candidate_seconds = float(sum(pair["candidate_assembly_seconds"] for pair in reports))
    numerically_equivalent = all(
        pair.get("numerically_equivalent_at_original_operator_gate") is True
        and pair.get("all_four_blocks_independently_compared") is True
        for pair in reports
    )
    candidate_faster = candidate_seconds < legacy_seconds
    if candidate_strategy not in {Q_ASSEMBLY_PREALLOCATED_V13, Q_ASSEMBLY_BOUNDED_V16}:
        raise ValueError(f"unsupported q-assembly comparison strategy: {candidate_strategy!r}")
    candidate_version = "v16" if candidate_strategy == Q_ASSEMBLY_BOUNDED_V16 else "v13"
    selected = bool(
        numerically_equivalent
        and (candidate_strategy == Q_ASSEMBLY_BOUNDED_V16 or candidate_faster)
    )
    return {
        "schema": f"task40extra.review_{candidate_version}_q_assembly_comparison.v1",
        "candidate_strategy": candidate_strategy,
        "profile": profile.identity(),
        "global_q_count": int(profile.q_count),
        "covered_q": sorted(covered_q),
        "sector_pairs": reports,
        "legacy_assembly_seconds": legacy_seconds,
        "candidate_assembly_seconds": candidate_seconds,
        "candidate_faster_for_complete_two_sector_build": candidate_faster,
        "all_four_blocks_numerically_equivalent": numerically_equivalent,
        "all_q_shapes_match_selected_profile": True,
        "mumps_factors_constructed": False,
        "candidate_selected_for_formal_cases": selected,
        "selected_strategy": candidate_strategy if selected else Q_ASSEMBLY_LEGACY,
        "selection_rule": (
            "retain V16 after exact four-block CSR/action and off-diagonal equivalence; "
            "report paired time separately"
            if candidate_strategy == Q_ASSEMBLY_BOUNDED_V16
            else "select V13 only when all four CSR/action blocks, the original "
            "off-diagonal gates, complete q coverage, and profile shapes pass "
            "and the total paired assembly time is strictly lower"
        ),
    }

def _local_condensation_row_facts(local_system: Any) -> dict[str, int]:
    """Expose the local trace and eliminated-interior row axes as recorded."""

    return {
        "local_trace_rows": int(local_system.active_rows),
        "local_interior_rows": int(local_system.active_interior_rows),
    }


def build_task40_v10_p6_reference_inverse(
    cfg: Any,
    axes: Mapping[str, tuple[float, ...]],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    profile: Any | None = None,
    event: Callable[[str, Mapping[str, Any]], None] | None = None,
    identity_gate: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None,
    jit_options: Mapping[str, Any] | None = None,
    share_transform_bank: bool = False,
    target_full_storage_rows: int | None = None,
    reference_pc_strategy: str = STRICT_ONLY,
    q_assembly_strategy: str = Q_ASSEMBLY_LEGACY,
    q_assembly_comparison_only: bool = False,
) -> dict[str, Any]:
    """Build the regular p6 inverse, or run a bounded no-factor q-assembly pair."""
    from mpi4py import MPI
    from dolfinx import fem
    from petsc4py import PETSc

    from .dtn_boundary_phase_gauge import BOUNDARY_PLANE
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action,
        destroy_same_mesh_physical_action,
    )
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from .original_port_blocks import DiagonalOriginalPortBlock
    from .p6_cell_condensed_action import build_p6_cell_condensed_action_from_carrier
    from .retained_port_block_layout import RESEARCH_PORT_LAYOUT
    from .fresh_c1_p6_component import _boundary_support
    from .task40_v10_p6_mumps import AllQExactMumps
    if not callable(allocation_gate):
        raise TypeError("p6 reference construction requires a live allocation gate")
    if q_assembly_strategy not in Q_ASSEMBLY_STRATEGIES:
        raise ValueError(f"unknown Task40 q assembly strategy: {q_assembly_strategy!r}")
    if type(q_assembly_comparison_only) is not bool:
        raise TypeError("q-assembly comparison-only selection must be an explicit boolean")
    if q_assembly_comparison_only and q_assembly_strategy not in {
        Q_ASSEMBLY_PREALLOCATED_V13,
        Q_ASSEMBLY_BOUNDED_V16,
    }:
        raise ValueError("q-assembly pairing requires an explicitly selected registered candidate")
    if (
        MPI.COMM_SELF.Get_size() != 1
        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
        or np.dtype(PETSc.IntType) != np.dtype(np.int32)
        or int(cfg.nedelec_degree) != 6
        or len(axes["y"]) != 5
    ):
        raise ValueError("Task40 V10 reference builder requires the qualified serial p6 profile")

    transform_bank = None
    if share_transform_bank:
        from .y_orbit_transform_bank import YOrbitTransformBank

        transform_bank = YOrbitTransformBank(
            mapping_limit=LIMITS["mapping"], allocation_gate=allocation_gate
        )
    global_levels = None
    global_bundle = None
    global_entities = None
    full_layout = None
    factors = None
    sectors = []
    owner = {
        "global_levels": None,
        "global_bundle": None,
        "global_entities": None,
        "full_layout": None,
        "sectors": sectors,
        "factors": None,
        "inverse": None,
        "transform_bank": transform_bank,
        "transform_bank_receipt": None,
    }
    try:
        regular_cfg = __import__("dataclasses").replace(
            cfg,
            air_void_box_nm=None,
            cell_notch=None,
            geometry_identity=f"{SCHEMA}.regular_reference",
        )
        global_levels = _build_same_mesh_levels(
            regular_cfg, MPI.COMM_SELF, (6,), include_positive_coefficients=False
        )
        global_bundle = build_same_mesh_physical_action(
            global_levels,
            regular_cfg,
            6,
            jit_options=jit_options,
            dtn_phase_gauge=BOUNDARY_PLANE,
            verify_dtn_quadrature=True,
        )
        if identity_gate is not None:
            identity_gate(global_bundle, global_levels)
        modes = tuple(global_bundle["modes"])
        from .task40_v10_p6_periodic_profile import (
            TASK40_V10_P6_PROFILE,
            Task40V10P6PeriodicProfile,
        )

        if profile is None:
            profile = TASK40_V10_P6_PROFILE
        if not isinstance(profile, Task40V10P6PeriodicProfile):
            raise TypeError("p6 reference builder requires a Task40 periodic case profile")
        cell_axes = tuple(map(int, cfg.mesh_axis_cell_counts_requested or ()))
        if cell_axes != profile.global_cell_axes:
            raise ValueError(
                f"p6 target grid {cell_axes} does not match reference profile "
                f"{profile.global_cell_axes}"
            )
        contexts = build_task40_v10_sector_contexts(
            modes,
            regular_cfg,
            axes,
            expected_q_counts=profile.q_port_counts,
            expected_sector_counts=profile.sector_port_counts,
        )
        global_entities = collect_y_orbit_entities(
            global_levels["spaces"][6],
            global_levels["floquets"][6],
            regular_cfg,
            axes,
            transform_bank=transform_bank,
        )
        full_layout = Task40V10FullLayout(
            global_entities,
            regular_cfg,
            expected_inventory={
                "ny": 4,
                "width": profile.rows_per_q,
                "independent_rows": profile.global_independent_rows,
                "storage_rows": profile.global_storage_rows,
                "interior_rows": profile.global_interior_rows,
            },
        )
        if (
            target_full_storage_rows is not None
            and int(target_full_storage_rows) != int(full_layout.full_rows)
        ):
            raise ValueError(
                "actual target and full-reference storage rows differ: "
                f"{target_full_storage_rows} != {full_layout.full_rows}"
            )
        owner["full_storage_dimensions"] = {
            "target_full_storage_rows": (
                None if target_full_storage_rows is None else int(target_full_storage_rows)
            ),
            "reference_full_storage_rows": int(full_layout.full_rows),
            "reference_independent_rows": int(len(global_entities.independent)),
            "target_reference_rows_match": (
                target_full_storage_rows is not None
                and int(target_full_storage_rows) == int(full_layout.full_rows)
            ),
        }
        global_h = np.asarray(
            [entry.normalization_h for entry in global_bundle["dtn_action"].carrier.entries],
            dtype=np.float64,
        )
        if (
            global_h.shape != (profile.mode_count,)
            or not np.isfinite(global_h).all()
            or np.any(global_h <= 0)
        ):
            raise ValueError(
                "regular p6 reference carrier must retain all "
                f"{profile.mode_count} positive original-H values"
            )
        owner.update(
            global_levels=global_levels,
            global_bundle=global_bundle,
            global_entities=global_entities,
            full_layout=full_layout,
        )
        if event is not None and q_assembly_strategy == Q_ASSEMBLY_BOUNDED_V16:
            event(
                "task40_v16_reference_global_ready",
                {
                    "profile": profile.identity(),
                    "global_storage_rows": int(full_layout.full_rows),
                    "global_independent_rows": int(len(global_entities.independent)),
                    "global_interior_rows": int(
                        full_layout.audit["dimension_counts"][3]
                    ),
                    "global_mode_count": int(profile.mode_count),
                    "ordered_mode_sha256": str(global_bundle["mode_sha256"]),
                    "carrier_manifest_sha256": str(
                        global_bundle["dtn_action"].carrier.mode_manifest_sha256
                    ),
                    "transform_bank_enabled": bool(share_transform_bank),
                    "_named_arrays": global_entities.named_backing_arrays("global"),
                },
            )
        all_q_matrices: dict[int, sparse.csr_matrix] = {}
        sector_audits = []
        q_assembly_pair_reports = []
        q_coverage: set[int] = set()
        for context in contexts:
            local_period_y = float(context.local_axes["y"][-1] - context.local_axes["y"][0])
            local_cfg = __import__("dataclasses").replace(
                cfg,
                case_name=f"{cfg.case_name}_v10_twist{context.twist_index}",
                period_y=local_period_y,
                grating_width_y=local_period_y,
                mesh_axis_cell_counts=(
                    profile.global_cell_axes[0],
                    profile.local_y_cells,
                    profile.global_cell_axes[2],
                ),
                mesh_axis_y_values=tuple(context.local_axes["y"]),
                mesh_plan_id=f"{SCHEMA}.local_twist{context.twist_index}",
                mesh_plan_sha256=None,
                air_void_box_nm=None,
                cell_notch=None,
                geometry_identity=f"{SCHEMA}.regular.local_twist{context.twist_index}",
            )
            phase_override = (complex(cfg.floquet_phase_x), context.tau)
            local_levels = _build_same_mesh_levels(
                local_cfg,
                MPI.COMM_SELF,
                (6,),
                include_positive_coefficients=False,
                research_phase_override=phase_override,
            )
            pending_sector = {
                "context": context,
                "levels": local_levels,
                "bundle": None,
                "action": None,
                "system": None,
            }
            sectors.append(pending_sector)
            selected = np.asarray(context.original_mode_indices, dtype=np.int64)
            local_modes = tuple(modes[int(i)] for i in selected)
            global_mode_rows = tuple(global_bundle["mode_rows"])
            mode_inventory = (
                local_modes,
                tuple(global_mode_rows[int(i)] for i in selected),
                global_bundle["mode_sha256"],
            )
            local_bundle = build_same_mesh_physical_action(
                local_levels,
                local_cfg,
                6,
                mode_inventory=mode_inventory,
                jit_options=jit_options,
                dtn_phase_gauge=BOUNDARY_PLANE,
                verify_dtn_quadrature=True,
                research_phase_override=phase_override,
            )
            pending_sector["bundle"] = local_bundle
            local_entities = collect_y_orbit_entities(
                local_levels["spaces"][6],
                local_levels["floquets"][6],
                local_cfg,
                context.local_axes,
                transform_bank=transform_bank,
            )
            transport = TwoCellNativeTransport(
                global_entities,
                local_entities,
                twist_index=context.twist_index,
                eta=context.eta,
                cfg=cfg,
            )
            carrier = local_bundle["dtn_action"].carrier
            local_h = np.asarray(
                [entry.normalization_h for entry in carrier.entries],
                dtype=np.float64,
            )
            if local_h.shape != (len(local_modes),):
                raise ValueError("local p6 boundary carrier mode inventory is incomplete")
            support_groups, support_rows, _support = _boundary_support(local_bundle)
            compiled = fem.form(
                local_bundle["volume_action"].bilinear_form,
                **({"jit_options": dict(jit_options)} if jit_options is not None else {}),
            )
            system = build_unconstrained_assembly_time_condensation(
                compiled,
                local_levels["spaces"][6],
                local_levels["mesh_data"].cell_tags,
                mpc=local_levels["floquets"][6].mpc,
                appended_global_rows=len(local_modes),
                appended_support_owned_cell_groups=support_groups,
                appended_support_group_by_row=support_rows,
                sum_duplicate_cell_integrals=True,
                strict_local_checks=True,
                materialize_global_matrix=False,
                retain_local_schur_for_matrix_free=True,
                share_identity_cache=True,
                preserve_exact_geometry=True,
                allocation_gate=allocation_gate,
            )
            pending_sector["system"] = system
            expected_inventory = (
                profile.local_storage_rows,
                profile.local_trace_rows,
                profile.local_interior_rows,
                len(local_modes),
            )
            actual_inventory = (
                system.full_rows,
                system.active_rows,
                system.active_interior_rows,
                system.appended_rows,
            )
            if actual_inventory != expected_inventory:
                raise ValueError(f"local p6 condensation inventory mismatch: {actual_inventory}")
            compact_h = DiagonalOriginalPortBlock.from_carrier(carrier.entries)
            action = build_p6_cell_condensed_action_from_carrier(
                system,
                carrier,
                owns_condensed=True,
                port_coupling_mode="cached",
                port_block_layout=RESEARCH_PORT_LAYOUT,
                original_port_block=compact_h,
            )
            system = None
            pending_sector["system"] = None
            pending_sector["action"] = action
            local_bundle["research_phase_override"] = phase_override
            trace = trace_layout_coordinates(
                local_entities,
                action.condensed,
                cell_phase_y=context.eta,
                allocation_gate=allocation_gate,
            )
            coordinates = TwoCellBranchCoordinates(
                trace,
                trace_rows=action.condensed.active_rows,
                local_modes=local_modes,
                local_h=local_h,
                context=context,
                global_h=global_h,
                allocation_gate=allocation_gate,
            )
            if q_assembly_comparison_only:
                block_audit = compare_task40_v10_sector_assembly(
                    action,
                    coordinates,
                    context,
                    allocation_gate=allocation_gate,
                    candidate_strategy=q_assembly_strategy,
                )
                q_assembly_pair_reports.append(block_audit)
                q_coverage.update(map(int, context.global_q_indices))
                sector_matrices = {}
            else:
                sector_matrices, block_audit = assemble_task40_v10_sector_blocks(
                    action,
                    coordinates,
                    context,
                    allocation_gate=allocation_gate,
                    assembly_strategy=q_assembly_strategy,
                )
            overlap = set(all_q_matrices).intersection(sector_matrices)
            if overlap:
                raise ValueError(f"p6 q matrix supplied by more than one twist sector: {sorted(overlap)}")
            all_q_matrices.update(sector_matrices)
            sector = pending_sector
            sector.update(
                transport=transport,
                coordinates=coordinates,
                entities=local_entities,
                trace=trace,
                block_audit=block_audit,
            )
            sector_audits.append(block_audit)
            if event is not None:
                sector_facts = {
                    "twist_index": context.twist_index,
                    "global_q_indices": list(context.global_q_indices),
                    "local_inventory": list(actual_inventory),
                    "block_audit": block_audit,
                }
                if q_assembly_strategy == Q_ASSEMBLY_BOUNDED_V16:
                    sector_facts.update(
                        condensation_owner_audit={
                            key: action.condensed.build_audit.get(key)
                            for key in (
                                "identity_cache_mode",
                                "identity_cache_readonly",
                                "identity_cache_class_count_local",
                                "identity_cache_bytes_local",
                                "retained_local_schur_bytes_local",
                                "retained_local_schur_class_count_local",
                                "local_lu_identity_relative_residual_max",
                                "local_lu_factor_cache_bytes_local",
                            )
                        },
                        action_buffer_inventory=dict(action.buffer_inventory),
                        source_owner_lifecycle=(
                            "assembly-time system owner transferred to action.condensed; "
                            "the action remains the owner of local recovery/LU/Schur data"
                        ),
                        _q_matrices=sector_matrices,
                    )
                event("task40_v10_p6_sector_ready", sector_facts)
            del compiled
        if not q_assembly_comparison_only and set(all_q_matrices) != set(range(4)):
            raise ValueError("two p6 twist sectors did not produce all four global q matrices")
        if event is not None and q_assembly_strategy == Q_ASSEMBLY_BOUNDED_V16:
            event(
                "task40_v16_q_csr_all_ready",
                {
                    "q_count": len(all_q_matrices),
                    "all_four_q_matrices": set(all_q_matrices) == set(range(4)),
                    "_q_matrices": all_q_matrices,
                },
            )
        if transform_bank is not None:
            transform_bank.seal()
            named_arrays = global_entities.named_backing_arrays("global")
            for sector_index, sector in enumerate(sectors):
                named_arrays.update(
                    sector["entities"].named_backing_arrays(f"sector{sector_index}")
                )
            receipt = transform_bank.receipt(named_arrays, stage="all_spaces_collected_pre_symbolic")
            owner["transform_bank_receipt"] = receipt
            if event is not None:
                event("task40_v12_transform_bank_ready", receipt)
        if q_assembly_comparison_only:
            comparison_report = _summarize_task40_b0_q_assembly_pairs(
                profile,
                q_assembly_pair_reports,
                q_coverage,
                candidate_strategy=q_assembly_strategy,
            )
            if event is not None:
                candidate_version = (
                    "v16"
                    if q_assembly_strategy == Q_ASSEMBLY_BOUNDED_V16
                    else "v13"
                )
                event(
                    f"task40_{candidate_version}_q_assembly_comparison_complete",
                    comparison_report,
                )
            destroy_task40_v10_p6_reference_inverse(owner)
            for sector in sectors:
                sector.clear()
            sectors.clear()
            all_q_matrices.clear()
            global_levels = None
            global_bundle = None
            global_entities = None
            full_layout = None
            transform_bank = None
            return {
                "comparison_only": True,
                "q_assembly_comparison": comparison_report,
            }
        expected_shapes = tuple(matrix.shape[0] for _q, matrix in sorted(all_q_matrices.items()))
        if expected_shapes != profile.augmented_rows_per_q:
            raise ValueError(
                "runtime q augmented dimensions differ from the selected p6 profile: "
                f"{expected_shapes} != {profile.augmented_rows_per_q}"
            )
        q_port_counts = [0] * profile.q_count
        for context in contexts:
            for branch, q in enumerate(context.global_q_indices):
                q_port_counts[int(q)] += int(
                    np.count_nonzero(context.local_branch_indices == branch)
                )
        first_local = sectors[0]
        local_system = first_local["action"].condensed
        local_entities = first_local["entities"]
        runtime_inventory = {
            "degree": int(cfg.nedelec_degree),
            "global_cell_count": int(
                global_levels["mesh_data"].mesh.topology.index_map(3).size_local
            ),
            "global_storage_rows": int(global_entities.full_rows),
            "global_independent_rows": int(len(global_entities.independent)),
            "global_interior_rows": int(full_layout.audit["dimension_counts"][3]),
            "global_trace_rows": int(
                len(global_entities.independent)
                - int(full_layout.audit["dimension_counts"][3])
            ),
            "q_count": len(all_q_matrices),
            "rows_per_q": int(full_layout.width),
            "trace_rows_per_q": int(
                (len(global_entities.independent)
                 - int(full_layout.audit["dimension_counts"][3]))
                // profile.q_count
            ),
            "local_cell_count": int(
                first_local["levels"]["mesh_data"].mesh.topology.index_map(3).size_local
            ),
            "local_storage_rows": int(local_entities.full_rows),
            "local_independent_rows": int(len(local_entities.independent)),
            **_local_condensation_row_facts(local_system),
            "local_width_per_q": int(local_entities.width),
            **{
                f"q_port_count_{q}": int(q_port_counts[q])
                for q in range(profile.q_count)
            },
        }
        inventory_audit = profile.validate_runtime_inventory(runtime_inventory)
        factors = AllQExactMumps(
            all_q_matrices,
            allocation_gate=allocation_gate,
            event=event,
            expected_shapes=expected_shapes,
            profile=profile,
            transform_bank=transform_bank,
            inverse_borrowers={
                "global": global_entities,
                **{
                    f"sector{index}": sector["entities"]
                    for index, sector in enumerate(sectors)
                },
            },
            full_storage_rows=int(full_layout.full_rows),
            target_reference_rows_match=bool(
                owner["full_storage_dimensions"]["target_reference_rows_match"]
            ),
            reference_pc_strategy=reference_pc_strategy,
        )
        owner["factors"] = factors
        owner["inverse"] = CompleteTwoCellInverse(
            (sectors[0], sectors[1]),
            full_layout,
            factors,
            allocation_gate=allocation_gate,
            reference_pc_strategy=reference_pc_strategy,
        )
        owner["sector_audits"] = sector_audits
        owner["profile"] = profile
        owner["runtime_inventory_validation"] = inventory_audit
        owner["q_matrix_audits"] = {
            q: {
                "shape": list(matrix.shape),
                "nnz": int(matrix.nnz),
            }
            for q, matrix in all_q_matrices.items()
        }
        if event is not None:
            event(
                "task40_v10_p6_reference_inverse_ready",
                {
                    "global_p6_inventory": full_layout.audit,
                    "sector_count": len(sectors),
            "profile": profile.identity(),
                    "all_four_q_matrices": owner["q_matrix_audits"],
                    "all_four_mumps_factors_live": True,
                },
            )
        return owner
    except BaseException:
        if factors is not None:
            factors.destroy()
        for sector in reversed(sectors):
            system = sector.get("system")
            if system is not None:
                try:
                    system.destroy()
                except Exception:
                    pass
            action = sector.get("action")
            if action is not None:
                try:
                    action.destroy()
                except Exception:
                    pass
            bundle = sector.get("bundle")
            if bundle:
                try:
                    destroy_same_mesh_physical_action(bundle)
                except Exception:
                    pass
            _destroy_task40_v10_levels(sector.get("levels"))
        if global_bundle is not None:
            try:
                destroy_same_mesh_physical_action(global_bundle)
            except Exception:
                pass
        _destroy_task40_v10_levels(global_levels)
        owner.pop("inverse", None)
        owner.pop("full_layout", None)
        owner.pop("global_entities", None)
        for sector in sectors:
            sector.pop("transport", None)
            sector.pop("entities", None)
        global_entities = None
        full_layout = None
        if transform_bank is not None:
            transform_bank.close()
        raise


def _destroy_task40_v10_levels(levels: Any) -> None:
    if not isinstance(levels, Mapping):
        return
    for floquet in levels.get("floquets", {}).values():
        mpc = getattr(floquet, "mpc", None)
        if mpc is not None:
            try:
                mpc.destroy()
            except Exception:
                pass


def destroy_task40_v10_p6_reference_inverse(owner: dict[str, Any]) -> None:
    """Release all factors, local p6 actions, and the borrowed regular carrier."""
    inverse = owner.pop("inverse", None)
    if inverse is not None:
        inverse.destroy()
    factors = owner.pop("factors", None)
    if factors is not None:
        factors.destroy()
    sectors = owner.pop("sectors", ())
    for sector in reversed(tuple(sectors)):
        action = sector.get("action")
        if action is not None:
            action.destroy()
        bundle = sector.get("bundle")
        if bundle:
            from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
            destroy_same_mesh_physical_action(bundle)
        _destroy_task40_v10_levels(sector.get("levels"))
    global_bundle = owner.pop("global_bundle", None)
    if global_bundle:
        from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
        destroy_same_mesh_physical_action(global_bundle)
    _destroy_task40_v10_levels(owner.pop("global_levels", None))
    for sector in sectors:
        sector.pop("transport", None)
        sector.pop("entities", None)
    owner.pop("full_layout", None)
    owner.pop("global_entities", None)
    owner.pop("sector_audits", None)
    owner.pop("q_matrix_audits", None)
    transform_bank = owner.pop("transform_bank", None)
    owner.pop("transform_bank_receipt", None)
    if transform_bank is not None:
        transform_bank.close()
    owner.clear()
