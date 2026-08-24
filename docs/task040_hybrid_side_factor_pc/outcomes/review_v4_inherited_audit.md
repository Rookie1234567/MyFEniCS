# Task040 V4-0 继承审计

## 状态

`completed_docs_only`。本页只记录 V4-0 的只读身份、冻结边界和已有证据；没有启动
V4-1 或任何 PDE、MPI、factor、QEP、FGMRES、heavy 运行。所有 V4-1 以后阶段仍为
`planned_not_run` 或条件未到达。

## 分支、Review 与环境

| 字段 | 只读值 |
|---|---|
| branch | `codex/20260822-task40-hybrid-side-factor-pc` |
| HEAD / upstream | `0599419e0aca9e3a33d7b4fa7718817a10d3d63a` / 同 SHA |
| ahead / behind | `0 / 0` |
| worktree | clean |
| Review V4 SHA256 | `4e16c3ed2935188a8b2c35ac7cee66540ddcdd994ac67039e98a42746ec1bd46` |
| activation | `_MYFENICS_WSL_QUALIFIED_ACTIVATION=1` |
| Python | `/home/Projects/MyFEniCS/.venv/bin/python` |
| PETSc scalar / index | `complex128` / `int32` |
| MPI / DOLFINx / SLEPc | 同一 WSL Linux ABI 栈；只读 preflight 通过 |
| 主机 inventory | MemAvail 约 `223 GiB`；swap configured `32 GiB`、used `0 B`；磁盘可用约 `758 GiB` |

## 冻结身份与已有 artifact

| 身份或证据 | 值 |
|---|---|
| physical case | `5 nm / 1 deg / phi=0 / S / p6h4 / M480 / MPI8 / threads1` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat` |
| input SHA256 | `4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811` |
| physical SHA256 | `8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c` |
| selected manifest SHA256 | `2dddaf7a6f8f045adabd840970952517d76305c7c0e03c71258642d856c13067` |
| probe manifest SHA256 | `7a03b2cf80fe5081d1fe1248b9d4c79f3ef4e955a8014e905c2f2ca82797baad` |
| exact-spool catalog / run manifest / resolved config | `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` / `292a57cf28bf64f3193357c54a57fed08d9e0d116fdd6da1b41d9b5f347400da` / `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883` |
| V3-2 compact record | `benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v3_2_full_span_consumer_v1.json`；SHA256 `08dd8d7e8d035ed6aeb3140ab675ee92ee7cd9e81942442d74ac0c0f1cc1fcd9` |
| V3-2 formal source / checker source | `c11aea058d01e86052d5490a71575a375e3fe207` / `0fbc33d07d27f8e4b2bce9c2bae2704ea9372c7b` |
| V3-2 formal root | `results/task040_v3_2_full_span_mpi8_c11aea05` |
| V3-2 run / watchdog / timeline | `125e04c30aee500bddb7115a1d1a9ef0cbe84309e53af998d589d59a06b674ae` / `aa4a0b2c959a01c66929f37686e922bb03c59f4cc724b5d5813a287c5e26d5fe` / `e2809753f2a5fb5ae4ff54cea57b67acc5bd8a5cfbf78d2c51ea2536d672f63e` |
| V3-2 fixed checker artifact | `e4d127090e83580ada4070a5ca558c2a75c045c003d2d61dfbd282df99050750` |
| augmented packet manifest / true joint | `f480189663ef293ec4f809818e322186d75a205f725a3aa35dc12c2d24aad209` / `ed7c973c92ff4704a687c9d61032930bb458076e552892c988990cf893e6e035` |

V2 producer packet、V3-1 augmented packet和V3-2 raw/checker均在 ignored `results/` 中保留；
本次只读 inventory 未加载大数组、未构造 factor。V3-2 的 PSS/USS 没有记录，不能从 RSS
推算。

### 五个 exact-output identity

| label | exact-output identity SHA256 | probe seed / source |
|---|---|---|
| `modal_traction_positive` | `3100fd4f186ba720ef8ef030e4fc45749d6726927e420102884d71016b0fe8cb` | `761` / `positive_traction` |
| `modal_traction_negative` | `a7a42879e64d78e3de3f956747806b628f01fa482bece281a8b20bda1bf065e4` | `763` / `negative_traction` |
| `external_dtn_coupling` | `f0f1c970644aebe13a7fe94806205f83c02c5ea90554ccc2987bd5720d7c37f8` | `769` / `pre_action_components.C` |
| `fixed_random_repeat_0` | `5322aabafa153d073e635fd80aa1f729f7e1c9c98dab2032ef3f2a67d6860baa` | `773` / `fixed_owner_range_formula` |
| `fixed_random_repeat_1` | `51429f3bd4db63c6cb870d10b7e6f757ac82255fa8871bb4af9d8449eeaa2c93` | `779` / `fixed_owner_range_formula` |

## 两种 operator identity 必须分开

V4-1 的首要风险是把 Task039 exact-side authority 与当前 bare-F 误认为同一个算子。
历史 exact-side spool 由 `ResearchExactSideLuAction`/Woodbury 路线产生，逻辑上对应：

```math
A_{side}=F-C H^{-1}D.
```

| operator | 当前可绑定的身份 | action / residual 口径 | V4-1 处理 |
|---|---|---|---|
| `components.F` / bare `F_b` | V3-2 before/after hash `e532b69e2cacc5205454ba42a563b537ccfaf7f9ca67b64be0ea4cfebca9d5b9`，两者相同 | Review §7.2 的正式 Gate 必须使用 `F_b x-b` true residual | 作为 V4-1 当前目标算子，独立记录 hash、action 和 residual |
| `system.A` / `A_side` | 历史 exact-side/Woodbury authority；本轮未把一个新的 current-source matrix hash 写入 V4 record | exact output 的历史 residual 不能自动解释为 bare-F residual；当前 A-side hash/action/residual 绑定仍 `unavailable_not_run` | 先做兼容性核验；若只对 `A_side` 成立而对 `F_b` 不成立，分类为真实 identity conflict，不调阈值或重建 factor 绕过 |

因此 V4-1 不能用 `system.A` residual 代替 `components.F` residual；A-side 结果可以作为解释
字段，但不得成为正式 bare-F Gate。

## V3-2 数值与资源继承

| source | r4 | r8 | r16 |
|---|---:|---:|---:|
| modal traction positive | `0.9931120049` | `0.9908281637` | `0.9753543932` |
| modal traction negative | `0.9947389066` | `0.9916159544` | `0.9753434892` |
| external DtN coupling | `0.9873782795` | `0.9829723344` | `0.9706859881` |
| fixed random repeat 0 | `0.9910369479` | `0.9889049160` | `0.9829154078` |
| fixed random repeat 1 | `0.9920231223` | `0.9893566601` | `0.9832307912` |

V3-2 classification 是 `COUPLED_INTERFACE_FULL_SPAN_NUMERICAL_FAIL`，但 identity、packet、
lifecycle、telemetry 和 resource checks 通过；`conditional32/64=false`，没有 preferred
checkpoint。组件 peak 为 `28,044,996,608 B = 26.118938446045 GiB`、wall
`892.680907273083 s`、swap `0`，不是完整 workflow saving。

| inherited full-workflow baseline | peak |
|---|---:|
| Hybrid direct | `93.377006531 GiB` |
| exact-side Hybrid iterative | `80.025856018 GiB` |
| V3-2 full-span component | `26.118938446045 GiB`，component/oracle diagnostic only |

## V4 冻结、授权与禁止

| 类别 | V4-0 继承口径 |
|---|---|
| 冻结 | `5 nm / 1° / phi=0 / S / p6h4 / M480 / MPI8 / threads1`；material、geometry、Floquet、selected mode、static condensation、DtN、global Hybrid、ordinary defaults不变 |
| 可读 authority | 仅允许读取 hash-bound exact spool；不重建 full-side exact factor；V3-2 packet 只作既有机制证据，不能自动变成 production input |
| V4-2 条件对照 | 仅在 V4-1 分类为 `DUAL_PROJECTION_INSUFFICIENT` 或 `TWO_LEVEL_COMPOSITION_INSUFFICIENT` 时，才可做一个固定 dual 或 one pre/post composition 对照 |
| V4-3 训练 | 固定三源 train：modal+、external、random0；holdout 固定 modal-、random1；最多 `R1/R2/R3` |
| V4-4 长方向 | 只跑 external 与 random0；连续 right-FGMRES `16/32/64/128`，条件 `256`；不授权 `512/1000` |
| V4-5 bounded rank | 总 coarse rank 仅 `64/128/256/512`；最多两个 rank 进入五源 heavy screen |
| V4-6 以后 | 先证明 packet-independent online reconstruction，再谈 bounded local patch、bottom/top/full 和 h3 |
| 禁止 | 改物理/mesh/M480/QEP/DtN/global operator；beta/sign/damping/sweep/ILU/BLR/restart 参数扫描；增加 overlap/分区或 coarse family；重跑 direct/V7、完整 0.7 nm PDE；把 exact output/raw RHS作为生产 basis；修改 ordinary defaults |

## V4-0 至 V4-10 顺序与真实停止 Gate

| 阶段 | frozen scope | 当前状态 | 真实停止或进入条件 |
|---|---|---|---|
| V4-0 | 继承身份与 docs-only audit | `completed_docs_only` | 只读身份不匹配则停止；本次已通过 |
| V4-1 | exact trace compatibility、Petrov/best projection、三维 lift | `planned_not_run` | exact authority 与 bare-F 不兼容，或 lift identity 不成立，则停止 |
| V4-2 | 条件 dual 或固定 two-level 对照 | `planned_conditional_not_run` | 仅由 V4-1 的明确诊断授权；未通过则进入 V4-3，不扫描更多菜单 |
| V4-3 | fixed train/holdout response enrichment | `planned_conditional_not_run` | `RESPONSE_TRACE_ENRICHMENT_NO_SIGNAL` 时停止当前 coarse family；PASS/OVERFIT 才能进 V4-4 |
| V4-4 | 两源 continuous FGMRES/Ritz direction sampler | `planned_conditional_not_run` | 与 V4-3 同为 pure stagnation 且无共享慢方向时停止 |
| V4-5 | 总 rank 64/128/256/512 bounded coarse audit | `planned_conditional_not_run` | rank512 仍不满足 lift/holdout 条件时 `BOUNDED_RESPONSE_COARSE_NOT_ESTABLISHED_BY_RANK512` |
| V4-6 | fresh packet-independent online reconstruction | `planned_conditional_not_run` | 不能移除 exact authority 依赖时 `EXACT_ORACLE_DEPENDENCE_NOT_REMOVED` |
| V4-7 | bounded local patch Level B | `planned_conditional_not_run` | local-row cap、factor、RSS、swap 或 residual Gate 失败时停止 |
| V4-8 | bottom/top/both/full Hybrid | `planned_conditional_not_run` | 同配置 top、full residual/physics/resource 任一失败时停止 |
| V4-9 | 条件 p6/h3 scaling probe | `planned_conditional_not_run` | `p_mem>1.30`、rank/rows/factor/swap 合同失败时停止 |
| V4-10 | evidence、Pareto、`response_v5.md` | `planned_closeout` | 只收口已完成证据；不把未运行阶段写成通过 |

## 缺失项与后续最小复用边界

当前没有 V4-1 trace/lift artifact、bare-F 对 exact authority 的兼容性结果、V4-3/4/5
direction/coarse selection、packet-independent reconstruction、bounded local factor 或 h3
数据。V4-1 预计复用现有 V3 PETSc carrier、canonical owner-row/remap、exact-output metadata
hash loader 和独立 checker 的纯身份读取；新的数值核心只应放在 `src/solvers`，runner/checker
仅编排和重算。不得复制整套 runner，也不得把 `A_side` residual 静默当作 `F_b` Gate。
