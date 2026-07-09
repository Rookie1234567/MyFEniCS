# Merge Recommendation

## Decision

`merge_code: yes, research runner only`

`merge_docs: yes`

`production_default_change: no`

## Reason

Task019 增加了有用的 p=2 诊断和可恢复工作流，但没有得到 production solver。不要把 SciPy selected FE RHS、offline basis construction 或 p=2 weak variants 接入 ordinary Stage4 R/T/A。

## Allowed Scope

| item | decision |
|---|---|
| `src/studies/run_stage4_p2_h5_true_fe_sampled_schur_qualification.py` | 可作为 opt-in research runner 保留 |
| task019 outcome CSV/MD | 可保留 |
| notes update | 可保留 |

## Forbidden

| item | reason |
|---|---|
| 默认 Stage4 solver | p=2 gate failed |
| p=2 h=2 preflight | p=2 h=5 未通过 |
| weak `1.08x` low-dimensional enrichment | 不能包装成成功求解器 |
