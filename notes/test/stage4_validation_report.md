# Stage 4 验证报告

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
