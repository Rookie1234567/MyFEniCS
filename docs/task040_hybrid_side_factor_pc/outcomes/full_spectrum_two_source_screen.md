# V8 full-spectrum two-source screen outcome

## 当前正式裁决

| 项目 | 结果 |
|---|---|
| root | `results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1` |
| source SHA | `089bf8a10441b83c5d293a02d649670675b631ca` |
| user entry | `python -m benchmarks.task040_level_a_watchdog ... --v8-full-spectrum-only --watchdog-enabled --bottom-route-only` |
| watchdog | MPI8，natural rc0，elapsed=`1533.1877332139993s` |
| resource | peak RSS=`38975795200 B`=`36.29903793334961 GiB`，swap=`0` |
| transform identity | `PASS` |
| screen | `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` |
| numerical screen | orchestration 与两个 source 条目已形成；均在 owner-vector load 失败；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0`；r8/r16/r32/r64 未形成 |

full-spectrum 先验证“原始有限元行能否被稳定地放回完整的 channel/harmonic 网格”，再进入两源求解；这个 transform Gate 通过并不等于后面的屏幕求解通过。两源 orchestration 和 source entries 已建立，但都在 owner-vector load 处发现 live canonical tokens 与 persisted layout 不一致，随后按 implementation failure 停止。无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段形成且为 `0`；r8/r16/r32/r64 也未形成，不能写成 `FULL_SPECTRUM_NO_SIGNAL`。

正式用户入口为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1 --source-sha 089bf8a10441b83c5d293a02d649670675b631ca --v8-full-spectrum-only --watchdog-enabled --bottom-route-only
```

watchdog 内部的 MPI8 worker 命令可从 `watchdog_summary.json` 复核，不把内部 `mpiexec` 数组当成用户入口。

## Raw marker stage table

| raw marker | stage wall (s) | RSS (B) | swap | PC/action apply |
|---|---:|---:|---:|---:|
| `v8_full_spectrum_preflight` | `0.0` | `1641885696` | `0` | `0/0` |
| `v8_full_spectrum_system_ready` | `370.97334908600897` | `12480098304` | `0` | `0/0` |
| `v8_full_spectrum_group0_factor_ready` | `207.90935626099235` | `17674514432` | `0` | `0/0` |
| `v8_full_spectrum_group1_factor_ready` | `182.9128659699927` | `21893591040` | `0` | `0/0` |
| `v8_full_spectrum_group2_factor_ready` | `241.10231349102105` | `28171911168` | `0` | `0/0` |
| `v8_full_spectrum_lower_transform_ready` | `348.30305793098523` | `38749306880` | `0` | `0/0` |
| `v8_full_spectrum_upper_transform_ready` | `144.6964194290049` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_symbol_ready` | `0.13321249099681154` | `38749315072` | `0` | `0/0` |
| `v8_full_spectrum_cleanup_complete` | `17.90213303899509` | `38874349568` | `0` | `0/0` |

因此 transform PASS、screen implementation failure、两个 source entries/orchestration 已形成但 owner-vector load 失败、无 source begin/end raw marker、无 one-apply/FGMRES checkpoint、apply-count字段=`0` 这几件事必须分别引用。旧的几何 extent、empty-local probe 和 token/layout 失败 root 仍在 full-spectrum outcome 与 route ledger 中保留；本页不覆盖这些历史现场。
