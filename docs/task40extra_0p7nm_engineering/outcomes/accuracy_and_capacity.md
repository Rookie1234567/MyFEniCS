# Task40extra 精度与容量结论：N6 受限结果

## R5 当前结果：离散解与同离散参考通过，规模结论仍有限

G0/G1 的 full A6 与恢复 identity 都分别通过 1e-6 / 1e-10 门槛。G0 的 direct reference full residual 为 5.055376131651821e-11（限值 1e-10），G0 iterative 与参考场、模态和功率的全部 applicable comparisons 通过。G0 到 G1 的固定坐标场差及 integrated power 差通过工程阈值；这两种比较分别回答“迭代解是否复现同离散方程”和“网格变细后这些固定样本是否稳定”，均不证明连续收敛。

| Gate / model | 实测 | 限值 | 判定 |
|---|---:|---:|---|
| G0 full A6 / strict identity | 9.798664008005796e-7 / 1.520588963522625e-11 | 1e-6 / 1e-10 | pass |
| G1 full A6 / strict identity | 9.901397191660007e-7 / 3.2542694546811876e-11 | 1e-6 / 1e-10 | pass |
| G0 direct full residual | 5.055376131651821e-11 | 1e-10 | pass |
| direct vs G0 FE L2 / scaled-curl | 1.0643994068890889e-7 / 1.0590110456109757e-7 | 1e-4 | pass |
| same-coordinate E/H and interface traces | max relative 4.95900726941708e-7 | 1e-4 | pass |
| 80-mode outgoing amplitude vector | 1.337435981717596e-7 relative | 1e-4 | pass |
| per-mode power / total R,T,A,A_volume | max abs 7.507099208936552e-8 / 7.591423312192092e-8 | 1e-6 / 1e-5 | pass |
| G0–G1 sampled total field / R,T,A_volume | max field plane change 0.004031; max power change 0.000472098 | 0.01 / 0.001 | engineering pass |

G0/G1 资源为 simultaneous process-tree RSS 3,776,098,304 / 6,855,741,440 B；direct 为 11,505,573,888 B。三场 task tree swap 均为 0，PSS profile disabled。direct INFOG16/17 的 7,932 decimal MB 是预估；INFOG18/19 与 INFOG22 是 MUMPS 分配/使用量，INFOG29 是因子项数。以上均不同于同时树 RSS。80-mode 截断未资格化，continuum convergence 未建立，约 2 TB target capacity UNKNOWN。

恢复 identity 根因、direct 原数组审计及 user-service 启动偏差见 [identity recovery report](identity_recovery_v1.md) 和 [R5 execution-context record](records/r5_execution_context.json)。下轮唯一候选为任务书 §8.1 的有界局部问题 + 多层全局波动纠错，等待下一 review 冻结，不在本批执行。旧 42 宏块 complete-PC 负结果不改写成通过。

## attempt4 历史 Gate 快照（R4 review_v1 修复运行前）

以下原始 attempt4 指标仍有效，解释旧运行为什么停止；不要将其当作 review_v1 G0/G1 当前状态。

## attempt4 原始精度 Gate

恢复 identity 检查把凝聚后未知量还原为完整场，再核对原方程与凝聚计算是否一致。

| Gate | 门槛 | G0 attempt4 | 判定 |
|---|---:|---:|---|
| 原 A6 full explicit true residual | ≤1e-6 | 第8步0.16667295750232392；release packet 0.16667295750232333 | 未通过 |
| native recovery identity | ≤1e-10 | difference norm 1.0129916171163611e-9 / operation scale 3.29448470971699 = 3.0748104980683956e-10 | 未通过，约3.07倍限值 |
| internal residual | ≤1e-10 | 6.4490341352469694e-18 | 通过 |
| port closure | ≤1e-8 | 1.4794093427202804e-15 | 通过 |
| Schur-port identity | ≤1e-10 | 1.3094474052481446e-29 | 通过 |
| energy closure / official output | ≤1e-5 / A6通过后生成 | official packet未生成 | NOT_RUN |
| G0–G1 field/power agreement | E/H/scaled curl ≤1%；R/T/A/volume ≤1e-3 | G1未运行 | NOT_RUN |
| G0 direct same-discrete reference | field ≤1e-4；R/T/A ≤1e-5 | direct未运行 | NOT_RUN |

原 A6 是物理离散系统的显式真残差；reported Schur relative 0.16667295750382732 只能说明压缩方程的进度。第8步 native identity 为 e_FE - B*H_p^-1*e_p。主控离线数组核验与记录一致。该值超门槛，不能自动称为舍入噪声；也不凭一次停步指定更深根因。

源码 callback 每8步执行snapshot；物理残差未过且 identity 超限时，源码推导状态为 RECOVERY_IDENTITY_GATE_FAIL / DIVERGED_BREAKDOWN。raw KSP status/reason 未持久化。worker summary 的 V20_RELEASE_GATE_FAIL 与 launcher wrapper 的 exit 4 / WORKER_FAILED 均保留，但后者不代表资源失败。

## attempt4 历史规模与成本

| 项目 | 实际值 | 口径 |
|---|---:|---|
| G0 mesh | 336 cells，6×4×14 | measured |
| p6/q4 rows | 229,680 / 69,856 | measured setup |
| modes | 80 | channel cutoff 未资格化 |
| outer solver | FGMRES restart32 / max_it2048；8 iterations | Gate stop；未到max_it |
| p6/p4 cold JIT | 58.575 / 18.047 s | 单个compiler events |
| x1 setup-check / p6 build audit | 22.907 / 15.216 s | 不同计时范围 |
| retained outer elapsed through terminal snapshot | 54.222 s | KSP-only时间未持久化 |
| process-tree RSS peak | 2,954,866,688 B | watchdog同时进程树采样峰 |
| swap / PSS | 0 B / disabled | 无资源Gate stop |
| workflow time | monotonic 356.929 s；conservative realtime 392.257 s | 差异35.330 s |
| shared ledger | debit 392.262 s；cumulative 530.887 s | 账本口径，不是KSP-only时间 |

外层计数为8 matvec、8 PC apply。setup-inclusive bridge=13、p4=26；terminal packet另报native=6、Schur=11、Hp solves=44。它们有不同计数范围，不能折算成外层PC次数。104个 qualified JIT hardlinks共1,400,533,851 B，是文件payload，不是RSS。attempt3单次耗时和必要人工修复工时unknown，不以时间差回填。

## attempt4 当时的容量和离散结论

attempt4 给出这个 G0 输入的一次真实setup、迭代、Gate、时间及 watchdog RSS 观测。它没有通过恢复/物理解算 Gate，也没有G1、匹配参考、official observables或完整容量闭环。没有证据选择有效的Phase II preconditioner；2 TB可行性保持unknown，不能从一个小规模RSS峰外推。

N2仍是独立的60-cell p2诊断，不代替G0。细节与artifact SHA见 [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)、[run index](records/run_index.json) 与 [phase-I results](records/phase_I_results.json)。
