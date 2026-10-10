"""Independent saved-array consistency checker; no FE or model producer call."""

import json
from pathlib import Path
import numpy as np
from src.io.neural_wave_campaign import ROOT, digest


def read_arrays(entry):
    path = ROOT / entry["path"]
    if digest(path) != entry["sha256"]:
        raise ValueError("CAPACITY_SAVED_ARRAY_HASH_FAILED")
    with np.load(path, allow_pickle=False) as saved:
        return {k: np.array(saved[k]) for k in saved.files}


def independent_tail(spectra, ranks, norm, defect):
    values = []
    for label in "xyz":
        axis_tails = []
        for axis, rank in enumerate(ranks):
            record = spectra[label][axis]
            sigma = np.asarray(record["singular_values"])
            axis_tails.append(max(0., np.sqrt(np.sum(sigma[rank:]**2))-
                                  defect-record["backward_error_numerator"]))
        values.append(max(axis_tails))
    return float(np.sqrt(sum(v*v for v in values))/norm)


def check_saved(artifact_root):
    root = Path(artifact_root)
    bridge = json.loads((root/"v40_interior_moment_tensor/interior_tensor.json").read_text())
    sr = json.loads((root/"v40_rank_and_feature_bounds/spectra.json").read_text())
    fr = json.loads((root/"v40_rank_and_feature_bounds/features.json").read_text())
    T, S = read_arrays(bridge["arrays"]), read_arrays(sr["arrays"])
    F = read_arrays(fr["arrays"])
    norm = bridge["original_full_scattered_E_denominator"]
    original = bridge['input_identity']['norm_record']
    original_path = ROOT/original['path']
    if digest(original_path) != original['sha256']:
        raise ValueError('CAPACITY_ORIGINAL_FULL_E_RECORD_HASH_FAILED')
    actual_original_norm=json.loads(original_path.read_text())['physics']['reference_scattered_norms'][0]
    if (norm<=0 or norm!=actual_original_norm or
        abs(bridge['reference_E_norm']-norm)/norm>1e-10 or
        not bridge["full_E_norm_independent_pass"]):
        raise ValueError("CAPACITY_ORIGINAL_FULL_E_DENOMINATOR_INVALID")
    defects = [np.linalg.norm(T['full_'+s]-T['independent_'+s]) for s in "xyz"]
    input_defect = float(np.linalg.norm(defects))
    pairing = input_defect/np.sqrt(sum(np.linalg.norm(T['independent_'+s])**2 for s in "xyz"))
    if pairing>1e-10 or bridge["max_functional_transform_relative"]>1e-12:
        raise ValueError("CAPACITY_ORIGINAL_FUNCTIONAL_INTEGRAL_PAIRING_FAILED")
    bessel_energy = float(sum(np.linalg.norm(T['full_'+s])**2 for s in "xyz"))
    if bessel_energy > norm**2*(1+1e-10):
        raise ValueError("CAPACITY_BESSEL_NORMALIZATION_FAILED")
    svd_rows=[]
    for s in "xyz":
        for a in range(3):
            M=np.moveaxis(T['full_'+s],a,0).reshape(T['full_'+s].shape[a],-1)
            U, sigma, Vh=(S[f'{s}_{a}_{key}'] for key in ('U','s','Vh'))
            r=sr['spectra'][s][a]
            if (len(sigma)!=min(M.shape) or np.any(np.diff(sigma)>0) or np.any(sigma<0)
                or not np.array_equal(sigma,np.asarray(r['singular_values']))):
                raise ValueError('CAPACITY_FULL_SPECTRUM_LAYOUT_OR_TRUNCATION_FAILED')
            backward=float(np.linalg.norm((U*sigma)@Vh-M)/np.linalg.norm(M))
            orthogonal=max(float(np.linalg.norm(U.conj().T@U-np.eye(len(sigma)))),
                           float(np.linalg.norm(Vh@Vh.conj().T-np.eye(len(sigma)))))
            if max(backward,orthogonal)>1e-12:
                raise ValueError('CAPACITY_SAVED_SVD_RECONSTRUCTION_FAILED')
            svd_rows.append(dict(component=s,axis=a,backward_relative=backward,orthogonality=orthogonal))
    bounds={}
    for name,ranks in (('pure_r8',[8,64,8]),('width16',[8,17,8]),('cheb19',[8,19,8])):
        lower=independent_tail(sr['spectra'],ranks,norm,input_defect)
        expected=sr['bounds'][name]['conservative_relative_lower_estimate']
        if abs(lower-expected)>1e-13:
            raise ValueError('CAPACITY_TAIL_ENERGY_OR_FULL_DENOMINATOR_FAILED')
        bounds[name]=lower
    feature_rows={}
    cells=(8,6,8)
    for name,record in fr['records'].items():
        energies=[]
        for s in "xyz":
            tensor=T['full_'+s].copy()
            for a in range(3):
                degree=tensor.shape[a]//cells[a]-1
                Q=F[f'{name}_Q_{a}_{degree}']
                FF=F[f'{name}_F_{a}_{degree}']
                axes_record=record['axis_feature_records'][s][a]
                if axes_record['discarded_nonzero_columns']!=0 or Q.shape[1]!=min(FF.shape):
                    raise ValueError('CAPACITY_FEATURE_COLUMN_TRUNCATION_REJECTED')
                if np.linalg.norm(Q.conj().T@Q-np.eye(Q.shape[1]))>1e-12:
                    raise ValueError('CAPACITY_FEATURE_NOT_ORTHONORMAL')
                if np.linalg.norm(FF-Q@(Q.conj().T@FF))>1e-12*max(np.linalg.norm(FF),1e-30):
                    raise ValueError('CAPACITY_FEATURE_MISSING_INPUT_COLUMNS')
                matrix=np.moveaxis(tensor,a,0)
                shape=matrix.shape
                matrix=matrix.reshape(shape[0],-1)
                tensor=np.moveaxis((Q@(Q.conj().T@matrix)).reshape(shape),0,a)
            energies.append(max(0.,float(np.linalg.norm(T['full_'+s]-tensor))-input_defect)**2)
        lower=float(np.sqrt(sum(energies))/norm)
        if abs(lower-record['relative_lower_estimate'])>1e-12:
            raise ValueError('CAPACITY_FEATURE_PROJECTION_BOUND_FAILED')
        if record['pde_only_solve'] or record['production_initialization_allowed']:
            raise ValueError('CAPACITY_LABEL_OR_PRODUCTION_PROMOTION_REJECTED')
        if record['actual_FE_certificate'] and not bridge['rank_bound_transferable_to_actual_FE']:
            raise ValueError('CAPACITY_FEATURE_ACTUAL_FE_PROMOTION_REJECTED')
        feature_rows[name]=dict(relative_lower_estimate=lower,
            finite_chart_full_space_qualified=record['finite_chart_full_space_qualified'],
            actual_FE_certificate=record['actual_FE_certificate'])
    transferable=(bridge['original_J_non_diagonal_max_nm']==0 and
                  bridge['original_axis_origin_or_width_nonseparability_max_nm']==0)
    if bridge['rank_bound_transferable_to_actual_FE'] != transferable or bridge['original_J_was_zeroed']:
        raise ValueError('CAPACITY_ACTUAL_GEOMETRY_RANK_PROMOTION_REJECTED')
    margin=sr['bounds']['pure_r8']['numerical_margin']
    if not transferable:
        selected='NO_VALID_FE_CAPACITY_CERTIFICATE'
    elif bounds['pure_r8']>1e-4+margin:
        selected='R8_CAPACITY_EXCLUDED_NUMERICALLY'
    elif bounds['width16']>1e-4+margin:
        selected='WIDTH16_CAPACITY_EXCLUDED_NUMERICALLY'
    elif any(v['actual_FE_certificate'] and v['relative_lower_estimate']>1e-4+margin for v in feature_rows.values()):
        selected='FROZEN_FEATURES_CAPACITY_EXCLUDED_NUMERICALLY'
    else:
        selected='REPRESENTATION_NOT_EXCLUDED_OPTIMIZATION_UNRESOLVED'
    return dict(qualified_saved_numeric_consistency=True, decision=selected,
        actual_FE_rank_bridge_qualified=transferable, conditional_chart_bounds=bounds,
        feature_bounds=feature_rows, SVD_checks=svd_rows, reference_E_norm=norm,
        Bessel_ratio=bessel_energy/norm**2, independent_moment_pair_relative=pairing,
        numerical_margin=margin, no_solver_or_production_PASS=True,
        original_V39_numerical_FAIL_unchanged=True, result_kind='DIAGNOSTIC')
