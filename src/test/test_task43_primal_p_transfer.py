from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from mpi4py import MPI

from benchmarks.task43_hp_adaptivity import round1_candidates as candidates
from src.adaptivity.exact_sequence_variable_p import (
    HexaEntityDegreeMap,
    build_variable_p_reference_space,
)
from src.adaptivity.stage4_local_h import (
    _build_forest,
    stage4_local_h_refinement_plan_payload,
)


class Task43ParentTransferPolicyTests(unittest.TestCase):
    def setUp(self):
        if MPI.COMM_WORLD.size != 1:
            self.skipTest("accepted-parent transfer policy is serial-only")

    def test_cli_keeps_transfer_by_default_and_skips_only_p_when_requested(self):
        parent = {
            "parent_storage_path": "unused-parent.npz",
            "parent_storage_sha256": "storage-hash",
            "parent_independent_fe_dofs": 100,
        }
        for skip in (False, True):
            with self.subTest(skip=skip), tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "plans"
                arguments = [
                    "--accepted-parent-selection-record", "unused-selection.json",
                    "--round-id", "policy_component", "--output-root", str(output),
                ]
                if skip:
                    arguments.append("--skip-parent-transfer")
                with (
                    patch.object(candidates, "_load_accepted_parent_state", return_value=parent),
                    patch.object(candidates, "_build_next_round_plan", return_value=({}, {})),
                    patch.object(candidates, "_audit_plan", side_effect=lambda *a, **k: {}) as audit,
                ):
                    self.assertEqual(candidates.main(arguments), 0)
                p_call, h_call = audit.call_args_list
                self.assertIs(p_call.kwargs["audit_parent_transfer"], not skip)
                self.assertNotIn("parent_storage_path", h_call.kwargs)
                self.assertNotIn("audit_parent_transfer", h_call.kwargs)
                bundle = json.loads((output / "plan_audit.json").read_text())
                self.assertIs(bundle["skip_parent_transfer_requested"], skip)

    def test_skip_preserves_real_authority_and_rejects_changed_parent_hash(self):
        cfg = candidates._h100_config(
            kind="empty_h_active_p3", case_name="task43_transfer_policy_component"
        )
        forest = _build_forest(
            cfg, comm_size=1, marked_root_boxes=(), maximum_level=1,
            allow_no_refinement=True,
        )
        plan = stage4_local_h_refinement_plan_payload(
            cfg, (), comm_size=1, trace_degree=3, cell_interior_degree=6,
            provenance={"purpose": "transfer policy component, no PDE"},
            cell_interior_degree_overrides={leaf.box: 3 for leaf in forest.leaves},
            variable_trace_from_cell_degrees=True, allow_no_refinement=True,
        )
        plan["task43_candidate"] = {
            "action": "p_up", "provenance": {"accepted_parent_selection_sha256": "component"},
        }
        with tempfile.TemporaryDirectory() as directory:
            plan_path = Path(directory) / "plan.json"
            plan_path.write_text(json.dumps(plan))
            storage = Path(directory) / "parent.npz"
            # Deliberately not an NPZ: skipped transfer must never load its field.
            storage.write_bytes(b"hash-bound component storage")
            arguments = {
                "plan_path": plan_path, "candidate_id": "policy_component", "comm": MPI.COMM_WORLD,
                "parent_storage_path": storage,
                "parent_storage_sha256": candidates._sha256_file(storage),
            }
            with patch.object(
                candidates, "_create_nedelec_space",
                side_effect=AssertionError("transfer entered"),
            ) as transfer:
                record = candidates._audit_plan(cfg, **arguments, audit_parent_transfer=False)
                transfer.assert_not_called()
                self.assertTrue(record["degrees"]["degree_plan_pass"])
                self.assertTrue(record["degrees"]["entity_constraints_pass"])
                self.assertEqual(record["forest"]["actual_leaf_cell_count"], len(forest.leaves))
                self.assertGreater(record["dofs"]["independent_active_fe_dofs"], 0)
                skipped = record["accepted_parent_transfer_audit"]
                self.assertEqual(skipped["status"], "not_run_direct_solve_does_not_use_initial_guess")
                self.assertIsNone(skipped["pass"])
                self.assertIsNone(skipped["wall_seconds"])
                self.assertEqual(skipped["cost_status"], "not_incurred")
                self.assertEqual(skipped["parent_storage_sha256"], arguments["parent_storage_sha256"])
                # Omitting the flag still enters the existing expensive path.
                with self.assertRaisesRegex(AssertionError, "transfer entered"):
                    candidates._audit_plan(cfg, **arguments)
                transfer.assert_called_once()
                storage.write_bytes(b"changed after binding")
                with self.assertRaisesRegex(ValueError, "storage SHA differs"):
                    candidates._audit_plan(cfg, **arguments, audit_parent_transfer=False)
                transfer.assert_called_once()

            plan["task43_candidate"]["action"] = "h_refine"
            plan_path.write_text(json.dumps(plan))
            h_record = candidates._audit_plan(
                cfg, plan_path=plan_path, candidate_id="h_policy_component", comm=MPI.COMM_WORLD,
                audit_parent_transfer=False,
            )
            self.assertEqual(
                h_record["accepted_parent_transfer_audit"]["status"],
                "not_run_cross_mesh_transfer_not_qualified",
            )
            self.assertIsNone(h_record["accepted_parent_transfer_audit"]["pass"])


class Task43PrimalVariablePTransferTests(unittest.TestCase):
    def test_oriented_p4_to_p5_primal_extraction_roundtrips_nonzero_cell_info(
        self,
    ):
        parent = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(4)
        )
        candidate = build_variable_p_reference_space(
            HexaEntityDegreeMap.uniform(5)
        )
        cell_info = 0b011  # face-0 reflection and one quarter-turn
        self.assertNotEqual(cell_info, 0)
        rng = np.random.default_rng(4305)
        parent_active = (
            rng.standard_normal(parent.hcurl_dimension)
            + 1j * rng.standard_normal(parent.hcurl_dimension)
        )
        parent_p6 = parent.active_to_p6_oriented(
            parent_active,
            cell_info=cell_info,
        )
        candidate_active, audit = candidate.extract_hcurl_coefficients_from_p6(
            parent_p6,
            cell_info=cell_info,
        )
        reconstructed_p6 = candidate.active_to_p6_oriented(
            candidate_active,
            cell_info=cell_info,
        )
        self.assertFalse(audit["transpose_dual_projection_used"])
        self.assertEqual(audit["cell_info"], cell_info)
        self.assertLessEqual(audit["p6_to_active_identity_error_max"], 5.0e-10)
        np.testing.assert_allclose(
            reconstructed_p6,
            parent_p6,
            rtol=5.0e-12,
            atol=5.0e-12,
        )

    def test_custom_mixed_entity_primal_extraction_roundtrips_orientation(self):
        parent = build_variable_p_reference_space(
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=3,
                face_degree=3,
                cell_degree=4,
            )
        )
        candidate = build_variable_p_reference_space(
            HexaEntityDegreeMap.dimension_uniform(
                edge_degree=3,
                face_degree=4,
                cell_degree=5,
            )
        )
        cell_info = 0b011
        rng = np.random.default_rng(4315)
        parent_active = (
            rng.standard_normal(parent.hcurl_dimension)
            + 1j * rng.standard_normal(parent.hcurl_dimension)
        )
        parent_p6 = parent.active_to_p6_oriented(
            parent_active,
            cell_info=cell_info,
        )
        candidate_active, audit = candidate.extract_hcurl_coefficients_from_p6(
            parent_p6,
            cell_info=cell_info,
        )
        reconstructed_p6 = candidate.active_to_p6_oriented(
            candidate_active,
            cell_info=cell_info,
        )
        self.assertLessEqual(audit["p6_to_active_identity_error_max"], 5.0e-10)
        np.testing.assert_allclose(
            reconstructed_p6,
            parent_p6,
            rtol=5.0e-12,
            atol=5.0e-12,
        )


if __name__ == "__main__":
    unittest.main()
