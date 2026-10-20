"""Profile-scoped, unqualified actual-geometry p6 q-metric evaluator.

This is deliberately tied to one frozen FFCx C source and one form signature.
It extracts only that source's pointwise geometry block and immutable FE0
reference tables.  It does not rewrite arbitrary FFCx kernels.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from time import perf_counter
from typing import Any, Callable, Mapping, Sequence

import numpy as np


IDENTITY = "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
QUALIFICATION_STATUS = "UNQUALIFIED_PENDING_BOUNDED_FFCX_ORACLE"
MAX_GEOMETRY_ORACLE_COMPARISONS = 6
V6_PREFIX_SAMPLE_CELL_INDICES = (26762, 26897, 0, 1, 2, 5, 6, 7505)
V6_PREFIX_QUALIFICATION_SCHEMA = "task41.p0.v6.actual_qmetric_prefix_qualification.v1"
EXPECTED_C_SOURCE_SHA256 = "d3302fba22074b755ac3b7d4a0b361af926ae7801aac25a7f1cd1d69cbeb9f03"
EXPECTED_C_CACHE_SHA256 = "6d251ab5b31faa9ea4e49c7ceb6eb6a44f4b547c9f3df01dd470161d79dc0cb2"
EXPECTED_UFCX_MODULE_SHA256 = "a6c6105ed735a28434e891f151f34e29fddbf22f9a3f3faddc99225a886d6882"
EXPECTED_UFCX_SIGNATURE = (
    "8d775db8d89c8233c332362d1087cdce53b24c2adeadcd395303c01f6a4a1dadd"
    "136226572864fbcd101a6504d8c94343880eddfde21e493f5e61e7a5757dd8e"
)
EXPECTED_C_SOURCE_BYTES = 108_832_231
DIMENSION = 882
POINT_COUNT = 512
POINT_BLOCK_SIZE = 32
FEATURE_NAMES = (
    "FE0_C0_Q907",
    "FE0_C0_D100_Q907",
    "FE0_C0_D010_Q907",
    "FE0_C0_D001_Q907",
    "FE0_C1_Q907",
    "FE0_C1_D100_Q907",
    "FE0_C1_D010_Q907",
    "FE0_C1_D001_Q907",
    "FE0_C2_Q907",
    "FE0_C2_D100_Q907",
    "FE0_C2_D010_Q907",
    "FE0_C2_D001_Q907",
)
FEATURE_COMPONENT_DERIVATIVE = (
    (0, (0, 0, 0)),
    (0, (1, 0, 0)),
    (0, (0, 1, 0)),
    (0, (0, 0, 1)),
    (1, (0, 0, 0)),
    (1, (1, 0, 0)),
    (1, (0, 1, 0)),
    (1, (0, 0, 1)),
    (2, (0, 0, 0)),
    (2, (1, 0, 0)),
    (2, (0, 1, 0)),
    (2, (0, 0, 1)),
)
EXPECTED_GEOMETRY_TABLE_NAMES = frozenset(
    {
        "FE2_C0_D100_Q907",
        "FE2_C1_D010_Q907",
        "FE2_C1_D011_Q907",
        "FE2_C1_D110_Q907",
        "FE2_C2_D001_Q907",
        "FE2_C2_D101_Q907",
        "weights_907",
    }
)
EXPECTED_STATIC_TABLE_EXTENTS = {
    **{name: (1, 1, POINT_COUNT, DIMENSION) for name in FEATURE_NAMES},
    **{
        name: (1, 1, POINT_COUNT, 8)
        for name in EXPECTED_GEOMETRY_TABLE_NAMES
        if name != "weights_907"
    },
    "weights_907": (POINT_COUNT,),
}
CACHE_IDENTITY_SCHEMA = "task41.p0.actual_qmetric_cache_identity.v1"
GEOMETRY_ORACLE_TRACE_SCHEMA = "J0_dxyz_sv_907_fw0_fw143_v1"
REQUIRED_GEOMETRY_TRACE_FIELDS = frozenset(
    {
        *(f"J0_c{index}" for index in range(9)),
        *(f"fw{index}" for index in range(144)),
        "sv_907_17", "sv_907_18", "sv_907_22", "sv_907_23",
        "sv_907_39", "sv_907_44", "sv_907_49", "sv_907_75",
        "sv_907_80", "sv_907_85",
    }
)


def _cache_identity_digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


INTEGRAL_BODY_BY_TAG = {
    1: "864d4c7eed2757a5abf2d85edfb0b0c88b2dd0a1",
    2: "400b1484491f511cf882a0fa24bcbec7f47377f5",
    3: "400b1484491f511cf882a0fa24bcbec7f47377f5",
}
PROFILE_TAGS = frozenset(INTEGRAL_BODY_BY_TAG)
HELPER_COMPILER_FLAGS = (
    "-std=c17",
    "-O2",
    "-g0",
    "-DNDEBUG",
    "-fno-strict-overflow",
    "-fno-fast-math",
    "-Wall",
    "-fPIC",
)


def _array_declaration_info(source: str, name: str) -> tuple[str, tuple[int, ...]]:
    """Return one frozen static double table and its checked C extents."""

    match = re.search(
        rf"static const double\s+{re.escape(name)}"
        r"(?P<dimensions>(?:\s*\[[^\]]+\])+)\s*=\s*\{",
        source,
    )
    if match is None:
        raise ValueError(f"frozen FFCx source lacks static table {name}")
    dimension_tokens = re.findall(r"\[([^\]]+)\]", match.group("dimensions"))
    if not dimension_tokens or any(
        re.fullmatch(r"\s*[1-9][0-9]*\s*", token) is None
        for token in dimension_tokens
    ):
        raise ValueError(f"frozen FFCx table {name} has a non-literal or non-positive extent")
    shape = tuple(int(token) for token in dimension_tokens)
    open_brace = source.find("{", match.start(), match.end())
    depth = 0
    end = None
    for index in range(open_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        raise ValueError(f"frozen FFCx table {name} has an unterminated initializer")
    while end < len(source) and source[end].isspace():
        end += 1
    if end >= len(source) or source[end] != ";":
        raise ValueError(f"frozen FFCx table {name} has an unexpected declaration end")
    return source[match.start() : end + 1], shape


def _array_declaration(source: str, name: str) -> str:
    """Return one frozen static double array declaration, including its values."""

    return _array_declaration_info(source, name)[0]


def _checked_array_declaration(
    source: str, name: str, expected_shape: tuple[int, ...]
) -> tuple[str, tuple[int, ...]]:
    declaration, shape = _array_declaration_info(source, name)
    if shape != expected_shape:
        raise ValueError(
            f"frozen FFCx table {name} has extent {shape}, expected {expected_shape}"
        )
    return declaration, shape


def _integral_body(source: str, digest: str) -> str:
    marker = f"// Code for integral integral_{digest}_hexahedron"
    start = source.find(marker)
    if start < 0:
        raise ValueError(f"frozen FFCx source lacks integral body {digest}")
    end = source.find("// Code for integral integral_", start + len(marker))
    if end < 0:
        end = len(source)
    return source[start:end]


def _geometry_trace_fields(geometry: str, function_name: str) -> tuple[str, ...]:
    """List the frozen scalar J/det/inverse/pullback values available per q point."""

    declarations = re.findall(
        r"(?m)^\s*double(?:\s+_Complex)?\s+([A-Za-z_]\w*)\s*=", geometry
    )
    fields = tuple(
        name
        for name in declarations
        if re.fullmatch(r"J0_c[0-8]", name)
        or re.fullmatch(r"J0_d(?:001|010|100)_c[0-8]", name)
        or re.fullmatch(r"sv_907_\d+", name)
        or re.fullmatch(r"fw\d+", name)
    )
    names = set(fields)
    if not REQUIRED_GEOMETRY_TRACE_FIELDS <= names:
        raise ValueError(
            f"frozen FFCx geometry {function_name} lacks J/det/inverse/fw trace fields"
        )
    if len(fields) != len(names):
        raise ValueError(f"frozen FFCx geometry {function_name} repeats trace fields")
    return fields


def _feature_pair_map(tensor_source: str) -> tuple[tuple[int, int], ...]:
    """Recover the exact 144 FFCx feature pairs from generated C assignments."""

    feature_index = {name: index for index, name in enumerate(FEATURE_NAMES)}
    temp_map: dict[int, tuple[int, int]] = {}
    for temp, fw, feature in re.findall(
        r"temp_(\d+)\[j\]\s*=\s*fw(\d+)\s*\*\s*"
        r"(FE0_C[012](?:_D[01]{3})?_Q907)\[0\]\[0\]\[iq\]\[j\];",
        tensor_source,
    ):
        if feature not in feature_index:
            raise ValueError(f"unrecognized frozen FFCx feature table {feature}")
        key = int(temp)
        if key in temp_map:
            raise ValueError(f"frozen FFCx source repeats temp_{key}")
        temp_map[key] = (int(fw), feature_index[feature])
    pairs_by_fw: dict[int, tuple[int, int]] = {}
    for left_feature, temp in re.findall(
        r"A\[882 \* \(i\) \+ \(j\)\]\s*\+=\s*"
        r"(FE0_C[012](?:_D[01]{3})?_Q907)\[0\]\[0\]\[iq\]\[i\]\s*"
        r"\*\s*temp_(\d+)\[j\];",
        tensor_source,
    ):
        if left_feature not in feature_index:
            raise ValueError(f"unrecognized frozen FFCx left feature {left_feature}")
        temp_index = int(temp)
        if temp_index not in temp_map:
            raise ValueError(f"frozen FFCx tensor uses unbound temp_{temp_index}")
        fw, right_index = temp_map[temp_index]
        if fw in pairs_by_fw:
            raise ValueError(f"frozen FFCx source repeats fw{fw} in tensor products")
        pairs_by_fw[fw] = (feature_index[left_feature], right_index)
    expected_fw = set(range(144))
    expected_pairs = {(left, right) for left in range(12) for right in range(12)}
    if set(pairs_by_fw) != expected_fw or set(pairs_by_fw.values()) != expected_pairs:
        raise ValueError(
            "frozen FFCx tensor source does not expose the expected 12-by-12 feature map"
        )
    return tuple(pairs_by_fw[index] for index in range(144))


def _geometry_snippet(
    body: str, function_name: str, *, include_trace: bool = False
) -> str:
    loop = "for (int iq = 0; iq < 512; ++iq)"
    start = body.find(loop)
    tensor_start = body.find("// Section: Tensor Computation", start)
    if start < 0 or tensor_start < 0:
        raise ValueError(f"frozen FFCx body {function_name} lacks the pinned Q907 sections")
    snippet = body[start:tensor_start]
    if snippet.count(loop) != 1:
        raise ValueError(f"frozen FFCx body {function_name} has multiple Q907 loops")
    if re.search(r"\b(?:w|c|entity_local_index|quadrature_permutation|custom_data)\b", snippet):
        raise ValueError(f"frozen FFCx geometry block {function_name} has an unsupported input")
    snippet = snippet.replace(loop, "for (int iq = iq_begin; iq < iq_end; ++iq)", 1)
    if "fw143" not in snippet:
        raise ValueError(f"frozen FFCx geometry block {function_name} does not emit all q metrics")
    loop_end = re.search(r"\n  }\n(?:  //[- ]+\s*\n)+\s*$", snippet)
    if loop_end is None:
        raise ValueError(
            f"frozen FFCx geometry block {function_name} has an unexpected Q907 loop ending"
        )
    snippet = snippet[: loop_end.start()]
    output = [
        "\n    for (int fw_index = 0; fw_index < 144; ++fw_index) {",
        "      switch (fw_index) {",
    ]
    output.extend(
        f"      case {index}: out[(iq - iq_begin) * 144 + {index}] = fw{index}; break;"
        for index in range(144)
    )
    output.extend(("      }", "    }"))
    if include_trace:
        trace_fields = _geometry_trace_fields(snippet, function_name)
        output.append("    if (trace != 0) {")
        output.extend(
            f"      trace[(iq - iq_begin) * {len(trace_fields)} + {index}] = {name};"
            for index, name in enumerate(trace_fields)
        )
        output.append("    }")
    return snippet.rstrip() + "\n" + "\n".join(output) + "\n  }\n"


def _instrument_original_kernel_geometry_oracle(
    body: str, integral_digest: str
) -> tuple[str, tuple[str, ...], str]:
    """Clone one frozen scalar kernel and add a bounded geometry side channel.

    The clone retains the original tensor calculation. It is generated for a
    separately gated oracle run and is never compiled or called by ``prepare``.
    """

    if integral_digest not in set(INTEGRAL_BODY_BY_TAG.values()):
        raise ValueError("original-kernel oracle digest is outside the frozen V6 profile")
    original_name = f"tabulate_tensor_integral_{integral_digest}_hexahedron"
    clone_name = f"task41_v6_original_geometry_oracle_{integral_digest[:12]}"
    if body.count(original_name) != 1:
        raise ValueError("frozen FFCx body does not contain one original integral function")
    loop = "for (int iq = 0; iq < 512; ++iq)"
    loop_start = body.find(loop)
    tensor_start = body.find("// Section: Tensor Computation", loop_start)
    if loop_start < 0 or tensor_start < 0:
        raise ValueError("frozen original kernel lacks the pinned Q907 geometry section")
    geometry = body[loop_start:tensor_start]
    loop_end = re.search(r"\n  }\n(?:  //[- ]+\s*\n)+\s*$", geometry)
    if loop_end is None:
        raise ValueError("frozen original kernel has an unexpected Q907 loop ending")
    fields = _geometry_trace_fields(geometry, original_name)
    instrument = [
        "\n    if (iq >= oracle_q_begin && iq < oracle_q_end) {",
    ]
    instrument.extend(
        f"      oracle_out[(iq - oracle_q_begin) * {len(fields)} + {index}] = {name};"
        for index, name in enumerate(fields)
    )
    instrument.append("    }")
    insertion = loop_start + loop_end.start()
    cloned = body[:insertion] + "\n".join(instrument) + body[insertion:]
    cloned = cloned.replace(original_name, clone_name, 1)
    signature = "void* custom_data)"
    if cloned.count(signature) != 1:
        raise ValueError("frozen original-kernel signature differs from the oracle profile")
    cloned = cloned.replace(
        signature,
        "void* custom_data, int oracle_q_begin, int oracle_q_end, "
        "double _Complex* restrict oracle_out)",
        1,
    )
    function_start = cloned.find(clone_name)
    function_open = cloned.find(")\n{", function_start)
    if function_open < 0:
        raise ValueError("instrumented original-kernel signature is malformed")
    guard = (
        "\n  if (oracle_q_begin < 0 || oracle_q_end > 512 || "
        "oracle_q_begin >= oracle_q_end || oracle_out == 0) return;"
    )
    cloned = cloned[: function_open + 3] + guard + cloned[function_open + 3 :]
    source = "#include <complex.h>\n#include <math.h>\n#include <stdint.h>\n\n" + cloned
    return source, fields, clone_name


def compare_geometry_traces(
    candidate: np.ndarray,
    original_kernel: np.ndarray,
    field_names: Sequence[str],
) -> dict[str, Any]:
    """Compare bounded helper and instrumented-original geometry traces."""

    left = np.asarray(candidate, dtype=np.complex128)
    right = np.asarray(original_kernel, dtype=np.complex128)
    fields = tuple(str(name) for name in field_names)
    if (
        left.ndim != 2
        or left.shape != right.shape
        or left.shape[1] != len(fields)
        or not fields
    ):
        raise ValueError("geometry traces must have the same (q points, named fields) shape")
    if not np.all(np.isfinite(left)) or not np.all(np.isfinite(right)):
        raise ValueError("geometry trace comparison contains a non-finite scalar")
    difference = np.abs(left - right)
    flat_index = int(np.argmax(difference))
    point_index, field_index = np.unravel_index(flat_index, difference.shape)
    original_norm = float(np.linalg.norm(right.ravel()))
    absolute_frobenius = float(np.linalg.norm((left - right).ravel()))
    return {
        "status": "BITWISE_EQUAL" if np.array_equal(left, right) else "MISMATCH",
        "point_count": int(left.shape[0]),
        "field_count": len(fields),
        "field_names_sha256": hashlib.sha256(
            "\n".join(fields).encode("ascii")
        ).hexdigest(),
        "max_abs": float(difference.flat[flat_index]),
        "max_point_index": int(point_index),
        "max_field": fields[int(field_index)],
        "absolute_frobenius": absolute_frobenius,
        "relative_frobenius": absolute_frobenius / max(original_norm, np.finfo(float).tiny),
    }


def _original_ffcx_compile_flags(
    build_log: str, source_name: str
) -> tuple[str, tuple[str, ...]]:
    """Recover the pinned FFCx compile flags from its hashed CFFI build log."""

    for line in build_log.splitlines():
        try:
            tokens = shlex.split(line)
        except ValueError:
            continue
        if not tokens or Path(tokens[0]).name not in {"gcc", "cc", "clang"}:
            continue
        if "-c" not in tokens or "-o" not in tokens:
            continue
        compile_index = tokens.index("-c")
        output_index = tokens.index("-o")
        if (
            output_index <= compile_index + 1
            or output_index + 1 >= len(tokens)
            or Path(tokens[compile_index + 1]).name != source_name
        ):
            continue
        flags = tuple(tokens[1:compile_index] + tokens[output_index + 2 :])
        return tokens[0], flags
    raise ValueError("hashed FFCx build log has no compile command for the frozen C source")


def _build_helper_source(
    source_text: str,
) -> tuple[
    str,
    tuple[tuple[int, int], ...],
    str,
    dict[str, tuple[int, ...]],
    tuple[str, ...],
]:
    feature_declarations: dict[str, str] = {}
    table_shapes: dict[str, tuple[int, ...]] = {}
    profile_data: dict[str, tuple[str, str, tuple[tuple[int, int], ...]]] = {}
    common_trace_fields: tuple[str, ...] | None = None
    for tag, digest in sorted(INTEGRAL_BODY_BY_TAG.items()):
        if digest in profile_data:
            continue
        body = _integral_body(source_text, digest)
        tensor_start = body.find("// Section: Tensor Computation")
        if tensor_start < 0:
            raise ValueError(f"frozen FFCx integral {digest} lacks tensor section")
        tensor_source = body[tensor_start:]
        pairs = _feature_pair_map(tensor_source)
        geometry = _geometry_snippet(body, digest, include_trace=True)
        trace_fields = _geometry_trace_fields(geometry, digest)
        if common_trace_fields is None:
            common_trace_fields = trace_fields
        elif trace_fields != common_trace_fields:
            raise ValueError(
                "the frozen integral bodies expose different geometry trace layouts"
            )
        geometry_names = sorted(
            set(
                re.findall(
                    r"\b(?:FE2_[A-Za-z0-9_]+_Q907|weights_907)\b", geometry
                )
            )
        )
        if set(geometry_names) != EXPECTED_GEOMETRY_TABLE_NAMES:
            raise ValueError(f"frozen FFCx integral {digest} geometry table set differs")
        geometry_declarations: dict[str, str] = {}
        for name in geometry_names:
            expected_shape = EXPECTED_STATIC_TABLE_EXTENTS[name]
            declaration, shape = _checked_array_declaration(
                body, name, expected_shape
            )
            previous_shape = table_shapes.get(name)
            if previous_shape is not None and previous_shape != shape:
                raise ValueError(f"FFCx geometry table extent {name} differs by integral body")
            table_shapes[name] = shape
            geometry_declarations[name] = declaration
        for name in FEATURE_NAMES:
            expected_shape = EXPECTED_STATIC_TABLE_EXTENTS[name]
            declaration, shape = _checked_array_declaration(
                body, name, expected_shape
            )
            previous_shape = table_shapes.get(name)
            if previous_shape is not None and previous_shape != shape:
                raise ValueError(f"FFCx reference table extent {name} differs by integral body")
            table_shapes[name] = shape
            previous = feature_declarations.get(name)
            if previous is not None and previous != declaration:
                raise ValueError(f"FFCx reference table {name} differs between integral bodies")
            feature_declarations[name] = declaration
        profile_data[digest] = (
            geometry,
            json.dumps(geometry_declarations, sort_keys=True),
            pairs,
        )
    if set(feature_declarations) != set(FEATURE_NAMES):
        raise ValueError("frozen FFCx source does not provide all 12 FE0 reference tables")
    pair_maps = {record[2] for record in profile_data.values()}
    if len(pair_maps) != 1:
        raise ValueError("the two frozen integral bodies have different FE0 tensor maps")
    pairs = next(iter(pair_maps))
    declarations = [feature_declarations[name] for name in FEATURE_NAMES]
    first_body = _integral_body(source_text, next(iter(INTEGRAL_BODY_BY_TAG.values())))
    weight_decl = _array_declaration(first_body, "weights_907")
    functions: list[str] = []
    for digest, (geometry, geometry_json, _pairs) in profile_data.items():
        table_map = json.loads(geometry_json)
        function_name = f"task41_geometry_{digest[:8]}"
        declarations_for_function = "\n".join(table_map[name] for name in sorted(table_map))
        functions.append(
            f"void {function_name}(const double *coordinate_dofs, int iq_begin, int iq_end, "
            "double _Complex *out, double _Complex *trace) {\n"
            f"  {declarations_for_function}\n"
            f"  {geometry}"
            "}\n"
        )
    pointer_cases = "\n".join(
        f"    case {index}: return &{name}[0][0][0][0];"
        for index, name in enumerate(FEATURE_NAMES)
    )
    helper = (
        "#include <complex.h>\n#include <math.h>\n#include <stdint.h>\n"
        "#include <string.h>\n\n"
        + "\n".join(declarations)
        + "\n"
        + weight_decl
        + "\n"
        + "const double *task41_reference_table_ptr(int index) {\n"
        "  switch (index) {\n"
        + pointer_cases
        + "\n    default: return 0;\n  }\n}\n"
        "const double *task41_reference_weights_ptr(void) { return weights_907; }\n"
        + "\n".join(functions)
    )
    if common_trace_fields is None:
        raise ValueError("frozen FFCx source has no actual geometry trace layout")
    helper_sha = hashlib.sha256(helper.encode("ascii")).hexdigest()
    return helper, pairs, helper_sha, table_shapes, common_trace_fields


def assemble_blocked_gram(
    qmetric: np.ndarray,
    reference_features: np.ndarray,
    feature_pairs: Sequence[tuple[int, int]],
    *,
    phase_seconds: dict[str, float] | None = None,
) -> np.ndarray:
    """Assemble one point block using full, non-Hermitian 12-feature Gram form."""

    metric_values = np.asarray(qmetric, dtype=np.complex128)
    features = np.asarray(reference_features, dtype=np.float64)
    if metric_values.ndim != 3 or metric_values.shape[1:] != (12, 12):
        raise ValueError("qmetric block must have shape (points, 12, 12)")
    if features.ndim != 3 or features.shape[:2] != metric_values.shape[:2]:
        raise ValueError("reference feature block must have shape (points, 12, dimension)")
    points, _, dimension = features.shape
    pairs = tuple((int(left), int(right)) for left, right in feature_pairs)
    if len(pairs) != 144 or set(pairs) != {
        (left, right) for left in range(12) for right in range(12)
    }:
        raise ValueError("feature-pair map must cover each ordered pair exactly once")
    # qmetric is recovered from FFCx fw values using the generated C map.  The
    # Gram reorganization changes only the accumulation schedule, not the
    # generated geometry graph, feature tables, coefficient, or matrix sides.
    matrix = np.zeros((dimension, dimension), dtype=np.complex128)
    gram_started = perf_counter()
    weighted = np.einsum("qab,qbj->qaj", metric_values, features, optimize=True)
    if phase_seconds is not None:
        phase_seconds["gram"] = phase_seconds.get("gram", 0.0) + float(
            perf_counter() - gram_started
        )
    pack_started = perf_counter()
    left_flat = np.ascontiguousarray(features.reshape((points * 12, dimension)))
    weighted_flat = np.ascontiguousarray(weighted.reshape((points * 12, dimension)))
    if phase_seconds is not None:
        phase_seconds["pack"] = phase_seconds.get("pack", 0.0) + float(
            perf_counter() - pack_started
        )
    gram_started = perf_counter()
    matrix[:] = left_flat.T @ weighted_flat
    if phase_seconds is not None:
        phase_seconds["gram"] = phase_seconds.get("gram", 0.0) + float(
            perf_counter() - gram_started
        )
    release_started = perf_counter()
    del weighted, left_flat, weighted_flat
    if phase_seconds is not None:
        phase_seconds["release"] = phase_seconds.get("release", 0.0) + float(
            perf_counter() - release_started
        )
    return matrix


class _FrozenFFCxGeometryHelper:
    def __init__(self, source_path: Path, scratch_directory: Path) -> None:
        self.source_path = source_path.resolve(strict=True)
        self.scratch_directory = scratch_directory
        self._temporary_directory: tempfile.TemporaryDirectory[str] | None = None
        self._library: ctypes.CDLL | None = None
        self._reference_tables: tuple[np.ndarray, ...] | None = None
        self._weights: np.ndarray | None = None
        self._reference_table_zero_counts: list[int] = []
        self._reference_table_zero_pattern_hashes: list[str] = []
        self.reference_weight_sha256: str | None = None
        self.static_table_shapes: dict[str, tuple[int, ...]] = {}
        self._geometry_functions: dict[str, Any] = {}
        self._oracle_functions: dict[str, tuple[Any, Any, tuple[str, ...]]] = {}
        self._oracle_artifact_bytes: dict[str, int] = {}
        self._oracle_compile_audits: dict[str, dict[str, Any]] = {}
        self._oracle_execution_count = 0
        self.geometry_trace_fields: tuple[str, ...] | None = None
        self.feature_pairs: tuple[tuple[int, int], ...] | None = None
        self.helper_source_sha256: str | None = None
        self.helper_library_sha256: str | None = None
        self.helper_source_bytes: int | None = None
        self.helper_library_bytes: int | None = None
        self.source_sha256: str | None = None
        self.source_bytes: int | None = None
        self.cache_metadata_path = Path(str(self.source_path) + ".cached")
        self.cache_metadata_sha256: str | None = None
        self.compiler_command: tuple[str, ...] | None = None

    @staticmethod
    def _file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    def prepare(self, *, expected_rule_points: np.ndarray, expected_rule_weights: np.ndarray) -> dict[str, Any]:
        if self._library is not None:
            return self.audit()
        started = perf_counter()
        self.cache_metadata_sha256 = self._file_sha256(self.cache_metadata_path)
        if self.cache_metadata_sha256 != EXPECTED_C_CACHE_SHA256:
            raise ValueError("actual-qmetric FFCx compile metadata differs from the frozen V6 profile")
        source_bytes = self.source_path.read_bytes()
        self.source_bytes = len(source_bytes)
        self.source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        if (
            self.source_bytes != EXPECTED_C_SOURCE_BYTES
            or self.source_sha256 != EXPECTED_C_SOURCE_SHA256
        ):
            raise ValueError("actual-qmetric FFCx C source identity differs from the frozen V6 profile")
        source_text = source_bytes.decode("ascii")
        helper_source, pairs, helper_sha, table_shapes, trace_fields = _build_helper_source(
            source_text
        )
        del source_text, source_bytes
        self.feature_pairs = pairs
        self.static_table_shapes = table_shapes
        self.geometry_trace_fields = trace_fields
        self.helper_source_sha256 = helper_sha
        self.scratch_directory.mkdir(parents=True, exist_ok=True)
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="task41_actual_qmetric_", dir=self.scratch_directory
        )
        work = Path(self._temporary_directory.name)
        c_path = work / "actual_qmetric_helper.c"
        so_path = work / "actual_qmetric_helper.so"
        c_path.write_text(helper_source, encoding="ascii")
        del helper_source
        self.helper_source_bytes = c_path.stat().st_size
        compiler = shlex.split(os.environ.get("CC", "gcc"))
        if not compiler:
            raise RuntimeError("CC is empty; cannot compile the frozen geometry helper")
        if shutil.which(compiler[0]) is None:
            raise RuntimeError(f"geometry helper compiler is unavailable: {compiler[0]}")
        command = (
            *compiler,
            *HELPER_COMPILER_FLAGS,
            "-shared",
            str(c_path),
            "-o",
            str(so_path),
            "-lm",
        )
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "frozen actual-qmetric helper compile failed: "
                + completed.stderr[-4000:]
            )
        self.compiler_command = tuple(command)
        self.helper_library_sha256 = self._file_sha256(so_path)
        self.helper_library_bytes = so_path.stat().st_size
        retained_helper_scratch = self.helper_source_bytes + self.helper_library_bytes
        if retained_helper_scratch > Task41ActualQMetricBlockedGramCandidate.helper_scratch_bytes_upper:
            raise MemoryError(
                "frozen helper source and library exceed the reserved retained scratch "
                f"({retained_helper_scratch} > "
                f"{Task41ActualQMetricBlockedGramCandidate.helper_scratch_bytes_upper})"
            )
        library = ctypes.CDLL(str(so_path))
        pointer_type = ctypes.POINTER(ctypes.c_double)
        library.task41_reference_table_ptr.argtypes = [ctypes.c_int]
        library.task41_reference_table_ptr.restype = pointer_type
        library.task41_reference_weights_ptr.argtypes = []
        library.task41_reference_weights_ptr.restype = pointer_type
        geometry_argument_types = [
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
            ctypes.c_void_p,
        ]
        for digest in sorted(set(INTEGRAL_BODY_BY_TAG.values())):
            function = getattr(library, f"task41_geometry_{digest[:8]}")
            function.argtypes = geometry_argument_types
            function.restype = None
            self._geometry_functions[digest] = function
        table_views: list[np.ndarray] = []
        for index in range(12):
            pointer = library.task41_reference_table_ptr(index)
            if not pointer:
                raise RuntimeError(f"frozen helper returned no FE0 reference table {index}")
            table = np.ctypeslib.as_array(pointer, shape=(POINT_COUNT * DIMENSION,))
            table = table.reshape((POINT_COUNT, DIMENSION))
            table.setflags(write=False)
            zero_pattern = np.packbits(
                np.asarray(table == 0.0).reshape(-1), bitorder="little"
            )
            self._reference_table_zero_counts.append(
                int(np.count_nonzero(table == 0.0))
            )
            self._reference_table_zero_pattern_hashes.append(
                hashlib.sha256(memoryview(zero_pattern).cast("B")).hexdigest()
            )
            table_views.append(table)
        weight_pointer = library.task41_reference_weights_ptr()
        if not weight_pointer:
            raise RuntimeError("frozen helper returned no Q907 weight table")
        weights = np.ctypeslib.as_array(weight_pointer, shape=(POINT_COUNT,))
        weights.setflags(write=False)
        if not np.array_equal(weights, np.asarray(expected_rule_weights, dtype=np.float64)):
            raise ValueError("FFCx Q907 weights differ from analyzed full-form weights")
        if np.asarray(expected_rule_points).shape != (POINT_COUNT, 3):
            raise ValueError("analyzed full-form rule is not the frozen 512-point Q907 rule")
        self._library = library
        self._reference_tables = tuple(table_views)
        self._weights = weights
        self.reference_weight_sha256 = hashlib.sha256(
            memoryview(np.ascontiguousarray(weights)).cast("B")
        ).hexdigest()
        self._validate_basix_reference_tables(expected_rule_points)
        self.preparation_seconds = float(perf_counter() - started)
        return self.audit()

    def _validate_basix_reference_tables(self, points: np.ndarray) -> None:
        if self._reference_tables is None:
            raise RuntimeError("FFCx reference tables are not prepared")
        import basix

        element = self._profile_element
        tabulation = np.asarray(element.tabulate(1, np.asarray(points, dtype=np.float64)))
        for table_index, (component, derivative) in enumerate(FEATURE_COMPONENT_DERIVATIVE):
            expected = np.asarray(
                tabulation[basix.index(*derivative), :, :, component], dtype=np.float64
            )
            actual = self._reference_tables[table_index]
            bitwise_equal = np.array_equal(expected, actual)
            if not bitwise_equal:
                difference = np.abs(expected - actual)
                structural_zero_equal = np.array_equal(
                    expected == 0.0, actual == 0.0
                )
                zero_mismatches = int(
                    np.count_nonzero((expected == 0.0) != (actual == 0.0))
                )
                mismatch_kind = (
                    "structural zero pattern differs"
                    if not structural_zero_equal
                    else "values differ with structural zero pattern preserved"
                )
                raise ValueError(
                    "Basix cross-check against the frozen FFCx reference table is not "
                    f"bitwise equal ({mismatch_kind}; table={FEATURE_NAMES[table_index]}, "
                    f"zero_pattern_mismatches={zero_mismatches}, "
                    f"max_abs={float(difference.max(initial=0.0)):.17g}); "
                    "this is a table-identity diagnostic, not a geometry result"
                )

    def bind_element(self, element: Any) -> None:
        self._profile_element = element

    def reference_block(self, start: int, stop: int) -> np.ndarray:
        if self._reference_tables is None:
            raise RuntimeError("FFCx reference tables are not prepared")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("reference-table block is outside Q907")
        return np.stack(
            [table[start:stop] for table in self._reference_tables], axis=1
        )

    def geometry_block(
        self, tag: int, coordinates: np.ndarray, start: int, stop: int
    ) -> np.ndarray:
        if self._library is None:
            raise RuntimeError("frozen FFCx geometry helper is not prepared")
        digest = INTEGRAL_BODY_BY_TAG[int(tag)]
        function = self._geometry_functions[digest]
        coordinate_array = np.asarray(coordinates)
        if (
            coordinate_array.shape != (8, 3)
            or coordinate_array.dtype != np.dtype(np.float64)
            or not coordinate_array.flags.c_contiguous
        ):
            raise ValueError("actual-qmetric coordinates must be original contiguous float64 (8, 3)")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("geometry block is outside the frozen Q907 rule")
        output = np.empty((stop - start, 144), dtype=np.complex128)
        function(
            coordinate_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            int(start),
            int(stop),
            ctypes.c_void_p(output.ctypes.data),
            ctypes.c_void_p(),
        )
        return output

    def geometry_trace_block(
        self, tag: int, coordinates: np.ndarray, start: int, stop: int
    ) -> np.ndarray:
        if self._library is None or self.geometry_trace_fields is None:
            raise RuntimeError("frozen FFCx geometry trace helper is not prepared")
        digest = INTEGRAL_BODY_BY_TAG[int(tag)]
        function = self._geometry_functions[digest]
        coordinate_array = np.asarray(coordinates)
        if (
            coordinate_array.shape != (8, 3)
            or coordinate_array.dtype != np.dtype(np.float64)
            or not coordinate_array.flags.c_contiguous
        ):
            raise ValueError("actual-qmetric coordinates must be original contiguous float64 (8, 3)")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("geometry trace block is outside the frozen Q907 rule")
        output = np.empty(
            (stop - start, len(self.geometry_trace_fields)), dtype=np.complex128
        )
        qmetric_scratch = np.empty((stop - start, 144), dtype=np.complex128)
        function(
            coordinate_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            int(start),
            int(stop),
            ctypes.c_void_p(qmetric_scratch.ctypes.data),
            ctypes.c_void_p(output.ctypes.data),
        )
        return output

    def original_kernel_oracle_source(
        self,
        tag: int,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
    ) -> dict[str, Any]:
        """Generate the original-kernel trace clone only after a resource gate."""

        digest = INTEGRAL_BODY_BY_TAG[int(tag)]
        if self.source_sha256 != EXPECTED_C_SOURCE_SHA256:
            raise RuntimeError("prepare the frozen source profile before generating its oracle")
        if not callable(allocation_gate):
            raise TypeError("original-kernel oracle source requires an external resource gate")
        metadata = self.cache_metadata_path.read_bytes()
        metadata_sha = hashlib.sha256(metadata).hexdigest()
        if metadata_sha != EXPECTED_C_CACHE_SHA256:
            raise ValueError("hashed FFCx build log changed before original-kernel oracle compile")
        compiler, flags = _original_ffcx_compile_flags(
            metadata.decode("utf-8"), self.source_path.name
        )
        if shutil.which(compiler) is None:
            raise RuntimeError(f"frozen FFCx compiler is unavailable: {compiler}")
        allocation_gate(
            "task41_v6_original_kernel_oracle_compile",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_workspace_bytes_upper,
                "workspace_bytes_upper": Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_workspace_bytes_upper,
                "scratch_bytes_upper": Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_scratch_bytes_upper,
                "oracle_source_bytes_upper": Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_source_bytes_upper,
                "shared_table_bytes_upper": self.shared_table_bytes_upper,
                "retained_helper_scratch_bytes": int(
                    (self.helper_source_bytes or 0) + (self.helper_library_bytes or 0)
                ),
                "ffcx_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
                "ffcx_compile_metadata_sha256": metadata_sha,
                "compiler": compiler,
                "compiler_flags": list(flags),
            },
        )
        source_generation_started = perf_counter()
        source_bytes = self.source_path.read_bytes()
        if (
            len(source_bytes) != EXPECTED_C_SOURCE_BYTES
            or hashlib.sha256(source_bytes).hexdigest() != EXPECTED_C_SOURCE_SHA256
        ):
            raise ValueError("original-kernel oracle source changed from the frozen profile")
        source_text = source_bytes.decode("ascii")
        body = _integral_body(source_text, digest)
        oracle_source, fields, function_name = _instrument_original_kernel_geometry_oracle(
            body, digest
        )
        source_generation_seconds = float(perf_counter() - source_generation_started)
        oracle_source_blob = oracle_source.encode("ascii")
        oracle_source_bytes = len(oracle_source_blob)
        if oracle_source_bytes > Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_source_bytes_upper:
            raise MemoryError("original-kernel oracle source exceeds its pre-gated upper bound")
        source_sha256 = hashlib.sha256(oracle_source_blob).hexdigest()
        del oracle_source_blob, source_text, source_bytes, body
        return {
            "source": oracle_source,
            "source_sha256": source_sha256,
            "source_bytes": oracle_source_bytes,
            "source_generation_seconds": source_generation_seconds,
            "compiler": compiler,
            "compiler_flags": list(flags),
            "compile_metadata_sha256": metadata_sha,
            "integral_digest": digest,
            "function_name": function_name,
            "trace_fields": fields,
            "trace_field_count": len(fields),
            "q_range_contract": "0 <= begin < end <= 512; writes only the requested interval",
            "original_tensor_section_preserved": "// Section: Tensor Computation" in oracle_source,
            "execution_status": "NOT_RUN_NO_WINDOW_APPROVAL",
        }

    def run_original_kernel_geometry_oracle(
        self,
        tag: int,
        coordinates: np.ndarray,
        start: int,
        stop: int,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
    ) -> dict[str, Any]:
        """Compile and run the bounded original FFCx kernel clone on explicit request."""

        digest = INTEGRAL_BODY_BY_TAG[int(tag)]
        coordinate_array = np.asarray(coordinates)
        if (
            coordinate_array.shape != (8, 3)
            or coordinate_array.dtype != np.dtype(np.float64)
            or not coordinate_array.flags.c_contiguous
        ):
            raise ValueError("original-kernel oracle requires original contiguous float64 (8, 3) coordinates")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("original-kernel oracle q range is outside the frozen Q907 rule")
        if not callable(allocation_gate):
            raise TypeError("original-kernel oracle requires an external resource allocation gate")
        self._compile_original_kernel_oracle(int(tag), allocation_gate=allocation_gate)
        function, library, fields = self._oracle_functions[digest]
        trace_bytes = int((stop - start) * len(fields) * np.dtype(np.complex128).itemsize)
        tensor_bytes = int(DIMENSION * DIMENSION * np.dtype(np.complex128).itemsize)
        allocation_gate(
            "task41_v6_original_kernel_oracle_call",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": tensor_bytes + trace_bytes,
                "raw_tensor_bytes": tensor_bytes,
                "geometry_trace_bytes": trace_bytes,
                "geometry_trace_field_count": len(fields),
                "q_begin": int(start),
                "q_end": int(stop),
                "frozen_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
                "compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
                "oracle_library_bytes": self._oracle_artifact_bytes[digest],
            },
        )
        output_allocation_started = perf_counter()
        tensor = np.zeros((DIMENSION, DIMENSION), dtype=np.complex128)
        trace = np.empty((stop - start, len(fields)), dtype=np.complex128)
        output_allocation_seconds = float(perf_counter() - output_allocation_started)
        kernel_started = perf_counter()
        function(
            ctypes.c_void_p(tensor.ctypes.data),
            ctypes.c_void_p(),
            ctypes.c_void_p(),
            coordinate_array.ctypes.data_as(ctypes.POINTER(ctypes.c_double)),
            ctypes.c_void_p(),
            ctypes.c_void_p(),
            ctypes.c_void_p(),
            int(start),
            int(stop),
            ctypes.c_void_p(trace.ctypes.data),
        )
        kernel_call_seconds = float(perf_counter() - kernel_started)
        self._oracle_execution_count += 1
        return {
            "tensor": tensor,
            "geometry_trace": trace,
            "trace_fields": fields,
            "tag": int(tag),
            "q_begin": int(start),
            "q_end": int(stop),
            "function_name": f"task41_v6_original_geometry_oracle_{digest[:12]}",
            "compile_audit": dict(self._oracle_compile_audits[digest]),
            "execution_status": "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE",
            "output_allocation_seconds": output_allocation_seconds,
            "kernel_call_seconds": kernel_call_seconds,
            "library_handle_retained": library is not None,
        }

    def _compile_original_kernel_oracle(
        self,
        tag: int,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
    ) -> None:
        digest = INTEGRAL_BODY_BY_TAG[int(tag)]
        if digest in self._oracle_functions:
            return
        if self._temporary_directory is None:
            raise RuntimeError("prepare the frozen geometry helper before its original-kernel oracle")
        oracle_record = self.original_kernel_oracle_source(
            int(tag), allocation_gate=allocation_gate
        )
        oracle_source = str(oracle_record["source"])
        compiler = str(oracle_record["compiler"])
        flags = tuple(str(value) for value in oracle_record["compiler_flags"])
        metadata_sha = str(oracle_record["compile_metadata_sha256"])
        work = Path(self._temporary_directory.name)
        source_path = work / f"original_kernel_oracle_{digest[:12]}.c"
        library_path = work / f"original_kernel_oracle_{digest[:12]}.so"
        source_path.write_text(oracle_source, encoding="ascii")
        del oracle_record["source"]
        del oracle_source
        command = (
            compiler,
            *flags,
            "-shared",
            str(source_path),
            "-lm",
            "-o",
            str(library_path),
        )
        compile_started = perf_counter()
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "frozen original-kernel geometry oracle compile failed: "
                + completed.stderr[-4000:]
            )
        compiler_seconds = float(perf_counter() - compile_started)
        library = ctypes.CDLL(str(library_path))
        function_name = str(oracle_record["function_name"])
        function = getattr(library, function_name)
        function.argtypes = [
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_double),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_void_p,
        ]
        function.restype = None
        artifact_bytes = int(source_path.stat().st_size + library_path.stat().st_size)
        self._oracle_artifact_bytes[digest] = artifact_bytes
        if sum(self._oracle_artifact_bytes.values()) > Task41ActualQMetricBlockedGramCandidate.original_kernel_oracle_scratch_bytes_upper:
            raise MemoryError("original-kernel oracle artifacts exceed the reserved scratch upper bound")
        self._oracle_functions[digest] = (
            function,
            library,
            tuple(oracle_record["trace_fields"]),
        )
        self._oracle_compile_audits[digest] = {
            "source_sha256": oracle_record["source_sha256"],
            "source_bytes": int(source_path.stat().st_size),
            "library_sha256": self._file_sha256(library_path),
            "library_bytes": int(library_path.stat().st_size),
            "compiler": compiler,
            "compiler_flags": list(flags),
            "compile_metadata_sha256": metadata_sha,
            "source_generation_seconds": float(
                oracle_record["source_generation_seconds"]
            ),
            "compiler_seconds": compiler_seconds,
            "command": list(command),
        }

    @property
    def reference_table_bytes(self) -> int:
        return int(
            12 * POINT_COUNT * DIMENSION * np.dtype(np.float64).itemsize
            + POINT_COUNT * np.dtype(np.float64).itemsize
        )

    @property
    def shared_table_bytes_upper(self) -> int:
        if not self.static_table_shapes:
            raise RuntimeError("frozen FFCx table extents are not prepared")
        geometry_copy_count = len(set(INTEGRAL_BODY_BY_TAG.values()))
        geometry_tables = sum(
            int(np.prod(shape, dtype=np.int64)) * np.dtype(np.float64).itemsize
            for name, shape in self.static_table_shapes.items()
            if name.startswith("FE2_") or name == "weights_907"
        )
        # FE0 reference arrays plus the separately exported Q907 weights, and
        # each unique geometry function's static FE2 and weight declarations.
        return int(self.reference_table_bytes + geometry_copy_count * geometry_tables)

    def audit(self) -> dict[str, Any]:
        return {
            "source_path": str(self.source_path),
            "source_sha256": self.source_sha256 or EXPECTED_C_SOURCE_SHA256,
            "source_bytes": self.source_bytes or EXPECTED_C_SOURCE_BYTES,
            "compile_metadata_path": str(self.cache_metadata_path),
            "compile_metadata_sha256": self.cache_metadata_sha256
            or EXPECTED_C_CACHE_SHA256,
            "helper_source_sha256": self.helper_source_sha256,
            "helper_source_bytes": self.helper_source_bytes,
            "helper_library_sha256": self.helper_library_sha256,
            "helper_library_bytes": self.helper_library_bytes,
            "helper_scratch_retained_bytes": int(
                (self.helper_source_bytes or 0) + (self.helper_library_bytes or 0)
            ),
            "compiler_command": list(self.compiler_command or ()),
            "compiler_flags": list(HELPER_COMPILER_FLAGS),
            "reference_table_names": list(FEATURE_NAMES),
            "reference_table_bytes": self.reference_table_bytes,
            "shared_table_bytes_upper": self.shared_table_bytes_upper,
            "reference_table_hashes": (
                [
                    hashlib.sha256(memoryview(np.ascontiguousarray(table)).cast("B")).hexdigest()
                    for table in self._reference_tables
                ]
                if self._reference_tables is not None
                else None
            ),
            "reference_weight_sha256": self.reference_weight_sha256,
            "reference_table_zero_counts": list(self._reference_table_zero_counts),
            "reference_table_zero_pattern_hashes": list(
                self._reference_table_zero_pattern_hashes
            ),
            "static_table_declared_extents": {
                name: list(shape)
                for name, shape in sorted(self.static_table_shapes.items())
            },
            "feature_pair_map": (
                [list(pair) for pair in self.feature_pairs]
                if self.feature_pairs is not None
                else None
            ),
            "quadrature_point_count": POINT_COUNT,
            "geometry_helper_block_size": POINT_BLOCK_SIZE,
            "geometry_expression_source": "frozen_FFCx_Q907_Jacobian_and_fw_graph",
            "geometry_shortcut_used": False,
            "geometry_trace_fields": list(self.geometry_trace_fields or ()),
            "geometry_trace_source": "same_frozen_FFCx_scalar_graph_as_actual_qmetric_block",
            "original_kernel_oracle_generator": (
                "_FrozenFFCxGeometryHelper.original_kernel_oracle_source"
            ),
            "original_kernel_oracle_execution_status": (
                "NOT_RUN_NO_WINDOW_APPROVAL"
                if self._oracle_execution_count == 0
                else "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE"
            ),
            "original_kernel_oracle_execution_count": self._oracle_execution_count,
            "original_kernel_oracle_artifact_bytes": int(
                sum(self._oracle_artifact_bytes.values())
            ),
            "original_kernel_oracle_compile_audits": {
                digest: dict(record)
                for digest, record in self._oracle_compile_audits.items()
            },
        }


class Task41ActualQMetricBlockedGramCandidate:
    """Unqualified exact-profile candidate using frozen C geometry and tables."""

    identity = IDENTITY
    point_block_size = POINT_BLOCK_SIZE
    profile_name = "task41_p0_v6_b0_actual_qmetric"
    requires_prefix_qualification = True
    required_prefix_sample_cell_indices = V6_PREFIX_SAMPLE_CELL_INDICES
    # One-time source extraction/compile is gated separately from each key.
    prepare_workspace_bytes_upper = 1024**3
    key_workspace_bytes_upper = 128 * 1024**2
    class_timing_metadata_bytes_upper = 16 * 1024**2
    workspace_bytes_upper = prepare_workspace_bytes_upper
    helper_scratch_bytes_upper = 128 * 1024**2
    original_kernel_oracle_scratch_bytes_upper = 512 * 1024**2
    original_kernel_oracle_workspace_bytes_upper = 1024**3
    original_kernel_oracle_source_bytes_upper = 2 * EXPECTED_C_SOURCE_BYTES

    @property
    def shared_table_bytes_upper(self) -> int:
        return self._helper.shared_table_bytes_upper

    def __init__(
        self,
        basix_element: Any,
        full_bilinear_form: Any,
        compiled_form: Any,
        *,
        c_source_path: str | Path,
        scratch_directory: str | Path,
    ) -> None:
        from src.solvers.task39extra_p6_raw_tensor import _analyze_original_form

        self.element = basix_element
        self.dimension = int(basix_element.dim)
        if self.dimension != DIMENSION:
            raise NotImplementedError(
                f"V6 actual-qmetric profile requires {DIMENSION} p6 DoFs, got {self.dimension}"
            )
        self.rules_by_tag_component, self.analysis_facts = _analyze_original_form(
            full_bilinear_form
        )
        expected_rules = {
            (tag, component)
            for tag in PROFILE_TAGS
            for component in ("curl", "mass")
        }
        if set(self.rules_by_tag_component) != expected_rules:
            raise NotImplementedError("full-form tag/component inventory differs from frozen V6 profile")
        base_rule = self.rules_by_tag_component[(1, "curl")]
        if len(base_rule.points) != POINT_COUNT:
            raise NotImplementedError("V6 actual-qmetric profile requires the frozen 512-point Q907 rule")
        for key, rule in self.rules_by_tag_component.items():
            if (
                not np.array_equal(rule.points, base_rule.points)
                or not np.array_equal(rule.weights, base_rule.weights)
            ):
                raise NotImplementedError(
                    f"FFCx analyzed quadrature differs for tag/component {key}"
                )
        self._rule = base_rule
        ffi = compiled_form.module.ffi
        signature = ffi.string(compiled_form.ufcx_form.signature).decode("ascii")
        if signature != EXPECTED_UFCX_SIGNATURE:
            raise NotImplementedError("compiled form signature differs from frozen V6 profile")
        module_path = getattr(compiled_form.module, "__file__", None)
        if module_path is None:
            raise NotImplementedError("compiled FFCx module has no stable filesystem identity")
        module_path = Path(module_path).resolve(strict=True)
        module_sha256 = _FrozenFFCxGeometryHelper._file_sha256(module_path)
        if module_sha256 != EXPECTED_UFCX_MODULE_SHA256:
            raise NotImplementedError("compiled FFCx module hash differs from frozen V6 profile")
        self.ffcx_module_path = str(module_path)
        self.ffcx_module_sha256 = module_sha256
        self.expected_ufcx_signature = signature
        self.ffcx_default_kernel_absent: bool | None = None
        self._helper = _FrozenFFCxGeometryHelper(
            Path(c_source_path), Path(scratch_directory)
        )
        self._helper.bind_element(basix_element)
        self._prepared = False
        self.preparation_seconds = 0.0
        self.class_seconds_total = 0.0
        self.class_seconds_max = 0.0
        self.class_count = 0
        self.phase_seconds = {
            "geometry": 0.0,
            "pack": 0.0,
            "gram": 0.0,
            "scatter": 0.0,
            "release": 0.0,
        }
        self.geometry_oracle_comparison_records: list[dict[str, Any]] = []
        self.original_kernel_oracle_records: list[dict[str, Any]] = []
        self.prefix_qualification_records: list[dict[str, Any]] = []
        self._oracle_failed_tags: set[int] = set()
        self._pending_oracle_tensor: tuple[int, bytes, np.ndarray] | None = None
        self._pairs: tuple[tuple[int, int], ...] | None = None
        self._pair_left: np.ndarray | None = None
        self._pair_right: np.ndarray | None = None
        self.evaluator_source_path = Path(__file__).resolve()
        self.evaluator_source_sha256 = _FrozenFFCxGeometryHelper._file_sha256(
            self.evaluator_source_path
        )
        self.cache_identity_payload = {
            "schema": CACHE_IDENTITY_SCHEMA,
            "implementation": self.identity,
            "evaluator_source_sha256": self.evaluator_source_sha256,
            "ffcx_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
            "ffcx_compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
            "ffcx_module_sha256": self.ffcx_module_sha256,
            "ufcx_signature": self.expected_ufcx_signature,
            "reference_table_source_sha256": EXPECTED_C_SOURCE_SHA256,
            "integral_body_by_tag": {
                str(tag): digest for tag, digest in INTEGRAL_BODY_BY_TAG.items()
            },
            "table_extent_contract": {
                "FE0": [1, 1, POINT_COUNT, DIMENSION],
                "FE2": [1, 1, POINT_COUNT, 8],
                "weights": [POINT_COUNT],
            },
            "compiler_flags": list(HELPER_COMPILER_FLAGS),
            "geometry_oracle_trace_schema": GEOMETRY_ORACLE_TRACE_SCHEMA,
        }
        self.cache_identity_sha256 = _cache_identity_digest(
            self.cache_identity_payload
        )
        self.cache_identity = f"{self.identity}:{self.cache_identity_sha256}"

    def validate_compiled_form(self, compiled_form: Any, kernels: dict[int, Any]) -> None:
        if np.dtype(compiled_form.dtype) != np.dtype(np.complex128):
            raise NotImplementedError("V6 actual-qmetric profile requires complex128")
        signature = compiled_form.module.ffi.string(
            compiled_form.ufcx_form.signature
        ).decode("ascii")
        if signature != self.expected_ufcx_signature:
            raise NotImplementedError("actual-qmetric evaluator was bound to another FFCx form")
        if -1 in kernels or set(map(int, kernels)) != PROFILE_TAGS:
            raise NotImplementedError("FFCx integral IDs differ from the frozen V6 profile")
        if any(len(value) != 1 for value in kernels.values()):
            raise NotImplementedError("duplicate FFCx integrals are not qualified by V6")
        self.ffcx_default_kernel_absent = True

    def prepare(self) -> None:
        if self._prepared:
            return
        self._helper.prepare(
            expected_rule_points=self._rule.points,
            expected_rule_weights=self._rule.weights,
        )
        if self._helper.feature_pairs is None:
            raise RuntimeError("frozen helper did not provide its feature-pair map")
        self._pairs = self._helper.feature_pairs
        self._pair_left = np.fromiter(
            (pair[0] for pair in self._pairs), dtype=np.intp, count=144
        )
        self._pair_right = np.fromiter(
            (pair[1] for pair in self._pairs), dtype=np.intp, count=144
        )
        self.preparation_seconds = float(getattr(self._helper, "preparation_seconds", 0.0))
        self._prepared = True

    def build(self, coordinates: np.ndarray, *, tag: int, dimension: int) -> np.ndarray:
        if int(dimension) != DIMENSION or int(tag) not in PROFILE_TAGS:
            raise NotImplementedError("actual-qmetric build key is outside the frozen profile")
        if int(tag) in self._oracle_failed_tags:
            raise RuntimeError("V6 local original-kernel oracle failed; candidate build is blocked")
        coordinate_array = np.asarray(coordinates)
        if self._pending_oracle_tensor is not None:
            pending_tag, pending_coordinates, pending_tensor = self._pending_oracle_tensor
            self._pending_oracle_tensor = None
            if (
                pending_tag == int(tag)
                and coordinate_array.shape == (8, 3)
                and coordinate_array.dtype == np.dtype(np.float64)
                and coordinate_array.flags.c_contiguous
                and coordinate_array.tobytes() == pending_coordinates
            ):
                return pending_tensor
        self.prepare()
        assert self._pairs is not None
        assert self._pair_left is not None and self._pair_right is not None
        started = perf_counter()
        result = np.zeros((DIMENSION, DIMENSION), dtype=np.complex128)
        for start in range(0, POINT_COUNT, self.point_block_size):
            stop = min(start + self.point_block_size, POINT_COUNT)
            geometry_started = perf_counter()
            qvalues = self._helper.geometry_block(int(tag), coordinates, start, stop)
            self.phase_seconds["geometry"] += float(perf_counter() - geometry_started)
            pack_started = perf_counter()
            metric = np.empty((stop - start, 12, 12), dtype=np.complex128)
            metric[:, self._pair_left, self._pair_right] = qvalues
            features = self._helper.reference_block(start, stop)
            self.phase_seconds["pack"] += float(perf_counter() - pack_started)
            block_matrix = assemble_blocked_gram(
                metric, features, self._pairs, phase_seconds=self.phase_seconds
            )
            scatter_started = perf_counter()
            result += block_matrix
            self.phase_seconds["scatter"] += float(perf_counter() - scatter_started)
            release_started = perf_counter()
            del qvalues, metric, features, block_matrix
            self.phase_seconds["release"] += float(perf_counter() - release_started)
        class_seconds = float(perf_counter() - started)
        self.class_count += 1
        self.class_seconds_total += class_seconds
        self.class_seconds_max = max(self.class_seconds_max, class_seconds)
        return np.ascontiguousarray(result, dtype=np.complex128)

    def original_kernel_oracle_source(
        self,
        tag: int,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
    ) -> dict[str, Any]:
        if int(tag) not in PROFILE_TAGS:
            raise ValueError("original-kernel oracle tag is outside the frozen V6 profile")
        if not self._prepared:
            raise RuntimeError("prepare the candidate through the workflow allocation gate before oracle source generation")
        return self._helper.original_kernel_oracle_source(
            tag, allocation_gate=allocation_gate
        )

    def compare_original_kernel_geometry(
        self,
        tag: int,
        coordinates: np.ndarray,
        start: int,
        stop: int,
        original_kernel_trace: np.ndarray,
    ) -> dict[str, Any]:
        if int(tag) not in PROFILE_TAGS:
            raise ValueError("geometry comparison tag is outside the frozen V6 profile")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("geometry comparison q range is outside the frozen Q907 rule")
        coordinate_array = np.asarray(coordinates)
        if (
            coordinate_array.shape != (8, 3)
            or coordinate_array.dtype != np.dtype(np.float64)
            or not coordinate_array.flags.c_contiguous
        ):
            raise ValueError("geometry comparison requires original contiguous float64 (8, 3) coordinates")
        if not self._prepared:
            raise RuntimeError("prepare the candidate through the workflow allocation gate before geometry comparison")
        if len(self.geometry_oracle_comparison_records) >= MAX_GEOMETRY_ORACLE_COMPARISONS:
            raise MemoryError("V6 geometry oracle comparison count exceeds its bounded eight-sample inventory")
        candidate_trace = self._helper.geometry_trace_block(
            tag, coordinates, start, stop
        )
        assert self._helper.geometry_trace_fields is not None
        comparison = compare_geometry_traces(
            candidate_trace,
            original_kernel_trace,
            self._helper.geometry_trace_fields,
        )
        self.geometry_oracle_comparison_records.append(
            {
                "tag": int(tag),
                "q_begin": int(start),
                "q_end": int(stop),
                **comparison,
            }
        )
        return {
            "tag": int(tag),
            "q_begin": int(start),
            "q_end": int(stop),
            **comparison,
        }

    def run_original_kernel_geometry_oracle(
        self,
        tag: int,
        coordinates: np.ndarray,
        start: int,
        stop: int,
        *,
        allocation_gate: Callable[[str, Mapping[str, Any]], None],
        candidate_tensor: np.ndarray | None = None,
        candidate_build_seconds: float | None = None,
    ) -> dict[str, Any]:
        if int(tag) not in PROFILE_TAGS:
            raise ValueError("original-kernel oracle tag is outside the frozen V6 profile")
        if start < 0 or stop > POINT_COUNT or start >= stop:
            raise ValueError("original-kernel oracle q range is outside the frozen Q907 rule")
        coordinate_array = np.asarray(coordinates)
        if (
            coordinate_array.shape != (8, 3)
            or coordinate_array.dtype != np.dtype(np.float64)
            or not coordinate_array.flags.c_contiguous
        ):
            raise ValueError("original-kernel oracle requires original contiguous float64 (8, 3) coordinates")
        if not self._prepared:
            raise RuntimeError("prepare the candidate through the workflow allocation gate before oracle execution")
        if len(self.original_kernel_oracle_records) >= MAX_GEOMETRY_ORACLE_COMPARISONS:
            raise MemoryError("V6 original-kernel oracle count exceeds its bounded eight-sample inventory")
        assert self._helper.geometry_trace_fields is not None
        trace_bytes = int(
            (stop - start)
            * len(self._helper.geometry_trace_fields)
            * np.dtype(np.complex128).itemsize
        )
        comparison_workspace_upper = int(
            3 * trace_bytes + (stop - start) * 144 * np.dtype(np.complex128).itemsize
        )

        def gated_allocation(label: str, facts: Mapping[str, Any]) -> None:
            adjusted = dict(facts)
            if label == "task41_v6_original_kernel_oracle_call":
                adjusted["geometry_comparison_workspace_bytes_upper"] = (
                    comparison_workspace_upper
                )
                adjusted["workspace_bytes"] = int(
                    adjusted.get("workspace_bytes", 0) + comparison_workspace_upper
                )
            allocation_gate(label, adjusted)

        oracle = self._helper.run_original_kernel_geometry_oracle(
            tag,
            coordinate_array,
            start,
            stop,
            allocation_gate=gated_allocation,
        )
        geometry_comparison = self.compare_original_kernel_geometry(
            tag,
            coordinate_array,
            start,
            stop,
            oracle["geometry_trace"],
        )
        tensor_bytes = int(DIMENSION * DIMENSION * np.dtype(np.complex128).itemsize)
        allocation_gate(
            "task41_v6_actual_qmetric_tensor_comparison",
            {
                "additional_payload_bytes": 0,
                "workspace_bytes": int(self.key_workspace_bytes_upper + 2 * tensor_bytes),
                "candidate_key_workspace_bytes_upper": self.key_workspace_bytes_upper,
                "raw_tensor_comparison_workspace_bytes_upper": 2 * tensor_bytes,
                "original_tensor_retained_bytes": tensor_bytes,
                "tag": int(tag),
                "coordinate_shape": list(coordinate_array.shape),
                "frozen_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
                "evaluator_cache_identity": self.cache_identity,
            },
        )
        if candidate_tensor is None:
            candidate_started = perf_counter()
            candidate_tensor = self.build(
                coordinate_array, tag=int(tag), dimension=DIMENSION
            )
            measured_candidate_build_seconds = float(perf_counter() - candidate_started)
        else:
            measured_candidate_build_seconds = float(candidate_build_seconds or 0.0)
        original_tensor = np.asarray(oracle["tensor"], dtype=np.complex128)
        candidate_tensor = np.asarray(candidate_tensor, dtype=np.complex128)
        if (
            original_tensor.shape != (DIMENSION, DIMENSION)
            or candidate_tensor.shape != (DIMENSION, DIMENSION)
            or not np.isfinite(original_tensor).all()
            or not np.isfinite(candidate_tensor).all()
        ):
            raise ValueError("original-kernel and candidate tensors must be finite complex128 882x882 arrays")
        difference = candidate_tensor - original_tensor
        original_norm = float(np.linalg.norm(original_tensor.ravel()))
        absolute_frobenius = float(np.linalg.norm(difference.ravel()))
        relative_frobenius = absolute_frobenius / max(
            original_norm, np.finfo(float).tiny
        )
        max_abs = float(np.max(np.abs(difference), initial=0.0))
        tensor_comparison = {
            "status": "PASS_SCREEN" if relative_frobenius <= 1.0e-11 else "FAIL_SCREEN",
            "relative_frobenius": relative_frobenius,
            "absolute_frobenius": absolute_frobenius,
            "max_abs": max_abs,
            "relative_limit": 1.0e-11,
        }
        original_tensor_sha256 = hashlib.sha256(
            memoryview(np.ascontiguousarray(original_tensor)).cast("B")
        ).hexdigest()
        candidate_tensor_sha256 = hashlib.sha256(
            memoryview(np.ascontiguousarray(candidate_tensor)).cast("B")
        ).hexdigest()
        record = {
            "tag": int(tag),
            "q_begin": int(start),
            "q_end": int(stop),
            "execution_status": oracle["execution_status"],
            "kernel_call_seconds": float(oracle["kernel_call_seconds"]),
            "output_allocation_seconds": float(oracle["output_allocation_seconds"]),
            "source_generation_seconds": float(
                oracle["compile_audit"].get("source_generation_seconds", 0.0)
            ),
            "compiler_seconds": float(
                oracle["compile_audit"].get("compiler_seconds", 0.0)
            ),
            "candidate_build_seconds": measured_candidate_build_seconds,
            "coordinates_shape": list(coordinate_array.shape),
            "coordinates_dtype": str(coordinate_array.dtype),
            "coordinates_sha256": hashlib.sha256(
                memoryview(np.ascontiguousarray(coordinate_array)).cast("B")
            ).hexdigest(),
            "original_tensor_sha256": original_tensor_sha256,
            "candidate_tensor_sha256": candidate_tensor_sha256,
            "tensor_comparison": tensor_comparison,
            "geometry_comparison": geometry_comparison,
            "compile_audit": dict(oracle["compile_audit"]),
        }
        self.original_kernel_oracle_records.append(record)
        oracle_passed = bool(
            tensor_comparison["status"] == "PASS_SCREEN"
            and geometry_comparison.get("status") == "BITWISE_EQUAL"
        )
        if not oracle_passed:
            self._pending_oracle_tensor = None
            self._oracle_failed_tags.add(int(tag))
        elif candidate_build_seconds is None:
            self._pending_oracle_tensor = (
                int(tag),
                coordinate_array.tobytes(),
                candidate_tensor,
            )
        else:
            # The production builder already owns this candidate tensor. Keep it
            # there and do not enqueue a duplicate build result for a later call.
            self._pending_oracle_tensor = None
        oracle.update(
            {
                "candidate_tensor": candidate_tensor,
                "tensor_comparison": tensor_comparison,
                "candidate_build_seconds": candidate_build_seconds,
                "geometry_comparison": geometry_comparison,
                "original_tensor_sha256": original_tensor_sha256,
                "candidate_tensor_sha256": candidate_tensor_sha256,
            }
        )
        return oracle

    def record_prefix_qualification(self, record: Mapping[str, Any]) -> None:
        """Retain each measured prefix result before the full-admission gate."""

        if len(self.prefix_qualification_records) >= len(V6_PREFIX_SAMPLE_CELL_INDICES):
            raise RuntimeError("V6 prefix qualification exceeds its frozen eight-key inventory")
        cell_index = record.get("cell_index")
        if type(cell_index) is not int or cell_index not in V6_PREFIX_SAMPLE_CELL_INDICES:
            raise ValueError("V6 prefix qualification cell is outside the frozen eight-key inventory")
        if any(item.get("cell_index") == cell_index for item in self.prefix_qualification_records):
            raise ValueError("V6 prefix qualification contains a duplicate sample cell")
        self.prefix_qualification_records.append(dict(record))

    def prefix_qualification_audit(self) -> dict[str, Any]:
        records = [dict(record) for record in self.prefix_qualification_records]
        by_cell = {record.get("cell_index"): record for record in records}
        complete = (
            len(records) == len(V6_PREFIX_SAMPLE_CELL_INDICES)
            and set(by_cell) == set(V6_PREFIX_SAMPLE_CELL_INDICES)
        )
        all_pass = complete and all(
            record.get("status") == "PASS" for record in records
        )
        geometry_witness_count = sum(
            record.get("geometry_witness", {}).get("status") == "BITWISE_EQUAL"
            for record in records
            if isinstance(record.get("geometry_witness"), Mapping)
        )
        if all_pass and geometry_witness_count < 1:
            all_pass = False
        status = (
            "PREFIX_QUALIFIED"
            if all_pass
            else "P0_NOT_RUN_NO_WINDOW_APPROVAL"
            if not records
            else "PREFIX_QUALIFICATION_INCOMPLETE_OR_FAILED"
        )
        return {
            "schema": V6_PREFIX_QUALIFICATION_SCHEMA,
            "status": status,
            "required_sample_cell_indices": list(V6_PREFIX_SAMPLE_CELL_INDICES),
            "sample_count": len(records),
            "required_sample_count": len(V6_PREFIX_SAMPLE_CELL_INDICES),
            "geometry_witness_count": int(geometry_witness_count),
            "full_admission_eligible": bool(all_pass),
            "records": records,
        }

    def __call__(
        self,
        compiled_form: Any,
        kernels: dict[int, Any],
        coordinates: np.ndarray,
        *,
        tag: int,
        dimension: int,
    ) -> np.ndarray:
        self.validate_compiled_form(compiled_form, kernels)
        return self.build(coordinates, tag=tag, dimension=dimension)

    def audit(self) -> dict[str, Any]:
        return {
            "implementation": self.identity,
            "qualification_status": QUALIFICATION_STATUS,
            "full_form_signature": self.analysis_facts["full_form_signature"],
            "integral_rule_records": list(self.analysis_facts["integral_rule_records"]),
            "integral_counts_by_tag": dict(self.analysis_facts["integral_counts_by_tag"]),
            "expected_ufcx_signature": self.expected_ufcx_signature,
            "ffcx_module_path": self.ffcx_module_path,
            "ffcx_module_sha256": self.ffcx_module_sha256,
            "ffcx_default_kernel_absent": self.ffcx_default_kernel_absent,
            "integral_body_by_tag": dict(INTEGRAL_BODY_BY_TAG),
            "point_block_size": self.point_block_size,
            "cache_identity": self.cache_identity,
            "cache_identity_sha256": self.cache_identity_sha256,
            "cache_identity_payload": dict(self.cache_identity_payload),
            "evaluator_source_path": str(self.evaluator_source_path),
            "evaluator_source_sha256": self.evaluator_source_sha256,
            "workspace_bytes_upper": self.workspace_bytes_upper,
            "prepare_workspace_bytes_upper": self.prepare_workspace_bytes_upper,
            "key_workspace_bytes_upper": self.key_workspace_bytes_upper,
            "class_timing_metadata_bytes_upper": (
                self.class_timing_metadata_bytes_upper
            ),
            "helper_scratch_bytes_upper": self.helper_scratch_bytes_upper,
            "original_kernel_oracle_scratch_bytes_upper": (
                self.original_kernel_oracle_scratch_bytes_upper
            ),
            "original_kernel_oracle_workspace_bytes_upper": (
                self.original_kernel_oracle_workspace_bytes_upper
            ),
            "original_kernel_oracle_source_bytes_upper": (
                self.original_kernel_oracle_source_bytes_upper
            ),
            "reference_table_bytes": self._helper.reference_table_bytes,
            "shared_table_bytes_upper": self._helper.shared_table_bytes_upper,
            "prepare_seconds": self.preparation_seconds,
            "class_count": self.class_count,
            "class_seconds_summary": {
                "count": self.class_count,
                "total": self.class_seconds_total,
                "max": self.class_seconds_max,
            },
            "class_timing_metadata_bytes": int(
                sys.getsizeof(self.class_count)
                + sys.getsizeof(self.class_seconds_total)
                + sys.getsizeof(self.class_seconds_max)
                + sys.getsizeof(self.phase_seconds)
                + sum(
                    sys.getsizeof(key) + sys.getsizeof(value)
                    for key, value in self.phase_seconds.items()
                )
            ),
            "phase_seconds_by_stage": dict(self.phase_seconds),
            "geometry_oracle_comparison_records": [
                dict(record) for record in self.geometry_oracle_comparison_records
            ],
            "original_kernel_oracle_records": [
                dict(record) for record in self.original_kernel_oracle_records
            ],
            "prefix_qualification": self.prefix_qualification_audit(),
            "mass_coefficient_conjugated": False,
            "hermitian_assumption": False,
            "raw_tensor_built_before_original_schur": True,
            "geometry_helper": self._helper.audit(),
        }
