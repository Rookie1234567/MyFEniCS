# Task005 决策

```text
classification = learned_pc_memory_budget_failure
secondary_finding = local_quality_and_model_runtime_positive
P0 = PASS
P1 = PASS
P2 = FAIL_STORAGE_GATE
P3-P9 = not_run_by_gate
ordinary_default_changed = false
production_claim_allowed = false
```

R4 证明 fixed-operator low-rank inverse 的局部能力和模型纯 runtime 都是正信号：
Lane A rank 64 与多个 Lane B candidate 4/4 admissible，owner grouped inference 明显
低于 7.2 ms。但在任务书要求把 required audit/operator storage 纳入预算后，最小
可接受配置也需要 68.282 MiB/owner，超过 33.670 MiB memory-neutral 和
50.505 MiB speed-first guard。

因此不得进入 full-16 training、shadow、active fallback 或 global A/B。后续若继续，
研究问题应先改为“如何无私有 CSR 副本完成严格 proxy + periodic exact audit”，而
不是继续增加 NN 容量或数据。只有该 blocker 在独立任务中通过 injected-failure、
zero-false-accept、drift 和 end-to-end storage tests，才可从 P3 恢复。
