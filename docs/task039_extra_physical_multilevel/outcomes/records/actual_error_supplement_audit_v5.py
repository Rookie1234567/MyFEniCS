"""Saved-only correlations, coarse cancellation, spatial partitions, MR closure."""
import hashlib,json
from pathlib import Path
import numpy as np
from src.runners.physical_diagnostic_completion import load_packet
base=Path('benchmarks/artifacts/task39extra/fine_reference_followup')
primary=base/'actual_errors_v1_formal_audit.json';audit=json.loads(primary.read_text())
p=base/audit['source_sha']/'actual_errors_v1'
packet=lambda name:load_packet(p/(name+'.json'))
close=lambda x,y:np.testing.assert_allclose(x,y,rtol=1e-11,atol=1e-13)
labels=['A2R160','LIGHT448','JOINT448'];gram=packet('actual_error_M0_gram')['gram']
close(gram,gram.conj().T)
energy=gram.diagonal().real
correlation=np.abs(gram)/np.sqrt(energy[:,None]*energy[None,:])
assert np.max(correlation)<=1+1e-12
rows={}
for i,label in enumerate(labels):
    e=packet(label+'_actual_error');projection=packet(label+'_projection');coarse=packet(label+'_coarse')['result'];gap=packet(label+'_coarse_gap')
    close(energy[i],projection['error_energy'])
    gp=gap['g_parallel'];gt=gap['g_perp'];gs=gp+gt
    close(gs,coarse['g'])
    norms=[float(np.linalg.norm(v)) for v in (gp,gt,gs)]
    cross=np.vdot(gp,gt)
    close(norms[2]**2,norms[0]**2+norms[1]**2+2*cross.real)
    coupling=dict(norm_g_parallel=norms[0],norm_g_perp=norms[1],norm_sum=norms[2],
        cross=[float(cross.real),float(cross.imag)],normalized_cross_real=float(cross.real/(norms[0]*norms[1])),
        cancellation_ratio=norms[2]/(norms[0]+norms[1]),complement_to_parallel=norms[1]/norms[0],
        relative_sum_defect=float(np.linalg.norm(gs-coarse['g'])/(norms[0]+norms[1])))
    q=coarse['q'];az=coarse['applied_direction'];alpha=np.vdot(az,q)/np.vdot(az,az)
    close(alpha,complex(*coarse['alpha']))
    close(coarse['unit_true_residual_ratio'],np.linalg.norm(q-az)/np.linalg.norm(q))
    close(coarse['mr_true_residual_ratio'],np.linalg.norm(q-alpha*az)/np.linalg.norm(q))
    close(coarse['unit_field_ratio']**2,coarse['unit_remaining_energy']/coarse['original_error_energy'])
    close(coarse['mr_field_ratio']**2,coarse['mr_remaining_energy']/coarse['original_error_energy'])
    close(coarse['decomposition_right'],projection['perpendicular_energy']+gap['coarse_response_gap_energy'])
    close(gap['gap_over_complement_field_ratio']**2,gap['coarse_response_gap_energy']/projection['perpendicular_energy'])
    cells=packet(label+'_cell_energies');mass=cells['mass'];curl=cells['curl'];tags=cells['material_tags'];z=cells['cell_centers'][:,2]
    totals=dict(L2_energy=float(mass.sum()),scaled_curl_energy=float(curl.sum()))
    def group(values):
        results=[]
        for value in np.unique(values):
            mask=values==value
            results.append(dict(key=float(value),cells=int(mask.sum()),L2_energy=float(mass[mask].sum()),scaled_curl_energy=float(curl[mask].sum()),
                L2_fraction=float(mass[mask].sum()/mass.sum()),scaled_curl_fraction=float(curl[mask].sum()/curl.sum())))
        close(sum(v['L2_fraction'] for v in results),1);close(sum(v['scaled_curl_fraction'] for v in results),1)
        return results
    rows[label]=dict(coupling=coupling,coarse_MR_alpha=[float(alpha.real),float(alpha.imag)],
        total_cell_integrals=totals,materials=group(tags),height_layers_nm=group(z))
for item in audit['artifact_hashes']:
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest()==item['sha256'],item['path']
result=dict(status='SAVED_ONLY_SUPPLEMENT_PASSED',source_sha=audit['source_sha'],primary_audit_sha256=hashlib.sha256(primary.read_bytes()).hexdigest(),
    primary_artifact_hashes_rechecked=len(audit['artifact_hashes']),labels=labels,phase_invariant_M0_correlation=correlation.tolist(),
    Gram_real=gram.real.tolist(),Gram_imag=gram.imag.tolist(),rows=rows,
    material_tag_names={'1':'air','2':'Si substrate','3':'Si grating'},tag_source='src/common/config_3d.py:34-36; src/geometry/mesh_builder_3d.py:_mark_cells',
    spatial_units='centroid z in nm; fractions of total error squared norm, not norm ratios',
    metric_scope='M0 Gram and field energies measured in formal runtime; saved-only algebra, partitions and scalar ratios recomputed, no FE validation rerun',
    inherited_enum='ORIGINAL_REJECTION_NOT_REPRODUCED is inapplicable to this new actual-error g; not replay of old eighth input, no old V3/V4 negative reclassification')
(base/'actual_errors_v1_supplement_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(dict(status=result['status'],correlation=result['phase_invariant_M0_correlation'],coupling={k:v['coupling'] for k,v in rows.items()}),indent=2))
