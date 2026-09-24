# V28：融合算子工程证据与修复后正式验证

## 修复后单次正式验证（最新状态）

在保留修复前 `WORKER_FAILED_BEFORE_KSP` 及两次更早启动/停止记录后，按明确授权完成一次修复后 original p6/h7.5、990 cells、80 个 DtN 通道、MPI1/thread1 的 Q4 正式验证。worker exit 0，完成126步，分类 `DISCRETE_SOLVE_AND_CONSISTENCY_PASS_AUTHORITY_LIMITED`。独立重算最终显式真残差为 `9.283164917015627e-7`，低于 `1e-6` 门限；这是同一离散问题上的通过，不代表连续极限收敛。

| 比较项 | V28 修复后 | R2 参考 | 解释 |
|---|---:|---:|---|
| workflow monotonic | 2936.076242 s | 3114.283620 s | 同口径少178.207378 s（5.72%） |
| workflow conservative realtime budget | 3203.447880 s | 3407.555410 s | 同口径少204.107530 s（5.99%）；V28 本次单次观测，clock discrepancy 为267.372473 s |
| pure KSP | 2113.442535 s | 2284.681784 s | 子阶段时间，不与 workflow 相加 |
| setup | 773.946359 s | 781.971881 s | 子阶段时间，不与 workflow/KSP 重复相加 |
| 进程树 RSS/PSS 峰值 | 7,356,289,024 / 7,324,145,664 B | 7,390,937,088 / 7,354,803,200 B | V28 监控10,901个样本、PSS全可读、swap=0；单次差值不作为已资格化内存收益 |

下表从任务合同每8步保存的原始残差记录中抽取每16步一个点，仅用于便于阅读；合同本身仍是每8步 residual、每32步 field。残差与 R2 只差舍入量级；累计 solve 时间按相同检查点直接比较，R2 仍作为本次比较分母。

| 迭代 | V28 残差 | V28 累计 solve (s) | R2 残差 | R2 累计 solve (s) | R2−V28 (s) |
|---:|---:|---:|---:|---:|---:|
| 16 | 4.143722296393416e-3 | 307.741215 | 4.1437222964080065e-3 | 323.336255 | 15.595039 |
| 32 | 3.3529179602836533e-4 | 615.525273 | 3.352917960387092e-4 | 635.743111 | 20.217838 |
| 48 | 1.9419221395322323e-4 | 925.579195 | 1.9419221371048617e-4 | 957.054663 | 31.475468 |
| 64 | 3.023352344555217e-5 | 1204.548392 | 3.0233523443058283e-5 | 1270.223461 | 65.675069 |
| 80 | 1.7609468797954283e-5 | 1491.888132 | 1.760946862124978e-5 | 1590.695348 | 98.807216 |
| 96 | 3.776699911513131e-6 | 1770.094144 | 3.7766998795463687e-6 | 1903.877056 | 133.782912 |
| 112 | 2.7139958196409527e-6 | 2057.738996 | 2.71399585136905e-6 | 2225.889514 | 168.150517 |

正式阶段计时也以相同 R2 worker summary 分项对照；这些是累计子计时，互有嵌套，不可相加成 workflow。A6 live action 为263次、`517.324812 s`，R2同为263次、`823.163921 s`，本次观测低37.15%；H6 apply为131次、`527.518364 s`，R2同为131次、`484.894140 s`，本次观测较慢8.79%，不据此推断 shared-contraction 的因果效果。H6 shared-contraction 候选未采用，是因为此前组件 AB/BA 证据未能显示可重复收益。p4 reduce/solve/recover 分别为 `76.988877/90.857100/71.475686 s`（R2 `72.140586/90.576005/65.846833 s`）；native A4 为 `457.127983 s`（R2 `416.448960 s`）；P/PH primal/adjoint 为 `78.144684/69.186809 s`（R2 `73.088556/64.878820 s`）。BAL_H 的 A-structure/C/smoother 累计分别为 `530.457791/851.401461/527.618924 s`（R2 `828.179220/790.865228/484.984241 s`）。当前记录最大的具名累计桶为 BAL_H C；由于这些计数会嵌套重叠，只把它作为下一步 profiling 目标，不据此断言独占瓶颈。

在 i=112，V28/R2 的 PSS/RSS 分别为 `7,319,279,616/7,351,422,976 B` 与 `7,354,127,360/7,386,054,656 B`；swap 均为0。official V28 结果为 `R_total=0.3650975537006263`、`T_total=0.013016803347760153`、`A_balance=0.6218856429516136`、`A_volume=0.6218856421339103`，能量闭合误差 `8.18e-10`。对 R2 的80模态归一化功率最大绝对差 `1.09e-14`；同坐标采样场最大相对差 `2.26e-13`；独立全 FE `L2/scaled-curl` 相对差为 `2.38e-14/8.92e-14`，均通过各自门限。80个通道及 E/H/curl 导出检查全通过。

现成 V24 `old_b_regression` 仍返回 `PARTIAL_PASS_POINT_SAMPLES_AND_MODAL_ONLY`，因为它还要求该 root 下的 V24 专用 `engineering/v24_same_discrete_fe_metrics.json` 和成对 watchdog 文件；这些旧版旁证不存在。本次参数化 V28 全 FE 度量另由现成离线脚本独立计算并通过，二者状态均按原值保留，未把 V24 checker 强行改写为全通过。详细 checker JSON、hash、逐步数据及累计尝试账本见 [修复后 compact record](records/fused_operator_speed_v28_post_repair_compact.json)。

本次同口径观察显示 V28 单次 workflow 比 R2 短，但不据单次运行隔离因果加速，也不把单次峰值差声明为内存收益；R2 保持比较分母，ordinary default 不变。conservative realtime 使用 wrapper 完整边界 `run_summary.json.workflow_clock_interval.budget_seconds=3203.447879573999`；监控报告中的 UTC elapsed `3203.447879536` 是另一字段，不混作同一个字段。修复前失败成本仍保留：共享账本 settled 总计 `3902.9635367376695 s`（含此前停止/失败和本次修复后验证，不能当成单次求解时间）。任何进一步 PDE 均需新的明确授权。

## 修复前阶段结论（历史记录，保留）

本批选择 original、13.5 nm、p6/h7.5、990 cells、80 个 DtN 通道、MPI1/thread1 的 A6 融合路线。A6 表示实际有损 Maxwell 体积算子；H6 是 BAL_H 预条件器内的正定辅助算子。小规模/保存向量工程证据支持 A6 fusion-only 候选，但唯一正式场在进入 Krylov 迭代（KSP）前因库存审计接口 `KeyError` 退出。因此本批没有新 solver residual、迭代、场、R/T/A 或端到端耗时；不能证明整场提速或内存节省，r2 仍是正式速度基线，ordinary default 未改变。

## 工程候选（不是完整求解）

| 路线 | 已测事实 | 裁决与边界 |
|---|---|---|
| A6 仅融合 | 同一批单元只做一次 gather、约束/方向展开和 Nédélec→多项式系数变换；curl 与复材料 mass 保留各自原积分点和规则，在共同系数空间合并后共用一次反变换、方向拉回和 scatter，DtN 仍只加一次。保存的 early_i008 full action wall 中位数 `3.344916 → 1.929905 s`；late_i120 `3.406328 → 1.979749 s`。最大相对差分别 `1.94e-16/1.67e-16`（对 split），对 native 为 `7.28e-15/6.56e-15` | 可作为本次正式候选；live-step 底层计数没有记录，不推断次数或整场收益 |
| A6 再加 shared contractions | early/late 候选 wall 中位数 `1.987725/1.967880 s`，对照 `1.959416/1.963857 s`；输出差 `0` | `NOT_ADOPTED`；两个 witness 均未显示更快 |
| H6 shared contractions | forward contraction 每次 `6696 → 5208`（减少 `22.22%`）；early wall `3.959227 → 3.937837 s`，late `3.913098 → 3.881848 s`，观测范围重叠 | `NOT_ADOPTED`；差异不足以确认实际收益，未增加试验 |
| 两线程 setup | 未试；运行时线程控制和全生命周期峰值中性均未证实 | 保持单线程，不装依赖、不另建线程方案 |

这些数字来自受控保存向量的组件配对，不包含完整 p4 因子、FGMRES 历史、正式场恢复和物理后处理，不能与 r2 full/KSP 时间相除后宣称 speedup。修复后正式场中的 A6/H6 与 p4 分项计时见上方新记录；它们仍是累计嵌套子计时，不替代同钟 full-workflow 比较。

## 修复前唯一正式场尝试与分类（负结果保持原分类）

身份：profile `physical_p6_trace_fused_kernel_v28`；input SHA256 `80c1cbcc9c0796f79c567391a8e80466d4a8a138ea0b45b85b2590d38e957b33`；physical-model SHA256 `0875aaf070d88732b09ead8c55a7d4c28dd75f9b329e90f35fea984a0b7464e6`；ordered-mode SHA256 `dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2`；失败运行 source SHA `b97b605d014fd90439b5b3fa471f2570edf1beff`。MPI1、PETSc complex128/int32、单线程；numeric cache 为 build，load count `0`。

| 次序 | 原始分类/事实 | 成本和保留方式 |
|---|---|---|
| 前台启动 `20260923T141356.354598Z` | 在 `/init.scope`，未满足独立 user-service 要求；sidecar 分类 `CONTROLLED_STOP_STARTUP_SCOPE_INVALID`，raw `USER_CONTROLLED_STOP` 保持不改，不视为数值失败 | monotonic `309.280157 s`；ledger settled `338.890104 s`；进程树 RSS 峰值 `5,894,668,288 B`，swap `0`，后代清空。原始 summary 与 sidecar 保留 |
| service admission `myfenics-case-20260923T142032-334083.service` | 因同 source SHA replay gate 在 worker 前拒绝；log 为 `V28 BLR stage Q4_ORIGINAL cannot replay the same source SHA` | 未开始 worker；没有 PDE 数值结果或 ledger reservation；log 保留 |
| 唯一获准 service replay `20260923T144543.633563Z` | user service 隔离有效；p4 factor 和 H6 setup 已执行，随后 worker 在 A6 candidate retained-inventory 消费处抛 `KeyError: 'retained_numeric_payload_components'`。worker/watchdog 分类 `WORKER_FAILED`，exit `4`；异常没有 traceback 文件 | watchdog monotonic `331.061333 s`；run-summary workflow `360.618731 s`，wrapper/workflow 与 watchdog 边界不同，不把两值相减当 clock discrepancy。原始 watchdog `resource_authority.workflow_clock_interval.discrepancy_seconds=29.498677823 s` 是独立记录；同时进程树 RSS/PSS 峰值 `6,569,861,120/6,537,753,600 B`，1256/1256 个 PSS 样本可读，swap `0`，后代已清空。不是完整正式峰值 |

失败代码的消费者严格读取 `audit["retained_numeric_payload_components"]`。fused factory 当时把 borrowed component view 的 local-kernel audit 当成完整 owner 清单；该视图没有此字段。worker 在正式 KSP/第 1 步之前退出，故本次 `iterations=0`，用户要求的16步汇报点没有到达；任务合同的每8步 residual / 每32步 field checkpoint 也都未运行。没有 final true residual、R/T/A、field 或 power。`WORKER_FAILED` 在这里表示软件接口错误，不是 Maxwell 离散不收敛。失败 root 中没有迭代/checkpoint 文件。

共享 workflow ledger 原件 `benchmarks/artifacts/task39extra/fused_operator_speed_v28/review_v26_fused_A6_H6_optional_setup_threads/shared_workflow_ledger.json`（SHA256 `8db4e543149b809e4968d5344cab9d7d4940e1418fb189ec0f6888beb9270bac`）记录两个 fresh workers，累计 settled elapsed `699.5099493818448 s`：第1次 `USER_CONTROLLED_STOP` 为 `338.8901043349492 s`，第2次唯一 bug replay `WORKER_FAILED` 为 `360.61984504689553 s`；`active_attempt=null`，同源 gate 拒绝没有启动 worker、没有 ledger reservation。该 ledger 数值不替代单次 replay run-summary workflow `360.618731128 s`（计时边界不同），也不与 watchdog monotonic `331.061333118 s` 混算。

本次记录到的独立阶段计时仅为：p4 symbolic `0.515182 s`、numeric factor `201.553137 s`（84680 rows）；H6 setup 子计时 B6 shell `0.000665 s`、diagonal `4.489061 s`、selected action `0.434562 s`、power10 `36.818355 s`。这些子项不求和冒充 setup 总时间；完整 setup、KSP、每步时间均为 `unknown/not_run`。失败运行的 partial RSS 也不与 r2 完整流程峰值比较。

Review V26 指定的最近完成 r2 full-run baseline：workflow/KSP/setup=`3114.283619607013/2284.681783819/781.971881371981 s`，126步，最终 true residual `9.283165086752956e-7`，同时进程树 RSS/PSS=`7,390,937,088/7,354,803,200 B`。本次在 KSP 前失败，不能据失败 elapsed/RSS 计算 speedup 或内存收益。

## 修复前的最小修复、测试与阶段决定（该时点记录）

修复提交 `f403cf126817a9019d2be59df6b2be6fc0d6bffd`：fused inventory 改从共享 MPC owner audit 只计一次；split 仍逐个登记两个 owner；fused `kernel_temporary_bytes` 改用已有 fused curl+mass temporary budget；p4 workspace consumer 改读取统一事实字段。新增 small-mesh test 实际调用 packed factory 并走同样的严格库存字段和预算读取路径，覆盖 fused 与 split；使用正式 `shared_contractions=False`，没有建 p4 factor。

qualified WSL activation/ABI preflight 通过（Python `.venv`，PETSc complex128/int32，同一 Linux ABI 栈）。三个 focused test files **15 passed in 1.44 s**；文档合同 **21 passed in 0.06 s**；新增 JSON parse、compileall、`git diff --check` 通过。未运行 full repository pytest、Ruff 或 CI；没有重跑 PDE。

| 阶段 | 状态 | 对结果的含义 |
|---|---|---|
| N0 路由/worker/checker 接口 | profile、launcher/workspace targeted tests 通过 | mock/小 fixture 资格，不含完整数值运行 |
| N1 A6 fusion | 保存向量配对通过，选作正式候选 | 正式 apply 计数未取得，不能外推 full-run |
| N2 共同张量收缩 | A6 增量与 H6 candidate 均未采用 | 不以收缩计数变化宣称 wall 或整场收益 |
| N3 唯一组合 | A6 fusion-only、shared contractions=false、单线程 | formal case 在门前接口失败，组合尚无 fresh PDE qualification |
| N4 optional threads | 未尝试；保留单线程 | 没有线程提速/峰值结论 |
| N5 formal regression | `INCOMPLETE_WORKER_FAILED_BEFORE_KSP` | residual、full/KSP speed、最终物理与全流程峰值均 unavailable |
| N6 收口 | 负结果、raw hashes、测试与决策记录已归档 | 文档/证据收口完成；最终 solver residual/field/physical gates `not_run` |
| adoption/baseline | `NO_FORMAL_ADOPTION; R2_BASELINE_RETAINED` | 不更新最快整场基线、不改默认；修复尚无 fresh PDE 证据 |

后续任何 fresh full regression 需新的明确授权；本批一次性 replay 已消耗，不在本轮另启数值任务。

## 原始证据索引

- 修复前失败 formal raw root：`results/euv_grazing1_phi0/task39extra_v28_fused_kernel_original_h7p5__full3d_iterative__mpi1__Mna/20260923T144543.633563Z/`。
- run summary SHA256 `411a81e05003fdcefc329e7528b601b92ac68d13e787230e97ac5cdb7aa21205`；worker summary SHA256 `048c9016990b790f220bcd7416e476e2444d3ea950f401bc9c062b92d7acdd04`；events SHA256 `68c95c66d12515ae0d6b86d9acff601c5eae53fc8f6d3407475949550e6f6656`。
- watchdog summary SHA256 `085e032e96f2af418df743f6e7e3a4a416a103869d4bd402b05ce747c8a6defb`；watchdog resources SHA256 `8cf09456493e779dcefc79c4bfaa670151ff4ee9456d3bf66941df5135aeec4a`；worker resources SHA256 `86026a31da3b409cc3f87de360e4edb5ebf8c99ef0dccc0404cad0ec3e26d433`。
- 前台 attempt raw `run_summary.json` SHA256 `d4b2ada16fa7be1bd333c7a2f30200d41acd349a5630a9d15922a46ca8753933`；startup sidecar SHA256 `7f51ae5d720fa4b9a09d73f64cd8fe6a3fcfa362c87a12800434c4a148ebdb8c`；replay-gate log SHA256 `7eb78da35d2349652a726058f2044d569df156b910acafb52752316ffdb051b2`。
- 工程/重复尝试成本不合并或清零：[component record](records/fused_operator_speed_v28_components.json) 保存 N1 A6 fusion-only、N2 A6/H6 shared-contraction 候选各自 AB/BA 顺序的三轮 raw wall/CPU 样本，以及 A6 首次 worker error `205.474985 s`、duplicate A6 supervisor-stop `114.445911 s`、H6 engineering run `157.877393 s` 和各自资源/raw hashes。A6 early/late 样本文件由运行后的 partial data 重建并保留 SHA，不是启动时捕获；这些样本只描述组件，不等同正式求解收益。本报告引用其原始分类，不把不同阶段时长相加成一次流程成本。
- 主表格/决策见 [compact record](records/fused_operator_speed_v28_compact.json)、[decision record](records/fused_operator_speed_v28_decision.json) 与 [Response V29](../response_v29.md)。原始 attempt 分类未改写。
- 修复后正式 raw root：`results/euv_grazing1_phi0/task39extra_v28_fused_kernel_original_h7p5_post_repair_v1__full3d_iterative__mpi1__Mna/20260923T225705.444431Z/`；run summary SHA256 `d4dbccdfc59091da89a389be818c0e880e4bcbcfdc6a50e4fd30b7c084eba93a`，worker summary SHA256 `9a18ee7b00cf1bcf0294c3e7d73b53d1f298956ee57d1e03fea3f88958de6c3b`，dynamic checker SHA256 `f466c1b3c5dee9de605b69a191466bba2ab659ff576077b848e4c226c1e79dc0`，same-discrete FE metrics SHA256 `221cc2ab472043a8db6d0cb48a913701cf287d3021fdd70386cdcea3d17b1e71`，saved-output audit SHA256 `1576dc0405f92bc9013e26642744b8f8b804751265eea594d50d790d5b4a0f72`。完整 provenance 见 [修复后 compact record](records/fused_operator_speed_v28_post_repair_compact.json)。
