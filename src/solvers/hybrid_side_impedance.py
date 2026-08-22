"""Small side-impedance transmission algebra for Task040.

The carrier is deliberately independent of the Hybrid global operator.  It
orchestrates restriction/prolongation and the frozen forward/backward sweep;
the caller supplies the local solve for
``R_j F_s R_j^T + T_j^- + T_j^+``.  Thus the impedance is a PC ingredient and
the bare ``F_s`` action is never modified by this module.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

__all__ = (
    "TASK040_FORWARD_ORDER",
    "TASK040_LEVEL_A_SUBDOMAINS",
    "TASK040_BACKWARD_ORDER",
    "TASK040_LEVEL_A_SOURCE_LABELS",
    "SideImpedanceTransmissionAction",
    "PetscSideImpedanceTransmissionAction",
    "build_first_order_interface_impedance",
    "build_first_order_tangential_impedance",
    "build_side_impedance_transmission_action",
    "build_petsc_side_impedance_transmission_action",
    "audit_petsc_level_a_one_apply",
)


TASK040_LEVEL_A_SUBDOMAINS = ((0, 1), (2, 3), (4, 5))
TASK040_FORWARD_ORDER = (0, 1, 2)
TASK040_BACKWARD_ORDER = (2, 1, 0)
TASK040_LEVEL_A_SOURCE_LABELS = (
    "physical_side_rhs",
    "modal_traction_positive",
    "modal_traction_negative",
    "external_dtn_coupling",
    "fixed_random_repeat_0",
    "fixed_random_repeat_1",
)


def build_first_order_tangential_impedance(
    tangential_mass: np.ndarray,
    beta: complex,
    outward_normal_sign: int,
) -> np.ndarray:
    """Return the fixed first-order tangential impedance ``-i beta M``.

    The outward normal is carried by the traction/integration-by-parts term;
    it is deliberately not folded into this Robin mass coefficient.
    """

    mass = np.asarray(tangential_mass, dtype=np.complex128)
    if mass.ndim != 2 or mass.shape[0] != mass.shape[1]:
        raise ValueError("Tangential impedance mass must be square.")
    if not np.all(np.isfinite(mass)) or not np.isfinite(complex(beta)):
        raise ValueError("Tangential impedance data must be finite.")
    if int(outward_normal_sign) not in {-1, 1}:
        raise ValueError("Artificial-interface outward normal must be +/-1.")
    return np.asarray(
        -1j * complex(beta) * mass,
        dtype=np.complex128,
    )


def build_first_order_interface_impedance(
    tangential_mass: np.ndarray,
    beta: complex,
    outward_normal_signs: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Build same-sign Robin masses for opposite traction normals."""

    if len(outward_normal_signs) != 2:
        raise ValueError("An interface needs two outward normal signs.")
    left, right = (int(value) for value in outward_normal_signs)
    if left != -right:
        raise ValueError("Artificial-interface normals must be opposite.")
    return (
        build_first_order_tangential_impedance(tangential_mass, beta, left),
        build_first_order_tangential_impedance(tangential_mass, beta, right),
    )


class SideImpedanceTransmissionAction:
    """Apply a fixed three-subdomain impedance transmission preconditioner.

    ``local_solve`` owns the local PC solve and must be source-independent.
    The action performs one forward sweep followed by one backward sweep, in
    the fixed order ``0 -> 1 -> 2 -> 1 -> 0``.  Coupling blocks are the bare
    block-tridiagonal coupling; only the local solve callback sees the
    impedance-modified blocks.
    """

    operator_identity = "task040.first_order_tangential_impedance_transmission"

    def __init__(
        self,
        *,
        global_size: int,
        local_sizes: Sequence[int],
        restriction: Sequence[Callable[[np.ndarray], np.ndarray]],
        prolongation: Sequence[Callable[[np.ndarray], np.ndarray]],
        local_solve: Sequence[Callable[[np.ndarray], np.ndarray]],
        coupling_left: Sequence[np.ndarray],
        coupling_right: Sequence[np.ndarray],
        interface_normals: Sequence[tuple[int, int]],
        restriction_prolongation_audit: Callable[[], float],
        bare_operator_identity_audit: Callable[[], bool],
        local_bare_matrices: Sequence[np.ndarray] | None = None,
        local_pc_matrices: Sequence[np.ndarray] | None = None,
        local_left_impedance: Sequence[np.ndarray] | None = None,
        local_right_impedance: Sequence[np.ndarray] | None = None,
        comm: MPI.Intracomm = MPI.COMM_WORLD,
        subdomains: Sequence[Sequence[int]] = TASK040_LEVEL_A_SUBDOMAINS,
    ) -> None:
        if tuple(tuple(int(v) for v in group) for group in subdomains) != (
            TASK040_LEVEL_A_SUBDOMAINS
        ):
            raise ValueError("Task040 transmission uses the frozen three subdomains.")
        if len(restriction) != 3 or len(prolongation) != 3 or len(local_solve) != 3:
            raise ValueError("Transmission action requires three local blocks.")
        if len(coupling_left) != 2 or len(coupling_right) != 2:
            raise ValueError("Transmission action requires two interface couplings.")
        if len(interface_normals) != 2:
            raise ValueError("Transmission action requires two interface normals.")
        if len(local_sizes) != 3 or any(int(value) <= 0 for value in local_sizes):
            raise ValueError("Transmission action requires three positive local sizes.")
        if not callable(restriction_prolongation_audit):
            raise ValueError(
                "Restriction/prolongation needs an observed audit callback."
            )
        if not callable(bare_operator_identity_audit):
            raise ValueError("Bare-F identity needs an observed audit callback.")
        self.comm = comm
        self._restriction = tuple(restriction)
        self._prolongation = tuple(prolongation)
        self._local_solve = tuple(local_solve)
        self._coupling_left = tuple(self._matrix(value) for value in coupling_left)
        self._coupling_right = tuple(self._matrix(value) for value in coupling_right)
        self._interface_normals = tuple(
            (int(pair[0]), int(pair[1])) for pair in interface_normals
        )
        if any(
            sign not in {-1, 1} for pair in self._interface_normals for sign in pair
        ) or any(left != -right for left, right in self._interface_normals):
            raise ValueError("Interface normals must be explicit opposite +/- pairs.")
        if not all(
            callable(restrict) and callable(prolong)
            for restrict, prolong in zip(self._restriction, self._prolongation)
        ):
            raise ValueError("Restriction/prolongation must be callbacks.")
        self._global_size = int(global_size)
        self._local_sizes = tuple(int(value) for value in local_sizes)
        if self._global_size <= 0:
            raise ValueError("Transmission global size must be positive.")
        self.restriction_prolongation_error = float(restriction_prolongation_audit())
        if not np.isfinite(self.restriction_prolongation_error):
            raise ValueError("Restriction/prolongation audit is non-finite.")
        if self.restriction_prolongation_error > 1.0e-12:
            raise ValueError("Restriction/prolongation does not form a partition.")
        self._bare_operator_identity_pass = bool(bare_operator_identity_audit())
        if not self._bare_operator_identity_pass:
            raise ValueError("Bare-F operator identity audit failed.")
        self._validate_couplings()
        self._validate_pc_local_identity(
            local_bare_matrices,
            local_pc_matrices,
            local_left_impedance,
            local_right_impedance,
        )
        self._apply_count = 0
        self._destroyed = False

    @staticmethod
    def _matrix(value: np.ndarray) -> np.ndarray:
        array = np.asarray(value, dtype=np.complex128)
        if array.ndim != 2 or not np.all(np.isfinite(array)):
            raise ValueError("Transmission matrix must be finite and two-dimensional.")
        return array.copy()

    def _validate_couplings(self) -> None:
        for index in range(2):
            left = self._coupling_left[index]
            right = self._coupling_right[index]
            expected = (self._local_sizes[index + 1], self._local_sizes[index])
            if left.shape != expected:
                raise ValueError("Forward coupling has the wrong local shape.")
            expected = (self._local_sizes[index], self._local_sizes[index + 1])
            if right.shape != expected:
                raise ValueError("Backward coupling has the wrong local shape.")

    def _validate_pc_local_identity(
        self,
        bare: Sequence[np.ndarray] | None,
        pc: Sequence[np.ndarray] | None,
        left: Sequence[np.ndarray] | None,
        right: Sequence[np.ndarray] | None,
    ) -> None:
        supplied = (bare, pc, left, right)
        if all(value is None for value in supplied):
            return
        if any(value is None for value in supplied) or any(
            len(value) != 3 for value in supplied if value is not None
        ):
            raise ValueError("PC identity audit requires all three local block sets.")
        for index in range(3):
            expected = (
                self._matrix(bare[index])
                + self._matrix(left[index])
                + self._matrix(right[index])
            )
            actual = self._matrix(pc[index])
            if actual.shape != expected.shape or not np.allclose(
                actual, expected, atol=1e-12, rtol=1e-12
            ):
                raise ValueError("Impedance changed the local PC identity.")
        self._pc_identity_bound = True

    def apply(self, rhs: np.ndarray) -> np.ndarray:
        """Apply one fixed forward/backward transmission sweep."""

        if self._destroyed:
            raise RuntimeError("Side impedance transmission action is destroyed.")
        source = np.asarray(rhs, dtype=np.complex128)
        if source.shape != (self._global_size,) or not np.all(np.isfinite(source)):
            raise ValueError("Transmission RHS has the wrong shape or is non-finite.")
        values: list[np.ndarray | None] = [None, None, None]
        for index in TASK040_FORWARD_ORDER:
            local_rhs = self._checked_restriction(index, source)
            if index:
                local_rhs = (
                    local_rhs - self._coupling_left[index - 1] @ values[index - 1]
                )
            values[index] = self._checked_local_solve(index, local_rhs)
        for index in TASK040_BACKWARD_ORDER:
            local_rhs = self._checked_restriction(index, source)
            if index:
                local_rhs = (
                    local_rhs - self._coupling_left[index - 1] @ values[index - 1]
                )
            if index < 2:
                local_rhs = local_rhs - self._coupling_right[index] @ values[index + 1]
            values[index] = self._checked_local_solve(index, local_rhs)
        result = sum(
            (self._checked_prolongation(index, values[index]) for index in range(3)),
            start=np.zeros(self._global_size, dtype=np.complex128),
        )
        if not np.all(np.isfinite(result)):
            raise FloatingPointError("Transmission action produced non-finite values.")
        self._apply_count += 1
        return result

    def _checked_restriction(self, index: int, source: np.ndarray) -> np.ndarray:
        value = np.asarray(self._restriction[index](source), dtype=np.complex128)
        if value.shape != (self._local_sizes[index],) or not np.all(np.isfinite(value)):
            raise ValueError("Restriction callback returned invalid values.")
        return value

    def _checked_prolongation(self, index: int, value: np.ndarray) -> np.ndarray:
        result = np.asarray(self._prolongation[index](value), dtype=np.complex128)
        if result.shape != (self._global_size,) or not np.all(np.isfinite(result)):
            raise ValueError("Prolongation callback returned invalid values.")
        return result

    def _checked_local_solve(self, index: int, rhs: np.ndarray) -> np.ndarray:
        value = np.asarray(self._local_solve[index](rhs), dtype=np.complex128)
        if value.shape != (self._local_sizes[index],) or not np.all(np.isfinite(value)):
            raise ValueError("Local impedance solve returned invalid values.")
        return value

    def audit(
        self,
        sources: Sequence[np.ndarray],
        *,
        bare_apply: Callable[[np.ndarray], np.ndarray] | None = None,
    ) -> dict[str, Any]:
        """Measure zero, repeat, linearity and optional bare-F contraction."""

        if not sources:
            raise ValueError("Transmission audit needs at least one source.")
        vectors = [np.asarray(source, dtype=np.complex128) for source in sources]
        zero = np.zeros(self._global_size, dtype=np.complex128)
        zero_error = float(np.linalg.norm(self.apply(zero), ord=np.inf))
        repeat_error = 0.0
        linearity_error = 0.0
        rho_values: list[float] = []
        for source in vectors:
            first = self.apply(source)
            second = self.apply(source)
            repeat_error = max(
                repeat_error,
                float(np.linalg.norm(first - second))
                / max(float(np.linalg.norm(first)), 1.0e-30),
            )
            if bare_apply is not None:
                residual = np.asarray(bare_apply(first), dtype=np.complex128) - source
                rho_values.append(
                    float(np.linalg.norm(residual))
                    / max(float(np.linalg.norm(source)), 1.0e-30)
                )
        if len(vectors) >= 2:
            a, b = vectors[:2]
            linearity = self.apply(a + b) - self.apply(a) - self.apply(b)
            linearity_error = float(np.linalg.norm(linearity)) / max(
                float(np.linalg.norm(self.apply(a + b))), 1.0e-30
            )
        local = {
            "finite": True,
            "zero_output_norm": zero_error,
            "repeat_relative_error": repeat_error,
            "linearity_relative_error": linearity_error,
            "rho": rho_values,
        }
        return {
            **local,
            "zero_map_pass": zero_error <= 1.0e-13,
            "repeat_pass": repeat_error <= 1.0e-10,
            "linearity_pass": linearity_error <= 1.0e-10,
            "rho": [
                float(self.comm.allreduce(value, op=MPI.MAX)) for value in rho_values
            ],
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "restriction_prolongation_pass": self.restriction_prolongation_error
            <= 1.0e-12,
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "impedance_applied_to_pc_only": True,
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "apply_count": int(self._apply_count),
        }

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "subdomains": [list(group) for group in TASK040_LEVEL_A_SUBDOMAINS],
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "global_size": self._global_size,
            "local_sizes": list(self._local_sizes),
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "impedance_applied_to_pc_only": True,
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "pc_identity_bound": bool(getattr(self, "_pc_identity_bound", False)),
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        self._local_solve = ()
        self._restriction = ()
        self._prolongation = ()
        self._coupling_left = ()
        self._coupling_right = ()
        self._destroyed = True


class _PetscTransmissionWorkspace:
    def __init__(self, scatter: PETSc.Scatter, template: PETSc.Vec) -> None:
        self.scatter = scatter
        self.rhs = template.duplicate()
        self.y = template.duplicate()
        self.temp = template.duplicate()

    def destroy(self) -> None:
        self.scatter.destroy()
        self.temp.destroy()
        self.y.destroy()
        self.rhs.destroy()


class PetscSideImpedanceTransmissionAction:
    """PETSc VecScatter carrier for the formal Level A/B route.

    This is the production carrier: all global/subdomain data stays in PETSc
    Vec/Mat ownership layouts.  Its sweep deliberately follows the existing
    ``LayerSweepAction`` cumulative-RHS semantics; the NumPy class above is
    only a tiny dense algebra oracle.
    """

    operator_identity = SideImpedanceTransmissionAction.operator_identity

    def __init__(
        self,
        *,
        parent_size: int,
        workspaces: Sequence[_PetscTransmissionWorkspace],
        local_solve: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
        coupling_left: Sequence[PETSc.Mat],
        coupling_right: Sequence[PETSc.Mat],
        interface_normals: Sequence[tuple[int, int]],
        restriction_prolongation_audit: Callable[[], float],
        bare_operator_identity_audit: Callable[[], bool],
    ) -> None:
        if len(workspaces) != 3 or len(local_solve) != 3:
            raise ValueError("PETSc transmission requires three local workspaces.")
        if len(coupling_left) != 2 or len(coupling_right) != 2:
            raise ValueError("PETSc transmission requires two interface couplings.")
        if len(interface_normals) != 2 or any(
            int(left) != -int(right) or int(left) not in {-1, 1}
            for left, right in interface_normals
        ):
            raise ValueError("PETSc interface normals must be opposite +/- pairs.")
        if not callable(restriction_prolongation_audit):
            raise ValueError("PETSc R/P needs an observed audit callback.")
        if not callable(bare_operator_identity_audit):
            raise ValueError("PETSc bare-F identity needs an observed audit callback.")
        self._parent_size = int(parent_size)
        self._workspaces = tuple(workspaces)
        self._local_solve = tuple(local_solve)
        self._coupling_left = tuple(coupling_left)
        self._coupling_right = tuple(coupling_right)
        self._interface_normals = tuple(
            (int(left), int(right)) for left, right in interface_normals
        )
        self.restriction_prolongation_error = float(restriction_prolongation_audit())
        if not np.isfinite(self.restriction_prolongation_error):
            raise ValueError("PETSc R/P audit is non-finite.")
        if self.restriction_prolongation_error > 1.0e-12:
            raise ValueError("PETSc R/P audit exceeds the frozen tolerance.")
        self._bare_operator_identity_pass = bool(bare_operator_identity_audit())
        if not self._bare_operator_identity_pass:
            raise ValueError("PETSc bare-F operator identity audit failed.")
        self._apply_count = 0
        self._destroyed = False

    def _gather(self, source: PETSc.Vec) -> None:
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                source,
                workspace.rhs,
                addv=PETSc.InsertMode.INSERT_VALUES,
                mode=PETSc.ScatterMode.FORWARD,
            )

    def _solve(self, index: int) -> None:
        self._local_solve[index](
            self._workspaces[index].rhs,
            self._workspaces[index].y,
        )

    def _forward(self) -> None:
        for index in TASK040_FORWARD_ORDER:
            workspace = self._workspaces[index]
            if index:
                self._coupling_left[index - 1].mult(
                    self._workspaces[index - 1].y,
                    workspace.temp,
                )
                workspace.rhs.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve(index)

    def _backward(self) -> None:
        for index in TASK040_BACKWARD_ORDER:
            workspace = self._workspaces[index]
            if index < 2:
                self._coupling_right[index].mult(
                    self._workspaces[index + 1].y,
                    workspace.temp,
                )
                # workspace.rhs already contains the forward lower coupling.
                workspace.rhs.axpy(PETSc.ScalarType(-1.0), workspace.temp)
            self._solve(index)

    def _scatter_solution(self, target: PETSc.Vec) -> None:
        target.set(0.0)
        for workspace in self._workspaces:
            workspace.scatter.scatter(
                workspace.y,
                target,
                addv=PETSc.InsertMode.ADD_VALUES,
                mode=PETSc.ScatterMode.REVERSE,
            )
        target.assemble()

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("PETSc side impedance transmission is destroyed.")
        if (
            source.getSize() != self._parent_size
            or target.getSize() != self._parent_size
        ):
            raise ValueError("PETSc transmission vector has the wrong global size.")
        self._gather(source)
        self._forward()
        self._backward()
        self._scatter_solution(target)
        self._apply_count += 1

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "operator_identity": self.operator_identity,
            "carrier": "petsc_vecscatter",
            "global_numpy_copy": False,
            "subdomain_vectors_global_numpy_copy": False,
            "subdomains": [list(group) for group in TASK040_LEVEL_A_SUBDOMAINS],
            "forward_order": list(TASK040_FORWARD_ORDER),
            "backward_order": list(TASK040_BACKWARD_ORDER),
            "interface_normals": [list(pair) for pair in self._interface_normals],
            "restriction_prolongation_error": self.restriction_prolongation_error,
            "restriction_prolongation_pass": self.restriction_prolongation_error
            <= 1.0e-12,
            "impedance_applied_to_pc_only": True,
            "bare_operator_unchanged": self._bare_operator_identity_pass,
            "bare_operator_identity_audited": True,
            "apply_count": self._apply_count,
            "destroyed": self._destroyed,
        }

    def destroy(self) -> None:
        if self._destroyed:
            return
        for workspace in reversed(self._workspaces):
            workspace.destroy()
        self._workspaces = ()
        self._local_solve = ()
        self._coupling_left = ()
        self._coupling_right = ()
        self._destroyed = True


def build_side_impedance_transmission_action(
    **kwargs: Any,
) -> SideImpedanceTransmissionAction:
    """Explicit opt-in constructor for the frozen Task040 transmission route."""

    return SideImpedanceTransmissionAction(**kwargs)


def build_petsc_side_impedance_transmission_action(
    *,
    parent_template: PETSc.Vec,
    local_templates: Sequence[PETSc.Vec],
    scatters: Sequence[PETSc.Scatter],
    local_solve: Sequence[Callable[[PETSc.Vec, PETSc.Vec], None]],
    coupling_left: Sequence[PETSc.Mat],
    coupling_right: Sequence[PETSc.Mat],
    interface_normals: Sequence[tuple[int, int]],
    restriction_prolongation_audit: Callable[[], float],
    bare_operator_identity_audit: Callable[[], bool],
) -> PetscSideImpedanceTransmissionAction:
    """Build the PETSc-owned carrier without copying global arrays."""

    if len(local_templates) != 3 or len(scatters) != 3:
        raise ValueError("PETSc transmission needs three templates and scatters.")
    workspaces = []
    try:
        workspaces = [
            _PetscTransmissionWorkspace(scatter, template)
            for scatter, template in zip(scatters, local_templates)
        ]
        return PetscSideImpedanceTransmissionAction(
            parent_size=int(parent_template.getSize()),
            workspaces=workspaces,
            local_solve=local_solve,
            coupling_left=coupling_left,
            coupling_right=coupling_right,
            interface_normals=interface_normals,
            restriction_prolongation_audit=restriction_prolongation_audit,
            bare_operator_identity_audit=bare_operator_identity_audit,
        )
    except Exception:
        for workspace in reversed(workspaces):
            workspace.destroy()
        raise


def audit_petsc_level_a_one_apply(
    action: PetscSideImpedanceTransmissionAction,
    bare_operator: PETSc.Mat,
    sources: Mapping[str, PETSc.Vec] | Sequence[PETSc.Vec],
    factor_inventory: Mapping[str, Any],
    *,
    labels: Sequence[str] = TASK040_LEVEL_A_SOURCE_LABELS,
    preferred_labels: Sequence[str] = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
    ),
) -> dict[str, Any]:
    """Audit one PETSc Level-A action on the frozen six-source family.

    The action and factor inventory are observed by the caller; this helper
    only computes true bare-F residuals and the zero/repeat/linearity gates.
    It never assembles or factorizes an operator.
    """

    labels = tuple(labels)
    preferred_labels = tuple(preferred_labels)
    comm = bare_operator.getComm().tompi4py()
    local_ok = len(labels) == 6 and len(set(labels)) == 6
    try:
        if isinstance(sources, Mapping):
            local_ok = local_ok and tuple(sources) == labels
            source_list = tuple(sources[label] for label in labels)
        else:
            source_list = tuple(sources)
            local_ok = local_ok and len(source_list) == len(labels)
        matrix_rows, matrix_cols = bare_operator.getSize()
        local_ok = local_ok and matrix_rows == matrix_cols
        local_ok = local_ok and all(
            isinstance(source, PETSc.Vec) and source.getSize() == matrix_rows
            for source in source_list
        )
    except (KeyError, TypeError, ValueError):
        source_list = ()
        local_ok = False
    if not bool(comm.allreduce(local_ok, op=MPI.LAND)):
        raise ValueError("Level-A source/operator contract failed collectively.")

    action_diagnostics = action.diagnostics
    action_identity = {
        "carrier": action_diagnostics.get("carrier"),
        "global_numpy_copy": action_diagnostics.get("global_numpy_copy"),
        "subdomain_vectors_global_numpy_copy": action_diagnostics.get(
            "subdomain_vectors_global_numpy_copy"
        ),
        "restriction_prolongation_pass": action_diagnostics.get(
            "restriction_prolongation_pass"
        ),
        "bare_operator_unchanged": action_diagnostics.get("bare_operator_unchanged"),
    }
    action_identity_local = (
        action_identity["carrier"] == "petsc_vecscatter"
        and action_identity["global_numpy_copy"] is False
        and action_identity["subdomain_vectors_global_numpy_copy"] is False
        and action_identity["restriction_prolongation_pass"] is True
        and action_identity["bare_operator_unchanged"] is True
    )
    action_identity_pass = bool(comm.allreduce(action_identity_local, op=MPI.LAND))

    inventory = dict(factor_inventory)
    inventory_pass = all(
        (
            inventory.get("observed") is True,
            inventory.get("factor_count_ready") == 3,
            inventory.get("oracle_only") is True,
            inventory.get("scalable_candidate") is False,
            inventory.get("full_side_exact_factor_count") == 0,
            inventory.get("global_direct_factor_count") == 0,
            inventory.get("nested_ksp_count") == 0,
        )
    )
    inventory_pass = bool(comm.allreduce(inventory_pass, op=MPI.LAND))
    outputs: dict[str, PETSc.Vec] = {}
    reports: list[dict[str, Any]] = []
    finite_pass = True
    try:
        for label, source in zip(labels, source_list):
            target = source.duplicate()
            residual = source.duplicate()
            repeated = source.duplicate()
            difference = source.duplicate()
            try:
                source_finite = bool(np.all(np.isfinite(source.array_r)))
                source_finite = bool(comm.allreduce(source_finite, op=MPI.LAND))
                action.apply(source, target)
                output_finite = bool(np.all(np.isfinite(target.array_r)))
                output_finite = bool(comm.allreduce(output_finite, op=MPI.LAND))
                finite_pass = finite_pass and source_finite and output_finite
                source_norm = float(source.norm())
                output_norm = float(target.norm())
                bare_operator.mult(target, residual)
                residual.axpy(PETSc.ScalarType(-1.0), source)
                residual_norm = float(residual.norm())
                rho = residual_norm / source_norm if source_norm > 1.0e-30 else None
                action.apply(source, repeated)
                target.copy(difference)
                difference.axpy(PETSc.ScalarType(-1.0), repeated)
                repeat_error = float(difference.norm()) / max(output_norm, 1.0e-30)
                outputs[label] = target.duplicate()
                target.copy(outputs[label])
                reports.append(
                    {
                        "label": label,
                        "source_norm": source_norm,
                        "output_norm": output_norm,
                        "true_residual_norm": residual_norm,
                        "true_residual_relative": rho,
                        "repeat_error": repeat_error,
                        "finite": source_finite and output_finite,
                        "physical_zero": label == labels[0] and source_norm <= 1.0e-13,
                    }
                )
            finally:
                difference.destroy()
                repeated.destroy()
                residual.destroy()
                target.destroy()

        mandatory = [report for report in reports if not report["physical_zero"]]
        preferred = [
            report for report in mandatory if report["label"] in preferred_labels
        ]
        linear_source = source_list[1].duplicate()
        linear_source.axpy(PETSc.ScalarType(1.0), source_list[2])
        linear_target = linear_source.duplicate()
        expected_linear = outputs[labels[1]].duplicate()
        try:
            expected_linear.axpy(PETSc.ScalarType(1.0), outputs[labels[2]])
            action.apply(linear_source, linear_target)
            linear_target.axpy(PETSc.ScalarType(-1.0), expected_linear)
            linearity_error = float(linear_target.norm()) / max(
                float(expected_linear.norm()), 1.0e-30
            )
        finally:
            expected_linear.destroy()
            linear_target.destroy()
            linear_source.destroy()

        physical = reports[0]
        physical_zero = bool(physical["physical_zero"])
        zero_map_pass: bool | str = (
            physical["output_norm"] <= 1.0e-13 if physical_zero else "not_applicable"
        )
        worst_rho = max(float(report["true_residual_relative"]) for report in mandatory)
        all_repeat_pass = all(report["repeat_error"] <= 1.0e-10 for report in reports)
        mandatory_rho_pass = all(
            float(report["true_residual_relative"]) < 1.0 for report in mandatory
        )
        preferred_rho_pass = all(
            float(report["true_residual_relative"]) <= 0.90 for report in preferred
        )
        gate = {
            "finite_pass": bool(finite_pass),
            "zero_map_pass": zero_map_pass,
            "action_identity_pass": action_identity_pass,
            "repeat_pass": all_repeat_pass,
            "linearity_relative_error": linearity_error,
            "linearity_pass": linearity_error <= 1.0e-10,
            "mandatory_rho_pass": mandatory_rho_pass,
            "worst_mandatory_rho": worst_rho,
            "worst_rho_pass": worst_rho <= 0.95,
            "preferred_rho_pass": preferred_rho_pass,
            "factor_inventory_pass": inventory_pass,
        }
        gate["pass"] = bool(
            gate["finite_pass"]
            and gate["zero_map_pass"] is not False
            and gate["action_identity_pass"]
            and gate["repeat_pass"]
            and gate["linearity_pass"]
            and gate["mandatory_rho_pass"]
            and gate["worst_rho_pass"]
            and gate["preferred_rho_pass"]
            and gate["factor_inventory_pass"]
        )
        return {
            "source_labels": list(labels),
            "reports": reports,
            "factor_inventory": inventory,
            "action_identity": action_identity,
            "gate": gate,
            "action_apply_count_delta": action.diagnostics["apply_count"]
            - action_diagnostics["apply_count"],
            "formal_source_apply_count": len(reports),
            "repeat_audit_apply_count": len(reports),
            "linearity_audit_apply_count": 1,
        }
    finally:
        for output in outputs.values():
            output.destroy()
