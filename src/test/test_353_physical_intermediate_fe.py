"""One merged tiny real-FE batch; no outer solve or bottom factor."""

from contextlib import ExitStack
from dataclasses import replace
import json
import time

from dolfinx import fem
from mpi4py import MPI
import numpy as np
import ufl

from src.common.config_3d import target_stage4_config
from src.solvers.fullspace_physical_intermediate import (
    BorrowedActionAdapter, apply_owned, modified_residual_accept,
)
from src.solvers.fullspace_physical_intermediate_runtime import (
    PHYSICAL_PAIRS, build_physical_intermediate_actions,
    destroy_physical_intermediate_actions, level_vector, owned_slave_indices,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels


def test_tiny_real_fe_native_galerkin_and_algebraic_transfers():
    assert MPI.COMM_WORLD.size == 1, 'this initial tiny qualification is MPI1'
    started = time.perf_counter()
    cfg = replace(
        target_stage4_config(degree=6, h_nm=100),
        period_x=20.0, period_y=15.0, grating_width_x=8.0, grating_width_y=15.0,
        grating_height=2.0, z_min=-1.0, z_max=3.0, air_height=3.0,
        substrate_thickness=1.0, mesh_cell_type='hexahedron',
        mesh_spacing_mode='boundary_fitted', mesh_axis_cell_counts=(3, 2, 3),
        incident_theta_deg=74.0, incident_phi_deg=17.0,
        n_substrate=1.4+.05j, n_grating=.9+.02j,
    )
    print('A1b tiny setup started: 18 cells, p6/4/2/1; no original p6h10', flush=True)
    setup = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6, 4, 2, 1), include_positive_coefficients=True)
    bundle = None
    facts = {'classification': 'tiny_FE_action_qualification', 'pairs': {}, 'mass': {},
             'outer_solve': False, 'bottom_factors': {'positive': 'not_built', 'shifted': 'not_built'}}
    try:
        bundle = build_physical_intermediate_actions(
            setup, cfg, stage_callback=lambda name, value: print(
                f'A1b {name}: {value}', flush=True))
        facts.update({
            'cells': int(setup['mesh'].topology.index_map(3).size_global),
            'rows': {str(p): int(setup['spaces'][p].dofmap.index_map.size_global) for p in (6, 4, 2, 1)},
            'owned_slaves': {str(p): len(owned_slave_indices(setup['spaces'][p], setup['floquets'][p])) for p in (6, 4, 2, 1)},
            'fine_integral_metadata': bundle['fine_integral_metadata'],
            'dtn_quadrature_degree': bundle['dtn_quadrature_degree'],
            'mode_count': len(bundle['physical'][6]['modes']),
            'mode_sha256': bundle['mode_sha256'],
            'factor_count': bundle['factor_count'], 'global_aij_count': bundle['global_aij_count'],
        })
        assert set(bundle['mass']) == set(bundle['shifted']) == {4, 2, 1}
        assert all(bundle['physical'][p]['mode_sha256'] == bundle['mode_sha256'] for p in (6, 4, 2, 1))
        assert all(facts['owned_slaves'][str(p)] > 0 for p in (6, 4, 2, 1))

        def relative(a, b):
            error = a.copy()
            try:
                error.axpy(-1, b)
                return float(error.norm()) / max(float(a.norm()), float(b.norm()), np.finfo(float).tiny)
            finally:
                error.destroy()

        def random_vector(degree, seed, resources):
            vector = level_vector(setup, degree)
            resources.callback(vector.destroy)
            rng = np.random.default_rng(seed)
            vector.array[:] = rng.normal(size=vector.getLocalSize()) + 1j*rng.normal(size=vector.getLocalSize())
            vector.array[owned_slave_indices(setup['spaces'][degree], setup['floquets'][degree])] = 0
            return vector

        for fine, coarse in PHYSICAL_PAIRS:
            print(f'A1b actual FE pair {fine}->{coarse}', flush=True)
            transfer = bundle['transfers'][(fine, coarse)]
            with ExitStack() as resources:
                def own(vector):
                    resources.callback(vector.destroy)
                    return vector
                x = random_vector(coarse, 390+coarse, resources)
                y = random_vector(fine, 410+fine, resources)
                xb, yb = x.array.copy(), y.array.copy()
                px = own(transfer.apply_primal(x))
                phy = own(transfer.apply_adjoint(y))
                px_again = own(transfer.apply_primal(x))
                phy_again = own(transfer.apply_adjoint(y))
                # Independent NumPy inner products are valid for this MPI1 fixture.
                lhs, rhs = np.vdot(px.array, y.array), np.vdot(x.array, phy.array)
                adjoint = abs(lhs-rhs)/max(abs(lhs), abs(rhs), np.finfo(float).tiny)
                primal_repeat, adjoint_repeat = relative(px, px_again), relative(phy, phy_again)
                assert adjoint <= 1e-10
                assert max(primal_repeat, adjoint_repeat) <= 1e-12
                assert np.max(np.abs(px.array[transfer.fine_slaves])) == 0
                assert np.max(np.abs(phy.array[transfer.coarse_slaves])) == 0
                np.testing.assert_array_equal(x.array, xb)
                np.testing.assert_array_equal(y.array, yb)
                # Old public owner semantics remain full-field, with nonzero slaves.
                full = own(transfer.owner.apply_primal(x))
                assert np.max(np.abs(full.array[transfer.fine_slaves])) > 1e-8
                full.array[transfer.fine_slaves] = 0
                assert relative(full, px) <= 1e-12
                components = {'curl': {}, 'material_mass': {}, 'dtn': {}, 'physical': {}}
                for degree in (fine, coarse):
                    physical = bundle['physical'][degree]
                    for name, action in physical['volume_action'].component_actions.items():
                        components[name][degree] = BorrowedActionAdapter(action)
                    components['dtn'][degree] = physical['dtn_action']
                    components['physical'][degree] = physical['physical_action']
                if fine != 6:
                    components['mass'] = {p: bundle['mass'][p] for p in (fine, coarse)}
                    components['shifted'] = {p: bundle['shifted'][p] for p in (fine, coarse)}
                errors = {}
                for name, actions in components.items():
                    direct = own(apply_owned(actions[coarse], x))
                    fine_action = own(apply_owned(actions[fine], px))
                    projected = own(transfer.apply_adjoint(fine_action))
                    errors[name] = relative(direct, projected)
                    repeat = own(apply_owned(actions[coarse], x))
                    assert relative(direct, repeat) <= 1e-12
                    assert errors[name] <= (1e-11 if name == 'shifted' else 1e-10), (fine, coarse, name, errors)
                    assert np.max(np.abs(direct.array[transfer.coarse_slaves])) == 0
                if fine == 6:
                    residual = own(y.copy())
                    correction, mr = modified_residual_accept(
                        residual, px, bundle['physical'][6]['physical_action'])
                    own(correction)
                    assert np.max(np.abs(correction.array[transfer.fine_slaves])) == 0
                    assert np.max(np.abs(residual.array[transfer.fine_slaves])) == 0
                    facts['fine_direction_MR'] = mr
                facts['pairs'][f'{fine}->{coarse}'] = {
                    'adjoint_relative': float(adjoint), 'primal_repeat': primal_repeat,
                    'adjoint_repeat': adjoint_repeat, 'native_galerkin': errors,
                    'input_unchanged': True, 'algebraic_slave_max': 0.0,
                }
                np.testing.assert_array_equal(x.array, xb)
                np.testing.assert_array_equal(y.array, yb)

        for degree in (4, 2, 1):
            with ExitStack() as resources:
                source = random_vector(degree, 990+degree, resources)
                physical = apply_owned(bundle['physical'][degree]['physical_action'], source)
                resources.callback(physical.destroy)
                mass = apply_owned(bundle['mass'][degree], source)
                resources.callback(mass.destroy)
                shifted = apply_owned(bundle['shifted'][degree], source)
                resources.callback(shifted.destroy)
                physical.axpy(-.5j * cfg.k0**2, mass)
                shift_error = relative(physical, shifted)
                assert shift_error <= 1e-11
                # Independent scalar integral checks W's coefficient and absence of k0^2.
                floquet = setup['floquets'][degree]
                field = fem.Function(floquet.mpc.function_space)
                source.copy(field.x.petsc_vec)
                field.x.scatter_forward()
                floquet.mpc.homogenize(field)
                floquet.mpc.backsubstitution(field)
                field.x.scatter_forward()
                dx = ufl.Measure('dx', domain=setup['mesh'], subdomain_data=setup['mesh_data'].cell_tags,
                                 metadata=bundle['volume_quadrature_metadata'][1])
                energy_form = sum(max(abs(eps), 1e-12)*ufl.inner(field, field)*dx(tag)
                                  for tag, eps in ((cfg.tags.air, cfg.eps_air),
                                                   (cfg.tags.substrate, cfg.eps_substrate),
                                                   (cfg.tags.grating, cfg.eps_grating)))
                independent = complex(fem.assemble_scalar(fem.form(energy_form)))
                vector_energy = np.vdot(source.array, mass.array)
                energy_error = abs(independent-vector_energy)/abs(independent)
                assert energy_error <= 1e-11
                assert vector_energy.real > 0
                # Even deliberately nonzero slave input gets zero mass slave rows.
                source.array[owned_slave_indices(setup['spaces'][degree], floquet)] = 2+3j
                slave_probe = apply_owned(bundle['mass'][degree], source)
                resources.callback(slave_probe.destroy)
                assert np.max(np.abs(slave_probe.array[owned_slave_indices(setup['spaces'][degree], floquet)])) == 0
                facts['mass'][str(degree)] = {'independent_energy_relative': float(energy_error),
                                             'shift_composition_relative': shift_error,
                                             'slave_row_identity': False}
        facts['elapsed_seconds_inclusive'] = time.perf_counter() - started
        print('A1B_FACTS ' + json.dumps(facts, sort_keys=True, allow_nan=False), flush=True)
    finally:
        if bundle is not None:
            destroy_physical_intermediate_actions(bundle)
        setup.clear()
