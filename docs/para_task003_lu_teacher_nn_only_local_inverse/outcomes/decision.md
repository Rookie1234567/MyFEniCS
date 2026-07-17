# 决策

最终分类：`exact_lu_oracle_global_signal_insufficient`。

slab-9 exact LU 相对 860-step baseline 变为 862 steps，未通过 2% Gate。条件式 slab 0/9/10 exact-LU oracle 为 840 steps，只下降 2.33%，未通过 5% Gate。因此 P3-P7、16-model rollout、h3 和 h2 全部 `not_run_by_gate`。保留 teacher/capture/oracle 基础设施，不训练无全局上限依据的模型，不改变 ordinary default。
