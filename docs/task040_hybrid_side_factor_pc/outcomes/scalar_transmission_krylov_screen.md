# V1-1 scalar transmission Krylov screen

状态：`not_run`。本页冻结 V1-1 的问题、测量和停止规则，不把 T40-3 的一次作用 rho 当作 Krylov 结果。

## 继承身份

本阶段必须复用 [inherited audit](review_v1_inherited_audit.md) 中完全相同的 input、physical model、selected packet、external keys、bare-F、三组分区、两个 z 接口、scalar `q=-i beta`、六个 source 和 `[0,1,2,2,1,0]` sweep。T40-3 raw root 为 `results/task040_level_a_bare_f_mpi8_483275dc`，其 compact SHA256 为 `0dad8a259709efa3c147cb7248e5436013fb62d54ba31e6449612e90bc10bdce`；这些是 provenance，不是本阶段的数值通过。

## 最小测量

对每个五个非零 source `b`，先使用同一次 fixed scalar action 的 exact cross-section factors 得到
`y = F_b M_0^{-1} b`，再只计算一个最优复标量诊断：

```math
\alpha_* = \frac{y^H b}{y^H y},\qquad
\rho_* = \frac{\lVert b-\alpha_*y\rVert_2}{\lVert b\rVert_2},\qquad
c = \frac{|b^H y|}{\lVert b\rVert_2\lVert y\rVert_2}.
```

记录 `alpha_real`、`alpha_imag`、magnitude、phase、`rho_star`、correlation、原始未缩放 rho，以及五个 source 的 5×5 cross-correlation matrix。physical zero 仍单列为 zero-map，不伪造成非零 Krylov source。

随后只允许固定 right-FGMRES checkpoints `0/4/8/16`；只有 16 步全部 finite、最后 8 步 residual drop 至少 `0.25` decade、process-tree RSS `<45 GiB` 且 swap 为 0，才可运行唯一的 32-step checkpoint。不得扫描 restart、damping、tolerance、sweep 或 budget。

## Gate 与决策

首个 checkpoint 的 mandatory true residual 必须全部 `<=1e-2`，并且 modal+、modal−、external 三项必须 `<=1e-3`。若固定 scalar transmission 的 Krylov Gate 通过，分类为 `SCALAR_TRANSMISSION_KRYLOV_PASS`，直接进入 V1-5，同时保留 scalar transmission 证据；若 16 步没有持续下降或五项仍均 `>=0.9`，分类为 `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`，不运行 32，关闭 scalar candidate 但继续 V1-2；若唯一 32-step checkpoint 失败，分类为 `SCALAR_TRANSMISSION_KRYLOV_CAPACITY_FAIL`，同样关闭 scalar candidate 并继续 V1-2。

任何阶段都必须独立从 raw reports、FGMRES residual history、watchdog samples 和 factor inventory 重算，不采信 worker 自报的 `pass/status`。记录 action apply count、factor `3 -> 0`、full-side/global/nested `0/0/0`、bare-F hash、source identity、peak RSS、swap、wall 和 cleanup；不创建 FE-sized dense interface matrix。

## 当前边界

V1-1 尚未运行，因此不能声称 fixed scalar FGMRES 有能力、没有能力、需要 damping，或需要 coarse information。若身份、ABI、resource、finite、factor 或 residual Gate 失败，保留 raw，停止本依赖链并进入 V1-8 收口；不得翻 q/sign、调 beta 或重跑 T40-3。
