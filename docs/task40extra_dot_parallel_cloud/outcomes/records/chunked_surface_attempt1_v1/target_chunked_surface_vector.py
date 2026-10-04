"""Explicit selected top/x native quadrature experiment; never builds FE objects.

The caller owns the already admitted MPI1 p6 fixture, finalized MPC, 3 GiB
whole-tree watchdog and source/config seal. This helper tabulates only bounded
chunks. Degree 27 is a mechanism witness; degree 160 is the original target
rule. Neither result qualifies full C/D, a carrier, a PDE or physical outputs.
"""
from __future__ import annotations

import hashlib
import importlib
import math
from pathlib import Path
from typing import Any

import numpy as np

SCHEMA = "task40extra.selected-native-chunked-top-x.v1"
REFERENCE_SHA256 = "cace8b9b472b9f8b7187f4cde1d028219041483a29cfc1981f9e6801c661737a"
OWNED_BUFFER_LIMIT = 128 << 20
BOOKKEEPING_BYTES = 1 << 20
MAX_CHUNK_SIZE = 256
CELL_DOFS = 882
EXPECTED_ROWS = 13224  # 104 edges*6 + 75 faces*60 + 18 interiors*450
_VERTICES = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
                      [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1]], dtype=np.float64)


def array_identity(value):
    value = np.asarray(value)
    if not value.flags.c_contiguous:
        raise ValueError("identity requires a contiguous native array")
    digest = hashlib.sha256()
    digest.update(str(value.dtype).encode())
    digest.update(str(value.shape).encode())
    digest.update(memoryview(value).cast("B"))
    return {"shape": list(value.shape), "dtype": str(value.dtype), "sha256": digest.hexdigest()}


def rule_signature(value):
    """The raw-C-byte signature used by compiled_surface_quadrature_identity."""
    value = np.asarray(value)
    if not value.flags.c_contiguous:
        raise ValueError("rule identity requires contiguous native storage")
    return {"shape": list(value.shape), "dtype": str(value.dtype),
            "sha256": hashlib.sha256(memoryview(value).cast("B")).hexdigest()}


def apply_native_basis_orientation(basis, values, cell_info):
    if (values.ndim != 3 or values.shape[1:] != (CELL_DOFS, 3)
            or values.dtype != np.float64 or not values.flags.c_contiguous):
        raise ValueError("native orientation needs contiguous point-by-882-by-3 real basis")
    for point in range(len(values)):
        basis.T_apply(values[point].reshape(-1), 3, int(cell_info))


class _Budget:
    def __init__(self, gate, event, persistent=0):
        self.gate, self.event, self.persistent = gate, event, int(persistent)
        self.maximum = 0

    def before(self, label, named=0, scratch=0, **facts):
        if min(self.persistent, named, scratch) < 0:
            raise ValueError("negative allocation admission")
        total = self.persistent + int(named) + int(scratch)
        record = {"persistent_owned_bytes_upper": self.persistent,
                  "new_live_named_bytes_upper": int(named),
                  "native_workspace_estimate_bytes": int(scratch),
                  "owned_and_workspace_bytes_upper": total,
                  "owned_buffer_limit_bytes": OWNED_BUFFER_LIMIT,
                  "estimate_is_measured_RSS": False,
                  "whole_process_3gib_current_RSS_watchdog_required": True, **facts}
        record["predicted_buffer_bytes"] = {
            "persistent_owned": self.persistent, "new_live_named": int(named),
            "native_workspace_estimate": int(scratch)}
        record["predicted_total_bytes"] = total
        self.event({"kind": "native_chunk_allocation_before", "label": label, **record})
        if total > OWNED_BUFFER_LIMIT:
            raise MemoryError("chunk owned-buffer admission exceeds 128 MiB")
        if self.gate(label, record) is False:
            raise MemoryError("caller rejected native chunk allocation")
        self.maximum = max(self.maximum, total)

    def reference_gate(self, label, facts):
        self.before("geometry/" + label, int(facts["requested_bytes"]), 0,
                    inherited_reference_admission=facts)
        return True


def affine_geometry(coordinates):
    """Exact axis-aligned affine map, including signed axis permutations."""
    x = np.asarray(coordinates)
    if x.shape != (8, 3) or x.dtype != np.float64 or not np.isfinite(x).all():
        raise ValueError("expected finite float64 eight-vertex geometry")
    origin = x[0]
    J = np.column_stack((x[1] - origin, x[2] - origin, x[4] - origin))
    if not (np.all(np.count_nonzero(J, axis=0) == 1)
            and np.all(np.count_nonzero(J, axis=1) == 1)
            and np.array_equal(origin + _VERTICES @ J.T, x)):
        raise ValueError("actual geometry is not literal affine axis geometry")
    K = np.zeros((3, 3), dtype=np.float64)
    for column in range(3):
        row = int(np.flatnonzero(J[:, column])[0])
        K[column, row] = 1.0 / J[row, column]
    determinant = float(np.dot(J[:, 0], np.cross(J[:, 1], J[:, 2])))
    if not np.isfinite(J).all() or not np.isfinite(K).all() or not math.isfinite(determinant) or determinant == 0:
        raise ValueError("invalid signed affine Jacobian")
    return origin, J, determinant, K


def dual_project(raw, slaves, masters, coefficients, offsets, *, failure_callback=None):
    """K^H b_FE in native storage: identity masters, literal zero slaves.

    Input arrays are public finalized-MPC metadata. No dense K is constructed.
    The operation is a dual projection, not a primal backsubstitution.
    """
    raw = np.asarray(raw)
    slaves, masters = np.asarray(slaves), np.asarray(masters)
    coefficients, offsets = np.asarray(coefficients), np.asarray(offsets)
    if raw.ndim != 1 or raw.dtype != np.complex128 or not np.isfinite(raw).all():
        raise ValueError("finite native complex128 raw vector required")
    n = len(raw)
    if (slaves.ndim != 1 or slaves.dtype.kind not in "iu" or masters.ndim != 1
            or masters.dtype.kind not in "iu" or offsets.dtype.kind not in "iu"
            or offsets.shape != (n + 1,) or offsets[0] != 0
            or np.any(offsets[1:] < offsets[:-1]) or offsets[-1] != len(coefficients)
            or coefficients.ndim != 1 or coefficients.dtype != np.complex128
            or len(masters) != len(coefficients) or not np.isfinite(coefficients).all()
            or len(np.unique(slaves)) != len(slaves)
            or np.any(slaves < 0) or np.any(slaves >= n)
            or np.any(masters < 0) or np.any(masters >= n)):
        raise ValueError("invalid finalized native MPC metadata")
    flag = np.zeros(n, dtype=bool)
    flag[slaves] = True
    if np.any(flag[masters]):
        raise ValueError("finalized MPC must reference independent local masters")
    for row in range(n):
        width = int(offsets[row + 1] - offsets[row])
        if bool(flag[row]) != bool(width):
            raise ValueError("slave flags and constraint offsets disagree")
    result = raw.copy()
    for slave in slaves:
        s = int(slave)
        for position in range(int(offsets[s]), int(offsets[s + 1])):
            # Scalar scatter preserves repeated master contributions.
            result[int(masters[position])] += np.conjugate(coefficients[position]) * raw[s]
    result[slaves] = 0
    if not np.isfinite(result).all() or not np.all(result[slaves] == 0):
        if failure_callback is not None:
            failure_callback(result)
        raise FloatingPointError("nonfinite projected vector or nonzero slave slots")
    return result


def unchanged_mask(raw):
    raw = np.asarray(raw)
    if raw.ndim != 1 or raw.dtype != np.complex128 or not np.isfinite(raw).all():
        raise ValueError("finite native complex128 raw vector required")
    if len(raw) > np.iinfo(np.int32).max:
        raise OverflowError("native row count exceeds int32")
    cutoff = max(1.0e-30, 1.0e-13 * float(np.max(np.abs(raw), initial=0.0)))
    rows = np.flatnonzero(np.abs(raw) > cutoff).astype(np.int32)
    values = np.ascontiguousarray(raw[rows])
    return rows, values, cutoff


def _load_reference():
    module = importlib.import_module("src.solvers.target_higher_quadrature_reference")
    path = Path(module.__file__).resolve()
    if hashlib.sha256(path.read_bytes()).hexdigest() != REFERENCE_SHA256:
        raise ValueError("pinned public reference/geometry source changed")
    return module, {"path": str(path), "sha256": REFERENCE_SHA256}


def _save(path, value, budget, *, extra_live=0):
    value = np.asarray(value)
    budget.before("save/" + path.name, int(extra_live) + 2 * value.nbytes + 8192 + (1 << 20), 0,
                  complete_unclipped_array=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as stream:
        np.save(stream, value, allow_pickle=False)
    temporary.replace(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    numeric = array_identity(value)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size,
            "sha256": digest.hexdigest(), "file_sha256": digest.hexdigest(),
            "numeric_sha256": numeric["sha256"], "shape": numeric["shape"], "dtype": numeric["dtype"]}


def _numerical_failure(message, stage, arrays, root, budget, event, *, extra_live=0):
    """Keep the actual failing chunk and partial full vectors, without clipping."""
    artifacts = {}
    for name, value in arrays.items():
        value = np.asarray(value)
        budget.before("failure_copy/" + name, int(extra_live) + 2 * value.nbytes + (1 << 20))
        contiguous = np.ascontiguousarray(value)
        artifacts[name] = (array_identity(contiguous) if root is None
                           else _save(root / f"failure_{stage}_{name}.npy", contiguous, budget, extra_live=extra_live))
        del contiguous
    event({"kind": "native_numerical_failure_arrays_saved", "stage": stage,
           "reason": message, "artifacts": artifacts, "numerical_qualification": False})
    raise FloatingPointError(message)


def assemble_chunked_top_x(*, V: Any, mesh_data: Any, mpc: Any, cfg: Any,
                          selected_modes: tuple, selected_indices: tuple,
                          quadrature_degree: int, allocation_gate, event,
                          output_dir, chunk_size: int = 128):
    """Assemble full selected b_FE and K^H b_FE; apply the existing cutoff last."""
    if not callable(allocation_gate) or not callable(event):
        raise ValueError("allocation gate and durable event callback required")
    if type(chunk_size) is not int or not 1 <= chunk_size <= MAX_CHUNK_SIZE:
        raise ValueError("chunk_size must be a positive integer <=256")
    if type(quadrature_degree) is not int or quadrature_degree not in (27, 160):
        raise ValueError("only distinct mechanism27 or original-target160 scope admitted")
    if (not 1 <= len(selected_modes) <= 8 or len(selected_indices) != len(selected_modes)
            or len(set(selected_indices)) != len(selected_indices)
            or any(type(i) is not int or i < 0 for i in selected_indices)):
        raise ValueError("distinct frozen selected inventory indices required")
    budget = _Budget(allocation_gate, event, persistent=BOOKKEEPING_BYTES)
    root = None if output_dir is None else Path(output_dir)
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)
    budget.before("public_source_and_native_metadata_validation", 8 << 20)
    reference, reference_source = _load_reference()
    if not mpc.finalized or V.mesh is not mesh_data.mesh or V.value_size != 3:
        raise ValueError("existing fixture/space and finalized MPC required")
    msh = V.mesh
    n = int(V.dofmap.index_map.size_local)
    if (msh.comm.size != 1 or msh.comm.rank != 0 or n != EXPECTED_ROWS
            or V.dofmap.index_map.num_ghosts or V.dofmap.index_map.size_global != n
            or V.dofmap.index_map_bs != 1 or V.dofmap.bs != 1):
        raise ValueError("exact MPI1 unghosted scalar native p6 fixture required")
    layout = reference._assert_same_native_layout(V, mpc.function_space)
    basis = V.element.basix_element
    if (basis.family.name != "N1E" or basis.cell_type.name != "hexahedron"
            or basis.degree != 6 or basis.dim != CELL_DOFS
            or tuple(basis.value_shape) != (3,) or np.dtype(basis.dtype) != np.dtype(np.float64)
            or basis.map_type.name != "covariantPiola"):
        raise ValueError("actual real p6 882-DoF covariant-Piola N1E basis required")
    phase_groups = {}
    for position, mode in enumerate(selected_modes):
        if (mode.side != "top" or np.shape(mode.k_vector) != (3,)
                or not all(np.isfinite(v) for v in (mode.alpha, mode.gamma, mode.k_vector[2]))):
            raise ValueError("finite actual top modes required")
        key = (complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2]))
        phase_groups.setdefault(key, []).append(position)
    if len(phase_groups) > 4:
        raise ValueError("selected modes exceed four distinct actual phase tuples")
    slaves = np.asarray(mpc.slaves)
    flags = np.asarray(mpc.is_slave)
    coefficients, offsets = (np.asarray(a) for a in mpc.coefficients())
    masters = np.asarray(mpc.masters.array)
    if flags.shape != (n,) or not np.array_equal(np.flatnonzero(flags), np.sort(slaves)):
        raise ValueError("actual finalized MPC slave flags disagree")
    # Validate all metadata through the same exact dual helper before any rule.
    dual_workspace = n * 80 + len(coefficients) * 64 + len(masters) * 16
    budget.before("MPC_validation_zero_vector", dual_workspace,
                  actual_coefficient_nnz=len(coefficients), actual_master_nnz=len(masters))
    validation = dual_project(np.zeros(n, dtype=np.complex128), slaves, masters, coefficients, offsets)
    del validation
    for slave in slaves:
        s = int(slave)
        if not np.array_equal(masters[int(offsets[s]):int(offsets[s + 1])], mpc.masters.links(s)):
            raise ValueError("public master links do not align with coefficient offsets")
    width = int(np.max(np.diff(offsets), initial=0))
    if width < 1 or any(np.asarray(V.dofmap.cell_dofs(c)).dtype != np.int32
                        for c in range(18)):
        raise ValueError("actual constrained native int32 cell maps required")
    rectangles = reference._actual_rectangles(mesh_data, cfg, budget.reference_gate, event)
    budget.before("public_cell_orientation_metadata", 18 * 4 + 4096)
    msh.topology.create_entity_permutations()
    permutations = msh.topology.get_cell_permutation_info()
    if permutations.dtype != np.uint32 or permutations.shape != (18,):
        raise ValueError("actual uint32 native cell orientation metadata required")
    from basix import CellType, PolysetType, QuadratureType, make_quadrature

    node_count = ((quadrature_degree + 2) // 2) ** 2
    rule_bytes = node_count * 3 * 8
    budget.before("same_production_default_and_gauss_rule", 2 * rule_bytes,
                  node_count * 6 * 8 + 8 * (quadrature_degree + 2) ** 2 * 8)
    points, weights = make_quadrature(CellType.quadrilateral, quadrature_degree,
                                    rule=QuadratureType.default, polyset_type=PolysetType.standard)
    gauss_points, gauss_weights = make_quadrature(CellType.quadrilateral, quadrature_degree,
                                                rule=QuadratureType.gauss_jacobi,
                                                polyset_type=PolysetType.standard)
    budget.persistent = BOOKKEEPING_BYTES + 2 * rule_bytes
    rule_artifacts = {} if root is None else {
        label: _save(root / (label + ".npy"), value, budget)
        for label, value in (("rule_default_points", points), ("rule_default_weights", weights),
                             ("rule_gauss_points", gauss_points), ("rule_gauss_weights", gauss_weights))}
    event({"kind": "native_actual_rules_saved_before_equality_gate", "artifacts": rule_artifacts})
    if (points.dtype != np.float64 or weights.dtype != np.float64
            or points.shape != (node_count, 2) or weights.shape != (node_count,)
            or not np.isfinite(points).all() or not np.isfinite(weights).all()
            or np.any(weights <= 0) or np.any(points < 0) or np.any(points > 1)
            or abs(float(weights.sum()) - 1) > 32 * np.finfo(float).eps
            or array_identity(points) != array_identity(gauss_points)
            or array_identity(weights) != array_identity(gauss_weights)):
        raise ValueError("primary production-default rule and public Gauss bytes differ")
    del gauss_points, gauss_weights
    count_modes = len(selected_modes)
    # Reserve both full vectors and the worst-case complete masked outputs.
    output_bytes = count_modes * n * (3 * 16 + 4 + 16 + 1)
    budget.persistent = BOOKKEEPING_BYTES + rule_bytes
    budget.before("complete_selected_native_outputs", output_bytes)
    b_FE = np.zeros((count_modes, n), dtype=np.complex128)
    raw_MPC = np.zeros_like(b_FE)
    masked_full = np.zeros_like(b_FE)
    masks = np.zeros((count_modes, n), dtype=bool)
    budget.persistent += output_bytes
    facet_records = []
    for rectangle in rectangles:
        cell = int(rectangle.cell)
        budget.before("actual_facet_cell_geometry_and_dofs", 1 << 20, facet=rectangle.facet, cell=cell)
        geometry = np.ascontiguousarray(msh.geometry.x[msh.geometry.dofmap[cell]], dtype=np.float64)
        origin, J, determinant, K = affine_geometry(geometry)
        dofs = np.asarray(V.dofmap.cell_dofs(cell))
        if (dofs.shape != (CELL_DOFS,) or dofs.dtype != np.int32
                or len(np.unique(dofs)) != CELL_DOFS or np.any(dofs < 0) or np.any(dofs >= n)):
            raise ValueError("actual native cell DoFs are invalid or repeat")
        info = int(permutations[cell])
        facet_records.append({**rectangle.__dict__, "cell_info": info,
                              "cell_geometry": array_identity(geometry),
                              "cell_dofs": array_identity(dofs),
                              "J": J.tolist(), "detJ": determinant, "K": K.tolist()})
        for start in range(0, node_count, chunk_size):
            stop = min(start + chunk_size, node_count)
            count = stop - start
            table_bytes = count * CELL_DOFS * 3 * 8
            # Two real tables; potential complex component conversion; geometry,
            # phases, local vectors and Python bookkeeping. No D*D transform.
            named = 2 * table_bytes + count * CELL_DOFS * 16 + count * 256 + CELL_DOFS * 64 + (1 << 20)
            native = 4 * count * 7**3 * 3 * 8 + 2 * table_bytes
            facts = {"facet": rectangle.facet, "cell": cell, "start": start, "stop": stop,
                     "chunk_points": count, "dense_orientation_matrix_bytes": 0}
            budget.before("physical_quadrature_chunk", named, native, **facts)
            xyz, physical_weights, cells = reference.map_chunk(rectangle, points[start:stop], weights[start:stop])
            budget.before("public_coordinate_pull_back", named, native, **facts)
            X = msh.geometry.cmap.pull_back(xyz, geometry)
            expected = (xyz - origin) @ K.T
            if (X.shape != (count, 3) or X.dtype != np.float64 or not np.isfinite(X).all()
                    or not np.allclose(X, expected, rtol=0, atol=256 * np.finfo(float).eps)):
                _numerical_failure("actual public pull-back differs from admitted affine map", "pullback",
                                   {"X": X, "expected": expected, "xyz": xyz, "partial_b_FE": b_FE},
                                   root, budget, event, extra_live=named + native)
            budget.before("public_coordinate_roundtrip", named, native, **facts)
            roundtrip = msh.geometry.cmap.push_forward(X, geometry)
            geometry_scale = float(np.max(np.abs(geometry), initial=1.0))
            if not np.allclose(roundtrip, xyz, rtol=0, atol=256 * np.finfo(float).eps * geometry_scale):
                _numerical_failure("actual public coordinate roundtrip failed", "roundtrip",
                                   {"roundtrip": roundtrip, "xyz": xyz, "partial_b_FE": b_FE}, root, budget, event,
                                   extra_live=named + native)
            del expected, roundtrip
            budget.before("public_basix_tabulate_zero_derivatives", named, native, **facts)
            tabulation = basis.tabulate(0, X)
            if (tabulation.shape != (1, count, CELL_DOFS, 3) or tabulation.dtype != np.float64
                    or not tabulation.flags.c_contiguous or not np.isfinite(tabulation).all()):
                _numerical_failure("actual native Basix chunk tabulation mismatch", "tabulation",
                                   {"tabulation": tabulation, "X": X, "partial_b_FE": b_FE}, root, budget, event,
                                   extra_live=named + native)
            values = tabulation[0]
            budget.before("public_native_T_apply_basis", named, native, **facts)
            apply_native_basis_orientation(basis, values, info)
            budget.before("public_covariant_Piola_push_forward", named, native, **facts)
            mapped = basis.push_forward(values.reshape(1, count * CELL_DOFS, 3),
                                        J[None, :, :], np.array([determinant], dtype=np.float64),
                                        K[None, :, :]).reshape(count, CELL_DOFS, 3)
            if mapped.dtype != np.float64 or not np.isfinite(mapped).all():
                _numerical_failure("nonfinite or nonreal actual physical basis", "Piola",
                                   {"mapped_basis": mapped, "partial_b_FE": b_FE}, root, budget, event,
                                   extra_live=named + native)
            for phase_key, positions in phase_groups.items():
                budget.before("actual_centered_phase_and_full_local_contraction", named, native, **facts)
                try:
                    phase = reference._phase_chunk(xyz, *phase_key, rectangle.zplane)
                except (FloatingPointError, ValueError) as error:
                    _numerical_failure(str(error), "phase",
                                       {"xyz": xyz, "physical_weights": physical_weights, "partial_b_FE": b_FE},
                                       root, budget, event, extra_live=named + native)
                weighted_phase = physical_weights * phase
                # Basis/geometry are real: conj(phi_x) is exactly phi_x. Phase
                # stays un-conjugated. T acts on basis rows, never T^-H.
                local = np.einsum("q,qj->j", weighted_phase, mapped[:, :, 0], optimize=False)
                if local.dtype != np.complex128 or not np.isfinite(local).all():
                    _numerical_failure("nonfinite full native local vector", "contraction",
                                       {"local": local, "weighted_phase": weighted_phase,
                                        "partial_b_FE": b_FE}, root, budget, event, extra_live=named + native)
                budget.before("full_native_cell_scatter", named, native, **facts)
                for position in positions:
                    np.add.at(b_FE[position], dofs, local)
                del phase, weighted_phase, local
            del mapped, values, tabulation, X, xyz, physical_weights, cells
        del geometry
    masked_rows, masked_values, component_records = [], [], []
    for position, inventory_index in enumerate(selected_indices):
        b_fe_artifact = None if root is None else _save(root / f"mode_{inventory_index}_top_x_b_FE.npy", b_FE[position], budget)
        event({"kind": "native_complete_b_FE_saved_before_projection", "original_mode_index": inventory_index,
               "artifact": b_fe_artifact})
        budget.before("finalized_exact_MPC_KH_projection", dual_workspace,
                      actual_coefficient_nnz=len(coefficients), actual_master_nnz=len(masters))
        def preserve_failed_projection(value):
            artifact = None if root is None else _save(root / f"mode_{inventory_index}_top_x_failed_raw.npy", value, budget)
            event({"kind": "native_failed_projection_saved", "original_mode_index": inventory_index, "artifact": artifact})
        raw_MPC[position] = dual_project(b_FE[position], slaves, masters, coefficients, offsets,
                                         failure_callback=preserve_failed_projection)
        raw_artifact = None if root is None else _save(root / f"mode_{inventory_index}_top_x_raw.npy", raw_MPC[position], budget)
        event({"kind": "native_complete_raw_MPC_saved_before_mask", "original_mode_index": inventory_index,
               "artifact": raw_artifact})
        budget.before("unchanged_post_projection_mask", n * 80)
        rows, values, cutoff = unchanged_mask(raw_MPC[position])
        masked_rows.append(rows)
        masked_values.append(values)
        masked_full[position, rows] = values
        masks[position, rows] = True
        removed = np.abs(raw_MPC[position]) <= cutoff
        if not np.array_equal(rows, np.flatnonzero(~removed)) or not np.array_equal(values, raw_MPC[position, rows]):
            raise ValueError("existing cutoff does not reproduce its own raw vector")
        item = {"original_mode_index": inventory_index,
                "original_mode_key": [inventory_index, "top", int(selected_modes[position].m),
                                      int(selected_modes[position].n), selected_modes[position].polarization],
                "b_FE": array_identity(b_FE[position]), "raw_MPC": array_identity(raw_MPC[position]),
                "masked_rows": array_identity(rows), "masked_values": array_identity(values),
                "masked_full": array_identity(masked_full[position]), "mask": array_identity(masks[position]),
                "cutoff": cutoff, "raw_nonzero_entries": int(np.count_nonzero(raw_MPC[position])),
                "masked_entries": len(rows), "exact_slave_zero": bool(np.all(raw_MPC[position, slaves] == 0)),
                "cutoff_removed_l2": float(np.linalg.norm(raw_MPC[position, removed])),
                "cutoff_removed_max_abs": float(np.max(np.abs(raw_MPC[position, removed]), initial=0)),
                "existing_mask_equals_own_raw_unchanged_cutoff": True}
        if root is not None:
            item["artifacts"] = {label: _save(root / f"mode_{inventory_index}_top_x_{label}.npy", value, budget)
                                 for label, value in (("masked_rows", rows), ("masked_values", values),
                                                      ("masked_full", masked_full[position]), ("mask", masks[position]))}
            item["artifacts"].update(b_FE=b_fe_artifact, raw=raw_artifact)
        component_records.append(item)
        event({"kind": "native_selected_component_finished", **item})
    if not np.isfinite(b_FE).all() or not np.isfinite(raw_MPC).all():
        raise FloatingPointError("nonfinite accumulated full native vectors")
    source_path = Path(__file__).resolve()
    record = {"schema": SCHEMA, "status": "ASSEMBLED_PENDING_INDEPENDENT_QUALIFICATION",
              "scope": "original_target_degree160_selected_top_x" if quadrature_degree == 160 else "mechanism_degree27_witness_only_not_target_qualification",
              "source": {"path": str(source_path), "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest()},
              "pinned_reference_source": reference_source, "native_layout": layout,
              "basis_hash": int(basis.hash()), "basis_map_type": basis.map_type.name,
              "native_rows": n, "expected_rows_derivation": "104*6 + 75*60 + 18*450",
              "MPC_max_expansion_width": width,
              "MPC": {label: array_identity(value) for label, value in (("slaves", slaves), ("masters", masters), ("coefficients", coefficients), ("offsets", offsets))},
              "cell_permutations": array_identity(permutations), "facets": facet_records,
              "quadrature_degree": quadrature_degree, "quadrature_rule": "Basix.default/standard.quadrilateral",
              "default_gauss_points_weights_byte_equal": True, "actual_nodes_per_facet": node_count,
              "points": rule_signature(points), "weights": rule_signature(weights),
              "rule_array_identities": {"points": array_identity(points), "weights": array_identity(weights)},
              "rule_artifacts": rule_artifacts,
              "chunk_maximum": chunk_size, "distinct_phase_tuples": len(phase_groups),
              "selected_original_mode_indices": list(selected_indices), "selected_components": component_records,
              "orientation_convention": "real standard native T on basis rows before covariant Piola; no dense transform",
              "orientation_template_reuse": "one borrowed native Basix element reuses its prepared finite edge/face transformations for every cell and chunk",
              "unique_actual_cell_orientation_states": sorted(set(int(permutations[r.cell]) for r in rectangles)),
              "primal_dual_convention": "vdot(u_master,b_MPC)=integral phase*conj(Function.eval(Ku)_x); b_MPC=K^H*b_FE",
              "basis_values_unthresholded": True, "FFCx_byte_equivalence_claimed": False,
              "owned_workspace_admission_maximum_bytes": budget.maximum,
              "retained_bookkeeping_allowance_bytes": BOOKKEEPING_BYTES,
              "owned_buffer_limit_bytes": OWNED_BUFFER_LIMIT, "estimate_is_measured_RSS": False,
              "full_C_D_qualification": False, "PDE_qualification": False,
              "mesh_space_form_JIT_factor_PDE_creation_calls": 0}
    return {"record": record, "arrays": {"b_FE": b_FE, "raw_MPC": raw_MPC,
            "masked_rows": tuple(masked_rows), "masked_values": tuple(masked_values),
            "masked_full": masked_full, "masks": masks,
            "rule_points": points, "rule_weights": weights}}
