# Task034 WSL 原生环境与扩展 MPI 资格化

## 1. 结论

在 clean source
`8440bbaf42de9d633479d0ed65bdda544bd871ef` 上执行的正式结构化资格化结果为：

```text
environment_gate_pass
```

Task034 正式环境集合 MPI1/2/4/8/16 全部通过；按工作站 48 物理核能力额外执行的
MPI32 也通过，但严格标记为 `exploratory`。MPI32 不替代补充任务书要求的 MPI16，
不声明加速，也尚不构成 MPI1/MPI32 代表性 PDE 数值一致性证据。

## 2. 执行身份

| 项目 | 正式值 |
|---|---|
| host | WSL2 Ubuntu 24.04 native |
| kernel | `6.18.33.2-microsoft-standard-WSL2` |
| source before/after | `8440bbaf42de9d633479d0ed65bdda544bd871ef` |
| worktree before/after | clean，包括 nonignored untracked |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python`，3.12.3 |
| MPI | Open MPI 4.1.6 |
| PETSc | 3.19.6，`complex128`，32-bit Int |
| SLEPc / slepc4py | PEP 可创建 / 3.19.2 |
| DOLFINx | 0.10.0.post2 |
| dolfinx_mpc | complex ABI probe 通过 |
| 可用物理核 | 48 |
| Docker | 未参与 |
| threads per rank | 1 |

历史分支 `origin/agent/wsl-environment-qualification` 的 bootstrap 报告只作为只读背景；
本结论来自 Task034 正式分支 clean SHA 上的结构化运行，没有把历史 bootstrap 冒充
完整 Phase A。

## 3. MPI 与 ABI Gate

| MPI ranks | 身份 | 启动 | rank 数完整 | Python/ABI | 库文件身份 | MUMPS/PEP |
|---:|---|---|---|---|---|---|
| 1 | formal | PASS | 1/1 | PASS | PASS | N/A |
| 2 | formal | PASS | 2/2 | PASS | PASS | N/A |
| 4 | formal | PASS | 4/4 | PASS | PASS | N/A |
| 8 | formal | PASS | 8/8 | PASS | PASS | PASS |
| 16 | formal | PASS | 16/16 | PASS | PASS | PASS |
| 32 | exploratory | PASS | 32/32 | PASS | PASS | PASS |

每个 rank 均记录并 hash 绑定 `mpi4py.MPI`、`petsc4py.PETSc`、
`slepc4py.SLEPc`、`dolfinx.cpp` 和 `dolfinx_mpc.cpp` 的绝对 `.so` 路径、
文件 SHA-256 与规范化 `ldd` 依赖。所有 MPI size 的 rank library identity
签名均为：

```text
1432cc9dda87762618c48898e344de03e1f327f7c0465d57c1b4828b5793bfc4
```

因此本次运行没有 Windows/WSL Python 混用，也没有多个 MPI ABI 混入。

## 4. 分布式求解器 microfixture

MPI8、MPI16 和探索性 MPI32 均执行：

1. PETSc `KSP=PREONLY`、`PC=LU`、factor solver `MUMPS` 的分布式对角系统；
2. SLEPc PEP TOAR 的良态二次多项式特征值问题。

| MPI ranks | MUMPS 解最大绝对误差 | PEP 预期根绝对误差 | PEP relative error |
|---:|---:|---:|---:|
| 8 | `1.1102230246251565e-16` | `4.000254488572078e-15` | `6.397388025438171e-13` |
| 16 | `1.1102230246251565e-16` | `2.0088577217000577e-15` | `6.513691294471371e-13` |
| 32 | `2.220446049250313e-16` | `5.995206263446584e-15` | `1.076777109383444e-12` |

固定阈值分别为 `1e-12`、`1e-8`、`1e-8`，未放宽。32 ranks 小于 48 个可用
物理核，因此没有 oversubscription。

## 5. 原始证据

原始详细 JSON/Markdown 保留在 gitignored 工件目录，Git 只提交紧凑记录：

| 工件 | SHA-256 |
|---|---|
| `benchmarks/artifacts/task034/phase_a/8440bba/wsl_extended_mpi_qualification.json` | `2f51282aa5eabc8dadf34da4a306adf775202dc21b5459ad2e2460911e3a2d32` |
| `benchmarks/artifacts/task034/phase_a/8440bba/wsl_extended_mpi_qualification.md` | `cf96ef59f9980112bc1cc0a36c2f1dc2af4d7cb4faf983c9c96d0f84c0d2b62d` |

紧凑记录：
`benchmarks/cases/092_workstation_wsl_adaptive_scalability/records/wsl_extended_mpi_qualification.json`。

## 6. 测试

实现提交前的同内容源状态已通过：

```text
focused: 25 passed
full suite: 432 passed, 18 skipped in 282.60s
targeted Ruff: PASS
git diff --check: PASS
```

全仓 `ruff check .` 的历史 15 项失败仍仅位于未改动旧文件，不属于本次资格化改动；
本次 changed files 的 targeted Ruff 全部通过。

## 7. 边界与下一步

本记录证明 WSL native、complex PETSc/SLEPc、MUMPS 和扩展 MPI 环境可用；它不替代
Phase A 的项目级 Floquet/QEP/cache/matching-trace 分层回归，也不替代 Phase F
固定几何 PDE 数值 Gate。Task034 后续仍按正式 MPI1/MPI8/MPI16 矩阵推进，并只增加
一个资源安全代表性 PDE anchor 的 MPI1/MPI32 数值一致性对照，以满足“少量证明”
而不扩张 MPI32 重型矩阵。
