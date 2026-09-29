"""Analytic proposed target inventory only; no mesh, form, solve or training."""

from copy import deepcopy
import hashlib
import json
import subprocess
from pathlib import Path

from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.neural_micro_pilot import hexa_inventory
from src.solvers.feinn_fem import physical_config

ROOT = Path("/home/fenics/Projects/NN-Lab-V2")
design = json.loads((ROOT / "input/task042extra_feinn_5nm/design_v1.json").read_text())
target = deepcopy(design)
target["geometry"].update(
    bounds_nm=[[-25, 25], [-12.5, 12.5], [-1.25, 121.25]],
    block_bounds_nm=[[-12.5, 12.5], [-12.5, 12.5], [0, 120]],
    notch_bounds_nm=[[0, 12.5], [-3.75, 3.75], [40, 80]],
    cells=[40, 20, 98],
    step_nm=1.25,
)
cfg, material = physical_config(target)
modes = outgoing_port_modes_3d(cfg)
inventory = hexa_inventory(target["geometry"]["cells"], 3)
inventory["independent_all_FE"] = (
    inventory["independent_trace_rows"] + inventory["interior_rows"]
)
nx, ny, nz = target["geometry"]["cells"]
inventory["independent_edge_moments"] = 3 * nx * ny * (3 * nz + 2)
inventory["independent_face_moments"] = 12 * nx * ny * (3 * nz + 1)
cells = inventory["cells"]
N = inventory["independent_all_FE"]
fe = json.loads(
    (ROOT / "benchmarks/artifacts/task42extra/index_e1_fe.json").read_text()
)["result"]
grad = json.loads(
    (ROOT / "benchmarks/artifacts/task42extra/index_e1_grad.json").read_text()
)["result"]
ratio = N / fe["identity"]["full_independent_rows"]
cell_ratio = cells / fe["identity"]["cells"]
fill = grad["Gram_factor"]["symbolic"]["symbolic_l_nnz"] * ratio ** (4 / 3)
flops = grad["Gram_factor"]["symbolic"]["symbolic_flops"] * ratio**2
port_rows = nx * ny * 2 * 3**2
record = dict(
    schema="task42extra.proposed-target-capacity.v1",
    kind="derived geometry/counts; predicted sparse/factor costs, not measured PDE",
    source_sha=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip(),
    calculation_module_sha256={
        str(path): hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in (
            Path(__file__).relative_to(ROOT),
            Path("src/common/modes_3d.py"),
            Path("src/geometry/neural_micro_pilot.py"),
            Path("src/solvers/feinn_fem.py"),
        )
    },
    source_design_sha256=hashlib.sha256(
        (ROOT / "input/task042extra_feinn_5nm/design_v1.json").read_bytes()
    ).hexdigest(),
    material_table_sha256=material.provenance["material_table_sha256"],
    proposed_geometry=target["geometry"],
    proposed_geometry_not_frozen=True,
    wavelength_nm=5,
    inventory=inventory,
    channels=dict(
        total=len(modes),
        top=sum(m.side == "top" for m in modes),
        bottom=sum(m.side == "bottom" for m in modes),
        ordered_keys=[[m.side, m.m, m.n, m.polarization] for m in modes],
        meaning="analytic original auto-propagating inventory; no target FE coupling assembled",
    ),
    bounds_align_to_h=True,
    N_ratio=ratio,
    cell_ratio=cell_ratio,
    array_payload_derived=dict(
        one_full_complex_FE_vector_bytes=N * 16,
        free_real_parameters_bytes=N * 16,
        free_lbfgs_20_direction_pairs_bytes=20 * 2 * N * 16,
        current_unbounded_volume_temporary_bytes=cells * 144**2 * 16,
        q15_coordinates_bytes=cells * 992 * 3 * 8,
        local_MPC_expansion_COO_upper_bytes=cells * 144 * 32,
        one_port_surface_independent_tangential_rows=port_rows,
        both_B_D_COO_upper_bytes=2 * len(modes) * port_rows * 32,
    ),
    Gram_predictions=dict(
        linear_cell_nnz=fe["gram"]["nnz"] * cell_ratio,
        linear_cell_payload_bytes=fe["gram"]["csr_payload_bytes"] * cell_ratio,
        factor_nnz_3D_N_4_over_3=fill,
        factor_storage_at_24_bytes_per_entry=fill * 24,
        conservative_factor_workspace_bytes=1.5 * fill * 24 + 64 * N + 64 * 2**20,
        factor_flops_3D_N_squared=flops,
        factor_seconds_at_M5_single_core_rate=grad["Gram_factor"]["numeric_seconds"]
        * ratio**2,
        exact_target_Gram_NNZ="unknown/not_assembled",
        matrix_free_cell_complex_multiply_adds_per_G_action=cells * 144**2,
        matrix_free_batch8_local_tensor_temporary_bytes=8 * 144**2 * 16,
        eight_full_complex_Krylov_vectors_bytes=8 * N * 16,
        hypothetical_scalar_p3_periodic_auxiliary_rows=(3 * nx)
        * (3 * ny)
        * (3 * nz + 1),
        matrix_free_iteration_count="unknown/not_run",
        multilevel_hierarchy_fill_and_iterations="unknown/not_run",
        actual_target_symbolic_fill="not_run",
        uncertainty="Different anisotropy, boundary graph, sparse ordering and cache can substantially change these predictions. They do not authorize a target run or prove a memory bound.",
    ),
    target_PDE_run=False,
    target_0p7nm_run=False,
    actual_target_mesh_created=False,
    next_resource_contract_required=True,
)
out = ROOT / "tmp/task42extra/development/target_capacity_v1.json"
out.write_text(json.dumps(record, indent=2) + "\n")
print(json.dumps({key: record[key] for key in ("inventory", "N_ratio", "cell_ratio")}))
print(
    json.dumps(
        dict(
            channels=record["channels"]["total"],
            top=record["channels"]["top"],
            bottom=record["channels"]["bottom"],
        )
    )
)
