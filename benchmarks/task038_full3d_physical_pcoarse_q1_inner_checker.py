"""Independently check the V16 Q1.2 small physical inner-solve evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PHASE = "inner-solve"
WORKFLOW = "q1-physical-pcoarse-inner"
CHECKER_SCHEMA = "task038.v16.q1.inner.checker.v1"
PARENT_SCHEMA = "task038.v16.q1.inner.parent.v1"
WORKER_SCHEMA = "task038.v16.q1.inner.worker.v1"
PROCESS_SCHEMA = "task038.v16.q1.source-authority.process-sample.v1"
MARKER_SCHEMA = "task038.v16.q1.inner.marker.v1"
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"
KEY_DIGEST = "sha256(canonical-key-json-v1)"
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
    "source_physical_rhs_complete",
    "source_random_complete",
    "release_complete",
    "record_written",
)
SOURCE_NAMES = ("physical_rhs", "random")
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
RESOLVED_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
PHYSICAL_MODEL_SHA256 = (
    "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
)
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
RSS_HARD = 2_000_000_000
STAGING_RSS_WATCHDOG = 1_950_000_000
MPI1_SOLVER_RSS_LIMIT = 500_000_000
INNER_MAX_IT = 5000
INNER_RESIDUAL_LIMIT = 1.0e-6
RESTART = 20
RELATIVE_LIMIT = 1.0e-12
_TINY = 1.0e-300


def _reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"schema:duplicate JSON key {key}")
        result[key] = value
    return result


def _reject_constant(token: str) -> Any:
    raise ValueError(f"schema:non-finite JSON constant {token}")


def _load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_bytes().decode("utf-8"),
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_constant,
        )
    except ValueError:
        raise
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"schema:cannot read {path}") from exc


def _load_json_line(line: str, label: str) -> Any:
    try:
        return json.loads(
            line,
            object_pairs_hook=_reject_pairs,
            parse_constant=_reject_constant,
        )
    except ValueError as exc:
        raise ValueError(f"schema:{label}:invalid JSON") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _field(value: Any, key: str, label: str) -> Any:
    if not isinstance(value, dict) or key not in value:
        raise ValueError(f"schema:{label}.{key}:missing")
    return value[key]


def _expect(value: Any, key: str, expected: Any, label: str) -> Any:
    actual = _field(value, key, label)
    if type(actual) is not type(expected) or actual != expected:
        raise ValueError(f"schema:{label}.{key}:expected {expected!r}")
    return actual


def _relative_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError(f"source:{label}:path must be relative")
    root = root.resolve()
    path = (root / value).resolve()
    if path != root and root not in path.parents:
        raise ValueError(f"source:{label}:path escapes artifact root")
    if not path.is_file():
        raise ValueError(f"source:{label}:file is missing")
    return path


def _source_facts(source: Any, expected_sha: str, label: str) -> None:
    expected = {
        "commit_sha": expected_sha,
        "branch": BRANCH,
        "upstream": f"origin/{BRANCH}",
        "upstream_sha": expected_sha,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
    }
    for key, item in expected.items():
        _expect(source, key, item, label)
    for key in ("python_executable", "python_prefix", "input_path"):
        if not isinstance(_field(source, key, label), str):
            raise ValueError(f"source:{label}.{key}:expected string")
    _expect(source, "input_sha256", INPUT_SHA256, label)


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


def _check_sample(sample: Any, label: str) -> dict[str, Any]:
    if not isinstance(sample, dict):
        raise ValueError(f"schema:{label}:sample is not an object")
    _expect(sample, "schema", PROCESS_SCHEMA, label)
    stage = _field(sample, "stage", label)
    if stage not in STAGE_ORDER:
        raise ValueError(f"schema:{label}.stage:unknown")
    if not isinstance(_field(sample, "all_status_readable", label), bool):
        raise ValueError(f"schema:{label}.all_status_readable:expected bool")
    compiler_count = _field(sample, "compiler_descendant_count", label)
    if not _is_int(compiler_count) or compiler_count < 0:
        raise ValueError(f"schema:{label}.compiler_descendant_count:invalid")
    for key in ("rss_bytes", "swap_bytes"):
        value = _field(sample, key, label)
        if value is not None and (not _is_int(value) or value < 0):
            raise ValueError(f"schema:{label}.{key}:invalid")
    race = sample.get("process_tree_exit_race_observed")
    observed = sample.get("worker_exit_code_observed_after_sample")
    if race is not None and not isinstance(race, bool):
        raise ValueError(f"schema:{label}.process_tree_exit_race_observed:invalid")
    if observed is not None and not _is_int(observed):
        raise ValueError(f"schema:{label}.worker_exit_code_observed_after_sample:invalid")
    if race is True and not _sample_effectively_readable(sample):
        raise ValueError(f"lifecycle:{label}:invalid exit-race annotation")
    if race is not True and observed is not None:
        raise ValueError(f"lifecycle:{label}:unbound exit-race code")
    return sample


def _cache_snapshot(cache: Path) -> dict[str, Any]:
    artifacts: list[dict[str, Any]] = []
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
        "cache_dir": str(cache),
        "artifacts": artifacts,
        "artifact_count": len(artifacts),
    }
    encoded = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return {
        "artifact_count": len(artifacts),
        "manifest_sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _check_stage(
    result: Any, samples: list[dict[str, Any]], label: str
) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise ValueError(f"schema:{label}:result is not an object")
    _expect(result, "stage", label.split(":", 1)[-1], label)
    if _field(result, "returncode", label) != 0 or not _is_int(result["returncode"]):
        raise ValueError(f"lifecycle:{label}:returncode is not zero")
    if result.get("stop_reason") is not None:
        reason = result["stop_reason"]
        prefix = "resource" if reason in {
            "process_tree_rss_watchdog",
            "process_tree_swap",
        } else "lifecycle"
        raise ValueError(f"{prefix}:{label}:stop_reason={reason}")
    if result.get("signals") != []:
        raise ValueError(f"lifecycle:{label}:signals are not empty")
    if result.get("process_group_gone") is not True or result.get("lifecycle_failure") is not False:
        raise ValueError(f"lifecycle:{label}:process group did not close")
    live = [sample for sample in samples if sample.get("exit_code") is None]
    exits = [sample for sample in samples if sample.get("exit_code") is not None]
    if len(live) != result.get("sample_count") or len(exits) != 1:
        raise ValueError(f"lifecycle:{label}:sample/exit count does not close")
    if exits[0].get("exit_code") != 0 or not _is_int(exits[0].get("exit_code")):
        raise ValueError(f"lifecycle:{label}:exit sample is not zero")
    rss = [int(sample["rss_bytes"]) for sample in samples if sample["rss_bytes"] is not None]
    swaps = [int(sample["swap_bytes"]) for sample in samples if sample["swap_bytes"] is not None]
    if not rss or not swaps:
        raise ValueError(f"lifecycle:{label}:no usable process measurement")
    if result.get("peak_rss_bytes") != max(rss):
        raise ValueError(f"lifecycle:{label}:peak does not match samples")
    if result.get("max_swap_bytes") != max(swaps):
        raise ValueError(f"lifecycle:{label}:swap does not match samples")
    effective = all(_sample_effectively_readable(sample) for sample in samples)
    if result.get("all_status_readable") is not effective:
        raise ValueError(f"lifecycle:{label}:readability does not match samples")
    if max(int(sample["compiler_descendant_count"]) for sample in exits) != 0:
        raise ValueError(f"lifecycle:{label}:exit has compiler descendants")
    return {
        "peak_rss_bytes": int(result["peak_rss_bytes"]),
        "max_swap_bytes": int(result["max_swap_bytes"]),
        "all_status_readable": bool(result["all_status_readable"]),
        "sample_count": len(live),
    }


def _check_process(parent: dict[str, Any], root: Path, expected_size: int) -> dict[str, Any]:
    process_path = _relative_path(root, _field(parent["paths"], "process_samples", "parent.paths"), "process")
    samples: list[dict[str, Any]] = []
    with process_path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if line.strip():
                samples.append(_check_sample(_load_json_line(line, f"process[{index}]"), f"process[{index}]"))
    if not samples:
        raise ValueError("lifecycle:process timeline is empty")
    observed_order = []
    by_stage: dict[str, list[dict[str, Any]]] = {}
    for sample in samples:
        stage = sample["stage"]
        if stage not in by_stage:
            observed_order.append(stage)
            by_stage[stage] = []
        by_stage[stage].append(sample)
    if tuple(observed_order) != STAGE_ORDER or set(by_stage) != set(STAGE_ORDER):
        raise ValueError("lifecycle:process stage order is not the fixed cold order")

    children = _field(parent, "children", "parent")
    if not isinstance(children, list) or len(children) != len(JIT_GROUPS):
        raise ValueError("schema:parent.children:expected seven groups")
    stage_facts = []
    for group, result in zip(JIT_GROUPS, children, strict=True):
        if not isinstance(result, dict):
            raise ValueError(f"schema:child:{group}:not an object")
        stage = f"precompile:{group}"
        if result.get("stage") != stage or result.get("group") != group:
            raise ValueError(f"schema:child:{group}:stage mismatch")
        stage_facts.append(_check_stage(result, by_stage[stage], f"stage:{stage}"))
    worker = _field(parent, "worker", "parent")
    if not isinstance(worker, dict) or worker.get("stage") != "worker":
        raise ValueError("schema:parent.worker:missing worker result")
    if parent.get("staging_rss_watchdog_bytes") != STAGING_RSS_WATCHDOG:
        raise ValueError("source:parent staging watchdog provenance is not fixed")
    for group, result in zip(JIT_GROUPS, children, strict=True):
        if result.get("rss_watchdog_bytes") != STAGING_RSS_WATCHDOG:
            raise ValueError(f"source:child:{group} staging watchdog provenance is not fixed")
    worker_watchdog = MPI1_SOLVER_RSS_LIMIT if expected_size == 1 else None
    if parent.get("rss_watchdog_bytes") != worker_watchdog or worker.get("rss_watchdog_bytes") != worker_watchdog:
        raise ValueError("source:worker watchdog provenance is not fixed")
    stage_facts.append(_check_stage(worker, by_stage["worker"], "stage:worker"))

    peak = max(int(sample["rss_bytes"]) for sample in samples if sample["rss_bytes"] is not None)
    max_swap = max(int(sample["swap_bytes"]) for sample in samples if sample["swap_bytes"] is not None)
    readable = all(_sample_effectively_readable(sample) for sample in samples)
    summary = _field(parent, "process", "parent")
    if not isinstance(summary, dict) or summary != {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "max_swap_bytes": max_swap,
        "all_status_readable": readable,
    }:
        raise ValueError("lifecycle:parent.process does not match raw timeline")
    if max_swap != 0 or not readable:
        raise ValueError("lifecycle:process swap/readability Gate failed")
    if expected_size == 1 and peak >= RSS_HARD:
        raise ValueError(f"resource:parent process peak {peak} >= {RSS_HARD}")
    worker_peak = int(worker["peak_rss_bytes"])
    if expected_size == 1 and worker_peak >= MPI1_SOLVER_RSS_LIMIT:
        raise ValueError(
            f"resource:solver worker peak {worker_peak} >= {MPI1_SOLVER_RSS_LIMIT}"
        )
    return {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "worker_peak_rss_bytes": worker_peak,
        "max_swap_bytes": max_swap,
        "all_status_readable": readable,
        "stages": stage_facts,
    }


def _check_cache(parent: dict[str, Any], worker: dict[str, Any], root: Path) -> dict[str, Any]:
    cache = root / "jit_cache"
    facts = _field(parent, "cache", "parent")
    initial = _field(facts, "initial", "parent.cache")
    empty_manifest = {
        "cache_dir": str(cache),
        "artifacts": [],
        "artifact_count": 0,
    }
    empty_hash = hashlib.sha256(
        json.dumps(
            empty_manifest, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()
    if initial != {"artifact_count": 0, "manifest_sha256": empty_hash}:
        raise ValueError("cache:initial cache is not empty or has a stale hash")
    actual = _cache_snapshot(cache)
    before = _field(facts, "before_worker", "parent.cache")
    after = _field(facts, "after_worker", "parent.cache")
    if before is None or after is None or before != after or after != actual:
        raise ValueError("cache:before/after cache snapshot changed or is stale")
    worker_cache = _field(worker, "cache", "worker")
    if worker_cache.get("path") != "jit_cache" or worker_cache.get("binding") is not True:
        raise ValueError("cache:worker cache binding is not explicit")
    if Path(worker_cache.get("xdg_cache_home", "")).resolve() != cache.resolve():
        raise ValueError("cache:worker XDG_CACHE_HOME is not root/jit_cache")
    if worker_cache.get("snapshot") != before:
        raise ValueError("cache:worker snapshot does not match before_worker")
    return {"initial": initial, "before_worker": before, "after_worker": after}


def _check_markers(parent: dict[str, Any], root: Path, expected_sha: str, expected_size: int) -> list[str]:
    descriptor = _field(parent, "markers", "parent")
    if not isinstance(descriptor, dict):
        raise ValueError("schema:parent.markers:missing")
    manifest_path = _relative_path(root, descriptor.get("manifest_relative_path"), "marker manifest")
    if _sha256(manifest_path) != descriptor.get("manifest_sha256"):
        raise ValueError("source:marker manifest hash mismatch")
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, list) or [row.get("name") for row in manifest] != list(MARKER_ORDER):
        raise ValueError("lifecycle:marker order is incomplete")
    if descriptor.get("names") != list(MARKER_ORDER):
        raise ValueError("lifecycle:parent marker names are not fixed")
    marker_dir = root / "markers"
    for index, row in enumerate(manifest):
        if not isinstance(row, dict) or row.get("sha256") != _sha256(marker_dir / f"{index:03d}_{MARKER_ORDER[index]}.json"):
            raise ValueError("source:marker hash mismatch")
        marker = _load_json(marker_dir / f"{index:03d}_{MARKER_ORDER[index]}.json")
        _expect(marker, "schema", MARKER_SCHEMA, f"marker:{index}")
        _expect(marker, "name", MARKER_ORDER[index], f"marker:{index}")
        _expect(marker, "marker_index", index, f"marker:{index}")
        facts = _field(marker, "facts", f"marker:{index}")
        _expect(facts, "source_sha", expected_sha, f"marker:{index}.facts")
        _expect(facts, "mpi_size", expected_size, f"marker:{index}.facts")
        _expect(facts, "phase", PHASE, f"marker:{index}.facts")
        _expect(facts, "workflow", WORKFLOW, f"marker:{index}.facts")
    return list(MARKER_ORDER)


def _key_bytes(key: Any) -> bytes:
    return json.dumps(
        key, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _read_canonical(
    root: Path, descriptor: Any, source_name: str, expected_size: int
) -> tuple[dict[str, complex], dict[str, Any]]:
    if not isinstance(descriptor, dict):
        raise ValueError(f"schema:canonical:{source_name}:descriptor missing")
    manifest_path = _relative_path(root, descriptor.get("manifest_relative_path"), f"{source_name} manifest")
    if _sha256(manifest_path) != descriptor.get("manifest_sha256"):
        raise ValueError(f"source:canonical:{source_name}:manifest hash mismatch")
    manifest = _load_json(manifest_path)
    _expect(manifest, "schema_version", MANIFEST_SCHEMA, f"manifest:{source_name}")
    _expect(manifest, "role", "full_fe_dual", f"manifest:{source_name}")
    _expect(manifest, "mpi_size", expected_size, f"manifest:{source_name}")
    _expect(manifest, "dtype", "complex128", f"manifest:{source_name}")
    _expect(manifest, "key_digest_algorithm", KEY_DIGEST, f"manifest:{source_name}")
    shards = _field(manifest, "per_rank_shards", f"manifest:{source_name}")
    if not isinstance(shards, list) or len(shards) != expected_size:
        raise ValueError(f"source:canonical:{source_name}:rank shard closure failed")
    values: dict[str, complex] = {}
    total = 0
    duplicate_count = 0
    for expected_rank, row in enumerate(shards):
        if not isinstance(row, dict) or row.get("rank") != expected_rank:
            raise ValueError(f"source:canonical:{source_name}:rank metadata mismatch")
        shard_path = manifest_path.parent / str(row.get("filename", ""))
        if _sha256(shard_path) != row.get("file_sha256"):
            raise ValueError(f"source:canonical:{source_name}:shard hash mismatch")
        local: set[str] = set()
        finite = True
        count = 0
        with shard_path.open(encoding="utf-8") as stream:
            for line_no, line in enumerate(stream):
                if not line.strip():
                    continue
                packet = _load_json_line(line, f"{source_name}.rank{expected_rank}[{line_no}]")
                _expect(packet, "schema_version", SHARD_SCHEMA, "canonical packet")
                key = _field(packet, "key", "canonical packet")
                key_token = _key_bytes(key).decode("utf-8")
                if hashlib.sha256(key_token.encode("utf-8")).hexdigest() != packet.get("key_sha256"):
                    raise ValueError(f"source:canonical:{source_name}:key digest mismatch")
                if key_token in local or key_token in values:
                    duplicate_count += 1
                local.add(key_token)
                pair = _field(packet, "value", "canonical packet")
                if not isinstance(pair, list) or len(pair) != 2 or not all(_finite(item) for item in pair):
                    finite = False
                    raise ValueError(f"numerical:canonical:{source_name}:nonfinite packet")
                values[key_token] = complex(float(pair[0]), float(pair[1]))
                count += 1
        if row.get("packet_count") != count or row.get("dtype") != "complex128" or row.get("key_digest_algorithm") != KEY_DIGEST:
            raise ValueError(f"source:canonical:{source_name}:shard facts mismatch")
        if row.get("packet_finite") is not True or row.get("local_duplicate_count") != 0:
            raise ValueError(f"source:canonical:{source_name}:shard finite/duplicate facts mismatch")
        total += count
    if duplicate_count or manifest.get("global_summed_packet_count") != total or manifest.get("summed_local_duplicate_count") != 0:
        raise ValueError(f"source:canonical:{source_name}:global packet closure failed")
    if descriptor.get("packet_count") != total:
        raise ValueError(f"source:canonical:{source_name}:descriptor count mismatch")
    audit = manifest.get("extractor_audit")
    if not isinstance(audit, dict) or audit.get("source") != source_name or audit.get("role") != "full_fe_dual":
        raise ValueError(f"source:canonical:{source_name}:extractor audit mismatch")
    return values, {"packet_count": total, "manifest_sha256": descriptor["manifest_sha256"]}


def _check_architecture(worker: dict[str, Any]) -> None:
    architecture = _field(worker, "architecture", "worker")
    expected_false = (
        "p6_shell",
        "p6_action",
        "global_physical_aij",
        "global_dense_dtn",
        "physical_factor",
        "numeric_allgather",
    )
    for key in expected_false:
        _expect(architecture, key, False, "worker.architecture")
    _expect(architecture, "levels", [3, 1], "worker.architecture")
    _expect(architecture, "p3_only", True, "worker.architecture")
    _expect(architecture, "phase_once", "finalized_floquet_mpc_once_no_wrapper_reapply", "worker.architecture")
    action = _field(architecture, "physical_action", "worker.architecture")
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
        _expect(action, key, False, "worker.architecture.physical_action")
    _expect(action, "dtn_mode_count", 80, "worker.architecture.physical_action")
    _expect(action, "dtn_mode_manifest_sha256", MODE_MANIFEST_SHA256, "worker.architecture.physical_action")
    _expect(action, "factor_count", 0, "worker.architecture.physical_action")
    pmg = _field(architecture, "positive_pmg", "worker.architecture")
    _expect(pmg, "method", "same_mesh_hcurl_pmg_v1", "worker.architecture.positive_pmg")
    _expect(pmg, "levels", [3, 1], "worker.architecture.positive_pmg")
    _expect(pmg, "numeric_allgather", False, "worker.architecture.positive_pmg")
    _expect(pmg, "physical_solve", False, "worker.architecture.positive_pmg")


def _check_source_record(
    record: Any,
    root: Path,
    expected_size: int,
) -> tuple[str, dict[str, complex], dict[str, Any]]:
    if not isinstance(record, dict):
        raise ValueError("schema:worker.sources:entry is not an object")
    name = record.get("name")
    if name not in SOURCE_NAMES:
        raise ValueError("schema:worker.sources:unknown source")
    generation = _field(record, "generation", f"source:{name}")
    _expect(generation, "name", name, f"source:{name}.generation")
    if name == "physical_rhs":
        if generation.get("role") != "physical_dual_rhs" or "degree-3" not in str(generation.get("formula")):
            raise ValueError("source:physical_rhs generation is not degree-3 physical RHS")
        rhs_facts = generation.get("rhs_facts")
        if not isinstance(rhs_facts, dict) or rhs_facts.get("degree") != 3:
            raise ValueError("source:physical_rhs rhs_facts degree is not three")
    else:
        if generation.get("role") != "random_primal_to_physical_dual_rhs":
            raise ValueError("source:random generation is not the fixed primal RHS")
        if generation.get("source_input_unchanged_relative", 1.0) > RELATIVE_LIMIT:
            raise ValueError("numerical:random source input changed")
    before = _field(record, "rhs_before", f"source:{name}")
    after = _field(record, "rhs_after", f"source:{name}")
    for label, facts in (("before", before), ("after", after)):
        if facts.get("finite") is not True or not _finite(facts.get("norm")):
            raise ValueError(f"numerical:{name} RHS {label} is nonfinite")
    rank_facts = _field(record, "rank_input_facts", f"source:{name}")
    if not isinstance(rank_facts, list) or len(rank_facts) != expected_size:
        raise ValueError(f"source:{name} rank input facts are incomplete")
    for item in rank_facts:
        if not isinstance(item, dict) or item.get("before_sha256") != item.get("after_sha256"):
            raise ValueError(f"numerical:{name} RHS input changed")
    pc = _field(record, "pc", f"source:{name}")
    for key in ("repeat_relative", "linearity_relative", "input_unchanged_relative"):
        if not _finite(pc.get(key)) or float(pc[key]) > RELATIVE_LIMIT:
            raise ValueError(f"numerical:{name} PC {key} failed")
    if pc.get("finite") is not True or pc.get("primal_finite") is not True or pc.get("owned_slave_max") != 0.0:
        raise ValueError(f"numerical:{name} PC output facts failed")
    solver = _field(record, "solver", f"source:{name}")
    settings = _field(solver, "settings", f"source:{name}.solver")
    expected_settings = {
        "ksp_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": RESTART,
        "cycle_max_it": RESTART,
        "max_it": INNER_MAX_IT,
        "start_iteration": 0,
        "residual_limit": INNER_RESIDUAL_LIMIT,
        "residual_replacement": True,
        "initial_guess_nonzero": False,
        "first_checkpoint_iteration": None,
        "checkpoint_interval": RESTART,
    }
    for key, value in expected_settings.items():
        _expect(settings, key, value, f"source:{name}.solver.settings")
    cycles = _field(solver, "cycles", f"source:{name}.solver")
    if not isinstance(cycles, list) or not cycles:
        raise ValueError(f"numerical:{name} has no restart cycles")
    previous_end = 0
    total_matvec = 0
    total_pc_apply = 0
    for cycle in cycles:
        if (
            cycle.get("start_iteration") != previous_end
            or cycle.get("end_iteration") != previous_end + RESTART
            or cycle.get("iterations") != RESTART
        ):
            raise ValueError(f"numerical:{name} restart cycle boundary is not contiguous")
        if cycle.get("ksp_destroyed") is not True or not _finite(cycle.get("explicit_true_residual")):
            raise ValueError(f"numerical:{name} cycle facts are incomplete")
        if not _is_int(cycle.get("matvec_count")) or not _is_int(cycle.get("pc_apply_count")):
            raise ValueError(f"numerical:{name} cycle counts are incomplete")
        total_matvec += int(cycle["matvec_count"])
        total_pc_apply += int(cycle["pc_apply_count"])
        previous_end = int(cycle["end_iteration"])
        resource = cycle.get("resource")
        process_tree = resource.get("process_tree") if isinstance(resource, dict) else None
        if (
            not isinstance(process_tree, dict)
            or process_tree.get("swap_bytes") != 0
            or process_tree.get("all_status_readable") is not True
            or resource.get("job_no_swap") is not True
        ):
            raise ValueError(f"resource:{name} solver cycle swapped")
    if (
        not _finite(solver.get("final_true_residual"))
        or solver["final_true_residual"] > INNER_RESIDUAL_LIMIT
        or solver["final_true_residual"] != cycles[-1]["explicit_true_residual"]
        or solver.get("iterations") != cycles[-1].get("end_iteration")
    ):
        raise ValueError(f"numerical:{name} final true residual failed")
    if not _is_int(solver.get("iterations")) or solver["iterations"] <= 0 or solver["iterations"] > INNER_MAX_IT:
        raise ValueError(f"numerical:{name} iteration cap failed")
    if (
        solver.get("matvec_count") != total_matvec
        or solver.get("pc_apply_count") != total_pc_apply
        or solver.get("explicit_action_count") != len(cycles) + 1
        or solver.get("ksp_destroy_count") != len(cycles)
    ):
        raise ValueError(f"numerical:{name} action/KSP cycle ledger failed")
    summary = _field(solver, "resource_summary", f"source:{name}.solver")
    if summary.get("sample_count") != len(cycles) or summary.get("max_swap_bytes") != 0 or summary.get("all_status_readable") is not True:
        raise ValueError(f"resource:{name} solver resource summary failed")
    if expected_size == 1 and summary.get("peak_memory_authority_bytes", RSS_HARD) >= MPI1_SOLVER_RSS_LIMIT:
        raise ValueError(f"resource:{name} solver peak exceeds MPI1 500MB target")
    packets, canonical = _read_canonical(root, _field(record, "canonical", f"source:{name}"), name, expected_size)
    return name, packets, {
        "final_true_residual": float(solver["final_true_residual"]),
        "iterations": int(solver["iterations"]),
        "packet_count": canonical["packet_count"],
        "solver_peak_rss_bytes": int(summary["peak_memory_authority_bytes"]),
    }


def _check_one(parent_path: Path, expected_sha: str, expected_size: int) -> tuple[dict[str, Any], dict[str, dict[str, complex]]]:
    parent_path = parent_path.resolve()
    root = parent_path.parent
    parent = _load_json(parent_path)
    _expect(parent, "schema", PARENT_SCHEMA, "parent")
    _expect(parent, "phase", PHASE, "parent")
    _expect(parent, "workflow", WORKFLOW, "parent")
    _expect(parent, "expected_mpi_size", expected_size, "parent")
    _source_facts(_field(parent, "source", "parent"), expected_sha, "parent.source")
    if parent.get("error") is not None:
        results = list(parent.get("children", []))
        results.append(parent.get("worker"))
        if any(
            isinstance(result, dict)
            and result.get("stop_reason") in {
                "process_tree_rss_watchdog",
                "process_tree_swap",
            }
            for result in results
        ):
            raise ValueError("resource:parent child stop reason is a resource Gate")
        raise ValueError(f"infrastructure:parent error={parent['error']}")
    worker_result = _field(parent, "worker", "parent")
    if not isinstance(worker_result, dict):
        raise ValueError("schema:parent.worker:missing")
    process = _check_process(parent, root, expected_size)
    _check_markers(parent, root, expected_sha, expected_size)
    worker_path = _relative_path(root, _field(parent["paths"], "worker_record", "parent.paths"), "worker record")
    if _sha256(worker_path) != worker_result.get("record_sha256") or worker_result.get("record_present") is not True:
        raise ValueError("source:worker record hash/presence mismatch")
    worker = _load_json(worker_path)
    _expect(worker, "schema", WORKER_SCHEMA, "worker")
    _check_cache(parent, worker, root)
    _source_facts(_field(worker, "source", "worker"), expected_sha, "worker.source")
    runtime = _field(worker, "runtime", "worker")
    _expect(runtime, "mpi_size", expected_size, "worker.runtime")
    _expect(runtime, "petsc_scalar_type", "complex128", "worker.runtime")
    _expect(runtime, "petsc_int_type", "int32", "worker.runtime")
    if any(value != "1" for value in _field(runtime, "threads", "worker.runtime").values()):
        raise ValueError("source:worker runtime thread ABI is not fixed to one")
    input_facts = _field(worker, "input", "worker")
    _expect(input_facts, "template_relative_path", "input/templates/full3d_iterative_example.dat", "worker.input")
    _expect(input_facts, "template_sha256", INPUT_SHA256, "worker.input")
    _expect(input_facts, "resolved_config_sha256", RESOLVED_SHA256, "worker.input")
    _expect(input_facts, "physical_model_sha256", PHYSICAL_MODEL_SHA256, "worker.input")
    mode = _field(worker, "mode_inventory", "worker")
    _expect(mode, "mode_count", 80, "worker.mode_inventory")
    _expect(mode, "mode_manifest_sha256", MODE_MANIFEST_SHA256, "worker.mode_inventory")
    _expect(mode, "degree", 3, "worker.mode_inventory")
    _expect(mode, "mesh_target_size_nm", 50.0, "worker.mode_inventory")
    _check_architecture(worker)
    records = _field(worker, "sources", "worker")
    if not isinstance(records, list) or [item.get("name") for item in records] != list(SOURCE_NAMES):
        raise ValueError("schema:worker.sources:fixed source order is missing")
    source_maps: dict[str, dict[str, complex]] = {}
    source_metrics = {}
    for record in records:
        name, packets, metrics = _check_source_record(record, root, expected_size)
        source_maps[name] = packets
        source_metrics[name] = metrics
    facts = {
        "process": process,
        "sources": source_metrics,
        "mpi_size": expected_size,
        "cache": _field(parent, "cache", "parent"),
    }
    return facts, source_maps


def _classify(error: str) -> str:
    if error.startswith("resource:"):
        return "Q1_PHYSICAL_INNER_RESOURCE_GATE_FAIL"
    if error.startswith("numerical:"):
        return "Q1_PHYSICAL_INNER_NUMERICAL_GATE_FAIL"
    if error.startswith("mpi_identity:"):
        return "Q1_PHYSICAL_INNER_MPI_IDENTITY_GATE_FAIL"
    return "INFRASTRUCTURE_FAILURE_RETRYABLE"


def _compact_failure(error: str) -> dict[str, Any]:
    return {
        "schema": CHECKER_SCHEMA,
        "passed": False,
        "classification": _classify(error),
        "errors": [error],
        "evidence_kind": {
            "process": "measured",
            "solver": "measured",
            "canonical": "derived",
        },
    }


def check_artifact(parent_record: str | Path, expected_source_sha: str, expected_mpi_size: int) -> dict[str, Any]:
    try:
        facts, _maps = _check_one(Path(parent_record), expected_source_sha, int(expected_mpi_size))
        return {
            "schema": CHECKER_SCHEMA,
            "passed": True,
            "classification": "Q1_PHYSICAL_INNER_PASS",
            "errors": [],
            "metrics": facts,
            "evidence_kind": {
                "process": "measured",
                "solver": "measured",
                "canonical": "derived",
                "cache": "derived",
            },
        }
    except Exception as exc:
        return _compact_failure(str(exc))


def check_pair(
    mpi1_parent_record: str | Path,
    mpi2_parent_record: str | Path,
    expected_source_sha: str,
) -> dict[str, Any]:
    try:
        facts1, maps1 = _check_one(Path(mpi1_parent_record), expected_source_sha, 1)
        facts2, maps2 = _check_one(Path(mpi2_parent_record), expected_source_sha, 2)
        for name in SOURCE_NAMES:
            left = maps1[name]
            right = maps2[name]
            if set(left) != set(right):
                raise ValueError(f"mpi_identity:{name} canonical key set differs")
            numerator = math.fsum(
                abs(left[key] - right[key]) ** 2 for key in left
            )
            denominator = math.fsum(abs(right[key]) ** 2 for key in right)
            relative = math.sqrt(numerator / max(denominator, _TINY))
            if not math.isfinite(relative) or relative > 1.0e-10:
                raise ValueError(f"mpi_identity:{name} canonical relative={relative}")
            facts1.setdefault("mpi_relative", {})[name] = relative
        return {
            "schema": CHECKER_SCHEMA,
            "passed": True,
            "classification": "Q1_PHYSICAL_INNER_PAIR_PASS",
            "errors": [],
            "metrics": {"mpi1": facts1, "mpi2": facts2},
            "evidence_kind": {
                "process": "measured",
                "solver": "measured",
                "canonical": "derived",
                "mpi_relative": "derived",
            },
        }
    except Exception as exc:
        return _compact_failure(str(exc))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpi1-parent", required=True)
    parser.add_argument("--mpi2-parent")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    if args.mpi2_parent is None:
        result = check_artifact(args.mpi1_parent, args.expected_source_sha, 1)
    else:
        result = check_pair(
            args.mpi1_parent, args.mpi2_parent, args.expected_source_sha
        )
    encoded = (json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    with Path(args.output).open("xb") as stream:
        stream.write(encoded)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
