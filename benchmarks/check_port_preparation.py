"""Independent saved-array checker: no FE imports, solver, factor or reference."""

import hashlib
import json
from pathlib import Path

import numpy as np

from src.solvers.bounded_port_provider import (
    BoundedPortAction,
    BoundedPortProvider,
    PortFunctional,
    json_bytes,
)
from src.solvers.port_component_study import relative


def read_arrays(receipt, root):
    path = Path(receipt["path"]).resolve()
    if (
        not path.is_relative_to(root)
        or hashlib.sha256(path.read_bytes()).hexdigest() != receipt["sha256"]
    ):
        raise ValueError("saved numeric container hash/path mismatch")
    with np.load(path, allow_pickle=False) as f:
        if set(f.files) != set(receipt["members"]):
            raise ValueError("saved member inventory")
        result = {k: f[k] for k in f.files}
    for key, array in result.items():
        member = receipt["members"][key]
        if (
            list(array.shape) != member["shape"]
            or array.dtype.str != member["dtype"]
            or hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()
            != member["sha256"]
            or not np.isfinite(array).all()
        ):
            raise ValueError("saved member shape/dtype/hash/finite")
        array.flags.writeable = False
    return result


class FilePortSource:
    def __init__(self, manifest, root, source_identity):
        self.manifest, self.root, self.source_identity = manifest, root, source_identity
        self.bytes_read = 0

    def upper_bytes(self, index):
        members = self.manifest["modes"][index]["file"]["members"]
        return (
            sum(
                np.prod(v["shape"], dtype=np.int64).item()
                * np.dtype(v["dtype"]).itemsize
                for v in members.values()
            )
            + 8
        )

    def expected_hash(self, index):
        return self.manifest["modes"][index]["numeric_sha256"]

    def __call__(self, index, source_identity):
        if source_identity != self.source_identity:
            raise ValueError("read-only source identity mismatch")
        row = self.manifest["modes"][index]
        a = read_arrays(row["file"], self.root)
        self.bytes_read += Path(row["file"]["path"]).stat().st_size
        return PortFunctional(
            tuple(row["key"]),
            a["coupling_rows"],
            a["coupling_values"],
            a["projection_rows"],
            a["projection_values"],
            row["H"],
            row["identity"],
        )


def check_component(record, root):
    root = Path(root).resolve()
    from src.io.port_preparation import PLAN

    plan = json.loads(PLAN.read_text())
    if (
        record["physical_sha256"] != plan["micro_physical_sha256"]
        or record["mode_manifest_sha256"] != plan["micro_mode_sha256"]
        or record["design_sha256"] != plan["micro_design_sha256"]
    ):
        raise ValueError("frozen micro physical/material/mode/design identity")
    manifest_path = Path(record["surface_manifest"]["path"])
    if (
        not manifest_path.resolve().is_relative_to(root)
        or hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        != record["surface_manifest"]["sha256"]
    ):
        raise ValueError("surface inventory hash")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest["schema"] != "bounded-port.surface.v1"
        or len(manifest["modes"]) != 40
        or manifest["mode_manifest_sha256"] != record["mode_manifest_sha256"]
        or manifest["physical_sha256"] != record["physical_sha256"]
        or manifest["global_rows"] != 34050
        or manifest["ownership_range"] != [0, 34050]
    ):
        raise ValueError("complete surface/mode inventory")
    if (
        record["volume_actions"]
        or record["new_LU"]
        or record["new_QR"]
        or record["KSP"]
        or record["reference_read"]
        or record["seven_block_factors_read"]
    ):
        raise ValueError("boundary-only ownership violated")
    rows = manifest["modes"]
    if [m["index"] for m in rows] != list(range(40)) or len(
        {tuple(m["key"]) for m in rows}
    ) != 40:
        raise ValueError("ordered mode inventory")
    original_identity_hash = hashlib.sha256(
        json_bytes(
            {
                "schema": "fullspace-dtn.mode-manifest.v1",
                "profile": "full3d_scalable_v1",
                "mode_count": 40,
                "modes": [m["identity"] for m in rows],
            }
        )
    ).hexdigest()
    if original_identity_hash != record["mode_manifest_sha256"]:
        raise ValueError("original ordered mode identity checksum")
    if (
        record["seeds"] != [423611, 423613]
        or record["FE_storage"] != 34050
        or record["quadrature"] != 15
    ):
        raise ValueError("frozen micro/witness identity")
    arrays = read_arrays(record["numeric_witness"], root)
    required = {"zero_forward"}
    for seed in (423611, 423613):
        required.update(
            k + "_" + str(seed)
            for k in (
                "x",
                "y",
                "alpha",
                "old_forward",
                "new_forward",
                "old_adjoint",
                "new_adjoint",
                "old_amplitudes",
                "new_amplitudes",
                "old_modal_rhs",
                "new_modal_rhs",
                "scaled_forward",
                "old_power",
                "new_power",
                "unit_old_power",
                "unit_new_power",
            )
        )
    if set(arrays) != required:
        raise ValueError("complete component witness inventory")
    source = FilePortSource(manifest, root, record["source_identity"])
    provider = BoundedPortProvider(
        [m["key"] for m in rows],
        [m["identity"] for m in rows],
        source,
        source_identity=record["source_identity"],
        global_rows=34050,
        ownership_range=manifest["ownership_range"],
        slave_rows=manifest["slave_rows"],
        max_modes=2,
        cache_bytes=2**20,
    )
    action = BoundedPortAction(provider)
    checks = []
    for seed in (423611, 423613):
        s = str(seed)
        x, y = arrays["x_" + s], arrays["y_" + s]
        if (
            x.shape != (34050,)
            or y.shape != (34050,)
            or arrays["alpha_" + s].shape != (40,)
        ):
            raise ValueError("input FE/port shapes")
        if np.any(x[np.array(manifest["slave_rows"], dtype=np.int64)]) or np.any(
            y[np.array(manifest["slave_rows"], dtype=np.int64)]
        ):
            raise ValueError("canonical slave-zero input")
        for kind, fresh in [
            ("forward", action.apply(x)),
            ("adjoint", action.apply(y, adjoint=True)),
            ("amplitudes", action.recover(x)),
            ("modal_rhs", action.modal_rhs(arrays["alpha_" + s])),
        ]:
            for partner in ("new", "old"):
                row = relative(fresh, arrays[partner + "_" + kind + "_" + s])
                checks.append(
                    dict(label="replay_" + partner + "_" + kind + "_" + s, **row)
                )
        row = relative(
            arrays["scaled_forward_" + s], (0.37 - 0.91j) * arrays["new_forward_" + s]
        )
        checks.append(dict(label="linear_" + s, **row))
        a, h = arrays["new_forward_" + s], arrays["new_adjoint_" + s]
        num = abs(np.vdot(y, a) - np.vdot(h, x))
        den = np.linalg.norm(y) * np.linalg.norm(a) + np.linalg.norm(
            h
        ) * np.linalg.norm(x)
        checks.append(
            {
                "label": "dual_" + s,
                "numerator": float(num),
                "denominator": float(den),
                "relative": float(num / den),
                "pass_gate": num <= 1e-10 * den,
            }
        )

        def complex_vec(values):
            return np.array([complex(v["real"], v["imag"]) for v in values])

        independent_weights, h_errors = [], []
        area = 1.4 * 1.05
        for mode in rows:
            identity = mode["identity"]
            k, e = complex_vec(identity["k_vector"]), complex_vec(identity["e_vector"])
            normal_sign = 1 if identity["side"] == "top" else -1
            H = np.cross(k, e) / (2 * np.pi / 0.7)
            phase = np.exp(1j * k[2] * (1.225 if normal_sign == 1 else -0.175))
            tangential = float(np.vdot(e[:2], e[:2]).real)
            h_expected = area * tangential * abs(phase) ** 2
            h_errors.append(abs(mode["H"] - h_expected) / h_expected)
            power = (
                max(0.5 * np.real(np.cross(e, H.conj()))[2] * normal_sign, 0.0)
                * area
                * abs(phase) ** 2
                / record["incident_power"]
            )
            independent_weights.append(power)
        if max(h_errors) > 1e-12:
            raise ValueError("original H/reference-plane convention")
        weights = np.array(independent_weights)
        for partner in ("new", "old"):
            power = weights * abs(arrays[partner + "_amplitudes_" + s]) ** 2
            row = relative(power, arrays[partner + "_power_" + s])
            checks.append(dict(label="power_recompute_" + partner + "_" + s, **row))
        unit_error = float(
            max(
                np.max(abs(weights - arrays["unit_new_power_" + s])),
                np.max(abs(weights - arrays["unit_old_power_" + s])),
            )
        )
        checks.append(
            {
                "label": "unit_power_" + s,
                "maximum_absolute": unit_error,
                "pass_gate": unit_error <= 1e-10,
            }
        )
    checks.append({"label": "zero", "pass_gate": not np.any(arrays["zero_forward"])})
    provider.clear()
    if not all(c["pass_gate"] for c in checks):
        raise ValueError("independent saved boundary component gate")
    stats = record["provider_stats"]
    if (
        stats["cache_peak_bytes"] > 2**20
        or stats["lease_peak_bytes"] > 2**20
        or stats["created_live_peak"] > 2
        or stats["active_batches_peak"] != 1
        or not record["cache_empty_after"]
        or stats["evictions"] == 0
    ):
        raise ValueError("bounded numeric lifetime/cache gate")
    return {
        "status": "PORT_COMPONENT_CACHE_CHECKED",
        "checks": checks,
        "replay_stats": provider.stats,
        "replay_bytes_read": source.bytes_read,
        "no_FE_runtime": True,
        "reference_read": False,
        "full_solve": False,
    }


def check_inventory(record):
    capacity = record["capacity"]
    nx, ny, nz = capacity["axis_cells"]
    p = 6
    full_edges = (
        nx * (ny + 1) * (nz + 1) + ny * (nx + 1) * (nz + 1) + nz * (nx + 1) * (ny + 1)
    )
    full_faces = nx * ny * (nz + 1) + nx * nz * (ny + 1) + ny * nz * (nx + 1)
    interior = 3 * p * (p - 1) ** 2 * nx * ny * nz
    trace = p * nx * ny * (3 * nz + 2) + 2 * p * (p - 1) * nx * ny * (3 * nz + 1)
    full = p * full_edges + 2 * p * (p - 1) * full_faces + interior
    c = capacity["counts"]
    if (
        c["full_fe_rows"] != full
        or c["independent_trace_rows"] != trace
        or c["interior_rows"] != interior
    ):
        raise ValueError("independent original-size entity counts")
    nport = record["inventory"]["mode_count"]
    if (
        capacity["arrays"]["one_dense_Hhat_or_port_matrix"]["bytes"]
        != 16 * nport * nport
    ):
        raise ValueError("full port N^2 accounting")
    if (
        not capacity["integer_range_pass"]
        or record["target_solve"] != "NOT_AUTHORIZED_OR_NOT_QUALIFIED"
        or record["volume_mesh_created"]
    ):
        raise ValueError("preparation capacity/authorization boundary")
    path = Path(record["ordered_modes"]["path"])
    if (
        hashlib.sha256(path.read_bytes()).hexdigest()
        != record["ordered_modes"]["sha256"]
    ):
        raise ValueError("target complete ordered inventory file hash")
    modes = json.loads(path.read_text())
    if len(modes) != nport or [m["mode_index"] for m in modes] != list(range(nport)):
        raise ValueError("target ordered inventory length")
    if len({(m["side"], m["m"], m["n"], m["polarization"]) for m in modes}) != nport:
        raise ValueError("target duplicate inventory")
    return {
        "status": "TARGET_INPUT_CAPACITY_CHECKED",
        "independent_full_rows": full,
        "independent_active_trace": trace,
        "complete_modes": nport,
    }


def check_saved():
    from src.io.port_preparation import ARTIFACT, read_stage

    inventory, _ = read_stage("INVENTORY")
    component, _ = read_stage("COMPONENT")
    a = check_inventory(inventory)
    b = check_component(component, ARTIFACT)
    return {
        "status": "V36_PREPARATION_CHECKED",
        "inventory": a,
        "component": b,
        "component_status": "PORT_COMPONENT_QUALIFIED_ON_MICRO",
        "target_status": "TARGET_SOLVE_NOT_AUTHORIZED_OR_NOT_QUALIFIED",
        "full_forward_qualification": False,
        "neural20": "NOT_DEMONSTRATED",
    }
