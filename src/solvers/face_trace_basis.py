"""Geometric, positive tangential-mass complement in a fixed micro space.

The original columns are kept verbatim. No field/error or amplitude-based
rank decision enters this construction. Only affine hex Nedelec faces apply.
"""
import hashlib
import numpy as np
from scipy.linalg import cholesky, qr, solve_triangular
from .scattering_anchor import relative, array_hash
from .subcell_response_kernel import transform


def mass_complement(P, G):
    P=np.asarray(P,complex);G=np.asarray(G,complex)
    n,k=P.shape
    if G.shape!=(n,n) or not np.isfinite(P).all() or not np.isfinite(G).all():raise ValueError('finite face mass inventory')
    hermitian=relative(G-G.conj().T,G)
    if hermitian>1e-12:raise ValueError('physical face Gram must be Hermitian')
    L=cholesky(G,lower=True,check_finite=True)
    Q,R=qr(L.conj().T@P,mode='full',pivoting=False,check_finite=True)
    # Fixed full column qualification; no truncation, pseudoinverse or scan.
    cond=float(np.linalg.cond(R[:k,:]))
    if not np.isfinite(cond) or cond>1e10:raise ValueError('original face columns not safely independent')
    Z=solve_triangular(L.conj().T,Q[:,k:],lower=False)
    cross=relative(P.conj().T@G@Z,np.abs(P).T@np.abs(G)@np.abs(Z))
    orth=relative(Z.conj().T@G@Z-np.eye(n-k),np.eye(n-k))
    reconstruct=relative(L.conj().T@P-Q[:,:k]@R[:k],L.conj().T@P)
    check=dict(original_columns=k,complement_columns=n-k,micro_columns=n,
        Hermitian_operation=hermitian,original_R_condition=cond,
        mass_cross_operation=cross,mass_orthogonality=orth,QR_reconstruction=reconstruct,
        original_verbatim_sha256=array_hash(P),positive_cholesky=True,rank_truncated=False)
    check['pass_gate']=max(cross,orth,reconstruct)<=1e-10
    if not check['pass_gate']:raise ValueError('geometric face complement not qualified')
    for a in (P,G,Z):a.setflags(write=False)
    return Z,check


def face_rows(V,layout,axis,side):
    """Complete face moments plus interior face-edge moments, no perimeter."""
    import basix
    ref=basix.cell.geometry(basix.CellType.hexahedron)
    top=basix.cell.topology(basix.CellType.hexahedron);el=V.element.basix_element
    lo,hi=layout.bounds;plane=lo[axis] if side==0 else hi[axis];rows=set();faces=[]
    for c,local in zip(layout.cells,layout.child_rows,strict=True):
        xyz=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];a=xyz.min(axis=0);h=xyz.max(axis=0)-a;verts=a+ref*h
        for e,vs in enumerate(top[2]):
            if np.all(verts[vs,axis]==plane):
                rows.update(map(int,local[el.entity_dofs[2][e]]));faces.append((int(c),local,e))
        for e,vs in enumerate(top[1]):
            p=verts[vs]
            if not np.all(p[:,axis]==plane):continue
            perimeter=any(np.all(p[:,j]==v) for j in range(3) if j!=axis for v in (lo[j],hi[j]))
            if not perimeter:rows.update(map(int,local[el.entity_dofs[1][e]]))
    if len(rows)!=264 or len(faces)!=4:raise ValueError('actual macro face zero-perimeter inventory is not 264/four')
    if not set(rows).issubset(set(map(int,layout.boundary))):raise ValueError('face selected an internal macro row')
    return np.asarray(sorted(rows),int),faces


def physical_gram(V,layout,axis,selected,faces,coefficient,q=15):
    """Physical two-component L2 mass on the four original micro faces."""
    import basix
    points,weights=basix.make_quadrature(basix.CellType.quadrilateral,q)
    ref=basix.cell.geometry(basix.CellType.hexahedron);top=basix.cell.topology(basix.CellType.hexahedron)
    el=V.element.basix_element;position={int(r):i for i,r in enumerate(selected)}
    G=np.zeros((264,264),complex);free=[j for j in range(3) if j!=axis]
    for c,local,face in faces:
        xyz=V.mesh.geometry.x[V.mesh.geometry.dofmap[c]];h=xyz.max(axis=0)-xyz.min(axis=0)
        pp=np.zeros((len(points),3));pp[:,axis]=ref[top[2][face][0],axis];pp[:,free]=points
        keep=np.asarray([j for j,r in enumerate(local) if int(r) in position],int)
        ids=np.asarray([position[int(local[j])] for j in keep],int)
        # Native coefficients = T * reference coefficients. Test conjugate
        # and periodic coefficients are included in the physical Gram once.
        T=transform(V,c)
        b=np.einsum('qjc,jk->qkc',el.tabulate(0,pp)[0],T.T[:,keep])/h
        b=b[:,:,free]*np.asarray(coefficient)[ids][None,:,None]
        mass=np.prod(h[free])*np.einsum('q,qic,qjc->ij',weights,np.conj(b),b)
        G[np.ix_(ids,ids)]+=mass
    return G


def signature(*arrays):
    return hashlib.sha256(''.join(array_hash(np.asarray(a)) for a in arrays).encode()).hexdigest()


def dense_face_witness(seed=6101):
    """Nested old/new space, non-Hermitian body, nonmutual 40-port load."""
    rng=np.random.default_rng(seed);ni,nt,old,ports=5,8,3,40
    P=rng.normal(size=(nt,old))+1j*rng.normal(size=(nt,old))
    g=rng.normal(size=(nt,nt))+1j*rng.normal(size=(nt,nt));G=g.conj().T@g+np.eye(nt)
    Z,check=mass_complement(P,G);R=np.c_[P,Z[:,:2]]
    A=rng.normal(size=(ni+nt+ports,)*2)+1j*rng.normal(size=(ni+nt+ports,)*2)+50*np.eye(ni+nt+ports)
    b=rng.normal(size=len(A))+1j*rng.normal(size=len(A))
    from scipy.linalg import block_diag
    J=block_diag(np.eye(ni),R,np.eye(ports));x=np.linalg.solve(J.conj().T@A@J,J.conj().T@b);u=J@x
    Ai=A[:ni,:ni];S=A[ni:,ni:]-A[ni:,:ni]@np.linalg.solve(Ai,A[:ni,ni:]);f=b[ni:]-A[ni:,:ni]@np.linalg.solve(Ai,b[:ni])
    B=block_diag(R,np.eye(ports));z=np.linalg.solve(B.conj().T@S@B,B.conj().T@f)
    v=np.r_[np.linalg.solve(Ai,b[:ni]-A[:ni,ni:]@(B@z)),B@z]
    residual=b-A@v
    return dict(complement=check,recovery=relative(u-v,u),mixed=relative(J.conj().T@residual,J.conj().T@b),
        ambient=relative(residual,b),nonzero_internal=True,nonzero_40port=True,
        wrong_transpose=relative(B.T@S@B-B.conj().T@S@B,B.conj().T@S@B))
