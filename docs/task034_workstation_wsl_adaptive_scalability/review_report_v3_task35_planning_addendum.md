# Task034 Review V3：Task035 规划补充

本文件与 `review_report_v3.md` 共同构成 Task034 Review V3 权威。它只处理本轮由 ChatGPT 新增的 Task035 planning package，不改变 Task034 已接受的数值结论。

## 1. 已新增的 Task035 planning package

当前 Task034 执行分支已经新增：

```text
docs/task035_hcurl_goal_oriented_adaptivity/README.md
docs/task035_hcurl_goal_oriented_adaptivity/task.md
notes/theory/hcurl_adaptive_error_estimators_and_hp_strategy.md
notes/theory/README.md（索引更新）
```

这些文件是 Task035 的任务书和理论准备，不表示 Task035 已经启动。Task035 仍锁定到：

```text
Task034 final selective merge complete
```

之后才由 Codex 从 clean master 创建：

```text
codex/20260721-task35-hcurl-goal-oriented-adaptivity
```

Codex 在 Task034 `response_v4.md` 中必须：

1. 确认上述 planning package 已纳入最终文档/manifest 分组；
2. 不在 Task034 中执行 Task035 代码或重型 PDE；
3. 更新 roadmap、development progress、capability matrix 和 docs index，使 Task035 的定位一致；
4. 最终 selective merge 时将任务书、理论文档和索引作为 compact planning/docs 合入；
5. `src/geometry/task034_adaptive_mesh.py` 仍保持 research-only，不因 Task035 planning 而升级。

## 2. Markdown 公式检查

新理论文档中连续 Maxwell 方程的第一个 curl 项在当前 GitHub 文本中出现了转义缺失：

```text
abla\times
```

应修正为可渲染的：

```text
\nabla\times
```

Codex 必须检查整篇新理论文档的 GitHub rendered view，确认：

- 所有 `\nabla`、`\eta`、`\mathbf`、`\mathrm` 等 LaTeX 命令未被字符串转义破坏；
- 所有 `$$...$$` block 有完整开闭；
- 表格列数一致；
- DOI 链接有效；
- `notes/theory/README.md` 链接可达。

该修正只涉及文档，不要求重跑 PDE。

## 3. Response V4

`response_v4.md` 必须同时回应：

- `review_report_v3.md`；
- 本 planning addendum。

完成后停止等待最终 Review V4，不得自行合并 master。
