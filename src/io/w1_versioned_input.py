"""Explicit schema2 input transaction; historical schema1 constants unchanged."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[2]
INSTANCE = "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"
ORIGIN = "independently_validated_v28"
CANDIDATE_SHA = "7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e"
CANDIDATE_BYTES = 36263033
KEY_SHA = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
PHYSICAL_SHA = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"
STAGES = {
    "input_contract_checks",
    "manifest_qualify",
    "control",
    "boundary",
    "boundary_check",
    "bundle_consume",
}
PROFILES = {"q60_native", "q60_phase_subdivision_v28"}
CONTRACT_KEYS = (
    "w1_receiver_schema",
    "input_origin",
    "instance_id",
    "manifest_path",
    "ledger_path",
    "physical_config_path",
    "math_commit",
    "quadrature_degree",
    "integration_profile",
    "output_root",
    "input_sha256",
    "coordinate_convention",
    "ledger_translation_nm",
)
FIELDS = set(CONTRACT_KEYS) - {"input_sha256"} | {
    "component",
    "stage",
    "window_path",
    "source_manifest_path",
    "checkpoint_path",
    "A_qualification_path",
    "prerequisite_paths",
}
FLAGS = dict(
    historical_bitwise_reproduction=False,
    equivalent_to_historical_numeric_manifest="UNKNOWN",
    historical_ledger_recovered=False,
)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for b in iter(lambda: stream.read(2**20), b""):
            h.update(b)
    return h.hexdigest()


def local_module(name, path):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def load(path, raw):
    d = tomllib.loads(raw.decode())
    surface = d.get("component") == "original_size_full_surface_w1"
    stages, fields = STAGES, FIELDS
    if surface:
        from src.io.w1_surface_contract import (
            EXTRA_FIELDS,
            SURFACE_STAGES,
            validate_surface_fields,
        )

        stages, fields = SURFACE_STAGES, FIELDS | EXTRA_FIELDS
        validate_surface_fields(d)
    if set(d) != fields:
        raise ValueError("W28_EXPLICIT_SCHEMA2_FIELDS")
    if (
        d["w1_receiver_schema"] != 2
        or d["instance_id"] != INSTANCE
        or d["input_origin"] != ORIGIN
        or d["component"]
        != ("original_size_full_surface_w1" if surface else "original_size_boundary_w1")
        or d["stage"] not in stages
        or d["math_commit"] != "c354afa449fb80cfb5012e7d2ff66a3e3e64e088"
        or type(d["quadrature_degree"]) is not int
        or d["quadrature_degree"] != 60
        or d["integration_profile"] not in PROFILES
        or d["coordinate_convention"] != "main_centered_nm"
        or d["ledger_translation_nm"] != [25.0, 12.5, 0.0]
        or d["checkpoint_path"] != ""
    ):
        raise ValueError("W28_FIXED_INSTANCE_PHYSICS_PROFILE")
    owned = ROOT / "benchmarks/artifacts/task42extra/w1_receiver"
    path_fields = (
        "manifest_path",
        "ledger_path",
        "physical_config_path",
        "output_root",
        "window_path",
        "source_manifest_path",
        "A_qualification_path",
    ) + (("v28_reference_root",) if surface else ())
    for k in path_fields:
        if not isinstance(d[k], str) or not d[k]:
            raise ValueError("W28_EXPLICIT_PATH")
        d[k] = str((ROOT / d[k]).resolve())
    if any(
        not Path(d[k]).is_relative_to(owned)
        for k in ("manifest_path", "ledger_path", "output_root")
    ):
        raise ValueError("W28_OWN_ARTIFACT_SCOPE")
    if surface and (
        not Path(d["v28_reference_root"]).is_relative_to(owned)
        or Path(d["v28_reference_root"]).is_symlink()
    ):
        raise ValueError("W29_INHERITED_REFERENCE_OWN_SCOPE")
    if (
        not isinstance(d["prerequisite_paths"], dict)
        or set(d["prerequisite_paths"]) - stages
    ):
        raise ValueError("W28_PREREQUISITE_STAGE")
    d["prerequisite_paths"] = {
        k: str((ROOT / v).resolve()) for k, v in d["prerequisite_paths"].items()
    }
    if any(not Path(v).is_relative_to(owned) for v in d["prerequisite_paths"].values()):
        raise ValueError("W28_PREREQUISITE_SCOPE")
    d.update(
        path=str(Path(path).resolve()), input_sha256=hashlib.sha256(raw).hexdigest()
    )
    return d


def candidate_identity(spec):
    p = Path(spec["manifest_path"])
    if not p.is_file():
        return dict(
            status="NOT_RUN_INPUT_UNAVAILABLE",
            received=False,
            candidate_available=False,
        )
    if (
        p.is_symlink()
        or p.stat().st_size != CANDIDATE_BYTES
        or digest(p) != CANDIDATE_SHA
    ):
        raise ValueError("W28_FIXED_CANDIDATE_BYTES_HASH")
    config = json.loads(Path(spec["physical_config_path"]).read_text())
    if (
        set(config)
        != {
            "schema",
            "physical_identity",
            "diffraction_rayleigh_tolerance",
            "time_convention",
            "coordinate_bridge_nm",
            "schema1_unchanged",
        }
        or config["schema"] != "w1-resolved-physical-config.v28"
        or config["diffraction_rayleigh_tolerance"] != 1e-6
        or config["time_convention"] != "exp(-i omega t)"
        or config["coordinate_bridge_nm"] != [25, 12.5, 0]
        or config["schema1_unchanged"] is not True
    ):
        raise ValueError("W28_FROZEN_CONFIG_POLICY")
    validator = local_module(
        "_w28_input_validator", ROOT / "src/common/w1_mode_validation.py"
    )
    if validator.canonical_sha(config["physical_identity"]) != PHYSICAL_SHA:
        raise ValueError("W28_FROZEN_PHYSICAL_CONFIG")
    return dict(
        status="CANDIDATE_PENDING_SCIENTIFIC_QUALIFICATION",
        received=False,
        candidate_available=True,
        manifest_path=str(p),
        manifest_bytes=CANDIDATE_BYTES,
        manifest_sha256=CANDIDATE_SHA,
        instance_id=INSTANCE,
        input_origin=ORIGIN,
        ordered_key_sha256=KEY_SHA,
        physical_identity_sha256=PHYSICAL_SHA,
        physical_config_sha256=digest(spec["physical_config_path"]),
        **FLAGS,
    )


def validate_inputs(spec, *, pending_ready=None):
    base = candidate_identity(spec)
    path = Path(spec["ledger_path"])
    marker = path.with_name("inputs_READY.json")
    if (
        not base["candidate_available"]
        or not path.is_file()
        or (not marker.is_file() and pending_ready is None)
    ):
        return base
    r = json.loads(path.read_text())
    ready = (
        pending_ready if pending_ready is not None else json.loads(marker.read_text())
    )
    if (
        r.get("schema") != "w1-independent-input-receipt.v28"
        or r.get("instance_id") != INSTANCE
        or r.get("input_origin") != ORIGIN
        or any(r.get(k) != v for k, v in FLAGS.items())
        or r.get("candidate_identity") != base
        or ready
        != dict(
            instance_id=INSTANCE,
            receipt_sha256=digest(path),
            manifest_sha256=CANDIDATE_SHA,
        )
    ):
        raise ValueError("W28_CROSS_INSTANCE_OR_RECEIPT_IDENTITY")
    parent = path.parent.resolve()
    for name in ("component", "evidence", "supervision", "receiver", "metrics"):
        row = r["qualification_files"][name]
        p = (parent / row["path"]).resolve()
        if (
            not p.is_relative_to(parent)
            or p.is_symlink()
            or not p.is_file()
            or p.stat().st_size != row["bytes"]
            or digest(p) != row["sha256"]
        ):
            raise ValueError("W28_QUALIFICATION_RAW_HASH")

    def opened(name):
        return json.loads((parent / r["qualification_files"][name]["path"]).read_text())

    sup, rec, comp = opened("supervision"), opened("receiver"), opened("component")
    evidence = opened("evidence")
    binding_path = Path(evidence["binding"]["path"])
    if not binding_path.resolve().is_relative_to(parent):
        raise ValueError("W28_QUALIFICATION_BINDING_SCOPE")
    binding = json.loads(binding_path.read_text())
    module = local_module("_w28_evidence", ROOT / "src/io/w1_evidence.py")
    module.validate_stage(
        binding_path.parent,
        identity=module.scientific_identity(binding),
        statuses={"VERSIONED_MODE_INPUT_QUALIFIED"},
        expected_stage="manifest_qualify",
    )
    if binding.get("original_inputs") != base or any(
        binding["contract"].get(k) != spec[k]
        for k in CONTRACT_KEYS
        if k not in {"input_sha256", "output_root", "integration_profile"}
    ):
        raise ValueError("W28_QUALIFICATION_SCIENTIFIC_BINDING")
    check = comp.get("mode_validation", {})
    if (
        sup.get("classification") != "COMPLETED"
        or sup.get("leader_exit_code") != 0
        or sup.get("descendants_cleared") is not True
        or sup.get("remaining_child_pids") != []
        or sup.get("sampled_process_tree_swap_peak_bytes") != 0
        or rec.get("cleared") is not True
        or rec.get("receiver_classification") != "COMPLETED"
        or rec.get("receiver_exit_code") != 0
        or check.get("status") != "MODE_SCIENCE_PASS"
        or check.get("mode_count") != 32060
        or check.get("ordered_key_sha256") != KEY_SHA
        or check.get("failed_count") != 0
        or check.get("groups")
        != {"top/s": 8015, "top/p": 8015, "bottom/s": 8015, "bottom/p": 8015}
        or any(
            v["relative"] > 1e-10 for v in check.get("maximum_by_field", {}).values()
        )
        or not check.get("maximum_by_field")
        or check.get("coverage_complete") is not True
    ):
        raise ValueError("W28_SCIENTIFIC_OR_SUPERVISION_GATE")
    return {
        **base,
        "status": "INDEPENDENT_INPUT_SCIENCE_PASS",
        "received": True,
        "ledger_path": str(path),
        "ledger_sha256": digest(path),
        "ledger_bytes": path.stat().st_size,
        "ledger_variant": "NEW_SCIENTIFIC_RECEIPT_NOT_HISTORICAL_LEDGER",
        "reopened": True,
    }


def publish_qualified_inputs(run, spec, atomic_json):
    """Called only after producer supervision, evidence, receiver and charge close."""
    run = Path(run)
    component = json.loads((run / "component_result.json").read_text())
    if component.get("mode_validation", {}).get("status") != "MODE_SCIENCE_PASS":
        return
    destination = Path(spec["ledger_path"])
    parent = destination.parent
    files = {}
    for name, filename in {
        "component": "component_result.json",
        "evidence": "evidence.json",
        "supervision": "supervisor_summary.json",
        "receiver": "receiver_result.json",
        "metrics": "mode_field_metrics.csv",
    }.items():
        path = run / filename
        files[name] = dict(
            path=str(path.relative_to(parent)),
            bytes=path.stat().st_size,
            sha256=digest(path),
        )
    value = dict(
        schema="w1-independent-input-receipt.v28",
        instance_id=INSTANCE,
        input_origin=ORIGIN,
        candidate_identity=candidate_identity(spec),
        qualification_files=files,
        **FLAGS,
    )
    atomic_json(destination, value)
    # Validate the reopened receipt against an in-memory marker candidate first.
    ready = dict(
        instance_id=INSTANCE,
        receipt_sha256=digest(destination),
        manifest_sha256=CANDIDATE_SHA,
    )
    if json.loads(destination.read_text()) != value:
        raise ValueError("W28_RECEIPT_REOPEN")
    validate_inputs(spec, pending_ready=ready)
    atomic_json(destination.with_name("inputs_READY.json"), ready)
    validate_inputs(spec)
