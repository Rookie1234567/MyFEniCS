# Response V29：Review V26 / V28 修复后正式验证收口

## 修复后最新状态

按明确授权完成一次 V28 修复后 original p6/h7.5、990 cells、80个DtN通道、MPI1/thread1正式验证，worker exit0、126步，独立最终显式真残差 `9.283164917015627e-7`（门限 `1e-6`），dynamic audit、同网格全 FE `L2/scaled-curl`、80模态功率、E/H/curl 导出均通过。V28 相对 R2 的 workflow monotonic/conservative realtime budget 为 `2936.076242/3203.447880 s`，R2 对应 `3114.283620/3407.555410 s`；同钟差值分别 `178.207378 s (5.72%)`、`204.107530 s (5.99%)`。这是一场运行的观察，不单独证明因果加速；R2 仍作比较分母，默认不变。

修复后峰值为进程树 RSS/PSS `7,356,289,024/7,324,145,664 B`，10,901个样本且 PSS 全可读，swap=0。A6 live action 263次累计 `517.325 s`，比 R2同计数 `823.164 s` 低37.15%；H6 apply 131次累计 `527.518 s`，比 R2 `484.894 s` 高8.79%，这是描述性观测，不用来归因 shared-contraction 效果。H6 shared-contraction 候选未采用，是因为此前组件 AB/BA 证据未能显示可重复收益。仍按单线程运行。下一步具名 profiling 目标是 BAL_H C（累计851.401 s）；计时类别重叠，尚不能称为独占热点。conservative realtime 的权威对照字段是 wrapper 完整边界 `run_summary.json.workflow_clock_interval.budget_seconds=3203.447879573999`。完整 i16…i112 残差/耗时比较、p4/A4/P-PH分项、功率、artifact hash 与累计尝试账本 `3902.9635367376695 s`（不是单场 runtime）见 [V28 outcome](outcomes/fused_operator_speed_v28.md) 与 [post-repair compact](outcomes/records/fused_operator_speed_v28_post_repair_compact.json)。此前修复前 `WORKER_FAILED_BEFORE_KSP` 与 ledger 分项保留在原记录中，未被覆盖。额外 PDE 仍需新的明确授权。

## 修复前结论（历史阶段记录，保留）

A6 fusion-only 的保存向量工程结果支持把该候选送入本批正式测试，但正式 V28 case 在 KSP 第 1 步之前触发库存接口 `KeyError`。所以本批**正式回归未完成、端到端收益未证、物理结果不可用**。本次失败后的 14 行生产改动和小网格回归测试通过，但尚无修复后 fresh PDE 证据。r2 仍是最快整场基线；ordinary default 不变；本批不再运行第三场 PDE。下一次 fresh regression 必须另有明确授权。共享 workflow ledger 原件及 SHA 已进入 compact record；两次 settled worker 合计 `699.5099493818448 s`，分项 `338.8901043349492/360.61984504689553 s`。它与 replay run-summary 的 `360.618731128 s` 是不同计时边界。组件配对的完整 AB/BA 三轮 wall/CPU 数组见 [component record](outcomes/records/fused_operator_speed_v28_components.json)，A6 raw partial-derived 文件的身份捕获限制见 V28 outcome。

## 修复前逐项回应（历史记录，保留）

| Review 问题 | 回答 |
|---|---|
| A6 实际减少哪些重复步骤？ | 对同一单元批次只做一次 gather、MPC/方向展开和 Nédélec→多项式系数变换；curl、复材料 mass 各保留原积分点与积分规则，在共同系数空间合并后只做一次反变换、方向拉回和 scatter，DtN 仍只加一次。保存向量 full-action wall 中位数 early `3.344916 → 1.929905 s`、late `3.406328 → 1.979749 s`。live formal logical-call counters 未保存；不据此写正式次数或整场收益。 |
| H6 少做哪些收缩？ | 候选 forward contractions `6696 → 5208/apply`，少 `22.22%`；输出一致，但 wall 差小且 trial ranges overlap，未采用 shared-contraction H6。 |
| 组件与完整 p4 case 分别快多少？ | 只有上述组件中位数是工程测量。p4 factor 本次 numeric `201.553137 s` 是 setup 成本，不是迭代速度。正式迭代未开始，所以整场、KSP、p4 case speedup 均 `unknown`；禁止拿约 `360.619 s` 的失败流程除以完整 r2 当加速。 |
| 每步/setup 花多久？ | 无 Krylov iteration，故用户要求的16步汇报点未到；任务合同的每8步 residual 与每32步 field checkpoints 也均 `not_run`。已独立记录 p4 symbolic/numeric 与若干 H6 setup 子计时；完整 setup 与 KSP time `unknown`，不把嵌套子项相加。 |
| 峰值是否增加？ | 本次未完成流程同时进程树 RSS/PSS peak 为 `6,569,861,120/6,537,753,600 B`；1256个PSS样本均可读，swap `0`。只描述到失败为止，不是完整 solver lifecycle peak，不能证明比 r2 少内存。 |
| 阶段线程有无尝试？ | 没有；两线程能力和完整生命周期峰值中性未资格化，保留单线程。 |
| 最终场和功率是否保持？ | 无最终场、R/T/A、逐模态功率或 closure 数据，不能判定本次 final-field regression。 |
| N0/N3/N6 到哪一步？ | N0 profile/launcher/workspace mock 与 small-fixture tests 通过；N3 选择 A6 fusion-only（shared contractions=false、单线程），但未获 fresh PDE qualification；N6 的负结果、hash、测试和 decision 已归档，数值终态 Gate 都 `not_run`。 |
| 下一最大热点？ | 此次停在迭代前，无法从正式 KSP 指认；本批组件失败/重复停止和 H6 engineering 成本保留在 [component record](outcomes/records/fused_operator_speed_v28_components.json)，不从 setup 差值造热点。 |

修复前失败阶段使用的 Review V26 R2 完成场参考为 workflow/KSP/setup `3114.283619607013/2284.681783819/781.971881371981 s`、126步、最终 residual `9.283165086752956e-7`、全流程 RSS/PSS `7,390,937,088/7,354,803,200 B`。当时失败成本不能与其比较；修复后同口径实测对照见上方最新状态和 V28 outcome。

## 根因与修复

消费者 `physical_p4_schur_v14.py` 严格要求每个 candidate owner audit 暴露 `retained_numeric_payload_components`。fused owner 实际在 `shared_fullspace_mpc_action` 下；factory 却将两个 borrowed local-kernel view 当成完整 owner 审计，导致缺键。修复在 fused 路径只登记一次共享 owner，split 路径维持两个独立 owner；融合临时预算统一从现有 `kernel_temporary_bytes` 事实传给 workspace consumer。small fixture 覆盖 factory 返回审计及同一严格库存/预算读取路径，正式 `shared_contractions=False`。

源代码与 focused regression 提交：`f403cf126817a9019d2be59df6b2be6fc0d6bffd`。qualified activation 下相关三文件 `15 passed in 1.44 s`；最终文档合同 `21 passed in 0.06 s`；JSON parse、compileall 与 diff check 通过。该修复没有 fresh PDE qualification。

完整阶段事实、三个启动/运行尝试、资源口径、证据 hash 和不重跑决定见 [V28 outcome](outcomes/fused_operator_speed_v28.md)、[compact record](outcomes/records/fused_operator_speed_v28_compact.json)、[decision record](outcomes/records/fused_operator_speed_v28_decision.json) 与 [selective merge manifest](outcomes/selective_merge_manifest_v28.md)。本轮测试是本地 targeted tests；full repository pytest、Ruff、CI 未运行/未声称。
