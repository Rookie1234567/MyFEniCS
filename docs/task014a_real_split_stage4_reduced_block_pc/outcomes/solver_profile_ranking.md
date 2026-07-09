# Solver Profile Ranking

## 排名结论

本轮只比较 task14a 指定的两个最小 profile：

```text
stage4_real_split_fgmres_jacobi
stage4_real_split_fgmres_fe_ams_aux_identity
```

## 主结果表

| 排名 | case | profile | true residual | iter | status | 说明 |
|---:|---|---|---:|---:|---|---|
| 1 | tiny10 auto | Jacobi | 8.817e-7 | 39 | converged | 小矩阵太容易，Jacobi 已通过 |
| 2 | tiny10 auto | FE-AMS + aux identity | 9.601e-7 | 37 | converged | 迭代少 2 步，但 true residual 略差 |
| 3 | default100 auto | FE-AMS + aux identity | 2.147e-2 | 1000 | max_it | 比 Jacobi 好约 1.60x，但未收敛 |
| 4 | default100 auto | Jacobi | 3.436e-2 | 1000 | max_it | 不收敛 |
| 5 | default100 zero-order | Jacobi | 4.397e-1 | 1000 | max_it | local Robin 对照，不计入 Stage C 通过 |
| 6 | default100 zero-order | FE-AMS | 5.337e-1 | 1000 | max_it | local Robin 对照中更差 |

## 改善倍数

| case | residual(Jacobi) | residual(FE-AMS) | Jacobi / FE-AMS | 判断 |
|---|---:|---:|---:|---|
| tiny10 auto | 8.817e-7 | 9.601e-7 | 0.92x | 未改善 |
| default100 auto | 3.436e-2 | 2.147e-2 | 1.60x | 弱改善，不达 10x 门槛 |
| default100 zero-order | 4.397e-1 | 5.337e-1 | 0.82x | 更差 |

## 解释

`FE-AMS + aux identity` 已经能在 MPC 后构造并运行，但当前正 Maxwell same-H1 AMS 只作为 FE block 的近似逆，不能处理 Stage4 的 Helmholtz 不定性、Rayleigh/DtN 模态误差和 FE/aux 耦合。default100 auto-propagating case 的 708 个 DtN auxiliary unknowns 也说明后续不能继续把 aux block 当作普通 identity。

## 排名建议

| 下一步候选 | 优先级 | 原因 |
|---|---:|---|
| DtN-aware FE/aux Schur correction | 高 | 当前最大缺口是 FE/aux 耦合与 aux identity 太弱 |
| Rayleigh/Floquet modal deflation | 高 | 直接针对周期光栅慢模态和传播/近截止模式 |
| same-H1 AMS 作为组合 PC 的 FE 子块 | 中 | 数据可构造，但不能单独承担 Stage4 |
| 继续调 Jacobi/ASM/ILU 参数 | 低 | 过去 task009-task011 已显示黑盒 profile 不够 |
