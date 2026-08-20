"""Read-only checker for compact T4 topology/action evidence."""

from __future__ import annotations

from collections.abc import Mapping
import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any

T4_SCHEMA = "task038.full3d.iterative.t4.action-record.v1"
T4_CHECK_SCHEMA = "task038.full3d.iterative.t4.action-check.v1"
T4_PROFILE = "full3d_scalable_v1"
T4_TRANSMISSION = "first_order_impedance_robin_v1"
T4_BRANCH = "codex/20260820-task38-extra-full3d-iterative-0p7nm"
T4_CASES = {
    "p2-mpi1": {"degree": 2, "mpi_size": 1},
    "p2-mpi2": {"degree": 2, "mpi_size": 2},
    "p3-mpi1": {"degree": 3, "mpi_size": 1},
    "p3-mpi2": {"degree": 3, "mpi_size": 2},
}
T4_ORACLE_LIMIT = 1.0e-11
T4_REPEAT_LIMIT = 1.0e-13
T4_IDEMPOTENCE_LIMIT = 1.0e-13
T4_CANONICAL_LIMIT = 1.0e-12
MANIFEST_SCHEMA = "task037.canonical-vector-manifest.v1"
SHARD_SCHEMA = "task037.canonical-vector-shard.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _obj(value: Any, name: str, problems: list[str]) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        problems.append(f"{name} is missing or not an object")
        return {}
    return value


def _pair(value: Any, name: str, problems: list[str]) -> complex | None:
    if not isinstance(value, list) or len(value) != 2 or not all(_finite(item) for item in value):
        problems.append(f"{name} is not a finite complex pair")
        return None
    return complex(float(value[0]), float(value[1]))


def _path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or Path(relative).is_absolute():
        raise ValueError("artifact relative path is invalid")
    result = (root / relative).resolve()
    result.relative_to(root.resolve())
    return result


def _read_manifest(raw_dir: Path, descriptor: Mapping[str, Any]) -> tuple[dict[str, complex], list[str], int]:
    problems: list[str] = []
    packets: dict[str, complex] = {}
    try:
        manifest_path = _path(raw_dir, descriptor.get("relative_path"))
        if not manifest_path.is_file():
            return {}, ["canonical manifest is missing"], 0
        if descriptor.get("kind") != "physical_hcurl_packet_manifest":
            problems.append("canonical manifest kind mismatch")
        if descriptor.get("bytes") != manifest_path.stat().st_size:
            problems.append("canonical manifest byte count mismatch")
        if descriptor.get("sha256") != _sha256(manifest_path):
            problems.append("canonical manifest SHA mismatch")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema_version") != MANIFEST_SCHEMA or manifest.get("dtype") != "complex128":
            problems.append("canonical manifest schema/dtype mismatch")
        shards = manifest.get("per_rank_shards")
        if not isinstance(shards, list) or not shards:
            return {}, problems + ["canonical manifest shards are missing"], 0
        total = 0
        for shard in shards:
            if not isinstance(shard, Mapping) or not isinstance(shard.get("filename"), str):
                problems.append("canonical shard descriptor is invalid")
                continue
            name = shard["filename"]
            try:
                shard_path = (manifest_path.parent / name).resolve()
                shard_path.relative_to(raw_dir.resolve())
            except (OSError, ValueError):
                problems.append(f"canonical shard path is invalid: {name}")
                continue
            if not shard_path.is_file():
                problems.append(f"canonical shard is missing: {name}")
                continue
            if shard.get("file_sha256") != _sha256(shard_path):
                problems.append(f"canonical shard SHA mismatch: {name}")
            local_keys: set[str] = set()
            count = 0
            try:
                lines = shard_path.read_text(encoding="utf-8").splitlines()
                for line_number, line in enumerate(lines, 1):
                    item = json.loads(line)
                    if item.get("schema_version") != SHARD_SCHEMA:
                        problems.append(f"canonical shard schema mismatch: {name}")
                    key_json = json.dumps(item.get("key"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                    key = key_json.decode()
                    if item.get("key_sha256") != hashlib.sha256(key_json).hexdigest():
                        problems.append(f"canonical key SHA mismatch: {name}:{line_number}")
                    value = item.get("value")
                    if not isinstance(value, list) or len(value) != 2 or not all(_finite(x) for x in value):
                        problems.append(f"canonical value is invalid: {name}:{line_number}")
                        continue
                    if key in local_keys or key in packets:
                        problems.append(f"duplicate canonical key: {name}:{line_number}")
                    local_keys.add(key)
                    packets[key] = complex(float(value[0]), float(value[1]))
                    count += 1
            except (OSError, UnicodeDecodeError, TypeError, ValueError, json.JSONDecodeError) as exc:
                problems.append(f"canonical shard is unreadable: {name}: {exc}")
            if shard.get("packet_count") != count or shard.get("local_duplicate_count") != 0:
                problems.append(f"canonical shard facts do not close: {name}")
            total += count
        if manifest.get("global_summed_packet_count") != total or descriptor.get("packet_count") != total:
            problems.append("canonical packet counts do not close")
        return packets, problems, total
    except (OSError, UnicodeDecodeError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return {}, problems + [f"canonical manifest is invalid: {exc}"], 0


def _check_source(record: Mapping[str, Any], problems: list[str]) -> bool:
    source = _obj(record.get("source"), "source", problems)
    for key, expected in {
        "branch": T4_BRANCH,
        "clean_start": True,
        "clean_end": True,
        "tracked_status_start": "",
        "tracked_status_end": "",
    }.items():
        if source.get(key) != expected:
            problems.append(f"source identity mismatch: {key}")
    start = source.get("commit_sha_start")
    end = source.get("commit_sha_end")
    expected_sha = source.get("expected_sha")
    valid = all(
        isinstance(value, str)
        and len(value) == 40
        and all(c in "0123456789abcdef" for c in value)
        for value in (start, end, expected_sha)
    )
    if not valid or start != end or expected_sha != start:
        problems.append("source expected SHA is missing, malformed, or not bound to start=end")
        return False
    return True


def _check_topology(record: Mapping[str, Any], problems: list[str]) -> dict[str, Any]:
    topology = _obj(record.get("topology"), "topology", problems)
    mpi_size = record.get("mpi_size")
    for key, expected in {"profile": T4_PROFILE, "slab_count": 2, "transmission": T4_TRANSMISSION}.items():
        if topology.get(key) != expected:
            problems.append(f"topology identity mismatch: {key}")
    for key in ("global_facet_count", "local_facet_count", "owned_trace_rows"):
        if not isinstance(topology.get(key), int) or topology[key] <= 0:
            problems.append(f"topology count is invalid: {key}")
    if not isinstance(topology.get("ghost_trace_rows"), int) or topology["ghost_trace_rows"] < 0:
        problems.append("topology ghost trace count is invalid")
    digest = topology.get("canonical_sha256")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        problems.append("topology canonical digest is invalid")
    if topology.get("owner_closure") is not True:
        problems.append("topology owner closure is not proven")
    if set(topology.get("interface_classifications", ())) != {"homogeneous", "nonhomogeneous"}:
        problems.append("topology material classifications are incomplete")
    if topology.get("floquet_phase_nontrivial") is not True:
        problems.append("Floquet phase nontriviality is missing")
    phases = _obj(topology.get("floquet_phases"), "topology.floquet_phases", problems)
    for name in ("x", "y", "corner"):
        _pair(phases.get(name), f"topology.floquet_phases.{name}", problems)
    error = topology.get("restriction_prolongation_adjoint_relative_error")
    if not _finite(error) or float(error) > 1.0e-11:
        problems.append("restriction/prolongation adjoint gate failed")
    plan = _obj(topology.get("neighbor_plan"), "topology.neighbor_plan", problems)
    for name in ("forward_send_peers", "forward_recv_peers", "backward_send_peers", "backward_recv_peers", "lower_participant_ranks", "upper_participant_ranks"):
        peers = plan.get(name)
        if not isinstance(peers, list) or any(not isinstance(peer, int) or peer < 0 or peer >= mpi_size for peer in peers):
            problems.append(f"neighbor plan is invalid: {name}")
    audit = _obj(topology.get("audit"), "topology.audit", problems)
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
            problems.append(f"topology audit mismatch: {key}")
    return {"canonical_sha256": topology.get("canonical_sha256"), "global_facet_count": topology.get("global_facet_count")}


def _check_reconstruction(record: Mapping[str, Any], problems: list[str]) -> None:
    facts = _obj(record.get("reconstruction"), "reconstruction", problems)
    for key, limit in {
        "first_reconstruction_relation_error": T4_ORACLE_LIMIT,
        "second_reconstruction_relation_error": T4_ORACLE_LIMIT,
        "second_full_owned_ghost_idempotence_error": T4_IDEMPOTENCE_LIMIT,
        "second_slave_idempotence_error": T4_IDEMPOTENCE_LIMIT,
    }.items():
        if not _finite(facts.get(key)) or float(facts[key]) > limit:
            problems.append(f"reconstruction gate failed: {key}")


def _check_actions(record: Mapping[str, Any], raw_dir: Path, problems: list[str]) -> dict[str, float]:
    actions, artifacts = _obj(record.get("actions"), "actions", problems), _obj(record.get("artifacts"), "artifacts", problems)
    telemetry = record.get("telemetry")
    if not isinstance(telemetry, list) or len(telemetry) != 8:
        problems.append("T4 telemetry does not contain one sample after each apply")
        telemetry = []
    seen = set()
    for sample in telemetry:
        if not isinstance(sample, Mapping):
            problems.append("T4 telemetry sample is invalid")
            continue
        seen.add((sample.get("source"), sample.get("direction"), sample.get("repeat")))
        if (
            sample.get("rss_semantics") != "mpi_rank_max_current_self_rss"
            or sample.get("swap_semantics") != "current_process_VmSwap"
            or sample.get("rank_max_swap_used_bytes") != 0
        ):
            problems.append("T4 RSS/swap telemetry semantics failed")
        if not _finite(sample.get("elapsed_seconds")) or float(sample["elapsed_seconds"]) < 0 or not isinstance(sample.get("rank_max_current_rss_bytes"), int) or sample["rank_max_current_rss_bytes"] <= 0:
            problems.append("T4 elapsed/RSS telemetry is invalid")
    expected_samples = {(s, d, r) for s in ("source_1", "source_2") for d in ("forward", "backward") for r in (0, 1)}
    if seen != expected_samples:
        problems.append("T4 telemetry apply identity is incomplete")
    derived = {}
    for source in ("source_1", "source_2"):
        source_actions = _obj(actions.get(source), f"actions.{source}", problems)
        for direction in ("forward", "backward"):
            fact = _obj(source_actions.get(direction), f"actions.{source}.{direction}", problems)
            expected, observed = _pair(fact.get("oracle_pairing"), "oracle pairing", problems), _pair(fact.get("candidate_pairing"), "candidate pairing", problems)
            if expected is None or observed is None:
                continue
            if abs(expected) <= 1.0e-14:
                problems.append(f"action oracle pairing is degenerate: {source}/{direction}")
            relative = abs(observed - expected) / max(abs(expected), math.ulp(1.0))
            if relative > T4_ORACLE_LIMIT or fact.get("finite") is not True:
                problems.append(f"action oracle gate failed: {source}/{direction}")
            repeat = fact.get("repeat_relative_difference")
            if not _finite(repeat) or float(repeat) > T4_REPEAT_LIMIT:
                problems.append(f"action repeat gate failed: {source}/{direction}")
            descriptor = fact.get("canonical")
            if not isinstance(descriptor, Mapping) or artifacts.get(f"{source}_{direction}") != descriptor:
                problems.append(f"action canonical descriptor mismatch: {source}/{direction}")
            else:
                _packets, manifest_problems, count = _read_manifest(raw_dir, descriptor)
                problems.extend(f"{source}/{direction}: {problem}" for problem in manifest_problems)
                if count == 0:
                    problems.append(f"action canonical packet set is empty: {source}/{direction}")
            derived[f"{source}_{direction}_relative_error"] = relative
    for source in ("source_1", "source_2"):
        descriptor = artifacts.get(source)
        if not isinstance(descriptor, Mapping):
            problems.append(f"source canonical descriptor is missing: {source}")
            continue
        _packets, manifest_problems, count = _read_manifest(raw_dir, descriptor)
        problems.extend(f"{source}: {problem}" for problem in manifest_problems)
        if count == 0:
            problems.append(f"source canonical packet set is empty: {source}")
    return derived


def _check_scope(record: Mapping[str, Any], problems: list[str]) -> None:
    audit = _obj(record.get("candidate_audit"), "candidate_audit", problems)
    for key, expected in {
        "candidate": "A", "action": "interior_facet_tangential_robin_weak_form",
        "phase_application": "finalized_floquet_mpc_once", "numeric_allgather": False,
        "global_aij_materialized": False, "dense_interface_mass_materialized": False,
        "dense_interface_schur_materialized": False, "slab_factor_materialized": False,
    }.items():
        if audit.get(key) != expected:
            problems.append(f"candidate audit mismatch: {key}")
    directions = _obj(audit.get("directions"), "candidate_audit.directions", problems)
    for direction in ("forward", "backward"):
        facts = _obj(directions.get(direction), f"candidate_audit.{direction}", problems)
        if facts.get("apply_count") != 4:
            problems.append(f"candidate apply count is not four: {direction}")
        for key in ("retained_numeric_payload_local_bytes", "retained_numeric_payload_global_max_bytes", "per_apply_bounded_temporary_bytes"):
            if not isinstance(facts.get(key), int) or facts[key] < 0:
                problems.append(f"candidate retained/work field is invalid: {direction}/{key}")
    resource = _obj(record.get("resource"), "resource", problems)
    if (
        resource.get("rss_semantics") != "mpi_rank_max_current_self_rss"
        or resource.get("process_tree_evidence") != "not_measured_t4"
        or resource.get("swap_semantics") != "mpi_rank_max_current_process_VmSwap"
        or resource.get("swap_used_bytes") != 0
    ):
        problems.append("T4 resource evidence is invalid")
    execution = _obj(record.get("execution"), "execution", problems)
    if execution.get("ksp_created") is not False or execution.get("pde_run") is not False or execution.get("official_physics") != "not_run":
        problems.append("T4 execution scope is not action-only")


def check_t4_record(record_path: Path) -> dict[str, Any]:
    problems: list[str] = []
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"schema": T4_CHECK_SCHEMA, "passed": False, "classification": "T4_EXECUTION_OR_EVIDENCE_FAIL", "checks": {"record_readable": False}, "problems": [f"record is unreadable: {exc}"]}
    if not isinstance(record, Mapping):
        problems.append("record root is not an object")
        record = {}
    case, spec = record.get("case"), T4_CASES.get(record.get("case"))
    if spec is None:
        problems.append("record case is not one of the four frozen T4 cases")
        spec = {"degree": None, "mpi_size": None}
    if record.get("schema") != T4_SCHEMA or record.get("degree") != spec["degree"] or record.get("mpi_size") != spec["mpi_size"] or record.get("profile") != T4_PROFILE:
        problems.append("record schema/case/profile identity mismatch")
    model = _obj(record.get("model"), "model", problems)
    model_identity = (
        all(
            _finite(model.get(key))
            for key in (
                "wavelength_nm",
                "mesh_target_nm",
                "incident_theta_deg",
                "incident_phi_deg",
            )
        )
        and model.get("degree") == spec["degree"]
        and model.get("analytic_source") == "incident_air_plane_wave_field"
        and model.get("source_family") == "fixed_oblique_s_p"
        and model.get("source_polarizations")
        == {"source_1": "s", "source_2": "p"}
        and model.get("test_polarization")
        == "fixed_s_plus_p_linear_combination"
        and model.get("test_linear_combination")
        == {"s": [0.6, 0.1], "p": [0.35, -0.2]}
        and model.get("incident_theta_deg") == 21.131
        and model.get("incident_phi_deg") == 33.690
    )
    if not model_identity:
        problems.append("model physical identity is invalid")
    source_ok = _check_source(record, problems)
    topology = _check_topology(record, problems)
    _check_reconstruction(record, problems)
    derived = _check_actions(record, Path(record.get("raw_dir", "")), problems)
    _check_scope(record, problems)
    checks = {
        "schema_case_identity": record.get("schema") == T4_SCHEMA and spec["degree"] is not None,
        "source_identity": source_ok,
        "topology_identity": not any(p.startswith(("topology", "neighbor", "Floquet", "restriction", "model")) for p in problems),
        "reconstruction": not any(p.startswith("reconstruction") for p in problems),
        "action_oracle": not any(p.startswith("action") for p in problems),
        "canonical_packets": not any("canonical" in p for p in problems),
        "resource_and_scope": not any(p.startswith(("T4", "candidate", "resource")) for p in problems),
    }
    passed = not problems and all(checks.values())
    return {"schema": T4_CHECK_SCHEMA, "case": case, "passed": bool(passed), "classification": "T4_PASS" if passed else "T4_EXECUTION_OR_EVIDENCE_FAIL", "checks": checks, "derived": {**topology, **derived}, "problems": problems}


def _relative(left: Mapping[str, complex], right: Mapping[str, complex]) -> tuple[float, bool]:
    if set(left) != set(right):
        return math.inf, False
    numerator = sum(abs(left[key] - right[key]) ** 2 for key in left)
    denominator = sum(abs(value) ** 2 for value in right.values())
    return math.sqrt(numerator) / max(math.sqrt(denominator), math.ulp(1.0)), True


def check_t4_aggregate(*, p2_mpi1_record_path: Path, p2_mpi2_record_path: Path, p3_mpi1_record_path: Path, p3_mpi2_record_path: Path) -> dict[str, Any]:
    paths = (p2_mpi1_record_path, p2_mpi2_record_path, p3_mpi1_record_path, p3_mpi2_record_path)
    individual = tuple(check_t4_record(path) for path in paths)
    records: dict[str, Mapping[str, Any]] = {}
    problems: list[str] = []
    for path, result in zip(paths, individual, strict=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            problems.append(f"aggregate record is unreadable: {path}: {exc}")
            continue
        if not isinstance(payload, Mapping):
            problems.append(f"aggregate record root is invalid: {path}")
            continue
        case = payload.get("case")
        if case in records:
            problems.append(f"aggregate contains duplicate case: {case}")
        records[case] = payload
        if not result.get("passed"):
            problems.append(f"individual T4 record failed: {case}")
    exact = set(records) == set(T4_CASES) and len(records) == 4
    if not exact:
        problems.append("aggregate does not contain exactly the four frozen T4 cases")
    shas = {_obj(record.get("source"), "source", problems).get("commit_sha_start") for record in records.values()}
    source_identity = len(shas) == 1 and None not in shas
    if not source_identity:
        problems.append("aggregate source SHA identity is not exact")
    comparisons: dict[str, Any] = {}
    topology_identity = True
    for degree in (2, 3):
        left, right = records.get(f"p{degree}-mpi1"), records.get(f"p{degree}-mpi2")
        if left is None or right is None:
            topology_identity = False
            continue
        left_topology, right_topology = _obj(left.get("topology"), "topology", problems), _obj(right.get("topology"), "topology", problems)
        if (left_topology.get("canonical_sha256"), left_topology.get("global_facet_count")) != (right_topology.get("canonical_sha256"), right_topology.get("global_facet_count")):
            topology_identity = False
            problems.append(f"p{degree} topology canonical identity differs across MPI")
        left_artifacts, right_artifacts = _obj(left.get("artifacts"), "artifacts", problems), _obj(right.get("artifacts"), "artifacts", problems)
        for role in ("source_1", "source_2", "source_1_forward", "source_1_backward", "source_2_forward", "source_2_backward"):
            ld, rd = left_artifacts.get(role), right_artifacts.get(role)
            if not isinstance(ld, Mapping) or not isinstance(rd, Mapping):
                problems.append(f"p{degree} canonical descriptor is missing: {role}")
                continue
            lp, le, _ = _read_manifest(Path(left.get("raw_dir", "")), ld)
            rp, re, _ = _read_manifest(Path(right.get("raw_dir", "")), rd)
            problems.extend(f"p{degree} MPI1 {role}: {error}" for error in le)
            problems.extend(f"p{degree} MPI2 {role}: {error}" for error in re)
            relative, keys_match = _relative(lp, rp)
            comparisons[f"p{degree}_{role}"] = {"relative_l2": relative, "limit": T4_CANONICAL_LIMIT, "key_identity": keys_match}
            if not keys_match or relative > T4_CANONICAL_LIMIT:
                problems.append(f"p{degree} canonical MPI identity failed: {role}")
    checks = {
        "exact_four_record_set": exact,
        "all_individual_records_pass": all(result.get("passed") is True for result in individual),
        "source_sha_identity": source_identity,
        "topology_identity": topology_identity,
        "canonical_source_action_identity": not any("canonical MPI identity failed" in p for p in problems),
    }
    passed = not problems and all(checks.values())
    return {"schema": T4_CHECK_SCHEMA, "passed": bool(passed), "classification": "T4_AGGREGATE_PASS" if passed else "T4_EXECUTION_OR_EVIDENCE_FAIL", "checks": checks, "canonical_comparisons": comparisons, "problems": problems}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--record", type=Path, required=True)
    aggregate = subparsers.add_parser("aggregate")
    for name in ("p2_mpi1", "p2_mpi2", "p3_mpi1", "p3_mpi2"):
        aggregate.add_argument(f"--{name.replace('_', '-')}-record", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = check_t4_record(args.record) if args.command == "check" else check_t4_aggregate(
        p2_mpi1_record_path=args.p2_mpi1_record,
        p2_mpi2_record_path=args.p2_mpi2_record,
        p3_mpi1_record_path=args.p3_mpi1_record,
        p3_mpi2_record_path=args.p3_mpi2_record,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
