from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import cos, pi, sin
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class Tags:
    air: int = 1
    substrate: int = 2
    grating: int = 3
    top_pml: int = 4
    bottom_pml: int = 5
    left: int = 11
    right: int = 12
    outer_top: int = 13
    outer_bottom: int = 14


@dataclass
class SimulationConfig:
    case_name: str = "air_substrate_grating"

    # 运行选择。直接运行 run_cases.py 时默认读取这里，不再强迫你写命令行参数。
    # calculation_method 可选: "scattered", "port", "all"。
    # constraint_backend 可选: "mpc_official", "manual", "both"。
    # port_boundary_model 可选: "robin", "dtn", "all"。
    # scattering_background 只对 scattered 有效，可选: "air", "layered"。
    # polarization_type 可选: "TM" 或 "TE"。TM 是当前 Ex/Ey 矢量模型，TE 是新增 Ez 标量模型。
    calculation_method: str = "all"
    constraint_backend: str = "both"
    port_boundary_model: str = "all"
    scattering_background: str = "layered"
    polarization_type: str = "TM"

    # 所有长度单位均为 um；下面的默认值是纳米级结构。
    period_x: float = 0.60
    air_height: float = 0.85
    substrate_thickness: float = 0.35
    pml_top_thickness: float = 0.30
    pml_bottom_thickness: float = 0.30
    grating_width: float = 0.30
    grating_height: float = 0.18
    lambda0: float = 0.633
    incident_angle_deg: float = 15.0
    n_air: complex = 1.0 + 0.0j
    n_substrate: complex = 1.45 + 0.0j
    n_grating: complex = 1.45 + 0.0j

    # scattered 方法固定使用上下 PML；端口法默认不用 PML，直接在上下边界放端口。
    use_pml: bool = True
    port_use_pml: bool = False

    # port_incident_amplitude 是入射端口电场振幅；1 表示输出为归一化电场。
    # port_dtn_order_count=N 表示 DtN 端口保留 m=-N...N 的 Floquet 衍射级次。
    port_incident_amplitude: complex = 1.0 + 0.0j
    port_dtn_order_count: int = 2
    # Fourier-DtN port: explicit 保留旧的 Q^*YQ 外积参考实现；
    # auxiliary 新增端口模态幅值辅助未知量，后续更适合扩展到大规模 3D。
    port_dtn_assembly: str = "auxiliary"
    # False 只使用 0 级；True 自动识别上下端口各自明确传播的衍射级。
    port_use_diffraction_orders: bool = False
    port_rayleigh_tolerance: float = 1.0e-6

    # True: 每次运行生成新的 results/run_..._YYYYMMDD_HHMMSS 文件夹。
    unique_output: bool = True

    # 后处理指标。diffraction_order_count=N 表示统计 m=-N...N 的反射/透射级次。
    compute_power_metrics: bool = True
    diffraction_order_count: int = 2
    power_probe_num_points: int = 512

    nedelec_degree: int = 2
    visualization_degree: int = 3
    mesh_target_size: float = 0.025
    pml_alpha: float = 5.0
    tags: Tags = field(default_factory=Tags)

    @property
    def eps_air(self) -> complex:
        return complex(self.n_air**2)

    @property
    def eps_substrate(self) -> complex:
        return complex(self.n_substrate**2)

    @property
    def eps_grating(self) -> complex:
        return complex(self.n_grating**2)

    @property
    def theta_rad(self) -> float:
        return self.incident_angle_deg * pi / 180.0

    @property
    def k0(self) -> float:
        return 2.0 * pi / self.lambda0

    @property
    def omega(self) -> float:
        return 2.0 * pi * 299_792_458.0 / (self.lambda0 * 1e-6)

    @property
    def kx(self) -> complex:
        return self.k0 * complex(self.n_air) * sin(self.theta_rad)

    @property
    def ky(self) -> complex:
        return -self.k0 * complex(self.n_air) * cos(self.theta_rad)

    @property
    def polarization(self) -> tuple[float, float]:
        return (cos(self.theta_rad), sin(self.theta_rad))

    @property
    def floquet_phase(self) -> complex:
        return np.exp(1j * self.kx * self.period_x)

    @property
    def total_height(self) -> float:
        pml_height = self.pml_top_thickness + self.pml_bottom_thickness if self.use_pml else 0.0
        return self.air_height + self.substrate_thickness + pml_height

    @property
    def physical_y_min(self) -> float:
        return -self.substrate_thickness

    @property
    def physical_y_max(self) -> float:
        return self.air_height

    @property
    def y_min(self) -> float:
        return self.physical_y_min - self.pml_bottom_thickness if self.use_pml else self.physical_y_min

    @property
    def y_max(self) -> float:
        return self.physical_y_max + self.pml_top_thickness if self.use_pml else self.physical_y_max

    @property
    def x_min(self) -> float:
        return -0.5 * self.period_x

    @property
    def x_max(self) -> float:
        return 0.5 * self.period_x

    @property
    def grating_x_min(self) -> float:
        return -0.5 * self.grating_width

    @property
    def grating_x_max(self) -> float:
        return 0.5 * self.grating_width

    @property
    def substrate_y_min(self) -> float:
        return -self.substrate_thickness

    @property
    def substrate_y_max(self) -> float:
        return 0.0

    @property
    def grating_y_min(self) -> float:
        return self.substrate_y_max

    @property
    def grating_y_max(self) -> float:
        return self.substrate_y_max + self.grating_height

    def as_jsonable(self) -> dict[str, object]:
        data = asdict(self)
        data["n_air"] = [complex(self.n_air).real, complex(self.n_air).imag]
        data["n_substrate"] = [complex(self.n_substrate).real, complex(self.n_substrate).imag]
        data["n_grating"] = [complex(self.n_grating).real, complex(self.n_grating).imag]
        data["k0"] = self.k0
        data["omega"] = self.omega
        data["kx"] = [complex(self.kx).real, complex(self.kx).imag]
        data["ky"] = [complex(self.ky).real, complex(self.ky).imag]
        data["polarization"] = list(self.polarization)
        data["floquet_phase"] = [self.floquet_phase.real, self.floquet_phase.imag]
        data["eps_air"] = [self.eps_air.real, self.eps_air.imag]
        data["eps_substrate"] = [self.eps_substrate.real, self.eps_substrate.imag]
        data["eps_grating"] = [self.eps_grating.real, self.eps_grating.imag]
        return data


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]
