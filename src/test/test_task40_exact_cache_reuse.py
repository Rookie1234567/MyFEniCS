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
