# Stage 2 验证报告

## 2026-06-19 更新：MPI Floquet side-wide 约束修复后的验证结果

额度恢复后已经补跑上一轮未完成的验证。`src/constraints/floquet_3d.py` 现在在 MPI 下不再逐三角面配对，而是对整张周期侧面拟合一个 Nedelec slave-to-master 变换。这样可以避开 `create_box` 在相对侧面使用不同三角剖分时造成的 facet pairing 错误。

本轮已完成验证：

```text
compileall + 默认 unittest:
  Ran 19 tests, OK, skipped=7

floquet_airbox normal, MPI 2, p1, h500:
  result_dir = results/3D_floquet_airbox_normal_p1_h500p0_np2_20260618_231036
  elapsed = 3.412 s, max_rss = 310.9 MB
  floquet_x/y mismatch = 1.18e-15 / 1.34e-15
  判定：通过，已修复之前 h500 mismatch 约 0.57/0.68 的问题

floquet_airbox normal, MPI 2, p1, h300:
  result_dir = results/3D_floquet_airbox_normal_p1_h300p0_np2_20260618_231101
  elapsed = 3.084 s, max_rss = 310.7 MB
  floquet_x/y mismatch = 3.75e-15 / 4.72e-15
  判定：通过，已修复之前 h300 超时且无 summary 的问题

pml_airbox normal, MPI 2, p1, h900:
  result_dir = results/3D_pml_airbox_normal_p1_h900p0_np2_20260618_231124
  elapsed = 83.406 s, max_rss = 2672.8 MB
  floquet_x/y mismatch = 6.20e-16 / 7.13e-16
  pml_reflection_proxy = 0.8223
  pml_decay_ratio_bottom = 0.0561
  判定：并行 Floquet 约束通过；PML 路径可作为 2B MPI smoke，但 PML proxy 还不能作为最终吸收性能验收

fresnel_interface normal s, serial, p2, h300, Floquet+PML:
  result_dir = results/3D_fresnel_interface_normal_p2_h300p0_20260618_231312
  elapsed = 187.920 s, max_rss = 3344.7 MB
  floquet_x/y mismatch = 2.22e-15 / 2.27e-15
  R/T/R+T = 0.018669 / 0.935656 / 0.954324
  Fresnel analytic R/T = 0.033736 / 0.966264
  判定：串行回归与上一轮一致；仍属于粗网格 smoke，不是最终定量验收
```

当前结论：

```text
1. Stage 2 的 MPI Floquet 约束路径已经从“h500/h300 不可靠”修正为“h500/h300 smoke 通过”。
2. pml_airbox MPI 2 h900 的 Floquet mismatch 已恢复到约 1e-15，说明 PML case 的并行周期约束不再是主要问题。
3. Fresnel+PML 的定量误差仍需后续做更细网格或更稳后处理扫描；本轮没有把它标记为最终通过。
4. 后续可以继续 Stage 2 参数扫描，但应优先控制 p2/h150 以下的内存压力。
```

## 2026-06-18 历史记录：继续定位后的结论

按新规则，本轮没有因为超时或物理误差暂停，而是继续定位。

关键修正：

```text
3D 串行 mesh builder 改为 z 方向显式包含 physical_z_min、interface_z、physical_z_max。
MPI 下暂时回退到 dolfinx.mesh.create_box，避免当前 Docker/DOLFINx 栈中自定义分布式 mesh segfault。
PDE 测试默认参数从 p1/h700 调整为 p2/h300。
```

Fresnel 定位结果：

```text
无 PML、无 Floquet，normal s：
  p1 h300: R/T = 0.526980 / 0.048783，未通过
  p2 h300: R/T = 0.061439 / 1.229299，明显改善但 T 偏高
  p2 h200: R/T = 0.062094 / 0.964772，T 接近解析，R 偏高
  p2 h150: R/T = 0.037266 / 0.940779，R 接近解析，R+T=0.978

加回 Floquet、无 PML，p2 h300：
  Floquet mismatch ≈ 1e-15
  R/T = 0.018938 / 0.955782，R+T=0.9747

加回 Floquet + PML，p2 h300：
  Floquet mismatch ≈ 2e-15
  R/T = 0.018669 / 0.935656，R+T=0.9543
  PML bottom decay ratio = 0.0762
```

当前判断：

```text
2C Fresnel 串行路径不是公式完全错误，而是 p1/h700 太粗且旧网格没有对齐界面/PML入口。
p2/h150 无 PML/Floquet 已经表现出合理收敛趋势。
p2/h300 加 Floquet/PML 可作为粗网格 smoke，但还不是最终定量验收。
```

MPI 定位结果：

```text
floquet_airbox MPI 2 h900:
  completed，Floquet mismatch ≈ 4e-16，输出 parallel.pvd

floquet_airbox MPI 2 h500:
  completed，但 Floquet mismatch ≈ 0.57 / 0.68，不能验收

floquet_airbox MPI 2 h300:
  5 分钟超时，无 summary

pml_airbox MPI 2 h900:
  completed，但 Floquet mismatch ≈ 0.51 / 0.51，只能算路径 smoke，不能算物理通过
```

当前判断：

```text
MPI 运行路径已恢复，不再 segfault。
但是 3D MPI Floquet 低层约束只在极小 h900 网格可靠；h500 已出现明显 mismatch，h300 性能超时。
后续需要专门优化/修正 3D MPI Floquet facet pairing 和 probe transform。
```

## 2026-06-18 更新：2C smoke 已跑通但未通过，MPI h300 超时

本轮补跑结果：

```text
fresnel_interface normal s, p1, h700, direct, serial
  case_status = completed
  R_total/T_total = 0.584166 / 0.311086
  Fresnel R/T     = 0.0337359 / 0.966264
  R/T error       = 0.550430 / 0.655178
  relative E err  = 1.93276
  elapsed/RSS     = 64.96 s / 2672 MB
  判定：路径跑通，但 2C 物理未通过

fresnel_interface normal p, p1, h700, direct, serial
  case_status = completed
  R_total/T_total = 0.900598 / 0.286458
  Fresnel R/T     = 0.0337359 / 0.966264
  R/T error       = 0.866862 / 0.679806
  relative E err  = 1.88091
  elapsed/RSS     = 60.75 s / 2674 MB
  判定：路径跑通，但 2C 物理未通过

floquet_airbox normal, MPI 2, p1, h300, direct
  第一次命令使用 OpenMPI 参数 --allow-run-as-root，被 MPICH/Hydra 拒绝。
  第二次改用 mpiexec -n 2，5 分钟超时。
  结果目录只生成 mesh_3d.h5 和 mesh_3d.xdmf，没有 run_summary.json。
  判定：未完成；后续已继续用 h900/h500 定位
```

这条历史记录之后，本轮已经继续定位。更新后的当前结论见本文最上方。

```text
2C 串行 Fresnel 已有收敛趋势；
2B PML MPI h900 已补跑但只能算路径 smoke；
3D MPI Floquet 在 h500/h300 仍需修正。
```

## 2026-06-18 更新：默认测试已通过，PDE/MPI 待补跑

已运行：

```bash
python3 -m compileall -q src
python3 -m unittest discover -s src/test -p "test_*.py"
```

结果：

```text
Ran 19 tests in 0.009s
OK (skipped=7)
```

解释：

```text
Level 0-3 默认严格测试已通过。
Level 4-10 是 PDE/综合测试入口，默认跳过，需要 RUN_STAGE2_PDE_TESTS=1 或单独 Docker/MPI 命令。
```

## 2026-06-18 更新：上一轮遗留项及本轮处理状态

上一轮文档明确留下三项未完成实跑，本轮处理状态如下：

```text
早期 fresnel_interface p1/h700 已补跑 s/p，但物理未通过；p2/h150 串行已有收敛趋势
floquet_airbox MPI 2 h300     已尝试，5 分钟超时
pml_airbox MPI 2              h900 已跑通，但 Floquet mismatch 大，只能算路径 smoke
```

本轮还新增十层测试框架。结果会按“先公式、再 PDE、最后 MPI/扫描”的顺序补充到本文件顶部。

## 当前测试命令

编译检查：

```bash
python3 -m compileall -q src
```

默认单元测试：

```bash
python3 -m unittest discover -s src/test -p "test_*.py"
```

PDE 小算例测试：

```bash
RUN_STAGE2_PDE_TESTS=1 python3 -m unittest discover -s src/test -p "test_*.py"
```

## 结果表

| 时间 | 测试 | 参数 | 结果 | 备注 |
|---|---|---|---|---|
| 2026-06-19 | compileall + Level 0-3 单元测试 | `python3 -m compileall -q src && python3 -m unittest discover -s src/test -p "test_*.py"` | 通过 | 19 tests, skipped 7 PDE |
| 2026-06-19 | floquet_airbox MPI 2 h500 | normal, p1, h500 | 通过 | mismatch=1.18e-15/1.34e-15 |
| 2026-06-19 | floquet_airbox MPI 2 h300 | normal, p1, h300 | 通过 | mismatch=3.75e-15/4.72e-15 |
| 2026-06-19 | pml_airbox MPI 2 h900 | normal, p1, h900 | smoke 通过 | mismatch=6.20e-16/7.13e-16，bottom decay=0.0561 |
| 2026-06-19 | Fresnel+Floquet+PML 回归 | serial, s, p2, h300 | smoke 通过 | R/T=0.0187/0.9357，仍需定量扫描 |
| 2026-06-18 | compileall | `python3 -m compileall -q src` | 通过 | Docker complex 环境 |
| 2026-06-18 | Level 0-3 单元测试 | `python3 -m unittest discover -s src/test -p "test_*.py"` | 通过 | 19 tests, skipped 7 PDE |
| 2026-06-18 | fresnel_interface smoke s | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | fresnel_interface smoke p | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | floquet_airbox MPI 2 h300 | normal, p1, h300 | 历史未完成 | 修复前只生成 mesh 文件，无 summary |
| 2026-06-18 | pml_airbox MPI 2 h900 | p1 | 历史 smoke | 修复前 mismatch 约 0.51 |
| 2026-06-18 | Fresnel 收敛定位 | serial, s, p2, h150 | 趋势通过 | R/T=0.0373/0.9408 |
| 2026-06-18 | Fresnel+Floquet+PML | serial, s, p2, h300 | smoke 通过 | R/T=0.0187/0.9357 |
| 2026-06-18 | floquet MPI 2 h900 | p1 | 路径通过 | mismatch 约 1e-15 |
| 2026-06-18 | floquet MPI 2 h500 | p1 | 历史未通过 | 修复前 mismatch 约 0.57/0.68 |
| 2026-06-18 | pml MPI 2 h900 | p1 | 历史 smoke | 修复前 mismatch 约 0.51 |

## 判定口径

`case_status=completed` 只说明线性求解和后处理没有崩溃，不代表物理已经验收。

Stage 2 真正验收需要同时看：

```text
relative_max_abs_E_error
floquet_x_face_mismatch / floquet_y_face_mismatch
pml_reflection_proxy / pml_decay_ratio_*
R_total / T_total / R_plus_T
fresnel_R_error / fresnel_T_error
max_rss_mb / elapsed_seconds
```

如果 PDE 误差偏大，本文件必须标记为“未通过/待定位”，不能因为程序跑完就写成通过。
