# RESPONSE V1：PARA-Task004 审阅回应

## 结论

接受 `review_report_v1.md` 的 `PASS_WITH_QUALIFICATIONS` 结论。Task004 保持：

```text
classification = all_slab_oracle_positive_signal
G16 two-step = positive signal, not strong signal
G16 one-step = numeric and architecture failure
learned training in Task004 = not run
ordinary default changed = false
```

Task005 只把 Task004 的 34.26% iteration/action reduction 当作 exact-local-inverse
理论上限，不把 exact LU 的时间或内存解释为 neural 性能。

## 已处理的非阻塞建议

| 审阅建议 | 处理 |
|---|---|
| `global_stored_factor_nnz` 容易被误解 | 保留兼容字段并新增 `global_stored_ilu_factor_nnz` 明确别名 |
| 外部 sampler 顶层仍写 `Task031` | 新增 `current_task` 与 `sampler_schema_origin`，Task5 运行显式写 `PARA-Task005` |
| Task5 保留 two-step smoother | Case094 冻结 `smoother_iterations=2` |
| 先做 16 independent upper bound | Case094 合同禁止在 independent Gate 前进入 shared/expert |

这些修改只增强诊断和 provenance，不改变 ordinary solver default、物理算子或
Task004 已接受的数值结论。
