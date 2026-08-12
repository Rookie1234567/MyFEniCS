# M3Y 全 84 个 packed row-complete factor 收口

## 结论

M3Y 是在用户明确授权下开启的 research-only、opt-in 路线：它把每个 882 行完整 patch 的 Hermitian 正定矩阵只保存为一维 lower packed complex128 Cholesky 因子。这样 loader 可以用 mmap 和三角求解读取因子，不需要长期保留方阵 factor 或 84 份 patch；packed action 的独立重算由 checker 完成。它验证的是这条局部 factor-store 路径，不是 PDE 资格化。

用户明确授权越过 Review V11 的 M2→M3 阶段锁及“禁止 84 个完整 882D factors”的限制；该授权没有放宽数值、容量、RSS、swap、full-space、provenance 或物理 Gate。M2 的正式 `FORMAL_NUMERIC_FAIL` 保持不变。

| 项目 | 结果 |
| --- | --- |
| 路线 | `M3Y`，packed row-complete factor store，research-only |
| 正式状态 | `PASS / QUALIFIED`（仅 M3Y 路线） |
| source / checker | `404f6c6a5326219bcf6aca098b332b68214781a3` / 同一 clean SHA |
| raw / compact | `benchmarks/artifacts/task037_extra_development/m3y_404f6c6_run1` / `benchmarks/cases/101_task37_extra_development/records/m3y_full_packed_patch_store.json` |
| M2 关系 | M2 `FORMAL_NUMERIC_FAIL` 不被改写，M3Y 是后续明确授权的新实验路线 |
| 普通默认路径 | 未改变 |

## 固定问题与拓扑

| 量 | 实测值 |
| --- | ---: |
| degree / `h_nm` | `6` / `10.0` |
| MPI | `1` |
| cells / classes / neighborhoods | `252 / 24 / 84` |
| row-complete patch rows / local nloc | `882 / 882` |
| global rows / constraints | `173802 / 9210` |
| factor count | `84`（上限 `96`） |
| factorization | lower packed complex128 Cholesky，SciPy `zpptrf/zpptrs` authority |

每个 factor 绑定自己的 row-complete matrix SHA、factor SHA、neighborhood/cell mapping 和固定 RHS solve 证据；抽样 neighborhood `0/41/83` 的重复 matrix/factor SHA 一致，全部 84 个 factor 的 solve/action 均记录为 finite、deterministic。builder 逐个生成并释放 patch，未把 84 个 dense patch 留在内存中。

## 资源与数值 Gate

| Gate | 限值 | 实测/状态 |
| --- | ---: | ---: |
| isolated JIT stage process-tree RSS | `<1,800,000,000 B` | `1,280,749,568 B` |
| builder process-tree RSS | `<1,800,000,000 B` | `1,068,343,296 B` |
| fresh mmap loader process-tree RSS | `<1,050,000,000 B` | `575,459,328 B` |
| 各阶段 swap | `0 B` | `0 B` |
| process cleanup | 全部退出 | `true` |
| packed factors | `<=96` | `84` |
| packed factor bytes | 由 `882*883/2*16` 计算 | `523,357,632 B` |
| metadata/mapping bytes | 实际数组和 identity 计数 | `1,838,930 B` |
| retained total | `<=560,000,000 B` | `525,196,562 B`，PASS |
| action closure / solve residual | `<=1e-11` | 最大均为 `8.402445013054496e-12`，PASS |
| predicted builder/online live set | `<=1,750,000,000 B` | `1,346,005,004 B`，`predicted`，不是实测 |

checker 从 raw 的 factor files、mapping、manifest 和 loader 记录独立重算了固定 RHS solve 及 packed factor action。最终 compact 的 20 项 checks 全部为 `true`，`problems=[]`，`status=pass`。

## 存储与禁止项核对

| 项目 | 结果 |
| --- | --- |
| fresh loader | factor arrays 为 read-only mmap，`mmap_backed=true` |
| square dense factors / pivots | `full_dense_factor_count=0`，`pivots_retained=false` |
| patch / global materialization | `patch_matrices=false`，`global_matrix=false`，`global_constraint_matrix=false` |
| Schur / static condensation / trace slab | 均为 `false` |
| QL/QH transform / per-cell factor | 均为 `false` |
| PDE、KSP、field、RTA | 本路线未运行 |

因此该证据只证明 packed local store 的构造、冷载、mapping、固定 solve 和 action closure；不证明全局 assembled matrix、PDE true residual、direct-authority physics comparison 或最终 RSS 目标。

## 代码与测试

M3Y 代码分为薄 runner 编排和已有 P1/R2 authority 复用；packed factor 的数值核心保持在 research-only store 模块。相关代码提交链为：

| 提交 | 作用 |
| --- | --- |
| `12777a72497a98576bcb8caa15d58b13a0c837c0` | M3Y builder/loader/watchdog/checker 初始实现与 test308 |
| `b8afa94dd93fca3336660c1e78c52021843acf92` | checker resource/identity/independent solve 收紧 |
| `404f6c6a5326219bcf6aca098b332b68214781a3` | packed BLAS action 修正及最终 formal source |

正式运行前的轻量验证为 `39 passed`，并完成 compileall、AST duplicate-key 检查和 `git diff --check`；Ruff 在该环境不可用。formal watchdog 与独立 `m3y-check` 不是 pytest qualification 的替代品，而是本次 raw/compact Gate 证据。

## 证据索引

| 证据 | SHA / 说明 |
| --- | --- |
| watchdog summary | `bd364d928a45fda15f49c8890c76ea6a59029b6320221cc7ec546b73f32fdeb8` |
| stage summary | `250e61783bf97ceb9a74fde8bf52910ad7d4f7d609fdfff852f098a6f814204c` |
| builder summary | `d0d7d3a80384994b3415dc41ac3e1b816c35b6ff0682fd3ad8384bb3a8fcb652` |
| loader summary | `eece84bb7250a80967665a0d63aef91dc9a0bd34366f69e2f506200a1e30ab82` |
| builder progress / timeline | `5676e6074bdb0a219cc7f96c26ea03071d74b2885e7481cb3633743f8d7aa2af` / `213d8dc29598b3487f2278b684a09eb4174f2f8791dcfe00acaa339f59714512` |
| loader progress / timeline | `da0a2c7aeb10f406357d486af76c6dbc9f89b266dea712044b7f70c732cca2f1` / `80c29993fe52821ec2711c6b1d52e45027289a81f6f8b4b656fc02713410c1a6` |
| stage progress / timeline | `1648701c75611f180a0c7d7444584ff25f63f815742f21cbc4a45ed19fe8a60d` / `3d79487825b847a7fd23f67d485c995c0874ff5b1389b1909577913bbcdc0b0a` |
| manifest | `949c04da123ccf1e0014a301f617e3a9509b9aaed365793948c469e12feade17` |
| compact file | `f40d6e27c628b946f9ff735027e966cd192748322aa29f752f27ebc4daeab979` |
| compact embedded evidence | `605cb0c19e4e7c49d0304474b1e6844d2047f78abca8d20e7692ba524de5b241` |
| frozen M2 v2 compact | `ebd512aa0e4b6823d5d95c5f816cc6e898c9fd97392af4f7346c83ba3ac4e31f`，未改变 |

## 后续边界

M4、M5、M6 已获用户明确授权继续，但当前仍为 `not_run_yet`；H2B-K、H2D、H4、PDE、official field/RTA、full true residual 和直接法权威物理对照也未运行。M3Y 的 PASS 不能被提升为“最终目标已达成”，也不能用 stage、builder 或 loader 峰值替代 PDE process-tree RSS。后续研究可在该授权边界内继续，但 M3Y 本身不等价于 PDE qualification。
