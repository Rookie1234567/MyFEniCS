"""Focused contract for integral-level surface quadrature metadata."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import ufl
from basix.ufl import element

from src.solvers.dtn_port_3d import _with_quadrature_degree

_DTN_SOURCE = Path(__file__).resolve().parents[1] / "solvers" / "dtn_port_3d.py"


def _surface_form() -> ufl.Form:
    coordinate_element = element(
        "Lagrange", "triangle", 1, shape=(2,), dtype=np.float64
    )
    domain = ufl.Mesh(coordinate_element)
    finite_element = element("Lagrange", "triangle", 1, dtype=np.float64)
    space = ufl.FunctionSpace(domain, finite_element)
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    ds = ufl.Measure(
        "ds",
        domain=domain,
        subdomain_data="synthetic-facet-tags",
        metadata={"source": "surface-fixture"},
    )
    base_integral = (ufl.inner(trial, test) * ds(1)).integrals()[0]
    return ufl.Form(
        (
            base_integral.reconstruct(
                subdomain_id=1,
                metadata={
                    "custom": "first",
                    "quadrature_degree": 3,
                    "quadrature_rule": "vertex",
                },
            ),
            base_integral.reconstruct(
                subdomain_id=7,
                metadata={"custom": "second", "facet_phase": "preserve"},
            ),
        )
    )


def test_none_quadrature_degree_preserves_identity() -> None:
    form = _surface_form()

    assert _with_quadrature_degree(form, None) is form


def test_surface_integrals_retain_structure_and_original_form() -> None:
    form = _surface_form()
    original_integrals = tuple(form.integrals())
    original_metadata = tuple(
        dict(integral.metadata()) for integral in original_integrals
    )

    transformed = _with_quadrature_degree(form, 11)
    transformed_integrals = tuple(transformed.integrals())

    assert transformed is not form
    assert len(transformed_integrals) == len(original_integrals) == 2
    for before, after in zip(original_integrals, transformed_integrals, strict=True):
        assert after.integrand() is before.integrand()
        assert after.integral_type() == before.integral_type() == "exterior_facet"
        assert after.ufl_domain() is before.ufl_domain()
        assert after.subdomain_id() == before.subdomain_id()
        assert after.subdomain_data() is before.subdomain_data()
        assert after.metadata()["custom"] == before.metadata()["custom"]
        assert after.metadata()["quadrature_degree"] == 11
        assert dict(before.metadata()) == original_metadata[
            original_integrals.index(before)
        ]

    assert tuple(form.integrals()) == original_integrals
    assert tuple(dict(integral.metadata()) for integral in form.integrals()) == (
        *original_metadata,
    )


def test_surface_entry_points_use_integral_metadata_helper() -> None:
    source = _DTN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assembler = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "_ReusableSurfaceComponentAssembler"
    )
    functions["_ReusableSurfaceComponentAssembler.__init__"] = next(
        node
        for node in assembler.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "__init__"
    )

    required = (
        "_assemble_mpc_vector",
        "_assemble_unconstrained_vector",
        "_ReusableSurfaceComponentAssembler.__init__",
        "_mode_projection_from_solution",
        "_surface_scalar",
    )
    for name in required:
        segment = ast.get_source_segment(source, functions[name])
        assert segment is not None
        assert "_with_quadrature_degree" in segment
        assert "form_compiler_options" not in segment
