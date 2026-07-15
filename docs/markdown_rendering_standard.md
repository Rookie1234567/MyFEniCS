# Markdown 公式与表格渲染标准

## 1. 目的

本标准用于避免 GitHub/ChatGPT 中出现以下问题：

```text
公式直接显示为 LaTeX 源码；
$$ delimiter 缺失或配对错误；
公式被代码围栏包住而无法渲染；
表格因单元格内的竖线而错列；
多行公式塞进表格后破坏整张表；
复制文档后只剩源码、没有可读结果。
```

Markdown 公式和表格的可渲染性属于交付 Gate。ChatGPT、Codex 和人工维护者均必须遵守。

---

# 2. 独立公式

独立公式必须使用空行隔开的 `$$` block，开始和结束 delimiter 各自单独占一行：

```markdown
正文说明。

$$
S_m = H_m - D_b A_b^{-1} C_b - D_t A_t^{-1} C_t.
$$

后续说明。
```

不得写成需要渲染但被代码围栏包住的形式。代码围栏只用于展示命令、文件内容或解释 Markdown 语法本身。

不得混用未经过仓库验证的 display delimiter。项目正式文档统一使用 `$$`，不使用 `\[ ... \]` 作为默认写法。

每个 Markdown 文件提交前必须确认：

- `$$` delimiter 数量为偶数；
- delimiter 没有被意外放进普通代码围栏；
- 多行公式前后有空行；
- LaTeX 命令在目标渲染器中可用；
- 公式中的下标、上标、括号和 `\left/\right` 成对。

---

# 3. 行内公式

短公式可使用单个 `$...$`，例如 `$M=160$`。

行内公式必须保持短小。包含分式、矩阵、换行、长下标或多项等式时，应改为独立 `$$` block。

不要把文件路径、命令参数、变量名误写成公式；这些内容使用反引号，例如 `mode_count_per_direction`。

---

# 4. Markdown 表格

## 4.1 基本规则

每一行必须具有相同列数。表头、分隔行和数据行必须对齐。

表格单元格中不得直接放置多行 `$$` 公式。复杂公式应放在表格前后，并在表格中使用短名称或符号引用。

单元格内出现 Markdown 竖线时，必须：

- 使用 `\|` 转义；或
- 改写为 `\vert`；或
- 使用不含竖线的文字描述；或
- 把短代码放入反引号，并确认目标渲染器不会把其中竖线当分隔符。

推荐：表格中只放短公式、短变量名和数值；推导放在表格外。

## 4.2 推荐示例

```markdown
| 方法 | rows | NNZ | 说明 |
|---|---:|---:|---|
| full 3D | 198,518 | 21,317,860 | baseline |
| Hybrid | 68,796 | 8,594,673 | M160 |
```

不推荐把矩阵、分段函数或多行推导直接写进单元格。

---

# 5. 表格中的数据身份

从 Task032 起，中大型任务表格应标明：

```text
unit
baseline / denominator
measured / derived / predicted / not_run
evidence path
```

未运行项必须写 `not_run` 或更具体的 `not_run_by_memory_gate`，不能留空。

不同内存口径不得放在同一百分比比较中，除非表格明确说明 sampler 和分母。

---

# 6. 提交前检查

每次新增或修改重要 Markdown 时：

1. 运行文档合同测试；
2. 检查本地 Markdown 预览；
3. 推送后检查 GitHub rendered view；
4. 检查公式是否显示为公式；
5. 检查表格是否错列；
6. 检查链接；
7. 检查代码围栏是否闭合；
8. 在 `response` 或 `outcomes/test_summary.md` 中记录检查结果。

若 GitHub 页面显示原始 LaTeX、破损表格、错位列或未闭合代码块，该文档不得标记为完成。

---

# 7. 自动合同建议

新任务的文档测试至少应检查：

- `$$` delimiter 配对；
- 必需表格存在；
- Markdown 本地链接可解析；
- protected work-principle clause 未被删除；
- 关键 summary 中存在数据身份和单位；
- 不在表格单元格中嵌入多行 display math；
- 关键文件不存在未闭合 fenced code block。

自动检查不能替代 rendered view 人工检查。