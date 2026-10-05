"""A relative-path, independently reopened local W1 numerical package.

Copying and array checking qualify this local handoff only, not a cross-machine
or power-loss storage backend. Production ingestion is explicitly opt-in.
"""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

INSTANCE = "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"
CANDIDATE_SHA = "7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e"
KEY_SHA = "03c1965cc13d89b256ea61212a5baba9aa97ef7ec20d356b0a04f9d233e95dec"
PHYSICAL_SHA = "a855565b82c1d88e84352dd355aec3531464261e5ab0df3e45de17e1879eaf1f"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(2**20), b""):
            h.update(block)
    return h.hexdigest()


def relative_file(root, name, row):
    path = (root / name).resolve()
    if (
        Path(name).is_absolute()
        or not path.is_relative_to(root.resolve())
        or path.is_symlink()
        or not path.is_file()
        or path.stat().st_size != row["bytes"]
        or sha(path) != row["sha256"]
    ):
        raise ValueError("W28_BUNDLE_FILE_SCOPE_BYTES_HASH")
    return path


def consume(package, output, *, qualification_only=False):
    """Independent process API: NumPy/stdlib only, zero producer/integrator calls."""
    package = Path(package).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((package / "package_manifest.json").read_text())
    if (
        manifest.get("schema") != "w1-relative-boundary-package.v28"
        or manifest.get("instance_id") != INSTANCE
        or manifest.get("handoff_status") != "SEALED_AWAITING_LOCAL_RELOCATED_CONSUMER"
        or manifest.get("main_ingestion_occurred") is not False
    ):
        raise ValueError("W28_BUNDLE_INSTANCE_PURPOSE")
    if not qualification_only:
        marker = package / "READY_FOR_MAIN_OPT_IN_NOT_INGESTED.json"
        if not marker.is_file():
            raise ValueError("W28_BUNDLE_READY_AFTER_CLEARED_CONSUMER_REQUIRED")
        ready = json.loads(marker.read_text())
        if (
            ready.get("instance_id") != INSTANCE
            or ready.get("status") != "READY_FOR_MAIN_OPT_IN_NOT_INGESTED"
            or ready.get("package_manifest_sha256")
            != sha(package / "package_manifest.json")
            or ready.get("consumer_cleared") is not True
        ):
            raise ValueError("W28_BUNDLE_READY_IDENTITY_OR_SUPERVISION")
    listed = manifest["files"]
    actual = {
        str(p.relative_to(package))
        for p in package.rglob("*")
        if p.is_file()
        and p.name
        not in {"package_manifest.json", "READY_FOR_MAIN_OPT_IN_NOT_INGESTED.json"}
    }
    if actual != set(listed):
        raise ValueError("W28_BUNDLE_COVERAGE")
    for name, row in listed.items():
        relative_file(package, name, row)
    if (
        sha(package / "input/mode_manifest.json") != CANDIDATE_SHA
        or manifest.get("manifest_sha256") != CANDIDATE_SHA
        or manifest.get("physical_identity_sha256") != PHYSICAL_SHA
        or manifest.get("ordered_key_sha256") != KEY_SHA
        or manifest.get("historical_bitwise_reproduction") is not False
        or manifest.get("equivalent_to_historical_numeric_manifest") != "UNKNOWN"
        or manifest.get("historical_ledger_recovered") is not False
    ):
        raise ValueError("W28_BUNDLE_FIXED_INPUT_IDENTITY")
    sys.path.insert(0, str(package / "code"))
    import w1_mode_validation as validator
    import w1_saved_boundary as checker
    import finite_json

    document = json.loads((package / "input/mode_manifest.json").read_text())
    config = json.loads((package / "input/resolved_config.json").read_text())
    if (
        validator.canonical_sha(config["physical_identity"])
        != manifest["physical_identity_sha256"]
    ):
        raise ValueError("W28_BUNDLE_PHYSICS")
    science = validator.validate_document(document, config["physical_identity"])
    if (
        science["status"] != "MODE_SCIENCE_PASS"
        or science["ordered_key_sha256"] != manifest["ordered_key_sha256"]
    ):
        raise ValueError("W28_BUNDLE_INDEPENDENT_INPUT_GATE")
    result = checker.check_saved(
        package / "raw", document["modes"], config, output / "boundary_metrics.csv"
    )
    if (
        result["status"] != "W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS"
        or result["coverage"] != {"4": 32060, "6": 32060}
        or result["failed_metric_count"] != 0
    ):
        raise ValueError("W28_BUNDLE_SAVED_NUMERIC_GATE")
    result.update(
        status="LOCAL_RELOCATED_CONSUMER_PASS",
        instance_id=INSTANCE,
        package_manifest_sha256=sha(package / "package_manifest.json"),
        files_reopened=len(listed),
        manifest_sha256=sha(package / "input/mode_manifest.json"),
        read_only_source_package=True,
        FE_factor_solve_Gram_NN_calls=0,
        cross_machine_or_power_failure_qualified=False,
    )
    finite_json.atomic_json(output / "consumer_receipt.json", result)
    return result


def build_and_consume(root, binding, run, helpers):
    """Called only after saved scientific qualification; no producer re-execution."""
    spec = binding["spec"]
    producer = Path(spec["prerequisite_paths"]["boundary"])
    check = Path(spec["prerequisite_paths"]["boundary_check"])
    saved = json.loads((check / "component_result.json").read_text())
    if saved["status"] != "W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS":
        raise ValueError("W28_BUNDLE_PRIOR_NUMERIC_GATE")
    package = run / "bundle"
    package.mkdir()
    raw = package / "raw"
    raw.mkdir()
    index = json.loads((producer / "chunk_index.json").read_text())
    if (
        index.get("complete") is not True
        or index["profile"] != spec["integration_profile"]
    ):
        raise ValueError("W28_BUNDLE_PARTIAL_PROFILE")
    names = {
        "chunk_index.json",
        "oracle_qualification.json",
        "integration_profile.json",
        "moment_decimal110.json",
    }
    names.add(index["oracle"]["path"])
    for group in ("layouts", "actions", "incident"):
        names.update(v["path"] for v in index[group].values())
    names.update(v["path"] for v in index["chunks"])
    for name in sorted(names):
        helpers.guard(binding)
        dest = raw / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(producer / name, dest)
    code = package / "code"
    code.mkdir()
    for name, source in [
        ("w1_saved_boundary.py", "src/solvers/w1_saved_boundary.py"),
        ("w1_mode_validation.py", "src/common/w1_mode_validation.py"),
        ("finite_json.py", "src/io/finite_json.py"),
    ]:
        shutil.copyfile(root / source, code / name)
    shutil.copyfile(root / "src/io/w1_boundary_bundle.py", package / "consumer.py")
    inp = package / "input"
    inp.mkdir()
    shutil.copyfile(spec["manifest_path"], inp / "mode_manifest.json")
    shutil.copyfile(spec["physical_config_path"], inp / "resolved_config.json")
    shutil.copyfile(
        root / "input/task042extra_feinn_5nm/w1_reference_definition_v28.json",
        inp / "reference_definition.json",
    )
    shutil.copyfile(spec["ledger_path"], inp / "scientific_input_receipt.json")
    prov = package / "provenance"
    prov.mkdir()
    qualified = json.loads(Path(spec["ledger_path"]).read_text())
    for name, row in qualified["qualification_files"].items():
        source = Path(spec["ledger_path"]).parent / row["path"]
        # Full field CSV belongs to raw scientific input qualification, not tiny Git evidence.
        shutil.copyfile(source, prov / ("input_" + name + source.suffix))
    for role, path in [
        ("native_control", Path(spec["prerequisite_paths"]["control"])),
        ("producer", producer),
        ("saved_checker", check),
    ]:
        folder = prov / role
        folder.mkdir()
        for name in (
            "binding.json",
            "component_result.json",
            "evidence.json",
            "supervisor_summary.json",
            "receiver_result.json",
        ):
            shutil.copyfile(path / name, folder / name)
    files = {
        str(p.relative_to(package)): dict(bytes=p.stat().st_size, sha256=sha(p))
        for p in package.rglob("*")
        if p.is_file()
    }
    identity = qualified["candidate_identity"]
    manifest = dict(
        schema="w1-relative-boundary-package.v28",
        instance_id=INSTANCE,
        input_origin="independently_validated_v28",
        integration_profile=spec["integration_profile"],
        files=files,
        handoff_status="SEALED_AWAITING_LOCAL_RELOCATED_CONSUMER",
        main_ingestion_occurred=False,
        manifest_sha256=identity["manifest_sha256"],
        physical_identity_sha256=identity["physical_identity_sha256"],
        ordered_key_sha256=identity["ordered_key_sha256"],
        receiver_source_sha=binding["receiver_source_sha"],
        mathematical_source_sha=binding["math_source_sha"],
        historical_bitwise_reproduction=False,
        equivalent_to_historical_numeric_manifest="UNKNOWN",
        historical_ledger_recovered=False,
        full_target_qualified=False,
        NN_used=False,
        source_package_numeric_status=saved["status"],
        command="python consumer.py --package . --output ../consumer_check",
    )
    helpers.atomic_json(package / "package_manifest.json", manifest)
    # Actual clean directory copy, not an index pointing to the original absolute paths.
    relocated = run / "relocated_package"
    if relocated.exists():
        raise ValueError("W28_RELOCATED_DIRECTORY_MUST_BE_NEW")
    shutil.copytree(package, relocated)
    helpers.guard(binding)
    output = run / "relocated_check"
    code = subprocess.run(
        [
            sys.executable,
            "-I",
            "-B",
            str(relocated / "consumer.py"),
            "--package",
            str(relocated),
            "--output",
            str(output),
            "--qualification-only",
        ],
        cwd=relocated,
        check=False,
    )
    if code.returncode != 0:
        raise ValueError("W28_RELOCATED_CONSUMER_EXIT")
    receipt = json.loads((output / "consumer_receipt.json").read_text())
    if (
        receipt["package_manifest_sha256"] != sha(package / "package_manifest.json")
        or receipt["manifest_sha256"] != identity["manifest_sha256"]
    ):
        raise ValueError("W28_RELOCATED_SAME_BYTES_REQUIRED")
    receipt.update(
        raw=helpers.file_receipt(output / "consumer_receipt.json"),
        raw_metrics=helpers.file_receipt(output / "boundary_metrics.csv"),
        package_manifest=helpers.file_receipt(package / "package_manifest.json"),
        relocated_manifest=helpers.file_receipt(relocated / "package_manifest.json"),
        bundle_directory=str(package),
        relocated_directory=str(relocated),
        copied_bytes=sum(v["bytes"] for v in files.values()),
        not_ingested_by_main=True,
    )
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--qualification-only", action="store_true")
    args = parser.parse_args()
    result = consume(
        args.package, args.output, qualification_only=args.qualification_only
    )
    print(
        json.dumps(
            {
                k: result[k]
                for k in ("status", "files_reopened", "package_manifest_sha256")
            }
        )
    )
