"""Frozen one-dimensional FTT hidden features, not field training or an oracle.

Near-related columns remain in the space. One 80-decimal QR checks the whole
finite functional matrix; no threshold scan, ridge, or column deletion.
"""

import numpy as np


def frozen_axis_functions(model, axis, values):
    """The actual last hidden functions plus the constant, no output weights."""
    import torch

    coordinates = torch.as_tensor(values, dtype=torch.float64).reshape(-1, 1)
    with torch.no_grad():
        hidden = model.cores[axis][:4](coordinates).numpy()
    return np.column_stack((hidden, np.ones(len(values))))


def functional_features(model, axis, bounds, cells, degree, *, high_precision=True):
    """Original q30 one-dimensional Gauss functional on a Cartesian chart.

The chart and finite nodes are declared explicitly. It does not silently
replace the original, slightly nonseparable physical mapping.
"""
    import mpmath as mp

    mp.mp.dps = 80
    nodes, weights = np.polynomial.legendre.leggauss(16)
    nodes, weights = (nodes+1)/2, weights/2
    width = (bounds[1]-bounds[0])/cells
    coordinates = np.concatenate([bounds[0]+(c+nodes)*width for c in range(cells)])
    normalized = (coordinates-float(model.center[axis]))/float(model.half_width[axis])
    values = frozen_axis_functions(model, axis, normalized)
    legendre = np.polynomial.legendre.legvander(2*nodes-1, degree)
    W = (legendre*np.sqrt(2*np.arange(degree+1)+1))*weights[:, None]*np.sqrt(width)
    F_double = np.einsum("np,cnk->cpk", W, values.reshape(cells, len(nodes), -1)).reshape(cells*(degree+1), -1)
    if not high_precision:
        return F_double, None
    arrays = {k: p.detach().numpy() for k, p in model.cores[axis].state_dict().items()}
    exact = []
    for v in normalized:
        h1 = [mp.sin(mp.mpf(float(arrays['0.weight'][i, 0]))*mp.mpf(float(v))
                     +mp.mpf(float(arrays['0.bias'][i]))) for i in range(16)]
        h2 = [mp.sin(mp.fsum(mp.mpf(float(arrays['2.weight'][i, j]))*h1[j]
                                  for j in range(16))+mp.mpf(float(arrays['2.bias'][i])))
              for i in range(16)]
        exact.append(h2+[mp.mpf(1)])
    F = mp.matrix(F_double.shape[0], F_double.shape[1])
    for c in range(cells):
        for d in range(degree+1):
            for feature in range(17):
                F[c*(degree+1)+d, feature] = mp.fsum(
                    mp.mpf(float(W[n, d]))*exact[c*len(nodes)+n][feature]
                    for n in range(len(nodes)))
    return F_double, F


def complete_feature_basis(F_double, F_high=None):
    """Preserve all columns, or all rows when the space is surjective.

The result is a finite-functionals mathematical space with conditioning
qualifications, never a proof that the entire floating FE implementation has
the same subspace for arbitrary unconstrained output amplitudes.
"""
    import mpmath as mp

    F_double = np.asarray(F_double, dtype=np.float64)
    left, sigma, right = np.linalg.svd(F_double, full_matrices=False)
    backward = float(np.linalg.norm((left*sigma)@right-F_double))
    norm = float(np.linalg.norm(F_double))
    defect = 64*np.finfo(float).eps*norm + backward
    row_count, column_count = F_double.shape
    high_singular = None
    if row_count <= column_count and sigma[-1] > defect:
        basis = np.eye(row_count, dtype=np.complex128)
        method = "FULL_ROW_SPACE_NO_COLUMN_TRUNCATION"
        high_precision_qualified = True
    elif F_high is not None:
        mp.mp.dps = 80
        S = mp.svd(F_high, compute_uv=False)
        high_singular = [mp.nstr(v, 30) for v in S]
        high_precision_qualified = all(v > mp.mpf('1e-65')*mp.norm(F_high) for v in S)
        # Tall QR is allowed to produce a small full row Q (at most24x24),
        # never a full global FE Q. Retain ALL input columns.
        if row_count <= column_count:
            basis = np.eye(row_count, dtype=np.complex128)
            method = "MPMATH80_FULL_ROW_SVD_NO_TRUNCATION" if high_precision_qualified else "UNQUALIFIED_FULL_ROW_SUPERSPACE_NO_EXCLUSION"
        else:
            Q, _ = mp.qr(F_high)
            basis = np.asarray([[complex(Q[i, j]) for j in range(column_count)]
                                for i in range(row_count)], dtype=np.complex128)
            method = "MPMATH80_COMPLETE_COLUMN_QR_NO_TRUNCATION"
    else:
        basis, _ = np.linalg.qr(F_double, mode="reduced")
        method = "DOUBLE_COMPLETE_COLUMN_QR_CONDITION_LIMITED"
        high_precision_qualified = bool(sigma[-1] > defect)
    orthogonality = float(np.linalg.norm(basis.conj().T@basis-np.eye(basis.shape[1])))
    reconstruction = float(np.linalg.norm(F_double-basis@(basis.conj().T@F_double))/max(norm, 1e-300))
    return basis, dict(shape=list(F_double.shape), singular_values=sigma.tolist(),
        high_precision_singular_values=high_singular,
        retained_dimension=basis.shape[1], discarded_nonzero_columns=0,
        relative_backward_error=backward/max(norm, 1e-300),
        measured_double_input_defect=defect, method=method,
        smallest_to_input_defect_ratio=float(sigma[-1]/max(defect,1e-300)),
        orthogonality_defect=orthogonality, full_column_reconstruction_relative=reconstruction,
        finite_functional_space_qualified=bool(high_precision_qualified and orthogonality<=1e-12 and reconstruction<=1e-12),
        conditioning_limited_for_actual_FP64_functions=bool(sigma[-1]<=defect),
        actual_FP64_arbitrary_output_certificate=bool(sigma[-1]>defect),
        finite_chart_versus_physical_FE_distinguished=True,
        new_output_coefficients_generated=False)


def feature_spaces(model, tensors, bounds, cells):
    bases, records, arrays = {}, {}, {}
    cache = {}
    for component, label in enumerate("xyz"):
        bases[label], records[label] = [], []
        for axis in range(3):
            degree = tensors[label].shape[axis]//cells[axis]-1
            key = (axis, degree)
            if key not in cache:
                F, high = functional_features(model, axis, bounds[axis], cells[axis], degree)
                cache[key] = complete_feature_basis(F, high)
                arrays[f"F_{axis}_{degree}"] = F
                arrays[f"Q_{axis}_{degree}"] = cache[key][0]
            Q, report = cache[key]
            bases[label].append(Q)
            records[label].append(dict(report, axis=axis, component=label))
    return bases, records, arrays


def chebyshev_spaces(tensors, bounds, cells):
    bases, records, arrays, cache = {}, {}, {}, {}
    nodes, weights = np.polynomial.legendre.leggauss(16)
    nodes, weights = (nodes+1)/2, weights/2
    for component, label in enumerate("xyz"):
        bases[label], records[label] = [], []
        for axis in range(3):
            degree = tensors[label].shape[axis]//cells[axis]-1
            key = (axis, degree)
            if key not in cache:
                width = (bounds[axis][1]-bounds[axis][0])/cells[axis]
                coordinates = np.concatenate([bounds[axis][0]+(c+nodes)*width for c in range(cells[axis])])
                normalized = 2*(coordinates-bounds[axis][0])/(bounds[axis][1]-bounds[axis][0])-1
                values = np.polynomial.chebyshev.chebvander(normalized,18).reshape(cells[axis],len(nodes),19)
                W = (np.polynomial.legendre.legvander(2*nodes-1,degree)*np.sqrt(2*np.arange(degree+1)+1))*weights[:,None]*np.sqrt(width)
                F = np.einsum("np,cnk->cpk",W,values).reshape(cells[axis]*(degree+1),19)
                cache[key] = complete_feature_basis(F)
                arrays[f"F_{axis}_{degree}"] = F
                arrays[f"Q_{axis}_{degree}"] = cache[key][0]
            Q, report = cache[key]
            bases[label].append(Q)
            records[label].append(dict(report, axis=axis,component=label))
    return bases, records, arrays
