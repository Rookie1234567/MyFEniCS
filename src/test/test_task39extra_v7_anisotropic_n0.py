"""Pure profile and fake-mesh checks for the explicit V7 N0 p4 target."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.input_validation import load_and_resolve
from src.io.native_capacity_profile import (
    V6_NATIVE_PROFILES,
    V6_P3_PROFILES,
    V6_PILOT16_PROFILES,
    V7_ANISO_N0_P4_PROFILE,
    V7_ANISO_N0_P4_PROFILES,
    V7_N0_ACTIVE_MODE_COUNT,
    V7_N0_ACTIVE_MODE_SHA256,
    V7_N0_PARENT_MODE_COUNT,
    V7_N0_PARENT_MODE_SHA256,
    V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY,
    V7_RSS_HARD_LIMIT_BYTES,
    native_profile_facts,
    validate_native_case,
    validate_same_mesh_coefficient_map_profile_binding,
)
from src.runners.physical_intermediate import validate_v7_functional_store_isolation
from src.runners.v7_anisotropic_mesh_evidence import (
    actual_v7_anisotropic_mesh_evidence,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg import (
    V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY as TRANSFER_V7_P64_POLICY,
)

INPUT = (
    Path(__file__).parents[2]
    / "input/task39extra_para_workstation_capacity/"
    "v7_0p7nm_si_p6_hx0p5_hy12p5_hz0p6_q4_n0_full.dat"
)
SI_INDEX = 0.9998851259969171 + 4.325285938225562e-06j


def test_v7_profile_resolves_as_full_n0_p4_and_not_a_pilot():
    specification = load_and_resolve(INPUT)
    config = specification.as_jsonable()
    identity = config["solver"]["preconditioner"]
    facts = native_profile_facts(identity)

    assert identity == V7_ANISO_N0_P4_PROFILE
    assert identity in V7_ANISO_N0_P4_PROFILES & V6_NATIVE_PROFILES
    assert identity not in V6_P3_PROFILES | V6_PILOT16_PROFILES
    assert config["method"]["kind"] == "full3d_iterative"
    assert config["discretization"]["mesh_axis_cell_counts"] == [100, 2, 234]
    assert config["solver"]["coarse_degree"] == 4
    assert config["execution"]["time_limit_mode"] == "none"
    assert V7_RSS_HARD_LIMIT_BYTES == 1_800_000_000_000
    assert config["execution"]["terminate_memory_gib"] == V7_RSS_HARD_LIMIT_BYTES / 2**30
    assert config["execution"]["memory_limit_gb"] == V7_RSS_HARD_LIMIT_BYTES / 2**30
    assert config["execution"]["terminate_memory_gib"] * 2**30 == V7_RSS_HARD_LIMIT_BYTES
    assert config["execution"]["memory_limit_gb"] * 2**30 == V7_RSS_HARD_LIMIT_BYTES
    assert facts["resources"]["absolute_cap_bytes"] == V7_RSS_HARD_LIMIT_BYTES
    assert facts["resources"]["planning_cap_bytes"] == V7_RSS_HARD_LIMIT_BYTES
    assert facts["resources"]["rss_hard_limit_bytes"] == V7_RSS_HARD_LIMIT_BYTES
    assert facts["campaign_authorization"]["resource_policy"]["rss_hard_limit_bytes"] == (
        V7_RSS_HARD_LIMIT_BYTES
    )
    memory_override = facts["campaign_authorization"]["memory_override"]
    assert memory_override["whole_process_tree_rss_cap_bytes"] == V7_RSS_HARD_LIMIT_BYTES
    assert memory_override["parent_and_worker_cap_bytes"] == V7_RSS_HARD_LIMIT_BYTES
    assert config["discretization"]["nedelec_degree"] == 6
    assert config["output"]["export_reference_planes"] is True
    assert config["output"]["sample_count_y"] >= 4
    assert config["output"]["diffraction_order_max_m"] == 142
    assert config["output"]["diffraction_order_max_n"] == 0
    selection = facts["component_options"]["dtn_mode_selection"]
    assert selection["parent_mode_count"] == V7_N0_PARENT_MODE_COUNT == 32060
    assert selection["parent_mode_sha256"] == V7_N0_PARENT_MODE_SHA256
    assert selection["active_mode_count"] == V7_N0_ACTIVE_MODE_COUNT == 572
    assert selection["expected_active_mode_sha256"] == V7_N0_ACTIVE_MODE_SHA256
    assert facts["execution_mode"] == "full_solve"
    assert facts["component_options"]["dtn_surface_assembly_backend_by_degree"] == {
        "p6": "q160_affine_hex_pointwise_weighted_legendre_component_pair_v1",
        "p4": "native_ffcx",
    }
    assert facts["retained_condensed_v20"]["same_mesh_trace_map_policy"] == (
        "basix_full_cell_interpolation_v1"
    )
    policy = V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
    assert policy == TRANSFER_V7_P64_POLICY
    assert facts["component_options"]["same_mesh_coefficient_map_policy"] == policy
    assert facts["coarse_operator"]["same_mesh_coefficient_map_policy"] == policy
    assert facts["backend"]["same_mesh_coefficient_map_policy"] == policy
    assert facts["backend"]["coarse_operator"]["same_mesh_coefficient_map_policy"] == policy
    assert facts["retained_condensed_v20"]["same_mesh_coefficient_map_policy"] == policy
    assert facts["condensed_route"]["same_mesh_coefficient_map_policy"] == policy
    assert validate_same_mesh_coefficient_map_profile_binding(
        identity, 4, facts["component_options"]
    ) == policy
    assert "same_mesh_trace_map_policy" not in facts["component_options"]
    assert facts["functional_store_policy"]["enabled"] is False
    assert facts["functional_store_policy"]["parent_import"] is False
    assert facts["functional_store_policy"]["cross_mesh_fe_reuse"] == "forbidden"


def test_v7_coefficient_policy_requires_the_explicit_profile_degree_and_option():
    options = native_profile_facts(V7_ANISO_N0_P4_PROFILE)["component_options"]
    policy = V7_P64_T_TRANSPOSE_COEFFICIENT_MAP_POLICY
    with pytest.raises(ValueError, match="coarse degree 4"):
        validate_same_mesh_coefficient_map_profile_binding(
            V7_ANISO_N0_P4_PROFILE, 3, options
        )
    missing = dict(options)
    missing.pop("same_mesh_coefficient_map_policy")
    with pytest.raises(ValueError, match="explicitly select"):
        validate_same_mesh_coefficient_map_profile_binding(
            V7_ANISO_N0_P4_PROFILE, 4, missing
        )
    wrong = dict(options, same_mesh_coefficient_map_policy="unknown_policy")
    with pytest.raises(ValueError, match="explicitly select"):
        validate_same_mesh_coefficient_map_profile_binding(
            V7_ANISO_N0_P4_PROFILE, 4, wrong
        )
    with pytest.raises(ValueError, match="restricted to the explicit V7 profile"):
        validate_same_mesh_coefficient_map_profile_binding(
            "dual_condensed_balh_native_5nm_v6",
            4,
            {"same_mesh_coefficient_map_policy": policy},
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("solver", "coarse_degree"), 3),
        (("discretization", "mesh_axis_cell_counts"), [100, 2, 233]),
        (("execution", "terminate_memory_gib"), 1816.079020500183),
        (("execution", "memory_limit_gb"), 1816.079020500183),
        (("output", "export_reference_planes"), False),
        (("output", "sample_count_y"), 3),
        (("output", "diffraction_order_max_m"), 141),
        (("materials", "n_air"), [1.0001, 0.0]),
        (("materials", "mu_r"), [1.0, 0.1]),
    ],
)
def test_v7_profile_rejects_contract_mutations(path, value):
    config = load_and_resolve(INPUT).as_jsonable()
    candidate = deepcopy(config)
    candidate[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        validate_native_case(candidate)


def test_v7_functional_store_environment_is_explicitly_isolated():
    validate_v7_functional_store_isolation(V7_ANISO_N0_P4_PROFILE, {})
    # Other explicit V6 store-capable routes retain their existing behavior.
    validate_v7_functional_store_isolation(
        "dual_condensed_balh_native_0p7nm_n0_p3_pilot16_v6",
        {"TASK39EXTRA_FUNCTIONAL_STORE_CONFIG": "/old/store.json"},
    )
    for key in (
        "TASK39EXTRA_FUNCTIONAL_STORE_CONFIG",
        "TASK39EXTRA_FUNCTIONAL_STORE_PARENT",
    ):
        with pytest.raises(ValueError, match="functional-store"):
            validate_v7_functional_store_isolation(
                V7_ANISO_N0_P4_PROFILE, {key: ""}
            )


def _axis(start, breaks, counts):
    pieces = []
    for left, right, count in zip(breaks[:-1], breaks[1:], counts, strict=True):
        piece = np.linspace(left, right, count + 1, dtype=np.float64)
        pieces.append(piece if not pieces else piece[1:])
    result = np.concatenate(pieces)
    assert result[0] == start
    return result


def _fake_v7_levels():
    nx, ny, nz = 100, 2, 234
    x = _axis(0.0, (0.0, 16.5, 33.5, 50.0), (33, 34, 33))
    y = np.linspace(0.0, 25.0, ny + 1, dtype=np.float64)
    z = _axis(-10.0, (-10.0, 0.0, 120.0, 130.0), (17, 200, 17))
    topology_coordinates = np.asarray(
        [(x_value, y_value, z_value)
         for z_value in z for y_value in y for x_value in x],
        dtype=np.float64,
    )
    geometry_index_by_topology_vertex = np.roll(
        np.arange(len(topology_coordinates), dtype=np.int32), 19
    )
    coordinates = np.empty_like(topology_coordinates)
    coordinates[geometry_index_by_topology_vertex] = topology_coordinates
    i = np.tile(np.arange(nx, dtype=np.int32), ny * nz)
    j = np.tile(np.repeat(np.arange(ny, dtype=np.int32), nx), nz)
    k = np.repeat(np.arange(nz, dtype=np.int32), nx * ny)
    layer = (nx + 1) * (ny + 1)
    base = k * layer + j * (nx + 1) + i
    dofmap = np.column_stack(
        (base, base + 1, base + nx + 1, base + nx + 2,
         base + layer, base + layer + 1, base + layer + nx + 1,
         base + layer + nx + 2)
    ).astype(np.int32)
    dofmap = geometry_index_by_topology_vertex[dofmap]
    x_mid = 0.5 * (x[i] + x[i + 1])
    z_mid = 0.5 * (z[k] + z[k + 1])
    tags = np.full(len(i), 1, dtype=np.int32)
    tags[z_mid < 0.0] = 2
    tags[(x_mid >= 16.5) & (x_mid <= 33.5) & (z_mid >= 0.0) & (z_mid <= 120.0)] = 3
    cell_tags = SimpleNamespace(
        indices=np.arange(len(tags), dtype=np.int32), values=tags
    )
    face_tags = SimpleNamespace(
        indices=np.arange(2 * ny * nz + 2 * nx * nz + 2 * nx * ny, dtype=np.int32),
        values=np.concatenate(
            (
                np.full(ny * nz, 11, dtype=np.int32),
                np.full(ny * nz, 12, dtype=np.int32),
                np.full(nx * nz, 13, dtype=np.int32),
                np.full(nx * nz, 14, dtype=np.int32),
                np.full(nx * ny, 15, dtype=np.int32),
                np.full(nx * ny, 16, dtype=np.int32),
            )
        ),
    )
    def node(ix, iy, iz):
        return iz * (ny + 1) * (nx + 1) + iy * (nx + 1) + ix

    facet_vertices = []
    for iz in range(nz):
        for iy in range(ny):
            facet_vertices.append(
                [node(0, iy, iz), node(0, iy + 1, iz),
                 node(0, iy, iz + 1), node(0, iy + 1, iz + 1)]
            )
    for iz in range(nz):
        for iy in range(ny):
            facet_vertices.append(
                [node(nx, iy, iz), node(nx, iy + 1, iz),
                 node(nx, iy, iz + 1), node(nx, iy + 1, iz + 1)]
            )
    for iz in range(nz):
        for ix in range(nx):
            facet_vertices.append(
                [node(ix, 0, iz), node(ix + 1, 0, iz),
                 node(ix, 0, iz + 1), node(ix + 1, 0, iz + 1)]
            )
    for iz in range(nz):
        for ix in range(nx):
            facet_vertices.append(
                [node(ix, ny, iz), node(ix + 1, ny, iz),
                 node(ix, ny, iz + 1), node(ix + 1, ny, iz + 1)]
            )
    for iy in range(ny):
        for ix in range(nx):
            facet_vertices.append(
                [node(ix, iy, 0), node(ix + 1, iy, 0),
                 node(ix, iy + 1, 0), node(ix + 1, iy + 1, 0)]
            )
    for iy in range(ny):
        for ix in range(nx):
            facet_vertices.append(
                [node(ix, iy, nz), node(ix + 1, iy, nz),
                 node(ix, iy + 1, nz), node(ix + 1, iy + 1, nz)]
            )
    facet_vertices = np.asarray(facet_vertices, dtype=np.int32)

    def entities_to_geometry_fn(_mesh, dimension, entities, permute):
        assert dimension == 2
        assert permute is False
        topology_vertices = facet_vertices[np.asarray(entities, dtype=np.int32)]
        return geometry_index_by_topology_vertex[topology_vertices]

    class _Topology:
        dim = 3
        _facet_vertices = facet_vertices

        @staticmethod
        def create_connectivity(_dimension, _vertex_dimension):
            raise AssertionError("QA must use entities_to_geometry, not topology IDs")

        @staticmethod
        def connectivity(_dimension, _vertex_dimension):
            raise AssertionError("QA must use entities_to_geometry, not topology IDs")

        def index_map(self, _dimension):
            return SimpleNamespace(size_local=nx * ny * nz,
                                   size_global=nx * ny * nz,
                                   num_ghosts=0)

        @staticmethod
        def cell_name():
            return "hexahedron"

    class _IndexMap:
        size_global = 30_340_800
        size_local = 30_340_800
        num_ghosts = 0

    class _P4IndexMap:
        size_global = 8_992_000
        size_local = 8_992_000
        num_ghosts = 0

    def fake_space(index_map):
        return SimpleNamespace(
            dofmap=SimpleNamespace(index_map=index_map, index_map_bs=1)
        )

    mesh = SimpleNamespace(
        topology=_Topology(),
        comm=SimpleNamespace(size=1),
        geometry=SimpleNamespace(x=coordinates, dofmap=dofmap),
    )
    levels = {
        "mesh": mesh,
        "mesh_data": SimpleNamespace(cell_tags=cell_tags, facet_tags=face_tags),
        "spaces": {6: fake_space(_IndexMap()), 4: fake_space(_P4IndexMap())},
        "entities_to_geometry_fn": entities_to_geometry_fn,
        "facet_vertices": facet_vertices,
        "geometry_index_by_topology_vertex": geometry_index_by_topology_vertex,
    }
    kx = 0.031 + 0.0j
    ky = 0.0 + 0.0j
    cfg = SimpleNamespace(
        mesh_axis_cell_counts_requested=(nx, ny, nz),
        geometry_kind="rectangular_block_grating",
        cell_notch=None,
        use_pml=False,
        use_floquet_xy=True,
        nedelec_degree=6,
        stage4_boundary_model="dtn_port",
        scattering_background="layered",
        stage4_dtn_order_policy="auto_propagating",
        stage4_dtn_assembly="auxiliary",
        x_min=0.0,
        x_max=50.0,
        y_min=0.0,
        y_max=25.0,
        domain_z_min=-10.0,
        domain_z_max=130.0,
        interface_z=0.0,
        grating_width_x=17.0,
        grating_width_y=25.0,
        grating_height=120.0,
        grating_x_min=16.5,
        grating_x_max=33.5,
        grating_y_min=0.0,
        grating_y_max=25.0,
        grating_z_min=0.0,
        grating_z_max=120.0,
        n_substrate=SI_INDEX,
        n_grating=SI_INDEX,
        n_air=1.0 + 0.0j,
        mu_r=1.0 + 0.0j,
        eps_air=1.0 + 0.0j,
        eps_substrate=SI_INDEX**2,
        eps_grating=SI_INDEX**2,
        tags=SimpleNamespace(air=1, substrate=2, grating=3,
                             x_min=11, x_max=12, y_min=13, y_max=14,
                             z_min=15, z_max=16),
        kx=kx,
        ky=ky,
        floquet_phase_x=np.exp(1j * kx * 50.0),
        floquet_phase_y=1.0 + 0.0j,
        full3d_reference_export=True,
        full3d_reference_sample_count_y=20,
        full3d_reference_plane_z=(10.0, 30.0, 60.0, 90.0, 110.0),
    )
    return levels, cfg


def test_v7_mesh_evidence_checks_all_cells_periodicity_tags_and_rows():
    levels, cfg = _fake_v7_levels()
    evidence = actual_v7_anisotropic_mesh_evidence(
        levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
    )

    assert evidence["schema"] == "task39extra.v7-anisotropic-mesh-evidence.v1"
    assert evidence["status"] == "PASS"
    assert evidence["actual_global_cell_count"] == 46_800
    geometry_ids = levels["entities_to_geometry_fn"](
        levels["mesh"], 2, np.asarray([0], dtype=np.int32), False
    )[0]
    topology_ids = levels["facet_vertices"][0]
    assert not np.array_equal(geometry_ids, topology_ids)
    assert np.array_equal(
        geometry_ids,
        levels["geometry_index_by_topology_vertex"][topology_ids],
    )
    assert evidence["actual_axis_cell_counts"] == [100, 2, 234]
    assert evidence["axis_segments"]["x"]["segment_counts"] == [33, 34, 33]
    assert evidence["axis_segments"]["y"]["segment_counts"] == [2]
    assert evidence["axis_segments"]["z"]["segment_counts"] == [17, 200, 17]
    assert evidence["jacobian"]["all_positive"] is True
    assert evidence["jacobian"]["sampled_or_all_cells"] == "all_46800_owned_cells"
    assert evidence["cell_tag_y_invariance"]["tags_constant_for_each_xz_column"] is True
    assert evidence["periodic_faces"]["x"]["paired_transverse_coordinates_exact"] is True
    assert evidence["periodic_faces"]["y"]["paired_transverse_coordinates_exact"] is True
    assert evidence["actual_unconstrained_space_rows"]["p6"][
        "global_unconstrained_space_rows"
    ] == 30_340_800
    assert evidence["actual_unconstrained_space_rows"]["p4"][
        "global_unconstrained_space_rows"
    ] == 8_992_000


def test_v7_mesh_evidence_rejects_wrong_cell_count_and_orientation():
    levels, cfg = _fake_v7_levels()
    original_index_map = levels["mesh"].topology.index_map
    levels["mesh"].topology.index_map = lambda dimension: SimpleNamespace(
        size_local=46_800, size_global=46_799, num_ghosts=0
    ) if dimension == 3 else original_index_map(dimension)
    with pytest.raises(ValueError, match="46800-cell"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )

    levels, cfg = _fake_v7_levels()
    levels["mesh"].geometry.dofmap[0, [1, 2]] = levels["mesh"].geometry.dofmap[0, [2, 1]]
    with pytest.raises(ValueError, match="vertex order|Jacobian"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )


def test_v7_boundary_qa_rejects_topology_ids_used_as_geometry_rows():
    levels, cfg = _fake_v7_levels()

    def topology_ids_instead_of_geometry(_mesh, _dimension, entities, _permute):
        indices = np.asarray(entities, dtype=np.int32)
        return levels["facet_vertices"][indices]

    with pytest.raises(ValueError, match="tag is not on its coordinate plane"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=topology_ids_instead_of_geometry
        )


def test_v7_mesh_evidence_rejects_material_or_periodic_geometry_drift():
    levels, cfg = _fake_v7_levels()
    levels["mesh_data"].cell_tags.values[17 * 100 + 33] = cfg.tags.air
    with pytest.raises(ValueError, match="tags|material"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )

    levels, cfg = _fake_v7_levels()
    # x-max, y-min, z-min node: move the transverse coordinate off its paired plane.
    levels["mesh"].geometry.x[100, 1] += 1.0e-6
    with pytest.raises(ValueError, match="axis|periodic"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )

    levels, cfg = _fake_v7_levels()
    cfg.eps_air = 1.0001 + 0.0j
    with pytest.raises(ValueError, match="permittivities"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )


def test_v7_mesh_evidence_rejects_missing_actual_degree_rows():
    levels, cfg = _fake_v7_levels()
    levels["spaces"].pop(4)
    with pytest.raises(ValueError, match="p4 space"):
        actual_v7_anisotropic_mesh_evidence(
            levels, cfg, entities_to_geometry_fn=levels["entities_to_geometry_fn"]
        )

    evidence = actual_v7_anisotropic_mesh_evidence(
        levels,
        cfg,
        entities_to_geometry_fn=levels["entities_to_geometry_fn"],
        required_space_degrees=(6,),
    )
    assert evidence["status"] == "PASS"
    assert set(evidence["actual_unconstrained_space_rows"]) == {"p6"}
    assert evidence["space_evidence_scope"] == {
        "required_space_degrees": [6],
        "not_built_space_degrees": [4],
    }

    with pytest.raises(ValueError, match="supports only"):
        actual_v7_anisotropic_mesh_evidence(
            levels,
            cfg,
            entities_to_geometry_fn=levels["entities_to_geometry_fn"],
            required_space_degrees=(4,),
        )
