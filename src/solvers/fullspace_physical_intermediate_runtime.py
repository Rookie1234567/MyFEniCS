"""Same-mesh FE actions and algebraic transfers for the physical middle level.

This opt-in builder borrows an existing mesh/space/MPC setup. It creates no
high-order AIJ, factor, source, or solver. Native low-order forms retain the
fine physical inventory and integration rules; their Galerkin equivalence
must be qualified before use on a new geometry/quadrature definition.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
from dolfinx.la.petsc import create_vector
from mpi4py import MPI

from .fullspace_physical_intermediate import BorrowedActionAdapter, ShiftedPhysicalAction


PHYSICAL_DEGREES = (6, 4, 2, 1)
PHYSICAL_PAIRS = ((6, 4), (4, 2), (2, 1))


def build_physical_intermediate_solver(cfg: Any, comm: Any, *,
                                       resource_sample: Callable[[], dict],
                                       marker: Callable[[str, dict], None],
                                       reference: bool = False, light: bool = False) -> dict:
    """Own one shared mesh and two separately bounded p1 factors, opt-in only."""
    from .fullspace_bounded_mumps import BoundedP1Factor
    from .fullspace_physical_intermediate import (
        PhysicalIntermediatePreconditioner, ShiftedAuxiliaryCycle,
    )
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .fullspace_same_mesh_hcurl_pmg_setup import build_p6_same_mesh_setup
    from .fullspace_v17_p3_oracle import build_p3_physical_diagnostic_matrix

    result: dict = {"diagonals": {}, "jacobi_facts": {}}
    try:
        degrees = (6, 4) if light else (6, 4, 3, 2, 1)
        if light and not reference:
            raise ValueError('light PC requires the exact p4 reference')
        marker("shared_mesh_spaces_started", {"degrees": list(degrees)})
        levels = _build_same_mesh_levels(cfg, comm, degrees)
        result["levels"] = levels
        if not light and int(levels["spaces"][1].dofmap.index_map.size_global) > 4096:
            raise ValueError("p1 storage rows exceed 4096 before matrix assembly")
        if light:
            from .physical_light_setup import build_light_h6_setup
            positive = build_light_h6_setup(levels, cfg, marker)
        else:
            marker("positive_s6_started", {})
            positive = build_p6_same_mesh_setup(cfg, comm, levels=levels,
                quadrature_diagonal=True, stage_callback=marker,
                coarse_solver_factory=lambda matrix: BoundedP1Factor(matrix, label="positive_p1",
                    resource_sample=resource_sample, marker=marker))
        result["positive"] = positive
        marker("fine_physical_started", {})
        fine = build_same_mesh_physical_action(levels, cfg, 6)
        result["fine"] = fine
        actions = build_physical_intermediate_actions(levels, cfg, fine_bundle=fine,
            stage_callback=marker, reference=reference)
        result["actions"] = actions
        if reference:
            from .fullspace_p4_reference import build_reference_matrix, PhysicalP4Reference
            matrix, result['reference_matrix_facts'] = build_reference_matrix(
                levels, cfg, actions['physical'][4], actions['volume_quadrature_metadata'],
                marker=marker, sample=resource_sample)
            result['reference_matrix'] = matrix
            middle = PhysicalP4Reference(matrix, actions['physical'][4]['physical_action'],
                owned_slave_indices(levels['spaces'][4], levels['floquets'][4]),
                fine_rows=int(levels['spaces'][6].dofmap.index_map.size_global),
                sample=resource_sample, marker=marker)
            result['reference_factor'] = middle
            result['middle'] = middle
            result['pc'] = PhysicalIntermediatePreconditioner(fine['physical_action'],
                positive['h6'] if light else positive['upper_cycle'], actions['transfers'][(6, 4)], middle,
                stage_callback=marker, **(dict(positive_identity='H6', outer_max_it=2048) if light else {}))
            marker('physical_intermediate_setup_complete', dict(reference_only=True,
                independent_p1_factors=0 if light else 1, reference_p4_factors=1, shifted_inverse_constructed=False))
            return result
        jacobi = {}
        for degree in (4, 2):
            marker("positive_diagonal_started", {"degree": degree})
            jacobi[degree], result["diagonals"][degree], result["jacobi_facts"][degree] = (
                build_positive_level_jacobi(levels, degree))
        marker("shifted_p1_matrix_started", {})
        matrix, result["shifted_p1_matrix_facts"] = build_p3_physical_diagnostic_matrix(
            levels, cfg, comm, degree=1, shift_weight=actions["weight"],
            mode_inventory=(fine["modes"], fine["mode_rows"], fine["mode_sha256"]),
            volume_quadrature_metadata=actions["volume_quadrature_metadata"])
        result["shifted_p1_matrix"] = matrix
        bottom = BoundedP1Factor(matrix, label="shifted_p1", resource_sample=resource_sample,
                                 marker=marker)
        result["shifted_p1_factor"] = bottom
        transfers = actions["transfers"]
        middle = ShiftedAuxiliaryCycle(actions["shifted"][4],
            actions["physical"][4]["physical_action"], actions["shifted"][2],
            transfers[(4, 2)], transfers[(2, 1)], transfers[(2, 1)], transfers[(4, 2)],
            bottom, p4_preconditioner=jacobi[4], p2_preconditioner=jacobi[2], stage_callback=marker)
        result["middle"] = middle
        result["pc"] = PhysicalIntermediatePreconditioner(
            fine["physical_action"], positive["upper_cycle"], transfers[(6, 4)], middle,
            stage_callback=marker)
        marker("physical_intermediate_setup_complete", {"independent_p1_factors": 2})
        return result
    except BaseException:
        destroy_physical_intermediate_solver(result)
        raise


def release_physical_intermediate_solver_stack(bundle: dict) -> None:
    """Release both factors and auxiliary operators before physical recovery."""
    from .fullspace_same_mesh_hcurl_pmg_physical import release_p6_same_mesh_solver_stack
    from .physical_equivalent_fast import release_equivalent_fast

    release_equivalent_fast(bundle)
    bundle.pop("pc", None)
    bundle.pop("middle", None)
    factor = bundle.pop('reference_factor', None)
    if factor is not None:
        factor.destroy()
    matrix = bundle.pop('reference_matrix', None)
    if matrix is not None:
        matrix.destroy()
    factor = bundle.pop("shifted_p1_factor", None)
    if factor is not None:
        factor.destroy()
    matrix = bundle.pop("shifted_p1_matrix", None)
    if matrix is not None:
        matrix.destroy()
    for diagonal in bundle.pop("diagonals", {}).values():
        diagonal.destroy()
    actions = bundle.pop("actions", None)
    if actions is not None:
        destroy_physical_intermediate_actions(actions)
    positive = bundle.get("positive")
    if positive is not None and 'h6' in positive:
        positive.pop('h6').destroy()
        positive.pop('p6_shell').destroy()
    elif positive is not None and 'light_facts' not in positive:
        release_p6_same_mesh_solver_stack({"setup": positive})
    bundle["auxiliary_stack_released"] = True


def destroy_physical_intermediate_solver(bundle: dict) -> None:
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
    from .fullspace_same_mesh_hcurl_pmg_setup import destroy_p6_same_mesh_setup_bundle

    release_physical_intermediate_solver_stack(bundle)
    fine = bundle.pop("fine", None)
    if fine is not None:
        destroy_same_mesh_physical_action(fine)
    positive = bundle.pop("positive", None)
    if positive is not None and 'light_facts' not in positive:
        destroy_p6_same_mesh_setup_bundle(positive)
    bundle.clear()


def qualify_physical_intermediate_setup(bundle: dict, *, marker: Callable,
                                        resource_sample: Callable) -> dict:
    """One legal vector per pair on this actual mesh; no outer solve claim."""
    from contextlib import ExitStack
    from .fullspace_physical_intermediate import apply_owned

    levels, actions = bundle['levels'], bundle['actions']
    facts = {'classification': 'setup_identity_only', 'pairs': {},
             'rows': {str(p): int(levels['spaces'][p].dofmap.index_map.size_global)
                      for p in levels['spaces']}}
    facts['owned_slaves'] = {str(p): len(owned_slave_indices(levels['spaces'][p], levels['floquets'][p]))
                             for p in levels['spaces']}
    facts['independent_rows'] = {p: rows-facts['owned_slaves'][p] for p, rows in facts['rows'].items()}
    facts['mode_sha256'] = actions['mode_sha256']
    if (facts['rows']['6'] != 173802 or facts['mode_sha256'] !=
            'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2'):
        raise RuntimeError(f'frozen original storage rows/mode identity mismatch: {facts}')
    rng = np.random.default_rng(3901)
    for fine, coarse in actions['transfers']:
        marker('setup_vector_identity_started', {'fine': fine, 'coarse': coarse})
        resource_sample()
        with ExitStack() as resources:
            def own(vector):
                resources.callback(vector.destroy)
                return vector

            x, y = own(level_vector(levels, coarse)), own(level_vector(levels, fine))
            for degree, vector in ((coarse, x), (fine, y)):
                vector.array[:] = rng.normal(size=vector.getLocalSize()) + 1j*rng.normal(size=vector.getLocalSize())
                vector.array[owned_slave_indices(levels['spaces'][degree], levels['floquets'][degree])] = 0
                vector.scale(1/vector.norm())
            transfer = actions['transfers'][(fine, coarse)]
            px, phy = own(transfer.apply_primal(x)), own(transfer.apply_adjoint(y))
            left, right = y.dot(px), phy.dot(x)  # PETSc conjugates its argument.
            adjoint = abs(left-right)/max(abs(left), abs(right), np.finfo(float).tiny)
            errors = {}
            kinds = {'physical': {p: actions['physical'][p]['physical_action'] for p in (fine, coarse)}}
            if fine != 6:
                kinds['shifted'] = {p: actions['shifted'][p] for p in (fine, coarse)}
            for name, operators in kinds.items():
                direct = own(apply_owned(operators[coarse], x))
                applied = own(apply_owned(operators[fine], px))
                projected = own(transfer.apply_adjoint(applied))
                denominator = max(direct.norm(), projected.norm(), np.finfo(float).tiny)
                projected.axpy(-1, direct)
                errors[name] = projected.norm()/denominator
            facts['pairs'][f'{fine}->{coarse}'] = {'adjoint_relative_error': adjoint,
                'native_galerkin_relative_errors': errors, 'limit': 1e-10}
            if not np.isfinite([adjoint, *errors.values()]).all() or max(adjoint, *errors.values()) > 1e-10:
                raise RuntimeError(f'actual-mesh setup vector identity failed: {facts}')
            if coarse == 1:
                native = own(apply_owned(actions['shifted'][1], x))
                explicit = own(x.duplicate())
                bundle['shifted_p1_matrix'].mult(x, explicit)
                denominator = max(native.norm(), explicit.norm(), np.finfo(float).tiny)
                explicit.axpy(-1, native)
                error = explicit.norm()/denominator
                facts['shifted_p1_matrix_native_relative_error'] = error
                if not np.isfinite(error) or error > 1e-10:
                    raise RuntimeError('shifted p1 AIJ/native identity failed')
    marker('setup_vector_identity_complete', facts)
    return facts


def owned_slave_indices(space: Any, floquet: Any) -> np.ndarray:
    """Local owned indices only; no constraint expansion or reduction."""
    if int(space.dofmap.index_map_bs) != 1:
        raise ValueError("physical middle level requires scalar-blocked H(curl) DoFs")
    slaves = np.asarray(floquet.mpc.slaves, dtype=np.int32)
    return slaves[(slaves >= 0) & (slaves < space.dofmap.index_map.size_local)].copy()


def level_vector(setup: Mapping[str, Any], degree: int) -> Any:
    space = setup["floquets"][degree].mpc.function_space
    return create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])


class AlgebraicOwnerTransfer:
    """Borrow the full-field owner transfer and expose slave-zero algebraic P.

    The existing primal operation expands the coarse field and reconstructs
    fine slave values. Only those final fine slave entries are removed here.
    The dual operation already computes the matching P^H once; it is passed
    through unchanged. The adapter owns no transfer and no persistent Vec.
    """

    def __init__(self, owner: Any) -> None:
        self.owner = owner
        self.fine_slaves = owned_slave_indices(owner.fine_space, owner.fine_floquet)
        self.coarse_slaves = owned_slave_indices(owner.coarse_space, owner.coarse_floquet)
        self.primal_count = 0
        self.adjoint_count = 0

    def _require_algebraic(self, source: Any, slaves: np.ndarray) -> None:
        valid = bool(np.all(source.array[slaves] == 0.0))
        if not self.owner.comm.allreduce(valid, op=MPI.LAND):
            raise ValueError("algebraic transfer input must have zero owned slave entries")

    def apply_primal(self, source: Any) -> Any:
        self._require_algebraic(source, self.coarse_slaves)
        space = self.owner.fine_space
        target = create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])
        try:
            self.owner.apply_primal_into(source, target)
            target.array[self.fine_slaves] = 0.0
            self.primal_count += 1
            return target
        except BaseException:
            target.destroy()
            raise

    def apply_adjoint(self, source: Any) -> Any:
        self._require_algebraic(source, self.fine_slaves)
        space = self.owner.coarse_space
        target = create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])
        try:
            self.owner.apply_adjoint_into(source, target)
            self._require_algebraic(target, self.coarse_slaves)
            self.adjoint_count += 1
            return target
        except BaseException:
            target.destroy()
            raise


def fine_volume_quadrature_metadata(setup: Mapping[str, Any], cfg: Any) -> tuple[tuple[dict, dict], list]:
    """Read actual same-ABI FFCx analysis of the unchanged fine action forms.

    This performs pullbacks, geometry lowering, scaling and restriction
    analysis, but generates or compiles no C. The fixed isotropic components
    must each have one common integration rule across their material tags.
    """
    import ufl
    from dolfinx import fem
    from ffcx.analysis import analyze_ufl_objects
    from .common_3d_forms import _build_physical_volume_terms

    space = setup["spaces"][6]
    dx = ufl.Measure("dx", domain=setup["mesh"], subdomain_data=setup["mesh_data"].cell_tags)
    forms = _build_physical_volume_terms(
        cfg, ufl.TrialFunction(space), ufl.TestFunction(space), dx)
    coefficient = fem.Function(setup["floquets"][6].mpc.function_space)
    metadata, records = [], []
    for name, form in zip(("curl", "material_mass"), forms, strict=True):
        analysis = analyze_ufl_objects([ufl.action(form, coefficient)], np.dtype(np.complex128))
        rules = set()
        for group in analysis.form_data[0].integral_data:
            for integral in group.integrals:
                rule = integral.metadata()
                if rule["quadrature_rule"] == "custom":
                    raise ValueError("custom fine quadrature is not qualified for this middle-level builder")
                pair = (int(rule["quadrature_degree"]), str(rule["quadrature_rule"]))
                rules.add(pair)
                records.append({"component": name, "integral_type": integral.integral_type(),
                                "subdomain_id": integral.subdomain_id(),
                                "quadrature_degree": pair[0], "quadrature_rule": pair[1]})
        if len(rules) != 1:
            raise ValueError("fine component has differing per-tag integration rules; explicit mapping required")
        degree, rule = rules.pop()
        metadata.append({"quadrature_degree": degree, "quadrature_rule": rule})
    return tuple(metadata), records


def build_physical_intermediate_actions(
    setup: Mapping[str, Any],
    cfg: Any,
    *,
    fine_bundle: Mapping[str, Any] | None = None,
    stage_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
    reference: bool = False,
) -> dict[str, Any]:
    """Build native 4/2/1 physical and shifted actions with the fine inventory.

    When supplied, the fine bundle is borrowed and left intact. Without it,
    the existing native p6 helper builds the fine action (tiny FE tests only
    until the whole-workflow watchdog is qualified). No numerical solve runs.
    """
    import ufl
    from dolfinx import fem
    from .fullspace_mpc_action import build_fullspace_mpc_form_action
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action
    from .fullspace_same_mesh_hcurl_pmg_runtime import build_same_mesh_hcurl_owner_transfer
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if any(degree not in setup["spaces"] for degree in ((6, 4) if reference else PHYSICAL_DEGREES)):
        raise ValueError("physical middle setup requires same-mesh degrees 6, 4, 2, 1")
    if "mass" not in setup or "mu" not in setup:
        raise ValueError("setup must include positive coefficients from the physical tags")
    quadratures, integral_records = fine_volume_quadrature_metadata(setup, cfg)
    result: dict[str, Any] = {
        "setup": setup, "physical": {}, "mass": {}, "mass_owned": {},
        "shifted": {}, "owners": {}, "transfers": {},
        "owned_physical_degrees": [], "volume_quadrature_metadata": quadratures,
        "fine_integral_metadata": integral_records,
        "factor_count": 0, "global_aij_count": 0,
    }

    def marker(name: str, degree: int) -> None:
        if stage_callback is not None:
            stage_callback(name, {"degree": degree})

    try:
        if fine_bundle is None:
            marker("native_physical_started", 6)
            fine_bundle = build_same_mesh_physical_action(setup, cfg, 6)
            result["owned_physical_degrees"].append(6)
        elif fine_bundle["setup"] is not setup:
            raise ValueError("borrowed fine action must use this exact setup")
        result["physical"][6] = fine_bundle
        inventory = (fine_bundle["modes"], fine_bundle["mode_rows"], fine_bundle["mode_sha256"])
        result["mode_sha256"] = fine_bundle["mode_sha256"]
        result["dtn_quadrature_degree"] = fine_bundle["dtn_quadrature_degree"]
        if reference:
            marker('native_physical_started', 4)
            result['physical'][4] = build_same_mesh_physical_action(setup, cfg, 4,
                mode_inventory=inventory, volume_quadrature_metadata=quadratures)
            result['owned_physical_degrees'].append(4)
            marker('owner_transfer_started', 6)
            owner = build_same_mesh_hcurl_owner_transfer(setup['spaces'][6], setup['floquets'][6],
                setup['spaces'][4], setup['floquets'][4])
            result['owners'][(6, 4)] = owner
            result['transfers'][(6, 4)] = AlgebraicOwnerTransfer(owner)
            return result
        # Existing positive mass coefficient = k0^2 |eps|. W omits k0^2.
        weight = fem.Function(setup["mass"].function_space)
        weight.x.array[:] = np.maximum(setup["mass"].x.array.real / cfg.k0**2, 1.0e-12)
        weight.x.scatter_forward()
        result["weight"] = weight
        result["weight_definition"] = "max(abs(epsilon_r),1e-12), without k0_squared"
        for degree in (4, 2, 1):
            marker("native_physical_started", degree)
            bundle = build_same_mesh_physical_action(
                setup, cfg, degree, mode_inventory=inventory,
                volume_quadrature_metadata=quadratures)
            result["physical"][degree] = bundle
            result["owned_physical_degrees"].append(degree)
            if bundle["dtn_quadrature_degree"] != result["dtn_quadrature_degree"]:
                raise ValueError("native lower level changed the fine DtN quadrature")
            marker("positive_mass_started", degree)
            space = setup["spaces"][degree]
            form = weight * ufl.inner(ufl.TrialFunction(space), ufl.TestFunction(space)) * ufl.dx(
                metadata=quadratures[1])
            action = build_fullspace_mpc_form_action(
                form, space,
                mpc=setup["floquets"][degree].mpc, slave_row_identity=False,
                jit_options=SAME_MESH_JIT_OPTIONS)
            result["mass_owned"][degree] = action
            result["mass"][degree] = BorrowedActionAdapter(action)
            result["shifted"][degree] = ShiftedPhysicalAction(
                result["physical"][degree]["physical_action"], result["mass"][degree], cfg.k0)
            marker("native_level_complete", degree)
        for fine, coarse in PHYSICAL_PAIRS:
            marker("owner_transfer_started", fine)
            owner = build_same_mesh_hcurl_owner_transfer(
                setup["spaces"][fine], setup["floquets"][fine],
                setup["spaces"][coarse], setup["floquets"][coarse])
            result["owners"][(fine, coarse)] = owner
            result["transfers"][(fine, coarse)] = AlgebraicOwnerTransfer(owner)
        return result
    except BaseException:
        destroy_physical_intermediate_actions(result)
        raise


def destroy_physical_intermediate_actions(bundle: dict[str, Any]) -> None:
    """Release only created actions and owners; preserve borrowed setup/fine."""
    from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action

    for owner in bundle.get("owners", {}).values():
        owner.destroy()
    for action in bundle.get("mass_owned", {}).values():
        action.destroy()
    for degree in bundle.get("owned_physical_degrees", ()):
        destroy_same_mesh_physical_action(bundle["physical"][degree])
    bundle.clear()


def build_positive_level_jacobi(setup: Mapping[str, Any], degree: int) -> tuple[Any, Any, dict]:
    """Build the existing exact constrained B diagonal, and bound imaginary roundoff.

    Hermitian diagonal entries are real. The explicit tolerance scales with
    machine precision and the local element summation dimension; it is not a
    tolerance for the physical equation or a modification of its coefficients.
    """
    from dolfinx import fem
    from .fullspace_physical_intermediate import PositiveDiagonalJacobi
    from .fullspace_same_mesh_hcurl_pmg_global import same_mesh_positive_form
    from .fullspace_same_mesh_hcurl_pmg_p6 import build_constrained_jacobi_diagonal
    from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS

    if degree not in (4, 2):
        raise ValueError('physical middle Jacobi is only required at p4 and p2')
    space = setup['spaces'][degree]
    form = same_mesh_positive_form(space, curl_coefficient=setup['mu'], mass_coefficient=setup['mass'])
    diagonal = build_constrained_jacobi_diagonal(
        fem.form(form, jit_options=dict(SAME_MESH_JIT_OPTIONS)), setup['floquets'][degree].mpc)
    try:
        values = diagonal.array
        if np.any(values.real <= 0) or not np.all(np.isfinite(values)):
            raise RuntimeError('positive FE diagonal has nonpositive or nonfinite entries')
        relative = float(setup['mesh'].comm.allreduce(
            float(np.max(np.abs(values.imag) / values.real)), op=MPI.MAX))
        limit = 64 * np.finfo(float).eps * int(space.element.space_dimension)
        facts = {'degree': degree, 'imag_over_real_max': relative, 'roundoff_limit': limit,
                 'roundoff_rule': '64*eps(float64)*element_space_dimension',
                 'source': 'exact constrained diagonal of positive curl_plus_k0_squared_abs_epsilon_mass',
                 'matrix_free_global': True}
        if relative > limit:
            raise RuntimeError(f'positive diagonal imaginary component exceeds roundoff bound: {facts}')
        diagonal.array[:] = diagonal.array.real
        return PositiveDiagonalJacobi(diagonal), diagonal, facts
    except BaseException:
        diagonal.destroy()
        raise
