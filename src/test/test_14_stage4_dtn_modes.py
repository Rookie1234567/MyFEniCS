from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import ufl
from dolfinx import fem, mesh
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from src.common.config_3d import SI_SUBSTRATE_INDEX_EUV_13P5_NM
from src.common.modes_3d import (
    incident_power_3d,
    outgoing_port_modes_3d,
)
from src.solvers.dtn_port_3d import (
    DTN_PORT_MODAL_POWER_SOURCE,
    DtnTraceAliasError,
    _auxiliary_direct_tangential_projection_audit,
    _dtn_n0_trace_alias_preflight,
    _incident_projection_onto_top_mode,
    _linear_residual,
    _mode_boundary_phase,
    _mode_power_at_boundary,
    _mode_projection_denominator,
    _mode_projections_from_solution,
    _outgoing_projection,
    _port_power_metrics,
    _sampled_tangential_projection,
    _traction_vector,
    _write_port_outputs,
)
from src.test.stage2_test_utils import stage4_block_config


def _dtn_cfg(**updates):
    values = {
        "stage_case": "stage4_block_grating",
        "stage4_boundary_model": "dtn_port",
        "stage4_dtn_order_policy": "auto_propagating",
        "stage4_dtn_assembly": "auxiliary",
        "use_pml": False,
        "pml_top_thickness": 0.0,
        "pml_bottom_thickness": 0.0,
        "diffraction_zero_order_only": True,
    }
    values.update(updates)
    return stage4_block_config(**values)


def _grazing_fixture_b_cfg(**updates):
    values = {
        "stage_case": "stage4_flat_layer_sanity",
        "stage4_dtn_order_policy": "zero_order",
        "period_x": 10.0,
        "period_y": 10.0,
        "air_height": 5.0,
        "substrate_thickness": 5.0,
        "z_min": -5.0,
        "z_max": 5.0,
        "grating_width_x": 0.0,
        "grating_width_y": 0.0,
        "grating_height": 0.0,
        "incident_theta_deg": 89.0,
    }
    values.update(updates)
    return _dtn_cfg(**values)


class Stage4DtnModeTests(unittest.TestCase):
    def test_linear_residual_releases_full_size_diagnostic_vector(self) -> None:
        residual = mock.Mock()
        residual.norm.return_value = 0.25
        rhs = mock.Mock()
        rhs.duplicate.return_value = residual
        rhs.norm.return_value = 1.0
        solution = mock.Mock()
        solution.norm.return_value = 0.5
        result = _linear_residual(mock.Mock(), rhs, solution)
        self.assertEqual(result["linear_system_residual_norm"], 0.25)
        residual.destroy.assert_called_once_with()

    @staticmethod
    def _alias_mode(n: int):
        return SimpleNamespace(
            side="top",
            m=0,
            n=int(n),
            polarization="s",
            k_vector=np.asarray([0.0, float(n), 1.0]),
            e_vector=np.asarray([1.0, 0.0, 0.0]),
        )

    @staticmethod
    def _alias_assemblers(vectors):
        class FakeAssembler:
            comm = MPI.COMM_SELF

            def __init__(self, component):
                self.component = component

            def assemble_entries(self, mode, _mpc):
                if self.component == 1:
                    return (
                        np.zeros(0, dtype=np.int32),
                        np.zeros(0, dtype=np.complex128),
                    )
                values = np.asarray(
                    vectors[int(mode.n)],
                    dtype=np.complex128,
                )
                return np.arange(len(values), dtype=np.int32), values

        return {
            ("top", 0): FakeAssembler(0),
            ("top", 1): FakeAssembler(1),
        }

    def test_opt_in_n0_trace_alias_preflight_fails_closed(self):
        modes = [self._alias_mode(0), self._alias_mode(-3)]
        orthogonal = _dtn_n0_trace_alias_preflight(
            modes,
            self._alias_assemblers(
                {0: [1.0, 0.0], -3: [0.0, 1.0]}
            ),
            None,
            enabled=True,
            overlap_tolerance=1.0e-8,
        )
        self.assertTrue(orthogonal["pass"])
        self.assertEqual(orthogonal["status"], "pass")
        with self.assertRaises(DtnTraceAliasError) as captured:
            _dtn_n0_trace_alias_preflight(
                modes,
                self._alias_assemblers(
                    {0: [1.0, 0.0], -3: [1.0, 0.0]}
                ),
                None,
                enabled=True,
                overlap_tolerance=1.0e-8,
            )
        self.assertEqual(
            captured.exception.audit["status"],
            "dtn_y_trace_alias_detected",
        )
        for bad_modes, vectors, expected in (
            (
                [self._alias_mode(-3)],
                {-3: [1.0, 0.0]},
                "not_exercised_missing_n0_target",
            ),
            (
                [self._alias_mode(0)],
                {0: [1.0, 0.0]},
                "not_exercised_missing_nonzero_n_control",
            ),
            (
                modes,
                {0: [0.0, 0.0], -3: [0.0, 1.0]},
                "invalid_zero_norm_trace_functional",
            ),
            (
                modes,
                {0: [1.0e200, 0.0], -3: [0.0, 1.0]},
                "invalid_nonfinite_trace_functional",
            ),
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(DtnTraceAliasError) as captured:
                    _dtn_n0_trace_alias_preflight(
                        bad_modes,
                        self._alias_assemblers(vectors),
                        None,
                        enabled=True,
                        overlap_tolerance=1.0e-8,
                    )
                self.assertEqual(
                    captured.exception.audit["status"],
                    expected,
                )

    def _single_bottom_s_power(self, cfg):
        modes = outgoing_port_modes_3d(cfg)
        bottom_index = next(
            idx
            for idx, mode in enumerate(modes)
            if mode.side == "bottom" and mode.m == 0 and mode.n == 0 and mode.polarization == "s"
        )
        incident_projections = [
            _incident_projection_onto_top_mode(mode, cfg) if mode.side == "top" else 0.0 + 0.0j
            for mode in modes
        ]
        aux_values = np.asarray(incident_projections, dtype=np.complex128)
        aux_values[bottom_index] = 1.0 + 0.0j
        metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
        return modes, bottom_index, incident_projections, aux_values, metrics

    def test_auto_dtn_orders_ignore_probe_zero_order_flag(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating", diffraction_zero_order_only=True)
        modes = outgoing_port_modes_3d(cfg)
        propagating_orders = {(mode.m, mode.n) for mode in modes if mode.propagating}
        self.assertIn((0, 0), propagating_orders)
        self.assertTrue(any(order != (0, 0) for order in propagating_orders))
        self.assertGreater(len(modes), 4)

    def test_zero_order_policy_keeps_only_zero_order_ports(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order", diffraction_zero_order_only=False)
        modes = outgoing_port_modes_3d(cfg)
        self.assertEqual({(mode.side, mode.m, mode.n) for mode in modes}, {("top", 0, 0), ("bottom", 0, 0)})
        self.assertEqual(len(modes), 4)

    def test_port_polarizations_are_transverse_and_power_positive(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating")
        for mode in outgoing_port_modes_3d(cfg):
            if not mode.propagating:
                continue
            self.assertLess(abs(np.dot(mode.k_vector, mode.e_vector)), 1.0e-10)
            self.assertGreater(mode.electric_tangential_norm_sq, 0.0)
            self.assertGreater(mode.power_per_unit_amplitude, 0.0)
            self.assertEqual(mode.vertical_sign, 1 if mode.side == "top" else -1)

    def test_zero_order_top_basis_projects_unit_incident_polarization(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        top_zero_modes = [
            mode for mode in outgoing_port_modes_3d(cfg) if mode.side == "top" and mode.m == 0 and mode.n == 0
        ]
        incident_e = np.asarray(cfg.polarization_vector, dtype=np.complex128)
        projections = [
            abs(np.vdot(mode.e_vector[:2], incident_e[:2])) ** 2 / mode.electric_tangential_norm_sq
            for mode in top_zero_modes
        ]
        self.assertAlmostEqual(float(sum(projections)), abs(complex(cfg.incident_amplitude)) ** 2, places=12)
        self.assertGreater(incident_power_3d(cfg), 0.0)

    def test_sampled_p_mode_projection_uses_only_tangential_components(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="auto_propagating")
        p_mode = next(
            mode
            for mode in outgoing_port_modes_3d(cfg)
            if mode.polarization == "p" and abs(mode.e_vector[2]) > 1.0e-10
        )
        sample_phases = np.asarray((1.0 + 0.0j, 0.0 + 1.0j), dtype=np.complex128)
        mode_samples = sample_phases[:, None] * p_mode.e_vector[None, :]
        expected = 2.0 - 3.0j
        electric_samples = expected * mode_samples
        electric_samples[:, 2] = np.asarray((1.0e6 + 2.0e6j, -3.0e6 + 4.0e6j))
        weights = np.asarray((0.25, 2.0), dtype=np.float64)

        projection = _sampled_tangential_projection(electric_samples, mode_samples, weights)
        full_vector_projection = np.sum(
            weights * np.sum(electric_samples * np.conj(mode_samples), axis=1)
        ) / np.sum(weights * np.sum(np.abs(mode_samples) ** 2, axis=1))

        self.assertNotEqual(p_mode.e_vector[2], 0.0)
        self.assertAlmostEqual(projection.real, expected.real, places=12)
        self.assertAlmostEqual(projection.imag, expected.imag, places=12)
        self.assertGreater(abs(full_vector_projection - expected), 1.0)

    def test_outgoing_projection_subtracts_incident_only_on_top(self):
        total = 3.0 + 5.0j
        incident = 1.0 - 2.0j

        self.assertEqual(_outgoing_projection(total, incident, "top"), 2.0 + 7.0j)
        self.assertEqual(_outgoing_projection(total, incident, "bottom"), total)

    def test_auxiliary_direct_projection_audit_covers_top_bottom_and_orders(self):
        cfg = _dtn_cfg(
            dtn_auxiliary_direct_projection_audit=True,
            dtn_auxiliary_direct_projection_tolerance=1.0e-10,
        )
        available = outgoing_port_modes_3d(cfg)
        modes = [
            next(
                mode
                for mode in available
                if mode.side == "top"
                and mode.polarization == "s"
                and (mode.m != 0 or mode.n != 0)
            ),
            next(
                mode
                for mode in available
                if mode.side == "bottom"
                and mode.polarization == "p"
                and abs(mode.e_vector[2]) > 1.0e-10
            ),
        ]
        auxiliary = np.asarray((2.0 + 3.0j, -1.0 + 0.5j))
        incident = [0.25 - 0.1j, 0.0 + 0.0j]
        with mock.patch(
            "src.solvers.dtn_port_3d._mode_projections_from_solution",
            return_value=list(auxiliary),
        ) as projection_mock:
            audit = _auxiliary_direct_tangential_projection_audit(
                object(),
                modes,
                auxiliary,
                incident,
                object(),
                cfg,
                quadrature_degree=17,
            )
        self.assertEqual(projection_mock.call_count, 1)
        self.assertEqual(projection_mock.call_args.args[1], modes)
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["quadrature_degree"], 17)
        self.assertEqual(len(audit["orders"]), 2)
        self.assertNotEqual(audit["orders"][0]["m"], 0)
        self.assertEqual(audit["orders"][1]["side"], "bottom")
        self.assertEqual(
            audit["orders"][0]["auxiliary_outgoing_projection"],
            auxiliary[0] - incident[0],
        )
        with self.assertRaisesRegex(ValueError, "input lengths must match"):
            _auxiliary_direct_tangential_projection_audit(
                object(),
                modes,
                auxiliary[:1],
                incident,
                object(),
                cfg,
                quadrature_degree=17,
            )
        with (
            mock.patch(
                "src.solvers.dtn_port_3d._mode_projections_from_solution",
                return_value=[complex(np.nan), auxiliary[1]],
            ),
            self.assertRaisesRegex(ValueError, "non-finite projection"),
        ):
            _auxiliary_direct_tangential_projection_audit(
                object(),
                modes,
                auxiliary,
                incident,
                object(),
                cfg,
                quadrature_degree=17,
            )

    def test_batch_projection_reuses_one_literal_form_per_active_side(self):
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        fdim = msh.topology.dim - 1
        top = mesh.locate_entities_boundary(
            msh, fdim, lambda coordinates: np.isclose(coordinates[2], 1.0)
        )
        bottom = mesh.locate_entities_boundary(
            msh, fdim, lambda coordinates: np.isclose(coordinates[2], 0.0)
        )
        cfg = _dtn_cfg()
        facets = np.concatenate((top, bottom)).astype(np.int32)
        values = np.concatenate(
            (
                np.full(len(top), cfg.tags.z_max, dtype=np.int32),
                np.full(len(bottom), cfg.tags.z_min, dtype=np.int32),
            )
        )
        order = np.argsort(facets)
        facet_tags = mesh.meshtags(msh, fdim, facets[order], values[order])
        mesh_data = SimpleNamespace(mesh=msh, facet_tags=facet_tags)
        electric_x = fem.Constant(msh, PETSc.ScalarType(1.25 - 0.3j))
        electric_y = fem.Constant(msh, PETSc.ScalarType(-0.4 + 0.8j))
        E_total = ufl.as_vector((electric_x, electric_y, PETSc.ScalarType(0.0)))
        available = outgoing_port_modes_3d(cfg)
        top_modes = [mode for mode in available if mode.side == "top"][:2]
        bottom_modes = [mode for mode in available if mode.side == "bottom"][:2]
        self.assertEqual(len(top_modes), 2)
        self.assertEqual(len(bottom_modes), 2)
        self.assertEqual(
            len({(mode.m, mode.n, mode.polarization) for mode in top_modes}), 2
        )
        self.assertEqual(
            len({(mode.m, mode.n, mode.polarization) for mode in bottom_modes}), 2
        )
        modes = [
            top_modes[0],
            bottom_modes[0],
            top_modes[1],
            bottom_modes[1],
        ]
        expected = []
        x = ufl.SpatialCoordinate(msh)
        ds = ufl.Measure("ds", domain=msh, subdomain_data=facet_tags)
        for mode in modes:
            phase = ufl.exp(
                PETSc.ScalarType(1j * mode.alpha) * x[0]
                + PETSc.ScalarType(1j * mode.gamma) * x[1]
                + PETSc.ScalarType(1j * mode.k_vector[2]) * x[2]
            )
            reference = ufl.as_vector(
                (
                    PETSc.ScalarType(mode.e_vector[0]) * phase,
                    PETSc.ScalarType(mode.e_vector[1]) * phase,
                    PETSc.ScalarType(0.0),
                )
            )
            literal_form = fem.form(
                ufl.inner(E_total, reference)
                * ds(cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min)
            )
            local = fem.assemble_scalar(literal_form)
            total = msh.comm.allreduce(local, op=MPI.SUM)
            expected.append(total / _mode_projection_denominator(mode, cfg))
        with mock.patch(
            "src.solvers.dtn_port_3d.fem.form", wraps=fem.form
        ) as form_mock:
            actual = _mode_projections_from_solution(
                E_total,
                modes,
                mesh_data,
                cfg,
                quadrature_degree=None,
            )
        self.assertEqual(form_mock.call_count, 2)
        np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1.0e-12)

    def test_sampled_projection_rejects_zero_tangential_mode_norm(self):
        electric_samples = np.asarray(((1.0, 2.0, 3.0),), dtype=np.complex128)
        normal_only_mode = np.asarray(((0.0, 0.0, 4.0 + 5.0j),), dtype=np.complex128)

        with self.assertRaisesRegex(ValueError, "zero tangential norm"):
            _sampled_tangential_projection(electric_samples, normal_only_mode)

    def test_lossy_bottom_port_power_is_evaluated_at_boundary_plane(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        bottom_y = [
            mode
            for mode in outgoing_port_modes_3d(cfg)
            if mode.side == "bottom" and mode.m == 0 and mode.n == 0 and mode.polarization == "y"
        ][0]
        phase = _mode_boundary_phase(bottom_y, cfg)
        self.assertLess(abs(phase), 1.0)
        self.assertAlmostEqual(
            _mode_power_at_boundary(bottom_y, cfg, 1.0 + 0.0j),
            bottom_y.power_per_unit_amplitude * abs(phase) ** 2,
            places=10,
        )
        area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
        self.assertAlmostEqual(
            _mode_projection_denominator(bottom_y, cfg),
            area * bottom_y.electric_tangential_norm_sq * abs(phase) ** 2,
            places=10,
        )

    def test_auxiliary_traction_uses_curl_cross_outward_normal_sign(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        y_modes = [
            mode
            for mode in outgoing_port_modes_3d(cfg)
            if mode.m == 0 and mode.n == 0 and mode.polarization == "y"
        ]
        self.assertEqual({mode.side for mode in y_modes}, {"top", "bottom"})
        for mode in y_modes:
            traction = _traction_vector(mode, cfg)
            self.assertAlmostEqual(traction[1].real, (-mode.beta.imag), places=12)
            self.assertAlmostEqual(traction[1].imag, mode.beta.real, places=12)

    def test_port_power_metrics_expose_dtn_modal_official_aliases(self):
        cfg = _dtn_cfg(stage4_dtn_order_policy="zero_order")
        modes = outgoing_port_modes_3d(cfg)
        incident_projections = [
            _incident_projection_onto_top_mode(mode, cfg) if mode.side == "top" else 0.0 + 0.0j
            for mode in modes
        ]
        aux_values = np.asarray(incident_projections, dtype=np.complex128)
        metrics = _port_power_metrics(cfg, modes, aux_values, incident_projections)
        self.assertEqual(metrics["power_source"], DTN_PORT_MODAL_POWER_SOURCE)
        self.assertEqual(metrics["diffraction_total_power_source"], DTN_PORT_MODAL_POWER_SOURCE)
        self.assertEqual(metrics["R_total"], metrics["R_total_dtn_port_modal"])
        self.assertEqual(metrics["T_total"], metrics["T_total_dtn_port_modal"])
        self.assertEqual(metrics["R_plus_T"], metrics["R_plus_T_dtn_port_modal"])
        self.assertIn("top outgoing amplitude", metrics["dtn_port_modal_amplitude_convention"])

    def test_lossy_below_critical_mode_counts_finite_port_transmission(self):
        cfg = _grazing_fixture_b_cfg()
        modes, bottom_index, incident_projections, aux_values, metrics = self._single_bottom_s_power(cfg)
        mode = modes[bottom_index]
        expected = _mode_power_at_boundary(mode, cfg, 1.0 + 0.0j) / incident_power_3d(cfg)

        self.assertFalse(mode.propagating)
        self.assertGreater(mode.power_per_unit_amplitude, 0.0)
        self.assertGreater(expected, 0.0)
        self.assertAlmostEqual(metrics["T_total"], expected, places=12)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, metrics, MPI.COMM_SELF)
            payload = json.loads((out_dir / "dtn_port_diffraction_orders_3d.json").read_text(encoding="utf-8"))
        row = payload["orders"][bottom_index]
        self.assertFalse(row["propagating"])
        self.assertTrue(row["power_carrying"])
        self.assertAlmostEqual(row["T"], expected, places=12)

    def test_lossless_evanescent_mode_carries_zero_finite_port_transmission(self):
        lossless_index = complex(SI_SUBSTRATE_INDEX_EUV_13P5_NM.real, 0.0)
        cfg = _grazing_fixture_b_cfg(n_substrate=lossless_index)
        modes, bottom_index, incident_projections, aux_values, metrics = self._single_bottom_s_power(cfg)
        mode = modes[bottom_index]

        self.assertFalse(mode.propagating)
        self.assertEqual(mode.power_per_unit_amplitude, 0.0)
        self.assertEqual(metrics["T_total"], 0.0)

        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir)
            _write_port_outputs(out_dir, cfg, modes, aux_values, incident_projections, metrics, MPI.COMM_SELF)
            payload = json.loads((out_dir / "dtn_port_diffraction_orders_3d.json").read_text(encoding="utf-8"))
        row = payload["orders"][bottom_index]
        self.assertFalse(row["propagating"])
        self.assertFalse(row["power_carrying"])
        self.assertEqual(row["T"], 0.0)


if __name__ == "__main__":
    unittest.main()
