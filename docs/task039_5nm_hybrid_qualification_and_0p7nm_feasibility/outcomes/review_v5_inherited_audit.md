# Task039 Review V5：继承证据与内存基线审计

本文是 V5-0 的 docs-only 启动审计。它冻结 V4 已有证据、当前运行环境和 V5 的执行边界；不生成 packet，不运行 pytest、MPI、PDE 或 QEP，也不把 V4 的旧结果改写成新的资格结果。

这里的“resident stack”指同一时刻仍占用内存的数组、PETSc 向量、矩阵、因子、耦合工作区、Python 引用和 MPI 进程树的合计。V5 先测它，是为了知道峰值究竟由哪些仍存活的对象造成，再决定删除、复用或流式化哪些对象。

## 1. 身份与审计边界

| 项目 | 本次只读核验结果 | 语义 |
|---|---|---|
| branch | `codex/20260812-task39-5nm-hybrid-0p7nm-feasibility` | measured |
| current HEAD | `054c2e33272efa2e999d106023c31737f4ec8c7a` | measured；本文件的审计来源身份 |
| upstream | `origin/codex/20260812-task39-5nm-hybrid-0p7nm-feasibility`，同为 `054c2e33272efa2e999d106023c31737f4ec8c7a` | measured |
| ahead / behind | `0 / 0` | measured |
| worktree | tracked 修改为空，nonignored untracked 为空 | measured；本文件创建前的基线 |
| Review V5 reviewed_head | `508d81ab1cffe26aff29038ab15f0b14a7516cde` | review 中冻结的前一代码/证据基线 |
| reviewed_head 与 current HEAD | `508d81ab` 是当前 `054c2e33` 的祖先；中间的 `5c8d195b` 为授权提交，当前 `054c2e33` 只新增/修正文档 review | derived from Git ancestry and diff |
| review authority | [review_report_v5.md](../review_report_v5.md) | V5 执行边界 |

本文件创建后，唯一预期的 tracked 变化就是本文件本身；没有修改 solver、runner、输入、schema、record 或 raw artifact。

## 2. V4 h4 Hybrid 证据与 hash 绑定

| 方法 | compact record 与 SHA256 | formal/raw 入口与关键 hash | 当前解释 |
|---|---|---|---|
| Hybrid direct | [direct compact](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_direct_packet_consumer_v1.json)，`fa1bb003e610a018e8a8d21d2f137c98b1d08817edcef6ee8a19f8cd9a0a5def` | [direct run](../../../results/task039_v4_h4_hybrid_direct_formal_mpi8_icntl14_1515f095)；run manifest `5f77b5a7c2c0bfe48f66394e94e837b59c8522f20bc5148226b0358e557af006`；run summary `3f19ead55f507e084488e2df77e352e2f650bcfe4fc2e1f85b42fbddc09b4a72`；direct payload `2cee09c0bd8f1d0b53fa1b6dbff1c6b1a23bcd3f752a4cc72cbf15fbdaf4c376` | `HYBRID_DIRECT_H4_OWN_PASS`；Full3D integrated comparison 独立为 unavailable |
| Hybrid iterative exact-side | [iterative compact](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_h4_hybrid_iterative_exact_side_v1.json)，`dff47fa35593958a0647f3a4768caa53001bae1b554891946d120339a88dad78` | [iterative run](../../../results/task039_v4_h4_hybrid_iterative_exact_side_formal_mpi8_c2829b7e)；run manifest `b446a43dcdc45ce7bc4b3eb3fbd46b9ab9685d29f4e9e31184baeac979c3d7c9`；run summary `8878167d282d4a750f2c1431da991c86adeb91eb6d125819e4ccb516d825a5d3`；consumer `96411440c380b12e1b774168af09cadb63710542a956dbe8691cf15a6eb19313`；checkpoint `edeae9afc48bd869974a62969ccccf2573e7b4ac5f7949f2b5dc27de0aea97c9`；posthoc comparison `2ecd04299524731f8f355b2c2fe28abd6da55355c7137a9e94a15593c43fe858` | `HYBRID_ITERATIVE_H4_EXACT_SIDE_NUMERICAL_PHYSICS_PASS_RESOURCE_FAIL`；outer exit 4 是资源目标未满足，不是数值失败 |

两条 Hybrid 记录都绑定 5 nm、1° grazing、phi=0、S、p6/h4、MPI8、M480 以及同一 method-independent packet。iterative 的资源失败必须保留；不能只因 residual、recovery 和 integrated checker 通过就称为资源资格通过。

## 3. shared h4/M480 packet 的本地可复用性

| 项目 | measured 值 | 解释 |
|---|---|---|
| packet directory | `results/task039_v4_h4_m480_shared_packet_eaad0f94` | 本地已存在；本次不生成新 packet |
| manifest | [manifest.json](../../../results/task039_v4_h4_m480_shared_packet_eaad0f94/manifest.json)，SHA256 `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` | shard、shape、dtype、ownership 和 identity 的 authority |
| identity file | [identity.json](../../../results/task039_v4_h4_m480_shared_packet_eaad0f94/identity.json)，文件 SHA256 `b3bb870fe6fa17cb262b6161f7317cc1950944755c9270d4628dd5c79e950690` | 文件字节 hash；不能与 canonical identity hash 混用 |
| canonical identity | `cfd5704b48bff980fa2d819f4deee9a59bb9a3db39bc24a70c53f42f067d39e9` | 两个 consumer 的 authority identity |
| producer/source SHA | `eaad0f942f014b65474ac57e3d5e561316489f20` | packet producer provenance |
| packet scope | `task039_v4_h4_m480`，M=480，MPI=8，`method_independent=true` | 可供 direct/iterative 复用；不是 Full3D 的 M480 |
| external inventory | 600 keys，SHA256 `ba431ec6683f2123e53e8f9f3fb13fd35ae22a6a8f9c0ed2d85aa1f1cb15b04a` | 两个 consumer 的 exact key authority |
| local shards | 32 个 `.npy`，每 rank 四组 `positive/negative × right/left`，rank ownership 连续覆盖 global size 11605 | measured；owner-row 分布，不是 8 份全局复制 |
| bytes | `.npy` payload/filesystem 总量 `356509696 B`；manifest+identity+shards 总量 `357128866 B` | measured file stats；不是 RSS 预测 |

因此当前 packet 可以严格复用：manifest SHA、canonical identity SHA、external-key hash 和 32/32 shard hash 必须原样命中。若以后 ignored packet 缺失，V5 只能记录 `missing` 并停止该 consumer，不能在 V5-0 生成替代 packet、重跑 QEP 或用文件大小推断模式状态。

packet 文件体积约 0.332 GiB，而 V4 Hybrid consumer 的峰值为 93--104 GiB。这一差距说明 packet 本身不是 V5 内存回归的充分解释；resident stack 的阶段归因仍必须实测。

## 4. Full3D 与 h5 历史边界

### 4.1 Full3D h4

既有 [Full3D lifecycle record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_full3d_h4_lifecycle_timeout_v1.json) 保留为负的完成度证据：正式 run 在 MUMPS factor setup 阶段由 21600.036 s monotonic watchdog timeout 停止，RSS 208.315395 GiB，PSS 约207.30 GiB，USS 约207.14 GiB，swap=0；factor-ready、solve、recovery、postprocess 均未完成。这不是数值失败，也不是 hard-memory stop，但它不是 completed Full3D method。

V5 因此保持 `Full3D_new_heavy_run = deferred / forbidden`。任何 V5 表格都不能把该 timeout-stop peak 写成 completed-method peak，也不能用它制造 Full3D 与 Hybrid 的正式 saving。

### 4.2 h5 历史 direct/iterative 与当前 lifecycle

| 证据 | measured 结果 | lifecycle / 比较边界 |
|---|---|---|
| 旧 1° p6/h5 Hybrid direct | `87064.125 MiB = 85.0235595703125 GiB`；见 [V3 memory record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_memory_lifecycle_v1.json)，SHA256 `2206d4d28b950a0e8ce26175d71b7f7faf555898dd27b6507c5f22dd2aade352` | V3 的旧 implementation/lifecycle；不是当前 h4 packet consumer baseline |
| DQ1 h5 exact-side explicit opt-in | `51019.37890625 MiB = 49.8236122131 GiB`，4888.064315 s，outer=1，数值/physics/resource pass；[DQ1 record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v3_h5_exact_side_case_qualification_v1.json)，SHA256 `0b15f84a0014c22f4e2c5c7e7cffedeab60b380507d25a3f5a599c0f47999b33` | 固定 h5、V3 exact-side precedent；不能替代 h4/M480 current baseline，也不能预测 V5 h4 resident stack |
| 旧 10° ILU0 iterative | `83155.31640625 MiB`，6000 / `DIVERGED_MAX_IT`；[historical record](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v2_h5_hybrid_iterative_m480_v1.json)，SHA256 `8475462561b3079e16401c9b95a0aca8396206c11788c577b40276a074b2636a` | 10° 历史负结果；不是同物理、同 lifecycle 或同 baseline |
| 当前 V4 h4 direct | `93.377006531 GiB` process-tree RSS peak | packet reuse、factor-before-postprocess、ICNTL14=100 的当前 direct reference |
| 当前 V4 h4 iterative | `104.334560394 GiB` process-tree RSS peak | exact-side、1 outer；数值/physics pass 但资源 objective fail |

“旧/当前差异”至少包括 h5 与 h4 的物理网格身份、V3 与 V4 的 packet consumer 接线、factor 生命周期、MUMPS workspace policy 和 telemetry 边界。上述差异未被 h 缩放公式吸收，不能把 DQ1 的 49.8236 GiB 直接写成 V5 h4 预期值。

V5-S 的 p6/h5 current-lifecycle Hybrid direct sidecar最多运行一次，且是 nonblocking curiosity measurement；它不能覆盖、改写或解除 h4 direct baseline，也不能把 h5 sidecar提升为一般 production 结论。本 V5-0 不运行该 sidecar。

## 5. qualified activation 与当前资源快照

本次只读 preflight 时间为 `2026-08-18T18:09:29+08:00`；没有启动 pytest、MPI、PDE、QEP 或 heavy worker。

| 项目 | measured 结果 | 语义 |
|---|---|---|
| qualified activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` | activation pass |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python` | repo `.venv` |
| PETSc | `ScalarType=numpy.complex128`；`IntType=numpy.int32` | ABI pass |
| MPI | Open MPI 4.1.6；preflight `COMM_WORLD size=1` | 只读 ABI 探针；不是 formal MPI8 run |
| libraries | petsc4py/slepc4py/dolfinx 来自 `/usr/lib/petscdir/petsc3.19/...`；mpi4py 来自 `/usr/lib/python3/dist-packages` | 同一 Linux WSL ABI 栈 |
| threads | `OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`、`OPENBLAS_NUM_THREADS=1` | measured |
| MemAvailable | `235002548 kB`，约 `224.12 GiB` | measured current snapshot；正式 heavy 前仍须逐次 preflight |
| swap | SwapTotal `33554432 kB`，SwapFree `33554432 kB`，SwapUsed `0` | measured current snapshot |
| disk | `/` available `801491296 KiB`，约 `764.36 GiB` | measured current snapshot |
| heavy process inventory | 未发现 pytest、mpiexec、PDE、Task39 worker 或 heavy solver | measured read-only process probe |

GiB 换算、SwapUsed=SwapTotal-SwapFree、磁盘 GiB 换算属于 derived；它们不改变原始 measured 单位。当前 preflight 通过，但它只授权后续按 Review V5 排队，不授权本 turn 启动 heavy。

## 6. V5 内存分类与 advancement Gate

V5 的唯一 matched resource baseline 是当前 h4 Hybrid direct 的 `93.377006531 GiB` process-tree RSS peak。分类如下：

| 分类 | RSS 条件 | 直观含义 |
|---|---:|---|
| regression fail | `>=93.377006531 GiB` | 仍不如 direct baseline |
| positive but target not met | `<93.377006531 GiB` 且 `>74.701605225 GiB` | 消除了回归，但未达到20%节省 |
| meaningful pass | `<=74.701605225 GiB` | 相对 direct 至少节省20% |
| strong pass | `<=65.363904572 GiB` | 相对 direct 至少节省30% |
| major pass | `<=56.026203919 GiB` | 相对 direct 至少节省40% |

`74.701605225`、`65.363904572`、`56.026203919 GiB` 是由 Review V5 冻结 baseline 得出的分类边界，属于 derived thresholds，不是新的运行测量。V5 正式目标是 meaningful pass；只达到 positive 必须如实分类。

setup-only 进入 full solve 前还有独立 advancement Gate：全过程 peak 应不高于 `84.039305878 GiB`（direct 的90%），或有保守上界低于 direct 且至少留5%余量；否则 controlled stop。该 Gate 不能用 packet 字节数、单 rank 的历史 ru_maxrss 或旧 h5 结果替代。

## 7. V5 顺序、时间政策与重型上限

### 7.1 固定顺序

| 阶段 | 作用 | 本次状态 / 上限 |
|---|---|---|
| V5-0 | 继承证据、身份、环境和 resident-stack baseline 审计 | 本文；不启动 heavy |
| V5-S | 当前 lifecycle 的 p6/h5 Hybrid direct sidecar | 最多一次；nonblocking；本次未运行 |
| V5-1 | 对既有 h4 raw 做离线内存归因 | offline；不重跑 h4 |
| V5-2 | h4 exact-side setup-only attribution | 条件执行；最多一次 |
| V5-3 | 保持同一数学的 exact-side compaction | 只有前序 Gate 通过才进入 |
| V5-4 | 单次 modal Schur 与固定-PC Krylov storage reduction | research-only、串行 heavy 上限受 Review 约束 |
| V5-5 | action-only / streaming Woodbury W | 只有前序证据支持才进入 |
| V5-6 | compact exact-side h4 formal run | advancement Gate 后最多一次 |
| V5-7/V5-8 | conditional factor-light funnel/formal | 每个阶段只允许一个候选及一次正式重型运行 |
| V5-9/V5-10 | 0.7 nm capacity update、response_v6 与停止审阅 | 0.7 nm Full PDE 禁止 |

### 7.2 watchdog 与延长政策

默认每个 heavy 阶段使用 21600 s watchdog、绝对内存上限 `224000000000 B`、swap 必须为0、poll 不超过0.25 s，并保持严格串行。达到 hard limit 或出现 swap 时，终止完整进程树并保存 controlled evidence；不要重跑或调参。

只有在唯一的 outer iterative formal 已经开始、约 19800 s 检查点仍满足 Review V5 的 residual trend、资源和 swap 条件时，才允许一次性把总 wall 上限延长到 28800 s。该延长不适用于 QEP、packet prep、direct setup、h5 sidecar、setup-only、outer iteration 尚未开始的阶段，也不适用于 Full3D 或 0.7 nm PDE。

Review V5 的 heavy 上限是资源预算，不是成功承诺：h5 packet producer 最多1次，h5 direct sidecar最多1次，h4 setup-only最多1次，h4 exact-side formal最多1次，factor-light阶段仅按条件最多1次；新的 Full3D heavy 和0.7 nm Full PDE均为0次。

### 7.3 禁止项与 ordinary defaults

禁止 M>480、ordinary ILU sweep、PC sweep、改物理/网格/MPI/容差来换取结果、重跑 V4 QEP/direct/Full3D 只为覆盖已有证据、并发 heavy，以及把 h5 或 Full3D timeout 当作 h4 Hybrid 通过。ordinary defaults、普通 solver 路径和公共输入语义保持不变；V5 优化只针对审定的 fixed-case explicit opt-in。

## 8. 为什么先测 resident stack

内存优化首先要回答“峰值时到底有哪些东西同时活着”。一个 0.332 GiB 的 mode packet 可以很小，但如果 consumer 同时保留 PETSc factor、global matrix、side coupling、field reconstruction 缓冲区和两套 Python/PETSc 引用，峰值仍可能超过100 GiB。反过来，删除一个已经释放的对象不会带来真实收益。

因此 V5 先对既有 h4 iterative 的 104.334560394 GiB 与 h4 direct 的 93.377006531 GiB 做阶段和生命周期归因，再决定是否做 compact、Schur/Krylov storage reduction 或 streaming。这样优化的是同时驻留的 resident stack，而不是把 packet 文件大小、单个 rank 的历史峰值或理论容量 proxy误当成 process-tree RSS。只有新运行的全过程 process-tree RSS、swap 和阶段边界，才能进入 V5 memory classification。

## 9. 证据语义与 V5-0 结论

| 证据类别 | 本审计可使用的例子 | 不可越界的解释 |
|---|---|---|
| measured | Git 身份、ABI、当前 MemAvailable/swap/disk、packet file bytes、V4 raw process-tree peak/wall、残差和 physics payload | 只代表对应来源、进程树和时间边界 |
| derived | compact/manifest SHA 关联、reviewed_head 祖先关系、GiB 换算、V5 分类阈值、串行 cold peak 取阶段最大值 | 不能写成新运行测量 |
| source-contract | method-independent owner-row packet、ordinary default 保持、V5 顺序和禁止项 | 不能伪装成 runtime telemetry |
| not_available / not_measured | Full3D completed solve；V4 direct/iterative PSS/USS；V5 新阶段 resident attribution；h5 current sidecar | 必须继续写明缺口，不得用旧结果补齐 |

本 V5-0 审计结论是：V4 h4 Hybrid direct/iterative 的 compact/raw、shared M480 packet 和 h5 历史边界均可复用为 baseline；当前环境满足只读资格化 preflight；Full3D heavy 继续 deferred；h5 current-lifecycle sidecar保持 nonblocking。V5 下一步必须按固定顺序先做真实 resident-stack attribution，再由 setup-only advancement Gate 决定是否进入后续优化或唯一 formal run。本文不宣称 V5 positive、meaningful、strong、major 或任何新的 production qualification。
