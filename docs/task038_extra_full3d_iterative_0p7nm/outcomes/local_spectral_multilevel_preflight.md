# Review V4 N0：bounded local spectral multilevel capacity preflight

## 1. 结论先行

adaptive coarse（自适应粗空间）是在外层 FGMRES 中保留少量、固定规则选出的
校正方向；它解决低频误差传播慢的问题，不改变当前 Maxwell physical action。N0
只回答“完整 setup+online+Krylov 的字节账本能否落入 V4 的 central/hard 线”，不
运行 N1、p6 basis、pytest 或 PDE。

| V4 N0 Gate | 结果 | 口径 |
|---|---:|---|
| central complete workflow | `1,698,919,864 B < 1,800,000,000 B` | current-self baseline + 新增同时存活项 + `32,000,000 B` runtime/process-tree baseline uncertainty reserve；derived/budget |
| hard complete workflow | `1,798,919,864 B < 2,000,000,000 B` | current-self baseline + hard reserves + `64,000,000 B` runtime/process-tree baseline uncertainty reserve；derived/budget |
| major unknown components | `0` | baseline、所有增量、construction transient、JIT/allocator reserve均有明确阶段口径；不是实测 pass |
| local active DoF cap | `882` | fixed、global-N independent |
| local factor cap | `6,230,448 B/factor`、`32` classes | fixed、global-N independent |
| global class-factor ownership | `199,374,336 B` is one global/process-tree total；每 class 一个 deterministic owner | MPI2 不复制32 factors；N1 必须验证 MPI1/MPI2 owner identity |
| maximum levels / top rank | `2 <= 3` / `32 <= 64` | frozen design |
| forbidden materialization | all false | no global AIJ/Schur/factor matrix、numeric allgather、full basis replication、global direct coarse solve |
| classification | `BOUNDED_LOCAL_SPECTRAL_MULTILEVEL_CAPACITY_PREFLIGHT_PASS_CONDITIONAL` | docs-only；不授权 N1 |

旧 D0 的 `424,000,000 B` 只在历史 D0 语境中保留；它不是 V4 N0 独立 Gate。当前
regional rank16 correction shard必须在线保留并计入，不能通过释放它得到虚假的
“multilevel”或 retained pass。

这不是 numerical/resource qualification：当前方案的 process-tree peak、cgroup
swap、local factor build 和 coarse construction 尚未实测，后续阶段仍必须 watchdog
fail-closed。

## 2. N0 preflight 身份

| 字段 | 实值/解释 |
|---|---|
| canonical worktree | `/home/shenjh/Projects/MyFEniCSx_task37_extra`；Git metadata `.git-codex`；canonical=true |
| branch / HEAD | `codex/20260820-task38-extra-full3d-iterative-0p7nm` / `5aaf5748fb24828c3d0d03411df9ff388b4cc2db` |
| upstream / ahead-behind | same HEAD / `0/0`；merge-base `438caf150439343ee7c4c58ad7e02a3da812a23c` |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `3.12.3`; `/home/shenjh/MyFEniCS-Surrogate/.venv/bin/python`；repo `.venv` symlink的resolved bin与 executable parent一致 |
| MPI | Open MPI `4.1.6`；mpi4py Linux extension；world size1 |
| PETSc/SLEPc | petsc4py/slepc4py均来自 `/usr/lib/petscdir/petsc3.19/...-complex` Linux ABI栈 |
| DOLFINx/Basix | DOLFINx `0.10.0.post2`；Basix `0.10.0` |
| scalar / index | `numpy.complex128` / `numpy.int32` |
| threads | OMP/OpenBLAS/MKL/NUMEXPR均为`1` |
| MemAvailable | `13,482,110,976 B` |
| system swap | total `42,949,672,960 B`；free `42,932,523,008 B`；used `17,149,952 B` |
| current process swap | `/proc/self/status VmSwap=0 kB`；不是 process-tree sample |
| process-tree/cgroup swap | 未启动worker，process-tree `not_measured`；cgroup `memory.swap.current/max`不可用，`not_measured` |
| disk | `/` available `942,367,264,768 B` |
| sandbox note | 默认sandbox PMIx listener探针失败；同一 qualified activation 的受控non-sandbox轻量ABI预检通过；未启动pytest/PDE |

## 3. 实测证据和静态比较

| 来源 | 只读身份/实值 | N0 使用边界 |
|---|---|---|
| T2 p6/h10 MPI1 | [`t2_p6_h10_mpi1_v1.json`](records/t2_p6_h10_mpi1_v1.json)，SHA-256 `dbf58723adbfd505f5863178c7e012dedd2b393c14b049e149e7e652d7f3dcde`；source `6d60bb5a9a59e88da98b027efeed8506d5dd7a82`；`setup_self_rss_bytes=951054336`，T2 retained=`6151104` | runtime baseline lower-bound/calibration；T2 retained已在baseline内 |
| T2/T3 docs | `matrix_free_action.md` SHA-256 `b49a0d94f2a3af0a253fbd689c6d8c8773ae058d1a707854b49fe23ba2295de55`；`dynamic_dtn.md` SHA-256 `035ec128f70768a9ffa1258d3fac9495eda1c13905e71ae396b41a7543ffb957` | T3增量只计 `2,875,736 B`；T2 retained不重复 |
| Task037 M3a | `task37_m3a_mpi_scaling_v1.json` SHA-256 `12826f33487e85bf26b81fe6a5f6072989fb318f7ac80055bd520724a45b4400`；旧 global factor CSR estimate `1,828,829,728 B`；MPI1/2/4/8 memory authority `4.600/5.683/8.266/12.593 GiB` | 旧 static-condensed/global route，只作负边界 |
| remote h2a | remote branch tip `b8785c53ce12986aa5a63300038c80c7d0ad1798`；`h2a_staged_factor_cache.json` SHA-256 `2af81d454b89d63e1a5d03916286b527112dd76da34259712e73557918516c9c`；24 classes/16 unique，retained `201,933,812 B`，peak `717,139,968 B` | 只读 exact-class/owner-local参考 |
| remote h2b exact | `h2b_row_complete_patch_exactclass_v4.json` SHA-256 `2f1862043f9e75002f53230eee86f8c6ee68ac389b319397bd71b3bdd93fc75b`；882 rows，dense block `12,446,784 B`，factor `12,450,312 B`，peak `767,352,832 B` | 冻结 local row/factor上限；不迁移代码 |
| remote h2b cap stop | `h2b_expanded_neighborhood_factor_v3.json` SHA-256 `2e56bab2a4d2b074bdc8cff4a89a1c23dfe1932c4a0d4bceeff960a7d6eb387f`；33 classes > 32 | 超过32 hard-stop，不合并 class |
| remote M3Y | `m3y_full_packed_patch_store.json`；file SHA-256 `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979`，evidence SHA-256 `605cb0c19e4e7c49d0304471b4e6844d2047f78abca8d20e7692ba524de5b241`；factor `6,230,448 B`/`n=882`，isolated JIT stage peak `1,280,749,568 B`，builder stage peak `1,068,343,296 B` | packed Cholesky及isolated JIT calibration；不替代 online baseline |
| remote G2/HX | G2 full factor lower bound `648,750,388 B`；HX retained lower bound `3,128,209,352 B` | 证明global/slab factor route不能迁入 |
| Candidate A/C/D2 | A compact SHA-256 `be39aa9ae8ae3f488dcc145829f6dbcfd836486cfc4016257f0281d70f2a481b`；C `315d247aa65ddf732532e77899578f63775ef725a961527bce14d496465e2d04`；D2 worker `ef98ba1e7c478b6c6a8297baf599aa34c1849188f3b1668f0cdaf63e4e95635d` | 只作历史容量边界；不改写负证据 |

### 3.1 唯一方案选择

| 方案 | 静态问题 | 决策 |
|---|---|---|
| vertex/edge-star | shared entity周围cell数和class/overlap随连接变化，较难给固定 local hard cap | rejected，不进入N1 |
| fixed-cell-block-1x1x1-shared-entity-overlap | 每个core是一个真实hexahedral cell；full local row、constraint和exact class可逐patch审计 | **唯一冻结** |

## 4. 数学、边界和mode合同

唯一 local auxiliary form：

```math
B_0(u,v) = ∫_{Ω_patch} μ_r^{-1} curl(u)·conj(curl(v)) dx
           + k_0^2 ∫_{Ω_patch} |epsilon_r(x)| u·conj(v) dx.
```

它是 cell-supported full local rows 的 constrained auxiliary block。shared rows 不
被写成 zero-Dirichlet 外部行，而是保留在约束 block 中，随后通过 shared-row PoU
嵌入 full space；`tau=0`，没有额外 Robin、shift或 source-dependent boundary项。
这同时解释了 overlap 和 boundary，不再把“zero trace”与“shared-row overlap”混写。

每个 exact class 使用 lower-packed complex128 Cholesky direct factor；存储上限为
`6,230,448 B`，最多32 classes。exact class digest 通过固定
`hash(exact_class_digest) mod mpi_size` 选择唯一 global class owner；每个 class
factor 全局只存一份，非 owner rank 不复制该 factor，patch RHS/solution 通过最多
`882` 个条目的 owner route 传输。因此总上限 `199,374,336 B` 是整个
process-tree/global total，不是 per-rank 上限；N1 必须比较 MPI1/MPI2 的 class-owner
映射和 factor identity。构造某一 class 时最多
有一个 `882×882` complex128 dense block（`12,446,784 B`）作为 transient；写入
packed factor后立即释放，不保存 dense LU、per-cell factor、global factor matrix或growing
slab factor。

每 patch 的固定 complex128 mode 集合为：

1. `g_x=∇x`、`g_y=∇y`、`g_z=∇z` 三个坐标梯度方向，按 local mass 归一化；
   finalized MPC/Floquet phase保留，不能按实数向量处理。
2. 在三梯度张成空间的 local-M 正交补中，取五个最小正 generalized modes，按
   `(lambda, exact-class, local-index)` 稳定排序并 local-M 归一化。

因此每 patch mode cap恰为8，全部252 patches的 owner-local mode payload为
`252×8×882×16=28,449,792 B`。不根据 source、residual、rho、condition或历史
contraction选择方向；若梯度独立性、正交性或正谱条件不能闭合，N1停止。

regional level固定rank16，top level固定rank32；两者都是 online correction，
regional `Z16`不能在top build后释放。levels=2，top rank仍满足V4 `<=64`。
owner routing只传PETSc owner rows到consumer ghosts，class factor route 只传 bounded
`882`-entry patch RHS/solution；numeric collective限于scalar/small coarse reductions；
无FE-sized numeric allgather、per-rank full basis或per-rank factor复制。

## 5. 完整容量账本（十进制 B）

### 5.1 精确算术和 baseline

| 项目 | 数值 | provenance / 是否重复计入 |
|---|---:|---|
| global rows | `N=173802` | current p6/h10 T2 identity |
| one complex128 vector | `N×16=2,780,832` | exact arithmetic |
| T2 current-self baseline | `951,054,336` | measured rank-current MPI1 setup RSS lower-bound/calibration；包含 mesh/space/MPC/Python/DOLFINx runtime 和 T2 retained `6,151,104 B` |
| runtime/process-tree baseline uncertainty reserve | central `32,000,000`；hard `64,000,000` | 因 current-self 不是 process-tree 上界而单独增加；覆盖 factor/local/coarse/online，不与 allocator reserve 混称 |
| T3 increment | `2,875,736` | derived: T3 retained `2,875,480` + fixed batch work `256`；T2 retained不再加 |
| right FGMRES restart20 | `V_{m+1}+Z_m=41` vectors；`41×N×16=114,014,112` | exact arithmetic；不是40 vectors |
| source/residual/solution + 3 work | `6×N×16=16,684,992` | exact arithmetic |
| local mode payload | `252×8×882×16=28,449,792` | exact upper；全部patch计入 |
| regional `Z16` | `16×N×16=44,493,312` | exact arithmetic；长期 online |
| top `Z32+AZ32` | `64×N×16=177,973,248` | exact arithmetic；长期 online |
| coarse metadata/work | `64,000,000` | fixed internal envelope；含 PoU/ownership/class/MPC/E/routing，不是独立替代V4 Gate |

### 5.2 分阶段 live set

| 阶段 | central B | hard B | simultaneous live set / 口径 |
|---|---:|---:|---|
| isolated JIT/cold calibration | `1,280,749,568 + 64,000,000 = 1,344,749,568` | `1,280,749,568 + 256,000,000 = 1,536,749,568` | M3Y isolated JIT stage anchor + separate JIT reserve；不是当前online baseline，不与online相加 |
| factor build | `1,226,875,456` | `1,290,875,456` | T2 baseline + global factor total `199,374,336` + one dense class block `12,446,784` + allocator `32/64 MB` + runtime/process-tree baseline uncertainty `32/64 MB`；dense block构造后释放 |
| local-mode/regional/top build | `1,546,030,016` | `1,610,030,016` | baseline + global factors + local modes + regional16/top32/metadata + six full vectors + allocator `32/64 MB` + same baseline uncertainty `32/64 MB` |
| post-setup/online | **`1,698,919,864`** | **`1,798,919,864`** | baseline + global factor `199,374,336` + modes `28,449,792` + two-level coarse `286,466,560` + FGMRES `114,014,112` + six vectors `16,684,992` + T3 `2,875,736` + telemetry/recovery/allocator `68/136 MB` + baseline uncertainty `32/64 MB` |
| **complete workflow** | **`max=1,698,919,864`** | **`max=1,798,919,864`** | 各阶段取最大，不相加历史独立峰值 |

central margin to `1,800,000,000 B` is `101,080,136 B`; hard margin to
`2,000,000,000 B` is `201,080,136 B`。`951,054,336 B` 不是完整 process-tree
measurement；它是已测 current-self lower bound，未来 watchdog必须证明实际 process-tree
和 cgroup/swap不越过这些阶段 envelope。

### 5.3 provenance closure

| 类别 | 本 N0 字段 |
|---|---|
| measured | T2 setup self RSS `951,054,336 B`；remote M3Y isolated JIT stage `1,280,749,568 B`（builder stage `1,068,343,296 B`）；历史 A/C/D2 peaks |
| exact arithmetic | vector、41 FGMRES vectors、6 work vectors、factor bytes、mode、regional/top payload |
| derived | factor total、T3 increment、stage sums、complete `max()` |
| budget | metadata/work `64 MB`、telemetry `4/8 MB`、recovery `32/64 MB`、allocator `32/64 MB`、runtime/process-tree baseline uncertainty `32/64 MB`、JIT reserve |
| not_measured | current N0 process-tree peak、cgroup swap authority、new factor/mode construction runtime |

`major unknown components=0` 的严格含义是没有遗漏的 live-set类别：runtime baseline、
全部新payload、single-class dense transient、JIT/allocator、telemetry和recovery都
已逐阶段给出测量、精确算术或预算。`not_measured`不被写成 measured pass；后续
resource Gate仍可因实际超限而 hard-stop。

## 6. lifecycle 与禁止项

| 顺序 | 阶段 | 关键生命周期约束 |
|---:|---|---|
| 1 | qualified activation/worktree/ABI/swap/disk preflight | 失败即停，不启动PDE |
| 2 | mesh/space/MPC/Floquet/JIT | 使用isolated cold envelope，不以warm cache隐藏 |
| 3 | fixed cell patch与exact class inventory | 882 rows、32 classes、packed factor cap；超限fail-closed |
| 4 | class owner assignment | exact class digest确定唯一 global owner，去重后每 class 只留一份 factor |
| 5 | factor build | 一次一个dense block，转packed Cholesky后释放dense transient；patch RHS/solution走 bounded `882`-entry owner route |
| 6 | local modes/PoU/regional `Z16` | 三梯度+五正谱方向；regional shard长期保留 |
| 7 | top `Z32/AZ32/E32` | 与regional level同时在线，owner-local sharded |
| 8 | exact T2 volume + streaming T3 DtN + FGMRES restart20 | physical `A`不被local auxiliary或Candidate transmission替换 |
| 9 | cleanup/watchdog | 分别记录post-setup/online process-tree、swap、return和orphan状态 |

禁止：D2 rank64重跑、增加CG步数、改PC/容差、Candidate C/JIT优化、新transmission、
Candidate A参数修改、global AIJ/Schur/factor、FE numeric allgather、per-rank full
basis、global direct coarse solve、rank>64、levels>3、按rho扫描mode/overlap/fill/class。

## 7. 边界与下一步

N0 只说明这一个 fixed local spectral multilevel 设计在容量账本上有可信窗口，不
证明 local factor已构造、mode代数已闭合、coarse contraction已通过或 `<2 GB` 已
实测。N1必须验证三梯度、五正谱方向、constrained B0、MPC/orientation、PoU、
owner/ghost和packed Cholesky closure；之后才能申请N2 cold setup。任一实际阶段超过
账本、swap非零、dense transient未释放或出现禁止项，必须保存真实负证据并停止。
