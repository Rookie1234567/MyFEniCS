"""Streamed native full3D/two-cell transport for the fixed p4 audit fixture.

All entity channels and both branches survive. No full-Ny R/F/Q/S is formed.
The complete original FE vectors remain the outer equation's coordinates.
"""
from __future__ import annotations

import numpy as np


class TwoCellNativeTransport:
    def __init__(self, full_entities, local_entities, *, twist_index, eta, global_phase, global_ky, global_period_y, direct_profile=None):
        if direct_profile is not None:
            from .y_orbit_direct_profile import direct_profile_metadata
            profile = direct_profile_metadata(direct_profile)
            if (type(twist_index) is not int or twist_index not in range(profile.replication_count)
                    or full_entities.ny != profile.ny or local_entities.ny != 2
                    or full_entities.width != profile.rows_per_q or local_entities.width != profile.rows_per_q
                    or len(full_entities.independent) != profile.independent_rows
                    or len(local_entities.independent) != profile.local_independent_rows
                    or full_entities.full_rows != profile.storage_rows or local_entities.full_rows != profile.local_storage_rows
                    or full_entities.dimension_counts.get(3) != profile.interior_rows
                    or local_entities.dimension_counts.get(3) != profile.local_interior_rows
                    or full_entities.bases != local_entities.bases or full_entities.slots != local_entities.slots
                    or getattr(full_entities, "_transform_bank", None) is None
                    or full_entities._transform_bank is not local_entities._transform_bank):
                raise ValueError("reviewed direct profile requires complete shared-bank full/local entity inventories")
        elif (twist_index not in (0,1) or full_entities.ny!=4 or local_entities.ny!=2
                or len(full_entities.independent)!=15872 or len(local_entities.independent)!=7936
                or full_entities.width!=local_entities.width or full_entities.bases!=local_entities.bases
                or full_entities.slots!=local_entities.slots
                or full_entities.dimension_counts.get(3)!=8640
                or local_entities.dimension_counts.get(3)!=4320):
            raise ValueError("fixed same80/two40 p4 complete entity/branch inventory required")
        self.full,self.local=full_entities,local_entities
        self.b,self.K,self.eta=int(twist_index),2 if direct_profile is None else profile.replication_count,complex(eta)
        self.ny=full_entities.ny
        self.full_independent_rows=len(full_entities.independent)
        self.local_independent_rows=len(local_entities.independent)
        self.direct_profile_name=None if direct_profile is None else profile.name
        self.tau=self.eta**2
        expected=np.exp(1j*(complex(global_ky).real*float(global_period_y)+2*np.pi*self.b)/self.ny)
        if (abs(complex(global_ky).imag)>1e-12 or abs(self.eta-expected)>1e-12
                or abs(np.exp(1j*complex(global_ky).real*float(global_period_y))-complex(global_phase))>1e-12):
            raise ValueError("branch phase must come from original physical ky/period, never principal sqrt(tau)")
        if (not np.isfinite(self.eta) or abs(abs(self.eta)-1)>1e-12
                or abs(self.tau**self.K-complex(global_phase))>1e-12):
            raise ValueError("global eigenphase must retain local twist and full cycle")
        if (not np.array_equal(full_entities.y_widths[:2],local_entities.y_widths)
                or np.ptp(full_entities.y_widths)/np.mean(full_entities.y_widths)>1e-12):
            raise ValueError("actual complete y-cell metrics must be audited, never silently rounded")
        self.audit={"twist_index":self.b,"global_q_branches":[self.b,self.b+self.K],
                    "eta":[self.eta.real,self.eta.imag],"tau":[self.tau.real,self.tau.imag],
                    "K":self.K,"global_matrices_created":False,"all_internal_channels_retained":True,
                    "raw_native_unitarity_assumed":False,"physical_dimension_reduced":False}

    def _fold_canonical(self, full, *, dual):
        full=np.asarray(full)
        shape=(self.ny,self.full.width)+full.shape[1:]
        values=full.reshape(shape)
        result=np.empty((2,self.local.width)+full.shape[1:],dtype=complex)
        phase=np.conj(self.tau) if dual else self.tau
        for a in range(2):
            if self.direct_profile_name is None:
                result[a]=(values[a]+phase*values[2+a])/np.sqrt(self.K)
            else:
                result[a]=sum(phase**s*values[2*s+a] for s in range(self.K))/np.sqrt(self.K)
        return result.reshape((self.local_independent_rows,)+full.shape[1:])

    def fold_dual(self, full_native):
        canonical=self.full.transform(full_native,direction="dual_to_canonical")
        return self.local.transform(self._fold_canonical(canonical,dual=True),direction="dual_from_canonical")

    def lift_primal(self, local_native):
        canonical=self.local.transform(local_native,direction="primal_to_canonical")
        values=canonical.reshape((2,self.local.width)+canonical.shape[1:])
        full=np.empty((self.ny,self.full.width)+canonical.shape[1:],dtype=complex)
        for s in range(self.K):full[2*s:2*s+2]=(self.tau**s/np.sqrt(self.K))*values
        return self.full.transform(full.reshape((self.full_independent_rows,)+canonical.shape[1:]),direction="primal_from_canonical")

    def extract_primal(self, full_native):
        canonical=self.full.transform(full_native,direction="primal_to_canonical")
        return self.local.transform(self._fold_canonical(canonical,dual=True),direction="primal_from_canonical")

    def fold_raw_coupling(self, full_C):
        # Auxiliary lift alpha_full=beta_local/sqrtK, after dual FE folding.
        return self.fold_dual(full_C)/np.sqrt(self.K)

    def fold_raw_projection(self, full_D):
        # D already contains its physical conjugation: row action is D*P,
        # requiring transpose moment transport, not a second conjugation.
        canonical=self.full.transform(full_D,direction="functional_to_canonical")
        return self.local.transform(self._fold_canonical(canonical,dual=False),
                                   direction="functional_from_canonical")/np.sqrt(self.K)

    def _lift_canonical(self, local, *, conjugate_phase=False):
        local=np.asarray(local)
        values=local.reshape((2,self.local.width)+local.shape[1:])
        full=np.empty((self.ny,self.full.width)+local.shape[1:],dtype=complex)
        phase=np.conj(self.tau) if conjugate_phase else self.tau
        for s in range(self.K):full[2*s:2*s+2]=phase**s*values/np.sqrt(self.K)
        return full.reshape((self.full_independent_rows,)+local.shape[1:])

    def lift_dual(self, local_native):
        canonical=self.local.transform(local_native,direction="dual_to_canonical")
        return self.full.transform(self._lift_canonical(canonical),direction="dual_from_canonical")

    def lift_raw_coupling(self, local_C):
        return np.sqrt(self.K)*self.lift_dual(local_C)

    def lift_raw_projection(self, local_D):
        canonical=self.local.transform(local_D,direction="functional_to_canonical")
        return np.sqrt(self.K)*self.full.transform(
            self._lift_canonical(canonical,conjugate_phase=True),direction="functional_from_canonical")

    def local_branch_primal(self, branch, canonical_values):
        if branch not in (0,1):raise ValueError("both local branches have explicit indices0/1")
        values=np.asarray(canonical_values,dtype=complex)
        if values.ndim not in (1,2) or values.shape[0]!=self.local.width:
            raise ValueError("all within-cell branch channels required")
        paired=np.concatenate((values,(-1)**branch*self.eta*values),axis=0)/np.sqrt(2)
        return self.local.transform(paired,direction="primal_from_canonical")
