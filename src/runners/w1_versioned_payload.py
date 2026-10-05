"""Opt-in versioned W1 orchestration; numerical kernels remain in solvers.

Pure scientific input/checker/consumer stages never import the frozen FE stack.
No global FE solve, Gram, neural forward, or historical generation is present.
"""

import csv
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
INSTANCE = "W1_0P7_FULL_32060_NATIVE_V27_REQUALIFIED_V28"


def _protected_ast(source, excluded):
    import ast

    tree = ast.parse(source)
    tree.body = [
        node
        for node in tree.body
        if not (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in excluded
        )
    ]
    return ast.dump(tree, include_attributes=False)


def _compatible_prior_control_source(binding, current_files, *, prior_role="control"):
    """Reuse B0 only when every dependency outside boundary/checker repairs is unchanged.

    Old bytes must match their actual Git blob.  The excluded functions never
    execute in B0; control_layout, run_payload, supervisor, contracts and all
    numerical control dependencies remain protected.  Current pure qualification
    is separately required by the launcher.  This is not a generic source bypass.
    """
    import re

    source = binding["receiver_source_sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ValueError("W28_CONTROL_SOURCE_SHA")
    exclusions = {
        "src/runners/w1_component_payload.py": {"layout_for"},
        "src/solvers/w1_saved_boundary.py": {"check_saved"},
        "src/runners/w1_versioned_payload.py": {
            "prerequisite_v28",
            "_protected_ast",
            "_compatible_prior_control_source",
            "qualify_moments",
            "boundary_v28",
            "validate_boundary_summary",
        },
    }
    exclusions["src/runners/w1_admission_budget.py"] = {"update_budget", "admit"}
    if prior_role != "control":
        if prior_role != "boundary_check":
            raise ValueError("W28_SOURCE_REUSE_ROLE")
        exclusions = {
            "src/runners/w1_admission_budget.py": {"update_budget", "admit"},
            "src/runners/w1_versioned_payload.py": {
                "prerequisite_v28",
                "_compatible_prior_control_source",
            },
        }
    old_files = binding["receiver_files"]
    if old_files.keys() != current_files.keys():
        raise ValueError("W28_CONTROL_DEPENDENCY_SET")
    changed = []
    for path, old_hash in old_files.items():
        if old_hash == current_files[path]:
            continue
        if path not in exclusions:
            raise ValueError("W28_CONTROL_PROTECTED_SOURCE:" + path)
        old = subprocess.run(
            ["git", "show", source + ":" + path],
            cwd=ROOT,
            check=True,
            capture_output=True,
            timeout=30,
        ).stdout
        new = (ROOT / path).read_bytes()
        if hashlib.sha256(old).hexdigest() != old_hash or (
            hashlib.sha256(new).hexdigest() != current_files[path]
        ):
            raise ValueError("W28_CONTROL_GIT_OR_CURRENT_HASH:" + path)
        if _protected_ast(old, exclusions[path]) != _protected_ast(
            new, exclusions[path]
        ):
            raise ValueError("W28_CONTROL_UNTESTED_DEPENDENCY_CHANGE:" + path)
        changed.append(path)
    return dict(
        previous_source=source,
        preserved_control_dependencies=True,
        boundary_only_changed_files=changed,
    )


def prerequisite_v28(stage, spec, receiver_files):
    from src.io.w1_evidence import scientific_identity, validate_stage
    from src.io.w1_versioned_input import CONTRACT_KEYS, digest, validate_inputs

    if stage == "input_contract_checks":
        return
    previous = spec["prerequisite_paths"]
    required = {
        "manifest_qualify": ["input_contract_checks"],
        "control": [],
        "boundary": ["control"],
        "boundary_check": ["boundary"],
        "bundle_consume": ["boundary_check"],
    }[stage]
    if stage not in {"manifest_qualify"} and not validate_inputs(spec)["received"]:
        raise ValueError("W28_SCIENTIFIC_INPUT_REQUIRED")
    statuses = {
        "input_contract_checks": {"V28_INPUT_CONTRACT_TESTS_PASS"},
        "control": {"CONTROL_NATIVE_BOUNDARY_PASS_NO_VOLUME_FE"},
        "boundary": {"BOUNDARY_COMPLETE_PENDING_SAVED_CHECKER"},
        "boundary_check": {"W1_REPRESENTATIVE_FACETS_FULL_MODE_EMPIRICAL_PASS"},
    }
    for name in required:
        run = Path(previous[name])
        binding = json.loads((run / "binding.json").read_text())
        for key in CONTRACT_KEYS:
            if key in {"input_sha256", "output_root", "integration_profile"}:
                continue
            if binding["contract"][key] != spec[key]:
                raise ValueError("W28_PREREQUISITE_INSTANCE_OR_INPUT:" + key)
        current_files = {p: digest(ROOT / p) for p in receiver_files}
        if binding["receiver_files"] != current_files:
            if name not in {"control", "boundary_check"}:
                raise ValueError("W28_PREREQUISITE_SOURCE")
            _compatible_prior_control_source(binding, current_files, prior_role=name)
        if binding["window_sha256"] != digest(spec["window_path"]):
            raise ValueError("W28_PREREQUISITE_WINDOW")
        if (
            name not in {"control", "input_contract_checks"}
            and binding["contract"]["integration_profile"]
            != spec["integration_profile"]
        ):
            raise ValueError("W28_PREREQUISITE_PROFILE")
        result = validate_stage(
            run,
            identity=scientific_identity(binding),
            statuses=statuses[name],
            expected_stage=name,
        )
        if name == "control" and result.get("native_control_complete") is not True:
            raise ValueError("W28_NATIVE_CONTROL_REQUIRED")
        if name == "control":
            from src.solvers.w1_saved_boundary import validate_native_control_saved

            validate_native_control_saved(run)
        if name == "boundary_check":
            validate_boundary_summary(result)


def validate_boundary_summary(value):
    import math

    if (
        value.get("coverage") != {"4": 32060, "6": 32060}
        or value.get("coverage_complete") is not True
        or value.get("failed_metric_count") != 0
        or value.get("physical_incident_rhs_qualified") is not True
        or value.get("coordinate_physics_qualified") is not True
        or not math.isfinite(value.get("maximum_original_relative", float("inf")))
        or value["maximum_original_relative"] > 1e-10
        or not math.isfinite(value.get("oracle_maximum_absolute", float("inf")))
        or value["oracle_maximum_absolute"] > 1e-12
        or not math.isfinite(
            value.get("one_dimensional_moment_maximum_absolute", float("inf"))
        )
        or value["one_dimensional_moment_maximum_absolute"] > 1e-12
        or value.get("one_dimensional_moment_failed_count") != 0
        or not value.get("maximum_by_field")
    ):
        raise ValueError("W28_FULL_NUMERIC_GATE_REQUIRED")
    if any(
        not math.isfinite(v["relative"]) or v["relative"] > 1e-10
        for v in value["maximum_by_field"].values()
    ):
        raise ValueError("W28_SAVED_FIELD_GATE")


def commit_stage(run, spec, result, receiver_files):
    from src.io.finite_json import atomic_json
    from src.io.w1_evidence import file_receipt, scientific_identity, validate_stage
    from src.io.w1_versioned_input import digest, publish_qualified_inputs

    run = Path(run)
    binding = json.loads((run / "binding.json").read_text())
    component = json.loads((run / "component_result.json").read_text())
    validate_stage(
        run,
        identity=scientific_identity(binding),
        statuses={component["status"]},
        expected_stage=spec["stage"],
    )
    if (
        spec["stage"] == "input_contract_checks"
        and component["status"] == "V28_INPUT_CONTRACT_TESTS_PASS"
    ):
        inherited = ROOT / "tmp/task42extra/w1_receiver/v27/P0_qualification.json"
        old = json.loads(inherited.read_text())
        value = dict(
            schema="w1-P0-delta-qualification.v28",
            scope="PURE_LOGIC_DELTA_ONLY",
            receiver_files={p: digest(ROOT / p) for p in receiver_files},
            inherited_qualification=file_receipt(inherited),
            changed_receiver_files={
                p: digest(ROOT / p)
                for p in receiver_files
                if old["receiver_files"].get(p) != digest(ROOT / p)
            },
            junit=file_receipt(run / "junit.xml"),
            supervision=file_receipt(run / "supervisor_summary.json"),
            test_source_files=[
                file_receipt(ROOT / "src/test/test_w1_versioned_input.py")
            ],
            scientific_scope="PURE_LOGIC_ONLY_NOT_FE_QUALIFICATION",
            source_sha=binding["receiver_source_sha"],
        )
        atomic_json(spec["A_qualification_path"], value)
    elif spec["stage"] == "manifest_qualify":
        publish_qualified_inputs(run, spec, atomic_json)
    elif (
        spec["stage"] == "bundle_consume"
        and component["status"] == "LOCAL_RELOCATED_CONSUMER_PASS"
    ):
        # Final ready marker follows numeric qualification AND successful cleared supervision.
        marker = (
            Path(component["bundle_directory"])
            / "READY_FOR_MAIN_OPT_IN_NOT_INGESTED.json"
        )
        atomic_json(
            marker,
            dict(
                status="READY_FOR_MAIN_OPT_IN_NOT_INGESTED",
                instance_id=INSTANCE,
                component_sha256=digest(run / "component_result.json"),
                evidence_sha256=digest(run / "evidence.json"),
                receiver_sha256=digest(run / "receiver_result.json"),
                package_manifest_sha256=component["package_manifest_sha256"],
                consumer_cleared=True,
            ),
        )
        from shutil import copyfile

        copyfile(marker, Path(component["relocated_directory"]) / marker.name)


def relative_receipt(path, parent, helpers):
    value = helpers.file_receipt(path)
    value["path"] = str(Path(path).relative_to(parent))
    return value


def qualify_moments(root, modes, layout, oracle, binding, run, helpers, profile):
    """Reuse bound V23 exact-frequency witnesses; fill only missing frequencies."""
    import numpy as np
    from src.solvers.directional_boundary import zvalue

    old = (
        root
        / "benchmarks/artifacts/task42extra/task42extra_v23_facet_qualification_20261004T131906722438Z"
    )
    npz = old / "oracle.npz"
    strings = old / "moment_decimal110.json"
    if (
        helpers.file_receipt(npz)["sha256"]
        != "12c174d1d7d67fa5441e0f0bf114c1a076949a86a79dc35db5d37e3b625cb7e6"
        or helpers.file_receipt(strings)["sha256"]
        != "5d1a9cce12533c14d500a0d343af384df944da8fe418536a619ef629ec44db68"
    ):
        raise ValueError("W28_BOUND_ORACLE_REUSE_HASH")
    with np.load(npz, allow_pickle=False) as f:
        oldfreq = f["frequencies"]
        old80 = f["moment_oracle80"]
        old110 = f["moment_oracle110"]
    oldstrings = json.loads(strings.read_text())
    existing = {float(v): i for i, v in enumerate(oldfreq)}
    widths = (layout.x[101] - layout.x[100], layout.y[2] - layout.y[1])
    selected = {0.0}
    for m in modes:
        for axis in (0, 1):
            w = float(zvalue(m["k_vector"][axis]).real * widths[axis])
            selected.update((w, -w))
    frequencies = sorted(selected)
    if any(abs(w) > 56 for w in frequencies):
        raise ValueError("W28_ORACLE_FREQUENCY_SCOPE")
    decimal = helpers.load_file(
        "_w28_decimal", root / "benchmarks/portable_facet_oracle.py"
    )
    a = []
    b = []
    c = []
    exact = []
    reused = new = 0
    for j, w in enumerate(frequencies):
        helpers.guard(binding)
        if w in existing:
            i = existing[w]
            b0, c0, cs = old80[i], old110[i], oldstrings[i]
            reused += 1
            method = "V23_bound_Decimal80_110_power_series"
        else:
            b0, _ = decimal.moments(w, 6, 80)
            c0, cs = decimal.moments(w, 6, 110, direct_quadrature=True)
            new += 1
            method = "Decimal80_power_series_vs_Decimal110_fixed_Gauss64"
        a0 = oracle.unit_interval_moments(w, 6)
        a.append(a0)
        b.append(b0)
        c.append(c0)
        exact.append(dict(omega=w, method=method, decimal110=cs))
        if j % 128 == 0:
            print("moment qualification", j, len(frequencies), flush=True)
    a, b, c = np.array(a), np.array(b), np.array(c)
    maximum = float(max(np.max(abs(a - c)), np.max(abs(b - c))))
    # An independent fixed Gauss64 cross-check at extrema and zero covers reuse methodology too.
    direct_checks = []
    for w in sorted({frequencies[0], 0.0, frequencies[-1]}):
        helpers.guard(binding)
        d, _ = decimal.moments(w, 6, 110, direct_quadrature=True)
        direct_checks.append(
            dict(omega=w, absolute=float(np.max(abs(c[frequencies.index(w)] - d))))
        )
    maximum = max(maximum, max(v["absolute"] for v in direct_checks))
    # Preserve the actual integration rule independently of its high-precision
    # reference. This also exposes a one-dimensional absolute failure even if
    # tensor contraction happens to cancel it in an empirical field witness.
    import basix
    from numpy.polynomial.legendre import legvander

    points, weights = basix.make_quadrature(basix.CellType.interval, 60)
    t = points[:, 0]
    if binding["contract"]["integration_profile"] == profile.NATIVE:
        integration = np.array(
            [
                (weights * np.exp(1j * w * t)) @ legvander(2 * t - 1, 6)
                for w in frequencies
            ]
        )
    else:
        integration = np.array(
            [
                profile.q60_moments(w, 6, t, weights, profile.subdivision_count(w))
                for w in frequencies
            ]
        )
    helpers.atomic_arrays(
        run / "oracle.npz",
        dict(
            frequencies=np.array(frequencies),
            analytic=a,
            reference80=b,
            reference110=c,
            integration_candidate=integration,
        ),
    )
    helpers.atomic_json(run / "moment_decimal110.json", exact)
    helpers.atomic_json(
        run / "oracle_qualification.json",
        dict(
            status="ORACLE_INTERVAL_PASS"
            if maximum <= 1e-12
            else "ORACLE_ACCURACY_UNRESOLVED",
            maximum_absolute=maximum,
            frequencies=len(frequencies),
            ell=[0, 6],
            maximum_abs_omega=max(abs(w) for w in frequencies),
            reused_frequency_count=reused,
            new_frequency_count=new,
            source_npz=helpers.file_receipt(npz),
            source_decimal=helpers.file_receipt(strings),
            direct_checks=direct_checks,
            precision=[80, 110],
            fixed_Gauss_points=64,
        ),
    )
    if maximum > 1e-12:
        raise ValueError("W28_INDEPENDENT_ORACLE_ACCURACY")
    return relative_receipt(run / "oracle.npz", run, helpers), a, c, frequencies


def boundary_v28(root, binding, modes, component, run, helpers):
    import numpy as np
    from src.solvers.directional_boundary import zvalue

    profile = helpers.load_file(
        "_w28_profile", root / "src/solvers/w1_facet_profile.py"
    )
    oracle = helpers.oracle_module(root)
    selected_profile = binding["contract"]["integration_profile"]
    kvec = np.array([[zvalue(v) for v in m["k_vector"]] for m in modes])
    index = dict(
        schema="w1-boundary-raw-index.v28",
        instance_id=INSTANCE,
        profile=selected_profile,
        complete=False,
        chunks=[],
        layouts={},
        actions={},
        incident={},
        chunk_limit=64,
        reference_definition_sha256=hashlib.sha256(
            (
                root / "input/task042extra_feinn_5nm/w1_reference_definition_v28.json"
            ).read_bytes()
        ).hexdigest(),
    )
    layout, _ = helpers.layout_for(modes, 4)
    oracle_row, _, refmom, freq = qualify_moments(
        root, modes, layout, oracle, binding, run, helpers, profile
    )
    index["oracle"] = oracle_row
    lookup = {float(w): refmom[j] for j, w in enumerate(freq)}
    del layout
    # Declared numerical remedy is fixed before any scoring, not selected by error.
    subdivisions = {
        str(w): profile.subdivision_count(w)
        if selected_profile != profile.NATIVE
        else 1
        for w in freq
    }
    helpers.atomic_json(
        run / "integration_profile.json",
        dict(
            profile=selected_profile,
            q=60,
            subdivisions=subdivisions,
            rule="minimal power of two for per-axis phase span <=4pi; global FE coordinates/Jacobian",
            no_changed_mesh_or_modes=True,
            reference_frozen_before_scoring=True,
        ),
    )
    chunks = index["chunks"]
    for p in (4, 6):
        helpers.guard(binding)
        layout, floquet = helpers.layout_for(modes, p)
        layout.polynomial = profile.ProfiledFacet(layout.polynomial, selected_profile)
        poly = layout.polynomial
        lay = dict(degree=np.array(p), rows=np.array(layout.rows))
        for side in ("top", "bottom"):
            lay.update(
                {
                    side + "_coeff": poly.coefficients[side],
                    side + "_active": poly.active[side],
                    side + "_rows": layout.maps[side][100, 1],
                    side + "_weights": layout.weights[side][100, 1],
                }
            )
        helpers.atomic_arrays(run / f"layout_p{p}.npz", lay)
        index["layouts"][str(p)] = relative_receipt(
            run / f"layout_p{p}.npz", run, helpers
        )
        action = profile.profiled_action(layout, modes, selected_profile)

        def action_factory(*args, _action=action, **kwargs):
            return _action

        states = {
            n: component.probe_actions(
                layout, modes, 60, action_factory=action_factory, seed=seed
            )
            for n, seed in (("original", None), ("generic", 4212801))
        }
        helpers.atomic_arrays(
            run / f"actions_p{p}.npz",
            {n + "_" + k: v for n, s in states.items() for k, v in s.items()},
        )
        index["actions"][str(p)] = relative_receipt(
            run / f"actions_p{p}.npz", run, helpers
        )
        J = np.diag([layout.x[101] - layout.x[100], layout.y[2] - layout.y[1], 10.0])
        for side in ("top", "bottom"):
            ids = [i for i, m in enumerate(modes) if m["side"] == side]
            origin = np.array(
                [layout.x[100], layout.y[1], 120.0 if side == "top" else -10.0]
            )
            folder = run / f"p{p}_{side}"
            folder.mkdir()
            if side == "top":
                packet = component.incident_boundary_packet(
                    poly, side, modes, J, origin, oracle, 60
                )
                helpers.atomic_arrays(run / f"incident_p{p}.npz", packet)
                index["incident"][str(p)] = relative_receipt(
                    run / f"incident_p{p}.npz", run, helpers
                )
            cache = {}
            for start in range(0, len(ids), 64):
                helpers.guard(binding)
                subset = ids[start : start + 64]
                candidate = []
                reference = []
                absolute = []
                for i in subset:
                    k = kvec[i]
                    key = tuple(k)
                    if key not in cache:
                        c = poly.integral_native(side, k, J, origin, 60)
                        ca = poly.integral_native(
                            side, k, J, origin + np.array([25, 12.5, 0]), 60
                        )
                        mx, my = (
                            lookup[float(k[0].real * J[0, 0])][: p + 1],
                            lookup[float(k[1].real * J[1, 1])][: p + 1],
                        )
                        r = np.einsum(
                            "a,b,abjc->jc",
                            mx,
                            my,
                            poly.coefficients[side],
                            optimize=True,
                        )
                        pos = origin.copy()
                        pos[2] += J[2, 2] if side == "top" else 0
                        r *= np.array([J[1, 1], J[0, 0]])
                        r *= np.exp(1j * np.dot(k, pos))
                        cache[key] = (c, r, ca)
                    c, r, ca = cache[key]
                    candidate.append(c)
                    reference.append(r)
                    absolute.append(ca)
                # Adjacent polarizations share k; discard cache after each bounded batch.
                cache.clear()
                data = dict(
                    candidate=np.array(candidate),
                    reference=np.array(reference),
                    absolute_candidate=np.array(absolute),
                    origins=np.array([origin, origin + [25, 12.5, 0]]),
                    reference_planes=np.array([130.0, -10.0]),
                    J=J,
                    alpha=states["original"]["alpha"][subset],
                    mode_indices=np.array(subset),
                    k=kvec[subset],
                    e=np.array(
                        [[zvalue(v) for v in modes[i]["e_vector"]] for i in subset]
                    ),
                    traction=np.array(
                        [
                            [zvalue(v) for v in modes[i]["traction_vector"]]
                            for i in subset
                        ]
                    ),
                    H=np.array([modes[i]["projection_denominator"] for i in subset]),
                    quadrature_degree=np.array(60),
                    degree=np.array(p),
                    profile=np.array(selected_profile),
                )
                data["B"] = np.array(
                    [
                        c @ -t[:2]
                        for c, t in zip(
                            data["candidate"], data["traction"], strict=True
                        )
                    ]
                )
                data["D"] = np.array(
                    [
                        (c @ e[:2]).conj() / h
                        for c, e, h in zip(
                            data["candidate"], data["e"], data["H"], strict=True
                        )
                    ]
                )
                target = folder / f"{start:05d}.npz"
                helpers.atomic_arrays(target, data, compressed=True)
                chunks.append(
                    {
                        **relative_receipt(target, run, helpers),
                        "degree": p,
                        "side": side,
                        "mode_indices": subset,
                    }
                )
                helpers.atomic_json(run / "chunk_index.json", index)
                if start % 1024 == 0:
                    print("boundary chunk", p, side, start, len(ids), flush=True)
        del layout, poly, action, states, lay
        gc.collect()
    index["complete"] = True
    helpers.atomic_json(run / "chunk_index.json", index)
    # Only a producer completion tag; numeric qualification belongs to an independent saved checker.
    raw = [helpers.file_receipt(run / r["path"]) for r in chunks]
    raw.extend(
        helpers.file_receipt(run / r["path"])
        for group in ("layouts", "actions", "incident")
        for r in index[group].values()
    )
    raw.extend(
        helpers.file_receipt(run / n)
        for n in (
            "oracle.npz",
            "oracle_qualification.json",
            "moment_decimal110.json",
            "chunk_index.json",
            "integration_profile.json",
        )
    )
    return dict(
        status="BOUNDARY_COMPLETE_PENDING_SAVED_CHECKER",
        raw_files=raw,
        full_native_columns=True,
        all_mode_count=32060,
        coverage={"4": 32060, "6": 32060},
        integration_profile=selected_profile,
        independent_numeric_gate=False,
        no_factor_solve_Gram_NN=True,
        floquet=floquet,
    )


def run_payload(root, snapshot, binding, helpers):
    def from_module(name, path):
        return helpers.load_file(name, root / path)

    contract = from_module("_w28_contract", "src/io/w1_receiver_contract.py")
    for name, expected in binding["receiver_files"].items():
        if contract.digest(root / name) != expected:
            raise ValueError("W28_PAYLOAD_SOURCE_CHANGED:" + name)
    run = Path(binding["run_path"])
    stage = binding["stage"]
    spec = binding["spec"]
    origin = time.monotonic()
    helpers.guard(binding)
    if stage == "input_contract_checks":
        target = root / "src/test/test_w1_versioned_input.py"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(target),
            "--junitxml=" + str(run / "junit.xml"),
        ]
        completed = subprocess.run(cmd, cwd=root, check=False)
        result = dict(
            status="V28_INPUT_CONTRACT_TESTS_PASS"
            if completed.returncode == 0
            else "V28_INPUT_CONTRACT_TESTS_FAIL",
            raw=helpers.file_receipt(run / "junit.xml"),
            scope="PURE_LOGIC_ONLY_NOT_NATIVE_FE",
            pytest_exit_code=completed.returncode,
        )
    elif stage == "manifest_qualify":
        validator = from_module("_w28_modes", "src/common/w1_mode_validation.py")
        config = json.loads(Path(spec["physical_config_path"]).read_text())
        document = json.loads(Path(spec["manifest_path"]).read_text())
        path = run / "mode_field_metrics.csv"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "mode_index",
                    "key",
                    "field",
                    "numerator",
                    "reference_norm",
                    "denominator",
                    "relative",
                    "near_zero",
                    "passed",
                ],
            )
            writer.writeheader()

            def write(row):
                helpers.guard(binding)
                writer.writerow(
                    {**row, "key": json.dumps(row["key"], separators=(",", ":"))}
                )

            science = validator.validate_document(
                document, config["physical_identity"], write_row=write
            )
        helpers.atomic_json(run / "mode_validation.json", science)
        result = dict(
            status="VERSIONED_MODE_INPUT_QUALIFIED"
            if science["status"] == "MODE_SCIENCE_PASS"
            else "INPUT_PHYSICS_FAILED",
            mode_validation=science,
            raw_metrics=helpers.file_receipt(path),
            raw=helpers.file_receipt(run / "mode_validation.json"),
            generation_count=0,
        )
    elif stage in {"control", "boundary"}:
        contract, component = helpers.source_modules(root, snapshot, binding)
        helpers.atomic_json(run / "runtime.json", helpers.numeric_runtime())
        if stage == "control":
            result = component.control_layout()
            result["p6_native_control"] = component.control_layout(degree=6)
            arrays = result.pop("arrays")
            arrays.update(
                {
                    "p6_" + k: v
                    for k, v in result["p6_native_control"].pop("arrays").items()
                }
            )
            result.update(
                raw=helpers.atomic_arrays(run / "control_arrays.npz", arrays),
                native_control_complete=True,
            )
        else:
            contract.require_same_binding(binding, spec, consumer=stage)
            modes = json.loads(Path(spec["manifest_path"]).read_text())["modes"]
            modes, physics = component.physical_modes(modes)
            helpers.atomic_json(run / "physics_binding.json", physics)
            result = boundary_v28(root, binding, modes, component, run, helpers)
        result.update(
            raw_runtime=helpers.file_receipt(run / "runtime.json"),
            raw_abi=helpers.file_receipt(run / "abi_receipt.json"),
            raw_overlay=helpers.file_receipt(run / "math_export_overlay.json"),
        )
    elif stage == "boundary_check":
        checker = from_module("_w28_saved", "src/solvers/w1_saved_boundary.py")
        producer = Path(spec["prerequisite_paths"]["boundary"])
        modes = json.loads(Path(spec["manifest_path"]).read_text())["modes"]
        config = json.loads(Path(spec["physical_config_path"]).read_text())
        metrics = run / "boundary_metrics.csv"
        result = checker.check_saved(
            producer, modes, config, metrics, guard=lambda: helpers.guard(binding)
        )
        result.update(
            raw_metrics=helpers.file_receipt(metrics),
            raw_index=helpers.file_receipt(producer / "chunk_index.json"),
            producer_directory=str(producer),
        )
    elif stage == "bundle_consume":
        bundle = from_module("_w28_bundle", "src/io/w1_boundary_bundle.py")
        result = bundle.build_and_consume(root, binding, run, helpers)
    else:
        raise ValueError("W28_IMPLEMENTED_STAGE_REQUIRED")
    result.update(
        receiver_source_sha=binding["receiver_source_sha"],
        binding_sha256=contract.digest(run / "binding.json"),
        elapsed_seconds=time.monotonic() - origin,
        instance_id=INSTANCE,
        input_origin=spec["input_origin"],
        integration_profile=spec["integration_profile"],
        math_commit=contract.MATH_COMMIT,
        NN_used=False,
        PDE_solved=False,
        official_results=False,
        full_target_qualified=False,
    )
    helpers.atomic_json(run / "component_result.json", result)
    print(
        json.dumps(
            {k: result[k] for k in ("status", "elapsed_seconds", "receiver_source_sha")}
        ),
        flush=True,
    )
    return 0
