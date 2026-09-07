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
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form


@pytest.mark.parametrize("degree", [2, 3, 6])
@pytest.mark.parametrize("component", [None, "curl", "mass"])
def test_original_form_complex_multimaster_affine_orientation(degree, component):
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
        component_form=form if component else None, component=component)
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
