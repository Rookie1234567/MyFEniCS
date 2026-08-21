"""Pure contract tests for the R2 component evidence layer."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks import fullspace_dual_component_checker as checker
from benchmarks import run_fullspace_dual_component as runner


ROOT = Path(__file__).resolve().parents[2]


def test_checker_has_no_execution_or_runner_imports() -> None:
    tree = ast.parse(
        (ROOT / "benchmarks/fullspace_dual_component_checker.py").read_text(),
        filename="fullspace_dual_component_checker.py",
    )
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(
        name == "benchmarks.run_fullspace_dual_component"
        or name.startswith(("src.", "dolfinx", "petsc", "mpi4py"))
        for name in imported
    )


def test_direct_form_has_one_coordinate_definition() -> None:
    source = (ROOT / "benchmarks/run_fullspace_dual_component.py").read_text()
    tree = ast.parse(source, filename="run_fullspace_dual_component.py")
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_direct_vector_form"
    )
    coordinate_assignments = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "x" for target in node.targets)
    ]
    assert len(coordinate_assignments) == 1


def test_zero_direct_scalar_keeps_a_linear_form_space() -> None:
    pytest.importorskip("dolfinx")
    ufl = pytest.importorskip("ufl")
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from dolfinx.fem import petsc as fem_petsc
    from mpi4py import MPI
    from petsc4py import PETSc

    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tdim = domain.topology.dim
    domain.topology.create_connectivity(tdim - 1, tdim)
    facets = mesh.exterior_facet_indices(domain.topology)
    facet_tags = mesh.meshtags(
        domain,
        tdim - 1,
        facets,
        runner.np.ones(facets.size, dtype=runner.np.int32),
    )
    space = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), 1, dtype=default_real_type),
    )
    form = runner._direct_vector_form(
        fem=fem,
        ufl=ufl,
        PETSc=PETSc,
        function_space=space,
        mesh_data=SimpleNamespace(mesh=domain, facet_tags=facet_tags),
        tag=1,
        component=0,
        scalar=0.0j,
        wavevector=(0.0j, 0.0j, 0.0j),
        quadrature_degree=2,
    )
    vector = fem_petsc.assemble_vector(form)
    try:
        assert vector.getSize() > 0
        assert runner.np.allclose(
            runner.np.asarray(vector.getArray(readonly=True)), 0.0
        )
    finally:
        vector.destroy()


def test_parser_requires_source_identity_and_mpi_size() -> None:
    args = runner._parser().parse_args(
        [
            "--case",
            "p2-h50",
            "--raw-dir",
            "/tmp/r2-raw",
            "--record",
            "/tmp/r2-record.json",
            "--expected-source-sha",
            "a" * 40,
            "--expected-mpi-size",
            "1",
        ]
    )
    assert args.expected_source_sha == "a" * 40
    assert args.expected_mpi_size == 1


def test_map_comparator_uses_reference_norm() -> None:
    comparison = checker._compare_maps({("key",): 1.0 + 0.0j}, {("key",): 2.0 + 0.0j})
    assert comparison["key_set_equal"] is True
    assert comparison["relative_l2"] == pytest.approx(0.5)


def test_checker_compact_output_drops_internal_tuple_key_maps() -> None:
    compact = checker._compact_json(
        {"canonical": {"map": {("entity", 1): 2.0}, "norm": 2.0}}
    )
    assert compact == {"canonical": {"norm": 2.0}}


def test_grouping_keeps_side_polarization_and_zero_semantics() -> None:
    modes = [
        SimpleNamespace(side="top", polarization="s"),
        SimpleNamespace(side="top", polarization="p"),
        SimpleNamespace(side="bottom", polarization="s"),
        SimpleNamespace(side="bottom", polarization="p"),
    ]
    amplitudes = runner.np.asarray([1.0 + 0.0j, 1.0e-16 + 0.0j, 0.0j, 2.0 + 0.0j])
    grouping = runner._mode_grouping(modes, amplitudes)
    assert set(grouping["side"]) == {"top", "bottom"}
    assert set(("s", "p")) <= set(grouping["polarization"])
    assert grouping["side"]["top"]["nonzero_mode_indices"] == [0, 1]
    assert grouping["side"]["bottom"]["nonzero_mode_indices"] == [3]
    assert grouping["side"]["top"]["exact_zero_mode_indices"] == []
    assert grouping["polarization"]["s"]["exact_zero_mode_indices"] == [2]


def test_rhs_repeat_uses_one_oracle_descriptor_and_explicit_pre_vectors() -> None:
    source = (ROOT / "benchmarks/run_fullspace_dual_component.py").read_text()
    assert "direct_rhs_repeat" not in source
    assert "candidate_rhs_pre" in source
    assert "direct_rhs_pre" in source
    assert 'rhs_state["oracle_repeat_alias_of"] = "oracle"' in source


def test_base_component_provenance_declares_no_candidate_component_api() -> None:
    source = (ROOT / "benchmarks/run_fullspace_dual_component.py").read_text()
    assert '"candidate_component_api": False' in source
    assert 'label=f"base_component{component}_oracle"' in source
