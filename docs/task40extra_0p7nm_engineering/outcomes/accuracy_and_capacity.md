# Task40extra 精度与容量结论：N6 受限结果

## 精度 Gate

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

## 实测规模与成本

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

## 容量和离散结论

attempt4 给出这个 G0 输入的一次真实setup、迭代、Gate、时间及 watchdog RSS 观测。它没有通过恢复/物理解算 Gate，也没有G1、匹配参考、official observables或完整容量闭环。没有证据选择有效的Phase II preconditioner；2 TB可行性保持unknown，不能从一个小规模RSS峰外推。

N2仍是独立的60-cell p2诊断，不代替G0。细节与artifact SHA见 [attempt4 compact record](records/g0_attempt4_identity_gate_stop.json)、[run index](records/run_index.json) 与 [phase-I results](records/phase_I_results.json)。
