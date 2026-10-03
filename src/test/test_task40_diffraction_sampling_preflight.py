import builtins
from pathlib import Path
import subprocess
import sys

import pytest

from src.io import load_and_resolve
from src.io.input_loader import InputError
from src.io.input_validation import _build_3d_config


ROOT = Path(__file__).resolve().parents[2]
TASK_INPUTS = ROOT / "input/task40extra_0p7nm_engineering"
E2 = TASK_INPUTS / "nonseparable_e2_p6_q4_manual_m2_growth.dat"


def test_e2_catalog_sampling_fails_during_input_resolution(tmp_path: Path) -> None:
    text = E2.read_text(encoding="utf-8")
    assert text.count("diffraction_sample_count_x = 25") == 1
    invalid = tmp_path / "e2_sampling_too_small.dat"
    invalid.write_text(
        text.replace("diffraction_sample_count_x = 25", "diffraction_sample_count_x = 24"),
        encoding="utf-8",
    )

    with pytest.raises(InputError, match=r"need at least 25 x 7"):
        load_and_resolve(invalid)


def test_e2_corrected_grid_and_existing_g0_g1_m2_inputs_resolve() -> None:
    e2 = load_and_resolve(E2)
    assert e2.output["diffraction_sample_count_x"] == 25
    assert e2.output["diffraction_sample_count_y"] == 24
    assert e2.physical_model_sha256 == (
        "48814d5fe34ab0e73de345c2d98661a96ef93ebb9690be738d040edac7cd84a7"
    )

    for name in (
        "nonseparable_g0_p6_q4_manual_m2_f3.dat",
        "nonseparable_g1_p6_q4_manual_m2_f5.dat",
    ):
        load_and_resolve(TASK_INPUTS / name)


def test_catalog_gate_is_skipped_when_diffraction_export_is_disabled() -> None:
    normalized = load_and_resolve(E2).as_jsonable()
    normalized["output"]["export_diffraction_orders"] = False
    normalized["output"]["diffraction_sample_count_x"] = 1

    _build_3d_config(normalized)


def test_generic_full3d_profile_does_not_import_diffraction_postprocessor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_import = builtins.__import__

    def reject_diffraction_import(name: str, *args, **kwargs):
        if name == "src.postprocessing.diffraction_3d":
            raise AssertionError("generic Full3D validation imported a FE postprocessor")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_diffraction_import)
    specification = load_and_resolve(ROOT / "input/templates/full3d_iterative_example.dat")
    assert specification.solver["preconditioner"] == "full3d_scalable_v1"
    assert specification.output["export_diffraction_orders"] is True


def test_task40_cross_inputs_leave_supervisor_free_of_mpi_children() -> None:
    code = """
import os
import sys
from pathlib import Path
from src.io import load_and_resolve
from src.runners import task038_launcher
root = Path.cwd()
for name in (
    "nonseparable_gx560_p6_q4_manual_m2_v3.dat",
    "nonseparable_gz528_p6_q4_manual_m2_v3.dat",
    "nonseparable_gx784_p6_q4_review_v5.dat",
):
    spec = load_and_resolve(root / "input/task40extra_0p7nm_engineering" / name)
    assert spec.output["export_diffraction_orders"] is True
    assert "dolfinx" not in sys.modules
    assert "mpi4py.MPI" not in sys.modules
    assert "petsc4py.PETSc" not in sys.modules
    for path in Path(f"/proc/{os.getpid()}/task").glob("*/children"):
        assert not path.read_text().strip(), path.read_text()
"""
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=ROOT, text=True, capture_output=True
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
