# Stage 4 验证报告

## 2026-06-25 更新：MPI VTX BUS error 修复、Floquet context 计时与 h=2.5 block 复核

本轮新增修复和验证：

```text
1. MPI 后处理：
   MPI 3D VTX .bp 写出在当前容器中可能触发不可恢复的 BUS error。
   现在 comm.size > 1 时跳过 VTX .bp，写 vtx_3d_skipped_mpi.txt，并继续写并行 VTU/PVD。

2. Floquet 计时：
   新增 floquet_build_topological_edge_context。
   原先 x-direction 计时包含首次构建周期边拓扑上下文的时间，因此会误以为 x 约束本身很慢。

3. DtN 装配优化保持有效：
   复用表面 x/y component form 后，1068 个 auxiliary modes 的 h=5 auto_propagating smoke 仍可在十几秒完成。
```

已运行命令：

```text
. dolfinx-complex-mode && python3 -m compileall -q src
结果：通过

. dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
结果：Ran 37 tests, OK (skipped=8)

mpiexec -n 8 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --stage4-boundary-model dtn_port \
  --stage4-dtn-order-policy zero_order \
  --mesh-target-size 2.5 \
  --nedelec-degree 1 \
  --visualization-degree 3 \
  --unique-output

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

结果摘要：

```text
h=2.5 block, np=8, zero_order:
  results/3D_stage4_block_grating_normal_p1_h2p5_np8_20260625_092003
  case_status = completed
  R/T/R+T = 0.3189887183 / 0.6810112817 / 1.0000000000
  max RSS = 2156 MB
  elapsed = 328.008 s
  vtx_3d_output_status = skipped_mpi
  ParaView = fields_3d_for_paraview_parallel.pvd

h=5 block, np=4, auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_093728
  DtN modes = 1068
  R/T/R+T = 0.3661053 / 0.6338947 / 1.0000000
  floquet_build_topological_edge_context = 0.591 s
  floquet_build_x_constraints = 0.021 s
  floquet_build_y_constraints = 0.016 s
  stage4_dtn_port_assembly_and_solve = 13.487 s
  elapsed = 16.604 s
```

结论：

```text
1. 用户遇到的 BUS error 更像是 MPI VTX/ADIOS2 后处理崩溃，不是求解器或 Floquet 崩溃。
2. h=2.5、np=8 的 block case 已经可以完整写出 summary 和 ParaView PVD。
3. DtN 不会影响 Floquet 约束；Floquet 几秒主要来自 topological edge context 和边界 edge 数量增长。
4. h=10 nm 对 13.5 nm 波长太粗，不作为物理验收；h=2.5 flat sanity 仍是当前更可信的均匀层口径。
```

## 2026-06-25 更新：DtN 端口装配优化与弱式符号复核

本轮完成两类修正：

```text
1. 计时拆分：
   boundary_condition_setup 不再包含 Floquet MPC 构建；
   Floquet 相关耗时看 floquet_constraint_setup_outer 和 floquet_build_x/y/corner。

2. DtN 端口优化：
   每个 (side,m,n) 只装配 x/y 两个表面分量；
   同一 (side,m,n) 的两个偏振通过线性组合得到 trace/traction；
   表面 form 使用 fem.Constant 更新 alpha/gamma/kz，避免为每个级次重新创建 form。
```

同时复核了 3D curl-curl 弱式边界符号。当前正式口径：

```text
FEM block        += - q * ell * auxiliary
top RHS          += +2i beta * E_inc 的等效向量
auxiliary        = 端口总场投影
top outgoing     = total_projection - incident_projection
bottom outgoing  = total_projection
```

验证命令和结果：

```text
compileall:
  . dolfinx-complex-mode && python3 -m compileall -q src
  结果：通过

unittest:
  . dolfinx-complex-mode && python3 -m unittest discover -s src/test -p "test_*.py"
  结果：Ran 37 tests, OK (skipped=8)
```

PDE 实跑：

```text
flat, n_sub=1.0, h=5, np=4:
  results/3D_stage4_flat_layer_sanity_normal_p1_h5p0_np4_20260625_074233
  R/T/R+T = 2.412601e-02 / 9.758740e-01 / 1.000000
  elapsed = 10.051 s

flat, n_sub=1.0, h=2.5, np=8:
  results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_074306
  R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000
  stage4_dtn_modal_loop_seconds = 0.033 s
  stage4_dtn_linear_solve_seconds = 222.650 s
  elapsed = 253.684 s

block grating, h=5, np=4, auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_074047
  DtN modes = 1068
  R/T/R+T = 3.661053e-01 / 6.338947e-01 / 1.000000
  stage4_dtn_modal_loop_seconds = 2.431 s
  stage4_dtn_port_assembly_and_solve = 12.210 s
  elapsed = 15.637 s
```

和旧记录对比：

```text
旧 h=5 block auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_063607
  elapsed ≈ 610 s

第一层优化后：
  elapsed ≈ 290 s
  modal loop ≈ 276 s

当前可复用 form 优化后：
  elapsed = 15.637 s
  modal loop = 2.431 s
```

结论：

```text
1. 之前 boundary_condition_setup 看起来变长，主要是旧计时口径把 Floquet MPC 也算进去了；
   当前 dtn_port 分支 boundary_condition_setup 接近 0。
2. 1068 个辅助模态的装配已经不是主要瓶颈；
   h=2.5 大问题中主要耗时是 MUMPS 直接求解。
3. h=5 flat 的 R=2.4% 是粗网格色散误差；h=2.5 收敛到 R=6.0e-4。
4. lossless block grating 的 R+T 保持在 1 的舍入误差内，没有再出现 PML/probe 分支那种 R+T 爆炸。
```

## 2026-06-25 更新：Stage 4 dtn_port 实跑验证完成，能量守恒恢复

本轮修复了 3D DtN auxiliary 端口的符号口径。最终采用与 2D 端口同构的形式：

```text
auxiliary unknown = 端口总场投影
FEM block        += q * ell * auxiliary
top RHS          += -2i beta * E_inc 的等价向量
R/T              = top(total_projection - incident_projection), bottom(total_projection)
```

当前已完成：

```text
1. python3 -m compileall -q src：通过。
2. python3 -m unittest discover -s src/test -p "test_*.py"：
   Ran 37 tests, OK (skipped=8)。
3. stage4_flat_layer_sanity + dtn_port 已跑通。
4. stage4_block_grating + dtn_port + auto_propagating 已跑通。
```

关键结果：

```text
flat, n_sub=1.0, h=2.5, np=8:
  results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_061747
  R/T/R+T = 6.043954e-04 / 9.993956e-01 / 1.000000
  elapsed = 278.66 s, max RSS = 2133.96 MB

flat, n_sub=1.45, h=2.5, np=8:
  results/3D_stage4_flat_layer_sanity_normal_p1_h2p5_np8_20260625_062303
  R/T/R+T = 2.061463e-02 / 9.793854e-01 / 1.000000
  解析 Fresnel R 约 3.37e-02；p1/h=2.5 仍有离散误差，但相对 h=5 明显收敛。
  elapsed = 273.63 s, max RSS = 2035.06 MB

block grating, h=5, np=4, auto_propagating:
  results/3D_stage4_block_grating_normal_p1_h5p0_np4_20260625_063607
  DtN modes = 1068, top/bottom = 354 / 714
  R/T/R+T = 3.661053e-01 / 6.338947e-01 / 1.000000
  elapsed = 610.00 s, max RSS = 1739.24 MB
```

当前判断：

```text
1. DtN 主线已经解决旧 PML/probe 分支的 R+T 爆炸问题。
2. lossless 情况下不再 clip，真实输出自然满足 R+T≈1。
3. h=5 对 EUV 仍偏粗；h=2.5 flat sanity 显示明显收敛。
4. h=2.5 + block + auto_propagating 预计端口装配会非常久，尚未作为本轮必跑项。
5. 旧 Stage 4 PML 散射场分支继续保留为诊断历史，不再作为可信 R/T 主线。
```

## 2026-06-25 更新：E/H Fourier 后处理修正后，目标 h=2.5 仍未通过

本轮修正了 Stage 4 衍射级后处理中的一个重要问题：

```text
旧官方口径：只用 E 的 Fourier 系数推断每个衍射级功率。
问题：同一个 (m,n) 在 probe 面上可能同时有下行/上行波，尤其有限 PML 有回波时，
      E-only 会把 incoming/outgoing 混在一起，导致透射率明显虚高。

新官方口径：对每个 (m,n) 单独使用切向 (E_x,E_y,H_x,H_y) Fourier 系数，
            解一个小的 up/down/s/p 模态系统，再只统计 top-up 反射和 bottom-down 透射。
```

新增单元测试：

```text
python3 -m unittest src.test.test_11_stage4_diffraction_modes
结果：7 tests OK

python3 -m unittest discover -s src/test -p "test_*.py"
结果：33 tests OK, skipped=8
```

关键实跑结果：

| case | result dir | h nm | PML | official power | R | T | R+T | E-only R+T | net-flux R+T | 结论 |
|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| zero contrast block | `results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260625_012331` | 12.5 | 25 nm natural | old run | 0.033736 | 0.966264 | 1.000000 | 1.000000 | 1.000000 | 通过 |
| weak contrast n=1.2 | `results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260625_012525` | 12.5 | 25 nm natural | old run | 0.033649 | 0.967980 | 1.001629 | 1.001629 | 1.006901 | 轻微超 1 |
| n=2 current | `results/3D_stage4_block_grating_normal_p1_h12p5_np4_20260625_013916` | 12.5 | 25 nm natural | E/H Fourier | 0.031539 | 0.969590 | 1.001129 | 1.008603 | 1.025137 | 后处理改善但仍超 1 |
| n=2 current | `results/3D_stage4_block_grating_normal_p1_h6p25_np4_20260625_014118` | 6.25 | 25 nm natural | E/H Fourier | 0.395799 | 1.002770 | 1.398569 | 1.781313 | 0.822158 | 场本身不可信 |
| n=2 strong PML | `results/3D_stage4_block_grating_normal_p1_h6p25_np4_20260625_015707` | 6.25 | 100 nm, alpha=30, zero | E/H Fourier | 0.423308 | 0.994351 | 1.417659 | - | 0.867155 | 加厚 PML 未解决 |
| n=2 target | `results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260625_020717` | 2.5 | 25 nm natural | E/H Fourier | 0.062028 | 1.922722 | 1.984750 | 2.602034 | 1.882674 | failed_stage4_energy_balance |

本轮判断：

```text
1. E/H Fourier 后处理是必要修正：h=12.5 的 R+T 从 1.0086 降到 1.0011，
   h=6.25 的 R+T 从 1.7813 降到 1.3986。
2. 目标 h=2.5 仍严重 R+T>1，因此问题不只是后处理。
3. h=6.25 改成 zero_tangential、PML=50/100 nm、alpha=8/30 后仍不通过，
   所以当前失败不能靠简单加厚 PML 修好。
4. h=6.25 和 h=2.5 的 max |E_scat| 已经达到 3.4 到 4.0，场本身出现强非物理/未收敛特征。
5. 对 13.5 nm、n_grating=2，材料内波长只有 6.75 nm；p1/h=2.5 只有约 2.7 个单元/材料内波长，
   仍低于常用的 6 个单元/波长经验要求。当前 direct + p1 + PML 路径不能把该 EUV 案例判为可信结果。
```

因此当前版本的程序行为是：flat/零对比度 sanity 通过；真实 block grating 若 `R+T>1`，继续标记为 `failed_stage4_energy_balance` 和 `diagnostic_only=true`，不允许误用为正式物理结果。

## 2026-06-24 更新：h=2.5 nm、np=16 正式重跑结论

本轮在资源空闲后重新跑了 13.5 nm 小周期 `stage4_block_grating`，参数为：

```text
lambda0 = 13.5 nm
period_x = period_y = 100 nm
block = 50 x 50 x 50 nm
substrate_thickness = 50 nm
air_height = 100 nm
pml_top/bottom = 25 / 25 nm
mesh_target_size = 2.5 nm
nedelec_degree = 1
MPI ranks = 16
diffraction_sample_count_x/y = 64 / 64
```

结果对比：

| PML outer BC | result dir | R | T | R+T | net-flux R+T | true residual | setup s | solve s | max \|E_scat\| in PML | 结论 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| natural | `results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_124802` | 0.068117 | 2.534148 | 2.602265 | 1.823622 | 9.12e-12 | 194.99 | 2096.60 | 2.864955 | failed_stage4_energy_balance |
| zero_tangential | `results/3D_stage4_block_grating_normal_p1_h2p5_np16_20260624_133711` | 0.069171 | 2.535508 | 2.604678 | 1.870036 | 5.64e-12 | 198.93 | 2158.22 | 2.850564 | failed_stage4_energy_balance |

本轮判断：

```text
1. direct LU 已正常收敛，true relative residual 约 1e-11。
2. Floquet 约束构建完成，没有再卡在 building/resolving 阶段；h=2.5 的约束数为 12960。
3. zero_tangential 与 natural 的 R/T 几乎相同，因此“PML 外边界是否强制零切向 E_scat”不是当前 R+T 爆炸主因。
4. E-Fourier R+T 和采样净通量 R+T 都大于 1，说明问题不是单一 R/T 公式的显示误差。
5. h=2.5 nm 对 13.5 nm 真空波长只略粗于 lambda0/6，对 n=2 光栅内波长则明显不足；
   但误差大到 2.6，不能简单归因于普通网格收敛误差，后续应继续查弱式/PML 张量/分层背景源项的一致性。
```

`zero_tangential` 结果还验证了 z 外边界强边界确实全局施加：

```text
strong_z_boundary_dirichlet_raw_dofs_global = 7376
strong_z_boundary_dirichlet_dofs_global = 7216
```

旧 summary 中 `strong_z_boundary_dirichlet_dofs` 曾只记录 rank0 本地 dof，rank0 没有 z 边界 dof 时会显示 0；代码已改为记录全局数，避免误读。

## 2026-06-24 更新：R/T 后处理修正后的 sanity 结果

代码变更：

```text
1. 删除 3D solver_profile / --solver-profile 公开入口，3D 当前固定使用内部 direct LU。
2. Stage 4 diffraction 后处理改为采样 E_scat，再加解析分层背景 E_bg_exact。
3. 当 diffraction_zero_order_only=False 时，官方 R/T 自动补全所有传播衍射级。
```

新增单元测试：

```text
python3 -m unittest src.test.test_11_stage4_diffraction_modes
结果：6 tests OK
```

解析/flat-layer 验证：

| case | result dir | h nm | PML | R | T | R+T | 结论 |
|---|---|---:|---|---:|---:|---:|---|
| analytic Fresnel postprocess | 单元测试 | - | - | 0.03373594 | 0.9662641 | 1.000000 | 通过 |
| stage4_flat_layer_sanity | `results/3D_stage4_flat_layer_sanity_normal_p1_h12p5_np2_20260624_101122` | 12.5 | natural, 25 nm | 0.03373594 | 0.9662641 | 1.000000 | 通过 |

block-grating 粗网格诊断：

| case | result dir | h nm | PML | orders | R | T | R+T | 结论 |
|---|---|---:|---|---:|---:|---:|---:|---|
| block grating | `results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260624_102538` | 12.5 | natural, 25 nm | resolved m,n<=10 | 0.034926 | 0.973677 | 1.008603 | failed_stage4_energy_balance |
| block grating | `results/3D_stage4_block_grating_normal_p1_h12p5_np2_20260624_102938` | 12.5 | natural, 50 nm, alpha=8 | resolved m,n<=10 | 0.034938 | 0.973685 | 1.008623 | failed_stage4_energy_balance |

判断：

```text
1. flat-layer sanity 已排除 Fresnel 背景、功率归一化和传播级枚举的主要错误。
2. PML 加厚后散射场衰减明显改善，但 h=12.5 的 R+T 超 1 基本不变，因此该误差不是 PML 厚度主导。
3. 当前 block-grating h=12.5 仍不是可信物理结果；需要用修复后的代码重跑 h=2.5 nm 或更细网格。
4. 修复前的 h=2.5 结果来自旧的 E_total 插值背景后处理，不能作为最终 R/T 结论。
```

## 2026-06-24 更新：13.5 nm 小周期 h25 smoke 与 PML 外边界对比

本轮默认案例改为 13.5 nm 波长、100 x 100 nm 周期、50 nm 立方体。h25/p1 只是流程 smoke，不作为精度结论。

```text
physical domain = 100 x 100 x 150 nm
pml_top/bottom = 25 / 25 nm
diffraction_probe_fraction = 0.75
top_probe_z / bottom_probe_z = 75 / -37.5 nm
diffraction_compute_modal_diagnostic = false
```

| PML outer BC | result dir | R | T | R+T | max \|E_scat\| in PML | linear_problem_setup |
|---|---|---:|---:|---:|---:|---:|
| natural | `results/3D_stage4_block_grating_normal_p1_h25p0_20260624_073407` | 0.045960 | 0.278516 | 0.324476 | 3.12e-2 | 93.95 s |
| zero_tangential | `results/3D_stage4_block_grating_normal_p1_h25p0_20260624_073105` | 0.045685 | 0.278052 | 0.323737 | 7.02e-4 | 0.004 s |

结论：

```text
1. 默认 natural 不再用外边界零值掩盖 PML 残余场。
2. 两种外边界在 h25 粗网格上的正式 E-Fourier R/T 很接近。
3. natural 当前在 dolfinx_mpc + no z Dirichlet + direct 路径下 setup 明显更慢。
4. 13.5 nm、100 nm 周期会打开很多传播衍射级；旧 E/H modal diagnostic 默认关闭，
   否则会在多级次情况下拖慢甚至卡住后处理。
```

## 2026-06-24 更新：Stage 4 MPI 串并行一致性已修复

本轮修复了 `stage4_block_grating, h50, p1` 在 MPI 下场幅值爆炸、`R+T>1` 的问题。根因不是 RHS，也不是 MUMPS 本身，而是 3D Nedelec Floquet 约束中边方向使用了未置换的几何边顺序；在并行重编号后，约束矩阵会出现很小但足以激发病态解的分区相关差异。

代码修复：

```text
src/constraints/floquet_3d.py
  1. 调用 mesh.topology.create_entity_permutations()。
  2. 用 entities_to_geometry(..., permute=True) 取得与 DOLFINx 拓扑一致的边方向。
  3. local constraint 保留本 rank 装配 owned cells 所需的 local slave dof。
     这符合 dolfinx_mpc.add_constraint 的语义；它不是全局重复约束。

src/solvers/solve_airbox_maxwell_3d.py
  1. MPI direct 显式选择 MUMPS/SuperLU_DIST/STRUMPACK 这类并行 LU。
  2. Stage 4 PML 外边界对散射场施加零切向 E，summary 写出
     stage4_outer_pml_zero_tangential_e_bc=true。
  3. summary 新增 unconstrained_rhs_norm、linear_system_rhs_norm、
     linear_system_solution_norm、linear_system_relative_residual、矩阵范数等诊断字段。
```

最终验证使用同一组参数：

```text
stage_case = stage4_block_grating
mesh_target_size = 50 nm
nedelec_degree = 1
visualization_degree = 1
solver_profile = direct
stage4_boundary_model = pml
probe planes = 807.5 / -332.5 nm
```

| MPI ranks | 结果目录 | case_status | R | T | R+T | max \|E\| | linear solution norm | matrix Frobenius | relative residual | elapsed s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `results/3D_stage4_block_grating_normal_p1_h50p0_20260624_040509` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 7.09e-12 | 255.5 |
| 2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260624_034631` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 3.66e-13 | 175.3 |
| 4 | `results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_034137` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 5.29e-13 | 182.3 |
| 8 | `results/3D_stage4_block_grating_normal_p1_h50p0_np8_20260624_035010` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 1.96e-13 | 189.9 |
| 12 | `results/3D_stage4_block_grating_normal_p1_h50p0_np12_20260624_035345` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 4.92e-13 | 243.1 |
| 16 | `results/3D_stage4_block_grating_normal_p1_h50p0_np16_20260624_035815` | completed | 0.001666 | 0.951074 | 0.952741 | 1.911019 | 1266.870459 | 45.797938 | 7.38e-13 | 362.3 |

结论：

```text
1. 串行与 MPI 2/4/8/12/16 的矩阵范数、RHS 范数、解范数、max|E| 和 R/T 已一致。
2. 正式 E-Fourier R+T = 0.952741，小于 1，Stage 4 lossless 能量门槛通过。
3. sampled net-flux R+T 仍约 1.014，只作为 H=curl(E) 后处理诊断，不作为正式 R/T。
4. h50/p1 仍是粗网格，和 COMSOL 对齐时应比较场形态与收敛趋势，不把 4.7% 的 A_balance 当成真实吸收。
```

## 2026-06-24 修复前记录：Stage 4 h50/p1 串行与 MPI 2/4/8/12/16 对比

本轮固定当前正式 600/500 nm block grating 案例：

```text
stage_case = stage4_block_grating
case = normal
mesh_target_size = 50 nm
nedelec_degree = 1
visualization_degree = 1
solver_profile = direct
stage4_boundary_model = pml
probe planes = 95% physical layers, top/bottom = 807.5 / -332.5 nm
```

尝试 `h=100 nm` 时被 hexa alignment 检查拒绝，因为当前几何要求 block 边界、interface、PML 入口全部落在网格面上；该几何的 z 方向分层最小需要 `nz=34`，也就是当前 `h=50 nm`。

对比结果如下：

| MPI ranks | 结果目录 | case_status | E-Fourier R+T | 相对串行差值 | net-flux R+T | max \|E\| | max \|E\| / serial | PML top/bottom decay | elapsed s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `results/3D_stage4_block_grating_normal_p1_h50p0_20260624_013712` | completed | 0.952775 | 0 | 1.014386 | 1.910820 | 1.00 | 0.175714 / 0.040724 | 223.7 |
| 2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260624_015216` | completed | 0.921741 | -0.031034 | 0.982857 | 1.877129 | 0.98 | 0.212881 / 0.040493 | 150.1 |
| 4 | `results/3D_stage4_block_grating_normal_p1_h50p0_np4_20260624_015509` | failed_stage4_energy_balance | 2.073427 | +1.120651 | 2.150272 | 23.617497 | 12.36 | 1.061739 / 0.187570 | 169.9 |
| 8 | `results/3D_stage4_block_grating_normal_p1_h50p0_np8_20260624_015823` | completed | 0.914782 | -0.037993 | 1.010485 | 11.706217 | 6.13 | 0.358386 / 0.066189 | 201.7 |
| 12 | `results/3D_stage4_block_grating_normal_p1_h50p0_np12_20260624_020211` | failed_stage4_energy_balance | 1.111209 | +0.158434 | 1.302703 | 9.874917 | 5.17 | 0.815837 / 0.243159 | 269.2 |
| 16 | `results/3D_stage4_block_grating_normal_p1_h50p0_np16_20260624_020710` | failed_stage4_energy_balance | 1.186946 | +0.234170 | 1.369332 | 7.655168 | 4.01 | 0.726095 / 0.685615 | 241.8 |

结论：

1. 当前 Stage 4 MPI 路径不满足串并行一致性。`np=2` 的场幅值接近串行，但 E-Fourier `R+T` 已偏低约 0.031；`np=4/12/16` 明确失败并出现 `R+T>1`。
2. `np=4/8/12/16` 的 `max|E|` 是串行的 4 到 12 倍，说明问题不是单纯的 diffraction 后处理，而是并行求解得到的场本身已经依赖 MPI 分区。
3. Floquet 总约束统计在各并行数中仍显示 `num_constraints=1552`、`max edge midpoint pairing error=0`，但 rank0 看到的 local slave dofs 随 MPI 数变化很大，`np=16` 时 rank0 为 0。后续应重点检查 `dolfinx_mpc` 低层约束数组在分布式所有权、ghost/master ownership、rank-local slave 注册上的一致性。
4. 在修复 MPI 串并行一致性前，Stage 4 物理结果应优先使用串行 direct；MPI 结果只能作为流程/性能诊断，不能作为物理验收。

## 2026-06-24 更新：衍射级 probe plane 默认位置修正

根据新的检查结论，逐衍射级 R/T 对 bottom probe plane 位置较敏感，而总 Poynting flux 已经接近 0.997。为了更靠近物理层外侧的均匀远场区域，Stage 4 默认衍射级采样面已改为：

```text
top_probe_z    = interface_z + 0.95 * (physical_z_max - interface_z)
bottom_probe_z = interface_z + 0.95 * (physical_z_min - interface_z)
```

当前 600/500 nm 案例对应：

```text
top_probe_z = 807.5 nm
bottom_probe_z = -332.5 nm
```

本次同时新增采样诊断字段：

```text
diffraction_sample_point_count_per_plane
diffraction_min_sample_count_x_for_fit_orders
diffraction_min_sample_count_y_for_fit_orders
```

后续重新实跑 h50/p1 时，需要重点比较：

```text
R_total_from_e_fourier / T_total_from_e_fourier / R_plus_T_from_e_fourier
R_total_from_net_flux / T_total_from_net_flux / R_plus_T_from_net_flux
diffraction_top_e_fourier_projection_residual_max
diffraction_bottom_e_fourier_projection_residual_max
```

若 E-Fourier 逐衍射级求和仍明显低于 net-flux 能量守恒值，则应继续把逐衍射级功率标为 diagnostic，并优先推进真正的 modal port 或更稳健的面投影后处理。

已按新默认 probe plane 重新实跑 h50/p1 normal：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260624_013712
top_probe_z / bottom_probe_z = 807.5 / -332.5 nm
sample points per plane = 24 x 24 = 576
minimum sample count for current fit orders = 3 x 3

official E-Fourier R/T = 1.656074e-03 / 9.511194e-01
official E-Fourier R+T = 9.527755e-01
sampled net-flux R/T = 4.427998e-02 / 9.701064e-01
sampled net-flux R+T = 1.014386e+00
top/bottom E-Fourier projection residual max = 9.519178e-02 / 4.453606e-02
case_status = completed
```

逐传播级次的 E-Fourier 功率：

| m | n | pol | R | T |
| --- | --- | --- | --- | --- |
| -1 | 0 | s | 0 | 8.104863e-02 |
| 0 | -1 | p | 0 | 3.495170e-02 |
| 0 | 0 | y | 1.656074e-03 | 7.191188e-01 |
| 0 | 1 | p | 0 | 3.495170e-02 |
| 1 | 0 | s | 0 | 8.104863e-02 |

结论：95% probe plane 让官方逐级 `R+T` 从旧结果约 0.936 提高到约 0.953，但仍没有达到 2D 中约 0.998 的能量闭合水平。当前瓶颈仍是 Stage 4 的 3D diffraction-order power decomposition，而不是采样点数量；576 个点已经明显高于 3 x 3 的最低 Fourier 区分要求。

## 2026-06-23 更新：600/500 nm COMSOL 对比单胞 h50 验证

本轮按 COMSOL 新案例更新了 Stage 4 默认几何：

```text
period_x / period_y = 600 / 500 nm
block = 300 x 200 x 150 nm
air_height = 850 nm
substrate_thickness = 350 nm
pml_top / pml_bottom = 250 / 250 nm
normal incidence S polarization: incident_phi_deg = 0 deg, E 主要沿 y
```

同时修正了 R/T 后处理：

```text
official R/T source = e_fourier_orders
old E/H modal-order powers = diagnostic only
lossless R+T pass tolerance = 1e-8
```

flat-layer sanity:

```text
results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_20260623_133806
R/T = 3.373594e-02 / 9.662641e-01
R+T = 1.000000e+00
case_status = completed
```

block grating normal:

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260623_135921
official E-Fourier R/T = 2.600070e-03 / 9.334178e-01
official R+T = 9.360178e-01
old modal diagnostic R+T = 1.065764e+00
case_status = completed
```

block grating theta=10 deg:

```text
results/3D_stage4_block_grating_normal_p1_h50p0_20260623_140352
official E-Fourier R/T = 9.938852e-03 / 9.276119e-01
official R+T = 9.375507e-01
old modal diagnostic R+T = 1.060111e+00
case_status = completed
```

h25 direct 尝试：

```text
15 分钟内未完成，残留 Docker 容器已停止。
判断：当前 Docker/direct LU 资源不足，不能作为物理失败。
```

关于 `linear_problem_setup`：本轮 h50/p1 中它约 90-100 s，`linear_problem_solve` 约 129 s。这不是单纯的 Python 函数调用耗时，而是 `dolfinx_mpc.LinearProblem` 构造受 Floquet MPC 约束后的线性系统、创建 PETSc 对象、触发表达式/矩阵装配等操作。h25 的矩阵和 LU 因子化成本会远高于 h50，因此当前直接法不适合继续把 h25 当作常规 smoke。

## 2026-06-23 更新：PML 流程回到 2D-like，evanescent fitting 修正 R+T 爆掉

本轮根据 COMSOL 电场模截图和“lossless R+T 不应超过 1”的要求继续修正 Stage 4。核心变化：

```text
1. Stage 4 正式 PML 分支不再对 z 外边界强加 Dirichlet，
   而是回到 2D scattered solver 类似的 PML 弱式 + natural outer boundary。

2. stage4_boundary_model="robin0" 保留为无 PML 诊断分支，
   不作为正式结果。

3. diffraction_3d 的默认 block grating 拟合中加入邻近 evanescent 级次。
   这些非传播级次只用于分离近场谐波，不计入传播功率。

4. ParaView 物理区电场模切片已经生成：
   results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409/stage4_Etot_physical_slices.png
```

代码检查：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

Ran 27 tests in 1.189s
OK (skipped=8)
```

实跑结果：

| 算例 | 结果目录 | 关键结果 | 判定 |
| --- | --- | --- | --- |
| block grating h50/p1/serial | `results/3D_stage4_block_grating_normal_p1_h50p0_20260623_084409` | R+T = 9.826341e-01, fit_order_count=9 | 通过，场分布可用于诊断 |
| block grating h50/p1/MPI2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_084643` | R+T = 9.142503e-01, fit_order_count=9 | 通过，但与串行仍有定量差异 |
| flat-layer sanity h50/p1/MPI2 | `results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np2_20260623_083941` | modal R+T = 1.000000 | 通过；注意 sampled net flux 仍只是诊断量 |
| 2.5D serial h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np1_20260623_084908` | max Ey ≈ 3.9e-14，但 3D R+T = 1.042795 | 未通过定量对齐 |

当前判断：

```text
1. COMSOL 参考图要求的“热点在柱子侧壁/界面附近，而不是 PML 支配显示”已经基本满足。
2. 真实 block grating h50/p1 不再出现 R+T>1，说明之前 0 级拟合被 evanescent 近场污染。
3. MPI2 与 serial 的 R/T 仍不完全一致，后续需要做更细网格、更多采样面位置和可能的并行后处理对照。
4. 2.5D y-extruded 的非物理 Ey 已消失，但 R/T 仍未复现旧 2D TM，因此还不能宣称 Stage 4 已完成最终定量验证。
```

下面更早的条目保留为历史排查记录；如果边界条件或 R/T 结论与本节冲突，以本节为准。

## 2026-06-23 更新：PML 外边界强截断与 2.5D 对照复跑

本轮继续响应“PML 外边界不应有电场、lossless 情况下 R+T 不应超过 1”的检查。已完成：

```text
1. Stage 4 求解后显式 E.x.scatter_forward()，避免 MPI 后处理读取未同步 ghost dof。
2. Stage 4 PML 外边界施加零切向 E，summary 字段 stage4_outer_pml_zero_tangential_e_bc=true。
3. Floquet low-level builder 改为在本 rank 可见的 slave dof 上登记本地约束，同时保留全局唯一 slave 统计。
4. 2.5D 对照 JSON 增加 max_abs_Ey、max_abs_E_sca_Ey、energy guard 字段。
```

代码检查：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

Ran 27 tests in 1.092s
OK (skipped=8)
```

实跑结论：

| 算例 | 结果目录 | 关键结果 | 判定 |
| --- | --- | --- | --- |
| flat-layer sanity h50/p1/MPI2 | `results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np2_20260623_073657` | R+T = 1.000000 | 通过 |
| block grating h50/p1/MPI2 | `results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_073428` | R+T = 1.084467 | 失败，diagnostic only |
| 2.5D serial h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np1_20260623_074217` | 3D R+T = 1.117862, max Ey = 8.5e-7 | 仍未和 2D TM 一致 |
| 2.5D MPI2 h50/p1 | `results/stage4_2p5d_compare_h50p0_p1_np2_20260623_074950` | 3D R+T = 1.220574, max Ey = 9.21e-1 | 失败，MPI 下额外偏振更明显 |

判断：PML 背景显示和外边界截断问题已经修正；flat-layer sanity 证明 0 级衍射拟合和 Fresnel 背景口径可用。但真实 grating 的 scattered-field full-vector 3D 路径仍不可信，尤其是 2.5D y-extruded benchmark 尚不能复现旧 2D TM。后续必须先修复 2.5D 对照，再继续真实 3D 定量 benchmark。

## 2026-06-23 更新：2.5D 对照暴露 Stage 4 全矢量解问题

本轮根据“R+T 不能超过 1”的原则重新检查 Stage 4。结论：当前 Stage 4 block grating 不能作为正确结果。

已完成代码检查：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.111s
OK (skipped=8)
```

### Stage 4 默认 block grating

命令：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_072542
```

关键结果：

| 指标 | 数值 |
| --- | ---: |
| R | 9.381001e-03 |
| T | 1.075089e+00 |
| R+T | 1.084470e+00 |
| stage4_energy_balance_pass | False |
| official_result | False |
| case_status | failed_stage4_energy_balance |
| max abs(Ex/Ey/Ez) | 2.749835e+00 / 3.337442e+00 / 2.054251e+00 |

说明：程序现在会把 lossless 且 `R+T > 1.01` 的 Stage 4 结果标记为失败诊断结果，不再把它当 official。

### 2.5D 对照

新增脚本：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.test.stage4_2p5d_compare \
  --mesh-target-size 50 \
  --nedelec-degree 1
```

结果目录：

```text
results/stage4_2p5d_compare_h50p0_p1_np2_20260623_065320
```

对照结果：

| 指标 | 2D TM | 3D y-extruded |
| --- | ---: | ---: |
| R | 5.958643e-04 | 7.524211e-03 |
| T | 8.747995e-01 | 1.399502e+00 |
| R+T | 8.753954e-01 | 1.407026e+00 |

3D y-extruded case 中 `max |E_scat_y|` 约为 `1.27`，但这个 2.5D 结构和入射条件下 `Ey` 理论上应接近 0。说明当前 3D 全矢量 Stage 4 解混入了非物理偏振/模式，不能只靠后处理修正。

### 本轮修正

```text
1. Stage 4 的 E_b 在 PML 区域置零，避免 E_tot 外边界被背景场染亮。
2. Stage 4 layered-scattered 现在对 PML 外边界施加零切向 E，避免散射场在外截断面自由漂移。
3. ParaView/summary 增加 Ex/Ey/Ez 分量最大值。
4. 增加 2.5D 对照脚本。
5. 增加 Stage 4 lossless energy-balance guard。
6. 增加 divergence_penalty 配置作为诊断项；h50 试验中 penalty=1 对当前问题无明显改善。
```

下一步硬门槛：先让 `stage4_2p5d_compare.py` 中 3D y-extruded case 的 `Ey` 接近 0，并且 R/T 与 2D TM 同趋势，再恢复真实 3D block grating。

## 2026-06-23 更新：PML/E_exact 修正后的最终验证

本轮目标是修正两个误导性问题：

```text
1. Stage 4 真实 grating 没有 E_exact，不能把 E_b 当精确解输出。
2. Stage 4 PML 吸收的是 E_scat，不能用 PML 中的 E_b/E_tot 模值判断吸收失败。
```

已完成代码检查：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.247s
OK (skipped=8)
```

已完成实跑：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.runners.run_3d_airbox \
  --stage-case stage4_all \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_all_normal_p1_h50p0_np2_20260623_062048
```

### flat-layer sanity

```text
case: airbox3d_normal_stage4_flat_layer_sanity
mesh cells: 1176
N1curl dofs: 4381
Floquet constraints: 769
E_scat: 0
PML metric field: E_scat
```

| 指标 | 数值 |
| --- | ---: |
| modal R | 3.373594e-02 |
| modal T | 9.662641e-01 |
| modal R+T | 1.000000e+00 |
| top fit residual | 6.202768e-15 |
| bottom fit residual | 5.371332e-15 |

结论：无 grating/source 时，calibrated diffraction modal postprocess 能精确回到 Fresnel 0 级。因此 Stage 4 的 `E_b`、Fresnel 背景和模态 R/T 后处理口径是自洽的。

### block grating h50/p1

```text
case: airbox3d_normal_stage4_block_grating
mesh cells: 1176
N1curl dofs: 4381
Floquet constraints: 769
estimated Floquet memory: 0.026 MB
linear_problem_setup: 80.582 s
linear_problem_solve: 25.454 s
max RSS: 4149.5 MB
```

| 指标 | 数值 |
| --- | ---: |
| modal R | 9.380284e-03 |
| modal T | 1.075087e+00 |
| modal R+T | 1.084467e+00 |
| A_balance | -8.446713e-02 |
| top fit residual | 1.667669e-02 |
| bottom fit residual | 7.202705e-03 |
| E_scat PML decay top | 1.817922e-02 |
| E_scat PML decay bottom | 6.249538e-03 |
| max abs(E_tot) physical z-region | 4.787418e+00 |
| max abs(E_tot) PML z-region | 1.484122e+02 |
| max abs(E_scat) physical z-region | 4.375600e+00 |
| max abs(E_scat) PML z-region | 1.789548e-01 |

结论：PML 对散射场有明显衰减，ParaView 中 PML 区域 `E_tot/E_b` 大主要来自背景场的 PML 复坐标延拓。默认 h50 block grating 的能量平衡仍偏大，`R+T` 高出约 8.4%，因此它目前是流程 smoke，不是最终高精度定量 benchmark。

### h40 对齐检查

尝试 `mesh_target_size=40 nm` 时程序主动拒绝：

```text
Stage-4 hexa meshes do not use midpoint approximation for material boundaries.
grating_x_min=100 nm is not on the uniform x-grid ...
```

这是预期保护。默认几何下 `h=50 nm` 和 `h=25 nm` 对齐，`h=40 nm` 不对齐。下一轮如果要做真实收敛，优先考虑 `h=25 nm`，但直接法内存会显著增加。

## 2026-06-23 更新：main.py 入口与 ParaView 三场输出

本轮修正后，从 `src.main` 直接运行 Stage 4 已通过：

```bash
mpirun -n 2 python3 -m fenics_vector_maxwell_floquet_demo_v2_parallel.src.main
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_020702
```

关键检查：

| item | value |
| --- | ---: |
| mesh target size | 50 nm |
| mesh cells resolved | 7 x 6 x 30 |
| N1curl dofs | 4687 |
| Floquet constraints | 823 |
| estimated Floquet memory | 0.028 MB |
| linear problem setup | 85.467 s |
| direct solve | 30.802 s |
| max RSS | 4065.9 MB |

`run_summary.json` 已记录 ParaView 电场数组：

```text
E_V_per_m_*       # 兼容旧字段，等同总场
E_tot_V_per_m_*   # 总场
E_sca_V_per_m_*   # 散射场
E_b_V_per_m_*     # 分层背景场
```

说明：本次 `main.py` 使用 `PML_ALPHA_3D=10`、PML 厚度 300 nm。背景场在 PML 中会做复坐标延拓，因此 `max_abs_E_b` 可能被 PML 区域放大；看结构附近场分布时优先用 ParaView 的 `domain_tag` 聚焦物理区。

## 2026-06-23 更新：第一轮 smoke 与后处理校准

本轮完成：

```text
compileall
unit tests
stage4_block_grating h50/p1 MPI 2 normal
stage4_flat_layer_sanity h50/p1 MPI 4 normal
stage4_block_grating h50/p1 MPI 2 theta=10 deg
```

没有完成：

```text
high-order 大周期 preset
absorbing grating preset
网格/PML 收敛扫描
```

这些留到 Stage 4 第二轮，因为当前直接法的 `linear_problem_setup` 约 90-103 s，最大 RSS 约 4 GB；继续扫参数会比较耗时。

## 快速测试

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 27 tests in 1.787s
OK (skipped=8)
```

新增测试：

```text
src/test/test_11_stage4_diffraction_modes.py
```

覆盖：

```text
zero-order catalog
large-period higher-order catalog
polarization transversality
analytic sampled modal fit
```

## h50/p1/MPI2 block grating normal

命令：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_block_grating \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_013520
```

关键结果：

| item | value |
| --- | ---: |
| mesh cells | 1176 |
| N1curl dofs | 4381 |
| Floquet constraints | 769 |
| estimated Floquet memory | 0.026 MB |
| x constraint seconds | 0.102 |
| y constraint seconds | 0.007 |
| corner resolve seconds | 0.001 |
| linear problem setup | 89.343 s |
| direct solve | 25.575 s |
| diffraction postprocess | 0.857 s |
| max RSS | 4064.5 MB |
| R_total | 9.380284e-03 |
| T_total | 1.075087e+00 |
| R+T | 1.084467e+00 |
| A_balance | -8.446713e-02 |
| top fit residual | 1.667669e-02 |
| bottom fit residual | 7.202705e-03 |

判断：

```text
能完整跑通并写出 ParaView / diffraction JSON / CSV。
Floquet 已不是内存瓶颈。
当前 R+T 偏离 1 约 8.4%，第一轮只作为 smoke，不作为精度验收。
后续应优先做 PML 厚度、probe plane、mesh refinement 和 modal port 收敛。
```

## h50/p1/MPI4 flat-layer sanity

命令：

```bash
mpiexec -n 4 python3 -m src.runners.run_3d_airbox \
  --stage-case stage4_flat_layer_sanity \
  --case normal \
  --mesh-target-size 50 \
  --nedelec-degree 1 \
  --visualization-degree 1 \
  --solver-profile direct
```

结果目录：

```text
results/3D_stage4_flat_layer_sanity_normal_p1_h50p0_np4_20260623_013244
```

关键结果：

| item | value |
| --- | ---: |
| grating source volume | 0 |
| RHS source norm | 0 |
| Floquet constraints | 769 |
| R_total | 3.373594e-02 |
| T_total | 9.662641e-01 |
| R+T | 1.000000e+00 |
| A_balance | -2.331468e-15 |
| top fit residual | 7.976109e-15 |
| bottom fit residual | 5.371332e-15 |

判断：

```text
diffraction postprocess 的 T normalization、polarization basis、FE response calibration 是正确的。
无 grating/source 时可以回到 Fresnel 0 级。
```

## h50/p1/MPI2 block grating oblique theta=10 deg

命令：

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

结果目录：

```text
results/3D_stage4_block_grating_normal_p1_h50p0_np2_20260623_013746
```

关键结果：

| item | value |
| --- | ---: |
| Floquet phase x | 1 + 3.69e-17j |
| Floquet phase y | 0.8692605 + 0.4943542j |
| Floquet constraints | 769 |
| R_total | 8.928319e-03 |
| T_total | 1.069460e+00 |
| R+T | 1.078389e+00 |
| A_balance | -7.838873e-02 |
| top fit residual | 1.703293e-02 |
| bottom fit residual | 6.630039e-03 |

判断：

```text
非零横向波矢下 Floquet 相位、corner phase 和 diffraction 输出正常。
能量平衡误差与 normal case 同量级，仍归类为第一轮粗网格/PML/边界误差。
```

## 当前结论

```text
1. Stage 4 主线已经跑通。
2. Floquet 约束构建不再是 OOM 风险点；h50/p1 下约束内存估计只有 0.026 MB。
3. direct solver 仍是主要耗时和内存来源。
4. diffraction 后处理已通过 flat-layer sanity，block grating 的能量误差更可能来自粗网格/PML/散射场边界，而不是 R/T 公式本身。
```
