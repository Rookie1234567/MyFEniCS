# Stage 2 验证报告

## 2026-06-18 更新：继续定位后的结论

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
| 2026-06-18 | compileall | `python3 -m compileall -q src` | 通过 | Docker complex 环境 |
| 2026-06-18 | Level 0-3 单元测试 | `python3 -m unittest discover -s src/test -p "test_*.py"` | 通过 | 19 tests, skipped 7 PDE |
| 2026-06-18 | fresnel_interface smoke s | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | fresnel_interface smoke p | serial, p1, h700 | 未通过 | 程序完成，但 R/T 偏差大 |
| 2026-06-18 | floquet_airbox MPI 2 h300 | normal, p1, h300 | 超时未完成 | 只生成 mesh 文件，无 summary |
| 2026-06-18 | pml_airbox MPI 2 h900 | p1 | 路径通过/物理未通过 | mismatch 约 0.51 |
| 2026-06-18 | Fresnel 收敛定位 | serial, s, p2, h150 | 趋势通过 | R/T=0.0373/0.9408 |
| 2026-06-18 | Fresnel+Floquet+PML | serial, s, p2, h300 | smoke 通过 | R/T=0.0187/0.9357 |
| 2026-06-18 | floquet MPI 2 h900 | p1 | 路径通过 | mismatch 约 1e-15 |
| 2026-06-18 | floquet MPI 2 h500 | p1 | 未通过 | mismatch 约 0.57/0.68 |
| 2026-06-18 | pml MPI 2 h900 | p1 | 路径通过/物理未通过 | mismatch 约 0.51 |

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
