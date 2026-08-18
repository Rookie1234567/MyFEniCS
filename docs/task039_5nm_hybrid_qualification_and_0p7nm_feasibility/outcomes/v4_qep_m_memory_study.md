# V4-9 QEP 与模式内存研究收口

## 总结

这组研究回答的是“模式数量增加时，内存瓶颈来自哪里、哪些离线方向值得继续”，不是
重新资格化 h4 三方法。最终分类为：

`QEP_MEMORY_DIRECTION_NOT_ESTABLISHED`

所有 Q-A/Q-B/Q-C/Q-D 结果均与同一 h4/M480 packet 绑定；没有改 solver、普通默认、M480
正式 authority，也没有运行新的 PDE。

## Q-A：owner-row packet 已经成立

Q-A 的 owner-row 意思是：每个 MPI rank 只保存自己拥有的横截面行，四类
positive/negative × right/left 数组都是 mode-major complex128 mmap，而不是每个 rank
复制完整 M480 basis。manifest 给出 rank8、global size 11605、32 个 shard 文件，四组
array payload 总计 `356,505,600 B`，约 `0.332022 GiB`。这是 persisted basis 的 measured
filesystem/shape accounting，不是 solver process-tree RSS。

| 项目 | 结论 | 口径 |
|---|---|---|
| owner-only packet | 已实现 | measured/manifest |
| `.npy` payload | 356,505,600 B | measured/manifest-derived |
| M240/320/400 payload proxy | 0.166011 / 0.221348 / 0.276685 GiB | derived，不是 RSS |
| producer peak | 9.478675842 GiB | measured process-tree |
| Hybrid direct peak | 93.377006531 GiB | measured process-tree |
| Hybrid iterative peak | 104.334560394 GiB | measured process-tree |
| full-basis iterative lifetime | 未单独持久化 | not_measured |

因此不能把 packet 的三百多 MB 线性缩放直接称为低 M solver 的内存预测；实际峰值还包括
operator、coupling、factor、Krylov 和恢复对象。

## Q-B：一支 QEP 的符号审计有正信号，但不是完整资格

Q-B 的 sampled operator probes 支持 reciprocal、z-invariant 变换的线性/对称结构，
positive/negative packet 的 beta 配对和 polynomial residual 通过 existing QEP tolerance。
但两支 trace subspace comparison 约为 `4.77e-7` 到 `7.60e-6`，超过要求的 `1e-10`；
traction numerical 与 Hybrid observables 没有因此被推断通过。故 Q-B 不是可以替代一支 QEP
的正式结论，也不能把 lossy-complex left/right 的符号映射当作已完成的 physical Gate。

## Q-C：batched/streaming component

小规模 component 固定比较 one-shot 8 与两个 4+4 batch。beta matching 最大误差约
`8.41e-14`，wall 变化为 `-8.6204%`；但 factor lifecycle 是 1 次对 2 次，且没有可靠的
process-tree RSS measurement。因此 Q-C 的 numerical equivalence 和 wall 是 measured
正信号，整体仍是 `NOT_ESTABLISHED`，不能宣称已实现 30% QEP peak reduction。

## Q-D：低 M 只能停在 feasibility audit

M240、M320、M400 两个分支都满足当前 packet 顺序下的完整 group boundary 和 nestedness，
但这只证明 metadata/subspace 候选没有切开已选 group。packet 没有可重解的 K0/K1/K2、
reduced RHS/solution、通用 trace/traction projection、full-field reconstruction basis
或参数化 port observable map；M480 解的系数也不能清零后冒充 reduced solve。

| M_eff | group boundary | payload proxy | reduced physics/resource Gate |
|---:|---|---:|---|
| 240 | positive/negative complete | 0.166011 GiB | all `NOT_ESTABLISHED` |
| 320 | positive/negative complete | 0.221348 GiB | all `NOT_ESTABLISHED` |
| 400 | positive/negative complete | 0.276685 GiB | all `NOT_ESTABLISHED` |

eta 没有选择；传播/弱衰减筛选和后续 enrich 没有被当作本轮实测结论。reduced residual、
R/T/A/A_volume、selected E/H、normal flux/power channels、interface residual 和
resource reduction 全部保持 `status=NOT_ESTABLISHED, pass=null`。

## 停止条件与下一步

V4 在这里停止：不扫描 eta，不重新做 M240/320/400 QEP/PDE，不创建新的 production
solver/checker。若未来继续，必须先补齐可重解 operator/RHS、恢复映射和 observables authority，
再以单独任务验证真实 reduced solve；当前 Q-D 只能作为 capacity/metadata feasibility
record。

证据入口：[Q-A](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_q9_offline_audit_v1.json)、
[Q-B](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_q9_qb_component_v1.json)、
[Q-C](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_q9_qc_component_v1.json)、
[Q-D](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v4_q9_qd_feasibility_v1.json)。
