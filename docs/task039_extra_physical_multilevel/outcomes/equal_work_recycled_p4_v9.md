# Task39extra V9：等新工作量复用对照与原始外层收口

本报告登记 V9 的 L0–L2 结果。V9 固定每次非零 I4 最多 16 个新 B4/Arnoldi 方向，并最多复用 8 对方向；它回答的是当前 `rank8/entity` 组合在相同新搜索上限下是否有可转化的外层收益，不是对所有 recycling、rank 或谱原因的定理判断。

## 结论

| 范围 | measured 结果 | 登记结论 |
|---|---:|---|
| L1 equal-new-work controls | 12/12 I4 rows 完成 16 个新 B4；6 个成对 RHS，去除冷启动后 5 个有效 pair；`G=0.4822327326491708`、`q<1=0.8`、`qmax=1.5802611912316964`、CARRY/RESET 时间比 `1.1568289908802627` | `L1_ADMISSION_OPEN`；控制质量和代数闭合有效，时间收益不一致，允许进入 L2 |
| L2 original | 76/76 I4 rows 完成 16 个新 B4；B4=`1216`、A4 matvec=`1292`、explicit A4=`168`；最大 I4=`21.477697932044975 s` | 等新工作量确实执行；I4/screen/cost 完整性通过 |
| L2 outer screen | 第一个安全检查点在 solve `1842.2495024400364 s`、PC `38`，full explicit true residual `0.1292009191903606`，高于 `0.10` | `TIME_PROGRESS_SCREEN_STOP`；没有达到继续投入门槛，也没有生成 official 物理结果 |
| 总状态 | worker/独立 checker 为 `TIME_PROGRESS_SCREEN_STOP`；runner parent 为 `WORKER_FAILED`、exit `4` | `EQUAL_WORK_RECYCLE_BOUNDED_NEGATIVE`；这是外层进展负结果，不是 swap/OOM 或清场故障 |

正式运行绑定 source `55b7325cae8477ded7b04cfab42181f18e035a0f`、13.5 nm、p6/h10、252 cells、complex128、MPI1、zero outer guess、empty pool、`right FGMRES32`。源码、输入、物理模型和 mode 身份见 [compact record](records/equal_work_recycled_p4_v9.json)。

复用此前求解方向的目的，是把已经发现的有效子空间再次用于新 RHS，减少一部分难误差的探索工作。代价是本轮仍固定支付 16 个新方向，并为池更新承担更多正交化与细化费用；因此 `G`/`q` 只是由实测残差推导出的指标，不是独立测得的物理量。

## L1：控制池有质量信号，但没有证明完整外层收益

RESET16 与 CARRY16 都完整执行 6 个固定 RHS，每项新工作为 16 个 B4。第一项是冷启动，按合同不进入投入统计；其余 5 个有效 pair 如下。`q` 是 CARRY/RESET 的原始 A4 相对残差比，时间和残差均为实测字段。

| 有效 RHS | RESET 秒 / rho | CARRY 秒 / rho | q |
|---|---:|---:|---:|
| A2R160 `p4_02` | `16.15620696602855` / `0.006682542877458616` | `16.93990526907146` / `0.01056016316798964` | `1.5802611912316964` |
| LIGHT448 `p4_09` | `16.15868292900268` / `0.30047937256932766` | `19.902967919013463` / `0.127165209596087` | `0.42320778464334347` |
| LIGHT448 `p4_10` | `16.16251050995197` / `0.005571467192068211` | `21.965383620001376` / `0.0031040725891846163` | `0.5571373719302722` |
| JOINT448 `p4_17` | `16.11429065000266` / `0.2599649952979579` | `18.745497990050353` / `0.051877465413138285` | `0.19955557998752532` |
| JOINT448 `p4_18` | `16.23732941795606` / `0.005860650030559121` | `18.524315103073604` / `0.002055514418206069` | `0.3507314730427553` |

五个有效 pair 中四个 q 小于 1，但 A2R160 的 q 大于 1；因此这是一项合约内的有限控制收益证据，不是“复用必然加速”。L1 两次完整 BAL_H control 的 PC 秒数为 A2R160 `47.372170652 s`、LIGHT448 `41.101025191 s`；两次 closure relative 分别为 `7.4466e-12`、`8.04426213727099e-12`，均低于 `1e-8`。L1 terminal monotonic 为 `486.3775251311017 s`，账本保守 charge 为 `530.530732766 s`；process-tree RSS 峰 `1504464896 B`，job swap peak `0 B`、global pswpin/pswpout delta `0/0`，后代清场。

全六个序列行（包括被 admission 排除的冷启动 pair）的累计 RESET/CARRY 时间为 `96.98303711495828 s / 112.19278895820025 s`，CARRY 比 RESET 多 `15.68%`；上表的五个有效 pair 则分别排除了冷启动后再计算 `q` 与 admission。

这些控制场只证明在有限 RHS 上池更新、A4 配对、eps 闭合和固定新工作记录是可审计的；它们没有把控制池或控制解带入 L2，也没有证明完整 p6 外层会按同样比例改善。

## L2：完整原始模型的受控负结果

### 等新工作和内部成本

L2 的 76 次 I4 全部为 `INNER_APPROXIMATE_RETURN/MAXITER_ONE`，每次 `completed_new_B4=16`、`discarded_new_B4=0`，共 1216 个新 B4；没有因为池满而退回 8 步。池在第 8 次 I4 结束达到 rank 8，第 9 次起使用 `m_call=16`，但新工作仍固定为 16。逐 I4 的完整标量成本、残差、pool rank、payload 和状态保存在 compact 的 `per_i4_scalar_cost_rows` 中；原始 JSONL 不上传、不改写。

| 项目 | L2 measured/derived |
|---|---:|
| I4 / completed new B4 | `76` / `1216` |
| A4 matvec / explicit A4 | `1292` / `168` |
| 最大 I4 elapsed | `21.477697932044975 s` |
| I4 instrumented payload peak | `90099456 B`，配置 cap `134217728 B` |
| 最终持久池 | `8` 对，数值载荷 `12533760 B` |
| native exit spot check | `8` 个退出抽查列，最大相对误差 `2.0690764445140585e-12` |
| BAL_H 退出 eps closure | relative `1.7869676338305148e-12`，limit `1e-8` |

其中 payload 是 I4 搜索向量、池、QR/SVD 临时量、适配向量和索引的 instrumented/derived ledger，不是 RSS；完整进程树 RSS 必须单独看资源表。native 退出抽查的误差定义为 `||A4U-Q||/||Q||`，这里的 `8` 是退出时抽查的列数，不是本次运行所有 native 调用的总次数。

### 外层时间筛选、终态和资源

每 8 步保存真实残差，每 32 步保存 regular checkpoint。第 32 步在 solve `1549.0652761079239 s` 时为 `0.1312380111087104`；第 38 步在首个可用的 1800 s 之后安全检查，残差仅降至 `0.1292009191903606`，相对 32 步约下降 `1.55%`（derived），仍高于 `0.10`，所以按合同停止。`5400 s / 1e-3` 和 `1e-6` Gate 均未到达。

终端解仍以 checkpoint 绑定：iteration `38`、solution SHA `96e8cc5629da1026288dbd1b68159d744fd1080ada2e39f30f4422c64dd375df`、manifest SHA `2ff3b11926cd7ae688f24c9ef60a283d512f15017b53a74c39e02bbff5a685e0`。它是可复核的未收敛解，不是 official field。

| 资源/时间字段 | 实测值与语义 |
|---|---:|
| solve monotonic / conservative | `1697.28324939101 s` / `1852.8785850500237 s` |
| workflow monotonic / conservative charge | `1898.7580305780284 s` / `2071.995232478 s` |
| process-tree RSS peak | `1426276352 B`，sampled simultaneous RSS |
| job swap peak / global pswpin/pswpout delta | `0 B` / `0,0` pages |
| leader / cleanup | worker exit `4`；descendants cleared，remaining child PIDs `[]` |

`WORKER_FAILED` 是 launcher 对 worker exit 4 的 parent 分类；独立 checker 的 gate failures 只有 fine residual `0.12920091919036078 > 1e-6` 和 official outputs unavailable。没有证据表明本次由于资源不足、swap、MPI 清场或实现异常而停止。V5 条件参考 workflow 的 global `pswpout` 448 页归因仍为 `UNRESOLVED`；V9 的 job 峰值与 global 计数增量为零，不覆盖或改写这条历史限制。

## 与历史模型的并列边界

下表先给出四条路线真正共同的 PC32 measured 节点，再单列接近 1800 s 的实际节点。不同 profile 的每步成本、池策略和停止规则不同；这些表用于标记观测边界，不能从终点或单一 residual 宣称 solver speedup。所有 solve clock 和 residual 均直接取已有 monitor/checker 记录，不对缺失节点插值。

### 共同外层步数：PC32

| 模型 | 实际节点 | solve clock (s) | full explicit true residual | 说明 |
|---|---:|---:|---:|---|
| V5 exact p4 original | 32 | `346.1266279852735` | `0.07312259253902377` | 准确 p4 baseline，后来完整通过 |
| V7 A entity16 | 32 | `1414.3534189191053` | `0.12231307354414034` | bounded candidate，后来中点停止 |
| V8 recycled entity gcrot8 | 32 | `985.3288360418159` | `0.1511040946440908` | `m=8` historical profile，后来 screen stop |
| V9 fixed-new16 | 32 | `1549.0652761079239` | `0.1312380111087104` | 当前等新工作量 profile |

### 接近 1800 s 的实际节点

| 模型 | 实际节点 | solve clock (s) | screen measured true residual | 说明 |
|---|---:|---:|---:|---|
| V5 exact p4 original | 160 | `1730.2127802911145` | `0.0010143070512597125` | 仍在继续；下一实际节点 PC172 为 `1862.0175709868245 s / 0.0009115148645006361` |
| V7 A entity16 | 41 | `1818.5808033521107` | `0.11311148655819143` | screen 后继续，未完成 |
| V8 recycled entity gcrot8 | 59 | `1831.843792324894` | `0.09114277170870651` | screen stop；独立 checker 最终字段为 `0.09114277170870674` |
| V9 fixed-new16 | 38 | `1842.2495024400364` | `0.1292009191903606` | 首个时间筛选点，超过 `0.10`，受控停止 |

V9 的 PC32→PC38 只提供当前 profile 的局部进展信息；不能据此宣称所有 recycling 无效、rank8 不足是唯一根因，或把 L1 的有限控制质量直接推广到完整 outer。

## 物理输出、费用与 selective merge

因为 full explicit residual 未达到 `1e-6`，official E/H、near-field、R/T/A、`A_volume`、80 模式复振幅/逐级功率、notch、recovery 和能量闭合均为 `not_run`，不是物理不匹配。V5 的双模型成功 baseline、V6/V7/V8 raw 与负结果不改判。

L0 只记录 clean-SHA probe `1.853111845 s`，属于 partial；完整实现准备时间为 `unknown`，不能把 `3600 s` reserved 上界当实测。因此现存 partial ledger 不能完整追认整个 `3600 s` preparation Gate；V9 batch ledger 的 `2604.379077089 s` 只包括实际记录的 L0 partial、L1 和 L2 charge，不含未知的完整准备时间，也不能暗示准备 Gate 已完成。L1 外层 charge `530.530732766 s`，L2 外层 charge `2071.995232478 s`；子阶段不重复相加。余数为 `33395.620922911 s`；L2 的 `14400 s` workflow reservation 是 runner 的独立保留额，不是额外 elapsed。

| selective merge 组 | V9 决定 |
|---|---|
| production numerical/core | 不提升 ordinary default；本轮没有完整物理资格 |
| reusable runner/watchdog | 保留既有 bounded lifecycle、screen、zero-swap 和 cleanup 证据；不因负结果改写 runner 语义 |
| checker/benchmark | 只合入 compact/checker 索引；checker 读取原始记录，不把 `WORKER_FAILED` 单独解释成资源失败 |
| compact evidence/docs | 可审阅材料为本报告、`equal_work_recycled_p4_v9.json`、summary/index/test_summary/handoff；raw 大数组留在 ignored artifact |
| research-only | `balanced_h6_entity_gcrot8_new16_v9` / `ENTITY_GCROT8_NEW16`，仅登记为受控负结果 |
| do-not-merge | field/matrix/factor/cache/timeline/checkpoint 大文件，以及未授权 notch、rank/参数扫描和 workstation heavy case |

证据索引：[V9 compact](records/equal_work_recycled_p4_v9.json)、[V9 L2 stop record](../../../benchmarks/artifacts/task39extra/v9_l2_original_p6/55b7325cae8477ded7b04cfab42181f18e035a0f/v9_l2_screen_stop_record.json)、[summary](summary.md)、[run index](records/run_index.json)、[test summary](test_summary.md) 和 [workstation handoff](workstation_handoff.md)。本轮不重跑 L2、不运行 notch/新候选，不构成 `master` merge approval。
