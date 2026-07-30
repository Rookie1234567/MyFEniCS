# Task036 V2 Hybrid validity map

## 当前状态

V2 的 226 配置点表已经冻结，但本轮新 PDE 尚未启动。因此这里暂时只记录已有 Task036
证据，不能把历史 p4/p6 点冒充新的 p5 全域扫描。

| 区域/点 | 当前证据 | 当前分类 |
|---|---|---|
| S, F1 M120 standard/static | reciprocal、projection、exact dual 与数值 Gate 通过 | representative pass；尚非全域资格化 |
| P, F2/F5 M120 static | Full3D-P 通过；Hybrid interface/modal rank 不足 | `FAIL_CLOSED`, M funnel pending |
| S, F1 M40 | bounded repair 后完整 row norm 仍为 `1.049407943e-6` | controlled negative |
| p6/h10, 10° grazing, phi=45° | Full3D 通过；Hybrid 一次 repair 后 row norm `1.033365679e-6` | near-degenerate controlled negative |

V2 正式 map 字段将在 actual p5/p6 runs 后追加：

```text
minimum_passing_M
selected_modes / available_finite_trace_rank
M_fraction_of_full_rank
Hybrid/Full3D wall ratio
Hybrid/Full3D peak-memory ratio
same-p observable error
failure root-cause class
```

当前不得宣称任何 P 参数区已 production-qualified，也不得把 Full3D fallback 记为
Hybrid success。
