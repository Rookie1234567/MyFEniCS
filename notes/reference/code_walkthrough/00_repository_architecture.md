# 仓库架构与文件责任

## 顶层

| 路径 | 责任 | 提交策略 |
|---|---|---|
| `src/` | 物理、离散、求解、后处理、测试 | 提交 |
| `benchmarks/` | 冻结案例、脚本、轻量记录、Gate | records 提交，artifacts 忽略 |
| `docs/` | Task/Outcome/Review 和项目状态 | 提交 |
| `notes/` | 理论、快速开始、代码解释、历史诊断 | 提交 |
| `results/` | 普通案例完整输出和 Task28 worktree | 忽略 |
| `papers/` | 用户提供论文 | 只按仓库策略处理 |
| `docker/` | 环境构建与恢复 | 提交文本配置 |

## `src/common`

| 文件 | 主要对象 | 状态 |
|---|---|---|
| `config.py` | `SimulationConfig`, 2D 单位/几何/材料/相位 | production |
| `config_3d.py` | `SimulationConfig3D`, stage/mesh/solver 派生量 | production |
| `materials.py` | 2D 目标/背景 `epsilon_r` 函数 | production |
| `analytic_fields_3d.py` | Fresnel、解析 E/H、PML 坐标参考 | validation support |
| `modes_3d.py` | order、port mode、极化、功率 | production |
| `pml.py`, `pml_3d.py` | 2D/3D 坐标变换张量 | production |
| `units.py` | c、真空阻抗 | production |
| `output_paths.py` | 时间戳目录 | production |

## geometry 与 constraints

| 文件 | 责任 |
|---|---|
| `geometry/mesh_builder.py` | 2D Gmsh 结构网格、材料矩形精确 tag |
| `geometry/mesh_builder_3d.py` | 3D tet/hex、边界贴合轴计划、材料面检查、MPI 分区 |
| `constraints/floquet_constraint.py` | 2D TM Nedelec manual Floquet |
| `constraints/floquet_scalar_constraint.py` | 2D TE 标量 Floquet |
| `constraints/floquet_3d.py` | 3D p1 边/p2 trace 双 Floquet MPC |

## runners 与 solvers

| 文件组 | 责任 | 状态 |
|---|---|---|
| `main.py` | PyCharm 命名 preset 门面 | public |
| `runners/run_cases.py` | 2D CLI、组合展开、结果根目录 | public |
| `runners/run_3d_cases.py` | 3D 单 stage dispatch、PETSc option parse | public |
| `solve_vector_maxwell.py` | 2D TM scattered | production |
| `solve_te_maxwell.py` | 2D TE scattered/port | production |
| `solve_port_maxwell.py` | 2D TM Robin/DtN total field | production |
| `solve_maxwell_3d_stage_*.py` | stage guard 与共享 flow 入口 | production |
| `common_3d_forms/fields/solve/postprocess/utils.py` | 共享 3D 分层实现 | production internal |
| `common_3d_case_flow.py` | 3D direct 主生命周期 | production internal |
| `dtn_port_3d.py` | 3D DtN 增广系统/幅值/功率 | production internal |
| `condensed_dtn.py` | 精确 Schur 与 matrix-free action | production |
| `physical_slab_two_level.py` | MPI owner slab + sparse two-level PC | qualified benchmark path |
| `stage4_runtime.py` | target Stage4 只装配 facade | qualified benchmark path |

`solve_airbox_maxwell_3d_old.py`、`solve_maxwell_3d_common_old.py`、`solve_maxwell_3d_stage_2_no_grating_old.py`、`solve_maxwell_3d_stage_4_grating_old.py` 与 `runners/run_3d_airbox_old.py` 是 deprecated history，不应被新入口 import。

## postprocessing

| 文件 | 责任 |
|---|---|
| `postprocess.py` | 2D 场/网格输出 |
| `power_metrics.py` | 2D modal/probe/Poynting/RTA/体吸收 |
| `near_field_2d.py` | 固定近场区域和积分 |
| `postprocess_3d.py` | owned-cell MPI 场输出、误差/分量指标 |
| `diffraction_3d.py` | Fourier/EH/probe diagnostic |
| `rta_3d.py` | official 体吸收与功率汇总 |
| `flat_layer_reference_3d.py` | Fresnel/有限吸收平层参考 |

## studies、tools、tests

`studies/` 是显式扫描/资源研究，不被普通 runner 自动调用。`tools/` 是环境检查、PML 诊断和渲染。`test/test_00...27` 按基础物理、3D 阶段、DtN/凝聚、PC、仓库/benchmark/文档契约递进；`diagnose_*` 和 `stage4_2p5d_compare.py` 是人工诊断，不属于自动单测。

## 依赖方向

允许：runner -> common/geometry/constraints/solver -> postprocess。benchmark 可调用稳定 solver facade 和少量登记过的内部函数。禁止：common 反向 import runner；production solver import notes/docs；普通 main 自动启动 benchmark MPI。
