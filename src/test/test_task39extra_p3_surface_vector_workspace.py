"""Pure fake checks for the opt-in shared surface-vector lifetime contract."""

from types import SimpleNamespace

import numpy as np
import pytest

import src.solvers.dtn_port_3d as dtn_port
import src.solvers.fullspace_dtn_action as fullspace_dtn
import src.solvers.fullspace_surface_legendre as surface_legendre


class _IndexMap:
    size_local = 8
    size_global = 8
    num_ghosts = 0
    local_range = (0, 8)

    @staticmethod
    def local_to_global(indices):
        return np.asarray(indices, dtype=np.int64)


class _DofMap:
    index_map_bs = 1

    def __init__(self, index_map):
        self.index_map = index_map

    @staticmethod
    def cell_dofs(cell):
        return (np.array([0, 1, 2, 3]) if cell == 0 else np.array([1, 2, 4, 5]))


class _Mesh:
    class _Comm:
        size = 1

    class _Topology:
        dim = 3

        class _CellIndexMap:
            size_local = 2
            num_ghosts = 0

        class _Connectivity:
            @staticmethod
            def links(facet):
                return np.array([0 if facet == 10 else 1], dtype=np.int32)

        @staticmethod
        def index_map(_dimension):
            return _Mesh._Topology._CellIndexMap()

        @staticmethod
        def create_connectivity(_from_dimension, _to_dimension):
            return None

        @staticmethod
        def connectivity(_from_dimension, _to_dimension):
            return _Mesh._Topology._Connectivity()

    comm = _Comm()
    topology = _Topology()


class _Mpc:
    def __init__(self, mesh):
        self._mesh = mesh
        self._index_map = _IndexMap()
        self._cpp_object = object()

    @property
    def function_space(self):
        # Finalization can hand out a fresh Python wrapper for the same space.
        return SimpleNamespace(mesh=self._mesh, dofmap=_DofMap(self._index_map))

    class _CellToSlaves:
        @staticmethod
        def links(cell):
            return np.array([3], dtype=np.int32) if cell == 0 else np.empty(0, dtype=np.int32)

    class _Masters:
        @staticmethod
        def links(slave):
            return np.array([6], dtype=np.int32) if slave == 3 else np.empty(0, dtype=np.int32)

    cell_to_slaves = _CellToSlaves()
    masters = _Masters()


class _LocalForm:
    def __init__(self, vector):
        self.array_w = vector.array

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def set(self, value):
        self.array_w.fill(value)


class _Vec:
    def __init__(self, index_map):
        self.index_map = index_map
        self.array = np.empty(index_map.size_local + index_map.num_ghosts, dtype=np.complex128)
        self.ghost_updates = 0
        self.destroyed = False

    def localForm(self):
        return _LocalForm(self)

    def getOwnershipRange(self):
        return self.index_map.local_range

    def ghostUpdate(self, **_kwargs):
        self.ghost_updates += 1

    def destroy(self):
        self.destroyed = True


def _surface_fixture(monkeypatch):
    mesh = _Mesh()
    mpc = _Mpc(mesh)
    function_space = SimpleNamespace(mesh=mesh, dofmap=_DofMap(mpc._index_map))

    class _FacetTags:
        @staticmethod
        def find(tag):
            return np.array([10 if tag == 16 else 11], dtype=np.int32)

    mesh_data = SimpleNamespace(mesh=mesh, facet_tags=_FacetTags())
    assemblers = {
        (side, component): SimpleNamespace(
            function_space=function_space,
            mesh_data=mesh_data,
            tag=16 if side == "top" else 15,
            form=SimpleNamespace(_cpp_object=object()),
        )
        for side in ("top", "bottom")
        for component in (0, 1)
    }
    vectors = []

    def create_vector(index_maps):
        index_map, _block_size = index_maps[0]
        vector = _Vec(index_map)
        vectors.append(vector)
        return vector

    monkeypatch.setattr(dtn_port, "create_vector", create_vector)
    return mesh, function_space, mpc, mesh_data, assemblers, vectors


def test_workspace_uses_form_space_and_mpc_index_map_and_binds_forms(monkeypatch):
    mesh, form_space, mpc, mesh_data, assemblers, vectors = _surface_fixture(monkeypatch)
    workspace = dtn_port._SurfaceMpcVectorWorkspace(
        form_space, mesh_data, mpc, assemblers
    )
    vector = vectors[0]
    assert vector.index_map is mpc._index_map
    assert workspace.local_support.tolist() == [0, 1, 2, 3, 4, 5, 6]
    assert workspace.owned_support.tolist() == [0, 1, 2, 3, 4, 5, 6]
    assert mesh is form_space.mesh

    vector.array[:7] = 9.0
    vector.array[7] = 7.0
    form = assemblers[("top", 0)].form
    calls = []

    def cpp_assemble(values, cpp_form, cpp_mpc):
        calls.append((cpp_form, cpp_mpc))
        assert np.all(values[:7] == 0.0)
        assert values[7] == 7.0

    monkeypatch.setattr(
        dtn_port,
        "dolfinx_mpc",
        SimpleNamespace(cpp=SimpleNamespace(mpc=SimpleNamespace(assemble_vector=cpp_assemble))),
    )
    with pytest.raises(ValueError, match="different MPC"):
        workspace.assemble(form, _Mpc(mesh))
    with pytest.raises(ValueError, match="unregistered form"):
        workspace.assemble(SimpleNamespace(_cpp_object=object()), mpc)

    workspace.assemble(form, mpc)
    assert calls == [(form._cpp_object, mpc._cpp_object)]
    assert vector.ghost_updates == 2
    assert vector.array[7] == 7.0
    workspace.destroy()
    assert vector.destroyed


def test_workspace_is_destroyed_if_ready_notification_raises(monkeypatch):
    mesh, form_space, mpc, mesh_data, assemblers, _vectors = _surface_fixture(monkeypatch)
    captured = []

    class _TrackingWorkspace:
        timing_totals = None

        @property
        def facts(self):
            return {"scratch_vector_count": 1}

        def __init__(self, actual_form_space, actual_mesh_data, actual_mpc, actual_assemblers,
                     *, collect_timings=False):
            assert actual_form_space is form_space
            assert actual_mesh_data is mesh_data
            assert actual_mpc is mpc
            assert actual_assemblers is assemblers
            assert not collect_timings
            self.destroyed = False
            captured.append(self)

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(dtn_port, "_SurfaceMpcVectorWorkspace", _TrackingWorkspace)
    monkeypatch.setattr(
        fullspace_dtn,
        "build_ordered_mode_manifest",
        lambda _modes, _cfg: ((), b"", "0" * 64),
    )

    class _CallbackError(RuntimeError):
        pass

    def notify(name, _facts):
        if name == "surface_carrier_workspace_ready":
            raise _CallbackError(name)

    with pytest.raises(_CallbackError):
        fullspace_dtn.build_fullspace_dtn_carrier_from_surface(
            (), assemblers, mpc, SimpleNamespace(),
            reuse_surface_vector=True, stage_callback=notify,
        )
    assert len(captured) == 1
    assert captured[0].destroyed
    assert mesh is form_space.mesh


def test_geometry_cache_and_shared_vec_are_released_if_callback_raises(monkeypatch):
    from src.solvers.fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    _mesh, _form_space, mpc, mesh_data, assemblers, _vectors = _surface_fixture(monkeypatch)
    lifecycle = []

    class _GeometryContext:
        backend = SURFACE_COMPONENT_PAIR_BACKEND
        _geometry_cache_enabled = True

        def begin_geometry_cache(self):
            lifecycle.append("begin")

        def end_geometry_cache(self):
            lifecycle.append("end")

    context = _GeometryContext()
    for assembler in assemblers.values():
        assembler.context = context
        assembler.surface_backend = SURFACE_COMPONENT_PAIR_BACKEND

    captured = []

    class _TrackingWorkspace:
        timing_totals = None

        @property
        def facts(self):
            return {"scratch_vector_count": 1}

        def __init__(self, actual_form_space, actual_mesh_data, actual_mpc, actual_assemblers,
                     *, collect_timings=False):
            assert actual_mesh_data is mesh_data
            assert actual_mpc is mpc
            assert actual_assemblers is assemblers
            assert not collect_timings
            self.destroyed = False
            captured.append(self)

        def destroy(self):
            self.destroyed = True

    monkeypatch.setattr(dtn_port, "_SurfaceMpcVectorWorkspace", _TrackingWorkspace)
    monkeypatch.setattr(
        fullspace_dtn,
        "build_ordered_mode_manifest",
        lambda _modes, _cfg: ((), b"", "0" * 64),
    )

    class _CallbackError(RuntimeError):
        pass

    def notify(name, _facts):
        if name == "surface_carrier_workspace_ready":
            raise _CallbackError(name)

    with pytest.raises(_CallbackError):
        fullspace_dtn.build_fullspace_dtn_carrier_from_surface(
            (),
            assemblers,
            mpc,
            SimpleNamespace(),
            reuse_surface_vector=True,
            reuse_surface_geometry_cache=True,
            stage_callback=notify,
            degree=6,
        )
    assert lifecycle == ["begin", "end"]
    assert len(captured) == 1 and captured[0].destroyed


def _pair_fixture(monkeypatch, *, fail_scatter_component=None):
    from src.solvers.fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    records = []
    for position, dofs in enumerate(([0, 1, 2, 3], [1, 2, 4, 5])):
        records.append(
            SimpleNamespace(
                cell=0,
                cell_plan=SimpleNamespace(
                    cell_dofs=np.asarray(dofs, dtype=np.int32),
                    slave_positions=np.empty(0, dtype=np.int32),
                    master_rows=(),
                    coefficient_rows=(),
                ),
                position=position,
            )
        )
    mpc = object()
    mesh_data = object()
    function_space = SimpleNamespace(element=object())

    class _Context:
        backend = SURFACE_COMPONENT_PAIR_BACKEND
        degree = 6
        _cell_permutations = np.asarray([27], dtype=np.uint32)
        quadrilateral_weights = np.ones(1, dtype=np.float64)

        def __init__(self):
            self.mpc = mpc
            self._component_pair_stats = {
                "backend": self.backend,
                "degree": self.degree,
                "pair_call_count": 0,
                "paired_facet_count": 0,
                "max_staging_bytes": 0,
                "max_staging_facets": 0,
                "staging_release_count": 0,
                "staging_buffer_count_max": 0,
                "max_explicit_numpy_payload_upper_bytes": 0,
                "staging_max_bytes_limit": 64 * 1024 * 1024,
                "staging_max_facet_limit": 4096,
            }
            self.pointwise_calls = 0

        def records(self, side):
            assert side == "top"
            return tuple(records)

        def trace_table(self, side, component):
            assert (side, component) in {("top", 0), ("top", 1)}
            return object()

        def pointwise_moments_pair(self, mode, record):
            assert mode.side == "top"
            self.pointwise_calls += 1
            if fail_scatter_component == 0 and self.pointwise_calls == 1:
                raise RuntimeError("fake component-zero callback failure")
            position = record.position
            moments = np.zeros((2, 3, 1, 1), dtype=np.complex128)
            moments[0, 0, 0, 0] = 10 + position
            moments[1, 0, 0, 0] = 20 + position
            return moments

    context = _Context()

    def make_assembler(component):
        assembler = object.__new__(dtn_port._SurfaceLegendreMomentAssembler)
        assembler.context = context
        assembler.function_space = function_space
        assembler.mesh_data = mesh_data
        assembler.comm = None
        assembler.side = "top"
        assembler.tag = 16
        assembler.component = component
        assembler.surface_backend = SURFACE_COMPONENT_PAIR_BACKEND
        assembler.call_count = 0
        assembler.facet_count = 0
        return assembler

    primary = make_assembler(0)
    companion = make_assembler(1)

    class _Workspace:
        def __init__(self):
            self._mpc = mpc
            self._function_space = function_space
            self._mesh_data = mesh_data
            self._allowed_assembler_ids = {id(primary), id(companion)}
            self.owned_support = np.arange(6, dtype=np.int32)
            self.local_support = self.owned_support
            self.timing_totals = None
            self.vector = _Vec(SimpleNamespace(size_local=6, num_ghosts=0, local_range=(0, 6)))
            self.calls = []

        def assemble_custom(self, assembler, actual_mpc, callback):
            assert actual_mpc is mpc
            assert id(assembler) in self._allowed_assembler_ids
            self.calls.append(assembler.component)
            self.vector.array.fill(0.0)
            if fail_scatter_component == assembler.component and assembler.component == 1:
                callback(self.vector)
                raise RuntimeError("fake component-one callback failure")
            callback(self.vector)
            return self.vector

    workspace = _Workspace()
    vector_results = []
    scatter_order = []
    transform_calls = []

    def fake_face(_trace, moments):
        scalar = complex(moments[0, 0, 0])
        return np.full(4, scalar, dtype=np.complex128)

    def fake_transform(_element, values, cell_info, *, check_finite):
        assert int(cell_info) == 27
        assert not check_finite
        transform_calls.append(values.copy())
        return values.copy() + 1.0

    def fake_scatter(local, storage, cell_dofs, *_rows):
        scatter_order.append((int(np.real(local[0])), tuple(cell_dofs.tolist())))
        if fail_scatter_component == "scatter_companion" and np.real(local[0]) >= 21:
            raise RuntimeError("fake component-one scatter failure")
        np.add.at(storage, cell_dofs, local)

    monkeypatch.setattr(
        surface_legendre, "assemble_face_from_weighted_moments", fake_face
    )
    monkeypatch.setattr(
        surface_legendre, "apply_standard_dof_transform", fake_transform
    )
    monkeypatch.setattr(
        surface_legendre,
        "add_prevalidated_complex_mpc_cell_contribution",
        fake_scatter,
    )

    def extract(vector, *, support=None, timing_totals=None):
        assert timing_totals is None
        rows = np.asarray(support, dtype=np.int64)
        values = vector.array[rows]
        selected = np.flatnonzero(values != 0.0)
        result = (rows[selected].copy(), values[selected].copy())
        vector_results.append(result)
        return result

    monkeypatch.setattr(dtn_port, "_vec_nonzero_owned_entries", extract)
    mode = SimpleNamespace(
        side="top",
        m=-142,
        n=35,
        alpha=2.5 + 0.125j,
        gamma=-0.75 + 0.25j,
        k_vector=(0.0, 0.0, 1.5 - 0.0625j),
    )
    return {
        "records": records,
        "context": context,
        "mpc": mpc,
        "mode": mode,
        "primary": primary,
        "companion": companion,
        "workspace": workspace,
        "vector_results": vector_results,
        "scatter_order": scatter_order,
        "transform_calls": transform_calls,
    }


def test_component_pair_reuses_one_vec_and_stages_by_facet_position(monkeypatch):
    fixture = _pair_fixture(monkeypatch)
    context = fixture["context"]
    workspace = fixture["workspace"]
    primary, companion = fixture["primary"], fixture["companion"]

    original_staging = dtn_port._SurfaceComponentPairStaging
    captured_staging = []

    def capture_staging(*args, **kwargs):
        staging = original_staging(*args, **kwargs)
        captured_staging.append(staging)
        return staging

    monkeypatch.setattr(dtn_port, "_SurfaceComponentPairStaging", capture_staging)
    (rows0, values0), (rows1, values1) = primary.assemble_pair_entries(
        companion,
        fixture["mode"],
        fixture["mpc"],
        workspace=workspace,
    )

    assert workspace.calls == [0, 1]
    assert context.pointwise_calls == 2
    assert len(fixture["transform_calls"]) == 4
    assert fixture["scatter_order"] == [
        (11, (0, 1, 2, 3)),
        (12, (1, 2, 4, 5)),
        (21, (0, 1, 2, 3)),
        (22, (1, 2, 4, 5)),
    ]
    np.testing.assert_array_equal(rows0, np.arange(6))
    np.testing.assert_array_equal(values0, [11, 23, 23, 11, 12, 12])
    np.testing.assert_array_equal(rows1, np.arange(6))
    np.testing.assert_array_equal(values1, [21, 43, 43, 21, 22, 22])
    assert not np.shares_memory(values0, workspace.vector.array)
    assert not np.shares_memory(values1, workspace.vector.array)
    assert context._component_pair_stats["max_staging_bytes"] == 2 * 4 * 16
    assert context._component_pair_stats["staging_buffer_count_max"] == 1
    assert context._component_pair_stats["staging_release_count"] == 1
    assert context._component_pair_stats["last_payload_bounds"][
        "staging_complex_values_bytes"
    ] == 2 * 4 * 16
    assert captured_staging[0].values is None
    assert captured_staging[0].workspace is None
    assert primary.call_count == companion.call_count == 1
    assert primary.facet_count == companion.facet_count == 2


def test_component_pair_rejects_wrong_phase_and_record_order_before_scatter(monkeypatch):
    from src.solvers.fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    fixture = _pair_fixture(monkeypatch)
    primary, companion = fixture["primary"], fixture["companion"]
    context, workspace = fixture["context"], fixture["workspace"]
    records = tuple(fixture["records"])
    staging = dtn_port._SurfaceComponentPairStaging(
        records,
        primary=primary,
        companion=companion,
        mode=fixture["mode"],
        mpc=fixture["mpc"],
        workspace=workspace,
    )
    wrong_mode = SimpleNamespace(**vars(fixture["mode"]))
    wrong_mode.gamma += 0.5
    with pytest.raises(ValueError, match="identity, phase or record order"):
        staging.assert_binding(
            primary=primary,
            companion=companion,
            mode=wrong_mode,
            mpc=fixture["mpc"],
            workspace=workspace,
            records=records,
        )
    with pytest.raises(ValueError, match="identity, phase or record order"):
        staging.assert_binding(
            primary=primary,
            companion=companion,
            mode=fixture["mode"],
            mpc=fixture["mpc"],
            workspace=workspace,
            records=tuple(reversed(records)),
        )
    staging.release()
    assert context.backend == SURFACE_COMPONENT_PAIR_BACKEND


def test_component_pair_binding_rejects_wrong_side_context_mpc_and_component(monkeypatch):
    fixture = _pair_fixture(monkeypatch)
    primary, companion = fixture["primary"], fixture["companion"]
    workspace = fixture["workspace"]
    records = tuple(fixture["records"])
    staging = dtn_port._SurfaceComponentPairStaging(
        records,
        primary=primary,
        companion=companion,
        mode=fixture["mode"],
        mpc=fixture["mpc"],
        workspace=workspace,
    )

    wrong_side_primary = SimpleNamespace(**vars(primary))
    wrong_side_primary.side = "bottom"
    wrong_context_companion = SimpleNamespace(**vars(companion))
    wrong_context_companion.context = SimpleNamespace(
        backend=primary.context.backend,
        degree=primary.context.degree,
        mpc=fixture["mpc"],
    )
    wrong_component_companion = SimpleNamespace(**vars(companion))
    wrong_component_companion.component = 0

    for bad_primary, bad_companion, bad_mpc in (
        (wrong_side_primary, companion, fixture["mpc"]),
        (primary, wrong_context_companion, fixture["mpc"]),
        (primary, companion, object()),
        (primary, wrong_component_companion, fixture["mpc"]),
    ):
        with pytest.raises(ValueError, match="identity, phase or record order"):
            staging.assert_binding(
                primary=bad_primary,
                companion=bad_companion,
                mode=fixture["mode"],
                mpc=bad_mpc,
                workspace=workspace,
                records=records,
            )
    staging.release()


def test_paired_backend_rejects_unpaired_entry_point():
    from src.solvers.fullspace_surface_legendre import SURFACE_COMPONENT_PAIR_BACKEND

    assembler = object.__new__(dtn_port._SurfaceLegendreMomentAssembler)
    assembler.surface_backend = SURFACE_COMPONENT_PAIR_BACKEND
    with pytest.raises(RuntimeError, match="cannot silently use the unpaired assembler"):
        assembler.assemble_entries(None, None)


@pytest.mark.parametrize("failure_point", ["component_zero", "scatter_companion"])
def test_component_pair_releases_staging_after_callback_errors(monkeypatch, failure_point):
    fixture = _pair_fixture(
        monkeypatch,
        fail_scatter_component=(
            0 if failure_point == "component_zero" else "scatter_companion"
        ),
    )
    captured = []
    original_staging = dtn_port._SurfaceComponentPairStaging

    def capture_staging(*args, **kwargs):
        staging = original_staging(*args, **kwargs)
        captured.append(staging)
        return staging

    monkeypatch.setattr(dtn_port, "_SurfaceComponentPairStaging", capture_staging)
    with pytest.raises(RuntimeError):
        fixture["primary"].assemble_pair_entries(
            fixture["companion"],
            fixture["mode"],
            fixture["mpc"],
            workspace=fixture["workspace"],
        )
    assert len(captured) == 1
    assert captured[0].values is None
    assert captured[0].workspace is None
    assert fixture["context"]._component_pair_stats["staging_release_count"] == 1


def test_component_pair_staging_checks_actual_facet_bytes_before_allocation(monkeypatch):
    fixture = _pair_fixture(monkeypatch)
    primary, companion = fixture["primary"], fixture["companion"]
    workspace, mode, mpc = fixture["workspace"], fixture["mode"], fixture["mpc"]
    huge = SimpleNamespace(
        cell=0,
        cell_plan=SimpleNamespace(cell_dofs=np.zeros(1025, dtype=np.int32)),
    )
    oversized = (huge,) * 4096
    original_empty = dtn_port.np.empty

    def reject_allocation(*args, **kwargs):
        raise AssertionError("staging allocation occurred before its byte guard")

    monkeypatch.setattr(dtn_port.np, "empty", reject_allocation)
    with pytest.raises(ValueError, match="staging bytes exceed"):
        dtn_port._SurfaceComponentPairStaging(
            oversized,
            primary=primary,
            companion=companion,
            mode=mode,
            mpc=mpc,
            workspace=workspace,
        )
    monkeypatch.setattr(dtn_port.np, "empty", original_empty)
