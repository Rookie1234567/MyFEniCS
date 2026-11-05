from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import task40_exact_cache_reuse as cache_reuse


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fixture(tmp_path, *, raw_count=7288, carrier_count=272):
    source_root = tmp_path / "source-attempt"
    tensor_root = source_root / "tensor"
    carrier_root = source_root / "carrier"
    numerical_source_sha = "d" * 64
    context_sha = _sha(
        json.dumps(
            {"numerical_source_sha256": numerical_source_sha},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    checkpoint_root = carrier_root / "carrier-checkpoint-v2" / context_sha
    tensor_root.mkdir(parents=True)
    checkpoint_root.mkdir(parents=True)
    source_jit_root = source_root / "xdg" / "fenics"
    source_jit_root.mkdir(parents=True)
    module_path = tmp_path / "compiled.so"
    module_path.write_bytes(b"compiled module identity\n")
    module_sha = _sha(module_path.read_bytes())
    raw_report_path = tmp_path / "raw-integrity.json"
    carrier_report_path = tmp_path / "carrier-integrity.json"
    jit_report_path = tmp_path / "jit-integrity.json"
    raw_report = {
        "status": "PASS",
        "root": str(tensor_root),
        "requests": raw_count,
        "verified": raw_count,
        "payload_bytes": cache_reuse.EXPECTED_RAW_BYTES,
        "errors": [],
        "rows": [{} for _ in range(raw_count)],
        "modules": {str(module_path): module_sha},
    }
    carrier_report = {
        "status": "PASS",
        "root": str(checkpoint_root),
        "verified": carrier_count,
        "bytes": cache_reuse.EXPECTED_CARRIER_BYTES,
        "errors": [],
        "rows": [{"index": index} for index in range(carrier_count)],
    }
    jit_files = []
    jit_count = cache_reuse.EXPECTED_JIT_FILE_COUNT
    for index in range(jit_count):
        name = (
            "libffcx_forms_fixture.cpython-312-x86_64-linux-gnu.so"
            if index == 0
            else f"cache-{index}.bin"
        )
        content = module_path.read_bytes() if index == 0 else f"jit-{index}\n".encode()
        file_path = source_jit_root / name
        file_path.write_bytes(content)
        byte_count = (
            len(content)
            if jit_count != 32
            else cache_reuse.EXPECTED_JIT_BYTES // jit_count
        )
        jit_files.append(
            {
                "name": name,
                "bytes": byte_count,
                "sha256": module_sha if index == 0 else _sha(content),
                "mode": 0o700 if index == 0 else 0o600,
            }
        )
    if jit_count == 32:
        jit_files[-1]["bytes"] += cache_reuse.EXPECTED_JIT_BYTES - sum(
            item["bytes"] for item in jit_files
        )
    jit_report = {
        "schema": "task40.gate_cd.jit_cache_integrity.v1",
        "root": str(source_jit_root),
        "files": jit_files,
        "file_count": jit_count,
        "payload_bytes": cache_reuse.EXPECTED_JIT_BYTES,
        "errors": [],
    }
    raw_report_path.write_text(json.dumps(raw_report), encoding="utf-8")
    carrier_report_path.write_text(json.dumps(carrier_report), encoding="utf-8")
    jit_report_path.write_text(json.dumps(jit_report), encoding="utf-8")
    target_attempt_id = "recovery-fixture"
    source_target_root = tmp_path / f"task40_gate_cd_formal_attempt_{target_attempt_id}"
    contract = {
        "schema": cache_reuse.SCHEMA,
        "profile_identity": cache_reuse.EXPECTED_PROFILE,
        "run_id": cache_reuse.EXPECTED_RUN_ID,
        "raw_tensor_count": raw_count,
        "raw_tensor_payload_bytes": cache_reuse.EXPECTED_RAW_BYTES,
        "carrier_count": carrier_count,
        "carrier_payload_bytes": cache_reuse.EXPECTED_CARRIER_BYTES,
        "require_cache_hits_only": True,
        "allow_compute_on_miss": False,
        "allow_source_cache_writes": False,
        "source_attempt_cache_root": str(source_root),
        "source_tensor_root": str(tensor_root),
        "source_carrier_root": str(carrier_root),
        "source_carrier_checkpoint_root": str(checkpoint_root),
        "source_jit_cache_root": str(source_jit_root),
        "target_attempt_cache_root": str(source_target_root),
        "target_attempt_id": target_attempt_id,
        "raw_integrity_report_path": str(raw_report_path),
        "raw_integrity_report_sha256": _sha(raw_report_path.read_bytes()),
        "carrier_integrity_report_path": str(carrier_report_path),
        "carrier_integrity_report_sha256": _sha(carrier_report_path.read_bytes()),
        "jit_integrity_report_path": str(jit_report_path),
        "jit_integrity_report_sha256": _sha(jit_report_path.read_bytes()),
        "raw_tensor_module_sha256": module_sha,
        "numerical_source_sha256": numerical_source_sha,
    }
    contract_path = tmp_path / "reuse-contract.json"
    contract_raw = json.dumps(contract, sort_keys=True).encode()
    contract_path.write_bytes(contract_raw)
    target_root = source_target_root
    target_tensor = target_root / "tensor"
    target_carrier = target_root / "carrier"
    target_tensor.mkdir(parents=True)
    target_carrier.mkdir()
    for name in ("tmp", "xdg", "pycache", "mpl"):
        (target_root / name).mkdir()
    env = {
        cache_reuse.MODE_ENV: cache_reuse.MODE,
        cache_reuse.CONTRACT_ENV: str(contract_path),
        cache_reuse.CONTRACT_SHA_ENV: _sha(contract_raw),
        "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT": str(target_root),
    }
    for index in range(raw_count):
        key = f"key-{index}"
        folder = tensor_root / key
        folder.mkdir()
        (folder / "complete.json").write_text("{}\n", encoding="utf-8")
        (folder / "tensor.npy").write_bytes(b"tensor\n")
    return contract, env, module_path, source_root, target_root


def _fake_modules(source_root):
    calls = {"loads": 0, "computes": 0, "commits": 0}

    def load_shard(root, job):
        calls["loads"] += 1
        if job.get("miss"):
            return None
        return {
            "key": job["key"],
            "path": str(Path(root) / job["key"] / "tensor.npy"),
            "metadata": {},
        }

    def digest(path):
        return _sha(Path(path).read_bytes())

    def compute_one(*args, **kwargs):
        calls["computes"] += 1
        return {}

    def commit_shard(*args, **kwargs):
        calls["commits"] += 1

    parallel = SimpleNamespace(
        load_shard=load_shard,
        digest=digest,
        key_for=lambda job: job["key"],
        run_batch=lambda *args, **kwargs: {},
        compute_one=compute_one,
        commit_shard=commit_shard,
    )

    class CarrierCheckpoint:
        def __init__(self, root, context, **kwargs):
            self.context = context
            context_sha = _sha(
                json.dumps(context, sort_keys=True, separators=(",", ":")).encode()
            )
            self.root = Path(root) / "carrier-checkpoint-v2" / context_sha

        def load(self, index, mode):
            if mode.get("miss"):
                return None
            return {"index": index}

        def restore_prefix(self, modes):
            restored = []
            for index, mode in enumerate(modes):
                entry = self.load(index, mode)
                if entry is None:
                    break
                restored.append(entry)
            return restored

        def commit(self, *args, **kwargs):
            calls["commits"] += 1

    class GateCDRuntimeLease:
        def prepare_attempt_cache(self):
            return {
                "root": Path(self.cache_root),
                "xdg": Path(self.cache_root) / "xdg",
            }

    carrier = SimpleNamespace(CarrierCheckpoint=CarrierCheckpoint)
    return parallel, carrier, GateCDRuntimeLease, calls


def test_cache_only_guard_rejects_any_missing_raw_shard_without_compute(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_reuse, "EXPECTED_RAW_COUNT", 2)
    monkeypatch.setattr(cache_reuse, "EXPECTED_CARRIER_COUNT", 2)
    monkeypatch.setattr(cache_reuse, "EXPECTED_JIT_FILE_COUNT", 1)
    monkeypatch.setattr(cache_reuse, "EXPECTED_JIT_BYTES", len(b"compiled module identity\n"))
    contract, env, module_path, source_root, target_root = _fixture(
        tmp_path, raw_count=2, carrier_count=2
    )
    parallel, carrier, lease_class, calls = _fake_modules(source_root)
    cache_reuse.install(
        parallel_cache=parallel,
        carrier_module=carrier,
        lease_class=lease_class,
        environ=env,
    )
    jobs = [
        {"key": "key-0", "module_path": str(module_path), "module_sha256": contract["raw_tensor_module_sha256"]},
        {"key": "key-1", "module_path": str(module_path), "module_sha256": contract["raw_tensor_module_sha256"], "miss": True},
    ]
    progress = []
    with pytest.raises(RuntimeError, match="cache miss"):
        parallel.run_batch(jobs, target_root / "tensor", [0], progress=lambda *row: progress.append(row))
    assert calls["computes"] == 0
    assert calls["commits"] == 0
    assert len(progress) == 1
    assert progress[0][0:2] == (1, 2)
    assert not (source_root / "verified_cache_reuse.jsonl").exists()


def test_cache_only_guard_returns_hits_and_blocks_all_writers(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_reuse, "EXPECTED_RAW_COUNT", 2)
    monkeypatch.setattr(cache_reuse, "EXPECTED_CARRIER_COUNT", 2)
    monkeypatch.setattr(cache_reuse, "EXPECTED_JIT_FILE_COUNT", 1)
    monkeypatch.setattr(cache_reuse, "EXPECTED_JIT_BYTES", len(b"compiled module identity\n"))
    contract, env, module_path, source_root, target_root = _fixture(
        tmp_path, raw_count=2, carrier_count=2
    )
    parallel, carrier, lease_class, calls = _fake_modules(source_root)
    cache_reuse.install(
        parallel_cache=parallel,
        carrier_module=carrier,
        lease_class=lease_class,
        environ=env,
    )
    jobs = [
        {"key": f"key-{index}", "module_path": str(module_path), "module_sha256": contract["raw_tensor_module_sha256"]}
        for index in range(2)
    ]
    progress = []
    result = parallel.run_batch(
        jobs,
        target_root / "tensor",
        [0],
        progress=lambda *row: progress.append(row),
    )
    assert len(result) == 2
    assert all(item["cache_hit"] for item in result.values())
    assert len(progress) == 2
    with pytest.raises(RuntimeError, match="forbids raw tensor computation"):
        parallel.compute_one({}, target_root / "tensor", 0, 0, 0)
    with pytest.raises(RuntimeError, match="forbids raw tensor cache writes"):
        parallel.commit_shard(target_root / "tensor", jobs[0], None, {})

    checkpoint = carrier.CarrierCheckpoint(
        target_root / "carrier",
        {
            "numerical_source_sha256": contract["numerical_source_sha256"],
        },
    )
    assert len(checkpoint.restore_prefix([{}, {}])) == 2
    with pytest.raises(RuntimeError, match="forbids carrier checkpoint writes"):
        checkpoint.commit(0, {}, {}, 1.0)
    lease = lease_class()
    lease.scope = {
        "identity": {
            "profile_identity": cache_reuse.EXPECTED_PROFILE,
            "run_id": cache_reuse.EXPECTED_RUN_ID,
        },
        "attempt_id": contract["target_attempt_id"],
    }
    lease.cache_root = target_root
    lease.submission_mode = "runtime"
    created = lease.prepare_attempt_cache()
    target_jit = created["xdg"] / "fenics"
    assert (target_jit / "libffcx_forms_fixture.cpython-312-x86_64-linux-gnu.so").read_bytes() == module_path.read_bytes()
    assert target_jit.stat().st_mode & 0o777 == 0o700
    assert next(target_jit.iterdir()).stat().st_mode & 0o222 == 0
    (target_jit / "later-new-form.c").write_text("new attempt-only form\n")
    audit = (target_root / "verified_cache_reuse.jsonl").read_text().splitlines()
    assert len(audit) == 4
    assert json.loads(audit[0])["event"] == "python_startup_guard_installed"
    assert json.loads(audit[1])["computed"] == 0
    assert json.loads(audit[2])["restored_modes"] == 2
    assert json.loads(audit[3])["event"] == "jit_cache_materialized_read_only"
    assert calls["computes"] == 0
    assert calls["commits"] == 0


def test_python_child_loads_the_opt_in_sitecustomize_hook(tmp_path, monkeypatch):
    _fixture(tmp_path)
    contract_path = tmp_path / "reuse-contract.json"
    contract_raw = contract_path.read_bytes()
    env = os.environ.copy()
    env.pop(cache_reuse.MODE_ENV, None)
    env.pop(cache_reuse.CONTRACT_ENV, None)
    env.pop(cache_reuse.CONTRACT_SHA_ENV, None)
    repo = Path(__file__).resolve().parents[2]
    env.update(
        {
            cache_reuse.MODE_ENV: cache_reuse.MODE,
            cache_reuse.CONTRACT_ENV: str(contract_path),
            cache_reuse.CONTRACT_SHA_ENV: _sha(contract_raw),
            "PYTHONPATH": f"{repo / 'scripts'}:{repo}:{env.get('PYTHONPATH', '')}",
        }
    )
    code = (
        "import src.solvers.parallel_tensor_cache as c; "
        "import os; assert os.environ.get('TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE') == '1'; "
        "assert c.run_batch.__module__ == 'task40_exact_cache_reuse'; "
        "print(c.run_batch.__module__)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "task40_exact_cache_reuse"


def test_sitecustomize_exits_before_user_code_when_helper_import_fails(tmp_path):
    hook_dir = tmp_path / "hook-only"
    hook_dir.mkdir()
    source_hook = Path(__file__).resolve().parents[2] / "scripts" / "sitecustomize.py"
    (hook_dir / "sitecustomize.py").write_bytes(source_hook.read_bytes())
    env = os.environ.copy()
    env.update(
        {
            cache_reuse.MODE_ENV: cache_reuse.MODE,
            cache_reuse.CONTRACT_ENV: str(tmp_path / "unused-contract.json"),
            cache_reuse.CONTRACT_SHA_ENV: "0" * 64,
            "PYTHONPATH": str(hook_dir),
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "print('MAIN_SENTINEL_EXECUTED')"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "MAIN_SENTINEL_EXECUTED" not in result.stdout
    assert "Gate-CD exact-cache guard refused Python startup" in result.stderr


def test_sitecustomize_exits_before_user_code_when_contract_hash_is_wrong(tmp_path):
    _fixture(tmp_path)
    env = os.environ.copy()
    repo = Path(__file__).resolve().parents[2]
    env.update(
        {
            cache_reuse.MODE_ENV: cache_reuse.MODE,
            cache_reuse.CONTRACT_ENV: str(tmp_path / "reuse-contract.json"),
            cache_reuse.CONTRACT_SHA_ENV: "0" * 64,
            "PYTHONPATH": f"{repo / 'scripts'}:{repo}",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", "print('MAIN_SENTINEL_EXECUTED')"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert "MAIN_SENTINEL_EXECUTED" not in result.stdout
    assert "contract SHA256 mismatch" in result.stderr


def test_z10_prelu_compat_adapter_adds_only_verified_snapshot_identity(tmp_path):
    import builtins
    import types

    contract, env, _module_path, _source_root, target_root = _fixture(tmp_path)
    attempt_id = "gcdz10m8n2-20261105-r3"
    renamed_target = target_root.parent / f"task40_gate_cd_formal_attempt_{attempt_id}"
    target_root.rename(renamed_target)
    target_root = renamed_target
    contract["target_attempt_id"] = attempt_id
    contract["target_attempt_cache_root"] = str(target_root)
    # Use the production source digest, which is also part of the frozen cache identity.
    from src.runners.exact_cache_contract import numerical_source_digest

    contract["numerical_source_sha256"] = numerical_source_digest()
    env["TASK40_GATE_CD_ATTEMPT_CACHE_ROOT"] = str(target_root)
    source_commit = "c" * 40
    unit = "task40-gcd-m8n2-original.service"
    invocation_id = "d" * 32
    live_path = tmp_path / "original272-live.json"
    live = {
        "unit": unit,
        "unit_properties": {
            "InvocationID": invocation_id,
            "MainPID": "71",
            "ControlGroup": "/user.slice/app.slice/original.service",
        },
        "main_pid_identity": {
            "pid": 71,
            "start_ticks": 901,
            "cgroup_path": "/user.slice/app.slice/original.service",
        },
        "control_group_processes": [
            {
                "pid": 71,
                "start_ticks": 901,
                "cgroup_path": "/user.slice/app.slice/original.service",
            }
        ],
    }
    live_raw = json.dumps(live, sort_keys=True).encode()
    live_path.write_bytes(live_raw)
    scope_path = tmp_path / "scope.json"
    scope = {
        "attempt_id": attempt_id,
        "package_sha256": "b" * 64,
        "planned_systemd_user_unit": (
            f"task40-gcd-z10-m8n2-r3-{source_commit[:8]}.service"
        ),
        "z10_prelu_live_clearance": {
            "schema": "task40.gate_cd.z10_prelu_live_clearance_overlay.v1",
            "live_receipt_path": str(live_path),
            "live_receipt_sha256": _sha(live_raw),
        },
        "identity": {
            "profile_identity": cache_reuse.EXPECTED_PROFILE,
            "run_id": cache_reuse.EXPECTED_RUN_ID,
            "direct_route_contract": {
                "pre_lu_pause": {
                    "schema": "task40.gate_cd.z10_prelu_pause_contract.v1",
                    "release_requires_original272": {
                        "unit": unit,
                        "invocation_id": invocation_id,
                    },
                }
            },
        },
    }
    scope_raw = (json.dumps(scope, sort_keys=True, separators=(",", ":")) + "\n").encode()
    scope_path.write_bytes(scope_raw)
    env.update(
        {
            "TASK40_GATE_CD_SUBMISSION_MODE": "runtime",
            "TASK40_GATE_CD_ATTEMPT_ID": attempt_id,
            "TASK40_GATE_CD_EXPECTED_UNIT": (
                f"task40-gcd-z10-m8n2-r3-{source_commit[:8]}.service"
            ),
            "TASK40_GATE_CD_ORIGINAL272_UNIT": unit,
            "TASK40_GATE_CD_ORIGINAL272_INVOCATION_ID": invocation_id,
            "TASK40_GATE_CD_PACKAGE_SHA256": "b" * 64,
            "TASK40_GATE_CD_SCOPE_PATH": str(scope_path.resolve()),
            "TASK40_GATE_CD_SCOPE_SHA256": _sha(scope_raw),
        }
    )

    output_parent = tmp_path / "outputs"
    run_directory = output_parent / "run"
    run_directory.mkdir(parents=True)
    input_bytes = b"frozen z10 input snapshot\n"
    (run_directory / "input_original.dat").write_bytes(input_bytes)
    input_sha = _sha(input_bytes)
    physical_sha = "a" * 64
    (run_directory / "input_sha256.txt").write_text(input_sha + "\n")
    (run_directory / "physical_model_sha256.txt").write_text(physical_sha + "\n")
    (run_directory / "source_sha.txt").write_text(source_commit + "\n")
    payload = {
        "run_id": cache_reuse.EXPECTED_RUN_ID,
        "model_id": "gate_cd_0p7nm_mapped_50x50_zminus10_to240",
        "solver": {"native_capacity_profile": cache_reuse.EXPECTED_PROFILE},
        "provenance": {
            "expected_output_parent": str(output_parent.resolve()),
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
        },
    }
    resolved_raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    (run_directory / "resolved_config.json").write_bytes(resolved_raw)
    resolved_sha = _sha(resolved_raw)
    manifest = {
        "run_id": payload["run_id"],
        "model_id": payload["model_id"],
        "source_sha": source_commit,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "resolved_config_sha256": resolved_sha,
        "native_capacity_profile_identity": cache_reuse.EXPECTED_PROFILE,
        "output_directory": str(run_directory.resolve()),
    }
    (run_directory / "run_manifest.json").write_text(json.dumps(manifest) + "\n")

    from src.runners.exact_cache_contract import load_exact_cache_contract

    exact_contract_path = tmp_path / "exact-cache-contract.json"
    exact_contract = {
        "schema": "exact-cache-execution.v1",
        "source_sha": source_commit,
        "resolved_payload_sha256": hashlib.sha256(
            json.dumps(
                payload, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest(),
        "worker_cpus": [0],
        "tensor_root": str(target_root / "tensor"),
        "carrier_root": str(target_root / "carrier"),
    }
    exact_contract_raw = json.dumps(exact_contract, sort_keys=True).encode()
    exact_contract_path.write_bytes(exact_contract_raw)
    exact_contract_sha = _sha(exact_contract_raw)
    original_loaded_contract = load_exact_cache_contract(
        exact_contract_path,
        exact_contract_sha,
        source_sha=source_commit,
        resolved_payload=payload,
    )

    received = {}
    fake_module = types.ModuleType(cache_reuse.Z10_P6_MODULE)

    def fake_p6(resolved_payload, output_directory, *, source_sha):
        loaded_contract = load_exact_cache_contract(
            exact_contract_path,
            exact_contract_sha,
            source_sha=source_sha,
            resolved_payload=resolved_payload,
        )
        received["payload"] = resolved_payload
        received["source_sha"] = source_sha
        received["output_directory"] = output_directory
        received["loaded_contract"] = loaded_contract
        received["identity"] = resolved_payload.get("identity")
        return resolved_payload

    fake_module.run_p6_condensed_direct = fake_p6
    previous_module = sys.modules.get(cache_reuse.Z10_P6_MODULE)
    previous_import = builtins.__import__
    sentinel_was_set = getattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE, False)
    if hasattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE):
        delattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE)
    sys.modules[cache_reuse.Z10_P6_MODULE] = fake_module
    try:
        cache_reuse._install_z10_prelu_identity_adapter(contract, env)
        imported = builtins.__import__(
            cache_reuse.Z10_P6_MODULE,
            globals(),
            locals(),
            (cache_reuse.Z10_P6_FUNCTION,),
            0,
        )
        result = imported.run_p6_condensed_direct(
            payload, run_directory, source_sha=source_commit
        )
        expected_identity = {
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "resolved_config_sha256": resolved_sha,
        }
        assert result.get("identity") == expected_identity
        assert "identity" not in result
        assert "identity" not in payload
        assert received["payload"] is not payload
        assert received["source_sha"] == source_commit
        assert received["output_directory"] == run_directory
        assert received["identity"] == expected_identity
        assert received["loaded_contract"] == original_loaded_contract
        assert json.dumps(
            received["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
        ) == json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        evidence = json.loads(
            (run_directory / "z10_prelu_identity_compatibility.json").read_text()
        )
        assert evidence["package_sha256"] == "b" * 64
        assert evidence["scope_sha256"] == _sha(scope_raw)
        assert evidence["numerical_source_sha256"] == numerical_source_digest()

        scope_path.write_text("tampered\n")
        with pytest.raises(RuntimeError, match="scope hash changed"):
            cache_reuse._verified_z10_prelu_payload_identity(
                payload,
                run_directory,
                source_commit,
                contract=contract,
                environ=env,
            )
    finally:
        builtins.__import__ = previous_import
        if sentinel_was_set:
            setattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE, True)
        elif hasattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE):
            delattr(builtins, cache_reuse._Z10_IMPORT_GUARD_ATTRIBUTE)
        if previous_module is None:
            sys.modules.pop(cache_reuse.Z10_P6_MODULE, None)
        else:
            sys.modules[cache_reuse.Z10_P6_MODULE] = previous_module
