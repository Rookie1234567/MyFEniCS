# Task040 Review V2 继承审计

## 结论与本轮范围

Review V2 的核心修正是把上一轮同一进程中的两个阶段拆开：先由独立 producer
建立接口 Schur 诊断包，再由全新 consumer 读取该包并测试 projected transmission。这样，
诊断工具的内存高水位不会自动叠加到 consumer；但 producer 的诊断结果仍不能直接称为
0.7 nm 生产方案。

本轮只完成 V2-0 文档审计。没有修改 solver、runner、checker、tests、ordinary defaults 或
任何 frozen artifact，没有运行 pytest、MPI、PDE、QEP 或 heavy。后续阶段必须遵守
[Review V2](../review_report_v2.md)；V1 的 compact evidence 与旧失败 root 保持原样。

## 身份、来源与环境

| 项目 | 已核对值 | 口径 |
|---|---|---|
| repository | `/home/Projects/MyFEniCS` | canonical checkout |
| branch | `codex/20260822-task40-hybrid-side-factor-pc` | 当前唯一 Task40 分支 |
| HEAD / upstream | `4da67165bdc273060353c122be8db8a372f60111` / 同值 | V2 review 基点 |
| ahead / behind | `0 / 0` | 当前同步状态 |
| worktree | clean | V2-0 开始前核对 |
| inherited Task039 base | `9dc9ac58e05e5422498dade503046f9ae87d13d9` | task.md 冻结值 |
| Review V2 SHA256 | `5b4fed4e0139cf715b3ddc91ba4bf024a2023e27329dc78fa340359cf1e29324` | `review_report_v2.md` |
| task.md SHA256 | `b09af10f19e5b380aac74c5b5be2e39cd8756d0a23727afc5bd1b853bf833ec7` | 当前任务书 |
| V1 response SHA256 | `0dc3f0709172bdedb266b0e709666810233eda06edd6dc7c7842f5952b7eb904` | 上一轮回应 |
| V1 resource record SHA256 | `da1d50737fae47943070d4eeda3b4dfbfec136a7871496e5879cb060df37c5a3` | compact record |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` | frozen |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` | inherited identity |
| physical model SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` | inherited identity |
| selected packet manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` | Task039 packet，只读 |
| exact-spool catalog SHA256 | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` | Task039 spool，只读 |
| V1-2 probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` | V1 frozen probe authority |
| physical case | 5 nm / 1° grazing / phi=0 / S / p6h4 / M480 / MPI8 | V2 不改变 |
| ABI snapshot | qualified activation=1；repo `.venv`；PETSc complex128/Int32；同一 Linux ABI；threads=1 | 继承 V1 已资格化快照；本轮不重跑 |

Task40 目录当前没有独立 `README.md` 或补充任务书文件；本轮权威材料是
`task.md`、`review_report_v2.md`、既有 `response_v1/response_v2` 和 `outcomes/`。

## 继承的正式状态与旧 root

| 项目 | 继承结论 | 说明 |
|---|---|---|
| V1-1 scalar screen | `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL` | 五个非零 source 的 `r16` 均约为 `0.98486–0.99368`；32 未运行；不是单纯幅值或相位问题 |
| V1-2 exact interface oracle | `NOT_QUALIFIED_DUE_RESOURCE_LIFECYCLE_STOP` | exact oracle marker 观测到 factor `3 -> 0`，但 probe/gate 未序列化 |
| V1-3 projected transmission | `NOT_EVALUATED` | setup 曾开始但未到 `projected_ready`，没有 one-apply/FGMRES checkpoint |
| V1-4 至 V1-7、Level B、top/full | `not_run_by_gate` | 依赖前置资格 Gate，未作数值结论 |

三个 V1 Run B root 均保留，不覆盖、不重分类：

| root | source SHA | 分类 | 事实 |
|---|---|---|---|
| `results/task040_v1_2_v1_3_run_b_mpi8_a3585c44` | `a3585c449f1ae1f9fb439ae905fe727efccb8aa7` | implementation failure | resolved schema 错把 `counts.per_side.bottom` 读成 `counts.bottom` |
| `results/task040_v1_2_v1_3_run_b_mpi8_618c668d` | `618c668d750f228c9eae457c8b69eda5d2cfcfda` | implementation failure | selected packet manifest SHA 与 exact-spool catalog SHA 混用 |
| `results/task040_v1_2_v1_3_run_b_mpi8_16ecba56` | `16ecba568be901325e53c3652aa10bb432de5a6b` | resource hard stop | `45.05752944946289 GiB`，swap=0；exact oracle 释放后未完成 probe serialization |

最后一个 root 不是 transmission 数学负结果。逻辑 factor count 回到零，也不能保证
PETSc/MPI allocator 立即把页归还给操作系统；这正是 V2 要求 producer/consumer 分进程的
工程原因。

## 四种资源语义

同一个 “45 GiB” 不能再代表所有阶段。每个阶段必须记录自己的 process-tree/cgroup 口径、
swap、factor inventory 和 wall：

| 资源语义 | 正式边界 | 允许的解释 |
|---|---:|---|
| V2-A producer preferred | `<=45 GiB` | 诊断包建立的首选目标 |
| V2-A producer absolute hard stop | `<=55 GiB` | 仅允许诊断/oracle；超过即停止，不能称 scalable candidate |
| V2-B consumer | `<45 GiB` | fresh consumer 的严格机制候选边界，swap 必须为 0 |
| Level B construction | `<=35 GiB` | bounded local PC 构造资源 Gate |
| Level B retained | `<=30 GiB` | setup 后长期 resident 状态 |
| Level B structure | `max_local_rows<=1024` | 每个局部 factor 的固定上限，不随全局网格增长 |
| full workflow | `<80.025856018 GiB` | 必须刷新 inherited exact-side iterative full-workflow baseline，并另报 20/30/40/50% tiers |

producer 的 `45–55 GiB` 结果最多只能说明离散接口 authority 已经建立；不能计为完整
Hybrid production memory pass。consumer 与 Level B 不得沿用 producer 的宽松线。

## V2 执行树与停止条件

| 阶段 | 作用 | 只有前置条件满足才进入 |
|---|---|---|
| V2-A1 | 独立 MPI8 interface-Schur packet producer | 冻结身份、ABI、资源与 source family 通过；先按 `<=45` 目标运行 |
| V2-A2 | producer 逐 group、一次只保留一个 factor 的 fallback | 若 A1 超过 `55 GiB`，先由 watchdog 形成 controlled hard-stop root，随后不得继续 A1；若 A1 未超过 `55 GiB` 但仍未写出完整包，也只能按同一数学执行逐 group factor→写包→销毁；不改变数学与 probes |
| V2-B1 | fresh consumer packet identity/remap setup | packet manifest 完成、hash 全部通过；consumer 不建 exact oracle |
| V2-B2 | projected one-apply 与 fixed right-FGMRES `0/4/8/16/(32)` | B1 identity/resource/lifecycle 通过；首个数值 Gate 达标即停止，不扫描参数 |
| V2-C | analytic mode-aware transmission | V2-B 数值与资源通过 |
| V2-D | bounded local patch Level B | V2-C 或明确授权的 projected transmission 通过；`<=35/<=30/1024` |
| V2-E | bottom、top、both-side setup、唯一 full Hybrid | Level B bottom 通过后按冻结配置顺序执行 |
| V2-F | 条件 h3 scalability probe | full/side 前置 Gate 通过且资源 preflight 允许 |
| V2-G | outcomes、Pareto、`response_v3.md` | 所有授权阶段完成或真实 Gate 停止 |

执行合同是 one-heavy-at-a-time。producer 与 consumer 是两个独立的 `mpiexec` 进程，不能
同时运行；producer 正常退出并留下完整 manifest 后才能启动 consumer。以下任一项立即保存
raw 并停止对应依赖链：身份/ABI 不一致、producer 超过 55 GiB、任一阶段 swap>0、packet
无法完整写出、consumer 达到或超过 45 GiB、canonical remap 失败、NaN/Inf、被授权的最终
checkpoint（16，或只有在满足 trend 条件后才授权的 32）仍未通过、`max_local_rows>1024`、
bottom 未通过却试图启动 top，或 full Hybrid residual/physics Gate 失败。

明确的路径/schema/ownership/lifecycle 错误仍可按 task.md 保留失败 root、增加 tiny/MPI
回归、做最小修复并重跑同一阶段；不得把真实数学、资源或扩展性失败伪装成 implementation
bug，也不得翻 sign、调 beta、改 mode span、加 coarse 或放宽 Gate。

## 现有构件与复用边界（仅审计）

| 现有构件 | V2 可复用的最小职责 | 本轮边界 |
|---|---|---|
| `src/solvers/hybrid_interface_schur.py::PetscDistributedPetrovAction` | 导出已 finalized 的 owner-local `U/V/G` 与小型 identity/diagnostics | 不在 benchmark 复制 Petrov 数学；不把 FE-sized basis gather 到 rank0 |
| `src/solvers/hcurl_canonical_vector_dolfinx.py` | canonical active-trace key、owner-local row identity、extract/reconstruct round-trip | Gamma key 必须语义稳定；不能只用 PETSc global row number |
| 现有 rank-shard/hash/manifest 工具 | 复用其小型 hash、逐 shard 校验和 manifest 收口理念 | 不新建通用 packet framework，不扩大 schema |
| Task039 `hybrid_side_response_packet` 路线 | 仅作禁止边界参考 | 不复用、重开或提升为 Task40 producer/consumer 算法 |

通俗地说，Petrov carrier 已经能保存“每个 rank 自己拥有的修正行”和小型 Gram；canonical
active-trace 模块能回答“这一行代表哪个稳定的物理/约束自由度”。V2 要把这两种身份接在
hash-bound shard 上，而不是把一整个有限元向量复制到所有 rank。

## 待后续阶段的最小实现策略

以下是 Review V2 已批准的后续设计，不是 V2-0 的实现声明：

1. producer 与 consumer 使用两个真正独立的 MPI 进程。producer 只完成 finalized `U/V/G`
   和 V1-2 probe authority，不建 V1-3 base factors、不运行 FGMRES。
2. producer 不同时长期保存 `Z/Y` 与已经 finalized 的 `U/V`；完成投影后应释放可重建的中间
   basis，避免把同一信息保存两份。保留的 per-rank owner-row shard 只包含 consumer 所需的
   finalized representation。
3. 每个 rank 写自己的 owner-row shard；rank0 只在所有 shard 已完成、哈希已核对后写 manifest。
   manifest 必须绑定 source/input/physical/packet identity、canonical key order、owner range、
   shard hashes、small `G` 与 diagnostics。manifest 完成前不能称 packet complete。
4. canonical Gamma key 必须独立于当前运行的 PETSc global row number，能证明全局 bijection，
   并在 consumer 端做 canonical key→owner-local row→canonical key round-trip；只验证 row ID
   排序不够。
5. consumer 每个 rank 只读取本地需要的 shard；numeric FE-sized data 不得 allgather。只有小型
   `G`、projected contractions、rank/singular values/condition 和 compact diagnostics 可以复制。
6. consumer 在没有 exact interface oracle 的情况下重新建立三个 scalar base factors，再用
   packet 的 finalized owner-local representation 构造 projected correction；exact-interface
   factor inventory 必须为 0，scalar base factor lifecycle 仍须 `3 -> 0`。

## 不变量与不授权项

| 不变量 | V2-0 结论 |
|---|---|
| ordinary default | 不变；V2 后续必须显式 research-only opt-in |
| QEP / M480 | 不重建 QEP，不改变 M480、branch、beta、normalization 或 key order |
| physical DtN | 不变；producer 不构造或修改 physical DtN，不改 external action |
| global Hybrid | 不改 global operator、recovery、R/T/A 或 ordinary entry point |
| producer | 禁建 V1-3 projected/base factor，禁运行 FGMRES |
| consumer | 禁建 exact-interface oracle，禁读取 producer factor object，禁 QEP/PDE |
| packet route | 只允许 Task40 interface-Schur authority；不重开 Task039 response packet |
| heavy policy | one-heavy；所有 resource/identity/numerical Gate 原样保留并按阶段解释 |

## V2-0 状态与证据入口

| 项目 | 状态 |
|---|---|
| V2-0 inherited audit | 本文完成；不含实现或运行 |
| V2-A/B/C/D/E/F | `not_run_by_gate`；等待本审计提交后按 Review V2 授权顺序执行 |
| V1 scalar negative | 原样保留：`SCALAR_TRANSMISSION_DIRECTIONAL_FAIL` |
| V1-2 / V1-3 | `NOT_QUALIFIED_DUE_RESOURCE_LIFECYCLE_STOP` / `NOT_EVALUATED` |
| V1 raw/compact | 保留在既有 ignored `results/` 与 compact record，未覆盖 |
| 下一步 | 由主审审阅本文后，另行批准 V2-A1 producer 实现 |

完整 V1 数值与资源边界见 [V1-8 summary](summary.md)、[V1-8 response](../response_v2.md) 和
[V1 resource-stop compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_2_v1_3_run_b_resource_stop_v1.json)。
