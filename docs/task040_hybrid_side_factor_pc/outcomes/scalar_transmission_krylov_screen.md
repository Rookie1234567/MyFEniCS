# V1-1 scalar transmission Krylov screen

状态：`controlled_numerical_negative`。V1-1 已完成一次冻结 MPI8 formal；本页同时保留原测量合同与独立重算结果。

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

V1-1 的固定 scalar FGMRES 已被独立分类为 directional negative；这不等于完整任务失败，也不裁决 mode-aware V1-2。不得由该结果推断 damping、coarse information 或具体替代机制；不得翻 q/sign、调 beta 或重跑 T40-3。V1-2 在本阶段只冻结 probe manifest、实现和 focused tests，不运行真实 Schur action。

## V1-1 formal result

formal root 为 `results/task040_v1_1_scalar_krylov_mpi8_bf029cbd`，源码 SHA 为 `bf029cbdccd50538e91dac3d3452f3a3de62b767`。输入、physical model、selected packet、exact spool、MPI8/threads1 和 qualified ABI 与 inherited audit 完全一致；physical source 是独立 zero-map，不能代替非零 transmission source。

Raw 与 compact hashes 见 [V1-1 compact record](../../../benchmarks/cases/104_5nm_hybrid_side_factor_pc/records/task040_v1_1_scalar_krylov_v1.json) 及其 formal root 下的独立 checker 输出。

| source | r4 | r8 | r16 | original rho | rho* | abs correlation | alpha* (real, imag) | abs(alpha*) / phase(rad) | x/b | y/b |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|---:|
| modal_traction_positive | 0.9979658618002183 | 0.9962316286627299 | 0.9879466665843744 | 20.927172149775153 | 0.9989474352667872 | 0.04586961493088805 | (0.0021872128174471165, 0.00010158644016656518) | 0.002189570668791183 / 0.046412258791209325 | 21.83602321819345 | 20.949136552058274 |
| modal_traction_negative | 0.9977202949485113 | 0.9956117419256832 | 0.9848624636236449 | 20.882058201142698 | 0.9990590420499665 | 0.043370848483781504 | (0.002074731283816264, 0.00003402361259700503) | 0.0020750102424470186 / 0.0163975756182099 | 21.57825774146584 | 20.901510554779293 |
| external_dtn_coupling | 0.9986897773778267 | 0.9962299036800422 | 0.9904365341397463 | 22.72219234750837 | 0.9990272919856846 | 0.04409614345665071 | (0.0019387531625571462, -0.000009509388996094642) | 0.001938776483714514 / -0.004904859949048704 | 23.13388746983002 | 22.74431520448744 |
| fixed_random_repeat_0 | 0.9989148128555043 | 0.997516474863946 | 0.9936472443626956 | 27.16318768865547 | 0.9993421802029867 | 0.036265780939355854 | (0.0013305344614071423, -0.00009929711292695814) | 0.0013342345631963007 / -0.07449140347887952 | 61.51376485883753 | 27.180963482520884 |
| fixed_random_repeat_1 | 0.9988651958887255 | 0.9973661209073308 | 0.9936792642154975 | 26.589731276457666 | 0.9993651460722303 | 0.03562730436097847 | (0.0013373464768138732, -0.0000673997183337197) | 0.0013390438084984167 / -0.050355492706907076 | 61.6355288814672 | 26.606526339814362 |

`alpha*` is the independently recomputed complex coefficient `conj(BHYjj)/YHYjj`; the phase is in radians.
The full complex normalized B-vs-Y matrix is hash-bound in `checker_recomputed.json`; the absolute-value entries are recorded in the compact record.

All five phase-one `r16` values are at least 0.9, and the required 0.25-decade trend is not met. Therefore conditional phase two (32 steps) was not run; right-PC applies were 80, with one shared KSP setup and one destroy.

## Resource and lifecycle evidence

| item | measured result |
|---|---:|
| peak process-tree RSS | 29,839,409,152 B = 27.790115356445312 GiB |
| process-sample wall | 669.4473022361053 s |
| swap | 0 B |
| watchdog | natural exit, return code 0, hard stop 48,318,382,080 B |
| factors | 3 cross-section oracle factors ready → 0 after cleanup; full-side/global/nested 0/0/0 |
| KSP | setup/destroy 1/1 |
| PDE/QEP | not_run / 0 |

27.790115356445312 GiB is the V1-1 component peak, not a full-workflow saving tier. The inherited full-workflow comparison remains 93.377006531 GiB direct versus 80.025856018 GiB exact-side iterative; V1-1 does not establish a new workflow envelope.

## Independent Gate classification

The raw-report checker was run with `python -m benchmarks.check_task040_level_a --run-root results/task040_v1_1_scalar_krylov_mpi8_bf029cbd`. It recomputed contractions, alpha, rho, normalized cross-correlation, checkpoint status, lifecycle, and watchdog resource fields; worker status was not trusted. Identity, finite, zero-map, linearity/repeat, RP, interface mass/support, bare-F, factor, resource and lifecycle checks passed, but the numerical checkpoint Gate failed. Classification is `SCALAR_TRANSMISSION_DIRECTIONAL_FAIL`, not an implementation/resource failure: the fixed scalar transmission candidate is closed, while V1-2 mode-aware/interface-Schur research remains the next planned route.

The full 5x5 complex normalized B-vs-Y matrix is hash-bound in `checker_recomputed.json`; the absolute matrix, in source-label order, is recorded in the compact record.
