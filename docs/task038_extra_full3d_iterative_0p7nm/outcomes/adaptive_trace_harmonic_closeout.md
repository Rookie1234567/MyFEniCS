# Review V4：adaptive trace-harmonic lane closeout

本文件记录 Review V4 N0 的容量优先审计。adaptive coarse（自适应粗空间）是给
外层迭代器提供少量固定校正方向的层次结构：它改善低频误差传播慢的问题，但不
改变当前 Maxwell 物理算子。N0 只冻结设计和容量账本；没有运行 N1、p6 basis、
pytest 或 PDE。

## 历史边界与修订后的 N0 分类

| lane | 已有结论 | N0 处理 |
|---|---|---|
| T2 matrix-free volume action | PASS；p6/h10 MPI1 setup current-self RSS `951,054,336 B`，T2 retained payload `6,151,104 B` 已包含在该 baseline 口径内 | 作为在线 runtime lower-bound/calibration；T2 payload不重复相加 |
| T3 dynamic DtN | PASS；动态发现80 modes=`78/0/2`，batch=`8` | 只加入 T3 增量 `2,875,736 B`（retained `2,875,480` + batch work `256`） |
| D1 trace-harmonic small oracle | PASS；p2/p3 fixture，不能外推为 p6 production | 只作代数和 ownership authority |
| D2 rank64 construction | MPI1 controlled negative；固定500步 CG `KSP_DIVERGED_ITS`，construction peak `3,013,468,160 B` | 保留负证据，不重跑、不增加 inner steps |
| Candidate A | physical `rho=0.8145890334049838 > 0.60`；gradient `0.8889127715646881 <=0.90` | 仍是冻结 smoother oracle，不是本 lane 证明 |
| Candidate B | `NOT_APPLICABLE / CANDIDATE_B_INTERIOR_MODAL_AUTHORITY_NOT_QUALIFIED` | 不使用 |
| Candidate C / transmission family | `DO_NOT_RERUN / DO_NOT_OPTIMIZE / DO_NOT_MERGE` research archive | 保留源码和负证据，不表述为数学上永远不可能 |
| Review V4 N0 | `BOUNDED_LOCAL_SPECTRAL_MULTILEVEL_CAPACITY_PREFLIGHT_PASS_CONDITIONAL` | V4 Gate 以完整 central/hard 和架构完整性为准；不授权 N1 |

## 唯一冻结设计

N0 只冻结 `fixed-cell-block-1x1x1-shared-entity-overlap`，不保留 vertex/edge-star
菜单。每个 hexahedral cell 是一个 patch core，最多 `882` 个 cell-supported
full local rows；shared H(curl) edge/facet/vertex rows 在相邻 patch 间重叠，并通过
PoU 合并。这个上限与 global N 无关，patch 数可以增长，但单 patch 和 class cap
不增长。

| 项目 | 冻结值 |
|---|---|
| auxiliary form | `B0(u,v)=∫ μr^-1 curl(u)·conj(curl(v)) dx + k0²∫ |epsilon_r(x)|u·conj(v) dx` |
| local block | cell-supported full local rows 的 constrained auxiliary block；shared rows 留在该 block 中，再在 full-space embedding 时施加 PoU |
| boundary/overlap | 不另设 zero-Dirichlet trace rows；`tau=0`，无 Robin、shift 或 source-dependent boundary项 |
| local factor | lower-packed complex128 Cholesky direct factor；不是 dense LU，不保留 dense factor |
| exact class | Nedelec element、geometry、material、orientation、MPC/Floquet constraint pattern、local row order |
| factor cap | 每 factor `6,230,448 B`；最多32个 exact numeric classes；全局/process-tree 总 factor cap `199,374,336 B` |
| factor build transient | 一次只构造一个 `882×882` complex128 dense block，`12,446,784 B`；factor写入packed storage后释放 dense block |
| local gradient directions | 三个固定坐标梯度 `g_x=∇x`、`g_y=∇y`、`g_z=∇z`，按 local mass 归一化，保持 complex128/MPC phase 语义 |
| local spectral directions | 在三梯度的 M-正交补中取五个最小正 generalized modes，按 `(lambda, exact-class, local-index)` 固定排序 |
| local mode cap | 每 patch恰定上限8（3 gradients + 5 positive spectral directions）；不由 source/residual/rho选择 |
| regional/top | regional rank16长期在线；top rank32的 `Z/AZ`长期在线；levels=2，top rank≤64 |
| ownership | cell core由cell owner持有；shared row由PETSc owner唯一拥有；ghost只做owner-to-consumer routing |
| class-factor ownership | `owner_rank = hash(exact_class_digest) mod mpi_size`；每个 exact class 的 factor 全局只保留一份，MPI2 不在每 rank 复制32份 |
| class route | patch RHS/solution 通过有界的 `882`-entry owner route 到 class owner，再回传结果；class-owner 分配、去重和 MPI1/MPI2 identity 是 N1 必检项 |
| collectives | metadata route、scalar reduction和小型 coarse reduction；无FE-sized numeric allgather、global AIJ/Schur/factor matrix或global direct coarse solve |

若 active rows超过882、factor超过`6,230,448 B`、exact class超过32，或 constraint/
orientation/owner关系不闭合，直接 hard-stop；不合并 class、不改边界、不降低/增加
mode、不调参。

## 证据身份

| 证据 | 身份和关键事实 |
|---|---|
| 当前 N0 source | branch `codex/20260820-task38-extra-full3d-iterative-0p7nm`，source Git SHA `5aaf5748fb24828c3d0d03411df9ff388b4cc2db`，base `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| T2 record | [`t2_p6_h10_mpi1_v1.json`](records/t2_p6_h10_mpi1_v1.json)，SHA-256 `dbf58723adbfd505f5863178c7e012dedd2b393c14b049e149e7e652d7f3dcde`；source `6d60bb5a9a59e88da98b027efeed8506d5dd7a82`；setup self RSS `951,054,336 B`，reference `7.263059324300498e-17` |
| T2 document | [`matrix_free_action.md`](matrix_free_action.md)，文件 SHA-256 `b49a0d94f2a3af0a253fbd689c6d8c8773ae058d1a707854b49fe23ba2295de55`；process-tree未测 |
| T3 document | [`dynamic_dtn.md`](dynamic_dtn.md)，source `691ac261fd62258d356183cb3c0383307605b15e`，文件 SHA-256 `035ec128f70768a9ffa1258d3fac9495eda1c13905e71ae396b41a7543ffb957`；80 modes=`78/0/2` |
| Task037 M3a | [`task37_m3a_mpi_scaling_v1.json`](../../../benchmarks/cases/100_static_condensed_full3d_iterative/records/task37_m3a_mpi_scaling_v1.json)，SHA-256 `12826f33487e85bf26b81fe6a5f6072989fb318f7ac80055bd520724a45b4400`；旧 global/static-condensed inventory，不迁移 |
| remote h2a/h2b/m3y | remote branch `origin/codex/20260806-task37-iterative-extra-development` tip `b8785c53ce12986aa5a63300038c80c7d0ad1798`；只读 `git show`/`ls-tree`。h2a SHA-256 `2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c`，h2b exact SHA-256 `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b`，m3y file SHA-256 `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979`，m3y evidence `605cb0c19e4e7c49d0304471b4e6844d2047f78abca8d20e7692ba524de5b241` |
| D2 record | [`d2_worker_p6_h10_mpi1_v1.json`](records/d2_worker_p6_h10_mpi1_v1.json)，SHA-256 `ef98ba1e7c478b6c6a8297baf599aa34c1849188f3b1668f0cdaf63e4e95635d`；source `cc8de60cc3e21b647aafb29ac9c10b46919823e7`；construction peak `3,013,468,160 B` |

M3Y 的 measured packed-factor evidence 给出 `factor_bytes=6,230,448`、`factor_n=882`
和 isolated JIT stage peak `1,280,749,568 B`；其 builder stage peak 是
`1,068,343,296 B`。它校准 local packed Cholesky 和 isolated cold/JIT 阶段，不能替代
当前 online runtime baseline。旧 M3a 的 global factor CSR
estimate `1,828,829,728 B` 和 G2/HX payload 则只证明被禁止的 global/growing-factor
路线不应迁入本 lane。

## 修订后的容量结论

`N=173802`，complex128 full vector=`2,780,832 B`。标准 right FGMRES restart20
使用 `V_{m+1}+Z_m = 41` 个 full vectors：
`41 × 173802 × 16 = 114,014,112 B`。

T2 MPI1 的 `951,054,336 B` 是 rank-current-self RSS 的 measured lower-bound/calibration，
不是完整 process-tree peak；它已经包含当前 mesh/space/MPC/Python/DOLFINx runtime
baseline 和 T2 retained `6,151,104 B`。账本不再重复加入 T2 retained，只加入 T3
增量和新的 local/coarse/Krylov 对象。由于它不是 process-tree 上界，所有 runtime-bearing
阶段另加独立的 baseline uncertainty reserve：central `32,000,000 B`、hard
`64,000,000 B`；这两个数不与 allocator reserve 混称。该 reserve 同时覆盖 factor
build、local-mode/regional/top build 和 post-setup/online；历史 isolated JIT 阶段仍
使用其单独的 JIT reserve，不用 warm-like 峰值替代 cold authority。

regional rank16 为 `44,493,312 B`，top rank32 `Z+AZ` 为 `177,973,248 B`，两级
coarse 加 `64,000,000 B` metadata/work 为 `286,466,560 B`。local mode cap8
的全部252 patch payload为 `28,449,792 B`。这些数据在 online apply 同时保留，
regional level 不能在 top build 后释放。

新的完整账本和阶段分类见
[`local_spectral_multilevel_preflight.md`](local_spectral_multilevel_preflight.md)
及 [`n0_local_spectral_capacity_v1.json`](records/n0_local_spectral_capacity_v1.json)。
修订后的 V4 complete workflow central=`1,698,919,864 B`、hard=`1,798,919,864 B`，
相对 central/hard 上限的 margin 分别为 `101,080,136 B` 和 `201,080,136 B`；它们
低于 `1,800,000,000 B` / `2,000,000,000 B`，但仍是 derived/budget，不是当前方案
的 measured resource pass。factor build central/hard 为 `1,226,875,456 /
1,290,875,456 B`，local-mode/regional/top build 为 `1,546,030,016 /
1,610,030,016 B`；这些阶段也已包含同一 baseline uncertainty reserve。

N0 不授权 N1。后续若冷启动、factor build、mode/coarse build、post-setup或在线
watchdog 任一阶段超过账本、swap非零、dense transient未释放或出现任一禁止项，
必须保存真实负证据并停止；不能通过预热 cache、减少 rank 或改 boundary 掩盖。
