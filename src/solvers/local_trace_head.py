"""Reuse the qualified thin LS with a canonical block decoder protocol."""

from time import perf_counter

import numpy as np

from src.solvers.orthonormal_trace_reprofile import OrthonormalTraceBasis
from src.solvers.tangent_head_model import bar_action

FAMILY = 'LOCAL_TRACE_REPRESENTATION_COMPARISON'
LIMITS = dict(local_raw_bases=2, union_bases=2, new_A_columns=10000,
              thin_LS_calls=12, thin_RHS=12, local_SVD=16, complement_SVD=2,
              original_audits=60, field_states=10)


class TraceLinearHead(OrthonormalTraceBasis):
    """Only initialization differs; old V14 solve/evaluate gates stay intact."""

    def __init__(self, packet, decoder, ports, *, count=lambda *a: None,
                 guard=lambda *a, **k: None, event=lambda *a, **k: None):
        from scipy.linalg import qr
        if decoder.shape[0] != packet.nt or not 0 < decoder.shape[1] <= 3120:
            raise ValueError('canonical local/union decoder inventory differs')
        self.packet, self.Q, self.ports = packet, decoder, ports
        self.count, self.guard = count, guard
        self.columns = decoder.shape[1]
        self.orthogonality = decoder.orthogonality()
        if self.orthogonality > 1e-10 or ports.cond_H > 1e10:
            raise ValueError('local decoder or original Hhat unqualified')
        guard(large=True, extra_actions=self.columns+5)
        count('new_A_columns', self.columns)
        self.times = {}
        began = perf_counter()
        self.A = np.empty(decoder.shape, np.complex128, order='F')
        for j in range(self.columns):
            guard(extra_actions=1)
            self.A[:, j], _ = bar_action(packet, ports, decoder.column(j))
            if j % 128 == 0 or j == self.columns-1:
                event('original_A_columns', completed=j+1, total=self.columns)
        self.times['original_barS_columns'] = perf_counter()-began
        self.pairing = self.check_pairing(self.A)
        if max(self.pairing) > 1e-10:
            raise ValueError('local/union original action pairing failed')
        guard(large=True)
        began = perf_counter()
        self.U, self.RA = qr(self.A, mode='economic', pivoting=False, check_finite=False)
        self.times['A_economic_QR_stationarity'] = perf_counter()-began

    def decomposition(self):
        return dict(family=FAMILY, actual_columns=self.columns,
                    main_forward='block_Q_times_c', raw_gamma_writeback=False,
                    Q_orthogonality=self.orthogonality, original_action_pairing=self.pairing,
                    Hhat_condition=self.ports.cond_H, basis_times_seconds=self.times,
                    exact_full_space_optimum_claimed=False,
                    payload_bytes=dict(decoder=self.Q.nbytes, A=self.A.nbytes,
                                       stationarity_U=self.U.nbytes, RA=self.RA.nbytes))
