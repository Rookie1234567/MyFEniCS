# Review V17 联合决策

## 当前结论

`NOT_QUALIFIED`。两个独立 oracle 都产生了可审计证据，但没有一个给出 Review V17 要求的 strong signal：Oracle A 的 exact p3 coarse span 是有效的数值失败，Oracle B 的 unrestarted Krylov 是有效的 WEAK signal。因此不得把两条局部结果拼成 production PC 通过，也不得启动新的 physical recovery。

| lane | 它实际回答的问题 | 结果 | 证据状态 |
|---|---|---|---|
| Oracle A | p3 coarse span 能否在 p6/h10 checkpoint 上把 fine physical residual 一并压低 | `EXACT_P3_COARSE_SPAN_FAIL`；`rho_ref=20.97573925716883 > 0.70` | evidence-valid numerical FAIL |
| Oracle B | 同一 p6/h10 checkpoint 上，不重启的 disk-backed Krylov 是否比 GMRES(20) 提供强改进 | `UNRESTARTED_KRYLOV_WEAK_SIGNAL`；ratio `0.4006010510326989 > 0.1` | evidence-valid WEAK |
| joint | 是否满足“coarse span 或 Krylov strong”才可继续 | 不满足 | V17 route closed |

Oracle A 的 `rho3=4.298361509181443e-12` 说明 correction 确实解决了 p3 投影残差，但 `rho_ref` 反而放大到约 21 倍；这正是该 coarse span 在 fine physical operator 上不可靠的证据。Oracle B 在 500 步的 unrestarted residual 为 `0.19374101288500692`，参考 GMRES(20) 为 `0.48362582271206495`，改善真实存在，但只达到 WEAK，而不是 `<=0.1` 的 strong threshold。

## 为什么停止

Oracle A 是“能否用有限 p3 空间表达并修正这一个 p6 残差”的局部实验；它不是 full PDE。Oracle B 是“长 Krylov 记忆是否有用”的算法实验；它也没有生成 official E/H、near-field 或 R/T/A。两项都没有证明在 0.7 nm、2 TiB 目标上可扩展。把 WEAK 当 STRONG，或把 A 的 coarse-space FAIL 忽略，都会越过 Review V17 的继续条件。

因此本轮不运行 fresh 20,000-step physical PDE，不做 official recovery，不选择 I20/I100，不运行 Q3–Q6，也不进入 W1–W4。V16 的 Q1.1/Q1.2 PASS、Q2 numerical FAIL、W0 capacity FAIL 及所有受控停止仍保持原样；V17 只补充了 A/B 两条独立机制证据。

## Review V17 决策矩阵的应用

Review 的固定规则是：A PASS 且 B STRONG 才允许继续 bounded GMRES-DR/thick-restart 类路线；A FAIL 且 B STRONG 只允许研究 deflated/recycled Krylov；A FAIL 且 B 为 NO/WEAK 时，coarse span 与 Krylov-only 两条路都没有 strong signal，下一阶段至多比较新的 wave-aware DD、PML/sweeping 或其他 global propagation architecture。当前正是最后一种情况。

这不是“所有物理求解都不可能”的结论。它只关闭了本轮已经测量的 exact p3 coarse-span 与 unrestarted Krylov-only 机制，并锁住未授权路线。任何新架构都必须另行给出小型 identity、内存和 lifecycle authority；本轮不实现、不宣称通过。

## 仍然锁定的边界

- `Q3–Q6`: `locked/not_run`；没有 I20/I100 扫描，也没有把未选方案写成失败实验。
- `W1–W4`: `locked/not_run`，因为 W0 的真实 interface rank/byte authority 仍是 `W0_INTERFACE_RANK_CAPACITY_FAIL`。
- `official physics`: `not_run`；没有 official recovery、E/H、near-field、同一 12+12 array 或 R/T/A。
- MPI1 的完整 process-tree RSS `<2,000,000,000 B` 仍是硬线；用户明确 MPI2 超过 2 GB 只如实记录而不因 RSS 单独关闭路线，但 MPI2 仍须通过数值、finite、repeat、input、provenance、swap 和 lifecycle。B 本次是 MPI1，因此实测 parent peak `1,451,954,176 B`、worker-stage peak `880,951,296 B`、swap `0`。

## 证据入口

- [Oracle A exact p3 coarse span](exact_p3_coarse_span_v17.md)
- [Oracle B unrestarted Krylov](unrestarted_krylov_v17.md)
- [V16 Q1 authority](records/physical_pcoarse_q1_qualification_v16.json)
- [V16 Q2 checkpoint outcome](physical_pcoarse_checkpoint_v16.md)
- [V16 W0 capacity preflight](wave_aware_dd_preflight_v16.md)

完整 raw evidence 位于 [`Oracle A v3 artifact`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_a_v3/d521d85ed63535a2c9bb03e44fe9f7a5e8d394e7/mpi1) 和 [`Oracle B v2 artifact`](../../../benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/v17_oracle_b_v2/3e3ad22944333439e9f4a5d71abc4c7384855dff/mpi1)。原始文件未被 M6 文档修改。
