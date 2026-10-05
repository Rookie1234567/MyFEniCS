"""V29 stages in the existing durable receiver, no second solver or launcher."""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

INSTANCE = "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"

PACKAGE_LOADER = '''"""Relative opt-in provider; --inspect checks saved identity, not new FE."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parent

def verify(require_ready=True):
    manifest_path=ROOT/'package_manifest.json'
    value=json.loads(manifest_path.read_text())
    if value['instance_id']!='W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28' or value['numerical_API_commit']!='c354afa449fb80cfb5012e7d2ff66a3e3e64e088':
        raise ValueError('PACKAGE_INSTANCE_AND_API_IDENTITY')
    if hashlib.sha256((ROOT/'input/mode_manifest.json').read_bytes()).hexdigest()!='7dd07d7145c70759f53465b6ec11237a89effdf7d68a0df6423768858639c56e':
        raise ValueError('PACKAGE_QUALIFIED_MODE_IDENTITY')
    if require_ready:
        ready=json.loads((ROOT/'READY_FOR_MAIN_OPT_IN_NOT_REMOTE_INGESTED.json').read_text())
        if ready['package_manifest_sha256']!=hashlib.sha256(manifest_path.read_bytes()).hexdigest():
            raise ValueError('PACKAGE_READY_IDENTITY')
    for row in value['files']:
        path=(ROOT/row['path']).resolve()
        if not path.is_relative_to(ROOT) or path.stat().st_size!=row['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('PACKAGE_FILE_IDENTITY:'+row['path'])
    for p in (4,6):
        result=json.loads((ROOT/('p'+str(p))/('check_p'+str(p)+'.json')).read_text())
        if not result['passed'] or result['failed_metrics'] or result['rows']!=4*p*p*272*4 or result['mode_count']!=32060:
            raise ValueError('PACKAGE_COMPLETE_CHECK_REQUIRED')
    return value

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

def provider(degree):
    """Receiver's existing qualified native ABI, explicit same-instance only.

    Construct the three original classes and return the thin provider. Calling
    its methods is the receiver's own authorization/cost, never done by inspect.
    """
    verify()
    if degree not in (4,6):raise ValueError('FIXED_P4_P6_SCOPE')
    import basix
    core=module('_frozen_main',ROOT/'code/directional_boundary.py')
    adapter=module('_thin_adapter',ROOT/'code/w1_full_surface_action.py')
    with np.load(ROOT/('p'+str(degree))/'layout.npz',allow_pickle=False) as raw:
        data={k:raw[k] for k in raw.files}
    element=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,degree,basix.LagrangeVariant.legendre)
    poly=core.FacetPolynomial(element)
    for side in ('bottom','top'):
        if not np.array_equal(poly.coefficients[side],data[side+'_coeff']):
            raise ValueError('RECEIVER_NATIVE_BASIS_CHANGED')
    layout=core.BoundaryLayout(data['x'],data['y'],poly,data['phases'])
    modes=json.loads((ROOT/'input/mode_manifest.json').read_text())['modes']
    return adapter.FullSurfaceAdapter(layout,modes,action_class=core.DirectionalBoundaryAction)

if __name__=='__main__':
    if sys.argv[1:]!=['--inspect']:raise SystemExit('Use --inspect; import provider for qualified explicit opt-in')
    value=verify()
    print(json.dumps(dict(status='MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED',files=len(value['files']),instance_id=value['instance_id'])))
'''


def prerequisite_surface(spec, files):
    from src.io.w1_versioned_input import validate_inputs
    from src.io.w1_evidence import scientific_identity, validate_stage

    if validate_inputs(spec).get("received") is not True:
        raise ValueError("W29_ACCEPTED_VERSIONED_INPUT_REQUIRED")
    index = Path(spec["v28_reference_root"]) / "chunk_index.json"
    if (
        __import__("hashlib").sha256(index.read_bytes()).hexdigest()
        != "9ed0ca56cc66fe6690a2786ad520dc3c049c5bfd5704fc0d686dad7ce560248f"
    ):
        raise ValueError("W29_REVIEWED_V28_REFERENCE_INDEX_CHANGED")
    required = {
        "input_contract_checks": [],
        "surface_p4": [],
        "surface_p6": [],
        "surface_check": ["surface_p4", "surface_p6"],
        "surface_handoff": ["surface_check"],
    }[spec["stage"]]
    statuses = {
        "surface_p4": {"FULL_SURFACE_COMPLETE_PENDING_INDEPENDENT_CHECK"},
        "surface_p6": {"FULL_SURFACE_COMPLETE_PENDING_INDEPENDENT_CHECK"},
        "surface_check": {"ORIGINAL_SIZE_FULL_SURFACE_ACTION_EMPIRICAL_PASS"},
    }
    for stage in required:
        directory = Path(spec["prerequisite_paths"][stage])
        binding = json.loads((directory / "binding.json").read_text())
        for key in (
            "instance_id",
            "input_origin",
            "manifest_path",
            "ledger_path",
            "physical_config_path",
            "math_commit",
            "quadrature_degree",
            "integration_profile",
            "surface_scope",
            "generic_seed",
            "seam_seed",
            "v28_reference_root",
        ):
            if binding["contract"][key] != spec[key]:
                raise ValueError("W29_UPSTREAM_INSTANCE_SCOPE_MISMATCH:" + key)
        if (
            binding["window_sha256"]
            != __import__("hashlib")
            .sha256(Path(spec["window_path"]).read_bytes())
            .hexdigest()
        ):
            raise ValueError("W29_UPSTREAM_WINDOW_MISMATCH")
        result = validate_stage(
            directory,
            identity=scientific_identity(binding),
            statuses=statuses[stage],
            expected_stage=stage,
        )
        if stage == "surface_check" and (
            result.get("passed") is not True or result.get("failed_metrics") != 0
        ):
            raise ValueError("W29_COMPLETE_NUMERIC_CHECK_REQUIRED")


def commit_surface(run, spec, result, files):
    from src.io.finite_json import atomic_json
    from src.io.w1_evidence import file_receipt, scientific_identity, validate_stage
    from src.io.w1_versioned_input import digest, ROOT

    run = Path(run)
    binding = json.loads((run / "binding.json").read_text())
    component = json.loads((run / "component_result.json").read_text())
    validate_stage(
        run,
        identity=scientific_identity(binding),
        statuses={component["status"]},
        expected_stage=spec["stage"],
    )
    freshness = json.loads((run / "worker_start_freshness.json").read_text())
    if (
        freshness.get("passed") is not True
        or not 0 <= freshness.get("age_seconds", 16) <= 15
    ):
        raise ValueError("W29_CANNOT_COMMIT_STALE_START")
    if (
        spec["stage"] == "input_contract_checks"
        and component.get("status") == "V29_SURFACE_CONTRACT_TESTS_PASS"
    ):
        atomic_json(
            spec["A_qualification_path"],
            dict(
                schema="w1-P0-delta-qualification.v29",
                scope="PURE_FULL_SURFACE_STARTUP_DELTA",
                receiver_files={p: digest(ROOT / p) for p in files},
                source_sha=binding["receiver_source_sha"],
                junit=file_receipt(run / "junit.xml"),
                supervision=file_receipt(run / "supervisor_summary.json"),
                test_source_files=[
                    file_receipt(ROOT / "src/test/test_w1_surface.py"),
                    file_receipt(ROOT / "src/test/test_w1_versioned_input.py"),
                ],
                inherited_scientific_input="V28 accepted; validated receipt unchanged; no repeated producer or mode checker",
                startup_freshness=file_receipt(run / "worker_start_freshness.json"),
            ),
        )
    elif (
        spec["stage"] == "surface_handoff"
        and component["status"] == "FULL_SURFACE_HANDOFF_PENDING_SUPERVISION"
    ):
        destination = Path(component["bundle_directory"])
        manifest = destination / "package_manifest.json"
        if digest(manifest) != component["package_manifest"]["sha256"]:
            raise ValueError("W29_HANDOFF_REOPEN_HASH")
        atomic_json(
            destination / "READY_FOR_MAIN_OPT_IN_NOT_REMOTE_INGESTED.json",
            dict(
                instance_id=INSTANCE,
                status="MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED",
                package_manifest_sha256=digest(manifest),
                consumer_cleared=True,
                evidence_sha256=digest(run / "evidence.json"),
                start_freshness_qualified=True,
            ),
        )
        import importlib.util

        loader = importlib.util.spec_from_file_location(
            "_w29_ready_reopen", destination / "consumer.py"
        )
        opened = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(opened)
        verified = opened.verify()
        atomic_json(
            run / "ready_consumer_reopen.json",
            dict(
                actual_ready_path_consumed=True,
                relative_package_manifest_sha256=digest(manifest),
                files=len(verified["files"]),
                instance_id=INSTANCE,
                new_numerical_lifecycle=False,
                physical_scope="surface API only; receiver volume/internal binding remains separate",
            ),
        )


def run_surface_payload(root, snapshot, binding, helpers):
    contract = helpers.load_file(
        "_w29_contract", root / "src/io/w1_receiver_contract.py"
    )
    for path, expected in binding["receiver_files"].items():
        if contract.digest(root / path) != expected:
            raise ValueError("W29_PAYLOAD_SOURCE_CHANGED:" + path)
    run = Path(binding["run_path"])
    stage = binding["stage"]
    spec = binding["spec"]
    began = time.monotonic()
    helpers.guard(binding)
    if stage == "input_contract_checks":
        target = root / "src/test/test_w1_surface.py"
        old = root / "src/test/test_w1_versioned_input.py"
        files = [str(root / p) for p in binding["receiver_files"] if p.endswith(".py")]
        # Legacy receiver files are bound for provenance; only this batch's
        # actual changes are linted. No historical full suite or reformat.
        changed = [
            str(root / p)
            for p in (
                "src/io/w1_evidence.py",
                "src/io/w1_versioned_input.py",
                "src/io/w1_surface_contract.py",
                "src/runners/w1_admission_budget.py",
                "src/runners/w1_admission_scope.py",
                "src/runners/w1_component_payload.py",
                "src/runners/w1_component_receiver.py",
                "src/runners/w1_start_freshness.py",
                "src/runners/w1_surface_payload.py",
                "src/solvers/w1_full_surface_action.py",
                "src/solvers/w1_full_surface_saved.py",
                "src/test/test_w1_surface.py",
            )
        ]
        lint = subprocess.run(
            [sys.executable, "-m", "ruff", "check", *changed], cwd=root, check=False
        )
        compile_check = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", *files], cwd=root, check=False
        )
        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(target),
            str(old) + "::test_schema2_is_explicit_and_schema1_strict",
            str(old) + "::test_batch_window_no_reset_and_caps",
            "--junitxml=" + str(run / "junit.xml"),
        ]
        completed = subprocess.run(command, cwd=root, check=False)
        result = dict(
            status="V29_SURFACE_CONTRACT_TESTS_PASS"
            if completed.returncode == 0
            and lint.returncode == 0
            and compile_check.returncode == 0
            else "V29_SURFACE_CONTRACT_TESTS_FAIL",
            pytest_exit_code=completed.returncode,
            ruff_exit_code=lint.returncode,
            compileall_exit_code=compile_check.returncode,
            raw=helpers.file_receipt(run / "junit.xml"),
            scope="PURE_STARTUP_AND_ADAPTER_LOGIC_ONLY",
        )
    elif stage in {"surface_p4", "surface_p6"}:
        contract.require_same_binding(binding, spec, consumer=stage)
        contract, component = helpers.source_modules(root, snapshot, binding)
        helpers.atomic_json(run / "runtime.json", helpers.numeric_runtime())
        core = helpers.load_file(
            "_w29_full_surface", root / "src/solvers/w1_full_surface_action.py"
        )
        result = core.produce(root, snapshot, binding, run, helpers, component)
        result.update(
            raw_runtime=helpers.file_receipt(run / "runtime.json"),
            raw_abi=helpers.file_receipt(run / "abi_receipt.json"),
            raw_overlay=helpers.file_receipt(run / "math_export_overlay.json"),
        )
    elif stage == "surface_check":
        checker = helpers.load_file(
            "_w29_full_surface_saved", root / "src/solvers/w1_full_surface_saved.py"
        )
        modes = json.loads(Path(spec["manifest_path"]).read_text())["modes"]
        reports = []
        for p in (4, 6):
            producer = Path(spec["prerequisite_paths"]["surface_p" + str(p)])
            report = checker.check_surface(
                producer,
                modes,
                run / ("metrics_p" + str(p) + ".csv"),
                lambda a, p=p: helpers.atomic_arrays(
                    run / ("independent_reference_p" + str(p) + ".npz"), a
                ),
                guard=lambda: helpers.guard(binding),
            )
            helpers.atomic_json(run / ("check_p" + str(p) + ".json"), report)
            report["raw_metrics"] = helpers.file_receipt(
                run / ("metrics_p" + str(p) + ".csv")
            )
            report["raw_reference"] = helpers.file_receipt(
                run / ("independent_reference_p" + str(p) + ".npz")
            )
            reports.append(report)
        passed = all(r["passed"] for r in reports)
        result = dict(
            status="ORIGINAL_SIZE_FULL_SURFACE_ACTION_EMPIRICAL_PASS"
            if passed
            else "FULL_SURFACE_NUMERICAL_FAILED",
            passed=passed,
            failed_metrics=sum(r["failed_metrics"] for r in reports),
            reports=reports,
            raw_reports=[
                helpers.file_receipt(run / ("check_p" + str(p) + ".json"))
                for p in (4, 6)
            ],
            checker_new_factor_solve_FE_NN_calls=0,
            main_API_used_to_generate_reference=False,
        )
    elif stage == "surface_handoff":
        # P1 already made actual calls to all three frozen main classes. Bind
        # those calls to independently qualified complete output, without a
        # third numerical lifecycle or another 1.6 GB portable package copy.
        bundle = run / "main_opt_in_bundle"
        bundle.mkdir(exist_ok=False)
        copied = []
        for prefix, path in [
            ("input/mode_manifest.json", Path(spec["manifest_path"])),
            ("input/resolved_config.json", Path(spec["physical_config_path"])),
        ]:
            destination = bundle / prefix
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(destination)
        for p in (4, 6):
            producer = Path(spec["prerequisite_paths"]["surface_p" + str(p)])
            check = Path(spec["prerequisite_paths"]["surface_check"])
            api = json.loads((producer / "main_api_call.json").read_text())
            if (
                api["face_inventory"] is not None
                or api["actual_facets"] != 2176
                or api["actual_modes"] != 32060
                or api["native_classes"]
                != ["FacetPolynomial", "BoundaryLayout", "DirectionalBoundaryAction"]
            ):
                raise ValueError("W29_ACTUAL_MAIN_API_CALL_REQUIRED")
            index = json.loads((producer / "surface_index.json").read_text())
            for path in [
                *[producer / row["path"] for row in index["arrays"].values()],
                producer / "surface_index.json",
                producer / "binding.json",
                check / ("check_p" + str(p) + ".json"),
                check / ("independent_reference_p" + str(p) + ".npz"),
            ]:
                destination = bundle / ("p" + str(p)) / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
                copied.append(destination)
        for path in [
            root / "src/solvers/w1_full_surface_action.py",
            root / "src/solvers/w1_full_surface_saved.py",
            snapshot / "src/solvers/directional_boundary.py",
        ]:
            destination = bundle / "code" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(destination)
        loader = bundle / "consumer.py"
        loader.write_text(PACKAGE_LOADER)
        copied.append(loader)
        dat_paths = {Path(spec["path"])}
        qualification=json.loads(Path(spec["A_qualification_path"]).read_text())
        p0_run=Path(qualification["supervision"]["path"]).parent
        for directory in [p0_run, *[Path(spec["prerequisite_paths"][s]) for s in ("surface_p4","surface_p6","surface_check")]]:
            stage_binding=json.loads((directory/"binding.json").read_text())
            dat_paths.add(Path(stage_binding["spec"]["path"]))
        for path in sorted(dat_paths):
            destination = bundle / "provenance" / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
            copied.append(destination)
        rows = []
        for path in copied:
            row = helpers.file_receipt(path)
            row["path"] = str(path.relative_to(bundle))
            rows.append(row)
        manifest = bundle / "package_manifest.json"
        helpers.atomic_json(
            manifest,
            dict(
                schema="w1-main-api-full-surface-package.v29",
                instance_id=INSTANCE,
                scope="2176 complete facets; p4/p6 32060 modes; no volume or remote ingestion",
                files=rows,
                numerical_API_commit=contract.MATH_COMMIT,
                receiver_source=binding["receiver_source_sha"],
                use="Explicit opt-in, same complete instance only; receiver supplies qualified existing native ABI",
                live_relative_dependencies=True,
                historical_absolute_paths_provenance_only=True,
            ),
        )
        # Same process reads the actual standalone relative-path loader after
        # writing all bytes. Ready is intentionally absent until supervision
        # has ended and the parent independently reopens and seals the stage.
        consumer = helpers.load_file("_w29_package_consumer", loader)
        consumer.verify(require_ready=False)
        result = dict(
            status="FULL_SURFACE_HANDOFF_PENDING_SUPERVISION",
            bundle_directory=str(bundle),
            package_manifest=helpers.file_receipt(manifest),
            raw_files=[helpers.file_receipt(p) for p in copied],
            copied_files=len(rows),
            package_bytes=sum(r["bytes"] for r in rows),
            actual_main_api_local_consumption=True,
            remote_main_ingested=False,
            pending_status="MAIN_API_ADAPTER_LOCAL_PASS_NOT_REMOTE_INGESTED",
            healthy_V28_package_not_copied=True,
        )
    else:
        raise ValueError("W29_IMPLEMENTED_STAGE_REQUIRED")
    result.update(
        receiver_source_sha=binding["receiver_source_sha"],
        binding_sha256=contract.digest(run / "binding.json"),
        elapsed_seconds=time.monotonic() - began,
        instance_id=INSTANCE,
        input_origin=spec["input_origin"],
        integration_profile=spec["integration_profile"],
        math_commit=contract.MATH_COMMIT,
        NN_used=False,
        PDE_solved=False,
        official_results=False,
        full_target_qualified=False,
        raw_start_freshness=helpers.file_receipt(run / "worker_start_freshness.json"),
    )
    helpers.atomic_json(run / "component_result.json", result)
    print(
        json.dumps(
            {k: result[k] for k in ("status", "elapsed_seconds", "receiver_source_sha")}
        ),
        flush=True,
    )
    return 0
