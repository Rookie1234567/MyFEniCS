# Review V4 inherited audit

本文件是 V4-0 的只读继承审计。它只登记已有记录、源码边界和启动前环境快照，
不把旧的 h5、10° 或受控停止结果升级成 V4 的 h4 authority，也不创建新的 raw
artifact。V4 的当前固定范围是 5 nm、1° grazing、phi=0、S、p6/h4、M=480、
MPI8；h3、0.7 nm PDE、M>480、ordinary ILU0/PC sweep 均不在本阶段范围内。

## 1. 身份、分支和 ABI

| 项目 | V4-0 实测值 | 语义 |
| --- | --- | --- |
| local branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | 当前 Task39 执行分支 |
| local HEAD | `89948eeb9d05e7c2b385b58c51b39d22a629c61c` | V4 review 已在本分支 |
| remote/upstream | 同一 SHA | `origin/<same branch>` |
| ahead/behind | `0/0` | 无远端漂移 |
| worktree | clean；无 nonignored untracked | ignored `results/` 不属于提交范围 |
| master | 未修改 | 不从 master 开发或合并 |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` | qualified WSL/Linux shell |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python` | 当前仓库 `.venv` |
| PETSc/SLEPc | PETSc 3.19.6；ScalarType `complex128`；IntType `int32` | 满足正式 ABI 前提 |
| MPI | Open MPI 4.1.6 | 与 petsc4py/slepc4py/dolfinx/mpi4py 同一 Linux 栈 |

本次启动前资源快照时间为 `2026-08-17T02:39:50.780892890Z`：

| 资源 | 快照 | measured 语义 |
| --- | ---: | --- |
| `/proc/meminfo` MemAvailable | `235561408 kB` | 当时系统可分配内存，不是 heavy process-tree 峰值 |
| swap | `0 kB used / 33554432 kB total` | 启动前系统状态；正式运行仍须全程 swap=0 |
| Task39 文件系统可用空间 | `822535417856 B` | `df` 工作区快照，不是因子或矩阵容量证明 |

上述快照只用于 preflight 身份和资源资格，不替代 V4 formal run 的 process-tree
RSS/PSS/USS、阶段峰值、swap 和磁盘证据。

## 2. 已继承证据

| 证据 | 身份/结果 | reusable / stale / missing |
| --- | --- | --- |
| 2D TE Q8 | 1°、5 nm、S/TE、MPI1；相邻 Q8 网格 Gate 通过 | `reusable research reference`；不替代 3D h4 |
| 1° Full3D h5 | source `5872cda24e47c750d654fa7b06d81057af5bf9fc`；input SHA `c8be071f…9981f5`；physical SHA `0462c980…ccd576d`；own solve 通过 | `reusable h5 reference`，对 V4 h4 为 stale |
| 1° Full3D h4.5 | own solve 通过；RSS 约 `125.5527 GiB`；与 h5 的 R/T/A/A_volume 差约 `1e-8` | `reusable convergence context`，不是 h4 authority |
| 1° Full3D h4 | compact record 为 `FULL3D_1DEG_H4_RESOURCE_CONTROLLED_STOP_AFTER_LINEAR_RTA`；600 external modes；linear true residual `3.5718033073581125e-10`；RSS `214091.234375 MiB`；swap=0 | `partial`；求解后在 recovery/postprocess 前受控停止，不能称 authority |
| 1° Hybrid direct M480 h5 | source `5bfab734a9ca053b69fa1f3f20d907aacbf8b07f`；physical SHA 与 h5 Full3D 一致；process-tree telemetry、direct payload 已有 | `reusable h5 implementation/reference`；不是 h4 结果 |
| exact-side DQ1 h5 | fixed-case explicit opt-in；1 outer iteration；约 `51019.37890625 MiB`、`49.8236 GiB`；worker/parent 资格证据完整 | `reusable solver/lifecycle precedent`；不是 h4 packet 或 h4 result |
| h5 QEP/M480 authority | candidate/selected QEP、retained dual rotation 和 left residual evidence 已有 | `reusable offline/QEP authority`；不能代替 h4 selected packet |
| 旧 10° V1/V2/V3 结果 | 原有正负结果、负结果和资源记录完整 | `preserved historical evidence`；不与当前 1° h4 混比 |

h4 Full3D compact record 见
[task039_v3_h4_full3d_direct_supplement_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_h4_full3d_direct_supplement_v1.json)。
旧 outcomes、response 和 negative records 均保持不变。

## 3. 缺失项与动态身份合同

| V4 必需项 | 当前状态 | 进入 formal 前要求 |
| --- | --- | --- |
| h4/M480 selected-mode packet | missing | 从同一 h4 authority 生成一次；包含 selected ±beta basis、trace、P/T、mapping/Gram、keys/order/group、QEP residual 和 identity hashes；不携带 EPS/ST/KSP/raw candidates |
| h4 Hybrid direct input/raw | missing | 必须取得与 h4 Full3D 相同物理、网格、external identity 的 official input；不能由 h5 文件猜测替代 |
| h4 exact-side iterative input/raw | missing | 依赖共享 h4 packet 和同一 h4 identity；当前没有可复用 formal result |
| h4 named telemetry | incomplete | 新 formal run 必须真实产生 process-tree samples、memory stages、object ledger 及 marker alignment |
| h4 external inventory | partial | 旧 h4 记录有 `external_mode_count=600`，但未来 checker 必须从 resolved config/producer manifest 动态读取 count、unique exact key set、producer/consumer/source/physical SHA；600 是当前官方期望身份，不是硬编码通过条件 |
| post-recovery authority | missing | h4 需完成 recovery、R/T/A/A_volume、closure、selected E/H、traction 和完整 key authority |

## 4. pre-recovery factor release 缺口

现有配置 `direct_release_solver_before_postprocess` 默认仍为 `False`。现有代码路径是：

1. `common_3d_case_flow.py` 调用 `solve_stage4_dtn_port_total_field()`；
2. `dtn_port_3d.py` 在返回前完成 assembly-time full-field recovery、true residual 和场重构；
3. 返回后，`common_3d_case_flow.py` 才 destroy KSP/MUMPS factor、system Mat、RHS/solution Vec，并执行 PETSc garbage cleanup/heap trim。

因此既有逻辑可复用为“postprocess 前释放”，但尚不是“full-field recovery 前释放”。V4-1
必须先实现最窄的 default-off lifecycle hook，并用 focused test 锁定以下顺序：冻结
active/augmented true residual、external auxiliary/q 和 hash-bound 最小解身份；释放
KSP/MUMPS factor；再执行 full-field recovery。若 Level A 的实测 RSS 仍不安全，才进入
Level B 的 solve/postprocess process split；不得预先重算、改物理、改 M 或改 Gate。

## 5. V4 依赖和预计 heavy 顺序

至少需要三个新的、严格串行的 MPI8 formal heavy case；旧 h4 controlled stop 不计入完成数：

1. V4-1 focused lifecycle/telemetry proof 后，重新完成一次 Full3D h4；
2. 从该 h4 authority 生成唯一共享 M480 packet，再完成 Hybrid direct h4；
3. 复用同一 packet 完成 exact-side Hybrid iterative h4。

随后才进行 same-grid integrated compare、offline QEP/M component study 和 V4-10
response_v5。2D Q8 现有记录可直接复用，不因 V4-0 再启动 2D heavy。所有 formal run
必须使用 warning 170 GiB、critical checkpoint 195 GiB、绝对 hard stop
`224000000000 bytes`、poll 不超过 0.25 s、swap=0；一次只运行一个 heavy。

当前可量化的 h4 Full3D 先例是约 5.1 小时 worker、约 5.23 小时 launcher、
`209.073471 GiB` process-tree peak；生命周期修复后的新峰值和 h4 Hybrid 两条路线
均为 `not_established`，不得用 h5 的 `49.8236 GiB` 或 `85.0236 GiB` 预测 h4 通过。

## 6. V4-0 边界结论

- V4-0 identity、ABI、分支和 clean Gate：通过。
- inherited h4 Full3D：仅 partial controlled-stop evidence，不是 numerical/physics authority。
- h4 packet、h4 Hybrid direct、h4 exact-side iterative：尚缺。
- pre-recovery factor release：已有释放逻辑，但生命周期边界仍晚于 recovery。
- ordinary defaults、master、旧 10°/V1/V2/V3 正负结果：保持不变。
- 在 V4-1 lifecycle contract 与上述 h4 identity/packet 缺口解决前，不启动 V4-2 或其他 PDE/heavy。
