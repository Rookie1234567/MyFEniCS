# Response V1：Task40extra B 线 N0–N6 受限结果

## 结论

G0 attempt4 已真实建立 0.7 nm 非可分三维 p6/q4 空间并进入外层 FGMRES。 恢复 identity 用通俗话说，是检查恢复出的全场与凝聚代数是否相互吻合。第 8 步原 A6 相对真残差为 0.16667295750232392，高于任务门槛 1e-6；native recovery identity 为 3.0748104980683956e-10，高于 1e-10 门槛。worker 原生 summary 分类保留为 V20_RELEASE_GATE_FAIL。它不是资源停止，也不是达到 2048 步迭代上限后的结论。

保存的 monitor 和终态数组没有持久化 KSP status 或 PETSc reason。根据源码 callback 与第 8 步记录指标，可推导停止路径是 RECOVERY_IDENTITY_GATE_FAIL / DIVERGED_BREAKDOWN；这是源码推导，不冒充原始状态字段。release packet 随后也记录 A6 超限。没有 official R/T/A、A_volume 或合格的完整场结果。G1、direct reference 和跨网格比较保持 NOT_RUN；N6 是受限收口，不是精度或容量资格通过。

## Gate 因果链

| 顺序 | 已保存证据 | 判定 |
|---|---|---|
| 第 8 步完整 snapshot | A6 relative=0.16667295750232392；reported Schur relative=0.16667295750382732 | 原方程残差尚未达到 1e-6 |
| native recovery identity | difference norm=1.0129916171163611e-9；operation scale=3.29448470971699；relative=3.0748104980683956e-10 | 超过 1e-10 门槛约 3.07 倍；不预先称为舍入误差 |
| 其他 identity 检查 | internal=6.4490341352469694e-18；port closure=1.4794093427202804e-15；Schur-port=1.3094474052481446e-29 | 各自低于对应门槛 |
| 源码 callback | 每 8 步检查；物理残差未通过且 native identity 超限时返回 DIVERGED_BREAKDOWN | RECOVERY_IDENTITY_GATE_FAIL 为源码推导；raw KSP reason 未保存 |
| release packet | V20_RELEASE_GATE_FAIL；A6 relative=0.16667295750232333；field packet 已保存 | 下游释放检查失败，official_result=false |

主控离线复核只读保存数组，确认 identity difference 等于 native residual 减 derived native residual，向量范数和比值一致；没有 FE 装配、分解或求解。SHA 与完整成本边界见 [attempt4 compact record](outcomes/records/g0_attempt4_identity_gate_stop.json)。

## N0–N6 状态

| 阶段 | 状态 | 结果 |
|---|---|---|
| N0 | complete | 保留 B 线执行分支和 canonical worktree |
| N1 | complete | 0.7 nm 材料、有限三维缺口几何、G0/G1 计划与 80-mode 身份冻结 |
| N2 | diagnostic_pass_only | 60-cell p2 tiny 诊断通过自身检查；不是 G0/G1 p6 |
| N3 / G0 | V20_RELEASE_GATE_FAIL | 前三次 implementation bug 保留；第四次到达 8 步后停止于 identity Gate |
| N4 / G1 | NOT_RUN | 未做 h 细化及跨网格场比较 |
| N5 / G0 direct | NOT_RUN | 没有合格 G0 iterative 对照解 |
| N6 | closed_limited | 保存当前数值 Gate、成本、资源与结论边界 |

三次先前实现错误依次是 ledger batch identity 不一致、wrapper 缺少 rectangular_air_void_audit、Task40 worktree 中 Task39 相对 JIT cache 路径不存在。三者均不是数值 Gate。attempt3 单次时长与必要人工修复工时没有独立可靠记录，记 unknown，不由 ledger 总量推算。

## Setup、迭代与资源

attempt4 建立 336 cells、p6 rows 229,680、q4 rows 69,856。几何 audit 与 native AQ projection 检查通过。p6/p4 condensation cold JIT 分别 58.575/18.047 s；x1 setup-check 22.907 s，p6 build audit 15.216 s。终态记录的 retained outer clock 为 54.222 s；KSP-only elapsed 未持久化。外层完成 8 次 matvec 和 8 次 PC apply；setup-inclusive bridge/p4 等计数单独保存在 compact record，不与外层 PC 次数混淆。

全流程 monotonic 时间为 356.929 s；保守 realtime accounting 为 392.257 s，两者相差 35.330 s。ledger 本次 debit 为 392.262 s，累计 530.887 s。以上口径分别记录，不推导 KSP 时间。watchdog 进程树 RSS 峰值为 2,954,866,688 B，swap 峰值为 0，PSS 按 profile 禁用，进程身份覆盖完整且后代已清场；没有资源 Gate stop。

## 决策

| 项目 | 决定 |
|---|---|
| G0 | 保留原始分类 V20_RELEASE_GATE_FAIL；源码推导 callback 为 RECOVERY_IDENTITY_GATE_FAIL |
| 官方输出 | R/T/A、A_volume、能量闭合与 official observables 均 NOT_RUN；只保存诊断场/误差包 |
| G1 / direct | NOT_RUN；本批停止后不追加 PDE |
| 容量 / Phase II | 2 TB 可行性 unknown；不选未经 accuracy evidence 证明有效的 PC |
| production / master | ordinary default 不变；不合并 master，等待 review |

详见 [outcomes summary](outcomes/summary.md)、[精度与容量](outcomes/accuracy_and_capacity.md)、[测试摘要](outcomes/test_summary.md) 与 [run index](outcomes/records/run_index.json)。
