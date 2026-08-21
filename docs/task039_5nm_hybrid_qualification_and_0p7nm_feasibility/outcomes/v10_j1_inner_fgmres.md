# V10-4：J1-preconditioned side FGMRES bottom 诊断

## 这一步做了什么

J1 是六层逐层因子形成的固定线性 action。它不是完整 side operator 的逆，只作为右预条件器，帮助 flexible GMRES（FGMRES）尝试求解真实的

```math
A_{\mathrm{side}}x=b,\qquad A_{\mathrm{side}}=F-CH^{-1}D.
```

本次只运行 bottom、五个 mandatory RHS；每个 RHS 从零初值开始，在 0/4/8/16 记录独立 true residual。只有保守的逐 RHS 条件满足，才允许同一 KSP 继续到32。本次五个 RHS 均未获授权，因此32没有运行；这不是把16结果重复标成32。

## 身份与资源

| 字段 | 权威值 |
|---|---|
| source / method / schema | `c6ee5b4933d51e384be0ff483eae7bf52945e979` / `task039_v10_h4_j1_inner_fgmres` / `task039.v10.h4.j1_inner_fgmres.v1` |
| input | `input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat`；input SHA file `488067f7b03f24d2ede9f830334529411e428052a09de721059ca803cd6ed1da` |
| MPI / threads | 8 / 1 |
| exact holdout | frozen producer `7e5d9b57a10b1093f0cb062eaf7bc12797c47e1f`；catalog `a2a7fb6fb01df4f795d31ff94f6ac6adf957ac4fe4a5c1a8d05176e3d64c0384` |
| raw root | `results/task039_v10_h4_j1_inner_fgmres_mpi8_c6ee5b49`（ignored local raw） |
| worker / parent | worker exit 0；parent termination null；parent warning false；wall `300.860810 s` |
| resource authority | parent process-tree samples；construction/overall `23630049280 B = 22.0071983337 GiB`，retained `20867825664 B = 19.4346771240 GiB`，swap `0 B` |
| resource Gate | construction `<=45 GiB` pass；retained `<=30 GiB` pass；hard stop `48318382080 B`；PSS/USS `not_measured` |

V10 的45 GiB/30 GiB是本路线的 component Gate。run summary 中遗留的通用224 GB预算不是本次 authority，也不改变这里的裁决。

## 五个 mandatory RHS 的 true residual

数值均来自 `explicit_true_residual`，不是 PETSc reported residual。`r_0=1` 是零初值时的初始残差基线；不是 zero-map。`32` 的 `—` 表示 conditional-32 未授权。

| RHS | 0 | 4 | 8 | 16 | 条件32 | 16 checkpoint wall |
|---|---:|---:|---:|---:|---|---:|
| modal traction positive | 1.0000000000 | 0.9978292301 | 0.9976800874 | 0.9971014671 | — | 5.4885817460 s |
| modal traction negative | 1.0000000000 | 0.9985402273 | 0.9983000205 | 0.9981152471 | — | 5.3976719009 s |
| external DtN coupling | 1.0000000000 | 0.9985105758 | 0.9981784041 | 0.9979895526 | — | 5.3854644500 s |
| fixed random repeat 0 | 1.0000000000 | 0.9995553367 | 0.9992101130 | 0.9989785112 | — | 5.3784727430 s |
| fixed random repeat 1 | 1.0000000000 | 0.9995393321 | 0.9992146644 | 0.9989849199 | — | 5.3942959879 s |

所有 RHS 在16停止，KSP reason code 为 `-3`，raw 未提供 reason name；`ksp_breakdown=false`、iterations=16、`first_nonfinite_stage=null`。每个 RHS 的 J1 apply count=16、A-side total apply count=20、显式 A-side true-residual matvec count=4。raw 完整保存了每个 RHS 的17项 reported residual history（iteration 0–16）；最后一项分别为 `0.9971014671`、`0.9981152471`、`0.9979895526`、`0.9989785112`、`0.9989849199`。compact record 以 raw diagnostic SHA256 绑定该历史，没有把 reported residual 当作 true-residual Gate。

## 统一 Gate

| checkpoint | 五个 RHS齐全 | worst mandatory | preferred modal/external max | 结论 |
|---:|---|---:|---:|---|
| 4 | yes | 0.9995553367 | 0.9985402273 | fail（mandatory `<=1e-2`，preferred `<=1e-3`） |
| 8 | yes | 0.9992146644 | 0.9983000205 | fail（mandatory `<=1e-2`，preferred `<=1e-3`） |
| 16 | yes | 0.9989849199 | 0.9981152471 | fail（mandatory `<=1e-2`，preferred `<=1e-3`） |
| 32 | no，五项均未运行 | not available | not available | not run；`conditional32_not_authorized` |

因此没有首个统一通过 checkpoint，`preferred_inner_budget=not_applicable`，`numerical_gate_pass=false`，分类为 `J1_INNER_FGMRES_NUMERICAL_LIMIT_NOT_REACHED_BY_32`。该分类是 controlled numerical negative，不是资源停止，也不是 implementation failure：finite、无 breakdown、zero-map、生命周期与资源均通过，但真实 side residual 仍约为1。

physical RHS 输入范数为零，单独执行的 zero-map 输出 finite、norm=`0.0`、limit=`1e-13`，pass；它不计入五个 mandatory RHS。

## 生命周期与边界

构造期间保留真实 `system.A` 与 J1 六层 factors；显式 F/C/D/H 在 Krylov 前释放。五个 RHS 顺序完成后，J1 factors 从 ready=6 清到 after=0，C/D/F/H/system 与 collective cleanup 均完成。exact factor/global direct/nested KSP 均为0；side FGMRES KSP count=5。selected-mode packet=false，SGS/QEP/top/both/full/recovery 均未运行。

该结果关闭本轮 top/both/full lane；它没有证明 FGMRES 可在更大预算通过，也没有产生完整 workflow 结果。compact 唯一数字源是 [task039_v10_j1_inner_fgmres_v1.json](../../../benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/task039_v10_j1_inner_fgmres_v1.json)。raw diagnostic SHA256 为 `a333d3add806bca865282b28e165d07ac18b586d26c2ff61f28e66c1f229fdd3`，resolved config SHA256 为 `f965c38abea08bee0ff83a6603e336ca4823deb932af7064aed3c571f8f63883`。
