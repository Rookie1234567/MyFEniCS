# V4-1 exact trace representability

## 状态

`planned_not_run`。V4-0 只完成 identity audit；本页不预写 trace、projection 或 lift
通过，也没有加载 exact-output 数组或启动 MPI/PDE。

## 唯一问题

先用既有 hash-bound exact-side outputs 做诊断，分别回答：

1. `296 + 480` 当前接口 span 是否能表示正确的 lower/upper trace；
2. Petrov dual 是否造成额外投影误差；
3. 给定 trace 后，三分区 harmonic lift/back-substitution 是否仍不能恢复三维 side 解。

历史 exact spool 来自 `A_side = F - C H^{-1} D` 的 ResearchExactSideLuAction/Woodbury
路径；Review 正式残差必须另以当前 bare `F_b` 核验。两种 operator 的 hash、action 和
residual 不得混用。

## 计划计算与 Gate

| 项目 | V4-1 固定合同 | 当前结果 |
|---|---|---|
| authority | 五个冻结 label；metadata/hash 先核验 | `not_run` |
| projection | 当前 Petrov 与 interface-mass metric best 两种投影 | `not_run` |
| lift | exact trace、Petrov trace、best trace 三种同构 group back-sub | `not_run` |
| formal operator | `F_b` action/hash；A-side 仅解释字段 | `not_run` |
| Gate | five solution rel `<=1e-8`、bare-F residual `<=1e-9`、finite/repeat/linearity、factor `3→0`、full-side factor `0`、swap `0`、peak `<45 GiB` | `not_run` |

投影必须避免 normal equations。metric-best 使用稳定 complex QR/SVD；所有 trace 用 canonical
keys，不假设 PETSc global row 顺序稳定。

## 证据边界

若 exact authority 对 `A_side` 成立而对 `F_b` 不成立，分类为
`EXACT_AUTHORITY_NOT_COMPATIBLE_WITH_CURRENT_BARE_F`，不是通过调阈值或重建 factor 解决的
implementation bug。若 tiny/exact algebra 证明只是 orientation、owner 或 action 接线错误，
才可按 Review V4 §4 做最小修复并绑定新 SHA。
