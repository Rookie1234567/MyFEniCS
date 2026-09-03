"""Independent checker for the V16 Q2 reference correction artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any


BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
PHASE = "q2-reference-correction"
WORKFLOW = "q2-reference-checkpoint-correction"
CHECKER_SCHEMA = "task038.v16.q2.checker.v1"
PARENT_SCHEMA = "task038.v16.q2.parent.v1"
WORKER_SCHEMA = "task038.v16.q2.worker.v1"
PROCESS_SCHEMA = "task038.v16.q1.source-authority.process-sample.v1"
MARKER_SCHEMA = "task038.v16.q2.marker.v1"
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
    "checkpoint_restored",
    "residual_reproduced",
    "inner_complete",
    "correction_measured",
    "release_complete",
    "record_written",
)
INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
RESOLVED_CONFIG_SHA256 = "78dc49b3a7ae212dec6374fde09eaaa231c131ce64790202da062b3ca2b09aad"
PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
CHECKPOINT_MANIFEST_SHA256 = "7f7d6fd29e6a3d6130de439fa510a19c6830061f59090cfd9f6ee4c51d8eb139"
CHECKPOINT_SOLUTION_SHA256 = "00f55e5256e673687942f79d98398d0fd2524d6d956c3b7ef5264615ab2c659b"
CHECKPOINT_SOURCE_SHA = "ee5920b9fa977a39fea7bc09cfbe155303acdb2d"
CHECKPOINT_INPUT_IDENTITY = "754dbf810cc38b32804bced03b8d4b8f702d5943671724e7529f47cadefe8b1f"
CHECKPOINT_OPERATOR_IDENTITY = "bbe5737b41b56c9dddb0c0ae3e0dd0384197dc22dd2faf41a2c57cc781f0a6f3"
CHECKPOINT_RESIDUAL = 0.4837947981092168
RSS_HARD = 2_000_000_000
RSS_WATCHDOG = 1_950_000_000
INNER_MAX_IT = 10_000
INNER_LIMIT = 1.0e-6
REPRO_LIMIT = 1.0e-11
RHO_REF_LIMIT = 0.70
RHO3_LIMIT = 0.10
RELATIVE_LIMIT = 1.0e-12
REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINT_RELATIVE = Path(
    "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/"
    "j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d/"
    "checkpoints/checkpoint-1000"
)


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
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"schema:cannot read {path}") from exc


def _load_line(line: str, label: str) -> Any:
    try:
        return json.loads(
            line, object_pairs_hook=_reject_pairs, parse_constant=_reject_constant
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
        "input_sha256": INPUT_SHA256,
    }
    for key, item in expected.items():
        _expect(source, key, item, label)
    for key in ("python_executable", "python_prefix", "input_path"):
        if not isinstance(_field(source, key, label), str):
            raise ValueError(f"source:{label}.{key}:expected string")


def _effective_readable(sample: dict[str, Any]) -> bool:
    return sample.get("all_status_readable") is True or (
        sample.get("all_status_readable") is False
        and sample.get("process_tree_exit_race_observed") is True
        and type(sample.get("worker_exit_code_observed_after_sample")) is int
        and sample["worker_exit_code_observed_after_sample"] == 0
        and sample.get("rss_bytes") is None
        and sample.get("swap_bytes") is None
    )


def _check_sample(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"schema:{label}:sample is not an object")
    _expect(value, "schema", PROCESS_SCHEMA, label)
    if value.get("stage") not in STAGE_ORDER:
        raise ValueError(f"schema:{label}.stage:unknown")
    if not isinstance(_field(value, "all_status_readable", label), bool):
        raise ValueError(f"schema:{label}.all_status_readable:invalid")
    for key in ("rss_bytes", "swap_bytes"):
        item = _field(value, key, label)
        if item is not None and (not _is_int(item) or item < 0):
            raise ValueError(f"schema:{label}.{key}:invalid")
    compiler = _field(value, "compiler_descendant_count", label)
    if not _is_int(compiler) or compiler < 0:
        raise ValueError(f"schema:{label}.compiler_descendant_count:invalid")
    if value.get("exit_code") is not None and not _is_int(value["exit_code"]):
        raise ValueError(f"schema:{label}.exit_code:invalid")
    race = value.get("process_tree_exit_race_observed")
    observed = value.get("worker_exit_code_observed_after_sample")
    if race is not None and not isinstance(race, bool):
        raise ValueError(f"schema:{label}.exit-race flag:invalid")
    if observed is not None and not _is_int(observed):
        raise ValueError(f"schema:{label}.exit-race code:invalid")
    if race is True and not _effective_readable(value):
        raise ValueError(f"lifecycle:{label}:invalid exit-race annotation")
    if race is not True and observed is not None:
        raise ValueError(f"lifecycle:{label}:unbound exit-race code")
    return value


def _check_stage(
    result: Any, samples: list[dict[str, Any]], expected_stage: str
) -> dict[str, Any]:
    label = f"stage:{expected_stage}"
    if not isinstance(result, dict):
        raise ValueError(f"schema:{label}:result is not an object")
    _expect(result, "stage", expected_stage, label)
    if result.get("returncode") != 0 or not _is_int(result["returncode"]):
        raise ValueError(f"lifecycle:{label}:returncode is not zero")
    if result.get("stop_reason") is not None:
        prefix = (
            "resource"
            if result["stop_reason"] in {"process_tree_rss_watchdog", "process_tree_swap"}
            else "lifecycle"
        )
        raise ValueError(f"{prefix}:{label}:stop_reason={result['stop_reason']}")
    if result.get("signals") != []:
        raise ValueError(f"lifecycle:{label}:signals are not empty")
    if result.get("process_group_gone") is not True or result.get("lifecycle_failure") is not False:
        raise ValueError(f"lifecycle:{label}:process group did not close")
    live = [item for item in samples if item.get("exit_code") is None]
    exits = [item for item in samples if item.get("exit_code") is not None]
    if result.get("sample_count") != len(live) or len(exits) != 1:
        raise ValueError(f"lifecycle:{label}:sample/exit count does not close")
    if exits[0].get("exit_code") != 0:
        raise ValueError(f"lifecycle:{label}:exit code is not zero")
    rss = [item["rss_bytes"] for item in samples if item["rss_bytes"] is not None]
    swaps = [item["swap_bytes"] for item in samples if item["swap_bytes"] is not None]
    if not rss or not swaps:
        raise ValueError(f"lifecycle:{label}:no usable process measurement")
    if result.get("peak_rss_bytes") != max(rss) or result.get("max_swap_bytes") != max(swaps):
        raise ValueError(f"lifecycle:{label}:summary does not match timeline")
    if result.get("all_status_readable") is not all(_effective_readable(item) for item in samples):
        raise ValueError(f"lifecycle:{label}:readability does not match timeline")
    if exits[0].get("compiler_descendant_count") != 0:
        raise ValueError(f"lifecycle:{label}:exit has compiler descendants")
    return {
        "peak_rss_bytes": int(result["peak_rss_bytes"]),
        "max_swap_bytes": int(result["max_swap_bytes"]),
        "all_status_readable": bool(result["all_status_readable"]),
    }


def _check_process(parent: dict[str, Any], root: Path) -> dict[str, Any]:
    process_path = _relative_path(
        root, _field(parent["paths"], "process_samples", "parent.paths"), "process"
    )
    samples: list[dict[str, Any]] = []
    with process_path.open(encoding="utf-8") as stream:
        for index, line in enumerate(stream):
            if line.strip():
                samples.append(_check_sample(_load_line(line, f"process[{index}]"), f"process[{index}]"))
    if not samples:
        raise ValueError("lifecycle:process timeline is empty")
    by_stage: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for sample in samples:
        stage = sample["stage"]
        if stage not in by_stage:
            by_stage[stage] = []
            order.append(stage)
        by_stage[stage].append(sample)
    if tuple(order) != STAGE_ORDER:
        raise ValueError("lifecycle:process stage order is not fixed cold order")
    children = _field(parent, "children", "parent")
    if not isinstance(children, list) or len(children) != len(JIT_GROUPS):
        raise ValueError("schema:parent.children:expected seven groups")
    stage_facts = []
    for group, child in zip(JIT_GROUPS, children, strict=True):
        if not isinstance(child, dict) or child.get("group") != group:
            raise ValueError(f"schema:child:{group}:group mismatch")
        stage = f"precompile:{group}"
        stage_facts.append(_check_stage(child, by_stage[stage], stage))
        _relative_path(root, child.get("record"), f"child:{group}.record")
        if child.get("rss_watchdog_bytes") != RSS_WATCHDOG:
            raise ValueError(f"source:child:{group}:watchdog mismatch")
    worker = _field(parent, "worker", "parent")
    if not isinstance(worker, dict):
        raise ValueError("schema:parent.worker:missing")
    stage_facts.append(_check_stage(worker, by_stage["worker"], "worker"))
    if parent.get("staging_rss_watchdog_bytes") != RSS_WATCHDOG:
        raise ValueError("source:parent.staging watchdog mismatch")
    if parent.get("rss_watchdog_bytes") != RSS_WATCHDOG or worker.get("rss_watchdog_bytes") != RSS_WATCHDOG:
        raise ValueError("source:worker watchdog mismatch")
    peak = max(item["rss_bytes"] for item in samples if item["rss_bytes"] is not None)
    swap = max(item["swap_bytes"] for item in samples if item["swap_bytes"] is not None)
    readable = all(_effective_readable(item) for item in samples)
    expected_process = {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": readable,
    }
    if _field(parent, "process", "parent") != expected_process:
        raise ValueError("lifecycle:parent.process does not match raw timeline")
    if swap != 0 or not readable:
        raise ValueError("resource:parent swap/readability Gate failed")
    if peak >= RSS_HARD:
        raise ValueError(f"resource:parent peak {peak} >= {RSS_HARD}")
    return {
        "sample_count": len(samples),
        "peak_rss_bytes": peak,
        "max_swap_bytes": swap,
        "all_status_readable": readable,
        "worker_peak_rss_bytes": stage_facts[-1]["peak_rss_bytes"],
    }


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
    manifest = {"cache_dir": str(cache), "artifacts": artifacts, "artifact_count": len(artifacts)}
    encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"artifact_count": len(artifacts), "manifest_sha256": hashlib.sha256(encoded).hexdigest()}


def _check_cache(parent: dict[str, Any], worker: dict[str, Any], root: Path) -> dict[str, Any]:
    cache = (root / _field(parent["paths"], "jit_cache", "parent.paths")).resolve()
    facts = _field(parent, "cache", "parent")
    empty = {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}
    empty_hash = hashlib.sha256(json.dumps(empty, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    if _field(facts, "initial", "parent.cache") != {"artifact_count": 0, "manifest_sha256": empty_hash}:
        raise ValueError("cache:initial cache is not empty")
    before = _field(facts, "before_worker", "parent.cache")
    after = _field(facts, "after_worker", "parent.cache")
    actual = _cache_snapshot(cache)
    if before is None or before != after or after != actual:
        raise ValueError("cache:before/after cache snapshot does not close")
    worker_cache = _field(worker, "cache", "worker")
    if worker_cache.get("path") != "jit_cache" or worker_cache.get("binding") is not True:
        raise ValueError("cache:worker binding is not explicit")
    if Path(worker_cache.get("xdg_cache_home", "")).resolve() != cache:
        raise ValueError("cache:worker XDG_CACHE_HOME is not root/jit_cache")
    if worker_cache.get("snapshot") != before:
        raise ValueError("cache:worker snapshot does not match parent")
    return {"initial": facts["initial"], "before_worker": before, "after_worker": after}


def _check_markers(parent: dict[str, Any], root: Path, source_sha: str) -> list[str]:
    descriptor = _field(parent, "markers", "parent")
    manifest_path = _relative_path(root, descriptor.get("manifest_relative_path"), "marker manifest")
    if _sha256(manifest_path) != descriptor.get("manifest_sha256"):
        raise ValueError("source:marker manifest hash mismatch")
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, list) or [row.get("name") for row in manifest] != list(MARKER_ORDER):
        raise ValueError("lifecycle:marker order is incomplete")
    if descriptor.get("names") != list(MARKER_ORDER):
        raise ValueError("lifecycle:marker names are not fixed")
    marker_dir = root / "markers"
    for index, name in enumerate(MARKER_ORDER):
        path = marker_dir / f"{index:03d}_{name}.json"
        if not path.is_file() or manifest[index].get("sha256") != _sha256(path):
            raise ValueError(f"source:marker:{name}:hash mismatch")
        marker = _load_json(path)
        _expect(marker, "schema", MARKER_SCHEMA, f"marker:{name}")
        _expect(marker, "name", name, f"marker:{name}")
        _expect(marker, "marker_index", index, f"marker:{name}")
        facts = _field(marker, "facts", f"marker:{name}")
        _expect(facts, "phase", PHASE, f"marker:{name}.facts")
        _expect(facts, "workflow", WORKFLOW, f"marker:{name}.facts")
        _expect(facts, "source_sha", source_sha, f"marker:{name}.facts")
        _expect(facts, "mpi_size", 1, f"marker:{name}.facts")
        if name == "inner_complete":
            if "cycles" in facts or "history" in facts:
                raise ValueError("schema:inner_complete marker is not compact")
            required = {"iterations", "final_true_residual", "matvec_count", "pc_apply_count", "ksp_destroy_count", "restart_workspace_destroyed"}
            if set(facts) - required - {"phase", "workflow", "source_sha", "mpi_size"}:
                raise ValueError("schema:inner_complete marker contains non-scalar payload")
    return list(MARKER_ORDER)


def _check_checkpoint() -> None:
    directory = REPO_ROOT / CHECKPOINT_RELATIVE
    manifest_path = directory / "manifest.json"
    if _sha256(manifest_path) != CHECKPOINT_MANIFEST_SHA256:
        raise ValueError("source:checkpoint manifest hash mismatch")
    manifest = _load_json(manifest_path)
    expected = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 1000,
        "mpi_size": 1,
        "input_identity_sha256": CHECKPOINT_INPUT_IDENTITY,
        "operator_identity_sha256": CHECKPOINT_OPERATOR_IDENTITY,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "source_sha": CHECKPOINT_SOURCE_SHA,
        "explicit_true_residual": CHECKPOINT_RESIDUAL,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
    }
    for key, value in expected.items():
        actual = manifest.get(key)
        if isinstance(value, float):
            if not _finite(actual) or not math.isclose(float(actual), value, rel_tol=1.0e-14, abs_tol=1.0e-15):
                raise ValueError(f"source:checkpoint.{key}:mismatch")
        elif actual != value:
            raise ValueError(f"source:checkpoint.{key}:mismatch")
    if set(manifest.get("forbidden_vector_roles", ())) != {
        "action",
        "residual",
        "krylov_basis",
    }:
        raise ValueError("source:checkpoint forbidden vector roles mismatch")
    ranks = manifest.get("ranks")
    if not isinstance(ranks, list) or len(ranks) != 1 or ranks[0].get("rank") != 0:
        raise ValueError("source:checkpoint rank metadata mismatch")
    descriptor = ranks[0].get("solution")
    if not isinstance(descriptor, dict) or descriptor.get("sha256") != CHECKPOINT_SOLUTION_SHA256:
        raise ValueError("source:checkpoint solution hash mismatch")
    solution_path = directory / str(descriptor.get("relative_path", ""))
    if _sha256(solution_path) != CHECKPOINT_SOLUTION_SHA256:
        raise ValueError("source:checkpoint solution file hash mismatch")


def _check_vector_facts(vectors: Any) -> None:
    if not isinstance(vectors, dict):
        raise ValueError("schema:vectors:missing")
    required = ("checkpoint_solution", "rhs_before", "rhs_after", "r6_before", "r6_after", "r6_new", "r3_before", "r3_after", "r3_new", "correction")
    for name in required:
        facts = _field(vectors, name, "vectors")
        if not _finite(facts.get("norm")) or float(facts["norm"]) < 0.0 or facts.get("finite") is not True:
            raise ValueError(f"numerical:vectors.{name}:nonfinite")
        if not _finite(facts.get("owned_slave_max")) or float(facts["owned_slave_max"]) < 0.0:
            raise ValueError(f"numerical:vectors.{name}:slave fact invalid")
        if not isinstance(facts.get("array_sha256"), str) or len(facts["array_sha256"]) != 64:
            raise ValueError(f"schema:vectors.{name}:hash missing")
    for name in required:
        if vectors[name]["owned_slave_max"] != 0.0:
            raise ValueError(f"numerical:{name} is not slave-zero")
    for before, after in (("rhs_before", "rhs_after"), ("r6_before", "r6_after"), ("r3_before", "r3_after")):
        if vectors[before]["array_sha256"] != vectors[after]["array_sha256"]:
            raise ValueError(f"numerical:{before} input changed")


def _check_inner(inner: Any) -> dict[str, Any]:
    settings = _field(inner, "settings", "inner")
    expected = {
        "ksp_type": "fgmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 20,
        "cycle_max_it": 20,
        "max_it": INNER_MAX_IT,
        "start_iteration": 0,
        "residual_limit": INNER_LIMIT,
        "residual_replacement": True,
        "initial_guess_nonzero": False,
        "first_checkpoint_iteration": None,
        "checkpoint_interval": 20,
    }
    for key, value in expected.items():
        _expect(settings, key, value, "inner.settings")
    cycles = _field(inner, "cycles", "inner")
    if not isinstance(cycles, list) or not cycles:
        raise ValueError("numerical:inner has no cycles")
    previous_end = 0
    total_matvec = total_pc = 0
    for index, cycle in enumerate(cycles):
        if (
            cycle.get("cycle_index") != index
            or cycle.get("start_iteration") != previous_end
            or cycle.get("iterations") != 20
            or cycle.get("end_iteration") != previous_end + 20
        ):
            raise ValueError("numerical:inner cycle boundary is not restart-20")
        if cycle.get("ksp_destroyed") is not True or not _finite(cycle.get("explicit_true_residual")):
            raise ValueError("numerical:inner cycle facts are incomplete")
        if not _is_int(cycle.get("matvec_count")) or not _is_int(cycle.get("pc_apply_count")):
            raise ValueError("numerical:inner cycle counts are invalid")
        total_matvec += cycle["matvec_count"]
        total_pc += cycle["pc_apply_count"]
        resource = _field(cycle, "resource", "inner.cycle")
        process_tree = _field(resource, "process_tree", "inner.cycle.resource")
        if process_tree.get("swap_bytes") != 0 or process_tree.get("all_status_readable") is not True or resource.get("job_no_swap") is not True:
            raise ValueError("resource:inner cycle swap/readability failed")
        previous_end = cycle["end_iteration"]
    final = _field(inner, "final_true_residual", "inner")
    if not _finite(final) or final > INNER_LIMIT or final != cycles[-1]["explicit_true_residual"]:
        raise ValueError("numerical:inner final true residual failed")
    if inner.get("iterations") != cycles[-1]["end_iteration"] or inner["iterations"] > INNER_MAX_IT:
        raise ValueError("numerical:inner iteration cap failed")
    if inner.get("matvec_count") != total_matvec or inner.get("pc_apply_count") != total_pc:
        raise ValueError("numerical:inner matvec/PC ledger failed")
    if inner.get("explicit_action_count") != len(cycles) + 1 or inner.get("ksp_destroy_count") != len(cycles):
        raise ValueError("numerical:inner explicit/KSP ledger failed")
    return {
        "iterations": int(inner["iterations"]),
        "final_true_residual": float(final),
        "matvec_count": int(inner["matvec_count"]),
        "pc_apply_count": int(inner["pc_apply_count"]),
        "explicit_action_count": int(inner["explicit_action_count"]),
    }


def _check_worker(parent: dict[str, Any], worker: dict[str, Any], root: Path) -> dict[str, Any]:
    _expect(worker, "schema", WORKER_SCHEMA, "worker")
    _expect(worker, "raw_facts_only", True, "worker")
    source = _field(worker, "source", "worker")
    _source_facts(source, parent["source"]["commit_sha"], "worker.source")
    runtime = _field(worker, "runtime", "worker")
    _expect(runtime, "mpi_size", 1, "worker.runtime")
    _expect(runtime, "petsc_scalar_type", "complex128", "worker.runtime")
    _expect(runtime, "petsc_int_type", "int32", "worker.runtime")
    threads = _field(runtime, "threads", "worker.runtime")
    if not isinstance(threads, dict) or any(value != "1" for value in threads.values()):
        raise ValueError("source:worker thread ABI is not one")
    facts = _field(worker, "facts", "worker")
    input_facts = _field(facts, "input_facts", "worker.facts")
    _expect(input_facts, "template_relative_path", "input/templates/full3d_iterative_example.dat", "worker.input")
    _expect(input_facts, "template_sha256", INPUT_SHA256, "worker.input")
    _expect(input_facts, "resolved_config_sha256", RESOLVED_CONFIG_SHA256, "worker.input")
    _expect(input_facts, "physical_model_sha256", PHYSICAL_MODEL_SHA256, "worker.input")
    checkpoint_authority = _field(facts, "checkpoint_authority", "worker.facts")
    _expect(checkpoint_authority, "manifest_sha256", CHECKPOINT_MANIFEST_SHA256, "worker.checkpoint")
    _expect(checkpoint_authority, "solution_sha256", CHECKPOINT_SOLUTION_SHA256, "worker.checkpoint")
    _expect(checkpoint_authority, "source_sha", CHECKPOINT_SOURCE_SHA, "worker.checkpoint")
    mode = _field(facts, "provenance", "worker.facts")
    for key, value in {
        "input_sha256": INPUT_SHA256,
        "resolved_config_sha256": RESOLVED_CONFIG_SHA256,
        "physical_model_sha256": PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": MODE_MANIFEST_SHA256,
    }.items():
        _expect(mode, key, value, "worker.provenance")
    architecture = _field(facts, "architecture", "worker.facts")
    for key in ("p6_pre_post_smoother", "global_physical_aij", "dense_dtn", "physical_factor", "numeric_allgather"):
        _expect(architecture, key, False, "worker.architecture")
    _expect(architecture, "p3_positive_pc", "setup_owned_lower_cycle", "worker.architecture")
    transfer_audit = _field(facts, "p63_transfer", "worker.facts")
    _expect(transfer_audit, "pair_fine_to_coarse", [6, 3], "worker.p63_transfer")
    for key in ("global_transfer_matrix", "numeric_allgather", "static_condensation"):
        _expect(transfer_audit, key, False, "worker.p63_transfer")
    action_audit = _field(facts, "actions", "worker.facts")
    for degree in ("p6", "p3"):
        audit = _field(action_audit, degree, "worker.actions")
        for key in (
            "global_aij_materialized",
            "global_schur_materialized",
            "ksp_created",
            "numeric_allgather",
            "t4_transmission_included",
        ):
            _expect(audit, key, False, f"worker.actions.{degree}")
    rhs = _field(facts, "rhs", "worker.facts")
    _expect(rhs, "degree", 6, "worker.rhs")
    _expect(rhs, "role", "physical_maxwell_rhs", "worker.rhs")
    _expect(rhs, "mode_manifest_sha256", MODE_MANIFEST_SHA256, "worker.rhs")
    _check_vector_facts(_field(facts, "vectors", "worker.facts"))
    inner = _check_inner(_field(facts, "inner", "worker.facts"))
    vectors = facts["vectors"]
    checkpoint = _field(facts, "checkpoint", "worker.facts")
    _expect(checkpoint, "manifest_sha256", CHECKPOINT_MANIFEST_SHA256, "worker.checkpoint")
    _expect(checkpoint, "restored_shard_sha256", CHECKPOINT_SOLUTION_SHA256, "worker.checkpoint")
    recomputed = vectors["r6_before"]["norm"] / max(vectors["rhs_before"]["norm"], 1.0e-300)
    if not math.isclose(recomputed, CHECKPOINT_RESIDUAL, rel_tol=1.0e-11, abs_tol=1.0e-15):
        raise ValueError("numerical:checkpoint residual reproduction failed")
    if not math.isclose(float(checkpoint.get("recomputed_residual")), recomputed, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise ValueError("numerical:checkpoint recomputed residual is not raw-norm derived")
    reproduction = abs(recomputed - CHECKPOINT_RESIDUAL) / max(abs(CHECKPOINT_RESIDUAL), 1.0e-300)
    if not math.isclose(float(checkpoint.get("reproduction_relative")), reproduction, rel_tol=1.0e-12, abs_tol=1.0e-15) or reproduction > REPRO_LIMIT:
        raise ValueError("numerical:checkpoint reproduction Gate failed")
    correction = _field(facts, "correction", "worker.facts")
    projected_constraint = correction.get("projected_full_constraint_residual")
    if (
        correction.get("finite") is not True
        or not _finite(projected_constraint)
        or projected_constraint < 0.0
        or projected_constraint > 1.0e-12
        or correction.get("algebraic_owned_slave_max") != 0.0
    ):
        raise ValueError("numerical:correction constraint/slave Gate failed")
    rho_ref = vectors["r6_new"]["norm"] / max(vectors["r6_before"]["norm"], 1.0e-300)
    rho3 = vectors["r3_new"]["norm"] / max(vectors["r3_before"]["norm"], 1.0e-300)
    if not _finite(rho_ref) or not _finite(rho3) or not math.isclose(float(correction.get("rho_ref")), rho_ref, rel_tol=1.0e-12, abs_tol=1.0e-15) or not math.isclose(float(correction.get("rho3")), rho3, rel_tol=1.0e-12, abs_tol=1.0e-15):
        raise ValueError("numerical:correction rho is not raw-norm derived")
    if rho_ref > RHO_REF_LIMIT or rho3 > RHO3_LIMIT:
        raise ValueError(f"numerical:correction contraction failed rho_ref={rho_ref} rho3={rho3}")
    unchanged = _field(facts, "input_unchanged", "worker.facts")
    for key in ("checkpoint_solution_relative", "rhs_relative", "r6_relative", "r3_relative"):
        if not _finite(unchanged.get(key)) or unchanged[key] > RELATIVE_LIMIT:
            raise ValueError(f"numerical:input unchanged failed: {key}")
    ops = _field(correction, "operation_counts", "worker.correction")
    p6 = _field(ops, "p6_action", "worker.operation_counts")
    p3 = _field(ops, "p3_action", "worker.operation_counts")
    lower = _field(ops, "lower_cycle", "worker.operation_counts")
    for item, expected_delta in ((p6, 2), (p3, inner["matvec_count"] + inner["explicit_action_count"]), (lower, inner["pc_apply_count"])):
        if not all(_is_int(item.get(key)) for key in ("before", "after", "delta")) or item["after"] - item["before"] != item["delta"] or item["delta"] != expected_delta:
            raise ValueError("numerical:physical operation count ledger failed")
    if p3.get("expected_from_inner") != p3["delta"] or lower.get("expected_from_inner") != lower["delta"]:
        raise ValueError("numerical:inner operation count binding failed")
    p63 = _field(ops, "p63", "worker.operation_counts")
    if p63 != {"primal": 1, "adjoint": 2}:
        raise ValueError("numerical:P63 operation count ledger failed")
    if correction.get("upper_cycle_apply_count_delta") != 0 or correction.get("p6_smoother_apply_count") != 0 or correction.get("physical_pcycle_applied") is not False:
        raise ValueError("architecture:Q2 invoked the p6 upper cycle")
    if _field(action_audit, "p6", "worker.actions").get("apply_count") != p6["after"] or _field(action_audit, "p3", "worker.actions").get("apply_count") != p3["after"]:
        raise ValueError("numerical:action audit count does not match operation ledger")
    return {
        "inner": inner,
        "recomputed_residual": recomputed,
        "rho_ref": rho_ref,
        "rho3": rho3,
        "operations": ops,
    }


def _check_one(parent_path: Path, expected_source_sha: str) -> dict[str, Any]:
    parent_path = parent_path.resolve()
    root = parent_path.parent
    parent = _load_json(parent_path)
    _expect(parent, "schema", PARENT_SCHEMA, "parent")
    _expect(parent, "phase", PHASE, "parent")
    _expect(parent, "workflow", WORKFLOW, "parent")
    _expect(parent, "expected_mpi_size", 1, "parent")
    _source_facts(_field(parent, "source", "parent"), expected_source_sha, "parent.source")
    if parent.get("error") is not None:
        results = list(parent.get("children", [])) + [parent.get("worker")]
        if any(isinstance(item, dict) and item.get("stop_reason") in {"process_tree_rss_watchdog", "process_tree_swap"} for item in results):
            raise ValueError("resource:parent child stop reason is a resource Gate")
        raise ValueError(f"infrastructure:parent error={parent['error']}")
    process = _check_process(parent, root)
    _check_markers(parent, root, expected_source_sha)
    _check_checkpoint()
    worker_result = _field(parent, "worker", "parent")
    worker_path = _relative_path(root, _field(parent["paths"], "worker_record", "parent.paths"), "worker record")
    if worker_result.get("record_present") is not True or _sha256(worker_path) != worker_result.get("record_sha256"):
        raise ValueError("source:worker record hash/presence mismatch")
    for name in ("stdout", "stderr"):
        log_path = root / f"worker.{name}.log"
        if _sha256(log_path) != worker_result.get(f"{name}_sha256"):
            raise ValueError(f"source:worker {name} hash mismatch")
    worker = _load_json(worker_path)
    cache = _check_cache(parent, worker, root)
    metrics = _check_worker(parent, worker, root)
    return {"process": process, "cache": cache, **metrics}


def _classify(error: str) -> str:
    if error.startswith("resource:"):
        return "Q2_PHYSICAL_PCOARSE_REFERENCE_RESOURCE_GATE_FAIL"
    if error.startswith("numerical:"):
        return "Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL"
    return "INFRASTRUCTURE_FAILURE_RETRYABLE"


def _failure(error: str) -> dict[str, Any]:
    return {
        "schema": CHECKER_SCHEMA,
        "passed": False,
        "classification": _classify(error),
        "errors": [error],
        "evidence_kind": {"process": "measured", "solver": "measured", "checkpoint": "derived", "cache": "derived"},
    }


def check_artifact(parent_record: str | Path, expected_source_sha: str, expected_mpi_size: int = 1) -> dict[str, Any]:
    try:
        if int(expected_mpi_size) != 1:
            raise ValueError("source:Q2 checker is fixed to MPI1")
        metrics = _check_one(Path(parent_record), expected_source_sha)
        return {
            "schema": CHECKER_SCHEMA,
            "passed": True,
            "classification": "Q2_PHYSICAL_PCOARSE_REFERENCE_PASS",
            "errors": [],
            "metrics": metrics,
            "evidence_kind": {"process": "measured", "solver": "measured", "checkpoint": "derived", "cache": "derived"},
        }
    except Exception as exc:
        return _failure(str(exc))


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    encoded = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mpi1-parent", "--parent", dest="parent", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    result = check_artifact(args.parent, args.expected_source_sha)
    try:
        _write_exclusive(Path(args.output), result)
    except Exception as exc:
        print(f"Q2 checker output failed: {exc}", flush=True)
        return 1
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
