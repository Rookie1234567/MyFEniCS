# V4-1 group lift identity

## 状态

`planned_not_run`。本页只冻结三种 trace 到三维 group 的对照，不宣称任何 lift 或 residual
结果。

## 固定对照

| 输入 trace | 目的 | 当前结果 |
|---|---|---|
| exact `t*` | 量化当前三维 lift 的 authority 上限 | `not_run` |
| Petrov `tP` | 测量 `G^{-1}Y^Ht*` 的 dual 投影损失 | `not_run` |
| metric-best `tB` | 与 dual 无关的 span 表示上限 | `not_run` |

三种输入必须使用同一 lower/upper owner-row ordering、同一 particular solve、同一 group
back-substitution。不得把 packet `U` 重新解释为 `Z`，也不得调用完整
`PetscInterfaceSchurOracle`。

## 数学与 Gate

```math
\frac{\lVert x_{lift}-x^\star\rVert_2}{\lVert x^\star\rVert_2}
\quad\text{and}\quad
\frac{\lVert b-F_bx_{lift}\rVert_2}{\lVert b\rVert_2}.
```

| Gate | frozen threshold | 当前结果 |
|---|---:|---|
| five solution relative errors | `<=1e-8` | `not_run` |
| five bare-F true residuals | `<=1e-9` | `not_run` |
| finite / repeat / linearity | true | `not_run` |
| factor lifecycle | `3→0`；full-side exact factor `0` | `not_run` |
| resource | peak `<45 GiB`；swap `0` | `not_run` |

正式 Gate 只使用 `F_b` true residual。只有 exact-trace lift identity 已按上述 §7.6 通过后，
才可根据 `tB` 与 `tP` 的差异分类：若 `tB` 也不能形成有效 lift，V4 分类优先为
`CURRENT_SPAN_INSUFFICIENT`；若 `tB` 有效而 `tP` 明显更差，才可标记
`DUAL_PROJECTION_INSUFFICIENT`。若 exact trace 本身未通过 §7.6，则必须先分类
`EXACT_TRACE_LIFT_IDENTITY_NOT_ESTABLISHED` 并停止，不得跳过该 Gate。
