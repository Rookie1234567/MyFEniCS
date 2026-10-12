"""One read-only parent-DtN observation at the filtered pilot endpoint."""

import time
from collections.abc import Mapping

import numpy as np


def _field(entry, key):
    return entry[key] if isinstance(entry, Mapping) else getattr(entry, key)


def _same_functional(parent, active):
    # The mode index is intentionally remapped, but its actual functional is not.
    return (
        float(_field(parent, 'normalization_h'))
        == float(_field(active, 'normalization_h'))
        and all(
            np.asarray(_field(parent, key)).dtype == np.asarray(_field(active, key)).dtype
            and np.asarray(_field(parent, key)).shape == np.asarray(_field(active, key)).shape
            and np.asarray(_field(parent, key)).tobytes() == np.asarray(_field(active, key)).tobytes()
            for key in ('coupling_rows', 'coupling_values', 'projection_rows', 'projection_values')
        )
    )


def _chunk_norm(values, subtract=None):
    total = 0.0
    for first in range(0, values.size, 65536):
        chunk = values[first:first + 65536]
        if subtract is not None:
            chunk = chunk - subtract[first:first + 65536]
        total += float(np.vdot(chunk, chunk).real)
    return float(np.sqrt(total))


def observe_full_dtn_endpoint(
    *, parent_store, active_entries, selected_parent_indices, storage_solution,
    n0_residual, native_rhs_norm, iteration, omitted_incident_rhs_zero,
):
    """Compare the saved full parent with the current N0 field once.

    Caller supplies the same evaluate packet's full zero-slave storage solution
    and native residual. The store validates every shard hash and live numerical
    identity. No FE assembly, factor, recovery or full carrier is constructed.
    """

    started = time.perf_counter()
    facts = {
        'schema': 'task39extra.n0-full-dtn-endpoint-observation.v1',
        'status': 'FULL_DTN_NOT_VERIFIED', 'iteration': int(iteration),
        'A6_full_relative': None, 'omitted_dtn_action_norm': None,
        'omitted_dtn_action_relative_to_rhs': None,
        'parent_functionals_read': 0, 'active_functionals_matched': 0,
        'omitted_functionals_applied': 0,
        'scope': 'one pilot endpoint; not convergence, RTA or full-model qualification',
        'new_FE_assembly_calls': 0, 'new_factor_calls': 0,
        'full_parent_carrier_constructed': False,
        'projection_convention': 'np.dot(D,u); D already contains conjugation',
        'full_residual_formula': 'r_full = r_n0 - sum_omitted(C * dot(D,u) / H)',
    }
    try:
        if omitted_incident_rhs_zero is not True:
            raise ValueError('omitted incident RHS is not proven zero from live metadata')
        if parent_store is None:
            raise ValueError('compatible full p6 parent store is unavailable')
        inventory = parent_store.n0_parent_store_inventory_facts()
        facts['parent_inventory'] = inventory
        if inventory.get('complete') is not True:
            raise ValueError('full parent shard inventory is incomplete or incompatible')
        parent_count = int(inventory['expected_mode_count'])
        selected = tuple(int(value) for value in selected_parent_indices)
        entries = tuple(active_entries)
        if (not selected or len(selected) != len(entries)
                or len(set(selected)) != len(selected)
                or tuple(sorted(selected)) != selected
                or selected[0] < 0 or selected[-1] >= parent_count):
            raise ValueError('active-to-parent endpoint mapping differs')
        active_by_parent = dict(zip(selected, entries, strict=True))
        solution = np.asarray(storage_solution)
        residual = np.asarray(n0_residual)
        rhs_norm = float(native_rhs_norm)
        if (solution.dtype != np.dtype(np.complex128)
                or residual.dtype != np.dtype(np.complex128)
                or solution.ndim != 1 or residual.shape != solution.shape
                or not np.isfinite(rhs_norm) or rhs_norm <= 0.0):
            raise ValueError('endpoint storage arrays or RHS norm are invalid')
        # One full-space working vector; never retain all parent functionals.
        omitted_action = np.zeros_like(residual)
        facts['additional_full_vector_payload_bytes'] = int(omitted_action.nbytes)
        facts['normalization_rhs_norm'] = rhs_norm
        n0_norm = _chunk_norm(residual)
        if not np.isfinite(n0_norm):
            raise ValueError('N0 endpoint native residual is nonfinite')
        facts['A6_n0_relative'] = n0_norm / rhs_norm
        max_omitted_modal_coefficient = 0.0
        for parent_index in range(parent_count):
            functional = parent_store.read_n0_parent_functional_for_endpoint(parent_index)
            if functional is None:
                raise ValueError(f'full parent shard {parent_index} is unavailable')
            facts['parent_functionals_read'] += 1
            active = active_by_parent.get(parent_index)
            if active is not None:
                if not _same_functional(functional, active):
                    raise ValueError(f'active functional differs from parent index {parent_index}')
                facts['active_functionals_matched'] += 1
            else:
                projection_rows = np.asarray(_field(functional, 'projection_rows'))
                coupling_rows = np.asarray(_field(functional, 'coupling_rows'))
                for rows in (projection_rows, coupling_rows):
                    if (rows.ndim != 1 or not np.issubdtype(rows.dtype, np.integer)
                            or (rows.size and (rows[0] < 0 or rows[-1] >= solution.size
                                or np.any(rows[1:] <= rows[:-1])))):
                        raise ValueError('parent rows are not unique ordered MPI1 storage indices')
                denominator = float(_field(functional, 'normalization_h'))
                if not np.isfinite(denominator) or denominator <= 0.0:
                    raise ValueError('parent normalization is invalid')
                coefficient = np.dot(
                    _field(functional, 'projection_values'), solution[projection_rows]
                ) / denominator
                if not np.isfinite(coefficient):
                    raise ValueError('omitted modal projection is nonfinite')
                omitted_action[coupling_rows] += (
                    coefficient * _field(functional, 'coupling_values')
                )
                max_omitted_modal_coefficient = max(
                    max_omitted_modal_coefficient, float(abs(coefficient))
                )
                facts['omitted_functionals_applied'] += 1
            del functional
        full_norm = _chunk_norm(residual, omitted_action)
        omitted_norm = _chunk_norm(omitted_action)
        if not np.isfinite([full_norm, omitted_norm]).all():
            raise ValueError('full parent endpoint residual or omitted contribution is nonfinite')
        facts.update(
            status='FULL_DTN_ENDPOINT_RESIDUAL_OBSERVED_NOT_QUALIFICATION',
            A6_full_relative=full_norm / rhs_norm,
            full_residual_norm=full_norm,
            omitted_dtn_action_norm=omitted_norm,
            omitted_dtn_action_relative_to_rhs=omitted_norm / rhs_norm,
            maximum_omitted_modal_coefficient_magnitude=max_omitted_modal_coefficient,
            active_functional_parity='BITWISE_ARRAY_AND_NORMALIZATION_EQUAL',
            omitted_incident_rhs_zero=True,
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        facts['reason'] = f'{type(exc).__name__}: {exc}'
        # Partial sums and partial stream coverage never become full results.
        facts['A6_full_relative'] = None
        facts['omitted_dtn_action_norm'] = None
        facts['omitted_dtn_action_relative_to_rhs'] = None
    finally:
        facts['elapsed_seconds'] = time.perf_counter() - started
    return facts
