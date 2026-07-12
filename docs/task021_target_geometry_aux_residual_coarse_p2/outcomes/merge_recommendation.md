# Merge Recommendation

## 建议

| 项目 | 建议 | 原因 |
|---|---|---|
| outcomes 文档与 CSV | 合并 | 记录了目标几何 p=2 h=5 的关键突破和负结果 |
| `src/postprocessing/postprocess.py` | 合并 | PyVista 缺失时给出清晰错误，低风险 |
| `src/studies/run_task021_target_aux_coarse.py` | 可选合并 | research runner 有复现实验价值，但不应默认启用 |
| production Stage4 默认 solver | 不合并变更 | 本轮没有改默认生产路径 |
| exact FE-block Schur | 不作为 production 默认 | 它是研究上界，含直接 FE factorization |

## 代码层级判断

本轮最重要的工程结论是：p=2 h=5 的真实残差可以被 Schur-aware FE response 路线压到 production-like，但当前实现仍在 serial SciPy research runner 中。它证明“路线可行”，还没有证明“MPI/PETSc 生产实现已完成”。

因此推荐审查策略为：

1. 合并文档、CSV、参数与轻量 history，保留完整任务证据。
2. 合并 PyVista 显式检查，因为它修复的是清晰错误信息。
3. 对 task021 research runner 做 opt-in 合并；若审查认为 research code 过重，可只保留在分支。
4. 不更改 `src/solvers` 中 Stage4 默认 KSP/PC 行为。

## 合并前检查

| 检查 | 状态 |
|---|---|
| 目标几何硬检查 | 通过 |
| complex-mode DOLFINx/PETSc 检查 | 通过 |
| p=2 h=5 true residual gate | production-like |
| p=2 h=2 full validation | 未执行，按任务书留到下一任务 |
| official R/T/A from iterative solution | 未执行，建议 task022 |
