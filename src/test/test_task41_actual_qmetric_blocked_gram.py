from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

import src.solvers.task41_actual_qmetric_blocked_gram as qmetric

from src.solvers.task41_actual_qmetric_blocked_gram import (
    INTEGRAL_BODY_BY_TAG,
    FEATURE_NAMES,
    DIMENSION,
    PROFILE_TAGS,
    Task41ActualQMetricBlockedGramCandidate,
    _array_declaration_info,
    _cache_identity_digest,
    _checked_array_declaration,
    _feature_pair_map,
    _geometry_trace_fields,
    _geometry_snippet,
    _instrument_original_kernel_geometry_oracle,
    assemble_blocked_gram,
    compare_geometry_traces,
)


def test_feature_pair_map_is_recovered_from_frozen_scalar_products():
    tensor_source = []
    pair_index = 0
    for left in range(12):
        for right in range(12):
            tensor_source.append(
                f"temp_{pair_index}[j] = fw{pair_index} * {FEATURE_NAMES[right]}[0][0][iq][j];"
            )
            tensor_source.append(
                f"A[882 * (i) + (j)] += {FEATURE_NAMES[left]}[0][0][iq][i] * temp_{pair_index}[j];"
            )
            pair_index += 1
    pairs = _feature_pair_map("\n".join(tensor_source))
    assert pairs == tuple((left, right) for left in range(12) for right in range(12))


def test_geometry_copy_stays_inside_the_frozen_q_loop():
    declarations = "\n".join(f"  double fw{index} = {index}.0;" for index in range(144))
    body = (
        "for (int iq = 0; iq < 512; ++iq)\n{\n"
        + declarations
        + "\n  }\n  // ------------------------ \n  // ------------------------ \n"
        "// Section: Tensor Computation\n"
    )
    snippet = _geometry_snippet(body, "fixture")
    assert snippet.index("out[(iq - iq_begin) * 144 + 0] = fw0") > snippet.index(
        "for (int iq = iq_begin; iq < iq_end; ++iq)"
    )
    assert snippet.index("out[(iq - iq_begin) * 144 + 143] = fw143") < snippet.rindex(
        "  }"
    )


def test_frozen_table_extent_is_read_from_the_declaration_and_checked():
    declaration = "static const double FE0_C0_Q907[1][1][2][3] = {{{{1, 2, 3}, {4, 5, 6}}}};"
    text, shape = _array_declaration_info(declaration, "FE0_C0_Q907")
    assert shape == (1, 1, 2, 3)
    assert text.startswith("static const double FE0_C0_Q907")
    with pytest.raises(ValueError, match="extent"):
        _checked_array_declaration(declaration, "FE0_C0_Q907", (1, 1, 2, 4))


def test_cache_identity_changes_with_the_frozen_evaluator_source():
    payload = {"evaluator_source_sha256": "a" * 64, "table_sha256": "b" * 64}
    original = _cache_identity_digest(payload)
    payload["evaluator_source_sha256"] = "c" * 64
    assert _cache_identity_digest(payload) != original


def _original_kernel_geometry_fixture() -> tuple[str, str]:
    digest = INTEGRAL_BODY_BY_TAG[1]
    function_name = f"tabulate_tensor_integral_{digest}_hexahedron"
    declarations = [f"  double J0_c{index} = {index}.0;" for index in range(9)]
    declarations.extend(
        f"  double sv_907_{index} = {index}.0;"
        for index in (17, 18, 22, 23, 39, 44, 49, 75, 80, 85)
    )
    declarations.extend(
        f"  double _Complex fw{index} = {index}.0;" for index in range(144)
    )
    body = (
        f"void {function_name}(double _Complex* restrict A, "
        "const double _Complex* restrict w, const double _Complex* restrict c, "
        "const double* restrict coordinate_dofs, const int* restrict entity_local_index, "
        "const uint8_t* restrict quadrature_permutation, void* custom_data)\n{\n"
        "for (int iq = 0; iq < 512; ++iq)\n{\n"
        + "\n".join(declarations)
        + "\n  }\n  // ------------------------\n  // ------------------------\n"
        "// Section: Tensor Computation\n  A[0] += fw0;\n}\n"
    )
    return body, digest


def test_instrumented_oracle_clone_preserves_the_original_tensor_kernel():
    body, digest = _original_kernel_geometry_fixture()
    source, fields, clone_name = _instrument_original_kernel_geometry_oracle(body, digest)
    assert clone_name in source
    assert "// Section: Tensor Computation\n  A[0] += fw0;" in source
    assert "int oracle_q_begin, int oracle_q_end" in source
    assert "if (oracle_q_begin < 0 || oracle_q_end > 512" in source
    assert f"oracle_out[(iq - oracle_q_begin) * {len(fields)} + 0] = J0_c0" in source
    assert f"oracle_out[(iq - oracle_q_begin) * {len(fields)} + {fields.index('fw143')}] = fw143" in source
    assert "oracle_out" not in body


def test_geometry_trace_comparison_reports_bitwise_and_mismatched_fields():
    body, digest = _original_kernel_geometry_fixture()
    geometry = body[body.index("for (int iq") : body.index("// Section: Tensor Computation")]
    fields = _geometry_trace_fields(geometry, digest)
    values = np.arange(2 * len(fields), dtype=np.float64).reshape((2, len(fields)))
    exact = compare_geometry_traces(values, values.copy(), fields)
    assert exact["status"] == "BITWISE_EQUAL"
    changed = values.astype(np.complex128)
    changed[1, fields.index("sv_907_17")] += 1.0e-15j
    mismatch = compare_geometry_traces(values, changed, fields)
    assert mismatch["status"] == "MISMATCH"
    assert mismatch["max_field"] == "sv_907_17"


def test_blocked_gram_matches_ordered_scalar_oracle_without_hermitian_projection():
    features = np.arange(72, dtype=np.float64).reshape((2, 12, 3)) / 7.0 - 2.0
    qmetric = np.arange(288, dtype=np.float64).reshape((2, 12, 12)) / 13.0
    qmetric = qmetric.astype(np.complex128) * (1.0 + 0.3j)
    qmetric[:, 0, 1] += 0.75 - 0.2j
    pairs = tuple((left, right) for left in range(12) for right in range(12))
    expected = np.zeros((3, 3), dtype=np.complex128)
    for point in range(features.shape[0]):
        for left in range(12):
            for right in range(12):
                expected += qmetric[point, left, right] * np.outer(
                    features[point, left], features[point, right]
                )
    actual = assemble_blocked_gram(qmetric, features, pairs)
    np.testing.assert_allclose(actual, expected, rtol=2e-15, atol=2e-15)
    assert np.linalg.norm(actual - actual.conjugate().T) > 1.0


def test_original_kernel_oracle_gates_before_reading_frozen_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "libffcx.c"
    source_bytes = b"small frozen source fixture"
    source_path.write_bytes(source_bytes)
    metadata_path = tmp_path / "libffcx.c.cached"
    metadata_bytes = b"gcc -pthread -c libffcx.c -o libffcx.o\n"
    metadata_path.write_bytes(metadata_bytes)
    monkeypatch.setattr(qmetric, "EXPECTED_C_SOURCE_BYTES", len(source_bytes))
    monkeypatch.setattr(
        qmetric, "EXPECTED_C_SOURCE_SHA256", hashlib.sha256(source_bytes).hexdigest()
    )
    monkeypatch.setattr(
        qmetric, "EXPECTED_C_CACHE_SHA256", hashlib.sha256(metadata_bytes).hexdigest()
    )
    monkeypatch.setattr(
        qmetric, "_integral_body", lambda _source, _digest: "frozen body fixture"
    )
    monkeypatch.setattr(
        qmetric,
        "_instrument_original_kernel_geometry_oracle",
        lambda _body, digest: (
            "// Section: Tensor Computation\n",
            ("J0_c0",),
            f"oracle_{digest[:8]}",
        ),
    )
    monkeypatch.setattr(qmetric.shutil, "which", lambda _compiler: "/usr/bin/gcc")
    helper = object.__new__(qmetric._FrozenFFCxGeometryHelper)
    helper.source_path = source_path
    helper.cache_metadata_path = metadata_path
    helper.source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    helper.helper_source_bytes = 8
    helper.helper_library_bytes = 16
    helper.static_table_shapes = {"FE2_fixture": (1,), "weights_907": (qmetric.POINT_COUNT,)}
    gate_called = False
    original_read_bytes = Path.read_bytes

    def observe_read(path: Path) -> bytes:
        if path == source_path:
            assert gate_called, "large frozen source was read before resource admission"
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", observe_read)

    def allocation_gate(label: str, facts: dict[str, object]) -> None:
        nonlocal gate_called
        assert label == "task41_v6_original_kernel_oracle_compile"
        assert facts["workspace_bytes"] == 1024**3
        assert facts["scratch_bytes_upper"] == 512 * 1024**2
        gate_called = True

    result = helper.original_kernel_oracle_source(
        1, allocation_gate=allocation_gate
    )
    assert gate_called
    assert result["source_bytes"] == len(result["source"].encode("ascii"))
    assert result["execution_status"] == "NOT_RUN_NO_WINDOW_APPROVAL"


def test_original_kernel_oracle_entry_compares_full_tensor_and_records_timings() -> None:
    tag = min(PROFILE_TAGS)
    coordinates = np.zeros((8, 3), dtype=np.float64)
    tensor = np.zeros((DIMENSION, DIMENSION), dtype=np.complex128)

    class Helper:
        geometry_trace_fields = ("J0_c0",)

        def run_original_kernel_geometry_oracle(
            self, _tag, _coordinates, _start, _stop, *, allocation_gate
        ):
            return {
                "tensor": tensor.copy(),
                "geometry_trace": np.zeros((1, 1), dtype=np.complex128),
                "execution_status": "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE",
                "kernel_call_seconds": 0.25,
                "output_allocation_seconds": 0.01,
                "compile_audit": {
                    "source_generation_seconds": 0.03,
                    "compiler_seconds": 0.15,
                },
            }

    candidate = object.__new__(Task41ActualQMetricBlockedGramCandidate)
    candidate._prepared = True
    candidate._helper = Helper()
    candidate.key_workspace_bytes_upper = 4096
    candidate.cache_identity = "frozen-cache-identity"
    candidate.geometry_oracle_comparison_records = []
    candidate.original_kernel_oracle_records = []
    candidate._oracle_failed_tags = set()
    candidate._pending_oracle_tensor = None
    candidate.compare_original_kernel_geometry = (
        lambda observed_tag, _coords, q_begin, q_end, _trace: {
            "tag": observed_tag,
            "q_begin": q_begin,
            "q_end": q_end,
            "status": "BITWISE_EQUAL",
        }
    )
    candidate.build = lambda _coords, *, tag, dimension: tensor.copy()
    gates = []

    def allocation_gate(label, facts):
        gates.append((label, facts))

    result = candidate.run_original_kernel_geometry_oracle(
        tag, coordinates, 0, 1, allocation_gate=allocation_gate
    )
    assert result["tensor_comparison"]["status"] == "PASS_SCREEN"
    assert result["candidate_tensor"].shape == (DIMENSION, DIMENSION)
    assert candidate.original_kernel_oracle_records[0]["kernel_call_seconds"] == 0.25
    assert candidate.original_kernel_oracle_records[0]["candidate_build_seconds"] >= 0.0
    assert tag not in candidate._oracle_failed_tags
    assert candidate._pending_oracle_tensor is not None
    assert gates[-1][0] == "task41_v6_actual_qmetric_tensor_comparison"
    assert gates[-1][1]["workspace_bytes"] == 4096 + 2 * DIMENSION * DIMENSION * 16


def test_oracle_pass_reuses_the_production_build_without_marking_it_failed() -> None:
    tag = min(PROFILE_TAGS)
    coordinates = np.zeros((8, 3), dtype=np.float64)
    candidate_tensor = np.zeros((DIMENSION, DIMENSION), dtype=np.complex128)

    class Helper:
        geometry_trace_fields = ("J0_c0",)

        def run_original_kernel_geometry_oracle(
            self, _tag, _coordinates, _start, _stop, *, allocation_gate
        ):
            return {
                "tensor": candidate_tensor.copy(),
                "geometry_trace": np.zeros((1, 1), dtype=np.complex128),
                "execution_status": "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE",
                "kernel_call_seconds": 0.25,
                "output_allocation_seconds": 0.01,
                "compile_audit": {
                    "source_generation_seconds": 0.03,
                    "compiler_seconds": 0.15,
                },
            }

    candidate = object.__new__(Task41ActualQMetricBlockedGramCandidate)
    candidate._prepared = True
    candidate._helper = Helper()
    candidate.key_workspace_bytes_upper = 4096
    candidate.cache_identity = "frozen-cache-identity"
    candidate.geometry_oracle_comparison_records = []
    candidate.original_kernel_oracle_records = []
    candidate._oracle_failed_tags = set()
    candidate._pending_oracle_tensor = None
    candidate.compare_original_kernel_geometry = (
        lambda observed_tag, _coords, q_begin, q_end, _trace: {
            "tag": observed_tag,
            "q_begin": q_begin,
            "q_end": q_end,
            "status": "BITWISE_EQUAL",
        }
    )

    def unexpected_duplicate_build(*_args, **_kwargs):
        raise AssertionError("the prefix oracle must reuse the already-built candidate tensor")

    candidate.build = unexpected_duplicate_build
    result = candidate.run_original_kernel_geometry_oracle(
        tag,
        coordinates,
        0,
        1,
        allocation_gate=lambda *_args, **_kwargs: None,
        candidate_tensor=candidate_tensor,
        candidate_build_seconds=0.125,
    )
    assert result["candidate_tensor"] is candidate_tensor
    assert candidate.original_kernel_oracle_records[0]["candidate_build_seconds"] == 0.125
    assert tag not in candidate._oracle_failed_tags
    assert candidate._pending_oracle_tensor is None


def test_oracle_candidate_tensor_is_consumed_once_by_the_exact_builder() -> None:
    coordinates = np.arange(24, dtype=np.float64).reshape((8, 3))
    tensor = np.ones((DIMENSION, DIMENSION), dtype=np.complex128)
    candidate = object.__new__(Task41ActualQMetricBlockedGramCandidate)
    candidate._oracle_failed_tags = set()
    candidate._pending_oracle_tensor = (1, coordinates.tobytes(), tensor)
    actual = candidate.build(coordinates, tag=1, dimension=DIMENSION)
    assert actual is tensor
    assert candidate._pending_oracle_tensor is None
