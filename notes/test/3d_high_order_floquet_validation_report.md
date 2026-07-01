# 3D 高阶 N1curl Floquet 约束验证报告

## 2026-07-01 更新：Stage 4B block grating p=2 已开放并完成第一轮 smoke

本轮把 `topological_trace_p2` 正式扩展到 `stage4_block_grating`。实现边界如下：

```text
支持：hexahedron + N1curl degree=2 + topological_trace_p2
仍拒绝：p>=3、tetra、dense/probe/pinv Floquet
```

代码层新增：

```text
floquet_3d.py:
  stage4_block_grating 加入 p=2 allow-list
  summary/log 新增 face transform fit count 和 max residual

mesh_builder_3d.py:
  Stage 4 hexa guard 从 “仅 p1/Stage4A p2” 改成允许 p1/p2，p>=3 继续报错

diagnose_p2_mpc_constraints.py:
  新增 --stage-case stage4_block_grating，用同一诊断脚本检查真实 grating 网格 trace 约束
```

### 基础测试

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 54 tests in 1.840s
OK (skipped=10)
```

### p=2 Floquet 约束残差诊断

命令：

```bash
mpiexec -n 2 python3 -m src.test.diagnose_p2_mpc_constraints
mpiexec -n 4 python3 -m src.test.diagnose_p2_mpc_constraints
mpiexec -n 2 python3 -m src.test.diagnose_p2_mpc_constraints --stage-case stage4_block_grating
mpiexec -n 4 python3 -m src.test.diagnose_p2_mpc_constraints --stage-case stage4_block_grating
```

结果摘要：

| case | MPI | x_edge bad | x_face bad | y_edge bad | y_face bad | corner bad | max residual |
|---|---:|---:|---:|---:|---:|---:|---:|
| Stage4A flat | 2 | 0 | 0 | 0 | 0 | 0 | 5.38e-13 |
| Stage4A flat | 4 | 0 | 0 | 0 | 0 | 0 | 5.38e-13 |
| Stage4B block mesh | 2 | 0 | 0 | 0 | 0 | 0 | 5.89e-13 |
| Stage4B block mesh | 4 | 0 | 0 | 0 | 0 | 0 | 8.71e-13 |

### PDE smoke 与验证闸门

| case | 参数 | MPI | dofs | constraints(edge/face) | R | T | R+T | 结论 |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Stage2A Floquet airbox | h100, p2, oblique | 1 | 7552 | 436 / 396 | - | - | - | 回归通过，场误差保持粗网格量级 |
| Stage4A flat sanity | lambda633, h20, p2, zero_order | 2 | 5676 | 356 / 320 | 9.209129e-13 | 1.000000e+00 | 1.000000e+00 | 长波 flat sanity 通过 |
| Stage4A flat EUV | lambda13.5, h10, p2, zero_order | 4 | 39270 | 1270 / 1200 | 1.411951e-01 | 8.588049e-01 | 1.000000e+00 | 与 4B0 对照用；不是物理收敛结论 |
| Stage4B zero contrast | lambda13.5, h10, p2, zero_order, n_sub=1, n_grating=1 | 4 | 47242 | 1394 / 1320 | 1.411951e-01 | 8.588049e-01 | 1.000000e+00 | 与同参数 Stage4A flat 数值一致 |
| Stage4A flat EUV | lambda13.5, h7.5, p2, zero_order | 4 | 105154 | 2450 / 2352 | 9.774197e-01 | 2.258031e-02 | 1.000000e+00 | 粗网格/端口数值诊断，不作为物理结论 |
| Stage4B zero contrast | lambda13.5, h7.5, p2, zero_order, n_sub=1, n_grating=1 | 4 | 120342 | 2622 / 2520 | 9.774197e-01 | 2.258031e-02 | 1.000000e+00 | 与同参数 Stage4A flat 数值一致 |
| Stage4B weak contrast | lambda13.5, h10, p2, zero_order, n_sub=1, n_grating=1.05 | 4 | 47242 | 1394 / 1320 | 1.117768e-01 | 8.107075e-01 | 9.224842e-01 | 路径可求解，R+T 未超过 1 |
| Stage4B real block | lambda13.5, h10, p2, zero_order, n_sub=1.45, n_grating=2.0 | 4 | 47242 | 1394 / 1320 | 3.545681e-01 | 2.644273e-01 | 6.189955e-01 | 路径可求解，R+T 未超过 1 |
| Stage4B real block | lambda13.5, h20, p2, auto_propagating | 4 | 12030 | 550 / 504 | 9.999613e-01 | 3.873717e-05 | 1.000000e+00 | 多级 DtN 主线可组装运行，1068 auxiliary modes |

### 当前判断

1. `stage4_block_grating + p=2` 的 Floquet 约束、MPI ghost slave 规则、MPC finalize 和直接求解都已经打通。
2. `4B0 zero-contrast` 与同参数 `Stage4A flat` 完全一致，说明真实 grating 网格/tag 本身没有引入虚假散射。
3. EUV `lambda0=13.5 nm` 下，`h10/h7.5` 的 zero-order flat 数值仍不代表最终物理收敛；它们只是验证 Stage4B p=2 路径一致性。
4. `auto_propagating` 多衍射级 DtN 在 h20/p2/MPI4 下可以完成 1068 个辅助模态装配和求解，但 h20 对 EUV 仍很粗，不能作为最终 R/T benchmark。

下一步建议：如果要做可信 EUV 定量，应优先做 `stage4_flat_layer_sanity + auto_propagating` 的 h 收敛和端口方向/功率归一化复查，再把真实 grating 推到 h5/h2.5。

## 2026-07-01 更新：Stage 4A p=2 MPI 场污染已修复

本轮重新检查 `stage4_flat_layer_sanity + p=2 + MPI`，发现 2026-06-30 的判断不完整：Stage 4A 场污染并不是 3D zero-order DtN 的主因，而是 p=2 Floquet face-interior dof 的局部 face transform 在 MPI 分区下不满足真实 Nedelec moment 约束。

### 根因

原先 p=2 face-interior dof 使用 Basix quadrilateral permutation 小矩阵来处理周期 face 的 4 个内部切向 moment。这个做法对部分 x-face permutation 在串行下不明显，但在 MPI2/MPI4 的不同 ghost/owned face 组合下，会让解析周期场本身不满足 slave/master 系数关系。

直接诊断：

```bash
mpiexec -n 2 python3 -m src.test.diagnose_p2_mpc_constraints
mpiexec -n 4 python3 -m src.test.diagnose_p2_mpc_constraints
```

修复前曾出现：

```text
x_face bad rows > 0
max_constraint_residual 约 1e1 到 2e1
```

修复后：

```text
np2: x_edge/x_face/y_edge/y_face/corner bad = 0，最大残差约 5.4e-13
np4: x_edge/x_face/y_edge/y_face/corner bad = 0，最大残差约 5.4e-13
```

### 修复方式

保留显式拓扑配对，但 p=2 face-interior transform 改为每个周期 face 的局部 4x4 Nedelec moment fit：

```text
1. 插值固定的低阶向量多项式场；
2. 只收集周期 face-interior dof 的真实 Nedelec 系数；
3. 每个 slave/master face pair 解一个常数规模 4x4 小系统；
4. 约束仍写成 slave_i = phase * sum_j T_ij master_j。
```

这不是旧的 whole-plane probe/pinv：不会构造整张周期面的 dense transform，复杂度仍为 `O(N_trace)`，p=2 每个 face block 是固定大小。

### Stage 4A zero-order flat sanity 复测

统一参数：

```text
stage_case = stage4_flat_layer_sanity
lambda0 = 633 nm
n_substrate = 1.0
stage4_dtn_order_policy = zero_order
nedelec_degree = 2
```

| case | MPI | h (nm) | dofs | constraints | edge | face | Floquet total (s) | R | T | R+T | max Ex/Ey/Ez | 结果目录 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Stage4A flat | 2 | 20 | 5676 | 676 | 356 | 320 | 0.130 | 9.209129e-13 | 1.000000e+00 | 1.000000e+00 | 2.78e-12 / 1.00e+00 / 2.76e-12 | `results/3D_stage4_flat_layer_sanity_normal_p2_h20p0_np2_20260701_032458` |
| Stage4A flat | 4 | 20 | 5676 | 676 | 356 | 320 | 0.118 | 9.209129e-13 | 1.000000e+00 | 1.000000e+00 | 2.80e-12 / 1.00e+00 / 2.71e-12 | `results/3D_stage4_flat_layer_sanity_normal_p2_h20p0_np4_20260701_032511` |
| Stage4A flat | 2 | 10 | 39270 | 2470 | 1270 | 1200 | 0.746 | 4.522295e-15 | 1.000000e+00 | 1.000000e+00 | 1.36e-11 / 1.00e+00 / 1.20e-11 | `results/3D_stage4_flat_layer_sanity_normal_p2_h10p0_np2_20260701_032727` |

结论：

```text
Stage 4A flat-layer sanity 的 p=2 MPI2/MPI4 已恢复与串行一致。
Stage 4B block grating 仍未开放 p=2；下一步若要开放，需要先做 block grating 的 p=2 物理验证。
```

基础测试：

```text
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"

结果：54 tests OK, 10 skipped
```

## 2026-06-30 更新：Stage 4A p=2 暂不作为通过验收

本轮复查发现，`p=2 topological_trace_p2` 在 Stage 2A `floquet_airbox` 的 serial/MPI 验证中是干净的，因此高阶 Floquet trace 配对本身不是当前主要问题。新的问题集中在 Stage 4 的 3D auxiliary DtN total-field 端口：即使在 `stage4_flat_layer_sanity, n_substrate=1.0, zero_order` 这个均匀层硬 sanity 中，端口辅助幅值给出的 R/T 也不符合 `R≈0, T≈1`。

因此当前状态改为：

```text
p=2 Floquet 可用于 Stage 2A/2B/2C 的约束机制验证。
Stage 4A p=2 仅保留为“能组装/能运行”的诊断入口，不能作为物理可信验收。
Stage 4B block grating 仍不开放 p=2。
下一步应先重推并修正 3D auxiliary DtN 的 zero-order 端口方程，再回到 p=2 Stage 4A。
```

详细续接记录见：

```text
notes/test/stage4_p2_mpi_resume_log.md
```

## 2026-06-30 更新：p=2 Stage 4A flat-layer sanity 已开放

本轮继续把 `topological_trace_p2` 从 Stage 2A/2B/2C 扩展到 Stage 4A `stage4_flat_layer_sanity`。Stage 4A 是无光栅 flat-layer + DtN total-field port sanity，用来验证二阶 Floquet trace 约束能否和 Stage 4 DtN 主线组合运行。

当前支持范围：

```text
p=1 -> topological_edges_p1
p=2 -> topological_trace_p2，可用于 floquet_airbox / pml_airbox / fresnel_interface / stage4_flat_layer_sanity
p>=3 -> NotImplementedError
stage4_block_grating -> p=2 暂未开放
```

新增运行命令：

```bash
python3 -m src.runners.run_3d_cases --stage-case stage4_flat_layer_sanity --case normal --mesh-target-size 10 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
mpiexec -n 2 python3 -m src.runners.run_3d_cases --stage-case stage4_flat_layer_sanity --case normal --mesh-target-size 10 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
```

实跑结果会继续写在本节下方；Stage 4B block grating 暂不接入 p=2，避免在 flat-layer sanity 完成前引入真实结构误差。

### Stage 4A h10 实跑结果

| case | MPI | p | h (nm) | dofs | constraints | edge | face | Floquet total (s) | R | T | R+T | max Ex/Ey/Ez | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| Stage4A flat | 1 | 2 | 10 | 39270 | 2470 | 1270 | 1200 | 0.626 | 3.223458e-01 | 6.776542e-01 | 1.000000e+00 | 3.61e-10 / 1.57e+00 / 3.58e-10 | completed |
| Stage4A flat | 2 | 2 | 10 | 39270 | 2470 | 1270 | 1200 | 0.357 | 3.228932e-01 | 6.771068e-01 | 1.000000e+00 | 7.67e-01 / 1.92e+00 / 8.58e-01 | completed |
| Stage4A p1 对照 | 1 | 1 | 10 | 5335 | 635 | 635 | 0 | 0.231 | 1.000000e+00 | 4.559376e-12 | 1.000000e+00 | 2.48e-13 / 1.49e+00 / 2.85e-13 | completed |
| Stage4A p1 对照 | 2 | 1 | 10 | 5335 | 635 | 635 | 0 | 0.142 | 1.000000e+00 | 4.559376e-12 | 1.000000e+00 | 1.72e-13 / 1.49e+00 / 2.13e-13 | completed |

结论：

1. Stage 4A p=2 已能 serial/MPI 跑通，且 `R+T` 保持 1，Floquet x/y mismatch 为 0。
2. p=2 serial/MPI 的总 R/T 差异约 `5.5e-4`，作为 smoke 可接受。
3. p=2 MPI 的场分量出现明显 Ex/Ez，而 p1 对照没有这个现象；因此 Stage4A p=2 当前只作为 Floquet/DtN 接入 smoke，不作为最终场分布可信结论。
4. `stage4_block_grating + p=2` 已确认会明确报 `NotImplementedError`，没有提前开放真实光栅。

## 2026-06-30 更新：p=2 Stage 2B/2C 已接入并完成 smoke

本轮把 `topological_trace_p2` 从 Stage 2A `floquet_airbox` 扩展到 Stage 2B `pml_airbox` 和 Stage 2C `fresnel_interface`。正式约束路径仍然是显式拓扑 trace 配对，不使用 probe / pseudo-inverse / dense side fitting。

实现状态：

```text
p=1 -> topological_edges_p1
p=2 -> topological_trace_p2，可用于 floquet_airbox / pml_airbox / fresnel_interface
p>=3 -> NotImplementedError
Stage 4 -> 本段记录产生时暂未开放 p=2 Floquet；最新状态见上方 Stage 4A 更新
```

这次还修正了 p=2 并行路径的一个风险点：全局约束只由 owning rank 发出；出现在 owned cell 上的 ghost slave 会进入本 rank 的 local MPC map，用于本地单元装配，但不会重复发出全局约束。

### 本轮命令

```bash
python -m compileall -q src

python3 -m unittest src.test.test_17_3d_high_order_floquet_trace

python3 -m src.runners.run_3d_cases --stage-case pml_airbox --case oblique --mesh-target-size 300 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
mpiexec -n 2 python3 -m src.runners.run_3d_cases --stage-case pml_airbox --case oblique --mesh-target-size 300 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
python3 -m src.runners.run_3d_cases --stage-case pml_airbox --case oblique --mesh-target-size 100 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
mpiexec -n 2 python3 -m src.runners.run_3d_cases --stage-case pml_airbox --case oblique --mesh-target-size 100 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto

python3 -m src.runners.run_3d_cases --stage-case fresnel_interface --case oblique --mesh-target-size 300 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
mpiexec -n 2 python3 -m src.runners.run_3d_cases --stage-case fresnel_interface --case oblique --mesh-target-size 300 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
python3 -m src.runners.run_3d_cases --stage-case fresnel_interface --case oblique --mesh-target-size 100 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
mpiexec -n 2 python3 -m src.runners.run_3d_cases --stage-case fresnel_interface --case oblique --mesh-target-size 100 --nedelec-degree 2 --visualization-degree 1 --floquet-constraint-mode auto
```

### Stage 2B：PML airbox p=2

| case | MPI | h (nm) | dofs | constraints | edge | face | slave faces | Floquet total (s) | E error | PML proxy | elapsed (s) | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| pml oblique | 1 | 300 | 690 | 178 | 98 | 80 | 20 | 0.021 | 4.024652e-02 | 8.933082e-19 | 255.323 | completed |
| pml oblique | 2 | 300 | 690 | 178 | 98 | 80 | 20 | 0.017 | 4.024652e-02 | 2.578250e-17 | 211.435 | completed |
| pml oblique | 1 | 100 | 11602 | 1282 | 666 | 616 | 154 | 0.190 | 4.919823e-03 | 0.000000e+00 | 766.307 | completed |
| pml oblique | 2 | 100 | 11602 | 1282 | 666 | 616 | 154 | 0.119 | 4.919823e-03 | 1.899485e-16 | 479.634 | completed |

结论：2B 的 p=2 Floquet trace 约束构建保持轻量，h100 也只需要约 0.12-0.19 秒；serial/MPI 的 E error 和约束数量一致。耗时主要来自直接法 `linear_problem_solve`，不是 Floquet 约束构建。

### Stage 2C：Fresnel interface p=2

| case | MPI | h (nm) | dofs | constraints | edge | face | Floquet total (s) | R | T | R+T | PML proxy | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| fresnel oblique | 1 | 300 | 690 | 178 | 98 | 80 | 0.023 | 2.123398e-01 | 1.051729e+00 | 1.264069e+00 | 3.744645e-01 | completed |
| fresnel oblique | 2 | 300 | 690 | 178 | 98 | 80 | 0.016 | 1.899935e-01 | 8.554535e-01 | 1.045447e+00 | 2.236888e-01 | completed |
| fresnel oblique | 1 | 100 | 11602 | 1282 | 666 | 616 | 0.185 | 8.741929e-02 | 8.612330e-01 | 9.486522e-01 | 2.880244e-01 | completed |
| fresnel oblique | 2 | 100 | 11602 | 1282 | 666 | 616 | 0.124 | 1.017348e-01 | 8.423203e-01 | 9.440551e-01 | 2.905455e-01 | completed |

结论：2C 的 p=2 高阶 Floquet 机制已经能和 Fresnel diagnostic 路径组合运行；约束数量、face constraints、mismatch 都正常。R/T 仍反映 Stage 2C 旧 incident-scattered + PML Fresnel 诊断模型本身的误差，本轮不把 2C 当作物理精确 benchmark，也不在这里修 Fresnel 物理模型。

### 测试状态

```text
python -m compileall -q src
  PASS

python3 -m unittest src.test.test_17_3d_high_order_floquet_trace
  PASS: 6 tests, 2 skipped

python3 -m unittest discover -s src/test -p "test_*.py"
  FAIL: 1 known failure in test_13_3d_stage_entrypoints
  原因：当前 src/main.py 的用户本地默认 stage_case 是 stage4_flat_layer_sanity，
       该测试仍期待 stage4_block_grating。本轮按要求未修改 src/main.py。
```

## 2026-06-30 更新：p=2 Stage 2A Floquet trace 路线已跑通

本轮实现并验证了第一版高阶 3D Floquet 约束：

```text
mesh: hexahedron
element: N1curl degree = 2
stage: Stage 2A floquet_airbox
constraint mode: topological_trace_p2
```

重要结论：

1. p=1 原路径保持为 `topological_edges_p1`，仍只配 mesh edge dof。
2. p=2 新路径为 `topological_trace_p2`，同时配 edge dof 和 face-interior tangential dof。
3. 正式路径不再使用 whole-plane probe / pseudo-inverse / dense transform。
4. p=2 face orientation 在 MPI 下会出现 rotated/reflected face order；现已通过 Basix `quadrilateral` 小矩阵组合处理。
5. 历史限制：本段记录产生时只开放 Stage 2A；最新状态见本文顶部更新。

## 实现口径

入口文件：

```text
src/constraints/floquet_3d.py
```

模式分流：

```text
auto + p=1 -> topological_edges_p1
auto + p=2 -> topological_trace_p2
p>=3      -> NotImplementedError
```

p=2 约束形式：

```text
slave_i = beta_x/beta_y/(beta_x beta_y) * sum_j T_ij master_j
```

其中：

- edge dof 使用 Basix `interval` transformation 处理 edge reversal。
- face-interior dof 使用 Basix `quadrilateral` transformation 的 D4 group 小矩阵处理 face rotation/reflection。
- corner edge dof 只约束一次，直接映射到 `(x_min, y_min)`，相位为 `beta_x * beta_y`。
- face-interior dof 没有 corner 分类，只属于 x-face 或 y-face。

## 验证命令

编译：

```bash
python -m compileall -q src
```

普通单元测试：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

新增 p=2 smoke 单元测试：

```bash
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest src.test.test_17_3d_high_order_floquet_trace
```

Stage 2A p=2 serial：

```bash
python3 -m src.runners.run_3d_cases \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

Stage 2A p=2 MPI：

```bash
mpiexec -n 2 python3 -m src.runners.run_3d_cases \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto

mpiexec -n 4 python3 -m src.runners.run_3d_cases \
  --stage-case floquet_airbox \
  --case oblique \
  --mesh-target-size 100 \
  --nedelec-degree 2 \
  --visualization-degree 1 \
  --floquet-constraint-mode auto
```

## 实跑结果

| case | MPI | p | h (nm) | constraints | edge constraints | face constraints | slave faces | Floquet setup (s) | E error | H error | max RSS (MB) | status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| p2 h100 serial | 1 | 2 | 100 | 832 | 436 | 396 | 99 | 0.129 | 4.919823e-03 | 6.989165e-02 | 400.2 | completed |
| p2 h100 MPI2 | 2 | 2 | 100 | 832 | 436 | 396 | 99 | 0.145 | 4.919823e-03 | 6.989165e-02 | 357.3 | completed |
| p2 h100 MPI4 | 4 | 2 | 100 | 832 | 436 | 396 | 99 | 0.148 | 4.919823e-03 | 6.989165e-02 | 337.6 | completed |
| p2 h300 MPI2 | 2 | 2 | 300 | 110 | 62 | 48 | 12 | 0.021 | 4.024652e-02 | 5.444023e-01 | 283.6 | completed |
| p1 h100 serial regression | 1 | 1 | 100 | 218 | 0 | 0 | 0 | 0.069 | 1.167041e-01 | 5.306181e-01 | 282.4 | completed |

结果目录：

```text
results/3D_floquet_airbox_oblique_p2_h100p0_20260630_020754
results/3D_floquet_airbox_oblique_p2_h100p0_np2_20260630_024839
results/3D_floquet_airbox_oblique_p2_h100p0_np4_20260630_024908
results/3D_floquet_airbox_oblique_p2_h300p0_np2_20260630_024803
results/3D_floquet_airbox_oblique_p1_h100p0_20260630_024935
```

## 已修复的 MPI 问题

初版 p=2 face transform 曾假设对面 face 的 oriented vertex order 完全一致。串行下这个假设成立，但 MPI 分区后会出现例如：

```text
[0, 2, 1, 3]
[2, 0, 3, 1]
```

这说明 slave face 和 master face 的局部顶点顺序发生了 quadrilateral rotation/reflection。现在通过 Basix 的 `quadrilateral` entity transformation 组合成 D4 小矩阵来处理，不回退到 dense/probe。

## 当前限制

1. 历史限制：本段记录产生时 p=2 只正式支持 `stage_case="floquet_airbox"`；最新状态见本文顶部更新。
2. p=3/p=4 还没有开放，但可以复用 p=2 trace block 框架继续扩展。
3. 历史限制：本段记录产生时 Stage 2B/2C 和 Stage 4 还没有启用 p=2 Floquet；最新状态见本文顶部更新。
4. 当前 p=2 face block 在已测结构化 hexa 上表现为 signed permutation，所以 `max_masters_per_slave=1`；代码仍按一般局部 block 形式写，后续更高阶时可支持多 master 小矩阵。
