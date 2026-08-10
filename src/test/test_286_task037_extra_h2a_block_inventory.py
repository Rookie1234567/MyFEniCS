from __future__ import annotations

import numpy as np
import pytest
import ufl
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_exact_class_block_cache import (
    H2AClassBlockSpec,
    H2ACellReference,
    build_b0_proxy_tensor,
    build_task037_extra_h2a_block_cache,
    make_task037_extra_h2a_class_key,
    tabulate_task037_extra_h2a_cell_tensor,
)
from src.test.test_272_task037_extra_fullspace_mf_mpi import _build_case


def _constraint_pattern(*, phase=1.0 + 0.0j, edge_topology="edge"):
    return (
        {
            "topology": edge_topology,
            "local_slave": 0,
            "phase": phase,
            "columns": ((1, 1.0 + 0.0j),),
        },
        {
            "topology": "face",
            "local_slave": 1,
            "phase": phase,
            "columns": ((0, phase), (1, 1.0 + 0.0j)),
        },
    )


def _key(**updates):
    values = {
        "cell_widths": (1.0, 2.0, 3.0),
        "material_tag": 1,
        "material_identity": ("epsilon_abs", 2.0),
        "orientation": (0,),
        "constraint_pattern": _constraint_pattern(),
        "canonical_local_basis_signature": (
            "N1curl",
            "canonical-basix-order-v1",
        ),
        "proxy_identity": ("B0", "k0=2"),
    }
    values.update(updates)
    return make_task037_extra_h2a_class_key(**values)


def _small_spec(class_key, *, mass=None, abs_epsilon=1.0):
    curl = np.asarray(
        ((3.0 + 0.2j, 0.4 - 0.1j), (0.4 + 0.1j, 2.0 + 0.3j)),
        dtype=np.complex128,
    )
    if mass is None:
        mass = np.eye(2, dtype=np.complex128)
    return H2AClassBlockSpec(
        class_key=class_key,
        curl_tensor=curl,
        mass_tensor=np.asarray(mass, dtype=np.complex128),
        k0=2.0,
        abs_epsilon=abs_epsilon,
    )


def test_h2a_opt_in_and_exact_key_dimensions_are_closed():
    base = _key()
    with pytest.raises(ValueError, match="explicit task037 opt-in"):
        build_task037_extra_h2a_block_cache([_small_spec(base)], [])

    variants = (
        _key(cell_widths=(1.0, 2.0, 4.0)),
        _key(material_tag=2),
        _key(material_identity=("epsilon_abs", 3.0)),
        _key(orientation=(1,)),
        _key(constraint_pattern=_constraint_pattern(edge_topology="edge-slave")),
        _key(constraint_pattern=_constraint_pattern(phase=np.exp(0.25j))),
        _key(constraint_pattern=()),
        _key(
            canonical_local_basis_signature=(
                "N1curl",
                "canonical-basix-order-v2",
            )
        ),
        _key(proxy_identity=("B0", "k0=3")),
    )
    assert all(variant != base for variant in variants)

    cache = build_task037_extra_h2a_block_cache(
        [_small_spec(base)],
        [
            H2ACellReference(base, np.asarray((0, 1), dtype=np.int64)),
            H2ACellReference(base, np.asarray((100, 101), dtype=np.int64)),
        ],
        task037_extra_h2a=True,
    )
    try:
        assert cache.audit["unique_class_count"] == 1
        assert cache.audit["local_cell_count"] == 2
        assert cache.audit["cell_factor_reference_count"] == 2
        assert cache.audit["per_cell_factor_count"] == 0
        assert cache.audit["global_matrix_materialized"] is False
        assert cache.audit["global_condensed_schur_materialized"] is False
        assert cache.audit["inventory_only"] is True
        assert cache.audit["Bc_inverse_implemented"] is False
    finally:
        cache.destroy()


def test_h2a_absolute_cell_rows_do_not_change_class_identity():
    key = _key()
    references = [
        H2ACellReference(
            key,
            np.asarray((2 * cell, 2 * cell + 1), dtype=np.int64),
        )
        for cell in range(100)
    ]
    references[-1] = H2ACellReference(
        key,
        np.asarray((1000, 1001), dtype=np.int64),
    )
    consumed = {"count": 0}

    def class_spec_stream():
        consumed["count"] += 1
        yield _small_spec(key)

    cache = build_task037_extra_h2a_block_cache(
        class_spec_stream(),
        references,
        task037_extra_h2a=True,
    )
    try:
        assert cache.audit["unique_class_count"] == 1
        assert cache.audit["class_operator_spec_count"] == 1
        assert cache.audit["cell_reference_count"] == 100
        assert cache.audit["local_cell_count"] == 100
        assert cache.audit["local_factor_count"] == 1
        assert cache.audit["per_cell_factor_count"] == 0
        assert consumed["count"] == 1
        assert (
            cache.audit["setup_temporary_dense_proxy_matrix_peak_per_class_count"]
            == 1
        )
        assert cache.audit["class_operator_specs_retained"] is False
        assert cache.audit["retained_dense_cell_matrix_count"] == 0
        assert tuple(cache.cells[0].local_dofs) == (0, 1)
        assert tuple(cache.cells[-1].local_dofs) == (1000, 1001)
    finally:
        cache.destroy()


def test_h2a_exact_numeric_hash_dedup_and_refinement_do_not_make_cell_factors():
    key_a = _key()
    key_same_tensor = _key(
        material_tag=2,
        material_identity=("epsilon_abs", 2.0, "same_numeric_tensor"),
    )
    key_changed_tensor = _key(
        material_tag=3,
        material_identity=("epsilon_abs", 2.0, "changed_numeric_tensor"),
    )
    changed_mass = np.eye(2, dtype=np.complex128)
    changed_mass[0, 0] = 1.25
    specs = [
        _small_spec(key_a),
        _small_spec(key_same_tensor),
        H2AClassBlockSpec(
            class_key=key_changed_tensor,
            curl_tensor=_small_spec(key_a).curl_tensor,
            mass_tensor=changed_mass,
            k0=2.0,
            abs_epsilon=1.0,
        ),
    ]
    references = [
        H2ACellReference(
            key_a,
            np.asarray((2 * cell, 2 * cell + 1), dtype=np.int64),
        )
        for cell in range(4)
    ]
    references.extend(
        (
            H2ACellReference(key_same_tensor, np.asarray((20, 21), dtype=np.int64)),
            H2ACellReference(key_changed_tensor, np.asarray((22, 23), dtype=np.int64)),
        )
    )
    cache = build_task037_extra_h2a_block_cache(
        specs,
        references,
        task037_extra_h2a=True,
    )
    try:
        assert cache.audit["unique_class_count"] == 3
        assert cache.audit["local_factor_count"] == 2
        assert cache.audit["numeric_hash_dedup_count"] == 1
        assert cache.audit["local_cell_count"] == 6
        assert cache.audit["cell_factor_reference_count"] == 6
        assert cache.audit["factor_payload_gate_pass"] is True
        assert cache.audit["factor_payload_gate_basis"] == (
            "resident_factor_values_plus_pivots_plus_class_metadata_global_sum"
        )
        assert (
            cache.audit["setup_cache_visible_local_retained_factor_bytes_before_peak"]
            > 0
        )
        assert cache.audit["setup_cache_visible_local_numeric_live_peak_bytes"] >= (
            cache.audit["setup_cache_visible_local_retained_factor_bytes_before_peak"]
            + cache.audit["setup_borrowed_curl_mass_bytes_peak"]
            + cache.audit["setup_temporary_dense_proxy_matrix_peak_bytes"]
        )
        components = dict(cache.audit["retained_numeric_payload_components"])
        assert sum(components.values()) == cache.audit[
            "retained_numeric_payload_local_bytes"
        ]
        assert cache.audit["retained_block_factor_payload_local_bytes"] == (
            components["factor_values_bytes"]
            + components["factor_pivot_indices_bytes"]
        )
        assert cache.audit["retained_dense_cell_matrix_count"] == 0
        assert cache.audit["cell_schur_matrix_nnz"] == 0
        assert cache.audit["slab_matrix_nnz"] == 0
        assert cache.audit["slab_factor_count"] == 0
        assert cache.audit["ksp_created"] is False
        assert cache.audit["dtn_used"] is False
        assert cache.audit["inventory_only"] is True
        assert cache.audit["constrained_smoother_implemented"] is False
        assert cache.audit["Bc_inverse_implemented"] is False
        rhs = np.asarray((1.0 + 0.2j, -0.4 + 0.7j), dtype=np.complex128)
        first = cache.solve_cell(0, rhs)
        repeated = cache.solve_cell(0, rhs)
        expected = np.linalg.solve(
            build_b0_proxy_tensor(
                specs[0].curl_tensor,
                specs[0].mass_tensor,
                k0=2.0,
                abs_epsilon=1.0,
            ),
            rhs,
        )
        assert np.array_equal(first, repeated)
        assert np.all(np.isfinite(first))
        assert np.linalg.norm(first - expected) / np.linalg.norm(expected) <= 1.0e-11
    finally:
        cache.destroy()
        cache.destroy()


def _proxy_forms(function_space, cell_tags):
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure(
        "dx",
        domain=function_space.mesh,
        subdomain_data=cell_tags,
    )
    epsilon = {1: 2.0, 2: 1.5}
    curl_terms = []
    mass_terms = []
    for tag in (1, 2):
        curl_terms.append(
            PETSc.ScalarType(1.0)
            * ufl.inner(ufl.curl(u), ufl.curl(v))
            * dx(tag)
        )
        mass_terms.append(PETSc.ScalarType(1.0) * ufl.inner(u, v) * dx(tag))
    return sum(curl_terms), sum(mass_terms), epsilon


@pytest.mark.parametrize("degree", (2, 3))
def test_h2a_ffcx_oriented_b0_factor_matches_local_dense_authority(degree: int):
    cfg, _mesh_data, function_space, cell_tags, tags, _floquet, _form = _build_case(
        degree,
        MPI.COMM_SELF,
    )
    del cfg
    curl_form, mass_form, epsilon = _proxy_forms(function_space, cell_tags)
    curl_compiled = fem.form(curl_form)
    mass_compiled = fem.form(mass_form)
    class_specs = []
    class_keys = set()
    cell_references = []
    authority_by_class = {}
    owned_cells = int(function_space.mesh.topology.index_map(3).size_local)
    for cell in range(owned_cells):
        curl_tensor, widths, cell_info = tabulate_task037_extra_h2a_cell_tensor(
            curl_compiled,
            function_space,
            cell_tags,
            cell,
        )
        mass_tensor, mass_widths, mass_info = tabulate_task037_extra_h2a_cell_tensor(
            mass_compiled,
            function_space,
            cell_tags,
            cell,
        )
        assert widths == mass_widths
        assert cell_info == mass_info
        tag = int(tags[cell])
        key = make_task037_extra_h2a_class_key(
            cell_widths=widths,
            material_tag=tag,
            material_identity=("epsilon_abs", epsilon[tag]),
            orientation=(cell_info,),
            constraint_pattern=_constraint_pattern(),
            canonical_local_basis_signature=(
                "N1curl",
                degree,
                "canonical-basix-local-order-v1",
            ),
            proxy_identity=("B0", "k0=2"),
        )
        if key not in class_keys:
            class_specs.append(
                H2AClassBlockSpec(
                    class_key=key,
                    curl_tensor=curl_tensor,
                    mass_tensor=mass_tensor,
                    k0=2.0,
                    abs_epsilon=epsilon[tag],
                )
            )
            class_keys.add(key)
            authority_by_class[key] = (curl_tensor, mass_tensor, tag)
        cell_references.append(
            H2ACellReference(
                key,
                np.asarray(
                    function_space.dofmap.cell_dofs(cell),
                    dtype=np.int64,
                ),
            )
        )

    cache = build_task037_extra_h2a_block_cache(
        class_specs,
        cell_references,
        task037_extra_h2a=True,
    )
    try:
        audit = cache.audit
        assert audit["proxy"] == "B0=K_curl+k0^2*M_abs_epsilon"
        assert audit["unique_class_count"] <= 32
        assert audit["unique_class_count"] < audit["local_cell_count"]
        assert audit["class_operator_spec_count"] == len(class_specs)
        assert audit["cell_reference_count"] == len(cell_references)
        assert (
            audit["setup_temporary_dense_proxy_matrix_peak_per_class_count"] == 1
        )
        assert audit["class_operator_specs_retained"] is False
        assert audit["factor_payload_gate_pass"] is True
        assert audit["factor_payload_gate_basis"] == (
            "resident_factor_values_plus_pivots_plus_class_metadata_global_sum"
        )
        assert audit[
            "retained_block_factor_payload_with_metadata_global_sum_bytes"
        ] == (
            audit["retained_block_factor_payload_global_sum_bytes"]
            + audit["retained_block_factor_metadata_global_sum_bytes"]
        )
        assert audit["original_dense_matrix_released_after_factorization"] is True
        assert audit["retained_original_dense_matrix_count"] == 0
        assert audit["per_cell_factor_count"] == 0
        assert audit["global_matrix_materialized"] is False
        assert audit["global_constraint_matrix_materialized"] is False
        assert audit["global_condensed_schur_materialized"] is False
        assert audit["cell_schur_matrix_nnz"] == 0
        assert audit["slab_matrix_nnz"] == 0
        assert audit["slab_factor_count"] == 0
        assert audit["ordinary_default_changed"] is False
        assert audit["inventory_only"] is True
        assert audit["constrained_smoother_implemented"] is False
        assert audit["Bc_inverse_implemented"] is False
        components = dict(audit["retained_numeric_payload_components"])
        assert sum(components.values()) == audit[
            "retained_numeric_payload_local_bytes"
        ]
        for cell, reference in enumerate(cell_references):
            curl_tensor, mass_tensor, tag = authority_by_class[reference.class_key]
            rhs = np.asarray(
                [
                    1.0 + 0.03 * index + 0.01j * (index + 1)
                    for index in range(curl_tensor.shape[0])
                ],
                dtype=np.complex128,
            )
            proxy = build_b0_proxy_tensor(
                curl_tensor,
                mass_tensor,
                k0=2.0,
                abs_epsilon=epsilon[tag],
            )
            assert np.array_equal(
                proxy,
                curl_tensor + (2.0**2 * epsilon[tag]) * mass_tensor,
            )
            expected = np.linalg.solve(proxy, rhs)
            observed = cache.solve_cell(cell, rhs)
            repeated = cache.solve_cell(cell, rhs)
            assert np.array_equal(observed, repeated)
            assert np.all(np.isfinite(observed))
            assert (
                np.linalg.norm(observed - expected) / np.linalg.norm(expected)
                <= 1.0e-11
            )
    finally:
        cache.destroy()
