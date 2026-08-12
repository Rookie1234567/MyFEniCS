"""Focused T2 loader, validation, derived-resolution, and hash contracts."""

import hashlib
import json
from dataclasses import FrozenInstanceError
from math import isclose, pi
from pathlib import Path

import pytest

from src.io import (
    InputError,
    LoadedInput,
    load_and_resolve,
    load_dat_input,
    resolved_config_sha256,
    write_resolved_config,
)


TEMPLATES = sorted(Path("input/templates").glob("*.dat"))


def test_load_dat_input_preserves_one_read_payload_and_freezes_document(tmp_path):
    path = tmp_path / "case.dat"
    raw = b'schema_version = 1\n[geometry]\nkind = "airbox"\n'
    path.write_bytes(raw)

    loaded = load_dat_input(path)

    assert isinstance(loaded, LoadedInput)
    assert loaded.source_path == path.resolve()
    assert loaded.raw_input_bytes == raw
    assert loaded.input_sha256 == hashlib.sha256(raw).hexdigest()
    assert loaded.document["geometry"]["kind"] == "airbox"
    with pytest.raises(TypeError):
        loaded.document["new"] = "value"
    with pytest.raises(FrozenInstanceError):
        loaded.raw_input_bytes = b"changed"


def test_load_dat_input_rejects_wrong_suffix_and_duplicate_keys(tmp_path):
    wrong_suffix = tmp_path / "case.toml"
    wrong_suffix.write_text("schema_version = 1\n", encoding="utf-8")
    with pytest.raises(InputError, match=".dat"):
        load_dat_input(wrong_suffix)

    duplicate = tmp_path / "duplicate.dat"
    duplicate.write_text("schema_version = 1\nschema_version = 1\n", encoding="utf-8")
    with pytest.raises(InputError, match="invalid TOML.*line"):
        load_dat_input(duplicate)


@pytest.mark.parametrize("template", TEMPLATES)
def test_all_templates_resolve_to_one_immutable_nine_section_spec(template):
    spec = load_and_resolve(template)

    assert set(spec.identity) == {
        "schema_version",
        "model_id",
        "run_id",
        "comparison_group",
        "dimension",
    }
    sections = {
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
        "solver",
        "execution",
        "output",
    }
    assert all(hasattr(spec, section) for section in sections)
    assert spec.derived
    with pytest.raises(TypeError):
        spec.geometry["period_x_nm"] = 1.0
    with pytest.raises(FrozenInstanceError):
        spec.method = {}


def test_3d_defaults_resolve_without_explicit_optional_enums(tmp_path):
    source = Path("input/templates/full3d_direct_example.dat").read_text(
        encoding="utf-8"
    )
    source = source.replace(
        'geometry_kind = "rectangular_block_grating"',
        'geometry_kind = "airbox"',
        1,
    )
    source = source.replace(
        "grazing_angle_deg = 1.0", "tilt_from_downward_z_deg = 10.0", 1
    )
    source = source.replace(
        'vertical_boundary = "dtn_port"', 'vertical_boundary = "strong_dirichlet"', 1
    )
    for line in (
        "grating_width_x_nm = 17.0\n",
        "grating_width_y_nm = 25.0\n",
        "grating_height_nm = 120.0\n",
        'dtn_order_policy = "auto_propagating"\n',
        'dtn_assembly = "auxiliary"\n',
        'mesh_spacing_mode = "boundary_fitted"\n',
        'floquet_constraint_mode = "auto"\n',
        'assembly_backend = "assembly_time_static_condensed"\n',
        "use_floquet_x = true\n",
        "use_floquet_y = true\n",
    ):
        source = source.replace(line, "", 1)
    path = tmp_path / "airbox_defaults.dat"
    path.write_text(source, encoding="utf-8")

    spec = load_and_resolve(path)

    assert spec.discretization["mesh_spacing_mode"] == "auto"
    assert spec.discretization["assembly_backend"] == "standard_full"
    assert spec.boundary["use_floquet_x"] is False
    assert spec.output["sample_count_x"] == 40
    assert spec.output["sample_count_y"] == 20
    assert (
        spec.derived["stage4_assembly_backend_audit"]["resolution"]["actual"]
        == "standard_full"
    )


def test_hybrid_pairs_bounds_and_solver_identity_fail_closed(tmp_path):
    invalid_pair = _write_variant(
        tmp_path,
        "invalid_pair.dat",
        "input/templates/hybrid_iterative_example.dat",
        [
            (
                'traction_model = "full3d_one_cell_exact_schur"',
                'traction_model = "continuous_qep_beta"',
            )
        ],
    )
    with pytest.raises(InputError, match="propagation/traction pair"):
        load_and_resolve(invalid_pair)

    invalid_backend = _write_variant(
        tmp_path,
        "invalid_backend.dat",
        "input/templates/hybrid_iterative_example.dat",
        [
            (
                'assembly_backend = "assembly_time_static_condensed"',
                'assembly_backend = "standard_full"',
            )
        ],
    )
    with pytest.raises(InputError, match="requires assembly_time_static_condensed"):
        load_and_resolve(invalid_backend)

    invalid_interfaces = _write_variant(
        tmp_path,
        "invalid_interfaces.dat",
        "input/templates/hybrid_iterative_example.dat",
        [("bottom_interface_nm = 10.0", "bottom_interface_nm = -1.0")],
    )
    with pytest.raises(InputError, match="inside the uniform grating slab"):
        load_and_resolve(invalid_interfaces)


def test_2d_port_capabilities_fail_closed(tmp_path):
    port = Path("input/templates/ordinary_2d_example.dat").read_text(encoding="utf-8")
    port = port.replace('kind = "2d_scattered"', 'kind = "2d_port"', 1)
    port = port.replace('vertical_boundary = "pml"', 'vertical_boundary = "dtn"', 1)
    port = port.replace("use_pml = true", "use_pml = false", 1)
    for line in (
        "pml_top_thickness_nm = 25.0\n",
        "pml_bottom_thickness_nm = 25.0\n",
        "pml_alpha = 5.0\n",
    ):
        port = port.replace(line, "", 1)
    port = port.replace(
        'constraint_backend = "mpc_auto"', 'constraint_backend = "manual"', 1
    )
    port = port.replace(
        'vertical_boundary = "dtn"',
        'vertical_boundary = "dtn"\ndtn_order_policy = "zero_order"\ndtn_assembly = "explicit"',
        1,
    )
    port = port.replace("mpi_size = 8", "mpi_size = 1", 1)
    valid = tmp_path / "valid_port.dat"
    valid.write_text(port, encoding="utf-8")
    assert load_and_resolve(valid).method["kind"] == "2d_port"

    auto = tmp_path / "auto_port.dat"
    auto.write_text(
        port.replace(
            'constraint_backend = "manual"', 'constraint_backend = "mpc_auto"', 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match="does not support mpc_auto"):
        load_and_resolve(auto)


def test_stage_mapping_and_non_grating_zero_hash_normalization(tmp_path):
    source = Path("input/templates/full3d_direct_example.dat").read_text(
        encoding="utf-8"
    )
    airbox = source.replace(
        'geometry_kind = "rectangular_block_grating"',
        'geometry_kind = "airbox"',
        1,
    )
    airbox = airbox.replace(
        "grazing_angle_deg = 1.0", "tilt_from_downward_z_deg = 10.0", 1
    )
    airbox = airbox.replace(
        'vertical_boundary = "dtn_port"', 'vertical_boundary = "strong_dirichlet"', 1
    )
    for line in (
        "grating_width_x_nm = 17.0\n",
        "grating_width_y_nm = 25.0\n",
        "grating_height_nm = 120.0\n",
        'dtn_order_policy = "auto_propagating"\n',
        'dtn_assembly = "auxiliary"\n',
        'assembly_backend = "assembly_time_static_condensed"\n',
        'floquet_constraint_mode = "auto"\n',
        "use_floquet_x = true\n",
        "use_floquet_y = true\n",
    ):
        airbox = airbox.replace(line, "", 1)
    airbox_path = tmp_path / "airbox.dat"
    airbox_path.write_text(airbox, encoding="utf-8")
    airbox_spec = load_and_resolve(airbox_path)
    assert airbox_spec.derived["internal"]["incident_theta_deg"] == 10.0
    assert airbox_spec.derived["internal"]["stage_case"] == "stage1_airbox"

    omitted = load_and_resolve(airbox_path)
    explicit = _write_variant(
        tmp_path,
        "airbox_explicit_zero.dat",
        airbox_path,
        [
            (
                "[materials]",
                "grating_width_x_nm = 0.0\ngrating_height_nm = 0.0\ngrating_width_y_nm = 0.0\n\n[materials]",
            )
        ],
    )
    assert (
        omitted.physical_model_sha256
        == load_and_resolve(explicit).physical_model_sha256
    )


def test_resolved_writer_uses_one_stable_payload_authority(tmp_path):
    spec = load_and_resolve("input/templates/hybrid_iterative_example.dat")
    target = tmp_path / "resolved_config.json"

    first_hash = write_resolved_config(spec, target)
    first_bytes = target.read_bytes()
    second_hash = write_resolved_config(spec, target)

    assert first_bytes == target.read_bytes()
    assert first_hash == second_hash == resolved_config_sha256(spec)
    assert first_hash == hashlib.sha256(first_bytes).hexdigest()
    assert json.loads(first_bytes) == spec.as_jsonable()


def _write_variant(tmp_path, name, source, replacements):
    text = Path(source).read_text(encoding="utf-8")
    for old, new in replacements:
        assert old in text
        text = text.replace(old, new, 1)
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_unknown_keys_and_inapplicable_fields_fail_closed_with_suggestions(tmp_path):
    unknown_section = _write_variant(
        tmp_path,
        "unknown_section.dat",
        "input/templates/ordinary_2d_example.dat",
        [("[geometry]", "[geomtry]")],
    )
    with pytest.raises(InputError, match="geomtry.*geometry"):
        load_and_resolve(unknown_section)

    unknown_field = _write_variant(
        tmp_path,
        "unknown_field.dat",
        "input/templates/ordinary_2d_example.dat",
        [("period_x_nm = 100.0", "period_x_nmm = 100.0")],
    )
    with pytest.raises(InputError, match="period_x_nmm.*period_x_nm"):
        load_and_resolve(unknown_field)

    inapplicable = _write_variant(
        tmp_path,
        "inapplicable.dat",
        "input/templates/ordinary_2d_example.dat",
        (("[boundary]\n", "[boundary]\nuse_floquet_y = true\n"),),
    )
    with pytest.raises(InputError, match="use_floquet_y.*not applicable"):
        load_and_resolve(inapplicable)

    missing = _write_variant(
        tmp_path,
        "missing_required.dat",
        "input/templates/ordinary_2d_example.dat",
        [("period_x_nm = 100.0\n", "")],
    )
    with pytest.raises(InputError, match="period_x_nm.*missing required"):
        load_and_resolve(missing)


def test_types_angles_polarization_and_boundary_contracts(tmp_path):
    bool_integer = _write_variant(
        tmp_path,
        "bool_integer.dat",
        "input/templates/ordinary_2d_example.dat",
        [("nedelec_degree = 2", "nedelec_degree = true")],
    )
    with pytest.raises(InputError, match="nedelec_degree.*integer"):
        load_and_resolve(bool_integer)

    nonfinite = _write_variant(
        tmp_path,
        "nonfinite.dat",
        "input/templates/ordinary_2d_example.dat",
        [("mesh_target_nm = 1.5", "mesh_target_nm = nan")],
    )
    with pytest.raises(InputError, match="NaN and infinity"):
        load_and_resolve(nonfinite)

    bad_pml = _write_variant(
        tmp_path,
        "bad_pml.dat",
        "input/templates/ordinary_2d_example.dat",
        [('vertical_boundary = "pml"', 'vertical_boundary = "robin"')],
    )
    with pytest.raises(InputError, match="2d_scattered"):
        load_and_resolve(bad_pml)

    bad_angle = _write_variant(
        tmp_path,
        "bad_angle.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                "grazing_angle_deg = 1.0",
                "grazing_angle_deg = 1.0\ntilt_from_downward_z_deg = 2.0",
            )
        ],
    )
    with pytest.raises(InputError, match="exactly one"):
        load_and_resolve(bad_angle)

    invalid_custom = _write_variant(
        tmp_path,
        "invalid_custom.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                'polarization = "s"',
                'polarization = "custom"\ncustom_polarization = [[1.0, 0.0], [0.0, 0.0], [0.0, 0.0]]',
            ),
        ],
    )
    with pytest.raises(InputError, match="transverse"):
        load_and_resolve(invalid_custom)

    bad_layer = _write_variant(
        tmp_path,
        "bad_layer.dat",
        "input/templates/full3d_direct_example.dat",
        [('scattering_background = "layered"', 'scattering_background = "air"')],
    )
    with pytest.raises(InputError, match="requires layered"):
        load_and_resolve(bad_layer)

    bad_floquet = _write_variant(
        tmp_path,
        "bad_floquet.dat",
        "input/templates/full3d_direct_example.dat",
        [("use_floquet_x = true", "use_floquet_x = false")],
    )
    with pytest.raises(InputError, match="Floquet x/y values must agree"):
        load_and_resolve(bad_floquet)


def test_explicit_floquet_mode_matches_resolved_trace_degree(tmp_path):
    bad_mode = _write_variant(
        tmp_path,
        "bad_floquet_mode.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                'floquet_constraint_mode = "auto"',
                'floquet_constraint_mode = "topological_edges"',
            )
        ],
    )
    with pytest.raises(InputError, match="resolved trace degree 1"):
        load_and_resolve(bad_mode)


def test_3d_dimension_consistency_accepts_decimal_nm_arithmetic(tmp_path):
    source = Path("input/templates/full3d_direct_example.dat").read_text(
        encoding="utf-8"
    )
    replacements = (
        ('geometry_kind = "rectangular_block_grating"', 'geometry_kind = "airbox"'),
        ("z_min_nm = -10.0", "z_min_nm = -0.1"),
        ("z_max_nm = 130.0", "z_max_nm = 0.5"),
        ("interface_z_nm = 0.0", "interface_z_nm = 0.2"),
        ("air_height_nm = 130.0", "air_height_nm = 0.3"),
        ("substrate_thickness_nm = 10.0", "substrate_thickness_nm = 0.3"),
        ("grazing_angle_deg = 1.0", "tilt_from_downward_z_deg = 10.0"),
        ('vertical_boundary = "dtn_port"', 'vertical_boundary = "strong_dirichlet"'),
        ('assembly_backend = "assembly_time_static_condensed"\n', ""),
        ('dtn_order_policy = "auto_propagating"\n', ""),
        ('dtn_assembly = "auxiliary"\n', ""),
        ("export_reference_planes = true", "export_reference_planes = false"),
        ("grating_width_x_nm = 17.0\n", ""),
        ("grating_width_y_nm = 25.0\n", ""),
        ("grating_height_nm = 120.0\n", ""),
        ("reference_plane_z_nm = [10.0, 30.0, 60.0, 90.0, 110.0]\n", ""),
    )
    for old, new in replacements:
        assert old in source
        source = source.replace(old, new, 1)
    path = tmp_path / "decimal_airbox.dat"
    path.write_text(source, encoding="utf-8")

    spec = load_and_resolve(path)

    assert spec.derived["internal"]["stage_case"] == "floquet_airbox"


def test_near_field_mesh_inputs_are_discretization_and_hash_bound(tmp_path):
    source = "input/templates/ordinary_2d_example.dat"
    for field, value, message in (
        (
            "near_field_margin_x_nm = 5.0",
            "near_field_margin_x_nm = -1.0",
            "must be non-negative",
        ),
        (
            "near_field_air_top_nm = 20.0",
            "near_field_air_top_nm = 0.0",
            "must be positive",
        ),
        (
            "near_field_sub_depth_nm = 10.0",
            "near_field_sub_depth_nm = 0.0",
            "must be positive",
        ),
    ):
        invalid = _write_variant(
            tmp_path, f"invalid_{field[:8]}.dat", source, [(field, value)]
        )
        with pytest.raises(InputError, match=message):
            load_and_resolve(invalid)

    original = load_and_resolve(source)
    changed = _write_variant(
        tmp_path,
        "changed_near_field.dat",
        source,
        [("near_field_margin_x_nm = 5.0", "near_field_margin_x_nm = 6.0")],
    )
    assert (
        load_and_resolve(changed).physical_model_sha256
        != original.physical_model_sha256
    )


def test_physical_hash_excludes_identity_method_solver_execution_and_output(tmp_path):
    source = "input/templates/full3d_direct_example.dat"
    changed_nonphysical = _write_variant(
        tmp_path,
        "nonphysical_changes.dat",
        source,
        [
            (
                'run_id = "euv_grazing1_phi0_full3d_direct_mpi8"',
                'run_id = "different_run"',
            ),
            ("mpi_size = 8", "mpi_size = 4"),
            ('results_root = "results"', 'results_root = "other_results"'),
            ("export_diffraction_orders = true", "export_diffraction_orders = false"),
            (
                'direct_solver_profile = "default"',
                'direct_solver_profile = "mumps_ooc"',
            ),
        ],
    )
    original = load_and_resolve(source)
    changed = load_and_resolve(changed_nonphysical)
    assert original.physical_model_sha256 == changed.physical_model_sha256
    assert original.input_sha256 != changed.input_sha256

    hybrid = load_and_resolve("input/templates/hybrid_direct_example.dat")
    assert original.physical_model_sha256 == hybrid.physical_model_sha256

    whitespace = tmp_path / "whitespace.dat"
    whitespace.write_bytes(Path(source).read_bytes() + b"\n")
    whitespace_spec = load_and_resolve(whitespace)
    assert whitespace_spec.physical_model_sha256 == original.physical_model_sha256
    assert whitespace_spec.input_sha256 != original.input_sha256

    physical_changes = (
        ("period_x_nm = 50.0", "period_x_nm = 51.0"),
        ("n_air = [1.0, 0.0]", "n_air = [1.1, 0.0]"),
        ("grazing_angle_deg = 1.0", "grazing_angle_deg = 2.0"),
        ("mesh_target_nm = 10.0", "mesh_target_nm = 11.0"),
        ('dtn_order_policy = "auto_propagating"', 'dtn_order_policy = "zero_order"'),
    )
    for index, replacement in enumerate(physical_changes):
        changed_physics = _write_variant(
            tmp_path,
            f"physical_change_{index}.dat",
            source,
            [replacement],
        )
        assert (
            load_and_resolve(changed_physics).physical_model_sha256
            != original.physical_model_sha256
        )


def test_expected_parent_is_deterministic_and_method_specific():
    direct = load_and_resolve("input/templates/hybrid_direct_example.dat")
    assert str(direct.expected_output_parent).endswith(
        "euv_grazing1_phi0_hybrid_direct_m120_mpi8__hybrid_direct__mpi8__M120"
    )
    full3d = load_and_resolve("input/templates/full3d_direct_example.dat")
    assert str(full3d.expected_output_parent).endswith(
        "euv_grazing1_phi0_full3d_direct_mpi8__full3d_direct__mpi8__Mna"
    )


def test_loader_rejects_invalid_utf8(tmp_path):
    path = tmp_path / "invalid_utf8.dat"
    path.write_bytes(b"schema_version = 1\n\xff\n")

    with pytest.raises(InputError, match="UTF-8"):
        load_dat_input(path)


def test_direct_rejects_hybrid_keys_dimension_mismatch_and_enum_typos(tmp_path):
    hybrid_key = _write_variant(
        tmp_path,
        "direct_with_hybrid_key.dat",
        "input/templates/full3d_direct_example.dat",
        [("[method]\n", "[method]\nbottom_interface_nm = 10.0\n")],
    )
    with pytest.raises(InputError, match="method.bottom_interface_nm.*not applicable"):
        load_and_resolve(hybrid_key)

    dimension_mismatch = _write_variant(
        tmp_path,
        "dimension_mismatch.dat",
        "input/templates/full3d_direct_example.dat",
        [("dimension = 3", "dimension = 2")],
    )
    with pytest.raises(InputError, match="not applicable"):
        load_and_resolve(dimension_mismatch)

    enum_typo = _write_variant(
        tmp_path,
        "enum_typo.dat",
        "input/templates/full3d_direct_example.dat",
        [('vertical_boundary = "dtn_port"', 'vertical_boundary = "dtn_prt"')],
    )
    with pytest.raises(InputError, match="dtn_prt.*dtn_port"):
        load_and_resolve(enum_typo)


def test_malformed_complex_pair_and_vector_fail_closed(tmp_path):
    bad_pair = _write_variant(
        tmp_path,
        "malformed_complex_pair.dat",
        "input/templates/full3d_direct_example.dat",
        [("n_air = [1.0, 0.0]", "n_air = [1.0]")],
    )
    with pytest.raises(InputError, match=r"materials.n_air.*\[real, imag\]"):
        load_and_resolve(bad_pair)

    bad_vector = _write_variant(
        tmp_path,
        "malformed_complex_vector.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                'polarization = "s"',
                'polarization = "custom"\ncustom_polarization = [[0.0, 0.0], [1.0, 0.0]]',
            )
        ],
    )
    with pytest.raises(InputError, match="custom_polarization.*three"):
        load_and_resolve(bad_vector)


def test_valid_te_polarizations_and_independent_3d_derived_values(tmp_path):
    te = _write_variant(
        tmp_path,
        "valid_te.dat",
        "input/templates/ordinary_2d_example.dat",
        [('polarization = "tm"', 'polarization = "te"')],
    )
    assert load_and_resolve(te).incidence["polarization"] == "te"

    p = _write_variant(
        tmp_path,
        "valid_p.dat",
        "input/templates/full3d_direct_example.dat",
        [('polarization = "s"', 'polarization = "p"')],
    )
    p_spec = load_and_resolve(p)
    assert p_spec.incidence["polarization"] == "p"

    custom = _write_variant(
        tmp_path,
        "valid_custom.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                'polarization = "s"',
                'polarization = "custom"\ncustom_polarization = [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0]]',
            )
        ],
    )
    custom_spec = load_and_resolve(custom)
    assert custom_spec.incidence["polarization"] == "custom"
    assert custom_spec.derived["polarization"] == (
        (0.0, 0.0),
        (1.0, 0.0),
        (0.0, 0.0),
    )

    direct = load_and_resolve("input/templates/full3d_direct_example.dat")
    assert isclose(direct.derived["internal"]["incident_theta_deg"], 89.0)
    assert isclose(direct.derived["k0"], 2.0 * pi / 13.5, rel_tol=1.0e-12)


def test_hybrid_accepted_alternate_pairs_and_rejected_solver_identities(tmp_path):
    direct_scalar = _write_variant(
        tmp_path,
        "hybrid_direct_scalar.dat",
        "input/templates/hybrid_direct_example.dat",
        [
            (
                'propagation_model = "continuous_beta"',
                'propagation_model = "full3d_uniform_cg"',
            ),
            (
                'traction_model = "continuous_qep_beta"',
                'traction_model = "scalar_cg_discrete_derivative"',
            ),
        ],
    )
    assert (
        load_and_resolve(direct_scalar).method["traction_model"]
        == "scalar_cg_discrete_derivative"
    )

    iterative_scalar = _write_variant(
        tmp_path,
        "hybrid_iterative_scalar.dat",
        "input/templates/hybrid_iterative_example.dat",
        [
            (
                'traction_model = "full3d_one_cell_exact_schur"',
                'traction_model = "scalar_cg_discrete_derivative"',
            )
        ],
    )
    assert (
        load_and_resolve(iterative_scalar).method["traction_model"]
        == "scalar_cg_discrete_derivative"
    )

    direct_bad_solver = _write_variant(
        tmp_path,
        "direct_bad_solver.dat",
        "input/templates/full3d_direct_example.dat",
        [('linear_solver = "direct"', 'linear_solver = "fgmres"')],
    )
    with pytest.raises(InputError, match="full3d_direct requires direct"):
        load_and_resolve(direct_bad_solver)

    iterative_bad_solver = _write_variant(
        tmp_path,
        "iterative_bad_solver.dat",
        "input/templates/hybrid_iterative_example.dat",
        [('linear_solver = "fgmres"', 'linear_solver = "direct"')],
    )
    with pytest.raises(InputError, match="hybrid_iterative requires fgmres"):
        load_and_resolve(iterative_bad_solver)

    bad_ilu = _write_variant(
        tmp_path,
        "bad_ilu_identity.dat",
        "input/templates/hybrid_iterative_example.dat",
        [("ilu_level = 0", "ilu_level = 1")],
    )
    with pytest.raises(InputError, match=r"ILU\(0\)"):
        load_and_resolve(bad_ilu)


@pytest.mark.parametrize(
    ("source", "old", "new", "message"),
    (
        (
            "input/templates/ordinary_2d_example.dat",
            "wavelength_nm = 13.5",
            "wavelength_nm = 0.0",
            "wavelength_nm",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "period_x_nm = 100.0",
            "period_x_nm = 0.0",
            "period_x_nm",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "mesh_target_nm = 1.5",
            "mesh_target_nm = 0.0",
            "mesh_target_nm",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "pml_alpha = 5.0",
            "pml_alpha = 0.0",
            "pml_alpha",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "power_probe_num_points = 1001",
            "power_probe_num_points = 1",
            "power_probe_num_points",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "mpi_size = 1",
            "mpi_size = 0",
            "mpi_size",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "warning_memory_gib = 4.0",
            "warning_memory_gib = 6.0",
            "warning_memory_gib",
        ),
        (
            "input/templates/ordinary_2d_example.dat",
            "timeout_seconds = 600",
            "timeout_seconds = 0",
            "timeout_seconds",
        ),
        (
            "input/templates/full3d_direct_example.dat",
            'mesh_spacing_mode = "boundary_fitted"',
            'mesh_spacing_mode = "local_refined"\nmesh_refined_size_nm = 0.0\nmesh_refinement_radius_nm = 1.0',
            "mesh_refined_size_nm",
        ),
        (
            "input/templates/full3d_direct_example.dat",
            'mesh_spacing_mode = "boundary_fitted"',
            'mesh_spacing_mode = "local_refined"\nmesh_refined_size_nm = 5.0\nmesh_refinement_radius_nm = 0.0',
            "mesh_refinement_radius_nm",
        ),
    ),
)
def test_core_numeric_and_execution_ranges_fail_closed(
    tmp_path, source, old, new, message
):
    invalid = _write_variant(tmp_path, f"invalid_{message}.dat", source, [(old, new)])
    with pytest.raises(InputError, match=message):
        load_and_resolve(invalid)


def test_warning_threshold_order_is_strict(tmp_path):
    invalid = _write_variant(
        tmp_path,
        "warning_equals_terminate.dat",
        "input/templates/ordinary_2d_example.dat",
        [("terminate_memory_gib = 6.0", "terminate_memory_gib = 4.0")],
    )
    with pytest.raises(InputError, match="warning_memory_gib"):
        load_and_resolve(invalid)


def test_stage_mapping_covers_floquet_airbox_pml_airbox_and_fresnel(tmp_path):
    source = Path("input/templates/full3d_direct_example.dat").read_text(
        encoding="utf-8"
    )

    def make_stage(name, geometry_kind, vertical, use_pml):
        text = source.replace(
            'geometry_kind = "rectangular_block_grating"',
            f'geometry_kind = "{geometry_kind}"',
            1,
        )
        text = text.replace(
            "grazing_angle_deg = 1.0", "tilt_from_downward_z_deg = 10.0", 1
        )
        text = text.replace(
            'vertical_boundary = "dtn_port"', f'vertical_boundary = "{vertical}"', 1
        )
        text = text.replace("use_pml = false", f"use_pml = {str(use_pml).lower()}", 1)
        for line in (
            "grating_width_x_nm = 17.0\n",
            "grating_width_y_nm = 25.0\n",
            "grating_height_nm = 120.0\n",
            'dtn_order_policy = "auto_propagating"\n',
            'dtn_assembly = "auxiliary"\n',
            'assembly_backend = "assembly_time_static_condensed"\n',
            'floquet_constraint_mode = "auto"\n',
        ):
            text = text.replace(line, "", 1)
        if use_pml:
            text = text.replace(
                "use_pml = true\n",
                "use_pml = true\npml_top_thickness_nm = 10.0\npml_bottom_thickness_nm = 10.0\npml_alpha = 5.0\n",
                1,
            )
        path = tmp_path / name
        path.write_text(text, encoding="utf-8")
        return load_and_resolve(path)

    floquet = make_stage("floquet_airbox.dat", "airbox", "strong_dirichlet", False)
    pml = make_stage("pml_airbox.dat", "airbox", "pml", True)
    fresnel = make_stage("fresnel.dat", "fresnel_interface", "pml", True)

    assert floquet.derived["internal"]["stage_case"] == "floquet_airbox"
    assert pml.derived["internal"]["stage_case"] == "pml_airbox"
    assert fresnel.derived["internal"]["stage_case"] == "fresnel_interface"


def test_fixed_p5_p6_trace_contract_and_bad_pair(tmp_path):
    valid = _write_variant(
        tmp_path,
        "fixed_p5_p6.dat",
        "input/templates/full3d_direct_example.dat",
        [
            (
                "nedelec_degree = 6",
                "nedelec_degree = 6\nnedelec_trace_degree = 5\nnedelec_interior_degree = 6",
            )
        ],
    )
    assert (
        load_and_resolve(valid).derived["nedelec_trace_contract"]
        == "fixed_p5_trace_p6_interior_exact_sequence"
    )

    invalid = _write_variant(
        tmp_path,
        "fixed_bad_pair.dat",
        valid,
        [("nedelec_interior_degree = 6", "nedelec_interior_degree = 5")],
    )
    with pytest.raises(InputError, match="p5 trace / p6 interior"):
        load_and_resolve(invalid)


def test_static_backend_scope_failure_is_an_input_error(tmp_path):
    source = Path("input/templates/full3d_direct_example.dat").read_text(
        encoding="utf-8"
    )
    source = source.replace(
        'geometry_kind = "rectangular_block_grating"', 'geometry_kind = "airbox"', 1
    )
    source = source.replace(
        "grazing_angle_deg = 1.0", "tilt_from_downward_z_deg = 10.0", 1
    )
    source = source.replace(
        'vertical_boundary = "dtn_port"', 'vertical_boundary = "strong_dirichlet"', 1
    )
    for line in (
        "grating_width_x_nm = 17.0\n",
        "grating_width_y_nm = 25.0\n",
        "grating_height_nm = 120.0\n",
        'dtn_order_policy = "auto_propagating"\n',
        'dtn_assembly = "auxiliary"\n',
    ):
        source = source.replace(line, "", 1)
    path = tmp_path / "static_out_of_scope.dat"
    path.write_text(source, encoding="utf-8")

    with pytest.raises(InputError, match="discretization.assembly_backend"):
        load_and_resolve(path)
