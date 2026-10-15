"""F5 P6 direct manifests must carry the worker's route contract."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from src.io.execution_plan import build_execution_plan
from src.io.input_validation import load_and_resolve
from src.io.run_specification import thaw
from src.runners.task038_input_worker import _load_and_validate_worker_payload
from src.runners.task038_launcher import _write_bootstrap

REPO = Path(__file__).resolve().parents[2]
INPUT = REPO / (
    "input/task39extra_para_workstation_capacity/"
    "v6_5nm_p6_condensed_direct_full600_y2.dat"
)


def test_f5_full600_direct_manifest_roundtrips_direct_route_contract(tmp_path):
    specification = load_and_resolve(INPUT)
    route = thaw(specification.derived["native_capacity_profile"])[
        "campaign_authorization"
    ]["direct_route"]
    plan = build_execution_plan(
        specification,
        tmp_path / "planned-run",
        source_sha="a" * 40,
        python_executable=REPO / ".venv/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
    )
    with TemporaryDirectory(dir=tmp_path) as temporary:
        run_directory = Path(temporary) / "run"
        run_directory.mkdir()
        test_specification = replace(
            specification,
            expected_output_parent=run_directory.parent,
        )
        manifest, resolved_sha = _write_bootstrap(
            test_specification,
            run_directory,
            source_sha="a" * 40,
            adapter_identity=plan.adapter_identity,
            start_time="2026-10-15T00:00:00Z",
        )
        assert manifest["native_capacity_contract"]["direct_route"] == route
        resolved, errors = _load_and_validate_worker_payload(
            resolved_config=run_directory / "resolved_config.json",
            manifest=run_directory / "run_manifest.json",
            expected_input_sha256=specification.input_sha256,
            expected_physical_model_sha256=specification.physical_model_sha256,
            expected_source_sha="a" * 40,
            expected_mpi_size=1,
            expected_method="full3d_direct",
            expected_adapter=plan.adapter_identity,
            expected_output_directory=run_directory,
            expected_resolved_config_sha256=resolved_sha,
            actual_mpi_size=1,
        )
        assert errors == []
        assert resolved is not None
