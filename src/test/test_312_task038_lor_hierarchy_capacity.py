"""Pure local S5-A1 interlevel transfer tests."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from src.solvers.fullspace_lor_memory_hierarchy import (
    ADJOINT_LIMIT,
    CURL_LIMIT,
    EDGE_QUADRATURE_LIMIT,
    GRADIENT_LIMIT,
    INTERLEVEL_BATCH_CELL_CAP,
    LINEARITY_LIMIT,
    REPEAT_LIMIT,
    _edge_endpoints,
    _structural_trace_mask,
    audit_local_interlevel_transfer,
    build_local_interlevel_edge_transfer,
)
from src.solvers import fullspace_lor_memory_hierarchy_runtime as s5_runtime


@pytest.fixture(scope="module", params=[(6, 3), (3, 1)])
def interlevel(request):
    fine_degree, coarse_degree = request.param
    return (
        fine_degree,
        coarse_degree,
        build_local_interlevel_edge_transfer(fine_degree, coarse_degree),
    )


def test_interlevel_shape_bytes_and_independent_audit(
    interlevel,
) -> None:
    fine_degree, coarse_degree, transfer = interlevel
    expected_shape = (
        3 * fine_degree * (fine_degree + 1) ** 2,
        3 * coarse_degree * (coarse_degree + 1) ** 2,
    )
    expected_node_shape = (
        (fine_degree + 1) ** 3,
        (coarse_degree + 1) ** 3,
    )
    assert transfer.edge_transfer.shape == expected_shape
    assert transfer.node_transfer.shape == expected_node_shape
    assert transfer.edge_transfer.dtype == np.complex128
    assert transfer.node_transfer.dtype == np.complex128
    assert transfer.edge_transfer.nbytes == expected_shape[0] * expected_shape[1] * 16
    assert transfer.node_transfer.nbytes == (
        expected_node_shape[0] * expected_node_shape[1] * 16
    )
    assert transfer.edge_transfer.flags.writeable is False
    assert transfer.node_transfer.flags.writeable is False
    assert transfer.audit["edge_line_integral_relative"] <= EDGE_QUADRATURE_LIMIT
    assert transfer.audit["curl_flux_relative"] <= CURL_LIMIT
    assert transfer.audit["gradient_commuting_relative"] <= GRADIENT_LIMIT
    assert transfer.audit["adjoint_work_relative"] <= ADJOINT_LIMIT
    assert transfer.audit["linearity_relative"] <= LINEARITY_LIMIT
    assert transfer.audit["repeat_relative"] <= REPEAT_LIMIT
    assert transfer.audit["simple_injection"] is False
    assert transfer.audit["line_integral_histopolation"] is True
    assert transfer.audit["oracle_workspace_retained"] is False
    assert transfer.audit["global_transfer_matrix"] is False
    allowed = _structural_trace_mask(fine_degree, coarse_degree)
    assert np.count_nonzero(transfer.edge_transfer[~allowed]) == 0
    assert transfer.audit["structural_projection"] is True
    assert transfer.audit["structural_forbidden_entry_count"] == int(
        np.count_nonzero(~allowed)
    )
    assert transfer.audit["structural_forbidden_nnz_after"] == 0
    removed_count = int(transfer.audit["structural_removed_nonzero_count"])
    removed_max_abs = float(transfer.audit["structural_removed_max_abs"])
    forbidden_count = int(transfer.audit["structural_forbidden_entry_count"])
    assert 0 <= removed_count <= forbidden_count
    assert np.isfinite(removed_max_abs) and removed_max_abs >= 0.0
    if removed_count == 0:
        assert removed_max_abs == 0.0
    else:
        assert removed_max_abs > 0.0


def _shared_face_trace_ratio(transfer, axis: int) -> float:
    fine_degree = int(transfer.fine_degree)
    coarse_degree = int(transfer.coarse_degree)
    fine_start, fine_end = _edge_endpoints(fine_degree)
    coarse_start, coarse_end = _edge_endpoints(coarse_degree)
    cells: list[dict[tuple[tuple[int, ...], tuple[int, ...]], complex]] = []
    for cell in range(2):
        offset = np.zeros(3, dtype=np.int32)
        if cell:
            offset[axis] = 1
        coarse = np.empty(coarse_start.shape[0], dtype=np.complex128)
        for column, (start, end) in enumerate(
            zip(coarse_start, coarse_end, strict=True)
        ):
            shared_coordinate = coarse_degree if cell == 0 else 0
            on_shared_face = (
                int(start[axis]) == int(end[axis]) == shared_coordinate
            )
            if on_shared_face:
                coarse[column] = 0.0
            else:
                coarse[column] = (1000.0 + 17.0 * column) * (cell + 1) + 1j * (
                    3.0 + column + 11.0 * cell
                )
        fine_values = transfer.apply_primal_many(coarse)
        cell_values: dict[tuple[tuple[int, ...], tuple[int, ...]], complex] = {}
        shared_coordinate = fine_degree if cell == 0 else 0
        for row, (start, end) in enumerate(zip(fine_start, fine_end, strict=True)):
            if (
                int(start[axis]) != int(end[axis])
                or int(start[axis]) != shared_coordinate
            ):
                continue
            shifted_start = tuple(
                (np.asarray(start) + offset * fine_degree).tolist()
            )
            shifted_end = tuple((np.asarray(end) + offset * fine_degree).tolist())
            cell_values[(shifted_start, shifted_end)] = fine_values[row]
        cells.append(cell_values)
    common = set(cells[0]).intersection(cells[1])
    assert common
    values = np.asarray(
        [cells[0][key] for key in common] + [cells[1][key] for key in common],
        dtype=np.complex128,
    )
    assert np.array_equal(values, np.zeros_like(values))
    return max(
        abs(cells[0][key] - cells[1][key])
        / (1.0e-12 * max(1.0, abs(cells[0][key]), abs(cells[1][key])))
        for key in common
    )


@pytest.mark.parametrize("axis", [0, 1, 2])
def test_structural_projection_blocks_shared_face_leakage(interlevel, axis: int) -> None:
    _fine_degree, _coarse_degree, transfer = interlevel
    assert _shared_face_trace_ratio(transfer, axis) <= 1.0


def test_interlevel_apply_and_hand_checked_adjoint(
    interlevel,
) -> None:
    fine_degree, _coarse_degree, transfer = interlevel
    rng = np.random.default_rng(3120 + fine_degree)
    coarse = rng.normal(size=transfer.edge_shape[1]) + 1j * rng.normal(
        size=transfer.edge_shape[1]
    )
    second = rng.normal(size=transfer.edge_shape[1]) + 1j * rng.normal(
        size=transfer.edge_shape[1]
    )
    fine = rng.normal(size=transfer.edge_shape[0]) + 1j * rng.normal(
        size=transfer.edge_shape[0]
    )
    before = coarse.copy()
    alpha = 0.37 + 0.19j
    beta = -0.23 + 0.41j
    observed = transfer.apply_primal_many(coarse)
    repeated = transfer.apply_primal_many(coarse)
    combined = transfer.apply_primal_many(alpha * coarse + beta * second)
    expected = alpha * observed + beta * transfer.apply_primal_many(second)
    adjoint = transfer.apply_adjoint_many(fine)
    lhs = np.vdot(observed, fine)
    rhs = np.vdot(coarse, adjoint)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= ADJOINT_LIMIT
    assert np.linalg.norm(combined - expected) / max(
        np.linalg.norm(expected), np.finfo(float).tiny
    ) <= LINEARITY_LIMIT
    assert np.linalg.norm(repeated - observed) / max(
        np.linalg.norm(observed), np.finfo(float).tiny
    ) <= REPEAT_LIMIT
    np.testing.assert_array_equal(coarse, before)
    assert np.all(np.isfinite(observed))
    assert np.all(np.isfinite(adjoint))
    assert transfer.apply_primal_many(
        np.stack([coarse] * INTERLEVEL_BATCH_CELL_CAP)
    ).shape == (INTERLEVEL_BATCH_CELL_CAP, transfer.edge_shape[0])
    with pytest.raises(ValueError, match="fixed cap"):
        transfer.apply_primal_many(
            np.stack([coarse] * (INTERLEVEL_BATCH_CELL_CAP + 1))
        )


def test_mutated_map_fails_independent_audit(
    interlevel,
) -> None:
    fine_degree, coarse_degree, transfer = interlevel
    bad_edge = transfer.edge_transfer.copy()
    bad_edge[0, 0] += 0.125 + 0.25j
    with pytest.raises(ValueError):
        audit_local_interlevel_transfer(
            fine_degree,
            coarse_degree,
            bad_edge,
            transfer.node_transfer,
        )


def test_forbidden_entry_fails_exact_zero_audit() -> None:
    transfer = build_local_interlevel_edge_transfer(6, 3)
    bad_edge = transfer.edge_transfer.copy()
    forbidden_row, forbidden_column = np.argwhere(
        ~_structural_trace_mask(6, 3)
    )[0]
    bad_edge[forbidden_row, forbidden_column] = 0.125 + 0.25j
    with pytest.raises(ValueError, match="structural forbidden"):
        audit_local_interlevel_transfer(
            6,
            3,
            bad_edge,
            transfer.node_transfer,
        )


def test_module_has_no_global_or_runtime_solver_dependencies() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_memory_hierarchy.py"
    source = path.read_text(encoding="utf-8")
    lowered = source.lower()
    assert "allgather" not in lowered
    assert "petsc" not in lowered
    assert "mpi" not in lowered
    assert "solver" not in lowered
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name not in {"mpi4py", "petsc4py", "dolfinx"} for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module not in {"mpi4py", "petsc4py", "dolfinx"}


def test_interlevel_object_is_immutable() -> None:
    transfer = build_local_interlevel_edge_transfer(3, 1)
    with pytest.raises(ValueError):
        transfer.edge_transfer[0, 0] = 1.0
    with pytest.raises(AttributeError):
        transfer.fine_degree = 1
    with pytest.raises(TypeError):
        transfer.audit["fine_degree"] = 1


class _FakeTopology:
    """Distinct parent/raw owner authorities with one repeated raw edge."""

    def __init__(self, edge_count: int, block_count: int, *, raw: bool) -> None:
        self.edge_count = int(edge_count)
        self.cell_edge_ids = np.arange(
            self.edge_count * block_count, dtype=np.uint32
        ).reshape(block_count, self.edge_count)
        if raw:
            # A raw edge can occur in multiple refined subcells; it is still
            # one owner value and must not change parent-cell multiplicity.
            self.cell_edge_ids[1, 0] = self.cell_edge_ids[0, 0]
        self.unique_edge_ids = np.arange(
            self.edge_count * block_count, dtype=np.uint32
        )
        self.owned_edge_ids = self.unique_edge_ids.copy()
        self.cell_orientation = np.ones_like(self.cell_edge_ids, dtype=np.int8)
        self.cell_phase_codes = np.zeros_like(self.cell_edge_ids, dtype=np.uint8)
        self.phase_values = np.ones(1, dtype=np.complex128)
        self.owner_schedule = {}
        self.owner_received_sort_order = np.empty(0, dtype=np.int32)
        self.owner_received_sorted_ids = np.empty(0, dtype=np.uint32)
        self.owner_received_group_starts = np.empty(0, dtype=np.int32)
        self.pull_schedule = {}
        self.pull_received_positions = np.empty(0, dtype=np.int32)
        self.pull_send_positions = np.empty(0, dtype=np.int32)
        self.audit = {
            "global_unique_edge_count": int(self.unique_edge_ids.size)
        }

    def pull_owner_unique_values(self, ids, values):
        ids = np.asarray(ids, dtype=np.uint32)
        values = np.asarray(values, dtype=np.complex128)
        np.testing.assert_array_equal(ids, self.owned_edge_ids)
        assert values.shape == ids.shape
        return values.copy()

    def cell_values_from_unique(self, values, start, stop):
        values = np.asarray(values, dtype=np.complex128)
        return values[self.cell_edge_ids[int(start):int(stop)]]

    def _route(self, blocks, *, additive: bool):
        output = np.zeros(self.owned_edge_ids.size, dtype=np.complex128)
        seen = np.zeros(output.size, dtype=bool)
        expected = 0
        for start, block in blocks:
            assert int(start) == expected
            block = np.asarray(block, dtype=np.complex128)
            stop = expected + block.shape[0]
            assert block.shape[1] == self.edge_count
            ids = self.cell_edge_ids[expected:stop]
            for row, row_ids in zip(block, ids, strict=True):
                if additive:
                    np.add.at(output, row_ids, row)
                else:
                    for owner, value in zip(row_ids, row, strict=True):
                        owner = int(owner)
                        if seen[owner]:
                            np.testing.assert_allclose(output[owner], value)
                        output[owner] = value
                        seen[owner] = True
            expected = stop
        assert expected == self.cell_edge_ids.shape[0]
        if not additive:
            assert np.all(seen)
        return self.owned_edge_ids.copy(), output

    def route_owner_cell_chunks(self, blocks):
        return self._route(blocks, additive=False)

    def route_owner_cell_chunks_additive(self, blocks):
        return self._route(blocks, additive=True)


class _FakeS5Level:
    """Small parent/raw owner-packet double used for lifecycle and bridge tests."""

    def __init__(self, degree: int, local_size: int, block_count: int, matrix) -> None:
        self.degree = degree
        self.block_count = block_count
        self.local_size = local_size
        self.matrix = matrix
        self.parent_topology = _FakeTopology(local_size, block_count, raw=False)
        self.raw_topology = _FakeTopology(local_size, block_count, raw=True)
        self.incidence_unique = np.ones(
            self.parent_topology.unique_edge_ids.size, dtype=np.float64
        )
        self.raw_permutations = np.zeros((block_count, 12), dtype=np.int32)
        self.destroy_count = 0
        self.audit = {
            "retained_known_bytes": {
                "matrix_index_bytes": 16,
                "matrix_numeric_bytes": 32,
            }
        }

    @property
    def parent_block_count(self):
        return self.block_count

    def _raw_to_parent(self, source):
        values = np.asarray(source, dtype=np.complex128)
        ids = self.raw_topology.owned_edge_ids
        assert values.shape == ids.shape
        return self.parent_topology.unique_edge_ids.copy(), self.parent_topology.pull_owner_unique_values(ids, values)

    def primal_to_owner(self, source):
        return self._raw_to_parent(source)

    def dual_to_owner(self, source):
        return self._raw_to_parent(source)

    def expand_primal(self, packet, start, stop):
        return self.parent_topology.cell_values_from_unique(packet[1], start, stop)

    def expand_dual(self, packet, start, stop):
        rows = self.parent_topology.cell_values_from_unique(packet[1], start, stop)
        positions = np.searchsorted(
            self.parent_topology.unique_edge_ids,
            self.parent_topology.cell_edge_ids[start:stop],
        )
        return rows / self.incidence_unique[positions]

    def route_primal_blocks(self, blocks):
        return self.parent_topology.route_owner_cell_chunks(blocks)

    def route_dual_blocks(self, blocks):
        return self.parent_topology.route_owner_cell_chunks_additive(blocks)

    def _parent_to_raw(self, packet):
        return self.raw_topology.pull_owner_unique_values(*packet).copy()

    def owner_to_primal(self, packet):
        return self._parent_to_raw(packet)

    def owner_to_dual(self, packet):
        return self._parent_to_raw(packet)

    def destroy(self):
        self.destroy_count += 1


class _FakeUnequalOwnerTopology:
    def __init__(self) -> None:
        self.owned_edge_ids = np.asarray([1, 3], dtype=np.uint32)
        self.unique_edge_ids = np.arange(4, dtype=np.uint32)

    def pull_owner_unique_values(self, ids, values):
        np.testing.assert_array_equal(ids, self.owned_edge_ids)
        assert np.asarray(values).shape == ids.shape
        return np.asarray([10, 20, 30, 40], dtype=np.complex128)


class _FakeMatrix:
    def __init__(self, name: str) -> None:
        self.name = name
        self.destroy_count = 0

    def destroy(self):
        self.destroy_count += 1


class _FakeVec:
    def __init__(self, local_size: int) -> None:
        self.local_size = int(local_size)

    def getLocalSize(self):
        return self.local_size


class _FakeSmoother:
    def __init__(self, local_size: int) -> None:
        self.destroy_count = 0
        self.apply_count = 0
        self._inv_sqrt = _FakeVec(local_size)

    def apply_into(self, source, target):
        target[:] = 0.5 * np.asarray(source, dtype=np.complex128)
        self.apply_count += 1
        return {"matrix_mult_count": 2, "apply_count": self.apply_count}

    def destroy(self):
        self.destroy_count += 1


def _fake_local_transfer(fine_degree: int, coarse_degree: int):
    shape = (
        3 * fine_degree * (fine_degree + 1) ** 2,
        3 * coarse_degree * (coarse_degree + 1) ** 2,
    )
    matrix = np.zeros(shape, dtype=np.complex128)
    diagonal = min(shape)
    matrix[np.arange(diagonal), np.arange(diagonal)] = 1.0 + 0.25j
    audit = {
        "edge_numeric_bytes": int(matrix.nbytes),
        "node_numeric_bytes": 0,
        "global_transfer_matrix": False,
        "oracle_workspace_retained": False,
    }
    from src.solvers.fullspace_lor_memory_hierarchy import LocalInterlevelEdgeTransfer

    return LocalInterlevelEdgeTransfer(
        fine_degree, coarse_degree, matrix, np.ones((1, 1), dtype=np.complex128), audit
    )


def test_s5_runtime_packet_uses_local_unique_inventory() -> None:
    topology = _FakeUnequalOwnerTopology()
    ids, values = s5_runtime._pull_unique_packet(
        topology,
        (topology.owned_edge_ids, np.asarray([1.0 + 0.0j, 2.0 + 0.0j])),
    )
    np.testing.assert_array_equal(ids, topology.unique_edge_ids)
    assert values.shape == topology.unique_edge_ids.shape


def test_s5_runtime_owner_packet_work_and_smoother_metadata() -> None:
    fine = _FakeS5Level(6, 882, 2, _FakeMatrix("level6"))
    middle = _FakeS5Level(3, 144, 2, _FakeMatrix("level3"))
    coarse = _FakeS5Level(1, 12, 2, _FakeMatrix("level1"))
    coarse.parent_topology = coarse.raw_topology
    coarse.incidence_unique[0] = 2.0
    assert fine.parent_topology is not fine.raw_topology
    assert fine.raw_topology.cell_edge_ids[0, 0] == fine.raw_topology.cell_edge_ids[1, 0]
    assert middle.parent_topology is not middle.raw_topology
    transfer_63 = s5_runtime._OwnerPacketTransfer(
        fine, middle, _fake_local_transfer(6, 3)
    )
    transfer_31 = s5_runtime._OwnerPacketTransfer(
        middle, coarse, _fake_local_transfer(3, 1)
    )
    assert transfer_63.audit["local_map"]["edge_rows"] == 882
    assert transfer_63.audit["local_map"]["edge_cols"] == 144
    assert transfer_63.audit["local_map"]["edge_exact_nnz"] == 144
    foundation = type("Foundation", (), {})()
    foundation.low_matrix = fine.matrix
    smoother6 = _FakeSmoother(882)
    smoother3 = _FakeSmoother(144)
    extension = s5_runtime.S5HierarchyExtension(
        foundation,
        fine,
        middle,
        coarse,
        transfer_63,
        transfer_31,
        smoother6,
        smoother3,
    )
    source = np.arange(288, dtype=np.float64).astype(np.complex128)
    source += 0.25j * np.arange(288, dtype=np.float64)
    before = source.copy()
    result = extension.apply_primal((6, 3), source)
    fine_probe = (
        np.arange(1764, dtype=np.float64).astype(np.complex128)
        + 0.5j * np.arange(1764, dtype=np.float64)
    )
    adjoint = extension.apply_adjoint((6, 3), fine_probe)
    assert result.shape == fine_probe.shape
    assert adjoint.shape == source.shape
    assert np.all(np.isfinite(result))
    assert np.array_equal(source, before)
    lhs = np.vdot(result, fine_probe)
    rhs = np.vdot(source, adjoint)
    assert abs(lhs - rhs) / max(abs(rhs), np.finfo(float).tiny) <= 1.0e-12
    fine.raw_topology.cell_edge_ids[1, 0] = fine.raw_topology.cell_edge_ids[1, 1]
    np.testing.assert_array_equal(
        result, extension.apply_primal((6, 3), source)
    )
    np.testing.assert_array_equal(
        adjoint, extension.apply_adjoint((6, 3), fine_probe)
    )
    repeat = extension.apply_primal((6, 3), source)
    assert np.array_equal(result, repeat)
    source31 = np.arange(24, dtype=np.float64).astype(np.complex128)
    result31 = extension.apply_primal((3, 1), source31)
    probe31 = np.arange(288, dtype=np.float64).astype(np.complex128)
    adjoint31 = extension.apply_adjoint((3, 1), probe31)
    assert result31.shape == probe31.shape
    assert adjoint31.shape == source31.shape
    assert abs(np.vdot(result31, probe31) - np.vdot(source31, adjoint31)) / max(
        abs(np.vdot(source31, adjoint31)), np.finfo(float).tiny
    ) <= 1.0e-12
    target = np.empty_like(source)
    facts = extension.apply_smoother(6, source, target)
    assert facts["fixed_chebyshev_degree"] == 3
    assert facts["fixed_power_steps"] == 10
    assert set(extension.smoothers) == {6, 3}
    with pytest.raises(ValueError, match="only on levels 6 and 3"):
        extension.apply_smoother(1, source, target)
    ledger = extension.retained_ledger({"process_tree": {"rss_bytes": 100000}})
    assert ledger["known_total_bytes"] > 0
    assert ledger["unattributed_remainder_bytes"] == (
        100000 - ledger["known_total_bytes"]
    )
    for key in (
        "level3_raw_permutations_bytes",
        "level3_incidence_unique_bytes",
        "level3_parent_topology_retained_array_bytes",
        "level3_raw_topology_retained_array_bytes",
        "level1_raw_permutations_bytes",
        "transfer_6_3_edge_bytes",
        "level6_chebyshev_work_vector_bytes",
        "level3_chebyshev_work_vector_bytes",
    ):
        assert key in ledger["known_bytes"]
    assert ledger["known_bytes"]["level3_incidence_unique_bytes"] > 0
    assert ledger["topology_aliases"]["level1_parent_raw_topology_shared"] is True
    assert not hasattr(fine, "parent_incidence")
    extension.destroy()
    assert foundation.low_matrix.destroy_count == 0
    assert middle.destroy_count == 1
    assert coarse.destroy_count == 1
    assert smoother6.destroy_count == 1
    assert smoother3.destroy_count == 1
    extension.destroy()
    assert middle.destroy_count == 1


def test_s5_runtime_fixed_builder_and_forbidden_contract() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_memory_hierarchy_runtime.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "build_s5_hierarchy_extension" in function_names
    assert "level_builder" not in source
    assert "_BlockLayout" not in source
    assert "foundation.refined_axes" not in source
    assert "foundation.comm" not in source
    assert "_raw_axes" not in source
    assert "foundation.high_mesh.comm" in source
    assert "parent_topology" in source and "raw_topology" in source
    assert "parent_incidence" not in source
    assert "incidence_unique" in source
    assert "build_canonical_lor_subedge_topology(" in source
    assert "build_local_lor_transfer(3)" in source
    assert "global_transfer_matrix = True" not in source
    assert "numeric_allgather = True" not in source
    assert "build_s5_hierarchy_extension(foundation" in source


def test_s5_build_level_refined_axis_lazy_import_provenance() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_memory_hierarchy_runtime.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    build_level = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_build_level"
    )
    geometry_names: list[str] = []
    fixture_names: list[str] = []
    for node in ast.walk(build_level):
        if not isinstance(node, ast.ImportFrom):
            continue
        names = [alias.name for alias in node.names]
        if node.module == "src.geometry.mesh_builder_3d":
            geometry_names.extend(names)
        if node.module and node.module.endswith("fullspace_lor_native_hx_fixture"):
            fixture_names.extend(names)
    assert "_refined_axis" not in geometry_names
    assert "_refined_axis" in fixture_names
