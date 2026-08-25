"""Pure Route-B runtime bridge and explicit-probe-level contracts."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers import fullspace_lor_interlevel_spectral_dolfinx as adapter
from src.solvers import fullspace_lor_memory_hierarchy_runtime as runtime
from src.solvers.fullspace_lor_nested_interlevel_runtime import (
    RouteBNestedHierarchyExtension,
)
from src.test.test_312_task038_lor_hierarchy_capacity import (
    _FakeMatrix,
    _FakeS5Level,
    _FakeTopology,
    _fake_local_transfer,
)


def test_s5_defaults_and_route_b_opt_in_are_frozen() -> None:
    assert runtime.S5_LEVELS == (6, 3, 1)
    assert runtime.S5_PAIRS == ((6, 3), (3, 1))
    assert runtime.ROUTE_B_LEVELS == (6, 2, 1)
    assert runtime.ROUTE_B_PAIRS == ((6, 2), (2, 1))
    with pytest.raises(ValueError, match="not enabled"):
        runtime._build_level(object(), 2, (), allowed_levels=runtime.S5_LEVELS)


def test_canonical_owner_and_raw_petsc_owner_contracts_are_separate() -> None:
    runtime_source = (
        Path(__file__).parents[1]
        / "solvers"
        / "fullspace_lor_memory_hierarchy_runtime.py"
    ).read_text(encoding="utf-8")
    nested_source = (
        Path(__file__).parents[1]
        / "solvers"
        / "fullspace_lor_nested_interlevel_runtime.py"
    ).read_text(encoding="utf-8")
    assert "validate_canonical_owner_identity" in runtime_source
    assert "validate_local_owner_layout=False" in runtime_source
    assert "validate_raw_map_layout" not in runtime_source
    assert nested_source.count("validate_canonical_owner_identity=True") == 3


def _route_b_fake_extension() -> tuple[RouteBNestedHierarchyExtension, object, list]:
    foundation_matrix = _FakeMatrix("foundation-low")
    level6 = _FakeS5Level(6, 882, 2, foundation_matrix)
    level2 = _FakeS5Level(2, 54, 2, _FakeMatrix("level2"))
    level1 = _FakeS5Level(1, 12, 2, _FakeMatrix("level1"))
    transfer_62 = runtime._OwnerPacketTransfer(
        level6, level2, _fake_local_transfer(6, 2),
        allowed_pairs=runtime.ROUTE_B_PAIRS,
        route_schema=runtime.ROUTE_B_SCHEMA,
    )
    transfer_21 = runtime._OwnerPacketTransfer(
        level2, level1, _fake_local_transfer(2, 1),
        allowed_pairs=runtime.ROUTE_B_PAIRS,
        route_schema=runtime.ROUTE_B_SCHEMA,
    )
    foundation = SimpleNamespace(low_matrix=foundation_matrix)
    return (
        RouteBNestedHierarchyExtension(
            foundation, level6, level2, level1, transfer_62, transfer_21
        ),
        foundation,
        [level6, level2, level1],
    )


@pytest.mark.parametrize(
    ("pair", "coarse_size", "fine_size"),
    [((6, 2), 2 * 54, 2 * 882), ((2, 1), 2 * 12, 2 * 54)],
)
def test_route_b_pair_bridge_and_owner_legality(pair, coarse_size, fine_size) -> None:
    extension, _foundation, levels = _route_b_fake_extension()
    fine, coarse = extension.pair_levels(pair)
    assert (fine.degree, coarse.degree) == pair
    source = np.arange(coarse_size, dtype=np.float64).astype(np.complex128) + 0.25j
    before = source.copy()
    result = extension.apply_primal(pair, source)
    probe = np.arange(fine_size, dtype=np.float64).astype(np.complex128) + 0.5j
    adjoint = extension.apply_adjoint(pair, probe)
    assert result.shape == (fine_size,)
    assert adjoint.shape == (coarse_size,)
    assert np.all(np.isfinite(result)) and np.all(np.isfinite(adjoint))
    assert np.array_equal(source, before)
    assert abs(np.vdot(result, probe) - np.vdot(source, adjoint)) <= 1.0e-12
    assert extension.audit["smoother_built"] is False
    assert extension.audit["ksp_created"] is False
    assert extension.audit["p1_global_direct_factor"] is False
    assert extension.audit["global_transfer_matrix"] is False
    extension.destroy()
    assert all(level.destroy_count == 1 for level in levels[1:])
    assert levels[0].destroy_count == 1
    assert extension.foundation is None
    extension.destroy()


def test_route_b_invalid_pair_is_value_error() -> None:
    extension, _foundation, _levels = _route_b_fake_extension()
    with pytest.raises(ValueError, match="Route-B pair"):
        extension.apply_primal((6, 3), np.zeros(1, dtype=np.complex128))
    with pytest.raises(ValueError, match="Route-B pair"):
        extension.apply_adjoint((3, 1), np.zeros(1, dtype=np.complex128))
    extension.destroy()


def test_route_b_production_constructor_rejects_same_count_wrong_owner_ids(monkeypatch) -> None:
    parent = _FakeTopology(12, 2, raw=False)
    raw = _FakeTopology(12, 2, raw=False)
    raw.owned_edge_ids = raw.owned_edge_ids + np.uint32(1000)
    raw_space = SimpleNamespace(
        mesh=SimpleNamespace(
            topology=SimpleNamespace(
                index_map=lambda _dim: SimpleNamespace(size_local=2)
            )
        )
    )
    monkeypatch.setattr(
        runtime, "_matrix_facts",
        lambda _matrix: {
            "rows": 1, "cols": 1, "nnz": 1, "index_bytes": 1,
            "numeric_bytes": 16, "petsc_reported_memory_bytes": 0,
            "petsc_overhead_bytes": 0, "type": "fake",
        },
    )
    with pytest.raises(ValueError, match="parent/raw owner inventories"):
        runtime._S5Level(
            degree=2, matrix=object(), raw_space=raw_space, raw_floquet=None,
            parent_topology=parent, raw_topology=raw,
            raw_map={}, raw_permutations=np.zeros((2, 12), dtype=np.int32),
            incidence_unique=np.ones(24),
        )


def test_route_b_extension_is_explicit_about_p2_for_adapter(monkeypatch) -> None:
    extension, foundation, _levels = _route_b_fake_extension()
    fine, coarse = adapter._probe_levels(
        extension, fine_degree=6, coarse_degree=2
    )
    assert (fine.degree, coarse.degree) == (6, 2)
    monkeypatch.setattr(
        adapter, "_analytic_source",
        lambda level, _foundation, _name: level,
    )
    assert adapter.build_probe_source(
        "random", foundation, extension, None,
        fine_degree=6, coarse_degree=2,
        probe_schema="task038.route-b.probe.v1",
    ) is coarse
    extension.destroy()


class _ProbeVec:
    def __init__(self, values_or_size) -> None:
        if isinstance(values_or_size, int):
            self.values = np.zeros(values_or_size, dtype=np.complex128)
        else:
            self.values = np.asarray(values_or_size, dtype=np.complex128).copy()
        self.destroyed = False

    @property
    def array(self):
        return self.values

    def getArray(self, readonly=False):
        return self.values

    def getOwnershipRange(self):
        return 0, self.values.size

    def assemble(self):
        return None

    def copy(self):
        return _ProbeVec(self.values)

    def scale(self, value):
        self.values *= value

    def axpy(self, value, other):
        self.values += value * other.values

    def destroy(self):
        self.destroyed = True


class _ProbeMatrix:
    def __init__(self, size: int) -> None:
        self.size = int(size)

    def createVecRight(self):
        return _ProbeVec(self.size)

    def createVecLeft(self):
        return _ProbeVec(self.size)

    def mult(self, source, target):
        target.values[:] = source.values


class _ProbeLevel:
    def __init__(self, degree: int, size: int) -> None:
        self.degree = int(degree)
        self.matrix = _ProbeMatrix(size)
        self.parent_topology = SimpleNamespace(
            audit={
                "phase_application": "once_in_canonical_owner_route",
                "slave_master_complete": True,
            }
        )

    def primal_to_owner(self, source):
        return (
            np.arange(source.values.size, dtype=np.uint32),
            source.values.copy(),
        )

    def dual_to_owner(self, source):
        return self.primal_to_owner(source)

    def owner_to_primal(self, packet):
        return _ProbeVec(packet[1])

    def owner_to_dual(self, packet):
        return _ProbeVec(packet[1])


class _ProbeExtension:
    def __init__(self, coarse_degree: int) -> None:
        self.fine = _ProbeLevel(6, 5)
        self.coarse = _ProbeLevel(coarse_degree, 3)

    def pair_levels(self, pair):
        assert tuple(pair) == (6, self.coarse.degree)
        return self.fine, self.coarse

    def apply_primal(self, pair, source):
        self.pair_levels(pair)
        return _ProbeVec(np.concatenate((source.values, np.zeros(2, dtype=np.complex128))))

    def apply_adjoint(self, pair, source):
        self.pair_levels(pair)
        return _ProbeVec(source.values[:3])


def test_measure_probe_preserves_route_a_b3_and_route_b_b2_raw_roles() -> None:
    source_a = _ProbeVec([1.0 + 0.5j, 2.0 + 0.25j, 3.0 + 0.75j])
    facts_a, arrays_a = adapter.measure_probe(
        "random", None, _ProbeExtension(3), source_a
    )
    assert facts_a["schema"] == adapter.PROBE_SCHEMA
    assert "b3" in arrays_a and "b2" not in arrays_a
    source_b = _ProbeVec([1.0 + 0.5j, 2.0 + 0.25j, 3.0 + 0.75j])
    facts_b, arrays_b = adapter.measure_probe(
        "random", None, _ProbeExtension(2), source_b,
        fine_degree=6, coarse_degree=2,
        probe_schema="task038.route-b.probe.v1", coarse_action_role="B2",
    )
    assert facts_b["coarse_action_role"] == "B2"
    assert "b2" in arrays_b and "b3" not in arrays_b


def test_nested_material_builder_reuses_one_p62_and_names_raw_roles(monkeypatch) -> None:
    calls = []
    p62 = np.eye(2, dtype=np.complex128)

    class Result:
        def __init__(self, digest):
            self.audit = {"class_digest": digest, "finite": True}
            self.retained = {
                "b2": np.zeros((2, 2), dtype=np.complex128),
                "b6p": np.zeros((3, 2), dtype=np.complex128),
                "eigenvector_min": np.ones(2, dtype=np.complex128),
                "eigenvector_max": np.ones(2, dtype=np.complex128),
            }

    def fake_builder(**kwargs):
        assert kwargs["p62"] is p62
        calls.append(kwargs["class_name"])
        return Result(kwargs["class_name"])

    monkeypatch.setattr(
        "src.solvers.fullspace_lor_nested_interlevel.build_nested_material_class",
        fake_builder,
    )
    def item(name, tag, role):
        identity = {
            "material_coefficient_identity": {
                "class_name": name, "material_role": role,
                "curl_coefficient": 1.0, "mass_coefficient": 1.0,
            },
            "geometry_jacobian_identity": {"widths": [1.0, 1.0, 1.0]},
        }
        return {
            "class_digest": name, "class_identity": identity, "tag": tag,
            "material_role": role, "cell_count_local": 1,
        }

    inventory = {"classes": [item("air_tag_1", 1, "air"), item("grating_tag_3", 3, "grating")]}
    audits, arrays = adapter.audit_nested_material_classes(inventory, p62)
    assert calls == ["air_tag_1", "grating_tag_3"]
    assert len(audits) == 2
    assert arrays["p62"] is not p62
    assert all(any(f"__{role}" in key for key in arrays) for role in ("b2", "b6p", "eigenvector_min", "eigenvector_max"))


def test_s5level_requires_uint32_canonical_ids(monkeypatch) -> None:
    topology = _FakeTopology(12, 2, raw=False)
    topology.owned_edge_ids = topology.owned_edge_ids.astype(np.uint64)
    raw = _FakeTopology(12, 2, raw=False)
    raw_space = SimpleNamespace(
        mesh=SimpleNamespace(
            topology=SimpleNamespace(
                index_map=lambda _dim: SimpleNamespace(size_local=1)
            )
        )
    )
    monkeypatch.setattr(
        runtime, "_matrix_facts",
        lambda _matrix: {
            "rows": 1, "cols": 1, "nnz": 1, "index_bytes": 1,
            "numeric_bytes": 16, "petsc_reported_memory_bytes": 0,
            "petsc_overhead_bytes": 0, "type": "fake",
        },
    )
    with pytest.raises(ValueError, match="uint32"):
        runtime._S5Level(
            degree=1, matrix=object(), raw_space=raw_space, raw_floquet=None,
            parent_topology=topology, raw_topology=raw,
            raw_map={}, raw_permutations=np.zeros((1, 12), dtype=np.int32),
            incidence_unique=np.ones(12),
        )


def test_route_b_runtime_source_has_no_solver_or_allgather() -> None:
    path = Path(__file__).parents[1] / "solvers" / "fullspace_lor_nested_interlevel_runtime.py"
    source = path.read_text(encoding="utf-8").lower()
    assert "allgather(" not in source
    assert "from petsc4py" not in source
    assert "from mpi4py" not in source
    tree = ast.parse(source)
    assert not any(
        isinstance(node, (ast.Import, ast.ImportFrom))
        and "mpi4py" in ast.unparse(node)
        for node in ast.walk(tree)
    )
