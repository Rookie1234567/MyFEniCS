from __future__ import annotations

import json
from pathlib import Path
import unittest

import numpy as np
from basix.ufl import element
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import default_real_type, fem, mesh

from src.adaptivity.fixed_trace_goal_entity_localization import (
    localize_recovered_dual_sensitivity_proxy,
    reference_v1_goal_band,
)


_REFERENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "significant_channel_reference_v1.json"
)


def _reference_v1() -> dict:
    return json.loads(_REFERENCE_PATH.read_text(encoding="utf-8"))


def _space_and_dual(comm: MPI.Intracomm):
    msh = mesh.create_unit_cube(
        comm,
        2,
        2,
        1,
        cell_type=mesh.CellType.hexahedron,
    )
    space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            2,
            dtype=default_real_type,
        ),
    )
    index_map = space.dofmap.index_map
    dual = PETSc.Vec().createMPI(
        (index_map.size_local, index_map.size_global),
        comm=comm,
    )
    start, end = map(int, dual.getOwnershipRange())
    global_ids = np.arange(start, end, dtype=np.float64)
    dual.getArray()[:] = np.asarray(
        (1.0 + 0.125 * global_ids)
        + 1j * (0.25 - 0.03125 * global_ids),
        dtype=PETSc.ScalarType,
    )
    dual.assemble()
    return space, dual


def _goal(quantity: str) -> dict:
    return {
        "side": "top",
        "m": -4,
        "n": 0,
        "polarization": "s",
        "quantity": quantity,
    }


class TestTask035bFixedTraceGoalEntityLocalization(unittest.TestCase):
    def test_reference_v1_resolves_independent_component_bands(
        self,
    ) -> None:
        reference = _reference_v1()
        source = next(
            channel
            for channel in reference["channels"]
            if channel["channel"]["side"] == "top"
            and channel["channel"]["m"] == -4
            and channel["channel"]["n"] == 0
            and channel["channel"]["polarization"] == "s"
        )
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            resolved = reference_v1_goal_band(
                reference,
                _goal(quantity),
            )
            self.assertEqual(resolved["band_component"], quantity)
            self.assertEqual(
                resolved["absolute_band"],
                source["numerical_convergence_band"]["absolute"][
                    quantity
                ],
            )
            self.assertGreater(resolved["absolute_band"], 0.0)
        with self.assertRaisesRegex(
            ValueError,
            "does not resolve uniquely",
        ):
            reference_v1_goal_band(
                reference,
                {
                    **_goal("power"),
                    "m": 12345,
                },
            )

    def test_serial_proxy_closes_entities_and_periodic_components(
        self,
    ) -> None:
        space, dual = _space_and_dual(MPI.COMM_SELF)
        reference = _reference_v1()
        report = localize_recovered_dual_sensitivity_proxy(
            space,
            dual,
            goal=_goal("amplitude_real"),
            reference_v1=reference,
            periodic_axes={
                "x": (0.0, 1.0),
                "y": (0.0, 1.0),
            },
        )
        self.assertEqual(
            report["estimator"],
            "recovered_dual_coefficient_sensitivity_proxy",
        )
        self.assertFalse(report["actual_enriched_residual_available"])
        self.assertFalse(report["residual_weighted"])
        self.assertFalse(report["actual_dwr_indicator"])
        self.assertFalse(report["lane_b_formal_selection_authorized"])
        self.assertIn(
            "strict global-p6-trace enriched operator",
            report["dwr_unavailable_reason"],
        )
        for name in ("edge_trace", "face_trace", "cell"):
            rows = report["entities"][name]["rows"]
            identity_name = (
                "canonical_cell_id"
                if name == "cell"
                else "canonical_entity_id"
            )
            self.assertEqual(
                [row[identity_name] for row in rows],
                list(range(len(rows))),
            )
            self.assertTrue(
                all(
                    np.isfinite(
                        row["normalized_sensitivity_proxy"]
                    )
                    and row["normalized_sensitivity_proxy"] >= 0.0
                    for row in rows
                )
            )
        closure = report["cell_distribution_closure"]
        self.assertLess(closure["relative_closure"], 5.0e-14)
        band = report["normalization"]["absolute_band"]
        expected = float(
            np.sum(
                np.abs(
                    np.asarray(
                        dual.getArray(readonly=True),
                        dtype=np.complex128,
                    )
                )
            )
            / band
        )
        self.assertAlmostEqual(
            closure["all_entity_proxy_sum"],
            expected,
            places=7,
        )
        periodic = report["periodic_transitive_aggregation"]
        self.assertEqual(
            periodic["edge_trace"]["max_component_size"],
            4,
        )
        self.assertEqual(
            periodic["face_trace"]["max_component_size"],
            2,
        )
        four_member_components = [
            component
            for component in periodic["edge_trace"]["components"]
            if component["member_count"] == 4
        ]
        self.assertGreaterEqual(len(four_member_components), 1)
        for component in four_member_components:
            member_values = [
                report["entities"]["edge_trace"]["rows"][member][
                    "normalized_sensitivity_proxy"
                ]
                for member in component[
                    "member_canonical_entity_ids"
                ]
            ]
            self.assertAlmostEqual(
                component["component_proxy_sum"],
                sum(member_values),
                places=7,
            )
        dual.destroy()

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 2,
        "MPI2 canonical entity localization check",
    )
    def test_mpi2_canonical_identity_and_periodic_transitivity(
        self,
    ) -> None:
        comm = MPI.COMM_WORLD
        space, dual = _space_and_dual(comm)
        report = localize_recovered_dual_sensitivity_proxy(
            space,
            dual,
            goal=_goal("amplitude_imag"),
            reference_v1=_reference_v1(),
            periodic_axes={
                0: (0.0, 1.0),
                1: (0.0, 1.0),
            },
        )
        identity = {
            "mesh_geometry_sha256": report["mesh_geometry_sha256"],
            "edge_geometry_sha256": report["entities"]["edge_trace"][
                "geometry_sha256"
            ],
            "face_geometry_sha256": report["entities"]["face_trace"][
                "geometry_sha256"
            ],
            "edge_rows": report["entities"]["edge_trace"]["rows"],
            "face_rows": report["entities"]["face_trace"]["rows"],
            "cell_rows": report["entities"]["cell"]["rows"],
            "periodic": report["periodic_transitive_aggregation"],
        }
        identities = comm.allgather(identity)
        self.assertTrue(
            all(candidate == identities[0] for candidate in identities)
        )
        self.assertEqual(
            report["periodic_transitive_aggregation"]["edge_trace"][
                "max_component_size"
            ],
            4,
        )
        self.assertEqual(
            report["periodic_transitive_aggregation"]["face_trace"][
                "max_component_size"
            ],
            2,
        )
        self.assertLess(
            report["cell_distribution_closure"]["relative_closure"],
            5.0e-14,
        )
        self.assertFalse(report["actual_dwr_indicator"])
        self.assertFalse(report["lane_b_formal_selection_authorized"])
        dual.destroy()


if __name__ == "__main__":
    unittest.main()
