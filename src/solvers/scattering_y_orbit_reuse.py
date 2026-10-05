"""Task042 opt-in frozen published y-orbit routines; no donor CLI/reader.

Extracted verbatim definitions from the named Git source below; public FE
constructors remain local. Only the complete native moment maps and unchanged
FGMRES32 reference-inverse outer algorithm are exposed here.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any
import numpy as np
from scipy import sparse
LIMITS = {"mapping": 1e-12, "operator": 1e-11, "residual": 1e-10, "solution": 1e-9, "excitation": 1e-3, "notch_modes": 1e-12}


def _relative(value: np.ndarray, reference: np.ndarray) -> float:
    return float(np.linalg.norm(value) / max(np.linalg.norm(reference), np.finfo(float).tiny))


def _right_sparse(matrix: np.ndarray, right: sparse.spmatrix) -> np.ndarray:
    return np.asarray((right.T @ matrix.T).T)


def _congruence(matrix: np.ndarray, q: sparse.spmatrix) -> np.ndarray:
    return np.asarray(q.conj().T @ _right_sparse(matrix, q))


def _sparse_payload(matrix: sparse.spmatrix) -> int:
    csr = matrix.tocsr()
    return int(csr.data.nbytes + csr.indices.nbytes + csr.indptr.nbytes)


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


def _gate(gate, name, payload, workspace=0, **facts):
    if not callable(gate):
        raise ValueError("a fresh measured whole-tree allocation gate is required")
    gate(name, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                "allocation_semantics": "additional_objects_to_current_resident_RSS", **facts})


def _payload(matrix):
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def trace_layout_coordinates(full_layout, system, *, allocation_gate):
    """Restrict existing build_y_orbit_layout; do not build another orbit map."""
    full = np.asarray(full_layout.independent, dtype=np.int64)
    active = np.asarray(system.trace_constraints.owned_active_original_dofs, dtype=np.int64)
    interior = np.concatenate([cell.interior_original_dofs for cell in system.cell_recovery_maps])
    if (full_layout.full_rows != system.full_rows or full.ndim != 1 or active.ndim != 1
            or np.any(full < 0) or np.any(full >= system.full_rows)
            or np.any(active < 0) or np.any(active >= system.full_rows)
            or len(np.unique(active)) != system.active_rows or len(np.unique(full)) != len(full)
            or len(np.unique(interior)) != system.active_interior_rows
            or len(interior) != system.active_interior_rows
            or len(np.intersect1d(active, interior))
            or not np.array_equal(np.sort(np.concatenate((active, interior))), np.sort(full))):
        raise ValueError("complete native trace/interior/full-FE partition disagrees")
    row_of = np.full(system.full_rows, -1, dtype=np.int64)
    row_of[full] = np.arange(len(full))
    positions = row_of[active]
    ny, width = int(full_layout.ny), int(full_layout.width)
    if len(np.unique(positions)) != system.active_rows or np.any(positions < 0) or system.active_rows % ny:
        raise ValueError("native trace positions/orbit count invalid")
    upper = 4 * _payload(full_layout.r) + 2 * _payload(full_layout.fourier)
    _gate(allocation_gate, "exact_trace_map_restriction", upper, upper)
    restricted = full_layout.r[positions, :].tocsr()
    columns = np.unique(restricted.indices)
    slots = columns[columns < width]
    if (len(slots) != system.active_rows // ny
            or not np.array_equal(columns, np.concatenate([j * width + slots for j in range(ny)]))):
        raise ValueError("trace canonical slots are not complete identical y orbits")
    outside = np.setdiff1d(np.arange(len(full)), positions)
    canonical_outside = np.setdiff1d(np.arange(len(full)), columns)
    # Exact structural closure, no small coefficient deletion or abs(orientation)=1.
    if (full_layout.r[outside, :][:, columns].nnz
            or full_layout.r_inverse[columns, :][:, outside].nnz
            or full_layout.native_translation[positions, :][:, outside].nnz
            or full_layout.native_translation[outside, :][:, positions].nnz
            or full_layout.fourier[columns, :][:, canonical_outside].nnz
            or full_layout.fourier[canonical_outside, :][:, columns].nnz):
        raise ValueError("trace restriction mixes interior and trace coordinates")
    r = restricted[:, columns].tocsr()
    del restricted
    ri = full_layout.r_inverse[columns, :][:, positions].tocsr()
    f = full_layout.fourier[columns, :][:, columns].tocsr()
    t = full_layout.native_translation[positions, :][:, positions].tocsr()
    identity = sparse.eye(system.active_rows, dtype=np.complex128, format="csr")
    scale = np.sqrt(system.active_rows)
    defects = {"left_inverse_relative": float(sparse.linalg.norm(ri @ r - identity) / scale),
               "right_inverse_relative": float(sparse.linalg.norm(r @ ri - identity) / scale),
               "fourier_unitarity_relative": float(sparse.linalg.norm(f.conj().T @ f - identity) / scale)}
    if any(not np.isfinite(value) or value > 1e-12 for value in defects.values()):
        raise ValueError("restricted native/canonical/DFT inverse gate failed")
    return {"R_t": r, "R_t_inverse": ri, "F_t": f, "native_trace_translation": t,
            "trace_width": system.active_rows // ny, "ny": ny,
            "trace_original_rows": active,
            "full_independent_trace_positions": positions,
            "full_canonical_trace_positions": columns,
            "audit": {**defects, "complete_trace_rows": system.active_rows,
                      "complete_interior_rows": len(interior), "partition_exact": True,
                      "structural_trace_interior_closure": True,
                      "primal_map": "Q_t=R_t F_t", "dual_map": "Q_t^H",
                      "primal_inverse": "F_t^H R_t_inverse", "R_unitary_assumed": False}}

