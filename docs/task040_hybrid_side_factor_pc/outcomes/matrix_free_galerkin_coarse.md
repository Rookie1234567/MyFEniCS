# V9-C1 matrix-free Galerkin coarse outcome

## 当前裁决

| 字段 | 值 |
|---|---|
| status | `not_run_by_numerical_gate` |
| reason | C0 worker 已形成 numerical no-signal；watchdog 仅留下 terminal resource metadata gap |
| watchdog raw next metadata (non-governing after numerical adjudication) | raw watchdog 写为 `V9_C1_MATRIX_FREE_GALERKIN_COARSE` |
| implementation decision | 本轮不实施、不测试、不启动 C1 |

worker 的 C0 one-apply 已给出 `rho_coarse=6.778773552009804`，这是已形成的数值 no-signal
证据；watchdog 的 `ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE`、
`v9_c0_resource_gate=false` 和 `swap_authority_readable=false` 只说明 terminal resource
authority 未闭合。Review §5.5 在 C0 numerical no-signal 后禁止运行同 basis 的 C1；旧
`next_required_stage=V9_C1_MATRIX_FREE_GALERKIN_COARSE` 作为 raw 字段保留，不转化为待执行任务。

## 预期数学合同（不是结果）

C1 的目标是只保留一个分布式稀疏 prolongation `P`，用 MatShell 对粗向量进行一次“送到细空间—施加裸算子—送回粗空间”的计算：

```math
A_c c = P^H F(Pc)
```

其中 `F` 是 current bare-F action；`P^H` 表示 P 的伴随 action，而不是必须物化的 `P_H` 矩阵。首版应禁止显式 `P_H`、`F*P`、`P_H*F*P`、PETSc `MatProduct` transient、global/coarse direct factor、FE numeric allgather 和 full-basis rank replication。

| Gate | 计划口径 |
|---|---|
| operator | current bare-F，external source only；不重建 physical DtN |
| action | `P.mult(c, fine_work_0)` → `F.mult(fine_work_0, fine_work_1)` → `P.multHermitian(fine_work_1, coarse_y)` |
| tiny identity | serial/MPI2 explicit reference relative `≤1e-10` |
| repeat/linearity/adjoint | 分别 `≤1e-11`；复数 scalar 保持 complex128 |
| coarse KSP | GMRES、PC NONE、zero initial；8 步，按既定条件至16，条件满足才至32 |
| resource | preferred RSS `≤35 GiB`，hard RSS `45 GiB`，swap `0`；setup `3600s`，one-apply `1800s` |

这些只是若获批后的设计合同，不能在当前文档中写成 measured C1 result。C1 若未来获批，必须同时报告 P ownership、实际 vector inventory、MatShell lifecycle、one composite apply 和 full explicit residual；coarse recurrence checkpoint 不能代替 true residual。

## 当前不做

不做 C2、five-source、top/both-side/full Hybrid、参数扫描、重跑 C0、full-spectrum、LOR、MPI4/8 formal、0.7 nm PDE、文档之外的代码改动或 Git 操作。
