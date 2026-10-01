"""Research-only six-template raw p6 tensor; no mesh orientation or PDE qualification."""
import numpy as np
import basix

def prepare_reference_templates(builder):
    """Use independent curl/mass quadrature, reusing one rule only after exact check."""
    for component in ('curl','mass'):
        base=builder.rules_by_tag_component[(1,component)]
        for (tag,comp),rule in builder.rules_by_tag_component.items():
            if comp==component and not (rule.degree==base.degree and rule.rule==base.rule and np.array_equal(rule.points,base.points) and np.array_equal(rule.weights,base.weights)):
                raise NotImplementedError('This bounded candidate requires identical component rules across material tags')
    out=[]; dx,dy,dz=(basix.index(1,0,0),basix.index(0,1,0),basix.index(0,0,1))
    n=builder.dimension
    for component in ('curl','mass'):
        rule=builder.rules_by_tag_component[(1,component)]; mats=np.zeros((3,n,n))
        for q in range(0,len(rule.points),32):
            tab=builder.element.tabulate(1,rule.points[q:q+32]); vals=tab[0] if component=='mass' else np.stack((tab[dy,:,:,2]-tab[dz,:,:,1],tab[dz,:,:,0]-tab[dx,:,:,2],tab[dx,:,:,1]-tab[dy,:,:,0]),axis=2)
            for a in range(3):
                f=np.ascontiguousarray(vals[:,:,a]); mats[a]+=f.T@(rule.weights[q:q+32,None]*f)
        out.extend(mats)
    return np.array(out)

def combine_reference_templates(builder,templates,coordinates,tag):
    """Exact double metric; fail closed outside positive diagonal affine geometry."""
    J,d=builder._affine_jacobian(coordinates); h=np.diag(J)
    if not np.array_equal(J,np.diag(h)) or not np.all(h>0):
        raise NotImplementedError('Only positive diagonal Jacobians are covered; use qualified original fallback')
    ck,cm=builder.coefficients_by_tag[tag]; weights=np.r_[ck*h*h/d,cm*d/(h*h)]
    out=np.zeros((builder.dimension,builder.dimension),dtype=complex)
    for a in range(6): out+=weights[a]*templates[a]
    return out
