"""Pure coverage tests for the Task38 T1 schema, templates, and manual."""

import json
import re
import tomllib
from pathlib import Path

from src.io.input_schema import (
    FIELD_SPECS,
    FIELD_SPECS_BY_KEY,
    IDENTITY_FIELD_SPECS,
    IDENTITY_KEYS,
    METHOD_KINDS,
    PUBLIC_FIELD_KEYS,
    PUBLIC_FIELD_SPECS,
    SCHEMA_VERSION,
    SECTION_FIELD_KEYS,
    SECTION_NAMES,
)


ROOT = Path(__file__).parents[2]
README = ROOT / "input" / "README.md"
TEMPLATES = ROOT / "input" / "templates"


def _flatten_sections(document):
    for section, values in document.items():
        if section in IDENTITY_KEYS:
            yield section, values
            continue
        for name, value in values.items():
            yield f"{section}.{name}", value


def _readme_table():
    text = README.read_text(encoding="utf-8")
    table_start = text.index("| 完整键名")
    marker_start = text.index("## Machine-readable schema markers")
    table_lines = text[table_start:marker_start].rstrip().splitlines()
    assert table_lines[0].startswith("| 完整键名 |")
    assert table_lines[1].startswith("| --- |")
    data_lines = table_lines[2:]
    assert len(data_lines) == len(PUBLIC_FIELD_KEYS)
    assert all(line.startswith("| `") for line in data_lines)
    rows = {}
    for line in data_lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        key = cells[0].strip("`")
        assert key not in rows
        rows[key] = cells
    assert list(rows) == list(PUBLIC_FIELD_KEYS)
    return text, rows


def test_schema_identity_sections_and_unique_whitelist():
    assert IDENTITY_KEYS == (
        "schema_version",
        "model_id",
        "run_id",
        "comparison_group",
        "dimension",
    )
    assert SECTION_NAMES == (
        "geometry",
        "materials",
        "incidence",
        "discretization",
        "boundary",
        "method",
        "solver",
        "execution",
        "output",
    )
    assert len(IDENTITY_FIELD_SPECS) == 5
    assert len(FIELD_SPECS) == 95
    assert len(PUBLIC_FIELD_SPECS) == len(PUBLIC_FIELD_KEYS) == 100
    assert set(FIELD_SPECS_BY_KEY) == set(PUBLIC_FIELD_KEYS)
    assert {name: len(keys) for name, keys in SECTION_FIELD_KEYS.items()} == {
        "geometry": 11,
        "materials": 6,
        "incidence": 8,
        "discretization": 12,
        "boundary": 10,
        "method": 7,
        "solver": 13,
        "execution": 5,
        "output": 23,
    }
    assert METHOD_KINDS == (
        "2d_scattered",
        "2d_port",
        "full3d_direct",
        "hybrid_direct",
        "hybrid_iterative",
    )
    assert FIELD_SPECS_BY_KEY["dimension"].value_type == "integer"
    assert FIELD_SPECS_BY_KEY["dimension"].allowed == ("2", "3")
    assert FIELD_SPECS_BY_KEY["discretization.mesh_spacing_mode"].allowed == (
        "auto",
        "uniform_strict",
        "boundary_fitted",
        "local_refined",
    )
    assert FIELD_SPECS_BY_KEY["boundary.dtn_order_policy"].allowed == (
        "zero_order",
        "auto_propagating",
        "manual",
    )
    assert FIELD_SPECS_BY_KEY["solver.linear_solver"].allowed == (
        "direct",
        "fgmres",
    )
    assert FIELD_SPECS_BY_KEY["solver.preconditioner"].allowed == (
        "hybrid_block_ldu_ilu0_dtn_woodbury",
    )
    for key in (
        "geometry.period_y_nm",
        "geometry.z_min_nm",
        "geometry.z_max_nm",
        "geometry.interface_z_nm",
        "geometry.air_height_nm",
        "geometry.substrate_thickness_nm",
        "solver.absolute_tolerance",
    ):
        assert FIELD_SPECS_BY_KEY[key].required is True
    assert "required only for grating geometry" in " ".join(
        FIELD_SPECS_BY_KEY["geometry.grating_width_x_nm"].constraints
    )
    assert "required only for 3D grating geometry" in " ".join(
        FIELD_SPECS_BY_KEY["geometry.grating_width_y_nm"].constraints
    )
    assert "required only for grating geometry" in " ".join(
        FIELD_SPECS_BY_KEY["geometry.grating_height_nm"].constraints
    )


def test_readme_markers_and_continuous_table():
    text, rows = _readme_table()
    marker_pattern = re.compile(r"^<!-- schema-field (\{.*\}) -->$", re.MULTILINE)
    markers = [json.loads(match) for match in marker_pattern.findall(text)]
    assert len(markers) == len(PUBLIC_FIELD_KEYS) == 100
    assert [marker["key"] for marker in markers] == list(PUBLIC_FIELD_KEYS)
    assert len({marker["key"] for marker in markers}) == len(markers)
    for marker in markers:
        spec = FIELD_SPECS_BY_KEY[marker["key"]]
        assert marker["unit"] == spec.unit
        assert tuple(marker["applicability"]) == spec.applicability

    for key, cells in rows.items():
        spec = FIELD_SPECS_BY_KEY[key]
        assert cells[2].strip("`") == spec.unit
        assert tuple(cells[6].split("/")) == spec.applicability

    assert "python scripts/run_case.py input/path/to/case.dat --validate-only" in text
    assert "python scripts/run_case.py input/path/to/case.dat --dry-run" in text
    assert (
        "results/<model_id>/<run_id>__<method>__mpi<N>__M<M-or-na>/<timestamp>/" in text
    )
    assert "Woodbury K、Schur size、runtime lifecycle" in text
    assert "T2 将实现 schema 解析" in text
    assert "T1 loader" not in text
    assert rows["geometry.grating_width_x_nm"][8] == (
        "`2D grating_width / 3D grating_width_x`"
    )
    assert rows["discretization.lock_near_field_template"][8] == (
        "`mesh_lock_near_field_template`"
    )
    assert rows["boundary.use_floquet_x"][8] == (
        "`2D periodic constraint contract / 3D use_floquet_xy`"
    )
    assert rows["output.near_field_margin_x_nm"][8] == "`near_field_margin_x`"
    assert rows["output.diffraction_order_max_m"][8].startswith(
        "`2D diffraction_order_count"
    )


def test_templates_parse_and_use_only_public_keys():
    expected = {
        "ordinary_2d_example.dat": "2d_scattered",
        "full3d_direct_example.dat": "full3d_direct",
        "hybrid_direct_example.dat": "hybrid_direct",
        "hybrid_iterative_example.dat": "hybrid_iterative",
    }
    found_methods = set()
    identity_and_sections = set(IDENTITY_KEYS) | set(SECTION_NAMES)
    forbidden_key_fragments = (
        "runs",
        "batch",
        "internal",
        "authority",
        "candidate_modes",
        "dtn_mode_count",
        "woodbury",
        "schur",
        "qep",
        "lifecycle",
    )
    for filename, expected_method in expected.items():
        document = tomllib.loads((TEMPLATES / filename).read_text(encoding="utf-8"))
        assert set(document) == identity_and_sections
        assert type(document["dimension"]) is int
        assert document["dimension"] in (2, 3)
        assert document["schema_version"] == SCHEMA_VERSION
        method = document["method"]["kind"]
        assert method == expected_method
        found_methods.add(method)
        dimension_tag = f"{document['dimension']}d"
        for key, value in _flatten_sections(document):
            assert key in FIELD_SPECS_BY_KEY
            assert not any(fragment in key for fragment in forbidden_key_fragments)
            spec = FIELD_SPECS_BY_KEY[key]
            assert (
                "all" in spec.applicability
                or dimension_tag in spec.applicability
                or method in spec.applicability
            )
            if spec.allowed and isinstance(value, str):
                assert value in spec.allowed
        for key in ("n_air", "n_substrate", "n_grating"):
            pair = document["materials"][key]
            assert isinstance(pair, list) and len(pair) == 2
            assert all(isinstance(item, (int, float)) for item in pair)
        if document["dimension"] == 2:
            assert "use_floquet_y" not in document["boundary"]
            assert "mesh_spacing_mode" not in document["discretization"]
        else:
            assert "use_floquet_y" in document["boundary"]
        if method in {"full3d_direct", "hybrid_direct"}:
            assert "preconditioner" not in document["solver"]
        if method == "hybrid_iterative":
            assert "preconditioner" in document["solver"]
            assert "side_residual_correction_steps" in document["solver"]
    assert found_methods == set(expected.values())
