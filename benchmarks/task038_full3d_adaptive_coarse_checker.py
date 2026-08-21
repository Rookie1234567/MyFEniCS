"""Pure read-only checker for the D1 adaptive coarse fixture evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np


D1_SCHEMA = "task038.full3d.iterative.adaptive-coarse-record.v1"
D1_CHECK_SCHEMA = "task038.full3d.iterative.adaptive-coarse-check.v1"
D1_PROFILE = "adaptive_trace_harmonic_two_level_v1"
D1_SERIAL_FIXTURE = "serial_p2_p3_assembled_oracle_only"
D1_MPI2_SERIAL_BOUNDARY = (
    "distributed_action_identity_only; serial assembled algebra is MPI1-only"
)
D1_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
D1_CASES = {
    "p2-mpi1": {"degree": 2, "mpi_size": 1},
    "p2-mpi2": {"degree": 2, "mpi_size": 2},
    "p3-mpi1": {"degree": 3, "mpi_size": 1},
    "p3-mpi2": {"degree": 3, "mpi_size": 2},
}
EXPECTED_WAVELENGTH_NM = 13.5
EXPECTED_THETA_DEG = 21.131
EXPECTED_PHI_DEG = 33.690
EXPECTED_SOURCE_FORMULA = "complex_value=stable_sha256(canonical_full_fe_key)"
EXPECTED_SOURCE_KEY_IDENTITY = (
    "physical full_fe canonical key; no local row/rank/mpi-size input"
)
CANONICAL_LIMIT = 1.0e-12
HERMITIAN_LIMIT = 1.0e-12
EIGEN_LIMIT = 1.0e-10
ADJOINT_LIMIT = 1.0e-11
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _obj(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} is missing or not an object")
        return {}
    return value


def _path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact relative path is invalid")
    target = (root / relative).resolve()
    target.relative_to(root.resolve())
    return target


def _key_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _read_manifest(
    raw_dir: Path,
    descriptor: dict[str, Any],
    errors: list[str],
    name: str,
    *,
    expected_name: str,
    expected_role: str,
    expected_mpi_size: int,
) -> dict[str, Any]:
    packets: dict[str, complex] = {}
    try:
        manifest_path = _path(raw_dir, descriptor.get("relative_path"))
    except (TypeError, ValueError, OSError) as exc:
        errors.append(f"{name} manifest path is invalid: {exc}")
        return {"packets": packets, "count": 0, "duplicates": 0, "finite": False}
    if not manifest_path.is_file():
        errors.append(f"{name} manifest is missing")
        return {"packets": packets, "count": 0, "duplicates": 0, "finite": False}
    expected_kind = (
        "physical_hcurl_primal_packet_manifest"
        if expected_role == "full_fe"
        else "physical_hcurl_dual_packet_manifest"
    )
    if descriptor.get("kind") != expected_kind:
        errors.append(f"{name} manifest kind is invalid")
    if descriptor.get("name") != expected_name:
        errors.append(f"{name} descriptor name mismatch")
    if descriptor.get("role") != expected_role:
        errors.append(f"{name} descriptor role mismatch")
    if descriptor.get("bytes") != manifest_path.stat().st_size:
        errors.append(f"{name} manifest byte count mismatch")
    if descriptor.get("sha256") != _sha256(manifest_path):
        errors.append(f"{name} manifest SHA mismatch")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{name} manifest is unreadable: {exc}")
        return {"packets": packets, "count": 0, "duplicates": 0, "finite": False}
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        errors.append(f"{name} manifest schema mismatch")
    if manifest.get("dtype") != "complex128":
        errors.append(f"{name} manifest dtype mismatch")
    if manifest.get("role") != expected_role:
        errors.append(f"{name} manifest role mismatch")
    if descriptor.get("mpi_size") != expected_mpi_size:
        errors.append(f"{name} descriptor MPI size mismatch")
    if manifest.get("mpi_size") != expected_mpi_size:
        errors.append(f"{name} manifest MPI size mismatch")
    if descriptor.get("mpi_size") != manifest.get("mpi_size"):
        errors.append(f"{name} descriptor/manifest MPI size mismatch")
    extractor_audit = manifest.get("extractor_audit")
    if not isinstance(extractor_audit, dict) or extractor_audit.get("role") != expected_role:
        errors.append(f"{name} extractor audit role mismatch")
    shards = manifest.get("per_rank_shards")
    if not isinstance(shards, list) or len(shards) != expected_mpi_size:
        errors.append(f"{name} shard list is missing")
        return {"packets": packets, "count": 0, "duplicates": 0, "finite": False}
    total = 0
    duplicates = 0
    finite = True
    for shard in shards:
        if not isinstance(shard, dict) or not isinstance(shard.get("filename"), str):
            errors.append(f"{name} shard descriptor is invalid")
            continue
        shard_name = shard["filename"]
        shard_path = (manifest_path.parent / shard_name).resolve()
        try:
            shard_path.relative_to(raw_dir.resolve())
        except ValueError:
            errors.append(f"{name} shard escapes raw directory: {shard_name}")
            continue
        if not shard_path.is_file():
            errors.append(f"{name} shard is missing: {shard_name}")
            continue
        if shard.get("file_sha256") != _sha256(shard_path):
            errors.append(f"{name} shard SHA mismatch: {shard_name}")
        local_keys: set[str] = set()
        count = 0
        try:
            lines = shard_path.read_text(encoding="utf-8").splitlines()
            for line_number, line in enumerate(lines, 1):
                item = json.loads(line)
                if item.get("schema_version") != SHARD_SCHEMA:
                    errors.append(f"{name} shard schema mismatch: {shard_name}:{line_number}")
                key_payload = item.get("key")
                tuple_payload = (
                    key_payload.get("tuple")
                    if isinstance(key_payload, dict)
                    else None
                )
                if (
                    not isinstance(tuple_payload, list)
                    or not tuple_payload
                    or tuple_payload[0] != expected_role
                ):
                    errors.append(f"{name} canonical key role mismatch: {shard_name}:{line_number}")
                key_bytes = _key_json(key_payload)
                if item.get("key_sha256") != hashlib.sha256(key_bytes).hexdigest():
                    errors.append(f"{name} key SHA mismatch: {shard_name}:{line_number}")
                value = item.get("value")
                if not isinstance(value, list) or len(value) != 2 or not all(_finite(x) for x in value):
                    errors.append(f"{name} coefficient is invalid: {shard_name}:{line_number}")
                    finite = False
                    continue
                key = key_bytes.decode("utf-8")
                if key in local_keys or key in packets:
                    duplicates += 1
                    errors.append(f"{name} duplicate key: {shard_name}:{line_number}")
                local_keys.add(key)
                packets[key] = complex(float(value[0]), float(value[1]))
                count += 1
        except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"{name} shard is unreadable: {shard_name}: {exc}")
        if shard.get("packet_count") != count:
            errors.append(f"{name} shard packet count mismatch: {shard_name}")
        if shard.get("local_duplicate_count") != 0:
            errors.append(f"{name} shard reports duplicates: {shard_name}")
        total += count
    if manifest.get("global_summed_packet_count") != total:
        errors.append(f"{name} global packet count mismatch")
    if manifest.get("summed_local_duplicate_count") != 0 or duplicates:
        errors.append(f"{name} duplicate count is nonzero")
    if descriptor.get("packet_count") != total:
        errors.append(f"{name} descriptor packet count mismatch")
    if descriptor.get("mpi_size") != manifest.get("mpi_size"):
        errors.append(f"{name} descriptor MPI size mismatch")
    return {"packets": packets, "count": total, "duplicates": duplicates, "finite": finite}


def _relative_packets(left: dict[str, complex], right: dict[str, complex]) -> dict[str, Any]:
    left_keys = set(left)
    right_keys = set(right)
    common = sorted(left_keys & right_keys)
    if common:
        left_values = np.asarray([left[key] for key in common], dtype=np.complex128)
        right_values = np.asarray([right[key] for key in common], dtype=np.complex128)
        relative = float(
            np.linalg.norm(left_values - right_values)
            / max(np.linalg.norm(right_values), np.finfo(float).tiny)
        )
    else:
        relative = float("inf")
    return {
        "left_count": len(left),
        "right_count": len(right),
        "common_count": len(common),
        "missing_key_count": len(right_keys - left_keys),
        "extra_key_count": len(left_keys - right_keys),
        "relative_l2": relative,
        "limit": CANONICAL_LIMIT,
        "pass": bool(
            left_keys == right_keys and relative <= CANONICAL_LIMIT
        ),
    }


def _relative_hermitian(matrix: np.ndarray) -> float:
    return float(
        np.linalg.norm(matrix - matrix.conj().T)
        / max(float(np.linalg.norm(matrix)), np.finfo(float).tiny)
    )


def _serial_algebra(
    raw_dir: Path, descriptor: dict[str, Any], errors: list[str]
) -> dict[str, Any]:
    try:
        path = _path(raw_dir, descriptor.get("relative_path"))
    except (TypeError, ValueError, OSError) as exc:
        errors.append(f"serial algebra path is invalid: {exc}")
        return {}
    if not path.is_file():
        errors.append("serial algebra raw NPZ is missing")
        return {}
    if descriptor.get("bytes") != path.stat().st_size or descriptor.get("sha256") != _sha256(path):
        errors.append("serial algebra raw NPZ hash/bytes mismatch")
    try:
        data = np.load(path, allow_pickle=False)
    except (OSError, ValueError, EOFError) as exc:
        errors.append(f"serial algebra NPZ is unreadable: {exc}")
        return {}
    facts: dict[str, Any] = {"slabs": {}}
    try:
        for slab_id in (0, 1):
            prefix = f"slab{slab_id}"
            names = {
                "B": f"B_slab{slab_id}",
                "M": f"M_slab{slab_id}",
                "active_free_positions": f"active_free_positions_slab{slab_id}",
                "trace_free_positions": f"trace_free_positions_slab{slab_id}",
                "interior_free_positions": f"interior_free_positions_slab{slab_id}",
                "block": f"block_slab{slab_id}",
                "mass_trace": f"mass_trace_slab{slab_id}",
                "K": f"stiffness_slab{slab_id}",
                "trace_positions": f"trace_positions_slab{slab_id}",
                "interior_positions": f"interior_positions_slab{slab_id}",
                "trace_values": f"trace_values_slab{slab_id}",
                "harmonic": f"harmonic_slab{slab_id}",
                "harmonic_first": f"harmonic_first_slab{slab_id}",
                "harmonic_second": f"harmonic_second_slab{slab_id}",
                "eigenvalues": f"eigenvalues_slab{slab_id}",
                "eigenvectors": f"eigenvectors_slab{slab_id}",
                "eigenvalues_repeat": f"eigenvalues_repeat_slab{slab_id}",
                "eigenvectors_repeat": f"eigenvectors_repeat_slab{slab_id}",
            }
            missing = [name for name in names.values() if name not in data]
            if missing:
                errors.append(f"serial algebra {prefix} arrays are missing")
                continue
            try:
                arrays = {key: np.asarray(data[name]) for key, name in names.items()}
                finite = bool(all(np.all(np.isfinite(value)) for value in arrays.values()))
                B = np.asarray(arrays["B"], dtype=np.complex128)
                M = np.asarray(arrays["M"], dtype=np.complex128)
                active = np.asarray(arrays["active_free_positions"], dtype=np.int64)
                trace = np.asarray(arrays["trace_free_positions"], dtype=np.int64)
                interior = np.asarray(arrays["interior_free_positions"], dtype=np.int64)
                block = np.asarray(arrays["block"], dtype=np.complex128)
                mass = np.asarray(arrays["mass_trace"], dtype=np.complex128)
                stiffness = np.asarray(arrays["K"], dtype=np.complex128)
                trace_positions = np.asarray(arrays["trace_positions"], dtype=np.int64)
                interior_positions = np.asarray(arrays["interior_positions"], dtype=np.int64)
                trace_values = np.asarray(arrays["trace_values"], dtype=np.complex128)
                harmonic = np.asarray(arrays["harmonic"], dtype=np.complex128)
                first = np.asarray(arrays["harmonic_first"], dtype=np.complex128)
                second = np.asarray(arrays["harmonic_second"], dtype=np.complex128)
                eigenvalues = np.asarray(arrays["eigenvalues"], dtype=np.float64)
                eigenvectors = np.asarray(arrays["eigenvectors"], dtype=np.complex128)
                eigenvalues_repeat = np.asarray(
                    arrays["eigenvalues_repeat"], dtype=np.float64
                )
                eigenvectors_repeat = np.asarray(
                    arrays["eigenvectors_repeat"], dtype=np.complex128
                )
                if (
                    B.ndim != 2
                    or B.shape[0] != B.shape[1]
                    or M.shape != B.shape
                    or active.ndim != 1
                    or trace.ndim != 1
                    or interior.ndim != 1
                    or block.shape != (active.size, active.size)
                    or mass.shape != (trace.size, trace.size)
                    or trace_values.shape != trace.shape
                    or harmonic.shape != (active.size, trace.size)
                    or first.shape != (active.size,)
                    or second.shape != (active.size,)
                    or stiffness.shape != (trace.size, trace.size)
                    or eigenvalues.shape != (min(16, trace.size),)
                    or eigenvectors.shape != (trace.size, min(16, trace.size))
                    or eigenvalues_repeat.shape != eigenvalues.shape
                    or eigenvectors_repeat.shape != eigenvectors.shape
                ):
                    raise ValueError("serial algebra array shapes do not close")
                all_rows = np.concatenate((trace, interior))
                if (
                    np.unique(active).size != active.size
                    or np.unique(trace).size != trace.size
                    or np.unique(interior).size != interior.size
                    or np.any(trace < 0)
                    or np.any(interior < 0)
                    or not np.all(np.isin(trace, active))
                    or not np.all(np.isin(interior, active))
                    or not np.array_equal(np.sort(all_rows), np.sort(active))
                ):
                    raise ValueError("serial algebra support indices do not close")
                if not np.array_equal(block, B[np.ix_(active, active)]):
                    raise ValueError("serial block is not B[active,active]")
                if not np.array_equal(mass, M[np.ix_(trace, trace)]):
                    raise ValueError("serial trace mass is not M[trace,trace]")
                block_positions = {int(row): index for index, row in enumerate(active)}
                expected_trace_positions = np.asarray(
                    [block_positions[int(row)] for row in trace], dtype=np.int64
                )
                expected_interior_positions = np.asarray(
                    [block_positions[int(row)] for row in interior], dtype=np.int64
                )
                if not np.array_equal(trace_positions, expected_trace_positions):
                    raise ValueError("serial trace block positions do not close")
                if not np.array_equal(interior_positions, expected_interior_positions):
                    raise ValueError("serial interior block positions do not close")
                expected_harmonic = np.zeros_like(harmonic)
                for column in range(trace.size):
                    expected_harmonic[trace_positions[column], column] = 1.0 + 0.0j
                    if interior_positions.size:
                        expected_harmonic[interior_positions, column] = np.linalg.solve(
                            block[np.ix_(interior_positions, interior_positions)],
                            -block[np.ix_(interior_positions, trace_positions)]
                            @ expected_harmonic[trace_positions, column],
                        )
                if not np.allclose(expected_harmonic, harmonic, rtol=0.0, atol=0.0):
                    raise ValueError("stored harmonic columns do not close")
                expected_stiffness = harmonic.conj().T @ block @ harmonic
                stiffness_error = float(
                    np.linalg.norm(stiffness - expected_stiffness)
                    / max(np.linalg.norm(expected_stiffness), np.finfo(float).tiny)
                )
                if stiffness_error > 1.0e-14:
                    raise ValueError("stored stiffness is not H^H B H")
                expected_extension = np.zeros(active.size, dtype=np.complex128)
                expected_extension[trace_positions] = trace_values
                if interior_positions.size:
                    expected_extension[interior_positions] = np.linalg.solve(
                        block[np.ix_(interior_positions, interior_positions)],
                        -block[np.ix_(interior_positions, trace_positions)] @ trace_values,
                    )
                eigen_residuals = []
                for index, eigenvalue in enumerate(eigenvalues):
                    left = stiffness @ eigenvectors[:, index]
                    right = eigenvalue * (mass @ eigenvectors[:, index])
                    eigen_residuals.append(
                        np.linalg.norm(left - right)
                        / max(
                            float(np.linalg.norm(left)),
                            float(np.linalg.norm(right)),
                            np.finfo(float).tiny,
                        )
                    )
                normalization = eigenvectors.conj().T @ mass @ eigenvectors
                facts["slabs"][prefix] = {
                    "auxiliary_hermitian_defect": _relative_hermitian(B),
                    "interface_mass_hermitian_defect": _relative_hermitian(M),
                    "support_block_hermitian_defect": _relative_hermitian(block),
                    "stiffness_hermitian_defect": _relative_hermitian(stiffness),
                    "stiffness_relation_error": stiffness_error,
                    "eigen_residual": float(max(eigen_residuals, default=0.0)),
                    "eigen_residual_limit": EIGEN_LIMIT,
                    "eigen_rank": int(eigenvalues.size),
                    "expected_eigen_rank": min(16, int(trace.size)),
                    "eigen_ascending": bool(
                        eigenvalues.size < 2 or np.all(np.diff(eigenvalues) >= 0.0)
                    ),
                    "eigen_repeat_exact": bool(
                        np.array_equal(eigenvalues, eigenvalues_repeat)
                        and np.array_equal(eigenvectors, eigenvectors_repeat)
                    ),
                    "eigen_mass_normalization_error": float(
                        np.linalg.norm(
                            normalization
                            - np.eye(eigenvectors.shape[1], dtype=np.complex128)
                        )
                    ),
                    "extension_relative_error": float(
                        np.linalg.norm(first - expected_extension)
                        / max(np.linalg.norm(expected_extension), np.finfo(float).tiny)
                    ),
                    "extension_repeat_relative_error": float(
                        np.linalg.norm(first - second)
                        / max(np.linalg.norm(second), np.finfo(float).tiny)
                    ),
                    "extension_repeat_exact": bool(np.array_equal(first, second)),
                    "finite": finite,
                }
            except (IndexError, KeyError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
                errors.append(f"serial algebra {prefix} relation/shape failure: {exc}")
        if "rp_volume" not in data or "rp_trace" not in data or "rp_restricted" not in data or "rp_prolonged" not in data:
            errors.append("serial R/P raw arrays are missing")
        else:
            try:
                volume = np.asarray(data["rp_volume"], dtype=np.complex128)
                trace = np.asarray(data["rp_trace"], dtype=np.complex128)
                restricted = np.asarray(data["rp_restricted"], dtype=np.complex128)
                prolonged = np.asarray(data["rp_prolonged"], dtype=np.complex128)
                if (
                    volume.ndim != 1
                    or trace.ndim != 1
                    or restricted.shape != trace.shape
                    or prolonged.shape != volume.shape
                ):
                    raise ValueError("serial R/P array shapes do not close")
                lhs = np.vdot(restricted, trace)
                rhs = np.vdot(volume, prolonged)
                facts["restriction_prolongation_adjoint_relative_error"] = float(
                    abs(lhs - rhs) / max(abs(lhs), np.finfo(float).tiny)
                )
            except (TypeError, ValueError) as exc:
                errors.append(f"serial R/P relation/shape failure: {exc}")
    finally:
        data.close()
    return facts


def _check_source(record: dict[str, Any], errors: list[str]) -> None:
    source = _obj(record.get("source"), "source", errors)
    expected = source.get("expected_sha")
    sha_values = (expected, source.get("commit_sha_start"), source.get("commit_sha_end"))
    valid_sha = all(
        isinstance(value, str)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
        for value in sha_values
    )
    if not valid_sha or not (expected == source.get("commit_sha_start") == source.get("commit_sha_end")):
        errors.append("source SHA is not exact and bound")
    for key, expected_value in {
        "branch": D1_BRANCH,
        "clean_start": True,
        "clean_end": True,
        "tracked_status_start": "",
        "tracked_status_end": "",
    }.items():
        if source.get(key) != expected_value:
            errors.append(f"source identity mismatch: {key}")


def _check_runtime(record: dict[str, Any], errors: list[str]) -> None:
    runtime = _obj(record.get("runtime"), "runtime", errors)
    if runtime.get("qualified_marker") != "1":
        errors.append("qualified activation marker is not recorded as 1")
    if runtime.get("petsc_scalar_type") != "complex128":
        errors.append("PETSc scalar type is not complex128")
    if runtime.get("petsc_int_type") != "int32":
        errors.append("PETSc integer type is not int32")
    executable = runtime.get("sys_executable")
    if not isinstance(executable, str) or "/.venv/" not in executable:
        errors.append("runtime executable is not repository .venv-bound")


def _check_model(record: dict[str, Any], errors: list[str]) -> None:
    model = _obj(record.get("model"), "model", errors)
    expected = {
        "wavelength_nm": EXPECTED_WAVELENGTH_NM,
        "incident_theta_deg": EXPECTED_THETA_DEG,
        "incident_phi_deg": EXPECTED_PHI_DEG,
        "source_formula": EXPECTED_SOURCE_FORMULA,
        "source_key_identity": EXPECTED_SOURCE_KEY_IDENTITY,
    }
    for key, expected_value in expected.items():
        if model.get(key) != expected_value:
            errors.append(f"model identity mismatch: {key}")


def _check_source_values(source: dict[str, Any], errors: list[str]) -> None:
    packets = source.get("packets", {})
    expected_values = []
    actual_values = []
    for key_json, value in packets.items():
        try:
            key_bytes = key_json.encode("utf-8")
            digest = hashlib.sha256(key_bytes).digest()
            expected_values.append(
                complex(
                    0.25 + 0.5 * int.from_bytes(digest[:8], "big") / float(1 << 64),
                    -0.20 + 0.4 * int.from_bytes(digest[8:16], "big") / float(1 << 64),
                )
            )
            actual_values.append(value)
        except (TypeError, ValueError):
            errors.append("source canonical key encoding is invalid")
    if expected_values:
        expected = np.asarray(expected_values, dtype=np.complex128)
        actual = np.asarray(actual_values, dtype=np.complex128)
        relative = float(
            np.linalg.norm(actual - expected)
            / max(np.linalg.norm(expected), np.finfo(float).tiny)
        )
        if relative > 1.0e-15:
            errors.append("source values do not match the frozen key formula")


def _check_topology(record: dict[str, Any], errors: list[str]) -> None:
    topology = _obj(record.get("topology"), "topology", errors)
    for key, expected in {"profile": "full3d_scalable_v1", "slab_count": 2}.items():
        if topology.get(key) != expected:
            errors.append(f"topology mismatch: {key}")
    for key in ("global_facet_count", "local_facet_count", "owned_trace_rows"):
        if not isinstance(topology.get(key), int) or topology[key] <= 0:
            errors.append(f"topology count is invalid: {key}")
    if not isinstance(topology.get("ghost_trace_rows"), int) or topology["ghost_trace_rows"] < 0:
        errors.append("topology ghost row count is invalid")
    digest = topology.get("canonical_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        errors.append("topology canonical digest is invalid")
    rp_error = topology.get("restriction_prolongation_adjoint_relative_error")
    if not _finite(rp_error) or float(rp_error) > 1.0e-11:
        errors.append("topology restriction/prolongation adjoint gate failed")
    if topology.get("owner_closure") is not True:
        errors.append("topology owner closure is not true")
    if set(topology.get("interface_classifications", ())) != {"homogeneous", "nonhomogeneous"}:
        errors.append("topology material classes are incomplete")
    if topology.get("floquet_phase_nontrivial") is not True:
        errors.append("topology phase nontriviality is absent")
    plan = _obj(topology.get("neighbor_plan"), "topology.neighbor_plan", errors)
    mpi_size = record.get("mpi_size")
    for name in (
        "forward_send_peers",
        "forward_recv_peers",
        "backward_send_peers",
        "backward_recv_peers",
        "lower_participant_ranks",
        "upper_participant_ranks",
    ):
        peers = plan.get(name)
        if not isinstance(peers, list) or any(
            not isinstance(peer, int) or peer < 0 or peer >= mpi_size for peer in peers
        ):
            errors.append(f"topology neighbor plan is invalid: {name}")
    audit = _obj(topology.get("audit"), "topology.audit", errors)
    for key, expected in {
        "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
        "phase_application": "finalized_floquet_mpc_once",
        "bounded_material_class_collective": True,
        "numeric_allgather": False,
        "global_aij_materialized": False,
        "dense_interface_mass_materialized": False,
        "dense_interface_schur_materialized": False,
        "slab_factor_materialized": False,
        "slave_rows_excluded": True,
    }.items():
        if audit.get(key) != expected:
            errors.append(f"topology audit mismatch: {key}")


def _check_definitions(record: dict[str, Any], errors: list[str]) -> None:
    definitions = _obj(record.get("definitions"), "definitions", errors)
    for slab in ("slab0", "slab1"):
        audit = _obj(definitions.get(slab), f"definitions.{slab}", errors)
        for key, expected in {
            "profile": D1_PROFILE,
            "slab_id": int(slab[-1]),
            "auxiliary_form": "curl_curl_plus_k0_squared_abs_epsilon_mass",
            "coercive_coefficient": "k0**2*abs(epsilon_r(x))",
            "source_independent": True,
            "restriction_prolongation": "owner_active_rows_unit_weight_euclidean",
            "interface_mass": "broken_tangential_facet_mass_dS",
            "phase_application": "finalized_floquet_mpc_once",
            "slave_rows_excluded_from_action": True,
            "fixture_assembled_oracle": "p2_p3_only",
            "future_p6_backend": "owner_local_matrix_free",
            "global_numeric_allgather": False,
            "global_aij_materialized": False,
            "global_schur_materialized": False,
            "growing_factor_materialized": False,
        }.items():
            if audit.get(key) != expected:
                errors.append(f"definition audit mismatch: {slab}.{key}")


def _check_artifacts(
    record: dict[str, Any], raw_dir: Path, errors: list[str]
) -> tuple[dict[str, Any], dict[str, Any]]:
    artifacts = _obj(record.get("artifacts"), "artifacts", errors)
    expected_mpi_size = record.get("mpi_size")
    source_descriptor = artifacts.get("source")
    if not isinstance(source_descriptor, dict):
        errors.append("source canonical descriptor is missing")
        source = {"packets": {}, "count": 0, "duplicates": 0, "finite": False}
    else:
        source = _read_manifest(
            raw_dir,
            source_descriptor,
            errors,
            "source",
            expected_name="source",
            expected_role="full_fe",
            expected_mpi_size=expected_mpi_size,
        )
    operators: dict[str, Any] = {}
    for slab in ("slab0", "slab1"):
        slab_artifacts = _obj(artifacts.get("operators", {}).get(slab), f"artifacts.operators.{slab}", errors)
        operators[slab] = {}
        for name in ("B", "M_Gamma"):
            state = _obj(slab_artifacts.get(name), f"artifacts.operators.{slab}.{name}", errors)
            action_descriptor = state.get("action")
            repeat_descriptor = state.get("repeat")
            if not isinstance(action_descriptor, dict) or not isinstance(repeat_descriptor, dict):
                errors.append(f"{slab}.{name} action/repeat descriptor is missing")
                continue
            artifact_name = f"{'M' if name == 'M_Gamma' else name}_slab{slab[-1]}"
            action = _read_manifest(
                raw_dir,
                action_descriptor,
                errors,
                f"{slab}.{name}.action",
                expected_name=artifact_name,
                expected_role="full_fe_dual",
                expected_mpi_size=expected_mpi_size,
            )
            repeat = _read_manifest(
                raw_dir,
                repeat_descriptor,
                errors,
                f"{slab}.{name}.repeat",
                expected_name=f"{artifact_name}_repeat",
                expected_role="full_fe_dual",
                expected_mpi_size=expected_mpi_size,
            )
            comparison = _relative_packets(action["packets"], repeat["packets"])
            if not comparison["pass"]:
                errors.append(f"{slab}.{name} repeat determinism gate failed")
            operators[slab][name] = {
                "action": action,
                "repeat": repeat,
                "repeat_comparison": comparison,
            }
    return source, operators


def _check_record_internal(record_path: Path) -> tuple[dict[str, Any], dict[str, Any] | None, Path | None]:
    errors: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"schema_version": D1_CHECK_SCHEMA, "passed": False, "errors": [f"record unreadable: {exc}"]}, None, None
    if not isinstance(record, dict):
        return {"schema_version": D1_CHECK_SCHEMA, "passed": False, "errors": ["record is not an object"]}, None, None
    if record.get("schema_version") != D1_SCHEMA:
        errors.append("record schema mismatch")
    if record.get("stage") != "d1":
        errors.append("record stage is not d1")
    case = record.get("case")
    spec = D1_CASES.get(case)
    if spec is None:
        errors.append("record case is unknown")
        spec = {"degree": -1, "mpi_size": -1}
    if record.get("degree") != spec["degree"] or record.get("mpi_size") != spec["mpi_size"]:
        errors.append("record case degree/MPI identity mismatch")
    if record.get("profile") != D1_PROFILE or record.get("mesh_target_nm") != 50.0:
        errors.append("record profile or mesh target mismatch")
    _check_source(record, errors)
    _check_runtime(record, errors)
    _check_model(record, errors)
    _check_topology(record, errors)
    _check_definitions(record, errors)
    raw_dir_value = record.get("raw_dir")
    raw_dir = Path(raw_dir_value).resolve() if isinstance(raw_dir_value, str) else None
    if raw_dir is None or not raw_dir.is_dir():
        errors.append("record raw_dir is missing")
        raw_dir = record_path.parent
    source, operators = _check_artifacts(record, raw_dir, errors)
    if not source["finite"] or source["count"] <= 0 or source["duplicates"] != 0:
        errors.append("source canonical finite/count/duplicate gate failed")
    _check_source_values(source, errors)
    serial = record.get("serial_algebra")
    serial_facts: dict[str, Any] = {}
    if record.get("mpi_size") == 1:
        if not isinstance(serial, dict) or serial.get("status") != "measured":
            errors.append("MPI1 serial assembled algebra is missing")
        else:
            if serial.get("fixture") != D1_SERIAL_FIXTURE:
                errors.append("MPI1 serial fixture identity mismatch")
            if serial.get("global_numeric_allgather") is not False:
                errors.append("MPI1 serial numeric allgather audit is not false")
            if serial.get("ksp_created") is not False:
                errors.append("MPI1 serial KSP audit is not false")
            if serial.get("dtype") != "complex128":
                errors.append("MPI1 serial dtype mismatch")
            serial_facts = _serial_algebra(raw_dir, serial, errors)
            for slab in ("slab0", "slab1"):
                facts = serial_facts.get("slabs", {}).get(slab, {})
                for key, limit in {
                    "auxiliary_hermitian_defect": HERMITIAN_LIMIT,
                    "interface_mass_hermitian_defect": HERMITIAN_LIMIT,
                    "support_block_hermitian_defect": HERMITIAN_LIMIT,
                    "stiffness_hermitian_defect": HERMITIAN_LIMIT,
                    "stiffness_relation_error": 1.0e-14,
                    "eigen_residual": EIGEN_LIMIT,
                    "eigen_mass_normalization_error": 1.0e-12,
                    "extension_relative_error": CANONICAL_LIMIT,
                    "extension_repeat_relative_error": 0.0,
                }.items():
                    if not _finite(facts.get(key)) or float(facts[key]) > limit:
                        errors.append(f"serial algebra gate failed: {slab}.{key}")
                if facts.get("eigen_rank") != facts.get("expected_eigen_rank"):
                    errors.append(f"serial eigen rank mismatch: {slab}")
                if facts.get("eigen_ascending") is not True:
                    errors.append(f"serial eigen ordering gate failed: {slab}")
                if facts.get("eigen_repeat_exact") is not True:
                    errors.append(f"serial eigen repeat gate failed: {slab}")
                if facts.get("extension_repeat_exact") is not True:
                    errors.append(f"serial extension repeat gate failed: {slab}")
                if not facts.get("finite"):
                    errors.append(f"serial algebra finite gate failed: {slab}")
            rp_error = serial_facts.get("restriction_prolongation_adjoint_relative_error")
            if not _finite(rp_error) or float(rp_error) > ADJOINT_LIMIT:
                errors.append("serial restriction/prolongation adjoint gate failed")
    elif (
        not isinstance(serial, dict)
        or serial.get("status") != "not_run"
        or serial.get("boundary") != D1_MPI2_SERIAL_BOUNDARY
    ):
        errors.append("MPI2 serial assembled algebra boundary is not exact not_run")
    execution = _obj(record.get("execution"), "execution", errors)
    for key in ("ksp_created", "slepc_used", "global_numeric_allgather", "pde_solve"):
        if execution.get(key) is not False:
            errors.append(f"execution audit is not false: {key}")
    resource = _obj(record.get("resource"), "resource", errors)
    for key in ("rank_max_current_rss_bytes", "rank_max_swap_used_bytes"):
        if not isinstance(resource.get(key), int) or resource[key] < 0:
            errors.append(f"resource telemetry is invalid: {key}")
    gates = {
        "source_canonical": {"count": source["count"], "finite": source["finite"], "duplicates": source["duplicates"]},
        "operator_repeat": {
            f"{slab}.{name}": operators.get(slab, {}).get(name, {}).get("repeat_comparison", {})
            for slab in ("slab0", "slab1")
            for name in ("B", "M_Gamma")
        },
        "serial_algebra": serial_facts,
    }
    result = {
        "schema_version": D1_CHECK_SCHEMA,
        "record": str(record_path.resolve()),
        "case": case,
        "degree": record.get("degree"),
        "mpi_size": record.get("mpi_size"),
        "passed": not errors,
        "errors": errors,
        "gates": gates,
    }
    return result, record, raw_dir


def check_record(record_path: Path) -> dict[str, Any]:
    return _check_record_internal(Path(record_path))[0]


def _check_aggregate(record_paths: list[Path]) -> dict[str, Any]:
    errors: list[str] = []
    if len(record_paths) != 4:
        errors.append("D1 aggregate requires exactly four records")
    checked: dict[str, tuple[dict[str, Any], dict[str, Any], Path]] = {}
    for path in record_paths:
        result, record, raw_dir = _check_record_internal(path)
        if record is None or raw_dir is None:
            errors.extend(result.get("errors", []))
            continue
        if not result.get("passed"):
            errors.append(f"individual record failed: {path}")
        case = record.get("case")
        if case in checked:
            errors.append(f"duplicate aggregate case: {case}")
        checked[case] = (result, record, raw_dir)
    if set(checked) != set(D1_CASES):
        errors.append("aggregate case set is not the exact p2/p3 MPI1/MPI2 set")
    source_shas = {
        record.get("source", {}).get("expected_sha")
        for _result, record, _root in checked.values()
    }
    if len(source_shas) != 1 or None in source_shas:
        errors.append("aggregate source Git SHA is not identical across four records")
    model_identities = {
        tuple(
            record.get("model", {}).get(key)
            for key in (
                "wavelength_nm",
                "incident_theta_deg",
                "incident_phi_deg",
                "source_formula",
                "source_key_identity",
            )
        )
        for _result, record, _root in checked.values()
    }
    if len(model_identities) != 1 or not model_identities:
        errors.append("aggregate model identity is not identical across four records")
    pair_gates: dict[str, Any] = {}
    for degree in (2, 3):
        left_case = f"p{degree}-mpi1"
        right_case = f"p{degree}-mpi2"
        if left_case not in checked or right_case not in checked:
            continue
        _left_result, left_record, left_root = checked[left_case]
        _right_result, right_record, right_root = checked[right_case]
        for key in ("canonical_sha256", "global_facet_count"):
            if left_record.get("topology", {}).get(key) != right_record.get("topology", {}).get(key):
                errors.append(f"MPI topology identity failed: p{degree}.{key}")
        if tuple(
            left_record.get("model", {}).get(key)
            for key in (
                "wavelength_nm",
                "incident_theta_deg",
                "incident_phi_deg",
                "source_formula",
                "source_key_identity",
            )
        ) != tuple(
            right_record.get("model", {}).get(key)
            for key in (
                "wavelength_nm",
                "incident_theta_deg",
                "incident_phi_deg",
                "source_formula",
                "source_key_identity",
            )
        ):
            errors.append(f"MPI model identity failed: p{degree}")
        names = [("source", None)]
        for slab in ("slab0", "slab1"):
            for name in ("B", "M_Gamma"):
                names.append((name, slab))
        pair_gates[f"p{degree}"] = {}
        for name, slab in names:
            if slab is None:
                left_descriptor = left_record.get("artifacts", {}).get("source")
                right_descriptor = right_record.get("artifacts", {}).get("source")
            else:
                left_descriptor = left_record.get("artifacts", {}).get("operators", {}).get(slab, {}).get(name, {}).get("action")
                right_descriptor = right_record.get("artifacts", {}).get("operators", {}).get(slab, {}).get(name, {}).get("action")
            if not isinstance(left_descriptor, dict) or not isinstance(right_descriptor, dict):
                errors.append(f"MPI pair descriptor missing: p{degree}.{slab or name}")
                continue
            left_errors: list[str] = []
            right_errors: list[str] = []
            if slab is None:
                expected_name = "source"
                expected_role = "full_fe"
            else:
                expected_name = f"{'M' if name == 'M_Gamma' else name}_{slab}"
                expected_role = "full_fe_dual"
            left_packets = _read_manifest(
                left_root,
                left_descriptor,
                left_errors,
                f"p{degree} MPI1 {name}",
                expected_name=expected_name,
                expected_role=expected_role,
                expected_mpi_size=1,
            )
            right_packets = _read_manifest(
                right_root,
                right_descriptor,
                right_errors,
                f"p{degree} MPI2 {name}",
                expected_name=expected_name,
                expected_role=expected_role,
                expected_mpi_size=2,
            )
            if left_errors or right_errors:
                errors.extend(left_errors + right_errors)
            comparison = _relative_packets(left_packets["packets"], right_packets["packets"])
            pair_gates[f"p{degree}"][f"{slab or name}.{name if slab else 'action'}"] = comparison
            if not comparison["pass"]:
                errors.append(f"MPI canonical identity failed: p{degree}.{slab or name}")
    return {
        "schema_version": D1_CHECK_SCHEMA,
        "stage": "d1-aggregate",
        "record_count": len(record_paths),
        "passed": not errors,
        "errors": errors,
        "individual": {case: result for case, (result, _record, _root) in checked.items()},
        "pair_gates": pair_gates,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--record", type=Path)
    group.add_argument("--aggregate", type=Path, nargs="+")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = (
        check_record(args.record)
        if args.record is not None
        else _check_aggregate(args.aggregate)
    )
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0 if result.get("passed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
