# Task034 环境与基线

## 结论

Task034 从指定的 clean `master` 建立独立执行分支，WSL 原生环境资格化通过，未使用此前 bootstrap 分支冒充 Phase A，也未合并 `master`。

```text
task034_addendum_loaded = true
phase_order_uses_fixed_geometry_benchmark_before_adaptive = true
mpi_matrix = [1, 8, 16]
case093_planned = true
```

## Git 与任务身份

| 字段 | 值 |
|---|---|
| 工作目录 | `/home/Projects/MyFEniCS` |
| base / `origin/master` | `82a5107b5c2bfe4c466a0d00ead31d7b172e2af4` |
| 正式分支 | `codex/20260717-task34-workstation-wsl-adaptive-scalability` |
| 建分支前状态 | `HEAD == origin/master`，无 tracked 修改、无 nonignored untracked 文件 |
| bootstrap 报告 | 只读检查 `origin/agent/wsl-environment-qualification:docs/workstation_wsl_environment_qualification.md` |
| task/addendum | 均完整读取；补充任务书优先于冲突的旧范围 |
| merge | 未合并 `master`；等待 ChatGPT review 后逐文件 selective merge |

## WSL 原生环境矩阵

| 组件 | 正式值 | 判定 |
|---|---|---|
| OS / kernel | Ubuntu 24.04 / Linux 6.18.33.2 WSL2 | pass |
| Python | 3.12.3 | pass |
| OpenMPI | 4.1.6 | pass |
| PETSc | 3.19.6，complex128，32-bit `PetscInt` | pass |
| SLEPc | 3.19.2 | pass |
| DOLFINx | 0.10.0.post2 | pass |
| `dolfinx_mpc` | import/smoke pass | pass |
| CPU | 48 physical cores | inventory |
| memory/swap | 约 228 GiB / 32 GiB；正式作业要求 job swap=0 | pass |
| MPI | 1/2/4/8/16 正式；32 exploratory | pass / exploratory |
| MUMPS / PEP | native microfixtures | pass |
| MPI identity signature | `1432cc...` | pass |

完整命令、ABI、cgroup、微测试和正式 MPI 记录见 `outcomes/wsl_environment_qualification.md`。环境、source-clean 和 ABI Gate 均在首个重型 PDE 前通过。

## 范围覆写

用户批准以 S polarization 为生产与收敛主线；P polarization 仅做 p2/h5 MPI8 Full3D 与 Hybrid M160 能力证明；不运行 p1。MPI 数值一致性仅选 p3/h5 S 代表案例覆盖 MPI1/8/16，MPI32 只作 exploratory。该范围调整没有改变 true residual、official R/T/A、资源停止条件或任何数值阈值。
