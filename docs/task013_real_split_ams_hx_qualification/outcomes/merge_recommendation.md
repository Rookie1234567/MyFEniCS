# 合并建议

```text
merge_code: no
merge_docs_only: yes
reason: 本轮证明 FE-only real-split AMS/HX same-H1 auxiliary 有 B 档研究价值，但没有接入 reduced/full Stage 4，也没有 official R/T/A。
minimal_files_to_merge: docs/task013_real_split_ams_hx_qualification/outcomes/*, docs/README.md, notes/reference/current_version_boundaries.md
files_to_drop: src/studies/run_real_split_ams_qualification.py can be dropped from master unless the next task explicitly wants to keep research runners
risks_if_merged: 用户或后续代码可能误以为 real-split AMS 已是 Stage 4 production solver；实验 Python PC 也可能增加维护负担
recommended_next_branch: codex/20260708-real-split-stage4-reduced-block-pc
```

## 判断依据

| 条件 | 本轮结果 | 合并含义 |
|---|---|---|
| real split 数学等价 | 通过 | 可作为研究记录 |
| FE-only p2 h5 收敛 | same-H1 310 iter 达到 `9.964e-7` | 值得继续 |
| 内存改善 | same-H1 RSS `1.323 GB`，远低于 BLR `17.85 GB` | 强正信号 |
| reduced Stage 4 | 未运行 | 不能合并为 solver |
| full Stage 4 R/T/A | 未运行 | 不能进入 production |

## 推荐策略

1. 当前分支保留完整代码和 outcomes，供审查。
2. 若审查同意继续，下一轮从本分支开 reduced Stage 4 integration。
3. 若最终合并到 `master`，建议只合并文档；脚本可以在后续成功接入 Stage 4 后再清理成正式工具。
