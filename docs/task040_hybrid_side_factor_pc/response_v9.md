# Task040 Review V8 response v9

## 当前 authority

这份 response 把“已经测到什么”和“没有测到什么”分开。所谓 local service，是只在边界附近解小块线性问题来帮助外层迭代；它减少单次内存，但不能自动证明完整物理求解成功。所谓 economical coarse，则是在这些局部响应上建立稀疏、分布式的粗空间；本轮正式运行在内存预估处停止，所以没有粗算子或外层残差。

| 项目 | 当前结论 | 证据边界 |
|---|---|---|
| V7 scale-normalized identity | Review V8 `review_adjudicated=true`；selected=`D0_lower_memory`；`V7_SCALE_NORMALIZED_FULL_INTERFACE_IDENTITY_PASS_D0` | raw 的 `formal_adjudication=false` 保持不改 |
| dedicated full-spectrum | `FULL_SPECTRUM_IMPLEMENTATION_FAILURE` | transform identity 通过（actual lower/upper=`7560+7560`，`72 channels × 105 harmonics`，`numeric_allgather=false`，`full_plane_numeric_replica=false`）；两个 source entries/orchestration 已形成，但 owner-vector load 失败；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0` |
| adaptive Stage A | `V8_ADAPTIVE_STAGE_A_LOCAL_GATE_PASS` | 630 patches 的 local service 通过；这是组件 Gate，`formal_adjudication=false`，不等于 outer numerical pass |
| exact generalized harmonic B1 | `not_completed_at_10800s` | root=`results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1`；wall timeout=`10800s`；无 run summary/数值结果；不是 numerical no-signal |
| adaptive Stage B/C | `ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE` | harmonic columns 已生成，但 conservative symbolic peak 超过 45 GiB；coarse allocation denied before source stage；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0` |
| Task040 状态 | `open / review required` | `selective merge=NO`；没有 Full3D handoff，也没有 0.7 nm physical infeasibility 结论 |

Git 身份（实现与正式运行）：`source HEAD/upstream/worktree=0ed2ebef3916fa209136310b104ec72b54f167d7 / 0ed2ebef3916fa209136310b104ec72b54f167d7 / clean`。Review V8 SHA=`0ce67c0c68c36e9677f3293a87c1c124e82c6f70`，`review_adjudicated=true`；raw `formal_adjudication=false` preserved；input SHA=`4e60924b5997e3ca99e324ea14779f9014efc6a1304a9aa11de9c808353f1811`，physical SHA=`8391d46139646440d869aa43abe6a68bc921fc1972a10030c64be81dffdd527c`。本次文档尚未提交；文档提交/推送后的最终 SHA 将在 Git 操作完成后另行报告，不在本文预填或自指。

## 正式证据索引

| 路线 | root / 关键文件 | 主要 SHA |
|---|---|---|
| full-spectrum | `results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1`；`worker/run_summary.json`、`memory_stage_markers.raw.jsonl` | run summary SHA `1dfe2cd4737cfac96bffe0e860340dd26f1d4c83a2f585a9f54d803837bc7ead`；watchdog SHA `553022bfe63724939dcb9dffd700c915a47434b32836792cb8984657dc9c0069`；raw marker SHA `ea4169bbfb8a26458e50e7e18f64aca8fda27ca4495826ec83c4038d0dc0388c` |
| adaptive Stage A | `results/task040_v8_adaptive_stage_a_mpi8_0b6c6a26_fix1` | source `0b6c6a26c75f29875c8f3139ada02f7cb08a1f98`；watchdog SHA `bab03ab534399b0870ffa55133aaf440f87ead32269766a07df0e532dd91926f`；run/manifest SHA `073789fa9783eab11d43cb83e9457f2610b5e3ac816494bf0e5abfd7f3fa3a23` |
| adaptive Stage B/C | `results/task040_v8_adaptive_stage_bc_mpi8_0ed2ebef_native`；`watchdog_summary.json`、`worker/run_summary.json`、`worker/v8_adaptive_stage_bc_manifest.json` | watchdog `cd3635f33c89b90d9ac2a509b70294e930f54c387817522044e5a71d0ba0e72a`；run/manifest `76b008ccbe761f73395bb4fc08543f9b9f415b3df0d9e3d922ce07451a0100c2` |

旧 full-spectrum/adaptive cache、marker 与 token 失败 root 均保留，未被当前结论覆盖。详细分类见 [route ledger](outcomes/route_signal_ledger.md)。

## Full-spectrum：transform 通过，numerical apply 未形成

用户入口命令（不是 watchdog 内部的 `mpiexec` 数组）为：

```text
python -m benchmarks.task040_level_a_watchdog --input /home/fenics/Projects/MyFEniCS/input/official/task039/5nm_p6h4_v4_1deg_hybrid_iterative_m480_mpi8.dat --exact-spool-root /home/fenics/Projects/MyFEniCS/results/task040_v5_2_fresh_bare_f_authority_mpi8_fd7bea41/worker/bare_f_authority --run-directory /home/fenics/Projects/MyFEniCS/results/task040_v8_full_spectrum_mpi8_089bf8a1_native_phase_repair1 --source-sha 089bf8a10441b83c5d293a02d649670675b631ca --v8-full-spectrum-only --watchdog-enabled --bottom-route-only
```

watchdog 内部为 MPI8；其内部命令可由 summary 复核。该 formal 的两个 source entries/orchestration 已形成，但均在 owner-vector load 抛出 implementation exception；因此无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0`、`r8/r16/r32/r64=null`，不能写成 numerical no-signal。

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

watchdog natural exit 的 elapsed=`1533.1877332139993s`，peak RSS=`38975795200 B`=`36.29903793334961 GiB`，swap=`0`。transform identity 与后续 screen implementation failure 是两个不同 Gate。

## Adaptive Stage A 与 Stage B/C

Stage A 的 630 个 one-cell patch 均为 432 rows，min/median/max=`432/432/432`，one-overlap、POU error=`0`、固定 PC shift=`0.1`。setup=`255.8505309909815s`，one-apply=`3.498585887020454s`；local residual ratio median=`0`、p90=`2.955562184972804e-15`、max=`4.401656276000086e-15`。global true residual relative=`2.390497409724407`，它不是 Stage-A local Gate，也不是 positive signal。watchdog elapsed=`648.611442990019s`，peak=`19211452416 B`=`17.892059326171875 GiB`，swap=`0`。

exact B1 root=`results/task040_v8_adaptive_stage_b1_mpi8_0e92079f_fix1` 达到 10800 s wall，没有 run summary 或数值结果；因此按 Review 只允许转 economical variant，不把它解释成 numerical no-signal。

corrected full-spectrum formal 的 implementation budget 已耗尽；按 Review V8 的路由裁决，随后切换到 adaptive，而不是再次猜测或重跑 full-spectrum。

Stage B/C final root 的 marker stage wall、资源和 apply count如下；所有列出的 marker swap=`0`、PC/action apply=`0`：

| marker | stage wall (s) | RSS (B) | swap | PC/action apply |
|---|---:|---:|---:|---:|
| `v8_adaptive_stage_bc_preflight` | `0.4432497579837218` | `1640165376` | `0` | `0/0` |
| `v8_adaptive_stage_bc_system_ready` | `135.29094206902664` | `12351209472` | `0` | `0/0` |
| `v8_adaptive_stage_bc_gamma_rhs_ready` | `1841.5527979590115` | `18695155712` | `0` | `0/0` |
| `v8_adaptive_stage_bc_factor_ready` | `140.34239087096648` | `19711967232` | `0` | `0/0` |
| `v8_adaptive_stage_bc_harmonic_columns_ready` | `307.40208898700075` | `19718201344` | `0` | `0/0` |
| `v8_adaptive_stage_bc_memory_preflight` | `0.18435753899393603` | `19658432512` | `0` | `0/0` |
| `v8_adaptive_stage_bc_coarse_ready` | `71.09255509404466` | `19682488320` | `0` | `0/0` |
| `v8_adaptive_stage_bc_classification` | `0.12693137297173962` | `19682488320` | `0` | `0/0` |
| `v8_adaptive_stage_bc_cleanup_complete` | `3.065563532989472` | `19672002560` | `0` | `0/0` |

630 patches、160 modes/patch、total coarse DoF=`100800`、570 factor classes、reuse saved=`60`、rows=`432`，factor nnz=`106375680`，owner loads=`[78,69,68,72,70,63,78,72]`，multi-RHS solves=`630`。`factor_bytes_global=0` 仅表示 release diagnostic matrices 后的字段，不表示 factor volume 为零或路线已经 factor-free。

### Factor inventory

| 路线 | mechanism/group factors ready | simultaneous_max | class_count | pre-cleanup ready | cleanup ready | full-side exact | global direct | group | QEP |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full-spectrum | `3` | `3` | n/a | n/a | `0` | `0` | `0` | `3` | `0` |
| adaptive Stage B/C | n/a | n/a | `570` | `570` | `0` | `0` | `0` | `0` | `0` |

adaptive BC 的 rows=`432`、factor nnz=`106375680`；`factor_bytes_global=0` 仍只表示 release 后诊断字段，不能当作 factor 内存为零。

| symbolic component | bytes |
|---|---:|
| P | `871970408` |
| P_H | `871718408` |
| F*P | `10653602408` |
| P_H*F*P | `24945446408` |
| PETSc sparse allocation overhead | `37342737632` |
| iterative vectors | `543312000` |
| MatProduct transient | `35599048816` |
| one-patch workspace | `15796544` |

live baseline=`19658432512 B`；conservative projected peak=`130502065136 B`=`121.539519295 GiB`（报告中约 `121.540 GiB`），hard=`48318382080 B`=`45 GiB`，headroom=`-82183683056 B`。这是 symbolic projection，不是实测峰值；实测 process-tree peak=`19786649600 B`=`18.427753448486328 GiB`。因此 `allocation_allowed=false`，P/P_H/FP/Ac/KSP 均为 `0`，没有 coarse action 或 outer solver；无 source begin/end raw marker、无 one-apply/FGMRES checkpoint，apply-count字段=`0`，也没有 positive/no-signal numerical classification。

BC watchdog natural rc=`0`，elapsed=`2504.0971691419836s`，4545 samples、terminal excluded=`2`，swap=`0`；cleanup complete，bare-F before/after 均为 `1cc07ab68ed747abfe7599ce1fdfeff95642653b29863d6f261e2fe9239d574f`。因此这是 Review V8 §12.2 的 resource Gate stop，不是方法的 numerical no-signal。

## 测试、合并与边界

仅采用已真实完成的本地 focused evidence；没有声明 full repository、MPI4 或 CI。测试/静态检查索引见 [test summary](outcomes/test_summary.md)。`0.7 nm` 为 `NOT_ESTABLISHED / resource-blocked`：没有 qualified factor-free h4 candidate、两源 checkpoint、h3 scaling 或 0.7 nm/2 TB PDE，不能写成物理不可行。2 TB 也不能全部当作 RSS；Review planning ceiling 仍为 1.5 TiB。

| 验证 | 结果 | 边界 |
|---|---|---|
| V8 §10.2 closeout contracts | `python -m pytest -q src/test/test_24_repository_work_principles.py src/test/test_25_benchmark_contract.py src/test/test_26_documentation_contract.py`；rc=`0`；`26 passed`、`0 failed`、`0 skipped`；pytest `0.54s`、shell 约 `1.683s` | qualified native activation；marker=`1`；repo `.venv` Python；PETSc `complex128`/`int32`；`mpi4py/petsc4py/slepc4py/dolfinx/basix` 原生栈；本地非 CI。X11 authorization warning 是非致命环境噪声；既有 touched focused tests 因代码 SHA 未变而复用，未重跑。 |

moving-PML owner-serial implementation 保持 retired，method family 没有被数值否定。master、Task39、物理方程、M480、physical DtN 和 ordinary defaults 未改变。当前建议是保留全部 raw/failure roots，等待 Review；`selective merge=NO`，Task040 仍 open，不创建 Full3D handoff。
