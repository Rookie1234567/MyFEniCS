from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(
    os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV") != "1",
    reason="native MPI identity regression requires the qualified complex activation",
)
def test_bootstrap_collects_native_identity_without_poisoning_parent_mpiexec(tmp_path):
    run_directory = tmp_path / "bootstrap"
    script = r"""
import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

from src.io import load_and_resolve
from src.runners.task038_launcher import _write_bootstrap

def native_mpi_environment():
    envp = ctypes.POINTER(ctypes.c_char_p).in_dll(ctypes.CDLL(None), "environ")
    result = {}
    index = 0
    while envp[index]:
        key, separator, value = envp[index].decode(errors="replace").partition("=")
        if separator and key.startswith(
            ("OMPI_", "PMI_", "PMIX_", "PRTE_", "ORTE_", "MPI_")
        ):
            result[key] = value
        index += 1
    return dict(sorted(result.items()))

root = Path.cwd()
os.environ["MYFENICS_TASK44_ROOT"] = str(root)
run_directory = Path(sys.argv[1])
run_directory.mkdir()
specification = load_and_resolve(
    root / "input/templates/full3d_layered_direct_example.dat"
)
before = native_mpi_environment()
manifest, _ = _write_bootstrap(
    specification,
    run_directory,
    source_sha="a" * 40,
    adapter_identity="task038.full3d_direct",
    start_time="2026-10-31T00:00:00+00:00",
)
after = native_mpi_environment()
launch = subprocess.run(
    ["/usr/bin/mpiexec", "-n", "1", "/bin/true"],
    capture_output=True,
    check=False,
    text=True,
)
print(json.dumps({
    "before": before,
    "after": after,
    "mpiexec_returncode": launch.returncode,
    "mpiexec_stdout": launch.stdout,
    "mpiexec_stderr": launch.stderr,
    "runtime_profile": manifest["environment"]["runtime_profile"],
    "mpi_size": manifest["environment"]["native_complex_identity"]["mpi_size"],
    "manifest_exists": (run_directory / "run_manifest.json").exists(),
}))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script, str(run_directory)],
        cwd=ROOT,
        env=os.environ.copy(),
        capture_output=True,
        check=False,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr or completed.stdout
    facts = json.loads(completed.stdout)
    assert facts["before"] == facts["after"]
    assert facts["mpiexec_returncode"] == 0, facts
    assert facts["runtime_profile"] == "native_linux_complex"
    assert facts["mpi_size"] == 1
    assert facts["manifest_exists"] is True
