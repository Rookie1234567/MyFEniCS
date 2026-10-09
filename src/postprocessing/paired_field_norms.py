"""Score a saved common numerator with a separately identified field norm.

The integration domain never changes when the denominator changes. Samples
are complete complex vectors, with the same original norm floor.
"""
import numpy as np

NAMES=('E_total','H_total','curl_total','E_scattered','H_scattered','curl_scattered')


def score_differences(numerator_squared,reference_squared,first_samples,second_samples):
    d=np.asarray(numerator_squared,float);r=np.asarray(reference_squared,float)
    if d.shape!=(6,) or r.shape!=(6,) or np.any(d<0) or np.any(r<0) or not np.all(np.isfinite([d,r])):
        raise ValueError('six finite nonnegative common differences and reference norms required')
    if set(first_samples)!=set(NAMES) or set(second_samples)!=set(NAMES):raise ValueError('six sample vectors required')
    fields={};selected={}
    for i,name in enumerate(NAMES):
        x=np.asarray(first_samples[name]);y=np.asarray(second_samples[name])
        if x.shape!=(240,3) or y.shape!=x.shape or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            raise ValueError('240 complete finite complex field vectors required')
        fields[name]=dict(difference_squared=float(d[i]),reference_squared=float(r[i]),relative=float(np.sqrt(d[i])/max(np.sqrt(r[i]),1e-12)))
        selected[name]=dict(difference_norm=float(np.linalg.norm(x-y)),reference_norm=float(np.linalg.norm(x)),
            relative=float(np.linalg.norm(x-y)/max(np.linalg.norm(x),1e-30)))
    return dict(fields=fields,selected=selected,field_and_selected_pass=max([v['relative'] for v in fields.values()]+[v['relative'] for v in selected.values()])<=1e-4,
        selected_denominator='first saved vector',integration_not_repeated=True)
