# Stage 4 验证报告

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
