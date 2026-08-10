# Markdown 公式与表格渲染标准

## 1. 目的

本标准用于避免 GitHub/ChatGPT 中出现以下问题：

```text
公式直接显示为 LaTeX 源码；
多行 $$ block 被 GFM 误解析；
独占一行的 = 或 - 被识别成 Setext 标题；
公式围栏缺失或配对错误；
普通代码块被误当作公式；
表格因单元格内的竖线而错列；
多行公式塞进表格后破坏整张表；
复制文档后只剩源码、没有可读结果。
```

Markdown 公式和表格的可渲染性属于交付 Gate。ChatGPT、Codex 和人工维护者均必须遵守。

本标准从 Task037b 起适用于所有新建 Markdown，以及以后被修改的历史 Markdown。
未被触碰的历史文档不要求一次性批量迁移；一旦修改，就必须把该文件中的 display math
迁移到本标准。

---

# 2. 独立公式

## 2.1 唯一正式格式

独立公式必须使用 GitHub 支持的 fenced `math` block：

````markdown
正文说明。

```math
S_m
=
G-P_bA_b^{-1}T_b-P_tA_t^{-1}T_t.
```

后续说明。
````

开始围栏必须写成：

```text
```math
```

结束围栏必须是独占一行的三个反引号。

`math` fence 是 GitHub 的数学公式围栏，不是普通代码块。围栏内部的 `=`、`-`、`_`、
`*` 和矩阵换行不会再被 GFM 抢先解释成标题、列表或强调语法。

## 2.2 禁止的新写法

新建或修改的正式 Markdown 不得使用以下 display math：

```text
$$ ... $$
\[ ... \]
普通 ``` 代码围栏包住 LaTeX
```

特别禁止多行：

````markdown
$$
A
=
B.
$$
````

原因是独占一行的 `=` 可能被 GitHub Flavored Markdown 解释成 Setext 一级标题，导致
公式前半段变成大标题、后半段变成原始 LaTeX。

同一行的历史 `$...$` 行内公式不受此禁令影响。

## 2.3 公式块布局

每个 fenced `math` block 前后必须有空行。公式内部可换行，但应保持一个清晰的数学对象。
长推导可以使用 `aligned`：

````markdown
```math
\begin{aligned}
r_b &= b_b-A_bu_b-T_ba,\\
r_t &= b_t-A_tu_t-T_ta,\\
r_m &= g_m-P_bu_b-P_tu_t-Ga.
\end{aligned}
```
````

一个公式块中不得混入普通段落、命令输出、文件路径或解释性列表。

## 2.4 展示 Markdown 语法本身

若文档需要展示 fenced `math` 的源码，外层必须使用四个反引号或更多，避免提前结束：

````markdown
````markdown
```math
A=B.
```
````
````

不得用与内部相同长度的围栏嵌套。

## 2.5 提交前检查

每个新增或修改的 Markdown 文件必须确认：

- `math` 开始与结束围栏成对；
- `math` fence 没有嵌套在普通三反引号围栏中；
- 正文中没有新引入的 display `$$`、`\[` 或 `\]`；
- 公式块前后有空行；
- LaTeX 命令在 GitHub math renderer 中可用；
- 下标、上标、括号和 `\left/\right` 成对；
- GitHub rendered view 中没有大标题、横线或原始 LaTeX 泄漏。

---

# 3. 行内公式

短公式使用单个 `$...$`，例如 `$M=120$`、`$p=6$` 和 `$h=10\,\mathrm{nm}$`。

行内公式必须保持短小。包含以下内容时改用 fenced `math`：

- 分式；
- 矩阵；
- 多行等式；
- 长下标；
- 分段函数；
- 三项以上的推导链。

不要把文件路径、命令参数、变量名或状态枚举误写成公式；这些内容使用反引号，例如：

```text
mode_count_per_direction
P6_P4_P2_FAMILY_CLOSED
--task037-f3-full
```

---

# 4. Markdown 表格

## 4.1 基本规则

每一行必须具有相同列数。表头、分隔行和数据行必须对齐。

表格单元格中不得放置 fenced `math` block，也不得放多行 display math。复杂公式应放在
表格前后，表格中只使用短名称、行内公式或符号引用。

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
| full 3D | 51,272 | 41,989,040 | static-condensed authority |
| Hybrid | 17,168 | 12,313,232 | M120 |
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

# 6. 提交前人工检查

每次新增或修改重要 Markdown 时：

1. 运行文档合同测试；
2. 检查本地 Markdown 预览；
3. 推送后检查 GitHub rendered view；
4. 检查 fenced `math` 是否显示为公式；
5. 检查公式中独占一行的 `=` 或 `-` 没有变成标题；
6. 检查表格是否错列；
7. 检查链接；
8. 检查普通代码围栏和 `math` 围栏是否闭合；
9. 在 `response` 或 `outcomes/test_summary.md` 中记录检查结果。

若 GitHub 页面显示原始 LaTeX、破损表格、异常大标题、错位列或未闭合围栏，该文档
不得标记为完成。

---

# 7. 自动合同要求

新任务的文档测试至少应检查：

- 新建或修改的正式 Markdown 不使用多行 `$$` display math；
- 不使用 `\[ ... \]` 作为 display math；
- fenced `math` 开始/结束配对；
- 必需表格存在；
- Markdown 本地链接可解析；
- protected work-principle clause 未被删除；
- 关键 summary 中存在数据身份和单位；
- 不在表格单元格中嵌入 fenced `math`；
- 普通代码围栏和 `math` 围栏均闭合；
- 关键文件不存在因独占 `=` / `-` 导致的 Setext 标题冲突。

自动检查不能替代 rendered view 人工检查。

---

# 8. 历史文档迁移边界

本标准不授权一次性批量改写整个仓库历史。迁移规则为：

```text
new file            -> 必须使用 fenced math
modified old file   -> 该文件的 display math 一并迁移
untouched old file  -> 可暂时保留，后续触碰时迁移
```

任何批量迁移都必须是独立 docs-only commit，并通过 rendered-view抽查；不得在同一提交中
混入数值代码、阈值或 candidate状态修改。
