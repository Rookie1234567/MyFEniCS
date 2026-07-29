# Task002 M0 仓库、双硬件与环境审计

## 结论

`PASS_FOR_M1_IMPLEMENTATION`。当前环境是本地 16 GB Windows 笔记本的原生 WSL2
Ubuntu FEM 阶段；不是工作站训练阶段。Git、分支、upstream、complex ABI、MPI2、内存、
swap 和磁盘满足 M1 开发条件。M0 没有进入 Docker、没有运行 PDE、没有生成训练数据。

## Git 身份

| 字段 | 现场值 | 状态 |
|---|---|---|
| root | `/home/shenjh/Projects/MyFEniCS-Surrogate` | pass |
| git dir | `/home/shenjh/Projects/MyFEniCS-Surrogate/.git` | pass |
| origin | `https://github.com/Rookie1234567/MyFEniCS.git` | pass |
| branch | `codex/only-one-13p5nm-surrogate-inversion` | pass |
| upstream | `origin/codex/only-one-13p5nm-surrogate-inversion` | pass |
| starting HEAD | `a990fbcced913dc6492431a0ec4f027cf9a664f9` | clean |
| HEAD vs upstream | `0 / 0` | pass |
| remote master SHA | `3f334313a55786778de70965585bcaef7c997e89` | read-only fetch |
| master-only / branch-only | `1 / 43` | no merge/rebase |

单分支 clone 没有本地 `origin/master` ref，因此用本轮 `FETCH_HEAD` 只读计算相对位置；
没有创建同步提交，也没有切换、merge 或 rebase。

## 本地硬件与资源

| 字段 | 现场值 | 语义 |
|---|---:|---|
| OS/kernel | Ubuntu 24.04.4 LTS / WSL2 6.6.114.1 | Linux FEM backend |
| CPU | Intel i7-13620H，8 cores / 16 logical | local phase |
| MemTotal | 14,654,963,712 B | WSL limit |
| MemAvailable | 13,811,171,328 B | M0 snapshot |
| swap total / used | 42,949,672,960 / 0 B | swap 不计作容量 |
| repository disk available | 1,017,320,861,696 B | ext4 `/dev/sdd` |
| GPU | `nvidia-smi` unavailable in this WSL session | workstation M6 later audit |

Task001 的资源规则继续适用：hard ceiling 为 `min(10.5 GiB, 0.77*MemTotal)`，一次只允许
一个 forward solve，每 rank 一个 thread，zero swap，watchdog 只清理自身进程组。

## FEM ABI

资格化入口为 `scripts/activate_myfenics_surrogate_wsl.sh`。现场检查：

| component | identity |
|---|---|
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | repo `.venv`, 3.12.3 |
| PETSc | complex128 / int32, petsc4py 3.19.6 |
| SLEPc | slepc4py 3.19.2 |
| DOLFINx | 0.10.0.post2 |
| Basix / UFL / FFCx | 0.10.0 / 2025.2.1 / 0.10.1.post0 |
| mpi4py | 3.1.5 |

MPI2 两个 rank 均使用同一 repo Python、complex128/int32 PETSc 与 DOLFINx 0.10.0.post2。
工作站 ML 环境尚未建立；它必须在 M6 前单独冻结，不能污染当前 FEM `.venv`。

## 权威与范围 disposition

Task001 Review V3 状态为 `approved_with_scoped_solver_routing`：S scope 已关闭并授权 Task002；
Hybrid-P research 延期。Case095/096 只作为历史离散/资源 authority，Case110 的 37 个
observable-v2 pass 与 Case111 的负/direct-reference evidence 均保持不变。Task002 必须冻结
新的 clean implementation/data source SHA，不能把 Task001 SHA 直接冒充 dataset source。

M0 放行 M1 实现，不放行正式 PDE。正式 PDE 只能在 M1 targeted/regression 通过并提交 clean
baseline 后开始。
