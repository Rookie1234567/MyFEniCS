# Response V19：R末态后的原方程抛光完成

P在每个周期重新搜索256个方向，只留下当前解；L额外保留本路线最近至多3个修正方向，用于减少下个周期重复搜索。两者都继续解完整原方程，保留40端口和单元内部的原恢复。这里改变的是重启之间保存的信息，没有训练网络、改变材料或缩减物理未知量。

Review V16授权的C0、P/L配对与冻结后独立FE审核已收口。严格同离散资格 **0/8**；结论 **FIELD_AND_EQUATION_PROGRESS_NOT_QUALIFIED**。没有新增hidden训练、基、GK、global p4因子或准确参考LU，旧负结果保持。

| 方法／库 | 实际调用 | 原rho起点→最终 | 本路线S+SH | charged wall(s) | 停止原因 |
|---|---|---|---|---|---|
| P_GPOLY | 64 | 0.000146307718165 → 2.23358499521e-05 | 16768 | 2279.93663295 | FIXED_64_CYCLE_LIMIT |
| P_GNN | 64 | 0.000199556374692 → 3.24881797774e-05 | 16768 | 2261.5433094 | FIXED_64_CYCLE_LIMIT |
| L_GPOLY | 64 | 0.000146307718165 → 9.67833470962e-06 | 16962 | 2298.25489228 | FIXED_64_CYCLE_LIMIT |
| L_GNN | 64 | 0.000199556374692 → 1.44393838546e-05 | 16962 | 2327.33009045 | FIXED_64_CYCLE_LIMIT |


| 冻结状态／同一0.7nm micro | 原Schur≤1e-6 | 原native≤1e-6 | 独立total-native≤1e-6 | 散射E≤1e-4 | 散射curl≤1e-4 | 完整资格 |
|---|---|---|---|---|---|---|
| V18-R-GPOLY | 0.000146307718165 | 5.67386863796e-05 | 1.96882893595e-05 | 8.07999012193e-05 | 7.98192590218e-05 | FAIL |
| P_GPOLY-FINAL | 2.23358499521e-05 | 8.66192707661e-06 | 3.0056833815e-06 | 7.99097168553e-05 | 7.98938859115e-05 | FAIL |
| L_GPOLY-FINAL | 9.67833470962e-06 | 3.75329480007e-06 | 1.30239098725e-06 | 7.95003214967e-05 | 7.9510166913e-05 | FAIL |
| P_GPOLY-CYCLE8 | 6.80805905911e-05 | 2.64019104846e-05 | 9.1614467379e-06 | 8.01429875488e-05 | 7.98921410883e-05 | FAIL |
| V18-R-GNN | 0.000199556374692 | 7.7388716746e-05 | 2.68538372247e-05 | 0.000100199130834 | 9.8749639854e-05 | FAIL |
| P_GNN-FINAL | 3.24881797774e-05 | 1.25990389751e-05 | 4.37185878872e-06 | 9.76389690217e-05 | 9.76039356484e-05 | FAIL |
| L_GNN-FINAL | 1.44393838546e-05 | 5.59964766271e-06 | 1.94307429584e-06 | 9.70793047547e-05 | 9.7083009907e-05 | FAIL |
| P_GNN-CYCLE8 | 9.11307000429e-05 | 3.53408300959e-05 | 1.22632463571e-05 | 9.92146330721e-05 | 9.88453864041e-05 | FAIL |


候选选择在读取REF7前按原rho冻结；两库起点分别为V18-R逻辑12831/11903，不是旧G256末态。P/L独立开始，不互相warm start。L的Arnoldi内部计数为unknown，实际底层S/SH逐周期实测；callback是外层状态，不冒充256内步。FIRST_PASS不可覆盖，合格与否由原审核决定。

新增正式one-run监督wall **9199.970576s**；本批辅助监督wall **102.206160s**（截至费用快照，含失败小测试；后续交付开销计入总elapsed）。V6起formal累计下界 **66613.525719s**，旧辅助unknown保持。同时整树采样峰 **796585984B（0.741879GiB）**，own swap/VRAM **0B**。父队列和子one-run计时嵌套，不重复相加；全部成本标shared-workstation。

全批S+SH **67543**、audit **269**；统一单路线wall **2382s**，各≤19500原作用、≤64调用。MPI1、现场选空闲核避开忙SMT、数学/Torch1、Loader0、不用GPU；12/16GiB与ownswap0通过0.5秒整树监督，现场无cgroup委派，不能称kernel连续硬限额。资源重入 **0**，冷却 **0.0s**；共享影响与相同严格精度加速INCONCLUSIVE，不承诺零干扰。上游基/image/LSQR的必要费用保留lineage，精确缺项unknown；研发总和不是某条成功解的部署时间。

初次短回归25 passed/3 failed，修复后28 passed；后置回归先41 passed/2 fixture failed，提前隔离测试目录后43 passed。solver周期重放0；VERIFY首次在sandbox因MPI本地socket EPERM、尚未初始化而失败，同源授权host-socket重放1次，ABI不变。失败费用和64作用/2audit保守上界保留，未重算Arnoldi。事务测试覆盖跨周期方向、半写/kill/hash/回滚和返回后补审；不声称CI/full pytest/Ruff。

L相对同起点P显著降残差，但散射场改善很小。GPOLY最大通道功率差从R原点1.5880640292786907e-6变为L末态1.7855346416961737e-6，反而恶化；8状态均仍高于1e-6功率门限。GNN-L能量闭合9.65601379288028e-6单项通过，不替代方程和通道功率。

最后收尾资源再核验未能确认空闲物理核，停止该核验，不启动任何新数值负载；费用保留。主机只读检查确认V19数值actor为0、自有锁可用、已结束监督器的后代全部清场，见[清场记录](outcomes/records/delivery_cleanup_v19.json)。这不修改已经测得的数值结果或放宽准入。

唯一worktree `/home/fenics/Projects/NN-Lab`，branch `task42_neural_coarse_inverse`，upstream `origin/task42_neural_coarse_inverse`；base `ccd357885f7f9be84efe3be07868cc94f13d93fc`。正式数值actual source **`b58919a4a0dcd677b915eb7d9bbd314520aef0e0`**，后置reader和最终文档HEAD分开，精确交付HEAD见最终回执。原0.7nm/384hex/p3/q15、双Floquet、完整40通道及canonical用户材料保持。

完整E/H/curl、复通道、R/T/A/A_volume与能量的实际值见[完整结果](outcomes/post_lsqr_residual_polish_v19.md)、[run/source](outcomes/records/run_index_v19.json)、[原数值Gate](outcomes/records/qualification_and_dispatch_v19.json)、[逐周期](outcomes/records/polish_cycles_v19.csv)、[费用](outcomes/records/resource_costs_v19.json)。未合格功率仍为UNQUALIFIED_DIAGNOSTIC。REF7非零native值保留，无参考反馈、幅相修正或验证后回训。

唯一下一建议：仅申请一个固定p3全trace ILU(0)预条件的短资格对照：先评估原p3 trace体块装配与因子容量、核对同一barS及完整40端口；Gate通过后从L-GPOLY冻结末态做一次预条件GMRES256周期。此方案需要额外装配和因子内存，须由下一份review明确预算与准入，不能沿用本批低RSS作容量保证；不扫描参数、不使用global p4 LU。本批未实施。

不执行新p4参考、最大模型、GPU、p6或merge。全部自身后代清场，仅推送本执行分支，停止等待review。GitHub精确页未取得视觉证据，**NOT_VERIFIED**；本地Markdown结构检查单列。
