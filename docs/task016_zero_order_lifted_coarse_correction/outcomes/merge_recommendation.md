# Merge Recommendation

## Decision

```text
merge_code: no
merge_docs_only: optional
```

## Reason

Task016 的研究结论有价值，但没有产生可用 solver：

| criterion | result |
|---|---|
| default100 p=1 h=5 residual <= `2e-3` | no |
| improvement >= `10x` | no |
| KSP stability | un-damped coarse PC 可能 PETSc FPE |
| production readiness | no |
| documentation value | yes |

## Keep On Research Branch

```text
src/studies/run_stage4_lifted_coarse_correction.py
docs/task016_zero_order_lifted_coarse_correction/outcomes/
```

这些文件适合作为研究分支留痕和后续 task17 输入，不建议合并到 `master` 的 production 路径。
