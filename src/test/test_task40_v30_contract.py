from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners import task40_v30_contract as contract_module


ROOT = Path(__file__).resolve().parents[2]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_v30_reference_gate_builds_two_distinct_mixed_fe_and_all_port_rhs():
    from src.runners.task40_v10_worker import _task40_v30_mixed_reference_rhs_cases

    cases = _task40_v30_mixed_reference_rhs_cases(
        independent_row_count=12,
        interior_rows=np.asarray([2, 5, 8], dtype=np.int64),
        original_h=np.asarray([1.0, 1.25, 1.5, 2.0], dtype=np.float64),
    )

    assert [name for name, _, _ in cases] == [
        "mixed_generic_fe_and_all_mode_port_rhs",
        "mixed_interior_fe_and_all_mode_port_rhs",
    ]
    for _, fe_rhs, port_rhs in cases:
        assert np.isfinite(fe_rhs).all() and np.any(fe_rhs != 0.0)
        assert np.isfinite(port_rhs).all() and np.all(port_rhs != 0.0)
    assert not np.array_equal(cases[0][1], cases[1][1])
    assert not np.array_equal(cases[0][2], cases[1][2])
    assert np.count_nonzero(cases[1][1]) == 3


def test_v30_worker_qualifies_reference_before_building_the_target():
    worker_path = Path(__file__).resolve().parents[1] / "runners/task40_v10_worker.py"
    source = worker_path.read_text(encoding="utf-8")

    reference_built = source.index("reference = build_task40_v10_p6_reference_inverse(")
    reference_qualified = source.index(
        'runtime.marker("v10_regular_reference_inverse_qualified", regular_checks)',
        reference_built,
    )
    v30_target_built = source.index(
        "_task40_v30_build_target_after_reference(", reference_qualified
    )
    target_builder_defined = source.index("def build_target_context(")
    actual_rows_checked = source.index(
        "actual_rows = int(target_action.condensed.full_rows)", target_builder_defined
    )
    target_backend_built = source.index(
        "target_fast_bundle = build_packed_physical_action(", actual_rows_checked
    )
    target_rhs_built = source.index(
        "physical_rhs, rhs_facts = build_physical_rhs(target_bundle)", target_backend_built
    )

    assert reference_built < reference_qualified < v30_target_built
    assert target_builder_defined < actual_rows_checked < target_backend_built
    assert reference_qualified < v30_target_built < target_rhs_built


def test_v30_reference_first_control_flow_passes_frozen_identity_and_sector_builder_args():
    from src.runners.task40_v10_worker import (
        _task40_v30_build_target_after_reference,
        _task40_v30_sector_builder_inputs,
    )

    mode_sha = "a" * 64
    mode_inventory = ((), (), mode_sha)
    reference = {"global_bundle": {"mode_sha256": mode_sha}}
    profile = SimpleNamespace(q_port_counts=(4076, 0, 0, 0, 3856, 0, 0, 0))
    coordinates = SimpleNamespace(width=773568)
    q_maps = {
        0: SimpleNamespace(shape=(1, 777644)),
        4: SimpleNamespace(shape=(1, 777424)),
    }
    events = ["reference_built", "reference_qualified"]

    def target_builder(*, reference_owner, mode_inventory):
        events.append("target_builder")
        sector_inputs = _task40_v30_sector_builder_inputs(
            global_bundle=reference_owner["global_bundle"],
            mode_inventory=mode_inventory,
            coordinates=coordinates,
            profile=profile,
            q_maps_by_q=q_maps,
            sector_q_indices=(0, 4),
        )
        events.append("sector_callback_arguments_bound")
        return sector_inputs

    result = _task40_v30_build_target_after_reference(
        reference_owner=reference,
        regular_checks={"passed": True},
        mode_inventory=mode_inventory,
        target_builder=target_builder,
    )

    assert events == [
        "reference_built",
        "reference_qualified",
        "target_builder",
        "sector_callback_arguments_bound",
    ]
    assert result["mode_manifest_sha256"] == mode_sha
    assert result["trace_rows_by_q"] == {0: 773568, 4: 773568}


@pytest.mark.parametrize("source_qualified_attempt", [False, True])
def test_v30_service_accepts_real_canonical_full_variant_only_with_exact_overrides(
    tmp_path, source_qualified_attempt
):
    from scripts import task40_v20_service_workflow as service

    assert service._v30_q0_csr_shape(
        [777_644, 777_644], (1_555_068, 777_644)
    ) == [777_644, 777_644]
    with pytest.raises(ValueError, match="q0 CSR shape"):
        service._v30_q0_csr_shape([1_555_068, 777_644], (1_555_068, 777_644))

    canonical_path = ROOT / "input/task40extra_0p7nm_engineering/target_original_ny8_resource_pilot_v20.dat"
    canonical_text = canonical_path.read_text(encoding="utf-8")
    source_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    artifact_attempt = service.V30_ARTIFACT_ROOT
    if source_qualified_attempt:
        artifact_attempt = artifact_attempt / "attempts" / source_sha
    selector = tmp_path / artifact_attempt / "q0_selector_v30_partial.json"
    selector.parent.mkdir(parents=True)
    selector.write_text(
        json.dumps(
            {
                "schema": "task40extra.review_v30_qualified_q_csr_selector.v1",
                "profile": service.V30_TARGET_PROFILE,
                "q_csr_entries": [
                    {
                        "q_index": 0,
                        "twist_index": 0,
                        "execution_identity": {"source_sha": source_sha},
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    stage_root = tmp_path / artifact_attempt / "stage_inputs/full"
    stage_root.mkdir(parents=True)
    stage_path = stage_root / canonical_path.name
    selector_rel = selector.relative_to(tmp_path).as_posix()
    output_rel = (tmp_path / artifact_attempt / "factor_bank").relative_to(tmp_path).as_posix()
    selector_sha = _sha(selector)
    rendered = service.render_stage_input(canonical_text, "full")
    overrides = (
        "task40_target_heavy_authorized = true\n"
        "task40_v30_q_csr_binding = { schema = \"task40extra.review_v30_q_csr_worker_binding.v1\", "
        f"selector_path = \"{selector_rel}\", selector_sha256 = \"{selector_sha}\" }}\n"
        "task40_v30_factor_bank_config = { schema = \"task40extra.review_v30_all_q_factor_bank.v1\", "
        f"output_directory = \"{output_rel}\", require_two_strict_rhs = true }}\n"
    )
    assert rendered.count("task40_target_heavy_authorized = false") == 1
    rendered = rendered.replace(
        "task40_target_heavy_authorized = false\n", overrides, 1
    )
    stage_path.write_text(rendered, encoding="utf-8")

    from src.io.input_validation import load_and_resolve

    canonical_resolved = load_and_resolve(canonical_path).as_jsonable()
    staged_resolved = load_and_resolve(stage_path).as_jsonable()
    expected_selector = {
        "schema": "task40extra.review_v30_q_csr_worker_binding.v1",
        "selector_path": selector_rel,
        "selector_sha256": selector_sha,
    }
    expected_factor = {
        "schema": "task40extra.review_v30_all_q_factor_bank.v1",
        "output_directory": output_rel,
        "require_two_strict_rhs": True,
    }
    for field in (
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
        "solver",
        "output",
        "derived",
    ):
        assert staged_resolved[field] == canonical_resolved[field]
    for field in (
        "schema_version",
        "model_id",
        "run_id",
        "comparison_group",
        "dimension",
    ):
        assert staged_resolved[field] == canonical_resolved[field]
    expected_execution = dict(canonical_resolved["execution"])
    expected_execution.update(
        {
            "task40_execution_stop_stage": "full",
            "task40_target_heavy_authorized": True,
            "task40_v30_q_csr_binding": expected_selector,
            "task40_v30_factor_bank_config": expected_factor,
        }
    )
    assert staged_resolved["execution"] == expected_execution

    invalid_inputs = (
        (
            rendered.replace(
                f'selector_sha256 = "{selector_sha}" }}',
                f'selector_sha256 = "{selector_sha}", extra = true }}',
                1,
            ),
            "exactly schema, selector_path, and selector_sha256",
        ),
        (
            rendered.replace(selector_sha, "A" * 64, 1),
            "64 lowercase hexadecimal characters",
        ),
        (
            rendered.replace(
                f'selector_path = "{selector_rel}"',
                'selector_path = "../selector.json"',
                1,
            ),
            "selector and factor-bank paths must be the exact legacy V30 pair or the same-source V30 attempt pair",
        ),
        (
            rendered.replace("require_two_strict_rhs = true", "require_two_strict_rhs = false", 1),
            "must be the TOML boolean true",
        ),
        (
            rendered.replace(
                'task40_target_heavy_authorized = true\n',
                'task40_target_heavy_authorized = false\n',
                1,
            ),
            "explicitly authorized full original-size target profile",
        ),
        (
            rendered.replace(
                'task40_v30_factor_bank_config = { schema = '
                '"task40extra.review_v30_all_q_factor_bank.v1", '
                f'output_directory = "{output_rel}", require_two_strict_rhs = true }}\n',
                "",
                1,
            ),
            "V30 requires both",
        ),
        (
            rendered.replace("\n[output]", "\nunregistered_v30_escape = true\n\n[output]", 1),
            "unknown field",
        ),
    )
    for index, (invalid_text, expected_error) in enumerate(invalid_inputs):
        assert invalid_text != rendered
        invalid_path = stage_root / f"invalid_{index}_{canonical_path.name}"
        invalid_path.write_text(invalid_text, encoding="utf-8")
        with pytest.raises(ValueError, match=expected_error):
            load_and_resolve(invalid_path)

    parsed_path, _campaign, stop_stage, data = service._parse_case_arguments(
        [
            str(stage_path),
            "--task40-v10-campaign-window",
            str(service.TASK40_V30_TARGET_CAMPAIGN_WINDOW),
        ],
        v30_contract=True,
    )
    assert stop_stage == "full"
    service._validate_service_stage_input_variant(
        parsed_path,
        canonical_path,
        canonical_text,
        stop_stage,
        data,
        repo_root=tmp_path,
        v30_contract=True,
    )
    identity = contract_module.require_v30_input_identity(
        canonical_path, stage_path, repo_root=tmp_path
    )
    assert identity["scientific_input_sha256"] == _sha(canonical_path)
    assert identity["staged_input_sha256"] == _sha(stage_path)
    assert identity["scientific_input_sha256"] != identity["staged_input_sha256"]

    changed = dict(data)
    changed["geometry"] = dict(data["geometry"])
    changed["geometry"]["period_x_nm"] += 0.01
    with pytest.raises(ValueError, match="outside its exact target-operation bindings"):
        service._validate_service_stage_input_variant(
            parsed_path, canonical_path, canonical_text, stop_stage, changed,
            repo_root=tmp_path, v30_contract=True,
        )


def test_v30_q4_reuses_real_v26_witness_and_support_receipts_read_only():
    from src.runners.task40_v10_campaign import TASK40_V28_CAMPAIGN_SHA256
    from src.runners.task40_v10_worker import (
        _task40_v30_open_saved_q4_native_witness,
        _task40_v30_q4_direct_hhat_evidence,
    )
    from src.solvers.task40_v30_selected_q_csr import _checked_saved_native_vector

    manifest_path = ROOT / contract_module.V30_Q0_DONOR["manifest_relative_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    fill = manifest["numeric_fill_identity"]
    donor = fill["donor_identity"]
    identity = fill["execution_identity"]
    operator_identity = {
        "scientific_input_sha256": contract_module.V30_CANONICAL_INPUT_SHA256
    }
    current_execution = {
        "source_sha": "a" * 40,
        "window_sha256": "b" * 64,
    }
    gate_records = []
    witness = _task40_v30_open_saved_q4_native_witness(
        contract={"preparation": {"accepted_q0_donor": contract_module.V30_Q0_DONOR}},
        repo_root=ROOT,
        operator_identity=operator_identity,
        current_execution_identity=current_execution,
        input_sha256=contract_module.V30_CANONICAL_INPUT_SHA256,
        physical_model_sha256=identity["physical_model_sha256"],
        mode_manifest_sha256=identity["mode_manifest_sha256"],
        ordered_mode_key_sha256=identity["ordered_mode_key_sha256"],
        allocation_gate=lambda label, facts: gate_records.append((label, facts)),
    )
    assert witness["v28_fill_execution_identity"]["input_sha256"] == identity["input_sha256"]
    assert witness["v28_fill_execution_identity"]["source_sha"] == identity["source_sha"]
    assert witness["v28_fill_execution_identity"]["campaign_window_sha256"] == (
        TASK40_V28_CAMPAIGN_SHA256
    )
    assert witness["v30_execution_identity"] == current_execution
    assert witness["saved_replay_manifest_sha256"] == donor["saved_replay_manifest"]["sha256"]
    assert witness["donor_verifier_receipt"]["schema"] == (
        "task40extra.review_v26_native_case_recovery_check.v1"
    )
    assert witness["array_references"]["case1_full_input"]["artifact_source_sha"] == (
        "5f47bd3f491b4bf485a5caca55da6cb61d8508c5"
    )
    assert witness["array_references"]["case1_full_output"]["artifact_source_sha"] == (
        "3a61e61caf638678d483b6fa06f36374abeef67d"
    )
    expected_lengths = {
        "case1_full_input": 777424,
        "case1_full_output": 777424,
        "selected_to_peer_cross": 777644,
        "peer_case1_input": 777644,
        "peer_case1_output": 777644,
        "peer_to_selected_cross": 777424,
    }
    for name, length in expected_lengths.items():
        value = _checked_saved_native_vector(
            witness,
            name,
            expected_length=length,
            expected_operator_identity=operator_identity,
            expected_current_identity=current_execution,
        )
        assert np.isfinite(value).all()
    assert gate_records[0][0] == "task40_v30_q4_v26_saved_native_witness_readback"

    support = _task40_v30_q4_direct_hhat_evidence(
        repo_root=ROOT,
        producer_facts={
            "producer_identity_sha256": donor["producer_identity_sha256"],
            "payload_sha256": {
                "v25_selected_q0_surface_functionals.bin": next(
                    item["sha256"]
                    for item in donor["producer_identity"]["payloads"]
                    if item["path"].endswith("v25_selected_q0_surface_functionals.bin")
                )
            },
        },
    )
    assert support["numeric_internal_support_empty"] is True
    assert support["internal_B_nnz"] == support["internal_D_nnz"] == 0
    assert support["producer_identity_sha256"] == donor["producer_identity_sha256"]


def _contract_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    absolute_window_path: bool = False,
):
    root = tmp_path / "target"
    root.mkdir()
    window_relative = (
        root / "v30/window.json"
        if absolute_window_path
        else Path("v30/window.json")
    )
    runtime_relative = Path("runtime")
    abi_relative = Path("abi/receipt.json")
    jit_relative = Path("jit")
    donor_manifest_relative = Path("donor/q0_manifest.json")
    donor_qualification_relative = Path("donor/q0_qualification.json")
    for name, value in (
        ("V30_EXECUTION_ROOT", root),
        ("V30_WINDOW_RELATIVE", window_relative),
        ("TASK40_V30_TARGET_CAMPAIGN_WINDOW", window_relative),
        ("V30_RUNTIME_RELATIVE", runtime_relative),
        ("V30_ABI_RECEIPT_RELATIVE", abi_relative),
        ("V30_JIT_CACHE_RELATIVE", jit_relative),
    ):
        monkeypatch.setattr(contract_module, name, value)

    runtime = root / runtime_relative
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python").write_text("fixture interpreter\n", encoding="utf-8")
    abi_receipt = root / abi_relative
    abi_receipt.parent.mkdir(parents=True)
    abi_receipt.write_bytes(b"fixture ABI receipt")
    jit_cache = root / jit_relative
    jit_cache.mkdir()
    donor_manifest = root / donor_manifest_relative
    donor_manifest.parent.mkdir(parents=True)
    donor_manifest.write_bytes(b"accepted q0 manifest")
    donor_qualification = root / donor_qualification_relative
    donor_qualification.write_bytes(b"accepted q0 native PASS")
    donor = {
        "identity_sha256": "d" * 64,
        "manifest_relative_path": donor_manifest_relative.as_posix(),
        "manifest_sha256": _sha(donor_manifest),
        "native_qualification_relative_path": donor_qualification_relative.as_posix(),
        "native_qualification_status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
        "native_qualification_sha256": _sha(donor_qualification),
    }
    monkeypatch.setattr(contract_module, "V30_Q0_DONOR", donor)
    monkeypatch.setattr(contract_module, "V30_ABI_RECEIPT_SHA256", _sha(abi_receipt))

    window_path = root / window_relative
    window_path.parent.mkdir(parents=True)
    user_approval = {
        "scope": contract_module.V30_SCOPE,
        "execution_host": contract_module.V30_TARGET_HOST,
        "execution_root": str(root),
        "resources": dict(contract_module.V30_RESOURCES),
        "statement": "approved fixture",
    }
    window = {
        "stage_scope": list(contract_module.TASK40_V30_STAGE_SCOPE),
        "initial_boot_id": contract_module.V30_TARGET_BOOT_ID,
        "user_approval": user_approval,
        "target_clock_receipt_sha256": "079a2031f16abe1d3eaf2a122801351670278d9007235b1705e0846e45920ae4",
    }
    window_path.write_text(json.dumps(window), encoding="utf-8")
    window_sha = _sha(window_path)
    monkeypatch.setattr(contract_module, "TASK40_V30_TARGET_CAMPAIGN_SHA256", window_sha)
    monkeypatch.setattr(
        contract_module,
        "load_fixed_campaign_window",
        lambda _path, require_current_boot: SimpleNamespace(sha256=window_sha),
    )
    contract_path = window_path.parent / "execution_contract_v30.json"
    payload = {
        "schema": contract_module.V30_CONTRACT_SCHEMA,
        "authorization_status": "USER_APPROVED",
        "scope": contract_module.V30_SCOPE,
        "campaign": contract_module.TASK40_V30_CAMPAIGN_ID,
        "review_commit": contract_module.TASK40_V30_REVIEW_COMMIT,
        "review_path": contract_module.TASK40_V30_REVIEW_PATH,
        "review_sha256": contract_module.TASK40_V30_REVIEW_SHA256,
        "source_at_entry": contract_module.TASK40_V30_SOURCE_AT_ENTRY,
        "campaign_stage_scope": list(contract_module.TASK40_V30_STAGE_SCOPE),
        "preparation": {
            "accepted_q0_donor": donor,
            "q_csr_worklist": contract_module.V30_Q_CSR_WORKLIST,
            "final_all_q_selector_required_at": "P3_all_q_resident_factor_bank",
        },
        "user_approval": user_approval,
        "execution": {
            "execution_host": contract_module.V30_TARGET_HOST,
            "execution_root": str(root),
            "host_identity": {
                "hostname": contract_module.V30_TARGET_HOSTNAME,
                "runtime_profile": "native_linux",
                "boot_id": contract_module.V30_TARGET_BOOT_ID,
            },
            "resources": dict(contract_module.V30_RESOURCES),
            "window": {
                "total_seconds": contract_module.TASK40_V30_CAMPAIGN_SECONDS,
                "numeric_cutoff_after_t0_seconds": 42_000.0,
                "closeout_reserve_seconds": contract_module.TASK40_V30_CLOSEOUT_RESERVE_SECONDS,
                "t0_utc": "2026-10-12T12:23:42.000Z",
            },
            "scalar_type": "complex128",
            "index_type": "int32",
            "runtime_prefix": runtime_relative.as_posix(),
            "abi_receipt_path": abi_relative.as_posix(),
            "abi_receipt_sha256": _sha(abi_receipt),
            "jit_cache": jit_relative.as_posix(),
            "campaign_window_path": window_relative.as_posix(),
            "campaign_window_sha256": window_sha,
        },
    }
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    return root, contract_path, payload


def _v30_full_stage_fixture(root: Path, source_sha: str):
    from scripts import task40_v20_service_workflow as service
    from src.io.input_validation import load_and_resolve

    canonical = root / contract_module.V30_CANONICAL_INPUT_RELATIVE
    canonical.parent.mkdir(parents=True, exist_ok=True)
    canonical.write_bytes(
        (ROOT / contract_module.V30_CANONICAL_INPUT_RELATIVE).read_bytes()
    )
    attempt = (
        root
        / contract_module.V30_ARTIFACT_ROOT_RELATIVE
        / "attempts"
        / source_sha
    )
    selector = attempt / "q0_selector_v30_partial.json"
    selector.parent.mkdir(parents=True, exist_ok=True)
    selector.write_text(
        json.dumps(
            {
                "schema": "task40extra.review_v30_qualified_q_csr_selector.v1",
                "profile": service.V30_TARGET_PROFILE,
                "q_csr_entries": [
                    {
                        "q_index": 0,
                        "twist_index": 0,
                        "execution_identity": {"source_sha": source_sha},
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    staged = attempt / "stage_inputs/full" / canonical.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    selector_relative = selector.relative_to(root).as_posix()
    output_relative = (attempt / "factor_bank").relative_to(root).as_posix()
    rendered = service.render_stage_input(canonical.read_text(encoding="utf-8"), "full")
    overrides = (
        "task40_target_heavy_authorized = true\n"
        "task40_v30_q_csr_binding = { schema = "
        '"task40extra.review_v30_q_csr_worker_binding.v1", '
        f'selector_path = "{selector_relative}", selector_sha256 = "{_sha(selector)}" }}\n'
        "task40_v30_factor_bank_config = { schema = "
        '"task40extra.review_v30_all_q_factor_bank.v1", '
        f'output_directory = "{output_relative}", require_two_strict_rhs = true }}\n'
    )
    rendered = rendered.replace(
        "task40_target_heavy_authorized = false\n", overrides, 1
    )
    staged.write_text(rendered, encoding="utf-8")
    return canonical, staged, selector, load_and_resolve(staged)


def _set_v30_contract_environment(
    monkeypatch: pytest.MonkeyPatch, root: Path, contract_path: Path
) -> None:
    from scripts import task40_v20_service_workflow as service

    contract_sha = _sha(contract_path)
    window_path = root / contract_module.V30_WINDOW_RELATIVE
    resources = contract_module.V30_RESOURCES
    for key, value in {
        "TASK40_V30_STRICT_EXECUTION": "1",
        "TASK40_V30_CONTRACT_PATH": str(contract_path),
        "TASK40_V30_CONTRACT_SHA256": contract_sha,
        "TASK40_V30_EXECUTION_WINDOW_PATH": service._v30_environment_window_path(
            {"path": window_path}
        ),
        "TASK40_V30_EXECUTION_WINDOW_SHA256": _sha(window_path),
        "TASK40_V30_TASK_MEMORY_MAX_BYTES": str(resources["task_memory_max_bytes"]),
        "TASK40_V30_HOST_RESERVE_BYTES": str(resources["host_reserve_bytes"]),
        "TASK40_V30_MEMORY_SWAP_MAX_BYTES": str(resources["memory_swap_max_bytes"]),
    }.items():
        monkeypatch.setenv(key, value)


def test_v30_service_exports_registered_relative_contract_window_as_absolute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from scripts import task40_v20_service_workflow as service

    root, _contract_path, payload = _contract_fixture(tmp_path, monkeypatch)
    contract_window_path = payload["execution"]["campaign_window_path"]
    assert not Path(contract_window_path).is_absolute()
    registered_path = root / contract_window_path

    assert service._v30_environment_window_path({"path": registered_path}) == str(
        registered_path.resolve()
    )


def test_v30_dispatcher_passes_authorized_copy_through_real_worker_before_runtime_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.runners import task038_full3d_iterative as dispatcher
    from src.runners import task40_v10_worker, task40_v20_stage_runner
    from src.runners import physical_p4_schur_v14
    from src.io import input_validation

    root, contract_path, _ = _contract_fixture(
        tmp_path, monkeypatch, absolute_window_path=True
    )
    source_sha = "a" * 40
    _canonical, _staged, _selector, resolved = _v30_full_stage_fixture(
        root, source_sha
    )
    _set_v30_contract_environment(monkeypatch, root, contract_path)
    monkeypatch.setattr(
        dispatcher,
        "__file__",
        str(root / "src/runners/task038_full3d_iterative.py"),
    )
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "__file__",
        str(root / "src/runners/task40_v20_stage_runner.py"),
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "__file__",
        str(root / "src/runners/task40_v10_worker.py"),
    )
    preflight = {
        "run_id": resolved.as_jsonable()["run_id"],
        "input_sha256": resolved.input_sha256,
        "physical_model_sha256": resolved.physical_model_sha256,
    }
    monkeypatch.setattr(
        task40_v20_stage_runner,
        "_preflight",
        lambda *_args, **_kwargs: (dict(preflight), None, None),
    )
    class RuntimeBoundaryReached(Exception):
        pass

    captured: dict[str, object] = {}
    real_worker = task40_v10_worker.run_task40_v10_p6_reference_worker

    def observed_worker(payload, run_directory, **kwargs):
        captured["payload_strategy"] = payload["solver"][
            "task40_factor_lifecycle_strategy"
        ]
        captured["requested"] = kwargs["v30_requested_factor_lifecycle_strategy"]
        captured["effective"] = kwargs["v30_effective_factor_lifecycle_strategy"]
        return real_worker(payload, run_directory, **kwargs)

    def stop_at_runtime(*args, **kwargs):
        captured["runtime_args"] = args
        captured["runtime_kwargs"] = kwargs
        raise RuntimeBoundaryReached

    monkeypatch.setattr(
        task40_v10_worker, "run_task40_v10_p6_reference_worker", observed_worker
    )
    monkeypatch.setattr(physical_p4_schur_v14, "_V14Runtime", stop_at_runtime)
    monkeypatch.setattr(
        input_validation,
        "simulation_config_3d_from_normalized",
        lambda *_args, **_kwargs: pytest.fail(
            "worker crossed the runtime boundary into FE configuration"
        ),
    )
    with pytest.raises(RuntimeBoundaryReached):
        dispatcher.run_full3d_iterative(
            resolved.as_jsonable(), tmp_path / "run", source_sha=source_sha
        )

    assert resolved.solver["task40_factor_lifecycle_strategy"] == "ONE_Q_REFACTOR_V19"
    assert captured["payload_strategy"] == "ALL_Q_RESIDENT"
    assert captured["requested"] == "ONE_Q_REFACTOR_V19"
    assert captured["effective"] == "ALL_Q_RESIDENT"
    runtime_kwargs = captured["runtime_kwargs"]
    assert runtime_kwargs["fixed_process_tree_cap_bytes"] == contract_module.V30_RESOURCES[
        "task_memory_max_bytes"
    ]
    assert runtime_kwargs["host_reserve_bytes"] == contract_module.V30_RESOURCES[
        "host_reserve_bytes"
    ]
    assert runtime_kwargs["task_cgroup_reserve_bytes"] == 0
    assert runtime_kwargs["require_cgroup_memory_details"] is True
    preflight_receipt = json.loads(
        (tmp_path / "run/v20_stage_preflight.json").read_text(encoding="utf-8")
    )
    assert preflight_receipt["v30_factor_lifecycle_authority"] == {
        "requested": "ONE_Q_REFACTOR_V19",
        "effective": "ALL_Q_RESIDENT",
    }
    worker_receipt = json.loads(
        (tmp_path / "run/v30_worker_service_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert worker_receipt["failure_type"] == "RuntimeBoundaryReached"
    assert worker_receipt["factor_lifecycle_strategy"] == {
        "requested": "ONE_Q_REFACTOR_V19",
        "effective": "ALL_Q_RESIDENT",
    }


def test_v30_launcher_passes_approved_resources_to_watchdog_without_fe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.runners import task038_launcher, task40_v10_campaign
    from benchmarks import subreaper_watchdog

    root, contract_path, _ = _contract_fixture(tmp_path, monkeypatch)
    source_sha = "b" * 40
    _canonical, staged, _selector, specification = _v30_full_stage_fixture(
        root, source_sha
    )
    _set_v30_contract_environment(monkeypatch, root, contract_path)
    monkeypatch.setattr(
        task038_launcher,
        "__file__",
        str(root / "src/runners/task038_launcher.py"),
    )
    window_path = root / contract_module.V30_WINDOW_RELATIVE
    window_sha = _sha(window_path)

    def observe(label):
        return {
            "label": label,
            "remaining_numerical_seconds": 42_000.0,
            "elapsed_seconds": 0.0,
        }

    campaign_window = SimpleNamespace(
        path=window_path,
        sha256=window_sha,
        t0_utc_ns=1,
        deadline_utc_ns=43_200_000_000_000,
        total_seconds=43_200.0,
        closeout_seconds=1_200.0,
        observe=observe,
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda _path: campaign_window,
    )
    run_directory = tmp_path / "launcher-run"

    def timestamp_directory(*_args, **_kwargs):
        run_directory.mkdir(parents=True, exist_ok=True)
        return run_directory

    monkeypatch.setattr(
        task038_launcher,
        "_timestamp_directory",
        timestamp_directory,
    )
    monkeypatch.setattr(
        task038_launcher, "current_cgroup_path", lambda: Path("/fake/task40.service")
    )
    monkeypatch.setattr(
        task038_launcher, "_is_v28_user_service_cgroup", lambda _path: True
    )
    monkeypatch.setattr(
        task038_launcher,
        "_physical_source_gate",
        lambda *_args, **_kwargs: {
            "source_sha": source_sha,
            "tracked_and_nonignored_untracked_clean": True,
        },
    )
    monkeypatch.setattr(
        task038_launcher,
        "build_execution_plan",
        lambda *_args, **_kwargs: SimpleNamespace(
            adapter_available=True, argv=("fixture-no-fe-worker",), contract_probe=False
        ),
    )
    captured: dict[str, object] = {}

    def fake_supervise(_argv, _directory, **kwargs):
        captured.update(kwargs)
        return {
            "leader_exit_code": 0,
            "classification": "COMPLETED",
            "launch_envelope": {"effective_total_bytes": 1},
            "memory_scope": "fixture subreaper and descendants",
            "descendants_cleared": True,
            "process_tree_swap_gate_enforced": True,
            "sampled_process_tree_swap_peak_bytes": 0,
            "job_cgroup_swap_gate_enforced": True,
            "job_cgroup_swap": {"passed": True},
        }

    monkeypatch.setattr(subreaper_watchdog, "supervise", fake_supervise)
    result = task038_launcher.launch_specification(
        specification, source_sha=source_sha, task40_v10_campaign_window=window_path
    )

    assert result["result_classification"] == "worker_exit0"
    assert captured["tree_cap_bytes"] == contract_module.V30_RESOURCES[
        "task_memory_max_bytes"
    ]
    assert captured["host_reserve_bytes"] == contract_module.V30_RESOURCES[
        "host_reserve_bytes"
    ]
    assert captured["task_cgroup_reserve_bytes"] == 0
    assert captured["require_job_cgroup_zero_swap"] is True
    assert captured["require_cgroup_memory_details"] is True
    worker_environment = captured["worker_environment"]
    assert worker_environment["TASK40_V30_CONTRACT_SHA256"] == _sha(contract_path)
    assert worker_environment["TASK40_V30_EXECUTION_WINDOW_PATH"] == str(
        window_path.resolve()
    )
    assert specification.as_jsonable()["provenance"]["source_path"] == str(staged)


@pytest.mark.parametrize("require_details", [False, True])
def test_subreaper_supervise_forwards_cgroup_detail_policy_before_worker_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, require_details: bool
):
    from benchmarks import subreaper_watchdog

    class MemoryEnvelopeReached(Exception):
        pass

    captured: dict[str, object] = {}

    def capture_memory_envelope(policy, **kwargs):
        captured.update(policy=policy, kwargs=kwargs)
        raise MemoryEnvelopeReached

    monkeypatch.setattr(
        subreaper_watchdog.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: SimpleNamespace(
            prctl=lambda *_prctl_args: 0
        ),
    )
    monkeypatch.setattr(subreaper_watchdog, "_children", lambda: [])
    monkeypatch.setattr(
        subreaper_watchdog, "memory_envelope", capture_memory_envelope
    )
    kwargs = {"require_cgroup_memory_details": True} if require_details else {}

    with pytest.raises(MemoryEnvelopeReached):
        subreaper_watchdog.supervise(
            ["fixture-no-worker"],
            tmp_path / f"watchdog-{require_details}",
            wall_seconds=1.0,
            interval=0.1,
            grace_seconds=0.1,
            **kwargs,
        )

    assert captured["kwargs"]["require_cgroup_memory_details"] is require_details


def test_v30_contract_validates_target_window_resources_and_q0_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, path, _ = _contract_fixture(tmp_path, monkeypatch)

    payload, digest = contract_module.require_authorized_contract(
        path,
        current_root=root,
        current_hostname="fenics-ws01",
    )

    assert digest == _sha(path)
    assert payload["preparation"]["accepted_q0_donor"]["identity_sha256"] == "d" * 64
    assert [row["q"] for row in payload["preparation"]["q_csr_worklist"]] == [4, 1, 5, 2, 6, 3, 7]
    assert payload["preparation"]["final_all_q_selector_required_at"] == "P3_all_q_resident_factor_bank"


def test_v30_contract_rejects_resource_or_target_identity_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root, path, payload = _contract_fixture(tmp_path, monkeypatch)
    payload["execution"]["resources"]["task_memory_max_bytes"] -= 1
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(contract_module.V30ContractError, match="resources differ"):
        contract_module.require_authorized_contract(path, current_root=root)


def test_v30_live_resource_gate_enforces_fixed_cap_reserve_and_zero_swap():
    contract = {"execution": {"resources": dict(contract_module.V30_RESOURCES)}}
    cap = contract_module.V30_RESOURCES["task_memory_max_bytes"]
    reserve = contract_module.V30_RESOURCES["host_reserve_bytes"]

    receipt = contract_module.validate_live_resource_contract(
        contract,
        cgroup_limit_bytes=cap,
        cgroup_current_bytes=100,
        cgroup_swap_current_bytes=0,
        host_effective_available_bytes=reserve + 100,
        additional_request_bytes=100,
    )

    assert receipt["passed"] is True
    with pytest.raises(contract_module.V30ContractError, match="swap"):
        contract_module.validate_live_resource_contract(
            contract,
            cgroup_limit_bytes=cap,
            cgroup_current_bytes=100,
            cgroup_swap_current_bytes=1,
            host_effective_available_bytes=reserve + 100,
            additional_request_bytes=0,
        )


def test_v30_memory_envelope_records_finite_ancestor_and_current_cgroup_mix(
    monkeypatch: pytest.MonkeyPatch,
):
    from benchmarks import subreaper_watchdog

    leaf = Path("/sys/fs/cgroup/task40.service")
    root = Path("/sys/fs/cgroup")
    values = {
        leaf / "memory.max": str(contract_module.V30_RESOURCES["task_memory_max_bytes"]),
        leaf / "memory.current": "700",
        leaf / "memory.stat": "anon 400\nfile 250\nfile_dirty 50\n",
        root / "memory.stat": "anon 500\nfile 300\nfile_dirty 60\n",
    }
    monkeypatch.setattr(
        subreaper_watchdog,
        "wsl_memory_snapshot",
        lambda: {"mem_total_bytes": 10_000, "mem_available_bytes": 8_000},
    )
    monkeypatch.setattr(subreaper_watchdog, "current_cgroup_path", lambda: leaf)
    monkeypatch.setattr(subreaper_watchdog.Path, "is_file", lambda path: path in values)
    monkeypatch.setattr(
        subreaper_watchdog.Path,
        "read_text",
        lambda path, *args, **kwargs: values[path],
    )

    envelope = subreaper_watchdog.memory_envelope(
        subreaper_watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY,
        host_reserve_bytes=1_000,
        task_cgroup_reserve_bytes=0,
        require_cgroup_memory_details=True,
    )

    assert envelope["cgroup_limits"] == [
        {
            "path": str(leaf),
            "limit_bytes": contract_module.V30_RESOURCES["task_memory_max_bytes"],
            "current_bytes": 700,
            "anon_bytes": 400,
            "file_bytes": 250,
            "file_dirty_bytes": 50,
        }
    ]
    assert envelope["cgroup_memory_stats"] == [
        {
            "path": str(leaf),
            "limit_bytes": contract_module.V30_RESOURCES["task_memory_max_bytes"],
            "current_bytes": 700,
            "anon_bytes": 400,
            "file_bytes": 250,
            "file_dirty_bytes": 50,
        },
    ]


def test_v30_worker_sample_applies_fixed_cap_and_resource_domains(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    from benchmarks import subreaper_watchdog
    from src.runners import physical_p4_schur_v14 as v14

    captured = {}
    monkeypatch.setattr(
        subreaper_watchdog,
        "memory_envelope",
        lambda policy, **kwargs: captured.update(policy=policy, kwargs=kwargs)
        or {
            "effective_available_bytes": 1_000,
            "reserve_bytes": 100,
            "effective_available_after_reserves_bytes": 600,
            "host_mem_available_bytes": 1_000,
            "task_cgroup_available_bytes": 600,
            "task_cgroup_reserve_bytes": 0,
            "reserve_domains_separated": True,
            "launch_cap_bytes": 600,
            "cgroup_limits": [{"limit_bytes": 750, "current_bytes": 150}],
            "cgroup_memory_stats": [
                {
                    "current_bytes": 150,
                    "anon_bytes": 100,
                    "file_bytes": 40,
                    "file_dirty_bytes": 10,
                }
            ],
        },
    )
    monkeypatch.setattr(
        "benchmarks.task038_full3d_jit_staging.process_tree_snapshot",
        lambda *_args, **_kwargs: {
            "rss_bytes": 200,
            "swap_bytes": 0,
            "all_status_readable": True,
        },
    )
    records = []
    monkeypatch.setattr(v14, "_append_jsonl", lambda _path, row: records.append(row))

    runtime = object.__new__(v14._V14Runtime)
    runtime.stop_requested = False
    runtime._pc_clock = None
    runtime.parent_pid = 1
    runtime._phase = "preflight"
    runtime.pss_sampling_policy = "disabled_by_profile"
    runtime.memory_policy = subreaper_watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY
    runtime.fixed_process_tree_cap_bytes = 750
    runtime.host_reserve_bytes_override = 100
    runtime.task_cgroup_reserve_bytes_override = 0
    runtime.require_cgroup_memory_details = True
    runtime.parent_cap = None
    runtime.inventory_cap = None
    runtime.workspace_cap = None
    runtime.inventory_used_bytes = 0
    runtime.inventory_peak_bytes = 0
    runtime.workspace_live_bytes = 0
    runtime.workspace_peak_bytes = 0
    runtime.require_zero_swap = True
    runtime.time_policy_facts = {}
    runtime.resources_path = tmp_path / "resources.jsonl"
    runtime.stage = "V30_TEST"
    runtime.physical_memory_pressure = True

    sample = runtime.sample("v30_test")

    assert captured == {
        "policy": subreaper_watchdog.PHYSICAL_MEMORY_PRESSURE_POLICY,
        "kwargs": {
            "host_reserve_bytes": 100,
            "task_cgroup_reserve_bytes": 0,
            "require_cgroup_memory_details": True,
        },
    }
    assert sample["dynamic_launch_cap_bytes"] == 800
    assert sample["fixed_process_tree_cap_bytes"] == 750
    assert sample["launch_cap_bytes"] == 750
    assert sample["v30_cgroup_limit_matches_fixed_cap"] is True
    assert sample["v30_cgroup_memory_details_complete"] is True
    assert records[0]["memory_envelope"]["cgroup_memory_stats"][0]["anon_bytes"] == 100


def test_v30_full_csr_validation_uses_bounded_finite_chunks(monkeypatch: pytest.MonkeyPatch):
    import numpy as np
    from scipy import sparse

    from src.solvers import task40_v30_qualified_q_csr as qualified

    matrix = sparse.csr_matrix(
        (np.array([1 + 0j, 2 + 0j], dtype=np.complex128),
         np.array([0, 1], dtype=np.int32),
         np.array([0, 1, 2], dtype=np.int32)),
        shape=(2, 2),
    )
    sizes = []
    original_isfinite = np.isfinite

    def record_size(value):
        sizes.append(np.asarray(value).size)
        return original_isfinite(value)

    monkeypatch.setattr(qualified.np, "isfinite", record_size)
    assert qualified._require_csr(matrix, "test CSR") is matrix
    assert sizes and max(sizes) <= 1 << 20


def test_v30_launcher_has_separate_contract_route_and_no_q_selector_flag():
    source = Path(__file__).resolve().parents[2] / "scripts/run_case_in_user_service.sh"

    text = source.read_text(encoding="utf-8")
    v30_branch = text.split("--task40-v30-execution-contract)", 1)[1]

    assert "src.runners.task40_v30_contract" in v30_branch
    assert "MemoryMax=${v30_values[4]}" in text
    assert "MemorySwapMax=${v30_values[9]}" in text
    assert "TASK40_V30_CONTRACT_SHA256" in text
