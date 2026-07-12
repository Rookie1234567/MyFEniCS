# main.py 参数地图

`src/main.py` 是 PyCharm 门面，不保存 benchmark 结果，也不替代两个 runner。`preset_cli_args()` 把不可变 dataclass 翻译为 `run_cases.py` 或 `run_3d_cases.py` 的参数；runner 再生成 `SimulationConfig`。

## 选择规则

| 入口 | 用途 |
|---|---|
| `ACTIVE_PYCHARM_PRESET` | 无参数 PyCharm Run 的唯一选择 |
| `python src/main.py --preset NAME` | 命令行复用相同 preset |
| `python src/main.py 2d ...` | 直接进入 2D runner |
| `python src/main.py 3d ...` | 直接进入 3D runner |

## 共同物理参数

| 字段 | 对象/单位 | 合法或常用值 | 改动影响 |
|---|---|---|---|
| `lambda0` | 真空波长，nm | `>0` | 改变波数、传播级和材料适用性 |
| `n_air/substrate/grating` | 复折射率 | `a+bj` | `Im(n)>0` 在当前约定中表示吸收；必须重查 RTA |
| `incident_*_deg` | 入射角，度 | 2D 一个角；3D theta/phi | 改变 Floquet 相位与端口传播常数 |
| `polarization_type/kind` | 偏振 | 2D `TM/TE`；3D `s/p/custom` | 选择不同函数空间/入射向量 |
| `period_x/y` | 周期，nm | `>0` | 改变倒格矢和衍射级 |

## 数值参数

| 字段 | 含义 | 约束 | 资格影响 |
|---|---|---|---|
| `nedelec_degree` | H(curl) 阶数 | 2D/3D 常用 1、2 | p=2 内存显著增加；迭代生产档固定 p=2 |
| `mesh_target_size` | 目标网格宽度，nm | `>0` | 不是精确单元宽度；改变即需网格收敛检查 |
| `mesh_cell_shape/type` | 单元类型 | 2D tri/quad；3D auto/tet/hex | Floquet Stage 4 主要使用匹配六面体 |
| `mesh_spacing_mode` | Stage 4 轴网格 | auto/uniform_strict/boundary_fitted/local_refined | 材料面必须与网格面一致 |
| `floquet_constraint_mode` | 周期约束构造 | auto 或代码列出的显式模式 | p=1/p=2 路径不同，不可随意互换 |
| `visualization_degree` | 输出插值阶数 | 正整数 | 影响输出体积，不改变原始 FE 解 |

## 边界与端口

| 字段 | 含义 | 建议 |
|---|---|---|
| `calculation_method` | 2D scattered 或 port | PML 用 scattered；DtN/Robin 用 port |
| `port_boundary_model` | robin/dtn | 多衍射级正式功率优先 DtN |
| `port_dtn_assembly` | auxiliary/explicit | auxiliary 正式路径；explicit 仅交叉核验 |
| `port_use_diffraction_orders` | 是否自动纳入传播级 | 正式周期端口开启 |
| `stage4_boundary_model` | 3D dtn_port/pml/robin0 | Stage 4 正式路径为 dtn_port |
| `stage4_dtn_order_policy` | auto_propagating/zero_order/manual | 真实光栅用 auto；小平层可 zero_order |
| `pml_*` | PML 厚度/强度 | 只在 PML 路线生效 | 厚度与 alpha 都需收敛诊断 |

## 直接求解配置

| profile | 真实含义 | 何时用 |
|---|---|---|
| `default` | PETSc LU；MPI 时选择可用 MUMPS | 普通 direct 基线 |
| `mumps_ooc` | MUMPS 直接 LU，因子文件可落盘 | 内存压力诊断；I/O 可能增加 |
| `mumps_blr` | MUMPS BLR 压缩直接分解，阈值 `1e-5` | 实验性 direct fallback；不是迭代器 |

`petsc_extra_options` 能覆盖 profile 默认值，覆盖后结果不再自动继承原 profile 的资格。`matrix_diagnostics_assemble_only=True` 会跳过求解，只测装配资源；不能把它写成“求解成功”。

## 输出参数

`unique_output=True` 每次创建时间戳目录；`results_root=None` 保持普通 `results/`。benchmark 脚本才显式改到 `benchmarks/artifacts/`。参数改动后的资格边界见 [`../reference/current_version_boundaries.md`](../reference/current_version_boundaries.md)。
