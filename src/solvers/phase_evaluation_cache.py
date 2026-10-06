"""Opt-in exact field evaluation cache; the original evaluator stays an oracle.

Keys retain every reference-point bit and the actual element object. A bounded
LRU stores value/curl tables, not approximate geometry classes. Coefficients
are checked at each use, so a modified Function cannot consume a stale entry.
"""
from collections import OrderedDict
import hashlib
import numpy as np
from .phase_explicit_accuracy_fields import PhaseEvaluator
from .scattering_anchor import relative


class ExactTabulations:
    def __init__(self, limit_bytes=1024*2**20):
        self.limit_bytes=limit_bytes;self.entries=OrderedDict();self.bytes=0
        self.hits=0;self.misses=0;self.peak_bytes=0

    def get(self,element,ref):
        # Retaining element in the key prevents id reuse and binds all its
        # basis, variant, mapping and DOF-order dependencies without rounding.
        p=np.ascontiguousarray(ref)
        key=(element,p.dtype.str,p.shape,hashlib.sha256(p.tobytes()).digest(),1)
        if key in self.entries:
            self.hits+=1;value=self.entries.pop(key);self.entries[key]=value;return value
        self.misses+=1
        tab=element.tabulate(1,p)
        values=tab[0].copy()
        curls=np.stack((tab[2,:,:,2]-tab[3,:,:,1],tab[3,:,:,0]-tab[1,:,:,2],tab[1,:,:,1]-tab[2,:,:,0]),axis=2)
        del tab
        value=(values,curls);size=sum(a.nbytes for a in value)
        if size<=self.limit_bytes:
            while self.bytes+size>self.limit_bytes:
                _,old=self.entries.popitem(last=False);self.bytes-=sum(a.nbytes for a in old)
            for a in value:a.setflags(write=False)
            self.entries[key]=value;self.bytes+=size;self.peak_bytes=max(self.peak_bytes,self.bytes)
        return value

    def polynomial(self,element,ref):
        """Exact Basix polyset tables, before its fixed nodal basis matrix.

        Contracting the nodal basis matrix with this cell's coefficients first
        is the same multiplication with a different association. This avoids
        constructing all dim*3 basis values at every physical point; it is not
        interpolation or projection into another FE space.
        """
        import basix
        p=np.ascontiguousarray(ref)
        key=(element,p.dtype.str,p.shape,hashlib.sha256(p.tobytes()).digest(),1,'polyset')
        if key in self.entries:
            self.hits+=1;value=self.entries.pop(key);self.entries[key]=value;return value[0]
        self.misses+=1
        tab=basix.polynomials.tabulate_polynomial_set(element.cell_type,element.polyset_type,element.embedded_superdegree,1,p)
        size=tab.nbytes
        if size<=self.limit_bytes:
            while self.bytes+size>self.limit_bytes:
                _,old=self.entries.popitem(last=False);self.bytes-=sum(a.nbytes for a in old)
            tab.setflags(write=False);self.entries[key]=(tab,);self.bytes+=size;self.peak_bytes=max(self.peak_bytes,self.bytes)
        return tab

    def record(self):
        return dict(hits=self.hits,misses=self.misses,resident_table_bytes=self.bytes,
            peak_resident_table_bytes=self.peak_bytes,limit_bytes=self.limit_bytes,
            keys='exact element equality/hash + complete float reference point bits + derivative1')


class CachedPhaseEvaluator(PhaseEvaluator):
    def __init__(self,space,q,kappa,*,cache=None):
        super().__init__(space,q,kappa)
        self.cache=ExactTabulations() if cache is None else cache
        self.element=space.element.basix_element
        self.basis_coefficients=self.element.coefficient_matrix
        self.inverse=[np.linalg.inv(J) for J,_,_ in self.geometry]
        self.coefficients={}

    def at(self,function,c,points,k0):
        J,o,det=self.geometry[c];inv=self.inverse[c]
        ref=(points-o)@inv.T;poly=self.cache.polynomial(self.element,ref)
        info=int(self.permutations[c]);dim=self.space.element.space_dimension
        if info not in self.transforms:
            T=np.eye(dim);self.space.element.T_apply(T.ravel(),self.permutations[c:c+1],dim);self.transforms[info]=T
        raw=function.x.array[self.space.dofmap.cell_dofs(c)]
        key=(id(function),c);saved=self.coefficients.get(key)
        if saved is None or not np.array_equal(raw,saved[0]):
            coef=self.transforms[info].T@raw
            expansion=(self.basis_coefficients.T@coef).reshape(3,poly.shape[1])
            saved=(raw.copy(),coef,expansion);self.coefficients[key]=saved
        reference=np.einsum('dpq,cp->dqc',poly,saved[2])
        e=reference[0]@inv
        curls=np.column_stack((reference[2,:,2]-reference[3,:,1],reference[3,:,0]-reference[1,:,2],reference[1,:,1]-reference[2,:,0]))
        curl=curls@J.T/det
        if len(self.eval_checks)<4:
            witness=np.unique([0,len(points)//2,len(points)-1])
            native=function.eval(points[witness],np.full(len(witness),c,np.int32))
            check=relative(e[witness]-native,native);self.eval_checks.append(check)
            if check>1e-11:raise ValueError('independent native cached envelope evaluation')
        return self.physical(points,e,curl,k0)


def cached_evaluator_factory():
    cache=ExactTabulations()
    def factory(space,q,kappa):return CachedPhaseEvaluator(space,q,kappa,cache=cache)
    factory.cache=cache
    return factory
