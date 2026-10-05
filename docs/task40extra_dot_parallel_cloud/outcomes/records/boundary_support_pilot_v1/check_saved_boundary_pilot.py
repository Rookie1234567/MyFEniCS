"""Saved-only pilot replay. No mesh, form, tabulation, JIT, factor or PDE.

Replays saved finite-array algebra and all full FFCx/vector/functionals. It
does not independently rebuild882 basis columns or certify unprocessed modes.
"""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np

N, RAW_LIMIT, OWNED_LIMIT = 13224, 512 << 20, 128 << 20
WORKSPACE = 12 << 20


def _require(value, message):
    if not value:
        raise ValueError(message)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def load_array(descriptor, root, gate):
    path = Path(descriptor["path"]).resolve()
    _require(path.is_relative_to(root.resolve()) and path.is_file() and not path.is_symlink(), "foreign/missing raw array")
    _require(path.stat().st_size == descriptor["bytes"] and sha256(path) == descriptor["sha256"], "array file bytes/hash differ")
    with path.open("rb") as stream:
        version = np.lib.format.read_magic(stream)
        _require(version in ((1, 0), (2, 0)), "unsupported NPY evidence version")
        shape, fortran, dtype = (np.lib.format.read_array_header_1_0(stream) if version == (1, 0)
                                 else np.lib.format.read_array_header_2_0(stream))
        payload = math.prod(shape)*dtype.itemsize
        _require(not dtype.hasobject and list(shape) == descriptor["shape"] and str(dtype) == descriptor["dtype"]
                 and payload <= RAW_LIMIT and stream.tell()+payload == path.stat().st_size,
                 "NPY header/dtype/payload differs from immutable evidence")
    gate("saved_pilot/mmap", {"predicted_total_bytes": payload+(1 << 20),
        "predicted_buffer_bytes": {"mapped_complete_payload": payload, "header_workspace": 1 << 20}})
    return np.load(path, allow_pickle=False, mmap_mode="r")


def _full_mask(value, native):
    rows, values, _ = native.unchanged_mask(value)
    output = np.zeros(N, np.complex128); output[rows] = values
    return output


def check_saved(*, record, root, gate, base, helper, core, sealed_manifest):
    """Verify complete saved authority with unchanged vector/action gates."""
    root = Path(root).resolve()
    _require(record.get("pilot_passed") is True and record.get("status") == "BOUNDARY_SUPPORT_PILOT_COMPLETE",
             "incomplete numerical worker packet")
    indices = record["selected_original_mode_indices"]
    _require(len(indices) == 12 and len(set(indices)) == 12, "selected inventory incomplete")
    keys = record["selected_original_keys"]
    expected = {(side, m, n, polar) for side in ("top", "bottom")
                for m, n in ((0, 0), (-142, -5), (-85, -35)) for polar in ("s", "p")}
    _require(len(keys) == 12 and {tuple(key[1:]) for key in keys} == expected and
             [key[0] for key in keys] == indices, "side/phase/polarization coverage differs")
    _require(len(sealed_manifest) == 32060 and len(record["selected_physical_rows"]) == 12,
             "full sealed physical inventory missing")
    for position, index in enumerate(indices):
        _require(record["selected_physical_rows"][position] == sealed_manifest[index],
                 "selected C/D/H operands differ from immutable physical manifest")
        physical = sealed_manifest[index]
        _require(keys[position] == [index, physical["side"], physical["m"], physical["n"], physical["polarization"]],
                 "selected indexed key differs from sealed physical manifest")
    mechanism_rows = record.get("mechanism_comparisons", [])
    _require(len(mechanism_rows) == 24 and {(item["index"], item["axis"]) for item in mechanism_rows} ==
             {(index, axis) for index in indices for axis in (0, 1)}, "unique complete mechanism controls missing")
    _require(all(item["side"] == sealed_manifest[item["index"]]["side"] for item in mechanism_rows),
             "mechanism side differs from immutable selected key")
    def load(mapping, simultaneous=0):
        payload = sum(math.prod(item["shape"])*np.dtype(item["dtype"]).itemsize for item in mapping.values())
        total = payload+simultaneous+WORKSPACE
        _require(total < OWNED_LIMIT, "saved replay simultaneous owned128MiB exceeded")
        gate("saved_pilot/complete_mapping_before_first_mmap", {"predicted_total_bytes": total,
             "predicted_buffer_bytes": {"complete_mapping_payload": payload, "caller_simultaneous_payload": simultaneous,
                                         "algebra_certificate_IO_workspace": WORKSPACE}})
        values = {key: load_array(item, root, gate) for key, item in mapping.items()}
        return values
    native, _, _ = helper.public_helpers()
    counts = {"FFCx_complete_vector_comparisons": 0, "dual_projections": 0,
              "component_mask_replays": 0, "bound_containment_checks": 0,
              "C_D_selected_replays": 0, "public_reference_action_checks": 0}
    for role in ("mechanism", "primary"):
        arrays = load(record[role + "_artifacts"])
        facts = record["mechanism_native_record" if role == "mechanism" else "primary_record"]
        for name in ("slaves", "masters", "coefficients", "offsets"):
            _require(base._native_payload_signature(arrays["MPC_"+name]) == record["actual_native_signatures"]["MPC"][name],
                     "saved complete actual-native MPC snapshot differs: "+name)
        _require(len(facts["components"]) == 24 and {(item["mode_position"], item["original_mode_index"], item["component"])
                 for item in facts["components"]} == {(p, indices[p], a) for p in range(12) for a in (0, 1)},
                 "complete component certificate labels missing")
        _require(len(facts["combined"]) == 24 and {(item["mode_position"], item["kind"]) for item in facts["combined"]} ==
                 {(p, k) for p in range(12) for k in ("C", "D")}, "complete combined certificate labels missing")
        slaves, masters = arrays["MPC_slaves"], arrays["MPC_masters"]
        coefficients, offsets = arrays["MPC_coefficients"], arrays["MPC_offsets"]
        for position in range(12):
            selected_components, selected_errors = np.empty((2, N), np.complex128), np.zeros((2, N), np.float64)
            for axis in (0, 1):
                for kind in ("anchor", "candidate"):
                    computed = native.dual_project(arrays["b_FE_"+kind][position, axis], slaves, masters, coefficients, offsets)
                    _require(np.array_equal(computed, arrays["raw_MPC_"+kind][position, axis]), "saved K^H projection differs")
                    counts["dual_projections"] += 1
                    masked = _full_mask(computed, native)
                    _require(np.array_equal(masked, arrays["masked_"+kind][position, axis]), "own unchanged component cutoff differs")
                    rows, _, _ = native.unchanged_mask(computed)
                    mask = np.zeros(N, dtype=bool); mask[rows] = True
                    _require(np.array_equal(mask, arrays["masks_"+kind][position, axis]), "saved component boolean mask differs")
                    counts["component_mask_replays"] += 1
                for prefix, bound_key in (("b_FE", "b_FE_error_bound"), ("raw_MPC", "raw_MPC_error_bound")):
                    error = np.abs(arrays[prefix+"_anchor"][position, axis]-arrays[prefix+"_candidate"][position, axis])
                    _require(np.isfinite(error).all() and np.all(error <= arrays[bound_key][position, axis]), "actual certificate bound violated")
                    counts["bound_containment_checks"] += 1
                certificate, _ = helper.mask_margin_certificate(arrays["raw_MPC_candidate"][position, axis],
                                                               arrays["raw_MPC_error_bound"][position, axis])
                choice = "closure84" if certificate["passed"] else "full882_fallback"
                item = next(item for item in facts["components"] if item["mode_position"] == position and
                            item["original_mode_index"] == indices[position] and item["component"] == axis)
                _require(item["selected"] == choice and item["certificate"] == certificate, "saved component certificate/fallback differs")
                selected_components[axis] = arrays["masked_candidate" if certificate["passed"] else "masked_anchor"][position, axis]
                if certificate["passed"]:
                    selected_errors[axis] = arrays["raw_MPC_error_bound"][position, axis]
                    selected_errors[axis, ~arrays["masks_candidate"][position, axis]] = 0
            physical = record["selected_physical_rows"][position]
            # These exact public-manifest operands were bound before the mesh.
            complex_vector = lambda values: np.array([complex(value["real"], value["imag"]) for value in values])
            traction, electric = complex_vector(physical["traction_vector"]), complex_vector(physical["e_vector"])
            for kind, coefficient in (("C", -traction[:2]), ("D", electric[:2])):
                raw_chosen, masked_chosen, _ = helper.combine_components(selected_components, coefficient)
                bound = helper.combined_error_bound(selected_components, arrays["masked_anchor"][position], selected_errors, coefficient)
                certificate, _ = helper.mask_margin_certificate(raw_chosen, bound)
                raw_anchor, anchor, _ = helper.combine_components(arrays["masked_anchor"][position], coefficient)
                _require(np.array_equal(bound, arrays[kind+"_combination_error_bound"][position]) and
                         np.all(np.abs(raw_chosen-raw_anchor) <= bound), "combined raw certificate bound differs or is violated")
                combined_item = next(item for item in facts["combined"] if item["mode_position"] == position and item["kind"] == kind)
                selected_label = "certified_components_then_combination" if certificate["passed"] else "full882_fallback"
                _require(combined_item["certificate"] == certificate and combined_item["selected"] == selected_label and
                         combined_item["actual_raw_bound_containment_passed"] is True,
                         "combined certificate/selection/containment receipt differs")
                if kind == "D":
                    anchor, masked_chosen = np.conjugate(anchor), np.conjugate(masked_chosen)
                selected = masked_chosen if certificate["passed"] else anchor
                _require(np.array_equal(anchor, arrays[kind+"_anchor"][position]) and
                         np.array_equal(selected, arrays[kind][position]), "selected C/D or single conjugation differs")
                metric = base.vector_comparison(selected, anchor)
                _require(metric["passed"], "selected C/D exceeds original1e-11 vector gate")
                counts["C_D_selected_replays"] += 1
            H = 1250.0*float(physical["electric_tangential_norm_sq"])
            _require(math.isfinite(H) and H > 0 and arrays["H"][position] == H, "production diagonal H differs")
        if role == "mechanism":
            for item in record["mechanism_comparisons"]:
                position = indices.index(item["index"]); axis = item["axis"]
                for key, actual in (("b_FE", "b_FE_anchor"), ("raw_MPC", "raw_MPC_anchor"), ("masked", "masked_anchor")):
                    witness = load_array(item["artifacts"][key], root, gate)
                    _require(base.vector_comparison(witness, arrays[actual][position, axis])["passed"], "full saved FFCx mechanism gate failed")
                    counts["FFCx_complete_vector_comparisons"] += 1
            for position, index in enumerate(indices):
                components = []
                for axis in (0, 1):
                    item = next(item for item in mechanism_rows if item["index"] == index and item["axis"] == axis)
                    rows, values = load_array(item["artifacts"]["rows"], root, gate), load_array(item["artifacts"]["values"], root, gate)
                    raw = load_array(item["artifacts"]["raw_MPC"], root, gate)
                    expected_rows, expected_values, _ = native.unchanged_mask(raw)
                    _require(np.array_equal(rows, expected_rows) and np.array_equal(values, expected_values),
                             "saved FFCx sparse values differ from raw-derived original cutoff")
                    flags = load_array(item["artifacts"]["mask"], root, gate)
                    expected_flags = np.zeros(N, dtype=bool); expected_flags[expected_rows] = True
                    _require(np.array_equal(flags, expected_flags), "saved FFCx boolean mask differs")
                    vector = np.zeros(N, np.complex128); vector[rows] = values; components.append(vector)
                physical = sealed_manifest[index]
                vector = lambda values: np.array([complex(v["real"], v["imag"]) for v in values])
                for kind, coefficient in (("C", -vector(physical["traction_vector"])[:2]), ("D", vector(physical["e_vector"])[:2])):
                    _, combined, _ = helper.combine_components(np.array(components), coefficient)
                    if kind == "D": combined = np.conjugate(combined)
                    _require(base.vector_comparison(combined, arrays[kind+"_anchor"][position])["passed"], "full saved FFCx C/D cancellation gate failed")
        del arrays
    states = load_array(record["state_artifacts"]["independent"], root, gate)
    primary = load(record["primary_artifacts"], states.nbytes)
    references = load(record["reference_artifacts"], states.nbytes+sum(value.nbytes for value in primary.values()))
    native_identity = record["reference_record"]["state_identity"]
    _require(base._native_payload_signature(states)["sha256"] == native_identity["master_state_sha256"] and
             np.all(states[primary["MPC_slaves"], :] == 0), "saved independent state identity/slave zeros differ")
    for field, name in (("MPC_slaves", "slaves_sha256"), ("MPC_coefficients", "coefficients_sha256"), ("MPC_offsets", "offsets_sha256")):
        _require(base._native_payload_signature(primary[field])["sha256"] == native_identity[name], "saved reference MPC identity differs")
    for state in range(3):
        expanded = load_array(record["state_artifacts"]["expanded_"+str(state)], root, gate)
        _require(base._native_payload_signature(expanded)["sha256"] == native_identity["expanded_state_sha256"][state],
                 "saved expanded Function state identity differs")
        flags = np.zeros(N, dtype=bool); flags[primary["MPC_slaves"]] = True
        _require(np.array_equal(expanded[~flags], states[~flags, state]), "saved independent master coefficients changed")
        for slave in primary["MPC_slaves"]:
            begin, end = int(primary["MPC_offsets"][slave]), int(primary["MPC_offsets"][slave+1])
            coefficient = primary["MPC_coefficients"][begin:end]
            wanted = np.sum(coefficient*states[primary["MPC_masters"][begin:end], state], dtype=np.complex128)
            scale = np.sum(np.abs(coefficient)*np.abs(states[primary["MPC_masters"][begin:end], state]))
            _require(abs(expanded[slave]-wanted) == 0 if scale == 0 else abs(expanded[slave]-wanted) <= 1e-10*scale,
                     "saved public backsubstitution relationship failed")
    for prefix, field in (("component", "component_actions"), ("Cdual", "Cdual_actions"), ("Dfunctional", "Dfunctional_actions")):
        action = load_array(record["action_artifacts"][field], root, gate)
        if prefix == "component":
            computed = np.array([[ [np.vdot(states[:, state], primary["raw_MPC_anchor"][position, axis])
                       for state in range(3)] for axis in (0, 1)] for position in range(12)])
        else:
            computed = np.array([[np.vdot(states[:, state], primary["C"][position]) if prefix == "Cdual"
                else np.dot(primary["D"][position], states[:, state]) for state in range(3)] for position in range(12)])
        _require(np.array_equal(computed, action), "saved native action contractions differ")
        scales = references[prefix+"_operation_scales_degree_plus16"]
        _require(core.reference_action_gate(computed, references[prefix+"_degree_plus16"], scales)["passed"] and
                 core.reference_action_gate(references[prefix+"_degree_plus8"], references[prefix+"_degree_plus16"], scales)["passed"],
                 "independent public-eval functional/convergence gate failed")
        counts["public_reference_action_checks"] += computed.size
    return {"status": "SAVED_SELECTED_PILOT_REPLAY_PASS", "passed": True, "counts": counts,
            "scope": "saved finite-array dual/mask/C/D/functionals for selected12 modes only",
            "basis_columns_rebuilt": False, "unprocessed_modes_qualified": False,
            "mesh_form_JIT_factor_PDE_calls": 0}
