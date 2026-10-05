"""Bounded affine-fixture support pilot; source preparation, not all-mode authority.

The caller supplies the existing 3 GiB watchdog and metadata Library seal.
The degree27 complete FFCx witnesses precede degree160 native work. The pilot
retains complete882-row anchors and does not build a carrier, volume or factor.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import resource
import sys
import time

import numpy as np

BASE_RUNNER_SHA = "3705674a56b9f4e7afe0b5ff77215ee5180cd397d39e20f1f70423d888ea7683"
PAIRS = ((0, 0), (-142, -5), (-85, -35))
SCHEMA = "task40extra.boundary-support-pilot.v1"
CELL_DOFS, NATIVE_ROWS = 882, 13224
OWNED_LIMIT = 128 << 20
RAW_LIMIT = 512 << 20
CHUNK_SIZE = 32


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def load_pinned(name, path, digest):
    if file_sha256(path) != digest:
        raise ValueError("pinned module bytes differ: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def selected_indices(modes):
    """Select literal complete-inventory keys; never infer a missing channel."""
    keys = [(m.side, int(m.m), int(m.n), m.polarization) for m in modes]
    if len(keys) != 32060 or len(set(keys)) != len(keys):
        raise ValueError("exact unique32060 physical inventory required")
    mapping = {key: index for index, key in enumerate(keys)}
    wanted = [(side, m, n, polar) for side in ("top", "bottom")
              for m, n in PAIRS for polar in ("s", "p")]
    if any(key not in mapping for key in wanted):
        raise ValueError("complete selected side/polarization/phase coverage missing")
    return tuple(mapping[key] for key in wanted)


def inventory_phase_identity(modes):
    """Mathematical unit modulus on exact centered port planes, all keys.

    This is not a bound on the library's finite exp evaluation. Every processed
    numerical phase batch must separately record its actual finite modulus.
    """
    if len(modes) != 32060:
        raise ValueError("full actual inventory required before mesh")
    for mode in modes:
        if mode.side not in ("top", "bottom"):
            raise ValueError("unknown physical port side")
        alpha, gamma, kz = complex(mode.alpha), complex(mode.gamma), complex(mode.k_vector[2])
        if not all(np.isfinite(v) for v in (alpha, gamma, kz)) or alpha.imag != 0 or gamma.imag != 0:
            raise ValueError("nonfinite or nonreal full-inventory tangential phase")
    return {"mode_count": len(modes), "all_tangential_wavevectors_literal_real": True,
            "centered_port_phase": "exp(i*alpha*x+i*gamma*y+i*kz*(z-z_port))",
            "exact_port_plane_delta_z": 0,
            "mathematical_modulus_on_plane": 1.0,
            "finite_exp_modulus_certified_by_this_metadata": False,
            "processed_batches_require_actual_phase_modulus": True}


def _payload(value):
    if isinstance(value, np.ndarray):
        return value.nbytes
    if isinstance(value, dict):
        return sum(_payload(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return sum(_payload(item) for item in value)
    return 0


def save_arrays(core, root, prefix, arrays, gate, event, held_bytes):
    """Save one array at a time, before shape/math checks, no bulk copy."""
    artifacts = {}
    for name, value in arrays.items():
        array = np.asarray(value)
        raw_bytes = sum(path.stat().st_size for path in root.rglob("*.npy"))
        if raw_bytes + array.nbytes + 8192 > RAW_LIMIT:
            raise MemoryError("complete untrimmed raw packet exceeds512MiB")
        predicted = held_bytes + 2*array.nbytes + (1 << 20)
        if predicted > OWNED_LIMIT:
            raise MemoryError("complete-array persistence exceeds owned128MiB")
        gate("pilot/save/" + name, {"predicted_total_bytes": predicted,
              "predicted_buffer_bytes": {"persistent_caller_owned_bytes": held_bytes,
                                         "new_file_IO_workspace_bytes": 2*array.nbytes+(1 << 20)}})
        artifact = core._save_array(root, prefix + "_" + name, array)
        artifacts[name] = artifact
        event({"stage": "complete_pilot_array_saved", "role": prefix, "name": name, "artifact": artifact})
    return artifacts


def actions(states, components, C, D):
    if (states.shape != (NATIVE_ROWS, 3) or components.shape != (12, 2, NATIVE_ROWS)
            or C.shape != (12, NATIVE_ROWS) or D.shape != C.shape
            or any(value.dtype != np.complex128 or not np.isfinite(value).all()
                   for value in (states, components, C, D))):
        raise ValueError("full selected native component/C/D shape differs")
    component = np.empty((12, 2, 3), dtype=np.complex128)
    cdual, dfunctional = np.empty((12, 3), dtype=np.complex128), np.empty((12, 3), dtype=np.complex128)
    for index in range(12):
        for state in range(3):
            for axis in range(2):
                component[index, axis, state] = np.vdot(states[:, state], components[index, axis])
            cdual[index, state] = np.vdot(states[:, state], C[index])
            dfunctional[index, state] = np.dot(D[index], states[:, state])
    return {"component_actions": component, "Cdual_actions": cdual, "Dfunctional_actions": dfunctional}


def validate_result(result, indices, degree, helper_identity, signatures, base):
    facts, arrays = result["record"], result["arrays"]
    if (facts.get("status") != "SOURCE_PILOT_ASSEMBLED_PENDING_CONTROLS"
            or facts.get("selected_output_gate_passed") is not True
            or facts.get("selected_output_status") != "CERTIFIED_CLOSURE_OR_COMPLETE_FULL882_FALLBACK"
            or facts.get("source") != {key: helper_identity[key] for key in ("path", "sha256")}
            or facts.get("selected_indices") != list(indices)
            or facts.get("quadrature_degree") != degree or facts.get("native_rows") != NATIVE_ROWS
            or facts.get("local_rows") != CELL_DOFS or facts.get("full_882_anchors_mandatory") is not True
            or facts.get("finite_excluded_values_thresholded") is not False
            or facts.get("FE_JIT_PDE_creation_calls") != 0
            or facts.get("owned_workspace_admission_maximum_bytes", OWNED_LIMIT+1) > OWNED_LIMIT):
        raise ValueError("support helper identity/scope/certificate gate differs")
    facets = facts.get("actual_facets", [])
    if len(facets) != 12 or any(sum(f["side"] == side for f in facets) != 6 for side in ("top", "bottom")):
        raise ValueError("complete twelve-side facet coverage missing")
    for key, expected in signatures.items():
        if key in facts and facts[key] != expected:
            raise ValueError("actual native signature differs: " + key)
    for name in ("slaves", "masters", "coefficients", "offsets"):
        if base._native_payload_signature(arrays["MPC_" + name]) != signatures["MPC"][name]:
            raise ValueError("saved actual MPC metadata differs: " + name)
    if base._native_payload_signature(arrays["cell_permutations"]) != signatures["cell_permutations"]:
        raise ValueError("saved actual native orientations differ")
    for key in ("actual_bound_containment", "own_component_masks"):
        if len(facts.get(key, [])) != 48 or not all(item["passed"] for item in facts[key]):
            raise ValueError("complete support bound/mask coverage failed: " + key)
    selected = []
    for position in range(12):
        for kind in ("C", "D"):
            metric = base.vector_comparison(arrays[kind][position], arrays[kind + "_anchor"][position])
            selected.append({"position": position, "kind": kind, **metric})
    if not all(item["passed"] for item in selected):
        raise ValueError("selected C/D output differs from complete882 anchor beyond1e-11")
    return selected


def run_pilot(*, repo_root, metadata_dir, metadata_seal, output_dir, cache_dir,
              allocation_gate, event, helper, reference_helper):
    base_path = Path(__file__).resolve().parents[1]/"chunked_native/run_chunked_surface_cost_mass_v2.py"
    base = load_pinned("pinned_boundary_pilot_utilities", base_path, BASE_RUNNER_SHA)
    core = base._load_core(repo_root)
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=False)
    cache = Path(cache_dir).resolve()
    cache.mkdir(parents=True, exist_ok=False)
    record = {"schema": SCHEMA, "status": "PARTIAL_NOT_RUN", "selected_only": True,
              "allmode_qualification": False, "carrier_volume_factor_PDE_calls": 0,
              "fixture_purpose": "18-cell original-dimensions affine boundary fixture; not an accuracy mesh",
              "raw_budget_bytes": RAW_LIMIT, "raw_budget_scope": "all complete NPY evidence files, including headers",
              "owned_buffer_limit_bytes": OWNED_LIMIT,
              "mechanism_comparisons": [], "FFCx_components": [], "compiled_mechanism": []}
    stage, started = "metadata", time.perf_counter()
    held = 0
    def checkpoint():
        core._write_bytes(root/"partial_pilot_record.json", core.canonical(core.jsonable(record)))
    def gate(label, facts):
        facts = dict(facts)
        if "owned_and_workspace_bytes_upper" in facts:
            total = int(facts["owned_and_workspace_bytes_upper"]) + held
            facts.update(caller_held_owned_bytes=held, combined_owned_bytes_upper=total,
                         predicted_total_bytes=total)
            facts["predicted_buffer_bytes"] = {**facts["predicted_buffer_bytes"], "caller_held_owned_bytes": held}
            if total > OWNED_LIMIT:
                raise MemoryError("helper plus caller-owned arrays exceed128MiB")
        return allocation_gate(label, facts)
    try:
        packet = core.validate_metadata_seal(metadata_dir=metadata_dir, seal=metadata_seal)
        bundle = core._fresh_inventory(repo_root=repo_root, allocation_gate=gate, event=event)
        if (bundle.manifest_bytes != (Path(metadata_dir)/"original_physical_manifest.json").read_bytes()
                or bundle.ordered_keys_bytes != (Path(metadata_dir)/"original_ordered_keys.json").read_bytes()
                or bundle.config_sha256 != packet["config_sha256"] or bundle.sources != packet["sources"]
                or bundle.quadrature_degree != 160):
            raise ValueError("fresh full physical inventory differs from immutable Library seal")
        indices = selected_indices(bundle.modes)
        modes = tuple(bundle.modes[index] for index in indices)
        record.update(inventory_phase_identity=inventory_phase_identity(bundle.modes),
            selected_original_mode_indices=indices, selected_original_keys=[core.mode_key(i, bundle.modes[i]) for i in indices],
            selected_physical_rows=[core.jsonable(bundle.rows[index]) for index in indices],
            metadata_seal=metadata_seal, config_sha256=bundle.config_sha256,
            ordered_keys_sha256=bundle.ordered_keys_sha256, physical_manifest_sha256=bundle.physical_manifest_sha256,
            actual_sources={"runner": {"path": str(Path(__file__).resolve()), "sha256": file_sha256(__file__)},
              "helper": base._function_identity(helper, core), "reference": base._function_identity(reference_helper, core)},
            cfg_as_jsonable=bundle.cfg.as_jsonable())
        checkpoint()
        stage = "fixture"
        V, mesh_data, floquet = core._bare_fixture(bundle.cfg, allocation_gate=gate, event=event)
        mpc, msh = floquet.mpc, mesh_data.mesh
        n = int(V.dofmap.index_map.size_local)
        if n != NATIVE_ROWS or V.dofmap.index_map.num_ghosts != 0:
            raise ValueError("exact13224 native rows without ghosts required")
        msh.topology.create_entity_permutations()
        signatures = base._actual_native_signatures(V, mpc)
        _, offsets = mpc.coefficients()
        mpc_width = max(1, int(np.max(np.diff(np.asarray(offsets)), initial=0)))
        from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler, _combine_owned_entries, _traction_vector
        from src.solvers.dtn_boundary_phase_gauge import assembly_projection_denominator
        H = np.array([assembly_projection_denominator(mode, bundle.cfg, "boundary_plane") for mode in modes], dtype=np.float64)
        record.update(actual_native_signatures=signatures, H_convention="explicit positive boundary-plane diagonal", H_diagonal=H)
        checkpoint()
        stage = "mechanism_chunked27"
        stage_started = time.perf_counter()
        mechanism = helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg,
            selected_modes=modes, selected_indices=indices, quadrature_degree=27,
            allocation_gate=gate, event=event, output_dir=root/"mechanism_native", production_h_diagonal=H,
            chunk_size=CHUNK_SIZE, enable_closure=True)
        ma = mechanism["arrays"]
        record["mechanism_native_wall_seconds"] = time.perf_counter()-stage_started
        held = _payload(ma)
        record["mechanism_native_record"] = mechanism["record"]
        record["mechanism_artifacts"] = save_arrays(core, root, "mechanism", ma, gate, event, held)
        checkpoint()
        record["mechanism_selected_output_comparisons"] = validate_result(mechanism, indices, 27,
            record["actual_sources"]["helper"], signatures, base)
        ffcx_entries = {}
        for side in ("top", "bottom"):
            group = tuple(j for j, mode in enumerate(modes) if mode.side == side)
            for axis in (0, 1):
                stage = "mechanism_FFCx_" + side + str(axis)
                core._admit(stage + "_compile", {"small_FFCx_workspace_allowance": 384 << 20,
                    "kernel_identity_workspace_allowance": 128 << 20}, allocation_gate=gate, event=event,
                    degree=27, mechanism_only=True, target_FFCx_form_calls=0)
                compile_started = time.perf_counter()
                assembly = _ReusableSurfaceComponentAssembler(V, mesh_data,
                    bundle.cfg.tags.z_max if side == "top" else bundle.cfg.tags.z_min, axis,
                    quadrature_degree=27, jit_options={"cache_dir": str(cache), "cffi_extra_compile_args": ["-O2"]},
                    boundary_reference_z=130.0 if side == "top" else -10.0, verify_compiled_gauss=True)
                compiled = core.jsonable(assembly.compiled_gauss_identity)
                item = {"side": side, "axis": axis, "identity": compiled,
                        "compile_and_identity_wall_seconds": time.perf_counter()-compile_started}
                kernel = compiled["loaded_kernel"]
                directory = root/("compiled_" + side + str(axis)); directory.mkdir()
                item["artifacts"] = {name: core._copy_pinned_file(Path(kernel[pathkey]), directory/Path(kernel[pathkey]).name, kernel[hashkey])
                    for name, pathkey, hashkey in (("C", "module_bound_C_path", "module_bound_C_sha256"),
                        ("binary", "module_path", "binary_sha256"))}
                item["rule_match"] = base.mechanism_rule_comparison(compiled, ma["rule_points"], ma["rule_weights"])
                record["compiled_mechanism"].append(item); checkpoint()
                for j in group:
                    mode, index = modes[j], indices[j]
                    core._admit(stage + "_complete_vectors", core.component_allocation_facts(n, 0, CELL_DOFS, mpc_width),
                        allocation_gate=gate, event=event, original_mode_index=index)
                    bfe, fe_owner = base._destroy_owned_vector_after_copy(lambda: assembly.assemble_unconstrained_vector(mode))
                    raw, raw_owner = base._destroy_owned_vector_after_copy(lambda: assembly.assemble_raw_mpc_vector(mode, mpc))
                    rows, values = assembly.assemble_entries(mode, mpc)
                    own, masked, mask = base.unchanged_mask_comparison(raw, rows, values)
                    artifacts = save_arrays(core, root, f"ffcx_{index}_{axis}",
                        {"b_FE": bfe, "raw_MPC": raw, "masked": masked, "mask": mask, "rows": rows, "values": values},
                        gate, event, held + _payload((bfe, raw, masked, mask, rows, values, ffcx_entries)))
                    comparison = {"index": index, "side": side, "axis": axis, "artifacts": artifacts,
                        "ownership": [fe_owner, raw_owner], "own_mask": own,
                        "b_FE": base.vector_comparison(bfe, ma["b_FE_anchor"][j, axis]),
                        "raw_MPC": base.vector_comparison(raw, ma["raw_MPC_anchor"][j, axis]),
                        "masked": base.vector_comparison(masked, ma["masked_anchor"][j, axis])}
                    comparison["passed"] = (fe_owner == raw_owner == (0, n) and own["passed"]
                        and all(comparison[name]["passed"] for name in ("b_FE", "raw_MPC", "masked")))
                    record["mechanism_comparisons"].append(comparison)
                    ffcx_entries[(j, axis)] = (rows, values)
                    checkpoint()
                    del bfe, raw, masked, mask
                del assembly
        for j, mode in enumerate(modes):
            entries = (ffcx_entries[(j, 0)], ffcx_entries[(j, 1)])
            traction = _traction_vector(mode, bundle.cfg)
            cr, cv = _combine_owned_entries(entries, (-traction[0], -traction[1]), comm=msh.comm)
            dr, dv = _combine_owned_entries(entries, (mode.e_vector[0], mode.e_vector[1]), comm=msh.comm)
            c, d = np.zeros(n, np.complex128), np.zeros(n, np.complex128)
            c[cr], d[dr] = cv, np.conjugate(dv)
            metrics = {"index": indices[j], "C": base.vector_comparison(c, ma["C_anchor"][j]),
                       "D": base.vector_comparison(d, ma["D_anchor"][j])}
            record.setdefault("mechanism_CD_comparisons", []).append(metrics)
            del c, d
        passed = (len(record["mechanism_comparisons"]) == 24
            and all(item["passed"] for item in record["mechanism_comparisons"])
            and all(item["rule_match"]["passed"] for item in record["compiled_mechanism"])
            and all(item[name]["passed"] for item in record["mechanism_CD_comparisons"] for name in ("C", "D")))
        record["mechanism_gate_passed"] = bool(passed); checkpoint()
        if not passed:
            raise ValueError("complete degree27 FFCx mechanism gate failed before160")
        del ma, mechanism, ffcx_entries
        held = 0
        stage = "native_primary160"
        stage_started = time.perf_counter()
        primary = helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg, selected_modes=modes,
            selected_indices=indices, quadrature_degree=160, allocation_gate=gate, event=event,
            output_dir=root/"target_native", production_h_diagonal=H, chunk_size=CHUNK_SIZE, enable_closure=True)
        arrays = primary["arrays"]; held = _payload(arrays)
        record["target_native_wall_seconds"] = time.perf_counter()-stage_started
        record["primary_record"] = primary["record"]
        record["primary_artifacts"] = save_arrays(core, root, "primary", arrays, gate, event, held)
        checkpoint()
        record["primary_selected_output_comparisons"] = validate_result(primary, indices, 160,
            record["actual_sources"]["helper"], signatures, base)
        stage = "native_states"
        states, fields = core._native_states(V, mpc, allocation_gate=gate, event=event)
        held += states.nbytes + sum(field.x.array.nbytes for field in fields)
        record["state_artifacts"] = save_arrays(core, root, "state", {"independent": states,
            **{f"expanded_{i}": np.asarray(field.x.array) for i, field in enumerate(fields)}}, gate, event, held)
        results = actions(states, arrays["raw_MPC_anchor"], arrays["C"], arrays["D"])
        record["action_artifacts"] = save_arrays(core, root, "action", results, gate, event, held + _payload(results))
        stage = "reference168_176"
        stage_started = time.perf_counter()
        reference = reference_helper(V=V, mesh_data=mesh_data, mpc=mpc, cfg=bundle.cfg, selected_modes=modes,
            selected_indices=indices, native_fields=fields, independent_states=states, quadrature_degree=160,
            allocation_gate=gate, event=event, output_dir=root/"reference")
        record["reference_record"] = reference["record"]
        record["public_reference_wall_seconds"] = time.perf_counter()-stage_started
        ra = reference["arrays"]
        record["reference_artifacts"] = save_arrays(core, root, "reference", ra, gate, event, held+_payload(ra))
        checks = {}
        for prefix, key in (("component", "component_actions"), ("Cdual", "Cdual_actions"), ("Dfunctional", "Dfunctional_actions")):
            expected = ra[prefix + "_degree_plus16"]
            scales = ra[prefix + "_operation_scales_degree_plus16"]
            checks[prefix] = core.reference_action_gate(results[key], expected, scales)
            checks[prefix + "_convergence"] = core.reference_action_gate(ra[prefix + "_degree_plus8"], expected, scales)
        record["reference_checks"] = checks
        if not all(check["passed"] for check in checks.values()):
            raise ValueError("selected component/C/D functional or convergence gate failed")
        record.update(status="BOUNDARY_SUPPORT_PILOT_COMPLETE", pilot_passed=True,
            mechanism_forms=4, actual_native_rows=n, full_C_D_allmode_qualification=False,
            support_accuracy_scope="selected three tuples/both sides/xy on literal18-cell affine fixture only")
    except BaseException as error:
        record.update(status="PARTIAL_FAILED_OR_CONTROLLED_STOP", pilot_passed=False, stopped_stage=stage,
            error_type=type(error).__name__, error=str(error))
        checkpoint()
        raise
    finally:
        record.update(wall_seconds=time.perf_counter()-started, named_retained_ndarray_bytes=held,
            self_RSS_high_water_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)*1024)
        checkpoint()
    artifact = core._write_bytes(root/"pilot_record.json", core.canonical(core.jsonable(record)))
    return {"record": core.jsonable(record), "pilot_record": artifact}
