# 决策

```text
classification = all_slab_oracle_positive_signal
lane_a_g16_iteration_reduction = 34.2625%
lane_a_strong_signal = false
lane_a_positive_signal = true
lane_b_numeric_pass = false
lane_b_architecture_signal = false
automatic_training_in_task004 = prohibited
ordinary_default_changed = false
```

G16 no-hidden-ILU two-step 通过 full residual、R/T/A、memory、swap和lifecycle Gate，并达到`>=20%` outer reduction，因此可在Task004最终审阅后建议一个独立Task005研究全slab learned inverse。候选组织方式（16 independent / 3 experts / shared trunk+adapters）仍需审阅和用户决定。

One-step不收敛且operator actions增加，拒绝作为后续默认目标。Task004不训练、不运行h3/h2、不改变ordinary default，也不把exact-LU wall time/memory称为neural性能。
