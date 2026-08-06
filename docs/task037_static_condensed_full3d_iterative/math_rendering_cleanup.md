# Task037 Markdown 数学公式渲染清理

## 目的

GitHub Markdown 统一使用：

- 行内公式：`$...$`；
- 独立公式块：单独成行的 `$$`；
- 普通正文中不再使用 `\(...\)` 或 `\[...\]`。

清理范围仅限：

```text
docs/task037_static_condensed_full3d_iterative/**/*.md
benchmarks/cases/100_static_condensed_full3d_iterative/**/*.md
```

不修改 fenced code blocks，也不触碰其他历史任务文档。

## 唯一执行命令

```bash
python scripts/fix_task37_markdown_math.py
python scripts/fix_task37_markdown_math.py --check
```

随后执行：

```bash
git diff --check
```

人工抽查至少以下文件在 GitHub 页面中的行内和块级公式：

```text
review_report_v1.md
review_report_v2.md
review_report_v3.md
review_report_v4.md
response_v3.md
task.md
candidate_f_p6_p4_p2_addendum.md
outcomes/p4_core_partial_condensation_controlled_negative.md
```

## 提交边界

公式清理必须形成单独的 docs-only commit：

```text
docs(task037): normalize GitHub math delimiters
```

禁止在同一提交中修改 Python 数值源码、测试阈值、candidate 状态或 ordinary defaults。

## Gate

```text
fix script exit                 = 0
--check exit                    = 0
git diff --check               = pass
remaining \[ \] \( \) in prose = 0
fenced code changes            = 0
```
