# Codex 任务书

## 目标

建立第一轮 `review_code` 审查分支，供 ChatGPT 审阅当前仓库代码和文档结构。

## 背景

后续协作采用分支化流程：Codex 从 `master` 开工作分支，完成修改、验证、提交并推送；ChatGPT 读取同一远程分支，提交 `REVIEW_REPORT_*.md`；用户本地拉取并确认后，Codex 按审查报告继续修复。

本轮不改动核心计算代码，重点是验证协作留痕结构是否清晰可用。

## 必需修改

- 在 `notes/docs/` 下放置本轮 Codex 任务书。
- 在 `notes/docs/` 下放置本轮 ChatGPT 审查报告占位文件。
- 在 `notes/outcomes/20260702_review_code/` 下放置本轮 Codex 输出记录。
- 所有 Markdown 文档使用中文。
- 不提交大体积计算结果文件。

## 必需验证

- 确认分支名为 `codex/review_code`。
- 确认工作树只包含本轮留痕文件改动。
- 确认新增文件位于新的 `notes/docs/` 和 `notes/outcomes/` 结构中。

## 验收标准

- `notes/docs/CODEX_TASK_20260702_review_code.md` 存在。
- `notes/docs/REVIEW_REPORT_20260702_review_code.md` 存在。
- `notes/outcomes/20260702_review_code/summary.md` 存在。
- `notes/outcomes/20260702_review_code/parameters.json` 存在。
- `notes/outcomes/20260702_review_code/metrics.csv` 存在。
- `notes/outcomes/20260702_review_code/run_log.txt` 存在。
- `notes/outcomes/20260702_review_code/changed_files.md` 存在。

## 输出要求

- Codex 完成后提交并推送到远程分支 `codex/review_code`。
- ChatGPT 审查后应直接更新同一分支上的 `REVIEW_REPORT_20260702_review_code.md`。
- Codex 后续读取审查报告时，以 `Required Fixes` 或中文等价章节为优先处理对象。

