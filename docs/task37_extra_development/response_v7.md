# Task037-extra Response V7：H2A 资源硬停交接

本文件是当前阶段的 consolidated authority。`response_v6.md` 保持冻结，继续作为 H1R3 action-only 资格化交接；本文件只记录 H2A 的失败资源证据，不把未运行的 PDE/KSP 或 smoother 结果写成通过。

## 阶段总表

| 阶段 | 状态 | 证据边界 |
|---|---|---|
| H1R.0 | PASS | progress markers |
| H1R3.0R | PASS | p6/h10 MPI1 action-only |
| H1R3.1 | PASS | p6/h10 MPI2 partition identity |
| H1R3.2 | PASS | p6/h5 MPI1 action-only scaling |
| H2A | **FAIL_RESOURCE / NOT_QUALIFIED** | p6/h10 setup/form-JIT process-tree RSS exceeded 1.1e9 B |
| H2B | `not_run / locked_by_H2A` | H2A 未资格化 |
| DtN / H4A / H4B / PDE / KSP | `not_run / locked_by_H2A` | 无后续运行 |

冻结结论继续有效：G2 LOR-HX=`G2_FAIL`；G3 additive LOR-HX=`prohibited`；old G4 sweep=`prohibited`；旧 H1.2=`CONTROLLED_STOP_TIMEOUT / NOT_QUALIFIED`；ordinary default=`unchanged`。H1R3.0R、H1R3.1、H1R3.2 的 PASS 不被本轮 H2A 失败改写。

## H2A 结论与范围

H2A 想验证的是一种低存储的局部预处理前置条件：把几何、材料、Basix 方向和 Floquet 局部拓扑都相同的 cell 归入 exact class，再为每个 class 保留一个局部 factor。这样可以避免每个 cell 都保存一份 dense tensor/factor，但它仍需要先完成高阶 form JIT 和 class inventory。本轮在该前置阶段因 RSS hard Gate 终止，没有得到 class/factor 或 refinement 数值。

| v5 actual | 值 |
|---|---:|
| source | `26bc171b35cce60b3b9197027e808f0af4d628d0`，起止 clean |
| p6 cells / rows | `252 / 173802`，由 marker 测得 |
| Floquet MPC | `floquet_mpc_ready` 已出现 |
| 最后阶段 | `form_compile_started` |
| constraints | unavailable；没有写入 summary/marker |
| class / factor / payload / refinement | unavailable / not_run |
| process-tree peak | `1,153,503,232 B`，超过 H2A `1,100,000,000 B` |
| swap / completion | `0 B / 26.986158804968 s` |

这不是数值算法 FAIL，也不是数值算法 PASS；它是资源 Gate 失败并因此整体未资格化。

## Review V7 第 10 节逐项回答

| # | 问题 | 当前事实 |
|---:|---|---|
| 1 | exact block class count / refinement 是否有界 | `unavailable`；未到 key discovery，p2/h10 与 p2/h5 未运行 |
| 2 | block factor、wave basis、KSP、DtN、总 live-set | factor、wave basis、KSP、DtN bytes 均 `unavailable/not_run`；仅观测到 H2A form-JIT process-tree peak `1,153,503,232 B` |
| 3 | coercive 四源 contraction / global solve | `not_run` |
| 4 | 75D wave coarse 是否提供全局修正 | `not_run` |
| 5 | matrix-free DtN 与 authority action/recovery 误差 | `not_run` |
| 6 | 20/100/200-step true residual | `not_run` |
| 7 | B2/B4 长尾、beta/Ritz fallback | `not_run` |
| 8 | full PDE 是否达到 `1e-6` true residual | `not_run`；没有 PDE 或 true residual |
| 9 | 正式 PDE peak 是否 `<2,000,000,000 B` | `not_run`；1.153 GB 是 H2A setup preflight，不能冒充 PDE 内存 |
| 10 | R/T/A、体吸收、12/12 power、12/12 amplitude | `not_run` |
| 11 | 失败、修复、clean SHA | v1/v2 为 launch-only；v3 `36272cb...`、v4 `fdda595...`、v5 `26bc171...` 依次保留 direct singleton、default-kernel、O0/g0 证据；v5 后不再 heavy rerun |
| 12 | p6/h1 近线性内存潜力 | H1 action evidence 已存在；H2/PDE near-linear potential 尚未资格化，不能外推 |

### 隔离编译证据的边界

同一 `54,429,950 B` C 文件的 O0 `/usr/bin/cc` 编译为 diagnostic：文件 SHA `556489845e2e85cd8166cc8cb8e259b062a97508f139d86abdcee11105c2aa08`，exit `0`，`7.91 s`，最大 RSS `674,521,088 B`，object `43,713,432 B`。它不是 H2A full process-tree measurement，不能替代正式 Gate。

## 运行次数、证据与边界

641474d/v2 是 PMIx sandbox launch-only，numeric formal attempt 为 0。之后 v3、v4、v5 均进入 direct singleton 的生产 setup；v5 是最后一次授权的 H2A heavy。initial formal 加两次 post-fix heavy rerun 已用完，不越权进行第三次。每次 watchdog 的 raw SHA、compact 和 failure details 见 [`h2_block_class_inventory.md`](outcomes/h2_block_class_inventory.md) 与 [`h2_block_class_inventory.json`](../../benchmarks/cases/101_task37_extra_development/records/h2_block_class_inventory.json)。

| 证据 | 状态 |
|---|---|
| compact file SHA | `bbc4ed0f5568accf3b301dd5af3c8f85744dd1595a0d89390d36cf3c2dcf28d2` |
| compact embedded SHA | `51c2f113a60560761fb38f0c1ca4f7c9f59ee0fadf16098c68b91fd64e1d4594` |
| raw source SHA | `26bc171b35cce60b3b9197027e808f0af4d628d0` |
| checker source SHA | `d65fcfb5b55c92682c74376dbe1fbefe22766f52` |
| checker | exit `1`，`gate_failed`；`measurements=null`，failure evidence 已 hash-bind |
| tests | test288 `30 passed`；286--288 `37 passed`；compileall/diff-check pass；Ruff unavailable |

完整 raw evidence 索引见 [`h2_block_class_inventory.md`](outcomes/h2_block_class_inventory.md)。v5 progress 的关键事实是：`mesh_build_ready`、`function_space_ready`、`floquet_mpc_ready` 均出现，最后为 `form_compile_started`；constraint count、class/factor/payload/refinement 仍 unavailable。

## 用户目标与 selective merge

用户的“MPI1 PDE `<2GB` + 直接法一致物理解”目标尚未达成：本轮没有 PDE、没有 true residual、没有 field/RTA，也没有 direct-method comparison。H2A 的 `1,153,503,232 B` 只是 form-JIT/setup 的 H2A process-tree preflight，不能当成 PDE 内存结果。

H2A cache/runner 在本轮结果下为 research-only、not qualified，不建议提升 production default；compact 与 outcome 作为负证据保留。本轮没有新增或运行 V7 的 H2B/two-level、matrix-free DtN、H4 路径，也没有对应新 record。没有新分支、PR、master 操作，ordinary default unchanged。后续若继续，必须由新 review 授权；本轮不自行实现或启动 V7 后续阶段。
