"""Synthetic primitive contracts only; no FE/JIT/new factors/PDE qualification."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from src.solvers import fresh_paired_compact_checker as checker


def metadata_fixture(stage="solve"):
    # Exact alias inventory in generator order is enough for metadata tests.
    counts = (76, 152, 152, 152)
    keys = [["top", i, q, "s"] for q in range(4) for i in range(counts[q])]
    authority = {"mode_keys": keys, "input_sha256": "1" * 64, "mode_manifest_sha256": "2" * 64}
    artifacts = {}
    def array(name, shape=(1,), dtype="complex128"):
        artifacts[name] = {"shape": list(shape), "dtype": dtype,
                           "payload_bytes": __import__("math").prod(shape) * checker.DTYPE_BYTES[dtype],
                           "file_sha256": "3" * 64, "path": "arrays/" + name + ".npy"}
    report = {"schema": checker.SCHEMA, "stage": stage, "prefactor_only": stage == "prefactor",
              "status": "FRESH_PAIRED_COMPACT_FULL3D_INVERSE_PASS" if stage == "solve" else "FRESH_PAIRED_ALLQ_PREFACTOR_PASS",
              "factor_count": 4 if stage == "solve" else 0, "degree": 4, "physical_mode_count": 532,
              "candidate_full_Ny_CSR_created": False, "candidate_full_F_created": False,
              "candidate_full_Q_created": False, "resident_Hhat_bytes": 0, "all_prefactor_gates_before_factors": True,
              "layout": {"full_storage_rows": 17204, "independent_rows": 15872, "ny": 4,
                         "rows_per_q": 3968, "all_q": [0, 1, 2, 3]}, "global_mode_keys": keys,
              "input_sha256": authority["input_sha256"], "physical_generator_manifest_sha256": authority["mode_manifest_sha256"],
              "reformed_blocks": [{"q": q, "shape": [checker.Q_ROWS[q]] * 2, "csr_prefix": f"q_{q}_S",
                 "physical_alias_count": counts[q], "nnz": 1, "CSR_sha256": "4" * 64} for q in range(4)],
              "cross_blocks": [{"p": p, "q": q, "csr_prefix": f"cross_{p}_{q}"} for p, q in sorted(checker.CROSS_PAIRS)],
              "raw_sector_receipts": [{"b": b, "sector_original_indices": [i for i, k in enumerate(keys) if k[2] % 2 == b]} for b in (0, 1)],
              "local_compact_snapshots": [], "artifacts": artifacts}
    for b in (0, 1):
        m = checker.PORT_COUNTS[b]
        report["local_compact_snapshots"].append({"twist": b, "port_count": m, "q_indices": [b, b + 2],
             "cells": [{} for _ in range(40)], "partition": {key: {} for key in ("independent", "trace", "interior", "slaves")},
             "qmaps": [{"shape": [3616 + m, checker.Q_ROWS[q]]} for q in (b, b + 2)],
             "carrier_records": [{} for _ in range(m)], "resident_dense_H_bytes": 0,
             "original_H_diagonal_bytes": m * 16, "resident_Hhat_bytes": 0,
             "recipes": [{"label": label} for label in sorted({"ports/H_original"} |
                 {f"volume/cell/{i}" for i in range(40)} | {f"direct/{s}/port/{i}" for s in ("C", "-D") for i in range(m)})]})
    for name, shape in {"independent_storage_rows": (15872,), "actual_interior_positions": (8640,),
         "full_mpc_slaves": (1332,), "full_mpc_offsets": (17205,), "port_original_H": (532,),
         "port_q_labels": (532,), "port_factor_coordinate_scale": (532,)}.items():
        array(name, shape)
    for name in ("full_mpc_masters", "full_mpc_coefficients", "original_carrier_global_rows", "original_carrier_ownership_range",
                 "original_carrier_slave_rows", "original_mode_e_vectors", "original_mode_k_vectors", "original_mode_outward_signs",
                 "original_mode_magnetic_denominator", "original_mode_boundary_area", "original_mode_incident_projections"):
        array(name, {"original_carrier_global_rows": (), "original_carrier_ownership_range": (2,),
                     "original_carrier_slave_rows": (1332,), "original_mode_e_vectors": (532, 3),
                     "original_mode_k_vectors": (532, 3), "original_mode_outward_signs": (532,),
                     "original_mode_magnetic_denominator": (), "original_mode_boundary_area": (),
                     "original_mode_incident_projections": (532,)}.get(name, (1,)))
    for prefix in [f"q_{q}_S" for q in range(4)] + [v["csr_prefix"] for v in report["cross_blocks"]] + ["original_port_C", "original_port_D"]:
        for part in ("data", "indices", "indptr"):
            array(prefix + "_" + part)
    for q in range(4):
        for suffix in ("column_error_norms", "reference_column_norms"):
            array(f"q_{q}_map_{suffix}", (3968,))
    for b in (0, 1):
        m = checker.PORT_COUNTS[b]
        for suffix, size in (("state", 8940), ("alpha", m), ("FE_rhs", 8940), ("port_rhs", m),
                             ("reduced_rhs", 3616 + m), ("reduced_action", 3616 + m), ("recovered", 8940)):
            array(f"twist_{b}_complete_recovery_{suffix}", (size,))
        array(f"twist_{b}_original_H", (m,))
    if stage == "solve":
        packet = {"outputs": {"status": "representable_global_output", "global_output_component_consistency_checked": True,
                               "finite_plane_mode_count": 532}}
        report.update(PDE_solved=True, regular_sources={k: copy.deepcopy(packet) for k in checker.SOURCES},
                      notched_sources={k: copy.deepcopy(packet) for k in checker.SOURCES}, augmented_controls=[{"q": q} for q in range(4)],
                      factor={"all_q_factors": 4, "all_four_retained_simultaneously": True,
                              "factor_reuse_plus_minus_q": False, "input_blocks": copy.deepcopy(report["reformed_blocks"])},
                      live_cache_numeric_sha256_before=["5" * 64, "6" * 64],
                      live_cache_numeric_sha256_after=["5" * 64, "6" * 64],
                      live_cache_recipe_before=[{}, {}], live_cache_recipe_after=[{}, {}],
                      same_live_cache_owners_through_apply=True, cache_rebuilt_per_PC_apply=False)
        for q in range(4):
            for suffix in ("rhs_a", "rhs_b", "solution_a", "solution_a_repeat", "solution_b", "solution_sum", "action_a"):
                array(f"q_{q}_" + suffix, (checker.Q_ROWS[q],))
        for name in checker.SOURCES:
            array(name + "_rhs", (15872,))
            for prefix in ("regular_", "notch_"):
                label = prefix + name
                array(label + "_solution", (15872,))
                for suffix in checker.VECTOR_SUFFIXES + checker.OUTPUT_SUFFIXES + checker.GLOBAL_OUTPUT_SUFFIXES:
                    array(label + "_" + suffix, (532, 3) if suffix in ("plane_electric", "plane_magnetic") else
                          (17204,) if suffix in ("rhs_storage", "solution_storage", "original_action", "volume_action",
                            "coupling_action", "native_residual", "augmented_FE_residual", "recovered_field") else (532,))
        for q in range(4):
            for suffix in checker.VECTOR_SUFFIXES + ("FE_rhs", "port_rhs", "solution", "effective_rhs", "port_operation_scale"):
                array(f"aug_q_{q}_" + suffix, (15872,) if suffix in ("FE_rhs", "solution", "effective_rhs") else
                      (17204,) if suffix in ("rhs_storage", "solution_storage", "original_action", "volume_action",
                        "coupling_action", "native_residual", "augmented_FE_residual") else (532,))
    return report, authority


class ActualSourceSchemaContracts(unittest.TestCase):
    def test_actual_clean_source_facts_schema_reaches_candidate_admission(self):
        report, authority = metadata_fixture()
        # source_facts serializes git porcelain as a string, including clean "".
        actual = {"head": "a" * 40, "branch": "task40extra_dot_parallel_cloud",
                  "dirty": "", "files_sha256": {"src/solvers/example.py": "b" * 64}}
        report.update(source=actual, source_clean_unchanged=True, environment={"ABI": "current"}, authority={"pinned": "test"})
        with mock.patch.object(checker, "_Candidate", side_effect=RuntimeError("candidate_admission_reached")) as candidate:
            with self.assertRaisesRegex(RuntimeError, "candidate_admission_reached"):
                checker.check_paired_compact_inverse(report, directory=".", reference=mock.Mock(report=authority, identity=mock.Mock(return_value={"pinned": "test"})),
                    allocation_gate=lambda *args: None, checker_source=copy.deepcopy(actual),
                    checker_environment=copy.deepcopy(report["environment"]))
            candidate.assert_called_once()

    def test_boolean_clean_or_dirty_porcelain_never_substitutes_actual_schema(self):
        for value in (False, True, " M src/solvers/example.py", None):
            report, authority = metadata_fixture()
            report.update(source={"head": "a" * 40, "branch": "task40extra_dot_parallel_cloud", "dirty": value},
                          source_clean_unchanged=True)
            with mock.patch.object(checker, "_Candidate") as candidate:
                with self.assertRaisesRegex(ValueError, "clean frozen own-branch"):
                    checker.check_paired_compact_inverse(report, directory=".", reference=mock.Mock(report=authority),
                                                        allocation_gate=lambda *args: None)
                candidate.assert_not_called()


class MetadataContracts(unittest.TestCase):
    def test_complete_current_stage_inventory_is_admitted(self):
        for stage in ("solve", "prefactor"):
            report, authority = metadata_fixture(stage)
            self.assertTrue(checker.validate_candidate_inventory(report, authority))

    def test_missing_diagonal_rejected_before_candidate_mapping(self):
        report, authority = metadata_fixture()
        report["reformed_blocks"].pop()
        with mock.patch("numpy.load", side_effect=AssertionError("must not mmap")) as mapping:
            with self.assertRaisesRegex(ValueError, "all4 diagonal"):
                checker.check_paired_compact_inverse(report, directory=".", reference=mock.Mock(report=authority),
                                                    allocation_gate=lambda *args: None)
            mapping.assert_not_called()

    def test_all_four_ordered_cross_directions_required(self):
        report, authority = metadata_fixture()
        report["cross_blocks"][0] = copy.deepcopy(report["cross_blocks"][1])
        with self.assertRaisesRegex(ValueError, "four ordered"):
            checker.validate_candidate_inventory(report, authority)

    def test_sector_union_cannot_duplicate_a_global_mode(self):
        report, authority = metadata_fixture()
        report["raw_sector_receipts"][1]["sector_original_indices"][0] = 0
        with self.assertRaisesRegex(ValueError, "local40/228"):
            checker.validate_candidate_inventory(report, authority)

    def test_all_actual_interiors_are_required(self):
        report, authority = metadata_fixture()
        report["artifacts"]["actual_interior_positions"]["shape"] = [8639]
        with self.assertRaisesRegex(ValueError, "shape inventory"):
            checker.validate_candidate_inventory(report, authority)

    def test_original_notch_fourth_load_cannot_be_omitted(self):
        report, authority = metadata_fixture()
        del report["artifacts"]["notch_notch_supported_plane_magnetic"]
        with self.assertRaisesRegex(ValueError, "saved candidate arrays"):
            checker.validate_candidate_inventory(report, authority)

    def test_augmented_nonzero_port_rhs_inventory_required(self):
        report, authority = metadata_fixture()
        del report["artifacts"]["aug_q_3_port_rhs"]
        with self.assertRaisesRegex(ValueError, "saved candidate arrays"):
            checker.validate_candidate_inventory(report, authority)

    def test_forbidden_full_candidate_map_rejected(self):
        report, authority = metadata_fixture()
        report["candidate_full_Q_created"] = True
        with self.assertRaisesRegex(ValueError, "compact ownership"):
            checker.validate_candidate_inventory(report, authority)

    def test_byte_descriptor_is_checked_before_mapping(self):
        report, authority = metadata_fixture()
        report["artifacts"]["q_0_S_data"]["payload_bytes"] += 1
        with self.assertRaisesRegex(ValueError, "descriptor invalid"):
            checker.validate_candidate_inventory(report, authority)

    def test_factor_input_hash_cannot_detach_from_checked_csr(self):
        report, authority = metadata_fixture()
        report["factor"]["input_blocks"][2]["CSR_sha256"] = "f" * 64
        with self.assertRaisesRegex(ValueError, "factor detached"):
            checker.validate_candidate_inventory(report, authority)

    def test_cache_numeric_owner_lifecycle_must_be_unchanged(self):
        report, authority = metadata_fixture()
        report["live_cache_numeric_sha256_after"][1] = "f" * 64
        with self.assertRaisesRegex(ValueError, "cache lifecycle"):
            checker.validate_candidate_inventory(report, authority)

    def test_saved_global_output_is_mandatory(self):
        report, authority = metadata_fixture()
        del report["artifacts"]["regular_physical_global_total_auxiliary"]
        with self.assertRaisesRegex(ValueError, "saved candidate arrays"):
            checker.validate_candidate_inventory(report, authority)

    def test_global_output_controlled_stop_cannot_be_a_pass(self):
        report, authority = metadata_fixture()
        report["notched_sources"]["physical"]["outputs"]["status"] = "global_output_controlled_stop"
        with self.assertRaisesRegex(ValueError, "representability"):
            checker.validate_candidate_inventory(report, authority)


class SavedFactorContracts(unittest.TestCase):
    @staticmethod
    def fixture():
        import numpy as np
        from scipy import sparse
        j = np.arange(3)
        a, b = np.cos(.23 * j) + 1j * np.sin(.37 * j), np.sin(.29 * j) + 1j * np.cos(.41 * j)
        arrays = {"rhs_a": a, "rhs_b": b, "solution_a": a.copy(), "solution_a_repeat": a.copy(),
                  "solution_b": b.copy(), "solution_sum": a + b, "action_a": a.copy()}
        read = mock.Mock(load=lambda key: arrays[key.removeprefix("q_0_")])
        return arrays, read, sparse.eye(3, format="csr", dtype=complex)

    def test_saved_primitive_factor_controls_use_only_products(self):
        _, read, matrix = self.fixture()
        checks = checker._Checks()
        checker._saved_factor_controls(0, matrix, read, checks)
        self.assertEqual(len(checks.records), 5)

    def test_corrupted_factor_solution_rejected(self):
        arrays, read, matrix = self.fixture()
        arrays["solution_b"][1] += .01
        with self.assertRaisesRegex(ValueError, "true_residual_b"):
            checker._saved_factor_controls(0, matrix, read, checker._Checks())

    def test_corrupted_saved_factor_action_rejected(self):
        arrays, read, matrix = self.fixture()
        arrays["action_a"][0] += .01
        with self.assertRaisesRegex(ValueError, "action_binding"):
            checker._saved_factor_controls(0, matrix, read, checker._Checks())


class AlgebraContracts(unittest.TestCase):
    def test_zero_scale_is_exact_including_subnormal_error(self):
        import numpy as np
        checks = checker._Checks()
        self.assertTrue(checker.metric_record(0, 0, 1e-11)["passed"])
        with self.assertRaisesRegex(ValueError, "saved algebra gate"):
            checks.compare("underflow", np.asarray([1e-300]), np.zeros(1), scale=0)
        self.assertFalse(checks.records[0]["passed"])

    def test_per_mode_scale_never_borrows_a_larger_mode(self):
        import numpy as np
        checks = checker._Checks()
        with self.assertRaisesRegex(ValueError, "per-mode gate"):
            checks.modes("weak_mode", np.asarray([0., 1e-12]), np.zeros(2), np.asarray([1e10, 1e-10]))

    def test_zero_per_mode_scale_is_exact(self):
        import numpy as np
        with self.assertRaisesRegex(ValueError, "per-mode gate"):
            checker._Checks().modes("zero_mode", np.asarray([1e-300]), np.zeros(1), np.zeros(1))

    def test_nonfinite_metrics_are_json_safe_failures(self):
        for error, scale, limit in ((float("nan"), 1., 1e-11), (1., float("inf"), 1e-11), (1., 1., float("inf"))):
            record = checker.metric_record(error, scale, limit)
            self.assertFalse(record["passed"])
            json.dumps(record, allow_nan=False)

    def test_cross_recipe_difference_uses_each_diagonal(self):
        import numpy as np
        from scipy import sparse
        a = sparse.csr_matrix(np.asarray([[1e-12 + 0j]]))
        b = sparse.csr_matrix((1, 1), dtype=complex)
        checker._sparse_compare(checker._Checks(), lambda *args: None, a, b, "cross", diagonal_scales=(1., 1.))
        with self.assertRaisesRegex(ValueError, "saved algebra gate"):
            checker._sparse_compare(checker._Checks(), lambda *args: None, a, b, "cross", diagonal_scales=(1., .01))


class OriginalOperandContracts(unittest.TestCase):
    @staticmethod
    def fixture(cancellation=False):
        import numpy as np
        from scipy import sparse
        independent = np.arange(15872, dtype=np.int32)
        slaves = np.arange(15872, 17204, dtype=np.int32)
        x, field, rhs = np.zeros(15872, complex), np.zeros(17204, complex), np.zeros(15872, complex)
        x[0] = field[0] = rhs[0] = 1
        right = np.zeros(17204, complex)
        right[0] = 1
        h, alpha = np.ones(532), np.zeros(532, complex)
        c, d = sparse.csc_matrix((17204, 532), dtype=complex), sparse.csr_matrix((532, 17204), dtype=complex)
        volume = right.copy()
        if cancellation:
            c = sparse.csc_matrix(([-1 + 0j], ([0], [0])), shape=(17204, 532))
            d = sparse.csr_matrix(([1e10 + 0j], ([0], [0])), shape=(532, 17204))
            alpha[0] = 1e10
            volume[0] = 1e10 + 1
        projection, coupling = d @ field, c @ alpha
        dnorm = np.zeros(532)
        dnorm[0] = 1e10 if cancellation else 0
        arrays = {"rhs_storage": right, "solution_storage": field, "volume_action": volume,
                  "original_action": right.copy(), "auxiliary_ports": alpha, "normalization_h": h,
                  "projection": projection, "coupling_action": coupling, "native_residual": np.zeros(17204, complex),
                  "augmented_FE_residual": np.zeros(17204, complex), "augmented_port_residual": np.zeros(532, complex)}
        inventory = (independent, np.arange(8640), slaves, None, None, None, h, c, d, dnorm)
        read = mock.Mock(load=lambda key: arrays[key.removeprefix("control_")])
        return arrays, inventory, read, rhs, x, np.zeros(532, complex)

    def test_corrupted_saved_original_volume_operand_is_rejected(self):
        arrays, inventory, read, rhs, x, g = self.fixture()
        arrays["volume_action"][0] += .01
        with self.assertRaisesRegex(ValueError, "bound_original_action"):
            checker._original_equations("control", rhs, x, g, read, checker._Checks(), inventory)


    def test_corrupted_original_coupling_operand_is_rejected(self):
        arrays, inventory, read, rhs, x, g = self.fixture()
        arrays["coupling_action"][0] += 1e-12
        with self.assertRaisesRegex(ValueError, "original_C_coupling"):
            checker._original_equations("control", rhs, x, g, read, checker._Checks(), inventory)

    def test_operand_scale_does_not_relax_true_original_residual(self):
        arrays, inventory, read, rhs, x, g = self.fixture(cancellation=True)
        arrays["original_action"][0] += 1e-6
        with self.assertRaisesRegex(ValueError, "full_original_true_residual"):
            checker._original_equations("control", rhs, x, g, read, checker._Checks(), inventory)

    def test_residual_record_consistency_uses_equation_operands(self):
        arrays, inventory, read, rhs, x, g = self.fixture(cancellation=True)
        arrays["augmented_FE_residual"][0] = 1e-4
        result = checker._Checks()
        checker._original_equations("control", rhs, x, g, read, result, inventory)
        record = next(r for r in result.records if r["name"] == "control_augmented_FE_residual_record")
        self.assertTrue(record["passed"])
        self.assertGreater(record["operation_scale"], 1e10)

    def test_detached_solution_packet_is_rejected_before_equations(self):
        arrays, inventory, read, rhs, x, g = self.fixture()
        arrays["solution_storage"][1] = .001
        with self.assertRaisesRegex(ValueError, "solution/RHS/slave binding"):
            checker._original_equations("control", rhs, x, g, read, checker._Checks(), inventory)


class GlobalOutputContracts(unittest.TestCase):
    def test_corrupted_saved_global_total_is_rejected_with_plane_outputs_intact(self):
        import numpy as np
        _, inventory, _, _, _, _ = OriginalOperandContracts.fixture()
        independent, interiors, slaves, _, _, _, h, c, d, _ = inventory
        field = np.zeros(17204, complex)
        field[0] = 1
        masters, coefficients, offsets = np.empty(0, np.int32), np.empty(0, complex), np.zeros(17205, np.int32)
        inventory = independent, interiors, slaves, masters, coefficients, offsets, h, c, d, np.ones(532)
        e, k = np.zeros((532, 3), complex), np.zeros((532, 3), complex)
        e[:, 0], k[:, 2] = 1, 1
        generator = e, k, np.ones(532), np.zeros(532, complex), 1., 1., [None] * 532, None
        arrays = {"recovered_field": field, "plane_total_auxiliary": np.zeros(532, complex),
                  "plane_outgoing_auxiliary": np.zeros(532, complex), "plane_incident_projections": np.zeros(532, complex),
                  "plane_electric": np.zeros((532, 3), complex), "plane_magnetic": np.zeros((532, 3), complex),
                  "direct_plane_outgoing_power_diagnostic": np.zeros(532), "mode_local_amplitude_scale": np.ones(532),
                  "plane_electric_scale": np.ones(532), "plane_magnetic_scale": np.ones(532),
                  "mode_power_operation_scale": np.ones(532) * .5, "global_total_auxiliary": np.zeros(532, complex),
                  "global_incident_projections": np.zeros(532, complex)}
        arrays["global_total_auxiliary"][7] = .001
        read = mock.Mock(load=lambda key: arrays[key.removeprefix("control_")])
        identity_conversion = lambda values, *args: np.asarray(values, dtype=complex)
        with mock.patch("src.solvers.dtn_boundary_phase_gauge.global_amplitudes_from_solver", side_effect=identity_conversion), \
             mock.patch("src.solvers.dtn_boundary_phase_gauge.solver_amplitudes_from_global", side_effect=identity_conversion):
            with self.assertRaisesRegex(ValueError, "bound_global_total_auxiliary"):
                checker._outputs("control", False, field, np.zeros(532), read, read, checker._Checks(), inventory, generator)


class CandidateAdmissionContracts(unittest.TestCase):
    def test_admission_denial_precedes_numpy_load(self):
        descriptor = {"path": "array.npy", "payload_bytes": 16, "shape": [1], "dtype": "complex128", "file_sha256": "0" * 64}
        def denied(*args):
            raise MemoryError("whole-tree admission denied")
        read = checker._Candidate(".", {"artifacts": {"a": descriptor}}, denied)
        with mock.patch("numpy.load") as mapping:
            with self.assertRaisesRegex(MemoryError, "admission denied"):
                read.load("a")
            mapping.assert_not_called()

    def test_sparse_admission_precedes_all_buffer_loads(self):
        descriptors = {"s_" + k: {"payload_bytes": 16} for k in ("data", "indices", "indptr")}
        read = checker._Candidate(".", {"artifacts": descriptors}, mock.Mock(side_effect=MemoryError("sparse gate")))
        with mock.patch.object(read, "load") as arrays:
            with self.assertRaisesRegex(MemoryError, "sparse gate"):
                read.csr("s", (1, 1))
            arrays.assert_not_called()

    def test_hash_and_snapshot_hash_bind_the_readonly_mapping(self):
        import numpy as np
        events = []
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "a.npy"
            value = np.asarray([1 + 2j])
            np.save(path, value)
            descriptor = {"path": "a.npy", "payload_bytes": 16, "shape": [1], "dtype": "complex128",
                          "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            ref = {"name": "a", "sha256": checker._numeric_sha(value)}
            read = checker._Candidate(temporary, {"artifacts": {"a": descriptor}}, lambda *args: events.append(args))
            actual = read.load(ref)
            self.assertFalse(actual.flags.writeable)
            self.assertTrue(events[0][1]["before_array_open"])
            ref["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "numeric hash"):
                read.load(ref)

    def test_invalid_offsets_are_rejected_before_sparse_constructor(self):
        import numpy as np
        read = checker._Candidate(".", {"artifacts": {"s_" + k: {"payload_bytes": 16}
                                                       for k in ("data", "indices", "indptr")}}, lambda *args: None)
        values = [np.asarray([1 + 0j]), np.asarray([0], dtype=np.int32), np.asarray([0, 2], dtype=np.int32)]
        with mock.patch.object(read, "load", side_effect=values), mock.patch("scipy.sparse.csr_matrix") as constructor:
            with self.assertRaisesRegex(ValueError, "raw sparse buffers"):
                read.csr("s", (1, 1))
            constructor.assert_not_called()


if __name__ == "__main__":
    unittest.main()
