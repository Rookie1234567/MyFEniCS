# 输出总结

## 任务

建立第一轮 `review_code` 审查分支，并按新的留痕结构准备任务书、审查报告占位文件和 Codex 输出记录。

## 分支

`codex/review_code`

## 改动文件

详见 `changed_files.md`。

## 运行命令

- `git switch master`
- `git switch -c codex/review_code`
- `git status --short --branch`
- `git branch --all`
- `git log -1 --oneline`

## 物理模型

本轮未改动物理模型或求解流程。

## 数值设置

本轮未运行数值算例，未改变网格、材料参数、边界条件、求解器配置或 Floquet 设置。

## 关键结果

- 新的留痕目录采用 `notes/docs/` 和 `notes/outcomes/<日期>_<任务名>/`。
- 本轮任务名为 `review_code`。
- Markdown 文档均使用中文。
- `.gitignore` 已允许 `notes/outcomes/**/*.csv` 中的小型指标文件入库。

## 能量检查

本轮未运行仿真，因此没有新的 `R`、`T`、`A` 或能量守恒误差。

## 网格 / 自由度 / 求解成本

本轮未运行仿真，因此没有新的网格规模、自由度数量或求解耗时。

## 已知问题

- `REVIEW_REPORT_20260702_review_code.md` 目前是占位文件，需要 ChatGPT 审查后填写。
- 本轮没有执行 Docker/FEniCS 数值验证，因为任务目标是流程和审查入口准备。

## 给审查的下一步问题

- 当前项目的核心代码结构是否足够清晰，便于后续逐轮修改？
- 当前验证资料是否足以支撑后续合并前判断？
- 是否需要把某些已有说明迁移到更稳定的 `notes/docs/` 或保留在现有专题目录中？
