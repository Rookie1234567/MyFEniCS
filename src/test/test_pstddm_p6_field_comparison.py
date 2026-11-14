"""Native field sampling fixture, without a Maxwell solve or factorization."""
from pathlib import Path
import json
import tempfile
import unittest

import numpy as np

from src.postprocessing.pstddm_p6_convergence import (
    common_axes, quadrature_blocks, save_common_field_samples,
    compare_saved_common_fields,
    compare_saved_port_observables,
)


class P6ComparisonTests(unittest.TestCase):
    def test_mode_phase_and_lossy_energy_are_real_gates(self):
        port = dict(reference_planes={'top_z':130., 'bottom_z':-10.},
                    modal_amplitude_convention='test', power_source='test',
                    orders=[dict(side='top', m=0, n=0, polarization='s',
                                 outgoing_amplitude_at_boundary=[1., 0.], power_ratio=.2)])
        summary = dict(R_total=.2, T_total=.3, A_volume_total=.5,
                       linear_system_relative_residual=1e-12)
        with tempfile.TemporaryDirectory() as temporary:
            roots = [Path(temporary)/name for name in ('a','b')]
            for root in roots:
                root.mkdir()
                (root/'port_power.json').write_text(json.dumps(port))
                (root/'run_summary.json').write_text(json.dumps(summary))
            self.assertTrue(compare_saved_port_observables(*roots)['passed'])
            port['orders'][0]['outgoing_amplitude_at_boundary'] = [0., 1.]
            (roots[0]/'port_power.json').write_text(json.dumps(port))
            self.assertFalse(compare_saved_port_observables(*roots)['passed'])
            (roots[1]/'port_power.json').write_text(json.dumps(port))
            summary['A_volume_total'] = .6
            for root in roots:
                (root/'run_summary.json').write_text(json.dumps(summary))
            self.assertFalse(compare_saved_port_observables(*roots)['physics_pass'])

    def test_common_subcells_preserve_volume_and_polynomial_integral(self):
        pair = [([0., .4, 1.], [0., 1.], [0., 1.]),
                ([0., .7, 1.], [0., .3, 1.], [0., 1.])]
        volume = moment = 0.
        for points, weights in quadrature_blocks(pair):
            volume += weights.sum()
            moment += np.dot(weights, np.prod(points**4, axis=1))
        self.assertAlmostEqual(volume, 1.)
        self.assertAlmostEqual(moment, 1/125)
        with self.assertRaises(ValueError):
            common_axes([([0., 1.],)*3, ([0., 2.],)*3])

    def test_native_p6_curl_and_saved_complex_difference(self):
        from mpi4py import MPI
        from dolfinx import fem, mesh
        from basix.ufl import element
        from src.common.config_3d import SimulationConfig3D
        msh = mesh.create_unit_cube(MPI.COMM_WORLD, 1, 1, 1, cell_type=mesh.CellType.hexahedron)
        V = fem.functionspace(msh, element('N1curl', 'hexahedron', 6))
        field = fem.Function(V)
        field.interpolate(lambda x: (1+.2j)*np.asarray([x[1]**2, x[2]**2, x[0]**2]))
        field.x.scatter_forward()
        cfg = SimulationConfig3D(nedelec_degree=6, lambda0=13.5)
        pair = [([0., 1.],)*3, ([0., .5, 1.],)*3]
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            for name in ('a', 'b'):
                (base/name).mkdir()
                save_common_field_samples(field, cfg, base/name, pair)
            points = np.load(base/'a/common_field_samples/points.npy')
            actual = np.load(base/'a/common_field_samples/H.npy')
            curl = (1+.2j)*(-2)*points[:, [2, 0, 1]]
            np.testing.assert_allclose(actual, curl/(1j*cfg.k0), rtol=2e-10, atol=2e-10)
            result = compare_saved_common_fields(base/'a', base/'b')
            self.assertTrue(result['passed'])
            for item in result['fields'].values():
                self.assertEqual(item['relative_l2'], 0.)
            target = base/'b/common_field_samples/E.npy'
            with target.open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash'):
                compare_saved_common_fields(base/'a', base/'b')


if __name__ == '__main__':
    unittest.main()
