"""Independent checker for the no-JIT J1 contract record."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


CHECKER_SCHEMA = "task038.v14.j1b.checker.v1"
RECORD_SCHEMA = "task038.v14.j1b.record.v1"
MARKER_SCHEMA = "task038.v14.j1b.marker.v1"
SAMPLE_SCHEMA = "task038.v14.j1b.process-sample.v1"
EXPECTED_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
EXPECTED_INPUT_SHA256 = "819fc99caea2dbc8ea22546917fbe3898c822a955d079b4582c4a27e34ebba41"
EXPECTED_PHYSICAL_MODEL_SHA256 = "9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f"
EXPECTED_MODE_MANIFEST_SHA256 = "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
EXPECTED_PROFILE = {
    "wavelength_nm": 13.5,
    "grazing_angle_deg": 1.0,
    "theta_deg": 89.0,
    "phi_deg": 0.0,
    "polarization": "s",
    "p_degree": 6,
    "h_nm": 10,
    "mesh_cell_type": "hexahedron",
    "mesh_spacing_mode": "boundary_fitted",
}
EXPECTED_MARKERS = (
    (0, "parent_started"),
    (1, "fresh_cache_created"),
    (37, "parent_complete"),
)
COMPILER_NAMES = frozenset(
    {"gcc", "g++", "cc1", "cc1plus", "clang", "clang++", "ld", "collect2"}
)


class ContractError(Exception):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _absolute(value: object) -> Path:
    if not isinstance(value, str) or not os.path.isabs(value):
        raise ContractError(f"path is not absolute: {value!r}")
    return Path(os.path.abspath(value))


def _read_json(path: Path) -> object:
    try:
        with path.open(encoding="utf-8") as stream:
            return json.load(stream)
    except (OSError, ValueError) as error:
        raise ContractError(f"cannot read JSON {path}: {error}") from error


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def _is_compiler(fact: dict) -> bool:
    names = {fact["comm"]}
    names.update(Path(token).name for token in fact["cmdline"].split())
    return bool(names & COMPILER_NAMES)


def _check_identity(record: dict, expected_source_sha: str) -> None:
    _require(re.fullmatch(r"[0-9a-f]{40}", expected_source_sha) is not None, "invalid expected source SHA")
    source_sha = record.get("source_sha")
    _require(isinstance(source_sha, str), "source_sha is missing")
    _require(re.fullmatch(r"[0-9a-f]{40}", source_sha) is not None, "source_sha is not a full lowercase SHA")
    _require(source_sha == expected_source_sha, "source_sha does not match CLI expectation")
    _require(record.get("schema") == RECORD_SCHEMA, "record schema mismatch")
    _require(record.get("marker_schema") == MARKER_SCHEMA, "record marker schema mismatch")
    _require(record.get("branch") == EXPECTED_BRANCH, "branch mismatch")
    _require(record.get("stage") == "j1-contract", "stage mismatch")
    _require(record.get("status") == "contract_observed", "J1 status is not contract_observed")
    _require(record.get("execution") == "no_jit", "J1 execution is not no_jit")
    identity = record.get("identity")
    _require(identity == {
        "input_sha256": EXPECTED_INPUT_SHA256,
        "physical_model_sha256": EXPECTED_PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": EXPECTED_MODE_MANIFEST_SHA256,
    }, "frozen identity mismatch")
    _require(record.get("profile") == EXPECTED_PROFILE, "exact profile mismatch")
    _require(record.get("flags") == {"compile": False, "mesh": False, "jit": False, "pde": False}, "J1 no-JIT flags mismatch")
    _require("passed" not in record and "classification" not in record, "raw record contains checker decision")

    command = record.get("command")
    _require(isinstance(command, dict), "command facts are missing")
    argv = command.get("argv")
    _require(isinstance(argv, list) and argv and all(isinstance(value, str) for value in argv), "command argv is invalid")
    _require(command.get("mode") == "j1-contract", "command mode mismatch")
    _require(command.get("source_sha") == source_sha, "command source mismatch")
    root = record.get("paths", {}).get("artifact_root")
    _require(command.get("artifact_root") == root, "command artifact root mismatch")
    _require(isinstance(command.get("executable"), str) and os.path.isabs(command["executable"]), "command executable is not absolute")
    _require(isinstance(command.get("cwd"), str) and os.path.isabs(command["cwd"]), "command cwd is not absolute")
    _require("--mode" in argv and argv[argv.index("--mode") + 1] == "j1-contract", "command does not contain j1 mode")
    _require("--source-sha" in argv and argv[argv.index("--source-sha") + 1] == source_sha, "command does not contain source SHA")
    _require("--artifact-root" in argv and argv[argv.index("--artifact-root") + 1] == root, "command does not contain artifact root")


def _check_paths(record: dict, record_argument: Path) -> dict[str, Path]:
    paths = record.get("paths")
    _require(isinstance(paths, dict), "path facts are missing")
    required = ("artifact_root", "cache_dir", "marker_dir", "record", "process_samples", "cache_manifest", "marker_manifest")
    values = {name: _absolute(paths.get(name)) for name in required}
    root = values["artifact_root"]
    _require(root.is_dir(), "artifact root is not a directory")
    _require(values["cache_dir"] == root / "jit_cache", "cache path is not root/jit_cache")
    _require(values["marker_dir"] == root / "markers", "marker path is not root/markers")
    _require(values["record"] == root / "j1_record.json", "record path is not the fixed root record")
    _require(values["record"] == record_argument, "record argument does not match record facts")
    for name in required[1:]:
        if name == "record":
            continue
        _require(values[name].is_relative_to(root), f"{name} escapes artifact root")
    _require(values["cache_dir"].is_dir(), "cache directory is missing")
    _require(values["marker_dir"].is_dir(), "marker directory is missing")
    return values


def _check_markers(record: dict, paths: dict[str, Path]) -> None:
    expected = EXPECTED_MARKERS
    marker_dir = paths["marker_dir"]
    actual_paths = sorted(path for path in marker_dir.iterdir() if path.is_file())
    _require([path.name for path in actual_paths] == [f"{index:03d}_{name}.json" for index, name in expected], "marker inventory is not the exact J1 subsequence")
    manifest_path = paths["marker_manifest"]
    manifest = _read_json(manifest_path)
    _require(isinstance(manifest, list) and len(manifest) == 3, "marker manifest is not a three-entry list")
    calculated = []
    for path, (index, name) in zip(actual_paths, expected):
        calculated.append({"name": name, "path": str(path), "sha256": _sha256(path)})
        payload = _read_json(path)
        _require(isinstance(payload, dict), f"marker {name} is not an object")
        _require(payload.get("schema") == MARKER_SCHEMA, f"marker {name} schema mismatch")
        _require(payload.get("name") == name and payload.get("marker_index") == index, f"marker {name} identity mismatch")
        _require(type(payload.get("timestamp_ns")) is int and payload["timestamp_ns"] > 0, f"marker {name} timestamp invalid")
        facts = payload.get("facts")
        _require(isinstance(facts, dict), f"marker {name} facts missing")
        common = {
            "stage": "j1-contract",
            "artifact_root": str(paths["artifact_root"]),
            "cache_dir": str(paths["cache_dir"]),
            "source_sha": record["source_sha"],
            "compile": False,
            "mesh": False,
            "jit": False,
            "pde": False,
        }
        for key, value in common.items():
            _require(facts.get(key) == value, f"marker {name} {key} mismatch")
        if name in {"parent_started", "parent_complete"}:
            _require(facts.get("record_path") == str(paths["record"]), f"marker {name} record path mismatch")
        if name == "parent_complete":
            _require(facts.get("status") == "contract_observed", "parent_complete status mismatch")
            _require(facts.get("execution") == "no_jit", "parent_complete execution mismatch")
            final_count = record.get("process", {}).get("compiler_descendant_count")
            _require(final_count == 0 and facts.get("compiler_descendant_count") == final_count, "parent_complete compiler count mismatch")
    _require(manifest == calculated, "marker manifest does not close marker hashes")
    _require(record["markers"]["manifest_path"] == str(manifest_path), "record marker manifest path mismatch")
    _require(record["markers"]["manifest_sha256"] == _sha256(manifest_path), "record marker manifest hash mismatch")
    _require(record["markers"]["names"] == [name for _, name in expected], "record marker names mismatch")


def _check_process(record: dict, paths: dict[str, Path]) -> None:
    process = record.get("process")
    _require(isinstance(process, dict), "process facts are missing")
    _require(process.get("sample_schema") == SAMPLE_SCHEMA, "record process sample schema mismatch")
    sample_path = _absolute(process.get("sample_path"))
    _require(sample_path == paths["process_samples"], "process sample path mismatch")
    _require(process.get("sample_sha256") == _sha256(sample_path), "process sample hash mismatch")
    _require(process.get("sample_count") == 1, "J1 requires exactly one process sample")
    with sample_path.open(encoding="utf-8") as stream:
        lines = [line for line in stream.read().splitlines() if line]
    _require(len(lines) == 1, "J1 process JSONL must contain one sample")
    sample = _read_json(sample_path) if sample_path.suffix == ".json" else json.loads(lines[0])
    _require(isinstance(sample, dict), "process sample is not an object")
    _require(sample.get("schema") == SAMPLE_SCHEMA, "process sample schema mismatch")
    _require(sample.get("stage") == "j1-contract", "process sample stage mismatch")
    _require(type(sample.get("root_pid")) is int and sample["root_pid"] > 0, "process root PID invalid")
    _require(type(sample.get("timestamp_ns")) is int and sample["timestamp_ns"] > 0, "process sample timestamp invalid")
    _require("exit_code" in sample and sample["exit_code"] is None, "process sample exit_code is not null")
    _require(sample.get("unreadable_pids") == [], "process sample has unreadable PIDs")
    _require(sample.get("all_status_readable") is True, "process sample is not readable")
    _require(type(sample.get("readability_retry_count")) is int and sample["readability_retry_count"] >= 0, "process retry count invalid")
    members = sample.get("members")
    _require(isinstance(members, list) and members, "process members are missing")
    required = ("pid", "ppid", "comm", "state", "cmdline", "stage", "rss_bytes", "pss_bytes", "swap_bytes", "timestamp_ns", "exit_code")
    pids = []
    for fact in members:
        _require(isinstance(fact, dict) and all(key in fact for key in required), "process member fields incomplete")
        _require(type(fact["pid"]) is int and fact["pid"] > 0, "process member PID invalid")
        _require(type(fact["ppid"]) is int and fact["ppid"] >= 0, "process member PPID invalid")
        _require(all(isinstance(fact[key], str) for key in ("comm", "state", "cmdline", "stage")), "process member text invalid")
        _require(fact["stage"] == "j1-contract", "process member stage mismatch")
        _require(type(fact["rss_bytes"]) is int and fact["rss_bytes"] >= 0, "process member RSS invalid")
        _require(fact["pss_bytes"] is None or (type(fact["pss_bytes"]) is int and fact["pss_bytes"] >= 0), "process member PSS invalid")
        _require(type(fact["swap_bytes"]) is int and fact["swap_bytes"] >= 0, "process member swap invalid")
        _require(type(fact["timestamp_ns"]) is int and fact["timestamp_ns"] > 0, "process member timestamp invalid")
        _require(fact["exit_code"] is None, "process member exit_code is not null")
        pids.append(fact["pid"])
    _require(len(pids) == len(set(pids)) and sample["root_pid"] in pids, "process PID membership invalid")
    pss_readable = all(fact["pss_bytes"] is not None for fact in members)
    _require(sample.get("pss_all_readable") is pss_readable, "process PSS readability mismatch")
    expected_pss = sum(fact["pss_bytes"] for fact in members) if pss_readable else None
    _require(sample.get("rss_bytes") == sum(fact["rss_bytes"] for fact in members), "process RSS aggregate mismatch")
    _require(sample.get("swap_bytes") == sum(fact["swap_bytes"] for fact in members), "process swap aggregate mismatch")
    _require(sample.get("pss_bytes") == expected_pss, "process PSS aggregate mismatch")
    compiler_count = sum(_is_compiler(fact) for fact in members if fact["pid"] != sample["root_pid"])
    _require(sample.get("compiler_descendant_count") == compiler_count == 0, "compiler descendant count is not zero")
    _require(process.get("root_pid") == sample["root_pid"], "record process root PID mismatch")
    _require(process.get("all_status_readable") is sample["all_status_readable"], "record process readability mismatch")
    _require(process.get("compiler_descendant_count") == sample["compiler_descendant_count"], "record compiler count mismatch")


def _check_cache(record: dict, paths: dict[str, Path]) -> None:
    cache = paths["cache_dir"]
    _require(list(cache.iterdir()) == [], "J1 cache is not empty")
    cache_facts = record.get("cache")
    _require(isinstance(cache_facts, dict), "cache facts are missing")
    manifest_path = _absolute(cache_facts.get("manifest_path"))
    _require(manifest_path == paths["cache_manifest"], "cache manifest path mismatch")
    _require(cache_facts.get("manifest_sha256") == _sha256(manifest_path), "cache manifest hash mismatch")
    manifest = _read_json(manifest_path)
    _require(manifest == {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}, "cache manifest is not empty")
    _require(cache_facts.get("artifact_count") == 0, "record reports cache artifacts")


def check_record(record_path: Path | str, expected_source_sha: str) -> dict:
    record_argument = Path(os.path.abspath(os.fspath(record_path)))
    record = _read_json(record_argument)
    _require(isinstance(record, dict), "record is not an object")
    _check_identity(record, expected_source_sha)
    paths = _check_paths(record, record_argument)
    _check_markers(record, paths)
    _check_process(record, paths)
    _check_cache(record, paths)
    return {
        "schema": CHECKER_SCHEMA,
        "passed": True,
        "classification": "J1_CONTRACT_PASS",
        "contract_errors": [],
        "gate_failures": [],
        "identity": {
            "source_sha": record["source_sha"],
            "branch": record["branch"],
            "input_sha256": record["identity"]["input_sha256"],
            "physical_model_sha256": record["identity"]["physical_model_sha256"],
            "mode_manifest_sha256": record["identity"]["mode_manifest_sha256"],
        },
        "evidence": {
            "raw_record_path": str(record_argument),
            "raw_record_sha256": _sha256(record_argument),
            "process_sample_sha256": record["process"]["sample_sha256"],
            "cache_manifest_sha256": record["cache"]["manifest_sha256"],
            "marker_manifest_sha256": record["markers"]["manifest_sha256"],
        },
        "metrics": {
            "marker_count": 3,
            "process_sample_count": 1,
            "cache_artifact_count": 0,
            "compiler_descendant_count": 0,
        },
    }


def _emit(result: dict, output: str | None) -> None:
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if output is None or output == "-":
        sys.stdout.write(encoded)
        return
    path = Path(os.path.abspath(output))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", required=True)
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--output", default="-")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = check_record(args.record, args.expected_source_sha)
    except (ContractError, OSError, ValueError, KeyError, IndexError, TypeError) as error:
        result = {
            "schema": CHECKER_SCHEMA,
            "passed": False,
            "classification": "CONTRACT_INVALID",
            "contract_errors": [str(error)],
            "gate_failures": [],
            "metrics": {},
        }
        _emit(result, args.output)
        return 1
    _emit(result, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
