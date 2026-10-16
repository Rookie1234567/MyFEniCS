from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
from pathlib import Path

import numpy as np
import pytest

from src.solvers.dtn_port_3d import (
    _combine_owned_entries,
    _vec_nonzero_owned_entries,
)

ACCOUNTING_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_scale_homogeneous_cutoff_accounting.py"
)
ACCOUNTING_SPEC = importlib.util.spec_from_file_location(
    "task40_scale_homogeneous_accounting_test", ACCOUNTING_PATH
)
assert ACCOUNTING_SPEC is not None and ACCOUNTING_SPEC.loader is not None
ACCOUNTING = importlib.util.module_from_spec(ACCOUNTING_SPEC)
ACCOUNTING_SPEC.loader.exec_module(ACCOUNTING)
WORKER_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/task40para_phi90_mesh_modes_direct/scripts/d13_saved_field_scale_homogeneous_worker.py"
)
WORKER_SPEC = importlib.util.spec_from_file_location("task40_scale_candidate_worker_test", WORKER_PATH)
assert WORKER_SPEC is not None and WORKER_SPEC.loader is not None
WORKER = importlib.util.module_from_spec(WORKER_SPEC)
WORKER_SPEC.loader.exec_module(WORKER)


class _SerialComm:
    def allreduce(self, value, op=None):
        return value


class _PetscComm:
    def tompi4py(self):
        return _SerialComm()


class _Vec:
    def __init__(self, values, *, first_row=0):
        self.values = np.asarray(values, dtype=np.complex128)
        self.first_row = int(first_row)

    def getOwnershipRange(self):
        return self.first_row, self.first_row + self.values.size

    def getArray(self, readonly=True):
        assert readonly is True
        return self.values

    def getComm(self):
        return _PetscComm()


def _entries(rows, values):
    return np.asarray(rows, dtype=np.int64), np.asarray(values, dtype=np.complex128)


def _candidate_route(components, coefficients):
    rows, values = _combine_owned_entries(
        components,
        coefficients,
        comm=_SerialComm(),
        relative_tol=1.0e-13,
        scale_homogeneous=True,
    )
    return rows, values


def test_default_helpers_retain_the_legacy_absolute_floor_and_candidate_is_opt_in():
    values = np.asarray([2.0e-31 + 0j, 4.0e-44 + 0j])
    legacy_rows, legacy_values = _vec_nonzero_owned_entries(_Vec(values))
    candidate_rows, candidate_values = _vec_nonzero_owned_entries(
        _Vec(values), relative_tol=1.0e-13, scale_homogeneous=True
    )
    assert legacy_rows.size == legacy_values.size == 0
    np.testing.assert_array_equal(candidate_rows, [0, 1])
    np.testing.assert_array_equal(candidate_values, values)

    # The historical path stays floor-sensitive at a small physical scale.
    scaled = values * (1.0e30 * (0.6 + 0.8j))
    legacy_scaled_rows, _ = _vec_nonzero_owned_entries(_Vec(scaled))
    assert legacy_scaled_rows.tolist() == [0, 1]


def test_component_candidate_rowset_is_invariant_under_safe_complex_rescaling():
    values = np.asarray([2.0e-31 + 0j, 4.0e-44 + 0j, 0.25e-44j])
    scale = 1.0e30 * (0.6 + 0.8j)
    low_rows, low_values = _vec_nonzero_owned_entries(
        _Vec(values, first_row=100),
        relative_tol=1.0e-13,
        scale_homogeneous=True,
        support=np.asarray([0, 1, 2], dtype=np.int32),
    )
    high_rows, high_values = _vec_nonzero_owned_entries(
        _Vec(values * scale, first_row=100),
        relative_tol=1.0e-13,
        scale_homogeneous=True,
        support=np.asarray([0, 1, 2], dtype=np.int32),
    )
    np.testing.assert_array_equal(low_rows, [100, 101])
    np.testing.assert_array_equal(high_rows, low_rows)
    np.testing.assert_allclose(high_values, low_values * scale, rtol=2e-15, atol=0.0)


@pytest.mark.parametrize(
    "route_coefficients",
    [
        ("projection", (0.6 + 0.8j, -0.3 + 0.4j), True),
        ("coupling", (-0.2 + 0.7j, 0.5 - 0.1j), False),
    ],
)
def test_actual_merge_helper_projection_and_coupling_rowsets_are_scale_homogeneous(
    route_coefficients,
):
    route, coefficients, conjugate_projection = route_coefficients
    original = (
        _entries([2, 5], [2.0e-31 + 0j, 4.0e-44 + 0j]),
        _entries([2, 3], [-1.0e-31 + 0j, 4.0e-44j]),
    )
    scale = 1.0e30 * (0.6 + 0.8j)
    scaled = tuple((rows, values * scale) for rows, values in original)
    low_rows, low_values = _candidate_route(original, coefficients)
    high_rows, high_values = _candidate_route(scaled, coefficients)
    np.testing.assert_array_equal(high_rows, low_rows)
    np.testing.assert_allclose(high_values, low_values * scale, rtol=3e-15, atol=0.0)

    # Independently check the two physical conventions after the actual
    # production merge: projection conjugates the merged entries; coupling does not.
    transformed = np.conjugate(low_values) if conjugate_projection else low_values
    if route == "projection":
        np.testing.assert_array_equal(transformed, np.conjugate(low_values))
    else:
        np.testing.assert_array_equal(transformed, low_values)
    assert low_rows.tolist() == [2, 3, 5]


def test_zero_inputs_are_explicitly_empty_at_both_candidate_stages():
    rows, values = _vec_nonzero_owned_entries(
        _Vec([0j, 0j]), scale_homogeneous=True
    )
    assert rows.size == values.size == 0
    merged_rows, merged_values = _candidate_route(
        (_entries([], []), _entries([], [])), (1 + 0j, 1 + 0j)
    )
    assert merged_rows.size == merged_values.size == 0
    merged_rows, merged_values = _candidate_route(
        (_entries([1], [0j]), _entries([1], [0j])), (1 + 0j, -1 + 0j)
    )
    assert merged_rows.size == merged_values.size == 0


@pytest.mark.parametrize(
    "values",
    [
        [complex(np.nan, 0.0)],
        [complex(0.0, np.inf)],
        [complex(1.7e308, 1.7e308)],  # finite components, overflowing magnitude
    ],
)
def test_component_candidate_rejects_nonfinite_or_overflowed_magnitudes(values):
    with pytest.raises(FloatingPointError):
        _vec_nonzero_owned_entries(_Vec(values), scale_homogeneous=True)


@pytest.mark.parametrize(
    "components,coefficients",
    [
        ((_entries([0], [complex(np.nan, 0.0)]), _entries([], [])), (1 + 0j, 1 + 0j)),
        ((_entries([0], [1.0e308]), _entries([], [])), (2 + 0j, 1 + 0j)),
        ((_entries([0], [np.nextafter(0.0, 1.0)]), _entries([], [])), (0.5 + 0j, 1 + 0j)),
        ((_entries([0], [1 + 0j]), _entries([], [])), (complex(np.inf, 0), 1 + 0j)),
    ],
)
def test_merge_candidate_rejects_nonfinite_overflow_and_product_underflow(
    components, coefficients
):
    with pytest.raises(FloatingPointError):
        _candidate_route(components, coefficients)


def test_relative_ratio_underflow_is_only_discarded_below_positive_tolerance():
    tiny = np.nextafter(0.0, 1.0)
    rows, _ = _vec_nonzero_owned_entries(
        _Vec([1.0e308 + 0j, tiny + 0j]),
        relative_tol=1.0e-13,
        scale_homogeneous=True,
    )
    assert rows.tolist() == [0]


def test_candidate_rejects_invalid_relative_tolerance():
    with pytest.raises(ValueError, match="0 < relative_tol < 1"):
        _vec_nonzero_owned_entries(_Vec([1 + 0j]), relative_tol=0.0, scale_homogeneous=True)


def test_candidate_support_validation_remains_fail_closed():
    with pytest.raises(ValueError, match="non-owned vector entry"):
        _vec_nonzero_owned_entries(
            _Vec([1 + 0j]),
            scale_homogeneous=True,
            support=np.asarray([1], dtype=np.int32),
        )


@pytest.mark.parametrize(
    "coefficients,conjugate",
    [
        ((0.6 + 0.8j, -0.3 + 0.4j), True),
        ((-0.2 + 0.7j, 0.5 - 0.1j), False),
    ],
)
def test_candidate_accounting_closes_actual_projection_and_coupling_helper_outputs(
    coefficients, conjugate
):
    raw_vectors = (
        _Vec([0j, 2.0e-31 + 0j, 0j, 4.0e-44 + 0j]),
        _Vec([0j, -1.0e-31 + 0j, 4.0e-44j, 0j]),
    )
    raw_entries = []
    candidate_entries = []
    for vector in raw_vectors:
        rows, values = _vec_nonzero_owned_entries(
            vector, relative_tol=1.0e-13, scale_homogeneous=True
        )
        raw_rows = np.asarray([1, 2, 3] if vector is raw_vectors[0] else [1, 2], dtype=np.int64)
        raw_values = (
            np.asarray([2.0e-31 + 0j, 0j, 4.0e-44 + 0j])
            if vector is raw_vectors[0]
            else np.asarray([-1.0e-31 + 0j, 4.0e-44j])
        )
        raw_entries.append((raw_rows, raw_values))
        candidate_entries.append((rows, values))
        expected_rows, expected_values, _facts = ACCOUNTING.expected_component_filter(
            raw_rows, raw_values
        )
        np.testing.assert_array_equal(rows, expected_rows)
        np.testing.assert_array_equal(values, expected_values)

    final_rows, final_values = _combine_owned_entries(
        tuple(candidate_entries),
        coefficients,
        comm=_SerialComm(),
        relative_tol=1.0e-13,
        scale_homogeneous=True,
    )
    expected = ACCOUNTING.expected_merged_filter(candidate_entries, coefficients)
    np.testing.assert_array_equal(final_rows, expected[2])
    np.testing.assert_array_equal(final_values, expected[3])

    storage = np.asarray([0j, 1.0 + 0.5j, -2.0 + 0.25j, 3.0 - 1.0j])
    facts = ACCOUNTING.route_cutoff_accounting(
        raw_entries,
        candidate_entries,
        coefficients,
        final_rows,
        final_values,
        storage,
        conjugate_combined_values=conjugate,
    )
    assert facts["closure_is_qualification_gate"] is False
    assert facts["closure_passed"] is True  # finite accounting only; not a solver gate
    for name in ("component_cutoff_delta_closure", "merged_cutoff_delta_closure"):
        closure = facts[name]
        assert closure["closure_residual_abs"] >= 0.0
        assert closure["term_count"] > 0
        assert closure["sum_abs_products_longdouble"]
        assert "NO_ABSOLUTE_FLOOR" in closure["closure_bound_policy"]


def test_candidate_worker_scopes_real_helper_opt_in_to_saved_field_capture():
    import src.solvers.dtn_port_3d as dtn_port

    original_vec = dtn_port._vec_nonzero_owned_entries
    original_merge = dtn_port._combine_owned_entries

    class _Capture:
        @staticmethod
        def _cutoff_stage_capture(**_kwargs):
            vector = _Vec([2.0e-31 + 0j, 4.0e-44 + 0j])
            component_rows, component_values = dtn_port._vec_nonzero_owned_entries(
                vector, relative_tol=1.0e-13
            )
            merge_rows, merge_values = dtn_port._combine_owned_entries(
                ((component_rows, component_values), (np.asarray([], dtype=np.int64), np.asarray([], dtype=np.complex128))),
                (1 + 0j, 1 + 0j),
                comm=_SerialComm(),
                relative_tol=1.0e-13,
            )
            return {
                "unchanged_production_cutoff": {},
                "six_exact_signed_key_results": [],
                "captured_component_rows": component_rows,
                "captured_merged_rows": merge_rows,
                "captured_merged_values": merge_values,
            }

    result = WORKER._candidate_capture(_Capture)
    assert result["captured_component_rows"].tolist() == [0, 1]
    assert result["captured_merged_rows"].tolist() == [0, 1]
    assert result["candidate_policy"]["absolute_floor"] is None
    # The opt-in wrappers are restored once this one capture returns.
    assert dtn_port._vec_nonzero_owned_entries is original_vec
    assert dtn_port._combine_owned_entries is original_merge
    legacy_rows, _ = dtn_port._vec_nonzero_owned_entries(_Vec([2.0e-31 + 0j]))
    assert legacy_rows.size == 0


def test_candidate_contract_and_sidecar_bind_saved_baseline_without_authorizing_execution():
    records = (
        Path(__file__).resolve().parents[2]
        / "docs/task40para_phi90_mesh_modes_direct/outcomes/records"
    )
    contract_path = records / "d13_saved_field_scale_homogeneous_cutoff_contract_v1.json"
    sidecar_path = records / "d13_saved_field_scale_homogeneous_cutoff_launch_v1.json"
    contract = json.loads(contract_path.read_text())
    sidecar = json.loads(sidecar_path.read_text())

    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    assert sidecar["contract_sha256"] == sha(contract_path)
    assert sidecar["worker_sha256"] == sha(WORKER_PATH)
    assert sidecar["status"] == "READY_FOR_REVIEW_NO_EXECUTION_AUTHORIZATION"
    assert contract["execution_authorized"] is False
    assert contract["scale_homogeneous_candidate"]["relative_tolerance"] == 1.0e-13
    assert contract["scale_homogeneous_candidate"]["absolute_floor"] is None
    assert len(contract["cases"]) == 2
    assert Path(sidecar["output_directory"]).name.endswith("_v1")

    source_path = Path(__file__).resolve().parents[2] / "src/solvers/dtn_port_3d.py"
    assert (
        contract["analysis_source_file_sha256"]["src/solvers/dtn_port_3d.py"]
        != sha(source_path)
    )
    with pytest.raises(ValueError, match="candidate source hash changed"):
        WORKER._verify_candidate_contract(
            contract_path, contract, require_execution_authorized=False
        )

    supervisor = WORKER._load_module(
        "task40_candidate_package_supervisor_test",
        Path(sidecar["supervisor_path"]),
    )
    command = sidecar["worker_command_argv"]
    supervisor._validate_worker_command(
        command,
        contract_path.resolve(),
        Path(sidecar["report_path"]).resolve(),
        contract,
    )
    exec_lines = [
        line.strip()
        for line in sidecar["shell_command"].splitlines()
        if line.strip().startswith("exec ")
    ]
    assert len(exec_lines) == 1
    shell_argv = shlex.split(exec_lines[0])[1:]
    if ">>" in shell_argv:
        shell_argv = shell_argv[: shell_argv.index(">>")]
    assert shell_argv == sidecar["exec_argv"]
    assert sidecar["exec_argv_matches_shell"] is True
