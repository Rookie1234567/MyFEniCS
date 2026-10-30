from __future__ import annotations

import hashlib
import os
import sys

import pytest

from scripts.task44_native_service import (
    _THREAD_VARIABLES,
    BRANCH,
    RUNTIME_PROBE_SCHEMA,
    _runtime_facts_digest,
    _validate_runtime_probe,
)


def _probe_document(tmp_path):
    input_path = tmp_path / "sample.dat"
    input_path.write_bytes(b"task44 sample input\n")
    source = {
        "branch": BRANCH,
        "source_sha": "a" * 40,
        "worktree_clean": True,
    }
    input_facts = {
        "path": str(input_path.resolve()),
        "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "model_id": "task44_sixlayer_0p7nm",
        "run_id": "sample_a",
        "layer_count": 6,
        "mpi_size": 1,
        "timeout_seconds": 0,
        "thread_controls": dict.fromkeys(_THREAD_VARIABLES, "1"),
    }
    environment = {
        "python_executable": os.path.abspath(sys.executable),
        "platform": "Linux-test",
        "qualified_activation": "MYFENICS_NATIVE_COMPLEX_ENV=1",
        "runtime_profile": "native_linux_complex",
        "native_complex_identity": {
            "activation_marker": "MYFENICS_NATIVE_COMPLEX_ENV=1",
            "task_root": str(tmp_path.resolve()),
            "petsc_scalar_type": "<class 'numpy.complex128'>",
            "petsc_int_type": "<class 'numpy.int32'>",
            "mpi_library_version": "Open MPI test",
            "mpi_size": 1,
            "module_paths": {
                "petsc4py": "/tmp/petsc4py/__init__.py",
                "slepc4py": "/tmp/slepc4py/__init__.py",
                "dolfinx": "/tmp/dolfinx/__init__.py",
                "basix": "/tmp/basix/__init__.py",
            },
        },
    }
    document = {
        "schema": RUNTIME_PROBE_SCHEMA,
        "source": source,
        "input": input_facts,
        "environment": environment,
    }
    document["facts_sha256"] = _runtime_facts_digest(source, input_facts, environment)
    return document, input_path, source


def test_isolated_runtime_facts_are_bound_to_source_input_and_environment(tmp_path):
    document, input_path, source = _probe_document(tmp_path)

    facts = _validate_runtime_probe(
        document,
        repo_root=tmp_path,
        input_path=input_path,
        expected_source=source,
    )

    assert facts[0] == source
    assert facts[1]["sha256"] == document["input"]["sha256"]
    assert facts[2]["runtime_profile"] == "native_linux_complex"


def test_isolated_runtime_probe_rejects_changed_input_even_with_updated_digest(tmp_path):
    document, input_path, source = _probe_document(tmp_path)
    document["input"]["sha256"] = "b" * 64
    document["facts_sha256"] = _runtime_facts_digest(
        document["source"], document["input"], document["environment"]
    )

    with pytest.raises(RuntimeError, match="input binding failed"):
        _validate_runtime_probe(
            document,
            repo_root=tmp_path,
            input_path=input_path,
            expected_source=source,
        )


def test_isolated_runtime_probe_rejects_mpi_or_abi_mismatch_even_with_updated_digest(tmp_path):
    document, input_path, source = _probe_document(tmp_path)
    document["environment"]["native_complex_identity"]["mpi_size"] = 2
    document["facts_sha256"] = _runtime_facts_digest(
        document["source"], document["input"], document["environment"]
    )

    with pytest.raises(RuntimeError, match="native environment gate failed"):
        _validate_runtime_probe(
            document,
            repo_root=tmp_path,
            input_path=input_path,
            expected_source=source,
        )
