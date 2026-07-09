# Merge Recommendation

## Decision

```text
merge_code: no
merge_docs_only: optional
```

## Reasons

| item | decision | reason |
|---|---|---|
| task15 diagnostic code | do not merge to master | 仍是研究脚本，依赖 explicit matrix export 和 Python PC |
| production direct/BLR path | unchanged | 本轮没有触碰正式求解路径 |
| p=2 h=5 gate | closed | default100 p=1 h=5 没有 10x 改善 |
| full p=2 h=2 gate | closed | 低阶 reduced case 尚未解决 |
| docs/outcomes | may merge | 负结果和瓶颈定位有复用价值 |

## Minimal Code To Keep On Research Branch

```text
src/studies/run_stage4_boundary_pc_diagnostic.py
src/studies/run_stage4_real_split_block_pc.py
src/constraints/floquet_3d.py
```

下一轮若 zero-order lifted coarse correction 成功，再考虑抽取最小、干净、可维护的 PC 构造接口进入 production solver。
