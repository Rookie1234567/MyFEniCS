from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from benchmarks.task035e_reference_leak_checker import (
    BLIND_INPUT_MANIFEST_SCHEMA,
    CHECKER_ARTIFACT_SCHEMA,
    FORMAL_BLIND_ENTRYPOINTS,
    EXIT_DYNAMIC_ACCESS,
    EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR,
    EXIT_PASS,
    EXIT_STATIC_LEAK,
    build_reference_leak_report,
    build_reference_leak_report_artifact,
    main,
    run_audit_canary,
    scan_blind_controller,
    validate_blind_input_manifest,
)


def _sha(character: str) -> str:
    return character * 64


def _manifest() -> dict[str, object]:
    return {
        "schema": BLIND_INPUT_MANIFEST_SCHEMA,
        "trial": {
            "trial_id": "blind-a",
            "algorithm_id": "multilevel-hp-v1",
            "source_sha": "1" * 40,
            "initial_path_id": "path-a-20-10-5",
            "maximum_cycles": 6,
        },
        "cycle": {
            "cycle_index": 0,
            "state": "initialized",
            "mesh_forest_sha256": _sha("2"),
            "degree_map_sha256": _sha("3"),
            "solution_snapshot_sha256": _sha("4"),
            "goal_inventory_sha256": _sha("5"),
            "full_residual_sha256": _sha("6"),
            "adjoint_bundle_sha256": _sha("7"),
            "p_shadow_bundle_sha256": None,
            "h_shadow_bundle_sha256": None,
            "resource_inventory_sha256": _sha("8"),
        },
    }


def _safe_package(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "source"
    package = root / "blind_controller"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(
        "from .entry import current_cycle\n",
        encoding="utf-8",
    )
    (package / "entry.py").write_text(
        "from .helper import identity\n\n"
        "def current_cycle(value):\n"
        "    return identity(value)\n",
        encoding="utf-8",
    )
    (package / "helper.py").write_text(
        "def identity(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    return root, package


def test_static_and_manifest_positive_path_passes(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    audit_entry = package / "audit_entry.py"
    audit_entry.write_text("VALUE = 1\n", encoding="utf-8")
    protected = tmp_path / "protected"
    protected.mkdir()
    static = scan_blind_controller(package, source_root=root)
    manifest = validate_blind_input_manifest(_manifest())
    report = build_reference_leak_report(
        controller_package=package,
        source_root=root,
        manifest=_manifest(),
        audit_entrypoint=audit_entry,
        audit_protected_paths=(protected,),
    )

    assert static["pass"] is True
    assert static["controller_file_count"] == 4
    assert manifest == {
        "pass": True,
        "schema": BLIND_INPUT_MANIFEST_SCHEMA,
        "additional_properties": False,
        "issues": [],
    }
    assert report["pass"] is True
    assert report["exit_code"] == EXIT_PASS
    assert report["checks"]["dynamic"]["status"] == "audit_pass"


def test_formal_report_rejects_missing_dynamic_audit(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    report = build_reference_leak_report(
        controller_package=package,
        source_root=root,
        manifest=_manifest(),
    )
    assert report["pass"] is False
    assert report["exit_code"] == EXIT_DYNAMIC_ACCESS
    assert report["checks"]["dynamic"]["status"] == (
        "formal_dynamic_audit_required"
    )


def test_transitive_forbidden_import_is_fingerprinted_not_echoed(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    protected_module = "src.adaptivity.hidden_auditor.package_reader"
    (package / "helper.py").write_text(
        f"from {protected_module} import read_package\n\n"
        "def identity(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(package, source_root=root)
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert any(item["rule_id"] == "S001" for item in report["findings"])
    assert protected_module not in rendered
    assert hashlib.sha256(protected_module.encode()).hexdigest() in rendered


def test_explicit_entrypoints_and_their_transitive_imports_are_scanned(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    benchmarks = root / "benchmarks"
    benchmarks.mkdir()
    entrypoint = benchmarks / "task035e_blind_cycle.py"
    helper = benchmarks / "entry_helper.py"
    entrypoint.write_text(
        "from benchmarks.entry_helper import identity\n",
        encoding="utf-8",
    )
    protected_module = "src.adaptivity.hidden_auditor.api"
    helper.write_text(
        f"from {protected_module} import audit\n\n"
        "def identity(value):\n"
        "    return value\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(
        package,
        source_root=root,
        source_entrypoints=(entrypoint,),
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert report["source_entrypoint_file_count"] == 1
    assert report["transitive_file_count"] == 1
    assert any(item["rule_id"] == "S001" for item in report["findings"])
    assert protected_module not in rendered


def test_repository_formal_blind_entrypoints_are_in_static_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    package = root / "src/adaptivity/blind_controller"
    entries = tuple(root / relative for relative in FORMAL_BLIND_ENTRYPOINTS)
    expected = (
        "benchmarks/task035e_campaign_bootstrap.py",
        "benchmarks/task035e_initial_space.py",
        "benchmarks/task035e_trial_metadata.py",
        "benchmarks/task035e_transition_producer.py",
        "benchmarks/task035e_candidate_output.py",
        "benchmarks/task035e_live_shadow_bridge.py",
        "benchmarks/task035e_cellwise_authority.py",
        "benchmarks/task035e_goal_marking.py",
        "benchmarks/task035e_shadow_bundle.py",
        "benchmarks/task035e_blind_bindings.py",
        "benchmarks/task035e_internal_gate_authority.py",
        "benchmarks/task035e_blind_campaign.py",
        "benchmarks/task035e_campaign_stages.py",
        "benchmarks/task035e_campaign_handlers.py",
        "benchmarks/task035e_p7_saturation_bridge.py",
        "benchmarks/task035e_blind_cycle.py",
    )

    report = scan_blind_controller(
        package,
        source_root=root,
        source_entrypoints=entries,
    )

    assert FORMAL_BLIND_ENTRYPOINTS == expected
    assert report["pass"] is True
    assert report["source_entrypoint_file_count"] == len(
        FORMAL_BLIND_ENTRYPOINTS
    )
    assert [row["source"] for row in report["source_entrypoints"]] == list(
        FORMAL_BLIND_ENTRYPOINTS
    )
    assert report["scanned_file_count"] >= (
        report["controller_file_count"] + len(FORMAL_BLIND_ENTRYPOINTS)
    )


def test_denial_flag_ast_proof_is_narrow_and_true_value_still_leaks(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    entry = package / "entry.py"
    entry.write_text(
        "_OUTPUT_FIELDS = frozenset({'hidden_reference_consumed'})\n\n"
        "def validate(raw):\n"
        "    if raw.get('hidden_reference_consumed') is not False:\n"
        "        raise ValueError('forbidden flag')\n"
        "    return {'hidden_reference_consumed': False}\n",
        encoding="utf-8",
    )

    safe = scan_blind_controller(package, source_root=root)

    assert safe["pass"] is True
    assert safe["findings"] == []

    entry.write_text(
        "_OUTPUT_FIELDS = frozenset({'hidden_reference_consumed'})\n\n"
        "def validate(raw):\n"
        "    if raw.get('hidden_reference_consumed') is not False:\n"
        "        raise ValueError('forbidden flag')\n"
        "    return {'hidden_reference_consumed': True}\n",
        encoding="utf-8",
    )
    leaked = scan_blind_controller(package, source_root=root)

    assert leaked["pass"] is False
    assert any(item["rule_id"] == "S005" for item in leaked["findings"])


def test_denial_get_without_raise_is_not_whitelisted(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    (package / "entry.py").write_text(
        "def validate(raw):\n"
        "    if raw.get('hidden_reference_consumed') is not False:\n"
        "        return None\n"
        "    return raw\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(package, source_root=root)

    assert report["pass"] is False
    assert any(item["rule_id"] == "S005" for item in report["findings"])


def test_explicit_forbidden_presence_guard_is_ast_proven(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    (package / "entry.py").write_text(
        "def validate(raw):\n"
        "    if raw.get('task035e_reference_certifier') is not None:\n"
        "        raise ValueError('evaluator input forbidden')\n"
        "    return raw\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(package, source_root=root)

    assert report["pass"] is True
    assert report["findings"] == []


def test_dynamic_audit_runs_real_side_effect_free_formal_entrypoint(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    protected = tmp_path / "protected"
    protected.mkdir()
    entrypoint = root / FORMAL_BLIND_ENTRYPOINTS[0]

    report = run_audit_canary(
        entrypoint,
        protected_paths=(protected,),
        argv=("--help",),
        cwd=root,
    )

    assert report["pass"] is True
    assert report["status"] == "audit_pass"
    assert report["violations"] == []


def test_forbidden_field_and_literal_are_redacted(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    protected_field = "reference_authority_path"
    protected_literal = "/sealed/reference/data/p6_h7p5.json"
    (package / "entry.py").write_text(
        f"{protected_field} = {protected_literal!r}\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(package, source_root=root)
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert {item["rule_id"] for item in report["findings"]} & {
        "S002",
        "S005",
        "S006",
        "S007",
    }
    assert protected_field not in rendered
    assert protected_literal not in rendered
    assert hashlib.sha256(protected_field.encode()).hexdigest() in rendered
    assert hashlib.sha256(protected_literal.encode()).hexdigest() in rendered


def test_protected_source_filename_is_redacted(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    protected_name = "hidden_auditor.py"
    protected_source = package / protected_name
    protected_source.write_text(
        "reference_authority_path = 1\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(package, source_root=root)
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert any(
        item["source"].startswith("redacted/")
        for item in report["findings"]
    )
    assert protected_name not in rendered


def test_manifest_is_additional_properties_false_and_leak_safe() -> None:
    payload = _manifest()
    payload["trial"]["unexpected"] = 1
    protected_field = "hidden_reference_hash"
    payload["cycle"][protected_field] = "9" * 64

    report = validate_blind_input_manifest(payload)
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert {item["rule_id"] for item in report["issues"]} >= {
        "M002",
        "M010",
    }
    assert protected_field not in rendered
    assert hashlib.sha256(protected_field.encode()).hexdigest() in rendered


def test_manifest_rejects_wrong_types_and_cycle_outside_trial() -> None:
    payload = _manifest()
    payload["trial"]["maximum_cycles"] = 1
    payload["cycle"]["cycle_index"] = 1
    payload["cycle"]["mesh_forest_sha256"] = True

    report = validate_blind_input_manifest(payload)

    assert report["pass"] is False
    assert {item["rule_id"] for item in report["issues"]} >= {
        "M005",
        "M008",
    }


def test_protected_fingerprint_catches_opaque_literal_without_echo(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    protected_value = "opaque-canary-value-123"
    protected_fingerprint = hashlib.sha256(protected_value.encode()).hexdigest()
    (package / "entry.py").write_text(
        f"CANARY = {protected_value!r}\n",
        encoding="utf-8",
    )

    report = scan_blind_controller(
        package,
        source_root=root,
        protected_fingerprints=(protected_fingerprint,),
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert any(item["rule_id"] == "S008" for item in report["findings"])
    assert protected_value not in rendered
    assert protected_fingerprint in rendered


def test_dynamic_audit_allows_unprotected_file_access(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed.txt"
    allowed.write_text("allowed\n", encoding="utf-8")
    protected = tmp_path / "protected"
    protected.mkdir()
    entrypoint = tmp_path / "entry.py"
    entrypoint.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).read_text(encoding='utf-8')\n",
        encoding="utf-8",
    )

    report = run_audit_canary(
        entrypoint,
        protected_paths=(protected,),
        argv=(str(allowed),),
    )

    assert report["pass"] is True
    assert report["status"] == "audit_pass"
    assert report["violations"] == []


def test_dynamic_audit_blocks_protected_file_without_path_echo(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    canary = protected / "authority-canary.json"
    canary.write_text("{}\n", encoding="utf-8")
    entrypoint = tmp_path / "entry.py"
    entrypoint.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "try:\n"
        "    Path(sys.argv[1]).read_text(encoding='utf-8')\n"
        "except Exception:\n"
        "    pass\n",
        encoding="utf-8",
    )

    report = run_audit_canary(
        entrypoint,
        protected_paths=(protected,),
        argv=(str(canary),),
    )
    rendered = json.dumps(report, sort_keys=True)

    assert report["pass"] is False
    assert report["status"] == "protected_access_detected"
    assert report["violations"]
    assert str(protected) not in rendered
    assert str(canary) not in rendered


def test_dynamic_audit_fails_closed_on_unmonitored_subprocess(
    tmp_path: Path,
) -> None:
    protected = tmp_path / "protected"
    protected.mkdir()
    entrypoint = tmp_path / "entry.py"
    entrypoint.write_text(
        "import subprocess\n"
        "import sys\n"
        "try:\n"
        "    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n"
        "except Exception:\n"
        "    pass\n",
        encoding="utf-8",
    )

    report = run_audit_canary(
        entrypoint,
        protected_paths=(protected,),
    )

    assert report["pass"] is False
    assert report["status"] == "protected_access_detected"
    assert {item["rule_id"] for item in report["violations"]} == {"D002"}


def test_combined_report_uses_independent_exit_bits(tmp_path: Path) -> None:
    root, package = _safe_package(tmp_path)
    (package / "entry.py").write_text(
        "from src.adaptivity.reference_certifier.api import certify\n",
        encoding="utf-8",
    )
    payload = copy.deepcopy(_manifest())
    payload["trial"]["extra"] = "not-allowed"
    audit_entry = package / "audit_entry.py"
    audit_entry.write_text("VALUE = 1\n", encoding="utf-8")
    protected = tmp_path / "protected"
    protected.mkdir()

    report = build_reference_leak_report(
        controller_package=package,
        source_root=root,
        manifest=payload,
        audit_entrypoint=audit_entry,
        audit_protected_paths=(protected,),
    )

    assert report["exit_code"] == (
        EXIT_STATIC_LEAK | EXIT_MANIFEST_LEAK_OR_SCHEMA_ERROR
    )
    assert report["exit_code_bits"] == {
        "static_leak": True,
        "manifest_leak_or_schema_error": True,
        "dynamic_access": False,
    }


def test_cli_outputs_json_and_dynamic_exit_bit(
    tmp_path: Path,
    capsys,
) -> None:
    root, package = _safe_package(tmp_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    protected = tmp_path / "protected"
    protected.mkdir()
    canary = protected / "canary"
    canary.write_text("secret", encoding="utf-8")
    entrypoint = package / "audit_entry.py"
    entrypoint.write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "Path(sys.argv[1]).read_bytes()\n",
        encoding="utf-8",
    )

    return_code = main(
        [
            "--controller-package",
            str(package),
            "--source-root",
            str(root),
            "--manifest",
            str(manifest),
            "--source-entry",
            str(entrypoint),
            "--audit-entry",
            str(entrypoint),
            "--protected-path",
            str(protected),
            "--audit-arg",
            str(canary),
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert return_code == EXIT_DYNAMIC_ACCESS
    assert output["exit_code"] == EXIT_DYNAMIC_ACCESS
    assert output["pass"] is False
    assert str(protected) not in json.dumps(output)
    assert str(canary) not in json.dumps(output)


def test_report_artifact_binds_payload_and_checker_source(
    tmp_path: Path,
) -> None:
    root, package = _safe_package(tmp_path)
    audit_entry = package / "audit_entry.py"
    audit_entry.write_text("VALUE = 1\n", encoding="utf-8")
    protected = tmp_path / "protected"
    protected.mkdir()
    report = build_reference_leak_report(
        controller_package=package,
        source_root=root,
        source_entrypoints=(audit_entry,),
        manifest=_manifest(),
        audit_entrypoint=audit_entry,
        audit_protected_paths=(protected,),
    )

    artifact = build_reference_leak_report_artifact(report)

    assert artifact["schema_version"] == CHECKER_ARTIFACT_SCHEMA
    assert artifact["payload"] == report
    assert artifact["producer"]["source"] == (
        "benchmarks/task035e_reference_leak_checker.py"
    )
    assert artifact["sha256"] == hashlib.sha256(
        json.dumps(
            report,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
