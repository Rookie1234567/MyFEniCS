# V1-2 discrete interface Schur/Steklov oracle

状态：`not_run`。本页描述 scalar Krylov screen 未通过后才允许执行的离散接口 oracle；没有把 T40-3 的 scalar rho 当作 Schur 误差。

## 目的与冻结边界

接口 Schur/Steklov operator 用来回答“固定 scalar `q M_t` 缺少了哪些真实跨接口作用”，而不是重新求解完整 PDE。形式上只在接口自由度上比较

```math
S_\Gamma = A_{\Gamma\Gamma} - A_{\Gamma I}A_{II}^{-1}A_{I\Gamma}.
```

实现必须复用 inherited audit 的 frozen bare-F、三组 `[0,1]/[2,3]/[4,5]`、z 位置、六源 identity、external-key hash、complex128/MPI8/threads=1 和 fixed scalar baseline。只允许使用已有 exact cross-section factors 作为 action/projected oracle；不得生成 FE-sized dense Schur、复制完整 basis 或改变 F、DtN、QEP、M、normalization、sign 或 physical parameters。

## 独立 authority

lower interface 使用 uniform substrate 的 frozen transverse Fourier/Floquet basis；upper interface 使用 inherited M480 grating/air right/left QEP trace/traction basis。执行任何 action 前必须 hash-bind canonical mode/order、branch、polarization、beta、orientation 和 normalization，并从五个 frozen nonzero RHS 生成 physically induced traces。再使用固定 seed 的 modal combinations 与固定 seed 的 complement probes；不得从待验证的 scalar packet action 自产 expected value。

报告 lower/upper 分开的 scalar `Z0` 与 sampled `S_Gamma` relative error、projected rank、singular values、condition、`alpha/rho/correlation`、selected-mode-span projection error 和 complement-probe error。若无法从既有 artifacts 独立恢复 left/right trace/traction identity，这是契约 blocker，应停止并记录缺失字段；不得重跑 QEP、修改 M 或猜符号。

## Gate 与资源

本阶段仍要求 finite、exact source identity、factor inventory `3/0/0/0`（cross-section/full-side/global/nested）、cleanup `3 -> 0`、peak `<45 GiB`、swap `0`、PDE/QEP/KSP not run。不存在合格的 Schur oracle 之前，不得进入 V1-3。V1-2 当前未运行，lower/upper Schur error、mode-span coverage、complement coverage、rank 和 condition 均为 `not_run`。

禁止把 single scalar T40-3 负结果扩大为所有 transmission 机制失败，也禁止因为本页尚未运行就宣称 scalar、mode-aware、bounded patch 或 coarse 方法通过/失败。
