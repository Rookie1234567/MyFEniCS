"""Pure numerical/schema regression tests; never create FE or JIT objects."""
import copy
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace

import numpy as np

import run_boundary_support_pilot as runner
import launch_boundary_support_pilot as launch
import check_saved_boundary_pilot as saved


def inventory():
    modes = [SimpleNamespace(side=side, m=m, n=n, polarization=polar,
        alpha=complex(m), gamma=complex(n), k_vector=np.array([m, n, 2+.1j]))
        for side in ("top", "bottom") for m, n in runner.PAIRS for polar in ("s", "p")]
    modes.extend(SimpleNamespace(side="top", m=1000+j, n=0, polarization="s", alpha=complex(j),
        gamma=0j, k_vector=np.array([j, 0, 2+.1j])) for j in range(32060-len(modes)))
    return modes


class RunnerTests(unittest.TestCase):
    def test_exact_selected_keys_and_full_phase_metadata(self):
        modes = inventory()
        self.assertEqual(runner.selected_indices(modes), tuple(range(12)))
        metadata = runner.inventory_phase_identity(modes)
        self.assertEqual(metadata["mode_count"], 32060)
        self.assertFalse(metadata["finite_exp_modulus_certified_by_this_metadata"])
        modes[19000].alpha = 1+1e-300j
        with self.assertRaises(ValueError):
            runner.inventory_phase_identity(modes)

    def test_missing_swapped_duplicate_keys_rejected(self):
        for change in (lambda m: m.pop(), lambda m: setattr(m[4], "polarization", "wrong"),
                       lambda m: m.__setitem__(1, m[0])):
            modes = inventory(); change(modes)
            with self.assertRaises(ValueError):
                runner.selected_indices(modes)

    def test_Cdual_Dfunctional_conventions_and_conjugation_negative(self):
        n = runner.NATIVE_ROWS
        states = np.zeros((n, 3), np.complex128)
        states[:2] = [[1+2j, -2+.3j, .4-1j], [-.7j, 3-1j, .1+.6j]]
        components = np.zeros((12, 2, n), np.complex128)
        components[:, :, :2] = [[.4+.8j, -.9+.2j], [1.2-.4j, .1+.7j]]
        ccoef, ecoef = np.array([.4-.3j, -1+.2j]), np.array([.1+.6j, -.8-.2j])
        C = ccoef[0]*components[:, 0]+ccoef[1]*components[:, 1]
        D = np.conjugate(ecoef[0]*components[:, 0]+ecoef[1]*components[:, 1])
        actual = runner.actions(states, components, C, D)
        wanted_c = np.einsum("j,ijk->ik", ccoef, actual["component_actions"])
        wanted_d = np.conjugate(np.einsum("j,ijk->ik", ecoef, actual["component_actions"]))
        np.testing.assert_allclose(actual["Cdual_actions"], wanted_c, rtol=1e-14, atol=0)
        np.testing.assert_allclose(actual["Dfunctional_actions"], wanted_d, rtol=1e-14, atol=0)
        self.assertGreater(np.max(np.abs(actual["Dfunctional_actions"]-np.conjugate(wanted_d))), .1)
        states[0, 0] = np.nan
        with self.assertRaises(ValueError):
            runner.actions(states, components, C, D)

    def test_save_admission_schema_is_complete_and_denial_precedes_write(self):
        base = launch.inherited()
        events = []
        def deny(label, facts):
            events.append(base.allocation_bytes(facts)); raise MemoryError("synthetic denial")
        class NoWriter:
            def _save_array(self, *args):
                raise AssertionError("write happened before admission")
        with self.assertRaises(MemoryError):
            runner.save_arrays(NoWriter(), Path("/definitely_absent_readonly_synthetic"), "test",
                               {"value": np.ones(3)}, deny, lambda x: None, 5)
        self.assertEqual(events, [5+2*24+(1 << 20)])


class LauncherTests(unittest.TestCase):
    def valid_record(self):
        pins = {name: {"path": name, "sha256": name} for name in ("runner", "helper", "reference")}
        record = {"status": "BOUNDARY_SUPPORT_PILOT_COMPLETE", "pilot_passed": True, "selected_only": True,
            "allmode_qualification": False, "full_C_D_allmode_qualification": False,
            "carrier_volume_factor_PDE_calls": 0, "physical_manifest_sha256": "manifest",
            "ordered_keys_sha256": "keys", "config_sha256": "cfg", "actual_sources": pins,
            "mechanism_forms": 4, "actual_native_rows": 13224, "mechanism_gate_passed": True,
            "selected_original_mode_indices": list(range(12)),
            "compiled_mechanism": [{"side": side, "axis": axis, "rule_match": {"passed": True},
                "identity": {"loaded_kernel": {"restoration_exact": True, "num_constants": 3,
                    "constant_roles": [{"role": role} for role in ("alpha", "gamma", "kz")],
                    "numerical_assembly_during_probe": False}, "rules": [{"degree": 27, "points": {"shape": [196, 2]},
                    "weights": {"shape": [196]}, "compiled_weight_tables_verified": 1}]}}
                    for side in ("top", "bottom") for axis in (0, 1)],
            "reference_record": {"reference_convergence_pass": True, "operation_rtol": 1e-10,
                "primary_degree": 160, "actual_facet_count": 12, "distinct_side_phase_groups": 6,
                "FE_JIT_PDE_creation_calls": 0, "no_numerical_denominator_floor": True,
                "selected_indices": list(range(12)), "rules": [{"degree": degree, "actual_nodes_per_facet": nodes,
                    "actual_geometric_points": 12*nodes, "state_side_component_nonzero": [[[True]*3]*2]*2}
                    for degree, nodes in ((168, 7225), (176, 7921))], "state_identity": {"slave_slots_zero": True,
                    "constraint_equations_checked": 3, "master_state_sha256": "state", "global_numbering_sha256": "numbers",
                    "cell_dof_order_sha256": "dofs"}},
            "mechanism_comparisons": [{"index": index, "axis": axis, "passed": True}
                                     for index in range(12) for axis in (0, 1)],
            "reference_checks": {name: {"passed": True} for name in ("component", "Cdual", "Dfunctional",
                "component_convergence", "Cdual_convergence", "Dfunctional_convergence")}}
        packet = {"original_physical_manifest_sha256": "manifest", "ordered_keys_sha256": "keys", "config_sha256": "cfg"}
        return record, packet, {"pilot_sources": pins}

    def test_actual_schema_and_missing_control_fail(self):
        base = launch.inherited(); record, packet, code = self.valid_record()
        launch.verify_record(base, record, packet, code)
        for mutate in (lambda r: r["mechanism_comparisons"].pop(),
                       lambda r: r["mechanism_comparisons"].__setitem__(1, r["mechanism_comparisons"][0]),
                       lambda r: r["reference_checks"].pop("Dfunctional_convergence"),
                       lambda r: r.__setitem__("carrier_volume_factor_PDE_calls", 1),
                       lambda r: r.__setitem__("allmode_qualification", True),
                       lambda r: r["compiled_mechanism"][0]["identity"]["loaded_kernel"].__setitem__("restoration_exact", False),
                       lambda r: r["reference_record"]["rules"][1].__setitem__("actual_nodes_per_facet", 6561),
                       lambda r: r["actual_sources"]["helper"].__setitem__("sha256", "wrong")):
            record, packet, code = self.valid_record(); code = copy.deepcopy(code); mutate(record)
            with self.assertRaises(ValueError):
                launch.verify_record(base, record, packet, code)

    def test_inherited_summary_rejects_controlled_stop(self):
        base = launch.inherited()
        with self.assertRaises(ValueError):
            base.require_summary({"status": "RESOURCE_CONTROLLED_STOP"}, {}, launch.WALL)
        self.assertEqual(launch.WALL, 600)
        self.assertEqual(base.CAP, 3 << 30)
        self.assertEqual(base.RESERVE, 128 << 20)


class SavedReaderTests(unittest.TestCase):
    def write(self, root, value):
        path = root/"actual.npy"; np.save(path, value)
        return {"path": str(path), "bytes": path.stat().st_size, "sha256": saved.sha256(path),
                "shape": list(value.shape), "dtype": str(value.dtype)}

    def test_literal_file_header_hash_roundtrip_and_preload_denial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = np.array([[1+2j, -.5j], [3-.2j, 4]], np.complex128)
            descriptor = self.write(root, value); requests = []
            actual = saved.load_array(descriptor, root, lambda label, facts: requests.append(facts))
            np.testing.assert_array_equal(actual, value)
            self.assertEqual(launch.inherited().allocation_bytes(requests[0]), value.nbytes+(1 << 20))
            def deny(*args):
                raise MemoryError("preload denial")
            with self.assertRaises(MemoryError):
                saved.load_array(descriptor, root, deny)

    def test_corrupt_truncated_object_and_foreign_evidence_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); value = np.ones(3, np.float64)
            descriptor = self.write(root, value); path = Path(descriptor["path"])
            data = bytearray(path.read_bytes()); data[-1] ^= 1; path.write_bytes(data)
            with self.assertRaises(ValueError):
                saved.load_array(descriptor, root, lambda *args: True)
            descriptor = self.write(root, value); path.write_bytes(path.read_bytes()[:-1])
            descriptor.update(bytes=path.stat().st_size, sha256=saved.sha256(path))
            with self.assertRaises(ValueError):
                saved.load_array(descriptor, root, lambda *args: True)
            descriptor = self.write(root, np.array(["synthetic"], object))
            with self.assertRaises(ValueError):
                saved.load_array(descriptor, root, lambda *args: True)
            descriptor = self.write(root, value)
            with self.assertRaises(ValueError):
                saved.load_array(descriptor, root/"unrelated", lambda *args: True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
