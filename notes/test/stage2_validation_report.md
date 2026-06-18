# Stage 2 验证报告

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

## 2026-06-18 更新：待补跑清单

上一轮文档明确留下三项未完成实跑：

```text
fresnel_interface smoke test
floquet_airbox MPI 2 h300
pml_airbox MPI 2
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
| 2026-06-18 | fresnel_interface smoke | 待跑 | 待更新 | 2C 尚未实跑 |
| 2026-06-18 | floquet_airbox MPI 2 h300 | 待跑 | 待更新 | 2A 并行细一点的 smoke |
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
