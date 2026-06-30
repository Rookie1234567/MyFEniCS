# 3D 高阶 N1curl Floquet 约束验证报告

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
5. 当前只开放 Stage 2A；Stage 2B/2C/Stage 4 的 p=2 Floquet 会继续明确报 `NotImplementedError`，等 Stage 2A 稳定后再接入。

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

1. p=2 只正式支持 `stage_case="floquet_airbox"`。
2. p=3/p=4 还没有开放，但可以复用 p=2 trace block 框架继续扩展。
3. Stage 2B/2C 和 Stage 4 还没有启用 p=2 Floquet；后续接入前需要分别跑 PML、Fresnel、grating 的独立验证。
4. 当前 p=2 face block 在已测结构化 hexa 上表现为 signed permutation，所以 `max_masters_per_slave=1`；代码仍按一般局部 block 形式写，后续更高阶时可支持多 master 小矩阵。
