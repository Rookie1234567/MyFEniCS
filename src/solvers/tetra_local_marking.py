"""One fixed global-denominator Dörfler marking, never a field-error oracle."""
import numpy as np


def freeze_marking(difference,reference,keys,*,theta=.5,floor=1e-12):
    d=np.asarray(difference,float);n=np.asarray(reference,float)
    if theta!=.5 or d.ndim!=2 or d.shape[1]!=3 or n.shape!=(2,) or len(keys)!=len(d):raise ValueError('fixed marking inventory')
    if not np.isfinite(d).all() or np.any(d<0) or not np.isfinite(n).all() or np.any(n<0):raise ValueError('nonnegative finite marking data')
    if len(set(keys))!=len(keys):raise ValueError('unique geometry keys required')
    denominator=np.maximum(n,floor**2);eta=d[:,:2]/denominator;eta=eta.sum(axis=1)
    total=float(eta.sum())
    if total<=0:raise ValueError('zero difference does not define an adaptive pilot')
    order=np.array(sorted(range(len(d)),key=lambda i:(-float(eta[i]),keys[i])),np.int64)
    cumulative=np.cumsum(eta[order]);count=int(np.searchsorted(cumulative,theta*total,side='left'))+1
    ids=order[:count]
    return dict(indices=ids,eta_squared=eta,order=order,reference_squared=n,denominator_squared=denominator,
        theta=theta,coverage=float(cumulative[count-1]/total),total_indicator=total,
        top_ten_percent_coverage=float(cumulative[max(0,int(np.ceil(.1*len(d)))-1)]/total),
        selected_count=count,minimum_prefix=True,indicator='discrete A/B difference; not a reliable Maxwell bound')
