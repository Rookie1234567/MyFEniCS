# Response V29：Review V26 / V28 正式回归的负结果与接口修复

## 结论

A6 fusion-only 的保存向量工程结果支持把该候选送入本批正式测试，但正式 V28 case 在 KSP 第 1 步之前触发库存接口 `KeyError`。所以本批**正式回归未完成、端到端收益未证、物理结果不可用**。本次失败后的 14 行生产改动和小网格回归测试通过，但尚无修复后 fresh PDE 证据。r2 仍是最快整场基线；ordinary default 不变；本批不再运行第三场 PDE。下一次 fresh regression 必须另有明确授权。共享 workflow ledger 原件及 SHA 已进入 compact record；两次 settled worker 合计 `699.5099493818448 s`，分项 `338.8901043349492/360.61984504689553 s`。它与 replay run-summary 的 `360.618731128 s` 是不同计时边界。组件配对的完整 AB/BA 三轮 wall/CPU 数组见 [component record](outcomes/records/fused_operator_speed_v28_components.json)，A6 raw partial-derived 文件的身份捕获限制见 V28 outcome。

## 逐项回应

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

Review V26 的 r2 完成场基线为 workflow/KSP/setup `3114.283619607013/2284.681783819/781.971881371981 s`、126步、最终 residual `9.283165086752956e-7`、全流程 RSS/PSS `7,390,937,088/7,354,803,200 B`。当前失败成本与资源边界不同，不据此做差后宣称收益。

## 根因与修复

消费者 `physical_p4_schur_v14.py` 严格要求每个 candidate owner audit 暴露 `retained_numeric_payload_components`。fused owner 实际在 `shared_fullspace_mpc_action` 下；factory 却将两个 borrowed local-kernel view 当成完整 owner 审计，导致缺键。修复在 fused 路径只登记一次共享 owner，split 路径维持两个独立 owner；融合临时预算统一从现有 `kernel_temporary_bytes` 事实传给 workspace consumer。small fixture 覆盖 factory 返回审计及同一严格库存/预算读取路径，正式 `shared_contractions=False`。

源代码与 focused regression 提交：`f403cf126817a9019d2be59df6b2be6fc0d6bffd`。qualified activation 下相关三文件 `15 passed in 1.44 s`；最终文档合同 `21 passed in 0.06 s`；JSON parse、compileall 与 diff check 通过。该修复没有 fresh PDE qualification。

完整阶段事实、三个启动/运行尝试、资源口径、证据 hash 和不重跑决定见 [V28 outcome](outcomes/fused_operator_speed_v28.md)、[compact record](outcomes/records/fused_operator_speed_v28_compact.json)、[decision record](outcomes/records/fused_operator_speed_v28_decision.json) 与 [selective merge manifest](outcomes/selective_merge_manifest_v28.md)。本轮测试是本地 targeted tests；full repository pytest、Ruff、CI 未运行/未声称。
