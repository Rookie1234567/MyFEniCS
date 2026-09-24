# Response V30：Review V27 / V29 A4、p6 tensor 与 H6 收口

## 结论

V29 唯一一次获准的 original p6/h7.5 正式运行完成：126步，独立完整 A6 真残差 `9.283162362107749e-7`，释放后同值，低于 `1e-6`。动态 checker 为 `DYNAMIC_PASS`，物理/端口检查通过。V28 的同离散 E/H、全 FE、80 模态与官方功率离线核验也通过。结果限定为这一离散模型的一致性通过，不宣称 continuum convergence 或其他模型/频率鲁棒。

V29 相比 V28 同口径观察到 workflow monotonic `2422.426 s` 对 `2936.076 s`（短 `513.650 s`，17.49%）；pure KSP `1837.175 s` 对 `2113.443 s`（短 `276.268 s`，13.07%）；setup `533.755 s` 对 `773.946 s`（短 `240.191 s`，31.03%）。这是一对正式运行的观察，不能独立证明任何单项是因果来源。完整分段边界、逐16步 residual/elapsed 与 p4 i112 基线见[V29 outcome](outcomes/a4_tensor_h6_v29.md)及[compact record](outcomes/records/a4_tensor_h6_v29_compact.json)。

## 按 Review V27 回答

1. **粗层精化后是否能继续外层？** opt-in 的 `continue_outer_best_finite` 最多进行两次额外精化；仍未达粗层软目标但状态有限完整时，返回最优完整状态并继续外层。非有限数、真实因子错误、约束/端口损坏、KSP breakdown 和实测资源 Gate 仍拒绝。正式场 `coarse_target_unmet_continued_count=0/262`，所以分支没有在大场触发，仅由小 fixture 覆盖；不能写成实场已触发。
2. **A4 检查是否减少？** 没有。正式动态记录为262逻辑单位、267个完整 A4 action、267次真实 MatSolve/物理 F4 调用；setup/iteration/check 分别为2/253/12。5次额外修正也均计入，计数闭合。实现为完整 `fused_sum_factorized_partial_assembly_full_A4`，以相同 p4 form 与 DtN 的独立 native FFCx 身份作资格 oracle。未隔步检查、未抽样、未建第二个 p4 全局矩阵或因子。
3. **三个候选去留？** P2 完整 A4 候选以最大 `3.18e-12` action/residual差和约 `2.818x` 配对中位数加速采用；P3 p6 raw-tensor 12类全部通过，构建时间 `230.547 s` 降为 `19.558 s`，采用到本 profile；P4 H6 实虚堆叠候选输出完全等价但 i120 apply 慢1.69%，故撤出；setup只快0.92%不能抵消。H6首次 attempt 的 adapter 软件错误及成本保留在组件表，没有改写为数值失败。
4. **时间及内存是否同口径？** 使用 monotonic 与 conservative realtime 分列；V29完整workflow两者为`2422.426/2643.635 s`，全流程时钟差`221.208 s`，成因 unknown，未分摊到阶段。worker采样进程树 RSS/PSS 峰值`7,323,303,936/7,291,101,184 B`，watchdog采样树 RSS`7,326,449,664 B`，swap0、后代清空。平均在线操作时间为A6 `1.966 s`、H6 `4.008 s`、P `0.296 s`、PH `0.258 s`、完整A4 `0.596 s`、p4 F4 `0.912 s`；这些桶有嵌套，不可相加。p4接口局部凝聚`26.588 s`与p6局部张量/Schur构建`34.122 s`已按原始字段分开；分阶段RSS/PSS及对象内存见[V29 setup/resource 台账](outcomes/a4_tensor_h6_v29.md)。按Review V27边界的CPU秒数均为`unknown`，未把wall-clock当CPU；空间/约束/端口/JIT、bridge/startup检查及正交化的未分项wall time也为`unknown`，完整清单见 compact record。相对 V28 的单次观测不是已资格化的内存收益。
5. **R1 部分运行如何处理？** 按用户选择“保留部分证据并停止重跑”，不再重放；R1 与正式 V29 分开，缺失的 BAL_H/i112 数据维持缺失，不用 V29 结果补造。其原始 identity/hash/耗时未在本轮交付记录中重新绑定。
6. **MUMPS及默认路径？** MUMPS、ordering/pivot、BLR/OOC、MPI和线程策略没有改变；普通默认保持原状。V29 显式 profile 结果等待 review，不合并 master。

V28 同离散离线检查通过，worker 内原有 `MATCHED_REFERENCE_NOT_AVAILABLE`/`NOT_ATTEMPTED` 不变。R/T/A、R00偏振拆分、时间/残差点、证据 hash 见 outcome 和对应 machine-readable records。完整场和大型缓存仍只留在 ignored artifacts。

## 验证与未运行项

正式 PDE：1场；额外 PDE：0。完成 V29/V28 同坐标场、全 FE、模态/功率和输出检查的独立只读离线 audit；它没有启动 PDE、算子、因子或 KSP。文档与记录修改后运行的针对性测试写入 [test summary](outcomes/test_summary.md)。Full repository pytest、Ruff、GitHub CI、MPI2/4和其他几何/波长均不在本轮范围，不声称通过。

执行源 SHA `780f58918b0e5a9868cd2ea3de26d451bc6b5d86`；本轮证据、outcomes、[selective merge manifest](outcomes/selective_merge_manifest_v29.md) 与本响应按 task39extra 同分支提交/推送，等待主控 review。当前不授权 merge master 或进一步 PDE。
