# Merge Recommendation

## 建议

```text
merge_code: no
merge_docs_only: optional
allow_p2_h5: no
continue_line: yes, but only for true-FE sampled Schur integration
```

## 理由

| 项目 | 判断 |
|---|---|
| Petrov/adjoint W | 没有通过 minimum useful gate |
| true-FE sampled lift one-shot | 通过 minimum useful gate，`5.819x` |
| strong gate | 未通过 |
| KSP PC | 未通过，right additive PC 变差 |
| production readiness | 未达到 |

本轮最有价值的是研究结论，不是可合并 solver。`run_stage4_petrov_adjoint_coarse_correction.py` 可以留在研究分支供 ChatGPT 审查，但暂不建议进入 `master` 的 production 路径。

## 可以合并的内容

若后续需要保留研究证据，可以只合并：

```text
docs/task017_petrov_adjoint_coarse_correction/outcomes/
notes/theory/maxwell_iterative_preconditioners_task012.md
docs/README.md
```

代码 runner 是否合并，建议等下一轮审查后再决定。
