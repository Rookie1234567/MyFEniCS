# Stage 2 验证报告

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
  判定：未完成，暂停后续 MPI/PML 实跑
```

这说明当前 Stage 2 的结论应写成：

```text
2A Floquet 约束构造仍有机器精度级 face mismatch 证据；
2B PML 指标代码已改为数值拟合，但 MPI 2 尚未补跑；
2C Fresnel 路径可运行，但 R/T 与解析值严重不一致，不能验收。
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
fresnel_interface smoke test  已补跑 s/p，但物理未通过
floquet_airbox MPI 2 h300     已尝试，5 分钟超时
pml_airbox MPI 2              尚未跑，因 MPI h300 超时后按中断规则暂停
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
| 2026-06-18 | pml_airbox MPI 2 | 待跑 | 待更新 | 2B 并行 smoke |

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
