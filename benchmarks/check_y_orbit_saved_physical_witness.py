"""Read-only saved-array products: no PDE assembly, factor, solve or SVD."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(repo, output):
    current = repo / 'benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_sparse_p2_phi5_attempt1'
    prior = repo / 'benchmarks/artifacts/task40extra_dot_parallel_cloud/y_orbit_p2_phi5_attempt1'
    report = json.loads((current / 'probe_report.json').read_text())
    old_report = json.loads((prior / 'pilot_report.json').read_text())
    reads = []

    def load(root, manifest, label, mmap=False):
        descriptor = manifest['artifacts'][label]
        path = root / descriptor['path']
        digest = sha(path)
        if digest != descriptor['file_sha256']:
            raise ValueError('artifact SHA256 mismatch: ' + label)
        array = np.load(path, allow_pickle=False, mmap_mode='r' if mmap else None)
        if list(array.shape) != descriptor['shape'] or str(array.dtype) != descriptor['dtype']:
            raise ValueError('artifact shape/dtype mismatch: ' + label)
        reads.append({'role': 'current' if root == current else 'prior', 'label': label,
                      'path': str(path.relative_to(repo)), 'sha256': digest,
                      'shape': list(array.shape), 'dtype': str(array.dtype)})
        return array

    def csr(label, shape):
        return sparse.csr_matrix((load(current, report, label + '_data'),
                                  load(current, report, label + '_indices'),
                                  load(current, report, label + '_indptr')), shape=shape)

    matrix = csr('reference_S', (2100, 2100))
    block = csr('q_0_S', (468, 468))
    trace_positions = load(current, report, 'trace_full_independent_trace_positions')
    interior_positions = np.setdiff1d(np.arange(2048), trace_positions)
    r = csr('trace_R_t', (1568, 1568))
    ri = csr('trace_R_t_inverse', (1568, 1568))
    fourier = csr('trace_F_t', (1568, 1568))
    port_q = load(current, report, 'port_q_labels')
    rhs = load(prior, old_report, 'physical_rhs', True)
    field = load(prior, old_report, 'A0_direct_physical', True)
    original = load(prior, old_report, 'A0_original', True)
    h = matrix[1568:, 1568:].diagonal()
    coupling = matrix[:1568, 1568:]
    projection = -matrix[1568:, :1568]
    projected = projection @ field[trace_positions]
    # Recover explicit diagonal auxiliary coordinates of an ALREADY SAVED
    # field, not an inverse application or a new block solve.
    alpha = projected / h
    residual = matrix @ np.concatenate((field[trace_positions], alpha)) - np.concatenate((rhs[trace_positions], np.zeros(532)))
    z_trace = (fourier.conj().T @ (ri @ field[trace_positions]))[:392]
    modal_rhs = ((r @ fourier).conj().T @ rhs[trace_positions])[:392]
    q0_ports = np.flatnonzero(port_q == 0)
    q0_residual = block @ np.concatenate((z_trace, alpha[q0_ports])) - np.concatenate((modal_rhs, np.zeros(76)))
    zero_c = np.asarray(abs(coupling).sum(axis=0)).ravel() == 0
    zero_d = np.asarray(abs(projection).sum(axis=1)).ravel() == 0
    zero_q0 = np.flatnonzero(zero_c[q0_ports] & zero_d[q0_ports])
    mode_keys = old_report['ports']['alias_groups']['0']
    zero_modes = [{**mode_keys[int(i)], 'q0_local_slot': int(i),
                   'actual_H': float(h[q0_ports[i]].real)} for i in zero_q0]
    events = [json.loads(line) for line in (current / 'probe_events.jsonl').read_text().splitlines()]
    port_admission = [entry for entry in events if entry.get('boundary') == 'complete_port_terms']
    result = {
        'schema': 'task40extra.sparse-p2.readonly-saved-witness.v1',
        'purpose': 'distinguish_saved_condensed_algebra_from_raw_auxiliary_scaling_failure',
        'operation_scope': ['artifact_hash_and_dtype_checks', 'sparse_and_dense_saved_matrix_products',
                            'diagonal_auxiliary_recovery_of_old_saved_field', 'norms_and_support_counts'],
        'PDE_assembly_factor_solve_SVD': False,
        'raw_block_gate_status': 'FAILED_PRESERVED', 'raw_failure': report['error'],
        'new_run_source_head': 'f2bd95ba813b3243bdfd052e90c53ccb0cf0e006',
        'prior_source_head': 'ac1410ca1187352fbe398325c5f7aaa33bf0d0bd',
        'input_manifest_hashes': {
            'current_report': sha(current / 'probe_report.json'),
            'current_provenance': sha(current / 'provenance.json'),
            'current_summary': sha(current / 'summary.json'),
            'prior_report': sha(prior / 'pilot_report.json'),
            'prior_provenance': sha(prior / 'provenance.json'),
            'prior_checker': sha(prior / 'independent_checker.json')},
        'read_artifacts': reads,
        'measured': {
            'full_H_min': float(abs(h).min()), 'full_H_max': float(abs(h).max()),
            'q0_H_min': float(abs(h[q0_ports]).min()), 'q0_H_max': float(abs(h[q0_ports]).max()),
            'Hhat_offdiagonal_nonzero_entries': int((matrix[1568:, 1568:] - sparse.diags(h)).count_nonzero()),
            'full_zero_C_columns': int(zero_c.sum()), 'full_zero_D_rows': int(zero_d.sum()),
            'q0_joint_zero_C_D_modes': zero_modes,
            'physical_original_interior_RHS_norm': float(np.linalg.norm(rhs[interior_positions])),
            'physical_original_interior_RHS_max': float(abs(rhs[interior_positions]).max()),
            'old_original_true_residual': float(np.linalg.norm(original @ field - rhs) / np.linalg.norm(rhs)),
            'saved_field_condensed_FE_relative': float(np.linalg.norm(residual[:1568]) / np.linalg.norm(rhs)),
            'saved_field_condensed_port_relative': float(np.linalg.norm(residual[1568:]) / np.linalg.norm(projected)),
            'saved_field_q0_FE_relative': float(np.linalg.norm(q0_residual[:392]) / np.linalg.norm(modal_rhs)),
            'saved_field_q0_port_relative': float(np.linalg.norm(q0_residual[392:]) /
                                                np.linalg.norm(block[392:, :392] @ z_trace)),
            'saved_physical_alpha_norm': float(np.linalg.norm(alpha)),
            'saved_physical_alpha_finite': bool(np.isfinite(alpha).all()),
            'complete_port_terms_admission': port_admission},
        'interpretation': {
            'physical_witness': 'roundoff_agreement_supports_condensation_signs_maps_on_near_zero_interior_load',
            'arbitrary_interior_RHS_qualification': 'not_run_still_pending',
            'raw_auxiliary_random_RHS_qualification': 'failed_not_reclassified',
            'scaling_as_leading_cause': 'inference_supported_by_173_decade_H_and_upstream_absolute_floor',
            'all_modes_physical_truncation_qualification': 'not_established_by_inventory_or_old_oracle_match'},
        'source_citations': [
            {'path': 'src/solvers/dtn_port_3d.py', 'sha256': sha(repo / 'src/solvers/dtn_port_3d.py'),
             'functions': ['_vec_nonzero_owned_entries', '_combine_owned_entries', '_ReusableSurfaceComponentAssembler', '_mode_projection_denominator'],
             'finding': 'absolute_floor1e-30_before_normalization; phase includes kz*z; H includes abs(boundaryphase)^2'},
            {'path': 'src/solvers/p4_cell_condensed_inverse.py', 'sha256': sha(repo / 'src/solvers/p4_cell_condensed_inverse.py'),
             'functions': ['assemble_condensed_ports', 'assemble_port_condensed_terms'],
             'finding': 'original B/-D/H signs retained; no nonzero Bi/Di admission in this run'}],
        'diagnostic_script_sha256': sha(Path(__file__)),
    }
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'receipt': str(output), 'sha256': sha(output),
                      'physical_FE_witness': result['measured']['saved_field_condensed_FE_relative'],
                      'q0_FE_witness': result['measured']['saved_field_q0_FE_relative'],
                      'raw_gate': result['raw_block_gate_status']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('repo', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); main(args.repo.resolve(), args.output.resolve())
