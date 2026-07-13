# 3D 分阶段代码架构

3D 代码按物理复杂度逐级增加机制。每个 stage wrapper 先验证 `cfg.stage_case`，再把明确配方交给共享流程；共享流程不会根据字符串偷偷改换物理问题。

## 1. Stage wrapper 与签名

| Stage | 入口 | 配方与状态 |
|---|---|---|
| 1 | `solve_maxwell_3d_stage_1_airbox::run_stage1_airbox_3d_case(cfg,out_dir)` | 均匀空气、解析场、verified |
| 2A | `solve_maxwell_3d_stage_2a_floquet_airbox::run_stage2a_floquet_airbox_3d_case` | 双 Floquet、test-backed |
| 2B | `solve_maxwell_3d_stage_2b_pml_airbox::run_stage2b_pml_airbox_3d_case` | z-PML、experimental accuracy |
| 2C | `solve_maxwell_3d_stage_2c_fresnel_interface::run_stage2c_fresnel_interface_3d_case` | 平界面/Fresnel、experimental accuracy |
| 4A | `solve_maxwell_3d_stage_4a_flat_layer_sanity::run_stage4a_flat_layer_sanity_3d_case` | 平层 + DtN/RTA sanity |
| 4B | `solve_maxwell_3d_stage_4b_block_grating::run_stage4b_block_grating_3d_case` | 真实 block grating + DtN |

旧的 `*_old.py` 仅用于历史追踪，不是 runner 的规范入口。

## 2. 共享流程签名

```text
common_3d_case_flow::run_prepared_3d_case_flow(
    cfg, out_dir, *, expected_stage_case, field_formulation,
    solve_reference_correction=False,
    solve_incident_scattered=False,
    solve_layered_scattered=False,
    solve_stage4_dtn_port=False,
    apply_strong_boundary_bc=True,
    run_diffraction_postprocess=False,
) -> dict[str, object]
```

这些布尔量由 wrapper 固定，不由用户任意组合。入口先检查 complex scalar、stage 名、PML 厚度、DtN 与 PML 互斥、Floquet 必需条件和 3D auxiliary-only DtN 限制。

## 3. 主调用顺序

```text
validate config and direct profile
-> prepare MUMPS OOC runtime
-> geometry/mesh_builder_3d::build_airbox_mesh_3d
-> common_3d_solve::_create_nedelec_space
-> common_3d_fields 构造 incident/background/reference field
-> common_3d_case_flow::_build_floquet_and_boundary_conditions
-> common_3d_forms::_build_variational_forms
-> standard direct solve 或 dtn_port_3d::solve_stage4_dtn_port_total_field
-> total/scattered/background field reconstruction
-> true residual + matrix/resource summary
-> postprocess_3d::save_airbox_3d_fields
-> diffraction_3d diagnostic + rta_3d volume absorption
-> JSON/CSV/log/progress
-> destroy PETSc/MPC/OOC resources
```

每个计时区间在 communicator 上取最大值；RSS 则按记录约定汇总，避免用单 rank 数冒充总内存。

## 4. 输入和对象规模

`SimulationConfig3D` 在各 rank 上复制，包含 nm 几何、材料、波长、角度、偏振、网格、边界和 solver profile。网格返回 `AirBox3DMesh`：

```text
mesh                 distributed DOLFINx mesh
cell_tags/facet_tags distributed MeshTags
mesh_cells_resolved  (nx,ny,nz)
axis/alignment stats replicated metadata
```

Nedelec 空间 `V` 的全局 DoF 为 `index_map.size_global * index_map_bs`。标准系统尺寸为 `N_fe x N_fe`；Stage4 auxiliary DtN 尺寸为 `(N_fe+N_aux)^2`。target h5 的代表值是 `N_fe=44,698`、`N_aux=80`、增广行数 `44,778`。

## 5. 方程配方

`common_3d_forms::_build_variational_forms` 形成统一 curl-curl 体项：

$$a(E,v)=\int\mu_r^{-1}curlE\cdot\overline{curlv}
-k_0^2\epsilon_rE\cdot\bar v\,dV+a_{boundary}.$$

配方差异来自 RHS 与 total-field 重构：

| 配方 | RHS/求解未知量 | 后处理前重构 |
|---|---|---|
| analytic/reference correction | 解析 reference mismatch | correction + reference |
| incident-scattered | `k0^2(eps-eps_air)E_inc` | `E_scat+E_inc` |
| layered-scattered | `k0^2(eps_true-eps_layered)E_bg` | `E_scat+E_bg` |
| Stage4 DtN total field | top incident traction + outgoing port | FE segment 已是 total field |

Stage4 `A_volume` 一律使用 total field，不能只积分 correction/scattered field。

## 6. 边界组合

`_build_floquet_and_boundary_conditions` 集中决定边界：x/y 周期使用 `DoubleFloquet3DData.mpc`；z 面按 stage 使用强边界、PML 外边界或 DtN。DtN case 要求 `use_floquet_xy=True`、`use_pml=False`，且不再加 z Dirichlet。

把边界决定分散到 wrapper 会产生 overconstraint 或封闭腔，因此共享流程是唯一生命周期 owner。

## 7. PETSc/DOLFINx ownership

- mesh、`V`、FE matrix/vector 和 KSP 按 MPI rank 分布。
- `fem.Function.x` 有 owned 与 ghost entries，求解/回代后需 scatter forward。
- `DoubleFloquet3DData.mpc` 必须存活到 assembly 和 backsubstitution 结束。
- standard `LinearProblem` 管理其 `A,b,x,solver`；DtN 返回显式 `A,b,x,ksp`，由 case flow 在写完诊断后销毁。
- auxiliary amplitudes是小型 replicated NumPy array；3D 增广矩阵中的 auxiliary 行由最后一个 rank 持有。
- rank 0 写 JSON/CSV/主日志；场输出只写各 rank owned cells。

失败路径先把 PETSc reason、matrix stats、timing、RSS 和 OOC 目录状态写入 summary，再释放对象。这样异常不会只留下一个 Python traceback。

## 8. 输出

`run_summary.json` 记录 resolved config、网格/DoF、约束、矩阵、solver、残差、RTA、时间和内存。`progress.jsonl` 在长阶段提供增量状态；`solver_log.txt` 保存可读日志；`power_summary.csv` 只扁平化已计算字段。

场文件包含 complex 分量的 real/imag/abs、材料 tag 和 PVD 聚合。完整结果保留在 `results/` 或 benchmark artifact root，不把大型 VTU 提交 Git。

## 9. 真实案例与 Gate

| Case | 代码路径 | 证据身份 |
|---|---|---|
| 010 | Stage1 | canonical lightweight reference |
| 011 | Stage2A | test-backed smoke |
| 012 | Stage2B | experimental，非精度资格 |
| 013 | Stage2C | experimental，非精度资格 |
| 020 | Stage4A | flat-layer sanity |
| 021 | Stage4B direct | target h5/h3 canonical |
| 031 | Stage4 runtime + iterative | target h5/h3/h2 qualified |

`test_13_3d_stage_entrypoints.py` 检查 wrapper stage guard；完整契约还由 `test_26`、`test_27` 和 benchmark checker 覆盖。

## 10. 限制

共享流程较长，但它承担对象生命周期和失败证据，不能轻率拆散。`stage4_runtime` 目前复用少量下划线 assembly helper，属于有测试保护的内部 API 债务。Stage2B/2C 可运行不等于精度已验证。理论阶梯见 [`../../theory/3d_stages_and_validation_ladder.md`](../../theory/3d_stages_and_validation_ladder.md)。
