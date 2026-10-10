"""Small saved-tensor capacity diagnostics, never a PDE solver or trainer.

The rank bounds are conditional on an independently established FE bridge.
Tails along different unfoldings overlap: take their maximum per component.
Only the three distinct physical components' energies are added.
"""

import numpy as np


def unfold(tensor, axis):
    value = np.asarray(tensor)
    if value.ndim != 3 or value.dtype != np.complex128 or not np.isfinite(value).all():
        raise ValueError("FINITE_COMPLEX128_THREE_AXIS_TENSOR_REQUIRED")
    if axis not in (0, 1, 2):
        raise ValueError("UNKNOWN_PHYSICAL_AXIS")
    return np.moveaxis(value, axis, 0).reshape(value.shape[axis], -1)


def full_spectrum(tensor, axis):
    matrix = unfold(tensor, axis)
    left, sigma, right = np.linalg.svd(matrix, full_matrices=False)
    numerator = float(np.linalg.norm((left * sigma) @ right - matrix))
    denominator = float(np.linalg.norm(matrix))
    relative = numerator / denominator if denominator else 0.0
    orthogonal = max(
        float(np.linalg.norm(left.conj().T @ left - np.eye(len(sigma)))),
        float(np.linalg.norm(right @ right.conj().T - np.eye(len(sigma)))),
    )
    return (left, sigma, right), dict(
        axis=axis,
        matrix_shape=list(matrix.shape),
        singular_values=sigma.tolist(),
        backward_error_numerator=numerator,
        backward_error_denominator=denominator,
        backward_error_relative=relative,
        orthogonality_defect=orthogonal,
        truncation="NONE_FULL_SPECTRUM",
        qualified=bool(relative <= 1e-12 and orthogonal <= 1e-12),
    )


def rank_bound(spectra, ranks, reference_E_norm, input_defect=0.0):
    if reference_E_norm <= 0 or input_defect < 0 or len(ranks) != 3:
        raise ValueError("ORIGINAL_FULL_E_DENOMINATOR_AND_DEFECT_REQUIRED")
    rows, tails = {}, []
    for component in "xyz":
        entries = []
        for axis, rank in enumerate(ranks):
            entry = spectra[component][axis]
            sigma = np.asarray(entry["singular_values"], dtype=np.float64)
            if rank < 0 or np.any(sigma < 0) or np.any(np.diff(sigma) > 0):
                raise ValueError("INVALID_COMPLETE_SPECTRUM_OR_RANK")
            raw = float(np.linalg.norm(sigma[rank:]))
            perturbation = input_defect + entry["backward_error_numerator"]
            entries.append(dict(axis=axis, rank=rank, tail_norm=raw,
                                perturbation_norm=perturbation,
                                conservative_tail_norm=max(0.0, raw-perturbation)))
        rows[component] = entries
        tails.append(max(e["conservative_tail_norm"] for e in entries))
    lower = float(np.linalg.norm(tails) / reference_E_norm)
    defect = max(input_defect,
                 max(e["backward_error_numerator"] for rows in spectra.values() for e in rows))
    margin = max(1e-8, 10.0 * defect / reference_E_norm)
    return dict(ranks=list(ranks), components=rows,
                denominator_full_scattered_E=reference_E_norm,
                conservative_relative_lower_estimate=lower,
                numerical_margin=margin, E_gate=1e-4,
                exceeds_gate_and_margin=bool(lower > 1e-4 + margin),
                same_component_axis_aggregation="MAX_NOT_SUM",
                physical_component_aggregation="SUM_ENERGIES",
                floating_point_diagnostic_not_interval_proof=True)


def necessary_ranks(spectra, reference_E_norm, input_defect=0.0):
    result = {}
    # An individual tail exceeding eps*||Eref|| already prevents the vector
    # criterion. These component-wise ranks are necessary, never sufficient.
    for threshold in (1e-2, 1e-3, 1e-4):
        rows = {}
        for component in "xyz":
            ranks = []
            for entry in spectra[component]:
                s = np.asarray(entry["singular_values"])
                allowance = input_defect + entry["backward_error_numerator"]
                ranks.append(next(r for r in range(len(s)+1)
                                  if max(0.0, np.linalg.norm(s[r:])-allowance)
                                  <= threshold*reference_E_norm))
            rows[component] = ranks
        result[str(threshold)] = rows
    return result


def axis_project(tensor, basis, axis):
    matrix = unfold(np.asarray(tensor, dtype=np.complex128), axis)
    basis = np.asarray(basis, dtype=np.complex128)
    if basis.ndim != 2 or basis.shape[0] != matrix.shape[0]:
        raise ValueError("FEATURE_AXIS_LAYOUT_MISMATCH")
    projected = basis @ (basis.conj().T @ matrix)
    shape = np.moveaxis(tensor, axis, 0).shape
    return np.moveaxis(projected.reshape(shape), 0, axis)


def feature_bound(tensors, bases, reference_E_norm, input_defect=0.0):
    energies, norms = {}, []
    for component in "xyz":
        original = tensors[component]
        projected = original.copy()
        for axis in range(3):
            projected = axis_project(projected, bases[component][axis], axis)
        difference = float(np.linalg.norm(original-projected))
        energies[component] = dict(error_norm=difference,
                                  tensor_norm=float(np.linalg.norm(original)))
        norms.append(max(0.0, difference-input_defect))
    return dict(components=energies, denominator_full_scattered_E=reference_E_norm,
                relative_lower_estimate=float(np.linalg.norm(norms)/reference_E_norm),
                projection="ALL_UNTRUNCATED_AXIS_SPACES_TT_RANK_RELAXED",
                combined_with_rank_bound="MAX_ONLY_NOT_ADD",
                frozen_hidden_only=True, not_all_trainable_networks=True)


def decision(bridge, pure_rank, width_rank, feature_records):
    if not bridge.get("rank_bound_transferable_to_actual_FE", False):
        return "NO_VALID_FE_CAPACITY_CERTIFICATE"
    if pure_rank["exceeds_gate_and_margin"]:
        return "R8_CAPACITY_EXCLUDED_NUMERICALLY"
    if width_rank["exceeds_gate_and_margin"]:
        return "WIDTH16_CAPACITY_EXCLUDED_NUMERICALLY"
    reliable = [v for v in feature_records.values() if v.get("full_space_qualified")]
    if any(v["relative_lower_estimate"] > 1e-4 + v.get("numerical_margin", 1e-8)
           for v in reliable):
        return "FROZEN_FEATURES_CAPACITY_EXCLUDED_NUMERICALLY"
    return "REPRESENTATION_NOT_EXCLUDED_OPTIMIZATION_UNRESOLVED"
