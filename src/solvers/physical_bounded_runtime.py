"""V7 bounded BAL_H assembly for the owner and projected sequential routes."""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

import numpy as np

from .fullspace_physical_intermediate import apply_owned
from .physical_balanced_coupling import PhysicalBalancedCoupling
from .physical_inexact_balance import InexactBalanceLedger
from .physical_recursive_coarse import PhysicalP2Inverse
from .physical_bounded_policy import BoundedI4Admission
from .physical_trace_entity import (
    CachedPhysicalTraceAction,
    PhysicalTraceEntities,
    complete_pq,
)
from .physical_projected_trace import (
    ProjectedSequentialTraceFactorStore,
    structured_mesh_cell_coordinates,
)


TRACE_INVENTORY = Path('benchmarks/artifacts/task39extra/v6_recursive/higher_trace_entity_inventory.json')
TRACE_INVENTORY_HASH = '9dee01eadae5fe78d4855cff412f1c18bcee55563e3373609d44a06184c064b6'
RECOVERY_ROOT = Path('benchmarks/artifacts/task39extra/v6_bubble_amplification_diagnostic/450255f4575792d052c1bac29837d39955ee1039/a2r160_g1')
RECOVERY_READOUT = Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_amplification_retry_readout.json')
RECOVERY_HASH = '403eb348a62802f7f0018a149922541b49a6fd3049c262d71c6b9a8a3bf05a97'
PARTICULAR_ROOT = Path('benchmarks/artifacts/task39extra/v6_bubble_particular_diagnostic/55a795e5b31b5c6b0323b92c517f6e989faf5803/a2r160_g1')
PARTICULAR_READOUT = Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_particular_readout.json')
PARTICULAR_HASH = 'a64486272a45e6449e6da606115b8c2f2a2dcf64535de416d61975ee0ced7150'
OWNER_PROBE = Path('benchmarks/artifacts/task39extra/v6_recursive/owner_route_probe.json')
OWNER_PROBE_HASH = '8905c25c47dcedf336a01cb48536d85181fb329ffb9198eabb9da5f6bcaaf01e'
DEFAULT_BINDING = Path('input/task39extra/p4_failure_diagnostic_v6.json')
PROJECTED_REUSE_RECORD = Path(
    'docs/task039_extra_physical_multilevel/outcomes/records/'
    'recursive_p4_complement_diagnostic_v6.json')
PROJECTED_SOURCE_SHA = 'dcca0f5ea6b7ba9221b23dd210a3c06839cc47be'
PROJECTED_PATCH_COUNT = 252
PROJECTED_PATCH_DIMENSION = 144


class BoundedPolicy:
    """Scalar setup identity returned beside the callable formal PC."""

    def __init__(self, identity: str, route: str) -> None:
        self.identity = dict(profile=identity, route=route,
                             reference_factor_count=0, global_p4_matrix=0,
                             global_p4_factor=0)


def _load_map(binding_path: Path) -> dict[str, Any]:
    from src.runners.physical_diagnostic_completion import load_packet

    binding = json.loads(binding_path.read_text())
    if binding.get('sample') != 'A2R160_BAL_H_p4_01':
        raise ValueError('V7 owner route requires the frozen A2R160 map binding')
    packet = binding['packets']['map']
    path = Path(packet['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest() != packet['sha256']:
        raise ValueError('V7 owner route p4 map hash differs')
    mapping = load_packet(path)
    return dict(binding=binding, map=mapping)


def _load_owner_classes() -> tuple[list[int], dict[str, dict[str, Any]], dict[str, Any]]:
    from src.solvers.physical_bubble_amplification import (
        PARTICULAR_HASH, PARTICULAR_READOUT, PARTICULAR_ROOT,
    )
    from src.solvers.physical_bubble_particular import (
        READOUT, READOUT_SHA, ROOT, saved_packet_reader,
    )

    old = saved_packet_reader(ROOT, READOUT, READOUT_SHA)
    particular = saved_packet_reader(PARTICULAR_ROOT, PARTICULAR_READOUT, PARTICULAR_HASH)
    class_map = particular('particular_class_map')
    cells = list(class_map['cell_classes'])
    classes: dict[str, dict[str, Any]] = {}
    for index in range(18):
        prefix = f'bubble_class_{index:03d}'
        identity = old(prefix + '_identity')
        key = identity['sha256']
        if identity['key'] != class_map['identities'][key]:
            raise ValueError('V7 owner-route class identity differs')
        harmonic = old(prefix + '_bubble_harmonic')
        retained = old(prefix + '_retained')
        classes[key] = dict(
            A=harmonic['A'], R=harmonic['R'], Q=harmonic['Q'],
            D=harmonic['D'], S=harmonic['S'], W=retained['W'],
            delta=retained['delta'], cell_info=identity['key']['orientation'],
        )
    return cells, classes, class_map


def _load_projected_blocks() -> dict[str, Any]:
    """Load only the saved full252 maps, D blocks, and LU/pivot packets.

    The V6 record is the authority for the exact packet paths and hashes.  No
    S-column construction is reachable from this loader; the returned local
    factor packet paths are hash-checked here.  Each packet's ``D`` array is
    checked and released during the one-at-a-time restore; only saved
    LU/pivots are retained by the two-group inverse.  The complete
    ``T`` action is built from the current physical callbacks, not from local
    projected blocks.
    """
    from src.runners.physical_diagnostic_completion import load_packet

    if not PROJECTED_REUSE_RECORD.is_file():
        raise ValueError('projected full252 reuse record is missing')
    authority = json.loads(PROJECTED_REUSE_RECORD.read_text())
    if authority.get('sources', {}).get('original_full252') != PROJECTED_SOURCE_SHA:
        raise ValueError('projected full252 source identity differs')

    def checked_json(descriptor: dict[str, Any]) -> Path:
        path = Path(descriptor['path'])
        if (not path.is_file() or
                hashlib.sha256(path.read_bytes()).hexdigest() != descriptor['sha256']):
            raise ValueError(f'projected packet hash differs: {path}')
        return path

    map_descriptor = authority['identities']['maps']
    map_path = checked_json(map_descriptor)
    maps = load_packet(map_path)
    indices = np.asarray(maps['indices'], dtype=np.int64)
    weights = np.asarray(maps['weights'], dtype=float)
    offsets = np.asarray(maps['offsets'], dtype=np.int64)
    if indices.shape != (PROJECTED_PATCH_COUNT, PROJECTED_PATCH_DIMENSION):
        raise ValueError('saved projected map dimensions differ')
    if offsets.shape != (1567,) or offsets[-1] != len(weights):
        raise ValueError('saved projected coefficient offsets differ')
    del maps

    entries = authority['identities']['factors']
    expected_keys = [f'split/factor_{index:03d}' for index in range(PROJECTED_PATCH_COUNT)]
    if sorted(entries) != expected_keys:
        raise ValueError('saved projected factor inventory differs')
    factor_descriptors = []
    for key in expected_keys:
        path = checked_json(entries[key])
        factor_descriptors.append((key, path))
    return dict(
        source_sha=PROJECTED_SOURCE_SHA,
        source_record_sha256=hashlib.sha256(PROJECTED_REUSE_RECORD.read_bytes()).hexdigest(),
        map_path=str(map_path),
        map_json_sha256=map_descriptor['sha256'],
        indices=indices, weights=weights, offsets=offsets,
        factor_descriptors=factor_descriptors,
    )


def _qualify_owner_route(levels: dict[str, Any], mapping: dict[str, Any], space: Any,
                         *, sample: Callable[[], Any], save: Callable[[str, dict[str, Any]], None]) -> dict[str, Any]:
    from src.runners.physical_diagnostic_completion import load_packet
    from .fullspace_physical_intermediate_runtime import level_vector

    if hashlib.sha256(OWNER_PROBE.read_bytes()).hexdigest() != OWNER_PROBE_HASH:
        raise ValueError('V7 owner-route probe hash differs')
    authority = json.loads(OWNER_PROBE.read_text())
    hashes = {item['path']: item['sha256'] for item in authority['evidence']}
    rows = []
    for label in ('range_q', 'saved_delta_z', 'S_probe_q'):
        sample()
        path = OWNER_PROBE.parent / 'owner_route_probe_arrays' / f'{label}.json'
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[str(path)]:
            raise ValueError('V7 owner-route probe packet hash differs')
        packet = load_packet(path)
        q = level_vector(levels, 2)
        output = None
        try:
            q.array[:] = packet['q']
            before = q.array.copy()
            output = space.transfer.apply_primal(q)
            slave_max = float(np.max(np.abs(output.array[mapping['slaves']])) if mapping['slaves'].size else 0.)
            relative = float(np.linalg.norm(output.array - packet['old_primal']) /
                             max(np.linalg.norm(packet['old_primal']), np.finfo(float).tiny))
            facts = dict(label=label, relative_error=relative,
                         input_unchanged=bool(np.array_equal(q.array, before)),
                         finite=bool(np.isfinite(output.array).all()), slave_max=slave_max,
                         owner=dict(space.owner.audit))
            save('bounded_owner_' + label, facts)
            if (not facts['input_unchanged'] or not facts['finite'] or slave_max != 0.0 or
                    relative > 1e-11):
                raise ValueError('V7 owner-route qualification failed')
            rows.append(facts)
        finally:
            q.destroy()
            if output is not None:
                output.destroy()
    return dict(status='PASS', source_probe_hash=OWNER_PROBE_HASH, rows=rows,
                routing=dict(space.owner.routing_costs))


def _qualify_current_operator_bridges(
    levels: dict[str, Any],
    actions: dict[str, Any],
    mapping: dict[str, Any],
    space: Any,
    matrix: Any,
    cached: Any,
    *,
    sample: Callable[[], Any],
    save: Callable[[str, dict[str, Any]], None],
) -> dict[str, Any]:
    """Bind saved owner objects to this run's native A4 and p2/S actions.

    File hashes and row counts establish provenance, but cannot prove that a
    saved local class packet is being used with the current DtN, mode order,
    quadrature, and MPC map.  These two one-vector bridges do that actual
    action check before the component is admitted to a formal stack.
    """

    from .fullspace_physical_intermediate_runtime import level_vector

    p4 = level_vector(levels, 4)
    p4_native = p4_cached = None
    p2 = level_vector(levels, 2)
    p2_saved = p2_current = augmented = assembled = None
    try:
        rng = np.random.default_rng(3916)
        p4.array[:] = rng.normal(size=p4.getLocalSize()) + 1j*rng.normal(size=p4.getLocalSize())
        p4.array[mapping['slaves']] = 0
        p4.scale(1 / max(float(p4.norm()), np.finfo(float).tiny))
        p4_before = p4.array.copy()
        sample()
        p4_native = apply_owned(actions['physical'][4]['physical_action'], p4)
        p4_cached = p4.duplicate()
        p4_cached.set(0)
        sample()
        cached.apply_into(p4, p4_cached)
        p4_relative = float(np.linalg.norm(p4_cached.array - p4_native.array) /
                            max(np.linalg.norm(p4_native.array), np.finfo(float).tiny))
        p4_facts = dict(
            relative_error=p4_relative,
            input_unchanged=bool(np.array_equal(p4.array, p4_before)),
            finite=bool(np.isfinite(p4_native.array).all() and np.isfinite(p4_cached.array).all()),
            slave_max=float(np.max(np.abs(p4_cached.array[mapping['slaves']]))
                           if mapping['slaves'].size else 0.0),
            limit=1e-11,
            native_mode_sha256=actions['mode_sha256'],
            current_quadrature=actions['volume_quadrature_metadata'],
        )
        if (not p4_facts['input_unchanged'] or not p4_facts['finite'] or
                p4_facts['slave_max'] != 0.0 or p4_relative > p4_facts['limit']):
            raise ValueError('V7 current native/cached A4 bridge failed')

        p2.array[:] = rng.normal(size=p2.getLocalSize()) + 1j*rng.normal(size=p2.getLocalSize())
        p2.array[space.transfer.coarse_slaves] = 0
        p2.scale(1 / max(float(p2.norm()), np.finfo(float).tiny))
        p2_before = p2.array.copy()
        p2_saved = p2.duplicate()
        p2_saved.set(0)
        sample()
        space.apply_into(p2, p2_saved)
        carrier = actions['physical'][2]['dtn_action'].carrier
        augmented = matrix.createVecRight()
        assembled = augmented.duplicate()
        augmented.set(0)
        n = p2.getLocalSize()
        augmented.array[:n] = p2.array
        for index, entry in enumerate(carrier.entries):
            augmented.array[n + index] = (
                np.dot(entry.projection_values, p2.array[entry.projection_rows]) /
                entry.normalization_h)
        matrix.mult(augmented, assembled)
        s_relative = float(np.linalg.norm(assembled.array[:n] - p2_saved.array) /
                           max(np.linalg.norm(p2_saved.array), np.finfo(float).tiny))
        s_facts = dict(
            relative_error=s_relative,
            input_unchanged=bool(np.array_equal(p2.array, p2_before)),
            finite=bool(np.isfinite(p2_saved.array).all() and np.isfinite(assembled.array).all()),
            slave_max=float(np.max(np.abs(p2_saved.array[space.transfer.coarse_slaves]))
                           if space.transfer.coarse_slaves.size else 0.0),
            limit=1e-10,
            matrix_shape=list(matrix.getSize()),
            mode_sha256=actions['mode_sha256'],
            quadrature=actions['volume_quadrature_metadata'],
        )
        if (not s_facts['input_unchanged'] or not s_facts['finite'] or
                s_facts['slave_max'] != 0.0 or s_relative > s_facts['limit']):
            raise ValueError('V7 current saved-S/current-DtN bridge failed')
        bridges = dict(status='PASS', native_cached_A4=p4_facts, saved_S_current_DtN=s_facts)
        save('bounded_operator_bridges', bridges)
        return bridges
    finally:
        for value in (assembled, augmented, p2_current, p2_saved, p2, p4_cached, p4_native, p4):
            if value is not None:
                value.destroy()


def build_owner_route_assets(
    levels: dict[str, Any],
    actions: dict[str, Any],
    *,
    cfg: Any,
    sample: Callable[[], Any],
    marker: Callable[[str, dict[str, Any]], None],
    save: Callable[[str, dict[str, Any]], None],
    binding_path: Path = DEFAULT_BINDING,
    projected: bool = False,
) -> dict[str, Any]:
    """Build the reusable formal trace component on an existing 6/4/2 mesh.

    No reference field, p4 AIJ matrix, or p4 factor is retained.  The saved
    packets contribute only the already qualified class/map/S identities; all
    formal actions use the current same-mesh DtN and the caller's p6/p4/p2
    setup.  ``projected=True`` replaces only the joint inverse apply with the
    saved full252 two-group sequential action; it does not construct the old
    1566 entity LUs or rerun the 36288 setup solves.
    """

    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg import _n1e
    from .physical_bubble_amplification import SavedBubbleSpace
    from .physical_bubble_particular import saved_packet_reader
    from .condensed_fine_reference import native_map_arrays
    from src.runners.physical_trace_controls import PATCH_AUTHORITY, PATCH_AUTHORITY_HASH
    from .physical_trace_cell_patch import build_cell_joint_patch_maps
    from src.geometry.mesh_builder_3d import _stage4_axis_plan

    if levels['mesh'].comm.size != 1:
        raise ValueError('V7 owner route is qualified only for MPI1')
    if hashlib.sha256(TRACE_INVENTORY.read_bytes()).hexdigest() != TRACE_INVENTORY_HASH:
        raise ValueError('V7 entity inventory hash differs')
    inventory = json.loads(TRACE_INVENTORY.read_text())
    if len(inventory['entities']) != 1566 or inventory['high_trace_dimension'] != 17064:
        raise ValueError('V7 entity inventory dimensions differ')
    if (actions.get('mode_sha256') !=
            'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2'):
        raise ValueError('V7 owner-route mode inventory differs from the qualified original')
    if len(actions['physical'][4]['modes']) != 80:
        raise ValueError('V7 owner-route requires the qualified 80-mode inventory')
    bound = _load_map(Path(binding_path))
    mapping = bound['map']
    current_map = native_map_arrays(levels['spaces'][4], levels['floquets'][4])
    if any(key not in mapping or not np.array_equal(value, mapping[key]) for key, value in current_map.items()):
        raise ValueError('V7 current p4 owner map differs from the bound map')
    cells, classes, class_map = _load_owner_classes()
    quadrature = actions['volume_quadrature_metadata']
    if list(quadrature) != [dict(quadrature_degree=15, quadrature_rule='default')] * 2:
        raise ValueError('V7 owner-route class quadrature is not the qualified 15/default rule')
    p2_map = native_map_arrays(levels['spaces'][2], levels['floquets'][2])
    recovered = saved_packet_reader(RECOVERY_ROOT, RECOVERY_READOUT, RECOVERY_HASH)
    saved_p2 = recovered('amplification_p2_map')
    if any(key not in saved_p2 or not np.array_equal(value, saved_p2[key]) for key, value in p2_map.items()):
        raise ValueError('V7 current p2 owner map differs from the bound map')
    p2_action = actions['physical'][2]['dtn_action']
    space = trace = matrix = bottom = cached = None
    try:
        space = SavedBubbleSpace(levels, classes, cells, p2_map, p2_action,
            sample=sample, save=save, fixed_serial_owner_route=True)
        owner_qualification = _qualify_owner_route(levels, mapping, space, sample=sample, save=save)
        stored = recovered('amplification_S_CSR')
        matrix = PETSc.Mat().createAIJ(size=stored['shape'],
            csr=(stored['indptr'], stored['indices'], stored['values']), comm=levels['mesh'].comm)
        if matrix.getSize() != (7326, 7326):
            raise ValueError('V7 restored physical p2 matrix size differs')
        cached = CachedPhysicalTraceAction(mapping, cells, classes,
            actions['physical'][4]['dtn_action'], lifecycle='formal', safe_checkpoint=sample)
        operator_bridges = _qualify_current_operator_bridges(
            levels, actions, mapping, space, matrix, cached, sample=sample, save=save)
        p4carrier = actions['physical'][4]['dtn_action'].carrier
        payload_limit = 256 * 1024**2
        marker('bounded_trace_entity_setup_started', dict(
            entity_count=len(inventory['entities']), projected=bool(projected)))
        joint_authority = None
        if projected:
            if hashlib.sha256(PATCH_AUTHORITY.read_bytes()).hexdigest() != PATCH_AUTHORITY_HASH:
                raise ValueError('V7 projected patch authority hash differs')
            joint_authority = json.loads(PATCH_AUTHORITY.read_text())
            if (joint_authority.get('patch_count') != PROJECTED_PATCH_COUNT or
                    joint_authority.get('exact_class_count') != 84):
                raise ValueError('V7 projected patch authority dimensions differ')
        trace = PhysicalTraceEntities(mapping, cells, classes, inventory['entities'], _n1e(4).entity_dofs,
            p4carrier, sample=sample, save=save, marker=marker, joint_authority=joint_authority,
            lifecycle='formal', build_joint=not projected)
        projected_facts = None
        if projected:
            frozen = _load_projected_blocks()
            axis_plan = _stage4_axis_plan(cfg, levels['mesh'].comm.size)
            coordinates = structured_mesh_cell_coordinates(
                levels['mesh'], (axis_plan.x_values, axis_plan.y_values, axis_plan.z_values))
            if len(cells) != PROJECTED_PATCH_COUNT or len(coordinates) != len(cells):
                raise ValueError('V7 projected structured cell inventory differs')
            current_offsets, _, current_indices, current_weights = build_cell_joint_patch_maps(
                cells, inventory['entities'], trace.blocks)
            if (not np.array_equal(current_indices, frozen['indices']) or
                    not np.array_equal(current_weights, frozen['weights']) or
                    not np.array_equal(current_offsets, frozen['offsets'])):
                raise ValueError('V7 current projected patch maps differ from saved maps')
            def unbound_complete_T(_value):
                raise RuntimeError('projected complete T was not attached')

            sequential = ProjectedSequentialTraceFactorStore(
                frozen['indices'], frozen['weights'], frozen['offsets'], coordinates,
                unbound_complete_T, sample=sample)
            from src.runners.physical_diagnostic_completion import load_packet
            restored = 0
            for key, factor_path in frozen['factor_descriptors']:
                packet = load_packet(factor_path)
                packet_matrix = np.asarray(packet['D'])
                facts = packet.get('facts', {})
                if (packet_matrix.shape != (PROJECTED_PATCH_DIMENSION, PROJECTED_PATCH_DIMENSION) or
                        packet_matrix.dtype != np.complex128 or not np.isfinite(packet_matrix).all() or
                        facts.get('matrix_sha256') != hashlib.sha256(packet_matrix.tobytes()).hexdigest()):
                    raise ValueError(f'saved projected block identity differs: {key}')
                sequential.append_saved_factor(
                    packet['LU'], packet['pivots'], facts=facts)
                restored += 1
                del packet_matrix, packet
            trace.joint = sequential
            del frozen
            group_counts = [int(len(group)) for group in sequential.group_members]
            projected_facts = dict(
                source_sha=PROJECTED_SOURCE_SHA,
                source_record_sha256=hashlib.sha256(PROJECTED_REUSE_RECORD.read_bytes()).hexdigest(),
                factor_count=PROJECTED_PATCH_COUNT,
                factor_dimension=PROJECTED_PATCH_DIMENSION,
                group_counts=group_counts,
                grouping='structured_cell_coordinate_parity_(i+j+k)%2',
                formula='M0 + M1 - M1*T*M0',
                setup_s_column_solves=0,
                no_saved_entity_lu_overlap=True,
                restored_factor_count=int(restored),
            )
        payload = int(trace.payload_bytes())
        if payload > payload_limit:
            raise MemoryError('formal bounded trace payload exceeds the 256 MiB local policy')
        extra_local_bytes = payload + 4117888
        bottom = PhysicalP2Inverse(matrix, space, space.transfer.coarse_slaves,
            sample=sample, marker=marker, save=save,
            action_identity='saved_S_cell_plus_p2_DtN', extra_local_bytes=extra_local_bytes)
        save('bounded_trace_storage', dict(entity_count=len(inventory['entities']),
            edge_entities=792, face_entities=774, named_payload_bytes=payload,
            extra_local_bytes=extra_local_bytes, payload_limit_bytes=payload_limit,
            formal_lifecycle=True, entity_pilot_upper_bound=263,
            owner_qualification=owner_qualification,
            operator_bridges=operator_bridges,
            p4_global_matrix=0, p4_global_factor=0,
            source_inventory_hash=TRACE_INVENTORY_HASH,
            source_component_sha='9dbf12355e6e6c7eac23d055c12da4e7eda2a7d8',
            projected=projected_facts))
        return dict(mapping=mapping, cells=cells, classes=classes, inventory=inventory,
                    class_map=class_map, p2_map=p2_map, space=space, trace=trace,
                    matrix=matrix, bottom=bottom, cached=cached,
                    owner_qualification=owner_qualification, payload_bytes=payload,
                    extra_local_bytes=extra_local_bytes, operator_bridges=operator_bridges,
                    projected=projected_facts)
    except BaseException:
        if cached is not None:
            cached = None
        if trace is not None:
            trace.destroy()
        if bottom is not None:
            bottom.destroy()
        if matrix is not None:
            matrix.destroy()
        if space is not None:
            space.destroy()
        raise


def build_formal_bounded(
    cfg: Any,
    comm: Any,
    contract: dict[str, Any],
    *,
    sample: Callable[[], Any],
    ledger: Any,
    directory: Path,
    identity: str,
    save: Callable[[str, dict[str, Any]], None],
    append: Callable[[str, dict[str, Any]], None],
    stop_requested: Callable[[], bool],
    capture_vectors: bool = False,
    retain_inexact_vectors: bool = False,
) -> tuple[dict[str, Any], Callable[[Any], Any], BoundedPolicy]:
    """Build one V7 BAL_H route and its callable; no PDE solve is started here."""

    route = contract.get('route')
    if route not in ('ENTITY16', 'PROJECTED_SEQ2_16'):
        raise ValueError(f'unknown bounded V7 route: {route!r}')
    if getattr(cfg, 'cell_notch', None):
        raise ValueError('V7 route-A original owner packets cannot be reused for notch materials')
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .fullspace_physical_intermediate_runtime import (
        build_physical_intermediate_actions, level_vector)
    from .physical_light_setup import build_light_h6_setup
    bundle: dict[str, Any] = dict(profile=identity, route=route)
    try:
        sample()
        levels = _build_same_mesh_levels(cfg, comm, (6, 4, 2))
        bundle['levels'] = levels
        positive = build_light_h6_setup(levels, cfg, ledger.marker)
        bundle['positive'] = positive
        fine = build_same_mesh_physical_action(levels, cfg, 6)
        bundle['fine'] = fine
        actions = build_physical_intermediate_actions(levels, cfg, fine_bundle=fine,
            stage_callback=ledger.marker, physical_only_degrees=(6, 4, 2))
        bundle['actions'] = actions
        assets = build_owner_route_assets(levels, actions, sample=sample,
            cfg=cfg, marker=ledger.marker, save=save,
            projected=(route == 'PROJECTED_SEQ2_16'))
        bundle['trace_assets'] = assets
        p64 = actions['transfers'][(6, 4)]
        p42 = assets['space'].transfer
        a4_cached = assets['cached']
        a4_native = actions['physical'][4]['physical_action']

        def a4(value):
            return apply_owned(a4_cached, value)

        def native_a4(value):
            return apply_owned(a4_native, value)

        def cu(value):
            result = value.duplicate()
            try:
                result.array[:] = complete_pq(value.array, assets['trace'].E,
                    assets['trace'].volume, lambda source: _coarse_array(source, value, p42, assets['bottom']))
                return result
            except BaseException:
                result.destroy()
                raise

        if route == 'PROJECTED_SEQ2_16':
            projected_T = dict(calls=0, F=0, FH=0, A4=0, CU=0,
                               seconds=0., complete=True,
                               expression='F^H A4 (I-CU A4) F')

            def complete_T(coefficients):
                # This is the current full physical action, not a sum of the
                # saved local D blocks. F/FH remain distinct non-Hermitian
                # maps; CU is the complete p4/p2 coarse feedback including
                # the original DtN through the current cached A4 action.
                started = time.perf_counter()
                source = corrected = first = second = coarse = None
                try:
                    projected_T['calls'] += 1
                    chunks = [coefficients[a:b] for a, b in zip(
                        assets['trace'].joint.offsets[:-1],
                        assets['trace'].joint.offsets[1:], strict=True)]
                    source = level_vector(bundle['levels'], 4)
                    source.array[:] = assets['trace'].F(chunks)
                    projected_T['F'] += 1
                    first = a4(source)
                    projected_T['A4'] += 1
                    coarse = cu(first)
                    projected_T['CU'] += 1
                    corrected = source.duplicate()
                    corrected.array[:] = source.array - coarse.array
                    second = a4(corrected)
                    projected_T['A4'] += 1
                    result = np.concatenate(assets['trace'].FH(second.array))
                    projected_T['FH'] += 1
                    if result.shape != coefficients.shape or not np.isfinite(result).all():
                        raise ValueError('projected complete T returned an invalid coefficient vector')
                    return result
                finally:
                    projected_T['seconds'] += time.perf_counter() - started
                    for value in (second, corrected, first, coarse, source):
                        if value is not None:
                            value.destroy()

            assets['trace'].joint.set_complete_T(complete_T)
            assets['projected_T'] = projected_T

        def ht(value):
            result = value.duplicate()
            try:
                result.array[:] = assets['trace'].apply(value.array)
                return result
            except BaseException:
                result.destroy()
                raise

        def restriction(value):
            coarse = p42.apply_adjoint(value)
            try:
                internal = np.concatenate([
                    assets['classes'][key]['Q'].conj().T @ value.array[assets['mapping']['dofmap'][cell]]
                    for cell, key in enumerate(assets['cells'])
                ])
                return np.concatenate([coarse.array.copy(), internal])
            finally:
                coarse.destroy()

        b4 = PhysicalBalancedCoupling(a4, cu, ht, restriction, route='BAL_H',
            checkpoint=sample, level_identity='formal owner-route cached A4 + p2 bottom')
        bundle['b4'] = b4
        admission = BoundedI4Admission(a4, b4.apply, sample=sample, save=save,
            stop_requested=stop_requested, residual_action=native_a4)
        bundle['i4_admission'] = admission
        inexact = InexactBalanceLedger(
            lambda value: apply_owned(fine['physical_action'], value),
            p64.apply_adjoint, save=save, checkpoint=sample, every=32,
            retain_call_vectors=retain_inexact_vectors)
        bundle['inexact_ledger'] = inexact

        def c64(value):
            rhs = p64.apply_adjoint(value)
            result = None
            try:
                result = admission(rhs)
                append('bounded_i4.jsonl', dict(call=admission.calls,
                    facts=deepcopy(result['facts']), admission=admission.snapshot()))
                inexact.record(rhs, result['applied'], result['residual'], result['facts'])
                return p64.apply_primal(result['solution'])
            finally:
                rhs.destroy()
                if result is not None:
                    for name in ('solution', 'applied', 'residual'):
                        if result.get(name) is not None:
                            result[name].destroy()

        def h6(value):
            sample()
            return positive['h6'].apply(value)

        outer = PhysicalBalancedCoupling(
            lambda value: apply_owned(fine['physical_action'], value), c64, h6,
            p64.apply_adjoint, route='BAL_H', checkpoint=sample,
            inexact_ledger=inexact, level_identity=f'p6/p4 bounded {route.lower()} V7',
            capture_vectors=capture_vectors)
        bundle['pc'] = outer

        def apply(value):
            result = None
            try:
                result = outer.apply(value)
                outer.last_apply_facts['bounded_i4'] = admission.snapshot()
                outer.last_apply_facts['trace_counts'] = dict(
                    cached=assets['cached'].counts, cached_seconds=assets['cached'].seconds,
                    entities=assets['trace'].counts, entity_seconds=assets['trace'].elapsed,
                    joint=dict(assets['trace'].joint.counts)
                    if assets['trace'].joint is not None else None,
                    projected_T=dict(assets.get('projected_T', {})),
                    bottom=dict(assets['bottom'].counts),
                    # These are lifetime counters at the end of this PC.  The
                    # independent checker subtracts the setup baseline once;
                    # it must not reconstruct them by summing nested timings.
                    B4=dict(applies=b4.apply_count, attempted=b4.attempted,
                            counts=dict(b4.total_counts),
                            operation_seconds=dict(b4.total_operation_seconds)),
                    S_action=dict(calls=assets['space'].action_count,
                                  seconds=assets['space'].action_seconds),
                    inexact_audit=dict(
                        audits=inexact.audit_count, extra_A6=inexact.A_count,
                        extra_PH=inexact.PH_count,
                        extra_A6_seconds=inexact.A_seconds,
                        extra_PH_seconds=inexact.PH_seconds,
                        audit_seconds=inexact.audit_seconds),
                )
                ledger.record_pc(outer.last_apply_facts)
                return result
            except BaseException:
                if result is not None:
                    result.destroy()
                raise

        policy = BoundedPolicy(identity, route)
        return bundle, apply, policy
    except BaseException:
        destroy_bounded_physical_solver(bundle)
        raise


def _coarse_array(source: np.ndarray, template: Any, p42: Any, bottom: Any) -> np.ndarray:
    rhs = template.duplicate()
    solution = None
    try:
        rhs.array[:] = source
        coarse = p42.apply_adjoint(rhs)
        try:
            solution = bottom.apply(coarse)
            result = p42.apply_primal(solution)
            try:
                return result.array.copy()
            finally:
                result.destroy()
        finally:
            coarse.destroy()
    finally:
        rhs.destroy()
        if solution is not None:
            solution.destroy()


def bounded_terminal_snapshot(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return lifetime counters before the auxiliary stack is released."""

    assets = bundle['trace_assets']
    b4 = bundle['b4']
    admission = bundle['i4_admission']
    inexact = bundle['inexact_ledger']
    bottom = assets['bottom']
    matrix = assets['matrix']
    return dict(
        outer_PC_applies=int(bundle['pc'].apply_count),
        outer_PC_attempted=int(bundle['pc'].attempted),
        B4=dict(
            applies=int(b4.apply_count), attempted=int(b4.attempted),
            counts=dict(b4.total_counts),
            operation_seconds=dict(b4.total_operation_seconds),
        ),
        I4=dict(calls=int(admission.calls), snapshot=admission.snapshot()),
        inexact_audit=dict(
            audits=int(inexact.audit_count), extra_A6=int(inexact.A_count),
            extra_PH=int(inexact.PH_count), extra_A6_seconds=float(inexact.A_seconds),
            extra_PH_seconds=float(inexact.PH_seconds),
            audit_seconds=float(inexact.audit_seconds),
        ),
        trace=dict(counts=dict(assets['trace'].counts), elapsed=dict(assets['trace'].elapsed),
                   payload_bytes=int(assets['payload_bytes']),
                   joint=dict(assets['trace'].joint.counts)
                   if assets['trace'].joint is not None else None,
                   projected_T=dict(assets.get('projected_T', {}))),
        cached=dict(counts=dict(assets['cached'].counts), seconds=dict(assets['cached'].seconds)),
        S_action=dict(calls=int(assets['space'].action_count),
                      seconds=float(assets['space'].action_seconds)),
        bottom=dict(counts=dict(bottom.counts), audit=dict(bottom.bottom.audit)),
        physical_p2_matrix=dict(size=list(matrix.getSize()), info=matrix.getInfo()),
        storage=dict(named_payload_bytes=int(assets['payload_bytes']),
                     extra_local_bytes=int(assets['extra_local_bytes']),
                     operator_bridges=assets['operator_bridges'],
                     projected=assets.get('projected')),
    )


def audit_bounded_exit(bundle: dict[str, Any], ledger: Any) -> dict[str, Any]:
    """Audit the final inexact identity and write one cumulative exit record."""

    inexact = bundle['inexact_ledger']
    before = dict(audits=inexact.audit_count, extra_A6=inexact.A_count,
                  extra_PH=inexact.PH_count, extra_A6_seconds=inexact.A_seconds,
                  extra_PH_seconds=inexact.PH_seconds, audit_seconds=inexact.audit_seconds)
    audit = inexact.audit_last()
    after = dict(audits=inexact.audit_count, extra_A6=inexact.A_count,
                 extra_PH=inexact.PH_count, extra_A6_seconds=inexact.A_seconds,
                 extra_PH_seconds=inexact.PH_seconds, audit_seconds=inexact.audit_seconds)
    costs = {key: after[key] - before[key] for key in before}
    snapshot = bounded_terminal_snapshot(bundle)
    ledger.append('bounded_exit_audit.jsonl', dict(
        audit=audit, last_PC=int(bundle['pc'].apply_count), audit_costs=costs,
        total=snapshot, action_counts='lifetime counters; no per-PC re-sum'))
    return snapshot


def release_bounded_physical_solver_stack(bundle: dict[str, Any]) -> None:
    """Release V7 auxiliary objects while retaining the fine action."""

    bundle.pop('pc', None)
    bundle.pop('i4_admission', None)
    bundle.pop('b4', None)
    inexact = bundle.pop('inexact_ledger', None)
    if inexact is not None:
        inexact.destroy()
    assets = bundle.pop('trace_assets', None)
    if assets is not None:
        if assets.get('cached') is not None:
            assets['cached'] = None
        if assets.get('trace') is not None:
            assets['trace'].destroy()
        if assets.get('bottom') is not None:
            assets['bottom'].destroy()
        if assets.get('matrix') is not None:
            assets['matrix'].destroy()
        if assets.get('space') is not None:
            assets['space'].destroy()
    actions = bundle.pop('actions', None)
    if actions is not None:
        from .fullspace_physical_intermediate_runtime import destroy_physical_intermediate_actions
        destroy_physical_intermediate_actions(actions)
    positive = bundle.pop('positive', None)
    if positive is not None:
        for key in ('h6', 'p6_shell'):
            value = positive.pop(key, None)
            if value is not None:
                value.destroy()
    bundle['auxiliary_stack_released'] = True


def destroy_bounded_physical_solver(bundle: dict[str, Any]) -> None:
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action

    release_bounded_physical_solver_stack(bundle)
    fine = bundle.pop('fine', None)
    if fine is not None:
        destroy_same_mesh_physical_action(fine)
    bundle.clear()
