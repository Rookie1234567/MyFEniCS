"""The two setup representatives come only from frozen nonzero support."""

import numpy as np

from src.runners.physical_p4_schur_v14 import _q3_representative_patches


def test_zero_port_entries_cannot_choose_the_dtn_representative():
    patches = (np.array([0, 1, 2, 3]), np.array([0, 2, 4]), np.array([4, 5]))
    ports = [{'b_gamma': np.array([0, 1, 2, 4]),
              'b_values': np.array([0., 0., 0., 1.+2j]),
              'd_gamma': np.array([0, 1, 2, 5]),
              'd_values': np.array([0., 0., 0., 2.-1j])}]
    largest, dtn, facts = _q3_representative_patches(patches, ports)
    assert (largest, dtn) == (0, 2)
    assert facts['nonzero_dtn_support_counts'] == [0, 1, 2]
