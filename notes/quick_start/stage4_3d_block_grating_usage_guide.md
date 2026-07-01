# Stage 4 真实 3D 周期矩形柱使用指南

## 2026-07-01 更新：矩阵/求解器诊断命令

如果你怀疑内存瓶颈来自矩阵结构，而不是单纯自由度数，可以先跑较粗网格诊断：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --matrix-diagnostics-assemble-unconstrained \
  -ksp_view -log_view
```

MUMPS out-of-core 测试：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile mumps_ooc \
  -ksp_view -log_view
```

尺度扫描 CSV：

```bash
python3 -m src.studies.run_3d_matrix_scale \
  --mesh-sizes 20 15 12 10 8 \
  --mpi-procs 2 \
  --stage-case stage4_block_grating \
  --nedelec-degree 1 \
  --stage4-dtn-order-policy zero_order \
  --petsc-direct-solver-profile default
```

详细字段说明见：

```text
notes/test/3d_matrix_solver_diagnostics.md
```

## 2026-07-01 更新：Stage 4B 真实矩形柱已支持 p=2 Floquet

现在 `stage4_block_grating` 可以直接使用二阶 N1curl：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 10 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto \
  --stage4-dtn-order-policy zero_order \
  --n-substrate 1.45 \
  --n-grating 2.0 \
  --diffraction-zero-order-only
```

如果要走正式多衍射级 DtN 主线，把 `zero_order` 换成 `auto_propagating`：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 20 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto \
  --stage4-dtn-order-policy auto_propagating \
  --n-substrate 1.45 \
  --n-grating 2.0 \
  --no-diffraction-zero-order-only
```

本轮 h20/p2/MPI4 已完成 `auto_propagating` smoke，1068 个 DtN auxiliary modes 可以完成组装和求解。不过 h20 对 `lambda0=13.5 nm` 仍很粗，只能说明流程可运行，不能作为最终物理 R/T。

为了确认 grating 几何和材料 tag 没有引入假散射，可以先跑 zero-contrast：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 10 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto \
  --stage4-dtn-order-policy zero_order \
  --n-substrate 1.0 \
  --n-grating 1.0 \
  --diffraction-zero-order-only
```

该结果应与同参数 `stage4_flat_layer_sanity` 一致。当前 h10/p2/MPI4 的对照值为：

```text
Stage4A flat:       R/T = 1.411951e-01 / 8.588049e-01
Stage4B zero block: R/T = 1.411951e-01 / 8.588049e-01
```

这表示 Stage4B p=2 路径一致；但 EUV h10 的 flat-layer 物理值还没收敛，不应把这组 R/T 当作最终 benchmark。

## 2026-06-30 更新：Stage 4A flat-layer sanity 支持 p=2 Floquet

如果只想验证二阶 N1curl Floquet 与 Stage 4 DtN flat layer 是否能组合运行，用 Stage 4A：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 10 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto

mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 10 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

当前限制：

```text
Stage 4A flat-layer sanity: p=2 已开放
Stage 4B block grating: p=2 暂未开放，仍使用 p=1
p>=3: 暂未实现
```

注意：Stage 4A 是无光栅平层 sanity，用来检查 p=2 Floquet 和 DtN 端口组合；它不代表真实 block grating 的 R/T 已经可信。

## 2026-06-26 更新：h=2 nm + MPI 的 fitted hexa 网格报错已修复

如果你设置：

```text
mesh_target_size = 2
mesh_spacing_mode = "auto"
```

对于当前 100 x 100 nm 周期、50 x 50 x 50 nm 方块案例，光栅边界在 25/75 nm。因为 25/75 不能被 2 nm 的 uniform grid 对齐，代码会自动切到：

```text
mesh_spacing_mode_resolved = boundary_fitted
mesh_cells_resolved = (51, 51, 75)
```

上一版在 MPI 下可能在 `dolfinx.mesh.create_mesh` 报：

```text
RuntimeError: Adding boundary vertices in ghost cells not allowed.
```

现在已经修复：custom tensor-product hexa builder 会让每个 rank 只提交自己的 cell 分片，不再把整张全局 cells 复制给每个 rank。

已验证：

```text
mpiexec -n 8: h=2 只建网格，通过
mpiexec -n 8: h=2 网格 + Nedelec + Floquet MPC，通过
Floquet constraints = 15477
max edge midpoint pairing error = 0
```

注意：这只说明 h=2 的前处理网格和 Floquet 约束已经可以并行建立。完整 direct LU 求解仍然可能很慢或占内存较大；如果后续卡住，需要看日志停在：

```text
mesh_build / floquet_constraint_setup_outer
```

还是停在：

```text
stage4_dtn_port_assembly_and_solve
```

这两类问题含义不同。

## 2026-06-26 更新：hexa 网格自动贴边与局部加密怎么用

Stage 4 现在不再要求所有结构尺寸都能被一个全局 uniform `mesh_target_size` 整除。推荐保持：

```text
mesh_cell_type = "auto"
mesh_spacing_mode = "auto"
```

这样运行时会自动判断：

```text
uniform_strict:
  当光栅 x/y/z 面、空气/基底界面、PML/端口面都已经在 uniform grid 上时使用。

boundary_fitted:
  当 target size 不能整除这些材料面时自动使用。
  代码会先插入必须对齐的几何平面，再在每个区间内按 target size 等分。

local_refined:
  需要你显式指定。
  光栅和界面附近使用 mesh_refined_size，远处使用 mesh_target_size。
```

命令行示例：

```bash
# 非整除 target size：自动生成贴边非均匀 hexa 网格
python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 30 \
  --mesh-spacing-mode auto \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy zero_order \
  --diffraction-zero-order-only

# 几何驱动局部加密：光栅附近 2.5 nm，远处 10 nm
python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 10 \
  --mesh-spacing-mode local_refined \
  --mesh-refined-size 2.5 \
  --mesh-refinement-radius 5 \
  --stage4-boundary-model dtn_port
```

在 `src/main.py` 的 `Stage4GratingInputs3D` 中对应修改：

```python
mesh_target_size = 10.0
mesh_spacing_mode = "local_refined"
mesh_refined_size = 2.5
mesh_refinement_radius = 5.0
```

结果目录里重点看：

```text
mesh_3d_partition_note.txt
run_summary.json:
  mesh_spacing_mode_resolved
  mesh_cells_resolved
  mesh_axis_cell_stats
  mesh_material_plane_alignment
  mesh_local_refinement_regions
```

注意：这里的 `local_refined` 是几何驱动的结构化加密，不是基于误差估计的自适应 AMR。它仍然是 tensor-product hexa 网格，所以 x/y 周期面对面的 edge 拓扑可以一一匹配，后续 Floquet 约束仍可用。

## 2026-06-25 更新：h=2.5 并行运行、BUS error 与 Floquet 耗时解释

如果你跑 `h=2.5 nm`、MPI 并行时看到 PETSc `BUS: Bus Error`，优先检查结果目录。若已经写出
`dtn_port_power_metrics_3d.json` 但没有完整 ParaView 文件，通常说明求解已经结束，崩在并行 VTX `.bp`
后处理。当前版本已在 MPI 下默认跳过 3D VTX `.bp`，改写：

```text
fields_3d_for_paraview_parallel.pvd
fields_3d_for_paraview_rank0000.vtu
fields_3d_for_paraview_rank0001.vtu
...
vtx_3d_skipped_mpi.txt
```

ParaView 请打开 `.pvd` 文件。串行运行仍会尝试写 `E_3d_numerical.bp` 和
`H_3d_A_per_m_from_curl.bp`。

Floquet 计时现在拆成：

```text
floquet_build_topological_edge_context
floquet_build_x_constraints
floquet_build_y_constraints
floquet_resolve_corner_master_chains
floquet_build_mpc_arrays
floquet_mpc_finalize
```

`h=2.5` 时 Floquet 需要几秒是正常的：周期边界 edge 数量从 h=5 的约 2470 个增加到 h=2.5 的约
9740 个。新增的 `topological_edge_context` 才是主要耗时项，DtN 边界不会反过来影响 Floquet 约束。

已验证案例：

```bash
mpiexec -n 8 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy zero_order \
  --mesh-target-size 2.5 \
  --nedelec-degree 1 \
  --visualization-degree 3 \
  --unique-output
```

结果：

```text
results/3D_stage4_block_grating_normal_p1_h2p5_np8_20260625_092003
R/T/R+T = 0.3189887 / 0.6810113 / 1.0000000
case_status = completed
vtx_3d_output_status = skipped_mpi
```

`h=10 nm` 对 `lambda0=13.5 nm` 太粗，只能看程序是否跑通，不能用来判断端口物理误差。

## 2026-06-25 更新：如何解读 DtN 与 boundary setup 耗时

本轮之后，Stage 4 日志中的计时口径拆开了：

```text
field_formulation_setup
  只看场形式、入射/背景场对象等准备。

floquet_constraint_setup_outer
  x/y Floquet MPC 总耗时；更细看：
  floquet_build_x_constraints
  floquet_build_y_constraints
  floquet_resolve_corner_master_chains
  floquet_build_mpc_arrays
  floquet_mpc_finalize

boundary_condition_setup
  只看强边界 dof/BC 对象设置。
  dtn_port 分支不使用 z 向强 Dirichlet，所以这里通常接近 0。

stage4_dtn_port_assembly_and_solve
  包含 FEM 基础矩阵装配、DtN 端口模态装配、增广矩阵 finalize、直接求解和回代。
  继续看 dtn_port_power_metrics_3d.json 才能知道具体慢在哪里。
```

新增的 DtN 细分字段：

```text
stage4_dtn_base_matrix_assembly_seconds
stage4_dtn_incident_source_vector_seconds
stage4_dtn_modal_loop_seconds
stage4_dtn_modal_vector_assembly_seconds
stage4_dtn_augmented_matrix_finalize_seconds
stage4_dtn_linear_solve_seconds
stage4_dtn_unique_surface_orders
stage4_dtn_component_vector_assemblies
stage4_dtn_component_vector_cache_hits
```

本轮 h=5 多模态实测：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy auto_propagating \
  --mesh-target-size 5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --unique-output
```

结果：

```text
results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_074047
DtN modes = 1068
stage4_dtn_port_assembly_and_solve = 12.210 s
stage4_dtn_modal_loop_seconds = 2.431 s
elapsed = 15.637 s
R/T/R+T = 0.366105 / 0.633895 / 1.000000
```

注意：h=2.5 的 flat sanity 中 `stage4_dtn_port_assembly_and_solve = 233.600 s`，但其中 `stage4_dtn_linear_solve_seconds = 222.650 s`，说明慢在直接求解器，不是端口模态装配。

## 2026-06-25 更新：dtn_port 已实跑通过，推荐作为 Stage 4 主线

当前可信 R/T 主线：

```text
stage4_boundary_model = "dtn_port"
stage4_dtn_order_policy = "auto_propagating"
stage4_dtn_assembly = "auxiliary"
use_pml = False
```

已验证结果：

```text
flat, n_sub=1.0, h=2.5:
  R/T/R+T = 6.04e-04 / 9.993956e-01 / 1.000000

flat, n_sub=1.45, h=2.5:
  R/T/R+T = 2.061e-02 / 9.793854e-01 / 1.000000

block grating, h=5, auto_propagating:
  DtN modes = 1068
  R/T/R+T = 3.661053e-01 / 6.338947e-01 / 1.000000
```

正式结果请看：

```text
dtn_port_power_metrics_3d.json
dtn_port_diffraction_orders_3d.json
dtn_port_diffraction_orders_3d.csv
dtn_auxiliary_amplitudes_3d.json
```

`h=5` 的真实 grating 结果是 smoke，不是最终 COMSOL 对标精度；如果要继续提高精度，下一步应跑 `h=2.5 + auto_propagating`，但预计耗时会明显高于 h=5。

## 2026-06-25 更新：新增 3D DtN 总场端口主线

当前 Stage 4 的新推荐主线是：

```text
stage4_boundary_model = "dtn_port"
stage4_dtn_order_policy = "auto_propagating"
stage4_dtn_assembly = "auxiliary"
use_pml = False
```

含义：

```text
1. 未知量改为 E_total，不再用 Stage 4 PML 散射场作为可信主线。
2. 上端口注入向下入射的 Floquet 基模。
3. 上下端口用同一套 3D Fourier 模态目录吸收全部传播出射衍射级。
4. 正式 R/T 来自 dtn_port_power_metrics_3d.json 和 dtn_port_diffraction_orders_3d.csv/json，
   不再依赖内部 probe 平面。
```

最小运行命令：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --stage4-boundary-model dtn_port \
  --mesh-target-size 5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --unique-output

mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --stage4-boundary-model dtn_port \
  --mesh-target-size 5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --unique-output
```

验证顺序：

```text
1. 先跑 stage4_flat_layer_sanity + dtn_port。
   这个案例没有 grating perturbation，必须优先接近 Fresnel 且 R+T≈1。

2. 再跑 n_grating 接近背景的弱扰动 grating。
   如果这里不连续回到 flat-layer，说明 DtN 符号、归一化或材料源项仍有 bug。

3. 最后跑默认 block grating。
   对 lossless 材料，R+T 不应超过 1 加一个很小数值容差；超过时 summary 会标记失败。
```

ParaView 中的新字段：

```text
E_total_V_per_m_*          求解得到的总场
E_incident_port_V_per_m_*  上端口入射基模诊断场
```

旧的 `stage4_boundary_model="pml"` 分支仍保留，用于查看历史 PML 散射场和内部 probe 诊断；但它不是当前可信 R/T 主线。

## 2026-06-25 更新：R/T 结果现在看 E/H Fourier 字段

最新代码中，Stage 4 官方 R/T 使用：

```text
diffraction_total_power_source = "eh_fourier_orders"
R_total_from_eh_fourier
T_total_from_eh_fourier
R_plus_T_from_eh_fourier
```

旧的 E-only 字段仍会输出，但只作为诊断：

```text
R_total_from_e_fourier
T_total_from_e_fourier
R_plus_T_from_e_fourier
```

原因是 E-only 不能区分同一个 `(m,n)` 级次在 probe 面上的上行/下行波；有限 PML 有回波时，它会把透射率抬得过高。

当前目标案例的最新正式重跑：

```text
results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260625_020717

E/H Fourier:
  R/T/R+T = 0.062028 / 1.922722 / 1.984750

E-only diagnostic:
  R+T = 2.602034

sampled net-flux diagnostic:
  R+T = 1.882674
```

结论：后处理已改进，但这个 h=2.5、p1、13.5 nm EUV block grating 仍不可信。运行结果中只要看到：

```text
case_status = failed_stage4_energy_balance
official_result = false
diagnostic_only = true
```

就不要把 ParaView 场分布或 R/T 当作可对标 COMSOL 的正式结果。

## 2026-06-24 更新：h=2.5 nm 运行状态与当前风险

当前 h=2.5 nm、p1、np=16 可以完整跑完，但能量验收未通过：

```text
natural:
  results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_124802
  R/T/R+T = 0.068117 / 2.534148 / 2.602265

zero_tangential:
  results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_133711
  R/T/R+T = 0.069171 / 2.535508 / 2.604678
```

两个外边界选项给出的结果几乎相同，所以目前不要把问题归因成“natural 外边界没有吸收”。当前更可靠的结论是：

```text
1. Floquet 约束和 direct LU 都跑完了；
2. R+T 严重大于 1，结果只能用于诊断；
3. 后续需要继续检查 Stage 4 弱式、PML 张量、背景场源项和 probe/modal 分解的一致性。
```

注意 h=2.5 nm 仍不满足光栅材料内波长 `lambda0 / n_grating / 6 = 1.125 nm` 的保守经验网格。因此即便模型修好，想和 COMSOL 对齐，仍需要更细网格或更高阶单元；这会明显增加 direct LU 内存压力。

## 2026-06-24 更新：当前推荐命令和 R/T 判断口径

当前 3D 代码已经移除 `--solver-profile`。Stage 4 运行命令示例：

```bash
mpiexec -n 8 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 2.5 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --stage4-pml-outer-bc natural \
  --diffraction-sample-count-x 64 \
  --diffraction-sample-count-y 64 \
  --unique-output
```

13.5 nm、100 nm 周期会打开很多传播衍射级。正式 R/T 不应手动截断到 `m,n<=2`；即使命令或 `main.py` 里给了 `diffraction_order_max_m/n=2`，代码也会自动扩展到所有传播级，并在 `power_metrics_3d.json` 里写出：

```text
diffraction_order_max_m_requested
diffraction_order_max_m_resolved
diffraction_order_max_n_requested
diffraction_order_max_n_resolved
```

后处理口径已经改为：

```text
E_probe = E_scat_numerical_probe + E_bg_exact_probe
```

不要再用修复前的 h=2.5 结果判断最终 R/T。最新 flat-layer sanity 已通过，真实 block-grating 需要用修复后的 h=2.5 或更细网格重跑；若 `R+T > 1`，程序会继续标记为 `failed_stage4_energy_balance`，该结果只能用于诊断。

## 2026-06-24 更新：13.5 nm 小周期立方体默认案例

当前 Stage 4 默认案例已经切到：

```text
lambda0 = 13.5 nm
period_x = period_y = 100 nm
block = 50 x 50 x 50 nm
substrate_thickness = 50 nm
air_height = 100 nm
physical domain = 100 x 100 x 150 nm
pml_top = pml_bottom = 25 nm
mesh_target_size = 5 nm
```

PML 外边界默认：

```text
stage4_pml_outer_bc = "natural"
```

也就是 PML 最外层不再强行设为零切向 `E_scat`。如果要恢复旧诊断行为，可以命令行加：

```bash
--stage4-pml-outer-bc zero_tangential
```

衍射级 probe 面默认也从 95% 改成 75%：

```text
top_probe_z = 0.75 * physical_z_max = 75 nm
bottom_probe_z = 0.75 * physical_z_min = -37.5 nm
```

这样 top probe 离 PML 入口 25 nm，离方块顶面 25 nm；bottom probe 离下方 PML 入口 12.5 nm。summary 会记录这些距离：

```text
diffraction_top_probe_distance_to_pml_start
diffraction_bottom_probe_distance_to_pml_start
diffraction_top_probe_distance_above_block
diffraction_bottom_probe_distance_below_interface
```

h25/p1 smoke 对比：

```text
natural:
  R/T/R+T = 0.045960 / 0.278516 / 0.324476
  max |E_scat| in PML = 3.12e-2
  linear_problem_setup ≈ 94 s

zero_tangential:
  R/T/R+T = 0.045685 / 0.278052 / 0.323737
  max |E_scat| in PML = 7.02e-4
  linear_problem_setup ≈ 0.004 s
```

结论：正式 E-Fourier R/T 对这个粗网格 smoke 变化很小，但 natural 更容易暴露 PML 截断处的残余场；代价是当前 `dolfinx_mpc + natural z outer boundary + direct` 的 setup 明显更慢。h25 只是流程验证，不是 13.5 nm 的精度网格。

## 2026-06-24 更新：Stage 4 代码入口已单独拆出

研究真实 3D 光栅时，优先只看这一条路径：

```text
src/main.py
  ACTIVE_3D_INPUT_GROUP = "stage4_grating"
  Stage4GratingInputs3D(...)

src/runners/run_3d_airbox.py
  _stage_defaults("stage4_block_grating")
  _run_stage_config(...)

src/solvers/solve_maxwell_3d_stage_4_grating.py
  run_stage4_grating_3d_case(...)

src/solvers/solve_maxwell_3d_common.py
  stage4_layered_background_field(...)
  _build_variational_forms(...)
  _stage4_lossless_energy_balance_check(...)

src/postprocessing/diffraction_3d.py
  compute_diffraction_orders_3d(...)
```

`src/main.py` 中 Stage 1/2 的 dataclass 不会影响 Stage 4。只要 `ACTIVE_3D_INPUT_GROUP` 保持为 `"stage4_grating"`，你只需要改 `Stage4GratingInputs3D` 这一块。

## 2026-06-24 更新：MPI 运行已恢复为可信路径

当前 Stage 4 `h50/p1` 已完成串行与 MPI 2/4/8/12/16 对比，正式 E-Fourier 功率结果一致：

```text
R_total = 0.001666
T_total = 0.951074
R_plus_T = 0.952741
max |E_tot| = 1.911019 V/m
```

推荐串行命令：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

推荐并行命令，例如 `np=4`：

```bash
mpiexec -n 4 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

阅读结果时重点看：

```text
case_status = completed
stage4_energy_balance_pass = true
R_total / T_total / R_plus_T
max_abs_E
linear_system_solution_norm
linear_system_relative_residual
stage4_outer_pml_zero_tangential_e_bc = true
floquet_num_global_ghost_slave_constraints
```

注意：

```text
1. Stage 4 PML 吸收的是散射场 E_sca，外边界现在对 E_sca 施加零切向边界。
2. E_tot = E_b + E_sca；ParaView 中看总电场用 E_tot_V_per_m_abs。
3. sampled net-flux R+T 仍是诊断字段；正式 R/T 使用 diffraction_total_power_source = e_fourier_orders。
4. 当前正式 R+T 小于 1，但 h50/p1 仍是粗网格，A_balance 主要反映离散和后处理误差，不应直接解释成真实吸收。
```

## 2026-06-24 更新：衍射级采样面改为物理层 95% 位置

Stage 4 衍射级后处理现在默认在物理区域上下均匀层的 95% 位置采样：

```text
top_probe_z    = interface_z + 0.95 * (physical_z_max - interface_z)
bottom_probe_z = interface_z + 0.95 * (physical_z_min - interface_z)
```

对当前 600/500 nm COMSOL 对比案例，`interface_z=0`，所以就是：

```text
top_probe_z    = 0.95 * 850  = 807.5 nm
bottom_probe_z = 0.95 * -350 = -332.5 nm
```

命令行里仍然可以手动覆盖：

```bash
--diffraction-top-probe-z 807.5 --diffraction-bottom-probe-z -332.5
```

summary 里会记录：

```text
diffraction_top_probe_z
diffraction_bottom_probe_z
diffraction_probe_position_fraction_from_interface_to_physical_boundary
diffraction_sample_count_x / diffraction_sample_count_y
diffraction_sample_point_count_per_plane
diffraction_min_sample_count_x_for_fit_orders
diffraction_min_sample_count_y_for_fit_orders
```

如果采样点数低于当前拟合级次所需的最低 Fourier 点数，程序会直接报错，而不是继续给出不可靠的衍射级功率。

## 2026-06-23 更新：600/500 nm COMSOL 对比单胞的推荐用法

当前 Stage 4 默认参数已经切换到这组 COMSOL 对比案例：

```text
period_x = 600 nm
period_y = 500 nm
grating_width_x = 300 nm
grating_width_y = 200 nm
grating_height = 150 nm
air_height = 850 nm
substrate_thickness = 350 nm
pml_top_thickness = 250 nm
pml_bottom_thickness = 250 nm
polarization_kind = s
incident_phi_deg = 0 deg   # normal incidence 下 S 偏振对应 Ey
diffraction_zero_order_only = False
```

推荐先跑 h50/p1：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

斜入射检查：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --incident-theta-deg 10 \
  --incident-phi-deg 0 \
  --polarization-kind s \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

如果要从命令行临时改几何，可以直接加：

```bash
--period-x 600 --period-y 500 \
--air-height 850 --substrate-thickness 350 \
--grating-width-x 300 --grating-width-y 200 --grating-height 150 \
--pml-top-thickness 250 --pml-bottom-thickness 250
```

现在 summary 中正式看：

```text
diffraction_total_power_source = e_fourier_orders
R_total / T_total / R_plus_T
R_total_from_e_fourier / T_total_from_e_fourier / R_plus_T_from_e_fourier
```

旧的：

```text
R_total_from_modal_orders / T_total_from_modal_orders
```

只作为诊断。h50/p1 中它可能因为 FE-curl 的 H 后处理高阶误差而给出 `R+T>1`，不要把它当作正式功率。

COMSOL-like 三图输出：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.tools.render_stage4_comsol_views \
  results/3D_stage4_block_grating_normal_p1_h50p0_YYYYMMDD_HHMMSS/fields_3d_for_paraview.vtu
```

它会生成：

```text
stage4_comsol_like_outer_surface.png
stage4_comsol_like_slice_yz_x_mid.png
stage4_comsol_like_slice_xz_y_mid.png
stage4_comsol_like_views.json
```

每张图单独取颜色范围，适合和 COMSOL 的外表面、y-z 切面、x-z 切面对比形态。

## 2026-06-23 更新：ParaView 变量已精简

当前 3D ParaView 文件不再输出一大串重复/派生数组。打开 `fields_3d_for_paraview.vtu` 或 MPI 的 `fields_3d_for_paraview_parallel.pvd` 后，优先看：

```text
E_tot_V_per_m_abs       # 总电场模，默认最适合对照 COMSOL 电场模
E_tot_V_per_m_real      # 总电场实部 vector，ParaView 里再选 X/Y/Z component
E_tot_V_per_m_imag      # 总电场虚部 vector，ParaView 里再选 X/Y/Z component
E_sca_V_per_m_abs       # 散射场模
E_b_V_per_m_abs         # 分层背景场模
H_A_per_m_abs           # 磁场模
domain_tag              # 用来筛选 air/substrate/grating/PML
```

已经删除：

```text
E_V_per_m_*                         # 和 E_tot 重复
*_Ex_real / *_Ey_real / *_Ez_real   # 改为 vector component 选择
*_physical_* / *_pml_*              # 这类筛选场不再写入 ParaView
is_physical_z_region / is_pml_z_region
```

说明：`E_tot_V_per_m_real` 和 `E_tot_V_per_m_imag` 是三分量 vector。你在 ParaView 里先选这个量，再在后面的 component 里选 `X/Y/Z`，就能看 Ex/Ey/Ez。

## 2026-06-23 更新：h50/p1 当前推荐运行方式与查看口径

本轮修正后，默认 Stage 4 block grating 在 h50/p1 下已经可以作为流程和场分布诊断算例运行：

```bash
python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

MPI2 版本：

```bash
mpiexec -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct \
  --stage4-boundary-model pml
```

最新实跑：

```text
serial:
  results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409
  R/T = 6.088269e-03 / 9.765458e-01
  R+T = 9.826341e-01

MPI2:
  results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_084643
  R/T = 7.279671e-03 / 9.069706e-01
  R+T = 9.142503e-01
```

ParaView 中优先看这个数组来对照 COMSOL 电场模截图：

```text
E_tot_physical_abs_V_per_m
```

它只看物理 z 区域，避免 PML 显示干扰。最新切片预览图在：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409/stage4_Etot_physical_slices.png
```

重要说明：

```text
1. Stage 4 正式 PML 分支现在是 2D-like natural boundary：
   strong_z_boundary_dirichlet_enabled=false。
2. diffraction fitting 会额外加入邻近 evanescent 级次做拟合，
   但只把传播级次计入 R/T。
3. 2.5D y-extruded 对照的 Ey 已接近 0，但 R/T 仍未和旧 2D TM 完全一致。
   因此 h50/p1 的真实 3D 结果仍不建议做最终定量 benchmark。
```

下面更早的条目是历史排查记录；如果和本节冲突，以本节为准。

## 2026-06-23 更新：当前 Stage 4 只能作为诊断输出

最新检查结果：

```text
stage4_flat_layer_sanity h50/p1/MPI2:
  R/T = 3.373594e-02 / 9.662641e-01
  R+T = 1.000000e+00

stage4_block_grating h50/p1/MPI2:
  R/T = 9.380284e-03 / 1.075087e+00
  R+T = 1.084467e+00
  official_result = False
  case_status = failed_stage4_energy_balance

stage4_2p5d_compare h50/p1:
  serial 3D y-extruded: R+T = 1.117862
  MPI2 3D y-extruded: R+T = 1.220574
```

因此现在不要把真实 grating 的 R/T 当作物理结果。推荐先跑：

```bash
python3 -m src.test.stage4_2p5d_compare --mesh-target-size 50 --nedelec-degree 1
mpiexec -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare --mesh-target-size 50 --nedelec-degree 1
```

ParaView 中优先看：

```text
E_tot_physical_abs_V_per_m
E_sca_physical_abs_V_per_m
E_b_physical_abs_V_per_m
domain_tag
is_physical_z_region
is_pml_z_region
```

PML 外边界现在对散射场施加零切向 E；注意 Nedelec 强边界控制的是切向分量，不是把 `|E|` 的三个分量全部钉成 0。判断 PML 吸收优先看 `E_sca_pml_abs_V_per_m` 和 summary 里的 `pml_scattered_decay_ratio_top/bottom`。

## 2026-06-23 更新：当前 Stage 4 不再标记为可信结果

当前 Stage 4 block grating 还能跑完并输出 ParaView，但 lossless 情况下 `R+T > 1`，因此程序现在会把它标记为：

```text
official_result = False
diagnostic_only = True
case_status = failed_stage4_energy_balance
```

你现在可以用它看网格、tag、Floquet 约束、PML 衰减和场分量诊断，但不要把 `R/T` 当作真实物理结果。

新增 2.5D 对照命令：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare \
  --mesh-target-size 50 \
  --nedelec-degree 1
```

这个命令会跑：

```text
reference_2d_tm       # 原 2D TM scattered solver
extruded_3d_stage4    # y 方向完全拉伸的 3D Stage 4
```

当前 h50/p1 诊断显示 3D y-extruded case 与 2D 不一致，并出现明显 `Ey` 分量。这说明下一步应该先修 2.5D 对照，而不是继续相信真实 3D block 的 R/T。

## 2026-06-23 更新：ParaView 中如何避免被 PML 背景场误导

Stage 4 的 `E_b` 是分层 Fresnel 背景场。它会在 PML 中做复坐标延拓，所以 PML 里的 `E_b` 或 `E_tot` 可能很大；这不是“散射场 PML 没有吸收”。看结构附近的真实物理场时，优先用新增的物理区数组：

```text
E_tot_physical_abs_V_per_m
E_sca_physical_abs_V_per_m
E_b_physical_abs_V_per_m
```

看 PML 是否吸收散射场时，优先用：

```text
E_sca_pml_abs_V_per_m
run_summary.json:
  pml_metric_field = E_scat
  pml_scattered_decay_ratio_top
  pml_scattered_decay_ratio_bottom
```

辅助筛选数组：

```text
domain_tag
is_physical_z_region
is_pml_z_region
```

最新 h50/p1/MPI2 验证中，flat-layer sanity 的 calibrated modal R/T 精确回到 Fresnel：

```text
R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.000000e+00
```

默认 block grating 的 calibrated modal R+T 仍为 `1.084467`，说明 h50 粗网格结果目前只能作为 smoke/流程验证，不能当最终定量 benchmark。下一个对齐细化网格是 `h=25 nm`，直接法可能会明显增加内存。

`R_total_from_net_flux/T_total_from_net_flux` 是 diagnostic-only：它用采样点上的 FE-curl 重建 H 做直接 Poynting 通量，flat sanity 中也不如 calibrated modal amplitudes 稳定。正式报告仍看 `R_total/T_total/R_plus_T`。

## 2026-06-23 更新：PML 和 E_exact 的正确查看方式

Stage 4 真实 grating 没有解析精确解，所以现在不再输出：

```text
E_exact_abs_V_per_m
E_error_abs_V_per_m
H_exact_abs_A_per_m
H_error_abs_A_per_m
```

ParaView 里应该按 2D scattered-field 的口径看三套场：

```text
E_tot_V_per_m_*   # 总场 E_total = E_b + E_sca，只建议在物理区解释
E_b_V_per_m_*     # 分层背景场 E_bg，不是精确解
E_sca_V_per_m_*   # 散射场，判断 PML 吸收时优先看它
```

PML 是人工层。Stage 4 的 PML 目标是吸收 `E_sca`，不是让 `E_b` 或 `E_tot` 在 PML 中为零。背景场在 PML 中经过复坐标延拓，可能有明显模值；这不代表 PML 没吸收散射场。

因此检查 PML 时优先看：

```text
run_summary.json:
  pml_metric_field = E_scat
  pml_scattered_decay_ratio_top
  pml_scattered_decay_ratio_bottom

ParaView:
  E_sca_V_per_m_abs
  domain_tag
```

## 2026-06-23 更新：main.py 配置和 ParaView 场变量

如果从 `src/main.py` 直接运行 Stage 4，推荐先用：

```text
STAGE_CASE_3D = "stage4_block_grating"
MESH_TARGET_SIZE_3D = 50.0
PML_TOP_THICKNESS_3D = 250.0
PML_BOTTOM_THICKNESS_3D = 250.0
PERIOD_X_3D = 350.0
PERIOD_Y_3D = 300.0
GRATING_WIDTH_X_3D = 150.0
GRATING_WIDTH_Y_3D = 100.0
GRATING_HEIGHT_3D = 150.0
```

不要直接把 `MESH_TARGET_SIZE_3D` 改成 `30.0`。原因是 Stage 4 当前使用均匀 hexa 网格，并且要求材料界面和 block 边界必须落在网格面上。默认几何下：

```text
h = 50 nm  对齐
h = 25 nm  对齐
h = 30 nm  不对齐，会报错
```

这是故意的保护，不是程序崩溃。它防止 block 边界被 midpoint tag 静默标错。

旧的 `E_V_per_m_*` 仍然保留，含义等同于 `E_tot_V_per_m_*`。

## 2026-06-23 更新：第一版 Stage 4 已接入

这一版先实现一个固定、可验证的真实 3D 周期结构：

```text
上方空气层 + top PML
中心矩形柱 grating
下方 substrate + bottom PML
x/y 双周期 Floquet
未知量为 E_scat，输出 E_total = E_bg + E_scat
```

默认 benchmark 参数：

```text
lambda0 = 633 nm
period_x / period_y = 350 / 300 nm
n_substrate = 1.45
n_grating = 2.0
block size = 150 x 100 x 150 nm
block bottom = z=0
mesh_target_size = 50 nm
nedelec_degree = 1
pml_top/bottom = 250 nm
pml_alpha = 5
```

第一版只支持：

```text
hexahedron mesh
degree=1 N1curl
topological_edges Floquet constraints
rectangular_block_grating
layered Fresnel background
```

如果 block 边界或材料界面没有落在 hexa 网格面上，程序会直接报错，不会用 midpoint 近似悄悄标错材料。

## 推荐运行命令

默认 normal incidence block grating：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

平界面 sanity，不放 grating/source，用来检查 diffraction 后处理能否回到 Fresnel 0 级：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

小角度 oblique smoke：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --incident-theta-deg 10 \
  --incident-phi-deg 90 \
  --polarization-kind s \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

## 输出文件

每次运行会在 `results/3D_stage4_...` 下写出：

```text
run_summary.json
run_log.txt
all_run_summary.json
fields_3d_for_paraview_parallel.pvd
diffraction_orders_3d.json
diffraction_orders_3d.csv
power_metrics_3d.json
```

ParaView 打开：

```text
fields_3d_for_paraview_parallel.pvd
```

重点看：

```text
domain_tag
E_V_per_m_real / E_V_per_m_imag / E_V_per_m_abs
E_tot_V_per_m_real / E_tot_V_per_m_imag / E_tot_V_per_m_abs
E_b_V_per_m_real / E_b_V_per_m_imag / E_b_V_per_m_abs
E_sca_V_per_m_real / E_sca_V_per_m_imag / E_sca_V_per_m_abs
H_A_per_m_real / H_A_per_m_imag / H_A_per_m_abs
```

## summary 里优先检查的字段

```text
field_formulation = layered_scattered
background_added_to_solution = true
rhs_source_region = physical_grating
rhs_source_tag_volumes.grating
rhs_source_norm
E_bg_norm / E_sca_norm / E_total_norm
floquet_num_constraints
floquet_estimated_constraint_memory_mb
R_total / T_total / R_plus_T / A_balance
diffraction_top_fit_residual
diffraction_bottom_fit_residual
diffraction_top_fe_response_condition
diffraction_bottom_fe_response_condition
```

当前第一版 h50/p1 是 smoke benchmark，不是最终高精度结果。`stage4_flat_layer_sanity` 已经回到 Fresnel 解析 R/T；`stage4_block_grating` 的 `R+T` 仍有约 8% 粗网格/边界误差，需要后续继续做 PML、网格和 modal port 收敛。
