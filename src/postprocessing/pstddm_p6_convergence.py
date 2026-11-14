"""Common physical quadrature for the bounded p6 mesh comparison.

Sampling observes the solved field. It does not modify the Maxwell operator.
The discontinuous Q6 curl representation is exact for affine hex N1curl p6;
it is not the low-order visualization interpolant.
"""
from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np


def common_axes(axis_pair):
    if len(axis_pair) != 2 or any(len(axes) != 3 for axes in axis_pair):
        raise ValueError('exactly two three-dimensional axis sets are required')
    result = []
    for first, second in zip(*axis_pair):
        a, b = np.asarray(first, dtype=float), np.asarray(second, dtype=float)
        if (a.ndim != 1 or b.ndim != 1 or len(a) < 2 or len(b) < 2
                or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b))
                or np.any(np.diff(a) <= 0) or np.any(np.diff(b) <= 0)
                or a[0] != b[0] or a[-1] != b[-1]):
            raise ValueError('ordered finite axes must share the same physical bounds')
        result.append(np.union1d(a, b))
    return result


def quadrature_blocks(axis_pair, order=8):
    """One common open subcell at a time, without dropping interface points."""
    axes = common_axes(axis_pair)
    x, w = np.polynomial.legendre.leggauss(order)
    reference = np.asarray(list(itertools.product(x, repeat=3)))
    weights = np.prod(np.asarray(list(itertools.product(w, repeat=3))), axis=1)
    for index in itertools.product(*(range(len(axis)-1) for axis in axes)):
        lo = np.asarray([axes[d][index[d]] for d in range(3)])
        hi = np.asarray([axes[d][index[d]+1] for d in range(3)])
        yield (lo+hi)/2 + reference*(hi-lo)/2, weights*np.prod((hi-lo)/2)


def _hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def save_common_field_samples(field, config, output_directory, axis_pair):
    from dolfinx import fem, geometry
    import ufl
    from src.common.analytic_fields_3d import (
        electric_field_code_values, magnetic_field_code_values,
    )
    from src.common.runtime_resource_policy import admit

    started = time.monotonic()
    mesh = field.function_space.mesh
    if mesh.comm.size != 1 or config.nedelec_degree != 6:
        raise ValueError('p6 comparison is qualified only for MPI1 and p6')
    axes = common_axes(axis_pair)
    count = int(np.prod([len(a)-1 for a in axes])) * 8**3
    # Include file-backed output pages, not just Python arrays and scratch.
    file_bytes = count*(4*3*16+3*8+8)
    ncell = mesh.topology.index_map(3).size_local
    admit('p6_common_field_samples', file_bytes+ncell*7**3*3*16+(64 << 20),
          estimate_basis='four complex fields, points/weights, DG6 curl and bounded scratch')
    output = Path(output_directory) / 'common_field_samples'
    output.mkdir(exist_ok=False)
    dg = fem.functionspace(mesh, ('DG', 6, (3,)))
    magnetic = fem.Function(dg)
    points = dg.element.interpolation_points
    if callable(points):
        points = points()
    magnetic.interpolate(fem.Expression(ufl.curl(field)/(1j*config.k0*config.mu_r), points))
    magnetic.x.scatter_forward()
    arrays = {}
    for name in ('E', 'H', 'E_scattered', 'H_scattered', 'points', 'weights'):
        shape = (count,) if name == 'weights' else (count, 3)
        dtype = np.float64 if name in ('points', 'weights') else np.complex128
        arrays[name] = np.lib.format.open_memmap(output/(name+'.npy'), mode='w+', dtype=dtype, shape=shape)
    tree = geometry.bb_tree(mesh, 3)
    offset = 0
    for physical, weights in quadrature_blocks(axis_pair):
        candidates = geometry.compute_collisions_points(tree, physical)
        hits = geometry.compute_colliding_cells(mesh, candidates, physical)
        cells = np.empty(len(physical), dtype=np.int32)
        for j in range(len(physical)):
            found = hits.links(j)
            if len(found) != 1:
                raise RuntimeError(f'common open point has {len(found)} owners: {physical[j]}')
            cells[j] = found[0]
        e = np.asarray(field.eval(physical, cells)).reshape(-1, 3)
        h = np.asarray(magnetic.eval(physical, cells)).reshape(-1, 3)
        eb = electric_field_code_values(config, physical)
        hb = magnetic_field_code_values(config, physical)
        section = slice(offset, offset+len(physical))
        values = dict(E=e, H=h, E_scattered=e-eb, H_scattered=h-hb,
                      points=physical, weights=weights)
        for name, value in values.items():
            if not np.all(np.isfinite(value)):
                raise ValueError(f'nonfinite comparison samples: {name}')
            arrays[name][section] = value
        offset += len(physical)
    if offset != count:
        raise RuntimeError('incomplete common quadrature')
    for array in arrays.values():
        array.flush()
    del array
    arrays.clear()
    record = dict(schema='pstddm.p6.common-fields.v1', count=count, order=8,
                  axes=[a.tolist() for a in axes], field='total plus flat-background-subtracted',
                  H_definition='curl(E)/(i*k0*mu_r), impedance-normalized code units',
                  elapsed_seconds=time.monotonic()-started,
                  files={p.name:dict(bytes=p.stat().st_size, sha256=_hash(p))
                         for p in sorted(output.glob('*.npy'))})
    (output/'manifest.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def compare_saved_common_fields(coarse_directory, fine_directory):
    """Stream two saved sets with a fixed fine-field denominator."""
    roots = [Path(p)/'common_field_samples' for p in (coarse_directory, fine_directory)]
    manifests = [json.loads((p/'manifest.json').read_text()) for p in roots]
    if any(manifests[0][key] != manifests[1][key] for key in ('count','order','axes','H_definition')):
        raise ValueError('common sampling identity mismatch')
    for root, manifest in zip(roots, manifests):
        for name, item in manifest['files'].items():
            if _hash(root/name) != item['sha256']:
                raise ValueError(f'saved field hash mismatch: {root/name}')
    count = manifests[0]['count']
    data = [{name:np.load(root/(name+'.npy'), mmap_mode='r')
             for name in ('E','H','E_scattered','H_scattered','points','weights')} for root in roots]
    sums = {name:[0., 0.] for name in ('E','H','E_scattered','H_scattered')}
    for start in range(0, count, 8192):
        part = slice(start, min(start+8192, count))
        for name in ('points','weights'):
            if not np.array_equal(data[0][name][part], data[1][name][part]):
                raise ValueError('common physical points/weights differ')
        weights = data[1]['weights'][part, None]
        for name, total in sums.items():
            a, b = data[0][name][part], data[1][name][part]
            total[0] += float(np.sum(weights*abs(a-b)**2))
            total[1] += float(np.sum(weights*abs(b)**2))
    result = {}
    for name, (difference, reference) in sums.items():
        relative = float(np.sqrt(difference/reference)) if reference > 0 else None
        result[name] = dict(difference_squared=difference, reference_squared=reference,
                            relative_l2=relative, passed=relative is not None and relative <= .01)
    return dict(fields=result, passed=all(item['passed'] for item in result.values()),
                reference='h7.5', finite_two_mesh_evidence_not_continuum_proof=True)


def compare_saved_port_observables(coarse_directory, fine_directory):
    """Compare every ordered channel; significant channels gate complex phase too."""
    roots = [Path(coarse_directory), Path(fine_directory)]
    ports = [json.loads((p/'port_power.json').read_text()) for p in roots]
    summaries = [json.loads((p/'run_summary.json').read_text()) for p in roots]
    def key(row):
        return row['side'], row['m'], row['n'], row['polarization']
    keys = [[key(row) for row in port['orders']] for port in ports]
    if keys[0] != keys[1] or len(set(keys[0])) != len(keys[0]) or not keys[0]:
        raise ValueError('complete ordered mode identity differs')
    for name in ('reference_planes', 'modal_amplitude_convention', 'power_source'):
        if ports[0][name] != ports[1][name]:
            raise ValueError(f'port physical convention differs: {name}')
    rows = []
    for a, b in zip(ports[0]['orders'], ports[1]['orders']):
        za, zb = (complex(*row['outgoing_amplitude_at_boundary']) for row in (a, b))
        pa, pb = float(a['power_ratio']), float(b['power_ratio'])
        if not all(np.isfinite(value) for value in (za, zb, pa, pb)):
            raise ValueError('nonfinite complete mode output')
        significant = max(pa, pb) >= 1e-6
        absolute = float(abs(za-zb))
        relative = absolute/abs(zb) if abs(zb) > 0 else (0. if absolute == 0 else None)
        rows.append(dict(key=list(key(a)), coarse_power=pa, fine_power=pb,
                         significant=significant, absolute_amplitude_difference=absolute,
                         relative_amplitude_difference=relative,
                         passed=(not significant or (relative is not None and relative <= .01))))
    powers = {}
    for name in ('R_total', 'T_total', 'A_volume_total'):
        values = [float(summary[name]) for summary in summaries]
        if not np.all(np.isfinite(values)):
            raise ValueError(f'nonfinite power: {name}')
        difference = abs(values[0]-values[1])
        powers[name] = dict(coarse=values[0], fine=values[1], difference=difference,
                            passed=difference <= 1e-3)
    closure = [abs(float(s['R_total'])+float(s['T_total'])+float(s['A_volume_total'])-1.)
               for s in summaries]
    residuals = [float(s['linear_system_relative_residual']) for s in summaries]
    physics_pass = all(v <= 1e-5 for v in closure)
    numerical_pass = all(np.isfinite(v) and v <= 1e-10 for v in residuals)
    return dict(orders=rows, powers=powers, energy_closure=closure,
                direct_original_residuals=residuals, physics_pass=physics_pass,
                numerical_pass=numerical_pass,
                passed=physics_pass and numerical_pass and all(row['passed'] for row in rows)
                       and all(row['passed'] for row in powers.values()),
                input_hashes=[{name:_hash(root/name) for name in ('port_power.json','run_summary.json')}
                              for root in roots])
