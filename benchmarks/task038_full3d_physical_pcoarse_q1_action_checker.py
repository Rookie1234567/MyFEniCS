"""Independently check the V16 Q1.1 physical-action identity artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PHASE = "action-identity"
WORKFLOW = "q1-physical-pcoarse-action-identity"
CHECKER_SCHEMA = "task038.v16.q1.action-identity.checker.v1"
PARENT_SCHEMA = "task038.v16.q1.action-identity.parent.v1"
WORKER_SCHEMA = "task038.v16.q1.action-identity.worker.v1"
PROCESS_SCHEMA = "task038.v16.q1.source-authority.process-sample.v1"
MARKER_SCHEMA = "task038.v16.q1.action-identity.marker.v1"
ACTION_MANIFEST_SCHEMA = "task038.v16.q1.action-identity.manifest.v1"
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
KEY_DIGEST_ALGORITHM = "sha256(canonical-key-json-v1)"
JIT_GROUPS = (
    "positive-p6",
    "positive-p3",
    "positive-p1",
    "dtn-surface",
    "incident-rhs",
    "physical-volume-curl",
    "physical-volume-mass",
)
STAGE_ORDER = tuple(f"precompile:{group}" for group in JIT_GROUPS) + ("worker",)
MARKER_ORDER = (
    "paths_ready",
    "abi_ready",
    "case_built",
    "probe_execution_started",
    "probe_execution_complete",
    "release_complete",
    "record_written",
)
PROBE_NAMES = (
    "random",
    "gradient",
    "curl",
    "checkerboard",
    "physical_component_derived",
    "r3_long_tail_derived",
)
OUTPUT_NAMES = (
    "direct",
    "composed",
    "direct_repeat",
    "composed_repeat",
    "direct_scaled",
    "composed_scaled",
)
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
R3_SOURCE_SHA = "6c9c97b71a31d54afe92b0858d1347c4815c9aa4"
R3_MANIFEST_SHA256 = "1a3d3ca86276876dee3590da2de60876553e7d49afc060d5066ca10a9cb7b7b2"
R3_SHARD_SHA256 = "ccfe99b98187e35cd316dc20eec5857559c6844d62bcd71eff9a41b450ea277a"
R3_PACKET_COUNT = 2538
RSS_WATCHDOG = 1_950_000_000
RSS_HARD = 2_000_000_000
ALPHA = complex(0.37, 0.19)
RELATIVE_LIMIT = 1.0e-12
GALERKIN_LIMIT = 1.0e-9
WORK_LIMIT = 1.0e-11
MPI_LIMIT = 1.0e-10
VOLUME_PHASE = "each_component_finalized_floquet_mpc_once_no_wrapper_reapply"
_MISSING = object()


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite JSON constant: {token}")


def _load_json(path: Path) -> Any:
    return json.loads(
        path.read_bytes().decode("utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError(f"path:{label}: expected relative path")
    root = root.resolve()
    result = (root / value).resolve()
    if result != root and root not in result.parents:
        raise ValueError(f"path:{label}: escapes artifact root")
    return result


def _field(value: Any, key: str, label: str) -> Any:
    if not isinstance(value, dict):
        raise ValueError(f"{label}: expected object")
    if key not in value:
        raise ValueError(f"{label}.{key}: missing")
    return value[key]


def _expect(value: Any, key: str, expected: Any, label: str) -> Any:
    actual = _field(value, key, label)
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f"{label}.{key}: expected {expected!r}, got {actual!r}")
    return actual


def _source_facts(source: Any, expected_source_sha: str) -> None:
    expected = {
        "commit_sha": expected_source_sha,
        "branch": BRANCH,
        "upstream": f"origin/{BRANCH}",
        "upstream_sha": expected_source_sha,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "input_sha256": INPUT_SHA256,
    }
    for key, item in expected.items():
        _expect(source, key, item, "source")
    if not isinstance(_field(source, "python_executable", "source"), str):
        raise ValueError("source.python_executable: expected string")
    if not isinstance(_field(source, "python_prefix", "source"), str):
        raise ValueError("source.python_prefix: expected string")


def _sample_effectively_readable(sample: dict[str, Any]) -> bool:
    observed_code = sample.get("worker_exit_code_observed_after_sample")
    return sample.get("all_status_readable") is True or (
        sample.get("all_status_readable") is False
        and sample.get("process_tree_exit_race_observed") is True
        and _is_int(observed_code)
        and observed_code == 0
        and sample.get("rss_bytes") is None
        and sample.get("swap_bytes") is None
    )


def _read_process(
    path: Path, parent: dict[str, Any], expected_size: int
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                sample = _load_line(line)
                if not isinstance(sample, dict):
                    raise ValueError("process sample must be an object")
                samples.append(sample)
    if not samples:
        raise ValueError("process timeline is empty")
    peak = 0
    swap = 0
    readable = True
    stage_order: list[str] = []
    previous_stage = None
    for sample in samples:
        _expect(sample, "schema", PROCESS_SCHEMA, "process sample")
        stage = _field(sample, "stage", "process sample")
        if stage not in STAGE_ORDER:
            raise ValueError("process sample stage is invalid")
        if stage != previous_stage:
            stage_order.append(stage)
            previous_stage = stage
        rss = _field(sample, "rss_bytes", "process sample")
        swap_value = _field(sample, "swap_bytes", "process sample")
        status_readable = _field(sample, "all_status_readable", "process sample")
        if not isinstance(status_readable, bool):
            raise ValueError("process sample.all_status_readable is invalid")
        compiler_count = _field(sample, "compiler_descendant_count", "process sample")
        if not _is_int(compiler_count) or compiler_count < 0:
            raise ValueError("process sample.compiler_descendant_count is invalid")
        race = (
            status_readable is False
            and sample.get("process_tree_exit_race_observed") is True
            and _is_int(sample.get("worker_exit_code_observed_after_sample"))
            and sample.get("worker_exit_code_observed_after_sample") == 0
            and rss is None
            and swap_value is None
        )
        if (
            sample.get("process_tree_exit_race_observed") is True
            or "worker_exit_code_observed_after_sample" in sample
        ) and not race:
            raise ValueError("process sample exit-race annotation is invalid")
        for value, label in ((rss, "rss_bytes"), (swap_value, "swap_bytes")):
            if value is None:
                if not race:
                    raise ValueError(f"process sample.{label} is missing")
            elif not _is_int(value) or value < 0:
                raise ValueError(f"process sample.{label} is invalid")
        if stage == "worker" and compiler_count != 0:
            raise ValueError("process sample worker has compiler descendants")
        if rss is not None:
            peak = max(peak, rss)
        if swap_value is not None:
            swap = max(swap, swap_value)
        readable = readable and _sample_effectively_readable(sample)
    if tuple(stage_order) != STAGE_ORDER:
        raise ValueError("process timeline stage order is invalid")
    result = _field(parent, "process", "parent")
    _expect(result, "sample_count", len(samples), "parent.process")
    _expect(result, "peak_rss_bytes", peak, "parent.process")
    _expect(result, "max_swap_bytes", swap, "parent.process")
    _expect(result, "all_status_readable", readable, "parent.process")
    if not readable:
        raise ValueError("process: unreadable sample")
    if swap != 0:
        raise ValueError("resource: process-tree swap is nonzero")
    if expected_size == 1 and peak >= RSS_HARD:
        raise ValueError(f"resource: process-tree RSS {peak} reaches {RSS_HARD}")
    return {"sample_count": len(samples), "peak_rss_bytes": peak, "swap_bytes": swap}


def _load_line(line: str) -> Any:
    return json.loads(
        line,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_constant,
    )


def _check_result(
    result: Any,
    label: str,
    expected_watchdog: int | None,
    expected_stage: str | None = None,
) -> None:
    if not isinstance(result, dict):
        raise ValueError(f"{label}: missing result")
    stop_reason = result.get("stop_reason")
    if stop_reason in {"process_tree_rss_watchdog", "process_tree_swap"}:
        raise ValueError(f"resource: {label} stopped by {stop_reason}")
    if not isinstance(_field(result, "argv", label), list):
        raise ValueError(f"{label}.argv: expected list")
    _expect(result, "returncode", 0, label)
    _expect(result, "stop_reason", None, label)
    _expect(result, "signals", [], label)
    _expect(result, "process_group_gone", True, label)
    _expect(result, "lifecycle_failure", False, label)
    _expect(result, "max_swap_bytes", 0, label)
    _expect(result, "all_status_readable", True, label)
    _expect(result, "rss_watchdog_bytes", expected_watchdog, label)
    if expected_stage is not None:
        _expect(result, "stage", expected_stage, label)


def _check_markers(root: Path, parent: dict[str, Any], expected_source_sha: str, mpi_size: int) -> None:
    marker_info = _field(parent, "markers", "parent")
    marker_manifest = _path(root, _field(marker_info, "manifest_relative_path", "parent.markers"), "marker manifest")
    if _sha256(marker_manifest) != _field(marker_info, "manifest_sha256", "parent.markers"):
        raise ValueError("marker manifest hash mismatch")
    rows = _load_json(marker_manifest)
    if not isinstance(rows, list) or [item.get("name") for item in rows] != list(MARKER_ORDER):
        raise ValueError("marker manifest order mismatch")
    for index, (row, name) in enumerate(zip(rows, MARKER_ORDER, strict=True)):
        if not isinstance(row, dict) or row.get("name") != name:
            raise ValueError("marker manifest row is invalid")
        marker = root / "markers" / f"{index:03d}_{name}.json"
        if not marker.is_file() or _sha256(marker) != row.get("sha256"):
            raise ValueError(f"marker hash mismatch: {name}")
        payload = _load_json(marker)
        _expect(payload, "schema", MARKER_SCHEMA, f"marker:{name}")
        _expect(payload, "name", name, f"marker:{name}")
        _expect(payload, "marker_index", index, f"marker:{name}")
        facts = _field(payload, "facts", f"marker:{name}")
        _expect(facts, "source_sha", expected_source_sha, f"marker:{name}.facts")
        _expect(facts, "mpi_size", mpi_size, f"marker:{name}.facts")


def _packet_key(record: dict[str, Any]) -> bytes:
    key = _field(record, "key", "packet")
    key_bytes = json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    _expect(record, "key_sha256", hashlib.sha256(key_bytes).hexdigest(), "packet")
    return key_bytes


def _read_packet_manifest(
    root: Path, descriptor: Any, label: str, expected_size: int
) -> tuple[dict[bytes, complex], dict[str, Any]]:
    if not isinstance(descriptor, dict):
        raise ValueError(f"{label}: descriptor must be an object")
    manifest_path = _path(root, _field(descriptor, "manifest_relative_path", label), f"{label}.manifest")
    expected_manifest_sha = _field(descriptor, "manifest_sha256", label)
    if _sha256(manifest_path) != expected_manifest_sha:
        raise ValueError(f"{label}: manifest hash mismatch")
    manifest = _load_json(manifest_path)
    _expect(manifest, "schema_version", MANIFEST_SCHEMA, f"{label}.manifest")
    _expect(manifest, "role", "full_fe_dual", f"{label}.manifest")
    _expect(manifest, "mpi_size", expected_size, f"{label}.manifest")
    shards = _field(manifest, "per_rank_shards", f"{label}.manifest")
    if not isinstance(shards, list) or len(shards) != expected_size:
        raise ValueError(f"{label}: shard count mismatch")
    packets: dict[bytes, complex] = {}
    total = 0
    for rank, shard in enumerate(shards):
        if not isinstance(shard, dict):
            raise ValueError(f"{label}: malformed shard metadata")
        _expect(shard, "rank", rank, f"{label}.shard")
        _expect(shard, "dtype", "complex128", f"{label}.shard")
        _expect(shard, "schema_version", SHARD_SCHEMA, f"{label}.shard")
        _expect(shard, "key_digest_algorithm", KEY_DIGEST_ALGORITHM, f"{label}.shard")
        shard_path = manifest_path.parent / _field(shard, "filename", f"{label}.shard")
        if _sha256(shard_path) != _field(shard, "file_sha256", f"{label}.shard"):
            raise ValueError(f"{label}: shard hash mismatch")
        shard_count = 0
        local_keys: set[bytes] = set()
        with shard_path.open(encoding="utf-8") as stream:
            for line in stream:
                record = _load_line(line)
                if not isinstance(record, dict):
                    raise ValueError(f"{label}: packet is not an object")
                _expect(record, "schema_version", SHARD_SCHEMA, f"{label}.packet")
                key_bytes = _packet_key(record)
                value = _field(record, "value", f"{label}.packet")
                if not isinstance(value, list) or len(value) != 2 or not all(_finite(item) for item in value):
                    raise ValueError(f"{label}: packet value is invalid")
                if key_bytes in local_keys or key_bytes in packets:
                    raise ValueError(f"{label}: duplicate canonical key")
                local_keys.add(key_bytes)
                packets[key_bytes] = complex(float(value[0]), float(value[1]))
                shard_count += 1
        _expect(shard, "packet_count", shard_count, f"{label}.shard")
        _expect(shard, "packet_finite", True, f"{label}.shard")
        _expect(shard, "local_duplicate_count", 0, f"{label}.shard")
        total += shard_count
    _expect(manifest, "global_summed_packet_count", total, f"{label}.manifest")
    _expect(manifest, "summed_local_duplicate_count", 0, f"{label}.manifest")
    audit = _field(manifest, "extractor_audit", f"{label}.manifest")
    _expect(audit, "role", "full_fe_dual", f"{label}.extractor_audit")
    _expect(audit, "global_packet_count", total, f"{label}.extractor_audit")
    _expect(descriptor, "role", "full_fe_dual", label)
    _expect(descriptor, "mpi_size", expected_size, label)
    _expect(descriptor, "packet_count", total, label)
    if total <= 0:
        raise ValueError(f"{label}: canonical packet count must be positive")
    return packets, audit


def _cache_snapshot(cache: Path) -> dict[str, Any]:
    if not cache.is_dir():
        raise ValueError("cache: jit cache directory is missing")
    artifacts = []
    for base, _directories, files in os.walk(cache, followlinks=False):
        for filename in files:
            path = Path(base) / filename
            if path.suffix not in {".c", ".o", ".so"} or not path.is_file():
                continue
            artifacts.append(
                {
                    "relative_path": path.relative_to(cache).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": _sha256(path),
                }
            )
    artifacts.sort(key=lambda item: item["relative_path"])
    manifest = {
        "cache_dir": str(cache.absolute()),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }
    return {
        "artifact_count": len(artifacts),
        "manifest_sha256": hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _check_architecture(worker: dict[str, Any]) -> None:
    architecture = _field(worker, "architecture", "worker")
    for action_name in ("p3_action", "p6_action"):
        audit = _field(architecture, action_name, "worker.architecture")
        label = f"worker.architecture.{action_name}"
        _expect(audit, "schema", "task038.fullspace-physical-action.v1", label)
        _expect(audit, "volume_phase_application", VOLUME_PHASE, label)
        _expect(audit, "dtn_mode_manifest_sha256", MODE_MANIFEST_SHA256, label)
        _expect(audit, "dtn_mode_count", 80, label)
        for key in (
            "global_aij_materialized",
            "global_schur_materialized",
            "ksp_created",
            "numeric_allgather",
            "trace_matrix_materialized",
            "global_volume_matrix_materialized",
            "global_constraint_matrix_materialized",
            "global_condensed_schur_materialized",
            "dense_cell_tensor_materialized",
        ):
            _expect(audit, key, False, label)
        _expect(audit, "factor_count", 0, label)
        _expect(audit, "explicit_c_matrix_count", 0, label)
        _expect(audit, "explicit_d_matrix_count", 0, label)
    p63 = _field(architecture, "p63", "worker.architecture")
    _expect(p63, "operator", "same_mesh_owner_transfer", "worker.architecture.p63")
    _expect(p63, "numeric_allgather", False, "worker.architecture.p63")
    _expect(p63, "global_matrix_materialized", False, "worker.architecture.p63")
    _expect(architecture, "canonical_output_role", "full_fe_dual", "worker.architecture")
    _expect(architecture, "phase_once", "finalized_floquet_mpc_once", "worker.architecture")


def _check_worker(
    root: Path, parent: dict[str, Any], expected_source_sha: str, expected_size: int
) -> dict[str, Any]:
    worker_result = _field(parent, "worker", "parent")
    expected_watchdog = RSS_WATCHDOG if expected_size == 1 else None
    _check_result(worker_result, "parent.worker", expected_watchdog)
    _expect(worker_result, "stage", "worker", "parent.worker")
    worker_path = _path(root, _field(_field(parent, "paths", "parent"), "worker_record", "parent.paths"), "worker record")
    if _sha256(worker_path) != _field(worker_result, "record_sha256", "parent.worker"):
        raise ValueError("worker record hash mismatch")
    worker = _load_json(worker_path)
    _expect(worker, "schema", WORKER_SCHEMA, "worker")
    _expect(worker, "raw_facts_only", True, "worker")
    _source_facts(_field(worker, "source", "worker"), expected_source_sha)
    runtime = _field(worker, "runtime", "worker")
    _expect(runtime, "mpi_size", expected_size, "worker.runtime")
    _expect(runtime, "petsc_scalar_type", "complex128", "worker.runtime")
    _expect(runtime, "petsc_int_type", "int32", "worker.runtime")
    input_facts = _field(worker, "input", "worker")
    _expect(input_facts, "template_sha256", INPUT_SHA256, "worker.input")
    _expect(input_facts, "physical_model_sha256", PHYSICAL_MODEL_SHA256, "worker.input")
    _expect(
        input_facts,
        "template_relative_path",
        "input/templates/full3d_iterative_example.dat",
        "worker.input",
    )
    mode = _field(worker, "mode_inventory", "worker")
    _expect(mode, "mode_count", 80, "worker.mode_inventory")
    _expect(mode, "mode_manifest_sha256", MODE_MANIFEST_SHA256, "worker.mode_inventory")
    _expect(mode, "tested_pair", [6, 3], "worker.mode_inventory")
    _expect(mode, "tested_mesh_target_size_nm", 50.0, "worker.mode_inventory")
    cache = _field(worker, "cache", "worker")
    _expect(cache, "binding", True, "worker.cache")
    cache_path = (root / "jit_cache").resolve()
    if Path(_field(cache, "xdg_cache_home", "worker.cache")).resolve() != cache_path:
        raise ValueError("worker cache binding mismatch")
    action_path = _path(
        root,
        _field(_field(worker, "paths", "worker"), "action_manifest", "worker.paths"),
        "action manifest",
    )
    _expect(worker, "action_manifest_sha256", _sha256(action_path), "worker")
    _check_architecture(worker)
    r3 = _field(worker, "r3_authority", "worker")
    for key, value in {
        "source_sha": R3_SOURCE_SHA,
        "manifest_sha256": R3_MANIFEST_SHA256,
        "shard_sha256": R3_SHARD_SHA256,
        "packet_count": R3_PACKET_COUNT,
        "role": "full_fe_dual",
    }.items():
        _expect(r3, key, value, "worker.r3_authority")
    _expect(_field(r3, "selected_facts", "worker.r3_authority"), "file_sha256", R3_SHARD_SHA256, "worker.r3_authority.selected_facts")
    _expect(r3, "selected_packet_count", R3_PACKET_COUNT, "worker.r3_authority")
    return worker


def _relative(
    left: dict[bytes, complex], right: dict[bytes, complex], label: str | None = None
) -> float:
    if set(left) != set(right):
        message = "canonical key identity differs"
        raise ValueError(message if label is None else f"{label}: {message}")
    numerator = math.fsum(abs(left[key] - right[key]) ** 2 for key in left)
    denominator = math.fsum(abs(value) ** 2 for value in right.values())
    return math.sqrt(numerator / max(denominator, 1.0e-300))


def _complex_pair(value: Any, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2 or not all(_finite(item) for item in value):
        raise ValueError(f"{label}: expected finite complex pair")
    return complex(float(value[0]), float(value[1]))


def _check_probes(
    root: Path, worker: dict[str, Any], expected_size: int
) -> dict[str, dict[str, dict[bytes, complex]]]:
    paths = _field(worker, "paths", "worker")
    manifest_path = _path(root, _field(paths, "action_manifest", "worker.paths"), "action manifest")
    action_manifest = _load_json(manifest_path)
    _expect(action_manifest, "schema", ACTION_MANIFEST_SCHEMA, "action manifest")
    _expect(action_manifest, "role", "full_fe_dual_action_outputs", "action manifest")
    _expect(action_manifest, "mpi_size", expected_size, "action manifest")
    _expect(action_manifest, "probe_order", list(PROBE_NAMES), "action manifest")
    outputs = _field(action_manifest, "outputs", "action manifest")
    if not isinstance(outputs, dict) or set(outputs) != set(PROBE_NAMES):
        raise ValueError("action manifest probe order is invalid")
    probes = _field(worker, "probes", "worker")
    if not isinstance(probes, list) or [item.get("name") for item in probes] != list(PROBE_NAMES):
        raise ValueError("worker probe order is invalid")
    canonical_all: dict[str, dict[str, dict[bytes, complex]]] = {
        "direct": {},
        "composed": {},
    }
    for probe, name in zip(probes, PROBE_NAMES, strict=True):
        if not isinstance(probe, dict):
            raise ValueError(f"probe {name} is invalid")
        _expect(probe, "name", name, f"probe:{name}")
        source_generation = _field(probe, "source_generation", f"probe:{name}")
        _expect(source_generation, "name", name, f"probe:{name}.source_generation")
        if name == "physical_component_derived":
            _expect(
                source_generation,
                "formula",
                "physical_rhs_compose_then_p63_adjoint",
                f"probe:{name}.source_generation",
            )
            _expect(
                source_generation,
                "dual_role",
                "full_fe_dual",
                f"probe:{name}.source_generation",
            )
        elif name == "r3_long_tail_derived":
            for key, value in {
                "role": "full_fe_dual",
                "source": "q1_source_authority_v7/r3.manifest.json",
                "reconstruction": "reconstruct_canonical_full_fe_dual_vector",
            }.items():
                _expect(source_generation, key, value, f"probe:{name}.source_generation")
        _expect(probe, "phase_application", "finalized_floquet_mpc_once", f"probe:{name}")
        projected = probe.get("projected_full_constraint_residual")
        algebraic = probe.get("algebraic_owned_slave_max")
        if not _finite(projected) or not _finite(algebraic):
            raise ValueError(f"probe:{name}: algebraic facts are non-finite")
        if projected > RELATIVE_LIMIT:
            raise ValueError(f"probe:{name}: projected constraint failed")
        if algebraic != 0.0:
            raise ValueError(f"probe:{name}: algebraic slave storage is not zero")
        stored_work = probe.get("p_p_h_work_identity_relative")
        lhs = _complex_pair(probe.get("work_lhs"), f"probe:{name}.work_lhs")
        rhs = _complex_pair(probe.get("work_rhs"), f"probe:{name}.work_rhs")
        work_relative = abs(lhs - rhs) / max(
            abs(lhs), abs(rhs), 1.0e-300
        )
        if (
            not _finite(stored_work)
            or abs(float(stored_work) - work_relative) > 1.0e-12
            or work_relative > WORK_LIMIT
        ):
            raise ValueError(f"probe:{name}: P/P^H work identity failed")
        source_relative = probe.get("source_input_unchanged_relative")
        if not _finite(source_relative) or source_relative > RELATIVE_LIMIT:
            raise ValueError(f"probe:{name}: source changed")
        source_before = _field(probe, "source_before", f"probe:{name}")
        source_after = _field(probe, "source_after", f"probe:{name}")
        if source_before.get("array_sha256") != source_after.get("array_sha256"):
            raise ValueError(f"probe:{name}: source hash changed")
        rank_facts = _field(probe, "source_rank_facts", f"probe:{name}")
        if not isinstance(rank_facts, list) or len(rank_facts) != expected_size:
            raise ValueError(f"probe:{name}: source rank facts are incomplete")
        for rank, facts in enumerate(rank_facts):
            if not isinstance(facts, dict):
                raise ValueError(f"probe:{name}: source rank facts are malformed")
            _expect(facts, "rank", rank, f"probe:{name}.source_rank_facts")
            before_sha = _field(
                facts, "before_sha256", f"probe:{name}.source_rank_facts"
            )
            after_sha = _field(
                facts, "after_sha256", f"probe:{name}.source_rank_facts"
            )
            if not isinstance(before_sha, str) or before_sha != after_sha:
                raise ValueError(f"probe:{name}: source rank hash changed")
            _expect(
                facts,
                "input_unchanged",
                True,
                f"probe:{name}.source_rank_facts",
            )
        for field_name in ("direct", "composed"):
            facts = _field(probe, field_name, f"probe:{name}")
            if facts.get("finite") is not True or facts.get("owned_slave_max") != 0.0:
                raise ValueError(f"probe:{name}: {field_name} facts failed")
        descriptors = _field(outputs, name, "action manifest.outputs")
        if not isinstance(descriptors, dict) or set(descriptors) != set(OUTPUT_NAMES):
            raise ValueError(f"probe:{name}: output order is invalid")
        packets: dict[str, dict[bytes, complex]] = {}
        for output in OUTPUT_NAMES:
            packets[output], audit = _read_packet_manifest(
                root, descriptors[output], f"{name}.{output}", expected_size
            )
            if audit.get("probe") != name or audit.get("output") != output:
                raise ValueError(f"{name}.{output}: extractor audit binding mismatch")
        canonical_all["direct"][name] = packets["direct"]
        canonical_all["composed"][name] = packets["composed"]
        galerk = _relative(
            packets["direct"], packets["composed"], f"probe:{name}"
        )
        repeat = max(
            _relative(
                packets["direct"], packets["direct_repeat"], f"probe:{name}"
            ),
            _relative(
                packets["composed"], packets["composed_repeat"], f"probe:{name}"
            ),
        )
        expected_direct = {key: ALPHA * value for key, value in packets["direct"].items()}
        expected_composed = {key: ALPHA * value for key, value in packets["composed"].items()}
        linearity = max(
            _relative(
                packets["direct_scaled"], expected_direct, f"probe:{name}"
            ),
            _relative(
                packets["composed_scaled"], expected_composed, f"probe:{name}"
            ),
        )
        checks = (
            ("physical_galerkin_relative", galerk, GALERKIN_LIMIT),
            ("repeat_relative_l2", repeat, RELATIVE_LIMIT),
            ("linearity_relative_l2", linearity, RELATIVE_LIMIT),
        )
        for field_name, actual, limit in checks:
            stored = probe.get(field_name)
            if not _finite(stored) or abs(float(stored) - actual) > 1.0e-12 or actual > limit:
                raise ValueError(f"probe:{name}: {field_name} failed")
    return canonical_all


def _check_one(
    path: Path, expected_source_sha: str, expected_size: int
) -> tuple[dict[str, Any], dict[str, dict[str, dict[bytes, complex]]]]:
    if expected_size not in (1, 2):
        raise ValueError("runtime: unsupported MPI size")
    root = path.resolve().parent
    parent = _load_json(path)
    _expect(parent, "schema", PARENT_SCHEMA, "parent")
    _expect(parent, "workflow", WORKFLOW, "parent")
    _expect(parent, "phase", PHASE, "parent")
    _expect(parent, "expected_mpi_size", expected_size, "parent")
    _source_facts(_field(parent, "source", "parent"), expected_source_sha)
    _expect(parent, "error", None, "parent")
    expected_watchdog = RSS_WATCHDOG if expected_size == 1 else None
    _expect(parent, "rss_watchdog_bytes", expected_watchdog, "parent")
    _read_process(
        _path(
            root,
            _field(_field(parent, "paths", "parent"), "process_samples", "parent.paths"),
            "process samples",
        ),
        parent,
        expected_size,
    )
    children = _field(parent, "children", "parent")
    if not isinstance(children, list) or [item.get("group") for item in children] != list(JIT_GROUPS):
        raise ValueError("parent child order is invalid")
    for child, group in zip(children, JIT_GROUPS, strict=True):
        _expect(child, "group", group, f"child:{group}")
        _check_result(
            child,
            f"child:{group}",
            expected_watchdog,
            expected_stage=f"precompile:{group}",
        )
    _check_markers(root, parent, expected_source_sha, expected_size)
    worker = _check_worker(root, parent, expected_source_sha, expected_size)
    cache = _field(parent, "cache", "parent")
    initial = _field(cache, "initial", "parent.cache")
    if not isinstance(initial, dict) or initial.get("artifact_count") != 0:
        raise ValueError("cache was not initially empty")
    before_worker = _field(cache, "before_worker", "parent.cache")
    after_worker = _field(cache, "after_worker", "parent.cache")
    if before_worker != after_worker:
        raise ValueError("cache changed during worker")
    actual_cache = _cache_snapshot(
        _path(
            root,
            _field(_field(parent, "paths", "parent"), "jit_cache", "parent.paths"),
            "jit cache",
        )
    )
    if actual_cache != after_worker:
        raise ValueError("cache: after_worker snapshot mismatch")
    return {
        "schema": CHECKER_SCHEMA,
        "source_sha": expected_source_sha,
        "mpi_size": expected_size,
        "peak_rss_bytes": parent["process"]["peak_rss_bytes"],
        "swap_bytes": parent["process"]["max_swap_bytes"],
    }, _check_probes(root, worker, expected_size)


def _result(passed: bool, classification: str, errors: list[str], **metrics: Any) -> dict[str, Any]:
    return {
        "schema": CHECKER_SCHEMA,
        "passed": bool(passed),
        "classification": classification,
        "errors": errors,
        "metrics": metrics,
        "evidence_kind": {
            "process": "measured",
            "canonical": "measured",
            "hash": "derived",
            "cache": "derived",
            "mpi_relative": "derived",
        },
    }


def _classify_error(message: str) -> str:
    for prefix in ("mpi1:", "mpi2:"):
        if message.startswith(prefix):
            message = message[len(prefix) :].lstrip()
            break
    if message.startswith("resource:"):
        return "Q1_PHYSICAL_ACTION_RESOURCE_GATE_FAIL"
    if message.startswith("mpi_identity:"):
        return "Q1_PHYSICAL_ACTION_MPI_IDENTITY_GATE_FAIL"
    if message.startswith("probe:"):
        return "Q1_PHYSICAL_ACTION_IDENTITY_GATE_FAIL"
    if message.startswith("worker.architecture"):
        return "Q1_PHYSICAL_ACTION_ARCHITECTURE_GATE_FAIL"
    return "INFRASTRUCTURE_FAILURE_RETRYABLE"


def check_artifact(
    parent_record: Path | str, expected_source_sha: str, expected_mpi_size: int
) -> dict[str, Any]:
    try:
        facts, _probes = _check_one(Path(parent_record), expected_source_sha, int(expected_mpi_size))
        return _result(True, "Q1_PHYSICAL_ACTION_IDENTITY_PASS", [], **facts)
    except Exception as exc:
        message = str(exc)
        return _result(False, _classify_error(message), [message])


def check_pair(
    mpi1_parent_record: Path | str,
    mpi2_parent_record: Path | str,
    expected_source_sha: str,
) -> dict[str, Any]:
    try:
        facts1, probes1 = _check_one(Path(mpi1_parent_record), expected_source_sha, 1)
        facts2, probes2 = _check_one(Path(mpi2_parent_record), expected_source_sha, 2)
        relative: dict[str, dict[str, float]] = {}
        for name in PROBE_NAMES:
            relative[name] = {}
            for output in ("direct", "composed"):
                try:
                    value = _relative(probes1[output][name], probes2[output][name])
                except ValueError as exc:
                    if str(exc) == "canonical key identity differs":
                        raise ValueError(
                            f"mpi_identity:{name}.{output} canonical key identity differs"
                        ) from exc
                    raise
                relative[name][output] = value
                if value > MPI_LIMIT:
                    raise ValueError(
                        f"mpi_identity:{name}.{output} relative {value} > {MPI_LIMIT}"
                    )
        return _result(
            True,
            "Q1_PHYSICAL_ACTION_IDENTITY_MPI_PAIR_PASS",
            [],
            mpi1=facts1,
            mpi2=facts2,
            mpi_relative=relative,
        )
    except Exception as exc:
        message = str(exc)
        return _result(False, _classify_error(message), [message])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpi1-parent", required=True)
    parser.add_argument("--mpi2-parent")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.mpi2_parent:
        result = check_pair(args.mpi1_parent, args.mpi2_parent, args.expected_source_sha)
    else:
        result = check_artifact(args.mpi1_parent, args.expected_source_sha, 1)
    output = Path(args.output)
    payload = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(payload)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
