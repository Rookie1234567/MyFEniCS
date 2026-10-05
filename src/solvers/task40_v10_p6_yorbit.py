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
                if self._transform_bank is not None:
                    self.transform_key((orbit,base))
                first,size=self.slots[base]
                canonical=slice(orbit*self.width+first,orbit*self.width+first+size)
                if direction in ("primal_to_canonical","dual_from_canonical","functional_from_canonical"):
                    key=(orbit,base)
                    if key not in self._inverses:
                        if self._transform_bank is None:
                            inverse=np.linalg.inv(matrix)
                            if np.linalg.norm(inverse@matrix-np.eye(size))/np.sqrt(size)>LIMITS["mapping"]:
                                raise ValueError("original entity moment inverse failed")
                        else:
                            inverse=self._transform_bank.inverse(matrix)
                        self._inverses[key]=inverse
                    elif (self._transform_bank is not None and
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
        from src.solvers.hcurl_canonical_vector_dolfinx import _entity_canonical_order
        from src.constraints.high_order_floquet_trace import quadrilateral_face_info
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
        if transform_bank is not None:
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
            if transform_bank is None:
                transform, _state = _physical_entity_transform(coords, dimension, cfg.nedelec_degree, tolerance)
            else:
                active = [int(value) in row_of for value in ids]
                if not any(active):
                    continue
                if not all(active):
                    raise ValueError("partly eliminated entity requires an explicit MPC block map")
                _canonical_coords, permutation = _entity_canonical_order(coords, dimension, tolerance)
                permutation = tuple(map(int, permutation))
                if dimension == 1:
                    if permutation not in ((0, 1), (1, 0)):
                        raise ValueError("unknown actual edge reversal")
                    state = ("edge_reversal", permutation != (0, 1))
                    semantics = ("canonical_edge", "lexicographic_xyz", "basix_coefficient_v1")
                else:
                    state = ("face_D4", permutation, int(quadrilateral_face_info(permutation)))
                    semantics = ("canonical_face", "axis_aligned_reference_q1", "basix_coefficient_v1")
                key = TransformKey(basis_identity, dimension, (len(positions), len(positions)),
                                   tuple(range(len(positions))), state, semantics)

                def physical_builder():
                    matrix, actual_semantics = _physical_entity_transform(
                        coords, dimension, cfg.nedelec_degree, tolerance)
                    if tuple(actual_semantics) != semantics:
                        raise ValueError("physical coefficient semantics changed")
                    return matrix

                transform = transform_bank.matrix(key, physical_builder)
            add_entity(ids, transform, coords, dimension,
                       template_key=None if transform_bank is None else key,
                       source_cell=cell, source_local_entity=int(local_entity[0]), source_positions=positions)
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
                               ("actual_element.Tt_apply", "cell_dim_block_size", "inverse_interior_block"))
            transform = transform_bank.matrix(key, cell_builder)
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
                modal_rhs_norm = float(np.linalg.norm(modal_rhs))
                modal_residual_relative = float(np.linalg.norm(modal_residual)) / max(
                    modal_rhs_norm, np.finfo(np.float64).tiny
                )
                if (
                    not np.isfinite(modal_residual_relative)
                    or modal_residual_relative > LIMITS["residual"]
                ):
                    raise FloatingPointError(
                        f"Task40 V10 q={q} inverse residual failed: "
                        f"{modal_residual_relative} > {LIMITS['residual']}"
                    )
                q_residual_records.append(
                    {
                        "q": q,
                        "branch": branch,
                        "rows": int(modal_rhs.size),
                        "rhs_norm": modal_rhs_norm,
                        "true_residual_relative": modal_residual_relative,
                        "limit": LIMITS["residual"],
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


def assemble_task40_v10_sector_blocks(
    action: Any,
    coordinates: TwoCellBranchCoordinates,
    context: Task40V10SectorContext,
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
) -> tuple[dict[int, sparse.csr_matrix], dict[str, Any]]:
    """Stream all four two-branch blocks and retain only the two diagonal blocks."""
    q_maps = tuple(
        coordinates.q_map(branch, allocation_gate=allocation_gate)
        for branch in (0, 1)
    )
    blocks: dict[tuple[int, int], sparse.csr_matrix] = {}
    for p in (0, 1):
        for q in (0, 1):
            blocks[p, q] = sparse.csr_matrix(
                (q_maps[p].shape[1], q_maps[q].shape[1]),
                dtype=np.complex128,
            )
    for rows, columns, values, label in action.iter_reduced_contributions(
        allocation_gate=allocation_gate
    ):
        for p in (0, 1):
            for q in (0, 1):
                term = project_reduced_contribution(
                    q_maps[p],
                    q_maps[q],
                    rows,
                    columns,
                    values,
                    allocation_gate=allocation_gate,
                    label=f"{label}/p{p}q{q}",
                )
                blocks[p, q] = (blocks[p, q] + term).tocsr()
                del term
        del rows, columns, values
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
    }
    return result, audit


def build_task40_v10_p6_reference_inverse(
    cfg: Any,
    axes: Mapping[str, tuple[float, ...]],
    *,
    allocation_gate: Callable[[str, Mapping[str, Any]], None],
    event: Callable[[str, Mapping[str, Any]], None] | None = None,
    identity_gate: Callable[[Mapping[str, Any], Mapping[str, Any]], None] | None = None,
    jit_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the regular p6 full-reference inverse and all four live MUMPS factors."""
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
    if (
        MPI.COMM_SELF.Get_size() != 1
        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
        or np.dtype(PETSc.IntType) != np.dtype(np.int32)
        or int(cfg.nedelec_degree) != 6
        or len(axes["y"]) != 5
    ):
        raise ValueError("Task40 V10 reference builder requires the qualified serial p6 profile")

    global_levels = None
    global_bundle = None
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
        from .task40_v10_p6_periodic_profile import TASK40_V10_P6_PROFILE
        profile = TASK40_V10_P6_PROFILE
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
        global_h = np.asarray(
            [entry.normalization_h for entry in global_bundle["dtn_action"].carrier.entries],
            dtype=np.float64,
        )
        if global_h.shape != (532,) or not np.isfinite(global_h).all() or np.any(global_h <= 0):
            raise ValueError("regular p6 reference carrier must retain all 532 positive original-H values")
        owner.update(
            global_levels=global_levels,
            global_bundle=global_bundle,
            global_entities=global_entities,
            full_layout=full_layout,
        )
        all_q_matrices: dict[int, sparse.csr_matrix] = {}
        sector_audits = []
        for context in contexts:
            local_period_y = float(context.local_axes["y"][-1] - context.local_axes["y"][0])
            local_cfg = __import__("dataclasses").replace(
                cfg,
                case_name=f"{cfg.case_name}_v10_twist{context.twist_index}",
                period_y=local_period_y,
                grating_width_y=local_period_y,
                mesh_axis_cell_counts=(4, 2, 5),
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
            expected_inventory = (28722, 8496, 18000, len(local_modes))
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
            sector_matrices, block_audit = assemble_task40_v10_sector_blocks(
                action,
                coordinates,
                context,
                allocation_gate=allocation_gate,
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
                event(
                    "task40_v10_p6_sector_ready",
                    {
                        "twist_index": context.twist_index,
                        "global_q_indices": list(context.global_q_indices),
                        "local_inventory": list(actual_inventory),
                        "block_audit": block_audit,
                    },
                )
            del compiled
        if set(all_q_matrices) != set(range(4)):
            raise ValueError("two p6 twist sectors did not produce all four global q matrices")
        expected_shapes = tuple(matrix.shape[0] for _q, matrix in sorted(all_q_matrices.items()))
        if expected_shapes != profile.augmented_rows_per_q:
            raise ValueError(
                f"runtime q augmented dimensions differ from the B0 profile: {expected_shapes}"
            )
        factors = AllQExactMumps(
            all_q_matrices,
            allocation_gate=allocation_gate,
            event=event,
            expected_shapes=expected_shapes,
        )
        owner["factors"] = factors
        owner["inverse"] = CompleteTwoCellInverse(
            (sectors[0], sectors[1]),
            full_layout,
            factors,
            allocation_gate=allocation_gate,
        )
        owner["sector_audits"] = sector_audits
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
    owner.pop("full_layout", None)
    owner.pop("global_entities", None)
    owner.pop("sector_audits", None)
    owner.pop("q_matrix_audits", None)
    owner.clear()
