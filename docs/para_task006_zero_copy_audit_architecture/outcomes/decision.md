# Task006 决策

```text
classification = audit_architecture_false_reject_failure
secondary = borrowed_exact_action_feasible_zero_private_CSR
P0 = PASS
P1 = PASS
P2 = FAIL_USABILITY_GATE
P3-P8 = not_run_by_gate
Task005_P3_resume = prohibited
ordinary_default_changed = false
```

## 决定性证据

P1 证明 borrowed exact action 本身可行：16/16、64/64 probes 的最大 action
relative error `6.030e-16`，rho difference `3.558e-16`，persistent private CSR
为 0。

P2 只访问 Q0/Task005 V，比较 q=64/128/256/512/1024/2048 和 one/two seeds。
12/12 family 均可通过保守阈值得到 Q0 observed false accept 0，但最佳 overall
non-harmful acceptance 仅 43.37%；符合最终 two-seed 要求的最佳值为 42.96%，
最差 slab false reject 为 81.89%。这远低于 acceptance `>=99%`、overall false
reject `<=5%`、per-slab false reject `<=10%`。

此外，未修改 `A_D0_R64` 在 Q0 exact ground truth 上已有 58/1024 samples harmful
（slab 0/5/9/15 分别 2/31/23/2）。若“unmodified acceptance >=99%”按全部输出
解释，则 zero false accept 下的理论 acceptance 上限只有 94.34%；若只按
non-harmful 子集解释，实际 proxy 仍大幅失败。

## 边界

这是 strict low-storage proxy 的 false-reject/usability failure，不是：

- borrowed action infeasible；
- persistent storage failure；
- NN model-only runtime failure；
- full16 learned-PC global failure；
- universal impossibility proof。

没有阈值被锁定，没有读取 Q1-Q5，没有运行 P3 locked replay、P4 injection、
P5 schedule、P6 lifecycle 或 P7 live shadow。继续需要新的独立任务重新定义
候选输出/安全目标（例如训练时直接约束 per-sample non-degradation，或改变
accept/fallback contract），不得从 Task005 P3 直接恢复。
