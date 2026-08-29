# Moving-PML sweep outcome

## 方法与边界

moving-PML 是 PC-only 的研究机制：在三个固定 z group 的人工边界增加两层、quadratic、
integrated attenuation=6 的临时吸收 collar，外层 bare `F` 不变。它必须通过五个冻结 source
的真实 residual 才能判定 signal；本轮没有到达第一个 source checkpoint。

## 首次运行：provider 接线失败

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_5e6ce061_native`，source
SHA=`5e6ce06194d182ce7ee5b0acdb2e4c550155895a`。实际命令为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_5e6ce061_native --source-sha 5e6ce06194d182ce7ee5b0acdb2e4c550155895a --v7-moving-pml-full-state --watchdog-enabled --bottom-route-only
```

watchdog worker natural exit、rc=`1`、
elapsed=`370.99143092300073 s`、peak RSS=`12805300224 B`、swap=`0`，没有 run summary。
首个具体错误为：

```text
RuntimeError: V5 internal modal sources require a runner-supplied hash-bound selected-mode provider
```

原因是 moving route 使用 `build_current_bare_f_rhs(modal±)`，但 system assembly 没有传既有
`_v5_selected_mode_provider(comm)`。`7b237ea6` 只复用该既有 provider 修复接线，没有改变
source、M480、物理或阈值。首 root watchdog SHA 为
`8d7477bdbbef7521017d2da24ca794edcdbfcea644f1800c12bf7e7e26cb91e0`，stdout SHA 为
`8509341768e011b020e141ed8847db0663b4b7bf9693912f655c26b73ecb6b76`，markers SHA 为
`7f9b3bdc024834eeb82d8b9b4db40135421f589acfaa1b5d85d32a8de27536ad`。

## 唯一 corrected formal：真实 wall/resource Gate

root：
`/home/fenics/Projects/MyFEniCS/results/task040_v7_moving_pml_mpi8_7b237ea6_native_rerun1`，
source SHA=`7b237ea653ea5afa0a731b30739663f0ea2374fc`。精确命令和全部 artifact hash 见
[Response V8](../response_v8.md)。

| 观测 | 值 |
|---|---:|
| outer / worker rc | `2 / 1` |
| termination | `wall_timeout` |
| elapsed / last authoritative sample | `21601.760233s / 21600.410422s` |
| peak process-tree RSS | `40560816128 B`（约 `37.78 GiB`） |
| peak swap / authoritative samples | `0 B / 34834` |
| hard stop / timeout | `45 GiB / 21600 s` |
| process group | 完整退出；`sigkill_required=false` |
| traceback | 无；仅已知 X11 authorization 噪声 |

阶段只到：identity/resource preflight → system ready → one-cell source factor `1→0` →
moving setup `factor_ready=3` → `v7_moving_pml_sources started`。因此没有 one-apply、
`r8/r16/r32/r64/r128`、FGMRES、classification 或 route signal；moving factors 的 `3→0`
和 cleanup/readback 也没有形成。watchdog 没有 `run_summary.json`、source manifest 或外部
checker output。

本次必须写成：

```text
classification = INCONCLUSIVE_RESOURCE_GATE
route signal   = SIGNAL_UNAVAILABLE
```

绝不写 `PML_SWEEP_NO_SIGNAL`、`PML_NO_SIGNAL` 或 positive。Review V7 §10.3 的真实
wall/resource Gate 独立满足本轮停止边界，因此 `adaptive_spectral_schwarz` 未启动，状态为
`NOT_RUN_DUE_TO_TRUE_RESOURCE_GATE`；这不是 adaptive negative。若 moving-PML 得到 valid
positive，按 Review 路由应进入 factor-free local service；本轮没有得到任何五源信号。
