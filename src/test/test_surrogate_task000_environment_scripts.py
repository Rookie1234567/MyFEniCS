from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "scripts" / "install_local_wsl_environment.sh"
ACTIVATE = ROOT / "scripts" / "activate_myfenics_surrogate_wsl.sh"


def test_task000_environment_scripts_parse_as_bash() -> None:
    for script in (INSTALL, ACTIVATE):
        completed = subprocess.run(
            ["bash", "-n", str(script)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr


def test_install_script_pins_native_complex_abi_without_docker() -> None:
    text = INSTALL.read_text(encoding="utf-8")
    assert "python3-dolfinx-complex" in text
    assert "python3-pyvista" in text
    assert "1:0.10.0.post3-2~ppa2~noble7" in text
    assert "a444aa3006fdf492091443cc8c885c1eec006c2f" in text
    assert "--system" in text and "--user" in text
    assert "sudo apt" not in text
    assert "print $2; exit" not in text
    assert "docker run" not in text.lower()


def test_surrogate_activation_is_linux_local_and_single_solve() -> None:
    text = ACTIVATE.read_text(encoding="utf-8")
    assert "activate_myfenics_wsl.sh" in text
    assert "benchmarks/artifacts/task000/runtime" in text
    assert "MYFENICS_MAX_PARALLEL_FORWARD_SOLVES=1" in text
    assert "OMP_NUM_THREADS=1" in text
    assert "codex/only-one-13p5nm-surrogate-inversion" in text
    assert "/mnt/*" in text
