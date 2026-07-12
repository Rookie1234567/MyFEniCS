# 3D Workstation MPI4 iterative：PyCharm 与 CLI 完整教程

## 1. 功能与物理图景

该路径针对固定 p=2 Stage4 target，先精确消去 DtN auxiliary unknowns，再用 right FGMRES 求解 FE condensed operator。预条件器由 16 个 complete physical slabs、shifted-F ILU1、两步内层 GMRES 和固定 75D coarse correction 组成。

## 2. 当前能力状态

| h | 状态 | iterations | full residual | peak total RSS |
|---:|---|---:|---:|---:|
| 5 nm | qualified | 1,201 | 9.839e-7 | 1.991 GB |
| 3 nm | qualified | 993 | 9.933e-7 | 5.082 GB |
| 2 nm | qualified | 1,804 | 9.997e-7 | 13.080 GB |

这是冻结 target 的 workstation profile，不是任意参数的 mesh-independent 定理。

## 3. 运行前提

1. 使用 qualified complex image。
2. MPI 必须是 4 ranks。
3. h2 前保证 WSL 可用约 14 GB，关闭其他大进程。
4. 普通 `src/main.py` 单进程 Run 不具备该 qualification。
5. 参数扫描不能覆盖 `benchmarks/records/workstation_*.json`。

## 4. PyCharm 方案 A：External Tool

打开 `Settings | Tools | External Tools`，新建 `Stage4 workstation h5 MPI4`：

```text
Program           = docker
Arguments         = run --rm
                    -v "$ProjectFileDir$:/work"
                    -w /work
                    myfenics-stage4:task28
                    mpiexec -n 4
                    /dolfinx-env/bin/python
                    -m benchmarks.run_workstation_iterative
                    --config benchmarks/configs/workstation_p2.json
                    --h-nm 5
                    --case-label pycharm_candidate_h5
                    --results-dir benchmarks/artifacts/cases/031
                    --record benchmarks/artifacts/cases/031/candidate_records/pycharm_h5.json
Working directory = $ProjectFileDir$
```

若 `docker` 不在 PATH，Program 使用 Docker Desktop `docker.exe` 的绝对路径。运行入口位于 `Tools | External Tools`。

## 5. PyCharm 方案 B：WSL/Docker Python + MPI wrapper

如果 PyCharm 的 interpreter 本身位于 qualified WSL/container：

```text
Module name       = benchmarks.run_workstation_iterative
Parameters        = --config benchmarks/configs/workstation_p2.json
                    --h-nm 5
                    --case-label pycharm_candidate_h5
                    --results-dir benchmarks/artifacts/cases/031
                    --record benchmarks/artifacts/cases/031/candidate_records/pycharm_h5.json
Working directory = repository root
Interpreter       = qualified complex DOLFINx interpreter
MPI wrapper       = mpiexec -n 4
```

若 IDE 无法在 module 前加 wrapper，使用方案 A。不要在 Python 进程内部 `subprocess` 静默 spawn MPI。

## 6. 完整冻结参数块

```text
config = benchmarks/configs/workstation_p2.json
MPI = 4
operator = F - C H^{-1} D
outer = right FGMRES, restart 100, rtol 1e-6, max_it 3000
coarse = 24 z intervals -> 25 nodes x 3 components = 75 vectors
local = 16 complete physical z slabs, overlap 0.25
factor = shifted-F ILU1
smoother = fixed two-step inner GMRES (sm2)
```

## 7. 参数含义与合法值

| 参数 | 含义 | 当前 qualified 值 |
|---|---|---|
| `--h-nm` | target mesh size | 5/3/2 |
| `mpi_size` | owner distribution | 4 |
| `num_physical_slabs` | complete z slabs | 16 |
| `coarse_dimension` | coarse basis count | 75 |
| `smoother_iterations` | inner fixed GMRES steps | 2 |
| `rtol` | outer reported target | 1e-6 |
| `restart` | FGMRES restart | 100 |

任何差异都会写入 `qualification_deviations`，非 canonical 参数应标 experimental。

## 8. 资源与安全边界

| h | 建议 |
|---:|---|
| 5 | 首次运行；约 2 GB |
| 3 | 先确认 6 GB 以上可用；约 5.1 GB |
| 2 | 只在约 14 GB 配额、系统空闲时运行；约 13.1 GB |

h=1.5 未资格化。不要通过增大 swap 把明显 OOM 当成正常性能。

## 9. CLI 等价命令

```text
H_VALUES="5" sh benchmarks/cases/031_workstation_iterative/run.sh
```

该脚本把候选 record 写到 ignored artifact 目录，不覆盖 canonical records。要一次跑 h5/h3：`H_VALUES="5 3"`。

## 10. 真实调用链

```text
benchmarks.run_workstation_iterative::main
-> stage4_runtime::assemble_target_stage4_system
-> condensed_dtn::split_petsc_augmented_system
-> condensed_dtn::create_matrix_free_condensed_operator
-> physical_slab_two_level::DistributedPhysicalSlabSmoother
-> physical_slab_two_level::SparseGalerkinTwoLevelPc
-> PETSc right FGMRES
-> recover_petsc_auxiliary
-> official 3D RTA
```

## 11. 输出目录和 record

```text
benchmarks/artifacts/cases/031/
├── case031_candidate_h5/
│   ├── progress.json
│   ├── parameters.json
│   ├── run_summary.json
│   └── field/RTA artifacts
└── candidate_records/h5.json
```

canonical references 位于 Case031 `records/`，以 SHA-256 指向顶层 records。

## 12. 关键 JSON 字段

| 字段 | 解释 |
|---|---|
| `reported_relative_residual` | KSP 报告值 |
| `condensed_true_residual` | 显式计算 `||A_c u-b_c||/||b_c||` |
| `full_augmented_true_residual` | 回代 aux 后完整系统真残差 |
| `coarse_rank/condition` | 75D coarse 质量 |
| `slab_diagnostics.subdomain_owners` | 16 slabs 的 owner |
| `peak_total_rss_including_rta_gb` | 全 MPI 总峰值，包括后处理 |
| `qualified_profile/deviations` | 是否仍在冻结参数 |

## 13. 成功 Gate

```text
ksp_reason > 0
reported, condensed, full residual <= 1e-6
三种 residual 相对一致
coarse rank = 75 且 condition <= 1e10
R/T/A closure <= 1e-6
h2 total peak RSS <= 14 GB
```

## 14. 常见错误

| 现象 | 原因 |
|---|---|
| PyCharm 显示 size=1 | 普通 Run 未经过 MPI wrapper |
| candidate 覆盖 canonical | `--record` 指向顶层 records |
| iterations 变了但仍写 qualified | 修改 config 未检查 deviations |
| reported 通过、full 不通过 | 回代或真残差路径错误 |
| MPI 某 rank 挂住 | 其他 rank 先异常退出，需看全部日志 |

## 15. 改成自己的参数扫描

复制 `workstation_p2.json` 到 ignored artifact 或新任务目录，设置新的 case label/record 路径，并明确 `qualified_profile=false`。先跑 h5；只有正信号和资源证据后再扩大。

## 16. 链接

- 迭代理论：[`../theory/iterative_solver_and_preconditioner.md`](../theory/iterative_solver_and_preconditioner.md)
- 运行代码：[`../reference/code_walkthrough/33_workstation_fgmres_runtime.md`](../reference/code_walkthrough/33_workstation_fgmres_runtime.md)
- PC 代码：[`../reference/code_walkthrough/32_physical_slab_two_level_pc.md`](../reference/code_walkthrough/32_physical_slab_two_level_pc.md)
- Case031：[`../../benchmarks/cases/031_workstation_iterative/README.md`](../../benchmarks/cases/031_workstation_iterative/README.md)
