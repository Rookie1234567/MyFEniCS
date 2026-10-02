"""Bounded full-3D reference-inverse architecture probe, never a default PC.

Only the periodic y CELL-INDEX action is diagonalized. Every edge, face,
cell-interior channel, all y blocks, and every actual DtN alias remain.
The initial implementation deliberately extracts Q^H A0 Q from a genuine
FFCx-assembled full 3D matrix. It does not implement scalable cell assembly.
"""

from __future__ import annotations

from dataclasses import dataclass, replace, field
from time import perf_counter
from types import SimpleNamespace
from typing import Any, Callable

import numpy as np
from scipy import sparse
from scipy.linalg import lu_factor, lu_solve


SCHEMA = "task40extra.y-orbit-full3d-reference.v1"
LIMITS = {"mapping": 1e-12, "operator": 1e-11, "residual": 1e-10,
          "solution": 1e-9, "excitation": 1e-3, "notch_modes": 1e-12}
SEED = 20261001


def _relative(value: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(value) / max(np.linalg.norm(reference), np.finfo(float).tiny))


def _right_sparse(matrix: np.ndarray, right: sparse.spmatrix) -> np.ndarray:
    return np.asarray((right.T @ matrix.T).T)


def _congruence(matrix: np.ndarray, q: sparse.spmatrix) -> np.ndarray:
    return np.asarray(q.conj().T @ _right_sparse(matrix, q))


def _sparse_payload(matrix: sparse.spmatrix) -> int:
    csr = matrix.tocsr()
    return int(csr.data.nbytes + csr.indices.nbytes + csr.indptr.nbytes)


def pilot_config(input_path, *, azimuth_deg: float = 0.0):
    """An 80-cell, reduced-geometry 0.7 nm algebra pilot, not target accuracy."""
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized

    specification = load_and_resolve(input_path)
    cfg = simulation_config_3d_from_normalized(specification.as_jsonable())
    scale = 7.0 / 135.0
    axes = {"x": tuple(value * scale for value in (0, 16.5, 25, 33.5, 50)),
            "y": tuple(value * scale for value in (0, 6.25, 12.5, 18.75, 25)),
            "z": tuple(value * scale for value in (-10, 0, 40, 80, 120, 130))}
    cfg = replace(cfg, case_name="y_orbit_p2_algebra_regular", nedelec_degree=2,
                  nedelec_trace_degree=None, nedelec_interior_degree=None,
                  visualization_degree=2, mesh_cell_type="hexahedron",
                  mesh_spacing_mode="boundary_fitted", mesh_axis_cell_counts=(4, 4, 5),
                  mesh_axis_x_values=axes["x"], mesh_axis_y_values=axes["y"],
                  mesh_axis_z_values=axes["z"], mesh_axis_z_profile=SCHEMA,
                  mesh_plan_id=SCHEMA, mesh_plan_sha256=None,
                  mesh_target_size=max(max(np.diff(value)) for value in axes.values()),
                  air_void_box_nm=None, cell_notch=None, geometry_model_variant="original",
                  geometry_identity=SCHEMA + ".regular", incident_phi_deg=azimuth_deg,
                  stage4_dtn_order_policy="manual", diffraction_zero_order_only=False,
                  diffraction_order_max_m=9, diffraction_order_max_n=3)
    return cfg, axes, specification.input_sha256


@dataclass
class YOrbitLayout:
    independent: np.ndarray
    full_rows: int
    ny: int
    width: int
    r: sparse.csr_matrix
    r_inverse: sparse.csr_matrix
    fourier: sparse.csr_matrix
    q: sparse.csr_matrix
    shift: sparse.csr_matrix
    native_translation: sparse.csr_matrix
    phase_y: complex
    audit: dict[str, Any]
    _transform_bank: Any = field(default=None, repr=False)
    _borrowed_entities: Any = field(default=None, repr=False)

    def named_backing_arrays(self, role):
        arrays = {f"{role}.independent": self.independent}
        for name in ("r", "r_inverse", "fourier", "q", "shift", "native_translation"):
            matrix = getattr(self, name)
            for member in ("data", "indices", "indptr"):
                arrays[f"{role}.{name}.{member}"] = getattr(matrix, member)
        return arrays

    def dual_to_modal(self, values):
        return np.asarray(self.q.conj().T @ values)

    def primal_to_modal(self, values):
        return np.asarray(self.fourier.conj().T @ (self.r_inverse @ values))

    def primal_from_modal(self, values):
        return np.asarray(self.q @ values)

    def modal_norms(self, values, *, dual: bool):
        transformed = self.dual_to_modal(values) if dual else self.primal_to_modal(values)
        return [float(np.linalg.norm(row)) for row in transformed.reshape(self.ny, self.width)]


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


def build_y_orbit_layout(space, floquet, cfg, axes, *, wrap_phase_y=None, cell_phase_y=None,
                         entities=None, transform_bank=None) -> YOrbitLayout:
    """Original full-map entry, plus explicit research-local wrap/eigenphase.

    The candidate only calls this for its two-cell local mesh. Full original
    outer transport calls collect_y_orbit_entities and never materializes R/F/Q.
    """
    borrowed_entities = entities
    if entities is None:
        entities=collect_y_orbit_entities(space,floquet,cfg,axes,transform_bank=transform_bank)
    else:
        if not isinstance(entities, YOrbitEntities):
            raise ValueError("already-collected complete YOrbitEntities required")
        identity = entities._collection_identity
        if (identity is None or identity[0] is not space or identity[1] is not floquet or identity[2] is not cfg
                or identity[3] != tuple((name, tuple(map(float, axes[name]))) for name in ("x", "y", "z"))):
            raise ValueError("collected entities do not belong to this actual space/MPC/config/axes")
        if transform_bank is not None and entities._transform_bank is not transform_bank:
            raise ValueError("layout and collected entities must borrow the same run-local bank")
    independent,full_rows,ny,width=entities.independent,entities.full_rows,entities.ny,entities.width
    records,bases,slots=entities.records,entities.bases,entities.slots
    dimension_counts=entities.dimension_counts
    tolerance=1e-9
    r_rows, r_cols, r_values, inv_rows, inv_cols, inv_values = [], [], [], [], [], []
    orientation_defect = 0.0
    for orbit in range(ny):
        for base in bases:
            native, transform = records[(orbit, base)]
            first, size = slots[base]
            if len(native) != size or transform.shape != (size, size):
                raise ValueError("translated entity channel dimensions disagree")
            inverse = (np.linalg.inv(transform) if entities._transform_bank is None else
                       entities._transform_bank.inverse(transform))
            orientation_defect = max(orientation_defect, float(np.linalg.norm(transform.conj().T @ transform - np.eye(size))))
            canonical = np.arange(orbit * width + first, orbit * width + first + size)
            for i, row in enumerate(native):
                for j, col in enumerate(canonical):
                    if transform[i, j] != 0:
                        r_rows.append(row); r_cols.append(col); r_values.append(transform[i, j])
                    if inverse[j, i] != 0:
                        inv_rows.append(col); inv_cols.append(row); inv_values.append(inverse[j, i])
    n = len(independent)
    r = sparse.csr_matrix((r_values, (r_rows, r_cols)), shape=(n, n))
    r_inverse = sparse.csr_matrix((inv_values, (inv_rows, inv_cols)), shape=(n, n))
    identity_defect = sparse.linalg.norm(r_inverse @ r - sparse.eye(n)) / np.sqrt(n)
    if identity_defect > LIMITS["mapping"]:
        raise ValueError("native/canonical inverse maps fail")
    phase = complex(cfg.floquet_phase_y if wrap_phase_y is None else wrap_phase_y)
    if abs(abs(phase) - 1.0) > LIMITS["mapping"] or abs(complex(cfg.ky).imag) > LIMITS["mapping"]:
        raise ValueError("initial unitary orbit probe requires real ky")
    if cell_phase_y is not None:
        cell_phase_y=complex(cell_phase_y)
        if (not np.isfinite(cell_phase_y) or abs(abs(cell_phase_y)-1)>LIMITS["mapping"]
                or abs(cell_phase_y**ny-phase)>LIMITS["mapping"]):
            raise ValueError("explicit cell eigenphase must retain the exact wrap and real Bloch unit circle")
    shift_rows = np.arange(n)
    shift_cols = ((shift_rows // width + 1) % ny) * width + shift_rows % width
    shift_values = np.ones(n, dtype=complex)
    shift_values[(ny - 1) * width:] = phase
    shift = sparse.csr_matrix((shift_values, (shift_rows, shift_cols)), shape=(n, n))
    f_rows, f_cols, f_values = [], [], []
    for j in range(ny):
        for q_index in range(ny):
            theta = (complex(cfg.ky).real * float(cfg.period_y) + 2 * np.pi * q_index) / ny
            value = (np.exp(1j*theta*j) if cell_phase_y is None else
                     (cell_phase_y*np.exp(2j*np.pi*q_index/ny))**j)/np.sqrt(ny)
            for slot in range(width):
                f_rows.append(j * width + slot); f_cols.append(q_index * width + slot); f_values.append(value)
    fourier = sparse.csr_matrix((f_values, (f_rows, f_cols)), shape=(n, n))
    q = (r @ fourier).tocsr()
    cycle = sparse.eye(n, dtype=complex, format="csr")
    for _ in range(ny):
        cycle = cycle @ shift
    cycle_error = sparse.linalg.norm(cycle - phase * sparse.eye(n)) / np.sqrt(n)
    fourier_error = sparse.linalg.norm(fourier.conj().T @ fourier - sparse.eye(n)) / np.sqrt(n)
    shift_unitarity = sparse.linalg.norm(shift.conj().T @ shift - sparse.eye(n)) / np.sqrt(n)
    if max(cycle_error, fourier_error, shift_unitarity) > LIMITS["mapping"]:
        raise ValueError("canonical unitary/cycle/DFT Gate fails")
    native_translation = (r @ shift @ r_inverse).tocsr()
    native_cycle = sparse.eye(n, dtype=complex, format="csr")
    for _ in range(ny):
        native_cycle = native_cycle @ native_translation
    native_cycle_error = sparse.linalg.norm(native_cycle - phase * sparse.eye(n)) / np.sqrt(n)
    eigenphases=(np.exp(1j*(complex(cfg.ky).real*cfg.period_y+2*np.pi*np.arange(ny))/ny)
                 if cell_phase_y is None else cell_phase_y*np.exp(2j*np.pi*np.arange(ny)/ny))
    eta = np.repeat(eigenphases,width)
    eigen_error = sparse.linalg.norm(shift @ fourier - fourier @ sparse.diags(eta)) / np.sqrt(n)
    probe = np.cos(np.arange(n) * 0.37) + 1j * np.sin(np.arange(n) * 0.23)
    dual_probe = np.sin(np.arange(n) * 0.29) + 1j * np.cos(np.arange(n) * 0.41)
    native_work = np.vdot(dual_probe, q @ probe)
    modal_work = np.vdot(q.conj().T @ dual_probe, probe)
    pairing_error = float(abs(native_work - modal_work) / max(abs(native_work), abs(modal_work), 1.0))
    if max(native_cycle_error, eigen_error, pairing_error) > LIMITS["mapping"]:
        raise ValueError("native cycle, DFT eigenvalues or primal/dual pairing Gate fails")
    widths = entities.y_widths
    audit = {"independent_rows": n, "full_storage_rows": full_rows, "ny": ny,
             "rows_per_q": width, "all_q": list(range(ny)), "dimension_dof_counts": dimension_counts,
             "mapping_inverse_relative": float(identity_defect), "orientation_euclidean_defect_max": orientation_defect,
             "canonical_shift_unitarity_relative": float(shift_unitarity), "translation_cycle_relative": float(cycle_error),
             "fourier_unitarity_relative": float(fourier_error), "q_euclidean_unitary_assumed": False,
             "native_translation_cycle_relative": float(native_cycle_error),
             "fourier_shift_eigen_relative": float(eigen_error), "primal_dual_pairing_relative": pairing_error,
             "phase_y": [phase.real, phase.imag], "translation_definition": "(Tu)(y)=u(y+h), wrap multiplies phase_y",
             "y_actual_widths": widths.tolist(), "y_actual_widths_hex": [float(v).hex() for v in widths],
             "y_width_max_relative_variation": float(np.ptp(widths) / np.mean(widths)),
             "geometry_index_tolerance": tolerance, "geometry_metric_rounding": False,
             "sparse_Q_payload_bytes": _sparse_payload(q), "dense_Q_created": False}
    if wrap_phase_y is not None or cell_phase_y is not None:
        audit.update(explicit_research_wrap=True,explicit_cell_eigenphases=[[v.real,v.imag] for v in eigenphases])
    return YOrbitLayout(independent, full_rows, ny, width, r, r_inverse, fourier, q, shift,
                        native_translation, phase, audit, _transform_bank=entities._transform_bank,
                        _borrowed_entities=borrowed_entities)


class FullOriginalAction:
    """Independent coefficients embedded into full original MPC storage."""
    def __init__(self, action, layout):
        from petsc4py import PETSc
        self.action, self.layout = action, layout
        self.source = PETSc.Vec().createSeq(layout.full_rows, comm=PETSc.COMM_SELF)
        self.target = self.source.duplicate()
        self.calls = 0

    def apply(self, values):
        self.source.array[:] = 0
        self.source.array[self.layout.independent] = values
        self.action.apply(self.source, self.target)
        self.calls += 1
        return np.asarray(self.target.array[self.layout.independent]).copy()

    def mult(self, _matrix, source, target):
        target.array[:] = self.apply(source.getArray(readonly=True))

    def close(self):
        self.source.destroy(); self.target.destroy()


def assemble_original_dense(volume_action, floquet, carrier, layout):
    """Existing FFCx form plus every existing DtN rank contribution."""
    from dolfinx import fem
    import dolfinx_mpc
    form = fem.form(volume_action.bilinear_form)
    matrix = dolfinx_mpc.assemble_matrix(form, floquet.mpc, bcs=[])
    try:
        matrix.assemble()
        indptr, indices, values = matrix.getValuesCSR()
        csr = sparse.csr_matrix((values, indices, indptr), shape=matrix.getSize())
        result = csr[layout.independent][:, layout.independent].toarray()
    finally:
        matrix.destroy()
    rows_of = np.full(layout.full_rows, -1, dtype=np.int64)
    rows_of[layout.independent] = np.arange(len(layout.independent))
    for entry in carrier.entries:
        c_rows, d_rows = rows_of[entry.coupling_rows], rows_of[entry.projection_rows]
        if np.any(c_rows < 0) or np.any(d_rows < 0):
            raise ValueError("carrier must use the same zero-slave dual coordinates")
        # projection_values ALREADY includes conjugation in the inherited carrier.
        result[np.ix_(c_rows, d_rows)] += np.outer(entry.coupling_values, entry.projection_values) / entry.normalization_h
    if not np.isfinite(result).all():
        raise ValueError("original FFCx/DtN matrix is nonfinite")
    return result


def audit_port_aliases(carrier, layout, cfg, modes):
    """Actual C/D/H augmented coupling, all physical n mod Ny aliases."""
    n = len(layout.independent)
    rows_of = np.full(layout.full_rows, -1, dtype=np.int64)
    rows_of[layout.independent] = np.arange(n)
    from src.common.modes_3d import outgoing_port_modes_3d
    mode_key = lambda mode: (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
    expected_keys = [mode_key(mode) for mode in outgoing_port_modes_3d(cfg)]
    supplied_keys = [mode_key(mode) for mode in modes]
    actual_keys = [(str(entry.mode_identity["side"]), int(entry.mode_identity["m"]),
                    int(entry.mode_identity["n"]), str(entry.mode_identity["polarization"]))
                   for entry in carrier.entries]
    if actual_keys != supplied_keys or actual_keys != expected_keys or len(set(actual_keys)) != len(actual_keys):
        raise ValueError("actual ordered carrier keys differ from the full production mode generator")
    aliases = {q: [] for q in range(layout.ny)}
    leakage_c = leakage_d = covariance_c = covariance_d = 0.0
    maximum_full_gram_error = 0.0
    for index, entry in enumerate(carrier.entries):
        identity = entry.mode_identity
        m, physical_n = int(identity["m"]), int(identity["n"])
        q_index = physical_n % layout.ny
        aliases[q_index].append({"index": index, "side": identity["side"], "m": m,
                                 "n": physical_n, "polarization": identity["polarization"]})
        c, d = np.zeros(n, complex), np.zeros(n, complex)
        if np.any(rows_of[entry.coupling_rows] < 0) or np.any(rows_of[entry.projection_rows] < 0):
            raise ValueError("actual carrier contains an eliminated MPC row")
        c[rows_of[entry.coupling_rows]] = entry.coupling_values
        d[rows_of[entry.projection_rows]] = entry.projection_values
        cm = np.asarray(layout.q.conj().T @ c)
        dm = np.asarray(layout.q.T @ d)  # DQ, never DQ-conjugate.
        outside = np.ones(n, dtype=bool)
        outside[q_index * layout.width:(q_index + 1) * layout.width] = False
        leakage_c = max(leakage_c, _relative(cm[outside], cm))
        leakage_d = max(leakage_d, _relative(dm[outside], dm))
        eta = np.exp(1j * (complex(cfg.ky).real * cfg.period_y + 2 * np.pi * physical_n) / layout.ny)
        covariance_c = max(covariance_c, _relative(layout.native_translation.conj().T @ c * eta - c, c))
        covariance_d = max(covariance_d, _relative(layout.native_translation.T @ d / eta - d, d))
        # H>0 is the carrier's actual diagonal normalization; it commutes with eta.
        maximum_full_gram_error = max(maximum_full_gram_error, abs(abs(eta)**2 - 1.0))
    if any(not values for values in aliases.values()):
        raise ValueError("manual port inventory must exercise all y blocks")
    if not any(item["n"] == 1 for item in aliases[1]) or not any(item["n"] == -3 for item in aliases[1]):
        raise ValueError("n=1 and n=-3 aliases must BOTH remain")
    worst = max(leakage_c, leakage_d, covariance_c, covariance_d, maximum_full_gram_error)
    if worst > LIMITS["operator"]:
        raise ValueError(f"actual augmented-port symmetry/alias Gate fails: {worst}")
    return {"mode_count": len(carrier.entries), "alias_groups": aliases,
            "production_generator_ordered_keys_match": True, "generator_mode_count": len(expected_keys),
            "coupling_off_q_relative_max": leakage_c, "projection_off_q_relative_max": leakage_d,
            "augmented_C_covariance_relative_max": covariance_c, "augmented_D_covariance_relative_max": covariance_d,
            "augmented_H_covariance_relative_max": maximum_full_gram_error,
            "augmented_definition": "[V C; -D H], A=V+C H^-1 D, D values already conjugated",
            "physical_n_aliases_collapsed": False, "all_p_channels_retained": True}


class YReferenceInverse:
    def __init__(self, matrix, layout, *, enforce_symmetry=True):
        self.layout = layout
        started = perf_counter()
        canonical = _congruence(matrix, layout.r)
        shifted = _congruence(canonical, layout.shift)
        canonical_covariance = _relative(shifted - canonical, canonical)
        del canonical, shifted
        shifted = _congruence(matrix, layout.native_translation)
        native_covariance = _relative(shifted - matrix, matrix)
        del shifted
        modal = _congruence(matrix, layout.q)
        off_sq = 0.0
        off_max = 0.0
        diagonal_sq = 0.0
        self.factors = []
        for q_index in range(layout.ny):
            rows = slice(q_index * layout.width, (q_index + 1) * layout.width)
            for other in range(layout.ny):
                cols = slice(other * layout.width, (other + 1) * layout.width)
                block = modal[rows, cols]
                if q_index == other:
                    diagonal_sq += float(np.linalg.norm(block)**2)
                else:
                    off_sq += float(np.linalg.norm(block)**2)
                    off_max = max(off_max, float(np.max(np.abs(block))))
        off_relative = float(np.sqrt(off_sq / max(diagonal_sq + off_sq, np.finfo(float).tiny)))
        self.audit = {"native_form_covariance_relative": native_covariance,
                      "canonical_form_covariance_relative": canonical_covariance,
                      "modal_off_block_relative": off_relative, "modal_off_block_absolute_max": off_max,
                      "dropped_coupling_policy": "only audited roundoff-level off-block entries",
                      "group_averaged_reference_used": False, "all_q_factors": layout.ny,
                      "factor_rows": [layout.width] * layout.ny, "factor_backend": "SciPy public dense LU",
                      "factor_reuse_plus_minus_q": False}
        if enforce_symmetry and max(native_covariance, canonical_covariance, off_relative) > LIMITS["operator"]:
            raise ValueError(f"reference symmetry Gate fails: {self.audit}")
        for q_index in range(layout.ny):
            rows = slice(q_index * layout.width, (q_index + 1) * layout.width)
            self.factors.append(lu_factor(np.array(modal[rows, rows], order="F"), overwrite_a=True, check_finite=True))
        del modal
        self.audit["factor_payload_bytes"] = sum(int(lu.nbytes + piv.nbytes) for lu, piv in self.factors)
        self.audit["setup_seconds"] = perf_counter() - started
        self.calls = 0

    def apply_array(self, rhs):
        transformed = self.layout.dual_to_modal(rhs).reshape(self.layout.ny, self.layout.width)
        result = np.empty_like(transformed)
        for q_index, factor in enumerate(self.factors):
            result[q_index] = lu_solve(factor, transformed[q_index], check_finite=True)
        self.calls += 1
        return self.layout.primal_from_modal(result.ravel())

    def apply(self, _pc, source, target):
        target.array[:] = self.apply_array(source.getArray(readonly=True))


def _solution_packet(action, matrix, rhs, solution, direct, layout, *, volume_action, dtn_action):
    native_residual = rhs - action.apply(solution)
    assembled_residual = rhs - matrix @ solution
    carrier = dtn_action.carrier
    auxiliary = dtn_action.recover_auxiliary(action.source)
    projected = np.asarray([np.dot(entry.projection_values, action.source.array[entry.projection_rows])
                            for entry in carrier.entries])
    h = np.asarray([entry.normalization_h for entry in carrier.entries])
    port_residual = h * auxiliary - projected
    coupling = np.zeros(layout.full_rows, complex)
    for amplitude, entry in zip(auxiliary, carrier.entries, strict=True):
        coupling[entry.coupling_rows] += amplitude * entry.coupling_values
    volume = volume_action.apply(action.source).array[layout.independent].copy()
    augmented_fe_residual = rhs - volume - coupling[layout.independent]
    return {"full_original_true_residual": _relative(native_residual, rhs),
            "assembled_true_residual": _relative(assembled_residual, rhs),
            "augmented_FE_true_residual": _relative(augmented_fe_residual, rhs),
            "augmented_port_closure_relative": _relative(port_residual, projected),
            "augmented_vs_original_residual_relative": _relative(augmented_fe_residual - native_residual, rhs),
            "auxiliary_ports_recovered": int(len(auxiliary)),
            "relative_direct_solution_difference": _relative(solution - direct, direct),
            "solution_primal_q_norms": layout.modal_norms(solution, dual=False),
            "rhs_dual_q_norms": layout.modal_norms(rhs, dual=True),
            "native_action_calls": action.calls}


def solve_notched_fgmres(action, inverse, rhs):
    from petsc4py import PETSc
    n = len(rhs)
    matrix = PETSc.Mat().createPython((n, n), context=action, comm=PETSc.COMM_SELF)
    matrix.setUp()
    b = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
    x = b.duplicate()
    monitor_solution = b.duplicate()
    b.array[:] = rhs; x.set(0.0)
    ksp = PETSc.KSP().create(comm=PETSc.COMM_SELF)
    history = []
    started = perf_counter()
    try:
        ksp.setOperators(matrix)
        ksp.setType("fgmres")
        ksp.setPCSide(PETSc.PC.Side.RIGHT)
        ksp.setGMRESRestart(32)
        pc = ksp.getPC(); pc.setType("python"); pc.setPythonContext(inverse)
        ksp.setTolerances(rtol=1e-11, atol=0.0, max_it=128)
        def monitor(current, iteration, internal_residual):
            current_solution = current.buildSolution(monitor_solution)
            full_residual = _relative(rhs - action.apply(current_solution.getArray(readonly=True)), rhs)
            history.append({"iteration": int(iteration), "internal_residual": float(internal_residual),
                            "full_original_true_residual": full_residual})
        ksp.setMonitor(monitor)
        ksp.solve(b, x)
        return x.array.copy(), {"iterations": int(ksp.getIterationNumber()), "reason": int(ksp.getConvergedReason()),
                                "history": history, "seconds": perf_counter() - started,
                                "outer_operator": "full_original_3D_FFCx_form_action_plus_all_DtN_modes",
                                "right_pc": "all_y_blocks_regular_geometry_reference_inverse"}
    finally:
        ksp.destroy(); monitor_solution.destroy(); x.destroy(); b.destroy(); matrix.destroy()


def run_full3d_pilot(input_path, *, event: Callable, save_array: Callable, azimuth_deg=0.0):
    """One regular inverse identity plus one same-mesh genuine 3D-notch solve."""
    from mpi4py import MPI
    from src.geometry.mesh_builder_3d import _mark_cells, _rectangular_air_void_audit
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action, build_physical_rhs, destroy_same_mesh_physical_action,
        _build_split_volume_action,
    )
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction

    cfg, axes, input_sha = pilot_config(input_path, azimuth_deg=azimuth_deg)
    event("regular_mesh_space_mpc_begin", {})
    levels = _build_same_mesh_levels(cfg, MPI.COMM_SELF, (2,), include_positive_coefficients=False)
    space, floquet = levels["spaces"][2], levels["floquets"][2]
    if int(levels["mesh"].topology.index_map(3).size_local) != 80:
        raise ValueError("pilot requires exactly 80 full-3D hexahedral cells")
    layout = build_y_orbit_layout(space, floquet, cfg, axes)
    if azimuth_deg == 5.0 and abs(layout.phase_y - 1.0) < 1e-3:
        raise ValueError("phi5 probe must exercise a genuinely nontrivial real-ky y wrap")
    if len(layout.independent) != 2048 or layout.width != 512:
        raise ValueError("actual full-FE inventory differs from the derived 2048/4x512")
    event("regular_layout_ready", layout.audit)
    save_array("Q_data", layout.q.data); save_array("Q_indices", layout.q.indices); save_array("Q_indptr", layout.q.indptr)
    save_array("R_inverse_data", layout.r_inverse.data); save_array("R_inverse_indices", layout.r_inverse.indices); save_array("R_inverse_indptr", layout.r_inverse.indptr)
    save_array("F_data", layout.fourier.data); save_array("F_indices", layout.fourier.indices); save_array("F_indptr", layout.fourier.indptr)
    save_array("independent_storage_rows", layout.independent)
    base = notched_action = action0 = action1 = None
    try:
        base = build_same_mesh_physical_action(levels, cfg, 2)
        action0 = FullOriginalAction(base["physical_action"], layout)
        event("regular_full_original_action_ready", {"mode_count": len(base["modes"]), "mode_manifest_sha256": base["mode_sha256"]})
        ports = audit_port_aliases(base["dtn_action"].carrier, layout, cfg, base["modes"])
        a0 = assemble_original_dense(base["volume_action"], floquet, base["dtn_action"].carrier, layout)
        rng = np.random.default_rng(SEED)
        generic_rhs = rng.standard_normal(len(layout.independent)) + 1j * rng.standard_normal(len(layout.independent))
        excitation = np.asarray(layout.modal_norms(generic_rhs, dual=True))
        if np.min(excitation) / np.linalg.norm(excitation) < LIMITS["excitation"]:
            raise ValueError("generic original FE RHS does not excite ALL y blocks")
        matrix_action_error = max(_relative(a0 @ source - action0.apply(source), a0 @ source)
                                  for source in (generic_rhs, np.conj(generic_rhs)))
        if matrix_action_error > LIMITS["operator"]:
            raise ValueError(f"independent FFCx-matrix/full-action Gate fails: {matrix_action_error}")
        save_array("A0_original", a0); save_array("generic_rhs", generic_rhs)
        physical_storage_rhs, rhs_facts = build_physical_rhs(base)
        try:
            physical_rhs = physical_storage_rhs.array[layout.independent].copy()
        finally:
            physical_storage_rhs.destroy()
        save_array("physical_rhs", physical_rhs)
        event("regular_direct_begin", {"matrix_payload_bytes": a0.nbytes})
        started = perf_counter()
        full_lu = lu_factor(np.array(a0, order="F"), overwrite_a=True)
        direct_generic = lu_solve(full_lu, generic_rhs)
        direct_physical = lu_solve(full_lu, physical_rhs)
        direct_payload = sum(value.nbytes for value in full_lu)
        direct_seconds = perf_counter() - started
        del full_lu
        for label, rhs, direct in (("generic", generic_rhs, direct_generic), ("physical", physical_rhs, direct_physical)):
            if _relative(rhs - action0.apply(direct), rhs) > LIMITS["residual"]:
                raise ValueError("full original A0 direct control does not pass true residual")
            save_array("A0_direct_" + label, direct)
        event("regular_direct_released", {"payload_bytes": direct_payload, "seconds": direct_seconds})
        inverse = YReferenceInverse(a0, layout)
        regular = {}
        for label, rhs, direct in (("generic", generic_rhs, direct_generic), ("physical", physical_rhs, direct_physical)):
            solution = inverse.apply_array(rhs)
            save_array("A0_modal_" + label, solution)
            packet = _solution_packet(action0, a0, rhs, solution, direct, layout,
                                      volume_action=base["volume_action"], dtn_action=base["dtn_action"])
            if packet["full_original_true_residual"] > LIMITS["residual"] or packet["relative_direct_solution_difference"] > LIMITS["solution"]:
                raise ValueError(f"all-y-block A0 inverse Gate fails: {packet}")
            if max(packet["augmented_FE_true_residual"], packet["augmented_port_closure_relative"],
                   packet["augmented_vs_original_residual_relative"]) > LIMITS["residual"]:
                raise ValueError("regular full augmented primal/dual residual Gate fails")
            regular[label] = packet
        event("regular_all_y_inverse_pass", inverse.audit)
        scale = 7.0 / 135.0
        notch_box = tuple(value * scale for value in (25, 33.5, 6.25, 18.75, 40, 80))
        notch_cfg = replace(cfg, case_name="y_orbit_p2_algebra_notch", air_void_box_nm=notch_box,
                            geometry_identity=SCHEMA + ".notch")
        tags = _mark_cells(levels["mesh"], notch_cfg)
        changed = np.flatnonzero(tags.values != levels["mesh_data"].cell_tags.values)
        if len(changed) != 2:
            raise ValueError("same-mesh 3D box notch must change exactly two actual cells")
        mesh_data = SimpleNamespace(**vars(levels["mesh_data"]))
        mesh_data.cell_tags = tags
        notch_audit = _rectangular_air_void_audit(levels["mesh"], tags, notch_cfg)
        mesh_data.rectangular_air_void_audit = notch_audit
        volume = _build_split_volume_action(mesh_data, notch_cfg, space, floquet, jit_options={})
        notched_action = FullspacePhysicalAction(volume, base["dtn_action"], owns_dtn=False)
        action1 = FullOriginalAction(notched_action, layout)
        a1 = assemble_original_dense(volume, floquet, base["dtn_action"].carrier, layout)
        notch_matrix_action_error = _relative(a1 @ generic_rhs - action1.apply(generic_rhs), a1 @ generic_rhs)
        if notch_matrix_action_error > LIMITS["operator"]:
            raise ValueError("notched original FFCx matrix/action Gate fails")
        delta_modal = _congruence(a1 - a0, layout.q)
        delta_norm = np.linalg.norm(delta_modal)
        for q_index in range(layout.ny):
            rows = slice(q_index * layout.width, (q_index + 1) * layout.width)
            delta_modal[rows, rows] = 0.0
        notch_off_relative = float(np.linalg.norm(delta_modal) / max(delta_norm, np.finfo(float).tiny))
        del delta_modal, a0
        if notch_off_relative < 1e-8:
            raise ValueError("notch must genuinely couple different transverse y blocks")
        save_array("A_notch_original", a1)
        event("notch_direct_begin", {"changed_cells": changed.tolist(), "delta_off_q_relative": notch_off_relative})
        started = perf_counter()
        full_lu = lu_factor(np.array(a1, order="F"), overwrite_a=True)
        notch_direct = {"generic": lu_solve(full_lu, generic_rhs), "physical": lu_solve(full_lu, physical_rhs)}
        notch_direct_seconds = perf_counter() - started
        del full_lu
        for label, direct in notch_direct.items():
            save_array("notch_direct_" + label, direct)
        event("notch_direct_released", {"seconds": notch_direct_seconds})
        notch = {}
        for label, rhs in (("generic", generic_rhs), ("physical", physical_rhs)):
            direct = notch_direct[label]
            if _relative(rhs - action1.apply(direct), rhs) > LIMITS["residual"]:
                raise ValueError("notched full original direct control fails")
            solution, krylov = solve_notched_fgmres(action1, inverse, rhs)
            save_array("notch_iterative_" + label, solution)
            packet = _solution_packet(action1, a1, rhs, solution, direct, layout,
                                      volume_action=volume, dtn_action=base["dtn_action"])
            packet.update(krylov)
            q_norms = np.asarray(packet["solution_primal_q_norms"])
            packet["nonzero_q_primal_relative"] = float(np.linalg.norm(q_norms[1:]) / np.linalg.norm(q_norms))
            if packet["full_original_true_residual"] > LIMITS["residual"] or packet["relative_direct_solution_difference"] > LIMITS["solution"]:
                raise ValueError(f"notched full-3D outer solve Gate fails: {packet}")
            if max(packet["augmented_FE_true_residual"], packet["augmented_port_closure_relative"],
                   packet["augmented_vs_original_residual_relative"]) > LIMITS["residual"]:
                raise ValueError("notched full augmented primal/dual residual Gate fails")
            if label == "physical" and packet["nonzero_q_primal_relative"] < LIMITS["notch_modes"]:
                raise ValueError("notch physical forcing must generate nonzero transverse block content")
            notch[label] = packet
            event("notch_" + label + "_solve_pass", {key: packet[key] for key in ("iterations", "full_original_true_residual", "nonzero_q_primal_relative")})
        return {"schema": SCHEMA, "status": "ARCHITECTURE_IDENTITY_AND_NOTCH_PASS",
                "role": "reduced_geometry_p2_full3d_algebra_architecture_only", "target_geometry_solution": False,
                "p2_physical_accuracy": False, "production_qualification": False, "official_RTA": False,
                "input_sha256": input_sha, "azimuth_deg": azimuth_deg,
                "axes_nm": {name: list(value) for name, value in axes.items()},
                "limits": LIMITS, "seed": SEED, "layout": layout.audit, "ports": ports,
                "matrix_vs_original_action_relative": matrix_action_error,
                "notch_matrix_vs_original_action_relative": notch_matrix_action_error,
                "reference_inverse": inverse.audit, "regular_sources": regular, "notched_sources": notch,
                "notch_delta_off_q_relative": notch_off_relative, "changed_cells": changed.tolist(),
                "notch_geometry_audit": notch_audit, "physical_rhs_facts": rhs_facts,
                "full_A0_direct_payload_bytes": int(direct_payload), "full_A0_direct_seconds": direct_seconds,
                "full_notch_direct_seconds": notch_direct_seconds,
                "design_signal": all(packet["iterations"] <= 32 for packet in notch.values()),
                "total_reference_inverse_calls": inverse.calls,
                "resource_numbers_are_payload_not_RSS": True, "no_2TB_or_48h_claim": True}
    finally:
        if action1 is not None: action1.close()
        if action0 is not None: action0.close()
        if notched_action is not None: notched_action.destroy()
        if base is not None: destroy_same_mesh_physical_action(base)
