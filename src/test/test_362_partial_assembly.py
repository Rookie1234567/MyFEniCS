"""Tiny independent original-form oracle; no original-scale solver builds."""
from contextlib import ExitStack
from types import SimpleNamespace
import tracemalloc
import hashlib

import numpy as np
import pytest
from mpi4py import MPI
from dolfinx import fem, mesh
import dolfinx_mpc
import ufl

from src.solvers.fullspace_mpc_action import FullspaceMpcFormAction
from src.solvers.fullspace_partial_assembly import IsotropicPartialAssembly
from src.solvers.fullspace_quadrature_diagonal import PositiveCellBasis
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form


@pytest.mark.parametrize("degree", [2, 3, 6])
@pytest.mark.parametrize(
    "component,packed,preallocated",
    [
        (None, False, False),
        ("curl", False, False),
        ("mass", False, False),
        (None, True, False),
        (None, True, True),
        ("curl", True, True),
        ("mass", True, True),
    ],
)
def test_original_form_complex_multimaster_affine_orientation(
    degree, component, packed, preallocated
):
    cell_count = 9 if degree == 2 else 2  # exercise one full batch and its tail
    domain = mesh.create_box(MPI.COMM_SELF, [np.zeros(3), np.array([1., 2., 3.])],
                             [cell_count, 1, 1], cell_type=mesh.CellType.hexahedron)
    # Sheared affine cells exercise all entries of the Piola metric.
    domain.geometry.x[:, 0] = domain.geometry.x[:, 0]**2 + .1*domain.geometry.x[:, 0]
    domain.geometry.x[:] = domain.geometry.x @ np.array([[1., .2, -.1], [0., 1., .3], [0., 0., 1.]])
    space = fem.functionspace(domain, ("N1curl", degree))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(space, np.array([0], np.int32), np.array([1, 2], np.int64),
        np.array([.25+.5j, -.1+.2j]), np.array([0, 0], np.int32), np.array([0, 2], np.int32))
    mpc.finalize()
    space = mpc.function_space
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    odd = np.arange(cell_count) % 2 == 1
    mu.x.array[:] = np.where(odd, 1.7, 1.)
    mass.x.array[:] = np.where(odd, .4, 2.)
    form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
    if component is not None:
        from src.solvers.common_3d_forms import _build_physical_volume_terms
        trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
        cfg = SimpleNamespace(tags=SimpleNamespace(air=1, substrate=2, grating=3),
            mu_r=.8, k0=1., eps_r=2.+.3j, substrate_index=np.sqrt(.4-.2j), grating_index=1.)
        tags = mesh.meshtags(domain, 3, np.arange(cell_count, dtype=np.int32),
                             np.where(odd, 2, 1).astype(np.int32))
        forms = _build_physical_volume_terms(cfg, trial, test,
            ufl.Measure("dx", domain=domain, subdomain_data=tags))
        mu.x.array[:] = 1/cfg.mu_r
        mass.x.array[:] = np.where(odd, -cfg.substrate_index**2, -cfg.eps_r)
        form = forms[0 if component == "curl" else 1]
    materials_before = (mu.x.array.copy(), mass.x.array.copy())
    tracemalloc.start()
    kernel = IsotropicPartialAssembly(space, mu, mass,
        component_form=form if component else None, component=component,
        contiguous_work=packed, preallocated_work=preallocated)
    _, initialization_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert np.count_nonzero(kernel.permutations) > 0
    print('tiny PA', degree, kernel.audit, 'traced initialization peak', initialization_peak, flush=True)
    with ExitStack() as owned:
        oracle = FullspaceMpcFormAction(form, space, mpc=mpc,
                                       slave_row_identity=component != "mass")
        owned.callback(oracle.destroy)
        from ffcx.analysis import analyze_ufl_objects
        from ffcx.element_interface import create_quadrature
        original_analysis = analyze_ufl_objects([oracle._action_ufl], np.dtype(np.complex128)).form_data[0]
        for group in original_analysis.integral_data:
            for integral in group.integrals:
                md = integral.metadata()
                points, weights = create_quadrature('hexahedron', md['quadrature_degree'],
                    md['quadrature_rule'], original_analysis.argument_elements)
                assert kernel.audit['quadrature_degree'] == md['quadrature_degree']
                assert kernel.audit['quadrature_rule'] == md['quadrature_rule']
                assert kernel.audit['points_sha256'] == hashlib.sha256(points.tobytes()).hexdigest()
                assert kernel.audit['weights_sha256'] == hashlib.sha256(weights.tobytes()).hexdigest()
        fast = FullspaceMpcFormAction(form, space, mpc=mpc, local_kernel=kernel,
                                     slave_row_identity=component != "mass")
        owned.callback(fast.destroy)
        assert fast.audit['coefficient_count'] == len(fast._action_ufl.coefficients()) > 0
        assert fast.audit['compiled_coefficient_count'] is None
        source = oracle.matrix.createVecRight()
        owned.callback(source.destroy)
        rng = np.random.default_rng(362+degree)
        source.array[:] = rng.normal(size=source.getLocalSize()) + 1j*rng.normal(size=source.getLocalSize())
        initial = source.array.copy()
        for slave_value in (initial[0], 0):
            source.array[0] = slave_value
            before = source.array.copy()
            expected = oracle.apply(source).array.copy()
            tracemalloc.start()
            observed = fast.apply(source).array.copy()
            _, apply_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            relative = np.linalg.norm(observed-expected)/np.linalg.norm(expected)
            print('degree', degree, 'relative', relative, 'traced apply peak', apply_peak, flush=True)
            assert relative <= 1e-11
            assert np.all(np.isfinite(observed))
            assert observed[0] == (0 if component == "mass" else slave_value)
            np.testing.assert_array_equal(fast.apply(source).array, observed)
            np.testing.assert_array_equal(source.array, before)
        np.testing.assert_array_equal(mu.x.array, materials_before[0])
        np.testing.assert_array_equal(mass.x.array, materials_before[1])
        if component is None:
            for change in ("source", "materials"):
                previous = observed.copy()
                if change == "source":
                    source.array[:] = rng.normal(size=source.getLocalSize()) + 1j*rng.normal(size=source.getLocalSize())
                    source.array[0] = 0
                else:
                    mu.x.array[:] *= 1.3
                    mass.x.array[:] *= .7
                    mu.x.scatter_forward()
                    mass.x.scatter_forward()
                before = source.array.copy()
                expected = oracle.apply(source).array.copy()
                observed = fast.apply(source).array.copy()
                relative = np.linalg.norm(observed-expected)/np.linalg.norm(expected)
                assert relative <= 1e-11
                assert np.linalg.norm(observed-previous) > 1e-3*np.linalg.norm(previous)
                np.testing.assert_array_equal(source.array, before)
                np.testing.assert_array_equal(fast.apply(source).array, observed)
                print('updated', change, 'degree', degree, 'relative', relative, flush=True)
        fast.destroy()
        np.testing.assert_array_equal(oracle.apply(source).array, expected)
        with pytest.raises(RuntimeError, match="destroyed"):
            fast.apply(source)


@pytest.mark.parametrize(
    "degree,component",
    [
        (2, "mass"),
        (2, "curl"),
        (2, None),
        (3, None),
        (6, "mass"),
        (6, "curl"),
        (6, None),
    ],
)
@pytest.mark.parametrize("reuse_projection_work", [False, True])
def test_sum_factorized_native_tabulate_adjoint_and_sheared_mpc(
    degree, component, reuse_projection_work
):
    """Qualify the opt-in kernel against native tabulation and the form oracle."""

    cell_count = 9 if degree == 2 else 2
    domain = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.array([1.0, 2.0, 3.0])],
        [cell_count, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    domain.geometry.x[:, 0] = domain.geometry.x[:, 0] ** 2 + 0.1 * domain.geometry.x[:, 0]
    domain.geometry.x[:] = domain.geometry.x @ np.array(
        [[1.0, 0.2, -0.1], [0.0, 1.0, 0.3], [0.0, 0.0, 1.0]]
    )
    space = fem.functionspace(domain, ("N1curl", degree))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.array([0], np.int32),
        np.array([1, 2], np.int64),
        np.array([0.25 + 0.5j, -0.1 + 0.2j]),
        np.array([0, 0], np.int32),
        np.array([0, 2], np.int32),
    )
    mpc.finalize()
    space = mpc.function_space
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    odd = np.arange(cell_count) % 2 == 1
    mu.x.array[:] = np.where(odd, 1.7, 1.0)
    mass.x.array[:] = np.where(odd, 0.4, 2.0)
    form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
    if component is not None:
        from src.solvers.common_3d_forms import _build_physical_volume_terms

        trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
        cfg = SimpleNamespace(
            tags=SimpleNamespace(air=1, substrate=2, grating=3),
            mu_r=0.8,
            k0=1.0,
            eps_r=2.0 + 0.3j,
            substrate_index=np.sqrt(0.4 - 0.2j),
            grating_index=1.0,
        )
        tags = mesh.meshtags(
            domain,
            3,
            np.arange(cell_count, dtype=np.int32),
            np.where(odd, 2, 1).astype(np.int32),
        )
        forms = _build_physical_volume_terms(
            cfg,
            trial,
            test,
            ufl.Measure("dx", domain=domain, subdomain_data=tags),
        )
        mu.x.array[:] = 1 / cfg.mu_r
        mass.x.array[:] = np.where(odd, -cfg.substrate_index**2, -cfg.eps_r)
        form = forms[0 if component == "curl" else 1]

    kernel = IsotropicPartialAssembly(
        space,
        mu,
        mass,
        component_form=form if component else None,
        component=component,
        sum_factorized_work=True,
        reuse_projection_work=reuse_projection_work,
    )
    assert kernel.audit["sum_factorized_opt_in"] is True
    assert kernel.audit["reuse_projection_work_opt_in"] is reuse_projection_work
    assert kernel._sum_factorized.audit["native_tensor_product_api"] is False
    sf = kernel._sum_factorized

    rng = np.random.default_rng(36200 + degree + (0 if component is None else 1))
    local = rng.normal(size=(1, sf.coefficient_matrix.shape[0])) + 1j * rng.normal(
        size=(1, sf.coefficient_matrix.shape[0])
    )
    polynomial = (local @ sf.coefficient_matrix).reshape(
        1, 3, sf.degree + 1, sf.degree + 1, sf.degree + 1
    )
    native = sf.element.tabulate(1, sf.points)
    derivative_tables = (
        (sf.derivatives_1d[0], sf.values_1d[1], sf.values_1d[2]),
        (sf.values_1d[0], sf.derivatives_1d[1], sf.values_1d[2]),
        (sf.values_1d[0], sf.values_1d[1], sf.derivatives_1d[2]),
    )

    def assert_scaled_close(observed, expected):
        difference = np.linalg.norm(observed - expected)
        scale = np.linalg.norm(expected)
        if scale > 0.0:
            assert difference / scale <= 1e-12
        else:
            assert np.max(np.abs(observed)) <= 256 * np.finfo(float).eps

    for vector_component in range(3):
        observed = sf._field_from_polynomial(
            polynomial[:, vector_component], sf.values_1d
        )[0]
        expected = np.einsum("i,qic->qc", local[0], native[0])[:, vector_component]
        assert_scaled_close(observed, expected)
        for derivative, tables in enumerate(derivative_tables):
            observed = sf._field_from_polynomial(
                polynomial[:, vector_component], tables
            )[0]
            expected = np.einsum("i,qic->qc", local[0], native[derivative + 1])[
                :, vector_component
            ]
            assert_scaled_close(observed, expected)

    identity = np.eye(sf.polynomial_dimension).reshape(
        sf.polynomial_dimension,
        sf.degree + 1,
        sf.degree + 1,
        sf.degree + 1,
    )
    polynomial_table = sf._evaluate(identity, *sf.values_1d).T
    field = rng.normal(size=(1, len(sf.points))) + 1j * rng.normal(
        size=(1, len(sf.points))
    )
    observed = sf._polynomial_from_field(field, sf.values_1d)
    expected = field[:, sf.natural_to_input] @ polynomial_table
    assert_scaled_close(observed, expected)

    with ExitStack() as owned:
        oracle = FullspaceMpcFormAction(
            form,
            space,
            mpc=mpc,
            slave_row_identity=component != "mass",
        )
        owned.callback(oracle.destroy)
        fast = FullspaceMpcFormAction(
            form,
            space,
            mpc=mpc,
            local_kernel=kernel,
            slave_row_identity=component != "mass",
        )
        owned.callback(fast.destroy)
        source = oracle.matrix.createVecRight()
        owned.callback(source.destroy)
        source.array[:] = rng.normal(size=source.getLocalSize()) + 1j * rng.normal(
            size=source.getLocalSize()
        )
        source.array[0] = 0.0
        before = source.array.copy()
        expected = oracle.apply(source).array.copy()
        observed = fast.apply(source).array.copy()
        relative = np.linalg.norm(observed - expected) / np.linalg.norm(expected)
        assert relative <= 2e-11
        assert np.all(np.isfinite(observed))
        np.testing.assert_array_equal(source.array, before)


def test_sum_factorized_stacked_real_imag_coefficient_transforms_match() -> None:
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(domain, ("N1curl", 6))
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.25
    mass.x.array[:] = 0.7
    separate = IsotropicPartialAssembly(
        space, mu, mass, sum_factorized_work=True
    )
    stacked = IsotropicPartialAssembly(
        space,
        mu,
        mass,
        sum_factorized_work=True,
        combine_real_imag_transforms=True,
    )
    old, new = separate._sum_factorized, stacked._sum_factorized
    assert new.audit["coefficient_transform_real_imag_layout"] == (
        "stacked_real_then_imag_single_real_gemm"
    )
    assert new.audit["batch_workspace_bytes"] == old.audit["batch_workspace_bytes"]

    rng = np.random.default_rng(36206)
    local = rng.normal(size=(3, old.element.dim)) + 1j * rng.normal(
        size=(3, old.element.dim)
    )
    metrics = np.repeat(separate.metrics[:1], len(local), axis=0)
    materials = np.column_stack(
        (
            np.full(len(local), mass.x.array[0], dtype=np.complex128),
            np.full(len(local), mu.x.array[0], dtype=np.complex128),
        )
    )
    expected = old.apply(local, metrics, materials)
    observed = new.apply(local, metrics, materials)
    np.testing.assert_allclose(observed, expected, rtol=3e-12, atol=3e-12)


def test_same_space_geometry_bundle_is_readonly_and_matches_native_action():
    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(domain, ("N1curl", 2))
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.4
    mass.x.array[:] = 0.8
    form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
    first = IsotropicPartialAssembly(
        space,
        mu,
        mass,
        sum_factorized_work=True,
        share_geometry=True,
    )
    bundle = first.geometry_bundle
    second = IsotropicPartialAssembly(
        space,
        mu,
        mass,
        sum_factorized_work=True,
        share_geometry=True,
        geometry_bundle=bundle,
    )
    del first
    assert second.geometry_bundle is bundle
    assert second._sum_factorized.reference_bundle is bundle["reference_bundle"]
    assert (
        second._sum_factorized.coefficient_matrix
        is bundle["reference_bundle"]["coefficient_matrix"]
    )
    for array in (second.dofs, second.permutations, second.metrics):
        assert array.flags.writeable is False
    assert second.basis.geometry_derivatives is bundle["geometry_derivatives"]
    assert bundle["source_space"] is space
    assert bundle["source_mesh"] is domain
    assert bundle["identity"]["reference_quadrature_rule"]
    with ExitStack() as owned:
        native = FullspaceMpcFormAction(form, space)
        owned.callback(native.destroy)
        fast = FullspaceMpcFormAction(form, space, local_kernel=second)
        owned.callback(fast.destroy)
        source = native.matrix.createVecRight()
        owned.callback(source.destroy)
        rng = np.random.default_rng(36207)
        source.array[:] = rng.normal(size=source.getLocalSize()) + 1j * rng.normal(
            size=source.getLocalSize()
        )
        expected = native.apply(source).array.copy()
        observed = fast.apply(source).array.copy()
        np.testing.assert_allclose(observed, expected, rtol=2e-11, atol=2e-11)


def test_direct_selected_h6_backend_does_not_build_native_action(monkeypatch):
    from src.common.config_3d import target_stage4_config
    from src.solvers import physical_light_setup
    from src.solvers.physical_light_setup import build_light_h6_setup

    domain = mesh.create_box(
        MPI.COMM_SELF,
        [np.zeros(3), np.ones(3) * np.array([3.0, 1.0, 1.0])],
        [3, 1, 1],
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(domain, ("N1curl", 6))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.finalize()
    work_space = mpc.function_space
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.0
    mass.x.array[:] = 1.0
    levels = {
        "spaces": {6: work_space},
        "floquets": {6: SimpleNamespace(mpc=mpc)},
        "mu": mu,
        "mass": mass,
    }
    native_calls = []
    actual_action = physical_light_setup.FullspaceMpcFormAction

    def tracking_action(*args, **kwargs):
        native_calls.append(kwargs.get("local_kernel") is None)
        return actual_action(*args, **kwargs)

    monkeypatch.setattr(physical_light_setup, "FullspaceMpcFormAction", tracking_action)
    result = build_light_h6_setup(
        levels,
        target_stage4_config(degree=6, h_nm=50.0),
        lambda *_args: None,
        packed_power10=True,
        packed_apply=True,
        sum_factorized_work=True,
        sum_factorized_power10=True,
        direct_selected_backend=True,
        reuse_projection_work=True,
        batched_target_grouping=True,
    )
    try:
        assert native_calls and all(call is False for call in native_calls)
        assert result["light_facts"]["direct_selected_backend_used"] is True
        assert result["light_facts"]["batched_target_grouping_opt_in"] is True
        assert result["light_facts"]["diagonal_local_type_reuse"][
            "local_type_cache_hits"
        ] >= 1
    finally:
        result["h6"].destroy()
        result["p6_shell"].destroy()


def test_nonaffine_geometry_and_nonpositive_material_rejected():
    domain = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron)
    space = fem.functionspace(domain, ("N1curl", 2))
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.
    mass.x.array[:] = -1.+.2j
    with pytest.raises(ValueError, match="positive real"):
        IsotropicPartialAssembly(space, mu, mass)
    mass.x.array[:] = 1.
    domain.geometry.x[0, 0] += .05
    with pytest.raises(NotImplementedError, match="affine"):
        IsotropicPartialAssembly(space, mu, mass)


def test_packed_physical_action_helper_borrows_dtn_and_cleans_volume():
    """Exercise the V24 PC-only packed action on a real tiny FE/MPC fixture."""

    from petsc4py import PETSc

    from src.solvers.common_3d_forms import _build_physical_volume_terms
    from src.solvers.fullspace_dtn_action import (
        FullspaceDtnAction,
        FullspaceDtnCarrier,
        FullspaceDtnModeFunctional,
    )
    from src.solvers.fullspace_physical_action import (
        FullspacePhysicalAction,
        FullspaceSplitVolumeAction,
    )
    from src.solvers.physical_equivalent_fast import build_packed_physical_action

    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    space = fem.functionspace(domain, ("N1curl", 2))
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.array([0], np.int32),
        np.array([1, 2], np.int64),
        np.array([0.25 + 0.5j, -0.1 + 0.2j]),
        np.array([0, 0], np.int32),
        np.array([0, 2], np.int32),
    )
    mpc.finalize()
    space = mpc.function_space
    tags = mesh.meshtags(
        domain,
        3,
        np.array([0], dtype=np.int32),
        np.array([1], dtype=np.int32),
    )
    cfg = SimpleNamespace(
        tags=SimpleNamespace(air=1, substrate=2, grating=3),
        mu_r=0.8,
        k0=1.0,
        eps_r=2.0 + 0.3j,
        substrate_index=np.sqrt(0.4 - 0.2j),
        grating_index=1.0 + 0.0j,
    )
    trial, test = ufl.TrialFunction(space), ufl.TestFunction(space)
    curl_form, mass_form = _build_physical_volume_terms(
        cfg,
        trial,
        test,
        ufl.Measure("dx", domain=domain, subdomain_data=tags),
    )
    native_volume = FullspaceSplitVolumeAction(
        curl_form, mass_form, space, mpc=mpc
    )
    identity = {
        "schema": "fullspace-dtn.mode.v1",
        "mode_index": 0,
        "side": "top",
        "m": 0,
        "n": 0,
        "polarization": "s",
        "alpha": 0.0 + 0.0j,
        "gamma": 1.0 + 0.0j,
        "beta": 1.0 + 0.0j,
        "k_vector": (0.0 + 0.0j, 0.0 + 0.0j, 1.0 + 0.0j),
        "e_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
        "h_vector": (0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j),
        "refractive_index": 1.0 + 0.0j,
        "vertical_sign": 1,
        "electric_tangential_norm_sq": 1.0,
        "power_per_unit_amplitude": 1.0,
        "propagating": True,
        "rayleigh_warning": False,
        "classification": "propagating",
        "rayleigh_tolerance": 1.0e-8,
        "projection_denominator": 1.0,
        "traction_vector": (1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j),
    }
    empty_rows = np.empty(0, dtype=PETSc.IntType)
    empty_values = np.empty(0, dtype=np.complex128)
    carrier = FullspaceDtnCarrier(
        [
            FullspaceDtnModeFunctional(
                mode_key=(0, "top", 0, 0, "s"),
                coupling_rows=empty_rows,
                coupling_values=empty_values,
                projection_rows=empty_rows,
                projection_values=empty_values,
                normalization_h=1.0,
                mode_identity=identity,
            )
        ],
        global_rows=int(space.dofmap.index_map.size_global),
        ownership_range=(0, int(space.dofmap.index_map.size_local)),
        comm=MPI.COMM_SELF,
    )
    dtn = FullspaceDtnAction(carrier, comm=MPI.COMM_SELF)
    native = FullspacePhysicalAction(native_volume, dtn, owns_dtn=False)
    common = {
        "levels": {
            "floquets": {
                6: SimpleNamespace(mpc=mpc),
                4: SimpleNamespace(mpc=mpc),
            },
            "mesh_data": SimpleNamespace(cell_tags=tags),
        },
        "fine": {"volume_action": native_volume, "dtn_action": dtn},
        "p4": {"volume_action": native_volume, "dtn_action": dtn},
    }
    packed = build_packed_physical_action(common, cfg, contiguous_work=True)
    packed_p4 = build_packed_physical_action(
        common, cfg, contiguous_work=True, degree=4
    )
    shared_mu, shared_mass = fem.Function(fem.functionspace(domain, ("DG", 0))), fem.Function(
        fem.functionspace(domain, ("DG", 0))
    )
    shared_mu.x.array[:] = 1.0
    shared_mass.x.array[:] = 1.0
    h6_like_kernel = IsotropicPartialAssembly(
        space,
        shared_mu,
        shared_mass,
        sum_factorized_work=True,
        share_geometry=True,
    )
    packed_v26 = build_packed_physical_action(
        common,
        cfg,
        contiguous_work=True,
        sum_factorized_work=True,
        reuse_projection_work=True,
        share_readonly_geometry=True,
        geometry_bundle=h6_like_kernel.geometry_bundle,
    )
    source = native_volume.component_actions["curl"].matrix.createVecRight()
    target = source.duplicate()
    try:
        rng = np.random.default_rng(36206)
        source.array[:] = rng.normal(size=source.getLocalSize()) + 1j * rng.normal(
            size=source.getLocalSize()
        )
        source_before = source.array.copy()
        native.apply(source, target)
        expected = target.array.copy()
        packed["physical_action"].apply(source, target)
        observed = target.array.copy()
        relative = np.linalg.norm(observed - expected) / max(
            np.linalg.norm(expected), np.finfo(float).tiny
        )
        assert relative <= 1.0e-11
        np.testing.assert_array_equal(source.array, source_before)
        packed["physical_action"].apply(source, target)
        np.testing.assert_array_equal(target.array, observed)
        assert packed["facts"]["native_a6_independent"] is True
        assert packed["facts"]["dtn_borrowed"] is True
        assert packed_p4["facts"]["degree"] == 4
        assert packed_p4["facts"]["action_role"] == "full_A4_verification_candidate"
        assert packed_p4["facts"]["native_a6_independent"] is False
        packed_p4["physical_action"].apply(source, target)
        np.testing.assert_allclose(target.array, expected, rtol=2e-11, atol=2e-11)
        packed_v26["physical_action"].apply(source, target)
        np.testing.assert_allclose(target.array, expected, rtol=2e-11, atol=2e-11)
        shared = packed_v26["facts"]["shared_geometry_bundle"]
        assert shared["same_owner"] is True
        assert shared["readonly_arrays"] is True
        if shared["source_owner"] == "h6_external":
            assert shared["borrowed_components"]
            assert shared["reference_data_shared"] is True
        else:
            assert shared["fallbacks"]
    finally:
        packed["physical_action"].destroy()
        packed_p4["physical_action"].destroy()
        packed_v26["physical_action"].destroy()
        # The candidate owns only its packed volume; the borrowed DtN remains
        # usable until the independent native owner releases it.
        assert dtn.matrix.getType()
        native.destroy()
        dtn.destroy()
        source.destroy()
        target.destroy()


def test_large_coordinate_affine_geometry_is_translation_invariant_for_both_consumers():
    def build(shift):
        domain = mesh.create_unit_cube(
            MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron
        )
        domain.geometry.x[:, 2] += shift
        space = fem.functionspace(domain, ("N1curl", 2))
        dg = fem.functionspace(domain, ("DG", 0))
        mu, mass = fem.Function(dg), fem.Function(dg)
        mu.x.array[:] = 1.
        mass.x.array[:] = 1.
        kernel = IsotropicPartialAssembly(space, mu, mass)
        basis = PositiveCellBasis(space, mu, mass)
        domain.topology.create_entity_permutations()
        cell = basis.cell(0, domain.topology.get_cell_permutation_info()[0])
        coefficients = np.arange(int(kernel.dofs.max()) + 1, dtype=np.complex128)
        output = np.zeros_like(coefficients)
        kernel.apply(coefficients, output)
        return kernel, cell, output

    origin_kernel, origin_cell, origin_output = build(0.)
    shifted_kernel, shifted_cell, shifted_output = build(120.)
    np.testing.assert_allclose(shifted_kernel.metrics, origin_kernel.metrics,
                               rtol=1e-13, atol=1e-13)
    np.testing.assert_allclose(shifted_output, origin_output, rtol=1e-13, atol=1e-13)
    for shifted, origin in zip(shifted_cell[:3], origin_cell[:3]):
        np.testing.assert_allclose(shifted, origin, rtol=1e-13, atol=1e-13)
    assert shifted_cell[3] == origin_cell[3] == [1., 1.]


def test_positive_diagonal_still_rejects_a_true_nonaffine_cell():
    domain = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron)
    domain.geometry.x[0, 0] += .05
    space = fem.functionspace(domain, ("N1curl", 2))
    dg = fem.functionspace(domain, ("DG", 0))
    mu, mass = fem.Function(dg), fem.Function(dg)
    mu.x.array[:] = 1.
    mass.x.array[:] = 1.
    basis = PositiveCellBasis(space, mu, mass)
    domain.topology.create_entity_permutations()
    with pytest.raises(NotImplementedError, match="affine"):
        basis.cell(0, domain.topology.get_cell_permutation_info()[0])


@pytest.mark.skipif(MPI.COMM_WORLD.size != 2, reason="explicit tiny MPI2 qualification only")
def test_mpi2_double_floquet_owned_and_shared_ghosts():
    from dataclasses import replace
    from src.common.config_3d import target_stage4_config
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    cfg = replace(target_stage4_config(degree=3, h_nm=100),
        period_x=20., period_y=15., grating_width_x=8., grating_width_y=15.,
        grating_height=2., z_min=-1., z_max=3., air_height=3., substrate_thickness=1.,
        mesh_cell_type='hexahedron', mesh_spacing_mode='boundary_fitted',
        mesh_axis_cell_counts=(3, 2, 3), incident_theta_deg=74., incident_phi_deg=17.,
        n_substrate=1.4+.05j, n_grating=.9+.02j)
    comm = MPI.COMM_WORLD
    setup = _build_same_mesh_levels(cfg, comm, (2, 3))
    mu, mass = setup['mu'], setup['mass']
    for degree in (2, 3):
        mpc = setup['floquets'][degree].mpc
        space = mpc.function_space
        index = space.dofmap.index_map
        assert comm.allreduce(index.num_ghosts, op=MPI.SUM) > 0
        assert comm.allreduce(len(mpc.slaves), op=MPI.SUM) > 0
        coefficients, _ = mpc.coefficients()
        assert comm.allreduce(int(np.count_nonzero(np.asarray(coefficients).imag)), op=MPI.SUM) > 0
        form = same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass)
        kernel = IsotropicPartialAssembly(space, mu, mass)
        with ExitStack() as owned:
            oracle = FullspaceMpcFormAction(form, space, mpc=mpc)
            owned.callback(oracle.destroy)
            fast = FullspaceMpcFormAction(form, space, mpc=mpc, local_kernel=kernel)
            owned.callback(fast.destroy)
            source = oracle.matrix.createVecRight()
            owned.callback(source.destroy)
            start, stop = source.getOwnershipRange()
            ids = np.arange(start, stop)
            source.array[:] = np.sin(.37*ids) + 1j*np.cos(.19*ids)
            slaves = np.asarray(mpc.slaves)
            local_slaves = slaves[slaves < index.size_local]
            source.array[local_slaves] = 0
            before = source.array.copy()
            with oracle.apply(source).localForm() as local:
                expected = local.array.copy()
            with fast.apply(source).localForm() as local:
                observed = local.array.copy()
            assert len(observed) == index.size_local + index.num_ghosts
            for name, selection in (("owned", slice(0, index.size_local)),
                                     ("ghost", slice(index.size_local, None))):
                numerator = comm.allreduce(float(np.linalg.norm((observed-expected)[selection])**2), op=MPI.SUM)
                denominator = comm.allreduce(float(np.linalg.norm(expected[selection])**2), op=MPI.SUM)
                relative = np.sqrt(numerator/max(denominator, np.finfo(float).tiny))
                assert relative <= 1e-11
                if comm.rank == 0:
                    print('MPI2', degree, name, 'relative', relative, flush=True)
            assert np.all(np.isfinite(observed))
            np.testing.assert_array_equal(observed[slaves], 0)
            with fast.apply(source).localForm() as local:
                np.testing.assert_array_equal(local.array, observed)
            np.testing.assert_array_equal(source.array, before)
            print('MPI2 rank', comm.rank, 'degree', degree, 'owned', index.size_local,
                  'ghosts', index.num_ghosts, 'slaves', len(slaves), flush=True)
