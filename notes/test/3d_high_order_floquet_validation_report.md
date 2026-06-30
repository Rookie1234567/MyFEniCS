# 3D 高阶 N1curl Floquet 约束验证报告

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
