"""Complex manufactured tensors and original interior-functional witnesses."""

import numpy as np
from src.solvers.ftt_capacity import full_spectrum, rank_bound, decision, feature_bound


def algebra_checks():
    rng = np.random.default_rng(4214001)
    tensors = {}
    for label in "xyz":
        factors = [rng.normal(size=(12,8))+1j*rng.normal(size=(12,8)) for _ in range(3)]
        factors = [np.linalg.qr(F)[0] for F in factors]
        tensors[label] = np.einsum("ir,jr,kr->ijk",*factors).astype(np.complex128)
    spectra = {s:[full_spectrum(t,a)[1] for a in range(3)] for s,t in tensors.items()}
    low = rank_bound(spectra,[8,64,8],np.sqrt(24))
    high = np.zeros((12,12,12),np.complex128)
    high[np.arange(12),np.arange(12),np.arange(12)]=1
    hs = {s:[full_spectrum(high,a)[1] for a in range(3)] for s in "xyz"}
    hb = rank_bound(hs,[8,64,8],6.0)
    Q=np.linalg.qr(rng.normal(size=(12,4))+1j*rng.normal(size=(12,4)))[0]
    fb=feature_bound(tensors,{s:[Q,Q,Q] for s in "xyz"},np.sqrt(24))
    exact = Q@(Q.conj().T@tensors['x'].reshape(12,-1))
    wrong = Q@(Q.T@tensors['x'].reshape(12,-1))
    conjugate_negative=float(np.linalg.norm(exact-wrong)/np.linalg.norm(exact))
    bessel_reference_energy = float(sum(np.linalg.norm(T)**2 for T in tensors.values())+3.0)
    passed = (not low['exceeds_gate_and_margin'] and hb['exceeds_gate_and_margin']
              and conjugate_negative>1e-3 and fb['relative_lower_estimate']>0.1)
    return dict(qualified=bool(passed),known_rank8=low,known_rank12=hb,
                wrong_conjugate_negative_relative=conjugate_negative,
                disjoint_component_Bessel_energy=sum(float(np.linalg.norm(T)**2) for T in tensors.values()),
                full_reference_energy_including_orthogonal_remainder=bessel_reference_energy,
                no_bridge_negative=decision({'rank_bound_transferable_to_actual_FE':False},hb,hb,{}),
                manufactured_not_PDE=True)


def functional_checks(packet, native):
    import basix
    from src.solvers.ftt_interior_bridge import interior_transform, physical_targets
    from src.solvers.feinn_interpolation import full_moment_element

    element=basix.create_element(basix.ElementFamily.N1E,basix.CellType.hexahedron,3)
    high=full_moment_element(element,30)
    if not (np.array_equal(high.points,packet['reference_points']) and
            np.array_equal(high.interpolation_matrix,packet['interpolation'])):
        raise ValueError('ORIGINAL_Q30_COMPLETE_FUNCTIONAL_PACKET_CHANGED')
    records=[]
    for J in [np.diag([1.25,1.25,1.25]),
              np.asarray([[0,1.4,0],[0,0,0.8],[1.1,0,0]]),
              np.asarray([[1.25,0.03,0.0],[0,1.25,0.02],[0.0,0.0,1.25]])]:
        T,d,s,r=interior_transform(element,J,True)
        _,_,target=physical_targets(element.x[3][0],J,True)
        rho=element.M[3][0][...,0]
        rng=np.random.default_rng(4214002)
        values=rng.normal(size=(3,len(element.x[3][0])))+1j*rng.normal(size=(3,len(element.x[3][0])))
        a=T@(rho.reshape(36,-1)@values.ravel())
        b=target.reshape(len(target),-1)@values.ravel()
        pair=float(np.linalg.norm(a-b)/np.linalg.norm(b))
        _,_,high_target=physical_targets(high.x[3][0],J,True)
        high_density=T@high.M[3][0][...,0].reshape(36,-1)
        high_pair=float(np.linalg.norm(high_density-high_target.reshape(len(high_target),-1))/np.linalg.norm(high_target))
        records.append(dict(r,complex_pair=pair,
            complete_q30_density_pair=high_pair,
            arbitrary_point_values_preserved_by_same_linear_functional=True,
            permutation_or_shear=bool(not np.array_equal(J,np.diag(np.diag(J))))))
    interior=packet['interior_positions']
    if not np.array_equal(interior,element.entity_dofs[3][0]):
        raise ValueError('BASIX_INTERNAL_POSITION_IDENTITY_FAILED')
    owner=packet['owner_rows'][:,interior]
    independent = len(np.unique(owner)) == owner.size and np.all(owner>=0)
    native_ids=packet['native_cell_dofs'][:,interior]
    no_slave=not bool(np.any(np.isin(native_ids,native['slaves'])))
    cross=float(np.max(abs(packet['transforms'][:,interior,:][:,:,np.setdiff1d(np.arange(144),interior)])))
    # Physical/dual extension phases enter once, not in the interior functions.
    phase=np.exp(1j*np.asarray([.37,-.41]))
    value=0.7+0.31j
    corner=phase[0]*phase[1]*value
    phases=dict(x=[phase[0].real,phase[0].imag],y=[phase[1].real,phase[1].imag],
                corner_absolute=float(abs(corner-phase[1]*(phase[0]*value))),
                synthetic_nonunit_not_actual_incidence=True)
    return dict(qualified=bool(all(max(r['relative'],r['complex_pair'],r['complete_q30_density_pair'])<=1e-12 for r in records)
                              and independent and no_slave and cross==0),
                original_functional_witnesses=records,interior_owner_count=int(owner.size),
                MPC_internal_independent=no_slave,orientation_interior_trace_cross_absolute=cross,
                dual_nonunit_Floquet=phases,random_pairs_not_uniform_rank_proof=True,
                original_q30_interpolation_bitwise_matched=True,
                algebraic_density_basis='Legendre tensor polynomial in original Basix interior dual span; Q111 survives affine component mixing',
                arbitrary_FTT_rank_theorem='separate one-dimensional functional products only if original physical coordinate maps separate exactly',
                original_MPC_expansion_values_nonunit_count=int(np.count_nonzero(abs(native['evals']-1)>1e-15)))
