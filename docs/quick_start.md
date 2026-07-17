# 快速开始

本文件保留全局 Docker/benchmark 最短命令。按功能使用 PyCharm preset、参数含义、输出和错误定位，请从 [`../notes/quick_start/README.md`](../notes/quick_start/README.md) 进入；理论与代码导读分别见 `notes/theory/README.md` 和 `notes/reference/code_walkthrough.md`。

## 1. 先确认边界

本项目必须使用 complex-mode PETSc。普通 2D/3D CLI 默认继续写入 `results/` 并使用既有 direct 求解器；正式 benchmark 必须显式写入 `benchmarks/artifacts/`。Task28 没有把迭代法设为普通默认。

当前 Stage4 Docker 环境状态为 `qualified_local_image`，原因和 clean machine 恢复步骤见 `docker/STAGE4_ENVIRONMENT.md`。

## 2. Windows PowerShell 构建环境

在仓库根目录运行：

```powershell
docker build -f docker/Dockerfile.stage4 -t myfenics-stage4:task28 .
docker run --rm myfenics-stage4:task28 python -c "from petsc4py import PETSc; import dolfinx_mpc, gmsh; print(PETSc.ScalarType, gmsh.__version__)"
```

预期包含 `numpy.complex128`。以下命令都把当前仓库挂载到容器 `/work`：

```powershell
$Repo = (Get-Location).Path
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 python -m compileall -q src benchmarks
```

## 3. 最快 2D 物理闭环

这是实际验证使用的单案例组合：TM、manual Floquet、auxiliary DtN、零折射率对比。不要使用默认的 `all/both/all` 组合代替它。

```powershell
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 python -m src.runners.run_cases --formulation port_total --constraint-backend manual --port-boundary-model dtn --port-dtn-assembly auxiliary --polarization-type TM --nedelec-degree 1 --visualization-degree 1 --period-x 10 --air-height 5 --substrate-thickness 5 --grating-width 5 --grating-height 2 --lambda0 13.5 --n-air 1 --n-substrate 1 --n-grating 1 --mesh-target-size 2 --no-generate-png-plots --results-root benchmarks/artifacts/quick_start/2d
```

验收：reduced residual 约为 `1e-15`，且 `R+T` 接近 1。该案例通常少于 15 秒、低于 1 GB。

## 4. 最快 3D sanity

```powershell
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 mpiexec -n 2 python -m src.runners.run_3d_cases --stage-case stage1_airbox --case normal --nedelec-degree 1 --visualization-degree 1 --period-x 10 --period-y 10 --air-height 5 --substrate-thickness 5 --mesh-target-size 5 --results-root benchmarks/artifacts/quick_start/3d_stage1
```

验收：`linear_system_relative_residual` 接近机器精度。Task28 参考运行约 10 秒、总峰值 RSS 约 0.53 GB。

## 5. 普通 direct Stage4

普通用户可省略 `--results-root`，此时仍写 `results/`。下面是 benchmark 隔离输出版本：

```powershell
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 mpiexec -n 4 python -m src.runners.run_3d_cases --stage-case stage4_block_grating --case oblique --nedelec-degree 2 --visualization-degree 2 --period-x 50 --period-y 25 --air-height 130 --substrate-thickness 10 --grating-width-x 17 --grating-width-y 25 --grating-height 120 --incident-theta-deg 80 --incident-phi-deg 0 --polarization-kind s --stage4-boundary-model dtn_port --stage4-dtn-order-policy auto_propagating --no-diffraction-compute-modal-diagnostic --mesh-target-size 5 --results-root benchmarks/artifacts/direct
```

| 网格 | Task28 direct 参考时间 | 总峰值 RSS | 建议 |
|---:|---:|---:|---|
| h=5 nm | 约 29 s | 2.29 GB | 快速交叉验证 |
| h=3 nm | 约 86 s | 8.18 GB | 当前 14 GB 环境可运行 |
| h=2 nm | 约 1666 s（历史 MPI8） | 约 20.53 GB | 默认脚本跳过，当前机器不要运行 |

`benchmarks/scripts/run_level3_direct.sh` 默认只跑 h=5/3；只有显式传入 `--include-resource-heavy-h2` 才会尝试 h=2。

## 6. Workstation 迭代求解

```powershell
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 mpiexec -n 4 python -m benchmarks.run_workstation_iterative --config benchmarks/configs/workstation_p2.json --h-nm 2 --results-dir benchmarks/artifacts/iterative --record benchmarks/records/workstation_p2_h2_mpi4.json
```

只有 `theta=80 deg`、`lambda=13.5 nm`、p=2、h=5/3/2、MPI4 和固定 JSON profile 属于已 qualification 范围。偏离时 runner 会打印警告并把 `qualified_profile` 写成 false，不能自动宣称 production pass。

| 网格 | 迭代数 | Task28 总时间 | 总峰值 RSS |
|---:|---:|---:|---:|
| h=5 nm | 1201 | 127 s | 1.99 GB |
| h=3 nm | 993 | 412 s | 5.08 GB |
| h=2 nm | 1804 | 2539 s | 13.08 GB |

## 7. 自动验收

```powershell
docker run --rm -v "${Repo}:/work" -w /work myfenics-stage4:task28 python -m benchmarks.check_benchmarks
```

checker 从 manifest 和 canonical records 重新计算三残差一致性、三网格迭代比、direct/iterative R/T/A 差、h=2 RSS、benchmark ID、KSP/coarse、physical model、actual/canonical artifact provenance、case-contained files、Case002 双解和 Case003 lossy regression。Task28 Response V3 为 `143/143`；任何 Gate 失败都会返回非零退出码。

## 8. 在哪里看结果

| 内容 | 目录 | Git |
|---|---|---|
| 普通完整场、网格、日志 | `results/` | 忽略 |
| benchmark 完整场和重型产物 | `benchmarks/artifacts/` | 忽略 |
| 轻量 benchmark 摘要 | `benchmarks/records/` | 跟踪 |
| 自动汇总 | `benchmarks/benchmark_summary.csv` | 跟踪 |

3D 普通结果中的 `run_summary.json` 看 `linear_system_relative_residual`、`total_peak_rss_gb` 和 official R/T/A。迭代 record 必须同时看 `reported_relative_residual`、`condensed_true_residual` 与 `full_augmented_true_residual`；三者通过后才允许读取 `official_rta`。

ParaView 打开 `.pvd` 或 `.vtu`；MPI 输出优先打开 `fields_3d_for_paraview_parallel.pvd`。这些文件只存在于 ignored artifact 目录。

## 9. 常见错误

| 现象 | 原因 | 处理 |
|---|---|---|
| `PETSc.ScalarType` 是 float64 | 使用了 real PETSc | 重新构建 `Dockerfile.stage4` 并检查 complex 环境变量 |
| `No module named gmsh` | 使用旧 Task27 镜像 | 使用统一 Stage4 镜像 |
| nonlocal DtN 拒绝 `mpc_official` | 2D DtN 组合不支持 | 使用 Quick Start 中的 `manual + auxiliary DtN` |
| h=2 direct OOM | 预计超过 20 GB | 使用 MPI4 workstation iterative |
| 有 R/T/A 但 residual 未通过 | 非正式场 | 丢弃该 R/T/A，不得作为 official |
| benchmark 写入 `results/` | 忘记 output root | 使用 scripts 或显式 `--results-root benchmarks/artifacts/...` |
| 复基座 T 被判为 0 | 旧代码把 complex beta 当 evanescent | 使用 Response V2 后代码；official 功率应在实际端口平面评价 |

## 10. Task33 高阶 Floquet 与 Hybrid fixed-p 收口

Task33 不改变普通 `src/main.py` 默认路径。Case090/091 的 clean-source、
14 GiB Gate、QEP/Hybrid watchdog、fixed-p D1/D2 与 reduced-scope checker
命令见
[`../notes/quick_start/60_task033_high_order_hybrid_hp.md`](../notes/quick_start/60_task033_high_order_hybrid_hp.md)。
该笔记中的 graded-h/adaptive、buffer 与 1 TiB 命令是研究分支历史和下一任务
重启材料，不属于 master 可执行能力。

最安全的当前入口是只读 planning checker：

```powershell
docker run --rm --memory 14g -v "${Repo}:/work" -w /work myfenics-stage4:task28 \
  python -m benchmarks.run_task033_reduced_scope_completion --verify
```

该命令验证 Review V6 接受的 reduced scope。历史
`python -m benchmarks.check_task033 --require-formal` 只用于原 21-role full scope；
其 committed manifest 继续是 `NOT_RUN`，不能用来否定或升级 reduced-scope 记录。

原 full-scope `--require-formal` 返回 2 是正确行为：committed formal manifest
仍为 `NOT_RUN`。这不否定 reduced scope completion；两套 checker 分别回答
“Review V6 缩减范围是否完成”和“原始 21-role 全范围是否完成”，不得混用。
